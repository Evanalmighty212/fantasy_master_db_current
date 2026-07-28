"""
lib/dataset2/usage_traits.py

Dataset 2 "opportunity/usage foundation" -- Source A only (approved
2026-07, research/dataset2/OPPORTUNITY_FOUNDATION_PROPOSAL_2026_07.md):
season-level aggregates of the already-fetched-but-not-retained
weekly advanced-stats columns (`targets`, `carries`, `target_share`,
`air_yards_share`, `wopr`, `racr`, `passing_epa`, `rushing_epa`,
`receiving_epa`), built directly from the real, already-cached
`data/raw/nflverse/annual/stats_player_week_{season}.csv` files.

Unlocks the base variables for families #15 (target-earning ability),
#17 (air-yard profile), #20 (carry profile), #22 (passing-game role
for running backs), #18's core receiving-efficiency inputs, and #88's
touch-count sub-signal -- see the proposal doc for the full mapping.
Deliberately does NOT build any derived interaction, ratio, or
threshold beyond the raw aggregates themselves -- per the approved
design, those are a LATER, separate step that consumes this
foundation, not part of it.

THREE STRUCTURALLY SEPARATE THINGS, approved 2026-07 -- never merge
them:

1. RAW SEASON AGGREGATES (`build_raw_season_usage()`): this season's
   own real totals/rates. Column names are PLAIN (`targets`,
   `carries`, `target_share`, ...) -- no prefix.
2. PRESEASON PREDICTOR FEATURES (`build_preseason_usage_features()`):
   the SAME fields, strictly LAGGED to the PRIOR season only, via the
   same `lag_join()` helper already used by families #7/#8/#39/#44.
   Column names are ALWAYS prefixed `prior_season_*`
   (`prior_season_targets`, `prior_season_target_share`, ...) -- an
   unambiguous naming convention so a predictor-facing column can
   never be confused with a same-season one. For a prediction season
   N, `prior_season_*` values are computed ONLY from season N-1's raw
   row and are mathematically INDEPENDENT of season N's own raw row --
   proven by tests/test_dataset2_usage_traits.py's
   TestNoSameSeasonLeakage, which mutates a season's own raw values
   and confirms that season's prior_season_* features (used to predict
   a LATER season) are unaffected, and separately confirms a given
   season's prior_season_* features exactly match the real prior
   season's raw row with zero dependency on its own season's data.
3. SAME-SEASON OUTCOME DATA: this is simply `build_raw_season_usage()`'s
   own output FOR THE PREDICTION SEASON ITSELF. It is never wrapped or
   relabeled by this module -- the plain, unprefixed column names are
   the whole safeguard: a caller building a preseason feature set must
   only reach for `prior_season_*` columns, never the plain ones, for
   the season being predicted. This module does not attempt to prevent
   a careless caller from misusing the raw columns -- correctness at
   the call-site is a caller responsibility this project has followed
   throughout (matching production.py's "caller scopes population"
   convention) -- but the naming makes the mistake hard to make by
   accident.

RAW AGGREGATION METHOD PER FIELD (a real, disclosed methodological
choice, not a threshold): `targets`/`carries` are SUMMED across the
season (unambiguous real totals). `target_share`/`air_yards_share`/
`wopr`/`racr` are AVERAGED across the real weeks with a non-null value
that season (the standard way these per-week share/rate metrics are
aggregated to a season level -- an unweighted mean, not weighted by
team pass volume, which this pipeline doesn't currently retain).
`passing_epa`/`rushing_epa`/`receiving_epa` are SUMMED (total real
value added that season, not averaged per-play).

MISSINGNESS: a player-season with zero real weekly rows for a given
activity (e.g. a WR who never recorded a target) gets NaN for that
activity's rate fields (`target_share`, etc.) and 0 for count fields
(`targets`) -- 0 real targets is a real, known fact, not missing data,
while an average of zero real weeks is genuinely undefined. Every
population row is preserved regardless.

TEST SCOPE: tests/test_dataset2_usage_traits.py proves implementation
correctness (aggregation math, the lag/leakage separation, missingness)
against synthetic fixtures only. Real-data integration and coverage
validation has not happened yet -- same required checkpoint as this
module's siblings, see research/dataset2/DATASET2_TRAIT_ROADMAP.md §6.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import lag_join, validate_columns

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position")

WEEKLY_REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "week",
    "targets",
    "carries",
    "target_share",
    "air_yards_share",
    "wopr",
    "racr",
    "passing_epa",
    "rushing_epa",
    "receiving_epa",
)

SUM_FIELDS = ("targets", "carries", "passing_epa", "rushing_epa", "receiving_epa")
MEAN_FIELDS = ("target_share", "air_yards_share", "wopr", "racr")

RAW_OUTPUT_COLUMNS = ("season", "player_id", "position") + SUM_FIELDS + MEAN_FIELDS

PRESEASON_OUTPUT_COLUMNS = ("season", "player_id", "position") + tuple(
    f"prior_season_{f}" for f in SUM_FIELDS + MEAN_FIELDS
)


def build_raw_season_usage(population: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """
    RAW season aggregates only -- this season's own real totals/rates.
    Plain column names, no prefix. See module docstring: this output
    is SAME-SEASON data and must never be used directly as a preseason
    predictor for the season it describes -- use
    build_preseason_usage_features() for that.

    `population` scopes which (season, player_id, position) rows are
    returned (every row preserved, even a player with zero real weekly
    rows -- counts become 0, rates become NaN, never guessed).
    `weekly` is the real per-week source
    (data/raw/nflverse/annual/stats_player_week_{season}.csv,
    concatenated across whatever seasons the caller needs).
    """
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(weekly, WEEKLY_REQUIRED_COLUMNS, "weekly")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )

    sums = weekly.groupby(["season", "player_id"])[list(SUM_FIELDS)].sum(min_count=1)
    means = weekly.groupby(["season", "player_id"])[list(MEAN_FIELDS)].mean()
    agg = sums.join(means, how="outer").reset_index()

    out = base.merge(agg, on=["season", "player_id"], how="left")
    for field in SUM_FIELDS:
        out[field] = out[field].fillna(0.0)
    # MEAN_FIELDS are left as NaN when no real weekly row exists -- an
    # average over zero real observations is genuinely undefined, not 0.

    return out[list(RAW_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_preseason_usage_features(raw_season_usage: pd.DataFrame) -> pd.DataFrame:
    """
    PRESEASON predictor features -- every field in `raw_season_usage`
    strictly lagged to the PRIOR season, via the same lag_join() used
    by families #7/#8/#39/#44. Every output column is prefixed
    `prior_season_*`. `raw_season_usage` must be
    build_raw_season_usage()'s own output (or an equivalent DataFrame
    with the same columns) covering the FULL multi-season population --
    pass every season you need lookups for, not a single season's
    slice, or early-season lookups will come back null even for real
    veterans (same caller-scoping requirement as
    lib/dataset2/prior_season_traits.py).

    Rookie handling: a player's first real season has no season N-1
    row to lag from, so every field is null -- the correct, structural
    behavior, not a gap (matches every other Dataset 2 lag-based
    module's rookie path).
    """
    validate_columns(raw_season_usage, RAW_OUTPUT_COLUMNS, "raw_season_usage")

    # Deduplicate once onto a single canonical frame, then compute and
    # assign every lag directly onto IT -- never a second,
    # independently-built frame relying on row order matching (the
    # exact positional-alignment bug caught and fixed in
    # prior_season_traits.py's own development).
    working = raw_season_usage.drop_duplicates(subset=["season", "player_id"]).reset_index(drop=True)

    for field in SUM_FIELDS + MEAN_FIELDS:
        working[f"prior_season_{field}"] = lag_join(working, field, 1)

    return working[list(PRESEASON_OUTPUT_COLUMNS)].reset_index(drop=True)
