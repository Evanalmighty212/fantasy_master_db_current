"""
expected_production_by_round_investigation.py  (Dataset 3 research foundation)

EXPLORATORY ONLY -- investigates raw historical fantasy production by
ADP round, pooling ALL player-seasons within a round across ALL 18
seasons (2007-2024) and ALL positions, per the task: "use all
historical players in each draft round across seasons rather than
averaging seasons first." Does NOT fit, smooth, or select an
expected-production model -- this script exists specifically to let
the raw data be inspected BEFORE any smoothing decision is made.

Round definition: ceil(overall_adp_observed / 12), matching
expected_production_tables.py's existing adp_round() convention
(TEAMS_FOR_ROUND = 12, config.py's TEAMS) -- reused directly, not
redefined, so "round" means the same thing everywhere in this
project's research code.

Production measure: fantasy_points_ppr (raw season total) is primary,
since this is a "production" question, not a rank/finish question --
distinct from Component 1's overall_finish_ppr-based approach. ppg_ppr
is reported alongside as a secondary, games-played-independent lens.

IMPORTANT CONFOUND, surfaced explicitly rather than glossed over:
pooling ACROSS POSITIONS on raw fantasy_points_ppr is NOT
position-neutral -- QBs structurally score more raw points than
RB/WR/TE in this scoring format, so a round with an unusually
QB-heavy composition can show elevated pooled production for reasons
having nothing to do with "value," purely from position mix. This
script reports each round's position composition explicitly and
re-tests every violation WITHIN position specifically to separate a
real phenomenon from a pooling artifact -- see compare_within_position().

Restricted to adp_matched == True rows (drafted, real ADP) -- ADP
round is undefined for unresolved/undrafted rows. This also naturally
excludes 2006 and 2025 (0 adp_matched rows each, verified) without any
season-specific carve-out in this script: 2006 has no established ADP
source, and 2025 is excluded from ADP-dependent fitting per the
canonical-2025-ADP investigation (docs/ADP_SOURCE_MATRIX.md's "2025
Cross-Source Validation" section) -- both exclusions are already
enforced upstream, not re-implemented here.

Input:  research/output/dataset3/broad_historical_dataset.csv
Output: research/output/dataset3/expected_production_by_round_pooled.csv
        research/output/dataset3/expected_production_by_round_violations.csv
        research/output/dataset3/expected_production_by_round_position_mix.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expected_production_tables import adp_round  # reuse, don't redefine

BROAD_DATASET_PATH = Path("research/output/dataset3/broad_historical_dataset.csv")
OUTPUT_DIR = Path("research/output/dataset3")

PERCENTILES = [0.10, 0.25, 0.50, 0.75, 0.90]
MIN_ROUND_N_FOR_ANALYSIS = 20  # rounds below this are reported but flagged low-confidence
POSITIONS = ["QB", "RB", "WR", "TE"]


def load_matched_with_round() -> pd.DataFrame:
    df = pd.read_csv(BROAD_DATASET_PATH)
    matched = df[df["adp_matched"]].copy()
    matched["adp_round"] = matched["overall_adp_observed"].apply(adp_round)
    return matched


def round_level_stats(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    rows = []
    for rnd, g in df.groupby("adp_round"):
        s = g[value_col]
        row = {
            "adp_round": int(rnd), "n": len(s),
            "mean": s.mean(), "median": s.median(), "std": s.std(),
        }
        for p in PERCENTILES:
            row[f"p{int(p*100)}"] = s.quantile(p)
        row["min"] = s.min()
        row["max"] = s.max()
        row["skew_mean_minus_median"] = s.mean() - s.median()
        rows.append(row)
    return pd.DataFrame(rows).sort_values("adp_round")


def find_violations(round_stats: pd.DataFrame, stat_col: str) -> list:
    """A violation: round R's stat_col > round (R-1)'s, i.e. a LATER
    (higher-numbered, cheaper) round shows a HIGHER expected value than
    the round drafted immediately before it."""
    violations = []
    rs = round_stats.sort_values("adp_round").reset_index(drop=True)
    for i in range(1, len(rs)):
        prev_round, cur_round = rs.loc[i - 1, "adp_round"], rs.loc[i, "adp_round"]
        prev_val, cur_val = rs.loc[i - 1, stat_col], rs.loc[i, stat_col]
        if cur_val > prev_val:
            violations.append({
                "earlier_round": int(prev_round), "later_round": int(cur_round),
                f"earlier_{stat_col}": prev_val, f"later_{stat_col}": cur_val,
                "gap": cur_val - prev_val,
            })
    return violations


def position_mix(df: pd.DataFrame) -> pd.DataFrame:
    mix = (
        df.groupby(["adp_round", "position"]).size().unstack(fill_value=0)
    )
    mix = mix.reindex(columns=POSITIONS, fill_value=0)
    pct = mix.div(mix.sum(axis=1), axis=0) * 100
    pct.columns = [f"pct_{c}" for c in pct.columns]
    out = pd.concat([mix.sum(axis=1).rename("n"), pct], axis=1).reset_index()
    return out


def compare_rounds(df: pd.DataFrame, earlier_round: int, later_round: int, value_col: str) -> dict:
    """Mann-Whitney U test (rank-sum), matching the project's stated
    convention for significance checks at this sample scale (per
    docs/LEAGUE_WINNER_TRAITS_SPEC.md's proposed rank-sum/proportions
    test for categorical trait testing) -- reused here for the same
    reason: a directional difference at this sample size is a real,
    checkable question, not something to eyeball."""
    a = df[df["adp_round"] == earlier_round][value_col].dropna()
    b = df[df["adp_round"] == later_round][value_col].dropna()
    if len(a) < 2 or len(b) < 2:
        return {"n_earlier": len(a), "n_later": len(b), "p_value": np.nan, "note": "insufficient n for test"}
    u_stat, p_value = stats.mannwhitneyu(b, a, alternative="greater")
    return {
        "n_earlier": len(a), "n_later": len(b),
        "mean_earlier": a.mean(), "mean_later": b.mean(),
        "median_earlier": a.median(), "median_later": b.median(),
        "u_statistic": u_stat, "p_value": p_value,
    }


def compare_within_position(df: pd.DataFrame, earlier_round: int, later_round: int, value_col: str) -> pd.DataFrame:
    rows = []
    for pos in POSITIONS:
        a = df[(df["adp_round"] == earlier_round) & (df["position"] == pos)][value_col].dropna()
        b = df[(df["adp_round"] == later_round) & (df["position"] == pos)][value_col].dropna()
        row = {"position": pos, "n_earlier": len(a), "n_later": len(b)}
        if len(a) >= 5 and len(b) >= 5:
            row["mean_earlier"] = a.mean()
            row["mean_later"] = b.mean()
            row["violation_persists_within_position"] = b.mean() > a.mean()
            u_stat, p_value = stats.mannwhitneyu(b, a, alternative="greater")
            row["p_value"] = p_value
        else:
            row["mean_earlier"] = a.mean() if len(a) else np.nan
            row["mean_later"] = b.mean() if len(b) else np.nan
            row["violation_persists_within_position"] = None
            row["p_value"] = np.nan
            row["note"] = "n<5 in one or both rounds -- not tested"
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    df = load_matched_with_round()
    print(f"ADP-matched player-seasons with a defined round: {len(df)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    points_stats = round_level_stats(df, "fantasy_points_ppr")
    ppg_stats = round_level_stats(df, "ppg_ppr")
    combined = points_stats.merge(ppg_stats, on=["adp_round", "n"], suffixes=("_points", "_ppg"))
    combined_path = OUTPUT_DIR / "expected_production_by_round_pooled.csv"
    combined.to_csv(combined_path, index=False)

    print("\n=== Pooled round-level stats (fantasy_points_ppr) ===")
    cols = ["adp_round", "n", "mean_points", "median_points", "std_points",
            "p10_points", "p25_points", "p75_points", "p90_points", "skew_mean_minus_median_points"]
    print(combined[cols].to_string(index=False))

    low_n_rounds = combined[combined["n"] < MIN_ROUND_N_FOR_ANALYSIS]["adp_round"].tolist()
    print(f"\nRounds below n={MIN_ROUND_N_FOR_ANALYSIS} (low-confidence, flagged not excluded): {low_n_rounds}")

    print("\n=== Position composition by round ===")
    mix = position_mix(df)
    mix_path = OUTPUT_DIR / "expected_production_by_round_position_mix.csv"
    mix.to_csv(mix_path, index=False)
    print(mix.round(1).to_string(index=False))

    print("\n=== MONOTONICITY VIOLATIONS (mean fantasy_points_ppr) ===")
    mean_violations = find_violations(points_stats.rename(columns={"mean": "mean"}), "mean")
    median_violations = find_violations(points_stats.rename(columns={"median": "median"}), "median")
    print(f"Mean-based violations: {[(v['earlier_round'], v['later_round']) for v in mean_violations]}")
    print(f"Median-based violations: {[(v['earlier_round'], v['later_round']) for v in median_violations]}")

    violation_rows = []
    for v in mean_violations:
        er, lr = v["earlier_round"], v["later_round"]
        test = compare_rounds(df, er, lr, "fantasy_points_ppr")
        within_pos = compare_within_position(df, er, lr, "fantasy_points_ppr")
        persists = within_pos["violation_persists_within_position"].fillna(False)
        n_positions_persisting = int(persists.sum())

        print(f"\n--- Violation: round {er} -> round {lr} ---")
        print(f"  Pooled means: {test.get('mean_earlier', float('nan')):.1f} -> {test.get('mean_later', float('nan')):.1f} "
              f"(n={test['n_earlier']} vs n={test['n_later']}), Mann-Whitney p={test.get('p_value', float('nan')):.4f}")
        print(f"  Position mix, round {er}: " + ", ".join(
            f"{p}={mix.loc[mix['adp_round']==er, f'pct_{p}'].values[0]:.0f}%" for p in POSITIONS))
        print(f"  Position mix, round {lr}: " + ", ".join(
            f"{p}={mix.loc[mix['adp_round']==lr, f'pct_{p}'].values[0]:.0f}%" for p in POSITIONS))
        print(f"  Within-position: violation persists for {n_positions_persisting}/4 positions tested")
        print(within_pos.to_string(index=False))

        violation_rows.append({
            "earlier_round": er, "later_round": lr,
            "pooled_mean_earlier": test.get("mean_earlier"), "pooled_mean_later": test.get("mean_later"),
            "n_earlier": test["n_earlier"], "n_later": test["n_later"],
            "mann_whitney_p_value": test.get("p_value"),
            "n_positions_violation_persists": n_positions_persisting,
        })

    pd.DataFrame(violation_rows).to_csv(OUTPUT_DIR / "expected_production_by_round_violations.csv", index=False)
    print(f"\nWrote {combined_path}, {mix_path}, and violations CSV.")


if __name__ == "__main__":
    main()
