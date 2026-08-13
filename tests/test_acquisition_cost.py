"""
tests/test_acquisition_cost.py

Covers lib/stars_by_value/acquisition_cost.py -- the acquisition-cost
classifier, rookie-QB depth-chart correction, MFL name-matching/
corroboration, and 2010-cohort fallback. Genuinely new logic (not a
promotion), specified via an explicit routing table reviewed and
approved before implementation -- see acquisition_cost.py's own module
docstring for the full table and the two deliberate asymmetries in it.

Fixtures for the 6 named regression cases encode REAL, verified facts,
not invented numbers:
- Herbert 2020, Cruz 2011, Nacua 2023: draftSelPct (17.9%, 6.7%, 18.5%)
  and classifier-relevant facts (draft round, rookie season, real
  Week-1 depth-chart status) are the exact settled values from
  docs/ADP_SOURCE_MATRIX.md parts 3-4.
- Kyren Williams 2023 (12% draftSelPct) and Gary Barnidge 2015 (absent
  from the 2015 AUG15 report entirely -- matched_zero) were NOT in any
  previously-documented threshold table -- both were queried LIVE
  against the real MFL API and cross-checked against real nflverse
  players.csv draft capital during this commit's specification pass,
  not assumed.
- Mike Vick 2010's gsis_id (00-0020245) is confirmed directly against
  data/manual/player_name_overrides.csv (used for a different fix,
  same player, same ID).

These are still synthetic pandas/dict fixtures (not live network
calls) -- the VALUES are real and traceable, the delivery mechanism is
mocked for test speed and determinism, matching this project's
established test convention.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.stars_by_value import acquisition_cost as ac
from config import SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT


def _players_df(*rows):
    cols = ["gsis_id", "position", "draft_year", "draft_round", "draft_pick", "rookie_season"]
    return pd.DataFrame(list(rows), columns=cols)


def _history_df(*rows):
    cols = ["season", "player_id", "games_played", "fantasy_points_ppr"]
    return pd.DataFrame(list(rows), columns=cols)


def _depth_chart_df(*rows):
    cols = ["season", "week", "game_type", "position", "gsis_id", "depth_team"]
    return pd.DataFrame(list(rows), columns=cols)


def _depth_chart_2025_df(*rows):
    cols = ["dt", "team", "gsis_id", "pos_abb", "pos_rank"]
    return pd.DataFrame(list(rows), columns=cols)


def _schedule_df(*rows):
    cols = ["season", "game_type", "week", "gameday", "home_team", "away_team"]
    return pd.DataFrame(list(rows), columns=cols)


def _mfl_players(*entries):
    return {"players": {"player": list(entries)}}


def _mfl_adp(total_drafts, *entries):
    return {"adp": {"totalDrafts": str(total_drafts), "player": list(entries)}}


class TestClassifyDraftStatus:
    def test_rookie_qb_is_likely_undrafted(self):
        players = _players_df({"gsis_id": "00-1", "position": "QB", "draft_year": 2020, "draft_round": 6, "draft_pick": 182, "rookie_season": 2020})
        history = _history_df()
        assert ac.classify_draft_status(2020, "00-1", players, history) == ac.BUCKET_LIKELY_UNDRAFTED

    def test_rookie_qb_first_round_is_still_likely_undrafted_before_correction(self):
        """Rule 1 fires unconditionally for any rookie QB -- the
        depth-chart correction is a SEPARATE step, not part of this
        function."""
        players = _players_df({"gsis_id": "00-2", "position": "QB", "draft_year": 2020, "draft_round": 1, "draft_pick": 1, "rookie_season": 2020})
        history = _history_df()
        assert ac.classify_draft_status(2020, "00-2", players, history) == ac.BUCKET_LIKELY_UNDRAFTED

    def test_day3_rookie_skill_position_is_likely_undrafted(self):
        players = _players_df({"gsis_id": "00-3", "position": "WR", "draft_year": 2023, "draft_round": 5, "draft_pick": 177, "rookie_season": 2023})
        history = _history_df()
        assert ac.classify_draft_status(2023, "00-3", players, history) == ac.BUCKET_LIKELY_UNDRAFTED

    def test_undrafted_rookie_skill_position_is_likely_undrafted(self):
        players = _players_df({"gsis_id": "00-4", "position": "WR", "draft_year": 2010, "draft_round": None, "draft_pick": None, "rookie_season": 2010})
        history = _history_df()
        assert ac.classify_draft_status(2010, "00-4", players, history) == ac.BUCKET_LIKELY_UNDRAFTED

    def test_day1_2_rookie_is_likely_drafted_missing_evidence(self):
        players = _players_df({"gsis_id": "00-5", "position": "RB", "draft_year": 2021, "draft_round": 2, "draft_pick": 45, "rookie_season": 2021})
        history = _history_df()
        assert ac.classify_draft_status(2021, "00-5", players, history) == ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE

    def test_day3_boundary_round_is_still_day1_2(self):
        players = _players_df({"gsis_id": "00-6", "position": "RB", "draft_year": 2021, "draft_round": 3, "draft_pick": 90, "rookie_season": 2021})
        history = _history_df()
        assert ac.classify_draft_status(2021, "00-6", players, history) == ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE

    def test_veteran_with_qualifying_prior_production_is_likely_drafted(self):
        players = _players_df({"gsis_id": "00-7", "position": "RB", "draft_year": 2015, "draft_round": 3, "draft_pick": 80, "rookie_season": 2015})
        history = _history_df({"season": 2019, "player_id": "00-7", "games_played": 10, "fantasy_points_ppr": 120.0})
        assert ac.classify_draft_status(2020, "00-7", players, history) == ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE

    def test_veteran_with_only_partial_qualifying_season_is_ambiguous(self):
        """Neither games nor points alone is enough -- both must clear
        in the SAME prior season."""
        players = _players_df({"gsis_id": "00-8", "position": "RB", "draft_year": 2015, "draft_round": 3, "draft_pick": 80, "rookie_season": 2015})
        history = _history_df(
            {"season": 2017, "player_id": "00-8", "games_played": 10, "fantasy_points_ppr": 20.0},  # games ok, points fail
            {"season": 2018, "player_id": "00-8", "games_played": 1, "fantasy_points_ppr": 90.0},   # points ok, games fail
            {"season": 2019, "player_id": "00-8", "games_played": 2, "fantasy_points_ppr": 30.0},
        )
        assert ac.classify_draft_status(2020, "00-8", players, history) == ac.BUCKET_AMBIGUOUS

    def test_veteran_with_no_qualifying_prior_season_is_ambiguous(self):
        players = _players_df({"gsis_id": "00-9", "position": "WR", "draft_year": 2010, "draft_round": 4, "draft_pick": 110, "rookie_season": 2010})
        history = _history_df()  # no prior-season rows at all
        assert ac.classify_draft_status(2020, "00-9", players, history) == ac.BUCKET_AMBIGUOUS

    def test_missing_players_row_is_ambiguous_not_raised(self):
        players = _players_df()
        history = _history_df()
        assert ac.classify_draft_status(2020, "00-missing", players, history) == ac.BUCKET_AMBIGUOUS

    def test_only_seasons_strictly_before_current_are_considered(self):
        """The current season's own production must not count toward
        its own prior-season lookback."""
        players = _players_df({"gsis_id": "00-10", "position": "WR", "draft_year": 2010, "draft_round": 4, "draft_pick": 110, "rookie_season": 2010})
        history = _history_df({"season": 2020, "player_id": "00-10", "games_played": 16, "fantasy_points_ppr": 200.0})
        assert ac.classify_draft_status(2020, "00-10", players, history) == ac.BUCKET_AMBIGUOUS


class TestRookieQbDepthChartCorrection:
    def test_confirmed_week1_starter_is_corrected_to_ambiguous(self):
        depth = _depth_chart_df({"season": 2012, "week": 1, "game_type": "REG", "position": "QB", "gsis_id": "00-luck", "depth_team": 1})
        result = ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_LIKELY_UNDRAFTED, 2012, "00-luck", True, depth)
        assert result == ac.BUCKET_AMBIGUOUS

    def test_confirmed_backup_stays_likely_undrafted(self):
        depth = _depth_chart_df({"season": 2020, "week": 1, "game_type": "REG", "position": "QB", "gsis_id": "00-herbert", "depth_team": 2})
        result = ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_LIKELY_UNDRAFTED, 2020, "00-herbert", True, depth)
        assert result == ac.BUCKET_LIKELY_UNDRAFTED

    def test_never_fires_for_non_qb_rookie_flag(self):
        depth = _depth_chart_df({"season": 2012, "week": 1, "game_type": "REG", "position": "QB", "gsis_id": "00-x", "depth_team": 1})
        result = ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_LIKELY_UNDRAFTED, 2012, "00-x", False, depth)
        assert result == ac.BUCKET_LIKELY_UNDRAFTED

    def test_never_fires_when_bucket_is_not_likely_undrafted(self):
        depth = _depth_chart_df({"season": 2012, "week": 1, "game_type": "REG", "position": "QB", "gsis_id": "00-y", "depth_team": 1})
        result = ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_AMBIGUOUS, 2012, "00-y", True, depth)
        assert result == ac.BUCKET_AMBIGUOUS

    def test_missing_depth_chart_data_stays_likely_undrafted(self):
        result = ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_LIKELY_UNDRAFTED, 2012, "00-z", True, None)
        assert result == ac.BUCKET_LIKELY_UNDRAFTED

    def test_absent_from_that_weeks_chart_stays_likely_undrafted(self):
        depth = _depth_chart_df({"season": 2012, "week": 1, "game_type": "REG", "position": "QB", "gsis_id": "00-other", "depth_team": 1})
        result = ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_LIKELY_UNDRAFTED, 2012, "00-notfound", True, depth)
        assert result == ac.BUCKET_LIKELY_UNDRAFTED

    def test_2025_with_real_data_but_no_team_or_schedule_raises(self):
        """2025's schema has no week label -- team + schedule_df are
        required to pick the right snapshot. Refuses to silently fall
        back to the pre-2025 week/game_type columns, which do not
        exist in depth_charts_2025.csv."""
        depth = _depth_chart_2025_df({"dt": "2025-09-07T00:00:00Z", "team": "TEN", "gsis_id": "00-w", "pos_abb": "QB", "pos_rank": 1})
        with pytest.raises(RuntimeError, match="requires both 'team' and 'schedule_df'"):
            ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_LIKELY_UNDRAFTED, 2025, "00-w", True, depth)

    def test_2025_empty_depth_chart_stays_likely_undrafted_without_raising(self):
        """Missing/empty depth-chart data is treated the same as every
        other season -- the missing-team/schedule guard only applies
        once there's real depth-chart data to interpret."""
        result = ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_LIKELY_UNDRAFTED, 2025, "00-w", True, _depth_chart_2025_df())
        assert result == ac.BUCKET_LIKELY_UNDRAFTED

    def test_2025_does_not_raise_when_correction_would_not_fire_anyway(self):
        """The guard is specifically about the correction firing, not
        about the season itself -- a non-QB-rookie row in 2025 must
        not be blocked by a rule that would never apply to it."""
        result = ac.apply_rookie_qb_depth_chart_correction(ac.BUCKET_AMBIGUOUS, 2025, "00-v", True, _depth_chart_2025_df())
        assert result == ac.BUCKET_AMBIGUOUS


