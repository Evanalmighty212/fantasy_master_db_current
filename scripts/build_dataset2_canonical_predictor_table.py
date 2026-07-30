"""
scripts/build_dataset2_canonical_predictor_table.py

Real-data driver for lib.dataset2.canonical_predictor_table -- loads
every real, already-cached source file, builds the canonical Dataset 2
PRESEASON PREDICTOR table (artifact 1 of
research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md's three-artifact
architecture), and writes it deterministically to
data/exports/ (gitignored, pipeline-regenerated, per CLAUDE.md -- this
script and its output are never both committed).

Writes three files:
  - dataset2_canonical_predictor_table.parquet
  - dataset2_canonical_predictor_table.csv
  - dataset2_canonical_predictor_table_data_dictionary.csv

Prints the summary this round's review explicitly asked for: row
count, season coverage, column count, duplicate-key audit, a
per-column missingness breakdown, and the deferred-family inventory.

REAL ENVIRONMENT CONSTRAINT, confirmed again this round:
`schedules.csv` is still not cached in this sandbox. This script
passes an empty (but correctly-columned) schedule frame everywhere the
underlying modules ask for one -- experience_age_draft.py's age
columns and depth_chart_traits.py's 2025 schema branch both end up
excluded/structurally-null as a direct, documented consequence (see
lib/dataset2/canonical_predictor_table.py's own module docstring).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.canonical_predictor_table import build_canonical_predictor_table

MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
PLAYERS_PATH = "data/raw/nflverse/reference/players.csv"
WEEKLY_GLOB = "data/raw/nflverse/annual/stats_player_week_*.csv"
SNAP_COUNTS_GLOB = "data/raw/nflverse/annual/snap_counts_*.csv"

OUTPUT_DIR = Path("data/exports")
PARQUET_PATH = OUTPUT_DIR / "dataset2_canonical_predictor_table.parquet"
CSV_PATH = OUTPUT_DIR / "dataset2_canonical_predictor_table.csv"
DICTIONARY_PATH = OUTPUT_DIR / "dataset2_canonical_predictor_table_data_dictionary.csv"


def _load_master_population() -> pd.DataFrame:
    df = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    return df[df["position"].isin(["QB", "RB", "WR", "TE"])]


def _load_players() -> pd.DataFrame:
    return pd.read_csv(PLAYERS_PATH, low_memory=False)


def _load_weekly() -> pd.DataFrame:
    root = Path("data/raw/nflverse/annual")
    frames = [pd.read_csv(f, low_memory=False) for f in sorted(root.glob("stats_player_week_*.csv"))]
    return pd.concat(frames, ignore_index=True)


def _load_snap_counts() -> pd.DataFrame:
    root = Path("data/raw/nflverse/annual")
    frames = [pd.read_csv(f, low_memory=False) for f in sorted(root.glob("snap_counts_*.csv"))]
    return pd.concat(frames, ignore_index=True)


def _load_depth_charts_pre2025() -> pd.DataFrame:
    root = Path("data/raw/nflverse/annual")
    files = [f for f in sorted(root.glob("depth_charts_*.csv")) if "2025" not in f.name]
    frames = [pd.read_csv(f, low_memory=False) for f in files]
    return pd.concat(frames, ignore_index=True)


def main():
    print("Loading real source data...")
    master_population = _load_master_population()
    players_df = _load_players()
    weekly_all = _load_weekly()
    weekly_reg_only = weekly_all[weekly_all["season_type"] == "REG"].copy()
    snap_counts_all = _load_snap_counts()
    depth_chart_pre2025 = _load_depth_charts_pre2025()

    print(f"  master population: {len(master_population)} rows, seasons {master_population['season'].min()}-{master_population['season'].max()}")
    print(f"  weekly (all season_types): {len(weekly_all)} rows")
    print(f"  weekly (REG only): {len(weekly_reg_only)} rows")
    print(f"  snap_counts: {len(snap_counts_all)} rows")
    print(f"  depth_charts (pre-2025 only): {len(depth_chart_pre2025)} rows")

    print("\nBuilding canonical predictor table...")
    predictor_table, column_registry, deferred_families = build_canonical_predictor_table(
        master_population, players_df, weekly_all, weekly_reg_only, snap_counts_all, depth_chart_pre2025,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    predictor_table.to_parquet(PARQUET_PATH, index=False, engine="fastparquet")
    predictor_table.to_csv(CSV_PATH, index=False)
    column_registry.to_csv(DICTIONARY_PATH, index=False)

    # --- Determinism check: rebuild once, compare byte-for-byte CSV output ---
    predictor_table_2, column_registry_2, _ = build_canonical_predictor_table(
        master_population, players_df, weekly_all, weekly_reg_only, snap_counts_all, depth_chart_pre2025,
    )
    csv_1 = predictor_table.to_csv(index=False)
    csv_2 = predictor_table_2.to_csv(index=False)
    deterministic = csv_1 == csv_2 and list(predictor_table.columns) == list(predictor_table_2.columns)

    # --- Summary ---
    print("\n" + "=" * 90)
    print("CANONICAL PRESEASON PREDICTOR TABLE -- SUMMARY")
    print("=" * 90)
    print(f"Row count: {len(predictor_table)}")
    print(f"Column count: {len(predictor_table.columns)}")
    print(f"Season coverage (prediction_season): {predictor_table['prediction_season'].min()}-{predictor_table['prediction_season'].max()}")
    print(f"Deterministic rebuild (identical CSV + column order): {deterministic}")

    dup_keys = predictor_table.duplicated(subset=["prediction_season", "player_id"]).sum()
    print(f"\nDuplicate (prediction_season, player_id) keys: {dup_keys}")
    dup_cols = predictor_table.columns[predictor_table.columns.duplicated()].tolist()
    print(f"Duplicate column names: {dup_cols if dup_cols else 'none'}")
    merge_suffix_cols = [c for c in predictor_table.columns if c.endswith("_x") or c.endswith("_y")]
    print(f"Columns with pandas merge-suffix artifacts (_x/_y): {merge_suffix_cols if merge_suffix_cols else 'none'}")

    future_rows = predictor_table[predictor_table["fam9_prediction_season_outcome_unavailable"] == True]  # noqa: E712
    print(f"\nFuture prediction_season rows (no outcome exists yet): {len(future_rows)}")
    if len(future_rows) > 0:
        print(f"  prediction_season values: {sorted(future_rows['prediction_season'].unique().tolist())}")

    print("\n--- Missingness summary (top-level, % null per column) ---")
    null_pct = (predictor_table.isna().mean() * 100).round(1).sort_values(ascending=False)
    print(null_pct.to_string())

    print("\n--- Deferred family inventory ---")
    for _, row in deferred_families.iterrows():
        print(f"  Family {row['family_number']}: {row['family_name']}")
        print(f"    Reason: {row['reason']}")

    print(f"\nWrote:\n  {PARQUET_PATH}\n  {CSV_PATH}\n  {DICTIONARY_PATH}")


if __name__ == "__main__":
    main()
