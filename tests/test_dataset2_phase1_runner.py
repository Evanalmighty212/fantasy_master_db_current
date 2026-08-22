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
    _design,
    _fit_firth,
    _fit_lwi,
    _binary_target_bootstrap_feasibility,
    _firth_point_estimates,
    _firth_termination_diagnostics,
    _prepare_firth_bootstrap_design,
    _prepare_firth_bootstrap_matrix,
    apply_primary_family_fdr,
    assemble_results,
    discovery_fit_rows,
    incremental_validation,
    null_centered_bootstrap_p_value,
    null_centered_joint_bootstrap_p_value,
    preflight_phase1_estimability,
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


def test_cached_numeric_firth_matches_legacy_coefficients_and_final_result():
    rows = _synthetic_rows()
    optimized = _fit_firth(
        rows, PRIMARY_TARGETS[1], _predictor(),
        replicates=20, seed=20260808, minimum_success_rate=0.99,
    )
    legacy = _fit_firth(
        rows, PRIMARY_TARGETS[1], _predictor(),
        replicates=20, seed=20260808, minimum_success_rate=0.99,
        _legacy_bootstrap_for_test=True,
    )
    assert optimized == legacy


def test_phase1_checkpoint_resume_matches_uninterrupted_final_outputs(tmp_path):
    rows = _synthetic_rows()
    predictor = _predictor()
    interrupted = {"raised": False}
    def stop_once(_record):
        if not interrupted["raised"]:
            interrupted["raised"] = True
            raise RuntimeError("synthetic interruption")
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        run_phase1(
            rows, [predictor], [predictor.column], bootstrap_replicates=4,
            minimum_success_rate=0.5, synthetic_test_mode=True,
            checkpoint_root=tmp_path / "resume", progress=stop_once,
        )
    resumed = run_phase1(
        rows, [predictor], [predictor.column], bootstrap_replicates=4,
        minimum_success_rate=0.5, synthetic_test_mode=True,
        checkpoint_root=tmp_path / "resume",
    )
    uninterrupted = run_phase1(
        rows, [predictor], [predictor.column], bootstrap_replicates=4,
        minimum_success_rate=0.5, synthetic_test_mode=True,
        checkpoint_root=tmp_path / "fresh",
    )
    pd.testing.assert_frame_equal(resumed.primary_results, uninterrupted.primary_results)
    assert resumed.incremental_results == uninterrupted.incremental_results
    assert resumed.robustness_results == uninterrupted.robustness_results
    assert resumed.categorical_references == uninterrupted.categorical_references


def test_bootstrap_design_drops_all_zero_nuisance_and_uses_local_map():
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
    reduced, local, diagnostics = _prepare_firth_bootstrap_design(
        design, np.array([0, 1, 0, 1]), schema,
    )
    assert tuple(reduced.columns) == ("const", "trait", "control_live")
    assert local["trait"] == 1
    assert diagnostics["nuisance_control_nonzero_support"] == {
        "control_zero": 0, "control_live": 2,
    }
    assert diagnostics["dropped_nuisance_columns"] == ("control_zero",)
    numeric, numeric_local, numeric_diagnostics = _prepare_firth_bootstrap_matrix(
        design.to_numpy(float), np.array([0, 1, 0, 1]), tuple(design.columns), schema,
    )
    np.testing.assert_array_equal(numeric, reduced.to_numpy(float))
    assert numeric_local == local
    assert numeric_diagnostics == diagnostics


def test_bootstrap_design_deterministically_reduces_exhaustive_nuisance_dummies():
    schema = type("Schema", (), {
        "predictor_columns": ("trait",),
        "control_columns": ("acquisition_a", "acquisition_b"),
    })()
    design = pd.DataFrame({
        "const": [1.0] * 6,
        "trait": [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0],
        "acquisition_a": [1.0, 1.0, 0.0, 0.0, 1.0, 0.0],
        "acquisition_b": [0.0, 0.0, 1.0, 1.0, 0.0, 1.0],
    })
    target = np.array([0, 1, 0, 1, 0, 1])

    reduced, local, diagnostics = _prepare_firth_bootstrap_design(design, target, schema)
    assert tuple(reduced.columns) == ("const", "trait", "acquisition_b")
    assert local == {"const": 0, "trait": 1, "acquisition_b": 2}
    assert diagnostics["dropped_nuisance_columns"] == ("acquisition_a",)
    original_nuisance = design[["const", "acquisition_a", "acquisition_b"]].to_numpy()
    reduced_nuisance = reduced[["const", "acquisition_b"]].to_numpy()
    assert np.linalg.matrix_rank(original_nuisance) == np.linalg.matrix_rank(reduced_nuisance)
    assert np.linalg.matrix_rank(
        np.column_stack([original_nuisance, reduced_nuisance])
    ) == np.linalg.matrix_rank(original_nuisance)

    numeric, numeric_local, numeric_diagnostics = _prepare_firth_bootstrap_matrix(
        design.to_numpy(float), target, tuple(design.columns), schema,
    )
    np.testing.assert_array_equal(numeric, reduced.to_numpy(float))
    assert numeric_local == local
    assert numeric_diagnostics == diagnostics


