"""
research/dataset2/bust_label_round2_analysis.py

Round 2 real-data analysis backing
DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md §18-26:
the G-raw-vs-E_P-dependent disagreement audit, the four-way era-
handling comparison, the availability/partial-season comparison, the
zero-game rule, and the final formula's exact counts/prevalence.
Analysis only -- writes no label column anywhere, matches round 1's
"reuse existing constants/functions, never reinvent" convention
(SBV_LAMBDA, SBV_STAR_THRESHOLD, DATASET2_ADP_ROUND_BUCKETS,
DATASET2_ERA_BOUNDARIES, DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE,
lib.stars_by_value.production.compute_production(),
lib.replacement.replacement_level_from_rank()).
"""

import sys
from pathlib import Path

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
from lib.stars_by_value import production as prod

OUTCOME_TABLE_PATH = "data/exports/dataset2_canonical_outcome_table.parquet"
MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
EP_LOOKUP_PATH = "data/processed/sbv_expected_production_lookup.parquet"
PLAYERS_PATH = "data/raw/nflverse/reference/players.csv"
MIN_N = DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE

pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 300)


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


def rank_pct(frame, value_col, group_cols):
    return frame.groupby(group_cols)[value_col].rank(pct=True, method="average", ascending=True)


def build_frame():
    outcome = pd.read_parquet(OUTCOME_TABLE_PATH)
    master = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    master = resolved_canonical_position_population(master)
    master_cols = master[
        ["season", "player_id", "overall_adp", "games_played", "ppg_ppr", "fantasy_points_ppr", "position_finish_ppr", "data_quality_flag"]
    ].drop_duplicates(subset=["season", "player_id"]).rename(columns={"season": "outcome_season"})

    players = pd.read_csv(PLAYERS_PATH, low_memory=False)
    players_cols = players[["gsis_id", "rookie_season", "display_name"]].drop_duplicates(subset=["gsis_id"])

    df = outcome.merge(master_cols, on=["outcome_season", "player_id"], how="left")
    df = df.merge(players_cols, left_on="player_id", right_on="gsis_id", how="left")
    df["is_rookie"] = df["outcome_season"] == df["rookie_season"]

    prod_pop = master[
        ["season", "player_id", "position", "games_played", "fantasy_points_ppr", "ppg_ppr", "position_finish_ppr", "data_quality_flag"]
    ].dropna(subset=["ppg_ppr", "position_finish_ppr", "games_played", "fantasy_points_ppr"]).copy()
    prod_pop["adp_matched"] = prod_pop["data_quality_flag"].isin(["matched_clean", "matched_needs_review"])
    prod_input = prod_pop[["season", "player_id", "position", "games_played", "fantasy_points_ppr", "ppg_ppr", "position_finish_ppr", "adp_matched"]]
    production_df = prod.compute_production(prod_input)
    keep_cols = ["season", "player_id", "P", "AATP", "PPG_AR"]
    production_df = production_df[keep_cols].rename(columns={"season": "outcome_season"})
    df = df.merge(production_df, on=["outcome_season", "player_id"], how="left")

    ep_lookup = pd.read_parquet(EP_LOOKUP_PATH)
    ep_small = ep_lookup[["prediction_season", "position", "draft_round", "expected_production"]].rename(
        columns={"prediction_season": "outcome_season", "draft_round": "adp_round"}
    )
    df = df.merge(ep_small, on=["outcome_season", "position", "adp_round"], how="left")

    df["adp_bucket"] = df["adp_round"].apply(adp_bucket)
    df["era"] = df["outcome_season"].apply(era_label)
    df["games_bucket"] = df["games_played"].apply(games_bucket)
    df["threshold"] = df["position"].map(SBV_STAR_THRESHOLD)
    df["score_like"] = df["P"] - SBV_LAMBDA * df["expected_production"]
    return df


