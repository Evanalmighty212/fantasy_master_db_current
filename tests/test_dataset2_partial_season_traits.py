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
    DATASET2_ROLE_THRESHOLDS_ACTIVE_GAME,
    DATASET2_ROLE_THRESHOLDS_SNAP_SHARE,
    DATASET2_ROLE_THRESHOLDS_TEAM_GAME,
)
from lib.dataset2.partial_season_traits import (
    EFFICIENCY_METRICS,
    OPPORTUNITY_STATUS_PENDING,
    TEAM_GAME_STATUS_APPLICABLE,
    TEAM_GAME_STATUS_UNAVAILABLE_TRADED,
    _role_tier_flags,
    _volume_eligible_flag,
    build_active_game_efficiency_traits,
    build_active_game_final_n_traits,
    build_active_game_role_traits,
    build_team_game_efficiency_traits,
    build_team_game_final_n_traits,
    build_team_game_half_split_traits,
    build_team_game_role_traits,
    build_team_game_snap_share_role_traits,
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


def _raw_snaps(rows):
    """rows: list of (season, week, team, player_id, offense_snaps) --
    matches build_team_game_snap_share_role_traits()'s expected
    already-matched, already-renamed Source B shape
    (SNAP_ROLE_REQUIRED_COLUMNS)."""
    return pd.DataFrame(
        [
            {"season": s, "week": w, "team": t, "player_id": p, "offense_snaps": snaps}
            for s, w, t, p, snaps in rows
        ]
    )


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


class TestTeamGameRoleTraits:
    """Protects build_team_game_role_traits() -- see module docstring's
    "MEANINGFUL-ROLE CLASSIFICATION" section and
    research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md
    §2e. team_final_n_games is always the fixed real window size, so
    with a constant per-week carry total the resulting
    opportunity_per_team_game rate equals that per-week value exactly
    -- used throughout to hit each config threshold precisely."""

    @pytest.mark.parametrize(
        "per_week_carries,expect_present,expect_meaningful,expect_strong",
        [
            (1.75, False, False, False),  # below role_present (2)
            (2.0, True, False, False),  # exactly at role_present
            (3.5, True, False, False),  # between role_present and meaningful
            (5.0, True, True, False),  # exactly at meaningful (5)
            (7.5, True, True, False),  # between meaningful and strong
            (10.0, True, True, True),  # exactly at strong_lead (10)
            (12.0, True, True, True),  # above strong_lead
        ],
    )
    def test_boundary_values_below_at_above_each_tier(
        self, per_week_carries, expect_present, expect_meaningful, expect_strong
    ):
        assert DATASET2_ROLE_THRESHOLDS_TEAM_GAME[("RB", "rushing")] == (2, 5, 10)
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        wp = pd.DataFrame(
            [
                {"season": 2015, "player_id": "P1", "week": wk, "team": "AAA", "carries": per_week_carries}
                for wk in last4
            ]
        )
        out = build_team_game_role_traits(pop, wp, wap, n=4, position="RB", metric_name="rushing")
        row = out.iloc[0]
        assert row["team_final_n_opportunity_per_team_game"] == pytest.approx(per_week_carries)
        assert row["team_final_n_role_present"] == expect_present
        assert row["team_final_n_meaningful_role"] == expect_meaningful
        assert row["team_final_n_strong_lead_role"] == expect_strong

    def test_zero_opportunity_applicable_row_flags_false_not_null(self):
        # A real, applicable window with zero real carries is a real
        # "no rushing role" finding -- rate 0.0 and all three flags
        # False, never null (null is reserved for non-applicable rows).
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = pd.DataFrame(
            [{"season": 2015, "player_id": "P1", "week": AAA_2015_WEEKS[0], "team": "AAA", "carries": 0}]
        )
        out = build_team_game_role_traits(pop, wp, wap, n=4, position="RB", metric_name="rushing")
        row = out.iloc[0]
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE
        assert row["team_final_n_opportunity_per_team_game"] == 0.0
        assert row["team_final_n_role_present"] == False  # noqa: E712
        assert row["team_final_n_meaningful_role"] == False  # noqa: E712
        assert row["team_final_n_strong_lead_role"] == False  # noqa: E712

    def test_unavailable_traded_status_all_role_fields_null(self):
        pop = _population((2023, "P1", "RB"))
        wap = _weekly_all_positions([(2023, wk, "KC", "REG") for wk in range(1, 10)] + [(2023, wk, "SF", "REG") for wk in range(10, 19)])
        wp = pd.DataFrame(
            [
                {"season": 2023, "player_id": "P1", "week": wk, "team": "KC", "carries": 5}
                for wk in range(1, 10)
            ]
            + [
                {"season": 2023, "player_id": "P1", "week": wk, "team": "SF", "carries": 5}
                for wk in range(10, 19)
            ]
        )
        out = build_team_game_role_traits(pop, wp, wap, n=4, position="RB", metric_name="rushing")
        row = out.iloc[0]
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_UNAVAILABLE_TRADED
        assert pd.isna(row["team_final_n_opportunity_per_team_game"])
        assert pd.isna(row["team_final_n_role_present"])
        assert pd.isna(row["team_final_n_meaningful_role"])
        assert pd.isna(row["team_final_n_strong_lead_role"])

    @pytest.mark.parametrize("n", [4, 6, 8])
    def test_final_4_6_8_windows_use_correct_fixed_denominator(self, n):
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        window_weeks = AAA_2015_WEEKS[-n:]
        wp = pd.DataFrame(
            [{"season": 2015, "player_id": "P1", "week": wk, "team": "AAA", "carries": 3.0} for wk in window_weeks]
        )
        out = build_team_game_role_traits(pop, wp, wap, n=n, position="RB", metric_name="rushing")
        row = out.iloc[0]
        assert row["team_final_n_games"] == n
        assert row["team_final_n_opportunity"] == 3.0 * n
        assert row["team_final_n_opportunity_per_team_game"] == 3.0  # constant per-game rate regardless of n

    def test_wr_and_te_targets_use_their_own_distinct_thresholds(self):
        assert DATASET2_ROLE_THRESHOLDS_TEAM_GAME[("WR", "receiving")] == (2, 4, 6)
        assert DATASET2_ROLE_THRESHOLDS_TEAM_GAME[("TE", "receiving")] == (1.5, 3, 5)
        wap_wr = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        # 3 targets/team-game clears WR role_present (2) but not TE's stronger meaningful (3) -- wait,
        # 3 targets/team-game is exactly at TE's meaningful threshold and below WR's meaningful (4).
        wr_pop = _population((2015, "P1", "WR"))
        wr_wp = pd.DataFrame(
            [{"season": 2015, "player_id": "P1", "week": wk, "team": "AAA", "targets": 3.0} for wk in last4]
        )
        wr_out = build_team_game_role_traits(wr_pop, wr_wp, wap_wr, n=4, position="WR", metric_name="receiving")
        te_pop = _population((2015, "P2", "TE"))
        te_wp = pd.DataFrame(
            [{"season": 2015, "player_id": "P2", "week": wk, "team": "AAA", "targets": 3.0} for wk in last4]
        )
        te_out = build_team_game_role_traits(te_pop, te_wp, wap_wr, n=4, position="TE", metric_name="receiving")
        assert wr_out.iloc[0]["team_final_n_meaningful_role"] == False  # noqa: E712 -- 3.0 < WR's 4
        assert te_out.iloc[0]["team_final_n_meaningful_role"] == True  # noqa: E712 -- 3.0 >= TE's 3

    def test_qb_has_no_team_game_entry_and_raises(self):
        pop = _population((2015, "P1", "QB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = pd.DataFrame(
            [{"season": 2015, "player_id": "P1", "week": AAA_2015_WEEKS[0], "team": "AAA", "attempts": 30}]
        )
        with pytest.raises(ValueError, match="No role-tier thresholds defined"):
            build_team_game_role_traits(pop, wp, wap, n=4, position="QB", metric_name="passing")


class TestActiveGameRoleTraits:
    """Protects build_active_game_role_traits() -- opportunity ONLY
    across the player's own real active games, per the module
    docstring's team-game-vs-active-game separation."""

    @pytest.mark.parametrize(
        "per_week_attempts,expect_present,expect_meaningful,expect_strong",
        [
            (19.0, False, False, False),  # below role_present (20)
            (20.0, True, False, False),  # exactly at role_present
            (25.0, True, True, False),  # exactly at meaningful (25)
            (30.0, True, True, True),  # exactly at strong_lead (30)
        ],
    )
    def test_boundary_values_below_at_above_each_tier(
        self, per_week_attempts, expect_present, expect_meaningful, expect_strong
    ):
        assert DATASET2_ROLE_THRESHOLDS_ACTIVE_GAME[("QB", "passing")] == (20, 25, 30)
        pop = _population((2015, "P1", "QB"))
        wp = pd.DataFrame(
            [
                {"season": 2015, "player_id": "P1", "week": wk, "team": "AAA", "attempts": per_week_attempts}
                for wk in AAA_2015_WEEKS[-4:]
            ]
        )
        out = build_active_game_role_traits(pop, wp, n=4, position="QB", metric_name="passing")
        row = out.iloc[0]
        assert row["active_final_n_opportunity_per_active_game"] == pytest.approx(per_week_attempts)
        assert row["active_final_n_role_present"] == expect_present
        assert row["active_final_n_meaningful_role"] == expect_meaningful
        assert row["active_final_n_strong_lead_role"] == expect_strong

    def test_zero_real_active_games_all_role_fields_null(self):
        # No real rows at all this season -- structurally nothing to
        # divide by, distinct from a real zero-opportunity active game.
        pop = _population((2015, "P1", "QB"))
        wp = pd.DataFrame(columns=["season", "player_id", "week", "team", "attempts"])
        out = build_active_game_role_traits(pop, wp, n=4, position="QB", metric_name="passing")
        row = out.iloc[0]
        assert row["active_final_n_games"] == 0
        assert pd.isna(row["active_final_n_opportunity_per_active_game"])
        assert pd.isna(row["active_final_n_role_present"])

    def test_real_active_games_zero_opportunity_flags_false_not_null(self):
        # On the field (a real row exists) but zero real attempts that
        # metric -- a real, meaningful "active but no role" finding.
        pop = _population((2015, "P1", "QB"))
        wp = pd.DataFrame(
            [{"season": 2015, "player_id": "P1", "week": wk, "team": "AAA", "attempts": 0} for wk in AAA_2015_WEEKS[-4:]]
        )
        out = build_active_game_role_traits(pop, wp, n=4, position="QB", metric_name="passing")
        row = out.iloc[0]
        assert row["active_final_n_games"] == 4
        assert row["active_final_n_opportunity_per_active_game"] == 0.0
        assert row["active_final_n_role_present"] == False  # noqa: E712

    @pytest.mark.parametrize("n", [4, 6, 8])
    def test_final_4_6_8_windows(self, n):
        pop = _population((2015, "P1", "RB"))
        wp = pd.DataFrame(
            [{"season": 2015, "player_id": "P1", "week": wk, "team": "AAA", "carries": 4.0} for wk in AAA_2015_WEEKS]
        )
        out = build_active_game_role_traits(pop, wp, n=n, position="RB", metric_name="rushing")
        row = out.iloc[0]
        assert row["active_final_n_games"] == n
        assert row["active_final_n_opportunity"] == 4.0 * n
        assert row["active_final_n_opportunity_per_active_game"] == 4.0


class TestSnapShareRoleTraits:
    """Protects build_team_game_snap_share_role_traits() -- team-game
    basis, position-specific thresholds, and the real max-based
    team-total denominator (mirroring snap_traits.py's
    build_season_snap_usage()) that stays independent of any single
    player's own week-to-week availability."""

    @pytest.mark.parametrize(
        "player_snaps_per_week,expect_present,expect_meaningful,expect_strong",
        [
            (15.0, False, False, False),  # 15/60 = 0.25, below WR role_present (0.30)
            (18.0, True, False, False),  # 18/60 = 0.30, exactly at role_present
            (33.0, True, True, False),  # 33/60 = 0.55, exactly at meaningful
            (42.0, True, True, True),  # 42/60 = 0.70, exactly at strong_lead
        ],
    )
    def test_boundary_values_below_at_above_each_tier(
        self, player_snaps_per_week, expect_present, expect_meaningful, expect_strong
    ):
        assert DATASET2_ROLE_THRESHOLDS_SNAP_SHARE["WR"] == (0.30, 0.55, 0.70)
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in last4])
        raw = _raw_snaps(
            [(2015, wk, "AAA", "OL1", 60.0) for wk in last4]
            + [(2015, wk, "AAA", "P1", player_snaps_per_week) for wk in last4]
        )
        out = build_team_game_snap_share_role_traits(pop, wp, wap, raw, n=4, position="WR")
        row = out.iloc[0]
        assert row["team_final_n_has_snap_coverage"] == True  # noqa: E712
        assert row["team_final_n_offense_snap_share"] == pytest.approx(player_snaps_per_week / 60.0)
        assert row["team_final_n_role_present"] == expect_present
        assert row["team_final_n_meaningful_role"] == expect_meaningful
        assert row["team_final_n_strong_lead_role"] == expect_strong

    def test_position_specific_thresholds_classify_the_same_share_differently(self):
        # A real 0.50 snap share is below WR's meaningful (0.55) but
        # above RB's meaningful (0.45) -- position-specific thresholds
        # must be independently wired, not one shared bar.
        assert DATASET2_ROLE_THRESHOLDS_SNAP_SHARE["RB"] == (0.20, 0.45, 0.60)
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        raw = _raw_snaps(
            [(2015, wk, "AAA", "OL1", 60.0) for wk in last4]
            + [(2015, wk, "AAA", "P1", 30.0) for wk in last4]  # 30/60 = 0.50
            + [(2015, wk, "AAA", "P2", 30.0) for wk in last4]
        )
        wr_pop = _population((2015, "P1", "WR"))
        wr_wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in last4])
        wr_out = build_team_game_snap_share_role_traits(wr_pop, wr_wp, wap, raw, n=4, position="WR")

        rb_pop = _population((2015, "P2", "RB"))
        rb_wp = _weekly_player([(2015, "P2", wk, "AAA", 5.0) for wk in last4])
        rb_out = build_team_game_snap_share_role_traits(rb_pop, rb_wp, wap, raw, n=4, position="RB")

        assert wr_out.iloc[0]["team_final_n_offense_snap_share"] == pytest.approx(0.50)
        assert rb_out.iloc[0]["team_final_n_offense_snap_share"] == pytest.approx(0.50)
        assert wr_out.iloc[0]["team_final_n_meaningful_role"] == False  # noqa: E712 -- 0.50 < WR's 0.55
        assert rb_out.iloc[0]["team_final_n_meaningful_role"] == True  # noqa: E712 -- 0.50 >= RB's 0.45

    def test_missing_source_b_coverage_flagged_false_share_null(self):
        # An applicable team-game window (real Source A team identity)
        # with ZERO real Source B rows for this team/season at all --
        # e.g. pre-2013 coverage gap. Must be distinguished from a real
        # zero share, not silently treated as one.
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in AAA_2015_WEEKS[-4:]])
        empty_raw = pd.DataFrame(
            {
                "season": pd.Series(dtype="int64"),
                "week": pd.Series(dtype="int64"),
                "team": pd.Series(dtype="object"),
                "player_id": pd.Series(dtype="object"),
                "offense_snaps": pd.Series(dtype="float64"),
            }
        )
        out = build_team_game_snap_share_role_traits(pop, wp, wap, empty_raw, n=4, position="WR")
        row = out.iloc[0]
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE
        assert row["team_final_n_has_snap_coverage"] == False  # noqa: E712
        assert pd.isna(row["team_final_n_offense_snap_share"])
        assert pd.isna(row["team_final_n_role_present"])

    def test_zero_snap_applicable_row_visible_not_confused_with_missing_coverage(self):
        # P1 is applicable and the TEAM has real Source B coverage
        # (OL1's rows), but P1 himself has zero real recorded snaps --
        # a real 0.0 share, has_snap_coverage True, flags False (not null).
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in last4])
        raw = _raw_snaps([(2015, wk, "AAA", "OL1", 60.0) for wk in last4])  # no P1 rows at all
        out = build_team_game_snap_share_role_traits(pop, wp, wap, raw, n=4, position="WR")
        row = out.iloc[0]
        assert row["team_final_n_has_snap_coverage"] == True  # noqa: E712
        assert row["team_final_n_offense_snap_share"] == 0.0
        assert row["team_final_n_role_present"] == False  # noqa: E712

    def test_unavailable_traded_status_all_snap_fields_null(self):
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions([(2023, wk, "KC", "REG") for wk in range(1, 10)] + [(2023, wk, "SF", "REG") for wk in range(10, 19)])
        wp = pd.DataFrame(
            [{"season": 2023, "player_id": "P1", "week": wk, "team": "KC", "fantasy_points_ppr": 5.0} for wk in range(1, 10)]
            + [{"season": 2023, "player_id": "P1", "week": wk, "team": "SF", "fantasy_points_ppr": 5.0} for wk in range(10, 19)]
        )
        raw = _raw_snaps(
            [(2023, wk, "KC", "P1", 30.0) for wk in range(1, 10)]
            + [(2023, wk, "SF", "P1", 30.0) for wk in range(10, 19)]
        )
        out = build_team_game_snap_share_role_traits(pop, wp, wap, raw, n=4, position="WR")
        row = out.iloc[0]
        assert row["team_game_window_status"] == TEAM_GAME_STATUS_UNAVAILABLE_TRADED
        assert pd.isna(row["team_final_n_offense_snap_share"])
        assert pd.isna(row["team_final_n_has_snap_coverage"])
        assert pd.isna(row["team_final_n_role_present"])

    def test_team_denominator_independent_of_player_own_availability(self):
        # P1 misses one of the window's 4 real team-games entirely
        # (no real Source B row that week) -- the team's real
        # offensive-play total for that week still counts in full
        # (via OL1), only P1's own numerator drops for that week.
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in last4])
        raw = _raw_snaps(
            [(2015, wk, "AAA", "OL1", 60.0) for wk in last4]
            + [(2015, wk, "AAA", "P1", 18.0) for wk in last4 if wk != last4[1]]  # missing 1 week
        )
        out = build_team_game_snap_share_role_traits(pop, wp, wap, raw, n=4, position="WR")
        row = out.iloc[0]
        assert row["team_final_n_team_offense_total"] == 240.0  # 60 * 4, unaffected by P1's absence
        assert row["team_final_n_offense_snaps"] == 54.0  # 18 * 3 real weeks, 0 the missing week
        assert row["team_final_n_offense_snap_share"] == pytest.approx(54.0 / 240.0)

    @pytest.mark.parametrize("n", [4, 6, 8])
    def test_final_4_6_8_windows(self, n):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        window_weeks = AAA_2015_WEEKS[-n:]
        wp = _weekly_player([(2015, "P1", wk, "AAA", 5.0) for wk in window_weeks])
        raw = _raw_snaps(
            [(2015, wk, "AAA", "OL1", 60.0) for wk in window_weeks]
            + [(2015, wk, "AAA", "P1", 30.0) for wk in window_weeks]
        )
        out = build_team_game_snap_share_role_traits(pop, wp, wap, raw, n=n, position="WR")
        row = out.iloc[0]
        assert row["team_final_n_games"] == n
        assert row["team_final_n_team_offense_total"] == 60.0 * n
        assert row["team_final_n_offense_snap_share"] == pytest.approx(0.50)


