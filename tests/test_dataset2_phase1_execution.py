"""Synthetic-only safeguards for the governed Phase 1 discovery entry point."""

import json

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from scripts import run_dataset2_phase1_discovery as entrypoint
from lib.dataset2.phase1_runner import PredictorDefinition, preflight_phase1_estimability


def _analysis_rows(seasons, predictor_values=None):
    n = len(seasons)
    rows = pd.DataFrame({
        "prediction_season": seasons,
        "player_id": [f"p{i}" for i in range(n)],
        "position": ["QB", "RB", "WR", "TE"] * (n // 4) + ["QB"] * (n % 4),
        "preseason_market_status": ["ordinary_market"] * n,
        "adp_round": [2.0] * n,
        "lwi_score": np.linspace(-1.0, 1.0, n),
        "star_by_value_label": [i % 2 for i in range(n)],
        "star_outcome_eligible": [True] * n,
        "bust_strict_below_replacement_label": [(i + 1) % 2 for i in range(n)],
        "bust_strict_below_replacement_eligible": [True] * n,
    })
    if predictor_values is not None:
        rows["trait"] = predictor_values
    return rows


def test_discovery_entrypoint_streams_chunks_then_explicitly_selects(monkeypatch):
    observed = {}
    source = _analysis_rows(list(range(2010, 2022)))
    def fake_read_csv(path, **kwargs):
        observed["path"] = path
        observed.update(kwargs)
        return [source.iloc[:5].copy(), source.iloc[5:].copy()]
    monkeypatch.setattr(entrypoint.pd, "read_csv", fake_read_csv)
    rows = entrypoint.discovery_rows(())
    assert observed["path"] == entrypoint.ANALYSIS_VIEW_CSV
    assert observed["chunksize"] == entrypoint.DISCOVERY_CSV_CHUNK_SIZE
    assert observed["float_precision"] == "round_trip"
    assert sorted(rows["prediction_season"].unique()) == list(range(2010, 2021))


def test_chunked_csv_preserves_nullable_values_and_is_deterministic(tmp_path, monkeypatch):
    seasons = [2009, *range(2010, 2021), 2021]
    predictor_values = [99.0, np.nan, *[float(i) / 4 for i in range(1, 11)], 88.0]
    source = _analysis_rows(
        seasons,
        predictor_values,
    )
    path = tmp_path / "analysis.csv"
    source.to_csv(path, index=False)
    monkeypatch.setattr(entrypoint, "ANALYSIS_VIEW_CSV", path)
    monkeypatch.setattr(entrypoint, "DISCOVERY_CSV_CHUNK_SIZE", 2)
    predictor = PredictorDefinition("trait", "continuous", "1", True)

    first = entrypoint.discovery_rows((predictor,))
    second = entrypoint.discovery_rows((predictor,))
    assert_frame_equal(first, second, check_exact=True)
    expected = pd.read_csv(path, float_precision="round_trip")
    expected = expected.loc[expected["prediction_season"].between(2010, 2020), first.columns]
    assert_frame_equal(first.reset_index(drop=True), expected.reset_index(drop=True), check_exact=True)
    assert first["prediction_season"].tolist() == list(range(2010, 2021))
    assert first["trait"].isna().tolist() == [True] + [False] * 10
    assert first["trait"].tolist()[1:] == predictor_values[2:-1]


def test_all_143_representatives_receive_family_specific_preflight():
    n = 220
    rows = _analysis_rows([2010 + (i % 11) for i in range(n)])
    predictors = tuple(
        PredictorDefinition(f"trait_{i:03d}", "continuous", str(i), True)
        for i in range(143)
    )
    rows = pd.concat([
        rows,
        pd.DataFrame({
            predictor.column: np.arange(n, dtype=float) + i / 1000.0
            for i, predictor in enumerate(predictors)
        }),
    ], axis=1)
    records = preflight_phase1_estimability(
        rows, predictors, [predictor.column for predictor in predictors],
    )
    assert len(records) == 143 * 3
    assert {(record.family, record.predictor_column) for record in records} == {
        (family, predictor.column)
        for family in ("lwi", "star", "strict_bust")
        for predictor in predictors
    }
    assert {record.disposition for record in records} == {"fit"}


def test_preflight_aggregates_invalid_family_designs_before_fitting():
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = np.arange(len(rows), dtype=float)
    rows.loc[0, "trait"] = np.inf
    predictor = PredictorDefinition("trait", "continuous", "1", True)
    with pytest.raises(ValueError, match="family=lwi predictor=trait.*non-finite"):
        preflight_phase1_estimability(rows, [predictor], ["trait"])


def test_preflight_records_lwi_only_binary_exclusion_and_keeps_valid_families():
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = [False] * 210 + [True] * 10
    rows.loc[rows["trait"], "lwi_score"] = np.nan
    predictor = PredictorDefinition("trait", "binary", "86", True)

    records = preflight_phase1_estimability(rows, [predictor], ["trait"])
    assert len(records) == 3
    by_family = {record.family: record for record in records}
    assert by_family["lwi"].disposition == "excluded_non_estimable"
    assert by_family["lwi"].governed_reason == "binary_no_discovery_contrast"
    assert by_family["lwi"].distinct_value_count == 1
    assert by_family["star"].disposition == "fit"
    assert by_family["strict_bust"].disposition == "fit"


def test_preflight_records_binary_target_no_contrast_for_only_affected_family():
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = np.arange(len(rows), dtype=float)
    rows["bust_strict_below_replacement_label"] = 0
    predictor = PredictorDefinition("trait", "continuous", "9", True)

    records = preflight_phase1_estimability(rows, [predictor], ["trait"])
    by_family = {record.family: record for record in records}
    assert by_family["lwi"].disposition == "fit"
    assert by_family["star"].disposition == "fit"
    assert by_family["strict_bust"].disposition == "excluded_non_estimable"
    assert by_family["strict_bust"].governed_reason == "binary_target_no_discovery_contrast"


@pytest.mark.parametrize("invalid", [np.nan, np.inf, 2])
def test_preflight_invalid_eligible_binary_target_fails_loudly(invalid):
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = np.arange(len(rows), dtype=float)
    rows["star_by_value_label"] = rows["star_by_value_label"].astype(float)
    rows.loc[0, "star_by_value_label"] = invalid
    predictor = PredictorDefinition("trait", "continuous", "9", True)
    with pytest.raises(ValueError, match="target"):
        preflight_phase1_estimability(rows, [predictor], ["trait"])


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (2, "binary predictor must be 0/1"),
        (np.inf, "binary predictor must be 0/1"),
    ],
)
def test_preflight_malformed_binary_remains_fail_loud(replacement, message):
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = pd.Series([False, True] * 110, dtype=object)
    rows.loc[0, "trait"] = replacement
    predictor = PredictorDefinition("trait", "binary", "86", True)
    with pytest.raises(ValueError, match=message):
        preflight_phase1_estimability(rows, [predictor], ["trait"])


