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

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))
from lib.player_season_authority import resolved_canonical_position_population
from lib.dataset2.canonical_predictor_table import build_canonical_predictor_table
from lib.dataset2.common import week1_kickoff_by_team
from lib.dataset2.future_season_spine import (
    ROSTER_SNAPSHOT_REQUIRED_COLUMNS,
    RosterSpineResult,
    build_future_season_roster_spine,
    roster_status_provenance_frame,
)
import nflverse_source

MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
PLAYERS_PATH = "data/raw/nflverse/reference/players.csv"
WEEKLY_GLOB = "data/raw/nflverse/annual/stats_player_week_*.csv"
SNAP_COUNTS_GLOB = "data/raw/nflverse/annual/snap_counts_*.csv"
GOVERNED_PRE2025_DEPTH_CHART_SEASONS = tuple(range(2006, 2025))
PRE2025_DEPTH_CHART_REQUIRED_COLUMNS = {
    "season", "club_code", "week", "game_type", "depth_team", "position", "gsis_id",
}

OUTPUT_DIR = Path("data/exports")
PARQUET_PATH = OUTPUT_DIR / "dataset2_canonical_predictor_table.parquet"
CSV_PATH = OUTPUT_DIR / "dataset2_canonical_predictor_table.csv"
DICTIONARY_PATH = OUTPUT_DIR / "dataset2_canonical_predictor_table_data_dictionary.csv"


