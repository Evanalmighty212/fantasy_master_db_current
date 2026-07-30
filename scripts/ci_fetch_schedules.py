"""
scripts/ci_fetch_schedules.py

CI-only driver for scripts/nflverse_source.py's real schedules
(games.csv) fetch -- the ONLY prerequisite blocking family #2 (age)
per lib/dataset2/canonical_predictor_table.py's DEFERRED_FAMILIES. The
fetch/pin/integrity-check machinery already exists in nflverse_source.py
(register_schedules_manifest_entry(), fetch_schedules_raw(),
fetch_schedules()) -- this script only PINS the asset for the first
time (this environment has never had real outbound internet to nflverse's
GitHub releases; local checks this round confirmed it directly) and
prints a coverage summary for the workflow's own review step, per this
project's established "review deliberately, never auto-commit" CI
convention (see fetch_adp.yml, fetch_mfl_historical.yml).

Run only inside GitHub Actions (a real outbound-internet environment)
-- see .github/workflows/fetch_schedules_and_firth_crosscheck.yml.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

import nflverse_source


def main():
    print("Registering the 'schedules' manifest entry (pins the real asset id + sha256)...")
    entry = nflverse_source.register_schedules_manifest_entry()
    print(f"  asset_id={entry['asset_id']}")
    print(f"  upstream_updated_at={entry['upstream_updated_at']}")
    print(f"  sha256={entry['sha256']}")
    print(f"  row_count={entry['row_count']}")

    print("\nFetching (verifying against the just-pinned hash)...")
    schedules = nflverse_source.fetch_schedules()
    print(f"Loaded {len(schedules)} rows, columns: {list(schedules.columns)}")

    print("\n=== Real season coverage ===")
    print(f"season range: {schedules['season'].min()}-{schedules['season'].max()}")
    print(f"distinct seasons: {schedules['season'].nunique()}")

    print("\n=== Real Week-1 date coverage (per season, regular season only) ===")
    reg = schedules[schedules["game_type"] == "REG"] if "game_type" in schedules.columns else schedules
    week1 = reg[reg["week"] == 1]
    week1_summary = week1.groupby("season")["gameday"].agg(["min", "max", "count"])
    print(week1_summary.to_string())

    print("\n=== Missing/null check on fields age computation needs ===")
    for col in ("season", "week", "gameday", "home_team", "away_team", "game_type"):
        if col in schedules.columns:
            n_null = schedules[col].isna().sum()
            print(f"  {col}: {n_null} null of {len(schedules)}")
        else:
            print(f"  {col}: COLUMN MISSING")

    summary_path = Path("data/raw/nflverse/reference/schedules_fetch_summary.csv")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    week1_summary.to_csv(summary_path)
    print(f"\nWrote {summary_path}")


if __name__ == "__main__":
    main()
