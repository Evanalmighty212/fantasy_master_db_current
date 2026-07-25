"""
short_season_ppg_adjustment_comparison.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Compares 5 candidate short-season treatments for the PPG-above-
replacement term specifically -- AATP is untouched in every variant.
Uses the confirmed Option B ADP-aware active window (reused from
production_weight_and_boundary_calibration.py, unchanged) and
illustrative 50/50 AATP/PPG weighting (not a final weight selection).
Does NOT select a shrinkage constant, final weights, or a production
threshold -- config.py untouched.

Five treatments, applied only to PPG_AR before it's scaled to
season-equivalent units:
  1. none              -- PPG_AR_eq = PPG_AR * G (unadjusted)
  2. shrinkage(k)       -- PPG_AR_eq = PPG_AR * G * games/(games+k),
                            tested at k=2,4,8,12
  3. capped_extrap      -- PPG_AR_eq = PPG_AR * min(2*games, G) --
                            limits how far the rate is extrapolated,
                            rather than down-weighting the rate itself
  4. min_games(t)       -- PPG_AR_eq = 0 if games<t else PPG_AR*G,
                            tested at t=4,6,8. AATP is NEVER zeroed --
                            only this one term.
  5. hybrid(k,T)        -- shrinkage(k) below T games, full value at
                            or above T -- tested at (k=4,T=8)

Real edge cases (found in the data, not invented): Carson Wentz 2023
(1 game), DeSean Jackson 2019 (2 games), CMC 2020 (3 games, the
flagship case), Dak Prescott 2020 (5 games), Deshaun Watson 2017 and
Derrick Henry 2021 (7-8 games, real, well-known LEGITIMATE
injury-shortened elite seasons -- the explicit contrast case to CMC
2020), Eli Manning 2007 (16 games, durable/modest), CMC 2019 (16
games, full-season-elite baseline).

Output: research/output/dataset3/ppg_adjustment_math_curves.csv
        research/output/dataset3/ppg_adjustment_edge_case_composites.csv
        research/output/dataset3/ppg_adjustment_edge_case_ranks.csv
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

SHRINKAGE_KS = [2, 4, 8, 12]
MIN_GAMES_THRESHOLDS = [4, 6, 8]
HYBRID = (4, 8)  # (k, T)


def ppg_eq_none(ppg_ar, games, G):
    return ppg_ar * G


def ppg_eq_shrink(ppg_ar, games, G, k):
    return ppg_ar * G * (games / (games + k))


def ppg_eq_capped_extrap(ppg_ar, games, G):
    return ppg_ar * min(2 * games, G)


def ppg_eq_min_games(ppg_ar, games, G, t):
    return ppg_ar * G if games >= t else 0.0


def ppg_eq_hybrid(ppg_ar, games, G, k, T):
    if games >= T:
        return ppg_ar * G
    return ppg_ar * G * (games / (games + k))


def build_all_treatments(row) -> dict:
    ppg_ar, games, G = row["PPG_AR"], row["games_played_capped"], row["G"]
    out = {"none": ppg_eq_none(ppg_ar, games, G)}
    for k in SHRINKAGE_KS:
        out[f"shrink_k{k}"] = ppg_eq_shrink(ppg_ar, games, G, k)
    out["capped_extrap"] = ppg_eq_capped_extrap(ppg_ar, games, G)
    for t in MIN_GAMES_THRESHOLDS:
        out[f"min_games_{t}"] = ppg_eq_min_games(ppg_ar, games, G, t)
    out[f"hybrid_k{HYBRID[0]}_T{HYBRID[1]}"] = ppg_eq_hybrid(ppg_ar, games, G, *HYBRID)
    return out


def main():
    print("Building ADP-aware AATP population (Option B, confirmed)...")
    df = build_adp_aware_aatp()

    print("\n=== Mathematical behavior: discount multiplier vs. games played (G=17) ===")
    G = 17
    games_range = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 17]
    math_rows = []
    for g in games_range:
        row = {"games_played": g}
        row["none_multiplier"] = 1.0
        for k in SHRINKAGE_KS:
            row[f"shrink_k{k}_multiplier"] = round(g / (g + k), 3)
        row["capped_extrap_multiplier"] = round(min(2 * g, G) / G, 3)
        for t in MIN_GAMES_THRESHOLDS:
            row[f"min_games_{t}_multiplier"] = 1.0 if g >= t else 0.0
        k, T = HYBRID
        row[f"hybrid_k{k}_T{T}_multiplier"] = 1.0 if g >= T else round(g / (g + k), 3)
        math_rows.append(row)
    math_df = pd.DataFrame(math_rows)
    math_df.to_csv(OUTPUT_DIR / "ppg_adjustment_math_curves.csv", index=False)
    print(math_df.to_string(index=False))

    print("\n=== Applying all treatments to real edge cases, computing the FULL 50/50 composite ===")
    treatment_names = list(build_all_treatments(df.iloc[0]).keys())
    case_rows = []
    for season, name in EDGE_CASES:
        matches = df[(df["season"] == season) & (df["player_name"] == name)]
        if matches.empty:
            print(f"  WARNING: {name} {season} not found")
            continue
        r = matches.iloc[0]
        treatments = build_all_treatments(r)
        row = {"season": season, "player_name": name, "position": r["position"],
               "games_played": r["games_played_capped"], "AATP": round(r["AATP"], 1), "raw_PPG_AR_eq": round(r["PPG_AR"] * r["G"], 1)}
        for t_name, val in treatments.items():
            row[f"composite_{t_name}"] = round(0.5 * r["AATP"] + 0.5 * val, 1)
        case_rows.append(row)
    case_df = pd.DataFrame(case_rows)
    case_df.to_csv(OUTPUT_DIR / "ppg_adjustment_edge_case_composites.csv", index=False)
    print(case_df.to_string(index=False))

    print("\n=== Where does each case RANK in the full population, under each treatment? ===")
    full = df.copy()
    rank_rows = []
    for t_name in treatment_names:
        full[f"ppg_eq_{t_name}"] = full.apply(lambda r: build_all_treatments(r)[t_name], axis=1)
        full[f"composite_{t_name}"] = 0.5 * full["AATP"] + 0.5 * full[f"ppg_eq_{t_name}"]
        for season, name in EDGE_CASES:
            match = full[(full["season"] == season) & (full["player_name"] == name)]
            if match.empty:
                continue
            val = match[f"composite_{t_name}"].values[0]
            rank = (full[f"composite_{t_name}"] > val).sum() + 1
            pctile = 100 * (1 - rank / len(full))
            rank_rows.append({"treatment": t_name, "season": season, "player_name": name,
                               "composite": round(val, 1), "rank_of_9615": rank, "percentile": round(pctile, 2)})
    rank_df = pd.DataFrame(rank_rows)
    rank_df.to_csv(OUTPUT_DIR / "ppg_adjustment_edge_case_ranks.csv", index=False)
    pivot = rank_df.pivot_table(index=["season", "player_name"], columns="treatment", values="rank_of_9615")
    print(pivot.to_string())

    print(f"\nWrote 3 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