def test_entrypoint_preflight_failure_prevents_runner_and_checkpoints(monkeypatch, tmp_path):
    calls = []
    def fail_preflight(*_args, **_kwargs):
        calls.append("preflight")
        raise ValueError("synthetic estimability failure")
    def forbidden_runner(*_args, **_kwargs):
        calls.append("runner")
        (tmp_path / "unexpected_checkpoint").write_text("bad")
    monkeypatch.setattr(entrypoint, "preflight_phase1_estimability", fail_preflight)
    monkeypatch.setattr(entrypoint, "run_phase1", forbidden_runner)

    with pytest.raises(ValueError, match="synthetic estimability failure"):
        entrypoint.run_preflighted_phase1(pd.DataFrame(), (), [], checkpoint_root=tmp_path)
    assert calls == ["preflight"]
    assert not (tmp_path / "unexpected_checkpoint").exists()


def test_entrypoint_persists_preflight_before_runner_and_verifies_identity(monkeypatch, tmp_path):
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = np.arange(len(rows), dtype=float)
    predictor = PredictorDefinition("trait", "continuous", "9", True)
    ledger = preflight_phase1_estimability(rows, [predictor], ["trait"])
    ledger_path = tmp_path / "checkpoints" / "preflight_ledger.csv"
    observed = {}

    def fake_runner(*_args, **_kwargs):
        observed["ledger_existed_before_runner"] = ledger_path.is_file()
        return type("Package", (), {"preflight_ledger": ledger})()

    monkeypatch.setattr(entrypoint, "run_phase1", fake_runner)
    package = entrypoint.run_preflighted_phase1(
        rows, [predictor], ["trait"], preflight_ledger_path=ledger_path,
    )
    assert observed["ledger_existed_before_runner"]
    assert package.preflight_ledger == ledger
    persisted = pd.read_csv(ledger_path)
    assert len(persisted) == 3
    strict = persisted.loc[persisted["family"].eq("strict_bust")].iloc[0]
    assert strict["binary_class_0_player_cluster_support"] == 110
    assert strict["binary_class_1_player_cluster_support"] == 110
    assert strict["bootstrap_target_signal_capable_draws"] == 2000
    assert strict["bootstrap_target_signal_attempted_draws"] == 2000


