"""
tests/test_download_stats.py

Covers the season-aggregation logic in scripts/03_download_stats.py.
The module is a numbered file (invalid Python identifier), so it's
loaded via importlib rather than a normal import.

Both non-trivial tests here are regression tests for REAL bugs found
while building the weekly-data export (see docs/METRIC_SPECIFICATION.md
and the module's own docstring, fixes #7): the "played" definition
originally missed special-teams-TD-only weeks, and nflverse's raw data
occasionally has duplicate rows for one player-week.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# nflverse_source must be importable (by name, for unittest.mock.patch's
# string target below) before 03_download_stats.py is loaded and adds
# scripts/ to sys.path itself.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "03_download_stats.py"


def load_module(tmp_path, monkeypatch):
    """Load 03_download_stats.py fresh, with RAW_DIR redirected to a
    temp directory so tests never touch the real data/ folder."""
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("download_stats", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["download_stats"] = mod
    spec.loader.exec_module(mod)
    return mod


def make_weekly_row(season, week, player_id, name, position, team,
                     attempts=0, carries=0, targets=0, points=0.0):
    return {
        "season": season, "week": week, "player_id": player_id,
        "player_display_name": name, "position": position,
        "recent_team": team, "season_type": "REG",
        "attempts": attempts, "carries": carries, "targets": targets,
        "fantasy_points_ppr": points,
    }


class TestPlayedDefinition:
    def test_special_teams_td_week_counts_as_played(self, tmp_path, monkeypatch):
        # Regression test for the Jeremy Ross 2013 week-14 case: zero
        # offensive touches, but real points from a return TD. That
        # week must count toward games_played.
        rows = [
            make_weekly_row(2013, 1, "00-X", "Test Returner", "RB", "AAA",
                             attempts=0, carries=5, targets=1, points=8.0),
            make_weekly_row(2013, 14, "00-X", "Test Returner", "RB", "AAA",
                             attempts=0, carries=0, targets=0, points=12.0),  # return TD week
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2013]
            season = mod.build_season_results()

        row = season[season.player_id == "00-X"].iloc[0]
        assert row["games_played"] == 2, (
            "Special-teams-TD-only week was excluded from games_played -- "
            "the exact bug found with Jeremy Ross's 2013 season."
        )
        assert row["fantasy_points_ppr"] == 20.0

    def test_bye_week_row_does_not_count_as_played(self, tmp_path, monkeypatch):
        rows = [
            make_weekly_row(2020, 1, "00-Y", "Test Player", "WR", "BBB",
                             attempts=0, carries=0, targets=5, points=10.0),
            make_weekly_row(2020, 2, "00-Y", "Test Player", "WR", "BBB",
                             attempts=0, carries=0, targets=0, points=0.0),  # bye/inactive
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2020]
            season = mod.build_season_results()

        row = season[season.player_id == "00-Y"].iloc[0]
        assert row["games_played"] == 1


class TestDuplicateWeekHandling:
    def test_duplicate_week_rows_are_summed_not_double_counted(self, tmp_path, monkeypatch):
        # Regression test for the Matthew Stafford 2010 week-8 case:
        # nflverse's own raw data had two rows for one player-week.
        rows = [
            make_weekly_row(2010, 1, "00-Z", "Test QB", "QB", "CCC",
                             attempts=30, points=15.0),
            make_weekly_row(2010, 8, "00-Z", "Test QB", "QB", "CCC",
                             attempts=40, points=20.0),
            make_weekly_row(2010, 8, "00-Z", "Test QB", "QB", "CCC",  # duplicate!
                             attempts=0, carries=0, targets=0, points=2.0),
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2010]
            season = mod.build_season_results()

        row = season[season.player_id == "00-Z"].iloc[0]
        # games_played must be 2 (weeks 1 and 8), NOT 3 -- the duplicate
        # week-8 row must not inflate the game count.
        assert row["games_played"] == 2
        assert row["fantasy_points_ppr"] == 37.0  # 15 + 20 + 2, not double-counted


class TestTeamHandlingDoesNotFragmentSeason:
    def test_traded_player_gets_one_row_not_two(self, tmp_path, monkeypatch):
        # Regression test for the original Priority 1 bug: recent_team
        # in the grouping key split traded players into multiple rows.
        rows = [
            make_weekly_row(2019, w, "00-T", "Traded Player", "RB", "TEAMA",
                             carries=10, points=8.0)
            for w in range(1, 5)
        ] + [
            make_weekly_row(2019, w, "00-T", "Traded Player", "RB", "TEAMB",
                             carries=10, points=8.0)
            for w in range(5, 9)
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2019]
            season = mod.build_season_results()

        matching = season[season.player_id == "00-T"]
        assert len(matching) == 1, "Traded player split into multiple rows"
        assert matching.iloc[0]["games_played"] == 8
        assert matching.iloc[0]["teams_all"] == "TEAMA,TEAMB"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
