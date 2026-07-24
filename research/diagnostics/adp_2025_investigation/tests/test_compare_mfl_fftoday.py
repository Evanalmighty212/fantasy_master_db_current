"""
tests/test_compare_mfl_fftoday.py

Regression test for a real bug found during the 2025 ADP investigation:
merging MFL's reconstructed ADP against FFToday's 2025 consensus, before
restricting both sides to real QB/RB/WR/TE rows, let FFToday's team-defense
rows collide with MFL's duplicate franchise-level rows (MFL's player table
carries up to 6 rows per NFL team under labels like "Def"/"TMPK"/"ST"/"Off"/
"Coach"/"PN", all sharing one team name) and inflated the reported overlap
from a correct 228 to an inconsistent 348. This test locks in the fix
(filter_to_skill_positions before merging) with a synthetic fixture that
reproduces the exact collision, so it cannot silently recur.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from compare_mfl_fftoday import filter_to_skill_positions, merge_mfl_fftoday, summarize


def _mfl_fixture():
    """One real QB plus MFL's realistic team-level duplicate rows for a
    single franchise (the exact shape that caused the original bug)."""
    return pd.DataFrame([
        {"player_norm": "josh allen", "position": "QB", "mean_adp": 20.0},
        {"player_norm": "denver broncos", "position": "Def", "mean_adp": 100.0},
        {"player_norm": "denver broncos", "position": "TMPK", "mean_adp": 101.0},
        {"player_norm": "denver broncos", "position": "ST", "mean_adp": 102.0},
        {"player_norm": "denver broncos", "position": "Off", "mean_adp": 103.0},
        {"player_norm": "denver broncos", "position": "Coach", "mean_adp": 104.0},
        {"player_norm": "denver broncos", "position": "PN", "mean_adp": 105.0},
    ])


def _fftoday_fixture():
    """One real QB plus one FFToday DEF row for the same team name."""
    return pd.DataFrame([
        {"player_norm": "josh allen", "position": "QB",
         "sleeper_rank": 20, "rtsports_rank": 25, "fftoday_espn_rank": 19, "avg_rank": 21.3},
        {"player_norm": "denver broncos", "position": "DEF",
         "sleeper_rank": 107, "rtsports_rank": 127, "fftoday_espn_rank": 96, "avg_rank": 110.0},
    ])


class TestTeamLevelRowContamination:
    def test_filter_removes_mfl_team_level_duplicates(self):
        mfl = _mfl_fixture()
        filtered = filter_to_skill_positions(mfl, "position")
        assert len(filtered) == 1
        assert filtered.iloc[0]["player_norm"] == "josh allen"

    def test_filter_removes_fftoday_def_rows(self):
        fft = _fftoday_fixture()
        filtered = filter_to_skill_positions(fft, "position")
        assert len(filtered) == 1
        assert filtered.iloc[0]["player_norm"] == "josh allen"

    def test_merge_without_filtering_reproduces_the_original_bug(self):
        """Documents the failure mode directly: merging RAW (unfiltered)
        inputs lets one FFToday DEF row match all 6 MFL team-level
        duplicates, inflating a 1-real-player overlap to 7 rows."""
        mfl_raw = _mfl_fixture()
        fft_raw = _fftoday_fixture()
        contaminated = mfl_raw.merge(
            fft_raw[["player_norm", "sleeper_rank", "rtsports_rank", "fftoday_espn_rank", "avg_rank"]],
            on="player_norm", how="inner",
        )
        assert len(contaminated) == 7  # 1 real match + 6 team-level duplicates
        assert len(contaminated) != 1  # the real, correct answer

    def test_merge_with_filtering_excludes_team_level_rows(self):
        """The fix: filtering both sides to skill positions before merging
        leaves only the real player match."""
        mfl_skill = filter_to_skill_positions(_mfl_fixture(), "position")
        fft_skill = filter_to_skill_positions(_fftoday_fixture(), "position")
        merged = merge_mfl_fftoday(mfl_skill, fft_skill)
        assert len(merged) == 1
        assert merged.iloc[0]["player_norm"] == "josh allen"

    def test_summarize_raises_if_position_breakdown_is_inconsistent(self):
        """summarize() asserts position-level counts sum to the total --
        this is the exact consistency check that caught the original bug
        (348 total vs. 228 summed by position). A contaminated merge must
        fail loudly here, not print a plausible-looking wrong number."""
        mfl_raw = _mfl_fixture()
        fft_raw = _fftoday_fixture().rename(columns={"position": "position_fft"})
        contaminated = mfl_raw.merge(
            fft_raw[["player_norm", "sleeper_rank", "rtsports_rank", "fftoday_espn_rank", "avg_rank", "position_fft"]],
            on="player_norm", how="inner",
        )
        with pytest.raises(AssertionError, match="does not match total overlap"):
            summarize(contaminated)

    def test_clean_merge_passes_summarize_consistency_check(self):
        mfl_skill = filter_to_skill_positions(_mfl_fixture(), "position")
        fft_skill = filter_to_skill_positions(_fftoday_fixture(), "position")
        merged = merge_mfl_fftoday(mfl_skill, fft_skill)
        summarize(merged)  # must not raise