class TestRookieQbDepthChartCorrection2025Schema:
    """Real, already-validated 2025 rookie-QB cases (2026-07 -- see
    docs/ADP_SOURCE_MATRIX.md's depth-chart-schema entry), re-pinned
    here as regression tests. Real per-team Week 1 2025 kickoff dates
    from nflverse's schedules release: TEN/DAL/PHI etc. played
    2025-09-07 (main Sunday slate); this fixture uses that date
    directly rather than the full 32-team schedule, since only the
    tested teams' games matter for these specific rows."""

    SCHEDULE = _schedule_df(
        {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "DEN", "away_team": "TEN"},
        {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "WAS", "away_team": "NYG"},
        {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "CLE", "away_team": "CIN"},
        {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "LA", "away_team": "HOU"},
    )

    def test_cam_ward_confirmed_starter_corrected_to_ambiguous(self):
        """Real, confirmed Week 1 2025 starter -- the only rookie QB in
        the entire 2025 class with pos_rank==1 at kickoff."""
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "TEN", "gsis_id": "00-ward", "pos_abb": "QB", "pos_rank": 1},
        )
        result = ac.apply_rookie_qb_depth_chart_correction(
            ac.BUCKET_LIKELY_UNDRAFTED, 2025, "00-ward", True, depth,
            team="TEN", schedule_df=self.SCHEDULE,
        )
        assert result == ac.BUCKET_AMBIGUOUS

    def test_jaxson_dart_confirmed_backup_stays_likely_undrafted(self):
        """Real: Russell Wilson was NYG's real Week 1 2025 starter."""
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "NYG", "gsis_id": "00-wilson", "pos_abb": "QB", "pos_rank": 1},
            {"dt": "2025-09-07T00:00:00Z", "team": "NYG", "gsis_id": "00-dart", "pos_abb": "QB", "pos_rank": 2},
        )
        result = ac.apply_rookie_qb_depth_chart_correction(
            ac.BUCKET_LIKELY_UNDRAFTED, 2025, "00-dart", True, depth,
            team="NYG", schedule_df=self.SCHEDULE,
        )
        assert result == ac.BUCKET_LIKELY_UNDRAFTED

    def test_shedeur_sanders_confirmed_backup_stays_likely_undrafted(self):
        """Real: Joe Flacco was CLE's real Week 1 2025 starter."""
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "CLE", "gsis_id": "00-flacco", "pos_abb": "QB", "pos_rank": 1},
            {"dt": "2025-09-07T00:00:00Z", "team": "CLE", "gsis_id": "00-sanders", "pos_abb": "QB", "pos_rank": 3},
        )
        result = ac.apply_rookie_qb_depth_chart_correction(
            ac.BUCKET_LIKELY_UNDRAFTED, 2025, "00-sanders", True, depth,
            team="CLE", schedule_df=self.SCHEDULE,
        )
        assert result == ac.BUCKET_LIKELY_UNDRAFTED

    def test_uses_latest_snapshot_on_or_before_kickoff_not_after(self):
        """A snapshot dated AFTER kickoff must never be used -- only
        confirms the earlier (or same-day) snapshot is picked when
        multiple exist."""
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-05T00:00:00Z", "team": "TEN", "gsis_id": "00-ward", "pos_abb": "QB", "pos_rank": 2},
            {"dt": "2025-09-07T00:00:00Z", "team": "TEN", "gsis_id": "00-ward", "pos_abb": "QB", "pos_rank": 1},
            {"dt": "2025-09-10T00:00:00Z", "team": "TEN", "gsis_id": "00-ward", "pos_abb": "QB", "pos_rank": 2},  # after kickoff, must be ignored
        )
        result = ac.apply_rookie_qb_depth_chart_correction(
            ac.BUCKET_LIKELY_UNDRAFTED, 2025, "00-ward", True, depth,
            team="TEN", schedule_df=self.SCHEDULE,
        )
        assert result == ac.BUCKET_AMBIGUOUS

    def test_player_absent_from_active_roster_snapshot_stays_likely_undrafted(self):
        """Real: several Day-3/UDFA 2025 rookie QBs never appeared on
        an active-roster depth chart at all."""
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "TEN", "gsis_id": "00-ward", "pos_abb": "QB", "pos_rank": 1},
        )
        result = ac.apply_rookie_qb_depth_chart_correction(
            ac.BUCKET_LIKELY_UNDRAFTED, 2025, "00-mccord", True, depth,
            team="PHI", schedule_df=self.SCHEDULE,
        )
        assert result == ac.BUCKET_LIKELY_UNDRAFTED

    def test_team_with_no_scheduled_week1_game_in_fixture_stays_likely_undrafted(self):
        """No RuntimeError -- a team simply absent from the (real,
        just incomplete-in-this-fixture) schedule means no kickoff
        date is known, so the correction can't fire; it doesn't mean
        the schema itself is unsupported."""
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "ZZZ", "gsis_id": "00-nowhere", "pos_abb": "QB", "pos_rank": 1},
        )
        result = ac.apply_rookie_qb_depth_chart_correction(
            ac.BUCKET_LIKELY_UNDRAFTED, 2025, "00-nowhere", True, depth,
            team="ZZZ", schedule_df=self.SCHEDULE,
        )
        assert result == ac.BUCKET_LIKELY_UNDRAFTED


