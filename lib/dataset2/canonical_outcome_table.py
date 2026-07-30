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
   real-ADP. **REAL DISCREPANCY FOUND AND DISCLOSED, not silently
   forced to match an earlier estimate**: of the 1,381
   below_production_gate real-ADP rows, 17 have an `adp_round` beyond
   the real fitted E_P lookup's coverage for that (season, position)
   cell -- the SAME real "out of range" condition already found for 2
   Star-ineligible rows, just never previously checked for this
   population (SBV's own pipeline never computes E_P for gate-failing
   rows at all, so this gap was invisible until this round's
   extension). Per instruction ("do not extrapolate... unless a
   defensible lookup extension is separately approved"), these 17
   rows are NOT extrapolated around -- they get the same
   `expected_production_lookup_out_of_range` reason as the original 2.
   REAL eligible count is therefore **2,711** (1,293 + 54 + 1,364), not
   2,728 (1,293 + 54 + 1,381) -- the 17-row gap is a genuine finding,
   not an error to paper over.

NAMING: `outcome_season` (not `season`), matching the predictor
table's `prediction_season` convention of an explicit, unambiguous id
column rather than a bare `season` that could be confused with a raw
source season.

BUST LABEL VALUES (`bust_primary_label`, `bust_strict_label`,
`bust_historical_sensitivity_label`) ARE NOT COMPUTED THIS ROUND --
every eligibility/reason-code field above is fully specified and
implemented, but the actual PERCENTILE-WITHIN-CELL threshold for
definition G (and the additional absolute floor for definition I, the
strict-hybrid) has never been given an approved numeric value in any
round of this project -- only the STRUCTURE ("position x ADP-range
conditioned percentile", "G plus an absolute shortfall floor") was
approved. Inventing a number here would repeat exactly the mistake
this project's own history warns against (see
research/dataset2/DATASET2_TRAIT_ROADMAP.md's family #9 threshold
rounds, each backed by real-data analysis before any cutoff was
fixed). These three label columns are present (per instruction) but
always null this round -- reserved for a follow-up round once a real
percentile/floor is proposed and approved with real-data support, the
same "reserve the name, don't invent the value" pattern already used
in this project for `opportunity_qualified`/`workload_qualified`.

`star_by_value_label`, `bust_primary_label`, `bust_strict_label`,
`bust_historical_sensitivity_label` are all pandas nullable "boolean"
dtype -- a real False/True value is never confusable with a real
<NA> (ineligible, or -- for the three bust labels this round --
"threshold not yet approved").

TEST SCOPE: tests/test_dataset2_canonical_outcome_table.py proves the
eligibility/reason-code logic (mutual exclusivity, every ineligible
row has exactly one reason, every eligible row has none, the specific
zero-game/MMC/ep-out-of-range cases this round's review named
directly) against synthetic fixtures. Real-data integration numbers
are produced by
scripts/build_dataset2_canonical_outcome_table.py against the real
2006-2025 population.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import validate_columns
from lib.stars_by_value import expected_production as ep
from lib.stars_by_value import minimal_market_cost as mmc

MASTER_POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position", "overall_adp")
SBV_STATUS_REQUIRED_COLUMNS = ("season", "player_id", "star_by_value_status", "star_by_value_score", "star_by_value_label")
PLAYERS_REQUIRED_COLUMNS = ("gsis_id", "draft_round")
EP_LOOKUP_REQUIRED_COLUMNS = ("prediction_season", "position", "draft_round", "expected_production")
PRODUCTION_REQUIRED_COLUMNS = ("season", "player_id", "P")

STATUS_NO_SBV_ROW_FOUND = "no_sbv_row_found"
_SCORED_LABELED_STATUSES = ("adp_scored", "minimal_market_cost_scored")

SBV_FIRST_SCOREABLE_SEASON = 2010

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
    "bust_primary_label",
    "bust_strict_eligible",
    "bust_strict_ineligibility_reason",
    "bust_strict_label",
    "bust_historical_sensitivity_eligible",
    "bust_historical_sensitivity_ineligibility_reason",
    "bust_historical_sensitivity_label",
    "underperformance_diagnostic_eligible",
    "underperformance_diagnostic_ineligibility_reason",
    "underperformance_diagnostic_value",
)


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

    # --- 2/3. Primary bust + historical sensitivity ---
    out["bust_primary_eligible"] = (out["has_real_market_adp"] & (out["outcome_season"] >= SBV_FIRST_SCOREABLE_SEASON)).astype("boolean")
    out["bust_historical_sensitivity_eligible"] = out["has_real_market_adp"].astype("boolean")
    out["bust_strict_eligible"] = out["bust_primary_eligible"]

    out["bust_primary_ineligibility_reason"] = out.apply(
        lambda r: None if r["bust_primary_eligible"] else _bust_reason(
            r["real_status"], bool(r["has_real_market_adp"]), bool(r["_is_drafted"]), pre_2010_relevant=True
        ),
        axis=1,
    )
    out["bust_strict_ineligibility_reason"] = out["bust_primary_ineligibility_reason"]
    out["bust_historical_sensitivity_ineligibility_reason"] = out.apply(
        lambda r: None if r["bust_historical_sensitivity_eligible"] else _bust_reason(
            r["real_status"], bool(r["has_real_market_adp"]), bool(r["_is_drafted"]), pre_2010_relevant=False
        ),
        axis=1,
    )

    # Reserved, not computed this round -- see module docstring.
    out["bust_primary_label"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out["bust_strict_label"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out["bust_historical_sensitivity_label"] = pd.Series(pd.NA, index=out.index, dtype="boolean")

    # --- 4. Underperformance diagnostic (raw P vs. E_P, computed
    # BEFORE any production-gate check) ---
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
            return "no_real_fantasy_adp_below_production_gate"
        if pd.isna(row["expected_production"]):
            return "expected_production_lookup_out_of_range"
        return "production_composite_unavailable"

    out["underperformance_diagnostic_ineligibility_reason"] = out.apply(_diagnostic_reason, axis=1)

    return out[list(OUTCOME_OUTPUT_COLUMNS)].reset_index(drop=True)
