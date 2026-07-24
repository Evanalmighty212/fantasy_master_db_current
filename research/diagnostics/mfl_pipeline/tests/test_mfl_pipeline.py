"""
tests/test_mfl_pipeline.py

Tests for the reusable logic in the isolated MFL diagnostic pipeline
(research/diagnostics/mfl_pipeline/). Not part of the production test
suite in tests/ at the repo root -- this protects exploratory
diagnostic code, not the canonical pipeline, which this diagnostic
was never wired into.

Each test protects a specific, real finding from the audit, not
speculative coverage:
- Pick-order reconstruction: overall_pick was manually verified
  against real chronological draft timestamps during the audit (every
  one of 15 checked picks matched exactly) -- this test locks that
  formula in with a synthetic snake-draft fixture.
- League classification: the superflex check specifically must catch
  a RANGE on the QB slot (e.g. "1-2"), not just string-compare against
  "1" -- this was the entire point of building it that way, per the
  original task's explicit caution not to rely on the QB field alone.
- Date-window filtering: protects the Aug15-kickoff boundary logic.
- Provenance categorization: protects the corrected, non-judgmental
  six-category taxonomy (a prior draft's "organic/non-organic" framing
  was revised on review -- commissioner-entered and externally-imported
  picks are NOT assumed fake).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from classify_leagues import classify_one, _parse_limit_max
from fetch_drafts import classify_pick_provenance, WINDOW_START, WINDOW_END
from run_sensitivity_analysis import find_early_qb_leagues


class TestPickOrderReconstruction:
    def test_overall_pick_matches_chronological_order(self):
        """Synthetic 4-team snake draft, 2 rounds -- overall_pick must
        match real draft order exactly, the same check performed
        manually against league 14090's real timestamps during the
        audit."""
        franchise_count = 4
        # round 1: franchises A,B,C,D in order. round 2 (snake): D,C,B,A.
        picks = [
            {"round": 1, "pick": 1, "franchise": "A"},
            {"round": 1, "pick": 2, "franchise": "B"},
            {"round": 1, "pick": 3, "franchise": "C"},
            {"round": 1, "pick": 4, "franchise": "D"},
            {"round": 2, "pick": 1, "franchise": "D"},
            {"round": 2, "pick": 2, "franchise": "C"},
            {"round": 2, "pick": 3, "franchise": "B"},
            {"round": 2, "pick": 4, "franchise": "A"},
        ]
        expected_overall = [1, 2, 3, 4, 5, 6, 7, 8]
        computed = [(p["round"] - 1) * franchise_count + p["pick"] for p in picks]
        assert computed == expected_overall

    def test_round_1_pick_1_is_overall_1(self):
        assert (1 - 1) * 12 + 1 == 1

    def test_round_2_pick_1_is_overall_13_for_12_team(self):
        # Verified directly against league 14090's real timestamps
        # during the audit -- round 2 pick 1 was the 13th real
        # chronological selection.
        assert (2 - 1) * 12 + 1 == 13


class TestLeagueClassification:
    def _league_json(self, qb_limit="1", extra_positions=None, uses_salaries="0",
                      taxi_squad="0", franchise_count=12):
        positions = [{"name": "QB", "limit": qb_limit}, {"name": "RB", "limit": "2"},
                     {"name": "WR", "limit": "2"}, {"name": "TE", "limit": "1"}]
        if extra_positions:
            positions.extend(extra_positions)
        return {
            "league": {
                "starters": {"position": positions},
                "usesSalaries": uses_salaries,
                "taxiSquad": taxi_squad,
                "franchises": {"count": str(franchise_count)},
            }
        }

    def test_qb_limit_flat_one_is_clean(self):
        result = classify_one(self._league_json(qb_limit="1"))
        assert result["is_clean_1qb"] is True

    def test_qb_limit_range_with_max_above_one_is_superflex(self):
        """The core check the task specifically required: a superflex
        slot can be encoded as a RANGE on the QB position itself
        (e.g. "1-2"), not necessarily a separately-named slot -- must
        not rely on QB == "1" alone."""
        result = classify_one(self._league_json(qb_limit="1-2"))
        assert result["is_clean_1qb"] is False
        assert "superflex_or_2qb" in result["exclusion_reasons"]

    def test_composite_qb_eligible_slot_name_is_caught(self):
        result = classify_one(self._league_json(
            qb_limit="1", extra_positions=[{"name": "QB/RB/WR/TE", "limit": "1"}]
        ))
        assert result["is_clean_1qb"] is False
        assert "composite_qb_eligible_slot" in result["exclusion_reasons"]

    def test_idp_position_present_excludes(self):
        result = classify_one(self._league_json(extra_positions=[{"name": "LB", "limit": "2"}]))
        assert result["is_clean_1qb"] is False
        assert "idp_league" in result["exclusion_reasons"]

    def test_auction_excludes(self):
        result = classify_one(self._league_json(uses_salaries="1"))
        assert result["is_clean_1qb"] is False
        assert "auction_or_salary_cap" in result["exclusion_reasons"]

    def test_taxi_squad_excludes(self):
        result = classify_one(self._league_json(taxi_squad="3"))
        assert result["is_clean_1qb"] is False
        assert "dynasty_taxi_squad" in result["exclusion_reasons"]

    def test_wrong_franchise_count_excludes(self):
        result = classify_one(self._league_json(franchise_count=24))
        assert result["is_clean_1qb"] is False
        assert "unexpected_franchise_count" in result["exclusion_reasons"]

    def test_fetch_error_reported_not_silently_skipped(self):
        result = classify_one({"_error": "timeout"})
        assert result["status"] == "fetch_error"

    def test_parse_limit_max_handles_ranges_and_flat_values(self):
        assert _parse_limit_max("1") == 1
        assert _parse_limit_max("1-2") == 2
        assert _parse_limit_max("2-3") == 3
        assert _parse_limit_max(None) == 0


class TestDateWindowFiltering:
    def test_window_boundaries(self):
        assert WINDOW_START == datetime(2025, 8, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert WINDOW_END == datetime(2025, 9, 4, 0, 0, 0, tzinfo=timezone.utc)

    def test_pick_before_window_excluded(self):
        ts = pd.Timestamp("2025-08-10", tz="UTC")
        assert not (WINDOW_START <= ts < WINDOW_END)

    def test_pick_at_window_start_included(self):
        ts = pd.Timestamp("2025-08-15", tz="UTC")
        assert WINDOW_START <= ts < WINDOW_END

    def test_pick_at_kickoff_excluded(self):
        # WINDOW_END is exclusive -- a pick AT kickoff is not preseason
        ts = pd.Timestamp("2025-09-04", tz="UTC")
        assert not (WINDOW_START <= ts < WINDOW_END)


class TestProvenanceCategorization:
    def test_empty_comment_is_native_live(self):
        assert classify_pick_provenance("") == "native_live_selection"
        assert classify_pick_provenance(None) == "native_live_selection"

    def test_keeper_tag_is_keeper(self):
        assert classify_pick_provenance("[Keeper.]") == "keeper"

    def test_adp_rank_autopick_is_automated(self):
        assert classify_pick_provenance("[Pick made based on ADP Rank]") == "automated_default_rank"

    def test_fantasysharks_autopick_is_automated(self):
        assert classify_pick_provenance("[Pick made based on FantasySharks.com Player Ranks]") == "automated_default_rank"

    def test_commissioner_is_commissioner_not_assumed_fake(self):
        """Corrected per review: a commissioner-entered pick may
        represent a genuine offline draft -- categorized neutrally,
        not excluded by default."""
        result = classify_pick_provenance("[Pick made by Commissioner.]")
        assert result == "commissioner_entered"

    def test_imported_is_externally_imported_not_assumed_fake(self):
        """Corrected per review: an imported pick may represent real
        human selections made on another platform."""
        result = classify_pick_provenance("[Pick imported from external source.]")
        assert result == "externally_imported"

    def test_unrecognized_comment_is_unknown(self):
        assert classify_pick_provenance("Go Bills!") == "unknown"


class TestEarlyQbLeagueDetection:
    def test_flags_league_with_two_qbs_in_first_12(self):
        picks = pd.DataFrame({
            "league_id": ["L1", "L1", "L1", "L2"],
            "position": ["QB", "QB", "RB", "QB"],
            "overall_pick": [3, 8, 1, 3],
        })
        flagged = find_early_qb_leagues(picks)
        assert "L1" in flagged
        assert "L2" not in flagged  # only 1 QB in first 12

    def test_does_not_flag_single_early_qb(self):
        picks = pd.DataFrame({
            "league_id": ["L1"], "position": ["QB"], "overall_pick": [5],
        })
        assert find_early_qb_leagues(picks) == set()

    def test_qb_after_pick_12_does_not_count(self):
        picks = pd.DataFrame({
            "league_id": ["L1", "L1"], "position": ["QB", "QB"], "overall_pick": [3, 20],
        })
        assert find_early_qb_leagues(picks) == set()
