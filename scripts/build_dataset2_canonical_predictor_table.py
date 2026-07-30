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

SCHEDULE DATA (2026-07): `schedules.csv` (nflverse `games.csv`) was
fetched and pinned via the established GitHub Actions/nflverse_source.py
path (scripts/ci_fetch_schedules.py) -- 7,548 real games, seasons
1999-2026, sha256-verified against scripts/nflverse_source_manifest.json's
`"schedules"` entry. This script loads it via
`nflverse_source.fetch_schedules()` (same cached-asset-id +
integrity-check convention as every other real source this pipeline
uses) and passes the REAL frame to
build_canonical_predictor_table(), which now includes family #2 (age)
-- see lib/dataset2/canonical_predictor_table.py's module docstring's
AGE INCLUSION section. depth_chart_traits.py's own 2025-schema branch
is a SEPARATE, still-deferred empty-schedule usage (its own preseason-
snapshot-selection concern, not touched by this change) -- see that
module's own docstring.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))
from lib.dataset2.canonical_predictor_table import build_canonical_predictor_table
import nflverse_source

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


def _load_schedules() -> pd.DataFrame:
    return nflverse_source.fetch_schedules()


def main():
    print("Loading real source data...")
    master_population = _load_master_population()
    players_df = _load_players()
    weekly_all = _load_weekly()
    weekly_reg_only = weekly_all[weekly_all["season_type"] == "REG"].copy()
    snap_counts_all = _load_snap_counts()
    depth_chart_pre2025 = _load_depth_charts_pre2025()
    schedule_df = _load_schedules()

    print(f"  master population: {len(master_population)} rows, seasons {master_population['season'].min()}-{master_population['season'].max()}")
    print(f"  weekly (all season_types): {len(weekly_all)} rows")
    print(f"  weekly (REG only): {len(weekly_reg_only)} rows")
    print(f"  snap_counts: {len(snap_counts_all)} rows")
    print(f"  depth_charts (pre-2025 only): {len(depth_chart_pre2025)} rows")
    print(f"  schedules: {len(schedule_df)} rows, seasons {schedule_df['season'].min()}-{schedule_df['season'].max()}")

    print("\nBuilding canonical predictor table...")
    predictor_table, column_registry, deferred_families = build_canonical_predictor_table(
        master_population, players_df, weekly_all, weekly_reg_only, snap_counts_all, depth_chart_pre2025, schedule_df,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    predictor_table.to_parquet(PARQUET_PATH, index=False, engine="fastparquet")
    predictor_table.to_csv(CSV_PATH, index=False)
    column_registry.to_csv(DICTIONARY_PATH, index=False)

    # --- Determinism check: rebuild once, compare byte-for-byte CSV output ---
    predictor_table_2, column_registry_2, _ = build_canonical_predictor_table(
        master_population, players_df, weekly_all, weekly_reg_only, snap_counts_all, depth_chart_pre2025, schedule_df,
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

    # --- Missingness, position-scope-adjusted (real revision this round) ---
    # A non-QB row's real <NA> on a QB-only column (e.g. a WR's
    # fam9_*_qb_passing_role_present) is CORRECT, INTENTIONAL
    # inapplicability, not "missing data" -- reporting its null rate
    # against the FULL population silently inflates it and hides that
    # distinction. column_registry's own `position_scope` (real,
    # inferred from each column's canonical name, verified against
    # every real column this round -- see
    # lib/dataset2/canonical_predictor_table.py::_infer_position_scope())
    # is used here so each column's null rate is computed within its
    # OWN applicable population, never the full 11,784-row table for a
    # position-scoped column.
    print("\n--- Missingness summary (position-scope-adjusted) ---")
    scope_by_col = column_registry.set_index("canonical_column")["position_scope"].to_dict()
    rows = []
    for col in predictor_table.columns:
        scope = scope_by_col.get(col, "ALL")
        if scope == "ALL":
            applicable = predictor_table
        else:
            applicable = predictor_table[predictor_table["position"] == scope]
        n_applicable = len(applicable)
        null_pct_scoped = round(applicable[col].isna().mean() * 100, 1) if n_applicable else float("nan")
        rows.append({"column": col, "position_scope": scope, "n_applicable_rows": n_applicable, "null_pct_within_scope": null_pct_scoped})
    missingness_df = pd.DataFrame(rows).sort_values("null_pct_within_scope", ascending=False)
    position_scoped_count = (missingness_df["position_scope"] != "ALL").sum()
    print(f"Columns scoped to a single position (excluded from the full-population denominator above): {position_scoped_count}")
    print("Top 15 by within-scope null %:")
    print(missingness_df.head(15).to_string(index=False))
    print("\nBottom 15 (least missing) by within-scope null %:")
    print(missingness_df.tail(15).to_string(index=False))
    missingness_df.to_csv(OUTPUT_DIR / "dataset2_canonical_predictor_table_missingness.csv", index=False)

    print("\n--- Deferred family inventory ---")
    for _, row in deferred_families.iterrows():
        print(f"  Family {row['family_number']}: {row['family_name']}")
        print(f"    Reason: {row['reason']}")

    print(f"\nWrote:\n  {PARQUET_PATH}\n  {CSV_PATH}\n  {DICTIONARY_PATH}")


if __name__ == "__main__":
    main()