def _load_master_population() -> pd.DataFrame:
    df = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    required = {
        "canonical_fantasy_position", "canonical_position_status",
        "canonical_position_authority", "canonical_team", "historical_input_revision",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Master dataset lacks canonical authority fields: {missing}")
    df = resolved_canonical_position_population(df)
    df["team"] = df["canonical_team"]
    return df


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


class DepthChartSourceIntegrityError(RuntimeError):
    """One governed depth-chart season cannot be trusted or parsed."""


def _governed_depth_chart_path(season: int) -> Path:
    return nflverse_source.DEPTH_CHARTS_CACHE_DIR / f"depth_charts_{season}.csv"


def _load_depth_charts_pre2025(
    seasons=GOVERNED_PRE2025_DEPTH_CHART_SEASONS,
) -> pd.DataFrame:
    """Validate and parse every governed 2006-2024 depth-chart source.

    This is deliberately an explicit season preflight rather than a glob:
    a missing season, extra file, or opaque list-comprehension parse failure
    must never silently change Dataset 2 Families 10/86. Local presence is
    required here; canonical pipeline execution does not perform an implicit
    network reacquisition. ``fetch_depth_chart_raw`` then enforces the
    committed manifest entry and SHA-256 before any CSV is parsed.
    """
    governed_paths: list[tuple[int, Path]] = []
    for season in seasons:
        path = _governed_depth_chart_path(season)
        if not path.is_file():
            raise DepthChartSourceIntegrityError(
                f"depth-chart source missing for season {season}: {path}. "
                "Restore/reacquire the governed manifest-pinned input; do not skip the season."
            )
        try:
            validated_path = nflverse_source.fetch_depth_chart_raw(season)
        except RuntimeError as exc:
            category = "hash mismatch" if "INTEGRITY CHECK FAILED" in str(exc) else "manifest validation failure"
            raise DepthChartSourceIntegrityError(
                f"depth-chart {category} for season {season} at {path}: {exc}"
            ) from exc
        except OSError as exc:
            raise DepthChartSourceIntegrityError(
                f"depth-chart source unreadable for season {season} at {path}: {exc}"
            ) from exc
        validated_path = Path(validated_path)
        if validated_path != path:
            raise DepthChartSourceIntegrityError(
                f"depth-chart manifest path disagreement for season {season}: expected {path}, got {validated_path}"
            )
        governed_paths.append((season, path))

    frames: list[pd.DataFrame] = []
    for season, path in governed_paths:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise DepthChartSourceIntegrityError(
                f"depth-chart source unreadable for season {season} at {path}: {exc}"
            ) from exc
        if not raw.strip():
            raise DepthChartSourceIntegrityError(
                f"depth-chart source blank/headerless for season {season} at {path}: no CSV content"
            )
        first_line = raw.splitlines()[0].decode("utf-8", errors="replace")
        header_columns = {column.strip().strip('"') for column in first_line.split(",")}
        if not PRE2025_DEPTH_CHART_REQUIRED_COLUMNS <= header_columns:
            if not (PRE2025_DEPTH_CHART_REQUIRED_COLUMNS & header_columns):
                category = "blank/headerless"
            else:
                category = "malformed CSV/schema"
            missing = sorted(PRE2025_DEPTH_CHART_REQUIRED_COLUMNS - header_columns)
            raise DepthChartSourceIntegrityError(
                f"depth-chart source {category} for season {season} at {path}: "
                f"required header columns missing {missing}"
            )
        try:
            frame = pd.read_csv(path, low_memory=False)
        except pd.errors.EmptyDataError as exc:
            raise DepthChartSourceIntegrityError(
                f"depth-chart source blank/headerless for season {season} at {path}: {exc}"
            ) from exc
        except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
            raise DepthChartSourceIntegrityError(
                f"depth-chart source malformed CSV for season {season} at {path}: {exc}"
            ) from exc
        missing_columns = sorted(PRE2025_DEPTH_CHART_REQUIRED_COLUMNS - set(frame.columns))
        if missing_columns:
            raise DepthChartSourceIntegrityError(
                f"depth-chart source malformed CSV/schema for season {season} at {path}: "
                f"required columns missing {missing_columns}"
            )
        if frame.empty:
            raise DepthChartSourceIntegrityError(
                f"depth-chart source blank/headerless for season {season} at {path}: header has no data rows"
            )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _load_schedules() -> pd.DataFrame:
    return nflverse_source.fetch_schedules()


# --- --live-2026-spine: opt-in governed live-2026 future-season spine ---
#
# Off by default. Loading any of this machinery, or touching
# players.csv/games.csv's manifest at all, is gated behind
# args.live_2026_spine in main() below -- the default (no-flag) build
# path never imports or calls any of it, so it cannot change the
# default build's behavior even by accident.

LIVE_SPINE_INCLUDED_PATH = OUTPUT_DIR / "dataset2_future_season_roster_spine.csv"
LIVE_SPINE_EXCLUDED_PATH = OUTPUT_DIR / "dataset2_future_season_roster_spine_excluded.csv"
LIVE_SPINE_SIDECAR_PATH = OUTPUT_DIR / "dataset2_future_season_roster_status_sidecar.csv"
LIVE_SPINE_HASH_MANIFEST_PATH = OUTPUT_DIR / "dataset2_future_season_roster_spine.sha256"


class LiveSpineProvenanceError(RuntimeError):
    """A live-2026 build's snapshot provenance could not be verified
    safely -- a missing/checksum-invalid governed source, or a snapshot
    that is not strictly before the earliest real Week 1 kickoff.
    Always raised BEFORE any roster spine is built or any row of the
    canonical table is touched."""


def _earliest_week1_kickoff_utc_date(schedule_df: pd.DataFrame, season: int) -> pd.Timestamp:
    """Earliest real per-team Week 1 REG kickoff date for `season`,
    normalized to a timezone-AWARE UTC midnight Timestamp.

    nflverse's `gameday` carries no time-of-day or timezone at all --
    only a bare calendar-date string (confirmed directly:
    lib.dataset2.common.week1_kickoff_by_team() parses it with a plain
    `pd.to_datetime(row["gameday"])`, which produces a timezone-NAIVE
    Timestamp). Calendar-date precision is therefore the most this can
    honestly claim -- comparing at finer granularity would assert a
    precision the source data doesn't actually have.
    """
    kickoffs = week1_kickoff_by_team(schedule_df, season)
    if not kickoffs:
        raise LiveSpineProvenanceError(
            f"No real Week 1 REG kickoff games found in schedule data for season {season} -- "
            "cannot verify a snapshot cutoff without at least one real game."
        )
    dates = []
    for value in kickoffs.values():
        ts = pd.Timestamp(value)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        dates.append(ts.normalize())
    return min(dates)


def _verify_snapshot_before_cutoff(retrieved_at: str, earliest_kickoff_utc_date: pd.Timestamp) -> None:
    """Fails loudly, by name (LiveSpineProvenanceError, never a bare
    ValueError/AssertionError), unless `retrieved_at`'s own UTC
    calendar date is strictly earlier than `earliest_kickoff_utc_date`.

    Refuses to compare a timezone-naive `retrieved_at` at all --
    guessing UTC for an unlabeled timestamp is exactly the kind of
    silent assumption this project's leakage rule exists to prevent.
    A snapshot dated the SAME calendar day as kickoff is rejected, not
    accepted -- "strictly before," not "on or before."
    """
    retrieved = pd.Timestamp(retrieved_at)
    if retrieved.tzinfo is None:
        raise LiveSpineProvenanceError(
            f"players.csv manifest retrieved_at {retrieved_at!r} has no timezone -- refusing to "
            "assume UTC for a cutoff-safety check this important."
        )
    retrieved_utc_date = retrieved.tz_convert("UTC").normalize()
    if retrieved_utc_date >= earliest_kickoff_utc_date:
        raise LiveSpineProvenanceError(
            f"players.csv snapshot retrieved_at={retrieved_at} (UTC date "
            f"{retrieved_utc_date.date()}) is not strictly before the earliest real Week 1 "
            f"kickoff date {earliest_kickoff_utc_date.date()} -- refusing to build a spine that "
            "could reflect in-season information."
        )


def load_live_2026_spine_inputs(prediction_season: int):
    """Verifies and loads the already-governed players/schedules source
    artifacts through nflverse_source's existing fetch/manifest
    machinery -- never a new fetch mechanism -- then verifies the
    players snapshot's provenance timestamp against
    `prediction_season`'s earliest real Week 1 kickoff BEFORE returning
    anything. Raises LiveSpineProvenanceError, never a bare/generic
    exception, on any missing manifest entry, checksum failure, or
    cutoff violation -- always before any roster spine row is built.

    Returns (players_df, schedule_df, retrieved_at, earliest_kickoff_utc_date).
    """
    manifest = nflverse_source._load_manifest()
    if manifest.get("players") is None:
        raise LiveSpineProvenanceError(
            "players.csv has no entry in the nflverse source manifest -- cannot build a live "
            "spine without governed provenance. Register it deliberately (GitHub Actions only; "
            "see nflverse_source.register_players_manifest_entry()) before retrying."
        )
    if manifest.get("schedules") is None:
        raise LiveSpineProvenanceError(
            "schedules (games.csv) has no entry in the nflverse source manifest -- cannot "
            "verify the Week 1 cutoff without it."
        )

    # Explicit local-cache guard, checked BEFORE calling either fetch_*_raw()
    # helper. Those helpers only skip their own network-download branch when
    # the local cache file already exists -- correct for their own contract,
    # but relying on that silently would make "no live network here" an
    # accident of this sandbox's network policy rather than a real guarantee
    # of this code. This check makes "never attempt a download in a local
    # run" true by construction: if either cache file is missing, this raises
    # our own named, specific error before fetch_players_raw()/
    # fetch_schedules_raw() are ever called, so neither can reach its
    # download fallback.
    if not nflverse_source.PLAYERS_CACHE_PATH.exists():
        raise LiveSpineProvenanceError(
            f"players.csv is not present locally at {nflverse_source.PLAYERS_CACHE_PATH} -- refusing to "
            "let fetch_players_raw() attempt a network download from a local run. Restore the "
            "governed local cache file (it should already be committed/present in this "
            "environment) before retrying; a live-2026-spine build must never trigger a real "
            "fetch outside GitHub Actions."
        )
    if not nflverse_source.SCHEDULES_CACHE_PATH.exists():
        raise LiveSpineProvenanceError(
            f"schedules (games.csv) is not present locally at {nflverse_source.SCHEDULES_CACHE_PATH} -- "
            "refusing to let fetch_schedules_raw() attempt a network download from a local run. "
            "Restore the governed local cache file before retrying; a live-2026-spine build must "
            "never trigger a real fetch outside GitHub Actions."
        )

    try:
        players_path = nflverse_source.fetch_players_raw()
    except RuntimeError as exc:
        raise LiveSpineProvenanceError(f"players.csv provenance verification failed: {exc}") from exc
    try:
        schedules_path = nflverse_source.fetch_schedules_raw()
    except RuntimeError as exc:
        raise LiveSpineProvenanceError(f"schedules provenance verification failed: {exc}") from exc

    schedule_df = pd.read_csv(schedules_path, low_memory=False)
    earliest_kickoff = _earliest_week1_kickoff_utc_date(schedule_df, prediction_season)
    retrieved_at = manifest["players"]["retrieved_at"]
    _verify_snapshot_before_cutoff(retrieved_at, earliest_kickoff)

    players_df = pd.read_csv(players_path, low_memory=False)
    return players_df, schedule_df, retrieved_at, earliest_kickoff


def build_governed_live_2026_spine(
    players_df: pd.DataFrame, prediction_season: int, retrieved_at: str, earliest_kickoff_utc_date: pd.Timestamp,
) -> RosterSpineResult:
    """Thin adapter from real players.csv's own columns to the already-
    committed, already-tested core (lib.dataset2.future_season_spine).
    No eligibility/cutoff logic lives here -- this function only shapes
    the real input to that core's contract."""
    snapshot = players_df[list(ROSTER_SNAPSHOT_REQUIRED_COLUMNS)]
    retrieved_ts = pd.Timestamp(retrieved_at)
    return build_future_season_roster_spine(snapshot, prediction_season, retrieved_ts, earliest_kickoff_utc_date)


def write_live_spine_outputs(spine_result: RosterSpineResult) -> None:
    """Writes the included spine, the excluded-row ledger, and the
    future-only roster-status sidecar as three SEPARATE files -- never
    merged into predictor_table/CSV_PATH/PARQUET_PATH, and never passed
    back into build_canonical_predictor_table(). This is the only place
    in this script that touches roster_status_provenance_frame()."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    spine_result.included.to_csv(LIVE_SPINE_INCLUDED_PATH, index=False)
    spine_result.excluded.to_csv(LIVE_SPINE_EXCLUDED_PATH, index=False)
    sidecar = roster_status_provenance_frame(spine_result.included)
    sidecar.to_csv(LIVE_SPINE_SIDECAR_PATH, index=False)

    paths = [LIVE_SPINE_INCLUDED_PATH, LIVE_SPINE_EXCLUDED_PATH, LIVE_SPINE_SIDECAR_PATH]
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in paths]
    LIVE_SPINE_HASH_MANIFEST_PATH.write_text("\n".join(lines) + "\n")


def resolve_live_2026_spine(live_2026_requested: bool, master_population: pd.DataFrame) -> RosterSpineResult | None:
    """THE testable seam between main()'s CLI parsing and the live-spine
    machinery: returns None immediately, touching nothing else, unless
    `live_2026_requested` is True -- this is what proves the no-flag
    default path never loads load_live_2026_spine_inputs/
    build_governed_live_2026_spine at all, not just that it happens to
    produce the same output."""
    if not live_2026_requested:
        return None
    print("\n--live-2026-spine requested: verifying governed provenance before any future row is built...")
    prediction_season = int(master_population["season"].max()) + 1
    live_players_df, live_schedule_df, retrieved_at, earliest_kickoff = load_live_2026_spine_inputs(prediction_season)
    print(f"  players.csv retrieved_at={retrieved_at}, earliest real Week 1 kickoff (UTC date)={earliest_kickoff.date()}")
    spine_result = build_governed_live_2026_spine(live_players_df, prediction_season, retrieved_at, earliest_kickoff)
    print(f"  governed roster spine: {len(spine_result.included)} included, {len(spine_result.excluded)} excluded")
    return spine_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-2026-spine", action="store_true",
        help="Opt-in: extend the canonical table with a governed live 2026 future-season roster "
        "spine (players.csv + schedules.csv provenance verified before any row is built). Off "
        "by default -- omitting this flag reproduces the exact same historical-only output as "
        "before this flag existed, and never loads any roster-snapshot machinery at all.",
    )
    args = parser.parse_args()
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

    live_spine_result = resolve_live_2026_spine(args.live_2026_spine, master_population)
    future_season_roster_spine = live_spine_result.included if live_spine_result is not None else None

    print("\nBuilding canonical predictor table...")
    predictor_table, column_registry, deferred_families = build_canonical_predictor_table(
        master_population, players_df, weekly_all, weekly_reg_only, snap_counts_all, depth_chart_pre2025, schedule_df,
        future_season_roster_spine=future_season_roster_spine,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    predictor_table.to_parquet(PARQUET_PATH, index=False, engine="fastparquet")
    predictor_table.to_csv(CSV_PATH, index=False)
    column_registry.to_csv(DICTIONARY_PATH, index=False)

    if live_spine_result is not None:
        write_live_spine_outputs(live_spine_result)
        print(
            f"  wrote {LIVE_SPINE_INCLUDED_PATH}, {LIVE_SPINE_EXCLUDED_PATH}, "
            f"{LIVE_SPINE_SIDECAR_PATH} (never merged into the canonical table above)"
        )

    # --- Determinism check: rebuild once, compare byte-for-byte CSV output ---
    predictor_table_2, column_registry_2, _ = build_canonical_predictor_table(
        master_population, players_df, weekly_all, weekly_reg_only, snap_counts_all, depth_chart_pre2025, schedule_df,
        future_season_roster_spine=future_season_roster_spine,
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
