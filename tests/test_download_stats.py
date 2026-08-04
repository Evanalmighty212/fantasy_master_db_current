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


class TestTradedPlayerExtraGameSeason:
    """Regression coverage for Rashid Shaheed's verified 2025 case:
    changing teams and avoiding both club byes can produce 18 real
    involvement weeks even though each club plays only 17 games."""

    def test_18_distinct_regular_season_weeks_are_preserved(self, tmp_path, monkeypatch):
        rows = [
            make_weekly_row(
                2025,
                week,
                "00-SHAHEED",
                "Traded Player",
                "WR",
                "NO" if week <= 9 else "SEA",
                targets=1,
                points=10.0,
            )
            for week in range(1, 19)
        ]

        with patch("nflverse_source.fetch_and_normalize", return_value=pd.DataFrame(rows)):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        row = season.loc[season["player_id"] == "00-SHAHEED"].iloc[0]
        assert row["games_played"] == 18
        assert row["ppg_ppr"] == 10.0
        assert row["teams_all"] == "NO,SEA"

        weekly = pd.read_csv(tmp_path / "data/raw/nflverse/weekly_results_ppr_2025_2025.csv")
        assert len(weekly) == 18
        assert not weekly.duplicated(["season", "player_id", "week"]).any()
        assert weekly["week"].tolist() == list(range(1, 19))

    def test_2021_plus_week_19_fails_loudly(self, tmp_path, monkeypatch):
        rows = [make_weekly_row(2025, 19, "00-X", "Postseason Leak", "WR", "NO", targets=1)]
        with patch("nflverse_source.fetch_and_normalize", return_value=pd.DataFrame(rows)):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            with pytest.raises(ValueError, match="1-18 from 2021 onward"):
                mod.build_season_results()

    def test_non_reg_row_fails_loudly(self, tmp_path, monkeypatch):
        row = make_weekly_row(2025, 18, "00-X", "Postseason Leak", "WR", "NO", targets=1)
        row["season_type"] = "POST"
        with patch("nflverse_source.fetch_and_normalize", return_value=pd.DataFrame([row])):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            with pytest.raises(ValueError, match="contains non-REG rows"):
                mod.build_season_results()

    def test_duplicate_player_week_after_aggregation_fails_loudly(self, tmp_path, monkeypatch):
        mod = load_module(tmp_path, monkeypatch)
        duplicate = pd.DataFrame(
            [
                {"season": 2025, "player_id": "00-X", "week": 1},
                {"season": 2025, "player_id": "00-X", "week": 1},
            ]
        )
        with pytest.raises(ValueError, match="duplicate .* keys after aggregation"):
            mod.validate_weekly_player_output(duplicate)


def _write_position_overrides(tmp_path, *rows):
    """Writes data/manual/position_overrides.csv inside tmp_path (the
    redirected RAW_DIR-adjacent cwd from load_module) -- load_module's
    monkeypatch.chdir means load_position_overrides() looks for this
    file relative to tmp_path, not the real repo file. Rows: dicts with
    player_id, season ('' for all seasons), correct_position, notes."""
    path = tmp_path / "data" / "manual" / "position_overrides.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list(rows), columns=["player_id", "season", "correct_position", "notes"]).to_csv(path, index=False)


