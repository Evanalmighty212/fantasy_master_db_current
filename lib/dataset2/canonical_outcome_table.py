"""
lib/dataset2/canonical_outcome_table.py

Dataset 2 canonical OUTCOME table -- artifact 2 of the three-artifact
architecture (research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md
§1a). Grain: one row per (`outcome_season`, `player_id`), built from
the real master population -- NEVER from the SBV export alone, so
every predictor-population row gets an explicit eligibility
determination (never a silent absence). NEVER joined into the
canonical predictor table (lib/dataset2/canonical_predictor_table.py)
-- no outcome column lives there, and this module never imports
anything from that one.

FOUR SEPARATE ELIGIBILITY UNIVERSES, per this round's approved
decisions -- explicitly NOT identical to one another:

1. STAR (`star_outcome_eligible`) -- True wherever a real, non-null
   `star_by_value_label` exists. Verified directly:
   `below_production_gate` rows carry a REAL, deliberate label=False
   (labeling.py's own step 2 -- production too low to ever be a Star
   is a determinate fact needing no acquisition-cost resolution at
   all), so they ARE star_outcome_eligible even though they never got
   a numeric score. `sbv_score_available` is a SEPARATE field (True
   only for the narrower adp_scored/minimal_market_cost_scored
   population) precisely so this distinction stays visible -- a
   below-gate row can be star_outcome_eligible=True,
   sbv_score_available=False, `star_by_value_label=False` all at
   once, and that combination is the CORRECT, intended state, not a
   contradiction.

2. PRIMARY BUST (`bust_primary_eligible`) -- position x ADP-range
   conditioned. Requires a REAL, usable fantasy market ADP
   (`overall_adp` non-null) AND `outcome_season >= 2010` (SBV's own
   temporal window, deliberately NOT dropped for this outcome per
   this round's decision). Does NOT require clearing SBV's production
   gate -- the entire point of this correction: 1,381 of the 7,190
   `below_production_gate` rows have real market ADP and are real,
   legitimate bust candidates that SBV's Star methodology structurally
   cannot see. MMC rows (54) are NOT eligible -- they have no real
   ADP-round to place in a peer group. NFL draft capital without a
   real market ADP does NOT establish fantasy acquisition cost and
   does NOT grant eligibility (the 244 real,
   drafted-but-no-market-ADP zero-game rows stay ineligible here,
   reserved for a future, separate prospect-failure diagnostic this
   module does not build).

3. BUST HISTORICAL SENSITIVITY (`bust_historical_sensitivity_eligible`)
   -- SAME real-ADP requirement as primary, WITHOUT the `>= 2010`
   restriction. A named, explicit SENSITIVITY population (the 521
   real pre-2010-ADP rows) -- never mixed into the primary label.

4. UNDERPERFORMANCE DIAGNOSTIC (`underperformance_diagnostic_eligible`)
   -- raw P vs. a real, non-extrapolated E_P. Computed BEFORE any
   production-gate check (per instruction) for
   adp_scored/minimal_market_cost_scored/below_production_gate-with-
   real-ADP. **Three counts, kept distinct, none silently forced to
   match another**:
   - **2,728 = theoretically eligible**: 1,347 scored rows + 1,381
     below_production_gate rows with real fantasy ADP. This is the
     population the extension instruction described -- every row that
     HAS both a real acquisition cost and measurable realized
     production.
   - **2,711 = computationally eligible under the current fitted E_P
     lookup**: of the 2,728 above, 17 below_production_gate real-ADP
     rows have an `adp_round` beyond the real fitted E_P lookup's
     coverage for that (season, position) cell -- the SAME real "out
     of range" condition already found for 2 Star-ineligible rows
     (`unscoreable_expected_production_out_of_range`), just never
     previously checked for this population (SBV's own pipeline never
     computes E_P for gate-failing rows at all, so this gap was
     invisible until this round's extension). Per instruction ("do not
     extrapolate... unless a defensible lookup extension is separately
     approved"), these 17 rows are NOT extrapolated around. **2,711 is
     the real value of `underperformance_diagnostic_eligible.sum()`.**
   - **17 = ineligible only for lookup-coverage reasons**: real ADP
     exists, production is measurable, but the fitted lookup has no
     cell for that (season, position, round) -- reason code
     `expected_production_lookup_out_of_range`, kept a DISTINCT reason
     from `no_usable_fantasy_acquisition_cost` (below), which covers a
     much larger, structurally different group: the 5,809
     `below_production_gate` rows with NO real ADP at all (never
     resolved a fantasy cost in the first place, so there was never a
     round to look up).
   These two ineligibility reasons must never share one string --
   conflating "no cost signal exists" with "a cost signal exists but
   the model doesn't cover it" was a real bug caught and fixed in this
   round (see `_diagnostic_reason()`).

NAMING: `outcome_season` (not `season`), matching the predictor
table's `prediction_season` convention of an explicit, unambiguous id
column rather than a bare `season` that could be confused with a raw
source season.

HISTORY -- bust label values were NOT computed in the first two
rounds this outcome table was built (only eligibility/reason-code
infrastructure existed): no percentile-within-cell threshold or
absolute floor had an approved numeric value yet, and inventing one
would have repeated the mistake this project's history warns against
(research/dataset2/DATASET2_TRAIT_ROADMAP.md's family #9 threshold
rounds, each backed by real-data analysis before any cutoff was
fixed). `research/dataset2/DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md`
did that real-data analysis across two rounds and reached an approved
formula -- **`bust_primary_label` and
`bust_strict_below_replacement_label` are now IMPLEMENTED** (see
below). `bust_historical_sensitivity_label` remains reserved and
always null -- only the primary and strict-below-replacement label
VALUES were approved for implementation this round, not the
historical-sensitivity label.

BUST LABEL COMPUTATION (approved formula, see the proposal doc's §23
for the full real-data justification):

- **Ranking measure**: `score_like = P - SBV_LAMBDA * expected_production`
  ("G-score" -- proposal §19 found real disagreement with the
  raw-P-only alternative ("G-raw") concentrates exactly where
  round-level E_P conditioning is supposed to correct for a coarse
  ADP-bucket's blindness, not near the E_P lookup's coverage edge --
  G-score is the more defensible ranking on that evidence, not merely
  because it was already in use).
- **Peer cells, with a MECHANICAL fallback (proposal §20, "Method 4")**:
  rank within (`position`, ADP bucket [`config.DATASET2_ADP_ROUND_BUCKETS`],
  era [`config.DATASET2_ERA_BOUNDARIES`]) wherever that cell has
  `config.DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE` or more real rows
  (`assignment_method="era_specific_g_score"`); for the smaller real
  sparse cells, fall back to the pooled (`position`, ADP bucket) cell,
  era ignored (`assignment_method="pooled_era_g_score_fallback"`).
  This is a real, disclosed compromise -- three era-aware methods
  compared in the proposal (era-stratified, era-normalized, this
  fallback) all agreed pooling alone over-flags the pre-2011 era, but
  pure era-stratification leaves 10 of 47 real cells too small to rank
  within honestly.
- **E_P-lookup coverage gap (19 real rows: 17 below-gate real-ADP rows
  + 2 already-known `unscoreable_expected_production_out_of_range`)**:
  these have real `P` but no `expected_production` cell, so
  `score_like` cannot be computed. Falls back to a raw-`P` percentile
  within the pooled (`position`, ADP bucket) cell instead (the same
  "G-raw" ranking method proposal §19 evaluated and did not select as
  primary, used ONLY as a fallback for rows G-score structurally
  cannot reach) -- `assignment_method="g_raw_lookup_gap_fallback"`.
- **Zero-game real-ADP rows (proposal §22)**: `games_played == 0`
  within the `bust_primary_eligible` population means `P` cannot be
  computed at all (`production.py` requires non-null `ppg_ppr`,
  undefined at 0 games). Grounded, not asserted: real replacement
  level (`lib.replacement.replacement_level_from_rank()`, the same
  function `production.py` itself calls) is a real, POSITIVE number
  for every position/season in this data -- 0 real recorded points
  across a full season is below ANY positive replacement baseline by
  construction, the worst possible outcome in any peer cell, without
  needing a percentile computation to establish it. Automatic
  `True` for EVERY threshold (primary 20%, both sensitivities, and
  strict-below-replacement) -- `assignment_method="automatic_zero_game"`.
  A general rule keyed on `games_played == 0`, not a player-specific
  override -- real count today is 1 (Isaac Guerendo, 2025 RB), but the
  rule generalizes to any future row meeting the same real condition.
- **Cutoffs**: `bust_primary_label` = bottom 20% (inclusive `<=`,
  `method="average"` percentile rank -- ties, if any ever occur, are
  labeled together, never arbitrarily split). `bust_primary_sensitivity_pct25_label`
  / `bust_primary_sensitivity_pct30_label` = bottom 25%/30%, computed
  from the SAME underlying percentile/assignment-method pipeline as
  the 20% primary -- only the cutoff differs, named as sensitivities
  per instruction, never treated as primary-label candidates.
- **`bust_strict_below_replacement_label`** (explicitly named to be
  unambiguous about its meaning, per instruction -- NOT a
  "SBV-Star-strict" or "high-confidence" label, specifically "primary
  bust AND below replacement level") = `bust_primary_label` (bottom
  20%) AND `P < 0` (real, parameter-free -- `P` is already defined
  relative to replacement level, so `P<0` needs no arbitrary
  percentage floor). Zero-game rows get automatic `True` here too, by
  logical extension of the same replacement-level argument (0 points
  is below any positive replacement baseline, which is exactly the
  condition `P<0` tests for on rows where `P` is computable) -- not
  because `P` was literally computed and found negative.
- **`bust_primary_assignment_method`**: one shared categorical column
  (`era_specific_g_score` / `pooled_era_g_score_fallback` /
  `g_raw_lookup_gap_fallback` / `automatic_zero_game`, or null if
  `bust_primary_eligible` is False) -- describes which ranking
  mechanism produced a row's percentile, shared across
  `bust_primary_label`, both sensitivities, and
  `bust_strict_below_replacement_label`, since all four are cutoffs
  applied to the SAME underlying per-row percentile/rule.

`bust_historical_sensitivity_label` remains RESERVED and always null
this round -- only the primary/strict-below-replacement label VALUES
were approved for implementation; the historical-sensitivity
(pre-2010) population's label was not in scope this round.

`star_by_value_label`, `bust_primary_label`,
`bust_primary_sensitivity_pct25_label`,
`bust_primary_sensitivity_pct30_label`,
`bust_strict_below_replacement_label`,
`bust_historical_sensitivity_label` are all pandas nullable "boolean"
dtype -- a real False/True value is never confusable with a real
<NA> (ineligible for the outcome dimension in question, or -- for
`bust_historical_sensitivity_label` specifically -- "not yet
computed").

TEST SCOPE: tests/test_dataset2_canonical_outcome_table.py proves the
eligibility/reason-code logic (mutual exclusivity, every ineligible
row has exactly one reason, every eligible row has none, the specific
zero-game/MMC/ep-out-of-range cases this round's review named
directly) AND the label-assignment logic (sparse-cell fallback, exact
minimum-cell-size boundary, lookup-gap fallback, zero-game handling,
tie handling, ineligible-null labels, input-order independence,
historical-sensitivity coverage) against synthetic fixtures. Real-data
integration numbers are produced by
scripts/build_dataset2_canonical_outcome_table.py against the real
2006-2025 population.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    DATASET2_ADP_ROUND_BUCKETS,
    DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE,
    DATASET2_ERA_BOUNDARIES,
    SBV_LAMBDA,
)
from lib.dataset2.common import validate_columns
from lib.stars_by_value import expected_production as ep
from lib.stars_by_value import minimal_market_cost as mmc

MASTER_POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position", "overall_adp", "games_played")
SBV_STATUS_REQUIRED_COLUMNS = ("season", "player_id", "star_by_value_status", "star_by_value_score", "star_by_value_label")
PLAYERS_REQUIRED_COLUMNS = ("gsis_id", "draft_round")
EP_LOOKUP_REQUIRED_COLUMNS = ("prediction_season", "position", "draft_round", "expected_production")
PRODUCTION_REQUIRED_COLUMNS = ("season", "player_id", "P")

STATUS_NO_SBV_ROW_FOUND = "no_sbv_row_found"
_SCORED_LABELED_STATUSES = ("adp_scored", "minimal_market_cost_scored")

SBV_FIRST_SCOREABLE_SEASON = 2010

BUST_PRIMARY_PERCENTILE = 0.20
BUST_PRIMARY_SENSITIVITY_PCT25 = 0.25
BUST_PRIMARY_SENSITIVITY_PCT30 = 0.30

ASSIGNMENT_METHOD_ERA_SPECIFIC = "era_specific_g_score"
ASSIGNMENT_METHOD_POOLED_ERA_FALLBACK = "pooled_era_g_score_fallback"
ASSIGNMENT_METHOD_G_RAW_LOOKUP_GAP_FALLBACK = "g_raw_lookup_gap_fallback"
ASSIGNMENT_METHOD_AUTOMATIC_ZERO_GAME = "automatic_zero_game"

OUTCOME_OUTPUT_COLUMNS = (
    "outcome_season",
    "player_id",
    "position",
    "real_status",
    "has_real_market_adp",
    "adp_round",
    "star_outcome_eligible",
    "star_outcome_ineligibility_reason",
    "star_by_value_label",
    "sbv_score_available",
    "star_by_value_score",
    "bust_primary_eligible",
    "bust_primary_ineligibility_reason",
    "bust_primary_assignment_method",
    "bust_primary_label",
    "bust_primary_sensitivity_pct25_label",
    "bust_primary_sensitivity_pct30_label",
    "bust_strict_below_replacement_eligible",
    "bust_strict_below_replacement_ineligibility_reason",
    "bust_strict_below_replacement_label",
    "bust_historical_sensitivity_eligible",
    "bust_historical_sensitivity_ineligibility_reason",
    "bust_historical_sensitivity_label",
    "underperformance_diagnostic_eligible",
    "underperformance_diagnostic_ineligibility_reason",
    "underperformance_diagnostic_value",
)


def _adp_bucket(adp_round):
    if pd.isna(adp_round):
        return None
    for label, lo, hi in DATASET2_ADP_ROUND_BUCKETS:
        if adp_round >= lo and (hi is None or adp_round <= hi):
            return label
    return None


def _era_label(season):
    b1, b2 = DATASET2_ERA_BOUNDARIES
    if season < b1:
        return f"pre-{b1}"
    if season < b2:
        return f"{b1}-{b2 - 1}"
    return f"{b2}+"


def _star_reason(real_status: str) -> str:
    return {
        "out_of_scope": "out_of_scope_temporal_window",
        "unscoreable_drafted_adp_missing": "acquisition_cost_unresolved_drafted",
        "unscoreable_ambiguous": "acquisition_cost_unresolved_ambiguous",
        "unscoreable_expected_production_out_of_range": "expected_production_lookup_out_of_range",
        STATUS_NO_SBV_ROW_FOUND: "zero_games_excluded_from_sbv_population",
    }[real_status]


def _bust_reason(real_status: str, has_real_adp: bool, is_drafted: bool, pre_2010_relevant: bool) -> str:
    """Shared reason logic for bust_primary/bust_historical_sensitivity
    -- `pre_2010_relevant` distinguishes the two (primary treats a real
    pre-2010 ADP row as ineligible-for-a-real-reason; historical
    sensitivity has already granted it eligibility, so this branch
    never fires there)."""
    if has_real_adp and pre_2010_relevant:
        return "pre_2010_temporal_window_real_adp"
    if real_status == "minimal_market_cost_scored":
        return "mmc_no_real_adp_round_peer_group"
    if real_status == "unscoreable_drafted_adp_missing":
        return "acquisition_cost_unresolved_drafted"
    if real_status == "unscoreable_ambiguous":
        return "acquisition_cost_unresolved_ambiguous"
    if real_status == "below_production_gate":
        return "no_real_fantasy_adp_below_production_gate"
    if real_status == "out_of_scope":
        return "no_real_fantasy_adp_pre_2010"
    if real_status == STATUS_NO_SBV_ROW_FOUND:
        return "zero_games_nfl_draft_capital_not_fantasy_adp" if is_drafted else "zero_games_no_valid_cost_signal"
    raise ValueError(f"Unhandled real_status for bust reason: {real_status!r}")


def _assign_bust_primary_labels(out: pd.DataFrame) -> pd.DataFrame:
    """Implements the approved bust-label formula (proposal doc §23) on
    a copy of `out`. Requires `bust_primary_eligible`, `score_like`,
    `P`, `position`, `adp_round`, `outcome_season`, `games_played`
    already present. Adds `bust_primary_assignment_method`,
    `bust_primary_label`, `bust_primary_sensitivity_pct25_label`,
    `bust_primary_sensitivity_pct30_label`, and
    `bust_strict_below_replacement_label`.

    Four assignment methods, in priority order:
    1. `automatic_zero_game` -- `games_played == 0` within the eligible
       population. `P` is undefined (`production.py` requires non-null
       `ppg_ppr`); labeled True at every threshold by the real,
       grounded replacement-level argument in the module docstring,
       never by a percentile computation.
    2. `era_specific_g_score` -- `score_like` available AND this row's
       real (position, ADP bucket, era) cell has
       `DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE` or more real rows.
    3. `pooled_era_g_score_fallback` -- `score_like` available but the
       row's era-specific cell is too small; ranked instead within the
       pooled (position, ADP bucket) cell, era ignored. A mechanical,
       pre-specified rule (§20's "Method 4"), never a per-row judgment
       call.
    4. `g_raw_lookup_gap_fallback` -- `score_like` unavailable (no
       fitted E_P cell for this row's season/position/round) but `P`
       is real; ranked on raw `P` within the pooled (position, ADP
       bucket) cell, using the SAME real reference population as method
       3 pools from (all eligible rows with real `P`), not just the
       gap rows themselves.

    Any remaining eligible row (P also null, games_played != 0) is an
    undocumented real-data gap outside all four mechanisms above --
    left with a null assignment method and a null label rather than
    silently guessed. Verified empty against the real 2006-2025
    population by `scripts/build_dataset2_canonical_outcome_table.py`.
    """
    out = out.copy()
    out["_adp_bucket"] = out["adp_round"].apply(_adp_bucket)
    out["_era"] = out["outcome_season"].apply(_era_label)

    eligible = out["bust_primary_eligible"].astype(bool)
    zero_game = eligible & (out["games_played"] == 0)
    has_score = eligible & ~zero_game & out["score_like"].notna()
    lookup_gap = eligible & ~zero_game & ~has_score & out["P"].notna()

    pct_final = pd.Series(pd.NA, index=out.index, dtype="Float64")
    assignment_method = pd.Series(pd.NA, index=out.index, dtype="object")

    # --- Methods 2/3: era-specific G-score, mechanical fallback to pooled ---
    sub = out.loc[has_score, ["position", "_adp_bucket", "_era", "score_like"]].copy()
    sub["_era_cell_n"] = sub.groupby(["position", "_adp_bucket", "_era"])["score_like"].transform("size")
    sub["_pct_era"] = sub.groupby(["position", "_adp_bucket", "_era"])["score_like"].rank(pct=True, method="average", ascending=True)
    sub["_pct_pooled"] = sub.groupby(["position", "_adp_bucket"])["score_like"].rank(pct=True, method="average", ascending=True)
    era_ok = sub["_era_cell_n"] >= DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE
    pct_final.loc[sub.index] = sub["_pct_era"].where(era_ok, sub["_pct_pooled"])
    assignment_method.loc[sub.index] = pd.Series(ASSIGNMENT_METHOD_ERA_SPECIFIC, index=sub.index).where(
        era_ok, ASSIGNMENT_METHOD_POOLED_ERA_FALLBACK
    )

    # --- Method 4: raw-P fallback for the E_P-lookup coverage gap,
    # ranked within the SAME real pooled reference population every
    # eligible real-P row belongs to (not just the gap rows). ---
    raw_pop = out.loc[eligible & out["P"].notna(), ["position", "_adp_bucket", "P"]].copy()
    raw_pop["_pct_raw_pooled"] = raw_pop.groupby(["position", "_adp_bucket"])["P"].rank(pct=True, method="average", ascending=True)
    pct_final.loc[lookup_gap] = raw_pop.loc[lookup_gap, "_pct_raw_pooled"]
    assignment_method.loc[lookup_gap] = ASSIGNMENT_METHOD_G_RAW_LOOKUP_GAP_FALLBACK

    # --- Method 1: automatic zero-game rule -- bypasses pct_final entirely ---
    assignment_method.loc[zero_game] = ASSIGNMENT_METHOD_AUTOMATIC_ZERO_GAME

    out["bust_primary_assignment_method"] = assignment_method

    def _cutoff_label(cutoff: float) -> pd.Series:
        lbl = pd.Series(pd.NA, index=out.index, dtype="boolean")
        has_pct = eligible & pct_final.notna()
        lbl.loc[has_pct] = (pct_final.loc[has_pct] <= cutoff).astype("boolean")
        lbl.loc[zero_game] = True
        return lbl

    out["bust_primary_label"] = _cutoff_label(BUST_PRIMARY_PERCENTILE)
    out["bust_primary_sensitivity_pct25_label"] = _cutoff_label(BUST_PRIMARY_SENSITIVITY_PCT25)
    out["bust_primary_sensitivity_pct30_label"] = _cutoff_label(BUST_PRIMARY_SENSITIVITY_PCT30)

    # --- Strict-below-replacement: primary(20%) AND P<0, with the
    # zero-game logical extension (see module docstring) -- computed
    # explicitly only over the eligible population so nullable-boolean
    # Kleene logic (NA & False == False) never leaks a False into an
    # ineligible row. ---
    strict = pd.Series(pd.NA, index=out.index, dtype="boolean")
    non_zero_eligible = eligible & ~zero_game
    strict.loc[non_zero_eligible] = (
        out.loc[non_zero_eligible, "bust_primary_label"].astype("boolean") & (out.loc[non_zero_eligible, "P"] < 0)
    )
    strict.loc[zero_game] = True
    out["bust_strict_below_replacement_label"] = strict

    return out.drop(columns=["_adp_bucket", "_era"])


def build_canonical_outcome_table(
    master_population: pd.DataFrame,
    sbv_status: pd.DataFrame,
    players_df: pd.DataFrame,
    ep_lookup: pd.DataFrame,
    production_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Builds the canonical outcome table -- one row per (outcome_season,
    player_id), every OUTCOME_OUTPUT_COLUMNS field. `master_population`
    is the SAME real 2006-2025 population the predictor table's spine
    is built from (never the family #9 "future" 2026 extension --
    outcome data cannot exist for a season with no real games played
    yet). `production_df` must be the caller's own real call to
    `lib.stars_by_value.production.compute_production()` -- this
    module never reads a weekly file itself, consistent with every
    other Dataset 2 module's "caller assembles inputs" convention.
    `ep_lookup` must be the real, already-fitted expected-production
    lookup table (`data/processed/sbv_expected_production_lookup.parquet`)
    -- this module only JOINS against it (never extrapolates a value
    for a cell that doesn't exist, see module docstring).
    """
    validate_columns(master_population, MASTER_POPULATION_REQUIRED_COLUMNS, "master_population")
    validate_columns(sbv_status, SBV_STATUS_REQUIRED_COLUMNS, "sbv_status")
    validate_columns(players_df, PLAYERS_REQUIRED_COLUMNS, "players_df")
    validate_columns(ep_lookup, EP_LOOKUP_REQUIRED_COLUMNS, "ep_lookup")
    validate_columns(production_df, PRODUCTION_REQUIRED_COLUMNS, "production_df")

    base = master_population[list(MASTER_POPULATION_REQUIRED_COLUMNS)].drop_duplicates(
        subset=["season", "player_id"]
    ).rename(columns={"season": "outcome_season"})

    sbv = sbv_status[list(SBV_STATUS_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).rename(
        columns={"season": "outcome_season"}
    )

    out = base.merge(sbv, on=["outcome_season", "player_id"], how="left")
    out["real_status"] = out["star_by_value_status"].fillna(STATUS_NO_SBV_ROW_FOUND)
    out["has_real_market_adp"] = out["overall_adp"].notna()
    out["adp_round"] = out["overall_adp"].apply(ep.adp_round)

    out = out.merge(
        players_df[list(PLAYERS_REQUIRED_COLUMNS)].drop_duplicates(subset=["gsis_id"]),
        left_on="player_id", right_on="gsis_id", how="left",
    )
    out["_is_drafted"] = out["draft_round"].notna()

    # --- 1. Star outcome ---
    out["star_by_value_label"] = out["star_by_value_label"].map({0: False, 1: True, 0.0: False, 1.0: True}).astype("boolean")
    out["star_outcome_eligible"] = out["star_by_value_label"].notna()
    out["star_outcome_ineligibility_reason"] = out["real_status"].where(~out["star_outcome_eligible"]).apply(
        lambda s: _star_reason(s) if pd.notna(s) else None
    )
    out["sbv_score_available"] = out["real_status"].isin(_SCORED_LABELED_STATUSES).astype("boolean")

    # --- 2. E_P + P, merged once, shared by the bust labels below AND
    # the underperformance diagnostic (§4) -- computed BEFORE any
    # production-gate check, per instruction. ---
    ep_small = ep_lookup[["prediction_season", "position", "draft_round", "expected_production"]].rename(
        columns={"prediction_season": "outcome_season", "draft_round": "adp_round"}
    )
    out = out.merge(ep_small, on=["outcome_season", "position", "adp_round"], how="left")

    mmc_mask = out["real_status"] == "minimal_market_cost_scored"
    out.loc[mmc_mask, "expected_production"] = out.loc[mmc_mask].apply(
        lambda r: mmc.minimal_market_cost_expected_production(r["position"], r["outcome_season"]), axis=1
    )

    out = out.merge(
        production_df[list(PRODUCTION_REQUIRED_COLUMNS)].rename(columns={"season": "outcome_season"}),
        on=["outcome_season", "player_id"], how="left",
    )
    out["score_like"] = out["P"] - SBV_LAMBDA * out["expected_production"]

    # --- 3. Primary bust + strict-below-replacement + historical
    # sensitivity: eligibility, then the approved label formula. ---
    out["bust_primary_eligible"] = (out["has_real_market_adp"] & (out["outcome_season"] >= SBV_FIRST_SCOREABLE_SEASON)).astype("boolean")
    out["bust_historical_sensitivity_eligible"] = out["has_real_market_adp"].astype("boolean")
    out["bust_strict_below_replacement_eligible"] = out["bust_primary_eligible"]

    out["bust_primary_ineligibility_reason"] = out.apply(
        lambda r: None if r["bust_primary_eligible"] else _bust_reason(
            r["real_status"], bool(r["has_real_market_adp"]), bool(r["_is_drafted"]), pre_2010_relevant=True
        ),
        axis=1,
    )
    out["bust_strict_below_replacement_ineligibility_reason"] = out["bust_primary_ineligibility_reason"]
    out["bust_historical_sensitivity_ineligibility_reason"] = out.apply(
        lambda r: None if r["bust_historical_sensitivity_eligible"] else _bust_reason(
            r["real_status"], bool(r["has_real_market_adp"]), bool(r["_is_drafted"]), pre_2010_relevant=False
        ),
        axis=1,
    )

    out = _assign_bust_primary_labels(out)

    # Reserved, not computed this round -- historical-sensitivity label
    # values were not in scope this round, only its eligibility. See
    # module docstring.
    out["bust_historical_sensitivity_label"] = pd.Series(pd.NA, index=out.index, dtype="boolean")

    diagnostic_candidate = out["real_status"].isin(("adp_scored", "minimal_market_cost_scored", "below_production_gate"))
    out["underperformance_diagnostic_eligible"] = (
        diagnostic_candidate & out["expected_production"].notna() & out["P"].notna()
    ).astype("boolean")
    out["underperformance_diagnostic_value"] = (out["P"] - out["expected_production"]).where(
        out["underperformance_diagnostic_eligible"]
    )

    def _diagnostic_reason(row):
        if row["underperformance_diagnostic_eligible"]:
            return None
        # A row already carrying the real, known ep_out_of_range status
        # gets that exact reason regardless of whether it's structurally
        # inside diagnostic_candidate -- it's the same real cause as the
        # generic within-candidate out-of-range case just below.
        if row["real_status"] == "unscoreable_expected_production_out_of_range":
            return "expected_production_lookup_out_of_range"
        if row["real_status"] not in ("adp_scored", "minimal_market_cost_scored", "below_production_gate"):
            return "outside_diagnostic_population"
        # Within the candidate population, a missing E_P has two distinct
        # real causes that must not share one reason code: no real
        # fantasy ADP to look up at all (the below_production_gate rows
        # SBV itself never resolves a cost for), versus a real ADP whose
        # round genuinely falls outside the fitted lookup's coverage for
        # that (season, position) cell.
        if not row["has_real_market_adp"]:
            return "no_usable_fantasy_acquisition_cost"
        if pd.isna(row["expected_production"]):
            return "expected_production_lookup_out_of_range"
        return "production_composite_unavailable"

    out["underperformance_diagnostic_ineligibility_reason"] = out.apply(_diagnostic_reason, axis=1)

    return out[list(OUTCOME_OUTPUT_COLUMNS)].reset_index(drop=True)
