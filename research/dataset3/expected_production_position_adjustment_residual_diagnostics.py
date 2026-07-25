"""
expected_production_position_adjustment_residual_diagnostics.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Final diagnostic before any model selection. Does NOT select or
implement the expected-production model. Reuses the out-of-sample
(leave-one-season-out) predictions already produced by
expected_production_position_adjustment_investigation.py -- residuals
here are computed against predictions each held-out season never saw
during fitting, not in-sample fitted residuals (which would trivially
average near zero and tell us nothing about generalization).

Answers, in order:
  1. Where does the pooled-only model's bias sit, by position, broken
     down both by individual round and by broad segment (Rounds 1-4,
     5-8, 9-12, 13-15)?
  2. Is each position's offset (the thing the constant adjustment
     assumes is stable) actually stable across seasons and across the
     project's existing era buckets (research/dataset3/lib/eras.py)?
  3. After applying the constant four-position additive offset, does
     meaningful systematic bias remain in any round segment?
  4. How does the constant four-position offset compare to QB-only and
     QB+RB variants -- narrower adjustments that only touch the
     position(s) actually shown to need correction?

Per instruction: stays lightweight, reuses the existing LOSO
predictions rather than fitting anything new, and does NOT build a
full round x position model -- that step is only taken if the residual
diagnostics below clearly demonstrate the constant offset is
inadequate.

Input:  research/output/dataset3/position_adjustment_loso_predictions.csv
Output: research/output/dataset3/residual_diagnostics_by_round.csv
        research/output/dataset3/residual_diagnostics_by_segment.csv
        research/output/dataset3/residual_diagnostics_by_season.csv
        research/output/dataset3/residual_diagnostics_by_era.csv
        research/output/dataset3/residual_diagnostics_segment_bias_test.csv
        research/output/dataset3/adjustment_variant_comparison.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.eras import assign_era
from expected_production_by_round_investigation import MIN_ROUND_N_FOR_ANALYSIS, POSITIONS

OUTPUT_DIR = Path("research/output/dataset3")
PREDS_PATH = OUTPUT_DIR / "position_adjustment_loso_predictions.csv"
VALUE_COL = "fantasy_points_ppr"
MIN_N_FOR_ANY_STAT = 5

ROUND_SEGMENTS = [(1, 4, "R1-4"), (5, 8, "R5-8"), (9, 12, "R9-12"), (13, 15, "R13-15")]


def assign_segment(rnd: int) -> str:
    for lo, hi, label in ROUND_SEGMENTS:
        if lo <= rnd <= hi:
            return label
    raise ValueError(f"Round {rnd} not covered by any segment")


def load_preds() -> pd.DataFrame:
    df = pd.read_csv(PREDS_PATH)
    df = df[df["position"].isin(POSITIONS)].copy()
    df["resid_pooled"] = df[VALUE_COL] - df["pred_pooled"]
    df["resid_additive"] = df[VALUE_COL] - df["pred_additive"]
    df["applied_offset"] = df["pred_additive"] - df["pred_pooled"]  # per-fold offset actually used
    df["segment"] = df["adp_round"].apply(assign_segment)
    df["era"] = df["season"].apply(assign_era)
    return df


def grouped_mean_residual(df: pd.DataFrame, group_cols: list, resid_col: str) -> pd.DataFrame:
    rows = []
    for keys, g in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        n = len(g)
        row = dict(zip(group_cols, keys))
        row["n"] = n
        row["mean_residual"] = g[resid_col].mean() if n >= MIN_N_FOR_ANY_STAT else np.nan
        row["insufficient_n"] = n < MIN_N_FOR_ANY_STAT
        rows.append(row)
    return pd.DataFrame(rows)


def segment_bias_test(df: pd.DataFrame) -> pd.DataFrame:
    """One-sample t-test: is mean(resid_additive) significantly
    different from 0 within this (position, segment) cell? Tests the
    MEAN specifically (not the median) since the additive offset was
    itself fit as a mean -- a t-test on the mean is the matching check
    for whether that mean-based correction still leaves a mean bias."""
    rows = []
    for (pos, seg), g in df.groupby(["position", "segment"]):
        resid = g["resid_additive"].dropna()
        row = {"position": pos, "segment": seg, "n": len(resid), "mean_residual": resid.mean()}
        if len(resid) >= MIN_N_FOR_ANY_STAT:
            t_stat, p_value = stats.ttest_1samp(resid, popmean=0)
            row["t_statistic"] = t_stat
            row["p_value"] = p_value
            row["significant_bias_remains"] = p_value < 0.05
        else:
            row["t_statistic"] = np.nan
            row["p_value"] = np.nan
            row["significant_bias_remains"] = None
            row["note"] = f"n<{MIN_N_FOR_ANY_STAT} -- not tested"
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["position", "segment"])


def compare_variants(df: pd.DataFrame) -> pd.DataFrame:
    """Constant four-position offset (already computed as pred_additive)
    vs. QB-only and QB+RB variants -- built by selectively zeroing the
    SAME per-fold offset already fit for pred_additive (applied_offset),
    not by refitting: a position's offset is estimated independently of
    every other position's within fit_position_additive_offset's
    groupby, so QB's offset value is identical whether or not RB/WR/TE
    are also being adjusted."""
    df = df.copy()
    df["pred_qb_only"] = df["pred_pooled"] + np.where(df["position"] == "QB", df["applied_offset"], 0.0)
    df["pred_qb_rb"] = df["pred_pooled"] + np.where(df["position"].isin(["QB", "RB"]), df["applied_offset"], 0.0)

    variants = {
        "pooled_only": "pred_pooled",
        "qb_only_offset": "pred_qb_only",
        "qb_rb_offset": "pred_qb_rb",
        "const_4_position_offset": "pred_additive",
    }
    rows = []
    for scope, sub in [("ALL", df)] + [(pos, df[df["position"] == pos]) for pos in POSITIONS]:
        if len(sub) < MIN_N_FOR_ANY_STAT:
            continue
        row = {"scope": scope, "n": len(sub)}
        for name, col in variants.items():
            err = (sub[VALUE_COL] - sub[col]).abs()
            row[f"mae_{name}"] = err.mean()
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    df = load_preds()
    print(f"LOSO out-of-sample predictions loaded: {len(df)} rows")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n=== 1a. Pooled-model mean residual by (position, round) ===")
    by_round = grouped_mean_residual(df, ["position", "adp_round"], "resid_pooled")
    by_round.to_csv(OUTPUT_DIR / "residual_diagnostics_by_round.csv", index=False)
    print(by_round.round(1).to_string(index=False))

    print("\n=== 1b. Pooled-model mean residual by (position, segment) ===")
    by_segment = grouped_mean_residual(df, ["position", "segment"], "resid_pooled")
    by_segment.to_csv(OUTPUT_DIR / "residual_diagnostics_by_segment.csv", index=False)
    print(by_segment.round(1).to_string(index=False))

    print("\n=== 2a. Stability check: pooled-model mean residual by (position, season) ===")
    by_season = grouped_mean_residual(df, ["position", "season"], "resid_pooled")
    by_season.to_csv(OUTPUT_DIR / "residual_diagnostics_by_season.csv", index=False)
    stability = by_season.dropna(subset=["mean_residual"]).groupby("position")["mean_residual"].agg(
        ["mean", "std", "min", "max"]
    )
    stability["cv_abs"] = (stability["std"] / stability["mean"].abs()).round(2)
    print("Per-season offset summary (mean/std/min/max across 18 seasons, cv_abs = std / |mean|):")
    print(stability.round(1).to_string())

    print("\n=== 2b. Stability check: pooled-model mean residual by (position, era) ===")
    by_era = grouped_mean_residual(df, ["position", "era"], "resid_pooled")
    by_era.to_csv(OUTPUT_DIR / "residual_diagnostics_by_era.csv", index=False)
    print(by_era.round(1).to_string(index=False))

    print("\n=== 3. Segment-level bias test AFTER the constant four-position offset ===")
    bias_test = segment_bias_test(df)
    bias_test.to_csv(OUTPUT_DIR / "residual_diagnostics_segment_bias_test.csv", index=False)
    print(bias_test.round(4).to_string(index=False))
    n_significant = bias_test["significant_bias_remains"].fillna(False).sum()
    print(f"\n{n_significant} of {bias_test['significant_bias_remains'].notna().sum()} testable "
          f"(position, segment) cells show significant remaining bias (p<0.05) after the constant offset.")

    print("\n=== 4. Constant 4-position offset vs. QB-only vs. QB+RB (LOSO MAE) ===")
    comparison = compare_variants(df)
    comparison.to_csv(OUTPUT_DIR / "adjustment_variant_comparison.csv", index=False)
    print(comparison.round(2).to_string(index=False))

    print(f"\nWrote 6 diagnostic CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
