"""
expected_production_position_adjustment_investigation.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Follow-up to expected_production_by_round_investigation.py. Does NOT
select or implement a final expected-production model. Answers one
question: does a simple position adjustment on top of the pooled
round curve predict held-out-season production materially better than
the pooled round curve alone -- and is that gain worth the added
complexity?

Per the task's explicit framing: round (12-team draft round) stays the
PRIMARY axis, since round is the acquisition cost this project
ultimately compares players against. Position-specific round tables
are reported as a secondary diagnostic only, not fit as a competing
model. Only ONE simple position-adjusted alternative is tested here,
not a full position x round model:

    expected(round, position) = pooled_round_mean(round) + position_offset(position)

`position_offset(position)` is a SINGLE number per position (QB/RB/WR/TE):
the average amount that position's real production has historically
differed from what the pooled round curve alone would have predicted,
averaged across every round that position was drafted in. This is a
one-way position "fixed effect" layered on top of the round curve, not
a separate round curve per position -- deliberately the simplest
adjustment that still targets the pooling confound documented in
expected_production_by_round_investigation.py (round 1 is 65% RB / 3%
QB; round 13-14 is far more QB/TE-heavy).

A multiplicative variant (position_ratio(position), applied as
pooled_round_mean(round) * position_ratio(position)) is also tested
alongside the additive one, since it's nearly free to compute once the
additive version exists and resolves an open question (does position's
deviation scale with the round-level baseline, or stay flat in raw
points) without building a third model.

Validation: leave-one-season-out (LOSO) cross-validation, consistent
with this project's existing convention for out-of-sample checks
(config.py's Component 1 LOSO monotonic EVA). For each of the 18
seasons (2007-2024), the round means and position offsets/ratios are
fit ONLY on the other 17 seasons, then used to predict the held-out
season's actual fantasy_points_ppr. This directly tests generalization,
not in-sample fit.

Input:  research/output/dataset3/broad_historical_dataset.csv (via
        expected_production_by_round_investigation.load_matched_with_round)
Output: research/output/dataset3/position_specific_round_stats.csv
        research/output/dataset3/position_adjustment_loso_predictions.csv
        research/output/dataset3/position_adjustment_loso_summary.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expected_production_by_round_investigation import (
    load_matched_with_round, MIN_ROUND_N_FOR_ANALYSIS, POSITIONS,
)

OUTPUT_DIR = Path("research/output/dataset3")
VALUE_COL = "fantasy_points_ppr"
MIN_N_FOR_ANY_STAT = 5  # matches compare_within_position()'s existing threshold


def position_specific_round_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (rnd, pos), g in df.groupby(["adp_round", "position"]):
        if pos not in POSITIONS:
            continue
        s = g[VALUE_COL]
        rows.append({
            "adp_round": int(rnd), "position": pos, "n": len(s),
            "mean": s.mean() if len(s) >= MIN_N_FOR_ANY_STAT else np.nan,
            "median": s.median() if len(s) >= MIN_N_FOR_ANY_STAT else np.nan,
            "std": s.std() if len(s) >= MIN_N_FOR_ANY_STAT else np.nan,
            "credible": len(s) >= MIN_ROUND_N_FOR_ANALYSIS,
            "insufficient_for_any_stat": len(s) < MIN_N_FOR_ANY_STAT,
        })
    return pd.DataFrame(rows).sort_values(["adp_round", "position"])


def fit_pooled_round_means(train: pd.DataFrame) -> dict:
    return train.groupby("adp_round")[VALUE_COL].mean().to_dict()


def fit_position_additive_offset(train: pd.DataFrame, round_means: dict) -> dict:
    t = train.copy()
    t["pooled_pred"] = t["adp_round"].map(round_means)
    t["residual"] = t[VALUE_COL] - t["pooled_pred"]
    return t.groupby("position")["residual"].mean().to_dict()


def fit_position_multiplicative_ratio(train: pd.DataFrame, round_means: dict) -> dict:
    """Ratio of sums (not mean-of-ratios) to avoid blowup when a single
    player-season's pooled prediction is near zero."""
    t = train.copy()
    t["pooled_pred"] = t["adp_round"].map(round_means)
    ratios = {}
    for pos, g in t.groupby("position"):
        denom = g["pooled_pred"].sum()
        ratios[pos] = g[VALUE_COL].sum() / denom if denom else np.nan
    return ratios


