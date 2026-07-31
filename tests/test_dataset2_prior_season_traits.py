"""
tests/test_dataset2_prior_season_traits.py

Covers lib/dataset2/prior_season_traits.py -- Dataset 2 families #8
(multi-year trend), #39 (prior-season availability), and #44 (changed
teams). Protects the specific approved decisions:

- Trend slopes use ONLY the intended lag window (2yr = seasons N-1/N-2
  only, 3yr = N-1/N-2/N-3) and require at least 2 real points -- a
  rookie or sophomore with insufficient history gets NaN, never a
  slope fabricated from one point or a zero-filled gap.
- changed_team is NULL for a player's first season (no prior team to
  compare against), never False -- an unknown must not be reported as
  a known non-event (docs/LEAGUE_WINNER_TRAITS_SPEC.md's rookie-path
  policy).
- Lag lookups are correct regardless of row order (guards the
  positional-alignment bug caught and fixed during this module's own
  development, before any test existed to pin it).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import prior_season_traits as pst


def _population_df(*rows):
    cols = ["season", "player_id", "position", "team", "ppg_ppr", "games_played"]
    return pd.DataFrame(list(rows), columns=cols)


class TestMultiYearTrend:
    def test_2yr_slope_from_two_real_points(self):
        pop = _population_df(
            {"season": 2020, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 10.0, "games_played": 16},
            {"season": 2021, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 14.0, "games_played": 16},
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 18.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        row_2022 = out[out["season"] == 2022].iloc[0]
        # points: (-1, 14.0), (-2, 10.0) -> slope = (14-10)/(-1 - -2) = 4.0/yr
        assert row_2022["ppg_trend_2yr_slope"] == pytest.approx(4.0)

    def test_3yr_slope_is_real_ols_over_three_points(self):
        pop = _population_df(
            {"season": 2019, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 8.0, "games_played": 16},
            {"season": 2020, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 10.0, "games_played": 16},
            {"season": 2021, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 14.0, "games_played": 16},
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 18.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        row_2022 = out[out["season"] == 2022].iloc[0]
        xs = np.array([-1, -2, -3])
        ys = np.array([14.0, 10.0, 8.0])
        expected_slope, _ = np.polyfit(xs, ys, 1)
        assert row_2022["ppg_trend_3yr_slope"] == pytest.approx(expected_slope)

    def test_rookie_has_null_trend_not_a_fabricated_slope(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 18.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        assert pd.isna(out.loc[0, "ppg_trend_2yr_slope"])
        assert pd.isna(out.loc[0, "ppg_trend_3yr_slope"])

    def test_sophomore_with_only_one_prior_point_has_null_2yr_and_3yr_trend(self):
        """A single prior-season point cannot support a slope -- both
        windows require at least 2 real points."""
        pop = _population_df(
            {"season": 2021, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 14.0, "games_played": 16},
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 18.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        row_2022 = out[out["season"] == 2022].iloc[0]
        assert pd.isna(row_2022["ppg_trend_2yr_slope"])
        assert pd.isna(row_2022["ppg_trend_3yr_slope"])


class TestPriorSeasonGamesPlayed:
    def test_lags_correctly(self):
        pop = _population_df(
            {"season": 2021, "player_id": "00-1", "position": "RB", "team": "TEN", "ppg_ppr": 12.0, "games_played": 13},
            {"season": 2022, "player_id": "00-1", "position": "RB", "team": "TEN", "ppg_ppr": 15.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        row_2022 = out[out["season"] == 2022].iloc[0]
        assert row_2022["prior_season_games_played"] == 13

    def test_rookie_is_null_not_zero(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "RB", "team": "TEN", "ppg_ppr": 15.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        assert pd.isna(out.loc[0, "prior_season_games_played"])

    def test_traded_player_18_game_fact_is_not_capped(self):
        """Rashid Shaheed's verified 2025 extra-game case must remain
        18 when carried into Dataset 2's raw prior-season games trait;
        one team's 17-game schedule is not a player-season ceiling."""
        pop = _population_df(
            {"season": 2025, "player_id": "00-SHAHEED", "position": "WR", "team": "SEA", "ppg_ppr": 10.0, "games_played": 18},
            {"season": 2026, "player_id": "00-SHAHEED", "position": "WR", "team": "SEA", "ppg_ppr": 10.0, "games_played": 17},
        )
        out = pst.build_prior_season_traits(pop)
        row_2026 = out[out["season"] == 2026].iloc[0]
        assert row_2026["prior_season_games_played"] == 18


class TestChangedTeam:
    def test_same_team_is_zero(self):
        pop = _population_df(
            {"season": 2021, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 12.0, "games_played": 16},
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 15.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        row_2022 = out[out["season"] == 2022].iloc[0]
        assert row_2022["changed_team"] == 0.0

    def test_different_team_is_one(self):
        pop = _population_df(
            {"season": 2021, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 12.0, "games_played": 16},
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "CLE", "ppg_ppr": 15.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        row_2022 = out[out["season"] == 2022].iloc[0]
        assert row_2022["changed_team"] == 1.0

    def test_rookie_is_null_not_false(self):
        """Undefined (no prior team to compare against) must not be
        reported as a known non-event."""
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 15.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        assert pd.isna(out.loc[0, "changed_team"])


class TestLagAlignmentIsKeyBasedNotPositional:
    """Regression guard: lag values must be correct regardless of row
    order in the input population (an earlier draft of this module
    relied on two separately-deduplicated frames sharing row order,
    which is not guaranteed)."""

    def test_shuffled_row_order_still_produces_correct_lags(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-2", "position": "RB", "team": "CLE", "ppg_ppr": 9.0, "games_played": 15},
            {"season": 2021, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 12.0, "games_played": 16},
            {"season": 2021, "player_id": "00-2", "position": "RB", "team": "CLE", "ppg_ppr": 7.0, "games_played": 14},
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "CLE", "ppg_ppr": 15.0, "games_played": 16},
        )
        out = pst.build_prior_season_traits(pop)
        p1_2022 = out[(out["player_id"] == "00-1") & (out["season"] == 2022)].iloc[0]
        p2_2022 = out[(out["player_id"] == "00-2") & (out["season"] == 2022)].iloc[0]
        assert p1_2022["prior_season_games_played"] == 16
        assert p1_2022["changed_team"] == 1.0  # TEN -> CLE
        assert p2_2022["prior_season_games_played"] == 14
        assert p2_2022["changed_team"] == 0.0  # CLE -> CLE


class TestRequiredColumnValidation:
    def test_missing_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2022], "player_id": ["00-1"]})
        with pytest.raises(ValueError, match="population is missing required columns"):
            pst.build_prior_season_traits(bad_pop)


class TestRowCountPreserved:
    def test_one_row_per_season_player(self):
        pop = _population_df(
            {"season": 2021, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 12.0, "games_played": 16},
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN", "ppg_ppr": 15.0, "games_played": 16},
            {"season": 2022, "player_id": "00-2", "position": "RB", "team": "CLE", "ppg_ppr": 9.0, "games_played": 15},
        )
        out = pst.build_prior_season_traits(pop)
        assert len(out) == 3
