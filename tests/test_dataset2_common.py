"""
tests/test_dataset2_common.py

Protects lib/dataset2/common.py's shared helpers -- created 2026-07
specifically to regression-test the real week-boundary bug found in
lib/dataset2/partial_season_traits.py (see
research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md §0):
`season_length()` returns real GAMES PLAYED (16 or 17), not the real
maximum REG week NUMBER, which is one higher because every team's real
bye week consumes a week-number slot without a played game.
`real_reg_week_slots()` and `build_team_game_index()` are the shared,
canonical way every Dataset 2 module must now derive week-boundary or
team-game-sequence logic -- this file is the one place their own
correctness is proven, so every consuming module can rely on it
without re-deriving it.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.common import build_team_game_index, real_reg_week_slots, season_length


class TestRealRegWeekSlots:
    def test_16_game_season_real_week_slots_is_17(self):
        # Real 2015 (pre-ERA_CUTOFF, season_length==16): real REG weeks
        # run 1-17 (verified directly against real stats_player_week_2015.csv).
        assert season_length(2015) == 16
        assert real_reg_week_slots(2015) == 17

    def test_17_game_season_real_week_slots_is_18(self):
        # Real 2021 (post-ERA_CUTOFF, season_length==17): real REG weeks
        # run 1-18 (verified directly against real stats_player_week_2021.csv).
        assert season_length(2021) == 17
        assert real_reg_week_slots(2021) == 18

    def test_postseason_exclusion_boundary_16_game_era(self):
        # Real week 17 is the final real REG week for a 16-game-era
        # season -- must NOT be classified postseason.
        assert 17 <= real_reg_week_slots(2015)
        # Real week 18 does not exist for a 16-game-era season at all;
        # if it appeared, it would correctly be beyond the real REG
        # boundary -- this is the exact rule participation_traits.py's
        # _is_postseason() applies via this same shared helper.
        assert 18 > real_reg_week_slots(2015)

    def test_postseason_exclusion_boundary_17_game_era(self):
        assert 18 <= real_reg_week_slots(2021)
        assert 19 > real_reg_week_slots(2021)


class TestBuildTeamGameIndex:
    def _weekly(self, rows):
        return pd.DataFrame(rows)

    def test_contiguous_weeks_get_sequential_index(self):
        w = self._weekly(
            [
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 2, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 3, "team": "KC", "season_type": "REG"},
            ]
        )
        out = build_team_game_index(w)
        assert out["team_game_index"].tolist() == [1, 2, 3]
        assert (out["team_total_games"] == 3).all()

    def test_bye_week_gap_is_compressed_out(self):
        # Real 2015 New England pattern: week 4 is the real bye --
        # absent from the raw data entirely, not a zero-row placeholder.
        w = self._weekly(
            [{"season": 2015, "week": wk, "team": "NE", "season_type": "REG"} for wk in [1, 2, 3, 5, 6]]
        )
        out = build_team_game_index(w)
        assert out.set_index("week")["team_game_index"].to_dict() == {1: 1, 2: 2, 3: 3, 5: 4, 6: 5}
        assert (out["team_total_games"] == 5).all()

    def test_real_16_game_season_produces_16_team_games(self):
        # A full real 16-game-era team-season: 17 real week slots minus
        # 1 real bye = 16 real games, verified directly earlier against
        # real 2015 data (every real team-season showed exactly 16 or
        # 17 distinct weeks, matching season_length exactly).
        weeks = [wk for wk in range(1, 18) if wk != 9]  # bye at week 9
        w = self._weekly([{"season": 2015, "week": wk, "team": "DAL", "season_type": "REG"} for wk in weeks])
        out = build_team_game_index(w)
        assert out["team_total_games"].iloc[0] == 16

    def test_postseason_rows_excluded(self):
        w = self._weekly(
            [
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 2, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 19, "team": "KC", "season_type": "POST"},
            ]
        )
        out = build_team_game_index(w)
        assert len(out) == 2
        assert out["team_total_games"].iloc[0] == 2

    def test_multiple_teams_independently_indexed(self):
        w = self._weekly(
            [
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 1, "team": "SF", "season_type": "REG"},
                {"season": 2023, "week": 2, "team": "KC", "season_type": "REG"},
            ]
        )
        out = build_team_game_index(w)
        kc = out[out["team"] == "KC"]
        sf = out[out["team"] == "SF"]
        assert kc["team_game_index"].tolist() == [1, 2]
        assert sf["team_game_index"].tolist() == [1]
        assert sf["team_total_games"].iloc[0] == 1

    def test_duplicate_player_rows_same_team_week_do_not_duplicate_game_index_rows(self):
        # Many real players share a (season, team, week) -- the team-game
        # index is over DISTINCT team-weeks, not one row per player.
        w = self._weekly(
            [
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
            ]
        )
        out = build_team_game_index(w)
        assert len(out) == 1

    def test_missing_required_column_raises(self):
        w = pd.DataFrame([{"season": 2023, "week": 1, "team": "KC"}])
        with pytest.raises(ValueError, match="missing required columns"):
            build_team_game_index(w)
