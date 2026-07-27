"""
lib/dataset2/experience_age_draft.py

Dataset 2 families #1 (NFL experience curve), #2 (age curve), #4 (NFL
draft capital), and #6's body-size portion (height/weight/BMI) --
approved 2026-07 as the first Dataset 2 implementation slice
(research/dataset2/DATASET2_TRAIT_ROADMAP.md, Tier 1 "players.csv
cluster": all four derive from players.csv + schedules, zero new
acquisition).

Per the roadmap's approved decisions, applied here:
- Age (#2) and experience (#1) are DISTINCT hypotheses (biological/
  positional development-decline vs. career-stage/adaptation), not
  duplicates or a single family split in two. Both are built here, and
  this module also builds the interaction form (age_x_experience) and
  position-adjusted forms (experience_position_z, age_position_z) the
  approval explicitly asked for. measure_age_experience_collinearity()
  below MEASURES and reports the real correlation between them -- it
  is a read-only diagnostic. Nothing in build_experience_age_draft_traits()
  consumes its output or drops a column because of it -- collinearity
  is something to report, never a reason to remove either trait before
  testing (see that function's own docstring, and
  tests/test_dataset2_experience_age_draft.py's
  TestCollinearityNeverDropsTraits).
- experience_years is DERIVED as season - rookie_season, never read
  from players.csv's own years_of_experience column, which reflects
  "as of today" (fetch time), not "as of that historical season" --
  roadmap §3d.
- age_at_week1_years uses the REAL per-team Week-1 kickoff date (from
  schedule_df), not a flat, shared calendar-date approximation -- the
  same convention already proven in
  lib/stars_by_value/acquisition_cost.py's rookie-QB depth-chart
  correction.
- Draft-capital fields use the nfl_draft_* prefix (roadmap §3a),
  deliberately never overlapping this project's existing
  overall_adp_*/positional_adp_*/acquisition_cost_* fantasy-market
  fields -- verified by
  tests/test_dataset2_experience_age_draft.py's
  TestDraftCapitalNaming.
- This module's body-size fields are deliberately named
  height_inches/weight_lbs/body_size_bmi, not "athletic_profile" --
  roadmap §6's renaming decision. True athletic (combine-drill) data
  is a separate, not-yet-built, coverage-unverified item (roadmap §5,
  Tier 3, "6 (split, part)").

MISSINGNESS POLICY (matches docs/LEAGUE_WINNER_TRAITS_SPEC.md and
docs/MATCHING_ARCHITECTURE.md): a population row whose player_id has
no match in players_df, or whose team has no Week-1 game in
schedule_df for that season, is KEPT (never silently dropped) with the
affected derived fields left null. This module never imputes,
zero-fills, or guesses a missing value.

TEST SCOPE, READ BEFORE TRUSTING THIS MODULE ON REAL DATA:
tests/test_dataset2_experience_age_draft.py proves IMPLEMENTATION
CORRECTNESS ONLY, against small synthetic fixtures -- it has never run
against the real players.csv/schedules population (not cached in this
dev sandbox; real fetches go through the established GitHub Actions
path). Real-data integration and coverage validation is a separate,
required, not-yet-done step -- see
research/dataset2/DATASET2_TRAIT_ROADMAP.md §6's "Required integration
checkpoint" for the exact real-data review this module must pass
(match rate, missing birth dates/rookie seasons/schedule matches,
real distribution shapes, duplicate matches, impossible values) before
its output is used in any Dataset 2 analysis.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import validate_columns

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position", "team")
PLAYERS_REQUIRED_COLUMNS = (
    "gsis_id",
    "birth_date",
    "rookie_season",
    "height",
    "weight",
    "draft_year",
    "draft_round",
    "draft_pick",
    "draft_team",
)
SCHEDULE_REQUIRED_COLUMNS = ("season", "game_type", "week", "gameday", "home_team", "away_team")

OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "experience_years",
    "age_at_week1_years",
    "age_x_experience",
    "experience_position_z",
    "age_position_z",
    "nfl_draft_year",
    "nfl_draft_round",
    "nfl_draft_pick",
    "nfl_draft_team",
    "height_inches",
    "weight_lbs",
    "body_size_bmi",
)


def _week1_kickoff_by_team(schedule_df: pd.DataFrame, season: int) -> dict:
    """Real per-team Week-1 REG-season kickoff date for `season`, keyed
    by team code -- same convention already proven in
    acquisition_cost.apply_rookie_qb_depth_chart_correction() (a real
    per-team date, not a shared project-wide approximation like
    "Sept 1"). A team with no Week-1 REG game in `schedule_df` for this
    season is simply absent from the returned dict -- the caller treats
    that as "kickoff date unknown" (null downstream), not an error."""
    week1 = schedule_df[
        (schedule_df["season"] == season) & (schedule_df["game_type"] == "REG") & (schedule_df["week"] == 1)
    ]
    kickoff = {}
    for _, row in week1.iterrows():
        gameday = pd.to_datetime(row["gameday"])
        kickoff[row["home_team"]] = gameday
        kickoff[row["away_team"]] = gameday
    return kickoff


def _kickoff_lookup_table(schedule_df: pd.DataFrame, seasons) -> pd.DataFrame:
    """season/team/kickoff_date rows for every season in `seasons`,
    built by calling _week1_kickoff_by_team() once per season (not once
    per population row -- that would recompute the same per-season
    dict thousands of times)."""
    frames = []
    for season in sorted(set(seasons)):
        kickoff = _week1_kickoff_by_team(schedule_df, season)
        if kickoff:
            frames.append(
                pd.DataFrame({"season": season, "team": list(kickoff.keys()), "_kickoff_date": list(kickoff.values())})
            )
    if not frames:
        return pd.DataFrame(columns=["season", "team", "_kickoff_date"])
    return pd.concat(frames, ignore_index=True)


def _within_group_zscore(df: pd.DataFrame, value_col: str, group_col: str) -> pd.Series:
    """Position-adjusted form: how many standard deviations this row's
    value_col sits from the mean for its group_col, computed over the
    population passed in. NaN input propagates to NaN output -- never
    imputed. A group with zero variance (e.g. a single-row group)
    produces NaN for that group rather than a divide-by-zero, which is
    disclosed missingness, not a bug."""
    grouped = df.groupby(group_col)[value_col]
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0, np.nan)
    return (df[value_col] - mean) / std


def build_experience_age_draft_traits(
    population: pd.DataFrame, players_df: pd.DataFrame, schedule_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Builds families #1, #2, #4, and #6's body-size portion for every
    row in `population` (one row per season/player_id/position/team --
    duplicates on those four columns are collapsed before joining).

    `population` must already be the caller's scoped Dataset 2
    population (which seasons/positions are in scope is the caller's
    decision, matching this project's established "caller scopes
    population, this module just computes" convention -- see
    lib/stars_by_value/production.py's module docstring for the
    precedent this follows).

    Returns one row per (season, player_id, position) with every column
    in OUTPUT_COLUMNS. Every row in `population` is preserved in the
    output -- see this module's docstring for the missingness policy.
    """
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(players_df, PLAYERS_REQUIRED_COLUMNS, "players_df")
    validate_columns(schedule_df, SCHEDULE_REQUIRED_COLUMNS, "schedule_df")

    out = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates().copy()

    players = players_df[list(PLAYERS_REQUIRED_COLUMNS)].drop_duplicates(subset=["gsis_id"])
    out = out.merge(players, left_on="player_id", right_on="gsis_id", how="left")

    # --- #1: NFL experience curve -- season-relative, per roadmap §3d ---
    out["experience_years"] = out["season"] - out["rookie_season"]

    # --- #2: Age curve -- real per-team Week-1 kickoff date ---
    kickoff_table = _kickoff_lookup_table(schedule_df, out["season"].unique())
    out = out.merge(kickoff_table, on=["season", "team"], how="left")
    out["birth_date"] = pd.to_datetime(out["birth_date"])
    out["age_at_week1_years"] = (out["_kickoff_date"] - out["birth_date"]).dt.days / 365.25
    out = out.drop(columns=["_kickoff_date"])

    # --- Joint / interaction / position-adjusted forms (approved 2026-07) ---
    out["age_x_experience"] = out["age_at_week1_years"] * out["experience_years"]
    out["experience_position_z"] = _within_group_zscore(out, "experience_years", "position")
    out["age_position_z"] = _within_group_zscore(out, "age_at_week1_years", "position")

    # --- #4: NFL draft capital -- nfl_draft_* naming (roadmap §3a) ---
    out = out.rename(
        columns={
            "draft_year": "nfl_draft_year",
            "draft_round": "nfl_draft_round",
            "draft_pick": "nfl_draft_pick",
            "draft_team": "nfl_draft_team",
        }
    )

    # --- #6 (body-size portion only, roadmap §6 renaming decision) ---
    out = out.rename(columns={"height": "height_inches", "weight": "weight_lbs"})
    out["body_size_bmi"] = 703.0 * out["weight_lbs"] / (out["height_inches"] ** 2)

    return out[list(OUTPUT_COLUMNS)].reset_index(drop=True)


def measure_age_experience_collinearity(traits_df: pd.DataFrame) -> dict:
    """Reports (never acts on) the real correlation between #1's
    experience_years and #2's age_at_week1_years, computed over
    whatever population `traits_df` (build_experience_age_draft_traits()'s
    output, or a subset of it) contains. Per the roadmap's approved
    decision: 'treat collinearity as something to measure and report,
    not as a reason to remove either trait before testing.' This
    function only reads `traits_df` and returns a plain dict -- nothing
    in this module calls this function's output to drop a column, and
    tests/test_dataset2_experience_age_draft.py's
    TestCollinearityNeverDropsTraits verifies that
    build_experience_age_draft_traits()'s OUTPUT_COLUMNS is unaffected
    by this function ever being called."""
    valid = traits_df.dropna(subset=["experience_years", "age_at_week1_years"])
    if len(valid) < 2:
        return {"n": len(valid), "pearson_r": None, "spearman_r": None}
    return {
        "n": int(len(valid)),
        "pearson_r": float(valid["experience_years"].corr(valid["age_at_week1_years"], method="pearson")),
        "spearman_r": float(valid["experience_years"].corr(valid["age_at_week1_years"], method="spearman")),
    }
