"""Synthetic-only tests for the Dataset 2 Phase 1 Version 1 runner."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import (
    DATASET2_STRICT_BUST_OR_DECREASE_GATE,
    DATASET2_STRICT_BUST_OR_INCREASE_GATE,
)
from lib.dataset2.phase1_runner import (
    PRIMARY_TARGETS,
    EvidenceStatus,
    ModelResult,
    PredictorDefinition,
    _fit_firth,
    _fit_lwi,
    _prepare_firth_bootstrap_design,
    apply_primary_family_fdr,
    assemble_results,
    discovery_fit_rows,
    incremental_validation,
    null_centered_bootstrap_p_value,
    null_centered_joint_bootstrap_p_value,
    resolve_categorical_references,
    run_phase1,
    strict_bust_practical_effect_passes,
    validate_predictor_definitions,
)
from lib.dataset2.phase1_analysis import BootstrapReplicateError


def _synthetic_rows() -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(20260808)
    for season in range(2010, 2021):
        for player_number in range(36):
            trait = rng.normal() + 0.03 * (season - 2010)
            rows.append({
                "prediction_season": season,
                "player_id": f"player_{player_number:02d}",
                "position": ("QB", "RB", "WR", "TE")[player_number % 4],
                "preseason_market_status": "ordinary_market",
                "adp_round": 1 + player_number % 15,
                "trait": trait,
                "trait_category": ("low", "middle", "high")[player_number % 3],
                "lwi_score": 8.0 * trait + rng.normal(scale=2.0),
                "star_by_value_label": int(rng.random() < 0.16 + 0.02 * (trait > 0)),
                "star_outcome_eligible": True,
                "bust_strict_below_replacement_label": int(rng.random() < 0.20 - 0.02 * (trait > 0)),
                "bust_strict_below_replacement_eligible": True,
            })
    return pd.DataFrame(rows)


def _predictor(kind: str = "continuous") -> PredictorDefinition:
    column = "trait_category" if kind == "categorical" else "trait"
    return PredictorDefinition(
        column=column,
        kind=kind,
        cluster_id="cluster_001",
        is_cluster_representative=True,
        reference_level="low" if kind == "categorical" else None,
    )


def _formal_evidence() -> EvidenceStatus:
    return EvidenceStatus(300, 30, 270, 11, 0.1, ())


def _model_result(family: str, predictor: PredictorDefinition, p: float) -> ModelResult:
    practical = None if family == "star" else True
    return ModelResult(
        family=family,
        predictor=predictor,
        contrast_names=("contrast_a", "contrast_b"),
        estimates=(1.1, 0.9),
        native_effects=(1.1, 0.9),
        raw_outcome_effects=(0.1, -0.1),
        confidence_intervals=((0.8, 1.4), (0.7, 1.2)),
        probability_differences=(0.01, -0.01),
        primary_p_value=p,
        evidence=_formal_evidence(),
        practical_effect_passes=practical,
        bootstrap_attempted=2000,
        bootstrap_successful=2000,
        bootstrap_failure_counts=(),
    )


def test_null_centered_bootstrap_p_value_uses_two_sided_finite_correction():
    # Centered draws are [0, -1, 2, -2]; two are at least as extreme as |2|.
    assert null_centered_bootstrap_p_value(2.0, [2.0, 1.0, 4.0, 0.0]) == pytest.approx(3 / 5)
    # The finite correction prevents a zero p-value.
    assert null_centered_bootstrap_p_value(10.0, [9.0, 10.0, 11.0]) == pytest.approx(1 / 4)


def test_joint_bootstrap_returns_one_finite_corrected_p_value():
    draws = [[0.8, -0.1], [1.2, 0.2], [0.9, 0.0], [1.1, 0.1]]
    value = null_centered_joint_bootstrap_p_value([1.0, 0.1], draws)
    assert 1 / 5 <= value <= 1
    with pytest.raises(ValueError, match="coefficient vector"):
        null_centered_joint_bootstrap_p_value([1.0], [[0.9], [1.1]])


def test_strict_bust_gate_uses_exact_reciprocal_boundaries():
    assert DATASET2_STRICT_BUST_OR_INCREASE_GATE == 1.20
    assert DATASET2_STRICT_BUST_OR_DECREASE_GATE == 1 / 1.20
    assert DATASET2_STRICT_BUST_OR_DECREASE_GATE != 0.83
    assert strict_bust_practical_effect_passes([1.20])
    assert strict_bust_practical_effect_passes([1 / 1.20])
    assert not strict_bust_practical_effect_passes([1.20 - 1e-10])
    assert not strict_bust_practical_effect_passes([1 / 1.20 + 1e-10])


def test_discovery_selection_is_eligible_2010_2020_and_rejects_holdout():
    rows = _synthetic_rows()
    rows.loc[rows.index[0], "star_outcome_eligible"] = False
    selected = discovery_fit_rows(rows, PRIMARY_TARGETS[1], "trait")
    assert selected["prediction_season"].min() == 2010
    assert selected["prediction_season"].max() == 2020
    assert not selected.index.isin([rows.index[0]]).any()

    holdout = pd.concat([rows, rows.iloc[[0]].assign(prediction_season=2021)])
    with pytest.raises(ValueError, match="protected holdout/application"):
        discovery_fit_rows(holdout, PRIMARY_TARGETS[1], "trait")


@pytest.mark.parametrize("bad_season", [None, "not-a-season", 2010.5, True])
def test_discovery_selection_rejects_invalid_seasons(bad_season):
    rows = _synthetic_rows()
    rows["prediction_season"] = rows["prediction_season"].astype(object)
    rows.loc[rows.index[0], "prediction_season"] = bad_season
    with pytest.raises(ValueError, match="seasons"):
        discovery_fit_rows(rows, PRIMARY_TARGETS[1], "trait")


def test_discovery_selection_rejects_ambiguous_eligibility_literals():
    rows = _synthetic_rows()
    rows["star_outcome_eligible"] = rows["star_outcome_eligible"].astype(object)
    rows.loc[rows.index[0], "star_outcome_eligible"] = "False"
    with pytest.raises(ValueError, match="eligibility column"):
        discovery_fit_rows(rows, PRIMARY_TARGETS[1], "trait")


def test_predictor_registry_blocks_outcomes_and_requires_categorical_reference():
    with pytest.raises(ValueError, match="outcome/leakage"):
        validate_predictor_definitions(
            [PredictorDefinition("star_by_value_label", "binary", "c", True)],
            ["star_by_value_label"],
        )
    with pytest.raises(ValueError, match="explicit reference"):
        validate_predictor_definitions(
            [PredictorDefinition("trait_category", "categorical", "c", True)],
            ["trait_category"],
        )
    with pytest.raises(ValueError, match="exactly one representative"):
        validate_predictor_definitions(
            [PredictorDefinition("trait", "continuous", "c", False)],
            ["trait"],
        )


def test_fixed_status_references_are_resolved_and_audited():
    rows = pd.DataFrame({
        "prediction_season": [2010, 2011, 2012, 2013, 2014],
        "fam9_team_game_window_status": [
            "applicable", "applicable", "unavailable_traded", "applicable", None,
        ],
        "fam10_depth_chart_status": ["starter", "backup", "deeper", "starter", "backup"],
    })
    predictors = [
        PredictorDefinition("fam9_team_game_window_status", "categorical", "c1", True),
        PredictorDefinition("fam10_depth_chart_status", "categorical", "c2", True),
    ]
    resolved, records = resolve_categorical_references(rows, predictors)
    assert [predictor.reference_level for predictor in resolved] == ["applicable", "starter"]
    assert [(record.reference_level, record.reference_frequency, record.eligible_nonnull_n) for record in records] == [
        ("applicable", 3, 4),
        ("starter", 2, 5),
    ]
    assert all(record.selection_method == "fixed_governed_status_reference" for record in records)


def test_team_reference_uses_frequency_then_alphabetical_tiebreak():
    rows = pd.DataFrame({
        "prediction_season": [2010, 2011, 2012, 2013, 2014, 2015],
        "fam10_depth_chart_team": ["CIN", "CIN", "BUF", "CIN", "BUF", None],
        "fam4_nfl_draft_team": ["SEA", "ARI", "SEA", "ARI", None, None],
    })
    predictors = [
        PredictorDefinition("fam10_depth_chart_team", "categorical", "c1", True),
        PredictorDefinition("fam4_nfl_draft_team", "categorical", "c2", True),
    ]
    resolved, records = resolve_categorical_references(rows, predictors)
    assert [predictor.reference_level for predictor in resolved] == ["CIN", "ARI"]
    assert records[0].reference_frequency == 3
    assert records[0].reference_share == pytest.approx(3 / 5)
    assert records[1].reference_frequency == 2
    assert records[1].selection_method == "most_frequent_discovery_category_alphabetical_tiebreak"


def test_absent_fixed_status_reference_fails_loudly():
    rows = pd.DataFrame({
        "prediction_season": [2010, 2011],
        "fam10_depth_chart_status": ["backup", "deeper"],
    })
    predictor = PredictorDefinition("fam10_depth_chart_status", "categorical", "c", True)
    with pytest.raises(ValueError, match="governed categorical reference is absent"):
        resolve_categorical_references(rows, [predictor])


def test_team_reference_with_no_eligible_values_fails_loudly():
    rows = pd.DataFrame({
        "prediction_season": [2010, 2011],
        "fam4_nfl_draft_team": [None, None],
    })
    predictor = PredictorDefinition("fam4_nfl_draft_team", "categorical", "c", True)
    with pytest.raises(ValueError, match="cannot be derived"):
        resolve_categorical_references(rows, [predictor])


def test_missing_categorical_predictor_column_fails_loudly():
    rows = pd.DataFrame({
        "prediction_season": [2010, 2011],
        "fam10_depth_chart_status": ["starter", "backup"],
    })
    predictor = PredictorDefinition("fam9_team_game_window_status", "categorical", "c", True)
    with pytest.raises(ValueError, match="absent from Phase 1 rows"):
        resolve_categorical_references(rows, [predictor])


def test_declared_reference_conflicting_with_governed_reference_fails_loudly():
    rows = pd.DataFrame({
        "prediction_season": [2010, 2011, 2012],
        "fam9_team_game_window_status": ["applicable", "applicable", "unavailable_traded"],
    })
    predictor = PredictorDefinition(
        "fam9_team_game_window_status", "categorical", "c", True,
        reference_level="unavailable_traded",
    )
    with pytest.raises(ValueError, match="disagrees with governed reference"):
        resolve_categorical_references(rows, [predictor])


def test_joint_categorical_lwi_test_is_reference_invariant():
    rows = _synthetic_rows()
    outcome_sd = float(rows["lwi_score"].std(ddof=1))
    low = _fit_lwi(rows, PRIMARY_TARGETS[0], _predictor("categorical"), outcome_sd)
    middle_predictor = PredictorDefinition(
        "trait_category", "categorical", "cluster_001", True, reference_level="middle",
    )
    middle = _fit_lwi(rows, PRIMARY_TARGETS[0], middle_predictor, outcome_sd)
    assert low.primary_p_value == pytest.approx(middle.primary_p_value, rel=1e-10, abs=1e-12)


def test_joint_categorical_firth_bootstrap_test_is_reference_invariant():
    rows = _synthetic_rows()
    rng = np.random.default_rng(99)
    probabilities = rows["trait_category"].map({"low": 0.08, "middle": 0.22, "high": 0.38})
    rows["star_by_value_label"] = (rng.random(len(rows)) < probabilities).astype(int)
    low = _fit_firth(
        rows, PRIMARY_TARGETS[1], _predictor("categorical"),
        replicates=20, seed=20260808, minimum_success_rate=0.99,
    )
    middle_predictor = PredictorDefinition(
        "trait_category", "categorical", "cluster_001", True, reference_level="middle",
    )
    middle = _fit_firth(
        rows, PRIMARY_TARGETS[1], middle_predictor,
        replicates=20, seed=20260808, minimum_success_rate=0.99,
    )
    assert low.primary_p_value == middle.primary_p_value


def test_continuous_lwi_fit_reports_standardized_and_native_effects():
    rows = _synthetic_rows()
    outcome_sd = float(rows["lwi_score"].std(ddof=1))
    result = _fit_lwi(rows, PRIMARY_TARGETS[0], _predictor(), outcome_sd)
    assert result.family == "lwi"
    assert result.estimates[0] == pytest.approx(result.raw_outcome_effects[0] / outcome_sd)
    assert result.native_effects[0] == pytest.approx(
        result.raw_outcome_effects[0] / rows["trait"].std(ddof=1)
    )
    assert result.practical_effect_passes
    assert np.isfinite(result.primary_p_value)


def test_categorical_firth_has_one_joint_p_and_descriptive_contrasts():
    rows = _synthetic_rows()
    result = _fit_firth(
        rows,
        PRIMARY_TARGETS[1],
        _predictor("categorical"),
        replicates=20,
        seed=20260808,
        minimum_success_rate=0.99,
    )
    assert result.contrast_names == ("trait_category_high", "trait_category_middle")
    assert len(result.estimates) == 2
    assert 0 <= result.primary_p_value <= 1
    assert result.bootstrap_successful >= 20 * 0.99


def test_bootstrap_design_drops_only_all_zero_nuisance_and_uses_local_map():
    schema = type("Schema", (), {
        "predictor_columns": ("trait",),
        "control_columns": ("control_zero", "control_live"),
    })()
    design = pd.DataFrame({
        "const": [1.0, 1.0, 1.0, 1.0],
        "trait": [-1.0, 0.0, 1.0, 2.0],
        "control_zero": [0.0, 0.0, 0.0, 0.0],
        "control_live": [0.0, 1.0, 0.0, 1.0],
    })
    reduced, local = _prepare_firth_bootstrap_design(design, np.array([0, 1, 0, 1]), schema)
    assert tuple(reduced.columns) == ("const", "trait", "control_live")
    assert local["trait"] == 1


def test_bootstrap_design_never_drops_absent_tested_contrast():
    schema = type("Schema", (), {
        "predictor_columns": ("trait",), "control_columns": ("control",),
    })()
    design = pd.DataFrame({"const": [1.0, 1.0], "trait": [0.0, 0.0], "control": [0.0, 1.0]})
    with pytest.raises(BootstrapReplicateError) as error:
        _prepare_firth_bootstrap_design(design, np.array([0, 1]), schema)
    assert error.value.category == "missing_predictor_contrast"


@pytest.mark.parametrize(
    ("design", "category"),
    [
        (pd.DataFrame({"const": [1.0, 1.0], "trait": [0.0, 1.0], "duplicate": [0.0, 1.0]}), "rank_failure"),
        (pd.DataFrame({"const": [1.0, 1.0], "trait": [0.0, np.inf]}), "non_finite_likelihood"),
    ],
)
def test_bootstrap_design_classifies_rank_and_nonfinite_failures(design, category):
    schema = type("Schema", (), {
        "predictor_columns": ("trait",), "control_columns": tuple(c for c in design if c != "trait"),
    })()
    with pytest.raises(BootstrapReplicateError) as error:
        _prepare_firth_bootstrap_design(design, np.array([0, 1]), schema)
    assert error.value.category == category


def test_categorical_predictor_enters_bh_once_not_once_per_contrast():
    categorical = _predictor("categorical")
    other = PredictorDefinition("trait", "continuous", "cluster_002", True)
    results = [_model_result("star", categorical, 0.02), _model_result("star", other, 0.04)]
    q_values = apply_primary_family_fdr(results)
    assert set(q_values) == {("star", "trait_category"), ("star", "trait")}
    assembled = assemble_results(results)
    assert len(assembled) == 2
    assert tuple(assembled.loc[0, "contrast_names"]) == ("contrast_a", "contrast_b")


def test_lwi_incremental_validation_reports_three_descriptive_metrics():
    rows = _synthetic_rows()
    result = incremental_validation(rows, PRIMARY_TARGETS[0], _predictor())
    assert result.folds == 6
    assert set(result.metrics) == {
        "mae_improvement", "rmse_improvement", "out_of_window_r2_improvement",
    }
    assert all(np.isfinite(value) for value in result.metrics.values())


def test_run_rejects_holdout_before_reading_outcomes():
    holdout_only = pd.DataFrame({"prediction_season": [2021]})
    with pytest.raises(ValueError, match="protected holdout/application"):
        run_phase1(holdout_only, [], [], synthetic_test_mode=True)


def test_run_rejects_nonfrozen_operational_settings_outside_synthetic_mode():
    rows = _synthetic_rows()
    with pytest.raises(ValueError, match="synthetic tests"):
        run_phase1(rows, [], [], bootstrap_replicates=5)


def test_end_to_end_runner_assembles_three_primary_families_from_synthetic_rows():
    package = run_phase1(
        _synthetic_rows(),
        [_predictor()],
        ["trait"],
        bootstrap_replicates=5,
        minimum_success_rate=0.8,
        synthetic_test_mode=True,
    )
    assert set(package.primary_results["family"]) == {"lwi", "star", "strict_bust"}
    assert len(package.incremental_results) == 3
    assert len(package.robustness_results) == 3
    assert set(package.primary_results["predictor_column"]) == {"trait"}
    assert package.categorical_references == ()


def test_phase1_runner_module_has_no_artifact_loader_or_repository_path():
    from lib.dataset2 import phase1_runner

    source = open(phase1_runner.__file__, encoding="utf-8").read()
    assert "read_csv" not in source
    assert "read_parquet" not in source
    assert "data/" not in source
