"""
replacement_cross_position_calibration_check.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Checks whether the top-25 PAR list's heavy RB skew (~21-22 RB, 2-3 WR,
1 QB, 0 TE, under flex_rb_wr_heavy) reflects genuine historical
value-over-replacement patterns, or whether PAR is structurally easier
for some positions to accumulate than others. Does NOT force equal
positional representation and does NOT modify the replacement
definition -- this is a diagnostic, not a fix.

Population: same as replacement_level_definition_comparison.py --
QB/RB/WR/TE player-seasons, games_played>=1, 2007-2024, PAR computed
under flex_rb_wr_heavy (45% RB / 45% WR / 10% TE FLEX allocation).

Output: research/output/dataset3/calibration_top_representation_by_era.csv
        research/output/dataset3/calibration_par_distribution_by_position.csv
        research/output/dataset3/calibration_position_champions.csv
        research/output/dataset3/calibration_ceiling_headroom.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.eras import assign_era
from lib.replacement import ROSTER_PRESETS, FLEX_ALLOCATION_RB_WR_HEAVY, replacement_rank_cutoff, replacement_level_from_rank

OUTPUT_DIR = Path("research/output/dataset3")
BROAD_DATASET_PATH = OUTPUT_DIR / "broad_historical_dataset.csv"
RAW_VALUE_COL = "fantasy_points_ppr"
RANK_COL = "position_finish_ppr"
WINDOW = 12
POSITIONS = ["QB", "RB", "WR", "TE"]
SEASON_MIN, SEASON_MAX = 2007, 2024
PRESET = ROSTER_PRESETS["12_team_standard"]


def load_population_with_par() -> pd.DataFrame:
    df = pd.read_csv(BROAD_DATASET_PATH)
    df = df[
        (df["games_played"] >= 1)
        & (df["position"].isin(POSITIONS))
        & (df["season"].between(SEASON_MIN, SEASON_MAX))
    ].copy()
    cutoff_by_position = {pos: replacement_rank_cutoff(PRESET, pos, FLEX_ALLOCATION_RB_WR_HEAVY) for pos in POSITIONS}
    replacement_points = replacement_level_from_rank(
        df, value_col=RAW_VALUE_COL, rank_col=RANK_COL, cutoff_by_position=cutoff_by_position, window=WINDOW,
    )
    df["replacement_points"] = replacement_points
    df["par"] = df[RAW_VALUE_COL] - df["replacement_points"]
    df["era"] = df["season"].apply(assign_era)
    return df, cutoff_by_position


def main():
    df, cutoffs = load_population_with_par()
    print(f"Population: {len(df)} player-seasons, cutoffs: {cutoffs}")

    era_season_counts = df.groupby("era")["season"].nunique().to_dict()
    print(f"Seasons per era: {era_season_counts}")

    print("\n=== 1. Top-25 / top-100 position representation, overall and by era ===")
    rep_rows = []
    for n in (25, 100):
        top_overall = df.nlargest(n, "par")
        counts = top_overall["position"].value_counts().reindex(POSITIONS, fill_value=0)
        rep_rows.append({"top_n": n, "era": "ALL", **counts.to_dict()})
        for era, g in df.groupby("era"):
            top_era = g.nlargest(n, "par")
            counts_era = top_era["position"].value_counts().reindex(POSITIONS, fill_value=0)
            rep_rows.append({"top_n": n, "era": era, **counts_era.to_dict()})
    rep_df = pd.DataFrame(rep_rows)
    rep_df.to_csv(OUTPUT_DIR / "calibration_top_representation_by_era.csv", index=False)
    print(rep_df.to_string(index=False))

    print("\n=== 2. PAR distribution by position (full population) ===")
    dist_rows = []
    for pos, g in df.groupby("position"):
        s = g["par"]
        dist_rows.append({
            "position": pos, "n": len(s), "mean": s.mean(), "median": s.median(), "std": s.std(),
            "p75": s.quantile(0.75), "p90": s.quantile(0.90), "p99": s.quantile(0.99), "max": s.max(),
        })
    dist_df = pd.DataFrame(dist_rows)
    dist_df.to_csv(OUTPUT_DIR / "calibration_par_distribution_by_position.csv", index=False)
    print(dist_df.round(1).to_string(index=False))

    print("\n=== 3. 'Equally exceptional' check: each season's #1 finisher at each position ===")
    champions = df[df[RANK_COL] == 1]
    champ_summary = champions.groupby("position")["par"].agg(["count", "mean", "median", "std", "min", "max"])
    champ_summary.to_csv(OUTPUT_DIR / "calibration_position_champions.csv")
    print(champ_summary.round(1).to_string())
    print("\nFull list of position champions (season, position, player, par):")
    print(champions[["season", "position", "player_name", "par"]].sort_values(["position", "season"]).to_string(index=False))

    print("\n=== 4. Ceiling headroom: does one position's talent pool structurally spread wider? ===")
    headroom_rows = []
    for pos, g in df.groupby("position"):
        avg_replacement = g["replacement_points"].mean()
        top5_by_season = g.groupby("season")[RAW_VALUE_COL].apply(lambda s: s.nlargest(5).mean())
        avg_top5 = top5_by_season.mean()
        top1_by_season = g.groupby("season")[RAW_VALUE_COL].max()
        avg_top1 = top1_by_season.mean()
        headroom_rows.append({
            "position": pos, "cutoff_rank": cutoffs[pos],
            "avg_replacement_points": avg_replacement,
            "avg_top1_points": avg_top1, "avg_top5_points": avg_top5,
            "headroom_top1_minus_replacement": avg_top1 - avg_replacement,
            "headroom_top5_minus_replacement": avg_top5 - avg_replacement,
        })
    headroom_df = pd.DataFrame(headroom_rows)
    headroom_df.to_csv(OUTPUT_DIR / "calibration_ceiling_headroom.csv", index=False)
    print(headroom_df.round(1).to_string(index=False))

    print(f"\nWrote 4 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