class TestMflNameMatching:
    def test_exact_match_with_last_first_reordering(self):
        directory = _mfl_players({"id": "123", "name": "Vick, Michael", "position": "QB", "team": "PHI"})
        mfl_id, status = ac.match_mfl_player("Michael Vick", "QB", directory)
        assert (mfl_id, status) == ("123", "matched")

    def test_no_candidate_is_unmatched(self):
        directory = _mfl_players({"id": "999", "name": "Someone, Else", "position": "WR", "team": "FA"})
        mfl_id, status = ac.match_mfl_player("Nobody Here", "QB", directory)
        assert (mfl_id, status) == (None, "unmatched")

    def test_position_mismatch_is_unmatched_not_a_false_match(self):
        directory = _mfl_players({"id": "5", "name": "Smith, Steve", "position": "TE", "team": "FA"})
        mfl_id, status = ac.match_mfl_player("Steve Smith", "WR", directory)
        assert (mfl_id, status) == (None, "unmatched")

    def test_same_name_same_position_collision_is_excluded(self):
        """The real, disclosed 'two Steve Smiths' precedent."""
        directory = _mfl_players(
            {"id": "1", "name": "Smith, Steve", "position": "WR", "team": "CAR"},
            {"id": "2", "name": "Smith, Steve", "position": "WR", "team": "NYG"},
        )
        mfl_id, status = ac.match_mfl_player("Steve Smith", "WR", directory)
        assert (mfl_id, status) == (None, "collision")

    def test_same_name_different_position_is_not_a_collision(self):
        directory = _mfl_players(
            {"id": "1", "name": "Smith, Steve", "position": "WR", "team": "CAR"},
            {"id": "2", "name": "Smith, Steve", "position": "DT", "team": "SEA"},
        )
        mfl_id, status = ac.match_mfl_player("Steve Smith", "WR", directory)
        assert (mfl_id, status) == ("1", "matched")


