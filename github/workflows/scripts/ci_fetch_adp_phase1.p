"""
ci_fetch_adp_phase1.py

Designed to run on GitHub Actions runners (real, unrestricted outbound
internet -- not a robots.txt-respecting sandbox), NOT locally. See
.github/workflows/fetch_adp.yml.

Fetches Fantasy Football Calculator's ADP API for every season in
Phase 1 of the acquisition plan, saves raw responses unchanged, and
writes an audit summary per the addendum's verification standard
(no season is marked "complete" without inspecting actual row counts
and metadata).

Rate limiting: FFC's docs ask that you not call the API too frequently,
since the underlying data only updates once per day -- this is aimed at
repeatedly polling the same live endpoint, not one-time historical
pulls of distinct years. This script still throttles between requests
as basic courtesy and is meant to be run manually (workflow_dispatch),
not on a schedule.

Output:
  data/raw/adp/ffc_adp_<year>_<scoring>.json   (raw, unmodified)
  data/raw/adp/ffc_fetch_summary.csv
"""

import json
import time
from pathlib import Path

import requests

RAW_DIR = Path("data/raw/adp")
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://fantasyfootballcalculator.com/api/v1/adp"
HEADERS = {"User-Agent": "Mozilla/5.0 (fantasy research project; GitHub Actions)"}

# (year, scoring) pairs -- Phase 1 from the acquisition plan
PPR_YEARS = list(range(2008, 2026))
STANDARD_YEARS = [2007, 2008]

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}


def fetch_one(year: int, scoring: str) -> dict:
    url = f"{BASE}/{scoring}?teams=12&year={year}"
    row = {
        "year": year,
        "scoring_requested": scoring,
        "url": url,
        "http_status": None,
        "teams_returned": None,
        "rounds": None,
        "total_drafts": None,
        "player_count": None,
        "usable_skill_players": None,
        "players_empty": None,
        "error": "",
    }
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        row["http_status"] = resp.status_code
        resp.raise_for_status()

        raw_path = RAW_DIR / f"ffc_adp_{year}_{scoring}.json"
        raw_path.write_bytes(resp.content)

        data = resp.json()
        meta = data.get("meta", {})
        players = data.get("players", [])

        row["teams_returned"] = meta.get("teams")
        row["rounds"] = meta.get("rounds")
        row["total_drafts"] = meta.get("total_drafts")
        row["player_count"] = len(players)
        row["players_empty"] = len(players) == 0
        row["usable_skill_players"] = sum(
            1 for p in players
            if p.get("position") in SKILL_POSITIONS and p.get("adp") is not None
        )
    except Exception as e:
        row["error"] = repr(e)

    return row


def main():
    summary_rows = []

    for year in PPR_YEARS:
        print(f"Fetching {year} ppr...")
        summary_rows.append(fetch_one(year, "ppr"))
        time.sleep(2)

    for year in STANDARD_YEARS:
        print(f"Fetching {year} standard...")
        summary_rows.append(fetch_one(year, "standard"))
        time.sleep(2)

    import csv
    summary_path = RAW_DIR / "ffc_fetch_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"\nWrote summary to {summary_path}")
    for row in summary_rows:
        status = "OK" if not row["error"] and not row["players_empty"] else "FAILED/EMPTY"
        print(f"  {row['year']} {row['scoring_requested']}: {status} "
              f"(teams_returned={row['teams_returned']}, "
              f"players={row['player_count']}, "
              f"skill_players={row['usable_skill_players']}, "
              f"error={row['error']})")


if __name__ == "__main__":
    main()
    