def section_19_disagreement_audit(primary):
    """G-raw vs. E_P-dependent (G-score) disagreement, §19."""
    rankable = primary[primary["score_like"].notna() & primary["P"].notna()].copy()
    rankable["pct_score"] = rank_pct(rankable, "score_like", ["position", "adp_bucket"])
    rankable["pct_raw"] = rank_pct(rankable, "P", ["position", "adp_bucket"])
    rankable["flag_score"] = rankable["pct_score"] <= 0.20
    rankable["flag_raw"] = rankable["pct_raw"] <= 0.20

    score_only = rankable[rankable["flag_score"] & ~rankable["flag_raw"]]
    raw_only = rankable[~rankable["flag_score"] & rankable["flag_raw"]]
    both = rankable[rankable["flag_score"] & rankable["flag_raw"]]

    print("=== §19 G-score vs. G-raw disagreement audit ===")
    print(f"rankable={len(rankable)}, flag_score={rankable['flag_score'].sum()}, flag_raw={rankable['flag_raw'].sum()}")
    print(f"score_only={len(score_only)}, raw_only={len(raw_only)}, both={len(both)}, "
          f"disagreement_pct={(len(score_only) + len(raw_only)) / (len(score_only) + len(raw_only) + len(both)) * 100:.1f}%")

    ep_lookup = pd.read_parquet(EP_LOOKUP_PATH)
    max_round_by_cell = ep_lookup.groupby(["prediction_season", "position"])["draft_round"].max().rename("max_covered_round").reset_index()
    max_round_by_cell = max_round_by_cell.rename(columns={"prediction_season": "outcome_season"})

    for name, subset in (("score_only", score_only), ("raw_only", raw_only)):
        merged = subset.merge(max_round_by_cell, on=["outcome_season", "position"], how="left")
        merged["rounds_from_boundary"] = merged["max_covered_round"] - merged["adp_round"]
        print(f"{name}: adp_round mean={subset['adp_round'].mean():.2f}, "
              f"rounds_from_lookup_boundary mean={merged['rounds_from_boundary'].mean():.2f}")
    print()
    return rankable


def section_20_era_comparison(primary):
    """Four era-handling methods compared, §20."""
    rankable = primary[primary["score_like"].notna()].copy()

    rankable["pct_m1"] = rank_pct(rankable, "score_like", ["position", "adp_bucket"])
    rankable["flag_m1"] = rankable["pct_m1"] <= 0.20

    rankable["pct_m2"] = rank_pct(rankable, "score_like", ["position", "adp_bucket", "era"])
    rankable["flag_m2"] = rankable["pct_m2"] <= 0.20
    cellsize_m2 = rankable.groupby(["position", "adp_bucket", "era"]).size()

    grp = rankable.groupby(["era", "position"])["score_like"]
    rankable["score_like_z"] = (rankable["score_like"] - grp.transform("mean")) / grp.transform("std")
    rankable["pct_m3"] = rank_pct(rankable, "score_like_z", ["position", "adp_bucket"])
    rankable["flag_m3"] = rankable["pct_m3"] <= 0.20

    cellsize_map = cellsize_m2.rename("era_cell_n")
    rankable = rankable.merge(cellsize_map, left_on=["position", "adp_bucket", "era"], right_index=True, how="left")
    small_cell = rankable["era_cell_n"] < MIN_N
    rankable["flag_m4"] = rankable["flag_m2"].where(~small_cell, rankable["flag_m1"])

    print("=== §20 Era-handling: four methods ===")
    print(f"Method 2 real sparse cells (n<{MIN_N}): {(cellsize_m2 < MIN_N).sum()} of {len(cellsize_m2)}")
    print(f"Method 4 fallback rows: {small_cell.sum()}")
    for m in ("m1", "m2", "m3", "m4"):
        print(f"  {m}: n={rankable[f'flag_{m}'].sum()}")
    for m in ("flag_m1", "flag_m2", "flag_m3", "flag_m4"):
        t = rankable.groupby("era").agg(n=("player_id", "size"), flagged=(m, "sum"))
        t["rate_pct"] = (t["flagged"] / t["n"] * 100).round(1)
        print(f"--- {m} by era ---\n{t}")
    print()
    return rankable


def section_21_availability_comparison(primary):
    """AATP-alone vs. PPG_AR-alone vs. current P, §21."""
    rankable = primary[primary["P"].notna() & primary["AATP"].notna() & primary["PPG_AR"].notna()].copy()
    rankable["pct_P"] = rank_pct(rankable, "P", ["position", "adp_bucket"])
    rankable["pct_AATP"] = rank_pct(rankable, "AATP", ["position", "adp_bucket"])
    rankable["pct_PPGAR"] = rank_pct(rankable, "PPG_AR", ["position", "adp_bucket"])
    rankable["flag_P"] = rankable["pct_P"] <= 0.20
    rankable["flag_AATP"] = rankable["pct_AATP"] <= 0.20
    rankable["flag_PPGAR"] = rankable["pct_PPGAR"] <= 0.20

    print("=== §21 Availability comparison ===")
    injury_pattern = rankable[rankable["flag_AATP"] & ~rankable["flag_PPGAR"]]
    performance_pattern = rankable[~rankable["flag_AATP"] & rankable["flag_PPGAR"]]
    print(f"Flagged by AATP not PPG_AR (injury-bust pattern): n={len(injury_pattern)}")
    print(f"Flagged by PPG_AR not AATP (performance-bust pattern): n={len(performance_pattern)}")
    print()
    return rankable


