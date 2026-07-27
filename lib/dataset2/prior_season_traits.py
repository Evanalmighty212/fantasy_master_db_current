"""
lib/dataset2/prior_season_traits.py

Dataset 2 families #8 (multi-year production trend), #39 (prior-season
availability/durability), and #44 (player changed teams) -- approved
2026-07 as part of the first implementation wave's "master-DB
self-join cluster" (research/dataset2/DATASET2_TRAIT_ROADMAP.md §6):
all three are strictly-lagged (season N-1, N-2, N-3) derivations
against the master DB's own season-level history, zero new
acquisition.

Family #7 (previous-season finish) is deliberately NOT in this module
-- its trait variables and the required raw/ADP-conditioned/
market-pricing analysis-function split live in
lib/dataset2/prior_finish_traits.py, kept separate per the roadmap's
approved decision to build #7 as its own reviewable slice.

ROOKIE HANDLING (matches docs/LEAGUE_WINNER_TRAITS_SPEC.md's "Rookies
need a separate feature path, not exclusion"): a player's first season
has no prior-season row to lag from, so every field in this module is
NULL for rookies -- this falls out naturally from the lag-join logic
below, not from special-case code, and is the CORRECT behavior, not a
gap to fix. `changed_team` is null for rookies specifically (not
False) for the same reason: "did the player change teams" is undefined
when there is no prior team to compare against, and guessing False
would misrepresent an unknown as a known non-event.

TEST SCOPE: tests/test_dataset2_prior_season_traits.py proves
implementation correctness against synthetic fixtures only. Real-data
integration and coverage validation (match rate, real trend-slope
distributions by position/era, real changed_team base rates) has not
happened yet -- same required checkpoint as
lib/dataset2/experience_age_draft.py, see
research/dataset2/DATASET2_TRAIT_ROADMAP.md §6.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import lag_join, validate_columns

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position", "team", "ppg_ppr", "games_played")

OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "ppg_trend_2yr_slope",
    "ppg_trend_3yr_slope",
    "prior_season_games_played",
    "changed_team",
)


def _slope_over_offsets(offsets_and_values) -> float:
    """OLS slope (ppg change per season) over the non-null
    (season_offset, ppg) points passed in. Fewer than 2 non-null points
    -> NaN (a slope needs at least two points; this is disclosed
    missingness, not an error)."""
    points = [(offset, val) for offset, val in offsets_and_values if pd.notna(val)]
    if len(points) < 2:
        return np.nan
    xs = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    slope, _intercept = np.polyfit(xs, ys, 1)
    return float(slope)


def build_prior_season_traits(population: pd.DataFrame) -> pd.DataFrame:
    """
    Builds families #8, #39, #44 for every row in `population`.

    `population` must already be the caller's scoped Dataset 2
    population, and must contain every (season, player_id) row needed
    to look up prior seasons -- i.e. pass the full multi-season
    population, not a single season's slice, or prior-season lookups
    for the earliest season(s) in your slice will come back null even
    for real veterans (this is a caller-scoping responsibility, the
    same "caller scopes population, this module just computes"
    convention as lib/stars_by_value/production.py).

    Returns one row per (season, player_id, position) with every
    column in OUTPUT_COLUMNS.
    """
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")

    # Everything is computed directly onto `base` (one row per season +
    # player_id, reset to a clean 0..n index) so every assignment below
    # is trivially aligned -- no reliance on two separately-deduplicated
    # frames sharing the same row order or index labels.
    base = population[["season", "player_id", "position", "team", "ppg_ppr", "games_played"]].drop_duplicates(
        subset=["season", "player_id"]
    ).reset_index(drop=True)

    # --- #8: multi-year production trend ---
    ppg_lag1 = lag_join(base, "ppg_ppr", 1)
    ppg_lag2 = lag_join(base, "ppg_ppr", 2)
    ppg_lag3 = lag_join(base, "ppg_ppr", 3)

    # _slope_over_offsets() already drops null points internally, so a
    # missing lag2 (e.g. a second-year player) naturally leaves the
    # 2yr window with a single point -> NaN, not a fabricated slope.
    base["ppg_trend_2yr_slope"] = [
        _slope_over_offsets([(-1, a), (-2, b)]) for a, b in zip(ppg_lag1, ppg_lag2)
    ]
    base["ppg_trend_3yr_slope"] = [
        _slope_over_offsets([(-1, a), (-2, b), (-3, c)]) for a, b, c in zip(ppg_lag1, ppg_lag2, ppg_lag3)
    ]

    # --- #39: prior-season availability (durability) ---
    base["prior_season_games_played"] = lag_join(base, "games_played", 1)

    # --- #44: player changed teams -- simple preseason-known binary flag ---
    prior_team = lag_join(base, "team", 1)
    base["changed_team"] = np.where(
        prior_team.isna(), np.nan, (base["team"].to_numpy() != prior_team.to_numpy()).astype(float)
    )

    return base[list(OUTPUT_COLUMNS)].reset_index(drop=True)
