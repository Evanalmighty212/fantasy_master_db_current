"""Regression coverage for governed Dataset 2 depth-chart preflight.

Protects the real failure where an opaque list-comprehension raised
``EmptyDataError`` without identifying the affected season or path.
All inputs here are synthetic temporary files; no production artifact
or network source is read or written.
"""

import hashlib
import json

import pandas as pd
import pytest

from scripts import build_dataset2_canonical_predictor_table as driver


HEADER = "season,club_code,week,game_type,depth_team,position,gsis_id\n"
VALID = HEADER + "2006,ARI,1,REG,1,QB,00-001\n"


def _governed_file(tmp_path, monkeypatch, content: bytes, *, manifest_hash=None):
    cache = tmp_path / "annual"
    cache.mkdir()
    path = cache / "depth_charts_2006.csv"
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest() if manifest_hash is None else manifest_hash
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "depth_charts": {"seasons": {"2006": {
            "asset_id": 1,
            "asset_url": "https://example.invalid/1",
            "sha256": digest,
            "schema_version": "test",
            "row_count": 1,
        }}},
    }))
    monkeypatch.setattr(driver.nflverse_source, "DEPTH_CHARTS_CACHE_DIR", cache)
    monkeypatch.setattr(driver.nflverse_source, "MANIFEST_PATH", manifest)
    return path


def test_successfully_loads_explicit_governed_season(tmp_path, monkeypatch):
    _governed_file(tmp_path, monkeypatch, VALID.encode())
    result = driver._load_depth_charts_pre2025(seasons=(2006,))
    assert result[["season", "club_code", "gsis_id"]].to_dict("records") == [
        {"season": 2006, "club_code": "ARI", "gsis_id": "00-001"},
    ]


def test_missing_source_names_season_and_path_without_fetching(tmp_path, monkeypatch):
    cache = tmp_path / "annual"
    cache.mkdir()
    monkeypatch.setattr(driver.nflverse_source, "DEPTH_CHARTS_CACHE_DIR", cache)
    with pytest.raises(driver.DepthChartSourceIntegrityError, match=r"missing for season 2006.*depth_charts_2006.csv"):
        driver._load_depth_charts_pre2025(seasons=(2006,))


def test_hash_mismatch_is_distinguished_and_names_source(tmp_path, monkeypatch):
    _governed_file(tmp_path, monkeypatch, VALID.encode(), manifest_hash="0" * 64)
    with pytest.raises(driver.DepthChartSourceIntegrityError, match=r"hash mismatch for season 2006.*depth_charts_2006.csv"):
        driver._load_depth_charts_pre2025(seasons=(2006,))


@pytest.mark.parametrize("content", [b"", b" \n\t", b"2006,ARI,1,REG,1,QB,00-001\n"])
def test_blank_or_headerless_source_is_never_valid(tmp_path, monkeypatch, content):
    _governed_file(tmp_path, monkeypatch, content)
    with pytest.raises(driver.DepthChartSourceIntegrityError, match=r"blank/headerless for season 2006.*depth_charts_2006.csv"):
        driver._load_depth_charts_pre2025(seasons=(2006,))


def test_header_only_source_is_never_treated_as_valid_empty_season(tmp_path, monkeypatch):
    _governed_file(tmp_path, monkeypatch, HEADER.encode())
    with pytest.raises(driver.DepthChartSourceIntegrityError, match=r"blank/headerless for season 2006.*no data rows"):
        driver._load_depth_charts_pre2025(seasons=(2006,))


def test_malformed_csv_is_distinguished_and_names_source(tmp_path, monkeypatch):
    malformed = (HEADER + '2006,ARI,1,REG,1,QB,"unterminated\n').encode()
    _governed_file(tmp_path, monkeypatch, malformed)
    with pytest.raises(driver.DepthChartSourceIntegrityError, match=r"malformed CSV for season 2006.*depth_charts_2006.csv"):
        driver._load_depth_charts_pre2025(seasons=(2006,))


def test_input_preflight_failure_occurs_before_construction_or_writes(tmp_path, monkeypatch):
    sentinel = pd.DataFrame()
    monkeypatch.setattr(driver, "_load_master_population", lambda: sentinel)
    monkeypatch.setattr(driver, "_load_players", lambda: sentinel)
    monkeypatch.setattr(driver, "_load_weekly", lambda: pd.DataFrame({"season_type": []}))
    monkeypatch.setattr(driver, "_load_snap_counts", lambda: sentinel)
    monkeypatch.setattr(
        driver, "_load_depth_charts_pre2025",
        lambda: (_ for _ in ()).throw(driver.DepthChartSourceIntegrityError("synthetic preflight failure")),
    )
    monkeypatch.setattr(driver, "_load_schedules", lambda: sentinel)
    monkeypatch.setattr(
        driver, "build_canonical_predictor_table",
        lambda *args, **kwargs: pytest.fail("construction must not begin after source validation fails"),
    )
    monkeypatch.setattr(driver, "OUTPUT_DIR", tmp_path / "exports")
    monkeypatch.setattr(driver, "PARQUET_PATH", tmp_path / "exports" / "predictor.parquet")
    monkeypatch.setattr(driver, "CSV_PATH", tmp_path / "exports" / "predictor.csv")
    monkeypatch.setattr(driver, "DICTIONARY_PATH", tmp_path / "exports" / "dictionary.csv")

    with pytest.raises(driver.DepthChartSourceIntegrityError, match="synthetic preflight failure"):
        driver.main()
    assert not (tmp_path / "exports").exists()