class TestResolveMflResult:
    def test_below_threshold_is_matched_low(self):
        adp = _mfl_adp(5000, {"id": "1", "draftSelPct": "17.9", "rank": "158", "averagePick": "120.0"})
        assert ac.resolve_mfl_result("1", "matched", adp) == ac.MFL_MATCHED_LOW

    def test_at_or_above_threshold_is_matched_high(self):
        adp = _mfl_adp(5000, {"id": "1", "draftSelPct": str(SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT), "rank": "10", "averagePick": "10.0"})
        assert ac.resolve_mfl_result("1", "matched", adp) == ac.MFL_MATCHED_HIGH

    def test_just_below_threshold_is_matched_low(self):
        adp = _mfl_adp(5000, {"id": "1", "draftSelPct": "19.999", "rank": "200", "averagePick": "150.0"})
        assert ac.resolve_mfl_result("1", "matched", adp) == ac.MFL_MATCHED_LOW

    def test_present_in_directory_absent_from_adp_report_is_matched_zero(self):
        adp = _mfl_adp(5000, {"id": "999", "draftSelPct": "50", "rank": "1", "averagePick": "1.0"})
        assert ac.resolve_mfl_result("1", "matched", adp) == ac.MFL_MATCHED_ZERO

    def test_unmatched_status_is_unmatched_regardless_of_adp_content(self):
        adp = _mfl_adp(5000, {"id": "1", "draftSelPct": "5", "rank": "300", "averagePick": "200.0"})
        assert ac.resolve_mfl_result(None, "unmatched", adp) == ac.MFL_UNMATCHED

    def test_collision_status_is_unmatched(self):
        adp = _mfl_adp(5000)
        assert ac.resolve_mfl_result(None, "collision", adp) == ac.MFL_UNMATCHED


