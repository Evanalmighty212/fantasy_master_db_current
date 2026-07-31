"""
tests/test_dataset2_usage_traits.py

Covers lib/dataset2/usage_traits.py -- Source A of the Dataset 2
opportunity/usage foundation. REVISED 2026-07 after a real-data
aggregation-semantics audit
(research/dataset2/USAGE_AGGREGATION_AUDIT_2026_07.md) found the
original weekly-average approach was mathematically wrong for share
fields and silently included postseason rows. Protects:

1. Postseason (season_type == 'POST') rows are excluded from every
   aggregate.
2. target_share/air_yards_share/wopr are RECOMPUTED from real summed
   numerators/denominators, never a naive average of weekly ratios --
   and specifically that air_yards_share uses team-week
   `passing_air_yards` as its denominator, not summed
   `receiving_air_yards` (the real, verified-correct formula).
3. racr is NOT output at all (deferred, per the approved
   reconstruct-or-defer rule) -- but its real underlying inputs
   (`receiving_yards`, `receiving_air_yards`) ARE output as plain sums.
4. The team-week denominator is computed from the FULL weekly file
   (all positions), not just the rows in `population`'s scope.
5. A traded player's recomputed shares correctly follow them across
   teams (each week's own real team is used for that week's
   denominator contribution).
6. The raw/preseason/same-season separation (unchanged from the first
   version): lag correctness and the load-bearing no-leakage guarantee.
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


def _weekly_row(season, pid, week, team, season_type="REG", targets=0, carries=0, receiving_yards=0,
                 receiving_air_yards=0, passing_air_yards=0, passing_epa=0.0, rushing_epa=0.0, receiving_epa=0.0,
                 receptions=0, receiving_yards_after_catch=0):
    return {
        "season": season, "player_id": pid, "week": week, "team": team, "season_type": season_type,
        "targets": targets, "carries": carries, "receiving_yards": receiving_yards,
        "receiving_air_yards": receiving_air_yards, "passing_air_yards": passing_air_yards,
        "passing_epa": passing_epa, "rushing_epa": rushing_epa, "receiving_epa": receiving_epa,
        "receptions": receptions, "receiving_yards_after_catch": receiving_yards_after_catch,
    }


def _weekly_df(*rows):
    if not rows:
        return pd.DataFrame(columns=list(ut.WEEKLY_REQUIRED_COLUMNS))
    return pd.DataFrame(list(rows))


class TestPostseasonExcluded:
    def test_post_row_not_counted_in_sums(self):
        pop = _population_df({"season": 2023, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-1", 1, "ATL", season_type="REG", targets=5),
            _weekly_row(2023, "00-1", 19, "ATL", season_type="POST", targets=100),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "targets"] == 5

    def test_post_row_not_counted_in_team_denominator(self):
        pop = _population_df({"season": 2023, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-1", 1, "ATL", season_type="REG", targets=5, passing_air_yards=100),
            _weekly_row(2023, "00-2", 1, "ATL", season_type="REG", targets=5, passing_air_yards=100),
            # a huge playoff week that must not leak into the REG denominator
            _weekly_row(2023, "00-1", 19, "ATL", season_type="POST", targets=50, passing_air_yards=1000),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "target_share"] == pytest.approx(0.5)  # 5 / (5+5), not diluted by the POST week


class TestTargetShareRecomputedNotAveraged:
    def test_recomputed_as_season_sum_ratio_not_weekly_average(self):
        """A naive weekly average would give (0.5+0.1)/2=0.30 for player
        A. The real, correct season share (per the audit's verified
        formula) is player's season targets / team's season targets =
        (5+1)/(10+10)=0.30 too in this SYMMETRIC case -- use an
        ASYMMETRIC volume case so the two methods actually diverge."""
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            # week 1: heavy team volume, player captures half
            _weekly_row(2023, "00-a", 1, "ATL", targets=10),
            _weekly_row(2023, "00-b", 1, "ATL", targets=10),
            # week 2: tiny team volume, player captures a small share
            _weekly_row(2023, "00-a", 2, "ATL", targets=1),
            _weekly_row(2023, "00-b", 2, "ATL", targets=9),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        # naive weekly average would be (0.5 + 0.1)/2 = 0.30
        # correct season-sum-ratio: (10+1)/(20+10) = 11/30 = 0.3667
        naive_average = 0.30
        correct = 11 / 30
        assert out.loc[0, "target_share"] == pytest.approx(correct)
        assert out.loc[0, "target_share"] != pytest.approx(naive_average, abs=1e-6)

    def test_uses_full_weekly_file_denominator_not_just_population_rows(self):
        """A real target recorded by a position OUTSIDE the skill-position
        population (e.g. a trick-play target to an OL/FB tagged
        differently) must still count in the team-week denominator --
        verified against real 2023 data that skill-only totals
        undercount the real team total."""
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-a", 1, "ATL", targets=5),
            _weekly_row(2023, "00-hidden", 1, "ATL", targets=5),  # e.g. a non-skill-tagged real target
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "target_share"] == pytest.approx(0.5)  # 5 / (5+5), not 5/5=1.0


class TestAirYardsShareUsesPassingAirYardsDenominator:
    def test_denominator_is_team_passing_air_yards_not_summed_receiving_air_yards(self):
        """The verified-correct real formula: air_yards_share =
        player's receiving_air_yards / team's passing_air_yards (the
        QB-side total, which includes incompletions/spikes not
        credited to any receiver) -- NOT summed receiving_air_yards,
        which undercounts (real 2023 check: mean discrepancy 0.0067,
        max 0.9, if the wrong denominator is used)."""
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            # team's real passing_air_yards (150) exceeds summed
            # receiving_air_yards (100) -- e.g. incompletions with no
            # credited receiver still count toward passing_air_yards.
            _weekly_row(2023, "00-a", 1, "ATL", receiving_air_yards=100, passing_air_yards=150),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "air_yards_share"] == pytest.approx(100 / 150)


class TestWoprRecomputedFromRecomputedShares:
    def test_wopr_formula(self):
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-a", 1, "ATL", targets=5, receiving_air_yards=40, passing_air_yards=100),
            _weekly_row(2023, "00-b", 1, "ATL", targets=5),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        expected_target_share = 0.5
        expected_ay_share = 40 / 100
        expected_wopr = 1.5 * expected_target_share + 0.7 * expected_ay_share
        assert out.loc[0, "wopr"] == pytest.approx(expected_wopr)


class TestRacrDeferredNotComputed:
    def test_racr_not_in_output_columns(self):
        assert "racr" not in ut.RAW_OUTPUT_COLUMNS
        assert "racr" not in ut.PRESEASON_OUTPUT_COLUMNS

    def test_receiving_yards_and_air_yards_still_output_as_raw_sums(self):
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-a", 1, "ATL", receiving_yards=30, receiving_air_yards=20),
            _weekly_row(2023, "00-a", 2, "ATL", receiving_yards=15, receiving_air_yards=-5),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "receiving_yards"] == 45
        assert out.loc[0, "receiving_air_yards"] == 15


class TestReceptionsSummed:
    """Added 2026-07 to unlock family #88's compact workload core
    (lib/dataset2/fragility_traits.py::build_workload_core_traits()).
    Same real, unambiguous SUM treatment as targets/carries -- no new
    aggregation logic, so this is a thin regression guard, not a new
    formula test."""

    def test_receptions_summed_across_real_reg_weeks(self):
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-a", 1, "ATL", receptions=5),
            _weekly_row(2023, "00-a", 2, "ATL", receptions=7),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "receptions"] == 12

    def test_postseason_receptions_excluded(self):
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-a", 1, "ATL", receptions=5, season_type="REG"),
            _weekly_row(2023, "00-a", 20, "ATL", receptions=9, season_type="POST"),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "receptions"] == 5

    def test_zero_real_receptions_is_real_zero_not_null(self):
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "RB"})
        weekly = _weekly_df(_weekly_row(2023, "00-a", 1, "ATL", carries=20, receptions=0))
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "receptions"] == 0

    def test_receptions_lagged_to_prior_season(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-a", "position": "WR"},
            {"season": 2023, "player_id": "00-a", "position": "WR"},
        )
        weekly = _weekly_df(_weekly_row(2022, "00-a", 1, "ATL", receptions=40))
        raw = ut.build_raw_season_usage(pop, weekly)
        out = ut.build_preseason_usage_features(raw)
        row_2023 = out[out["season"] == 2023].iloc[0]
        assert row_2023["prior_season_receptions"] == 40

    def test_rookie_prior_season_receptions_is_null(self):
        pop = _population_df({"season": 2023, "player_id": "00-rookie", "position": "WR"})
        weekly = _weekly_df(_weekly_row(2023, "00-rookie", 1, "ATL", receptions=10))
        raw = ut.build_raw_season_usage(pop, weekly)
        out = ut.build_preseason_usage_features(raw)
        assert pd.isna(out.loc[0, "prior_season_receptions"])


class TestReceivingYardsAfterCatchSummed:
    """Added 2026-07 to unlock family #18's receiving-efficiency core
    (lib/dataset2/receiving_efficiency_traits.py). Same real,
    unambiguous SUM treatment as receiving_yards -- no new aggregation
    logic. See usage_traits.py's own module-docstring YAC coverage
    audit for the real coverage finding backing this field."""

    def test_yac_summed_across_real_reg_weeks(self):
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-a", 1, "ATL", receiving_yards_after_catch=15),
            _weekly_row(2023, "00-a", 2, "ATL", receiving_yards_after_catch=22),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "receiving_yards_after_catch"] == 37

    def test_postseason_yac_excluded(self):
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-a", 1, "ATL", receiving_yards_after_catch=15, season_type="REG"),
            _weekly_row(2023, "00-a", 20, "ATL", receiving_yards_after_catch=40, season_type="POST"),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "receiving_yards_after_catch"] == 15

    def test_real_negative_weekly_yac_is_summed_not_floored(self):
        # A real, possible per-week outcome (see module docstring's
        # audit) -- must never be clamped to zero during aggregation.
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        weekly = _weekly_df(
            _weekly_row(2023, "00-a", 1, "ATL", receiving_yards_after_catch=10),
            _weekly_row(2023, "00-a", 2, "ATL", receiving_yards_after_catch=-3),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "receiving_yards_after_catch"] == 7

    def test_yac_lagged_to_prior_season(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-a", "position": "WR"},
            {"season": 2023, "player_id": "00-a", "position": "WR"},
        )
        weekly = _weekly_df(_weekly_row(2022, "00-a", 1, "ATL", receiving_yards_after_catch=55))
        raw = ut.build_raw_season_usage(pop, weekly)
        out = ut.build_preseason_usage_features(raw)
        row_2023 = out[out["season"] == 2023].iloc[0]
        assert row_2023["prior_season_receiving_yards_after_catch"] == 55

    def test_rookie_prior_season_yac_is_null(self):
        pop = _population_df({"season": 2023, "player_id": "00-rookie", "position": "WR"})
        weekly = _weekly_df(_weekly_row(2023, "00-rookie", 1, "ATL", receiving_yards_after_catch=20))
        raw = ut.build_raw_season_usage(pop, weekly)
        out = ut.build_preseason_usage_features(raw)
        assert pd.isna(out.loc[0, "prior_season_receiving_yards_after_catch"])


class TestTradedPlayerFollowedCorrectly:
    def test_season_share_uses_each_weeks_own_real_team(self):
        """Real pattern from a real 2023 trade (Chase Claypool,
        CHI weeks 1-3 -> MIA weeks 7-18): the player's recomputed
        season share must be built from EACH week's own team's
        denominator, not one team's full-season total."""
        pop = _population_df({"season": 2023, "player_id": "00-traded", "position": "WR"})
        weekly = _weekly_df(
            # weeks with TEAM_A
            _weekly_row(2023, "00-traded", 1, "TEAM_A", targets=2),
            _weekly_row(2023, "00-traded", 2, "TEAM_A", targets=8),
            _weekly_row(2023, "00-other-a", 1, "TEAM_A", targets=8),
            _weekly_row(2023, "00-other-a", 2, "TEAM_A", targets=12),
            # weeks with TEAM_B, after the trade
            _weekly_row(2023, "00-traded", 3, "TEAM_B", targets=1),
            _weekly_row(2023, "00-other-b", 3, "TEAM_B", targets=19),
        )
        out = ut.build_raw_season_usage(pop, weekly)
        # player targets: 2+8+1=11. Team-week denominators actually
        # applicable to THIS player: week1 TEAM_A=10, week2 TEAM_A=20,
        # week3 TEAM_B=20 -> denominator = 10+20+20 = 50
        assert out.loc[0, "targets"] == 11
        assert out.loc[0, "target_share"] == pytest.approx(11 / 50)