def section_22_23_final_formula(primary):
    """Zero-game rule + final combined formula counts, §22-25.

    IMPORTANT (found during implementation verification, not before):
    the ranking here MUST use Method 4 (era-specific with mechanical
    minimum-sample fallback to pooled), matching §20's recommendation
    and what §23 claims to implement. An earlier version of this
    function used the plain pooled ranking (Method 1) here instead --
    a real bug, not a rounding difference -- which produced an
    incorrect 532 total. The correct, era-aware total is 522; see the
    proposal doc's corrected §23-26 for the full disclosure.
    """
    rankable_score = primary[primary["score_like"].notna()].copy()
    rankable_score["_era_cell_n"] = rankable_score.groupby(["position", "adp_bucket", "era"])["score_like"].transform("size")
    rankable_score["_pct_era"] = rankable_score.groupby(["position", "adp_bucket", "era"])["score_like"].rank(pct=True, method="average", ascending=True)
    rankable_score["_pct_pooled"] = rank_pct(rankable_score, "score_like", ["position", "adp_bucket"])
    era_ok = rankable_score["_era_cell_n"] >= MIN_N
    rankable_score["pct_score"] = rankable_score["_pct_era"].where(era_ok, rankable_score["_pct_pooled"])
    rankable_score["flag_primary"] = rankable_score["pct_score"] <= 0.20
    rankable_score["flag_strict"] = rankable_score["flag_primary"] & (rankable_score["P"] < 0)

    raw_rankable = primary[primary["P"].notna()].copy()
    raw_rankable["pct_raw_all"] = rank_pct(raw_rankable, "P", ["position", "adp_bucket"])
    raw_rankable["flag_raw_all"] = raw_rankable["pct_raw_all"] <= 0.20

    missing_score = primary[primary["score_like"].isna()].copy()
    ep_gap_rows = missing_score[missing_score["P"].notna()].copy()
    ep_gap_rows["flag_primary"] = raw_rankable.loc[ep_gap_rows.index, "flag_raw_all"].values
    ep_gap_rows["flag_strict"] = ep_gap_rows["flag_primary"] & (ep_gap_rows["P"] < 0)

    zero_game_rows = missing_score[missing_score["P"].isna()].copy()
    zero_game_rows["flag_primary"] = True
    zero_game_rows["flag_strict"] = True

    combined = pd.concat([
        rankable_score[["display_name", "outcome_season", "position", "adp_bucket", "era", "games_bucket", "is_rookie", "flag_primary", "flag_strict"]],
        ep_gap_rows[["display_name", "outcome_season", "position", "adp_bucket", "era", "games_bucket", "is_rookie", "flag_primary", "flag_strict"]],
        zero_game_rows[["display_name", "outcome_season", "position", "adp_bucket", "era", "games_bucket", "is_rookie", "flag_primary", "flag_strict"]],
    ])

    print("=== §22-23 Final formula: zero-game rule + combined counts ===")
    print(f"combined n={len(combined)}, final primary={combined['flag_primary'].sum()}, final strict={combined['flag_strict'].sum()}")
    for dim in ("position", "adp_bucket", "era", "games_bucket", "is_rookie"):
        t = combined.groupby(dim).agg(n=("flag_primary", "size"), primary=("flag_primary", "sum"), strict=("flag_strict", "sum"))
        t["primary_rate"] = (t["primary"] / t["n"] * 100).round(1)
        t["strict_rate"] = (t["strict"] / t["n"] * 100).round(1)
        print(f"--- By {dim} ---\n{t}")
    print()
    return combined


if __name__ == "__main__":
    df = build_frame()
    primary = df[df["bust_primary_eligible"]].copy()
    section_19_disagreement_audit(primary)
    section_20_era_comparison(primary)
    section_21_availability_comparison(primary)
    section_22_23_final_formula(primary)
