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
from config import DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY, DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY
from lib.dataset2.partial_season_traits import (
    OPPORTUNITY_STATUS_PENDING,
    build_active_game_final_n_traits,
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
        assert row["team_game_window_applicable"] == True  # noqa: E712

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
        assert out.iloc[0]["team_final_n_games_ppg"] == 5.0


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
        assert pd.isna(row["team_final_n_games_ppg"])  # 2 < sensitivity floor (3)


class TestTeamGameWindowTradedPlayerExclusion:
    def test_traded_player_gets_not_applicable(self):
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions(
            [(2023, wk, "KC", "REG") for wk in range(1, 10)] + [(2023, wk, "SF", "REG") for wk in range(10, 19)]
        )
        wp = _weekly_player(
            [(2023, "P1", wk, "KC", 5.0) for wk in range(1, 10)] + [(2023, "P1", wk, "SF", 5.0) for wk in range(10, 19)]
        )
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_game_window_applicable"] == False  # noqa: E712
        assert pd.isna(row["team_final_n_games"])
        assert pd.isna(row["team_final_n_games_ppg"])

    def test_single_team_player_gets_applicable(self):
        pop = _population((2023, "P1", "WR"))
        wap = _weekly_all_positions([(2023, wk, "KC", "REG") for wk in range(1, 19)])
        wp = _weekly_player([(2023, "P1", wk, "KC", 5.0) for wk in range(1, 19)])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        assert out.iloc[0]["team_game_window_applicable"] == True  # noqa: E712


class TestTeamGameFinalNFloorEnforcement:
    def test_primary_floor_from_config(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        active_n = DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY
        wp = _weekly_player([(2015, "P1", wk, "AAA", 10.0) for wk in last4[:active_n]])
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        row = out.iloc[0]
        assert row["team_final_n_active_games"] == active_n
        assert row["team_final_n_sample_qualified_primary"] == True  # noqa: E712

    def test_below_sensitivity_floor_ppg_is_nan(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        below = DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY - 1
        rows = [(2015, "P1", wk, "AAA", 10.0) for wk in last4[:below]] if below > 0 else []
        wp = _weekly_player(rows)
        out = build_team_game_final_n_traits(pop, wp, wap, n=4)
        assert pd.isna(out.iloc[0]["team_final_n_games_ppg"])


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
        assert out.iloc[0]["team_game_window_applicable"] == False  # noqa: E712


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
