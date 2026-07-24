"""
discover_leagues.py  (ISOLATED DIAGNOSTIC)

League discovery method, documented precisely: MFL's aggregate ADP
report page embeds a "jump to league" <select> populated with exactly
the leagues that contributed to THAT report's specific filter
combination -- verified directly (not assumed) by comparing the
dropdown across two different filter pulls and confirming they differ
(586 leagues for FC=12/PPR/redraft/non-mock/AUG15 vs. 2,595 for an
unfiltered pull) -- so this is a real, filter-derived discovery
mechanism, not a static site-wide league list.

Report filters used for discovery (matches the cleanest combination
already validated in the prior diagnostic pass):
  PERIOD=AUG15, FCOUNT=12, IS_PPR=2 (PPR), IS_KEEPER=N (redraft only),
  IS_MOCK=1 (exclude mock drafts), PAGE=ALL (get every league, not
  just the first page).

This pre-filters on team count, scoring, redraft-vs-keeper, and
mock-vs-real BEFORE any per-league API call happens -- the remaining
work (classify_leagues.py) only needs to check the dimensions this
report-level filter can't express: QB/superflex format, IDP, auction,
best-ball, rookie-only.

Output: research/diagnostics/mfl_pipeline/output/discovered_leagues.csv
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mfl_client import get_html

DISCOVERY_URL = (
    "https://www45.myfantasyleague.com/2025/reports?R=ADP&POS=*"
    "&PERIOD=AUG15&FCOUNT=12&IS_PPR=2&IS_KEEPER=N&IS_MOCK=1&PAGE=ALL"
)
OUTPUT_PATH = Path(__file__).resolve().parent / "output" / "discovered_leagues.csv"


def discover() -> pd.DataFrame:
    html = get_html(DISCOVERY_URL)
    matches = re.findall(r'L=(\d+)&amp;O=17">([^<]+)', html)
    total_drafts_match = re.search(r"A total of (\d+) drafts were included", html)
    total_drafts = int(total_drafts_match.group(1)) if total_drafts_match else None

    df = pd.DataFrame(matches, columns=["league_id", "league_name"]).drop_duplicates(subset="league_id")
    print(f"Discovered {len(df)} unique league IDs from the report's own "
          f"league-selector (report covered {total_drafts} total drafts).")
    return df


def main():
    df = discover()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
