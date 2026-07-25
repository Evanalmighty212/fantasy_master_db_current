"""
expected_production_temporal_validation.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Tests two things that must be resolved before any production model is
fit, following the QB+RB additive offset selected in the prior
diagnostic (expected_production_position_adjustment_residual_diagnostics.py).
Does NOT select or implement the final expected-production model.

1. TEMPORAL HONESTY. Every prior script in this investigation
   (expected_production_position_adjustment_investigation.py and its
   residual-diagnostics follow-up) used leave-one-SEASON-out (LOSO)
   folds: for held-out season Y, the round means and position offsets
   were fit on all 17 OTHER seasons -- including seasons AFTER Y. That
   is a legitimate technique for estimating how well a fixed structure
   generalizes in general (and matches this project's existing
   Component 1 LOSO convention, which is appropriate there because LWI
   is a retrospective, all-history-known scoring metric, not a
   real-time forecast). It is NOT temporally honest for Dataset 3's
   expected-production baseline, whose whole purpose is representing
   "what would a fair observer have expected at draft time" -- a
   number that, for any historical season Y, can only be built from
   seasons before Y. This script replaces LOSO with an EXPANDING
   WINDOW: for each prediction year Y, round means and the QB/RB
   offsets are fit using ONLY seasons strictly before Y, then
   evaluated against Y's real outcomes. The old LOSO numbers are
   re-reported alongside, restricted to the same test years, to make
   the size of the leakage concretely visible rather than asserted.

2. TIME WEIGHTING. Compares two ways of combining those prior seasons:
   - "equal": every prior season weighted the same.
   - "recency": exponential decay by season age, 5-year half-life.
     The half-life is not arbitrary -- residual_diagnostics_by_era.csv
     (previous diagnostic) found QB's gap vs. the pooled baseline grew
     roughly 4x from the pre-2011 era to 2011-2020 (+22.9 -> +94.6),
     a real structural drift spanning roughly one 5-10 year era
     boundary, which is what recency weighting is meant to track
     faster than an equally-weighted average would.

MIN_PRIOR_SEASONS = 3 before a year is tested at all: with roughly 200
player-seasons per season and 15 rounds, 3 pooled seasons gives most
round cells above this project's existing MIN_ROUND_N_FOR_ANALYSIS=20
credibility bar (see expected_production_by_round_investigation.py)
without requiring years of unavailable future history.

Input:  research/output/dataset3/broad_historical_dataset.csv (via
        expected_production_by_round_investigation.load_matched_with_round)
        research/output/dataset3/position_adjustment_loso_predictions.csv
        (for the leakage-comparison numbers only)
Output: research/output/dataset3/temporal_validation_predictions.csv
        research/output/dataset3/temporal_validation_summary.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expected_production_by_round_investigation import load_matched_with_round, POSITIONS

OUTPUT_DIR = Path("research/output/dataset3")
LOSO_PREDS_PATH = OUTPUT_DIR / "position_adjustment_loso_predictions.csv"
VALUE_COL = "fantasy_points_ppr"

MIN_PRIOR_SEASONS = 3
HALF_LIFE_YEARS = 5
ADJUST_POSITIONS = {"QB", "RB"}  # per the prior diagnostic's selection


def season_weight(season: int, asof_year: int, scheme: str) -> float:
    if scheme == "equal":
        return 1.0
    if scheme == "recency":
        age = (asof_year - 1) - season  # 0 = most recent prior season
        return 0.5 ** (age / HALF_LIFE_YEARS)
    raise ValueError(f"unknown scheme: {scheme}")


def fit_round_means(train: pd.DataFrame, asof_year: int, scheme: str) -> dict:
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    return {rnd: np.average(g[VALUE_COL], weights=g["w"]) for rnd, g in t.groupby("adp_round")}


def fit_position_offsets(train: pd.DataFrame, round_means: dict, asof_year: int, scheme: str) -> dict:
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    t["pooled_pred"] = t["adp_round"].map(round_means)
    t["residual"] = t[VALUE_COL] - t["pooled_pred"]
    offsets = {}
    for pos in ADJUST_POSITIONS:
        sub = t[t["position"] == pos].dropna(subset=["residual"])
        offsets[pos] = np.average(sub["residual"], weights=sub["w"]) if len(sub) else np.nan
    return offsets


def walk_forward(df: pd.DataFrame, scheme: str) -> pd.DataFrame:
    all_seasons = sorted(df["season"].unique())
    results = []
    for asof_year in all_seasons:
        train = df[df["season"] < asof_year]
        if train["season"].nunique() < MIN_PRIOR_SEASONS:
            continue
        test = df[df["season"] == asof_year].copy()
        if test.empty:
            continue

        round_means = fit_round_means(train, asof_year, scheme)
        offsets = fit_position_offsets(train, round_means, asof_year, scheme)

        test["pred_pooled"] = test["adp_round"].map(round_means)
        test["pred_qb_rb"] = test["pred_pooled"] + test["position"].map(
            lambda p: offsets.get(p, 0.0) if p in ADJUST_POSITIONS else 0.0
        )
        test["scheme"] = scheme
        test["test_year"] = asof_year
        results.append(test)

    out = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    n_before = len(out)
    out = out.dropna(subset=["pred_pooled", "pred_qb_rb"])
    if n_before - len(out):
        print(f"  [{scheme}] dropped {n_before - len(out)} rows with no matching prior-season round data")
    return out


def load_leakage_comparison(test_years: set) -> pd.DataFrame:
    """Re-derive QB+RB predictions from the OLD leave-one-season-out
    (future-leaking) file, restricted to the same test years used by
    the honest walk-forward, for a fair side-by-side comparison."""
    old = pd.read_csv(LOSO_PREDS_PATH)
    old = old[old["position"].isin(POSITIONS) & old["season"].isin(test_years)].copy()
    old["applied_offset"] = old["pred_additive"] - old["pred_pooled"]
    old["pred_qb_rb"] = old["pred_pooled"] + np.where(
        old["position"].isin(ADJUST_POSITIONS), old["applied_offset"], 0.0
    )
    old["scheme"] = "leso_leaky_baseline"
    old["test_year"] = old["season"]
    return old[["test_year", "position", VALUE_COL, "pred_pooled", "pred_qb_rb", "scheme"]]


def summarize(preds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scheme, sub_scheme in preds.groupby("scheme"):
        for scope, sub in [("ALL", sub_scheme)] + [(pos, sub_scheme[sub_scheme["position"] == pos]) for pos in POSITIONS]:
            if len(sub) < 5:
                continue
            err_pooled = (sub[VALUE_COL] - sub["pred_pooled"]).abs()
            err_adj = (sub[VALUE_COL] - sub["pred_qb_rb"]).abs()
            rows.append({
                "scheme": scheme, "scope": scope, "n": len(sub),
                "mae_pooled_only": err_pooled.mean(),
                "mae_qb_rb_adjusted": err_adj.mean(),
            })
    return pd.DataFrame(rows)


def compare_schemes(equal_preds: pd.DataFrame, recency_preds: pd.DataFrame) -> pd.DataFrame:
    """Paired comparison on the exact same (test_year, player) rows."""
    key_cols = ["test_year", "position"]
    e = equal_preds.reset_index(drop=True)
    r = recency_preds.reset_index(drop=True)
    e["abs_err"] = (e[VALUE_COL] - e["pred_qb_rb"]).abs()
    r["abs_err"] = (r[VALUE_COL] - r["pred_qb_rb"]).abs()
    rows = []
    for scope, e_sub, r_sub in [("ALL", e, r)] + [
        (pos, e[e["position"] == pos], r[r["position"] == pos]) for pos in POSITIONS
    ]:
        if len(e_sub) < 5 or len(e_sub) != len(r_sub):
            continue
        w_stat, p_value = stats.wilcoxon(e_sub["abs_err"].values, r_sub["abs_err"].values)
        rows.append({
            "scope": scope, "n": len(e_sub),
            "mae_equal": e_sub["abs_err"].mean(), "mae_recency": r_sub["abs_err"].mean(),
            "recency_improvement_pct": 100 * (e_sub["abs_err"].mean() - r_sub["abs_err"].mean()) / e_sub["abs_err"].mean(),
            "wilcoxon_p": p_value,
        })
    return pd.DataFrame(rows)


def main():
    df = load_matched_with_round()
    df = df[df["position"].isin(POSITIONS)].copy()
    print(f"ADP-matched skill-position player-seasons: {len(df)}")

    print("\n=== Running expanding-window walk-forward (equal weighting) ===")
    equal_preds = walk_forward(df, "equal")
    print(f"  test years: {sorted(equal_preds['test_year'].unique())}")

    print("\n=== Running expanding-window walk-forward (recency weighting, half-life=5y) ===")
    recency_preds = walk_forward(df, "recency")

    test_years = set(equal_preds["test_year"].unique())
    leaky = load_leakage_comparison(test_years)

    equal_preds["scheme"] = "expanding_window_equal"
    recency_preds["scheme"] = "expanding_window_recency"
    all_preds = pd.concat([
        equal_preds[["test_year", "position", VALUE_COL, "pred_pooled", "pred_qb_rb", "scheme"]],
        recency_preds[["test_year", "position", VALUE_COL, "pred_pooled", "pred_qb_rb", "scheme"]],
        leaky,
    ], ignore_index=True)
    all_preds.to_csv(OUTPUT_DIR / "temporal_validation_predictions.csv", index=False)

    print("\n=== Summary: MAE by scheme and scope ===")
    summary = summarize(all_preds)
    summary.to_csv(OUTPUT_DIR / "temporal_validation_summary.csv", index=False)
    print(summary.round(2).to_string(index=False))

    print("\n=== Equal vs. recency: paired comparison (same test rows) ===")
    comparison = compare_schemes(equal_preds, recency_preds)
    print(comparison.round(4).to_string(index=False))

    print(f"\nWrote temporal_validation_predictions.csv and temporal_validation_summary.csv to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
