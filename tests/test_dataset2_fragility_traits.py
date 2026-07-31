"""
tests/test_dataset2_fragility_traits.py

Covers lib/dataset2/fragility_traits.py -- Dataset 2 families #86
(split, part) and #88 (split, part). REVISED 2026-07 after the
real-data integration audit found the original universal
`committee_uncertainty` interpretation was wrong for WR (multiple
rank-1 WRs reflect real, historically-shifting base personnel
structure, not role uncertainty the way an RB/TE committee does).

Protects the revised, position-aware design:
- `multiple_rank1_players` is the neutral source fact for every
  position, no interpretation attached.
- `qb_starter_uncertainty`/`rb_committee_indicator`/`te_co_starter_indicator`
  are each populated ONLY for their own position (null elsewhere) and
  equal the neutral fact restricted to that position.
- WR gets NO uncertainty-style indicator at all -- only
  personnel-structure/opportunity facts:
  `wr_starter_group_size`, `wr_starter_group_member`,
  `wr_league_starter_group_size_norm` (real, computed fresh per season
  -- never a fixed constant), `wr_starter_group_size_vs_league_norm`.
- Every native tie is preserved; no ordering is ever inferred within a
  tied group, for any position.
- `team_qb_uncertainty` and the #88 durability-risk fields are
  unchanged by this revision.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import fragility_traits as ft
from lib.dataset2 import depth_chart_traits as dct


def _depth_chart_traits_df(*rows):
    cols = [
        "season", "player_id", "position", "depth_chart_team",
        "depth_chart_native_rank", "depth_chart_status", "depth_rank_tied",
        "starter_group_size", "position_starter_count", "depth_chart_schema_era",
    ]
    return pd.DataFrame(list(rows), columns=cols)


def _age_draft_df(*rows):
    cols = ["season", "player_id", "position", "body_size_bmi"]
    return pd.DataFrame(list(rows), columns=cols)


def _row(season, pid, position, team, rank, status, tied, group_size, structural_count):
    return {
        "season": season, "player_id": pid, "position": position, "depth_chart_team": team,
        "depth_chart_native_rank": rank, "depth_chart_status": status, "depth_rank_tied": tied,
        "starter_group_size": group_size, "position_starter_count": structural_count,
        "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL,
    }


class TestMultipleRank1PlayersNeutralFact:
    def test_true_for_any_tied_position(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-wr1", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
        )
        out = ft.build_volume_fragility_traits(df)
        assert out.loc[0, "multiple_rank1_players"] == 1.0

    def test_false_for_clean_single_starter(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-1", "RB", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, False, 1, 1),
        )
        out = ft.build_volume_fragility_traits(df)
        assert out.loc[0, "multiple_rank1_players"] == 0.0

    def test_null_when_no_data(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-1", "WR", None, None, None, None, None, None),
        )
        out = ft.build_volume_fragility_traits(df)
        assert pd.isna(out.loc[0, "multiple_rank1_players"])


class TestPositionScopedIndicatorsQbRbTe:
    def test_qb_starter_uncertainty_populated_only_for_qb(self):
        df = _depth_chart_traits_df(
            _row(2019, "00-newton", "QB", "CAR", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 1),
            _row(2019, "00-allen", "QB", "CAR", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 1),
            _row(2019, "00-mccaffrey", "RB", "CAR", 1, dct.DEPTH_CHART_STATUS_STARTER, False, 1, 1),
        )
        out = ft.build_volume_fragility_traits(df)
        qb_rows = out[out["position"] == "QB"]
        rb_rows = out[out["position"] == "RB"]
        assert (qb_rows["qb_starter_uncertainty"] == 1.0).all()
        assert qb_rows["rb_committee_indicator"].isna().all()
        assert rb_rows["qb_starter_uncertainty"].isna().all()

    def test_rb_committee_indicator_fires_for_real_committee(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-white", "RB", "NE", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 2, 1),
            _row(2020, "00-michel", "RB", "NE", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 2, 1),
        )
        out = ft.build_volume_fragility_traits(df)
        assert (out["rb_committee_indicator"] == 1.0).all()
        assert out["qb_starter_uncertainty"].isna().all()
        assert out["te_co_starter_indicator"].isna().all()

    def test_te_co_starter_indicator_fires_for_real_co_starters(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-kelce", "TE", "KC", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 2, 1),
            _row(2020, "00-yelder", "TE", "KC", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 2, 1),
        )
        out = ft.build_volume_fragility_traits(df)
        assert (out["te_co_starter_indicator"] == 1.0).all()

    def test_clean_single_starter_indicators_false_not_null(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-1", "RB", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, False, 1, 1),
        )
        out = ft.build_volume_fragility_traits(df)
        assert out.loc[0, "rb_committee_indicator"] == 0.0


class TestWrGetsNoUncertaintyIndicator:
    def test_wr_three_way_tie_has_no_uncertainty_fields_populated(self):
        """The central fix: a real 3-way WR tie must NOT populate any
        of the QB/RB/TE-style uncertainty indicators."""
        df = _depth_chart_traits_df(
            _row(2020, "00-wr1", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
            _row(2020, "00-wr2", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
            _row(2020, "00-wr3", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
        )
        out = ft.build_volume_fragility_traits(df)
        assert out["qb_starter_uncertainty"].isna().all()
        assert out["rb_committee_indicator"].isna().all()
        assert out["te_co_starter_indicator"].isna().all()
        # but the neutral fact IS still true -- it's just not interpreted as uncertainty
        assert (out["multiple_rank1_players"] == 1.0).all()

    def test_wr_starter_group_size_is_raw_pass_through(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-wr1", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
            _row(2020, "00-rb1", "RB", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, False, 1, 1),
        )
        out = ft.build_volume_fragility_traits(df)
        wr_row = out[out["player_id"] == "00-wr1"].iloc[0]
        rb_row = out[out["player_id"] == "00-rb1"].iloc[0]
        assert wr_row["wr_starter_group_size"] == 3
        assert pd.isna(rb_row["wr_starter_group_size"])  # never populated for non-WR

    def test_wr_starter_group_member_true_for_starter_false_for_backup(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-wr1", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
            _row(2020, "00-wr4", "WR", "ATL", 2, dct.DEPTH_CHART_STATUS_BACKUP, False, 3, 3),
        )
        out = ft.build_volume_fragility_traits(df)
        starter = out[out["player_id"] == "00-wr1"].iloc[0]
        backup = out[out["player_id"] == "00-wr4"].iloc[0]
        assert starter["wr_starter_group_member"] == 1.0
        assert backup["wr_starter_group_member"] == 0.0


class TestWrLeagueNorm:
    def test_norm_is_real_empirical_mode_not_a_fixed_constant(self):
        """3 teams: two with a 2-player WR group, one with a 3-player
        group -- the real mode that season is 2, not the old fixed
        constant of 3."""
        rows = []
        for team, size in [("ATL", 2), ("NYG", 2), ("DAL", 3)]:
            n_players = size
            for i in range(n_players):
                rows.append(_row(2008, f"00-{team}-{i}", "WR", team, 1, dct.DEPTH_CHART_STATUS_STARTER, True, size, 3))
        df = _depth_chart_traits_df(*rows)
        out = ft.build_volume_fragility_traits(df)
        assert (out["wr_league_starter_group_size_norm"] == 2).all()

    def test_deviation_from_norm_computed_correctly(self):
        rows = []
        for team, size in [("ATL", 2), ("NYG", 2), ("DAL", 3)]:
            for i in range(size):
                rows.append(_row(2008, f"00-{team}-{i}", "WR", team, 1, dct.DEPTH_CHART_STATUS_STARTER, True, size, 3))
        df = _depth_chart_traits_df(*rows)
        out = ft.build_volume_fragility_traits(df)
        dal_row = out[out["player_id"] == "00-DAL-0"].iloc[0]
        atl_row = out[out["player_id"] == "00-ATL-0"].iloc[0]
        assert dal_row["wr_starter_group_size_vs_league_norm"] == 1  # 3 - 2
        assert atl_row["wr_starter_group_size_vs_league_norm"] == 0  # 2 - 2

    def test_norm_computed_per_team_not_per_player_row(self):
        """A 3-way-tied team must count ONCE toward the mode, not three
        times -- otherwise large tied groups would bias their own norm
        upward just by having more rows."""
        rows = []
        # 5 teams with group size 2 (5 team observations), 1 team with group size 3 (but 3 rows/players)
        for i in range(5):
            rows.append(_row(2008, f"00-two-{i}", "WR", f"TEAM{i}", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 2, 3))
        for i in range(3):
            rows.append(_row(2008, f"00-three-{i}", "WR", "BIGTEAM", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3))
        df = _depth_chart_traits_df(*rows)
        out = ft.build_volume_fragility_traits(df)
        # mode by TEAM count is 2 (5 teams) vs 3 (1 team) -- must stay 2,
        # not flip to 3 just because the 3-way team contributed more rows
        assert (out["wr_league_starter_group_size_norm"] == 2).all()


class TestTiesNeverOrdered:
    def test_all_tied_wr_players_keep_identical_native_rank_and_group_size(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-wr1", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
            _row(2020, "00-wr2", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
            _row(2020, "00-wr3", "WR", "ATL", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
        )
        out = ft.build_volume_fragility_traits(df)
        assert (out["wr_starter_group_size"] == 3).all()
        assert (out["wr_starter_group_member"] == 1.0).all()


class TestTeamQbUncertaintyUnchanged:
    def test_broadcast_to_every_skill_player_on_tied_qb_team(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-qb1", "QB", "TEAM", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 2, 1),
            _row(2020, "00-qb2", "QB", "TEAM", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 2, 1),
            _row(2020, "00-wr1", "WR", "TEAM", 1, dct.DEPTH_CHART_STATUS_STARTER, True, 3, 3),
        )
        out = ft.build_volume_fragility_traits(df)
        assert (out["team_qb_uncertainty"] == 1.0).all()

    def test_null_when_no_team_data_not_false(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-1", "WR", None, None, None, None, None, None),
        )
        out = ft.build_volume_fragility_traits(df)
        assert pd.isna(out.loc[0, "team_qb_uncertainty"])


class TestBodySizePositionZ:
    def test_zscore_matches_within_group_pattern(self):
        df = _age_draft_df(
            {"season": 2020, "player_id": "00-1", "position": "WR", "body_size_bmi": 24.0},
            {"season": 2020, "player_id": "00-2", "position": "WR", "body_size_bmi": 26.0},
            {"season": 2020, "player_id": "00-3", "position": "WR", "body_size_bmi": 28.0},
        )
        out = ft.build_durability_risk_traits(df)
        z = out.set_index("player_id")["body_size_position_z"]
        assert z["00-1"] == pytest.approx(-1.0)
        assert z["00-2"] == pytest.approx(0.0)
        assert z["00-3"] == pytest.approx(1.0)


class TestDurabilityRiskNoWorkloadPlaceholder:
    """The literal `workload_qualified="pending"` placeholder was
    removed 2026-07 once the real compact workload core
    (TestWorkloadCoreTraits below) was built -- see
    build_durability_risk_traits()'s own docstring."""

    def test_workload_qualified_column_no_longer_exists(self):
        df = _age_draft_df(
            {"season": 2020, "player_id": "00-1", "position": "WR", "body_size_bmi": 24.0},
        )
        out = ft.build_durability_risk_traits(df)
        assert "workload_qualified" not in out.columns


