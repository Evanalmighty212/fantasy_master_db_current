"""
02_clean_adp.py  [NOT YET IMPLEMENTED]

Purpose:
- Take the raw ADP pulls in data/raw/adp/ (and eventually data/raw/fantasypros/)
  and normalize them into one clean, deduplicated ADP table per season.
- Standardize player names (this is where rapidfuzz matching against the
  nflverse player table will likely live, or feed into 04).
- Flag seasons with missing/incomplete coverage per docs/ADP_SOURCE_MATRIX.md.

Input:  data/raw/adp/*.csv, data/raw/fantasypros/* (once that source is built)
Output: data/processed/adp_clean_<start>_<end>.csv

Depends on: 01_download_adp.py having run (and, later, a FantasyPros
downloader once docs/ADP_SOURCE_MATRIX.md's open question is resolved).
"""

def main():
    raise NotImplementedError(
        "02_clean_adp.py has not been built yet. "
        "See docs/ADP_SOURCE_MATRIX.md for the current state of ADP sourcing."
    )


if __name__ == "__main__":
    main()