def test_bootstrap_design_does_not_remove_intercept_or_predictor_involved_dependency():
    schema = type("Schema", (), {
        "predictor_columns": ("trait",),
        "control_columns": ("const", "control_duplicate_of_trait"),
    })()
    design = pd.DataFrame({
        "const": [1.0, 1.0, 1.0, 1.0],
        "trait": [0.0, 1.0, 0.0, 1.0],
        "control_duplicate_of_trait": [0.0, 1.0, 0.0, 1.0],
    })
    with pytest.raises(BootstrapReplicateError) as error:
        _prepare_firth_bootstrap_design(design, np.array([0, 1, 0, 1]), schema)
    assert error.value.category == "rank_failure"
    assert error.value.diagnostics["dropped_nuisance_columns"] == ()
    assert error.value.diagnostics["reduced_design_column_count"] == 3


def test_bootstrap_design_is_unchanged_when_no_nuisance_reduction_is_needed():
    schema = type("Schema", (), {
        "predictor_columns": ("trait",), "control_columns": ("control",),
    })()
    design = pd.DataFrame({
        "const": [1.0, 1.0, 1.0, 1.0],
        "trait": [-1.0, 0.0, 1.0, 2.0],
        "control": [0.0, 1.0, 0.0, 1.0],
    })
    reduced, local, diagnostics = _prepare_firth_bootstrap_design(
        design, np.array([0, 1, 0, 1]), schema,
    )
    pd.testing.assert_frame_equal(reduced, design)
    assert local == {"const": 0, "trait": 1, "control": 2}
    assert diagnostics["dropped_nuisance_columns"] == ()


def test_bootstrap_design_never_drops_absent_tested_contrast():
    schema = type("Schema", (), {
        "predictor_columns": ("trait",), "control_columns": ("control",),
    })()
    design = pd.DataFrame({"const": [1.0, 1.0], "trait": [0.0, 0.0], "control": [0.0, 1.0]})
    with pytest.raises(BootstrapReplicateError) as error:
        _prepare_firth_bootstrap_design(design, np.array([0, 1]), schema)
    assert error.value.category == "missing_predictor_contrast"
    assert error.value.diagnostics["reduced_design_row_count"] == 2
    assert error.value.diagnostics["target_class_support"] == {"0.0": 1, "1.0": 1}


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
    assert "reduced_design_rank" in error.value.diagnostics
    assert "condition_number" in error.value.diagnostics


def test_nonconverged_firth_diagnostics_include_solver_and_reduced_design_fields():
    fitted = type("Fitted", (), {
        "termination_reason": "line_search_failure",
        "n_iter": 41,
        "final_score_norm": 0.7,
        "final_newton_decrement": 0.2,
        "final_likelihood_change": -1e-11,
        "step_halving_count": 73,
        "iteration_tail": ({
            "iteration_number": 41,
            "score_norm": 0.7,
            "newton_decrement": 0.2,
            "likelihood_change": -1e-11,
            "maximum_coefficient_update": 0.01,
            "step_halving_count": 2,
            "termination_reason": "line_search_failure",
        },),
    })()
    design = {
        "reduced_design_row_count": 120,
        "reduced_design_column_count": 7,
        "reduced_design_rank": 7,
        "condition_number": 44.0,
        "target_class_support": {"0.0": 100, "1.0": 20},
        "nuisance_control_nonzero_support": {"era_2011_plus": 110},
    }
    diagnostics = _firth_termination_diagnostics(fitted, design)
    assert diagnostics == {
        **design,
        "termination_reason": "line_search_failure",
        "iteration_count": 41,
        "final_score_norm": 0.7,
        "final_newton_decrement": 0.2,
        "final_likelihood_change": -1e-11,
        "total_step_halvings": 73,
        "iteration_tail": ({
            "iteration_number": 41,
            "score_norm": 0.7,
            "newton_decrement": 0.2,
            "likelihood_change": -1e-11,
            "maximum_coefficient_update": 0.01,
            "step_halving_count": 2,
            "termination_reason": "line_search_failure",
        },),
    }


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


