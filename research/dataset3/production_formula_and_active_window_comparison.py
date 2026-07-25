"""
production_formula_and_active_window_comparison.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Three focused comparisons before selecting a production formula or an
active-window rule. Does NOT select weights, thresholds, or implement
anything -- config.py untouched.

PART 1: three candidate ways to combine AATP (season-long,
availability-adjusted) and PPG_AR_season_equiv (rate-when-active,
extrapolated to season-equivalent units) into one continuous
production score:
  1. weighted sum (illustrative 50/50 -- NOT a weight selection)
  2. geometric mean, negative values clipped to 0
  3. "signed-log" combination -- the natural continuous extension of
     geometric mean into signed territory. Geometric mean of two
     positive numbers is exp(mean(log(x), log(y))) -- an arithmetic
     mean in log space. That breaks the moment either input is <= 0,
     which is exactly why option 2 has to clip. signed_log(x) =
     sign(x) * log(1 + |x|) extends log smoothly through zero and into
     negative territory, preserving HOW negative a value is instead of
     collapsing every negative value to the same clipped floor.

Verified data-quality fix applied here: games_played is capped at the
season's VERIFIED regular-season length (16 games 2006-2020, 17 from
2021 on -- NOT derived from max(games_played), per last turn's
correction). Two known bad rows (Emmanuel Sanders, 2019, showing 17;
Rashid Shaheed, 2025, showing 18) are corrected by this cap, along with
any other row silently affected by the same upstream bug.

PART 2: ADP-aware active-window rule (meaningful preseason ADP = full
season-long eligibility from Week 1, regardless of rookie/veteran
status; undrafted = eligibility from first verified active appearance)
vs. the earlier rookie/veteran rule. Rookie season is derived as the
first season a player_id appears anywhere in the 2006-2025 database --
disclosed boundary caveat: this can't distinguish a true rookie from a
veteran who debuted before 2006, in the database's earliest seasons.

PART 3: winsorization boundary sweep for raw surplus, using a
simplified (pooled-only, not yet position-adjusted) expanding-window
expected-AATP-by-round curve -- sufficient for testing where the
TAIL of the surplus distribution should be clipped, without redoing
the full position-offset selection (separate, larger, not-yet-done
work already flagged).

Output: research/output/dataset3/production_formula_comparison.csv
        research/output/dataset3/production_formula_edge_cases.csv
        research/output/dataset3/active_window_rule_disagreements.csv
        research/output/dataset3/winsorization_boundary_sweep.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.replacement import ROSTER_PRESETS, FLEX_ALLOCATION_RB_WR_HEAVY, replacement_rank_cutoff, replacement_level_from_rank
from expected_production_by_round_investigation import POSITIONS, adp_round

OUTPUT_DIR = Path("research/output/dataset3")
BROAD_DATASET_PATH = OUTPUT_DIR / "broad_historical_dataset.csv"
PRESET = ROSTER_PRESETS["12_team_standard"]
WINDOW = 12
MIN_PRIOR_SEASONS = 3


def verified_season_length(season: int) -> int:
    return 17 if season >= 2021 else 16


def signed_log(x):
    return np.sign(x) * np.log1p(np.abs(x))


# ---------- PART 1: production formula ----------

def build_production_population() -> pd.DataFrame:
    df = pd.read_csv(BROAD_DATASET_PATH)
    df = df[(df["games_played"] >= 1) & (df["position"].isin(POSITIONS)) & (df["season"].between(2007, 2024))].copy()

    df["G"] = df["season"].apply(verified_season_length)
    n_capped = (df["games_played"] > df["G"]).sum()
    print(f"Rows with games_played exceeding the verified season length (capped): {n_capped}")
    print(df[df["games_played"] > df["G"]][["season", "player_name", "games_played", "G"]].to_string(index=False))
    df["games_played_capped"] = df[["games_played", "G"]].min(axis=1)
    df["games_missed"] = df["G"] - df["games_played_capped"]

    cutoffs = {pos: replacement_rank_cutoff(PRESET, pos, FLEX_ALLOCATION_RB_WR_HEAVY) for pos in POSITIONS}
    replacement_ppg = replacement_level_from_rank(
        df, value_col="ppg_ppr", rank_col="position_finish_ppr", cutoff_by_position=cutoffs, window=WINDOW,
    )
    df["replacement_ppg"] = replacement_ppg

    df["AATP"] = df["fantasy_points_ppr"] + df["replacement_ppg"] * df["games_missed"]
    df["PPG_AR"] = df["ppg_ppr"] - df["replacement_ppg"]
    df["PPG_AR_eq"] = df["PPG_AR"] * df["G"]
    return df


def part1(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("PART 1: three production-combination candidates")
    print("=" * 70)

    d = df.copy()
    d["prod_weighted_sum"] = 0.5 * d["AATP"] + 0.5 * d["PPG_AR_eq"]
    d["prod_geo_clipped"] = np.sqrt(d["AATP"].clip(lower=0) * d["PPG_AR_eq"].clip(lower=0))
    d["prod_signed_log"] = 0.5 * (signed_log(d["AATP"]) + signed_log(d["PPG_AR_eq"]))

    print(f"\nCorrelations between the three candidates (Spearman):")
    print(d[["prod_weighted_sum", "prod_geo_clipped", "prod_signed_log"]].corr(method="spearman").round(3).to_string())

    print("\n--- Harsh-gate check: does geo_mean create a cliff at PPG_AR_eq=0? ---")
    print("Synthetic sweep, AATP held fixed at 150 (a solid, clearly-passing production level):")
    sweep = pd.DataFrame({"PPG_AR_eq": np.linspace(-20, 20, 9)})
    sweep["AATP"] = 150.0
    sweep["weighted_sum"] = 0.5 * sweep["AATP"] + 0.5 * sweep["PPG_AR_eq"]
    sweep["geo_clipped"] = np.sqrt(sweep["AATP"].clip(lower=0) * sweep["PPG_AR_eq"].clip(lower=0))
    sweep["signed_log"] = 0.5 * (signed_log(sweep["AATP"]) + signed_log(sweep["PPG_AR_eq"]))
    print(sweep.round(2).to_string(index=False))

    d.to_csv(OUTPUT_DIR / "production_formula_comparison.csv", index=False)

    print("\n--- Real historical edge cases ---")
    cases = {}
    cases["few_games_elite_rate"] = d[(d["games_played_capped"] <= 6) & (d["ppg_ppr"] >= d["ppg_ppr"].quantile(0.95))].nlargest(3, "ppg_ppr")
    cases["many_games_modest_rate"] = d[(d["games_played_capped"] >= 15) & (d["PPG_AR"].between(-2, 2))].nlargest(3, "AATP")
    cases["below_replacement_rate_decent_games"] = d[(d["games_played_capped"] >= 10) & (d["PPG_AR"] < -3)].nsmallest(3, "PPG_AR")
    cases["solid_both_dimensions"] = d[(d["AATP"] >= d["AATP"].quantile(0.85)) & (d["PPG_AR"] >= d["PPG_AR"].quantile(0.85))].nlargest(3, "AATP")

    rows = []
    for case_name, sub in cases.items():
        for _, r in sub.iterrows():
            rows.append({
                "case": case_name, "season": r["season"], "player_name": r["player_name"], "position": r["position"],
                "games_played": r["games_played_capped"], "AATP": round(r["AATP"], 1), "PPG_AR_eq": round(r["PPG_AR_eq"], 1),
                "weighted_sum": round(r["prod_weighted_sum"], 1), "geo_clipped": round(r["prod_geo_clipped"], 1),
                "signed_log": round(r["prod_signed_log"], 2),
            })
    edge_df = pd.DataFrame(rows)
    edge_df.to_csv(OUTPUT_DIR / "production_formula_edge_cases.csv", index=False)
    print(edge_df.to_string(index=False))
    return d


# ---------- PART 2: active-window rule comparison ----------

def part2(df: pd.DataFrame, broad: pd.DataFrame):
    print("\n" + "=" * 70)
    print("PART 2: ADP-aware vs. rookie/veteran active-window rule")
    print("=" * 70)

    first_season = broad.groupby("player_id")["season"].min().rename("first_season_in_db")
    d = df.merge(first_season, on="player_id", how="left")
    d["is_rookie_proxy"] = d["season"] == d["first_season_in_db"]
    d["meaningful_adp"] = d["adp_matched"]

    d["rule_veteran_rookie"] = np.where(d["is_rookie_proxy"], "first_appearance", "week1")
    d["rule_adp_aware"] = np.where(d["meaningful_adp"], "week1", "first_appearance")
    d["disagree"] = d["rule_veteran_rookie"] != d["rule_adp_aware"]

    print(f"\nTotal disagreements: {d['disagree'].sum()} of {len(d)} player-seasons")
    print(d.groupby(["is_rookie_proxy", "meaningful_adp"]).size().rename("n").reset_index().to_string(index=False))

    disagreements = d[d["disagree"]].copy()
    type1 = disagreements[disagreements["is_rookie_proxy"] & disagreements["meaningful_adp"]]  # high-ADP rookie
    type2 = disagreements[~disagreements["is_rookie_proxy"] & ~disagreements["meaningful_adp"]]  # low/no-ADP veteran

    print(f"\n--- Type 1: rookie with meaningful ADP (rookie/vet rule under-credits, ADP-aware credits from Week 1) ---")
    print(f"n={len(type1)}. Examples with reduced games played (games_played < G, suggesting a real missed-time case):")
    ex1 = type1[type1["games_played_capped"] < type1["G"]].nsmallest(8, "games_played_capped")[
        ["season", "player_name", "position", "overall_adp_observed", "games_played_capped", "G", "fantasy_points_ppr"]]
    print(ex1.to_string(index=False))

    print(f"\n--- Type 2: undrafted/deep veteran (rookie/vet rule over-credits from Week 1, ADP-aware anchors to first appearance) ---")
    print(f"n={len(type2)}. Examples with reduced games played:")
    ex2 = type2[type2["games_played_capped"] < type2["G"]].nsmallest(8, "games_played_capped")[
        ["season", "player_name", "position", "first_season_in_db", "games_played_capped", "G", "fantasy_points_ppr"]]
    print(ex2.to_string(index=False))

    all_examples = pd.concat([
        ex1.assign(disagreement_type="type1_rookie_with_meaningful_adp"),
        ex2.assign(disagreement_type="type2_veteran_no_meaningful_adp"),
    ], ignore_index=True)
    all_examples.to_csv(OUTPUT_DIR / "active_window_rule_disagreements.csv", index=False)


# ---------- PART 3: winsorization boundary sweep ----------

def fit_round_means_pooled(train: pd.DataFrame) -> dict:
    return train.groupby("adp_round")["AATP"].mean().to_dict()


def part3(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("PART 3: winsorization boundary sweep for raw surplus (AATP target)")
    print("=" * 70)

    matched = df[df["adp_matched"]].copy()
    matched["adp_round"] = matched["overall_adp_observed"].apply(adp_round)

    results = []
    for asof_year in sorted(matched["season"].unique()):
        train = matched[matched["season"] < asof_year]
        if train["season"].nunique() < MIN_PRIOR_SEASONS:
            continue
        test = matched[matched["season"] == asof_year].copy()
        if test.empty:
            continue
        round_means = fit_round_means_pooled(train)
        test["expected_AATP"] = test["adp_round"].map(round_means)
        results.append(test)
    preds = pd.concat(results, ignore_index=True).dropna(subset=["expected_AATP"])
    preds["surplus"] = preds["AATP"] - preds["expected_AATP"]
    print(f"Test population (expanding window, 2010-2024): {len(preds)} rows")
    print(f"Expected AATP by round -- confirms it stays positive, no zero-crossing:")
    print(preds.groupby("adp_round")["expected_AATP"].mean().round(1).to_string())

    boundaries = [(1, 99), (2, 98), (5, 95), (0.5, 99.5)]
    sweep_rows = []
    for lo, hi in boundaries:
        lo_val = preds["surplus"].quantile(lo / 100)
        hi_val = preds["surplus"].quantile(hi / 100)
        n_clipped_low = (preds["surplus"] < lo_val).sum()
        n_clipped_high = (preds["surplus"] > hi_val).sum()
        sweep_rows.append({
            "boundary": f"{lo}/{hi}", "low_clip_value": round(lo_val, 1), "high_clip_value": round(hi_val, 1),
            "n_clipped_low": n_clipped_low, "n_clipped_high": n_clipped_high,
            "n_clipped_total": n_clipped_low + n_clipped_high, "pct_clipped": round(100 * (n_clipped_low + n_clipped_high) / len(preds), 2),
        })
    sweep_df = pd.DataFrame(sweep_rows)
    sweep_df.to_csv(OUTPUT_DIR / "winsorization_boundary_sweep.csv", index=False)
    print(sweep_df.to_string(index=False))

    print("\n--- Who actually gets clipped? Top 5 highest-surplus and lowest-surplus real player-seasons ---")
    print(preds.nlargest(5, "surplus")[["season", "player_name", "position", "adp_round", "surplus"]].round(1).to_string(index=False))
    print(preds.nsmallest(5, "surplus")[["season", "player_name", "position", "adp_round", "surplus"]].round(1).to_string(index=False))


def main():
    print("Building AATP/PPG_AR production population (2007-2024, verified season lengths)...")
    df = build_production_population()
    broad = pd.read_csv(BROAD_DATASET_PATH)

    part1(df)
    part2(df, broad)
    part3(df)

    print(f"\nWrote 4 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
