"""
normalized_shrinkage_comparison.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Tests a NORMALIZED reliability-shrinkage function against ordinary
shrinkage and capped extrapolation. Does not select a final constant
or implement anything -- config.py untouched.

Ordinary shrinkage's disclosed weakness (found in the prior
comparison): games/(games+k) never reaches exactly 1.0, even at a
full G-game season -- it always discounts something. The fix is a
simple, principled rescaling: divide by the formula's own value at
g=G, so the curve is stretched to span exactly [0, 1] across the real
domain [0, G] instead of [0, G/(G+k)]:

    normalized_multiplier(g, k, G) = [g/(g+k)] / [G/(G+k)]
                                    = g*(G+k) / (G*(g+k))

This simplifies the resulting PPG_AR_eq formula cleanly:
    PPG_AR_eq_normalized = PPG_AR * (G+k) * g/(g+k)
(ordinary shrinkage is the same formula with a plain G in place of
(G+k) -- the normalization is a one-constant change, not a new model).
At g=0 it's still exactly 0 (same strong discount at tiny samples);
at g=G it's exactly PPG_AR*G (full, undiscounted credit) -- monotonic
and continuous throughout, since it's just a positive rescaling of an
already-monotonic function.

Output: research/output/dataset3/normalized_shrinkage_math_curves.csv
        research/output/dataset3/normalized_shrinkage_edge_case_ranks.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_weight_and_boundary_calibration import build_adp_aware_aatp

OUTPUT_DIR = Path("research/output/dataset3")

EDGE_CASES = [
    (2023, "Carson Wentz"), (2019, "DeSean Jackson"), (2020, "Christian McCaffrey"),
    (2020, "Dak Prescott"), (2017, "Deshaun Watson"), (2021, "Derrick Henry"),
    (2007, "Eli Manning"), (2019, "Christian McCaffrey"),
]

NORM_KS = [2, 4, 8]
ORDINARY_K = 4  # representative, per the prior comparison's finding that k=4 was the smallest decisive value


def ppg_eq_none(ppg_ar, g, G):
    return ppg_ar * G


def ppg_eq_ordinary_shrink(ppg_ar, g, G, k):
    return ppg_ar * G * (g / (g + k))


def ppg_eq_normalized_shrink(ppg_ar, g, G, k):
    return ppg_ar * (G + k) * (g / (g + k))


def ppg_eq_capped_extrap(ppg_ar, g, G):
    return ppg_ar * min(2 * g, G)


def build_treatments(row) -> dict:
    ppg_ar, g, G = row["PPG_AR"], row["games_played_capped"], row["G"]
    out = {"none": ppg_eq_none(ppg_ar, g, G), "ordinary_shrink_k4": ppg_eq_ordinary_shrink(ppg_ar, g, G, ORDINARY_K),
           "capped_extrap": ppg_eq_capped_extrap(ppg_ar, g, G)}
    for k in NORM_KS:
        out[f"normalized_shrink_k{k}"] = ppg_eq_normalized_shrink(ppg_ar, g, G, k)
    return out


def main():
    print("Building ADP-aware AATP population (Option B, confirmed)...")
    df = build_adp_aware_aatp()

    print("\n=== Mathematical behavior: reliability multiplier vs. games played (G=17) ===")
    G = 17
    games_range = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 17]
    math_rows = []
    for g in games_range:
        row = {"games_played": g}
        row["ordinary_shrink_k4"] = round(g / (g + ORDINARY_K), 3)
        for k in NORM_KS:
            row[f"normalized_shrink_k{k}"] = round((G + k) * g / (G * (g + k)), 3)
        row["capped_extrap"] = round(min(2 * g, G) / G, 3)
        math_rows.append(row)
    math_df = pd.DataFrame(math_rows)
    math_df.to_csv(OUTPUT_DIR / "normalized_shrinkage_math_curves.csv", index=False)
    print(math_df.to_string(index=False))

    print("\n=== Confirm: does normalized shrinkage reach EXACTLY 1.0 at g=G=17? ===")
    for k in NORM_KS:
        val = (G + k) * G / (G * (G + k))
        print(f"  k={k}: multiplier at g=17 = {val:.6f}")

    print("\n=== Full 50/50 composite for real edge cases ===")
    treatment_names = list(build_treatments(df.iloc[0]).keys())
    case_rows = []
    for season, name in EDGE_CASES:
        match = df[(df["season"] == season) & (df["player_name"] == name)]
        if match.empty:
            continue
        r = match.iloc[0]
        treatments = build_treatments(r)
        row = {"season": season, "player_name": name, "games_played": r["games_played_capped"], "AATP": round(r["AATP"], 1)}
        for t_name, val in treatments.items():
            row[f"composite_{t_name}"] = round(0.5 * r["AATP"] + 0.5 * val, 1)
        case_rows.append(row)
    case_df = pd.DataFrame(case_rows)
    print(case_df.to_string(index=False))

    print("\n=== Rank out of full population (9615), by treatment ===")
    full = df.copy()
    rank_rows = []
    for t_name in treatment_names:
        full[f"ppg_eq_{t_name}"] = full.apply(lambda r: build_treatments(r)[t_name], axis=1)
        full[f"composite_{t_name}"] = 0.5 * full["AATP"] + 0.5 * full[f"ppg_eq_{t_name}"]
        for season, name in EDGE_CASES:
            match = full[(full["season"] == season) & (full["player_name"] == name)]
            if match.empty:
                continue
            val = match[f"composite_{t_name}"].values[0]
            rank = (full[f"composite_{t_name}"] > val).sum() + 1
            rank_rows.append({"treatment": t_name, "season": season, "player_name": name, "rank_of_9615": rank})
    rank_df = pd.DataFrame(rank_rows)
    rank_df.to_csv(OUTPUT_DIR / "normalized_shrinkage_edge_case_ranks.csv", index=False)
    pivot = rank_df.pivot_table(index=["season", "player_name"], columns="treatment", values="rank_of_9615")
    print(pivot.to_string())

    print(f"\nWrote 2 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
