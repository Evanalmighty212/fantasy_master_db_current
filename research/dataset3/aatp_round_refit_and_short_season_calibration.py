"""
aatp_round_refit_and_short_season_calibration.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Covers three of the six provisional-decision validations requested:
Task 1 (ADP depth / fitting population), Task 3 (full AATP round-curve
refit), Task 4 (short-season reliability problem). Tasks 2, 5, 6 are
reaffirmed, not re-tested -- no new empirical question was raised for
them. Does NOT select a final answer for any of these -- config.py
untouched.

Uses the corrected, ADP-aware AATP construction (verified season
length, weekly-data-based active window) built in
production_weight_and_boundary_calibration.py -- reused here, not
rebuilt.

TASK 1 precision check (done before building the comparison, not
assumed): the 20 player-seasons with adp_rank > 200 land EXCLUSIVELY
in round 14 (14 of them) and round 15 (6 of them) -- nowhere else.
Capping the fitting population at 200 is specifically a question about
whether to keep or drop these 20 players from the two thinnest,
already-fragile bins in the whole curve -- not a broad population
change. Draft status (and therefore AATP's active-window treatment)
is left untouched in both conditions, per instruction -- only whether
these 20 rows are USED WHEN FITTING the round means changes.

Output: research/output/dataset3/adp_depth_fitting_comparison.csv
        research/output/dataset3/aatp_round_curve_final.csv
        research/output/dataset3/aatp_position_variant_comparison.csv
        research/output/dataset3/aatp_equal_vs_recency.csv
        research/output/dataset3/short_season_candidates.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.eras import assign_era
from expected_production_by_round_investigation import POSITIONS, adp_round
from expected_production_position_adjustment_residual_diagnostics import assign_segment, MIN_N_FOR_ANY_STAT
from production_weight_and_boundary_calibration import build_adp_aware_aatp

OUTPUT_DIR = Path("research/output/dataset3")
MIN_PRIOR_SEASONS = 3
HALF_LIFE_YEARS = 5

VARIANTS = {
    "none": None, "QB_only": {"QB"}, "RB_only": {"RB"}, "WR_only": {"WR"}, "TE_only": {"TE"},
    "QB_RB": {"QB", "RB"}, "QB_TE": {"QB", "TE"}, "WR_TE": {"WR", "TE"}, "QB_TE_WR": {"QB", "TE", "WR"},
    "all_four": {"QB", "RB", "WR", "TE"},
}


def season_weight(season, asof_year, scheme):
    if scheme == "equal":
        return 1.0
    age = (asof_year - 1) - season
    return 0.5 ** (age / HALF_LIFE_YEARS)


# ---------- TASK 1: fitting population comparison ----------

def task1(matched: pd.DataFrame):
    print("\n" + "=" * 70)
    print("TASK 1: fitting population -- all trustworthy ADP vs. capped at 200")
    print("=" * 70)

    all_pop = matched.copy()
    capped_pop = matched[matched["adp_rank"] <= 200].copy()
    print(f"All-trustworthy fitting population: {len(all_pop)}. Capped-at-200: {len(capped_pop)}. "
          f"Difference: {len(all_pop) - len(capped_pop)} rows, all in round 14/15.")

    rows = []
    for label, fit_pop in [("all_trustworthy", all_pop), ("capped_200", capped_pop)]:
        for rnd in [14, 15]:
            sub = fit_pop[fit_pop["adp_round"] == rnd]
            rows.append({"population": label, "round": rnd, "n": len(sub), "mean_AATP": round(sub["AATP"].mean(), 1)})
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n--- Out-of-sample expanding-window MAE, each fitting population predicting the SAME real-world test rows ---")
    results = {}
    for label, fit_source in [("all_trustworthy", all_pop), ("capped_200", capped_pop)]:
        preds = []
        for asof_year in sorted(matched["season"].unique()):
            train = fit_source[fit_source["season"] < asof_year]
            if train["season"].nunique() < MIN_PRIOR_SEASONS:
                continue
            test = matched[matched["season"] == asof_year].copy()  # test = full real population, always
            if test.empty:
                continue
            round_means = train.groupby("adp_round")["AATP"].mean().to_dict()
            test["pred"] = test["adp_round"].map(round_means)
            preds.append(test)
        p = pd.concat(preds, ignore_index=True).dropna(subset=["pred"])
        p["abs_err"] = (p["AATP"] - p["pred"]).abs()
        results[label] = p

    comp_rows = []
    for scope in ["ALL", 14, 15]:
        row = {"scope": scope}
        for label in results:
            p = results[label]
            sub = p if scope == "ALL" else p[p["adp_round"] == scope]
            row[f"mae_{label}"] = round(sub["abs_err"].mean(), 3) if len(sub) else np.nan
            row[f"n_{label}"] = len(sub)
        comp_rows.append(row)
    comp_df = pd.DataFrame(comp_rows)
    comp_df.to_csv(OUTPUT_DIR / "adp_depth_fitting_comparison.csv", index=False)
    print(comp_df.to_string(index=False))

    e = results["all_trustworthy"][["season", "player_id", "abs_err"]].rename(columns={"abs_err": "err_all"})
    c = results["capped_200"][["season", "player_id", "abs_err"]].rename(columns={"abs_err": "err_capped"})
    merged = e.merge(c, on=["season", "player_id"])
    _, p_val = stats.wilcoxon(merged["err_all"], merged["err_capped"])
    print(f"\nWilcoxon paired test (all_trustworthy vs. capped_200 errors, same rows): p={p_val:.4f}")
    return results["all_trustworthy"]


# ---------- TASK 3: full AATP round-curve refit ----------

def fit_round_means(train, asof_year, scheme):
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    return {r: np.average(g["AATP"], weights=g["w"]) for r, g in t.groupby("adp_round")}


def fit_offsets(train, round_means, asof_year, scheme):
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    t["pooled_pred"] = t["adp_round"].map(round_means)
    t["residual"] = t["AATP"] - t["pooled_pred"]
    return {pos: np.average(t[t["position"] == pos].dropna(subset=["residual"])["residual"],
                             weights=t.loc[(t["position"] == pos) & t["residual"].notna(), "w"])
            for pos in POSITIONS}


def walk_forward(matched, scheme):
    results = []
    for asof_year in sorted(matched["season"].unique()):
        train = matched[matched["season"] < asof_year]
        if train["season"].nunique() < MIN_PRIOR_SEASONS:
            continue
        test = matched[matched["season"] == asof_year].copy()
        if test.empty:
            continue
        round_means = fit_round_means(train, asof_year, scheme)
        offsets = fit_offsets(train, round_means, asof_year, scheme)
        test["pred_pooled"] = test["adp_round"].map(round_means)
        for name, spec in VARIANTS.items():
            if spec is None:
                test[f"pred_{name}"] = test["pred_pooled"]
            else:
                test[f"pred_{name}"] = test["pred_pooled"] + test["position"].map(
                    lambda p: offsets.get(p, 0.0) if p in spec else 0.0)
        test["test_year"] = asof_year
        results.append(test)
    out = pd.concat(results, ignore_index=True)
    pred_cols = [f"pred_{v}" for v in VARIANTS]
    return out.dropna(subset=pred_cols)


def task3(matched: pd.DataFrame):
    print("\n" + "=" * 70)
    print("TASK 3: full AATP round-curve refit (all-trustworthy fitting population, per Task 1 finding)")
    print("=" * 70)

    equal_preds = walk_forward(matched, "equal")
    equal_preds["segment"] = equal_preds["adp_round"].apply(assign_segment)
    equal_preds["era"] = equal_preds["season"].apply(assign_era)
    print(f"Test population: {len(equal_preds)} rows, years {sorted(equal_preds['test_year'].unique())}")

    pooled = equal_preds.groupby("adp_round")["AATP"].agg(["count", "mean", "median"]).reset_index()
    pooled.to_csv(OUTPUT_DIR / "aatp_round_curve_final.csv", index=False)
    print("\nPooled round curve (out-of-sample, expanding window):")
    print(pooled.round(1).to_string(index=False))
    print(f"Round 15 sample size in the EXPANDING-WINDOW test set specifically: "
          f"{(equal_preds['adp_round']==15).sum()} -- flagged low-confidence, not excluded.")

    print("\n--- Position residual from pooled curve, by segment ---")
    equal_preds["resid_pooled"] = equal_preds["AATP"] - equal_preds["pred_none"]
    seg_resid = equal_preds.groupby(["position", "segment"])["resid_pooled"].mean().round(1)
    print(seg_resid.to_string())

    print("\n--- Variant comparison: are positional offsets still needed for AATP? ---")
    comp_rows = []
    for scope, sub in [("ALL", equal_preds)] + [(pos, equal_preds[equal_preds["position"] == pos]) for pos in POSITIONS]:
        row = {"scope": scope, "n": len(sub)}
        for name in VARIANTS:
            row[f"mae_{name}"] = (sub["AATP"] - sub[f"pred_{name}"]).abs().mean()
        comp_rows.append(row)
    variant_df = pd.DataFrame(comp_rows)
    variant_df.to_csv(OUTPUT_DIR / "aatp_position_variant_comparison.csv", index=False)
    print(variant_df.round(2).to_string(index=False))

    all_mae = variant_df[variant_df["scope"] == "ALL"].iloc[0]
    ranked = sorted([(v, all_mae[f"mae_{v}"]) for v in VARIANTS], key=lambda x: x[1])
    print("\nRanked by overall MAE:")
    for name, mae in ranked:
        print(f"  {name:12s} {mae:.3f}")
    leading = ranked[0][0]

    print(f"\n--- Equal vs. recency weighting for leading variant ({leading}) ---")
    recency_preds = walk_forward(matched, "recency")
    e = equal_preds[["test_year", "position", "AATP", f"pred_{leading}"]].reset_index(drop=True)
    r = recency_preds[["test_year", "position", "AATP", f"pred_{leading}"]].reset_index(drop=True)
    e["abs_err"] = (e["AATP"] - e[f"pred_{leading}"]).abs()
    r["abs_err"] = (r["AATP"] - r[f"pred_{leading}"]).abs()
    rows = []
    for scope, e_sub, r_sub in [("ALL", e, r)] + [(pos, e[e["position"] == pos], r[r["position"] == pos]) for pos in POSITIONS]:
        if len(e_sub) < MIN_N_FOR_ANY_STAT or len(e_sub) != len(r_sub):
            continue
        _, p_val = stats.wilcoxon(e_sub["abs_err"].values, r_sub["abs_err"].values)
        rows.append({"scope": scope, "n": len(e_sub), "mae_equal": e_sub["abs_err"].mean(),
                     "mae_recency": r_sub["abs_err"].mean(), "wilcoxon_p": p_val})
    tw_df = pd.DataFrame(rows)
    tw_df.to_csv(OUTPUT_DIR / "aatp_equal_vs_recency.csv", index=False)
    print(tw_df.round(4).to_string(index=False))


# ---------- TASK 4: short-season problem ----------

def task4(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("TASK 4: short-season problem -- real historical edge cases")
    print("=" * 70)

    cases = pd.DataFrame([
        {"season": 2020, "player_name": "Christian McCaffrey"},
        {"season": 2020, "player_name": "Dak Prescott"},
        {"season": 2023, "player_name": "Carson Wentz"},
    ])
    d = df.merge(cases, on=["season", "player_name"])
    # add a short-but-unremarkable contrast case and a full-season elite baseline, found from real data
    short_unremarkable = df[(df["games_played_capped"] <= 4) & (df["PPG_AR"].between(-2, 2))].nlargest(1, "games_played_capped")
    full_season_elite = df[(df["season"] == 2019) & (df["player_name"] == "Christian McCaffrey")]
    d = pd.concat([d, short_unremarkable.assign(player_name=short_unremarkable["player_name"]), full_season_elite], ignore_index=True)

    G = 17
    ks = [4, 8]
    min_games_list = [4, 6, 8]
    rows = []
    for _, r in d.iterrows():
        gp = r["games_played_capped"]
        row = {"season": r["season"], "player_name": r["player_name"], "position": r["position"],
               "games_played": gp, "raw_PPG_AR": round(r["PPG_AR"], 2), "raw_PPG_AR_eq": round(r["PPG_AR_eq"], 1)}
        for k in ks:
            reliability = gp / (gp + k)
            row[f"shrunk_PPG_AR_eq_k{k}"] = round(r["PPG_AR"] * reliability * r["G"], 1)
        for mg in min_games_list:
            row[f"min_games_{mg}_PPG_AR_eq"] = round(r["PPG_AR_eq"], 1) if gp >= mg else 0.0
        capped_extrap_games = min(2 * gp, r["G"])
        row["capped_extrap_PPG_AR_eq"] = round(r["PPG_AR"] * capped_extrap_games, 1)
        rows.append(row)
    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUTPUT_DIR / "short_season_candidates.csv", index=False)
    print(result_df.to_string(index=False))


def main():
    print("Building ADP-aware AATP population (reused from production_weight_and_boundary_calibration)...")
    df = build_adp_aware_aatp()
    matched = df[df["adp_matched"]].copy()
    matched["adp_round"] = matched["overall_adp_observed"].apply(adp_round)

    task1(matched)
    task3(matched)
    task4(df)

    print(f"\nWrote 5 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
