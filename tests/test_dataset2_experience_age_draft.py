"""
tests/test_dataset2_experience_age_draft.py

Covers lib/dataset2/experience_age_draft.py -- Dataset 2 families #1
(experience), #2 (age), #4 (NFL draft capital), and #6's body-size
portion. These tests protect the specific approved decisions in
research/dataset2/DATASET2_TRAIT_ROADMAP.md, not generic coverage:

- experience_years must be derived as season - rookie_season, never
  read from a players.csv-style "years_of_experience" column (roadmap
  §3d -- that column reflects "as of today," not "as of that
  historical season"). TestExperienceYears's fixture omits any such
  column entirely, so a regression that tried to read one would fail
  loudly (KeyError) rather than silently returning a stale value.
- age_at_week1_years must use the real per-team Week-1 kickoff date,
  not a shared calendar-date approximation -- TestAgeAtWeek1 uses two
  teams with DIFFERENT real kickoff dates and the SAME birth_date to
  prove the computed ages differ accordingly.
- nfl_draft_* naming must never collide with this project's existing
  fantasy-ADP/acquisition-cost vocabulary (roadmap §3a) --
  TestDraftCapitalNaming asserts no output column name contains "adp"
  or "acquisition".
- #6 is named body_size_bmi/height_inches/weight_lbs, never
  "athletic_profile" (roadmap §6's renaming decision).
- Age (#2) and experience (#1) are approved as distinct hypotheses;
  measure_age_experience_collinearity() must MEASURE their real
  correlation without ever causing either trait to be dropped --
  TestCollinearityNeverDropsTraits is the regression guard for that.
- Missingness (no players.csv match, no schedule match) must leave a
  row's derived fields null, never drop the row or guess a value
  (docs/LEAGUE_WINNER_TRAITS_SPEC.md's missingness policy).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import experience_age_draft as ead


def _population_df(*rows):
    cols = ["season", "player_id", "position", "team"]
    return pd.DataFrame(list(rows), columns=cols)


def _players_df(*rows):
    cols = [
        "gsis_id", "birth_date", "rookie_season", "height", "weight",
        "draft_year", "draft_round", "draft_pick", "draft_team",
    ]
    return pd.DataFrame(list(rows), columns=cols)


def _schedule_df(*rows):
    cols = ["season", "game_type", "week", "gameday", "home_team", "away_team"]
    return pd.DataFrame(list(rows), columns=cols)


SCHEDULE = _schedule_df(
    {"season": 2022, "game_type": "REG", "week": 1, "gameday": "2022-09-08", "home_team": "TEN", "away_team": "NYG"},
    {"season": 2022, "game_type": "REG", "week": 1, "gameday": "2022-09-11", "home_team": "CLE", "away_team": "CAR"},
)


class TestExperienceYears:
    def test_derived_from_rookie_season_not_a_stale_column(self):
        """rookie_season=2019, season=2022 -> experience_years=3.
        players_df deliberately has NO years_of_experience-style
        column at all -- a regression that tried to read one would
        raise KeyError, not silently return a wrong value."""
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2019, "height": 72, "weight": 200,
             "draft_year": 2019, "draft_round": 3, "draft_pick": 80, "draft_team": "TEN"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        assert out.loc[0, "experience_years"] == 3

    def test_missing_rookie_season_is_null_not_zero(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": None, "height": 72, "weight": 200,
             "draft_year": None, "draft_round": None, "draft_pick": None, "draft_team": None},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        assert pd.isna(out.loc[0, "experience_years"])


class TestAgeAtWeek1:
    def test_uses_real_per_team_kickoff_date_not_a_shared_approximation(self):
        """Same birth_date, two teams with DIFFERENT real 2022 Week-1
        kickoff dates (TEN 2022-09-08, CLE 2022-09-11) -- the computed
        ages must differ by exactly the 3-day gap, proving the
        per-team date is actually used, not a flat approximation."""
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"},
            {"season": 2022, "player_id": "00-2", "position": "WR", "team": "CLE"},
        )
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
            {"gsis_id": "00-2", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 101, "draft_team": "CLE"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        age_ten = out.loc[out["player_id"] == "00-1", "age_at_week1_years"].iloc[0]
        age_cle = out.loc[out["player_id"] == "00-2", "age_at_week1_years"].iloc[0]
        expected_gap_years = 3 / 365.25
        assert age_cle - age_ten == pytest.approx(expected_gap_years, abs=1e-9)

        expected_age_ten = (pd.Timestamp("2022-09-08") - pd.Timestamp("1998-01-01")).days / 365.25
        assert age_ten == pytest.approx(expected_age_ten, abs=1e-9)

    def test_team_with_no_week1_game_in_schedule_is_null_not_an_error(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR", "team": "ZZZ"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "ZZZ"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        assert pd.isna(out.loc[0, "age_at_week1_years"])

    def test_relocated_franchise_resolves_age_via_real_historical_schedule_code(self):
        """Real, found case (2026-07 age-integration audit): this
        project's population always labels the Rams "LA" even for
        historical pre-relocation seasons, but the real 2015 schedule
        file itself says "STL" (the real code in use that season, the
        Rams did not move to LA until 2016). age_at_week1_years must
        still resolve to the real 2015 Week-1 kickoff date via
        lib.dataset2.common's historical-team-code alias -- not go
        null just because the two conventions disagree. See
        tests/test_dataset2_common.py::TestHistoricalTeamCodeAliases
        for the underlying alias-resolution unit tests."""
        pop = _population_df({"season": 2015, "player_id": "00-1", "position": "WR", "team": "LA"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1993-01-01", "rookie_season": 2013, "height": 72, "weight": 200,
             "draft_year": 2013, "draft_round": 3, "draft_pick": 80, "draft_team": "LA"},
        )
        schedule = _schedule_df(
            {"season": 2015, "game_type": "REG", "week": 1, "gameday": "2015-09-13", "home_team": "STL", "away_team": "SEA"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, schedule)
        expected_age = (pd.Timestamp("2015-09-13") - pd.Timestamp("1993-01-01")).days / 365.25
        assert out.loc[0, "age_at_week1_years"] == pytest.approx(expected_age, abs=1e-9)
        assert not pd.isna(out.loc[0, "age_x_experience"])


class TestDraftCapitalNaming:
    def test_output_uses_nfl_draft_prefix(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        assert out.loc[0, "nfl_draft_year"] == 2020
        assert out.loc[0, "nfl_draft_round"] == 4
        assert out.loc[0, "nfl_draft_pick"] == 100
        assert out.loc[0, "nfl_draft_team"] == "TEN"

    def test_no_output_column_collides_with_fantasy_adp_or_acquisition_cost_vocabulary(self):
        """Regression guard for roadmap §3a's naming-collision risk --
        this module must never emit a column that could be mistaken
        for fantasy-market ADP/acquisition-cost fields."""
        for col in ead.OUTPUT_COLUMNS:
            assert "adp" not in col.lower()
            assert "acquisition" not in col.lower()


class TestBodySizeProfile:
    def test_bmi_computed_correctly(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        expected_bmi = 703.0 * 200 / (72 ** 2)
        assert out.loc[0, "body_size_bmi"] == pytest.approx(expected_bmi)
        assert out.loc[0, "height_inches"] == 72
        assert out.loc[0, "weight_lbs"] == 200

    def test_not_named_athletic_profile(self):
        """Roadmap §6: this Tier-1 build is body-size only (no combine
        drills) and must not be labeled 'athletic'."""
        for col in ead.OUTPUT_COLUMNS:
            assert "athletic" not in col.lower()


class TestPositionAdjustedAndInteractionForms:
    def test_position_zscore_and_interaction(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"},
            {"season": 2022, "player_id": "00-2", "position": "WR", "team": "TEN"},
            {"season": 2022, "player_id": "00-3", "position": "WR", "team": "TEN"},
        )
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "2000-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
            {"gsis_id": "00-2", "birth_date": "1996-01-01", "rookie_season": 2018, "height": 72, "weight": 200,
             "draft_year": 2018, "draft_round": 2, "draft_pick": 50, "draft_team": "TEN"},
            {"gsis_id": "00-3", "birth_date": "1998-01-01", "rookie_season": 2019, "height": 72, "weight": 200,
             "draft_year": 2019, "draft_round": 3, "draft_pick": 75, "draft_team": "TEN"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)

        # experience_years: 2, 4, 3 -- mean 3, std 1
        exp_z = out.set_index("player_id")["experience_position_z"]
        assert exp_z["00-1"] == pytest.approx(-1.0)
        assert exp_z["00-2"] == pytest.approx(1.0)
        assert exp_z["00-3"] == pytest.approx(0.0)

        # interaction is exactly age * experience for every row
        recomputed = out["age_at_week1_years"] * out["experience_years"]
        assert (out["age_x_experience"] == recomputed).all()

    def test_single_row_group_zscore_is_null_not_a_crash(self):
        """A position group of size 1 has zero variance -- must
        produce NaN (disclosed), not a divide-by-zero error."""
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "QB", "team": "TEN"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        assert pd.isna(out.loc[0, "experience_position_z"])
        assert pd.isna(out.loc[0, "age_position_z"])


class TestCollinearityMeasurement:
    def test_reports_real_correlation(self):
        traits = pd.DataFrame({
            "experience_years": [1, 2, 3, 4, 5],
            "age_at_week1_years": [22.0, 23.0, 24.0, 25.0, 26.0],
        })
        result = ead.measure_age_experience_collinearity(traits)
        assert result["n"] == 5
        assert result["pearson_r"] == pytest.approx(1.0, abs=1e-9)
        assert result["spearman_r"] == pytest.approx(1.0, abs=1e-9)

    def test_nulls_excluded_not_treated_as_zero(self):
        traits = pd.DataFrame({
            "experience_years": [1, 2, np.nan, 4, 5],
            "age_at_week1_years": [22.0, 23.0, 24.0, 25.0, 26.0],
        })
        result = ead.measure_age_experience_collinearity(traits)
        assert result["n"] == 4


class TestCollinearityNeverDropsTraits:
    """Regression guard for the roadmap's approved decision: 'treat
    collinearity as something to measure and report, not as a reason
    to remove either trait before testing.'"""

    def test_calling_collinearity_measurement_does_not_mutate_the_traits_table(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        columns_before = list(out.columns)

        ead.measure_age_experience_collinearity(out)

        assert list(out.columns) == columns_before
        assert "experience_years" in out.columns
        assert "age_at_week1_years" in out.columns

    def test_output_columns_constant_always_includes_both_traits(self):
        assert "experience_years" in ead.OUTPUT_COLUMNS
        assert "age_at_week1_years" in ead.OUTPUT_COLUMNS


class TestMissingnessDisclosed:
    def test_player_with_no_players_csv_match_keeps_row_with_null_fields(self):
        pop = _population_df({"season": 2022, "player_id": "00-unknown", "position": "WR", "team": "TEN"})
        players = _players_df(
            {"gsis_id": "00-different-player", "birth_date": "1998-01-01", "rookie_season": 2020,
             "height": 72, "weight": 200, "draft_year": 2020, "draft_round": 4, "draft_pick": 100,
             "draft_team": "TEN"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        assert len(out) == 1
        assert out.loc[0, "player_id"] == "00-unknown"
        assert pd.isna(out.loc[0, "experience_years"])
        assert pd.isna(out.loc[0, "age_at_week1_years"])
        assert pd.isna(out.loc[0, "nfl_draft_round"])
        assert pd.isna(out.loc[0, "body_size_bmi"])


class TestRequiredColumnValidation:
    def test_population_missing_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2022], "player_id": ["00-1"]})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
        )
        with pytest.raises(ValueError, match="population is missing required columns"):
            ead.build_experience_age_draft_traits(bad_pop, players, SCHEDULE)

    def test_players_df_missing_column_raises(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"})
        bad_players = pd.DataFrame({"gsis_id": ["00-1"]})
        with pytest.raises(ValueError, match="players_df is missing required columns"):
            ead.build_experience_age_draft_traits(pop, bad_players, SCHEDULE)

    def test_schedule_df_missing_column_raises(self):
        pop = _population_df({"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"})
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
        )
        bad_schedule = pd.DataFrame({"season": [2022]})
        with pytest.raises(ValueError, match="schedule_df is missing required columns"):
            ead.build_experience_age_draft_traits(pop, players, bad_schedule)


class TestRowCountPreserved:
    def test_duplicate_population_rows_collapse_but_no_real_row_is_dropped(self):
        pop = _population_df(
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"},
            {"season": 2022, "player_id": "00-1", "position": "WR", "team": "TEN"},  # exact duplicate
            {"season": 2022, "player_id": "00-2", "position": "RB", "team": "CLE"},
        )
        players = _players_df(
            {"gsis_id": "00-1", "birth_date": "1998-01-01", "rookie_season": 2020, "height": 72, "weight": 200,
             "draft_year": 2020, "draft_round": 4, "draft_pick": 100, "draft_team": "TEN"},
            {"gsis_id": "00-2", "birth_date": "1997-01-01", "rookie_season": 2019, "height": 70, "weight": 210,
             "draft_year": 2019, "draft_round": 1, "draft_pick": 10, "draft_team": "CLE"},
        )
        out = ead.build_experience_age_draft_traits(pop, players, SCHEDULE)
        assert len(out) == 2
