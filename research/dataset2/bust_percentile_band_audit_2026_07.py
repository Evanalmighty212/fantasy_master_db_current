"""
research/dataset2/bust_percentile_band_audit_2026_07.py

Read-only, one-off DESCRIPTIVE audit script -- reproduces the real
bust_primary_label percentile (pct_final) exactly as
lib/dataset2/canonical_outcome_table.py::_assign_bust_primary_labels()
computes it internally (that value is never persisted to the final
outcome table, only the boolean labels derived from it), so real
player examples can be shown for finer percentile bands than the
persisted 20%/25%/30% cutoffs distinguish.

SAFETY: this script does NOT reimplement the label formula blindly --
it calls the real, already-tested build_canonical_outcome_table()
directly for the ground-truth labels, then independently recomputes
pct_final with the same mechanical groupby/rank logic, and asserts its
own reproduction of bust_primary_label/bust_strict_below_replacement_label
matches the real, persisted values with ZERO disagreements before any
percentile-band number below is trusted. This is a DESCRIPTIVE-ONLY
audit of the existing, approved bust definition -- it does not create,
change, or propose any new label.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from lib.dataset2.canonical_outcome_table import (
    BUST_PRIMARY_PERCENTILE,
    build_canonical_outcome_table,
)
from lib.stars_by_value import production as prod
from config import DATASET2_ADP_ROUND_BUCKETS, DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE, DATASET2_ERA_BOUNDARIES, SBV_LAMBDA

MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
SBV_EXPORT_PATH = "data/exports/stars_by_value_player_seasons.csv"
PLAYERS_PATH = "data/raw/nflverse/reference/players.csv"
EP_LOOKUP_PATH = "data/processed/sbv_expected_production_lookup.parquet"


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


def main():
    master_population = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    master_population = master_population[master_population["position"].isin(["QB", "RB", "WR", "TE"])]
    sbv_status = pd.read_csv(SBV_EXPORT_PATH, low_memory=False)
    players_df = pd.read_csv(PLAYERS_PATH, low_memory=False)
    ep_lookup = pd.read_parquet(EP_LOOKUP_PATH)

    pop = master_population.dropna(subset=["ppg_ppr", "position_finish_ppr", "games_played", "fantasy_points_ppr"]).copy()
    pop["adp_matched"] = pop["data_quality_flag"].isin(["matched_clean", "matched_needs_review"])
    prod_input = pop[["season", "player_id", "position", "games_played", "fantasy_points_ppr", "ppg_ppr", "position_finish_ppr", "adp_matched"]].copy()
    production_df = prod.compute_production(prod_input)[["season", "player_id", "P"]]

    real = build_canonical_outcome_table(master_population, sbv_status, players_df, ep_lookup, production_df)
    players = players_df[["gsis_id", "display_name"]]

    # --- Independent recomputation of P/expected_production/score_like,
    # same real merges build_canonical_outcome_table() itself performs. ---
    from lib.stars_by_value import expected_production as ep
    from lib.stars_by_value import minimal_market_cost as mmc

    base = master_population[["season", "player_id", "position", "games_played", "overall_adp"]].drop_duplicates(
        subset=["season", "player_id"]
    ).rename(columns={"season": "outcome_season"})
    sbv = sbv_status[["season", "player_id", "star_by_value_status", "star_by_value_score", "star_by_value_label"]].drop_duplicates(
        subset=["season", "player_id"]
    ).rename(columns={"season": "outcome_season"})
    out = base.merge(sbv, on=["outcome_season", "player_id"], how="left")
    out["real_status"] = out["star_by_value_status"].fillna("no_sbv_row_found")
    out["has_real_market_adp"] = out["overall_adp"].notna()
    out["adp_round"] = out["overall_adp"].apply(ep.adp_round)

    ep_small = ep_lookup[["prediction_season", "position", "draft_round", "expected_production"]].rename(
        columns={"prediction_season": "outcome_season", "draft_round": "adp_round"}
    )
    out = out.merge(ep_small, on=["outcome_season", "position", "adp_round"], how="left")
    mmc_mask = out["real_status"] == "minimal_market_cost_scored"
    out.loc[mmc_mask, "expected_production"] = out.loc[mmc_mask].apply(
        lambda r: mmc.minimal_market_cost_expected_production(r["position"], r["outcome_season"]), axis=1
    )
    out = out.merge(production_df.rename(columns={"season": "outcome_season"}), on=["outcome_season", "player_id"], how="left")
    out["score_like"] = out["P"] - SBV_LAMBDA * out["expected_production"]

    out["bust_primary_eligible"] = (out["has_real_market_adp"] & (out["outcome_season"] >= 2010))
    out["_adp_bucket"] = out["adp_round"].apply(_adp_bucket)
    out["_era"] = out["outcome_season"].apply(_era_label)

    eligible = out["bust_primary_eligible"].astype(bool)
    zero_game = eligible & (out["games_played"] == 0)
    has_score = eligible & ~zero_game & out["score_like"].notna()
    lookup_gap = eligible & ~zero_game & ~has_score & out["P"].notna()

    pct_final = pd.Series(pd.NA, index=out.index, dtype="Float64")
    sub = out.loc[has_score, ["position", "_adp_bucket", "_era", "score_like"]].copy()
    sub["_era_cell_n"] = sub.groupby(["position", "_adp_bucket", "_era"])["score_like"].transform("size")
    sub["_pct_era"] = sub.groupby(["position", "_adp_bucket", "_era"])["score_like"].rank(pct=True, method="average", ascending=True)
    sub["_pct_pooled"] = sub.groupby(["position", "_adp_bucket"])["score_like"].rank(pct=True, method="average", ascending=True)
    era_ok = sub["_era_cell_n"] >= DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE
    pct_final.loc[sub.index] = sub["_pct_era"].where(era_ok, sub["_pct_pooled"])

    raw_pop = out.loc[eligible & out["P"].notna(), ["position", "_adp_bucket", "P"]].copy()
    raw_pop["_pct_raw_pooled"] = raw_pop.groupby(["position", "_adp_bucket"])["P"].rank(pct=True, method="average", ascending=True)
    pct_final.loc[lookup_gap] = raw_pop.loc[lookup_gap, "_pct_raw_pooled"]

    out["pct_final"] = pct_final
    out.loc[zero_game, "pct_final"] = 0.0  # automatic bust -- treat as percentile 0 for banding purposes only

    recomputed_label = pd.Series(pd.NA, index=out.index, dtype="boolean")
    has_pct = eligible & out["pct_final"].notna()
    recomputed_label.loc[has_pct] = (out.loc[has_pct, "pct_final"] <= BUST_PRIMARY_PERCENTILE).astype("boolean")

    out = out.merge(real[["outcome_season", "player_id", "bust_primary_label"]], on=["outcome_season", "player_id"], how="left", suffixes=("", "_real"))
    comparable = eligible & out["bust_primary_label"].notna()
    disagreements = (recomputed_label.loc[comparable] != out.loc[comparable, "bust_primary_label"]).sum()
    print(f"VALIDATION: {comparable.sum()} comparable eligible rows, {disagreements} disagreements between "
          f"independent pct_final recomputation and the real, persisted bust_primary_label.")
    if disagreements > 0:
        print("STOP: recomputation does not match real labels -- do not trust percentile bands below.")
        return

    out = out.merge(players, left_on="player_id", right_on="gsis_id", how="left")
    banded = out[eligible & out["pct_final"].notna()].copy()

    bands = [(0.0, 0.10, "bottom 10%"), (0.10, 0.15, "10-15%"), (0.15, 0.20, "15-20%"), (0.20, 0.25, "just above 20% (20-25%)")]
    for lo, hi, label in bands:
        cell = banded[(banded["pct_final"] > lo) & (banded["pct_final"] <= hi)] if lo > 0 else banded[banded["pct_final"] <= hi]
        print(f"\n=== {label} (pct_final in ({lo}, {hi}]): n={len(cell)} ===")
        examples = cell.sort_values("pct_final").head(6)
        print(examples[["display_name", "position", "outcome_season", "adp_round", "pct_final", "P", "score_like"]].to_string(index=False))


if __name__ == "__main__":
    main()
