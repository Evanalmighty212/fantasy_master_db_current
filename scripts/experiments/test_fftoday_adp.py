"""
FFToday Historical ADP Automation Test

Purpose:
- Test whether FFToday ADP pages can be read automatically.
- Check PPR ADP history coverage.
- Count usable rows per season.
"""

import pandas as pd

YEARS = list(range(2011, 2026))

# First guess based on FFToday URL pattern:
# 25_adp_standard.html, 25_adp_half_ppr.html
CANDIDATE_PATTERNS = [
    "https://www.fftoday.com/rankings/{yy}_adp_ppr.html",
    "https://www.fftoday.com/rankings/{yy}_adp_ppr_scoring.html",
    "https://www.fftoday.com/rankings/{yy}_adp.html",
]

results = []

for year in YEARS:
    yy = str(year)[-2:]
    print(f"\nTesting {year}...")

    best = None

    for pattern in CANDIDATE_PATTERNS:
        url = pattern.format(yy=yy)

        try:
            tables = pd.read_html(url)
            for i, df in enumerate(tables):
                cols = [str(c).strip() for c in df.columns]
                row_count = len(df)

                if row_count >= 100:
                    best = {
                        "season": year,
                        "url": url,
                        "table_index": i,
                        "rows": row_count,
                        "columns": cols,
                        "status": "PASS",
                    }
                    break

            if best:
                break

        except Exception as e:
            last_error = str(e)

    if best:
        print(f"  PASS - {best['rows']} rows")
        print(f"  URL: {best['url']}")
        print(f"  Columns: {best['columns'][:12]}")
        results.append(best)
    else:
        print("  FAIL - no usable ADP table found")
        results.append({
            "season": year,
            "url": None,
            "table_index": None,
            "rows": 0,
            "columns": None,
            "status": "FAIL",
        })

summary = pd.DataFrame(results)

print("\n==============================")
print("SUMMARY")
print("==============================")
print(summary[["season", "rows", "status", "url"]])

print(f"\nSuccessful seasons: {(summary['status'] == 'PASS').sum()}/{len(summary)}")
print(f"Average rows: {summary['rows'].mean():.1f}")

summary.to_csv("outputs/fftoday_adp_source_test.csv", index=False)
print("\nSaved outputs/fftoday_adp_source_test.csv")