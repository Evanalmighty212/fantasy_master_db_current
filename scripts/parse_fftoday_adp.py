"""
parse_fftoday_adp.py

Parses FFToday's raw ADP HTML pages into clean CSVs. The data is NOT
JavaScript-rendered as originally suspected -- it's a real <table>
buried in old-style nested-table markup, which is why a simple
markdown-converting fetch missed it (the converter doesn't handle the
nested-table-in-a-cell layout) but a real HTML parser finds it fine.

Structure discovered (2007-2009 confirmed, likely holds for the whole
pre-2010 archive using the same `NN_adp.htm` URL pattern):
  - The real player table is identifiable as the <table> whose header
    row's text contains both "Name" and "Pos".
  - That table's row 0 is a wrapper cell containing a NESTED table with
    all the real rows -- calling find_all('tr') on the outer table
    recursively picks up the nested rows too, which is what we want.
  - Real player rows have either 5 columns (Pick, Name, Pos, Team,
    Overall -- seen in 2007) or 7 columns (+ High, Low -- seen in
    2008/2009) and start with a "round.pick" pattern like "1.01".
  - A separate table containing "Data Based On" has the collection
    metadata (league size, rounds, draft count, date range) -- ALWAYS
    check the date range before trusting a year's data. Two of FFC's
    own pre-2010 archives (fetched separately) turned out to span
    659-1026 days instead of a real single-season snapshot; FFToday's
    2007-2009 pages were verified clean (1-3 day windows) but this
    should be re-checked for any additional years pulled later.

Usage:
    python parse_fftoday_adp.py <input.html> <year> <output_dir>
"""

import csv
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}
PICK_PATTERN = re.compile(r"^\d+\.\d+$")


def find_data_table(soup):
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if len(rows) > 50:
            header_text = rows[0].get_text(separator="|", strip=True) if rows else ""
            if "Name" in header_text and "Pos" in header_text:
                return t
    return None


def find_metadata_text(soup):
    for t in soup.find_all("table"):
        txt = t.get_text(separator=" ", strip=True)
        if "Data Based On" in txt:
            return txt
    return ""


def extract_player_rows(data_table):
    """Returns (rows, has_high_low). Each row is a list of cell strings."""
    rows = data_table.find_all("tr")
    player_rows = []
    has_high_low = None
    for r in rows:
        tds = r.find_all("td")
        if len(tds) in (5, 7) and PICK_PATTERN.match(tds[0].get_text(strip=True)):
            vals = [" ".join(td.get_text(strip=True).split()) for td in tds]
            player_rows.append(vals)
            has_high_low = len(tds) == 7
    return player_rows, has_high_low


def parse_file(html_path: str, year: str, out_dir: str):
    with open(html_path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    data_table = find_data_table(soup)
    if data_table is None:
        raise ValueError(f"No ADP data table found in {html_path} -- "
                          f"page structure may differ from the 2007-2009 "
                          f"pattern this parser was built against.")

    meta_text = find_metadata_text(soup)
    player_rows, has_high_low = extract_player_rows(data_table)

    if not player_rows:
        raise ValueError(f"Data table found but zero player rows extracted "
                          f"from {html_path} -- check PICK_PATTERN / column "
                          f"count assumptions against this page's actual "
                          f"structure before trusting this as 'no data'.")

    cols = ["pick", "name", "position", "team", "overall_adp"]
    if has_high_low:
        cols += ["high", "low"]

    out_path = Path(out_dir) / f"fftoday_adp_{year}_standard.csv"
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(player_rows)

    skill_count = sum(1 for r in player_rows if r[2] in SKILL_POSITIONS)

    print(f"{year}: {len(player_rows)} total rows, {skill_count} skill "
          f"(QB/RB/WR/TE) rows -> {out_path}")
    print(f"  metadata: {meta_text[:200]}")

    return out_path, len(player_rows), skill_count


def main():
    if len(sys.argv) != 4:
        print("Usage: python parse_fftoday_adp.py <input.html> <year> <output_dir>")
        sys.exit(1)
    parse_file(sys.argv[1], sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