class TestRoutingTable2011Plus:
    """Every one of the 12 documented cells, verified directly against
    the approved routing table -- not a sample."""

    @pytest.mark.parametrize("bucket,mfl_result,expected_status,expected_provenance", [
        (ac.BUCKET_LIKELY_UNDRAFTED, ac.MFL_MATCHED_LOW, ac.STATUS_MMC, ac.PROVENANCE_MMC_CORROBORATED),
        (ac.BUCKET_LIKELY_UNDRAFTED, ac.MFL_MATCHED_ZERO, ac.STATUS_MMC, ac.PROVENANCE_MMC_CORROBORATED),
        (ac.BUCKET_LIKELY_UNDRAFTED, ac.MFL_MATCHED_HIGH, ac.STATUS_AMBIGUOUS, ac.PROVENANCE_AMBIGUOUS_DISAGREEMENT),
        (ac.BUCKET_LIKELY_UNDRAFTED, ac.MFL_UNMATCHED, ac.STATUS_AMBIGUOUS, ac.PROVENANCE_AMBIGUOUS_DISAGREEMENT),
        (ac.BUCKET_AMBIGUOUS, ac.MFL_MATCHED_LOW, ac.STATUS_MMC, ac.PROVENANCE_MMC_CORROBORATED),
        (ac.BUCKET_AMBIGUOUS, ac.MFL_MATCHED_ZERO, ac.STATUS_MMC, ac.PROVENANCE_MMC_CORROBORATED),
        (ac.BUCKET_AMBIGUOUS, ac.MFL_MATCHED_HIGH, ac.STATUS_AMBIGUOUS, ac.PROVENANCE_AMBIGUOUS_DISAGREEMENT),
        (ac.BUCKET_AMBIGUOUS, ac.MFL_UNMATCHED, ac.STATUS_AMBIGUOUS, ac.PROVENANCE_AMBIGUOUS_DISAGREEMENT),
        (ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, ac.MFL_MATCHED_LOW, ac.STATUS_AMBIGUOUS, ac.PROVENANCE_AMBIGUOUS_DISAGREEMENT),
        (ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, ac.MFL_MATCHED_ZERO, ac.STATUS_AMBIGUOUS, ac.PROVENANCE_AMBIGUOUS_DISAGREEMENT),
        (ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, ac.MFL_MATCHED_HIGH, ac.STATUS_DRAFTED_MISSING, ac.PROVENANCE_DRAFTED_UNRESOLVED),
        (ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, ac.MFL_UNMATCHED, ac.STATUS_DRAFTED_MISSING, ac.PROVENANCE_DRAFTED_UNRESOLVED),
    ])
    def test_routing_cell(self, bucket, mfl_result, expected_status, expected_provenance):
        status, provenance = ac.route_2011_plus(bucket, mfl_result)
        assert (status, provenance) == (expected_status, expected_provenance)

    def test_table_covers_every_bucket_x_result_combination_exactly_once(self):
        assert len(ac._ROUTING_2011_PLUS) == len(ac.CLASSIFIER_BUCKETS) * len(ac.MFL_RESULTS)

    def test_unknown_combination_raises(self):
        with pytest.raises(ValueError, match="No routing rule"):
            ac.route_2011_plus("not_a_real_bucket", ac.MFL_MATCHED_LOW)

    def test_classifier_alone_never_grants_mmc_when_mfl_unmatched(self):
        """The one-directional asymmetry: likely_undrafted+unmatched
        must NOT be MMC, even though likely_drafted_missing_evidence+
        unmatched IS allowed to resolve via classifier alone."""
        status, _ = ac.route_2011_plus(ac.BUCKET_LIKELY_UNDRAFTED, ac.MFL_UNMATCHED)
        assert status != ac.STATUS_MMC

    def test_classifier_alone_can_resolve_drafted_missing_when_mfl_unmatched(self):
        status, provenance = ac.route_2011_plus(ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, ac.MFL_UNMATCHED)
        assert status == ac.STATUS_DRAFTED_MISSING
        assert provenance == ac.PROVENANCE_DRAFTED_UNRESOLVED


