"""
tests/test_dataset2_partial_season_canonical.py

Protects lib/dataset2/partial_season_canonical.py -- the family #9
canonicalization prerequisite (research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md)
built before any Dataset 2 canonical predictor table. Three concerns,
each real and previously either missing or wrong:

1. GRAIN: partial_season_traits.py's builders return multiple rows per
   (season, player_id) whenever window_n/(position, metric_name) vary.
   TestGrainAndNaming proves the pivot produces exactly one row per
   (season, player_id) / (prediction_season, player_id), with no
   column-name collisions, and spot-checks the canonical naming scheme.
2. LAG: partial_season_traits.py itself never lags anything -- every
   output describes the observation season's own in-season split.
   TestLagLeakage proves the separate preseason-facing relabeling step
   is a real, row-for-row shift (mutating one observation row can only
   ever change the ONE preseason row it maps to), that rookies get
   real nulls (never zeroes), and that the most recent real
   observation season still produces a real, explicitly-flagged
   future prediction-season row.
3. BOOLEAN NORMALIZATION: a real bug class found while writing the
   canonical-table proposal -- several of partial_season_traits.py's
   own `>=` comparisons against a real NaN silently evaluate to False,
   not NaN, for TEAM-GAME-basis flags on a non-applicable row.
   TestBooleanNormalization proves the canonical layer fixes this
   (real <NA>, nullable "boolean" dtype) without breaking the
   ACTIVE-GAME-basis case, where a real zero-active-games False is a
   real fact, not an artifact, and must stay False.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.partial_season_canonical import (
    CANONICAL_OUTCOME_PENDING_COLUMN,
    CANONICAL_STATUS_COLUMN,
    build_family9_observation_wide,
    build_family9_preseason_features,
)
from lib.dataset2.partial_season_traits import TEAM_GAME_STATUS_APPLICABLE, TEAM_GAME_STATUS_UNAVAILABLE_TRADED

# Real 2015 (16-game era) team AAA: real bye at week 9 -> 16 real games
# across weeks 1-17 -- same fixture convention as
# tests/test_dataset2_partial_season_traits.py.
AAA_2015_WEEKS = [wk for wk in range(1, 18) if wk != 9]
AAA_2016_WEEKS = list(range(1, 18))  # no bye modeled -- fine, only used for a second season


def _population(*rows):
    return pd.DataFrame([{"season": s, "player_id": p, "position": pos} for s, p, pos in rows])


def _weekly_all_positions(rows):
    """rows: list of (season, week, team, season_type)."""
    return pd.DataFrame([{"season": s, "week": w, "team": t, "season_type": st} for s, w, t, st in rows])


def _full_weekly_player(rows):
    """rows: list of (season, player_id, week, team, ppg, attempts, carries,
    rushing_yards, targets, receiving_yards). Every family #9 efficiency/
    role pair's real source column is required on every call regardless
    of which position is actually in the population, so every test
    fixture must carry all of them (unused ones default to 0)."""
    columns = (
        "season",
        "player_id",
        "week",
        "team",
        "fantasy_points_ppr",
        "attempts",
        "passing_epa",
        "carries",
        "rushing_yards",
        "targets",
        "receiving_yards",
    )
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        [
            {
                "season": s,
                "player_id": p,
                "week": w,
                "team": t,
                "fantasy_points_ppr": ppg,
                "attempts": att,
                "passing_epa": 0.0,
                "carries": carries,
                "rushing_yards": ry,
                "targets": tgt,
                "receiving_yards": recy,
            }
            for s, p, w, t, ppg, att, carries, ry, tgt, recy in rows
        ]
    )


def _rb_weekly(season, player_id, weeks, team, carries_per_week=5, ppg=5.0):
    return [
        (season, player_id, wk, team, ppg, 0, carries_per_week, carries_per_week * 4.0, 2, 10.0) for wk in weeks
    ]


class TestGrainAndNaming:
    def test_observation_wide_one_row_per_season_player(self):
        pop = _population((2015, "P1", "RB"), (2015, "P2", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _full_weekly_player(_rb_weekly(2015, "P1", AAA_2015_WEEKS, "AAA") + _rb_weekly(2015, "P2", AAA_2015_WEEKS, "AAA"))
        out, mapping = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        assert len(out) == 2
        assert out.duplicated(subset=["season", "player_id"]).sum() == 0
        assert len(out.columns) == len(set(out.columns))
        assert len(mapping) > 0

    def test_preseason_features_one_row_per_prediction_season_player(self):
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _full_weekly_player(_rb_weekly(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        pre = build_family9_preseason_features(out)
        assert len(pre) == 1
        assert pre.duplicated(subset=["prediction_season", "player_id"]).sum() == 0

    def test_no_column_name_collisions_across_efficiency_and_role_and_snap(self):
        pop = _population((2015, "P1", "RB"), (2015, "P2", "QB"), (2015, "P3", "WR"), (2015, "P4", "TE"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        rows = (
            _rb_weekly(2015, "P1", AAA_2015_WEEKS, "AAA")
            + [(2015, "P2", wk, "AAA", 15.0, 25, 0, 0.0, 0, 0.0) for wk in AAA_2015_WEEKS]
            + [(2015, "P3", wk, "AAA", 8.0, 0, 0, 0.0, 6, 40.0) for wk in AAA_2015_WEEKS]
            + [(2015, "P4", wk, "AAA", 4.0, 0, 0, 0.0, 3, 20.0) for wk in AAA_2015_WEEKS]
        )
        wp = _full_weekly_player(rows)
        last4 = AAA_2015_WEEKS[-4:]
        raw_snaps = pd.DataFrame(
            [{"season": 2015, "week": wk, "team": "AAA", "player_id": "OL1", "offense_snaps": 60.0} for wk in last4]
            + [
                {"season": 2015, "week": wk, "team": "AAA", "player_id": pid, "offense_snaps": 20.0}
                for wk in last4
                for pid in ("P1", "P2", "P3", "P4")
            ]
        )
        # Would raise RuntimeError on any real collision -- the test IS
        # that this call succeeds across every position/window combo.
        out, mapping = build_family9_observation_wide(pop, wp, wap, raw_snaps, window_ns=(4, 6, 8))
        assert len(out.columns) == len(set(out.columns))
        assert mapping["canonical_column"].duplicated().sum() == 0

    def test_canonical_naming_matches_window_position_metric_basis_tier(self):
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _full_weekly_player(_rb_weekly(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4, 6))
        expected = [
            "fam9_team_final_4_rb_rushing_role_present",
            "fam9_team_final_6_rb_rushing_role_present",
            "fam9_active_final_4_rb_rushing_role_present",
            "fam9_team_final_4_rb_receiving_meaningful_role",
            "fam9_team_first_half_points_per_team_game",
            "fam9_team_second_half_points_per_team_game",
            CANONICAL_STATUS_COLUMN,
        ]
        for col in expected:
            assert col in out.columns, col

    def test_team_and_active_game_bases_preserved_as_separate_columns_with_different_values(self):
        # P1 misses week 1 of the real final-4 window entirely (team
        # game happened, no real usage) but that week is NOT among
        # their own real active games -- team-game rate should read
        # lower than active-game rate for the same real window.
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        last4 = AAA_2015_WEEKS[-4:]
        rows = [(2015, "P1", wk, "AAA", 5.0, 0, 10, 40.0, 0, 0.0) for wk in last4[1:]]
        wp = _full_weekly_player(rows)
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        team_rate = out.iloc[0]["fam9_team_final_4_rb_rushing_opportunity_per_team_game"]
        active_rate = out.iloc[0]["fam9_active_final_4_rb_rushing_opportunity_per_active_game"]
        assert team_rate == pytest.approx(30 / 4)  # 3 real weeks of 10 carries / fixed window size 4
        assert active_rate == pytest.approx(10.0)  # 30 carries / 3 real active games
        assert team_rate != active_rate

    def test_applicable_zero_usage_preserved_as_real_zero_not_null(self):
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        # A real row outside the final-4 window establishes the single
        # team; zero real usage inside the window itself.
        wp = _full_weekly_player([(2015, "P1", AAA_2015_WEEKS[0], "AAA", 0.0, 0, 0, 0.0, 0, 0.0)])
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        row = out.iloc[0]
        assert row[CANONICAL_STATUS_COLUMN] == TEAM_GAME_STATUS_APPLICABLE
        assert row["fam9_team_final_4_rb_rushing_opportunity_per_team_game"] == 0.0
        assert row["fam9_team_final_4_rb_rushing_role_present"] == False  # noqa: E712 -- real, not null

    def test_team_game_window_status_semantics_preserved_for_traded_player(self):
        pop = _population((2023, "P1", "RB"))
        wap = _weekly_all_positions(
            [(2023, wk, "KC", "REG") for wk in range(1, 10)] + [(2023, wk, "SF", "REG") for wk in range(10, 19)]
        )
        rows = [(2023, "P1", wk, "KC", 5.0, 0, 5, 20.0, 0, 0.0) for wk in range(1, 10)] + [
            (2023, "P1", wk, "SF", 5.0, 0, 5, 20.0, 0, 0.0) for wk in range(10, 19)
        ]
        wp = _full_weekly_player(rows)
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        row = out.iloc[0]
        assert row[CANONICAL_STATUS_COLUMN] == TEAM_GAME_STATUS_UNAVAILABLE_TRADED
        assert pd.isna(row["fam9_team_final_4_rb_rushing_opportunity_per_team_game"])
        # Active-game basis never filters by team -- must stay real.
        assert not pd.isna(row["fam9_active_final_4_rb_rushing_opportunity_per_active_game"])


class TestLagLeakage:
    def _build_pre(self, seasons_weekly_rows, weekly_all_positions_rows, population_rows):
        pop = _population(*population_rows)
        wap = _weekly_all_positions(weekly_all_positions_rows)
        wp = _full_weekly_player(seasons_weekly_rows)
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        return build_family9_preseason_features(out)

    def test_mutating_season_n_does_not_change_season_n_own_preseason_row(self):
        # Two real seasons (2014 real weeks -> a REG span, 2015's AAA_2015_WEEKS)
        # for the same player. prediction_season=2015's row is sourced
        # from OBSERVATION season 2014 -- mutating season 2015's own
        # weekly data must never change it.
        weeks_2014 = list(range(1, 17))
        pop = [(2014, "P1", "RB"), (2015, "P1", "RB")]
        wap_rows = [(2014, wk, "AAA", "REG") for wk in weeks_2014] + [
            (2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS
        ]

        rows_baseline = _rb_weekly(2014, "P1", weeks_2014, "AAA", carries_per_week=5) + _rb_weekly(
            2015, "P1", AAA_2015_WEEKS, "AAA", carries_per_week=7
        )
        pre_baseline = self._build_pre(rows_baseline, wap_rows, pop)

        rows_mutated = _rb_weekly(2014, "P1", weeks_2014, "AAA", carries_per_week=5) + _rb_weekly(
            2015, "P1", AAA_2015_WEEKS, "AAA", carries_per_week=99  # season 2015 mutated
        )
        pre_mutated = self._build_pre(rows_mutated, wap_rows, pop)

        row_2015_baseline = pre_baseline[pre_baseline["prediction_season"] == 2015].iloc[0]
        row_2015_mutated = pre_mutated[pre_mutated["prediction_season"] == 2015].iloc[0]
        pd.testing.assert_series_equal(row_2015_baseline, row_2015_mutated, check_names=False)

    def test_mutating_season_n_only_changes_season_n_plus_1_feature_row(self):
        weeks_2014 = list(range(1, 17))
        pop = [(2014, "P1", "RB"), (2015, "P1", "RB")]
        wap_rows = [(2014, wk, "AAA", "REG") for wk in weeks_2014] + [
            (2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS
        ]
        rows_baseline = _rb_weekly(2014, "P1", weeks_2014, "AAA", carries_per_week=5) + _rb_weekly(
            2015, "P1", AAA_2015_WEEKS, "AAA", carries_per_week=7
        )
        rows_mutated = _rb_weekly(2014, "P1", weeks_2014, "AAA", carries_per_week=5) + _rb_weekly(
            2015, "P1", AAA_2015_WEEKS, "AAA", carries_per_week=99
        )
        pre_baseline = self._build_pre(rows_baseline, wap_rows, pop)
        pre_mutated = self._build_pre(rows_mutated, wap_rows, pop)

        rate_baseline = pre_baseline.set_index("prediction_season")[
            "fam9_team_final_4_rb_rushing_opportunity_per_team_game"
        ]
        rate_mutated = pre_mutated.set_index("prediction_season")[
            "fam9_team_final_4_rb_rushing_opportunity_per_team_game"
        ]
        assert rate_baseline[2015] == rate_mutated[2015]  # unaffected -- sourced from 2014
        assert rate_baseline[2016] != rate_mutated[2016]  # sourced from mutated 2015

    def test_rookie_or_no_prior_data_gets_null_not_zero_on_left_join(self):
        pop = [(2015, "P1", "RB")]
        wap_rows = [(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS]
        rows = _rb_weekly(2015, "P1", AAA_2015_WEEKS, "AAA")
        pre = self._build_pre(rows, wap_rows, pop)

        # Target scoring population for prediction_season 2016 includes
        # a real rookie (P2) with NO observation-season history at all.
        target = pd.DataFrame({"prediction_season": [2016, 2016], "player_id": ["P1", "P2"]})
        joined = target.merge(pre, on=["prediction_season", "player_id"], how="left")

        p1_row = joined[joined["player_id"] == "P1"].iloc[0]
        p2_row = joined[joined["player_id"] == "P2"].iloc[0]

        assert not pd.isna(p1_row["fam9_team_final_4_rb_rushing_opportunity_per_team_game"])
        assert pd.isna(p2_row["fam9_team_final_4_rb_rushing_opportunity_per_team_game"])
        assert pd.isna(p2_row["fam9_team_final_4_rb_rushing_opportunity_per_team_game"]) and (
            p2_row["fam9_team_final_4_rb_rushing_opportunity_per_team_game"] != 0.0
        )
        # A real rookie must never read as a real, applicable zero --
        # they simply have no observation-season row to lag from.
        assert pd.isna(p2_row[CANONICAL_STATUS_COLUMN])

    def test_final_historical_observation_season_produces_a_future_prediction_row(self):
        pop = [(2025, "P1", "RB")]
        wap_rows = [(2025, wk, "AAA", "REG") for wk in AAA_2015_WEEKS]
        rows = _rb_weekly(2025, "P1", AAA_2015_WEEKS, "AAA")
        pre = self._build_pre(rows, wap_rows, pop)

        row = pre.iloc[0]
        assert row["observation_season"] == 2025
        assert row["prediction_season"] == 2026
        assert not pd.isna(row["fam9_team_final_4_rb_rushing_opportunity_per_team_game"])
        assert row[CANONICAL_OUTCOME_PENDING_COLUMN] == True  # noqa: E712

    def test_earlier_season_not_flagged_as_outcome_pending(self):
        weeks_2014 = list(range(1, 17))
        pop = [(2014, "P1", "RB"), (2015, "P1", "RB")]
        wap_rows = [(2014, wk, "AAA", "REG") for wk in weeks_2014] + [
            (2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS
        ]
        rows = _rb_weekly(2014, "P1", weeks_2014, "AAA") + _rb_weekly(2015, "P1", AAA_2015_WEEKS, "AAA")
        pre = self._build_pre(rows, wap_rows, pop)

        row_2015 = pre[pre["prediction_season"] == 2015].iloc[0]
        row_2016 = pre[pre["prediction_season"] == 2016].iloc[0]
        assert row_2015[CANONICAL_OUTCOME_PENDING_COLUMN] == False  # noqa: E712
        assert row_2016[CANONICAL_OUTCOME_PENDING_COLUMN] == True  # noqa: E712

    def test_no_duplicate_prediction_season_player_keys(self):
        pop = [(2014, "P1", "RB"), (2015, "P1", "RB"), (2015, "P2", "WR")]
        weeks_2014 = list(range(1, 17))
        wap_rows = [(2014, wk, "AAA", "REG") for wk in weeks_2014] + [
            (2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS
        ]
        rows = (
            _rb_weekly(2014, "P1", weeks_2014, "AAA")
            + _rb_weekly(2015, "P1", AAA_2015_WEEKS, "AAA")
            + [(2015, "P2", wk, "AAA", 8.0, 0, 0, 0.0, 5, 30.0) for wk in AAA_2015_WEEKS]
        )
        pre = self._build_pre(rows, wap_rows, pop)
        assert pre.duplicated(subset=["prediction_season", "player_id"]).sum() == 0


class TestBooleanNormalization:
    def test_team_game_boolean_columns_null_not_false_for_non_applicable_status(self):
        pop = _population((2023, "P1", "RB"))
        wap = _weekly_all_positions(
            [(2023, wk, "KC", "REG") for wk in range(1, 10)] + [(2023, wk, "SF", "REG") for wk in range(10, 19)]
        )
        rows = [(2023, "P1", wk, "KC", 5.0, 0, 5, 20.0, 0, 0.0) for wk in range(1, 10)] + [
            (2023, "P1", wk, "SF", 5.0, 0, 5, 20.0, 0, 0.0) for wk in range(10, 19)
        ]
        wp = _full_weekly_player(rows)
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        row = out.iloc[0]

        assert row[CANONICAL_STATUS_COLUMN] == TEAM_GAME_STATUS_UNAVAILABLE_TRADED
        for col in (
            "fam9_team_final_4_sample_qualified_primary",
            "fam9_team_final_4_sample_qualified_sensitivity",
            "fam9_team_final_4_rb_rushing_efficiency_volume_eligible_exploratory",
            "fam9_team_final_4_rb_rushing_role_present",
        ):
            assert pd.isna(row[col]), col
            assert out[col].dtype == "boolean", col

    def test_active_game_boolean_columns_stay_real_false_for_real_zero_active_games(self):
        # P1 has real rows for a DIFFERENT season only -- zero real
        # active games in season 2015 itself. This is a real, known
        # fact (never played that season), not a comparison-against-NaN
        # artifact -- False must be preserved, not converted to <NA>.
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _full_weekly_player([])
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        row = out.iloc[0]
        assert row["fam9_active_final_4_sample_qualified_primary"] == False  # noqa: E712
        assert out["fam9_active_final_4_sample_qualified_primary"].dtype == "boolean"

    def test_role_tier_flags_already_nullable_stay_nullable_after_normalization(self):
        pop = _population((2015, "P1", "RB"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _full_weekly_player(_rb_weekly(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, _ = build_family9_observation_wide(pop, wp, wap, None, window_ns=(4,))
        assert out["fam9_team_final_4_rb_rushing_role_present"].dtype == "boolean"
        assert out["fam9_active_final_4_rb_rushing_role_present"].dtype == "boolean"

    def test_snap_share_has_coverage_null_for_no_source_b_data(self):
        pop = _population((2015, "P1", "WR"))
        wap = _weekly_all_positions([(2015, wk, "AAA", "REG") for wk in AAA_2015_WEEKS])
        wp = _full_weekly_player([(2015, "P1", wk, "AAA", 5.0, 0, 0, 0.0, 3, 20.0) for wk in AAA_2015_WEEKS])
        empty_raw_snaps = pd.DataFrame(
            {
                "season": pd.Series(dtype="int64"),
                "week": pd.Series(dtype="int64"),
                "team": pd.Series(dtype="object"),
                "player_id": pd.Series(dtype="object"),
                "offense_snaps": pd.Series(dtype="float64"),
            }
        )
        out, _ = build_family9_observation_wide(pop, wp, wap, empty_raw_snaps, window_ns=(4,))
        row = out.iloc[0]
        assert row[CANONICAL_STATUS_COLUMN] == TEAM_GAME_STATUS_APPLICABLE
        assert row["fam9_team_final_4_wr_snap_has_snap_coverage"] == False  # noqa: E712
        assert pd.isna(row["fam9_team_final_4_wr_snap_offense_snap_share"])
        assert pd.isna(row["fam9_team_final_4_wr_snap_role_present"])
