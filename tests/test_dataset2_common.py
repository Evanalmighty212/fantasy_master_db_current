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
from lib.dataset2.common import (
    build_team_game_index,
    real_reg_week_slots,
    season_length,
    week1_kickoff_by_team,
)


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


def _schedule(rows):
    """rows: (season, week, gameday, home_team, away_team) -- REG game_type."""
    cols = ("season", "game_type", "week", "gameday", "home_team", "away_team")
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(
        [
            {"season": s, "game_type": "REG", "week": w, "gameday": g, "home_team": h, "away_team": a}
            for s, w, g, h, a in rows
        ]
    )


class TestHistoricalTeamCodeAliases:
    """Protects week1_kickoff_by_team()'s real, verified franchise-
    relocation alias resolution (Oakland->Las Vegas Raiders, St.
    Louis->Los Angeles Rams, San Diego->Los Angeles Chargers) -- added
    2026-07 after the real age (family #2) integration audit found 624
    historical predictor-table rows with a real players.csv birth_date
    match but no real Week-1 schedule match, and every one of them
    resolved to exactly these 3 real relocations (see
    research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md
    §11.7). This project's population always uses the CURRENT/
    canonical team code (LV/LA/LAC) for every historical season; the
    real nflverse schedule file uses whichever code was actually in
    use at the time (OAK/STL/SD pre-relocation)."""

    def test_relocation_case_resolves_to_historical_schedule_date(self):
        # Real 2015 pattern: population says "LA" (this project's
        # always-current convention) but the real 2015 schedule file
        # itself says "STL" (the Rams hadn't moved yet) -- must still
        # resolve to the real 2015 Week-1 kickoff date.
        sched = _schedule([(2015, 1, "2015-09-13", "STL", "SEA")])
        kickoff = week1_kickoff_by_team(sched, 2015)
        assert kickoff["LA"] == pd.Timestamp("2015-09-13")
        # The raw historical code itself must also still resolve (additive,
        # never a replacement).
        assert kickoff["STL"] == pd.Timestamp("2015-09-13")

    def test_all_three_verified_relocations_resolve(self):
        sched = _schedule(
            [
                (2019, 1, "2019-09-09", "OAK", "DEN"),  # Raiders, pre-move (moved 2020)
                (2015, 1, "2015-09-13", "STL", "SEA"),  # Rams, pre-move (moved 2016)
                (2016, 1, "2016-09-11", "SD", "KC"),  # Chargers, pre-move (moved 2017)
            ]
        )
        assert week1_kickoff_by_team(sched, 2019)["LV"] == pd.Timestamp("2019-09-09")
        assert week1_kickoff_by_team(sched, 2015)["LA"] == pd.Timestamp("2015-09-13")
        assert week1_kickoff_by_team(sched, 2016)["LAC"] == pd.Timestamp("2016-09-11")

    def test_post_relocation_season_needs_no_alias(self):
        # From the real, verified cutoff season onward, the real
        # schedule file itself already uses the current code directly
        # -- no aliasing needed, and none must be silently applied.
        sched = _schedule([(2020, 1, "2020-09-13", "LV", "CAR")])
        kickoff = week1_kickoff_by_team(sched, 2020)
        assert kickoff["LV"] == pd.Timestamp("2020-09-13")

    def test_alias_is_season_aware_not_applied_outside_its_real_range(self):
        # Real, found boundary: OAK's real alias range is 1999-2019
        # ONLY. A synthetic "OAK" row in season 2020 (never real --
        # the real 2020 schedule never has an "OAK" row at all) must
        # NOT be silently canonicalized to "LV" -- proves the alias
        # table is keyed by season, not just by code.
        sched = _schedule([(2020, 1, "2020-09-13", "OAK", "CAR")])
        kickoff = week1_kickoff_by_team(sched, 2020)
        assert "LV" not in kickoff
        assert kickoff["OAK"] == pd.Timestamp("2020-09-13")  # raw code itself still resolves

    def test_unverified_nonmatching_team_remains_absent_never_guessed(self):
        # Real, found case: MIA and TB's real Week-1 game in the 2017
        # season was postponed league-wide (Hurricane Irma) and never
        # replayed as a real Week 1 game -- there is no real Week-1
        # kickoff for either team that season. This is genuine missing
        # data, not a team-code mismatch, and must NEVER be guessed at
        # via the alias table (neither team is in it).
        sched = _schedule([(2017, 1, "2017-09-10", "KC", "NE")])  # some other real Week-1 game
        kickoff = week1_kickoff_by_team(sched, 2017)
        assert "MIA" not in kickoff
        assert "TB" not in kickoff

    def test_no_unrelated_team_season_changed(self):
        # A normal, non-relocated team's real kickoff must be entirely
        # unaffected by the alias machinery.
        sched = _schedule(
            [
                (2015, 1, "2015-09-13", "STL", "SEA"),
                (2015, 1, "2015-09-13", "KC", "HOU"),
            ]
        )
        kickoff = week1_kickoff_by_team(sched, 2015)
        assert kickoff["KC"] == pd.Timestamp("2015-09-13")
        assert kickoff["HOU"] == pd.Timestamp("2015-09-13")
        assert "SD" not in kickoff and "LAC" not in kickoff  # no cross-alias leakage

    def test_deterministic_across_repeated_calls(self):
        sched = _schedule(
            [
                (2015, 1, "2015-09-13", "STL", "SEA"),
                (2016, 1, "2016-09-11", "SD", "KC"),
                (2019, 1, "2019-09-09", "OAK", "DEN"),
            ]
        )
        first = {s: week1_kickoff_by_team(sched, s) for s in (2015, 2016, 2019)}
        second = {s: week1_kickoff_by_team(sched, s) for s in (2015, 2016, 2019)}
        assert first == second