class TestMissingnessAndZeroWeeks:
    def test_zero_real_weekly_rows_counts_zero_shares_null(self):
        pop = _population_df({"season": 2023, "player_id": "00-1", "position": "WR"})
        weekly = _weekly_df()
        out = ut.build_raw_season_usage(pop, weekly)
        assert out.loc[0, "targets"] == 0
        assert pd.isna(out.loc[0, "target_share"])
        assert pd.isna(out.loc[0, "wopr"])


class TestRawSeasonUsageRequiredColumns:
    def test_population_missing_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2023]})
        weekly = _weekly_df(_weekly_row(2023, "00-1", 1, "ATL"))
        with pytest.raises(ValueError, match="population is missing required columns"):
            ut.build_raw_season_usage(bad_pop, weekly)

    def test_weekly_missing_column_raises(self):
        pop = _population_df({"season": 2023, "player_id": "00-1", "position": "WR"})
        bad_weekly = pd.DataFrame({"season": [2023]})
        with pytest.raises(ValueError, match="weekly is missing required columns"):
            ut.build_raw_season_usage(pop, bad_weekly)


class TestRawSeasonUsageRowCountPreserved:
    def test_one_row_per_season_player(self):
        pop = _population_df(
            {"season": 2023, "player_id": "00-1", "position": "WR"},
            {"season": 2023, "player_id": "00-2", "position": "RB"},
        )
        weekly = _weekly_df(_weekly_row(2023, "00-1", 1, "ATL", targets=5))
        out = ut.build_raw_season_usage(pop, weekly)
        assert len(out) == 2