class TestRoleConfigConsistency:
    """Protects config.py's DATASET2_ROLE_THRESHOLDS_* dicts -- each
    tuple must be strictly increasing (role_present < meaningful_role <
    strong_lead_role) for _role_tier_flags()'s tier logic to be
    coherent, and every (position, metric_name) key must resolve to a
    real opportunity column via EFFICIENCY_METRICS."""

    def test_team_game_thresholds_strictly_increasing_and_resolvable(self):
        for key, (present, meaningful, strong) in DATASET2_ROLE_THRESHOLDS_TEAM_GAME.items():
            assert present < meaningful < strong, key
            assert key in EFFICIENCY_METRICS, key

    def test_active_game_thresholds_strictly_increasing_and_resolvable(self):
        for key, (present, meaningful, strong) in DATASET2_ROLE_THRESHOLDS_ACTIVE_GAME.items():
            assert present < meaningful < strong, key
            assert key in EFFICIENCY_METRICS, key

    def test_snap_share_thresholds_strictly_increasing(self):
        for position, (present, meaningful, strong) in DATASET2_ROLE_THRESHOLDS_SNAP_SHARE.items():
            assert present < meaningful < strong, position

    def test_snap_share_covers_every_offense_position(self):
        assert set(DATASET2_ROLE_THRESHOLDS_SNAP_SHARE.keys()) == {"QB", "RB", "WR", "TE"}


