"""
02_clean_adp.py

Purpose:
- Take the raw ADP pulls in data/raw/adp/ (FFC JSON + FFToday CSV) and
  normalize them into one clean, canonical-schema ADP table per season.
- Source selection is driven by docs/ADP_SEASON_SOURCE_PLAN.csv, NOT by
  "whatever raw files happen to exist" -- that plan already encodes the
  hard-won verification work (which years FFC is broken/contaminated
  for, which years FFToday is the verified-clean choice, etc.). This
  script trusts that plan rather than re-deciding source quality from
  scratch.
- Standardize player names into a normalized matching key (full
  fuzzy/ID matching against nflverse happens later, in 04 -- this just
  strips the obvious noise: parenthetical team tags, extra whitespace,
  case).
- Never silently drops a season -- every season in the source plan gets
  a row in the coverage report, even if it ends up unprocessed.

Canonical schema (per the addendum's Priority 3 spec):
  season, source, scoring_format, league_size,
  player_name_original, player_name_normalized,
  position, team, overall_adp, adp_rank, times_drafted,
  source_quality_flag

Input:  docs/ADP_SEASON_SOURCE_PLAN.csv
        data/raw/adp/ffc_adp_<year>_<scoring>.json
        data/raw/adp/fftoday_adp_<year>_standard.csv
Output: data/processed/adp_clean_<start>_<end>.csv
        data/processed/adp_clean_coverage_report.csv
"""

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import SEASONS

RAW_DIR = Path("data/raw/adp")
OUT_DIR = Path("data/processed")
PLAN_PATH = Path("docs/ADP_SEASON_SOURCE_PLAN.csv")

OUT_DIR.mkdir(parents=True, exist_ok=True)

CANONICAL_COLUMNS = [
    "season", "source", "scoring_format", "league_size",
    "player_name_original", "player_name_normalized",
    "position", "team", "overall_adp", "adp_rank",
    "times_drafted", "source_quality_flag",
    "draft_selection_count", "draft_selection_denominator",
    "draft_selection_rate", "mfl_reconstruction_identity",
]

# Contamination check: a real single-season preseason snapshot is a
# handful of days, not months. Anything wider gets excluded even if a
# raw file exists for it -- this mirrors the manual finding for FFC's
# 2007/2008 standard archives (659-1026 day windows), applied
# programmatically so it can't silently regress if those files are
# ever re-fetched.
MAX_CLEAN_SNAPSHOT_DAYS = 30

PAREN_TAG_RE = re.compile(r"\s*\([^)]*\)\s*$")  # trailing "(NYG)" etc.
WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(raw_name: str) -> str:
    name = raw_name.strip()
    name = PAREN_TAG_RE.sub("", name)          # "Steve Smith(NYG)" -> "Steve Smith"
    name = WHITESPACE_RE.sub(" ", name)         # collapse any internal whitespace/newlines
    name = name.replace(".", "")                # "T.J. Houshmandzadeh" -> "TJ Houshmandzadeh"
    return name.strip().lower()


def load_ffc_source(year: int, scoring: str):
    """Returns (rows, quality_flag, notes) or (None, flag, notes) if unusable."""
    fname = RAW_DIR / f"ffc_adp_{year}_{scoring}.json"
    if not fname.exists():
        return None, "missing_raw_file", f"{fname} not found -- run the fetch step first"

    with open(fname, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("status") == "Error":
        return None, "verified_empty", data.get("errors", "no data")

    meta = data.get("meta", {})
    players = data.get("players", [])
    if not players:
        return None, "verified_wrong_format", "status=Success but zero players -- known FFC anomaly"

    try:
        span_days = (date.fromisoformat(meta["end_date"]) - date.fromisoformat(meta["start_date"])).days
    except (KeyError, ValueError):
        span_days = None

    if span_days is not None and span_days > MAX_CLEAN_SNAPSHOT_DAYS:
        return None, "contaminated_multi_season", (
            f"snapshot spans {span_days} days ({meta.get('start_date')} to "
            f"{meta.get('end_date')}) -- not a real single-season snapshot, excluded"
        )

    league_size = meta.get("teams")
    rows = []
    for p in players:
        rows.append({
            "season": year,
            "source": "fantasyfootballcalculator",
            "scoring_format": meta.get("type", scoring),
            "league_size": league_size,
            "player_name_original": p.get("name"),
            "player_name_normalized": normalize_name(p.get("name", "")),
            "position": p.get("position"),
            "team": p.get("team"),
            "overall_adp": p.get("adp"),
            "adp_rank": None,  # computed after load, per season+scoring
            "times_drafted": p.get("times_drafted"),
            "source_quality_flag": "verified_clean",
        })
    return rows, "verified_clean", f"{len(rows)} players, {span_days}-day snapshot"


def load_fftoday_source(year: int, scoring: str = "standard"):
    fname = RAW_DIR / f"fftoday_adp_{year}_{scoring}.csv"
    if not fname.exists():
        return None, "missing_raw_file", f"{fname} not found"

    df = pd.read_csv(fname)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "season": year,
            "source": "fftoday",
            "scoring_format": scoring,
            # All FFToday snapshots verified so far were 12-team leagues
            # (confirmed in the "Data Based On" metadata during manual
            # extraction) -- hardcoded here since the clean CSV output
            # doesn't carry that metadata through. Re-check this
            # assumption if FFToday years beyond 2007-2009 are added.
            "league_size": 12,
            "player_name_original": r["name"],
            "player_name_normalized": normalize_name(str(r["name"])),
            "position": r["position"],
            "team": r["team"],
            "overall_adp": r["overall_adp"],
            "adp_rank": None,
            "times_drafted": None,  # not available at player granularity from FFToday
            "source_quality_flag": "verified_clean_cached_by_fftoday",
        })
    return rows, "verified_clean_cached_by_fftoday", f"{len(rows)} players"


