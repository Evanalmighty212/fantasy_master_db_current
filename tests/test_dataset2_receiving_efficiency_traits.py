"""
tests/test_dataset2_receiving_efficiency_traits.py

Covers lib/dataset2/receiving_efficiency_traits.py -- Dataset 2 family
#18 (receiving efficiency), CORE portion only, approved 2026-07.
Protects:

1. Each ratio is a season-TOTAL-over-season-TOTAL computation (never
   an average of weekly ratios) -- this module itself only performs
   the ratio on already-aggregated inputs, so this suite proves the
   ratio math is correct given real season totals, and
   tests/test_dataset2_usage_traits.py's own aggregation tests (season
   summing, REG-only, traded-player-correct) prove those totals
   themselves are correct -- see TestUpstreamAggregationWouldBeWrongIfAveraged
   below for the one worked case showing why this separation matters.
2. Zero/null denominators produce NULL, never a guessed 0.0.
3. A real negative or zero YAC total with positive receptions produces
   the real calculated value, never suppressed.
4. Missing prior-season history (rookie) propagates null through every
   ratio.
5. No "efficient receiver" threshold/classification of any kind is
   built -- these are continuous ratios only.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import receiving_efficiency_traits as ret
from lib.dataset2 import usage_traits as ut


def _preseason_usage_df(*rows):
    cols = [
        "season", "player_id", "position", "prior_season_targets", "prior_season_receptions",
        "prior_season_receiving_yards", "prior_season_receiving_yards_after_catch",
    ]
    return pd.DataFrame(list(rows), columns=cols)


class TestRatioFormulas:
    def test_catch_rate_is_receptions_over_targets(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 100,
             "prior_season_receptions": 65, "prior_season_receiving_yards": 900,
             "prior_season_receiving_yards_after_catch": 350},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert out.loc[0, "prior_season_catch_rate"] == pytest.approx(0.65)

    def test_yards_per_target_is_receiving_yards_over_targets(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 100,
             "prior_season_receptions": 65, "prior_season_receiving_yards": 900,
             "prior_season_receiving_yards_after_catch": 350},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert out.loc[0, "prior_season_receiving_yards_per_target"] == pytest.approx(9.0)

    def test_yac_per_reception_is_yac_over_receptions(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 100,
             "prior_season_receptions": 65, "prior_season_receiving_yards": 900,
             "prior_season_receiving_yards_after_catch": 350},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert out.loc[0, "prior_season_yac_per_reception"] == pytest.approx(350 / 65)


class TestZeroAndNullDenominators:
    def test_zero_targets_makes_catch_rate_and_ypt_null_not_zero(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 0,
             "prior_season_receptions": 0, "prior_season_receiving_yards": 0,
             "prior_season_receiving_yards_after_catch": 0},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert pd.isna(out.loc[0, "prior_season_catch_rate"])
        assert pd.isna(out.loc[0, "prior_season_receiving_yards_per_target"])

    def test_zero_receptions_makes_yac_per_reception_null_not_zero(self):
        # Positive targets, zero receptions -- a real, possible season
        # (targeted but never caught a pass).
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 10,
             "prior_season_receptions": 0, "prior_season_receiving_yards": 0,
             "prior_season_receiving_yards_after_catch": 0},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert pd.isna(out.loc[0, "prior_season_yac_per_reception"])
        # catch_rate is a real, calculated zero here (0 real receptions
        # / 10 real targets = a real 0.0, NOT null -- targets is
        # positive, so this is a real, known outcome, unlike the
        # zero-targets case above).
        assert out.loc[0, "prior_season_catch_rate"] == pytest.approx(0.0)

    def test_positive_receptions_with_negative_yac_produces_real_negative_value(self):
        # Real, disclosed possible outcome (see usage_traits.py's own
        # YAC audit) -- must NOT be floored to zero or nulled out.
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 5,
             "prior_season_receptions": 4, "prior_season_receiving_yards": 20,
             "prior_season_receiving_yards_after_catch": -8},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert out.loc[0, "prior_season_yac_per_reception"] == pytest.approx(-2.0)

    def test_positive_receptions_with_zero_yac_produces_real_zero(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 5,
             "prior_season_receptions": 4, "prior_season_receiving_yards": 20,
             "prior_season_receiving_yards_after_catch": 0},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert out.loc[0, "prior_season_yac_per_reception"] == pytest.approx(0.0)


class TestMissingPriorHistory:
    def test_no_prior_season_row_propagates_null_through_every_ratio(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-rookie", "position": "WR", "prior_season_targets": np.nan,
             "prior_season_receptions": np.nan, "prior_season_receiving_yards": np.nan,
             "prior_season_receiving_yards_after_catch": np.nan},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert pd.isna(out.loc[0, "prior_season_catch_rate"])
        assert pd.isna(out.loc[0, "prior_season_receiving_yards_per_target"])
        assert pd.isna(out.loc[0, "prior_season_yac_per_reception"])


class TestUpstreamAggregationWouldBeWrongIfAveraged:
    """The load-bearing case: a naive average of WEEKLY catch rates
    gives a different, wrong number vs. the real season-total ratio
    this module (fed by usage_traits.py's own real season-sum
    aggregation) actually computes. Proven end-to-end through the real
    upstream aggregation, not just asserted in isolation."""

    def test_season_total_ratio_differs_from_naive_weekly_average(self):
        # Week 1: 1 target, 1 reception -> weekly catch rate 100%.
        # Week 2: 19 targets, 9 receptions -> weekly catch rate 47.4%.
        # Naive average of the two weekly rates: (1.0 + 0.474) / 2 = 73.7%.
        # Real season-total rate: (1+9) / (1+19) = 10/20 = 50%.
        weekly = pd.DataFrame([
            {"season": 2023, "player_id": "00-1", "week": 1, "team": "ATL", "season_type": "REG",
             "targets": 1, "carries": 0, "receiving_yards": 10, "receiving_air_yards": 5,
             "passing_air_yards": 30, "passing_epa": 0.0, "rushing_epa": 0.0, "receiving_epa": 0.4,
             "receptions": 1, "receiving_yards_after_catch": 3},
            {"season": 2023, "player_id": "00-1", "week": 2, "team": "ATL", "season_type": "REG",
             "targets": 19, "carries": 0, "receiving_yards": 90, "receiving_air_yards": 60,
             "passing_air_yards": 200, "passing_epa": 0.0, "rushing_epa": 0.0, "receiving_epa": 2.1,
             "receptions": 9, "receiving_yards_after_catch": 30},
        ])
        pop = pd.DataFrame([{"season": 2023, "player_id": "00-1", "position": "WR"},
                             {"season": 2024, "player_id": "00-1", "position": "WR"}])
        raw = ut.build_raw_season_usage(pop, weekly)
        preseason = ut.build_preseason_usage_features(raw)
        out = ret.build_receiving_efficiency_traits(preseason)
        row_2024 = out[out["season"] == 2024].iloc[0]

        naive_weekly_average = (1.0 + 9 / 19) / 2
        real_season_total_rate = 10 / 20

        assert row_2024["prior_season_catch_rate"] == pytest.approx(real_season_total_rate)
        assert row_2024["prior_season_catch_rate"] != pytest.approx(naive_weekly_average)


class TestTargetsUnreliableCoverageFloor:
    """Real, audited finding (2026-07): `targets` in the raw nflverse
    weekly file is essentially untracked for real observation seasons
    2006-2008 (99.5-99.6% of real reception rows show targets==0 in
    each of those seasons vs. 0.0% every season 2009+) -- see module
    docstring and config.DATASET2_TARGETS_UNRELIABLE_OBSERVATION_SEASONS.
    catch_rate/yards_per_target are forced null for the affected
    prediction seasons (2007-2009) even when the real underlying counts
    would otherwise produce a computable value; yac_per_reception is
    untouched (clean, different denominator)."""

    def test_catch_rate_and_ypt_nulled_for_affected_prediction_seasons(self):
        df = _preseason_usage_df(
            {"season": 2007, "player_id": "00-1", "position": "WR", "prior_season_targets": 1,
             "prior_season_receptions": 45, "prior_season_receiving_yards": 400,
             "prior_season_receiving_yards_after_catch": 100},
            {"season": 2008, "player_id": "00-1", "position": "WR", "prior_season_targets": 1,
             "prior_season_receptions": 50, "prior_season_receiving_yards": 450,
             "prior_season_receiving_yards_after_catch": 120},
            {"season": 2009, "player_id": "00-1", "position": "WR", "prior_season_targets": 1,
             "prior_season_receptions": 55, "prior_season_receiving_yards": 500,
             "prior_season_receiving_yards_after_catch": 140},
        )
        out = ret.build_receiving_efficiency_traits(df).set_index("season")
        for season in (2007, 2008, 2009):
            assert pd.isna(out.loc[season, "prior_season_catch_rate"])
            assert pd.isna(out.loc[season, "prior_season_receiving_yards_per_target"])

    def test_yac_per_reception_unaffected_by_the_floor(self):
        df = _preseason_usage_df(
            {"season": 2008, "player_id": "00-1", "position": "WR", "prior_season_targets": 1,
             "prior_season_receptions": 50, "prior_season_receiving_yards": 450,
             "prior_season_receiving_yards_after_catch": 120},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert out.loc[0, "prior_season_yac_per_reception"] == pytest.approx(120 / 50)

    def test_seasons_outside_the_floor_are_computed_normally(self):
        df = _preseason_usage_df(
            {"season": 2006, "player_id": "00-1", "position": "WR", "prior_season_targets": 100,
             "prior_season_receptions": 60, "prior_season_receiving_yards": 800,
             "prior_season_receiving_yards_after_catch": 300},
            {"season": 2010, "player_id": "00-1", "position": "WR", "prior_season_targets": 100,
             "prior_season_receptions": 65, "prior_season_receiving_yards": 850,
             "prior_season_receiving_yards_after_catch": 320},
        )
        out = ret.build_receiving_efficiency_traits(df).set_index("season")
        # 2006 (prediction_season) is lagged FROM 2005, which is
        # outside the audited 2006-2008 unreliable range -- real,
        # computed value expected.
        assert out.loc[2006, "prior_season_catch_rate"] == pytest.approx(0.6)
        assert out.loc[2010, "prior_season_catch_rate"] == pytest.approx(0.65)


class TestRequiredColumnValidation:
    def test_missing_column_raises(self):
        bad_df = pd.DataFrame({"season": [2023]})
        with pytest.raises(ValueError, match="preseason_usage_df is missing required columns"):
            ret.build_receiving_efficiency_traits(bad_df)


class TestRowCountPreserved:
    def test_one_row_per_input_row(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 50,
             "prior_season_receptions": 30, "prior_season_receiving_yards": 400,
             "prior_season_receiving_yards_after_catch": 150},
            {"season": 2023, "player_id": "00-2", "position": "TE", "prior_season_targets": 20,
             "prior_season_receptions": 15, "prior_season_receiving_yards": 150,
             "prior_season_receiving_yards_after_catch": 60},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert len(out) == 2

    def test_no_classification_or_threshold_column_output(self):
        """Explicitly NOT approved this round -- guards against a
        future accidental addition."""
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "WR", "prior_season_targets": 50,
             "prior_season_receptions": 30, "prior_season_receiving_yards": 400,
             "prior_season_receiving_yards_after_catch": 150},
        )
        out = ret.build_receiving_efficiency_traits(df)
        assert set(out.columns) == set(ret.RECEIVING_EFFICIENCY_OUTPUT_COLUMNS)
        assert not any("efficient" in c or "qualified" in c or "flag" in c for c in out.columns)
