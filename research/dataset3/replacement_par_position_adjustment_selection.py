"""
replacement_par_position_adjustment_selection.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Redoes the position-adjustment selection from scratch against
points_above_replacement (PAR, under the approved provisional
flex_rb_wr_heavy replacement definition), instead of reusing the
raw-points QB+RB selection. Does NOT select or implement a final
model or touch config.py.

Every prediction in this script is EXPANDING-WINDOW (prior seasons
only, per test year) -- no leave-one-season-out anywhere, since LOSO's
use of future seasons is exactly the leakage problem already
identified and rejected for this purpose.

Variants tested (all "lightweight" -- an offset is one number, or one
number per included position, never a per-round table):
  - none                  -- pooled round curve alone, no adjustment
  - one_constant_all      -- ONE shared scalar offset applied to every
                              position alike (not position-specific) --
                              a genuine trivial baseline, not to be
                              confused with a 4-position model.
  - QB_only, RB_only, WR_only, TE_only
  - QB_RB                 -- the prior (raw-points) selection, kept for
                              direct comparison, not assumed to still win.
  - QB_TE, WR_TE          -- explicitly requested combinations.
  - QB_TE_WR              -- justified by the residual-diagnostics
                              finding below: RB's PAR residual is by far
                              the smallest in magnitude of the four, so
                              "adjust everything except the position
                              with the least bias" is a real, motivated
                              combination, not an arbitrary addition.
  - all_four_separate      -- ceiling reference (one independent offset
                              per position) -- not itself a "lightweight
                              recommendation," included only to show how
                              much is left on the table by choosing a
                              smaller combination.

RESULTS (2026-07 run, recorded here since this script's output is
gitignored and not committed):
  - Variant ranking by overall MAE: all_four_separate (57.12) ~=
    QB_TE_WR (57.17) < QB_TE (57.51) < WR_TE (57.59) < TE_only (57.93)
    < QB_RB, the old raw-points selection (58.11) < QB_only (58.15) <
    WR_only (58.24) < RB_only (58.53) < none = one_constant_all (58.57,
    identical -- a single shared offset collapses to ~0 by
    construction, exactly as expected).
  - TE_only ALONE already beats the old QB_RB selection -- carrying
    that selection forward unchanged would have been worse than doing
    nothing for QB and adjusting TE instead.
  - QB_TE_WR recommended: captures nearly all the 4-position ceiling's
    benefit while excluding RB, whose PAR residual is both the
    smallest in magnitude and the least stable across seasons (cv=3.1,
    std exceeds the mean) of the four positions.
  - Equal vs. recency (QB_TE_WR): QB's recency benefit reproduces
    independently under PAR (1.4%, p=0.0005) -- not inherited from the
    raw-points result. Everywhere else, a wash or marginal cost
    (RB/WR/TE all p>0.05).
  - Segment bias test after QB_TE_WR: 5 of 16 (position, segment)
    cells still show significant remaining bias (p<0.05) -- more than
    the raw-points QB+RB case left behind (2/16). QB's true bias is
    front-loaded (much bigger in R1-4 than later rounds), TE's is
    uneven across segments (R9-12 far exceeds R5-8), WR's grows worse
    by round -- a single constant number per position can't fully
    track any of those shapes. Disclosed limitation, not grounds on
    its own to build a round-varying model.

Output: research/output/dataset3/par_residuals_by_round.csv
        research/output/dataset3/par_residuals_by_segment.csv
        research/output/dataset3/par_residuals_by_season.csv
        research/output/dataset3/par_residuals_by_era.csv
        research/output/dataset3/par_variant_comparison_equal.csv
        research/output/dataset3/par_leading_variant_equal_vs_recency.csv
        research/output/dataset3/par_leading_variant_segment_bias_test.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.eras import assign_era
from expected_production_by_round_investigation import POSITIONS
from expected_production_replacement_adjusted_retest import load_par_round_population, PAR_COL
from expected_production_position_adjustment_residual_diagnostics import assign_segment, MIN_N_FOR_ANY_STAT

OUTPUT_DIR = Path("research/output/dataset3")
MIN_PRIOR_SEASONS = 3
HALF_LIFE_YEARS = 5

VARIANTS = {
    "none": None,
    "one_constant_all": "GLOBAL",
    "QB_only": {"QB"},
    "RB_only": {"RB"},
    "WR_only": {"WR"},
    "TE_only": {"TE"},
    "QB_RB": {"QB", "RB"},
    "QB_TE": {"QB", "TE"},
    "WR_TE": {"WR", "TE"},
    "QB_TE_WR": {"QB", "TE", "WR"},
    "all_four_separate": {"QB", "RB", "WR", "TE"},
}


def season_weight(season: int, asof_year: int, scheme: str) -> float:
    if scheme == "equal":
        return 1.0
    age = (asof_year - 1) - season
    return 0.5 ** (age / HALF_LIFE_YEARS)


def fit_round_means(train: pd.DataFrame, asof_year: int, scheme: str) -> dict:
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    return {rnd: np.average(g[PAR_COL], weights=g["w"]) for rnd, g in t.groupby("adp_round")}


def fit_offsets(train: pd.DataFrame, round_means: dict, asof_year: int, scheme: str) -> tuple:
    """Returns (per_position_offsets_dict, global_scalar_offset)."""
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    t["pooled_pred"] = t["adp_round"].map(round_means)
    t["residual"] = t[PAR_COL] - t["pooled_pred"]
    per_position = {}
    for pos in POSITIONS:
        sub = t[t["position"] == pos].dropna(subset=["residual"])
        per_position[pos] = np.average(sub["residual"], weights=sub["w"]) if len(sub) else np.nan
    global_offset = np.average(t["residual"].dropna(), weights=t.loc[t["residual"].notna(), "w"])
    return per_position, global_offset


def predict_variant(test: pd.DataFrame, per_position: dict, global_offset: float, variant_spec) -> pd.Series:
    if variant_spec is None:
        return test["pred_pooled"]
    if variant_spec == "GLOBAL":
        return test["pred_pooled"] + global_offset
    return test["pred_pooled"] + test["position"].map(
        lambda p: per_position.get(p, 0.0) if p in variant_spec else 0.0
    )


def walk_forward_all_variants(df: pd.DataFrame, scheme: str) -> pd.DataFrame:
    results = []
    for asof_year in sorted(df["season"].unique()):
        train = df[df["season"] < asof_year]
        if train["season"].nunique() < MIN_PRIOR_SEASONS:
            continue
        test = df[df["season"] == asof_year].copy()
        if test.empty:
            continue

        round_means = fit_round_means(train, asof_year, scheme)
        per_position, global_offset = fit_offsets(train, round_means, asof_year, scheme)

        test["pred_pooled"] = test["adp_round"].map(round_means)
        for variant_name, spec in VARIANTS.items():
            test[f"pred_{variant_name}"] = predict_variant(test, per_position, global_offset, spec)
        test["test_year"] = asof_year
        results.append(test)

    out = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    pred_cols = [f"pred_{v}" for v in VARIANTS]
    return out.dropna(subset=pred_cols)


def grouped_mean_residual(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    rows = []
    for keys, g in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        n = len(g)
        row = dict(zip(group_cols, keys))
        row["n"] = n
        row["mean_residual_par"] = g["resid_pooled"].mean() if n >= MIN_N_FOR_ANY_STAT else np.nan
        row["insufficient_n"] = n < MIN_N_FOR_ANY_STAT
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    print("Loading PAR-valued, round-assigned population (flex_rb_wr_heavy)...")
    df = load_par_round_population()
    print(f"ADP-matched, round-assigned, PAR-valued player-seasons: {len(df)}")

    print("\n=== Building expanding-window predictions (equal weighting, all variants) ===")
    equal_preds = walk_forward_all_variants(df, "equal")
    equal_preds["resid_pooled"] = equal_preds[PAR_COL] - equal_preds["pred_none"]
    equal_preds["segment"] = equal_preds["adp_round"].apply(assign_segment)
    equal_preds["era"] = equal_preds["season"].apply(assign_era)
    print(f"  test years: {sorted(equal_preds['test_year'].unique())}, n={len(equal_preds)}")

    print("\n=== 1a. Pooled-model PAR residual by (position, round) ===")
    by_round = grouped_mean_residual(equal_preds, ["position", "adp_round"])
    by_round.to_csv(OUTPUT_DIR / "par_residuals_by_round.csv", index=False)
    print(by_round.round(1).to_string(index=False))

    print("\n=== 1b. By (position, segment) ===")
    by_segment = grouped_mean_residual(equal_preds, ["position", "segment"])
    by_segment.to_csv(OUTPUT_DIR / "par_residuals_by_segment.csv", index=False)
    print(by_segment.round(1).to_string(index=False))

    print("\n=== 1c. By (position, season) -- stability check ===")
    by_season = grouped_mean_residual(equal_preds, ["position", "season"])
    by_season.to_csv(OUTPUT_DIR / "par_residuals_by_season.csv", index=False)
    stability = by_season.dropna(subset=["mean_residual_par"]).groupby("position")["mean_residual_par"].agg(
        ["mean", "std", "min", "max"]
    )
    stability["cv_abs"] = (stability["std"] / stability["mean"].abs()).round(2)
    print(stability.round(1).to_string())

    print("\n=== 1d. By (position, era) ===")
    by_era = grouped_mean_residual(equal_preds, ["position", "era"])
    by_era.to_csv(OUTPUT_DIR / "par_residuals_by_era.csv", index=False)
    print(by_era.round(1).to_string(index=False))

    print("\n=== 2. Variant comparison (equal weighting, expanding window, MAE) ===")
    comp_rows = []
    for scope, sub in [("ALL", equal_preds)] + [(pos, equal_preds[equal_preds["position"] == pos]) for pos in POSITIONS]:
        if len(sub) < MIN_N_FOR_ANY_STAT:
            continue
        row = {"scope": scope, "n": len(sub)}
        for variant_name in VARIANTS:
            row[f"mae_{variant_name}"] = (sub[PAR_COL] - sub[f"pred_{variant_name}"]).abs().mean()
        comp_rows.append(row)
    variant_comparison = pd.DataFrame(comp_rows)
    variant_comparison.to_csv(OUTPUT_DIR / "par_variant_comparison_equal.csv", index=False)
    print(variant_comparison.round(2).to_string(index=False))

    all_mae = variant_comparison[variant_comparison["scope"] == "ALL"].iloc[0]
    ranked = sorted(
        [(v, all_mae[f"mae_{v}"]) for v in VARIANTS], key=lambda x: x[1]
    )
    print("\nVariants ranked by overall MAE (lower is better):")
    for name, mae in ranked:
        print(f"  {name:20s} {mae:.3f}")
    leading_lightweight = next(name for name, _ in ranked if name != "all_four_separate")
    print(f"\nLeading lightweight variant (excluding the ceiling-reference all_four_separate): {leading_lightweight}")

    print(f"\n=== 3. Equal vs. recency weighting for the leading variant ({leading_lightweight}) ===")
    recency_preds = walk_forward_all_variants(df, "recency")
    e = equal_preds[["test_year", "position", PAR_COL, f"pred_{leading_lightweight}"]].reset_index(drop=True)
    r = recency_preds[["test_year", "position", PAR_COL, f"pred_{leading_lightweight}"]].reset_index(drop=True)
    e["abs_err"] = (e[PAR_COL] - e[f"pred_{leading_lightweight}"]).abs()
    r["abs_err"] = (r[PAR_COL] - r[f"pred_{leading_lightweight}"]).abs()
    time_rows = []
    for scope, e_sub, r_sub in [("ALL", e, r)] + [(pos, e[e["position"] == pos], r[r["position"] == pos]) for pos in POSITIONS]:
        if len(e_sub) < MIN_N_FOR_ANY_STAT or len(e_sub) != len(r_sub):
            continue
        _, p_value = stats.wilcoxon(e_sub["abs_err"].values, r_sub["abs_err"].values)
        time_rows.append({
            "scope": scope, "n": len(e_sub),
            "mae_equal": e_sub["abs_err"].mean(), "mae_recency": r_sub["abs_err"].mean(),
            "improvement_pct": 100 * (e_sub["abs_err"].mean() - r_sub["abs_err"].mean()) / e_sub["abs_err"].mean(),
            "wilcoxon_p": p_value,
        })
    time_df = pd.DataFrame(time_rows)
    time_df.to_csv(OUTPUT_DIR / "par_leading_variant_equal_vs_recency.csv", index=False)
    print(time_df.round(4).to_string(index=False))

    print(f"\n=== 4. Segment-level bias test AFTER applying '{leading_lightweight}' (equal weighting) ===")
    equal_preds["resid_leading"] = equal_preds[PAR_COL] - equal_preds[f"pred_{leading_lightweight}"]
    bias_rows = []
    for (pos, seg), g in equal_preds.groupby(["position", "segment"]):
        resid = g["resid_leading"].dropna()
        row = {"position": pos, "segment": seg, "n": len(resid), "mean_residual": resid.mean()}
        if len(resid) >= MIN_N_FOR_ANY_STAT:
            t_stat, p_value = stats.ttest_1samp(resid, popmean=0)
            row["p_value"] = p_value
            row["significant_bias_remains"] = p_value < 0.05
        else:
            row["p_value"] = np.nan
            row["significant_bias_remains"] = None
        bias_rows.append(row)
    bias_df = pd.DataFrame(bias_rows).sort_values(["position", "segment"])
    bias_df.to_csv(OUTPUT_DIR / "par_leading_variant_segment_bias_test.csv", index=False)
    print(bias_df.round(4).to_string(index=False))
    n_sig = bias_df["significant_bias_remains"].fillna(False).sum()
    n_tested = bias_df["significant_bias_remains"].notna().sum()
    print(f"\n{n_sig} of {n_tested} testable cells show significant remaining bias (p<0.05) after '{leading_lightweight}'.")

    print(f"\nWrote 7 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
