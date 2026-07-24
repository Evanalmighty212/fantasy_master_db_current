"""
replacement_level_tables.py  (Dataset 3 research foundation, Deliverable 4)

EXPLORATORY ONLY. Shows plausible position-specific replacement
production under stated 10-team and 12-team roster assumptions, at
both season and weekly grain. Does NOT select a final replacement
definition for Dataset 3 (or propose changing LWI's own, separate
replacement thresholds in config.py) -- see lib/replacement.py's
module docstring for why every assumption here is an explicit,
labeled parameter rather than a silent default.

Roster assumptions (ALL stated explicitly, see lib/replacement.py):
  - 10-team and 12-team standard leagues
  - Starters per team: 1 QB / 2 RB / 2 WR / 1 TE, +1 shared FLEX
    (RB/WR/TE eligible)
  - Two flex-allocation scenarios per team size: FLEX excluded
    entirely ("starters only"), and FLEX split evenly 1/3-1/3-1/3
    across RB/WR/TE ("even flex"). A third, RB/WR-heavy allocation is
    available in lib/replacement.py but not run here by default --
    add it to SCENARIOS below if a third comparison point is wanted.
  - Replacement rank cutoff = starters implied by the above, rounded
    to the nearest whole rank.
  - Replacement production = median value among players whose
    SEASON-END positional finish (position_finish_ppr) falls in
    [cutoff, cutoff + WINDOW]. WINDOW = 3 here (smaller than LWI's own
    window of 12, since these cutoffs are themselves much smaller,
    especially 10-team QB/TE) -- an explicit, changeable choice, not a
    finding.

Weekly grain -- TWO tables, not one, because they answer genuinely
different questions:

1. `replacement_level_weekly_active.csv` -- "ACTIVE-WEEK production":
   the real weekly point distribution posted BY replacement-tier
   players (identified by season-end rank) IN THE WEEKS THEY ACTUALLY
   PLAYED. weekly_results_ppr_*.csv only contains rows for weeks a
   player had real involvement -- a missed week is an ABSENT row, not
   a zero-row -- so this table's numbers are conditioned on activity
   and will read HIGHER than true replacement output across a full
   slate, since replacement-tier players themselves also miss games.
   Labeled "active-week", not "weekly replacement estimate", so it
   can't be misread as unconditional.

2. `replacement_level_weekly_calendar.csv` -- fills in explicit
   ZEROES for weeks a replacement-tier player's team actually played
   but that player has no recorded row for (i.e. genuinely missed,
   not a bye). Team bye weeks are INFERRED, not sourced from a real
   schedule: for each (season, team, week), if NO player on that team
   has any row at all in weekly_results_ppr, that week is treated as
   the team's bye (or a real canceled game -- see below) and excluded
   from the calendar rather than zero-filled. Verified directly
   against the real data before trusting this: 606 of 608 real
   team-seasons produce exactly one such excluded week, matching a
   real bye. The 2 exceptions (2022 BUF, 2022 CIN) both show TWO
   excluded weeks each -- not a bug: Week 17 that season was the real,
   nationally-covered Bills-Bengals game canceled after Damar Hamlin's
   on-field cardiac arrest, which is correctly excluded here too,
   since no player could have produced real points in a game that
   never resumed. For players traded mid-season, this uses their
   master-DB season-of-record `team` for the WHOLE season to determine
   excluded weeks -- a known, stated simplification (their actual
   excluded weeks may differ pre/post-trade), not silently hidden.

**Neither table necessarily models realistic waiver-wire
availability.** Both describe what SEASON-END replacement-rank
players (by finish) actually produced -- not whether that specific
player was actually on any real league's waiver wire in that specific
week, healthy, and startable. Reconstructing genuine week-by-week
roster availability isn't possible from data currently in this
pipeline -- would need real per-league roster/transaction data, which
doesn't exist here. Treat both tables as production ranges for
players who ENDED the season at replacement rank, not as a model of
in-season replacement-pickup behavior.

Input:  research/output/dataset3/broad_historical_dataset.csv
        data/raw/nflverse/weekly_results_ppr_2006_2025.csv
Output: research/output/dataset3/replacement_level_season.csv
        research/output/dataset3/replacement_level_weekly_active.csv
        research/output/dataset3/replacement_level_weekly_calendar.csv
        research/output/dataset3/replacement_level_summary_by_scenario.csv
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.replacement import (
    ROSTER_PRESETS, FLEX_ALLOCATION_NONE, FLEX_ALLOCATION_EVEN,
    replacement_rank_cutoff, replacement_level_from_rank,
)

BROAD_DATASET_PATH = Path("research/output/dataset3/broad_historical_dataset.csv")
WEEKLY_PATH = Path("data/raw/nflverse/weekly_results_ppr_2006_2025.csv")
OUTPUT_DIR = Path("research/output/dataset3")

POSITIONS = ["QB", "RB", "WR", "TE"]
WINDOW = 3
PERCENTILES = [0.10, 0.25, 0.75, 0.90]

SCENARIOS = [
    ("10_team_no_flex", "10_team_standard", FLEX_ALLOCATION_NONE),
    ("10_team_even_flex", "10_team_standard", FLEX_ALLOCATION_EVEN),
    ("12_team_no_flex", "12_team_standard", FLEX_ALLOCATION_NONE),
    ("12_team_even_flex", "12_team_standard", FLEX_ALLOCATION_EVEN),
]


def build_cutoffs(preset_name: str, flex_allocation: dict) -> dict:
    preset = ROSTER_PRESETS[preset_name]
    return {pos: replacement_rank_cutoff(preset, pos, flex_allocation) for pos in POSITIONS}


def season_level_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario_name, preset_name, flex_alloc in SCENARIOS:
        cutoffs = build_cutoffs(preset_name, flex_alloc)
        repl_points = replacement_level_from_rank(
            df, "fantasy_points_ppr", "position_finish_ppr", cutoffs, window=WINDOW
        )
        repl_ppg = replacement_level_from_rank(
            df, "ppg_ppr", "position_finish_ppr", cutoffs, window=WINDOW
        )
        tmp = df[["season", "position"]].copy()
        tmp["scenario"] = scenario_name
        tmp["cutoff_rank"] = tmp["position"].map(cutoffs)
        tmp["replacement_points"] = repl_points
        tmp["replacement_ppg"] = repl_ppg
        rows.append(tmp.drop_duplicates(subset=["season", "position", "scenario"]))
    return pd.concat(rows, ignore_index=True).sort_values(["scenario", "position", "season"])


def _weekly_with_rank(df: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    rank_lookup = df[["season", "player_id", "position", "position_finish_ppr"]].drop_duplicates()
    weekly = weekly.merge(rank_lookup, on=["season", "player_id"], how="inner",
                           suffixes=("", "_rank"))
    # weekly source already has its own 'position' column -- keep the
    # master DB's version (post position_overrides.csv corrections)
    # since that's the one position_finish_ppr was actually ranked
    # against. Avoids a silent mismatch between the two sources' raw
    # position tags.
    if "position_rank" in weekly.columns:
        weekly = weekly.drop(columns=["position"]).rename(columns={"position_rank": "position"})
    return weekly


def active_week_table(df: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """ACTIVE-WEEK production -- see module docstring. Conditioned on
    real recorded activity; will read higher than true full-slate
    replacement output, since replacement-tier players miss games too."""
    weekly = _weekly_with_rank(df, weekly)

    rows = []
    for scenario_name, preset_name, flex_alloc in SCENARIOS:
        cutoffs = build_cutoffs(preset_name, flex_alloc)
        for pos in POSITIONS:
            cutoff = cutoffs[pos]
            tier = weekly[
                (weekly["position"] == pos)
                & (weekly["position_finish_ppr"] >= cutoff)
                & (weekly["position_finish_ppr"] <= cutoff + WINDOW)
            ]
            if len(tier) == 0:
                continue
            pts = tier["fantasy_points_ppr"]
            row = {
                "scenario": scenario_name, "position": pos, "cutoff_rank": cutoff,
                "n_player_weeks": len(pts), "mean": pts.mean(), "median": pts.median(),
            }
            for p in PERCENTILES:
                row[f"p{int(p*100)}"] = pts.quantile(p)
            rows.append(row)
    return pd.DataFrame(rows)


def infer_excluded_weeks(weekly: pd.DataFrame, team_col: str = "recent_team") -> dict:
    """
    (season, team) -> set of weeks excluded from the calendar because
    NO player on that team has any recorded row that week -- i.e. a
    real bye, or (rarely) a real canceled game. See module docstring
    for the verification performed (606/608 real team-seasons produce
    exactly one such week; the 2 exceptions are a real, known
    canceled game, not a bug) before trusting this inference.
    """
    max_week_by_season = weekly.groupby("season")["week"].max().to_dict()
    active = weekly.groupby(["season", team_col, "week"]).size().reset_index(name="n")

    excluded = {}
    for season, max_wk in max_week_by_season.items():
        all_weeks = set(range(1, int(max_wk) + 1))
        teams = weekly.loc[weekly["season"] == season, team_col].unique()
        for team in teams:
            active_weeks = set(
                active.loc[(active["season"] == season) & (active[team_col] == team), "week"]
            )
            excluded[(season, team)] = all_weeks - active_weeks
    return excluded


def calendar_week_table(df: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """
    Calendar-week production WITH EXPLICIT ZEROES for genuinely missed
    (non-bye, non-canceled) weeks -- see module docstring for the
    trade-mid-season simplification (uses the player's master-DB
    season team for the whole season).
    """
    excluded_weeks = infer_excluded_weeks(weekly)
    weekly_indexed = weekly.set_index(["season", "player_id", "week"])["fantasy_points_ppr"]

    rows = []
    for scenario_name, preset_name, flex_alloc in SCENARIOS:
        cutoffs = build_cutoffs(preset_name, flex_alloc)
        for pos in POSITIONS:
            cutoff = cutoffs[pos]
            tier_players = df[
                (df["position"] == pos)
                & (df["position_finish_ppr"] >= cutoff)
                & (df["position_finish_ppr"] <= cutoff + WINDOW)
            ][["season", "player_id", "team"]]
            if len(tier_players) == 0:
                continue

            calendar_points = []
            for _, r in tier_players.iterrows():
                season, player_id, team = r["season"], r["player_id"], r["team"]
                max_wk = weekly.loc[weekly["season"] == season, "week"].max()
                if pd.isna(max_wk):
                    continue
                excluded = excluded_weeks.get((season, team), set())
                for wk in range(1, int(max_wk) + 1):
                    if wk in excluded:
                        continue
                    pts = weekly_indexed.get((season, player_id, wk), 0.0)
                    calendar_points.append(pts)

            if not calendar_points:
                continue
            pts = pd.Series(calendar_points)
            row = {
                "scenario": scenario_name, "position": pos, "cutoff_rank": cutoff,
                "n_calendar_weeks": len(pts), "n_zero_weeks": int((pts == 0).sum()),
                "mean": pts.mean(), "median": pts.median(),
            }
            for p in PERCENTILES:
                row[f"p{int(p*100)}"] = pts.quantile(p)
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(BROAD_DATASET_PATH)
    weekly = pd.read_csv(WEEKLY_PATH)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Roster assumptions:")
    for scenario_name, preset_name, flex_alloc in SCENARIOS:
        cutoffs = build_cutoffs(preset_name, flex_alloc)
        print(f"  {scenario_name}: {cutoffs}")

    season_table = season_level_table(df)
    season_path = OUTPUT_DIR / "replacement_level_season.csv"
    season_table.to_csv(season_path, index=False)
    print(f"\nreplacement_level_season.csv: {len(season_table)} rows -> {season_path}")

    active_table = active_week_table(df, weekly)
    active_path = OUTPUT_DIR / "replacement_level_weekly_active.csv"
    active_table.to_csv(active_path, index=False)
    print(f"\nreplacement_level_weekly_active.csv: {len(active_table)} rows -> {active_path}")
    print("ACTIVE-WEEK production (conditioned on real recorded activity -- reads HIGH, see docstring):")
    print(active_table.to_string(index=False))

    calendar_table = calendar_week_table(df, weekly)
    calendar_path = OUTPUT_DIR / "replacement_level_weekly_calendar.csv"
    calendar_table.to_csv(calendar_path, index=False)
    print(f"\nreplacement_level_weekly_calendar.csv: {len(calendar_table)} rows -> {calendar_path}")
    print("CALENDAR-WEEK production (explicit zeroes for genuinely missed, non-bye weeks):")
    print(calendar_table.to_string(index=False))

    comparison = active_table.merge(
        calendar_table, on=["scenario", "position", "cutoff_rank"], suffixes=("_active", "_calendar")
    )
    comparison["mean_gap"] = comparison["mean_active"] - comparison["mean_calendar"]
    print("\nGap between active-week and calendar-week mean (how much active-week overstates output):")
    print(comparison[["scenario", "position", "cutoff_rank", "mean_active", "mean_calendar", "mean_gap"]].to_string(index=False))

    summary = (
        season_table.groupby(["scenario", "position", "cutoff_rank"])[["replacement_points", "replacement_ppg"]]
        .agg(["mean", "median", "min", "max"])
    )
    summary.columns = [f"{col}_{stat}" for col, stat in summary.columns]
    summary = summary.reset_index()
    summary_path = OUTPUT_DIR / "replacement_level_summary_by_scenario.csv"
    summary.to_csv(summary_path, index=False)
    print(f"\nreplacement_level_summary_by_scenario.csv: {len(summary)} rows -> {summary_path}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