class TestPositionOverrideRescuesNonSkillTaggedPlayer:
    """Fix #10 (2026-07, Travis Hunter data-quality gap): a player whose
    LISTED position is entirely outside SKILL_POSITIONS (not a
    within-skill TE-vs-WR mislabel like Matthews/Funchess) was
    previously dropped by Step 2 before Step 5b's override mechanism
    ever ran. These tests prove the fix rescues an explicitly
    overridden player while leaving every other non-skill-tagged
    player -- including OTHER CBs, FBs, and defensive scorers with no
    override entry -- excluded exactly as before."""

    def test_travis_hunter_real_case_included_with_real_production(self, tmp_path, monkeypatch):
        """Real gsis_id and real 2025 weekly totals (7 weeks, 46
        touches, up to 24.1 PPR points in week 7), confirmed directly
        against data/raw/nflverse/annual/stats_player_week_2025.csv
        during the 2026-07 audit -- not synthetic numbers."""
        _write_position_overrides(tmp_path, {
            "player_id": "00-0040718", "season": "", "correct_position": "WR",
            "notes": "Travis Hunter -- see data/manual/position_overrides.csv",
        })
        rows = [
            make_weekly_row(2025, 1, "00-0040718", "Travis Hunter", "CB", "JAX", targets=8, points=9.3),
            make_weekly_row(2025, 2, "00-0040718", "Travis Hunter", "CB", "JAX", targets=6, points=5.2),
            make_weekly_row(2025, 3, "00-0040718", "Travis Hunter", "CB", "JAX", targets=2, points=3.1),
            make_weekly_row(2025, 4, "00-0040718", "Travis Hunter", "CB", "JAX", targets=5, points=7.2),
            make_weekly_row(2025, 5, "00-0040718", "Travis Hunter", "CB", "JAX", targets=3, points=9.4),
            make_weekly_row(2025, 6, "00-0040718", "Travis Hunter", "CB", "JAX", targets=7, points=5.5),
            make_weekly_row(2025, 7, "00-0040718", "Travis Hunter", "CB", "JAX", targets=14, points=24.1),
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        matching = season[season.player_id == "00-0040718"]
        assert len(matching) == 1, "Travis Hunter was excluded -- fix #10 regression"
        row = matching.iloc[0]
        assert row["position"] == "WR"
        assert row["games_played"] == 7
        assert row["fantasy_points_ppr"] == pytest.approx(63.8, abs=0.05)

    def test_ordinary_cb_without_override_stays_excluded(self, tmp_path, monkeypatch):
        """The narrow-rescue guarantee: a DIFFERENT CB with real
        offensive involvement but NO position_overrides.csv entry must
        NOT be rescued -- proves the fix does not broaden the eligible
        population to all CBs. A real skill-position companion row is
        included alongside it, matching how real weekly data always
        contains a mix of positions (an all-excluded population is not
        a realistic scenario this pipeline needs to handle)."""
        _write_position_overrides(tmp_path, {
            "player_id": "00-0040718", "season": "", "correct_position": "WR", "notes": "Travis Hunter",
        })
        rows = [
            make_weekly_row(2025, 1, "00-OTHER-CB", "Some Other CB", "CB", "AAA", targets=3, points=4.0),
            make_weekly_row(2025, 2, "00-OTHER-CB", "Some Other CB", "CB", "AAA", targets=2, points=2.5),
            make_weekly_row(2025, 1, "00-REAL-WR", "Real Skill Player", "WR", "AAA", targets=5, points=8.0),
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        assert len(season[season.player_id == "00-OTHER-CB"]) == 0, (
            "An ordinary CB with no override entry was rescued -- the fix "
            "must not broaden the eligible population beyond explicit overrides."
        )
        assert len(season[season.player_id == "00-REAL-WR"]) == 1

    def test_fb_without_override_stays_excluded(self, tmp_path, monkeypatch):
        """Fullbacks remain out of v1.0 scope -- the fix must not
        sweep in FB just because it now runs pre-filter."""
        rows = [
            make_weekly_row(2025, 1, "00-SOME-FB", "Some Fullback", "FB", "BBB", carries=3, points=6.0),
            make_weekly_row(2025, 1, "00-REAL-WR2", "Real Skill Player", "WR", "BBB", targets=5, points=8.0),
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        assert len(season[season.player_id == "00-SOME-FB"]) == 0
        assert len(season[season.player_id == "00-REAL-WR2"]) == 1

    def test_defensive_scorer_with_incidental_points_stays_excluded(self, tmp_path, monkeypatch):
        """A defensive player who scores fantasy points via a
        pick-six/fumble return (real fantasy_points_ppr, zero
        offensive touches) must not be rescued just because the
        override mechanism now runs earlier."""
        rows = [
            make_weekly_row(2025, 3, "00-DEF-SCORE", "Some Defender", "CB", "CCC",
                             attempts=0, carries=0, targets=0, points=6.0),
            make_weekly_row(2025, 1, "00-REAL-WR3", "Real Skill Player", "WR", "CCC", targets=5, points=8.0),
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        assert len(season[season.player_id == "00-DEF-SCORE"]) == 0
        assert len(season[season.player_id == "00-REAL-WR3"]) == 1

    def test_only_explicitly_listed_player_ids_are_rescued_mixed_population(self, tmp_path, monkeypatch):
        """A combined population check: override present for one
        player only, several other non-skill-tagged players present --
        exactly one is rescued, matching the override table exactly,
        not a pattern/heuristic."""
        _write_position_overrides(tmp_path, {
            "player_id": "00-RESCUED", "season": "", "correct_position": "WR", "notes": "test override",
        })
        rows = [
            make_weekly_row(2025, 1, "00-RESCUED", "Rescued Player", "CB", "AAA", targets=5, points=8.0),
            make_weekly_row(2025, 1, "00-NOT-RESCUED-1", "Not Rescued FB", "FB", "BBB", carries=2, points=3.0),
            make_weekly_row(2025, 1, "00-NOT-RESCUED-2", "Not Rescued CB", "CB", "CCC", targets=1, points=1.5),
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        assert set(season["player_id"]) == {"00-RESCUED"}
        assert season[season.player_id == "00-RESCUED"].iloc[0]["position"] == "WR"

    def test_within_skill_position_override_still_works_unchanged(self, tmp_path, monkeypatch):
        """Regression guard: the pre-existing Matthews/Funchess-style
        case (already skill-tagged, e.g. TE-vs-WR) must still work
        exactly as before -- fix #10 adds a rescue path, it doesn't
        change the existing within-skill override behavior."""
        _write_position_overrides(tmp_path, {
            "player_id": "00-TWEENER", "season": "", "correct_position": "WR", "notes": "test tweener",
        })
        rows = [
            make_weekly_row(2025, 1, "00-TWEENER", "Tweener Player", "TE", "DDD", targets=6, points=10.0),
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        matching = season[season.player_id == "00-TWEENER"]
        assert len(matching) == 1
        assert matching.iloc[0]["position"] == "WR"


class TestPositionOverrideIsIdempotent:
    """apply_position_overrides() now runs twice in the real pipeline
    (Step 1b on weekly rows, Step 5b on season rows) -- these tests
    prove that's safe: applying the SAME override table a second time
    to already-corrected data is a true no-op, never a second
    transformation. Checked both as a direct function-level property
    and end-to-end through the real Step 1b + Step 5b ordering."""

    def test_apply_position_overrides_is_idempotent_directly(self):
        """apply_position_overrides(df) and
        apply_position_overrides(apply_position_overrides(df)) must be
        identical -- a second application changes nothing."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("download_stats_idem", SCRIPT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        overrides = pd.DataFrame([
            {"player_id": "00-0040718", "season": "", "correct_position": "WR", "notes": "Travis Hunter"},
        ])
        base = pd.DataFrame([
            {"season": 2025, "player_id": "00-0040718", "position": "CB", "fantasy_points_ppr": 63.8},
            {"season": 2025, "player_id": "00-OTHER", "position": "RB", "fantasy_points_ppr": 10.0},
        ])

        once = mod.apply_position_overrides(base.copy(), overrides)
        twice = mod.apply_position_overrides(once.copy(), overrides)

        pd.testing.assert_frame_equal(once.reset_index(drop=True), twice.reset_index(drop=True))

    def test_travis_hunter_unchanged_by_a_forced_third_application(self, tmp_path, monkeypatch):
        """End-to-end through the real Step 1b + Step 5b pipeline,
        then a MANUALLY forced third apply_position_overrides() call on
        the final season output -- proves he's not "transformed twice"
        by the new ordering, and a hypothetical extra pass changes
        nothing further."""
        _write_position_overrides(tmp_path, {
            "player_id": "00-0040718", "season": "", "correct_position": "WR", "notes": "Travis Hunter",
        })
        rows = [
            make_weekly_row(2025, w, "00-0040718", "Travis Hunter", "CB", "JAX", targets=t, points=p)
            for w, t, p in [(1, 8, 9.3), (2, 6, 5.2), (3, 2, 3.1), (4, 5, 7.2), (5, 3, 9.4), (6, 7, 5.5), (7, 14, 24.1)]
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        row = season[season.player_id == "00-0040718"].iloc[0]
        assert row["position"] == "WR"
        assert row["fantasy_points_ppr"] == pytest.approx(63.8, abs=0.05)

        overrides = mod.load_position_overrides()
        season_again = mod.apply_position_overrides(season.copy(), overrides)
        pd.testing.assert_frame_equal(season.reset_index(drop=True), season_again.reset_index(drop=True))

    def test_matthews_funchess_style_override_unchanged_by_second_pass(self, tmp_path, monkeypatch):
        """Same idempotency guarantee for the pre-existing
        within-skill-position case (already TE-vs-WR, no Step 1b
        rescue needed, but Step 5b + a forced extra pass must still be
        a no-op)."""
        _write_position_overrides(tmp_path, {
            "player_id": "00-TWEENER", "season": "", "correct_position": "WR", "notes": "test tweener",
        })
        rows = [
            make_weekly_row(2025, 1, "00-TWEENER", "Tweener Player", "TE", "DDD", targets=6, points=10.0),
        ]
        weekly_df = pd.DataFrame(rows)

        with patch("nflverse_source.fetch_and_normalize", return_value=weekly_df):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = [2025]
            season = mod.build_season_results()

        assert season[season.player_id == "00-TWEENER"].iloc[0]["position"] == "WR"

        overrides = mod.load_position_overrides()
        season_again = mod.apply_position_overrides(season.copy(), overrides)
        pd.testing.assert_frame_equal(season.reset_index(drop=True), season_again.reset_index(drop=True))


class TestNKealHarrySeasonSpecificOverride:
    """Protects Evan's narrowly approved Harry scope: WR in exactly
    2019-2022, keyed by player identity and applied before positional
    finish ranks are constructed. It must not become a career-wide or
    name-based correction."""

    HARRY_ID = "00-0035624"
    APPROVED_SEASONS = {2019, 2020, 2021, 2022}

    @staticmethod
    def _harry_override_rows():
        return [
            {
                "player_id": TestNKealHarrySeasonSpecificOverride.HARRY_ID,
                "season": str(season),
                "correct_position": "WR",
                "notes": "approved narrow Harry test fixture",
            }
            for season in sorted(TestNKealHarrySeasonSpecificOverride.APPROVED_SEASONS)
        ]

    def test_committed_override_scope_is_exactly_2019_through_2022(self):
        overrides = pd.read_csv(
            Path(__file__).resolve().parent.parent / "data/manual/position_overrides.csv",
            dtype=str,
        )
        harry = overrides[overrides["player_id"] == self.HARRY_ID]
        assert set(harry["season"]) == {"2019", "2020", "2021", "2022"}
        assert set(harry["correct_position"]) == {"WR"}
        assert harry["season"].notna().all(), "Harry must not receive an all-season override"

    def test_weekly_and_season_rows_correct_only_approved_seasons_before_ranking(self, tmp_path, monkeypatch):
        _write_position_overrides(tmp_path, *self._harry_override_rows())
        rows = []
        for season in range(2018, 2025):
            rows.extend(
                [
                    make_weekly_row(season, 1, self.HARRY_ID, "N'Keal Harry", "TE", "NE", targets=1, points=10.0),
                    make_weekly_row(season, 1, "00-WR-PEER", "WR Peer", "WR", "NE", targets=1, points=20.0),
                    make_weekly_row(season, 1, "00-OTHER-HARRY", "Other Harry", "TE", "NE", targets=1, points=5.0),
                ]
            )
        weekly_df = pd.DataFrame(rows)

        with patch(
            "nflverse_source.fetch_and_normalize",
            side_effect=lambda season: weekly_df[weekly_df["season"] == season].copy(),
        ):
            mod = load_module(tmp_path, monkeypatch)
            mod.SEASONS = list(range(2018, 2025))
            season = mod.build_season_results()

        harry = season[season["player_id"] == self.HARRY_ID].set_index("season")
        assert set(harry.loc[list(self.APPROVED_SEASONS), "position"]) == {"WR"}
        assert harry.loc[2018, "position"] == "TE"
        assert harry.loc[2023, "position"] == "TE"
        assert harry.loc[2024, "position"] == "TE"

        # The correction precedes Step 6: the 20-point WR peer ranks
        # WR1 and Harry's 10 points rank WR2 in each approved season.
        assert set(harry.loc[list(self.APPROVED_SEASONS), "position_finish_ppr"]) == {2}

        weekly = pd.read_csv(tmp_path / "data/raw/nflverse/weekly_results_ppr_2018_2024.csv")
        harry_weekly = weekly[weekly["player_id"] == self.HARRY_ID].set_index("season")
        assert set(harry_weekly.loc[list(self.APPROVED_SEASONS), "position"]) == {"WR"}
        assert set(harry_weekly.loc[list(self.APPROVED_SEASONS), "results_source_position_raw"]) == {"TE"}
        assert harry_weekly.loc[2018, "position"] == "TE"
        assert harry_weekly.loc[2023, "position"] == "TE"
        assert harry_weekly.loc[2024, "position"] == "TE"

        other = season[season["player_id"] == "00-OTHER-HARRY"]
        assert set(other["position"]) == {"TE"}, "Correction leaked to another player identity"

    def test_season_specific_application_is_idempotent_and_identity_keyed(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("download_stats_harry", SCRIPT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        overrides = pd.DataFrame(self._harry_override_rows())
        base = pd.DataFrame(
            [
                {"season": season, "player_id": self.HARRY_ID, "position": "TE"}
                for season in range(2018, 2025)
            ]
            + [{"season": 2020, "player_id": "00-NOT-HARRY", "position": "TE"}]
        )

        once = mod.apply_position_overrides(base.copy(), overrides)
        twice = mod.apply_position_overrides(once.copy(), overrides)
        pd.testing.assert_frame_equal(once, twice)

        harry = once[once["player_id"] == self.HARRY_ID].set_index("season")
        assert set(harry.loc[list(self.APPROVED_SEASONS), "position"]) == {"WR"}
        assert set(harry.loc[[2018, 2023, 2024], "position"]) == {"TE"}
        assert once.loc[once["player_id"] == "00-NOT-HARRY", "position"].iat[0] == "TE"


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
