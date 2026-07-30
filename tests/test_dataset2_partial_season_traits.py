"""
tests/test_dataset2_partial_season_traits.py

Protects lib/dataset2/partial_season_traits.py -- REWRITTEN 2026-07
after a real, confirmed week-boundary bug was found and fixed (see
that module's own docstring and
research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md §0).
Regression-tests, per instruction: a real 16-game season played across
Weeks 1-17, a real 17-game season played across Weeks 1-18, postseason
exclusion, and final-N logic never returning more than N real TEAM
games. Also proves the redefined team-game-vs-active-game window
distinction, inactive-game zero-filling, and traded-player exclusion
from team-game windows.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (
    DATASET2_EFFICIENCY_VOLUME_EXPLORATORY,
    DATASET2_EFFICIENCY_VOLUME_SENSITIVITY,
    DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY,
    DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_SENSITIVITY,
)
from lib.dataset2.partial_season_traits import (
    OPPORTUNITY_STATUS_PENDING,
    TEAM_GAME_STATUS_APPLICABLE,
    TEAM_GAME_STATUS_UNAVAILABLE_TRADED,
    build_active_game_efficiency_traits,
    build_active_game_final_n_traits,
    build_team_game_efficiency_traits,
    build_team_game_final_n_traits,
    build_team_game_half_split_traits,
)


def _population(*rows):
    return pd.DataFrame([{"season": s, "player_id": p, "position": pos} for s, p, pos in rows])


def _weekly_all_positions(rows):
    """rows: list of (season, week, team, season_type)."""
    return pd.DataFrame([{"season": s, "week": w, "team": t, "season_type": st} for s, w, t, st in rows])


def _weekly_player(rows):
    """rows: list of (season, player_id, week, team, ppg)."""
    return pd.DataFrame(
        [{"season": s, "player_id": p, "week": w, "team": t, "fantasy_points_ppr": pts} for s, p, w, t, pts in rows]
    )


def _weekly_player_metric(rows, col_names):
    """rows: list of (season, player_id, week, team, *values); col_names:
    names for the trailing values in order (e.g. ["targets","receiving_yards"])."""
    records = []
    for season, player_id, week, team, *values in rows:
        record = {"season": season, "player_id": player_id, "week": week, "team": team}
        record.update(zip(col_names, values))
        records.append(record)
    return pd.DataFrame(records)


# Real 2015 (16-game era) team AAA: real bye at week 9 -> 16 real games
# across weeks 1-17. Real 2021 (17-game era) team BBB: real bye at
# week 10 -> 17 real games across weeks 1-18. Matches the real patterns
# already verified directly against real nflverse data (see the module
# docstring / proposal doc §0).
AAA_2015_WEEKS = [wk for wk in range(1, 18) if wk != 9]  # 16 real games, real bye at week 9
BBB_2021_WEEKS = [wk for wk in range(1, 19) if wk != 10]  # 17 real games, real bye at week 10


class TestTeamGameFinalNRealBoundaries:
    """Regression: a real 16-game season played across Weeks 1-17, a
    real 17-game season played across Weeks 1-18, and final-N logic
    never returning more than N real team games."""

    def test_16_game_season_final_4_never_exceeds_4_team_games(self):
        pop = _population((2015, "P1", "WR"))
        # another player on the team supplies every real team-week
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player([(2015, "P1", wk, "AAA", 10.0) for wk in AAA_2015_WEEKS[-2:]])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_final_n_games"] == 4
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE

    def test_17_game_season_final_4_never_exceeds_4_team_games(self):
        pop = _population((2021, "P1", "WR"))
        wap = _weekly_all_positions([(2021, wk, "BBB", "REG") for wk in BBB_2021_WEEKS])
        wp = _weekly_player([(2021, "P1", wk, "BBB", 10.0) for wk in BBB_2021_WEEKS[-2:]])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        assert out.iloc[0]["team_final_n_games"] == 4

    def test_real_final_4_weeks_are_the_true_last_4_team_games_16_game_era(self):
        # The team's true last 4 real games for AAA/2015 are the final
        # 4 entries of AAA_2015_WEEKS (weeks 14,15,16,17 -- the bye at
        # week 9 already excluded upstream).
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player([(2015, "P1", wk, "AAA", 1.0) for wk in AAA_2015_WEEKS])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        assert out.iloc[0]["team_final_n_active_games"] == 4
        # With the OLD buggy boundary this would have pulled 5 real
        # weeks (13-17) instead of the true last 4 (14-17).

    def test_postseason_weeks_excluded_from_team_game_index(self):
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions(
            [(2023, wk, "KC", "REG") for wk in range(1, 19)] + [(2023, 19, "KC", "POST"), (2023, 20, "KC", "POST")]
        )
        wp = _weekly_player([(2023, "P1", wk, "KC", 5.0) for wk in range(1, 19)])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        # If postseason leaked in, the real final-4 would pull from
        # weeks 17-20 instead of the true real REG weeks 15-18.
        assert out.iloc[0]["team_final_n_active_games"] == 4
        assert out.iloc[0]["team_final_n_points_per_team_game"] == 5.0
        assert out.iloc[0]["team_final_n_points_per_active_game"] == 5.0


class TestTeamGameFinalNInactiveZeroFill:
    def test_inactive_team_game_zero_filled_not_dropped(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        # player only has real usage in 2 of the team's real final 4 games
        wp = _weekly_player([(2015, "P1", last4[0], "AAA", 20.0), (2015, "P1", last4[2], "AAA", 10.0)])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_final_n_games"] == 4  # window always has 4 real team games
        assert row["team_final_n_active_games"] == 2  # only 2 had real usage
        # per-team-game rate: real, defined, NEVER floor-gated -- (20+10+0+0)/4
        assert row["team_final_n_points_per_team_game"] == 7.5
        # per-active-game rate: floor-gated, null below the sensitivity floor (2 < 3)
        assert pd.isna(row["team_final_n_points_per_active_game"])

    def test_fully_inactive_applicable_window_gets_zero_per_team_game_not_null(self):
        # The exact case §1a-0 of the reliability proposal distinguishes:
        # a rostered, applicable player with ZERO real usage across the
        # entire window must show a real 0.0 per-team-game rate, not a
        # null -- a real "produced nothing" fact, never confused with
        # "unavailable."
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        # a real row outside the final-4 window establishes the single team
        wp = _weekly_player([(2015, "P1", AAA_2015_WEEKS[0], "AAA", 0.0)])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE
        assert row["team_final_n_active_games"] == 0
        assert row["team_final_n_points_per_team_game"] == 0.0
        assert not pd.isna(row["team_final_n_points_per_team_game"])
        assert pd.isna(row["team_final_n_points_per_active_game"])


class TestTeamGameWindowTradedPlayerExclusion:
    def test_traded_player_gets_unavailable_traded_status(self):
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions(
            [(2023, wk, "KC", "REG") for wk in range(1, 10)] + [(2023, wk, "SF", "REG") for wk in range(10, 19)]
        )
        wp = _weekly_player(
            [(2023, "P1", wk, "KC", 5.0) for wk in range(1, 10)] + [(2023, "P1", wk, "SF", 5.0) for wk in range(10, 19)]
        )
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_UNAVAILABLE_TRADED
        assert pd.isna(row["team_final_n_games"])
        assert pd.isna(row["team_final_n_points_per_team_game"])
        assert pd.isna(row["team_final_n_points_per_active_game"])

    def test_traded_player_still_gets_a_valid_active_game_window(self):
        # Team-game windows exclude traded players; active-game windows
        # never filter by team at all, so a traded player must remain
        # fully available there (and to a dedicated trade-split
        # analysis, not built in this module).
        pop = _population((2023, "P1", "WR"))
        wp = _weekly_player(
            [(2023, "P1", wk, "KC", 5.0) for wk in range(1, 10)] + [(2023, "P1", wk, "SF", 5.0) for wk in range(10, 19)]
        )
        out = build_active_game_final_n_traits(pop, wp, n=4)
        row = out.iloc[0]
        assert row["active_final_n_games"] == 4
        assert row["active_final_n_games_ppg"] == 5.0

    def test_single_team_player_gets_applicable(self):
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions([(2023, wk, "KC", "REG") for wk in range(1, 19)])
        wp = _weekly_player([(2023, "P1", wk, "KC", 5.0) for wk in range(1, 19)])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        assert out.iloc[0]["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE

    def test_player_with_no_real_rows_gets_no_team_evidence_status(self):
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions([(2023, wk, "KC", "REG") for wk in range(1, 19)])
        # P1 never appears -- practice squad / unrostered. An empty
        # weekly_player still needs the real required columns present.
        wp = pd.DataFrame(columns=["season", "player_id", "week", "team", "fantasy_points_ppr"])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_game_window_status"] == "unavailable_no_team_evidence"
        assert pd.isna(row["team_final_n_games"])

    def test_rostered_but_fully_inactive_player_represented_with_zero_not_dropped(self):
        # A player on the roster (single real team) but with ZERO real
        # usage across the entire window must show up as a real,
        # meaningful "applicable, zero opportunity" row -- never
        # conflated with "unavailable" and never dropped.
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        # P1 has zero real rows in weekly_player, but IS listed as
        # rostered via at least one non-final-window real row so a
        # single team is identifiable.
        wp = _weekly_player([(2015, "P1", AAA_2015_WEEKS[0], "AAA", 0.0)])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE
        assert row["team_final_n_games"] == 4
        assert row["team_final_n_active_games"] == 0
        assert not pd.isna(row["team_final_n_games"])  # present, not dropped


class TestTeamGameFinalNFloorEnforcement:
    def test_primary_floor_from_config(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        active_n = DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY
        wp = _weekly_player([(2015, "P1", wk, "AAA", 10.0) for wk in last4[:active_n]])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_final_n_active_games"] == active_n
        assert row["team_final_n_sample_qualified_primary"] == True  # noqa: E712

    def test_below_primary_floor_active_rate_is_nan_but_team_rate_is_not(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        below = DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY - 1
        rows = [(2015, "P1", wk, "AAA", 10.0) for wk in last4[:below]] if below > 0 else []
        wp = _weekly_player(rows)
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert pd.isna(row["team_final_n_points_per_active_game"])
        # per-team-game rate stays real and defined even below the floor
        assert not pd.isna(row["team_final_n_points_per_team_game"])

    def test_between_primary_and_sensitivity_rate_shown_but_not_sensitivity_qualified(self):
        # PRIMARY(3) gates whether the rate is shown at all; SENSITIVITY(4)
        # is a stricter, separately-exposed comparison flag on top of an
        # already-shown rate -- never a second nulling gate. A player with
        # exactly PRIMARY active games (3) should show a real, non-null
        # rate while failing the stricter SENSITIVITY flag.
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        assert DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY < DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_SENSITIVITY
        wp = _weekly_player(
            [(2015, "P1", wk, "AAA", 10.0) for wk in last4[:DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY]]
        )
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert not pd.isna(row["team_final_n_points_per_active_game"])
        assert row["team_final_n_sample_qualified_primary"] == True  # noqa: E712
        assert row["team_final_n_sample_qualified_sensitivity"] == False  # noqa: E712


class TestActiveGameFinalN:
    def test_never_exceeds_n_active_games(self):
        pop = _population((2015, "P1", "WR"))
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in range(1, 18)])
        out = build_active_game_final_n_traits(pop, wp, n=4)
        assert out.iloc[0]["active_final_n_games"] == 4

    def test_player_with_fewer_real_games_than_n_gets_actual_count(self):
        pop = _population((2015, "P1", "WR"))
        wp = _weekly_player([(2015, "P1", 1, "AAA", 5.0), (2015, "P1", 2, "AAA", 7.0)])
        out = build_active_game_final_n_traits(pop, wp, n=4)
        assert out.iloc[0]["active_final_n_games"] == 2
        assert pd.isna(out.iloc[0]["active_final_n_games_ppg"])  # below sensitivity floor

    def test_takes_the_players_own_most_recent_real_rows_regardless_of_week_gaps(self):
        pop = _population((2015, "P1", "WR"))
        wp = _weekly_player(
            [
                (2015, "P1", 1, "AAA", 1.0),
                (2015, "P1", 2, "AAA", 1.0),
                (2015, "P1", 15, "AAA", 9.0),
                (2015, "P1", 16, "AAA", 9.0),
                (2015, "P1", 17, "AAA", 9.0),
            ]
        )
        out = build_active_game_final_n_traits(pop, wp, n=3)
        assert out.iloc[0]["active_final_n_games_ppg"] == 9.0

    def test_no_week_arithmetic_means_no_era_sensitivity(self):
        # Immune to the real week-boundary bug by construction -- same
        # correctness for a 16-game-era and 17-game-era season with no
        # special-casing needed.
        pop = _population((2015, "P1", "WR"), (2021, "P2", "WR"))
        wp = _weekly_player(
            [(2015, "P1", wk, "AAA", 5.0) for wk in AAA_2015_WEEKS]
            + [(2021, "P2", wk, "BBB", 5.0) for wk in BBB_2021_WEEKS]
        )
        out = build_active_game_final_n_traits(pop, wp, n=4)
        assert (out["active_final_n_games"] == 4).all()


class TestTeamGameHalfSplitRealBoundaries:
    def test_half_split_uses_team_game_index_not_calendar_week(self):
        # AAA/2015: 16 real games, bye at week 9. Team-game-index cutoff
        # = ceil(16/2) = 8.
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player([(2015, "P1", wk, "AAA", 1.0) for wk in AAA_2015_WEEKS])
        out = build_team_game_half_split_traits(pop, wp, wap)
        row = out.iloc[0]
        assert row["first_half_team_games"] == 8
        assert row["second_half_team_games"] == 8

    def test_17_game_era_half_split_boundary(self):
        # BBB/2021: 17 real games, bye at week 10. cutoff = ceil(17/2) = 9.
        pop = _population((2021, "P1", "WR"))
        wap = _weekly_all_positions([(2021, wk, "BBB", "REG") for wk in BBB_2021_WEEKS])
        wp = _weekly_player([(2021, "P1", wk, "BBB", 1.0) for wk in BBB_2021_WEEKS])
        out = build_team_game_half_split_traits(pop, wp, wap)
        row = out.iloc[0]
        assert row["first_half_team_games"] == 9
        assert row["second_half_team_games"] == 8

    def test_games_split_sums_to_real_season_total(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player([(2015, "P1", wk, "AAA", 1.0) for wk in AAA_2015_WEEKS])
        out = build_team_game_half_split_traits(pop, wp, wap)
        row = out.iloc[0]
        assert row["first_half_team_games"] + row["second_half_team_games"] == 16

    def test_inactive_half_game_zero_filled(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        first_half_weeks = AAA_2015_WEEKS[:8]
        wp = _weekly_player([(2015, "P1", wk, "AAA", 10.0) for wk in first_half_weeks[:4]])
        out = build_team_game_half_split_traits(pop, wp, wap)
        row = out.iloc[0]
        assert row["first_half_active_games"] == 4
        assert row["first_half_team_games"] == 8

    def test_traded_player_not_applicable(self):
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions(
            [(2023, wk, "KC", "REG") for wk in range(1, 10)] + [(2023, wk, "SF", "REG") for wk in range(10, 19)]
        )
        wp = _weekly_player(
            [(2023, "P1", wk, "KC", 5.0) for wk in range(1, 10)] + [(2023, "P1", wk, "SF", 5.0) for wk in range(10, 19)]
        )
        out = build_team_game_half_split_traits(pop, wp, wap)
        assert out.iloc[0]["team_game_window_status"] == TEAM_GAME_STATUS_UNAVAILABLE_TRADED


class TestOpportunityQualifiedAlwaysPending:
    def _pop_and_data(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in AAA_2015_WEEKS])
        return pop, wp, wap

    def test_team_game_final_n(self):
        pop, wp, wap = self._pop_and_data()
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        assert (out["opportunity_qualified"] == OPPORTUNITY_STATUS_PENDING).all()

    def test_active_game_final_n(self):
        pop, wp, _ = self._pop_and_data()
        out = build_active_game_final_n_traits(pop, wp, n=4)
        assert (out["opportunity_qualified"] == OPPORTUNITY_STATUS_PENDING).all()

    def test_team_game_half_split(self):
        pop, wp, wap = self._pop_and_data()
        out = build_team_game_half_split_traits(pop, wp, wap)
        assert (out["opportunity_qualified"] == OPPORTUNITY_STATUS_PENDING).all()


class TestUnavailableOtherStatus:
    def test_team_with_no_real_games_in_team_game_index_gets_other_status(self):
        # P1's single real team ("ZZZ") never appears in
        # weekly_all_positions at all -- a real inconsistency between
        # the two inputs, not a traded player and not "no team
        # evidence" (P1 clearly has real rows). Must be disclosed as
        # its own status, not silently left "applicable" with a null
        # result.
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions([(2023, wk, "KC", "REG") for wk in range(1, 19)])
        wp = _weekly_player([(2023, "P1", wk, "ZZZ", 5.0) for wk in range(1, 19)])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_game_window_status"] == "unavailable_other"
        assert pd.isna(row["team_final_n_games"])


class TestRequiredColumnValidation:
    def test_final_n_missing_team_column_raises(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        bad_weekly = pd.DataFrame([{"season": 2015, "player_id": "P1", "week": 1, "fantasy_points_ppr": 5.0}])
        with pytest.raises(ValueError, match="missing required columns"):
            build_team_game_final_n_traits(pop, bad_weekly, wap, n=4)

    def test_invalid_n_raises(self):
        pop = _population((2015, "P1", "WR"))
        wp = _weekly_player([(2015, "P1", 1, "AAA", 5.0)])
        with pytest.raises(ValueError, match="n must be a positive integer"):
            build_active_game_final_n_traits(pop, wp, n=0)


class TestRowCountPreserved:
    def test_population_row_count_preserved_team_game(self):
        pop = _population((2015, "P1", "WR"), (2015, "P2", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in AAA_2015_WEEKS])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        assert len(out) == 2  # P2 preserved even with zero real rows anywhere

    def test_population_row_count_preserved_active_game(self):
        pop = _population((2015, "P1", "WR"), (2015, "P2", "RB"))
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in AAA_2015_WEEKS])
        out = build_active_game_final_n_traits(pop, wp, n=4)
        assert len(out) == 2


class TestTeamGameEfficiencyTraits:
    def test_real_rate_computed_from_opportunity_and_production(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        # 3 targets/20 yards, 2 targets/10 yards -> 5 targets, 30 yards over the real window
        wp = _weekly_player_metric(
            [(2015, "P1", last4[0], "AAA", 3, 20.0), (2015, "P1", last4[2], "AAA", 2, 10.0)],
            ["targets", "receiving_yards"],
        )
        out = build_team_game_efficiency_traits(pop, wp, wap, n=4, position="WR", metric_name="receiving")
        row = out.iloc[0]
        assert row["team_final_n_opportunity"] == 5
        assert row["team_final_n_production"] == 30.0
        assert row["team_final_n_efficiency_rate"] == 6.0

    def test_zero_opportunity_applicable_row_rate_null_but_counts_zero_not_missing(self):
        # Minimal computability (§2c): denominator 0 -> rate null, but
        # the real zero opportunity/production stay visible, never
        # confused with an unavailable row.
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player_metric([(2015, "P1", AAA_2015_WEEKS[0], "AAA", 0, 0.0)], ["targets", "receiving_yards"])
        out = build_team_game_efficiency_traits(pop, wp, wap, n=4, position="WR", metric_name="receiving")
        row = out.iloc[0]
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE
        assert row["team_final_n_opportunity"] == 0.0
        assert row["team_final_n_production"] == 0.0
        assert pd.isna(row["team_final_n_efficiency_rate"])

    def test_eligibility_flags_from_config_thresholds(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        exploratory_min = DATASET2_EFFICIENCY_VOLUME_EXPLORATORY[("WR", "receiving")]
        # exactly at the exploratory minimum, real targets spread across the window
        per_week = exploratory_min // 4
        remainder = exploratory_min - per_week * 4
        targets_by_week = [per_week] * 4
        targets_by_week[0] += remainder
        wp = _weekly_player_metric(
            [(2015, "P1", wk, "AAA", t, float(t) * 5) for wk, t in zip(last4, targets_by_week)],
            ["targets", "receiving_yards"],
        )
        out = build_team_game_efficiency_traits(pop, wp, wap, n=4, position="WR", metric_name="receiving")
        row = out.iloc[0]
        assert row["team_final_n_opportunity"] == exploratory_min
        assert row["team_final_n_efficiency_volume_eligible_exploratory"] == True  # noqa: E712
        assert row["team_final_n_efficiency_volume_eligible_sensitivity"] == False  # noqa: E712
        # the rate itself is still real and shown, eligibility is a label, not a gate
        assert not pd.isna(row["team_final_n_efficiency_rate"])

    def test_below_exploratory_minimum_neither_flag_set_but_rate_still_shown(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        wp = _weekly_player_metric([(2015, "P1", last4[0], "AAA", 1, 8.0)], ["targets", "receiving_yards"])
        out = build_team_game_efficiency_traits(pop, wp, wap, n=4, position="WR", metric_name="receiving")
        row = out.iloc[0]
        assert row["team_final_n_efficiency_volume_eligible_exploratory"] == False  # noqa: E712
        assert row["team_final_n_efficiency_volume_eligible_sensitivity"] == False  # noqa: E712
        assert row["team_final_n_efficiency_rate"] == 8.0

    def test_unknown_position_metric_pair_raises(self):
        pop = _population((2015, "P1", "QB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player_metric([(2015, "P1", AAA_2015_WEEKS[0], "AAA", 1, 8.0)], ["targets", "receiving_yards"])
        with pytest.raises(ValueError, match="No efficiency metric defined"):
            build_team_game_efficiency_traits(pop, wp, wap, n=4, position="QB", metric_name="receiving")

    def test_only_requested_position_returned(self):
        pop = _population((2015, "P1", "WR"), (2015, "P2", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player_metric(
            [(2015, "P1", AAA_2015_WEEKS[0], "AAA", 3, 20.0), (2015, "P2", AAA_2015_WEEKS[0], "AAA", 2, 10.0)],
            ["targets", "receiving_yards"],
        )
        out = build_team_game_efficiency_traits(pop, wp, wap, n=4, position="WR", metric_name="receiving")
        assert list(out["player_id"]) == ["P1"]

    def test_rb_rushing_and_receiving_are_independent_metrics(self):
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        wp = pd.DataFrame(
            [
                {
                    "season": 2015, "player_id": "P1", "week": wk, "team": "AAA",
                    "carries": 10, "rushing_yards": 40.0, "targets": 2, "receiving_yards": 15.0,
                }
                for wk in last4
            ]
        )
        rushing = build_team_game_efficiency_traits(pop, wp, wap, n=4, position="RB", metric_name="rushing")
        receiving = build_team_game_efficiency_traits(pop, wp, wap, n=4, position="RB", metric_name="receiving")
        assert rushing.iloc[0]["team_final_n_efficiency_rate"] == 4.0  # 160 yards / 40 carries
        assert receiving.iloc[0]["team_final_n_efficiency_rate"] == 7.5  # 60 yards / 8 targets


class TestActiveGameEfficiencyTraits:
    def test_real_rate_and_eligibility(self):
        pop = _population((2015, "P1", "WR"))
        wp = _weekly_player_metric(
            [(2015, "P1", wk, "AAA", 3, 15.0) for wk in AAA_2015_WEEKS], ["targets", "receiving_yards"]
        )
        out = build_active_game_efficiency_traits(pop, wp, n=4, position="WR", metric_name="receiving")
        row = out.iloc[0]
        assert row["active_final_n_games"] == 4
        assert row["active_final_n_opportunity"] == 12
        assert row["active_final_n_production"] == 60.0
        assert row["active_final_n_efficiency_rate"] == 5.0
        assert row["active_final_n_efficiency_volume_eligible_exploratory"] == False  # noqa: E712

    def test_zero_opportunity_rate_null_counts_visible(self):
        pop = _population((2015, "P1", "WR"))
        wp = _weekly_player_metric([(2015, "P1", 1, "AAA", 0, 0.0)], ["targets", "receiving_yards"])
        out = build_active_game_efficiency_traits(pop, wp, n=4, position="WR", metric_name="receiving")
        row = out.iloc[0]
        assert row["active_final_n_opportunity"] == 0.0
        assert pd.isna(row["active_final_n_efficiency_rate"])

    def test_population_row_count_preserved(self):
        pop = _population((2015, "P1", "WR"), (2015, "P2", "WR"))
        wp = _weekly_player_metric(
            [(2015, "P1", wk, "AAA", 3, 15.0) for wk in AAA_2015_WEEKS], ["targets", "receiving_yards"]
        )
        out = build_active_game_efficiency_traits(pop, wp, n=4, position="WR", metric_name="receiving")
        assert len(out) == 2  # P2 preserved with zero real rows


class TestEfficiencyConfigConsistency:
    def test_every_efficiency_metric_has_both_volume_levels_and_primary_below_sensitivity(self):
        from lib.dataset2.partial_season_traits import EFFICIENCY_METRICS

        for key in EFFICIENCY_METRICS:
            assert key in DATASET2_EFFICIENCY_VOLUME_EXPLORATORY, key
            assert key in DATASET2_EFFICIENCY_VOLUME_SENSITIVITY, key
            assert DATASET2_EFFICIENCY_VOLUME_EXPLORATORY[key] < DATASET2_EFFICIENCY_VOLUME_SENSITIVITY[key], key