def parse_source_token(token: str):
    """
    Maps a primary_source/secondary_source token from the season plan
    (e.g. 'fftoday_standard_VERIFIED', 'ffc_api_ppr_VERIFIED') to a
    (loader_name, scoring) pair. Returns (None, None) for anything not
    yet wired up to an actual loader (Kaggle, FantasyPros, etc. --
    those are still manual/future work per the source matrix).
    """
    if token.startswith("fftoday_standard"):
        return "fftoday", "standard"
    if token.startswith("ffc_api_ppr"):
        return "ffc", "ppr"
    if token.startswith("ffc_standard"):
        return "ffc", "standard"
    return None, None


def main():
    if not PLAN_PATH.exists():
        raise FileNotFoundError(
            f"{PLAN_PATH} not found -- 02_clean_adp.py requires the "
            f"verified season source plan to know which source to trust "
            f"per season. Run the Phase 1/2 acquisition work first."
        )

    plan = list(csv.DictReader(open(PLAN_PATH)))

    all_rows = []
    coverage_rows = []

    for row in plan:
        season = int(row["season"])
        loader_name, scoring = parse_source_token(row["primary_source"])

        if loader_name is None:
            coverage_rows.append({
                "season": season,
                "attempted_source": row["primary_source"],
                "result": "no_loader_available",
                "rows_added": 0,
                "notes": "This source isn't wired up to an automated loader yet "
                         "(e.g. Kaggle, FantasyPros -- both need manual/JS-capable "
                         "fetching per the source matrix). Season excluded from "
                         "clean output, not silently guessed at.",
            })
            continue

        if loader_name == "ffc":
            rows, flag, notes = load_ffc_source(season, scoring)
        else:
            rows, flag, notes = load_fftoday_source(season, scoring)

        if rows is None:
            coverage_rows.append({
                "season": season,
                "attempted_source": row["primary_source"],
                "result": flag,
                "rows_added": 0,
                "notes": notes,
            })
            continue

        all_rows.extend(rows)
        coverage_rows.append({
            "season": season,
            "attempted_source": row["primary_source"],
            "result": flag,
            "rows_added": len(rows),
            "notes": notes,
        })

    if not all_rows:
        print("WARNING: no ADP rows produced at all. Check that raw files "
              "exist under data/raw/adp/ and re-run the fetch scripts if not.")

    df = pd.DataFrame(all_rows, columns=CANONICAL_COLUMNS)

    # adp_rank computed per season+scoring_format, not globally -- and
    # computed AFTER all rows are loaded so it reflects the real
    # position within that season's draft, not the order rows happened
    # to be appended in.
    df["adp_rank"] = (
        df.groupby(["season", "scoring_format"])["overall_adp"]
        .rank(method="first", ascending=True)
        .astype("Int64")
    )

    df = df.sort_values(["season", "adp_rank"])

    out_path = OUT_DIR / f"adp_clean_{SEASONS[0]}_{SEASONS[-1]}.csv"
    df.to_csv(out_path, index=False)

    coverage_path = OUT_DIR / "adp_clean_coverage_report.csv"
    pd.DataFrame(coverage_rows).to_csv(coverage_path, index=False)

    print(f"Wrote {len(df)} clean ADP rows -> {out_path}")
    print(f"Wrote coverage report -> {coverage_path}")
    print(f"\nSeasons with usable data: "
          f"{sorted(df['season'].unique().tolist())}")
    seasons_excluded = [r["season"] for r in coverage_rows if r["rows_added"] == 0]
    print(f"Seasons excluded (see coverage report for why): {seasons_excluded}")

    return df


if __name__ == "__main__":
    main()
