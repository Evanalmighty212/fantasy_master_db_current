"""
tests/test_dataset2_depth_chart_traits.py

Covers lib/dataset2/depth_chart_traits.py -- Dataset 2 family #10
(projected depth-chart position) plus the depth-chart-dependent
#86/#88 sub-signals. Protects the tie-preserving design approved
2026-07 after real 2020/2025 nflverse depth-chart data showed the two
schema eras are not naturally comparable for every position (see the
module's own docstring for the full real-data findings this design is
built on).

What's specifically protected here, per the approved test list:
- Offensive filtering excludes special-teams rows for all four
  positions, both schema eras.
- Tied historical rank-1 players remain tied and are ALL classified
  as starters -- never split into a fabricated 1-vs-2 order.
- A historical 3-player WR starter group is not arbitrarily ordered
  (all three keep native_rank == 1).
- 2025's strict vendor ordering is preserved as real source data, but
  its own schema_era label always marks it distinctly from the
  tie-preserving historical schema, so a consumer can test for a
  difference rather than silently pooling the two.
- starter_group_size is computed correctly (a real 3-wide WR group, a
  real 2-player RB committee, and an unremarkable single-RB team all
  produce the right number) and position_starter_count is the FIXED
  structural reference, never derived from a specific team's ties.
- Preseason-timing validation: pre-2025 uses exactly week==1/REG;
  2025 selects the correct per-team snapshot via the real kickoff
  date, never a snapshot after kickoff.
- Missingness: no depth-chart match -> every field null, row kept.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import depth_chart_traits as dct


def _population_df(*rows):
    cols = ["season", "player_id", "position"]
    return pd.DataFrame(list(rows), columns=cols)


def _pre2025_df(*rows):
    cols = ["season", "club_code", "week", "game_type", "formation", "gsis_id", "position", "depth_team"]
    return pd.DataFrame(list(rows), columns=cols)


def _schema2025_df(*rows):
    cols = ["dt", "team", "gsis_id", "pos_grp", "pos_abb", "pos_rank"]
    return pd.DataFrame(list(rows), columns=cols)


def _schedule_df(*rows):
    cols = ["season", "game_type", "week", "gameday", "home_team", "away_team"]
    return pd.DataFrame(list(rows), columns=cols)


EMPTY_2025 = _schema2025_df()
EMPTY_SCHEDULE = _schedule_df()


class TestOffensiveFilteringExcludesSpecialTeams:
    def test_pre2025_special_teams_row_excluded_for_all_four_positions(self):
        pop = _population_df(
            {"season": 2020, "player_id": "00-qb", "position": "QB"},
            {"season": 2020, "player_id": "00-rb", "position": "RB"},
            {"season": 2020, "player_id": "00-wr", "position": "WR"},
            {"season": 2020, "player_id": "00-te", "position": "TE"},
        )
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Special Teams", "gsis_id": "00-qb", "position": "QB", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Special Teams", "gsis_id": "00-rb", "position": "RB", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Special Teams", "gsis_id": "00-wr", "position": "WR", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Special Teams", "gsis_id": "00-te", "position": "TE", "depth_team": 1},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        # every row should be null -- none of these matched a real offensive row
        assert out["depth_chart_status"].isna().all()

    def test_2025_special_teams_row_excluded_for_all_four_positions(self):
        pop = _population_df(
            {"season": 2025, "player_id": "00-qb", "position": "QB"},
            {"season": 2025, "player_id": "00-rb", "position": "RB"},
            {"season": 2025, "player_id": "00-wr", "position": "WR"},
            {"season": 2025, "player_id": "00-te", "position": "TE"},
        )
        schema2025 = _schema2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "ATL", "gsis_id": "00-qb", "pos_grp": "Special Teams", "pos_abb": "QB", "pos_rank": 1},
            {"dt": "2025-09-07T00:00:00Z", "team": "ATL", "gsis_id": "00-rb", "pos_grp": "Special Teams", "pos_abb": "RB", "pos_rank": 1},
            {"dt": "2025-09-07T00:00:00Z", "team": "ATL", "gsis_id": "00-wr", "pos_grp": "Special Teams", "pos_abb": "WR", "pos_rank": 1},
            {"dt": "2025-09-07T00:00:00Z", "team": "ATL", "gsis_id": "00-te", "pos_grp": "Special Teams", "pos_abb": "TE", "pos_rank": 1},
        )
        schedule = _schedule_df(
            {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "ATL", "away_team": "TB"},
        )
        out = dct.build_depth_chart_traits(pop, _pre2025_df(), schema2025, schedule)
        assert out["depth_chart_status"].isna().all()


class TestTiedHistoricalRank1PlayersRemainTied:
    def test_wr_three_way_starter_group_not_arbitrarily_ordered(self):
        pop = _population_df(
            {"season": 2020, "player_id": "00-wr1", "position": "WR"},
            {"season": 2020, "player_id": "00-wr2", "position": "WR"},
            {"season": 2020, "player_id": "00-wr3", "position": "WR"},
        )
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-wr1", "position": "WR", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-wr2", "position": "WR", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-wr3", "position": "WR", "depth_team": 1},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        # ALL three keep native_rank == 1 -- none is arbitrarily promoted/demoted
        assert (out["depth_chart_native_rank"] == 1).all()
        assert (out["depth_chart_status"] == dct.DEPTH_CHART_STATUS_STARTER).all()
        assert (out["depth_rank_tied"] == True).all()  # noqa: E712

    def test_rb_committee_tie_both_classified_as_starters(self):
        pop = _population_df(
            {"season": 2020, "player_id": "00-white", "position": "RB"},
            {"season": 2020, "player_id": "00-michel", "position": "RB"},
        )
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "NE", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-white", "position": "RB", "depth_team": 1},
            {"season": 2020, "club_code": "NE", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-michel", "position": "RB", "depth_team": 1},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        assert (out["depth_chart_status"] == dct.DEPTH_CHART_STATUS_STARTER).all()
        assert (out["depth_rank_tied"] == True).all()  # noqa: E712
        assert (out["starter_group_size"] == 2).all()

    def test_clean_single_starter_not_flagged_tied(self):
        pop = _population_df(
            {"season": 2020, "player_id": "00-gurley", "position": "RB"},
            {"season": 2020, "player_id": "00-hill", "position": "RB"},
        )
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-gurley", "position": "RB", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-hill", "position": "RB", "depth_team": 2},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        starter_row = out[out["player_id"] == "00-gurley"].iloc[0]
        backup_row = out[out["player_id"] == "00-hill"].iloc[0]
        assert starter_row["depth_rank_tied"] == False  # noqa: E712
        assert starter_row["depth_chart_status"] == dct.DEPTH_CHART_STATUS_STARTER
        assert backup_row["depth_chart_status"] == dct.DEPTH_CHART_STATUS_BACKUP
        assert starter_row["starter_group_size"] == 1


class Test2025StrictOrderPreservedButLabeledDistinctly:
    def test_2025_never_flagged_tied_and_schema_era_label_correct(self):
        pop = _population_df(
            {"season": 2025, "player_id": "00-london", "position": "WR"},
            {"season": 2025, "player_id": "00-mooney", "position": "WR"},
            {"season": 2025, "player_id": "00-mccloud", "position": "WR"},
        )
        schema2025 = _schema2025_df(
            {"dt": "2025-08-03T10:09:07Z", "team": "ATL", "gsis_id": "00-london", "pos_grp": "3WR 1TE", "pos_abb": "WR", "pos_rank": 1},
            {"dt": "2025-08-03T10:09:07Z", "team": "ATL", "gsis_id": "00-mooney", "pos_grp": "3WR 1TE", "pos_abb": "WR", "pos_rank": 2},
            {"dt": "2025-08-03T10:09:07Z", "team": "ATL", "gsis_id": "00-mccloud", "pos_grp": "3WR 1TE", "pos_abb": "WR", "pos_rank": 3},
        )
        schedule = _schedule_df(
            {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "ATL", "away_team": "TB"},
        )
        out = dct.build_depth_chart_traits(pop, _pre2025_df(), schema2025, schedule)
        assert (out["depth_rank_tied"] == False).all()  # noqa: E712
        assert (out["depth_chart_schema_era"] == dct.SCHEMA_ERA_2025_STRICT_ORDER).all()
        london = out[out["player_id"] == "00-london"].iloc[0]
        assert london["depth_chart_status"] == dct.DEPTH_CHART_STATUS_STARTER
        assert london["starter_group_size"] == 1  # only ONE player has native_rank==1 in 2025

    def test_historical_schema_era_label_distinct_from_2025(self):
        pop = _population_df({"season": 2020, "player_id": "00-1", "position": "QB"})
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-1", "position": "QB", "depth_team": 1},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        assert out.loc[0, "depth_chart_schema_era"] == dct.SCHEMA_ERA_HISTORICAL
        assert dct.SCHEMA_ERA_HISTORICAL != dct.SCHEMA_ERA_2025_STRICT_ORDER


class TestStarterGroupSizeAndStructuralCount:
    def test_position_starter_count_is_fixed_not_derived_from_ties(self):
        """A real 2-player RB committee (starter_group_size=2) must NOT
        change RB's structural position_starter_count (still 1)."""
        pop = _population_df(
            {"season": 2020, "player_id": "00-white", "position": "RB"},
            {"season": 2020, "player_id": "00-michel", "position": "RB"},
        )
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "NE", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-white", "position": "RB", "depth_team": 1},
            {"season": 2020, "club_code": "NE", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-michel", "position": "RB", "depth_team": 1},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        assert (out["starter_group_size"] == 2).all()
        assert (out["position_starter_count"] == 1).all()  # structural RB constant, unaffected by the real tie

    def test_wr_structural_count_is_three(self):
        pop = _population_df({"season": 2020, "player_id": "00-1", "position": "WR"})
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-1", "position": "WR", "depth_team": 1},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        assert out.loc[0, "position_starter_count"] == 3

    def test_backup_row_shows_its_teams_real_starter_group_size(self):
        """A bench WR (rank 2) should still see how crowded the real
        starting group was, not just starters themselves."""
        pop = _population_df(
            {"season": 2020, "player_id": "00-wr1", "position": "WR"},
            {"season": 2020, "player_id": "00-wr2", "position": "WR"},
            {"season": 2020, "player_id": "00-wr3", "position": "WR"},
            {"season": 2020, "player_id": "00-bench", "position": "WR"},
        )
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-wr1", "position": "WR", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-wr2", "position": "WR", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-wr3", "position": "WR", "depth_team": 1},
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-bench", "position": "WR", "depth_team": 2},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        bench_row = out[out["player_id"] == "00-bench"].iloc[0]
        assert bench_row["depth_chart_status"] == dct.DEPTH_CHART_STATUS_BACKUP
        assert bench_row["starter_group_size"] == 3


class TestPreseasonTimingValidation:
    def test_pre2025_only_week1_reg_used_not_later_weeks(self):
        pop = _population_df({"season": 2020, "player_id": "00-1", "position": "QB"})
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "REG", "formation": "Offense", "gsis_id": "00-1", "position": "QB", "depth_team": 2},
            {"season": 2020, "club_code": "ATL", "week": 8, "game_type": "REG", "formation": "Offense", "gsis_id": "00-1", "position": "QB", "depth_team": 1},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        # must use the week-1 row (rank 2), never the later week-8 promotion
        assert out.loc[0, "depth_chart_native_rank"] == 2

    def test_pre2025_playoff_game_type_excluded(self):
        pop = _population_df({"season": 2020, "player_id": "00-1", "position": "QB"})
        pre2025 = _pre2025_df(
            {"season": 2020, "club_code": "ATL", "week": 1, "game_type": "WC", "formation": "Offense", "gsis_id": "00-1", "position": "QB", "depth_team": 1},
        )
        out = dct.build_depth_chart_traits(pop, pre2025, EMPTY_2025, EMPTY_SCHEDULE)
        assert pd.isna(out.loc[0, "depth_chart_status"])

    def test_2025_uses_latest_snapshot_on_or_before_kickoff_not_after(self):
        pop = _population_df({"season": 2025, "player_id": "00-1", "position": "QB"})
        schema2025 = _schema2025_df(
            {"dt": "2025-09-05T00:00:00Z", "team": "ATL", "gsis_id": "00-1", "pos_grp": "3WR 1TE", "pos_abb": "QB", "pos_rank": 2},
            {"dt": "2025-09-07T00:00:00Z", "team": "ATL", "gsis_id": "00-1", "pos_grp": "3WR 1TE", "pos_abb": "QB", "pos_rank": 1},
            {"dt": "2025-09-10T00:00:00Z", "team": "ATL", "gsis_id": "00-1", "pos_grp": "3WR 1TE", "pos_abb": "QB", "pos_rank": 2},  # after kickoff, must be ignored
        )
        schedule = _schedule_df(
            {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "ATL", "away_team": "TB"},
        )
        out = dct.build_depth_chart_traits(pop, _pre2025_df(), schema2025, schedule)
        assert out.loc[0, "depth_chart_native_rank"] == 1

    def test_2025_team_with_no_resolvable_kickoff_is_null_not_an_error(self):
        pop = _population_df({"season": 2025, "player_id": "00-1", "position": "QB"})
        schema2025 = _schema2025_df(
            {"dt": "2025-09-07T00:00:00Z", "team": "ZZZ", "gsis_id": "00-1", "pos_grp": "3WR 1TE", "pos_abb": "QB", "pos_rank": 1},
        )
        out = dct.build_depth_chart_traits(pop, _pre2025_df(), schema2025, EMPTY_SCHEDULE)
        assert pd.isna(out.loc[0, "depth_chart_status"])


