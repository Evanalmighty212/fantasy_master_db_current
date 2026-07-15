"""
03_download_stats.py

Purpose:
- Download weekly nflverse data for every season in scope.
- Aggregate to season-level PPR fantasy results.
- Compute overall and positional finish ranks.

Input:  config.SEASONS
Output: data/raw/nflverse/season_results_ppr_<start>_<end>.csv
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import nfl_data_py as nfl

from config import SEASONS

RAW_DIR = Path("data/raw/nflverse")
RAW_DIR.mkdir(parents=True, exist_ok=True)


def build_season_results():
    print("Step 1: Downloading weekly nflverse data...")
    frames = []
    failed = []

    for season in SEASONS:
        try:
            print(f"  downloading {season}...")
            frames.append(nfl.import_weekly_data([season]))
        except Exception as e:
            print(f"  FAILED {season}: {e}")
            failed.append({"season": season, "error": str(e)})

    if not frames:
        raise RuntimeError("No weekly data downloaded.")

    weekly = pd.concat(frames, ignore_index=True)
    weekly = weekly[weekly["season_type"] == "REG"].copy()

    pd.DataFrame(failed).to_csv(RAW_DIR / "weekly_download_failures.csv", index=False)

    print("Step 2: Building season-level PPR results...")
    group_cols = [
        "season",
        "player_id",
        "player_display_name",
        "position",
        "recent_team",
    ]

    season = (
        weekly.groupby(group_cols, dropna=False)
        .agg(
            games_played=("week", "nunique"),
            fantasy_points_ppr=("fantasy_points_ppr", "sum"),
            ppg_ppr=("fantasy_points_ppr", "mean"),
        )
        .reset_index()
    )

    season["overall_finish_ppr"] = (
        season.groupby("season")["fantasy_points_ppr"]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )

    season["position_finish_ppr"] = (
        season.groupby(["season", "position"])["fantasy_points_ppr"]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )

    season = season.sort_values(["season", "overall_finish_ppr"])

    out_path = RAW_DIR / f"season_results_ppr_{SEASONS[0]}_{SEASONS[-1]}.csv"
    season.to_csv(out_path, index=False)

    print(f"Created {out_path}")
    print(f"Rows: {len(season)}")

    return season


def main():
    build_season_results()


if __name__ == "__main__":
    main()