class TestRouting2010:
    def _overrides(self, *rows):
        cols = ["season", "player_id", "override_type", "adp_overall", "adp_round"]
        return pd.DataFrame(list(rows), columns=cols)

    def test_vick_uses_general_minimal_market_override_without_numeric_adp(self):
        overrides = self._overrides({"season": "2010", "player_id": ac.VICK_2010_GSIS_ID, "override_type": "minimal_market_cost", "adp_overall": None, "adp_round": None})
        result = ac.route_2010(ac.VICK_2010_GSIS_ID, overrides)
        assert result["status"] == ac.STATUS_MMC
        assert result["provenance"] == ac.PROVENANCE_MMC_2010_OVERRIDE
        assert result["adp_overall"] is None

    def test_minimal_market_cost_override_resolves_to_mmc(self):
        overrides = self._overrides({"season": "2010", "player_id": "00-other", "override_type": "minimal_market_cost", "adp_overall": None, "adp_round": None})
        result = ac.route_2010("00-other", overrides)
        assert result["status"] == ac.STATUS_MMC
        assert result["provenance"] == ac.PROVENANCE_MMC_2010_OVERRIDE

    def test_usable_adp_override_returns_values_not_a_status(self):
        overrides = self._overrides({"season": "2010", "player_id": "00-other2", "override_type": "usable_adp", "adp_overall": 55.2, "adp_round": 5})
        result = ac.route_2010("00-other2", overrides)
        assert result["status"] is None
        assert result["provenance"] is None
        assert result["adp_overall"] == 55.2
        assert result["adp_round"] == 5

    def test_no_override_and_not_vick_falls_to_ambiguous(self):
        result = ac.route_2010("00-nobody", self._overrides())
        assert result["status"] == ac.STATUS_AMBIGUOUS
        assert result["provenance"] == ac.PROVENANCE_AMBIGUOUS_DISAGREEMENT

    def test_multiple_override_rows_for_same_player_raises(self):
        overrides = self._overrides(
            {"season": "2010", "player_id": "00-dupe", "override_type": "usable_adp", "adp_overall": 10.0, "adp_round": 1},
            {"season": "2010", "player_id": "00-dupe", "override_type": "minimal_market_cost", "adp_overall": None, "adp_round": None},
        )
        with pytest.raises(ValueError, match="Multiple 2010 override rows"):
            ac.route_2010("00-dupe", overrides)