def test_incremental_validation_records_governed_team_levels_unseen_in_training():
    rows = _synthetic_rows()
    rows["depth_team"] = np.where(rows.index % 2 == 0, "CIN", "BUF")
    rows.loc[rows["prediction_season"].eq(2016) & (rows.index % 4 == 0), "depth_team"] = "LA"
    rows.loc[rows["prediction_season"].eq(2017) & (rows.index % 4 == 0), "depth_team"] = "LAC"
    rows.loc[rows["prediction_season"].eq(2020) & (rows.index % 4 == 0), "depth_team"] = "LV"
    predictor = PredictorDefinition(
        "depth_team", "categorical", "cluster_team", True, reference_level="CIN",
    )

    result = incremental_validation(
        rows,
        PRIMARY_TARGETS[0],
        predictor,
        governed_categorical_levels=("BUF", "CIN", "LA", "LAC", "LV"),
    )

    assert result.validation_events == (
        (2016, "governed_level_unseen_in_training", ("LA",)),
        (2017, "governed_level_unseen_in_training", ("LAC",)),
        (2020, "governed_level_unseen_in_training", ("LV",)),
    )
    training = rows.loc[rows["prediction_season"].between(2010, 2015)]
    validation = rows.loc[rows["prediction_season"].eq(2016)]
    _, schema = _design(
        training,
        predictor,
        governed_categorical_levels=("BUF", "CIN", "LA", "LAC", "LV"),
    )
    validation_design, _ = _design(validation, predictor, schema)
    assert not validation_design.loc[
        validation["depth_team"].eq("LA"), list(schema.predictor_columns)
    ].to_numpy().any()


def test_incremental_validation_rejects_category_outside_governed_discovery_set():
    rows = _synthetic_rows()
    rows["depth_team"] = np.where(rows.index % 2 == 0, "CIN", "BUF")
    rows.loc[rows["prediction_season"].eq(2016) & (rows.index % 4 == 0), "depth_team"] = "MALFORMED"
    predictor = PredictorDefinition(
        "depth_team", "categorical", "cluster_team", True, reference_level="CIN",
    )

    with pytest.raises(ValueError, match="outside governed discovery set.*MALFORMED"):
        incremental_validation(
            rows,
            PRIMARY_TARGETS[0],
            predictor,
            governed_categorical_levels=("BUF", "CIN", "LA", "LAC", "LV"),
        )


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
    assert len(package.preflight_ledger) == 3
    assert {record.disposition for record in package.preflight_ledger} == {"fit"}


def test_runner_skips_only_non_estimable_family_and_excludes_it_from_bh():
    rows = _synthetic_rows()
    rows["trait_binary"] = rows.index % 11 == 0
    rows.loc[rows["trait_binary"], "lwi_score"] = np.nan
    predictor = PredictorDefinition("trait_binary", "binary", "cluster_086", True)

    package = run_phase1(
        rows, [predictor], [predictor.column], bootstrap_replicates=5,
        minimum_success_rate=0.8, synthetic_test_mode=True,
    )

    assert set(package.primary_results["family"]) == {"star", "strict_bust"}
    assert len(package.incremental_results) == 2
    assert len(package.robustness_results) == 2
    assert not (package.primary_results["family"] == "lwi").any()
    by_family = {record.family: record for record in package.preflight_ledger}
    assert by_family["lwi"].disposition == "excluded_non_estimable"
    assert by_family["lwi"].governed_reason == "binary_no_discovery_contrast"
    assert by_family["star"].disposition == "fit"
    assert by_family["strict_bust"].disposition == "fit"


def test_runner_excludes_binary_target_no_contrast_from_all_result_outputs():
    rows = _synthetic_rows()
    rows["bust_strict_below_replacement_label"] = 0
    predictor = _predictor()

    package = run_phase1(
        rows, [predictor], [predictor.column], bootstrap_replicates=5,
        minimum_success_rate=0.8, synthetic_test_mode=True,
    )

    assert set(package.primary_results["family"]) == {"lwi", "star"}
    assert {value.family for value in package.incremental_results} == {"lwi", "star"}
    assert {value.family for value in package.robustness_results} == {"lwi", "star"}
    strict_record = next(
        record for record in package.preflight_ledger if record.family == "strict_bust"
    )
    assert strict_record.disposition == "excluded_non_estimable"
    assert strict_record.governed_reason == "binary_target_no_discovery_contrast"


