"""
ci_investigate_fftoday.py

One-time investigation script, NOT part of the regular pipeline.

FFToday's ADP pages return a near-empty shell when fetched with a plain
markdown-converting fetcher (confirmed separately) -- this script grabs
the truly raw HTML on an unrestricted GitHub Actions runner so we can
actually see what's going on: frameset? AJAX call? something else?

Fetches a spread of years (old-style site design vs. newer) so we can
compare structure and figure out the real data source, then build a
proper fetcher once we know the pattern.

Output: data/raw/adp_investigation/fftoday_raw_<year>.html
"""

import time
from pathlib import Path

import requests

OUT_DIR = Path("data/raw/adp_investigation")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Spread across eras: old two-digit-year pattern (confirmed live for 09),
# a couple more old-style years to test the pattern, and a modern year
# (25) which the original handoff doc confirmed uses a DIFFERENT URL
# pattern (25_adp_standard.html vs 09_adp.htm) -- fetching both patterns
# to compare structure.
URLS = {
    "2006": "https://www.fftoday.com/rankings/06_adp.htm",
    "2007": "https://www.fftoday.com/rankings/07_adp.htm",
    "2008": "https://www.fftoday.com/rankings/08_adp.htm",
    "2009": "https://www.fftoday.com/rankings/09_adp.htm",
    "2015": "https://www.fftoday.com/rankings/15_adp.htm",
    "2025_alt_pattern": "https://www.fftoday.com/rankings/25_adp_standard.html",
}


def main():
    for label, url in URLS.items():
        print(f"Fetching {label}: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            print(f"  status={resp.status_code}, length={len(resp.text)} chars")
            out_path = OUT_DIR / f"fftoday_raw_{label}.html"
            out_path.write_text(resp.text, encoding="utf-8", errors="replace")

            # Quick structural hints, printed to the log for a fast read
            # even before downloading the artifact
            lower = resp.text.lower()
            print(f"  has <frameset>: {'<frameset' in lower}")
            print(f"  has <frame : {'<frame ' in lower or '<frame\\n' in lower}")
            print(f"  has <iframe: {'<iframe' in lower}")
            print(f"  has <table: {'<table' in lower}, count={lower.count('<table')}")
            print(f"  mentions XMLHttpRequest/fetch(: "
                  f"{'xmlhttprequest' in lower or 'fetch(' in lower}")
        except Exception as e:
            print(f"  FAILED: {e!r}")
        time.sleep(1)


if __name__ == "__main__":
    main()
