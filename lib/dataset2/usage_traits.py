"""
lib/dataset2/usage_traits.py

Dataset 2 "opportunity/usage foundation" -- Source A only (approved
2026-07, research/dataset2/OPPORTUNITY_FOUNDATION_PROPOSAL_2026_07.md).
REVISED 2026-07 after a real-data aggregation-semantics audit (see
research/dataset2/USAGE_AGGREGATION_AUDIT_2026_07.md) found the first
version's weekly-average approach for share/rate fields was
mathematically wrong, and that it silently included real postseason
rows. This version RECOMPUTES season-level shares from real summed
numerators/denominators wherever that reconstruction was verified
correct against real data, and DEFERS the one metric (RACR) that could
not be reliably reconstructed, per the approved
reconstruct-or-defer rule.

Built directly from the real, already-cached
`data/raw/nflverse/annual/stats_player_week_{season}.csv` files.
Unlocks the base variables for families #15 (target-earning ability),
#17 (air-yard profile), #20 (carry profile), #22 (passing-game role
for running backs), #18's core receiving-efficiency inputs, and #88's
touch-count sub-signal.

REQUIRED INPUT SCOPE, real finding: `weekly` must be the FULL raw
weekly file, ALL positions, not pre-filtered to skill positions --
verified against real 2023 data that restricting to QB/RB/WR/TE before
computing team-week totals silently drops real targets/passing-air-
yards attributed to other position tags (135 targets and 66
passing-air-yards of real 2023 season volume came from non-skill-
tagged rows). `population` still scopes which (season, player_id)
rows are RETURNED (skill positions only, as always) -- only the
team-level denominator computation needs the full file.

POSTSEASON EXCLUSION, real finding: the raw weekly file contains real
`season_type == 'POST'` rows (837 real rows in 2023 alone) mixed in
with `'REG'` rows. The FIRST version of this module did not filter
this and would have silently folded playoff production into a
"season" aggregate. This version filters to `season_type == 'REG'`
internally -- not left to the caller, since the failure mode (a wrong
number that still looks plausible) is exactly what this project's
fail-loud convention exists to prevent.

AGGREGATION METHOD PER FIELD -- verified against real 2023 data,
not assumed:

- `targets`, `carries`, `receiving_yards`, `receiving_air_yards`:
  SUMMED across the season. Real counts/yardage, unambiguous.
- `passing_epa`, `rushing_epa`, `receiving_epa`: SUMMED. Verified real:
  these are per-week TOTALS (not per-play averages) already -- a
  player's weekly EPA scales with their real weekly volume (spot-
  checked: players with 20+ real targets in a week show EPA in the
  5-17 range, consistent with per-play EPA around 0.3-0.85 summed over
  ~20 plays, not a bounded per-play average). Summing weekly totals
  gives the real season total.
- `target_share`: RECOMPUTED at the season level as
  `season target_share = player's season targets / that player's
  real team-week targets, summed only over the weeks that player
  actually played (using THAT WEEK's real team, so a mid-season trade
  is followed correctly -- see below)`. NEVER a weekly average.
  Verified against real 2023 data: this recomputation reconciles
  EXACTLY (max float-precision-level difference, 5.5e-16) against
  nflverse's own real per-week `target_share` values, confirming this
  IS nflverse's own real formula, not an approximation.
- `air_yards_share`: RECOMPUTED the same way, but the denominator is
  team-week `passing_air_yards` (the real QB-side total, including
  incompletions/spikes), NOT summed `receiving_air_yards` (which
  undercounts -- verified: using summed receiving_air_yards as the
  denominator gives a mean real discrepancy of 0.0067 and a max of 0.9
  against nflverse's real values; switching to `passing_air_yards`
  reconciles EXACTLY, same float-precision level as target_share).
- `wopr`: RECOMPUTED from the two recomputed shares above as
  `1.5 * target_share + 0.7 * air_yards_share` -- nflverse's own
  published formula, verified to reconcile exactly against real 2023
  weekly WOPR values using this same formula on the raw weekly shares,
  so recomputing it from the season-level recomputed shares is the
  same real formula applied one level up, not a new approximation.
- `racr` -- DEFERRED, NOT COMPUTED. Real investigation: a naive
  player-level `receiving_yards / receiving_air_yards` recomputation
  was tested against real 2023 weekly `racr` values and diverges
  badly in real rows with negative or near-zero `receiving_air_yards`
  (max absolute discrepancy 38.0; a "treat non-positive air yards as
  racr=0" hypothesis was also tested and still diverges on 532/17,806
  real rows). nflverse's exact real racr formula could not be reliably
  reverse-engineered from the data available in this pipeline within
  this investigation. Per the approved rule ("if a metric cannot be
  reconstructed correctly, preserve the underlying inputs and defer
  that derived season metric rather than creating an inaccurate
  aggregate"), this module does NOT output a season-level `racr`
  column at all. `receiving_yards` and `receiving_air_yards` (both
  real, unambiguous sums) ARE output, so a consumer can compute their
  own ratio once/if the real per-row formula is confirmed.

TRADED PLAYERS: represented as PLAYER-SEASON rows (one row per
(season, player_id), same grain as every other Dataset 2 module), not
player-team-season rows. Verified this is not a simplification that
loses accuracy: because the team-week denominator lookup uses each
week's own real `team` value, a traded player's recomputed shares
correctly reflect "targets captured, given whichever team's target
pool was actually available that week" -- spot-checked against a real
2023 trade (Chase Claypool, CHI weeks 1-3 -> MIA weeks 7-18) in
research/dataset2/USAGE_AGGREGATION_AUDIT_2026_07.md.

DUPLICATE WEEKS: checked directly against real 2023 data -- zero
duplicate (player_id, week) rows found within REG. Not defended
against with extra code, since no real occurrence was found to defend
against; if this project's real data ever produces one,
`groupby().sum()`/`.mean()` would silently double-count it, which is a
real, disclosed limitation of this version, not a decision this module
makes.

THREE STRUCTURALLY SEPARATE THINGS -- see this module's own functions:

1. RAW SEASON AGGREGATES (`build_raw_season_usage()`): this season's
   own real values. Plain column names, no prefix. SAME-SEASON DATA --
   never use this season's own row as a predictor for that season.
2. PRESEASON PREDICTOR FEATURES (`build_preseason_usage_features()`):
   every field strictly LAGGED to the PRIOR season via the same
   `lag_join()` already used by families #7/#8/#39/#44, always
   `prior_season_*` prefixed. Per field, the predictor type is:
   - `prior_season_targets`/`carries`/`receiving_yards`/
     `receiving_air_yards`: a lagged COUNT (prior season's real total).
   - `prior_season_passing_epa`/`rushing_epa`/`receiving_epa`: a
     lagged prior-season TOTAL (not efficiency-per-play, a real sum).
   - `prior_season_target_share`/`air_yards_share`/`wopr`: a lagged
     RECOMPUTED SHARE/WEIGHTED RATE (the season-level recomputation
     above, computed once for the prior season, then lagged whole --
     not re-averaged or re-weighted at lag time).
3. SAME-SEASON OUTCOME DATA: simply #1's own output for the season
   being predicted. Never re-wrapped; the naming convention is the
   whole safeguard.

TEST SCOPE: tests/test_dataset2_usage_traits.py proves implementation
correctness (recomputation math, REG-only filtering, traded-player
handling, the lag/leakage separation, missingness) against synthetic
fixtures. Real-data integration and coverage validation has not
happened yet at the FULL 2006-2025 population level -- same required
checkpoint as this module's siblings, see
research/dataset2/DATASET2_TRAIT_ROADMAP.md §6.
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
    "team",
    "season_type",
    "targets",
    "carries",
    "receiving_yards",
    "receiving_air_yards",
    "passing_air_yards",
    "passing_epa",
    "rushing_epa",
    "receiving_epa",
)

# Real counts/totals, summed across the season -- unambiguous.
SUM_FIELDS = (
    "targets",
    "carries",
    "receiving_yards",
    "receiving_air_yards",
    "passing_epa",
    "rushing_epa",
    "receiving_epa",
)

# Season-level shares/rates RECOMPUTED from real summed numerators and
# denominators -- never a weekly average. See module docstring.
RATE_FIELDS = ("target_share", "air_yards_share", "wopr")

RAW_OUTPUT_COLUMNS = ("season", "player_id", "position") + SUM_FIELDS + RATE_FIELDS

PRESEASON_OUTPUT_COLUMNS = ("season", "player_id", "position") + tuple(
    f"prior_season_{f}" for f in SUM_FIELDS + RATE_FIELDS
)


def build_raw_season_usage(population: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """
    RAW season aggregates only -- this season's own real totals and
    recomputed shares. Plain column names, no prefix. See module
    docstring: this output is SAME-SEASON data and must never be used
    directly as a preseason predictor for the season it describes --
    use build_preseason_usage_features() for that.

    `population` scopes which (season, player_id, position) rows are
    RETURNED (skill positions only, as always -- every row preserved,
    even a player with zero real weekly rows). `weekly` must be the
    FULL raw weekly file across ALL positions (not pre-filtered to
    skill positions) -- required for the real team-week denominators
    to be correct, see module docstring. Both REG and POST rows may be
    present in `weekly`; POST is filtered out internally.
    """
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(weekly, WEEKLY_REQUIRED_COLUMNS, "weekly")

    reg = weekly[weekly["season_type"] == "REG"].copy()

    team_week_totals = (
        reg.groupby(["season", "week", "team"])
        .agg(_team_week_targets=("targets", "sum"), _team_week_passing_air_yards=("passing_air_yards", "sum"))
        .reset_index()
    )
    reg = reg.merge(team_week_totals, on=["season", "week", "team"], how="left")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )

    player_sums = (
        reg.groupby(["season", "player_id"])
        .agg(
            **{f: (f, "sum") for f in SUM_FIELDS},
            _own_team_week_targets_sum=("_team_week_targets", "sum"),
            _own_team_week_pay_sum=("_team_week_passing_air_yards", "sum"),
        )
        .reset_index()
    )

    out = base.merge(player_sums, on=["season", "player_id"], how="left")
    for field in SUM_FIELDS:
        out[field] = out[field].fillna(0.0)

    out["target_share"] = out["targets"] / out["_own_team_week_targets_sum"].replace(0, np.nan)
    out["air_yards_share"] = out["receiving_air_yards"] / out["_own_team_week_pay_sum"].replace(0, np.nan)
    out["wopr"] = 1.5 * out["target_share"] + 0.7 * out["air_yards_share"]

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
    slice.

    Rookie handling: a player's first real season has no season N-1
    row to lag from, so every field is null -- the correct, structural
    behavior, matching every other Dataset 2 lag-based module's rookie
    path.
    """
    validate_columns(raw_season_usage, RAW_OUTPUT_COLUMNS, "raw_season_usage")

    # Deduplicate once onto a single canonical frame, then compute and
    # assign every lag directly onto IT -- never a second,
    # independently-built frame relying on row order matching.
    working = raw_season_usage.drop_duplicates(subset=["season", "player_id"]).reset_index(drop=True)

    for field in SUM_FIELDS + RATE_FIELDS:
        working[f"prior_season_{field}"] = lag_join(working, field, 1)

    return working[list(PRESEASON_OUTPUT_COLUMNS)].reset_index(drop=True)
