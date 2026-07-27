"""
tests/test_dataset2_partial_season_traits.py

Covers lib/dataset2/partial_season_traits.py -- Dataset 2 family #9's
sample-size portion (approved 2026-07: primary floor >=4 games,
sensitivity floor >=3 games, exposed separately; opportunity
qualification explicitly pending). Protects:

- The two sample-size floors are exposed as SEPARATE columns, never
  collapsed into one flag.
- A window below the sensitivity floor (< 3 games) has its PPG value
  structurally nulled -- not just flagged, actually unusable by
  accident.
- opportunity_qualified is the literal "pending" string on every row,
  never True/False/silently-qualified.
- Season-length-aware half boundaries (16-game vs. 17-game era).
- final-N-games is genuinely parametrized (different n -> different
  real counts on the same fixture), not a hardcoded single window.
- Population rows with zero matching weekly data are preserved
  (games=0, ppg=NaN), never dropped.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from lib.dataset2 import partial_season_traits as pst


def _population_df(*rows):
    cols = ["season", "player_id", "position"]
    return pd.DataFrame(list(rows), columns=cols)


def _weekly_df(*rows):
    cols = ["season", "player_id", "week", "fantasy_points_ppr"]
    return pd.DataFrame(list(rows), columns=cols)


def _weeks(season, player_id, points_by_week):
    """Helper: one weekly row per (week, points) pair."""
    return [{"season": season, "player_id": player_id, "week": wk, "fantasy_points_ppr": pts} for wk, pts in points_by_week.items()]


class TestHalfSplitSeasonLengthAwareBoundaries:
    def test_16_game_era_halves_at_week_8(self):
        """2020 season (16 games): first half = weeks 1-8, second = 9-16."""
        pop = _population_df({"season": 2020, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2020, "00-1", {w: 10.0 for w in range(1, 17)}))
        out = pst.build_half_split_traits(pop, weekly)
        row = out.iloc[0]
        assert row["first_half_games"] == 8
        assert row["second_half_games"] == 8

    def test_17_game_era_halves_at_week_9(self):
        """2022 season (17 games): ceil(17/2)=9 -> first half = weeks 1-9, second = 10-17."""
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2022, "00-1", {w: 10.0 for w in range(1, 18)}))
        out = pst.build_half_split_traits(pop, weekly)
        row = out.iloc[0]
        assert row["first_half_games"] == 9
        assert row["second_half_games"] == 8


class TestFloorEnforcement:
    def test_four_games_qualifies_both_floors(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0, 2: 12.0, 3: 8.0, 4: 14.0}))
        out = pst.build_half_split_traits(pop, weekly)
        row = out.iloc[0]
        assert row["first_half_games"] == 4
        assert row["first_half_sample_qualified_primary"] == True  # noqa: E712
        assert row["first_half_sample_qualified_sensitivity"] == True  # noqa: E712
        assert row["first_half_ppg"] == pytest.approx((10 + 12 + 8 + 14) / 4)

    def test_three_games_qualifies_sensitivity_only_ppg_still_populated(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0, 2: 12.0, 3: 8.0}))
        out = pst.build_half_split_traits(pop, weekly)
        row = out.iloc[0]
        assert row["first_half_games"] == 3
        assert row["first_half_sample_qualified_primary"] == False  # noqa: E712
        assert row["first_half_sample_qualified_sensitivity"] == True  # noqa: E712
        assert row["first_half_ppg"] == pytest.approx((10 + 12 + 8) / 3)

    def test_two_games_fails_both_floors_and_ppg_is_structurally_nulled(self):
        """Below the sensitivity floor -- PPG must be NaN, not just flagged."""
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0, 2: 12.0}))
        out = pst.build_half_split_traits(pop, weekly)
        row = out.iloc[0]
        assert row["first_half_games"] == 2
        assert row["first_half_sample_qualified_primary"] == False  # noqa: E712
        assert row["first_half_sample_qualified_sensitivity"] == False  # noqa: E712
        assert pd.isna(row["first_half_ppg"])

    def test_zero_games_preserved_row_not_dropped(self):
        """Player in population but with no weekly rows in this half
        (e.g. injured all season) -- row stays, games=0, ppg null."""
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df()  # no weekly rows at all
        out = pst.build_half_split_traits(pop, weekly)
        assert len(out) == 1
        row = out.iloc[0]
        assert row["first_half_games"] == 0
        assert row["second_half_games"] == 0
        assert pd.isna(row["first_half_ppg"])
        assert pd.isna(row["second_half_ppg"])


class TestOpportunityQualifiedAlwaysPending:
    def test_half_split_output(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0, 2: 12.0, 3: 8.0, 4: 14.0}))
        out = pst.build_half_split_traits(pop, weekly)
        assert (out["opportunity_qualified"] == pst.OPPORTUNITY_STATUS_PENDING).all()

    def test_final_n_games_output(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0, 2: 12.0, 3: 8.0, 4: 14.0}))
        out = pst.build_final_n_games_traits(pop, weekly, n=4)
        assert (out["opportunity_qualified"] == pst.OPPORTUNITY_STATUS_PENDING).all()
        # never a boolean or any other type
        assert set(out["opportunity_qualified"].unique()) == {"pending"}


class TestFinalNGamesParametrization:
    def test_different_n_produce_different_real_counts(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2022, "00-1", {w: 10.0 + w for w in range(1, 18)}))  # full 17-game season
        out_n4 = pst.build_final_n_games_traits(pop, weekly, n=4)
        out_n6 = pst.build_final_n_games_traits(pop, weekly, n=6)
        assert out_n4.iloc[0]["final_n_games"] == 4
        assert out_n6.iloc[0]["final_n_games"] == 6
        assert out_n4.iloc[0]["window_n"] == 4
        assert out_n6.iloc[0]["window_n"] == 6

    def test_window_uses_trailing_weeks_not_leading(self):
        """Points differ by week (week 14-17 = 100s, weeks 1-13 = 1s) --
        a trailing-4 window must average the LATE points, not the
        early ones."""
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        points = {w: 1.0 for w in range(1, 14)}
        points.update({14: 100.0, 15: 100.0, 16: 100.0, 17: 100.0})
        weekly = _weekly_df(*_weeks(2022, "00-1", points))
        out = pst.build_final_n_games_traits(pop, weekly, n=4)
        assert out.iloc[0]["final_n_games_ppg"] == pytest.approx(100.0)

    def test_invalid_n_raises(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0}))
        with pytest.raises(ValueError, match="n must be a positive integer"):
            pst.build_final_n_games_traits(pop, weekly, n=0)


class TestRequiredColumnValidation:
    def test_half_split_missing_population_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2022]})
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0}))
        with pytest.raises(ValueError, match="population is missing required columns"):
            pst.build_half_split_traits(bad_pop, weekly)

    def test_half_split_missing_weekly_column_raises(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        bad_weekly = pd.DataFrame({"season": [2022]})
        with pytest.raises(ValueError, match="weekly is missing required columns"):
            pst.build_half_split_traits(pop, bad_weekly)

    def test_final_n_games_missing_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2022]})
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0}))
        with pytest.raises(ValueError, match="population is missing required columns"):
            pst.build_final_n_games_traits(bad_pop, weekly, n=4)


class TestConfigConsistency:
    def test_sensitivity_floor_never_exceeds_primary_floor(self):
        assert config.DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY <= config.DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY

    def test_floors_are_positive(self):
        assert config.DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY >= 1
        assert config.DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY >= 1


class TestRowCountPreserved:
    def test_one_row_per_season_player_half_split(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "WR"},
            {"season": 2022, "player_id": "00-2", "position": "RB"},
        )
        weekly = _weekly_df(*_weeks(2022, "00-1", {1: 10.0}))
        out = pst.build_half_split_traits(pop, weekly)
        assert len(out) == 2
