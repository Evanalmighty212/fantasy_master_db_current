"""
lib/dataset2/partial_season_traits.py

Dataset 2 family #9 (partial-season production splits) -- SAMPLE-SIZE
PORTION ONLY, approved 2026-07 from real retained-count analysis
(research/dataset2/DATASET2_TRAIT_ROADMAP.md §6, family #9). Builds:

- build_half_split_traits(): first-half vs. second-half PPG
  (season-length-aware halves, per lib.dataset2.common.season_length())
- build_final_n_games_traits(): PPG over the trailing `n` weeks,
  parametrized (threshold-sensitivity rule: one parametrized window,
  not many hardcoded fixed-N columns)

Both expose PRIMARY (>= config.DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY,
4 games) and SENSITIVITY (>= config.DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY,
3 games) sample-size qualification as two SEPARATE boolean columns --
never collapsed into one "qualified" flag, per the approved decision
that both must be reported. Below the sensitivity floor, the window is
never a usable finding: the corresponding *_ppg value is set to NaN,
not just flagged -- this is a structural guarantee (a downstream
consumer cannot accidentally average in a <3-game PPG), not merely
documentation of a rule a consumer has to remember to apply.

MINIMUM-OPPORTUNITY IS DELIBERATELY NOT IMPLEMENTED HERE.
`opportunity_qualified` is present in every output row but is ALWAYS
the literal string OPPORTUNITY_STATUS_PENDING -- never True/False,
never silently defaulted to "qualified." A real opportunity floor
(target share / carries / snap share) cannot be computed with real
data yet: per the roadmap's investigation, that data is either
fetched-but-not-retained or not yet wired into this pipeline at all
(families #15/#16/#20). A games-played threshold alone can include a
player who was active but had a negligible role (e.g. a decoy WR4 with
one target across four games) -- do not characterize this module's PPG
values as a final, opportunity-qualified finding until that floor is
added and this module is revised to apply it.

TEST SCOPE: tests/test_dataset2_partial_season_traits.py proves
implementation correctness (floor enforcement, window parametrization,
season-length-aware half boundaries) against synthetic fixtures only.
Real-data integration and coverage validation has not happened yet --
same required checkpoint as this module's siblings, see
research/dataset2/DATASET2_TRAIT_ROADMAP.md §6.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY, DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY
from lib.dataset2.common import season_length, validate_columns

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position")
WEEKLY_REQUIRED_COLUMNS = ("season", "player_id", "week", "fantasy_points_ppr")

OPPORTUNITY_STATUS_PENDING = "pending"

HALF_SPLIT_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "first_half_games",
    "first_half_ppg",
    "first_half_sample_qualified_primary",
    "first_half_sample_qualified_sensitivity",
    "second_half_games",
    "second_half_ppg",
    "second_half_sample_qualified_primary",
    "second_half_sample_qualified_sensitivity",
    "opportunity_qualified",
)

FINAL_N_GAMES_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "window_n",
    "final_n_games",
    "final_n_games_ppg",
    "final_n_games_sample_qualified_primary",
    "final_n_games_sample_qualified_sensitivity",
    "opportunity_qualified",
)


def _apply_floor(games: pd.Series, ppg: pd.Series):
    """Returns (ppg_with_floor_enforced, qualified_primary, qualified_sensitivity).
    ppg is set to NaN wherever games < SENSITIVITY floor -- a <3-game
    window is never a usable finding, structurally, not just by
    convention."""
    qualified_primary = games >= DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY
    qualified_sensitivity = games >= DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY
    ppg_enforced = np.where(qualified_sensitivity, ppg, np.nan)
    return ppg_enforced, qualified_primary, qualified_sensitivity


def build_half_split_traits(population: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """
    `population` scopes which (season, player_id, position) rows are
    returned (every row preserved, even a player with zero weekly rows
    in a half -- games=0, ppg=NaN, both floors False, not a dropped
    row). `weekly` is the per-week box-score-level detail
    (season, player_id, week, fantasy_points_ppr).
    """
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(weekly, WEEKLY_REQUIRED_COLUMNS, "weekly")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )

    w = weekly.copy()
    w["G"] = w["season"].apply(season_length)
    w["first_half_cutoff"] = np.ceil(w["G"] / 2)
    w["half"] = np.where(w["week"] <= w["first_half_cutoff"], "first_half", "second_half")

    first_half = (
        w[w["half"] == "first_half"]
        .groupby(["season", "player_id"])["fantasy_points_ppr"]
        .agg(first_half_games="count", _first_half_total="sum")
        .reset_index()
    )
    second_half = (
        w[w["half"] == "second_half"]
        .groupby(["season", "player_id"])["fantasy_points_ppr"]
        .agg(second_half_games="count", _second_half_total="sum")
        .reset_index()
    )

    out = base.merge(first_half, on=["season", "player_id"], how="left").merge(
        second_half, on=["season", "player_id"], how="left"
    )
    out["first_half_games"] = out["first_half_games"].fillna(0).astype(int)
    out["second_half_games"] = out["second_half_games"].fillna(0).astype(int)

    first_half_ppg_raw = out["_first_half_total"] / out["first_half_games"].replace(0, np.nan)
    second_half_ppg_raw = out["_second_half_total"] / out["second_half_games"].replace(0, np.nan)

    (
        out["first_half_ppg"],
        out["first_half_sample_qualified_primary"],
        out["first_half_sample_qualified_sensitivity"],
    ) = _apply_floor(out["first_half_games"], first_half_ppg_raw)
    (
        out["second_half_ppg"],
        out["second_half_sample_qualified_primary"],
        out["second_half_sample_qualified_sensitivity"],
    ) = _apply_floor(out["second_half_games"], second_half_ppg_raw)

    out["opportunity_qualified"] = OPPORTUNITY_STATUS_PENDING

    return out[list(HALF_SPLIT_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_final_n_games_traits(population: pd.DataFrame, weekly: pd.DataFrame, n: int) -> pd.DataFrame:
    """PPG over the trailing `n` weeks of each season, parametrized --
    call this once per window size you want to compare (e.g. n=4, n=6,
    n=8), rather than this module hardcoding a single fixed window."""
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(weekly, WEEKLY_REQUIRED_COLUMNS, "weekly")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )

    w = weekly.copy()
    w["G"] = w["season"].apply(season_length)
    w["weeks_from_end"] = w["G"] - w["week"] + 1
    in_window = w[w["weeks_from_end"] <= n]

    agg = (
        in_window.groupby(["season", "player_id"])["fantasy_points_ppr"]
        .agg(final_n_games="count", _final_n_total="sum")
        .reset_index()
    )

    out = base.merge(agg, on=["season", "player_id"], how="left")
    out["final_n_games"] = out["final_n_games"].fillna(0).astype(int)
    ppg_raw = out["_final_n_total"] / out["final_n_games"].replace(0, np.nan)

    (
        out["final_n_games_ppg"],
        out["final_n_games_sample_qualified_primary"],
        out["final_n_games_sample_qualified_sensitivity"],
    ) = _apply_floor(out["final_n_games"], ppg_raw)

    out["window_n"] = n
    out["opportunity_qualified"] = OPPORTUNITY_STATUS_PENDING

    return out[list(FINAL_N_GAMES_OUTPUT_COLUMNS)].reset_index(drop=True)
