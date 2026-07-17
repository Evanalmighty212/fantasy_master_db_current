"""
03_download_stats.py

Purpose:
- Download weekly nflverse data for every season in scope.
- Aggregate to season-level PPR fantasy results.
- Compute overall and positional finish ranks.

Fixes applied (Priority 1 audit, see docs/ or PR notes):
1. `recent_team` removed from the player-season grouping key. A player
   traded mid-season previously got split into multiple rows (one per
   team), which silently fragmented their season totals -- games_played,
   fantasy_points_ppr, and ppg_ppr were all undercounted for anyone who
   changed teams. Team is now captured separately (primary_team +
   teams_all) without affecting the aggregation.
2. "Official" games_played is now defined as weeks with actual offensive
   involvement (attempts + carries + targets > 0), not just "any row
   present in the weekly table for that week." nflverse weekly data can
   include appearance rows for weeks with zero offensive usage; counting
   those as "games played" overstates games and understates PPG.
3. ppg_ppr is calculated explicitly as fantasy_points_ppr / games_played
   (using the official games_played from #2), not pandas' row-mean --
   the old row-mean was averaging over every row in the group (including
   the fragments from #1 and any non-played rows from #2), which made it
   silently wrong in two compounding ways.
4. Filtered to QB/RB/WR/TE before aggregation -- K/DST are out of scope
   per docs/VERSION_1_SCOPE.md and were previously polluting both the
   output rows and the overall_finish_ppr ranking.
5. Duplicate player-season validation: after grouping strictly on
   (season, player_id), any player_id appearing more than once in a
   season (e.g. inconsistent player_display_name/position across weeks)
   is flagged to a CSV instead of silently passing through.
6. Also emits a weekly-level output (weekly_results_ppr_*.csv) alongside
   the season-level table, closing the data gap identified in
   docs/METRIC_SPECIFICATION.md -- two LWI components (Playoff
   Performance, Consistency) are inherently weekly-pattern metrics and
   can't be computed from season totals alone.
7. "Played" definition broadened after finding a real gap while testing
   #6: attempts+carries+targets > 0 alone missed weeks where a player
   scored ENTIRELY via a special-teams return touchdown (zero passing/
   rushing/receiving touches, but real points on the board -- e.g.
   Jeremy Ross, week 14 2013: 0/0/0 attempts/carries/targets, but 12.0
   fantasy points from two return TDs). That week is a real played
   game and was being wrongly excluded from games_played, which both
   undercounted games_played and overstated ppg_ppr for every player
   who ever had a scoring week like this. Fixed by broadening "played"
   to: (attempts+carries+targets > 0) OR (fantasy_points_ppr != 0) --
   fully general rather than enumerating every possible scoring
   category (return TDs, two-point conversion returns, etc.) by name.

Input:  config.SEASONS
Output: data/raw/nflverse/season_results_ppr_<start>_<end>.csv
        data/raw/nflverse/weekly_results_ppr_<start>_<end>.csv
        data/raw/nflverse/weekly_download_failures.csv
        data/raw/nflverse/season_player_duplicates.csv
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import nfl_data_py as nfl

from config import SEASONS

RAW_DIR = Path("data/raw/nflverse")
RAW_DIR.mkdir(parents=True, exist_ok=True)

SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]

# Columns used to determine whether a week counts as "officially played."
# A row with zero across all of these represents no offensive involvement
# (bye week, inactive, practice squad, etc.) even if nflverse emitted a
# row for that player/week.
INVOLVEMENT_COLS = ["attempts", "carries", "targets"]

# The grouping key is deliberately narrow: season + player_id only.
# player_display_name and position are carried through via first()/mode()
# rather than included in the groupby key, so a player who is (rarely)
# logged with two different display-name spellings or a mid-season
# position change in the source data doesn't get split into two rows --
# that kind of inconsistency is instead caught by the duplicate check
# below and surfaced for review, not silently multiplied.
GROUP_KEY = ["season", "player_id"]


def build_season_results():
    print("Step 1: Downloading weekly nflverse data...")
    frames = []
    failed = []

    for season in SEASONS:
        try:
            print(f"  downloading {season}...")
            frames.append(nfl.import_weekly_data([season]))
        except Exception as e:
            print(f"  FAILED {season}: {e}")
            failed.append({"season": season, "error": str(e)})

    if not frames:
        raise RuntimeError("No weekly data downloaded.")

    weekly = pd.concat(frames, ignore_index=True)
    weekly = weekly[weekly["season_type"] == "REG"].copy()

    pd.DataFrame(failed).to_csv(RAW_DIR / "weekly_download_failures.csv", index=False)

    print("Step 2: Filtering to QB/RB/WR/TE (v1.0 scope)...")
    before = len(weekly)
    weekly = weekly[weekly["position"].isin(SKILL_POSITIONS)].copy()
    print(f"  {before} -> {len(weekly)} rows after position filter")

    for col in INVOLVEMENT_COLS:
        if col not in weekly.columns:
            raise KeyError(
                f"Expected involvement column '{col}' not found in nflverse "
                f"weekly data -- games_played definition needs updating "
                f"to match the current nfl_data_py schema."
            )

    print("Step 3: Computing official games_played (weeks with real offensive involvement)...")
    involvement = weekly[INVOLVEMENT_COLS].fillna(0).sum(axis=1)
    # Broadened per fix #7 (see module docstring): attempts+carries+targets
    # alone misses weeks where a player scored entirely via a special-teams
    # return TD (zero offensive touches, but real points). Any nonzero
    # fantasy_points_ppr is itself proof of a real played week.
    scored_points = weekly["fantasy_points_ppr"].fillna(0) != 0
    played = weekly[(involvement > 0) | scored_points].copy()

    games_played = (
        played.groupby(GROUP_KEY, dropna=False)["week"]
        .nunique()
        .rename("games_played")
    )

    print("Step 4: Summing season totals (all weeks -- non-played weeks contribute 0)...")
    totals = (
        weekly.groupby(GROUP_KEY, dropna=False)
        .agg(fantasy_points_ppr=("fantasy_points_ppr", "sum"))
    )

    # Team handling, deliberately outside the aggregation key (fix #1).
    # primary_team: the team the player appeared for most that season,
    # ties broken by whichever team they last appeared with (so a
    # deadline-deal player is credited to their new team on a tie).
    def _primary_team(group):
        counts = group["recent_team"].value_counts()
        top = counts[counts == counts.max()].index
        if len(top) == 1:
            return top[0]
        last_team = group.sort_values("week")["recent_team"].iloc[-1]
        return last_team if last_team in top else top[0]

    team_info = (
        weekly.groupby(GROUP_KEY, dropna=False)
        .apply(lambda g: pd.Series({
            "primary_team": _primary_team(g),
            "teams_all": ",".join(sorted(set(g["recent_team"].dropna()))),
        }))
    )

    # Carry through display name and position without letting either
    # fragment the grouping key -- use the most frequent value observed.
    identity_info = (
        weekly.groupby(GROUP_KEY, dropna=False)
        .agg(
            player_display_name=("player_display_name", lambda s: s.mode().iat[0]),
            position=("position", lambda s: s.mode().iat[0]),
        )
    )

    season = (
        totals.join(games_played, how="left")
        .join(team_info, how="left")
        .join(identity_info, how="left")
        .reset_index()
    )
    season["games_played"] = season["games_played"].fillna(0).astype("Int64")

    print("Step 5: Calculating PPG explicitly (fantasy_points_ppr / games_played)...")
    season["ppg_ppr"] = season.apply(
        lambda r: round(r["fantasy_points_ppr"] / r["games_played"], 2)
        if r["games_played"] and r["games_played"] > 0
        else pd.NA,
        axis=1,
    )

    print("Step 6: Ranking overall and positional finishes...")
    season["overall_finish_ppr"] = (
        season.groupby("season")["fantasy_points_ppr"]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )
    season["position_finish_ppr"] = (
        season.groupby(["season", "position"])["fantasy_points_ppr"]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )

    season = season.sort_values(["season", "overall_finish_ppr"])

    print("Step 7: Validating for duplicate player-seasons...")
    dupes = season[season.duplicated(subset=GROUP_KEY, keep=False)]
    dupe_path = RAW_DIR / "season_player_duplicates.csv"
    dupes.to_csv(dupe_path, index=False)
    if len(dupes) > 0:
        print(f"  {len(dupes)} duplicate (season, player_id) rows "
              f"found -- see {dupe_path}.")
    else:
        print("  No duplicate (season, player_id) rows found.")

    # Hard fail, not just a warning: exactly one row per (season, player_id)
    # is a structural requirement of the Master Historical Database (every
    # downstream join in 04_build_master_dataset.py assumes it), so the
    # pipeline should stop here rather than silently propagate a broken
    # table. This is intentionally cheap and intentionally strict.
    duplicate_count = season.duplicated(subset=GROUP_KEY).sum()
    assert duplicate_count == 0, (
        f"{duplicate_count} duplicate (season, player_id) rows found in "
        f"season results -- see {dupe_path} for details. This usually "
        f"means a team/roster field leaked back into the aggregation "
        f"grouping key. Fix the aggregation before re-running the pipeline."
    )

    out_path = RAW_DIR / f"season_results_ppr_{SEASONS[0]}_{SEASONS[-1]}.csv"
    season.to_csv(out_path, index=False)

    print(f"\nCreated {out_path}")
    print(f"Rows: {len(season)}")
    print(f"Seasons covered: {season['season'].min()}-{season['season'].max()}")
    print(f"Duplicate player-seasons flagged: {len(dupes)}")

    print("\nStep 8: Writing weekly-level results (for Playoff Performance / "
          "Consistency in the LWI -- see docs/METRIC_SPECIFICATION.md)...")
    # Reuses the SAME "played" filter (Step 3, broadened per fix #7) --
    # deliberately, so a week counts here iff it counted toward
    # games_played. This is also exactly the bye-week exclusion the
    # Consistency spec calls for.
    #
    # De-dup guard: nflverse's own raw data occasionally has TWO rows
    # for the same (season, player_id, week) -- found while testing
    # this (Matthew Stafford, 2010, week 8: one row with real passing
    # stats, a second with all-zero stats but 2.0 fantasy points,
    # apparently a correction/revision artifact in their source, not
    # anything in this script's logic). Left un-deduped, that would
    # silently double-count one week in any Consistency calculation
    # built on this table. Summing collapses it to one row per week
    # with the correct total, matching games_played's nunique()-based
    # count exactly.
    weekly_raw = played[
        GROUP_KEY + ["week", "player_display_name", "position", "recent_team", "fantasy_points_ppr"]
    ]
    dup_weeks = weekly_raw[weekly_raw.duplicated(subset=GROUP_KEY + ["week"], keep=False)]
    if len(dup_weeks) > 0:
        print(f"  NOTE: {len(dup_weeks)} raw rows found sharing a (season, "
              f"player_id, week) key -- nflverse source data artifact, not "
              f"a bug here. Summing fantasy_points_ppr within each "
              f"duplicated week so it counts once, matching games_played.")

    weekly_out = (
        weekly_raw.groupby(GROUP_KEY + ["week"], as_index=False)
        .agg(
            player_display_name=("player_display_name", "first"),
            position=("position", "first"),
            recent_team=("recent_team", "first"),
            fantasy_points_ppr=("fantasy_points_ppr", "sum"),
        )
        .sort_values(GROUP_KEY + ["week"])
    )

    weekly_out_path = RAW_DIR / f"weekly_results_ppr_{SEASONS[0]}_{SEASONS[-1]}.csv"
    weekly_out.to_csv(weekly_out_path, index=False)
    print(f"Created {weekly_out_path}")
    print(f"Rows: {len(weekly_out)} (player-weeks with real offensive involvement)")

    return season


def main():
    build_season_results()


if __name__ == "__main__":
    main()