def _raw_usage_df(*rows):
    cols = list(ut.RAW_OUTPUT_COLUMNS)
    return pd.DataFrame(list(rows), columns=cols)


def _raw_row(season, pid, position, targets=0.0, carries=0.0, receiving_yards=0.0, receiving_air_yards=0.0,
             passing_epa=0.0, rushing_epa=0.0, receiving_epa=0.0, receptions=0.0,
             receiving_yards_after_catch=0.0, target_share=np.nan, air_yards_share=np.nan, wopr=np.nan):
    return [season, pid, position, targets, carries, receiving_yards, receiving_air_yards, passing_epa,
            rushing_epa, receiving_epa, receptions, receiving_yards_after_catch, target_share, air_yards_share, wopr]


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
    mathematically INDEPENDENT of that same season's own raw row."""

    def test_mutating_current_season_raw_value_does_not_change_its_own_prior_season_feature(self):
        raw_original = _raw_usage_df(
            _raw_row(2019, "00-1", "WR", targets=40, target_share=0.10),
            _raw_row(2020, "00-1", "WR", targets=999, target_share=0.99),
        )
        out_original = ut.build_preseason_usage_features(raw_original)
        row_2020_before = out_original[out_original["season"] == 2020].iloc[0]

        raw_mutated = _raw_usage_df(
            _raw_row(2019, "00-1", "WR", targets=40, target_share=0.10),
            _raw_row(2020, "00-1", "WR", targets=1, target_share=0.01),
        )
        out_mutated = ut.build_preseason_usage_features(raw_mutated)
        row_2020_after = out_mutated[out_mutated["season"] == 2020].iloc[0]

        assert row_2020_before["prior_season_targets"] == row_2020_after["prior_season_targets"] == 40
        assert row_2020_before["prior_season_target_share"] == row_2020_after["prior_season_target_share"] == pytest.approx(0.10)

    def test_exhaustive_check_every_row_matches_real_prior_season_value(self):
        rows = []
        for pid in ["00-1", "00-2", "00-3"]:
            for season in range(2018, 2023):
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