def run_loso(df: pd.DataFrame) -> pd.DataFrame:
    all_predictions = []
    for held_out_season in sorted(df["season"].unique()):
        train = df[df["season"] != held_out_season]
        test = df[df["season"] == held_out_season].copy()

        round_means = fit_pooled_round_means(train)
        offsets = fit_position_additive_offset(train, round_means)
        ratios = fit_position_multiplicative_ratio(train, round_means)

        test["pred_pooled"] = test["adp_round"].map(round_means)
        test["pred_additive"] = test["pred_pooled"] + test["position"].map(offsets)
        test["pred_multiplicative"] = test["pred_pooled"] * test["position"].map(ratios)
        test["held_out_season"] = held_out_season
        all_predictions.append(test)

    preds = pd.concat(all_predictions, ignore_index=True)
    preds = preds.dropna(subset=["pred_pooled", "pred_additive", "pred_multiplicative"])
    for method in ("pooled", "additive", "multiplicative"):
        preds[f"abs_err_{method}"] = (preds[VALUE_COL] - preds[f"pred_{method}"]).abs()
        preds[f"sq_err_{method}"] = (preds[VALUE_COL] - preds[f"pred_{method}"]) ** 2
    return preds


def summarize_loso(preds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scope, sub in [("ALL", preds)] + [(pos, preds[preds["position"] == pos]) for pos in POSITIONS]:
        if len(sub) < MIN_N_FOR_ANY_STAT:
            continue
        row = {"scope": scope, "n": len(sub)}
        for method in ("pooled", "additive", "multiplicative"):
            row[f"mae_{method}"] = sub[f"abs_err_{method}"].mean()
            row[f"rmse_{method}"] = np.sqrt(sub[f"sq_err_{method}"].mean())
        for method in ("additive", "multiplicative"):
            w_stat, p_value = stats.wilcoxon(sub["abs_err_pooled"], sub[f"abs_err_{method}"])
            row[f"mae_improvement_{method}_over_pooled"] = row["mae_pooled"] - row[f"mae_{method}"]
            row[f"mae_improvement_pct_{method}"] = (
                100 * (row["mae_pooled"] - row[f"mae_{method}"]) / row["mae_pooled"]
            )
            row[f"wilcoxon_p_{method}_vs_pooled"] = p_value
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    df = load_matched_with_round()
    print(f"ADP-matched player-seasons with a defined round: {len(df)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n=== 1. Position-specific round stats (secondary diagnostic) ===")
    pos_stats = position_specific_round_stats(df)
    pos_stats.to_csv(OUTPUT_DIR / "position_specific_round_stats.csv", index=False)
    n_credible = pos_stats["credible"].sum()
    n_insufficient = pos_stats["insufficient_for_any_stat"].sum()
    print(f"{len(pos_stats)} (round, position) cells total. "
          f"{n_credible} credible (n>={MIN_ROUND_N_FOR_ANALYSIS}), "
          f"{n_insufficient} insufficient for any stat (n<{MIN_N_FOR_ANY_STAT}).")
    print(pos_stats.to_string(index=False))

    print("\n=== 2. LOSO cross-validation: pooled vs. position-adjusted ===")
    preds = run_loso(df)
    preds.to_csv(OUTPUT_DIR / "position_adjustment_loso_predictions.csv", index=False)
    summary = summarize_loso(preds)
    summary.to_csv(OUTPUT_DIR / "position_adjustment_loso_summary.csv", index=False)
    print(summary.round(3).to_string(index=False))

    print(f"\nWrote position_specific_round_stats.csv, "
          f"position_adjustment_loso_predictions.csv, "
          f"position_adjustment_loso_summary.csv to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