def test_strict_bust_preflight_excludes_exact_frozen_draw_infeasibility():
    rows = _synthetic_rows()
    minority_players = {"player_00", "player_01"}
    rows["bust_strict_below_replacement_label"] = rows["player_id"].isin(
        minority_players
    ).astype(int)
    predictor = _predictor()

    class_0, class_1, capable, attempted = _binary_target_bootstrap_feasibility(
        discovery_fit_rows(rows, PRIMARY_TARGETS[2], predictor.column),
        PRIMARY_TARGETS[2],
    )
    records = preflight_phase1_estimability(rows, [predictor], [predictor.column])
    strict_record = next(record for record in records if record.family == "strict_bust")

    assert (class_0, class_1) == (34, 2)
    assert attempted == 2000
    assert capable < 1980
    assert strict_record.disposition == "excluded_non_estimable"
    assert strict_record.governed_reason == "binary_target_cluster_bootstrap_infeasible"
    assert strict_record.binary_class_0_player_cluster_support == class_0
    assert strict_record.binary_class_1_player_cluster_support == class_1
    assert strict_record.bootstrap_target_signal_capable_draws == capable
    assert strict_record.bootstrap_target_signal_attempted_draws == attempted

    package = run_phase1(
        rows, [predictor], [predictor.column], bootstrap_replicates=5,
        minimum_success_rate=0.8, synthetic_test_mode=True,
    )
    assert set(package.primary_results["family"]) == {"lwi", "star"}
    assert {value.family for value in package.incremental_results} == {"lwi", "star"}
    assert {value.family for value in package.robustness_results} == {"lwi", "star"}


def test_frozen_draw_feasibility_matches_direct_player_cluster_draw_sequence():
    rows = _synthetic_rows().loc[lambda frame: frame["prediction_season"].eq(2010)].copy()
    rows["bust_strict_below_replacement_label"] = rows["player_id"].isin(
        {"player_00", "player_01"}
    ).astype(int)
    target = PRIMARY_TARGETS[2]
    observed = _binary_target_bootstrap_feasibility(rows, target, replicates=25, seed=17)

    players = pd.Index(rows["player_id"].unique())
    masks = np.asarray([
        sum(1 << int(value) for value in rows.loc[
            rows["player_id"].eq(player), target.target_column
        ].unique())
        for player in players
    ])
    rng = np.random.default_rng(17)
    direct = sum(
        np.bitwise_or.reduce(masks[rng.choice(len(players), len(players), replace=True)]) == 3
        for _ in range(25)
    )
    assert observed == (34, 2, int(direct), 25)


@pytest.mark.parametrize(
    ("capable", "disposition"),
    [(1980, "fit"), (1979, "excluded_non_estimable")],
)
def test_strict_bust_frozen_draw_gate_uses_exact_99_percent_boundary(
    monkeypatch, capable, disposition,
):
    rows = _synthetic_rows()
    predictor = _predictor()
    monkeypatch.setattr(
        "lib.dataset2.phase1_runner._binary_target_bootstrap_feasibility",
        lambda *_args, **_kwargs: (30, 6, capable, 2000),
    )
    strict = next(
        record for record in preflight_phase1_estimability(
            rows, [predictor], [predictor.column],
        )
        if record.family == "strict_bust"
    )
    assert strict.disposition == disposition
    assert strict.governed_reason == (
        None if disposition == "fit" else "binary_target_cluster_bootstrap_infeasible"
    )


def _rows_with_season_confined_categorical_level():
    """A categorical level ('high') exists only in the final discovery season.

    Mirrors a real governed-team predictor whose level first appears in the
    last discovery season (e.g. a franchise relocation): omitting that one
    season in leave-one-season-out robustness removes every row carrying it.
    """
    rows = []
    rng = np.random.default_rng(20260808)
    for season in range(2010, 2021):
        for player_number in range(36):
            trait = rng.normal() + 0.03 * (season - 2010)
            if season == 2020 and player_number % 4 == 0:
                category = "high"
            else:
                category = "low" if player_number % 2 == 0 else "middle"
            offset = 6.0 if category == "high" else 0.0
            rows.append({
                "prediction_season": season,
                "player_id": f"player_{player_number:02d}",
                "position": ("QB", "RB", "WR", "TE")[player_number % 4],
                "preseason_market_status": "ordinary_market",
                "adp_round": 1 + player_number % 15,
                "trait_category": category,
                "lwi_score": offset + rng.normal(scale=0.4),
                # Constant so star/strict_bust are excluded at preflight
                # (binary_target_no_discovery_contrast) rather than left to an
                # unrelated Firth convergence outcome on a deliberately sparse
                # categorical cell; this test targets the LWI robustness path.
                "star_by_value_label": 0,
                "star_outcome_eligible": True,
                "bust_strict_below_replacement_label": 0,
                "bust_strict_below_replacement_eligible": True,
            })
    return pd.DataFrame(rows)