def _preseason_usage_df(*rows):
    cols = ["season", "player_id", "position", "prior_season_carries", "prior_season_receptions"]
    return pd.DataFrame(list(rows), columns=cols)


class TestWorkloadCoreTraits:
    """Protects build_workload_core_traits() -- family #88's compact
    PRIOR-SEASON workload core, approved 2026-07 (see
    research/dataset2/DATASET2_OUTCOME_DEFINITION_AUDIT_2026_07.md §1).
    Real "touches" = carries + receptions, NEVER carries + targets
    (targets is a separate real opportunity measure, deliberately not
    an input to this function at all)."""

    def test_touches_is_carries_plus_receptions(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "RB", "prior_season_carries": 200, "prior_season_receptions": 45},
        )
        out = ft.build_workload_core_traits(df)
        assert out.loc[0, "prior_season_touches"] == 245

    def test_zero_real_prior_season_touches_is_real_zero_not_null(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "QB", "prior_season_carries": 0.0, "prior_season_receptions": 0.0},
        )
        out = ft.build_workload_core_traits(df)
        assert out.loc[0, "prior_season_touches"] == 0
        assert out.loc[0, "prior_season_heavy_touch_workload"] == False  # noqa: E712 -- real False, not null

    def test_missing_prior_history_is_null_not_zero(self):
        """A rookie's first real season: usage_traits.py's own
        lag_join() leaves BOTH prior_season_carries and
        prior_season_receptions null together (no season N-1 row
        exists at all) -- touches must propagate null, never silently
        treat the missing inputs as zero."""
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-rookie", "position": "RB", "prior_season_carries": np.nan, "prior_season_receptions": np.nan},
        )
        out = ft.build_workload_core_traits(df)
        assert pd.isna(out.loc[0, "prior_season_touches"])
        assert pd.isna(out.loc[0, "prior_season_heavy_touch_workload"])

    def test_heavy_touch_workload_flag_at_real_threshold(self):
        import config
        assert config.DATASET2_FAM88_HEAVY_TOUCH_WORKLOAD_THRESHOLD == 350
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-heavy", "position": "RB", "prior_season_carries": 300, "prior_season_receptions": 50},  # 350, exact boundary
            {"season": 2023, "player_id": "00-light", "position": "RB", "prior_season_carries": 300, "prior_season_receptions": 49},  # 349, just under
        )
        out = ft.build_workload_core_traits(df).set_index("player_id")
        assert out.loc["00-heavy", "prior_season_heavy_touch_workload"] == True  # noqa: E712
        assert out.loc["00-light", "prior_season_heavy_touch_workload"] == False  # noqa: E712

    def test_heavy_touch_workload_is_nullable_boolean_dtype(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "RB", "prior_season_carries": 300, "prior_season_receptions": 50},
        )
        out = ft.build_workload_core_traits(df)
        assert out["prior_season_heavy_touch_workload"].dtype == "boolean"

    def test_required_column_validation(self):
        bad_df = pd.DataFrame({"season": [2023]})
        with pytest.raises(ValueError, match="preseason_usage_df is missing required columns"):
            ft.build_workload_core_traits(bad_df)

    def test_one_row_per_input_row(self):
        df = _preseason_usage_df(
            {"season": 2023, "player_id": "00-1", "position": "RB", "prior_season_carries": 100, "prior_season_receptions": 20},
            {"season": 2023, "player_id": "00-2", "position": "WR", "prior_season_carries": 0, "prior_season_receptions": 60},
        )
        out = ft.build_workload_core_traits(df)
        assert len(out) == 2


class TestRequiredColumnValidation:
    def test_volume_fragility_missing_column_raises(self):
        bad_df = pd.DataFrame({"season": [2020]})
        with pytest.raises(ValueError, match="depth_chart_traits_df is missing required columns"):
            ft.build_volume_fragility_traits(bad_df)

    def test_durability_risk_missing_column_raises(self):
        bad_df = pd.DataFrame({"season": [2020]})
        with pytest.raises(ValueError, match="experience_age_draft_df is missing required columns"):
            ft.build_durability_risk_traits(bad_df)


class TestRowCountPreserved:
    def test_volume_fragility_one_row_per_input_row(self):
        df = _depth_chart_traits_df(
            _row(2020, "00-1", "QB", "TEAM", 1, dct.DEPTH_CHART_STATUS_STARTER, False, 1, 1),
            _row(2020, "00-2", "RB", "TEAM", 1, dct.DEPTH_CHART_STATUS_STARTER, False, 1, 1),
        )
        out = ft.build_volume_fragility_traits(df)
        assert len(out) == 2
