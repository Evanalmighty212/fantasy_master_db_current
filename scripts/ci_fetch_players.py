"""
scripts/ci_fetch_players.py

CI-only driver for scripts/nflverse_source.py's real players (players.csv)
fetch/pin -- mirrors scripts/ci_fetch_schedules.py's pattern exactly. The
fetch/pin/integrity-check machinery already exists in nflverse_source.py
(register_players_manifest_entry(), fetch_players_raw(), fetch_players())
-- this script only PINS the current asset (this environment has never
had real outbound internet to nflverse's GitHub releases) and writes a
small, machine-readable summary for the workflow's own review step, per
this project's established "review deliberately, never auto-commit" CI
convention (see fetch_adp.yml, fetch_mfl_historical.yml, ci_fetch_schedules.py).

REVIEW ARTIFACT ONLY. Running this script (only possible inside GitHub
Actions, a real outbound-internet environment -- see
.github/workflows/fetch_players.yml) produces a CANDIDATE
data/raw/nflverse/reference/players.csv, a CANDIDATE
scripts/nflverse_source_manifest.json, and this summary file. It does
NOT commit, push, or otherwise change this repository's committed
state in any way -- those three files are uploaded as a downloadable
workflow artifact for deliberate local review. Nothing in the repo's
history changes until a human downloads that artifact, inspects it
(sha256/row-count/retrieval-date/status-code checks, per the
operational readiness runbook), and separately, deliberately commits
the refreshed manifest.

SCOPE, DELIBERATELY NARROW: this script touches ONLY
register_players_manifest_entry() and fetch_players() -- the players
registration/fetch path -- and nothing else in nflverse_source.py
(not register_manifest_entry/fetch_season_raw for stats_player, not
register_schedules_manifest_entry/fetch_schedules, not
register_depth_chart_manifest_entry/fetch_depth_chart, not
register_snap_counts_manifest_entry/fetch_snap_counts, not
register_pbp_participation_manifest_entry/fetch_pbp_participation).
register_players_manifest_entry() itself only ever writes the
top-level "players" key in the manifest (see its own docstring) -- so
a run of this script can only ever change that one manifest key, never
any other season/schedules/depth_charts/snap_counts/pbp_participation
entry, and never any pipeline artifact outside the nflverse raw-cache
directory. It imports nothing from 02_clean_adp.py, 03_download_stats.py,
04_build_master_dataset.py, 05_calculate_metrics.py,
06_generate_rankings.py, or lib/dataset2/canonical_predictor_table.py --
those pipeline stages are entirely unreachable from this script.
"""

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

import nflverse_source

SUMMARY_PATH = Path("data/raw/nflverse/reference/players_fetch_summary.json")


def main():
    print("Registering the 'players' manifest entry (pins the real asset id + sha256)...")
    entry = nflverse_source.register_players_manifest_entry()
    print(f"  asset_id={entry['asset_id']}")
    print(f"  upstream_updated_at={entry['upstream_updated_at']}")
    print(f"  retrieved_at={entry['retrieved_at']}")
    print(f"  sha256={entry['sha256']}")
    print(f"  row_count={entry['row_count']}")
    print(f"  schema_version={entry['schema_version']}")

    print("\nFetching (verifying against the just-pinned hash)...")
    players = nflverse_source.fetch_players()
    print(f"Loaded {len(players)} rows, columns: {list(players.columns)}")

    summary = {
        "asset_id": entry["asset_id"],
        "upstream_updated_at": entry["upstream_updated_at"],
        "retrieved_at": entry["retrieved_at"],
        "sha256": entry["sha256"],
        "row_count": entry["row_count"],
        "schema_version": entry["schema_version"],
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"\nWrote {SUMMARY_PATH}")
    print(
        "\nThis is a CANDIDATE snapshot only -- it changes nothing in the committed repository. "
        "Review the uploaded artifact (players.csv + nflverse_source_manifest.json + this summary) "
        "and commit the refreshed manifest separately and deliberately, only after verification."
    )


if __name__ == "__main__":
    main()
