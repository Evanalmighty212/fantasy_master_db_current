"""
fetch_drafts.py  (ISOLATED DIAGNOSTIC)

For every league classified as clean_1qb, fetches its real draft
results (MFL's TYPE=draftResults API -- confirmed to return real,
per-pick Unix timestamps, not just pick order) and filters individual
PICKS (not whole leagues) to the August 15 - 2025 kickoff window.

Why per-pick, not per-league: a league's classification (clean_1qb,
franchise count, etc.) is a league-level property, but WHEN a specific
draft happened is a per-draft property -- a league could in principle
have redrafted more than once, or MFL's report-level PERIOD=AUG15
filter (already applied at discovery) could itself be a minimum-date
filter, not an exact window (verified directly: PERIOD=AUG15 is "on or
after Aug 15", not "Aug 15 through kickoff"). So this script re-applies
the exact window using the real per-pick timestamp, not trusting the
report-level filter's label at face value.

2025 kickoff cutoff: 2025-09-04 00:00 UTC (real-world Thursday night
opener) -- an explicit, disclosed assumption, not derived from a
verified schedule source in this pass.

PICK PROVENANCE -- corrected taxonomy (see prior draft's over-strong
"organic/non-organic" framing, revised on review): a commissioner may
enter a genuine offline draft; an imported draft may represent real
human selections made on another platform. Neither is automatically
fake. This module now assigns one of SIX neutral, descriptive
categories per pick, and leaves the judgment of which to trust for
which purpose to reconstruct_adp.py's named sensitivity variants, not
to a single blanket filter here:
  - native_live_selection: MFL's own live draft clock, no annotation
    at all -- the strongest single signal of a real-time human pick,
    but not proof every unannotated pick is human (a fast auto-pick
    on a live clock leaves no comment either).
  - automated_default_rank: MFL's own system explicitly says it
    picked this (its "ADP Rank" / "Pre-Draft List" / "Work List" /
    "Draft List" default, or a third-party list like FantasySharks) --
    a real signal that no human chose this pick, regardless of
    platform.
  - commissioner_entered: a commissioner typed this pick in --
    genuinely ambiguous as noted above, not excluded by default.
  - externally_imported: recorded as sourced from outside MFL --
    also genuinely ambiguous, not excluded by default.
  - keeper: explicitly tagged as a kept player, not a fresh
    market-priced selection this season -- excluded from every
    variant, since a keeper price reflects a prior season's dynamics,
    not 2025's market.
  - unknown: any other non-empty annotation not matching the above.

Output: research/diagnostics/mfl_pipeline/output/draft_picks_in_window.csv
        (every in-window pick, provenance-tagged, NOT pre-filtered to
        one "winning" category -- that choice belongs to reconstruct_adp.py)
        research/diagnostics/mfl_pipeline/output/all_players.csv
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mfl_client import get_json, cache_stats

CLASSIFICATION_PATH = Path(__file__).resolve().parent / "output" / "league_classification.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

DRAFT_RESULTS_URL_TEMPLATE = "https://api.myfantasyleague.com/2025/export?TYPE=draftResults&L={league_id}&JSON=1"
ALL_PLAYERS_URL = "https://api.myfantasyleague.com/2025/export?TYPE=players&JSON=1"

WINDOW_START = datetime(2025, 8, 15, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2025, 9, 4, 0, 0, 0, tzinfo=timezone.utc)  # 2025 kickoff -- see module docstring

PROVENANCE_CATEGORIES = [
    "native_live_selection", "automated_default_rank", "commissioner_entered",
    "externally_imported", "keeper", "unknown",
]


def fetch_all_players() -> pd.DataFrame:
    data = get_json(ALL_PLAYERS_URL)
    players = data.get("players", {}).get("player", [])
    return pd.DataFrame(players)


def classify_pick_provenance(comment) -> str:
    c = str(comment or "").strip()
    if c == "":
        return "native_live_selection"
    if "Keeper" in c:
        return "keeper"
    if ("ADP Rank" in c or "Pre-Draft List" in c or "Work List" in c
            or "Draft List" in c or "FantasySharks" in c):
        return "automated_default_rank"
    if "imported" in c.lower():
        return "externally_imported"
    if "commissioner" in c.lower():
        return "commissioner_entered"
    return "unknown"


def fetch_league_draft(league_id: str) -> list:
    data = get_json(DRAFT_RESULTS_URL_TEMPLATE.format(league_id=league_id))
    if "_error" in data:
        return []
    picks = data.get("draftResults", {}).get("draftUnit", {}).get("draftPick", [])
    if isinstance(picks, dict):
        picks = [picks]
    franchise_count_raw = data.get("draftResults", {}).get("draftUnit", {}).get("round1DraftOrder", "")
    franchise_count = len([x for x in franchise_count_raw.split(",") if x.strip()])
    for p in picks:
        p["league_id"] = league_id
        p["franchise_count_in_draft"] = franchise_count
    return picks


def main():
    classification = pd.read_csv(CLASSIFICATION_PATH, dtype={"league_id": str})
    clean_leagues = classification[classification["is_clean_1qb"] == True]  # noqa: E712
    print(f"{len(clean_leagues)} clean_1qb leagues to fetch draft results for "
          f"(of {len(classification)} classified).")

    all_picks = []
    for i, row in enumerate(clean_leagues.itertuples()):
        picks = fetch_league_draft(row.league_id)
        all_picks.extend(picks)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(clean_leagues)} league drafts fetched...")

    if not all_picks:
        print("No draft picks retrieved -- nothing to write.")
        return

    picks_df = pd.DataFrame(all_picks)
    n_before = len(picks_df)
    for col in ("timestamp", "round", "pick"):
        picks_df[col] = pd.to_numeric(picks_df[col], errors="coerce")
    picks_df = picks_df.dropna(subset=["timestamp", "round", "pick"]).copy()
    n_dropped = n_before - len(picks_df)
    if n_dropped:
        print(f"  {n_dropped} of {n_before} picks had a missing/unusable timestamp, "
              f"round, or pick field -- excluded (can't be date-placed or overall-ranked).")

    picks_df["timestamp_dt"] = pd.to_datetime(picks_df["timestamp"], unit="s", utc=True)
    picks_df["round"] = picks_df["round"].astype(int)
    picks_df["pick_in_round"] = picks_df["pick"].astype(int)
    picks_df["overall_pick"] = (
        (picks_df["round"] - 1) * picks_df["franchise_count_in_draft"] + picks_df["pick_in_round"]
    )

    in_window = picks_df[(picks_df["timestamp_dt"] >= WINDOW_START) & (picks_df["timestamp_dt"] < WINDOW_END)].copy()
    print(f"\nTotal picks fetched: {len(picks_df)}")
    print(f"Picks within Aug15-kickoff window: {len(in_window)} "
          f"({len(in_window) / len(picks_df) * 100:.1f}%)")

    in_window["provenance"] = in_window["comments"].apply(classify_pick_provenance)
    print(f"\nPick provenance breakdown (in-window picks, n={len(in_window)}):")
    print(in_window["provenance"].value_counts().reindex(PROVENANCE_CATEGORIES, fill_value=0).to_string())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    in_window.to_csv(OUTPUT_DIR / "draft_picks_in_window.csv", index=False)
    print(f"\nWrote {OUTPUT_DIR / 'draft_picks_in_window.csv'} ({len(in_window)} rows, "
          f"in-window, ALL provenance categories tagged -- not pre-filtered)")

    players_df = fetch_all_players()
    players_df.to_csv(OUTPUT_DIR / "all_players.csv", index=False)
    print(f"Wrote {OUTPUT_DIR / 'all_players.csv'} ({len(players_df)} players)")

    print(f"\nCache stats: {cache_stats()}")


if __name__ == "__main__":
    main()
