"""
lib/stars_by_value/labeling.py

The Stars-by-Value wiring layer: the four-step processing order
(methodology section 11, settled) that turns a player-season row into
a final status/provenance/score/label, calling the already-built
modules from Commits 5-8 -- never duplicating their formulas or
classification logic.

THE FOUR STEPS, IN STRICT ORDER (never reordered, never short-circuited
differently):
  1. Temporal/study-scope eligibility. season < SBV_FIRST_SCOREABLE_SEASON,
     or position outside SBV_POSITIONS, or games_played < 1 ->
     out_of_scope, label=NULL, BOTH thresholds NULL. A pre-2010 row is
     caught HERE and returns immediately -- it never reaches step 2's
     production-gate check and never reaches step 3's acquisition-cost
     logic. This is a hard, structural guarantee (an early return, not
     a downstream filter), directly protecting the settled invariant
     "below_production_gate is therefore only ever assigned to 2010+
     rows, never earlier ones."
  2. Production gate. Only reached by rows that passed step 1. P (the
     production composite -- already computed upstream by
     production.py, NOT recomputed here) below the position's p82.5
     floor -> below_production_gate, label=0, score=NULL, gate
     threshold populated, Star threshold NULL (it was never a live
     question for this row). Gate-failing rows return here and never
     reach step 3 -- acquisition-cost logic is never invoked for them.
  3. Acquisition-cost resolution. Only reached by gate-clearing rows.
     matched_clean -> real E_P lookup (expected_production.py's
     already-validated table) -> adp_scored. matched_needs_review ->
     unscoreable_adp_needs_review (both thresholds populated,
     score/label NULL -- the bar is known, the score to compare
     against it isn't). no_adp_match -> delegates entirely to
     acquisition_cost.py's classify_row() (which itself handles the
     rookie-QB depth-chart correction, MFL corroboration, and the 2010
     fallback including the Vick exception) -> minimal_market_cost_scored
     (E_P from minimal_market_cost.py), unscoreable_drafted_adp_missing,
     or unscoreable_ambiguous. A 2010 usable_adp override is the one
     exception: it supplies a real adp_round and the row is treated as
     adp_scored from that point on, not as an acquisition-cost
     "unscoreable" outcome.
  4. Score and label. Only for the two scoreable statuses from step 3
     (adp_scored, minimal_market_cost_scored): score = P - SBV_LAMBDA * E_P
     (methodology section 6/10, settled -- NOT duplicated anywhere
     else in this codebase, computed here for the first time since no
     other module owns the final composite). label = 1 if
     score >= SBV_STAR_THRESHOLD[position] else 0 -- exact >=, not >.
     Every other status gets score=NULL, label=NULL (except
     below_production_gate, handled entirely in step 2).

THIS MODULE DOES NOT: recompute P (production.py's job, already done
upstream), refit E_P (expected_production.py's job -- this module only
reads the already-materialized, already-validated lookup table),
re-derive the acquisition-cost classifier or MFL corroboration
(acquisition_cost.py's job, called as a black box), or recompute the
MMC expectation formula (minimal_market_cost.py's job, called as a
black box). It also never writes any output file -- that's a later,
separate commit's job (end-to-end pipeline wiring).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    SBV_FIRST_SCOREABLE_SEASON,
    SBV_LAMBDA,
    SBV_POSITIONS,
    SBV_PRODUCTION_GATE_FLOOR,
    SBV_STAR_THRESHOLD,
    SBV_STATUSES,
    SBV_PROVENANCE_TYPES,
)
from lib.stars_by_value import acquisition_cost as ac
from lib.stars_by_value import expected_production as ep
from lib.stars_by_value import minimal_market_cost as mmc

# --- Statuses: reuse acquisition_cost.py's constants where they overlap,
# define the rest locally. All validated against config.SBV_STATUSES /
# SBV_PROVENANCE_TYPES by tests, not at runtime (avoids an import-time
# dependency cycle risk and matches acquisition_cost.py's own convention).
STATUS_ADP_SCORED = "adp_scored"
STATUS_UNSCOREABLE_ADP_NEEDS_REVIEW = "unscoreable_adp_needs_review"
STATUS_MMC_SCORED = ac.STATUS_MMC
STATUS_DRAFTED_MISSING = ac.STATUS_DRAFTED_MISSING
STATUS_AMBIGUOUS = ac.STATUS_AMBIGUOUS
STATUS_BELOW_PRODUCTION_GATE = "below_production_gate"
STATUS_OUT_OF_SCOPE = "out_of_scope"

PROVENANCE_ADP_MATCHED_CLEAN = "adp_matched_clean"
PROVENANCE_ADP_MATCHED_NEEDS_REVIEW = "adp_matched_needs_review"
PROVENANCE_MMC_CORROBORATED = ac.PROVENANCE_MMC_CORROBORATED
PROVENANCE_MMC_2010_OVERRIDE = ac.PROVENANCE_MMC_2010_OVERRIDE
PROVENANCE_DRAFTED_UNRESOLVED = ac.PROVENANCE_DRAFTED_UNRESOLVED
PROVENANCE_AMBIGUOUS_DISAGREEMENT = ac.PROVENANCE_AMBIGUOUS_DISAGREEMENT
PROVENANCE_BELOW_PRODUCTION_GATE = "below_production_gate"
PROVENANCE_OUT_OF_SCOPE_NON_SKILL_POSITION = "out_of_scope_non_skill_position"
PROVENANCE_OUT_OF_SCOPE_TEMPORAL_WINDOW = "out_of_scope_temporal_window"
PROVENANCE_OUT_OF_SCOPE_INSUFFICIENT_PARTICIPATION = "out_of_scope_insufficient_participation"

_SCOREABLE_STATUSES = (STATUS_ADP_SCORED, STATUS_MMC_SCORED)

OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "star_by_value_status",
    "star_by_value_provenance_type",
    "star_by_value_score",
    "star_by_value_label",
    "star_by_value_production_gate_threshold",
    "star_by_value_threshold",
)


def _lookup_expected_production(lookup_df: pd.DataFrame, season: int, position: str, draft_round: int) -> float:
    match = lookup_df[
        (lookup_df["prediction_season"] == season)
        & (lookup_df["position"] == position)
        & (lookup_df["draft_round"] == draft_round)
    ]
    if match.empty:
        raise ValueError(
            f"No E_P lookup entry for (prediction_season={season}, position={position!r}, "
            f"draft_round={draft_round}) -- expected_production_lookup is missing this cell."
        )
    return float(match.iloc[0]["expected_production"])


def _result(season, player_id, status, provenance, score, label, gate_threshold, star_threshold) -> dict:
    return {
        "season": season,
        "player_id": player_id,
        "star_by_value_status": status,
        "star_by_value_provenance_type": provenance,
        "star_by_value_score": score,
        "star_by_value_label": label,
        "star_by_value_production_gate_threshold": gate_threshold,
        "star_by_value_threshold": star_threshold,
    }


def assign_sbv_status(
    row: dict,
    expected_production_lookup: pd.DataFrame,
    players_df: pd.DataFrame = None,
    history_df: pd.DataFrame = None,
    depth_chart_df=None,
    mfl_adp_response=None,
    mfl_players_response=None,
    overrides_2010_df: pd.DataFrame = None,
    schedule_df=None,
) -> dict:
    """Runs the four-step process for one row. `row` must have: season,
    player_id, player_name, position, games_played, P (production
    composite, already computed upstream), data_quality_flag
    ("matched_clean" | "matched_needs_review" | "no_adp_match"),
    adp_round (required only for matched_clean rows). `row["team"]` is
    read and passed through ONLY for season==2025 rows reaching
    acquisition_cost.classify_row() (see that function's own
    docstring) -- absent/None for every other row, harmlessly ignored.
    Does NOT validate expected_production_lookup itself -- see
    label_rows(), which validates it exactly once before calling this
    per row."""
    season = row["season"]
    player_id = row["player_id"]
    position = row["position"]
    games_played = row["games_played"]

    # --- Step 1: temporal/study-scope eligibility ---
    if season < SBV_FIRST_SCOREABLE_SEASON:
        return _result(season, player_id, STATUS_OUT_OF_SCOPE, PROVENANCE_OUT_OF_SCOPE_TEMPORAL_WINDOW, None, None, None, None)
    if position not in SBV_POSITIONS:
        return _result(season, player_id, STATUS_OUT_OF_SCOPE, PROVENANCE_OUT_OF_SCOPE_NON_SKILL_POSITION, None, None, None, None)
    if games_played < 1:
        return _result(season, player_id, STATUS_OUT_OF_SCOPE, PROVENANCE_OUT_OF_SCOPE_INSUFFICIENT_PARTICIPATION, None, None, None, None)

    # --- Step 2: production gate -- only in-scope rows reach here ---
    gate_floor = SBV_PRODUCTION_GATE_FLOOR[position]
    P = row["P"]
    if P < gate_floor:
        return _result(season, player_id, STATUS_BELOW_PRODUCTION_GATE, PROVENANCE_BELOW_PRODUCTION_GATE, None, 0, gate_floor, None)

    # --- Step 3: acquisition-cost resolution -- only gate-clearing rows reach here ---
    data_quality_flag = row["data_quality_flag"]
    e_p = None

    if data_quality_flag == "matched_clean":
        status, provenance = STATUS_ADP_SCORED, PROVENANCE_ADP_MATCHED_CLEAN
        e_p = _lookup_expected_production(expected_production_lookup, season, position, int(row["adp_round"]))

    elif data_quality_flag == "matched_needs_review":
        status, provenance = STATUS_UNSCOREABLE_ADP_NEEDS_REVIEW, PROVENANCE_ADP_MATCHED_NEEDS_REVIEW

    else:  # no_adp_match -- delegate entirely to acquisition_cost.py
        if season == 2010:
            ac_result = ac.classify_row(
                season, player_id, row["player_name"], position, players_df, history_df,
                overrides_2010_df=overrides_2010_df,
            )
        else:
            # row.get("team") works identically for a dict or a pandas
            # Series (label_rows() passes rows via .iterrows()) --
            # returns None if absent, harmless for every non-2025 row.
            ac_result = ac.classify_row(
                season, player_id, row["player_name"], position, players_df, history_df,
                depth_chart_df=depth_chart_df, mfl_adp_response=mfl_adp_response,
                mfl_players_response=mfl_players_response,
                team=row.get("team"), schedule_df=schedule_df,
            )

        if ac_result["status"] is None:
            # 2010 usable_adp override -- exits to the normal adp_scored
            # path with the override-supplied round, not an
            # acquisition-cost "unscoreable" outcome. IMPLEMENTATION
            # INTERPRETATION, NOT A SETTLED SPEC: the override schema
            # settles the STATUS (adp_scored), but neither
            # STARS_BY_VALUE_METHODOLOGY.md nor the implementation plan
            # ever specified a PROVENANCE value for this path, and the
            # 10-value enum has no dedicated one distinguishing this
            # from a real canonical-source match. adp_matched_clean is
            # used as the closest existing fit -- documented explicitly
            # (not left implicit) in STARS_BY_VALUE_METHODOLOGY.md's
            # 2010-cohort section, flagged there for review if this
            # path is ever exercised against a real row (zero today).
            status, provenance = STATUS_ADP_SCORED, PROVENANCE_ADP_MATCHED_CLEAN
            e_p = _lookup_expected_production(expected_production_lookup, season, position, int(ac_result["adp_round"]))
        elif ac_result["status"] == STATUS_MMC_SCORED:
            status, provenance = ac_result["status"], ac_result["provenance"]
            e_p = mmc.minimal_market_cost_expected_production(position, season)
        else:
            status, provenance = ac_result["status"], ac_result["provenance"]

    # --- Step 4: score and label -- only for the two scoreable statuses ---
    star_threshold = SBV_STAR_THRESHOLD[position]
    if status in _SCOREABLE_STATUSES:
        score = P - SBV_LAMBDA * e_p
        label = 1 if score >= star_threshold else 0
    else:
        score, label = None, None

    return _result(season, player_id, status, provenance, score, label, gate_floor, star_threshold)


def label_rows(
    rows: pd.DataFrame,
    expected_production_lookup: pd.DataFrame,
    players_df: pd.DataFrame = None,
    history_df: pd.DataFrame = None,
    depth_charts_by_season: dict = None,
    mfl_adp_by_season: dict = None,
    mfl_players_by_season: dict = None,
    overrides_2010_df: pd.DataFrame = None,
    schedule_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """Validates expected_production_lookup EXACTLY ONCE, then runs
    assign_sbv_status() per row. depth_charts_by_season /
    mfl_adp_by_season / mfl_players_by_season are dicts keyed by
    season, since acquisition_cost.py's inputs are fetched per season,
    not per row -- avoids re-fetching or re-passing the same season's
    data for every row that season. schedule_df is a SINGLE, all-seasons
    frame (nflverse_source.fetch_schedules()'s shape), not season-keyed
    -- only consulted for season==2025 rows whose classifier_bucket
    reaches the rookie-QB depth-chart correction; harmlessly unused
    otherwise."""
    ep.validate_lookup(expected_production_lookup)

    depth_charts_by_season = depth_charts_by_season or {}
    mfl_adp_by_season = mfl_adp_by_season or {}
    mfl_players_by_season = mfl_players_by_season or {}

    results = []
    for _, row in rows.iterrows():
        season = row["season"]
        results.append(
            assign_sbv_status(
                row,
                expected_production_lookup,
                players_df=players_df,
                history_df=history_df,
                depth_chart_df=depth_charts_by_season.get(season),
                mfl_adp_response=mfl_adp_by_season.get(season),
                mfl_players_response=mfl_players_by_season.get(season),
                overrides_2010_df=overrides_2010_df,
                schedule_df=schedule_df,
            )
        )

    out = pd.DataFrame(results, columns=list(OUTPUT_COLUMNS))
    out["star_by_value_label"] = out["star_by_value_label"].astype("Int8")
    out["star_by_value_status"] = out["star_by_value_status"].astype("category")
    out["star_by_value_provenance_type"] = out["star_by_value_provenance_type"].astype("category")
    return out