class TestMissingnessDisclosed:
    def test_no_matching_depth_chart_row_all_fields_null_row_kept(self):
        pop = _population_df({"season": 2020, "player_id": "00-nowhere", "position": "WR"})
        out = dct.build_depth_chart_traits(pop, _pre2025_df(), EMPTY_2025, EMPTY_SCHEDULE)
        assert len(out) == 1
        assert pd.isna(out.loc[0, "depth_chart_native_rank"])
        assert pd.isna(out.loc[0, "depth_chart_status"])
        assert pd.isna(out.loc[0, "depth_chart_schema_era"])


class TestRequiredColumnValidation:
    def test_population_missing_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2020]})
        with pytest.raises(ValueError, match="population is missing required columns"):
            dct.build_depth_chart_traits(bad_pop, _pre2025_df(), EMPTY_2025, EMPTY_SCHEDULE)

    def test_pre2025_missing_column_raises(self):
        pop = _population_df({"season": 2020, "player_id": "00-1", "position": "QB"})
        bad_pre2025 = pd.DataFrame({"season": [2020]})
        with pytest.raises(ValueError, match="depth_chart_pre2025_df is missing required columns"):
            dct.build_depth_chart_traits(pop, bad_pre2025, EMPTY_2025, EMPTY_SCHEDULE)

    def test_2025_missing_column_raises(self):
        pop = _population_df({"season": 2025, "player_id": "00-1", "position": "QB"})
        bad_2025 = pd.DataFrame({"team": ["ATL"]})
        schedule = _schedule_df(
            {"season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-07", "home_team": "ATL", "away_team": "TB"},
        )
        with pytest.raises(ValueError, match="depth_chart_2025_df is missing required columns"):
            dct.build_depth_chart_traits(pop, _pre2025_df(), bad_2025, schedule)


class TestRowCountPreserved:
    def test_one_row_per_season_player(self):
        pop = _population_df(
            {"season": 2020, "player_id": "00-1", "position": "QB"},
            {"season": 2020, "player_id": "00-2", "position": "RB"},
        )
        out = dct.build_depth_chart_traits(pop, _pre2025_df(), EMPTY_2025, EMPTY_SCHEDULE)
        assert len(out) == 2