def test_entrypoint_persists_categorical_bootstrap_feasibility_fields(monkeypatch, tmp_path):
    n = 220
    rows = _analysis_rows([2010 + (i % 11) for i in range(n)])
    rows["trait"] = [
        "rare" if i < 2 else ("low" if i % 2 == 0 else "middle") for i in range(n)
    ]
    predictor = PredictorDefinition("trait", "categorical", "9", True, reference_level="low")
    ledger = preflight_phase1_estimability(rows, [predictor], ["trait"])
    ledger_path = tmp_path / "checkpoints" / "preflight_ledger.csv"

    monkeypatch.setattr(
        entrypoint, "run_phase1",
        lambda *_args, **_kwargs: type("Package", (), {"preflight_ledger": ledger})(),
    )
    entrypoint.run_preflighted_phase1(
        rows, [predictor], ["trait"], preflight_ledger_path=ledger_path,
    )

    persisted = pd.read_csv(ledger_path)
    star = persisted.loc[persisted["family"].eq("star")].iloc[0]
    assert star["disposition"] == "excluded_non_estimable"
    assert star["governed_reason"] == "categorical_predictor_cluster_bootstrap_infeasible"
    assert json.loads(star["categorical_contrasts_below_bootstrap_threshold"]) == ["trait_rare"]
    support = dict(json.loads(star["categorical_contrast_player_cluster_support"]))
    capable = dict(json.loads(star["categorical_contrast_bootstrap_capable_draws"]))
    assert support["trait_rare"] == 2
    assert capable["trait_rare"] < 1980
    assert star["categorical_contrast_bootstrap_attempted_draws"] == 2000

    lwi = persisted.loc[persisted["family"].eq("lwi")].iloc[0]
    assert lwi["disposition"] == "fit"
    assert pd.isna(lwi["categorical_contrasts_below_bootstrap_threshold"])


def test_entrypoint_rejects_final_ledger_identity_mismatch(monkeypatch, tmp_path):
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = np.arange(len(rows), dtype=float)
    predictor = PredictorDefinition("trait", "continuous", "9", True)
    ledger_path = tmp_path / "preflight.csv"
    monkeypatch.setattr(
        entrypoint, "run_phase1",
        lambda *_args, **_kwargs: type("Package", (), {"preflight_ledger": ()})(),
    )
    with pytest.raises(RuntimeError, match="differs from persisted pre-fit ledger"):
        entrypoint.run_preflighted_phase1(
            rows, [predictor], ["trait"], preflight_ledger_path=ledger_path,
        )
    assert ledger_path.is_file()


def test_entrypoint_persists_ledger_before_governed_count_failure(monkeypatch, tmp_path):
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = np.arange(len(rows), dtype=float)
    predictor = PredictorDefinition("trait", "continuous", "9", True)
    ledger_path = tmp_path / "preflight.csv"
    monkeypatch.setattr(
        entrypoint, "run_phase1",
        lambda *_args, **_kwargs: pytest.fail("fitting must not start after count mismatch"),
    )
    with pytest.raises(RuntimeError, match="disposition counts disagree"):
        entrypoint.run_preflighted_phase1(
            rows, [predictor], ["trait"], preflight_ledger_path=ledger_path,
            expected_preflight_counts={
                "lwi": {"fit": 142, "excluded_non_estimable": 1},
                "star": {"fit": 143, "excluded_non_estimable": 0},
                "strict_bust": {"fit": 105, "excluded_non_estimable": 38},
            },
        )
    assert ledger_path.is_file()
