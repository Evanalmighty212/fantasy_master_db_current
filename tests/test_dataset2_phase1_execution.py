"""Synthetic-only safeguards for the governed Phase 1 discovery entry point."""

import pandas as pd

from scripts import run_dataset2_phase1_discovery as entrypoint


def test_discovery_entrypoint_uses_nested_and_filter_then_explicit_selection(monkeypatch):
    observed = {}
    source = pd.DataFrame({"prediction_season": list(range(2010, 2022))})

    class SyntheticParquet:
        def __init__(self, path):
            observed["path"] = path

        def to_pandas(self, **kwargs):
            observed.update(kwargs)
            return source.copy()

    monkeypatch.setattr(entrypoint.fastparquet, "ParquetFile", SyntheticParquet)
    rows = entrypoint.discovery_rows(())
    assert observed["filters"] == [[
        ("prediction_season", ">=", 2010),
        ("prediction_season", "<=", 2020),
    ]]
    assert observed["row_filter"] is True
    assert sorted(rows["prediction_season"].unique()) == list(range(2010, 2021))
