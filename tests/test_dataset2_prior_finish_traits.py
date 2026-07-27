"""
tests/test_dataset2_prior_finish_traits.py

Covers lib/dataset2/prior_finish_traits.py -- Dataset 2 family #7's
FEATURE CONSTRUCTION only (prior_overall_finish, prior_positional_finish,
prior_ppg). Deliberately does not test any Star-rate/ADP-conditioning
logic -- that lives in lib/dataset2/prior_finish_analysis.py and its
own test file, kept structurally separate per the approved design.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import prior_finish_traits as pft


def _population_df(*rows):
    cols = ["season", "player_id", "position", "overall_finish_ppr", "position_finish_ppr", "ppg_ppr"]
    return pd.DataFrame(list(rows), columns=cols)


class TestPriorFinishLags:
    def test_all_three_fields_lag_correctly(self):
        pop = _population_df(
            {"season": 2021, "player_id": "00-1", "position": "WR", "overall_finish_ppr": 22, "position_finish_ppr": 8, "ppg_ppr": 14.5},
            {"season": 2022, "player_id": "00-1", "position": "WR", "overall_finish_ppr": 15, "position_finish_ppr": 5, "ppg_ppr": 16.0},
        )
        out = pft.build_prior_finish_traits(pop)
        row_2022 = out[out["season"] == 2022].iloc[0]
        assert row_2022["prior_overall_finish"] == 22
        assert row_2022["prior_positional_finish"] == 8
        assert row_2022["prior_ppg"] == pytest.approx(14.5)

    def test_rookie_is_null_not_zero_or_worst_rank(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "WR", "overall_finish_ppr": 15, "position_finish_ppr": 5, "ppg_ppr": 16.0},
        )
        out = pft.build_prior_finish_traits(pop)
        assert pd.isna(out.loc[0, "prior_overall_finish"])
        assert pd.isna(out.loc[0, "prior_positional_finish"])
        assert pd.isna(out.loc[0, "prior_ppg"])


class TestRequiredColumnValidation:
    def test_missing_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2022], "player_id": ["00-1"]})
        with pytest.raises(ValueError, match="population is missing required columns"):
            pft.build_prior_finish_traits(bad_pop)


class TestRowCountPreserved:
    def test_one_row_per_season_player(self):
        pop = _population_df(
            {"season": 2021, "player_id": "00-1", "position": "WR", "overall_finish_ppr": 22, "position_finish_ppr": 8, "ppg_ppr": 14.5},
            {"season": 2022, "player_id": "00-1", "position": "WR", "overall_finish_ppr": 15, "position_finish_ppr": 5, "ppg_ppr": 16.0},
            {"season": 2022, "player_id": "00-2", "position": "RB", "overall_finish_ppr": 40, "position_finish_ppr": 20, "ppg_ppr": 9.0},
        )
        out = pft.build_prior_finish_traits(pop)
        assert len(out) == 3
