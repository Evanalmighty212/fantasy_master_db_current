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

TestProductionSourceRegression is the regression pin for the 2026-07
provenance-audit fix: this pipeline used to read
research/diagnostics/mfl_pipeline/output/adp_all_non_keeper.csv (an
explicitly isolated research artifact) instead of the real MFL AUG15
production cache via mfl_client.py. These tests mock mfl_client's
fetch functions directly -- the same convention
tests/test_mfl_historical_backfill.py already uses -- and prove
overall_adp comes from the mocked production averagePick, not from
any other source, using named real players (including Travis Hunter,
whose real observed gap between the two sources was 79.42 vs 60.90 --
an 18.5-pick difference, large enough to shift adp_round).
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

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


def _adp_entry(pid, average_pick, drafts_selected_in=100, rank=None):
    return {
        "id": pid, "averagePick": str(average_pick), "rank": str(rank or 1),
        "minPick": "1", "maxPick": "999", "draftSelPct": "50",
        "draftsSelectedIn": str(drafts_selected_in),
    }


def _players_entry(pid, name, position, team="AAA"):
    return {"id": pid, "name": name, "position": position, "team": team}


def _mock_mfl(monkeypatch, adp_entries, players_entries, total_drafts="1000"):
    adp_resp = {"adp": {"totalDrafts": total_drafts, "player": adp_entries}}
    players_resp = {"players": {"player": players_entries}}
    monkeypatch.setattr(MOD.mfl_client, "fetch_adp", lambda season: adp_resp)
    monkeypatch.setattr(MOD.mfl_client, "fetch_players", lambda season: players_resp)


class TestAmariCooperExclusion:
    def test_amari_cooper_row_is_excluded_from_2025_adp_clean_rows(self, monkeypatch):
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 156.6), _adp_entry("2", 2.0)],
            players_entries=[
                _players_entry("1", "Cooper, Amari", "WR"),
                _players_entry("2", "Chase, Ja'Marr", "WR"),
            ],
        )
        rows = MOD.build_2025_adp_clean_rows()
        assert "Amari Cooper" not in rows["player_name_original"].values
        assert "Ja'Marr Chase" in rows["player_name_original"].values

    def test_exclusion_is_named_and_scoped_to_the_exact_player_position_pair(self, monkeypatch):
        """A DIFFERENT 'Amari Cooper' at a different position, or a
        different player who happens to share only the position,
        must NOT be excluded -- the exclusion key is (name, position),
        not just name."""
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 156.6), _adp_entry("2", 100.0)],
            players_entries=[
                _players_entry("1", "Cooper, Amari", "WR"),  # excluded
                _players_entry("2", "Else, Someone", "WR"),  # not excluded
            ],
        )
        rows = MOD.build_2025_adp_clean_rows()
        assert len(rows) == 1
        assert rows.iloc[0]["player_name_original"] == "Someone Else"

    def test_exclusion_reason_is_documented_at_module_scope(self):
        assert ("Amari Cooper", "WR") in MOD.EXCLUDED_2025_ADP_ROWS
        reason = MOD.EXCLUDED_2025_ADP_ROWS[("Amari Cooper", "WR")]
        assert "Darius Cooper" in reason
        assert "zero 2025 nflverse stats" in reason


class TestBuild2025AdpCleanRowsSchema:
    def test_output_matches_canonical_columns_shape(self, monkeypatch):
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 2.0), _adp_entry("2", 6.3)],
            players_entries=[
                _players_entry("1", "Chase, Ja'Marr", "WR"),
                _players_entry("2", "Allen, Josh", "QB"),
            ],
        )
        rows = MOD.build_2025_adp_clean_rows()
        for col in MOD.CANONICAL_COLUMNS:
            assert col in rows.columns, f"missing canonical column: {col}"

    def test_season_is_always_2025(self, monkeypatch):
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 2.0)],
            players_entries=[_players_entry("1", "Chase, Ja'Marr", "WR")],
        )
        rows = MOD.build_2025_adp_clean_rows()
        assert (rows["season"] == 2025).all()

    def test_source_matches_config_mfl_2025_adp_source(self, monkeypatch):
        import config
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 2.0)],
            players_entries=[_players_entry("1", "Chase, Ja'Marr", "WR")],
        )
        rows = MOD.build_2025_adp_clean_rows()
        assert (rows["source"] == config.MFL_2025_ADP_SOURCE).all()

    def test_name_reordering_last_first_to_first_last(self, monkeypatch):
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 2.0)],
            players_entries=[_players_entry("1", "Chase, Ja'Marr", "WR")],
        )
        rows = MOD.build_2025_adp_clean_rows()
        assert rows.iloc[0]["player_name_original"] == "Ja'Marr Chase"

    def test_adp_rank_matches_02_clean_adp_convention(self, monkeypatch):
        """Identical convention to 02_clean_adp.py:
        groupby(season, scoring_format)['overall_adp'].rank(method='first')."""
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 2.0), _adp_entry("2", 6.3), _adp_entry("3", 3.3)],
            players_entries=[
                _players_entry("1", "Chase, Ja'Marr", "WR"),
                _players_entry("2", "Allen, Josh", "QB"),
                _players_entry("3", "Robinson, Bijan", "RB"),
            ],
        )
        rows = MOD.build_2025_adp_clean_rows().sort_values("overall_adp")
        assert list(rows["adp_rank"]) == [1, 2, 3]

    def test_adp_entry_with_no_matching_players_row_is_skipped_not_guessed(self, monkeypatch):
        """A real edge case mfl_client's two reports can disagree on --
        an id present in the adp report but absent from the players
        report must be dropped, never assigned a guessed position/team."""
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 2.0), _adp_entry("999", 50.0)],
            players_entries=[_players_entry("1", "Chase, Ja'Marr", "WR")],  # no entry for id 999
        )
        rows = MOD.build_2025_adp_clean_rows()
        assert len(rows) == 1
        assert rows.iloc[0]["player_name_original"] == "Ja'Marr Chase"

    def test_times_drafted_comes_from_production_drafts_selected_in(self, monkeypatch):
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("1", 2.0, drafts_selected_in=2364)],
            players_entries=[_players_entry("1", "Nacua, Puka", "WR")],
        )
        rows = MOD.build_2025_adp_clean_rows()
        assert rows.iloc[0]["times_drafted"] == 2364