class TestNamedRegressionCases:
    """The 6 named cases -- pinning ACQUISITION-COST resolution
    (status/provenance), not the eventual Star label, per explicit
    instruction. Herbert/Cruz/Nacua/Williams/Barnidge -> MMC. Vick ->
    drafted-cost-existed-but-missing."""

    def test_herbert_2020(self):
        players = _players_df({"gsis_id": "00-herbert", "position": "QB", "draft_year": 2020, "draft_round": 6, "draft_pick": 182, "rookie_season": 2020})
        history = _history_df()
        depth = _depth_chart_df({"season": 2020, "week": 1, "game_type": "REG", "position": "QB", "gsis_id": "00-herbert", "depth_team": 2})
        mfl_players = _mfl_players({"id": "h1", "name": "Herbert, Justin", "position": "QB", "team": "LAC"})
        mfl_adp = _mfl_adp(5892, {"id": "h1", "draftSelPct": "17.9", "rank": "158", "averagePick": "120.0"})

        result = ac.classify_row(
            2020, "00-herbert", "Justin Herbert", "QB", players, history,
            depth_chart_df=depth, mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["classifier_bucket"] == ac.BUCKET_LIKELY_UNDRAFTED
        assert result["mfl_result"] == ac.MFL_MATCHED_LOW
        assert result["status"] == ac.STATUS_MMC
        assert result["provenance"] == ac.PROVENANCE_MMC_CORROBORATED

    def test_cruz_2011(self):
        """2nd-year player, real UDFA, missed his entire rookie (2010)
        season with injury -- no qualifying prior production, lands in
        ambiguous, resolved to MMC via the ambiguous+low-MFL rule."""
        players = _players_df({"gsis_id": "00-cruz", "position": "WR", "draft_year": None, "draft_round": None, "draft_pick": None, "rookie_season": 2010})
        history = _history_df({"season": 2010, "player_id": "00-cruz", "games_played": 0, "fantasy_points_ppr": 0.0})
        mfl_players = _mfl_players({"id": "c1", "name": "Cruz, Victor", "position": "WR", "team": "NYG"})
        mfl_adp = _mfl_adp(7098, {"id": "c1", "draftSelPct": "6.7", "rank": "268", "averagePick": "151.4"})

        result = ac.classify_row(
            2011, "00-cruz", "Victor Cruz", "WR", players, history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["classifier_bucket"] == ac.BUCKET_AMBIGUOUS
        assert result["mfl_result"] == ac.MFL_MATCHED_LOW
        assert result["status"] == ac.STATUS_MMC
        assert result["provenance"] == ac.PROVENANCE_MMC_CORROBORATED

    def test_nacua_2023(self):
        players = _players_df({"gsis_id": "00-nacua", "position": "WR", "draft_year": 2023, "draft_round": 5, "draft_pick": 177, "rookie_season": 2023})
        history = _history_df()
        mfl_players = _mfl_players({"id": "n1", "name": "Nacua, Puka", "position": "WR", "team": "LAR"})
        mfl_adp = _mfl_adp(7923, {"id": "n1", "draftSelPct": "18.5", "rank": "209", "averagePick": "123.0"})

        result = ac.classify_row(
            2023, "00-nacua", "Puka Nacua", "WR", players, history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["classifier_bucket"] == ac.BUCKET_LIKELY_UNDRAFTED
        assert result["mfl_result"] == ac.MFL_MATCHED_LOW
        assert result["status"] == ac.STATUS_MMC
        assert result["provenance"] == ac.PROVENANCE_MMC_CORROBORATED

    def test_kyren_williams_2023(self):
        """Real, verified live this session: MFL draftSelPct=12% (id
        15710), a 2nd-year player in 2023 (drafted 2022 round 5) who
        was buried on the depth chart as a rookie -- no qualifying 2022
        production, lands in ambiguous, resolved to MMC via the
        ambiguous+low-MFL rule."""
        players = _players_df({"gsis_id": "00-kyren", "position": "RB", "draft_year": 2022, "draft_round": 5, "draft_pick": 164, "rookie_season": 2022})
        history = _history_df({"season": 2022, "player_id": "00-kyren", "games_played": 3, "fantasy_points_ppr": 15.0})
        mfl_players = _mfl_players({"id": "15710", "name": "Williams, Kyren", "position": "RB", "team": "LAR"})
        mfl_adp = _mfl_adp(9970, {"id": "15710", "draftSelPct": "12", "rank": "358", "averagePick": "170.71"})

        result = ac.classify_row(
            2023, "00-kyren", "Kyren Williams", "RB", players, history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["classifier_bucket"] == ac.BUCKET_AMBIGUOUS
        assert result["mfl_result"] == ac.MFL_MATCHED_LOW
        assert result["status"] == ac.STATUS_MMC
        assert result["provenance"] == ac.PROVENANCE_MMC_CORROBORATED

    def test_barnidge_2015(self):
        """Real, verified live this session: found in MFL's 2015
        player directory (id 9189) but ABSENT from the 2015 AUG15 ADP
        report entirely -- matched_zero, not unmatched. A 7-year
        veteran in 2015 with no qualifying 2012-2014 production, lands
        in ambiguous, resolved to MMC via the ambiguous+matched_zero
        rule (an even stronger signal than a low nonzero percentage)."""
        players = _players_df({"gsis_id": "00-barnidge", "position": "TE", "draft_year": 2008, "draft_round": 5, "draft_pick": 141, "rookie_season": 2008})
        history = _history_df(
            {"season": 2012, "player_id": "00-barnidge", "games_played": 2, "fantasy_points_ppr": 5.0},
            {"season": 2013, "player_id": "00-barnidge", "games_played": 1, "fantasy_points_ppr": 0.0},
            {"season": 2014, "player_id": "00-barnidge", "games_played": 3, "fantasy_points_ppr": 10.0},
        )
        mfl_players = _mfl_players({"id": "9189", "name": "Barnidge, Gary", "position": "TE", "team": "CLE"})
        mfl_adp = _mfl_adp(4628)  # confirmed empty player list -- absent entirely

        result = ac.classify_row(
            2015, "00-barnidge", "Gary Barnidge", "TE", players, history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["classifier_bucket"] == ac.BUCKET_AMBIGUOUS
        assert result["mfl_result"] == ac.MFL_MATCHED_ZERO
        assert result["status"] == ac.STATUS_MMC
        assert result["provenance"] == ac.PROVENANCE_MMC_CORROBORATED

    def test_vick_2010(self):
        """Governed evidence resolves categorical minimal market cost;
        it never fabricates numeric ADP."""
        players = _players_df({"gsis_id": ac.VICK_2010_GSIS_ID, "position": "QB", "draft_year": 2001, "draft_round": 1, "draft_pick": 1, "rookie_season": 2001})
        history = _history_df(
            {"season": 2007, "player_id": ac.VICK_2010_GSIS_ID, "games_played": 0, "fantasy_points_ppr": 0.0},
            {"season": 2008, "player_id": ac.VICK_2010_GSIS_ID, "games_played": 0, "fantasy_points_ppr": 0.0},
            {"season": 2009, "player_id": ac.VICK_2010_GSIS_ID, "games_played": 0, "fantasy_points_ppr": 0.0},
        )
        overrides = pd.DataFrame([{"season": 2010, "player_id": ac.VICK_2010_GSIS_ID, "override_type": "minimal_market_cost", "adp_overall": None, "adp_round": None}])

        result = ac.classify_row(
            2010, ac.VICK_2010_GSIS_ID, "Michael Vick", "QB", players, history,
            overrides_2010_df=overrides,
        )
        assert result["classifier_bucket"] == ac.BUCKET_AMBIGUOUS  # audit trail only -- does not drive the outcome
        assert result["status"] == ac.STATUS_MMC
        assert result["provenance"] == ac.PROVENANCE_MMC_2010_OVERRIDE
        assert result["adp_overall"] is None


class TestClassifyRowValidation:
    def test_season_2010_without_overrides_df_raises(self):
        players = _players_df({"gsis_id": "00-1", "position": "QB", "draft_year": 2001, "draft_round": 1, "draft_pick": 1, "rookie_season": 2001})
        with pytest.raises(ValueError, match="overrides_2010_df is required"):
            ac.classify_row(2010, "00-1", "Someone", "QB", players, _history_df())

    def test_pre_2011_non_2010_season_raises(self):
        players = _players_df()
        with pytest.raises(ValueError, match="before SBV_MFL_AVAILABLE_FROM_SEASON"):
            ac.classify_row(2009, "00-1", "Someone", "QB", players, _history_df())

    def test_2011_plus_without_mfl_responses_raises(self):
        players = _players_df({"gsis_id": "00-1", "position": "QB", "draft_year": 2020, "draft_round": 6, "draft_pick": 180, "rookie_season": 2020})
        with pytest.raises(ValueError, match="mfl_adp_response and mfl_players_response are required"):
            ac.classify_row(2020, "00-1", "Someone", "QB", players, _history_df())


class TestTeamScheduleDfPassthrough:
    """Fixed 2026-07: classify_row() previously never passed team/
    schedule_df through to apply_rookie_qb_depth_chart_correction(),
    so that function's real season==2025 path could never actually be
    reached correctly via the normal orchestration entry point (only
    directly, in isolation, as tested in TestRookieQbDepthChartCorrection2025Schema
    above). These tests prove the full round-trip through classify_row()
    itself, not just the lower-level function."""

    SCHEDULE = _schedule_df(
        {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "DEN", "away_team": "TEN"},
    )

    def test_confirmed_2025_starter_reaches_ambiguous_via_classify_row(self):
        players = _players_df({
            "gsis_id": "00-ward", "position": "QB", "draft_year": 2025,
            "draft_round": 1, "draft_pick": 1, "rookie_season": 2025,
        })
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "TEN", "gsis_id": "00-ward", "pos_abb": "QB", "pos_rank": 1},
        )
        mfl_players = _mfl_players({"id": "1", "name": "Ward, Cam", "position": "QB", "team": "TEN"})
        mfl_adp = _mfl_adp(200, {"id": "1", "draftSelPct": "45.0"})

        result = ac.classify_row(
            2025, "00-ward", "Cam Ward", "QB", players, _history_df(),
            depth_chart_df=depth, mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
            team="TEN", schedule_df=self.SCHEDULE,
        )
        assert result["classifier_bucket"] == ac.BUCKET_AMBIGUOUS, (
            "Real Week-1 starter status did not reach the classifier via "
            "classify_row()'s team/schedule_df passthrough."
        )

    def test_confirmed_2025_backup_stays_likely_undrafted_via_classify_row(self):
        players = _players_df({
            "gsis_id": "00-dart", "position": "QB", "draft_year": 2025,
            "draft_round": 1, "draft_pick": 25, "rookie_season": 2025,
        })
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "TEN", "gsis_id": "00-wilson", "pos_abb": "QB", "pos_rank": 1},
            {"dt": "2025-09-07T00:00:00Z", "team": "TEN", "gsis_id": "00-dart", "pos_abb": "QB", "pos_rank": 2},
        )
        mfl_players = _mfl_players({"id": "2", "name": "Dart, Jaxson", "position": "QB", "team": "TEN"})
        mfl_adp = _mfl_adp(200, {"id": "2", "draftSelPct": "5.0"})

        result = ac.classify_row(
            2025, "00-dart", "Jaxson Dart", "QB", players, _history_df(),
            depth_chart_df=depth, mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
            team="TEN", schedule_df=self.SCHEDULE,
        )
        assert result["classifier_bucket"] == ac.BUCKET_LIKELY_UNDRAFTED

    def test_2025_rookie_qb_without_team_or_schedule_raises_via_classify_row(self):
        players = _players_df({
            "gsis_id": "00-ward", "position": "QB", "draft_year": 2025,
            "draft_round": 1, "draft_pick": 1, "rookie_season": 2025,
        })
        depth = _depth_chart_2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "TEN", "gsis_id": "00-ward", "pos_abb": "QB", "pos_rank": 1},
        )
        mfl_players = _mfl_players({"id": "1", "name": "Ward, Cam", "position": "QB", "team": "TEN"})
        mfl_adp = _mfl_adp(200, {"id": "1", "draftSelPct": "45.0"})

        with pytest.raises(RuntimeError, match="requires both 'team' and 'schedule_df'"):
            ac.classify_row(
                2025, "00-ward", "Cam Ward", "QB", players, _history_df(),
                depth_chart_df=depth, mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
            )

    def test_non_qb_rookie_2025_row_unaffected_by_missing_team_or_schedule(self):
        """The passthrough must not become a NEW blocking requirement
        for rows that never reach the depth-chart correction at all --
        a non-rookie or non-QB row must classify normally without
        team/schedule_df."""
        players = _players_df({
            "gsis_id": "00-vet", "position": "WR", "draft_year": 2018,
            "draft_round": 3, "draft_pick": 75, "rookie_season": 2018,
        })
        mfl_players = _mfl_players({"id": "3", "name": "Someone, Vet", "position": "WR", "team": "TEN"})
        mfl_adp = _mfl_adp(200, {"id": "3", "draftSelPct": "45.0"})

        result = ac.classify_row(
            2025, "00-vet", "Vet Someone", "WR", players, _history_df(),
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["classifier_bucket"] in (ac.BUCKET_AMBIGUOUS, ac.BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE)


class TestNoResearchImports:
    def test_module_does_not_import_research(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(ac))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "research" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "research" not in module