def test_robustness_marks_season_confined_categorical_contrast_unavailable_not_zero():
    rows = _rows_with_season_confined_categorical_level()
    predictor = PredictorDefinition(
        "trait_category", "categorical", "cluster_001", True, reference_level="low",
    )

    package = run_phase1(
        rows, [predictor], [predictor.column], bootstrap_replicates=5,
        minimum_success_rate=0.8, synthetic_test_mode=True,
    )

    lwi_row = package.primary_results.loc[package.primary_results["family"].eq("lwi")].iloc[0]
    high_index = list(lwi_row["contrast_names"]).index("trait_category_high")
    lwi_robustness = next(r for r in package.robustness_results if r.family == "lwi")
    fold_by_season = dict(lwi_robustness.leave_one_season_out_estimates)

    assert fold_by_season[2020][high_index] is None
    assert all(
        fold_by_season[season][high_index] is not None
        for season in fold_by_season if season != 2020
    )

    full = lwi_robustness.full_estimates[high_index]
    available_signs = [
        np.sign(values[high_index] - 0.0) == np.sign(full - 0.0)
        for season, values in lwi_robustness.leave_one_season_out_estimates
        if values[high_index] is not None
    ]
    assert lwi_robustness.direction_status[high_index] == (
        "all_folds_same_direction" if all(available_signs) else "mixed_fold_directions"
    )
    # Proves the fix is not equivalent to treating the unavailable fold as
    # zero: substituting 0.0 for the omitted season would flip this vote.
    hypothetical_zero_signs = [
        np.sign((values[high_index] if values[high_index] is not None else 0.0) - 0.0)
        == np.sign(full - 0.0)
        for _, values in lwi_robustness.leave_one_season_out_estimates
    ]
    assert not all(hypothetical_zero_signs)
    assert lwi_robustness.direction_status[high_index] == "all_folds_same_direction"
    # star/strict_bust are excluded upstream (not silently skipped by a crash).
    excluded = {
        record.family: record.governed_reason
        for record in package.preflight_ledger if record.disposition == "excluded_non_estimable"
    }
    assert excluded == {
        "star": "binary_target_no_discovery_contrast",
        "strict_bust": "binary_target_no_discovery_contrast",
    }


def test_firth_point_estimates_omits_a_level_missing_from_the_fold_without_crashing():
    rows = _synthetic_rows()
    predictor = PredictorDefinition(
        "trait_category", "categorical", "cluster_001", True, reference_level="low",
    )
    target = PRIMARY_TARGETS[1]
    fit_rows = discovery_fit_rows(rows, target, predictor.column)
    full_estimates = _firth_point_estimates(fit_rows, target, predictor)
    assert "trait_category_high" in full_estimates

    fold_without_high = fit_rows.loc[fit_rows["trait_category"] != "high"]
    fold_estimates = _firth_point_estimates(fold_without_high, target, predictor)

    assert "trait_category_high" not in fold_estimates
    assert set(fold_estimates) == set(full_estimates) - {"trait_category_high"}
    assert all(np.isfinite(value) and value > 0 for value in fold_estimates.values())


def test_firth_point_estimates_returns_odds_ratios_keyed_by_contrast_name():
    rows = _synthetic_rows()
    predictor = PredictorDefinition(
        "trait_category", "categorical", "cluster_001", True, reference_level="low",
    )
    target = PRIMARY_TARGETS[1]
    fit_rows = discovery_fit_rows(rows, target, predictor.column)
    _, schema = _design(fit_rows, predictor)

    estimates = _firth_point_estimates(fit_rows, target, predictor)

    assert isinstance(estimates, dict)
    assert set(estimates) == set(schema.predictor_columns)
    assert all(np.isfinite(value) and value > 0 for value in estimates.values())


def test_phase1_runner_module_has_no_artifact_loader_or_repository_path():
    from lib.dataset2 import phase1_runner

    source = open(phase1_runner.__file__, encoding="utf-8").read()
    assert "read_csv" not in source
    assert "read_parquet" not in source
    assert "data/" not in source
