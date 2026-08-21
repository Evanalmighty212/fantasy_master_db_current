"""Synthetic-only safeguards for the governed Phase 1 discovery entry point."""

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
    assert {(family, column) for family, column, _ in records} == {
        (family, predictor.column)
        for family in ("lwi", "star", "strict_bust")
        for predictor in predictors
    }


def test_preflight_aggregates_invalid_family_designs_before_fitting():
    rows = _analysis_rows([2010 + (i % 11) for i in range(220)])
    rows["trait"] = np.arange(len(rows), dtype=float)
    rows.loc[:109, "lwi_score"] = np.nan
    rows.loc[110:, "trait"] = 1.0
    predictor = PredictorDefinition("trait", "continuous", "1", True)
    with pytest.raises(ValueError, match="family=lwi predictor=trait.*invalid discovery SD"):
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
