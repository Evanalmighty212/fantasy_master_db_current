"""
tests/test_2025_adp_integration.py

Covers scripts/2025_adp_integration.py -- wires the approved 2025 raw
MFL AUG15 ADP source into the normal adp_clean pipeline.

TestAmariCooperExclusion is the regression pin for the real,
individually-documented rejection from the 2025 matching audit: the
real Amari Cooper has zero 2025 nflverse stats rows, so his real MFL
ADP entry fuzzy-matches to the unrelated "Darius Cooper" every time
the unmodified player_matching.py algorithm runs. Excluding this one
row is the narrowest fix available (no negative-override mechanism
exists in this pipeline) -- see the module's own docstring and
docs/ADP_SOURCE_MATRIX.md's Commit D audit entry for the full record.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SCRIPT_PATH = REPO_ROOT / "scripts" / "2025_adp_integration.py"


def load_module():
    spec = importlib.util.spec_from_file_location("adp_2025_integration", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = load_module()

MFL_RAW_COLUMNS = ["player", "name", "position", "team", "mean_adp", "median_adp", "n_drafts"]


def _mfl_raw_row(player_id, name, position, team, mean_adp, n_drafts=100):
    return {
        "player": player_id, "name": name, "position": position, "team": team,
        "mean_adp": mean_adp, "median_adp": mean_adp, "n_drafts": n_drafts,
    }


class TestAmariCooperExclusion:
    def test_amari_cooper_row_is_excluded_from_2025_adp_clean_rows(self, tmp_path, monkeypatch):
        mfl_raw = pd.DataFrame([
            _mfl_raw_row("1", "Cooper, Amari", "WR", "BUF", 156.6),
            _mfl_raw_row("2", "Chase, Ja'Marr", "WR", "CIN", 2.0),
        ])
        raw_path = tmp_path / "mfl_raw.csv"
        mfl_raw.to_csv(raw_path, index=False)
        monkeypatch.setattr(MOD, "MFL_RAW_PATH", raw_path)

        rows = MOD.build_2025_adp_clean_rows()
        assert "Amari Cooper" not in rows["player_name_original"].values
        assert "Ja'Marr Chase" in rows["player_name_original"].values

    def test_exclusion_is_named_and_scoped_to_the_exact_player_position_pair(self, tmp_path, monkeypatch):
        """A DIFFERENT 'Amari Cooper' at a different position, or a
        different player who happens to share only the position,
        must NOT be excluded -- the exclusion key is (name, position),
        not just name."""
        mfl_raw = pd.DataFrame([
            _mfl_raw_row("1", "Cooper, Amari", "WR", "BUF", 156.6),  # excluded
            _mfl_raw_row("2", "Someone, Else", "WR", "CIN", 100.0),  # not excluded
        ])
        raw_path = tmp_path / "mfl_raw.csv"
        mfl_raw.to_csv(raw_path, index=False)
        monkeypatch.setattr(MOD, "MFL_RAW_PATH", raw_path)

        rows = MOD.build_2025_adp_clean_rows()
        assert len(rows) == 1
        assert rows.iloc[0]["player_name_original"] == "Else Someone"

    def test_exclusion_reason_is_documented_at_module_scope(self):
        assert ("Amari Cooper", "WR") in MOD.EXCLUDED_2025_ADP_ROWS
        reason = MOD.EXCLUDED_2025_ADP_ROWS[("Amari Cooper", "WR")]
        assert "Darius Cooper" in reason
        assert "zero 2025 nflverse stats" in reason


class TestBuild2025AdpCleanRowsSchema:
    def test_output_matches_canonical_columns_shape(self, tmp_path, monkeypatch):
        mfl_raw = pd.DataFrame([
            _mfl_raw_row("1", "Chase, Ja'Marr", "WR", "CIN", 2.0),
            _mfl_raw_row("2", "Allen, Josh", "QB", "BUF", 6.3),
        ])
        raw_path = tmp_path / "mfl_raw.csv"
        mfl_raw.to_csv(raw_path, index=False)
        monkeypatch.setattr(MOD, "MFL_RAW_PATH", raw_path)

        rows = MOD.build_2025_adp_clean_rows()
        for col in MOD.CANONICAL_COLUMNS:
            assert col in rows.columns, f"missing canonical column: {col}"

    def test_season_is_always_2025(self, tmp_path, monkeypatch):
        mfl_raw = pd.DataFrame([_mfl_raw_row("1", "Chase, Ja'Marr", "WR", "CIN", 2.0)])
        raw_path = tmp_path / "mfl_raw.csv"
        mfl_raw.to_csv(raw_path, index=False)
        monkeypatch.setattr(MOD, "MFL_RAW_PATH", raw_path)

        rows = MOD.build_2025_adp_clean_rows()
        assert (rows["season"] == 2025).all()

    def test_source_matches_config_mfl_2025_adp_source(self, tmp_path, monkeypatch):
        import config
        mfl_raw = pd.DataFrame([_mfl_raw_row("1", "Chase, Ja'Marr", "WR", "CIN", 2.0)])
        raw_path = tmp_path / "mfl_raw.csv"
        mfl_raw.to_csv(raw_path, index=False)
        monkeypatch.setattr(MOD, "MFL_RAW_PATH", raw_path)

        rows = MOD.build_2025_adp_clean_rows()
        assert (rows["source"] == config.MFL_2025_ADP_SOURCE).all()

    def test_name_reordering_last_first_to_first_last(self, tmp_path, monkeypatch):
        mfl_raw = pd.DataFrame([_mfl_raw_row("1", "Chase, Ja'Marr", "WR", "CIN", 2.0)])
        raw_path = tmp_path / "mfl_raw.csv"
        mfl_raw.to_csv(raw_path, index=False)
        monkeypatch.setattr(MOD, "MFL_RAW_PATH", raw_path)

        rows = MOD.build_2025_adp_clean_rows()
        assert rows.iloc[0]["player_name_original"] == "Ja'Marr Chase"

    def test_adp_rank_matches_02_clean_adp_convention(self, tmp_path, monkeypatch):
        """Identical convention to 02_clean_adp.py:
        groupby(season, scoring_format)['overall_adp'].rank(method='first')."""
        mfl_raw = pd.DataFrame([
            _mfl_raw_row("1", "Chase, Ja'Marr", "WR", "CIN", 2.0),
            _mfl_raw_row("2", "Allen, Josh", "QB", "BUF", 6.3),
            _mfl_raw_row("3", "Robinson, Bijan", "RB", "ATL", 3.3),
        ])
        raw_path = tmp_path / "mfl_raw.csv"
        mfl_raw.to_csv(raw_path, index=False)
        monkeypatch.setattr(MOD, "MFL_RAW_PATH", raw_path)

        rows = MOD.build_2025_adp_clean_rows().sort_values("overall_adp")
        assert list(rows["adp_rank"]) == [1, 2, 3]


class TestIntegrateGuardsAgainstDoubleIntegration:
    def test_refuses_if_2025_already_present(self, tmp_path, monkeypatch):
        existing = pd.DataFrame([{
            "season": 2025, "source": "mfl_aug15_2025", "scoring_format": "PPR", "league_size": 12,
            "player_name_original": "Test Player", "player_name_normalized": "test player",
            "position": "WR", "team": "AAA", "overall_adp": 10.0, "adp_rank": 1,
            "times_drafted": 100, "source_quality_flag": "verified_mfl_raw_canonical",
        }])
        adp_clean_path = tmp_path / "adp_clean.csv"
        existing.to_csv(adp_clean_path, index=False)
        monkeypatch.setattr(MOD, "ADP_CLEAN_PATH", adp_clean_path)

        with pytest.raises(RuntimeError, match="already has 2025 rows"):
            MOD.integrate()
