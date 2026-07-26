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

SEASON SELECTION (2026-07, added so a one-off season -- e.g. 2025 --
never needs a second, near-duplicate workflow): main() accepts an
optional --seasons argument, e.g. `--seasons 2025` or
`--seasons 2011-2014,2025`. Left empty (the default, including how
.github/workflows/fetch_mfl_historical.yml has always invoked this
script), it fetches exactly SEASONS below (2011-2024) -- unchanged
from the original historical backfill. parse_seasons_arg() validates
strictly: malformed tokens, reversed ranges, and seasons outside MFL's
supported range all raise ValueError naming the bad token, rather than
silently dropping or clamping anything.

Output:
  data/raw/mfl/adp_<season>_period_aug15.json   (via mfl_client.py, unchanged)
  data/raw/mfl/players_<season>.json            (via mfl_client.py, unchanged)
  scripts/mfl_source_manifest.json              (via mfl_client.py, unchanged)
  data/raw/mfl/historical_backfill_summary.csv  (this script's own report)
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import config
import mfl_client

SEASONS = list(range(2011, 2025))  # 2011-2024 inclusive -- the original, still-default backfill range
SUMMARY_PATH = REPO_ROOT / "data/raw/mfl/historical_backfill_summary.csv"

_SEASON_TOKEN = re.compile(r"^\d{4}$")
_RANGE_TOKEN = re.compile(r"^(\d{4})-(\d{4})$")


def _validate_season_supported(season: int, token: str) -> None:
    lo, hi = config.SBV_MFL_AVAILABLE_FROM_SEASON, config.SEASONS[-1]
    if season < lo or season > hi:
        raise ValueError(
            f"--seasons token {token!r} includes unsupported season {season} -- "
            f"MFL data is only supported for {lo}-{hi} (config.SBV_MFL_AVAILABLE_FROM_SEASON..config.SEASONS[-1])."
        )


def parse_seasons_arg(spec: str, default=None) -> list:
    """Parses a --seasons value into a sorted, de-duplicated list of
    season ints. Empty/blank input returns `default` (SEASONS if not
    given) unchanged -- the original 2011-2024 behavior. Otherwise
    spec is a comma-separated list of tokens, each either a single
    4-digit season ("2025") or an inclusive range ("2011-2014");
    mixing both is fine ("2011-2014,2025"). Strict validation: a
    malformed token, a reversed range (start > end), or any season
    outside MFL's supported range raises ValueError naming the exact
    bad token -- never silently dropped, clamped, or guessed at.
    Duplicate seasons across tokens (e.g. an overlapping range and a
    single season) are silently collapsed, not rejected -- the
    contract is a unique, sorted result, not strict input uniqueness."""
    if default is None:
        default = SEASONS
    if not spec or not spec.strip():
        return list(default)

    seasons = set()
    for raw_token in spec.split(","):
        token = raw_token.strip()
        if not token:
            continue  # tolerate stray/trailing commas and whitespace, not an empty spec overall

        single_match = _SEASON_TOKEN.match(token)
        range_match = _RANGE_TOKEN.match(token)

        if single_match:
            season = int(token)
            _validate_season_supported(season, token)
            seasons.add(season)
        elif range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start > end:
                raise ValueError(f"--seasons range {token!r} is reversed (start {start} > end {end}).")
            for season in range(start, end + 1):
                _validate_season_supported(season, token)
            seasons.update(range(start, end + 1))
        else:
            raise ValueError(
                f"--seasons token {token!r} is not a valid season (YYYY) or range (YYYY-YYYY)."
            )

    return sorted(seasons)


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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seasons", default="",
        help=(
            "Comma-separated seasons and/or ranges, e.g. '2025' or "
            "'2011-2014,2025'. Empty (default) fetches the standard "
            f"{SEASONS[0]}-{SEASONS[-1]} historical backfill."
        ),
    )
    args = parser.parse_args()
    seasons = parse_seasons_arg(args.seasons)

    print(f"Fetching MFL AUG15 ADP + player-directory snapshots for {len(seasons)} season(s): {seasons}...")
    summary = run_backfill(seasons=seasons)

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
