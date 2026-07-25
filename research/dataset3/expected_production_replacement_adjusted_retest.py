"""
expected_production_replacement_adjusted_retest.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Re-tests every structural finding from the raw-points investigation
(expected_production_by_round_investigation.py,
expected_production_position_adjustment_investigation.py,
expected_production_position_adjustment_residual_diagnostics.py,
expected_production_temporal_validation.py) against
points_above_replacement under the now-selected flex_rb_wr_heavy
definition (45% RB / 45% WR / 10% TE flex allocation), instead of
raw fantasy_points_ppr. Does NOT select or implement a final model.

This exists specifically because "the shape findings likely transfer"
was flagged, correctly, as an unearned assumption -- nothing here
assumes the round curve, the QB/RB offset story, or the recency-
weighting result carries over. Every one is re-run from scratch
against the new target.

Target construction: points_above_replacement is computed over the
FULL real population (games_played>=1, all QB/RB/WR/TE, 2007-2024) --
replacement level is a property of the whole real population that
season, not just the drafted subset -- then joined onto the
ADP-matched, round-assigned population
(expected_production_by_round_investigation.load_matched_with_round)
for the round-based analysis, which only makes sense for drafted
players.

Output: research/output/dataset3/retest_par_by_round_pooled.csv
        research/output/dataset3/retest_par_position_specific.csv
        research/output/dataset3/retest_par_qbrb_offset_comparison.csv
        research/output/dataset3/retest_par_temporal_comparison.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.replacement import ROSTER_PRESETS, replacement_rank_cutoff, replacement_level_from_rank
from expected_production_by_round_investigation import load_matched_with_round, MIN_ROUND_N_FOR_ANALYSIS, POSITIONS

OUTPUT_DIR = Path("research/output/dataset3")
BROAD_DATASET_PATH = OUTPUT_DIR / "broad_historical_dataset.csv"
RAW_VALUE_COL = "fantasy_points_ppr"
# broad_historical_dataset.csv already has a "points_above_replacement" column
# (LWI's own current_lwi-threshold definition) -- named distinctly here so the
# join below can't silently collide with or overwrite it.
PAR_COL = "par_flex_rb_wr_heavy"
RANK_COL = "position_finish_ppr"
WINDOW = 12
SEASON_MIN, SEASON_MAX = 2007, 2024
PRESET = ROSTER_PRESETS["12_team_standard"]
SELECTED_ALLOCATION = {"RB": 0.45, "WR": 0.45, "TE": 0.10}  # flex_rb_wr_heavy
MIN_PRIOR_SEASONS = 3
HALF_LIFE_YEARS = 5
ADJUST_POSITIONS = {"QB", "RB"}


def build_par_lookup() -> pd.DataFrame:
    """PAR under flex_rb_wr_heavy, full real population -- same
    methodology as replacement_level_definition_comparison.py."""
    df = pd.read_csv(BROAD_DATASET_PATH)
    df = df[
        (df["games_played"] >= 1)
        & (df["position"].isin(POSITIONS))
        & (df["season"].between(SEASON_MIN, SEASON_MAX))
    ].copy()
    cutoff_by_position = {pos: replacement_rank_cutoff(PRESET, pos, SELECTED_ALLOCATION) for pos in POSITIONS}
    replacement_points = replacement_level_from_rank(
        df, value_col=RAW_VALUE_COL, rank_col=RANK_COL, cutoff_by_position=cutoff_by_position, window=WINDOW,
    )
    df["replacement_points"] = replacement_points
    df[PAR_COL] = df[RAW_VALUE_COL] - df["replacement_points"]
    return df[["season", "player_id", PAR_COL]]


def load_par_round_population() -> pd.DataFrame:
    matched = load_matched_with_round().drop(columns=["points_above_replacement"], errors="ignore")
    par_lookup = build_par_lookup()
    merged = matched.merge(par_lookup, on=["season", "player_id"], how="left")
    n_before = len(merged)
    merged = merged.dropna(subset=[PAR_COL])
    if n_before - len(merged):
        print(f"  dropped {n_before - len(merged)} ADP-matched rows with no PAR value "
              f"(games_played==0 or missing rank -- shouldn't happen for drafted players, flagged if it does)")
    return merged


# ---------- 1. Pooled round-level PAR curve ----------

def round_level_stats(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    rows = []
    for rnd, g in df.groupby("adp_round"):
        s = g[value_col]
        rows.append({"adp_round": int(rnd), "n": len(s), "mean": s.mean(), "median": s.median()})
    return pd.DataFrame(rows).sort_values("adp_round")


def find_violations(round_stats: pd.DataFrame, stat_col: str) -> list:
    rs = round_stats.sort_values("adp_round").reset_index(drop=True)
    violations = []
    for i in range(1, len(rs)):
        if rs.loc[i, stat_col] > rs.loc[i - 1, stat_col]:
            violations.append((int(rs.loc[i - 1, "adp_round"]), int(rs.loc[i, "adp_round"])))
    return violations


# ---------- 2. Position-specific residual from the pooled PAR curve ----------

def position_mean_residual(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    round_means = df.groupby("adp_round")[value_col].mean().to_dict()
    d = df.copy()
    d["pooled_pred"] = d["adp_round"].map(round_means)
    d["residual"] = d[value_col] - d["pooled_pred"]
    rows = []
    for pos, g in d.groupby("position"):
        rows.append({"position": pos, "n": len(g), "mean_residual": g["residual"].mean()})
    return pd.DataFrame(rows)


# ---------- 3. QB+RB offset vs. pooled-only, expanding window + recency (reused logic, PAR target) ----------

def season_weight(season: int, asof_year: int, scheme: str) -> float:
    if scheme == "equal":
        return 1.0
    age = (asof_year - 1) - season
    return 0.5 ** (age / HALF_LIFE_YEARS)


def fit_round_means(train: pd.DataFrame, value_col: str, asof_year: int, scheme: str) -> dict:
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    return {rnd: np.average(g[value_col], weights=g["w"]) for rnd, g in t.groupby("adp_round")}


def fit_position_offsets(train: pd.DataFrame, value_col: str, round_means: dict, asof_year: int, scheme: str) -> dict:
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    t["pooled_pred"] = t["adp_round"].map(round_means)
    t["residual"] = t[value_col] - t["pooled_pred"]
    offsets = {}
    for pos in ADJUST_POSITIONS:
        sub = t[t["position"] == pos].dropna(subset=["residual"])
        offsets[pos] = np.average(sub["residual"], weights=sub["w"]) if len(sub) else np.nan
    return offsets


def walk_forward(df: pd.DataFrame, value_col: str, scheme: str) -> pd.DataFrame:
    results = []
    for asof_year in sorted(df["season"].unique()):
        train = df[df["season"] < asof_year]
        if train["season"].nunique() < MIN_PRIOR_SEASONS:
            continue
        test = df[df["season"] == asof_year].copy()
        if test.empty:
            continue
        round_means = fit_round_means(train, value_col, asof_year, scheme)
        offsets = fit_position_offsets(train, value_col, round_means, asof_year, scheme)
        test["pred_pooled"] = test["adp_round"].map(round_means)
        test["pred_qb_rb"] = test["pred_pooled"] + test["position"].map(
            lambda p: offsets.get(p, 0.0) if p in ADJUST_POSITIONS else 0.0
        )
        test["test_year"] = asof_year
        results.append(test)
    out = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    return out.dropna(subset=["pred_pooled", "pred_qb_rb"])


def summarize_walk_forward(preds: pd.DataFrame, value_col: str) -> pd.DataFrame:
    rows = []
    for scope, sub in [("ALL", preds)] + [(pos, preds[preds["position"] == pos]) for pos in POSITIONS]:
        if len(sub) < 5:
            continue
        err_pooled = (sub[value_col] - sub["pred_pooled"]).abs()
        err_adj = (sub[value_col] - sub["pred_qb_rb"]).abs()
        rows.append({
            "scope": scope, "n": len(sub),
            "mae_pooled_only": err_pooled.mean(), "mae_qb_rb_adjusted": err_adj.mean(),
            "improvement_pct": 100 * (err_pooled.mean() - err_adj.mean()) / err_pooled.mean(),
        })
    return pd.DataFrame(rows)


def main():
    print("Building points_above_replacement (flex_rb_wr_heavy) and joining to the round-based population...")
    df = load_par_round_population()
    print(f"ADP-matched, round-assigned, PAR-valued player-seasons: {len(df)}")

    print("\n=== 1. Pooled expected PRODUCTION vs. pooled expected PAR, by round ===")
    raw_stats = round_level_stats(df, RAW_VALUE_COL)
    par_stats = round_level_stats(df, PAR_COL)
    combined = raw_stats.merge(par_stats, on=["adp_round", "n"], suffixes=("_raw", "_par"))
    combined.to_csv(OUTPUT_DIR / "retest_par_by_round_pooled.csv", index=False)
    print(combined.round(1).to_string(index=False))

    raw_violations = find_violations(raw_stats, "mean")
    par_violations = find_violations(par_stats, "mean")
    print(f"\nMonotonicity violations, raw points: {raw_violations}")
    print(f"Monotonicity violations, PAR:        {par_violations}")

    print("\n=== 2. Position mean residual from the pooled curve: raw points vs. PAR ===")
    raw_resid = position_mean_residual(df, RAW_VALUE_COL).rename(columns={"mean_residual": "mean_residual_raw"})
    par_resid = position_mean_residual(df, PAR_COL).rename(columns={"mean_residual": "mean_residual_par"})
    resid_compare = raw_resid.merge(par_resid, on=["position", "n"])
    resid_compare.to_csv(OUTPUT_DIR / "retest_par_position_specific.csv", index=False)
    print(resid_compare.round(1).to_string(index=False))

    print("\n=== 3. QB+RB offset vs. pooled-only, expanding window, PAR target ===")
    equal_preds = walk_forward(df, PAR_COL, "equal")
    recency_preds = walk_forward(df, PAR_COL, "recency")
    equal_summary = summarize_walk_forward(equal_preds, PAR_COL)
    equal_summary["scheme"] = "equal"
    recency_summary = summarize_walk_forward(recency_preds, PAR_COL)
    recency_summary["scheme"] = "recency"
    temporal_comparison = pd.concat([equal_summary, recency_summary], ignore_index=True)
    temporal_comparison.to_csv(OUTPUT_DIR / "retest_par_temporal_comparison.csv", index=False)
    print(temporal_comparison.round(3).to_string(index=False))

    print("\n=== 4. Equal vs. recency weighting, paired comparison, PAR target ===")
    e = equal_preds.reset_index(drop=True)
    r = recency_preds.reset_index(drop=True)
    e["abs_err"] = (e[PAR_COL] - e["pred_qb_rb"]).abs()
    r["abs_err"] = (r[PAR_COL] - r["pred_qb_rb"]).abs()
    rows = []
    for scope, e_sub, r_sub in [("ALL", e, r)] + [(pos, e[e["position"] == pos], r[r["position"] == pos]) for pos in POSITIONS]:
        if len(e_sub) < 5 or len(e_sub) != len(r_sub):
            continue
        _, p_value = stats.wilcoxon(e_sub["abs_err"].values, r_sub["abs_err"].values)
        rows.append({
            "scope": scope, "n": len(e_sub),
            "mae_equal": e_sub["abs_err"].mean(), "mae_recency": r_sub["abs_err"].mean(),
            "improvement_pct": 100 * (e_sub["abs_err"].mean() - r_sub["abs_err"].mean()) / e_sub["abs_err"].mean(),
            "wilcoxon_p": p_value,
        })
    print(pd.DataFrame(rows).round(4).to_string(index=False))

    print(f"\nWrote 4 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
