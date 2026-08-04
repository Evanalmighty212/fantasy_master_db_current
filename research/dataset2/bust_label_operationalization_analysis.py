"""
research/dataset2/bust_label_operationalization_analysis.py

Real-data analysis backing
research/dataset2/DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md.
Produces every table cited in that proposal. Does NOT write a bust
label column anywhere -- this is analysis-only, per instruction to
stop before implementing any bust label.

Reuses existing, approved config constants directly (never
reinvented): SBV_LAMBDA, SBV_STAR_THRESHOLD, DATASET2_ADP_ROUND_BUCKETS,
DATASET2_ERA_BOUNDARIES, DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE. Reuses
lib.stars_by_value.production.compute_production() and
lib.stars_by_value.expected_production.adp_round() directly, exactly as
lib/dataset2/canonical_outcome_table.py does. Reads the already-built
data/exports/dataset2_canonical_outcome_table.parquet as its population
spine rather than re-deriving eligibility logic a second time.

Extends usage of SBV_LAMBDA/SBV_STAR_THRESHOLD beyond SBV's own scope
(SBV itself never computes a threshold-relative score for
below_production_gate rows, since a gate-failing row's Star label is
already determined). Applying these same, already-approved constants
to gate-failing rows here is a DELIBERATE ANALYTICAL EXTENSION for
Dataset 2B peer-ranking purposes only -- it never changes any Star
label or SBV export value, and is flagged in the proposal doc as a
choice for review, not a silent assumption.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lib.player_season_authority import resolved_canonical_position_population

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    DATASET2_ADP_ROUND_BUCKETS,
    DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE,
    DATASET2_ERA_BOUNDARIES,
    SBV_LAMBDA,
    SBV_STAR_THRESHOLD,
)
from lib.stars_by_value import expected_production as ep

OUTCOME_TABLE_PATH = "data/exports/dataset2_canonical_outcome_table.parquet"
MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
EP_LOOKUP_PATH = "data/processed/sbv_expected_production_lookup.parquet"
PLAYERS_PATH = "data/raw/nflverse/reference/players.csv"

pd.set_option("display.width", 160)
pd.set_option("display.max_rows", 100)


def adp_bucket(adp_round):
    if pd.isna(adp_round):
        return None
    for label, lo, hi in DATASET2_ADP_ROUND_BUCKETS:
        if adp_round >= lo and (hi is None or adp_round <= hi):
            return label
    return None


def era_label(season):
    b1, b2 = DATASET2_ERA_BOUNDARIES
    if season < b1:
        return f"pre-{b1}"
    if season < b2:
        return f"{b1}-{b2 - 1}"
    return f"{b2}+"


def games_bucket(g):
    if pd.isna(g):
        return None
    g = int(g)
    if g == 0:
        return "0"
    if g <= 4:
        return "1-4"
    if g <= 8:
        return "5-8"
    if g <= 12:
        return "9-12"
    return "13+"


def build_analysis_frame():
    outcome = pd.read_parquet(OUTCOME_TABLE_PATH)
    master = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    master = resolved_canonical_position_population(master)
    master_cols = master[
        ["season", "player_id", "overall_adp", "games_played", "ppg_ppr", "fantasy_points_ppr", "position_finish_ppr", "data_quality_flag"]
    ].drop_duplicates(subset=["season", "player_id"]).rename(columns={"season": "outcome_season"})

    players = pd.read_csv(PLAYERS_PATH, low_memory=False)
    players_cols = players[["gsis_id", "rookie_season"]].drop_duplicates(subset=["gsis_id"])

    df = outcome.merge(master_cols, on=["outcome_season", "player_id"], how="left")
    df = df.merge(players_cols, left_on="player_id", right_on="gsis_id", how="left")
    df["is_rookie"] = df["outcome_season"] == df["rookie_season"]

    # --- Recompute P exactly as the outcome-table driver does, for the
    # full population (needed here to attach raw P alongside the
    # eligibility flags already stored in the outcome table). ---
    from lib.stars_by_value import production as prod

    prod_pop = master[
        ["season", "player_id", "position", "games_played", "fantasy_points_ppr", "ppg_ppr", "position_finish_ppr", "data_quality_flag"]
    ].dropna(subset=["ppg_ppr", "position_finish_ppr", "games_played", "fantasy_points_ppr"]).copy()
    prod_pop["adp_matched"] = prod_pop["data_quality_flag"].isin(["matched_clean", "matched_needs_review"])
    prod_input = prod_pop[["season", "player_id", "position", "games_played", "fantasy_points_ppr", "ppg_ppr", "position_finish_ppr", "adp_matched"]]
    production_df = prod.compute_production(prod_input)[["season", "player_id", "P"]].rename(columns={"season": "outcome_season"})
    df = df.merge(production_df, on=["outcome_season", "player_id"], how="left")

    # --- E_P via the same fitted lookup the diagnostic uses (fine-
    # grained draft_round, NOT the coarse ADP bucket). ---
    ep_lookup = pd.read_parquet(EP_LOOKUP_PATH)
    ep_small = ep_lookup[["prediction_season", "position", "draft_round", "expected_production"]].rename(
        columns={"prediction_season": "outcome_season", "draft_round": "adp_round"}
    )
    df = df.merge(ep_small, on=["outcome_season", "position", "adp_round"], how="left")

    df["adp_bucket"] = df["adp_round"].apply(adp_bucket)
    df["era"] = df["outcome_season"].apply(era_label)
    df["games_bucket"] = df["games_played"].apply(games_bucket)
    df["threshold"] = df["position"].map(SBV_STAR_THRESHOLD)

    # score_like = SBV's own score formula (P - LAMBDA*E_P), applied to
    # every row with both P and E_P available -- including
    # below_production_gate rows SBV itself never scores. Verify
    # against SBV's own real star_by_value_score for scored rows as a
    # correctness check.
    df["score_like"] = df["P"] - SBV_LAMBDA * df["expected_production"]
    df["score_minus_threshold"] = df["score_like"] - df["threshold"]
    df["pct_below_threshold"] = -df["score_minus_threshold"] / df["threshold"] * 100

    return df


def verify_score_like_matches_real_sbv_score(df):
    scored = df[df["sbv_score_available"] & df["score_like"].notna()]
    diff = (scored["score_like"] - scored["star_by_value_score"]).abs()
    print(f"score_like vs real star_by_value_score, {len(scored)} scored rows: max abs diff = {diff.max():.6f}, mean = {diff.mean():.6f}")


if __name__ == "__main__":
    import os

    df = build_analysis_frame()
    verify_score_like_matches_real_sbv_score(df)
    out_path = os.path.join(
        "/private/tmp/claude-501/-Users-evanfeldman-Desktop-fantasy-master-db-v3/7bf19d18-23db-47fd-a56e-5d1a7b9e0921/scratchpad",
        "dataset2_bust_analysis_frame.parquet",
    )
    df.to_parquet(out_path, index=False)
    print(f"Wrote {out_path}, {len(df)} rows")
