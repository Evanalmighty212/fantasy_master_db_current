"""
FantasyPros Historical ADP Automation Test

Purpose:
- Verify historical PPR ADP pages exist.
- Check whether they can be read automatically.
- Count rows returned.
- Determine whether FantasyPros is a viable long-term ADP source.
"""

import pandas as pd

YEARS = list(range(2006, 2026))

results = []

for year in YEARS:
    url = f"https://www.fantasypros.com/nfl/adp/ppr-overall.php?year={year}"
    print(f"Testing {year}...")

    try:
        tables = pd.read_html(url)

        if not tables:
            raise Exception("No tables found")

        df = tables[0]

        results.append({
            "season": year,
            "rows": len(df),
            "status": "PASS"
        })

        print(f"  PASS - {len(df)} rows")

    except Exception as e:
        results.append({
            "season": year,
            "rows": 0,
            "status": f"FAIL ({e})"
        })

        print(f"  FAIL - {e}")

print("\n==============================")
print("SUMMARY")
print("==============================")

summary = pd.DataFrame(results)
print(summary)

passes = (summary["status"] == "PASS").sum()

print(f"\nSuccessful seasons: {passes}/{len(summary)}")
print(f"Average rows: {summary['rows'].mean():.1f}")
