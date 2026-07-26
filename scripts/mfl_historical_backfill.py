"""
scripts/mfl_historical_backfill.py

Designed to run on GitHub Actions runners (real, unrestricted outbound
internet -- not a robots.txt-respecting sandbox), NOT locally. See
.github/workflows/fetch_mfl_historical.yml. Mirrors
ci_fetch_adp_phase1.py's role for FFC -- a manual, deliberate driver
over an existing, already-tested fetch client, not new fetch logic.

Fetches MFL AUG15 ADP + player-directory snapshots for every season in
SEASONS below, using scripts/mfl_client.py's EXISTING caching, rate
limiting, and integrity-check behavior UNCHANGED:
  - Cache hit (local file present, hash matches the committed manifest)
    -> returns silently, no network call. Resumable by construction --
    re-running this script after a partial run only fetches the
    seasons that didn't already succeed.
  - Cache present but hash MISMATCHED -> mfl_client raises loudly; this
    script records it as a per-season failure and moves on, rather
    than passing force_refresh=True (which would silently accept new
    data without a human decision -- never done automatically here).
  - Cache missing -> real fetch, rate-limited per mfl_client.py's own
    throttling.

One season's failure (network error, integrity mismatch, anything)
never aborts the run -- every other season is still attempted, and the
summary names exactly which seasons succeeded/failed and why.

Does NOT rebuild the master DB, run player_matching.py, or touch
scripts/2025_adp_integration.py/04_build_master_dataset.py -- fetching
and integrating are deliberately separate steps.

Output:
  data/raw/mfl/adp_<season>_period_aug15.json   (via mfl_client.py, unchanged)
  data/raw/mfl/players_<season>.json            (via mfl_client.py, unchanged)
  scripts/mfl_source_manifest.json              (via mfl_client.py, unchanged)
  data/raw/mfl/historical_backfill_summary.csv  (this script's own report)
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import mfl_client

SEASONS = list(range(2011, 2025))  # 2011-2024 inclusive
SUMMARY_PATH = REPO_ROOT / "data/raw/mfl/historical_backfill_summary.csv"


# mfl_client.py's two response shapes -- {"adp": {"player": [...]}} vs
# {"players": {"player": [...]}} -- see that module's own docstring.
_TOP_LEVEL_KEY = {"adp": "adp", "players": "players"}


def _fetch_one(season: int, fetch_fn, label: str) -> dict:
    """Runs one mfl_client fetch call, catching any exception (network
    error, integrity mismatch, anything mfl_client itself raises) so a
    single season's failure never aborts the loop."""
    try:
        data = fetch_fn(season)
        row_count = len(data.get(_TOP_LEVEL_KEY[label], {}).get("player", []))
        return {"season": season, f"{label}_status": "ok", f"{label}_error": "", f"{label}_row_count": row_count}
    except Exception as e:
        return {"season": season, f"{label}_status": "failed", f"{label}_error": str(e), f"{label}_row_count": None}


def run_backfill(seasons=SEASONS) -> pd.DataFrame:
    rows = []
    for season in seasons:
        adp_result = _fetch_one(season, mfl_client.fetch_adp, "adp")
        players_result = _fetch_one(season, mfl_client.fetch_players, "players")
        rows.append({**adp_result, **{k: v for k, v in players_result.items() if k != "season"}})
        print(f"  season {season}: adp={adp_result['adp_status']} players={players_result['players_status']}")

    summary = pd.DataFrame(rows)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SUMMARY_PATH, index=False)
    return summary


def main():
    print(f"Fetching MFL AUG15 ADP + player-directory snapshots for seasons {SEASONS[0]}-{SEASONS[-1]}...")
    summary = run_backfill()

    n_adp_ok = (summary["adp_status"] == "ok").sum()
    n_players_ok = (summary["players_status"] == "ok").sum()
    print(f"\nDone. ADP: {n_adp_ok}/{len(summary)} succeeded. Players: {n_players_ok}/{len(summary)} succeeded.")
    failed = summary[(summary["adp_status"] == "failed") | (summary["players_status"] == "failed")]
    if len(failed):
        print(f"\n{len(failed)} season(s) had at least one failure:")
        print(failed[["season", "adp_status", "adp_error", "players_status", "players_error"]].to_string(index=False))
    print(f"\nWrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
