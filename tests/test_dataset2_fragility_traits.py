"""
tests/test_dataset2_fragility_traits.py

Covers lib/dataset2/fragility_traits.py -- Dataset 2 families #86
(split, part) and #88 (split, part). Protects:

- committee_uncertainty fires ONLY when the real observed
  starter_group_size exceeds the position's fixed structural
  expectation (a real RB/TE committee), and never fires for WR's
  routine 3-wide starting group (which matches its own structural
  expectation exactly).
- team_qb_uncertainty is broadcast to every skill-position player on a
  team with a tied-starter QB situation, null (not False) when no real
  depth-chart data exists for that team.
- body_size_position_z uses the same within-group z-score pattern
  already approved for families #1/#2.
- workload_qualified is always the literal "pending" string, never a
  fabricated True/False -- family #88's workload-gated portion remains
  deferred, per the same pattern approved for family #9.
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


class TestCommitteeUncertainty:
    def test_fires_for_real_rb_committee(self):
        df = _depth_chart_traits_df(
            {"season": 2020, "player_id": "00-white", "position": "RB", "depth_chart_team": "NE",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": True, "starter_group_size": 2, "position_starter_count": 1,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
        )
        out = ft.build_volume_fragility_traits(df)
        assert out.loc[0, "committee_uncertainty"] == 1.0

    def test_never_fires_for_normal_wr_three_wide_group(self):
        df = _depth_chart_traits_df(
            {"season": 2020, "player_id": "00-ridley", "position": "WR", "depth_chart_team": "ATL",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": True, "starter_group_size": 3, "position_starter_count": 3,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
        )
        out = ft.build_volume_fragility_traits(df)
        assert out.loc[0, "committee_uncertainty"] == 0.0

    def test_clean_single_starter_not_flagged(self):
        df = _depth_chart_traits_df(
            {"season": 2020, "player_id": "00-1", "position": "RB", "depth_chart_team": "ATL",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": False, "starter_group_size": 1, "position_starter_count": 1,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
        )
        out = ft.build_volume_fragility_traits(df)
        assert out.loc[0, "committee_uncertainty"] == 0.0

    def test_null_when_no_depth_chart_data(self):
        df = _depth_chart_traits_df(
            {"season": 2020, "player_id": "00-1", "position": "RB", "depth_chart_team": None,
             "depth_chart_native_rank": None, "depth_chart_status": None,
             "depth_rank_tied": None, "starter_group_size": None, "position_starter_count": None,
             "depth_chart_schema_era": None},
        )
        out = ft.build_volume_fragility_traits(df)
        assert pd.isna(out.loc[0, "committee_uncertainty"])


class TestTeamQbUncertainty:
    def test_broadcast_to_every_skill_player_on_tied_qb_team(self):
        df = _depth_chart_traits_df(
            {"season": 2020, "player_id": "00-qb1", "position": "QB", "depth_chart_team": "TEAM",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": True, "starter_group_size": 2, "position_starter_count": 1,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
            {"season": 2020, "player_id": "00-qb2", "position": "QB", "depth_chart_team": "TEAM",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": True, "starter_group_size": 2, "position_starter_count": 1,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
            {"season": 2020, "player_id": "00-wr1", "position": "WR", "depth_chart_team": "TEAM",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": True, "starter_group_size": 3, "position_starter_count": 3,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
        )
        out = ft.build_volume_fragility_traits(df)
        assert (out["team_qb_uncertainty"] == 1.0).all()  # every player on TEAM, including the WR

    def test_clean_qb_team_flagged_false_not_null(self):
        df = _depth_chart_traits_df(
            {"season": 2020, "player_id": "00-qb1", "position": "QB", "depth_chart_team": "TEAM",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": False, "starter_group_size": 1, "position_starter_count": 1,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
            {"season": 2020, "player_id": "00-wr1", "position": "WR", "depth_chart_team": "TEAM",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": True, "starter_group_size": 3, "position_starter_count": 3,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
        )
        out = ft.build_volume_fragility_traits(df)
        assert (out["team_qb_uncertainty"] == 0.0).all()

    def test_null_when_no_team_data_not_false(self):
        df = _depth_chart_traits_df(
            {"season": 2020, "player_id": "00-1", "position": "WR", "depth_chart_team": None,
             "depth_chart_native_rank": None, "depth_chart_status": None,
             "depth_rank_tied": None, "starter_group_size": None, "position_starter_count": None,
             "depth_chart_schema_era": None},
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
        # mean=26, std=2 -> z-scores -1, 0, 1
        z = out.set_index("player_id")["body_size_position_z"]
        assert z["00-1"] == pytest.approx(-1.0)
        assert z["00-2"] == pytest.approx(0.0)
        assert z["00-3"] == pytest.approx(1.0)

    def test_single_row_group_is_null_not_a_crash(self):
        df = _age_draft_df({"season": 2020, "player_id": "00-1", "position": "QB", "body_size_bmi": 27.0})
        out = ft.build_durability_risk_traits(df)
        assert pd.isna(out.loc[0, "body_size_position_z"])


class TestWorkloadQualifiedAlwaysPending:
    def test_always_pending_literal(self):
        df = _age_draft_df(
            {"season": 2020, "player_id": "00-1", "position": "WR", "body_size_bmi": 24.0},
            {"season": 2020, "player_id": "00-2", "position": "RB", "body_size_bmi": 26.0},
        )
        out = ft.build_durability_risk_traits(df)
        assert set(out["workload_qualified"].unique()) == {"pending"}


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
            {"season": 2020, "player_id": "00-1", "position": "QB", "depth_chart_team": "TEAM",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": False, "starter_group_size": 1, "position_starter_count": 1,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
            {"season": 2020, "player_id": "00-2", "position": "RB", "depth_chart_team": "TEAM",
             "depth_chart_native_rank": 1, "depth_chart_status": dct.DEPTH_CHART_STATUS_STARTER,
             "depth_rank_tied": False, "starter_group_size": 1, "position_starter_count": 1,
             "depth_chart_schema_era": dct.SCHEMA_ERA_HISTORICAL},
        )
        out = ft.build_volume_fragility_traits(df)
        assert len(out) == 2