class TestProductionSourceRegression:
    """Pins the 2026-07 fix: overall_adp must come from the mocked
    mfl_client production fetch, never from any other source. Uses
    named real players from the actual provenance audit, including
    Travis Hunter -- the case with the largest observed real-world gap
    (79.42 from the old isolated-pipeline source vs. 60.90 from the
    real production AUG15 report)."""

    NAMED_CASES = [
        # (mfl_id, name, position, real production averagePick)
        ("13589", "Allen, Josh", "QB", 6.68),
        ("16161", "Robinson, Bijan", "RB", 3.87),
        ("15281", "Chase, Ja'Marr", "WR", 2.49),
        ("17777", "McBride, Trey", "TE", 34.63),
        ("18888", "Hunter, Travis", "WR", 60.90),
    ]

    def test_named_players_overall_adp_matches_production_average_pick(self, monkeypatch):
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry(pid, avg) for pid, _, _, avg in self.NAMED_CASES],
            players_entries=[_players_entry(pid, name, pos) for pid, name, pos, _ in self.NAMED_CASES],
        )
        rows = MOD.build_2025_adp_clean_rows().set_index("player_name_original")

        for pid, name, pos, avg in self.NAMED_CASES:
            first_last = MOD._mfl_name_to_first_last(name)
            assert rows.loc[first_last, "overall_adp"] == pytest.approx(avg), (
                f"{first_last}: overall_adp must equal the production averagePick ({avg}), "
                f"not any other source's value"
            )

    def test_travis_hunter_does_not_equal_the_old_isolated_pipeline_value(self, monkeypatch):
        """The real, observed regression case: the isolated pipeline's
        adp_all_non_keeper.csv had Travis Hunter at mean_adp=79.42.
        The fix must produce the real production value (60.90), not
        that number."""
        OLD_ISOLATED_PIPELINE_VALUE = 79.42
        _mock_mfl(
            monkeypatch,
            adp_entries=[_adp_entry("18888", 60.90)],
            players_entries=[_players_entry("18888", "Hunter, Travis", "WR")],
        )
        rows = MOD.build_2025_adp_clean_rows()
        hunter = rows[rows["player_name_original"] == "Travis Hunter"].iloc[0]
        assert hunter["overall_adp"] == pytest.approx(60.90)
        assert hunter["overall_adp"] != pytest.approx(OLD_ISOLATED_PIPELINE_VALUE)

    def test_loader_calls_mfl_client_fetch_functions_for_season_2025(self, monkeypatch):
        calls = {}

        def fake_fetch_adp(season):
            calls["adp_season"] = season
            return {"adp": {"totalDrafts": "1", "player": []}}

        def fake_fetch_players(season):
            calls["players_season"] = season
            return {"players": {"player": []}}

        monkeypatch.setattr(MOD.mfl_client, "fetch_adp", fake_fetch_adp)
        monkeypatch.setattr(MOD.mfl_client, "fetch_players", fake_fetch_players)
        MOD._load_production_mfl_2025_adp()
        assert calls == {"adp_season": 2025, "players_season": 2025}

    def test_loader_never_forces_refresh(self, monkeypatch):
        """Same integrity guarantee mfl_historical_backfill.py's
        TestNeverForcesRefresh already pins for the CI backfill driver
        -- this caller must never pass force_refresh=True either,
        which would silently accept a mismatched/replaced snapshot
        without a human decision."""
        with patch.object(MOD.mfl_client, "fetch_adp", return_value={"adp": {"totalDrafts": "1", "player": []}}) as mock_adp, \
             patch.object(MOD.mfl_client, "fetch_players", return_value={"players": {"player": []}}) as mock_players:
            MOD._load_production_mfl_2025_adp()
        mock_adp.assert_called_once_with(2025)
        mock_players.assert_called_once_with(2025)


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