class TestNullableFlagPropagation:
    """Direct unit-level proof (added 2026-07 during the Source A
    targets/receiving_air_yards coverage remediation) that neither
    `_role_tier_flags()` nor `_volume_eligible_flag()` ever turns a
    real null input into a real `False` -- both must produce `pd.NA`.
    Previously only exercised indirectly through the higher-level
    builder functions; this class isolates the exact concern."""

    def test_role_tier_flags_null_rate_produces_na_not_false(self):
        rate = pd.Series([None, 0.1, 0.6, 0.9])
        present, meaningful, strong = _role_tier_flags(rate, (0.2, 0.5, 0.8))
        assert pd.isna(present.iloc[0])
        assert pd.isna(meaningful.iloc[0])
        assert pd.isna(strong.iloc[0])
        # real, known rates still resolve correctly, not swallowed by the null-safety
        assert present.iloc[1] == False and meaningful.iloc[1] == False and strong.iloc[1] == False  # noqa: E712
        assert present.iloc[2] == True and meaningful.iloc[2] == True and strong.iloc[2] == False  # noqa: E712
        assert present.iloc[3] == True and meaningful.iloc[3] == True and strong.iloc[3] == True  # noqa: E712

    def test_role_tier_flags_output_dtype_is_nullable_boolean(self):
        rate = pd.Series([None, 0.5])
        present, meaningful, strong = _role_tier_flags(rate, (0.2, 0.4, 0.6))
        for flag in (present, meaningful, strong):
            assert flag.dtype == "boolean"

    def test_volume_eligible_flag_null_opportunity_produces_na_not_false(self):
        opportunity = pd.Series([None, 5.0, 20.0])
        flag = _volume_eligible_flag(opportunity, min_value=10.0)
        assert pd.isna(flag.iloc[0])
        assert flag.iloc[1] == False  # noqa: E712 -- real, known, below threshold
        assert flag.iloc[2] == True  # noqa: E712 -- real, known, at/above threshold

    def test_volume_eligible_flag_output_dtype_is_nullable_boolean(self):
        opportunity = pd.Series([None, 15.0])
        flag = _volume_eligible_flag(opportunity, min_value=10.0)
        assert flag.dtype == "boolean"
