"""
tests/test_dataset2_usage_traits.py

Covers lib/dataset2/usage_traits.py -- Source A of the Dataset 2
opportunity/usage foundation (approved 2026-07,
research/dataset2/OPPORTUNITY_FOUNDATION_PROPOSAL_2026_07.md). Protects
the three-way separation the approval requires:

1. build_raw_season_usage() -- this season's own real totals/rates,
   plain column names.
2. build_preseason_usage_features() -- the same fields strictly lagged
   to the PRIOR season, `prior_season_*` prefixed.
3. Same-season outcome data is never re-labeled -- it's just #1's own
   output for the season being predicted, which #2 must never read.

TestNoSameSeasonLeakage is the load-bearing test class here: it proves
a season's prior_season_* features are mathematically independent of
that SAME season's own raw row, not just that they happen to look
right on one example -- mutating the current season's raw value and
recomputing must never change the prior_season_* output.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import usage_traits as ut


def _population_df(*rows):
    cols = ["season", "player_id", "position"]
    return pd.DataFrame(list(rows), columns=cols)


def _weekly_row(season, pid, week, targets=0, carries=0, target_share=None, air_yards_share=None,
                 wopr=None, racr=None, passing_epa=None, rushing_epa=None, receiving_epa=None):
    return {
        "season": season, "player_id": pid, "week": week,
        "targets": targets, "carries": carries, "target_share": target_share,
        "air_yards_share": air_yards_share, "wopr": wopr, "racr": racr,
        "passing_epa": passing_epa, "rushing_epa": rushing_epa, "receiving_epa": receiving_epa,
    }


def _weekly_df(*rows):
    if not rows:
        return pd.DataFrame(columns=list(ut.WEEKLY_REQUIRED_COLUMNS))
    return pd.DataFrame(list(rows))


class TestRawSeasonUsageSumFields:
    def test_targets_and_carries_summed_across_weeks(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2022, "00-1", 1, targets=5, carries=0),
            _weekly_row(2022, "00-1", 2, targets=8, carries=1),
            _weekly_row(2022, "00-1", 3, targets=6, carries=0),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "targets"] == 19
        assert out.loc[0, "carries"] == 1

    def test_epa_summed_not_averaged(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2022, "00-1", 1, targets=5, receiving_epa=2.0),
            _weekly_row(2022, "00-1", 2, targets=5, receiving_epa=-1.5),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "receiving_epa"] == pytest.approx(0.5)

    def test_zero_weekly_rows_gives_zero_not_null(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df()
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "targets"] == 0
        assert out.loc[0, "carries"] == 0


class TestRawSeasonUsageMeanFields:
    def test_target_share_averaged_over_real_weeks(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2022, "00-1", 1, targets=5, target_share=0.20),
            _weekly_row(2022, "00-1", 2, targets=8, target_share=0.30),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "target_share"] == pytest.approx(0.25)

    def test_mean_field_null_when_no_real_weekly_data(self):
        """An average over zero real weeks is undefined -- must be NaN,
        never 0 (0 would falsely imply 'this player had a real 0% share')."""
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df()
        out = ut.build_raw_season_usage(pop, weekly)
        assert pd.isna(out.loc[0, "target_share"])
        assert pd.isna(out.loc[0, "wopr"])
        assert pd.isna(out.loc[0, "racr"])

    def test_racr_excludes_null_weeks_from_the_average(self):
        """racr is null on a real 0-air-yards target week -- that week
        must not corrupt the season average as if it were a real 0."""
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2022, "00-1", 1, targets=5, racr=2.0),
            _weekly_row(2022, "00-1", 2, targets=1, racr=None),  # a real 0-air-yards target
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "racr"] == pytest.approx(2.0)


class TestRawSeasonUsageRequiredColumns:
    def test_population_missing_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2022]})
        weekly = _weekly_df(_weekly_row(2022, "00-1", 1))
        with pytest.raises(ValueError, match="population is missing required columns"):
            ut.build_raw_season_usage(bad_pop, weekly)

    def test_weekly_missing_column_raises(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR"})
        bad_weekly = pd.DataFrame({"season": [2022]})
        with pytest.raises(ValueError, match="weekly is missing required columns"):
            ut.build_raw_season_usage(pop, bad_weekly)


class TestRawSeasonUsageRowCountPreserved:
    def test_one_row_per_season_player(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "WR"},
            {"season": 2022, "player_id": "00-2", "position": "RB"},
        )
        weekly = _weekly_df(_weekly_row(2022, "00-1", 1, targets=5))
        out = ut.build_raw_season_usage(pop, weekly)
        assert len(out) == 2


def _raw_usage_df(*rows):
    cols = list(ut.RAW_OUTPUT_COLUMNS)
    return pd.DataFrame(list(rows), columns=cols)


def _raw_row(season, pid, position, targets=0.0, carries=0.0, target_share=np.nan, air_yards_share=np.nan,
             wopr=np.nan, racr=np.nan, passing_epa=0.0, rushing_epa=0.0, receiving_epa=0.0):
    return [season, pid, position, targets, carries, passing_epa, rushing_epa, receiving_epa,
            target_share, air_yards_share, wopr, racr]


class TestPreseasonLagCorrectness:
    def test_lags_all_fields_by_exactly_one_season(self):
        raw = _raw_usage_df(
            _raw_row(2021, "00-1", "WR", targets=50, target_share=0.15),
            _raw_row(2022, "00-1", "WR", targets=80, target_share=0.22),
        )
        out = ut.build_preseason_usage_features(raw)
        row_2022 = out[out["season"] == 2022].iloc[0]
        assert row_2022["prior_season_targets"] == 50
        assert row_2022["prior_season_target_share"] == pytest.approx(0.15)

    def test_output_never_contains_plain_same_season_columns(self):
        raw = _raw_usage_df(_raw_row(2022, "00-1", "WR", targets=80))
        out = ut.build_preseason_usage_features(raw)
        assert "targets" not in out.columns
        assert "target_share" not in out.columns
        assert set(out.columns) == set(ut.PRESEASON_OUTPUT_COLUMNS)

    def test_rookie_first_season_is_null(self):
        raw = _raw_usage_df(_raw_row(2022, "00-1", "WR", targets=80, target_share=0.22))
        out = ut.build_preseason_usage_features(raw)
        assert pd.isna(out.loc[0, "prior_season_targets"])
        assert pd.isna(out.loc[0, "prior_season_target_share"])


class TestNoSameSeasonLeakage:
    """The load-bearing test class for the approved raw/preseason
    separation: a season's prior_season_* features must be
    mathematically INDEPENDENT of that same season's own raw row, not
    just correct by coincidence on one example."""

    def test_mutating_current_season_raw_value_does_not_change_its_own_prior_season_feature(self):
        raw_original = _raw_usage_df(
            _raw_row(2019, "00-1", "WR", targets=40, target_share=0.10),
            _raw_row(2020, "00-1", "WR", targets=999, target_share=0.99),  # the "current" season being predicted
        )
        out_original = ut.build_preseason_usage_features(raw_original)
        row_2020_before = out_original[out_original["season"] == 2020].iloc[0]

        # Mutate ONLY season 2020's own raw values -- its prior-season
        # feature (which should reflect 2019) must be completely unaffected.
        raw_mutated = _raw_usage_df(
            _raw_row(2019, "00-1", "WR", targets=40, target_share=0.10),
            _raw_row(2020, "00-1", "WR", targets=1, target_share=0.01),
        )
        out_mutated = ut.build_preseason_usage_features(raw_mutated)
        row_2020_after = out_mutated[out_mutated["season"] == 2020].iloc[0]

        assert row_2020_before["prior_season_targets"] == row_2020_after["prior_season_targets"] == 40
        assert row_2020_before["prior_season_target_share"] == row_2020_after["prior_season_target_share"] == pytest.approx(0.10)

    def test_exhaustive_check_every_row_matches_real_prior_season_value(self):
        """Multi-player, multi-season fixture -- every single
        prior_season_targets value must equal that player's REAL
        season-1 targets, with zero exceptions, mirroring the
        exhaustive (not sampled) leakage check already used for
        family #7's real-data audit."""
        rows = []
        for pid in ["00-1", "00-2", "00-3"]:
            for i, season in enumerate(range(2018, 2023)):
                rows.append(_raw_row(season, pid, "WR", targets=float(season * 10 + hash(pid) % 7)))
        raw = _raw_usage_df(*rows)
        out = ut.build_preseason_usage_features(raw)

        lookup = raw.set_index(["season", "player_id"])["targets"]
        mismatches = 0
        for _, row in out.iterrows():
            prior_key = (row["season"] - 1, row["player_id"])
            if prior_key in lookup.index:
                if row["prior_season_targets"] != lookup.loc[prior_key]:
                    mismatches += 1
            else:
                if pd.notna(row["prior_season_targets"]):
                    mismatches += 1
        assert mismatches == 0


class TestPreseasonRequiredColumns:
    def test_missing_column_raises(self):
        bad_raw = pd.DataFrame({"season": [2022]})
        with pytest.raises(ValueError, match="raw_season_usage is missing required columns"):
            ut.build_preseason_usage_features(bad_raw)


class TestPreseasonRowCountPreserved:
    def test_one_row_per_season_player(self):
        raw = _raw_usage_df(
            _raw_row(2021, "00-1", "WR", targets=50),
            _raw_row(2022, "00-1", "WR", targets=80),
            _raw_row(2022, "00-2", "RB", carries=100),
        )
        out = ut.build_preseason_usage_features(raw)
        assert len(out) == 3
