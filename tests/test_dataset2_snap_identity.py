"""
tests/test_dataset2_snap_identity.py

Covers lib/dataset2/snap_identity.py -- the pfr_player_id -> gsis_id
identity crosswalk for Dataset 2 Source B (snap_counts). Protects:

- Every row is preserved, matched or not -- never silently dropped.
- Unmatched rows are labeled with WHY (no real pfr_id in players.csv,
  vs. a null pfr_player_id in the source itself) -- two different real
  situations, not collapsed into one.
- A real one-to-many conflict on the players.csv side (duplicate
  pfr_id) is detected and raises loudly rather than silently fanning
  out the merge.
- A real many-to-one conflict (two distinct pfr_player_id values
  matching the same gsis_id) is detected and reported, not hidden.
- Match-rate breakdowns by season/position are computed correctly.
- Row count is preserved through the crosswalk merge.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import snap_identity as si


def _snaps_df(*rows):
    cols = ["season", "position", "pfr_player_id", "player"]
    return pd.DataFrame(list(rows), columns=cols)


def _players_df(*rows):
    cols = ["gsis_id", "pfr_id"]
    return pd.DataFrame(list(rows), columns=cols)


class TestCrosswalkBasicMatching:
    def test_matched_row_gets_gsis_id(self):
        snaps = _snaps_df({"season": 2023, "position": "WR", "pfr_player_id": "HillTy00", "player": "Tyreek Hill"})
        players = _players_df({"gsis_id": "00-0033040", "pfr_id": "HillTy00"})
        out = si.crosswalk_snap_counts_identity(snaps, players)
        assert out.loc[0, "gsis_id"] == "00-0033040"
        assert out.loc[0, "identity_match_status"] == si.MATCH_STATUS_MATCHED

    def test_unmatched_row_no_pfr_id_in_players_preserved_not_dropped(self):
        snaps = _snaps_df({"season": 2023, "position": "WR", "pfr_player_id": "NoMatch00", "player": "Nobody Real"})
        players = _players_df({"gsis_id": "00-0033040", "pfr_id": "HillTy00"})
        out = si.crosswalk_snap_counts_identity(snaps, players)
        assert len(out) == 1
        assert pd.isna(out.loc[0, "gsis_id"])
        assert out.loc[0, "identity_match_status"] == si.MATCH_STATUS_UNMATCHED_NO_PFR_ID_IN_PLAYERS

    def test_null_pfr_player_id_in_source_labeled_distinctly(self):
        snaps = _snaps_df({"season": 2023, "position": "WR", "pfr_player_id": None, "player": "Mystery Player"})
        players = _players_df({"gsis_id": "00-0033040", "pfr_id": "HillTy00"})
        out = si.crosswalk_snap_counts_identity(snaps, players)
        assert out.loc[0, "identity_match_status"] == si.MATCH_STATUS_UNMATCHED_NULL_PFR_PLAYER_ID

    def test_row_count_preserved(self):
        snaps = _snaps_df(
            {"season": 2023, "position": "WR", "pfr_player_id": "HillTy00", "player": "Tyreek Hill"},
            {"season": 2023, "position": "RB", "pfr_player_id": "NoMatch00", "player": "Nobody Real"},
        )
        players = _players_df({"gsis_id": "00-0033040", "pfr_id": "HillTy00"})
        out = si.crosswalk_snap_counts_identity(snaps, players)
        assert len(out) == 2

    def test_players_with_null_pfr_id_never_falsely_match(self):
        snaps = _snaps_df({"season": 2023, "position": "WR", "pfr_player_id": None, "player": "X"})
        players = _players_df({"gsis_id": "00-1", "pfr_id": None}, {"gsis_id": "00-2", "pfr_id": "HillTy00"})
        out = si.crosswalk_snap_counts_identity(snaps, players)
        assert pd.isna(out.loc[0, "gsis_id"])


class TestDuplicatePfrIdConflictRaisesLoudly:
    def test_one_to_many_conflict_raises(self):
        snaps = _snaps_df({"season": 2023, "position": "WR", "pfr_player_id": "DupeId00", "player": "X"})
        players = _players_df(
            {"gsis_id": "00-1", "pfr_id": "DupeId00"},
            {"gsis_id": "00-2", "pfr_id": "DupeId00"},
        )
        with pytest.raises(RuntimeError, match="one-to-many crosswalk conflict"):
            si.crosswalk_snap_counts_identity(snaps, players)


class TestIdentityAuditMatchSummary:
    def test_counts_and_rate(self):
        snaps = _snaps_df(
            {"season": 2023, "position": "WR", "pfr_player_id": "HillTy00", "player": "Tyreek Hill"},
            {"season": 2023, "position": "RB", "pfr_player_id": "NoMatch00", "player": "Nobody Real"},
        )
        players = _players_df({"gsis_id": "00-0033040", "pfr_id": "HillTy00"})
        audit = si.build_identity_audit(snaps, players)
        summary = audit["match_summary"].iloc[0]
        assert summary["total_rows"] == 2
        assert summary["matched_rows"] == 1
        assert summary["unmatched_rows"] == 1
        assert summary["match_rate"] == pytest.approx(0.5)

    def test_match_rate_by_season_and_position(self):
        snaps = _snaps_df(
            {"season": 2022, "position": "WR", "pfr_player_id": "HillTy00", "player": "Tyreek Hill"},
            {"season": 2023, "position": "RB", "pfr_player_id": "NoMatch00", "player": "Nobody Real"},
        )
        players = _players_df({"gsis_id": "00-0033040", "pfr_id": "HillTy00"})
        audit = si.build_identity_audit(snaps, players)
        by_season = audit["match_rate_by_season"].set_index("season")["match_rate"]
        assert by_season[2022] == pytest.approx(1.0)
        assert by_season[2023] == pytest.approx(0.0)
        by_pos = audit["match_rate_by_position"].set_index("position")["match_rate"]
        assert by_pos["WR"] == pytest.approx(1.0)
        assert by_pos["RB"] == pytest.approx(0.0)

    def test_unmatched_detail_never_silently_discarded(self):
        snaps = _snaps_df(
            {"season": 2023, "position": "RB", "pfr_player_id": "NoMatch00", "player": "Nobody Real"},
            {"season": 2023, "position": "RB", "pfr_player_id": "NoMatch00", "player": "Nobody Real"},
        )
        players = _players_df({"gsis_id": "00-1", "pfr_id": "SomeoneElse00"})
        audit = si.build_identity_audit(snaps, players)
        detail = audit["unmatched_detail"]
        assert len(detail) == 1
        assert detail.iloc[0]["row_count"] == 2

    def test_missing_player_ids_detected(self):
        snaps = _snaps_df({"season": 2023, "position": "WR", "pfr_player_id": "HillTy00", "player": "Tyreek Hill"})
        players = _players_df({"gsis_id": "00-1", "pfr_id": "HillTy00"}, {"gsis_id": "00-2", "pfr_id": None})
        audit = si.build_identity_audit(snaps, players)
        assert len(audit["missing_player_ids"]) == 1
        assert audit["missing_player_ids"].iloc[0]["gsis_id"] == "00-2"

    def test_many_to_one_conflict_detected_not_hidden(self):
        """Two distinct real pfr_player_id values in the snap data both
        happen to resolve to the same gsis_id (e.g. a real
        players.csv data issue) -- must be surfaced, not silently
        merged away."""
        snaps = _snaps_df(
            {"season": 2023, "position": "WR", "pfr_player_id": "IdOne00", "player": "Player A"},
            {"season": 2023, "position": "WR", "pfr_player_id": "IdTwo00", "player": "Player A Variant"},
        )
        players = _players_df(
            {"gsis_id": "00-1", "pfr_id": "IdOne00"},
            {"gsis_id": "00-1", "pfr_id": "IdTwo00"},
        )
        # players.csv itself has 00-1 appearing twice here with two different
        # pfr_ids -- a real (if rare) data situation this test constructs
        # directly since duplicate gsis_id was never observed in real data.
        audit = si.build_identity_audit(snaps, players)
        assert len(audit["many_to_one_conflicts"]) == 2
        assert set(audit["many_to_one_conflicts"]["pfr_player_id"]) == {"IdOne00", "IdTwo00"}


class TestRequiredColumnValidation:
    def test_snaps_missing_column_raises(self):
        bad = pd.DataFrame({"season": [2023]})
        players = _players_df({"gsis_id": "00-1", "pfr_id": "X"})
        with pytest.raises(ValueError, match="snap_counts is missing required columns"):
            si.crosswalk_snap_counts_identity(bad, players)

    def test_players_missing_column_raises(self):
        snaps = _snaps_df({"season": 2023, "position": "WR", "pfr_player_id": "X", "player": "Y"})
        bad_players = pd.DataFrame({"gsis_id": ["00-1"]})
        with pytest.raises(ValueError, match="players is missing required columns"):
            si.crosswalk_snap_counts_identity(snaps, bad_players)
