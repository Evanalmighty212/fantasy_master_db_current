"""
wr_preseason_cohort_replacement_analysis.py

Research script (NOT part of the production pipeline -- reads the
master database, writes nowhere production output is read from).

Second follow-up to wr_games_played_impact.py / wr_elite_ppg_games_
played_impact.py. The prior elite-PPG script still selected its
"elite" cohort using the SAME season being evaluated -- so a player's
membership in the elite group already reflected the outcome (rate of
production) of the very season whose games-played relationship we
were then measuring. That's hindsight/survivorship bias: the cohort
can only contain players who, whatever games they missed, still
produced at an elite rate DURING the games they played.

This script removes that specific bias by defining "elite" using ONLY
the PRIOR season (fully known before the season being evaluated
starts), then tracking that fixed, preseason-knowable cohort into the
following season with no further selection on the following season's
outcome. This is a materially closer analogue to a real preseason
question ("this WR entered the year as a proven top-12/top-6 PPG
performer -- what happens if he misses time this year?").

================================================================
POPULATION AND KEY DEFINITIONS
================================================================

Qualified pool (both prior-season cohort selection AND following-
season PPG-rank lookups): WR player-seasons, games_played >= 8,
ranked by ppg_ppr descending within season, pandas `rank(method=
"min")` (ties share the better rank; a tie AT the cohort cutoff
means the cohort can hold slightly more than 12 (or 6) players that
year -- rare at 2-decimal PPG precision, but reported transparently
rather than arbitrarily broken).

Cohorts: for every following season Y in 2007-2025, the prior season
is Y-1. Two cohorts are built independently, using ppg_rank in Y-1:
  - top12: prior_ppg_rank <= 12
  - top6:  prior_ppg_rank <= 6
Cohort membership is fixed at this point and never revisited using Y.

Player identity across seasons: player_id (stable across a team
change within or between seasons). The master database already
carries one row per player per season regardless of how many teams
that player was on (verified directly: Emmanuel Sanders' 2019 season,
split between Denver and San Francisco, is a single row) -- so
mid-season and season-to-season team changes require no special
handling here.

Games-played buckets (following season only, same convention as the
prior two scripts): 17, 16, 15, 14, 13, 12, and 8-11 combined.
Cohort members who played the following season but logged fewer than
8 games, and cohort members with NO row at all in the following
season (retired, out of the league, or otherwise absent from the
box-score source), fall outside every bucket below -- see "Cohort
accounting" for where they went; they are deliberately not folded
into the 8-11 bucket, which would understate how bad the true worst
case can be.

"WR PPG rank" vs "WR positional finish" are DIFFERENT things,
reported separately throughout, per the same principle already
applied to positional-vs-overall finish in the prior script:
  - ppg_rank: rank by rate (ppg_ppr) within the games>=8 qualified
    pool only -- "how elite was he on a per-game basis."
  - position_finish_ppr: the database's own within-WR rank by season
    TOTAL points, across the entire WR population regardless of
    games played -- "where did his real, actual season end up."
A player can miss significant time and still rank elite by rate while
falling well outside the top tier by total-points finish; that gap is
exactly what several of the tables below are measuring.

================================================================
REPLACEMENT-POINTS METHODOLOGY
================================================================

missed_games = season_length(season) - games_played, clipped at a
floor of 0. season_length = 17 for season >= 2021, else 16. Because
each team's actual schedule length already excludes that team's own
bye week, this formula does NOT need a separate bye-week adjustment
-- a player who played every game his team played has games_played
== season_length by construction, bye week already excluded.

adjusted_points = fantasy_points_ppr + missed_games * replacement_ppg

replacement_ppg is looked up PER SEASON (never a fixed cross-era
number) as the ppg_ppr of the WR who actually finished at
position_finish_ppr == 48 (low/"WR48"), 36 (medium/"WR36"), or 24
(strong/"WR24") that season -- i.e. the real, observed per-game rate
of whoever actually occupied that season-ending rank, not a
theoretical or windowed estimate. This intentionally does NOT reuse
this project's own LWI replacement-level convention
(LWI_REPLACEMENT_RANK_THRESHOLDS / LWI_REPLACEMENT_WINDOW in
config.py, a 12-player-window median centered near WR42) -- the user
task for this script specified exact WR48/36/24 anchors, and a single
season-actual value at that rank is the more literal, auditable
reading of that instruction. This is a real, disclosed methodological
choice, not an oversight: it means a rank-24/36/48 finisher who
happened to reach that rank in relatively few games (high rate, low
counting stats) can push a season's replacement_ppg for that
threshold slightly high relative to a smoothed estimate. In two
seasons (2011 and 2016) no WR finished at exactly rank 48 (a tie
elsewhere in the standings skips that integer) -- for those, the
nearest rank <= 48 with a valid ppg_ppr is used instead, logged to
stdout when the script runs.

The KNOWN 2019 games_played == 17 outlier (one player, traded
mid-season, real per the prior script's verification against raw
weekly data -- see wr_games_played_impact.py) and the games_played
== 18 anomaly (one 2025 row) both produce a negative raw missed_games
under a 16- or 17-game season length; both are clipped to the 0
floor like any other case, so they simply contribute zero replacement
production, never negative. Neither row is a following-season member
of either cohort in this dataset (checked directly), so this only
matters for the full-population ranking denominator described next,
not for any cohort-level number reported below.

"Adjusted roster-slot rank" is computed by ranking adjusted_points
within season across the ENTIRE WR population (every games_played
value, 0 included -- a totally missed season becomes "a replacement
player started every game," which is the correct interpretation for
a roster-slot-value question), independently for each of the three
replacement assumptions. Cohort members' adjusted rank is then looked
up from that full-population ranking. This is a DIFFERENT ranking
from the real, actual position_finish_ppr / overall_finish_ppr
reported in the cohort-tracking tables above it -- the two are never
combined or substituted for each other.
"""

from pathlib import Path

import numpy as np
import pandas as pd

MASTER_DB_PATH = Path("data/master/master_historical_db_with_lwi_2006_2025.csv")
OUTPUT_DIR = Path("research/output")

MIN_GAMES = 8
GAMES_BUCKET_ORDER = ["17", "16", "15", "14", "13", "12", "8-11"]
COHORT_DEFS = {"top12": 12, "top6": 6}
PPG_RANK_THRESHOLDS = [6, 12, 20, 24]
WR_FINISH_THRESHOLDS = [12, 20, 24]
REPLACEMENT_ASSUMPTIONS = {"low_WR48": 48, "medium_WR36": 36, "strong_WR24": 24}
ROSTER_SLOT_THRESHOLDS = [12, 20, 24, 36]
FIRST_FOLLOWING_SEASON = 2007
LAST_FOLLOWING_SEASON = 2025


def season_length(season: int) -> int:
    return 17 if season >= 2021 else 16


def games_bucket(games_played) -> str:
    if pd.isna(games_played):
        return "n/a"
    g = int(games_played)
    return str(g) if g >= 12 else "8-11"


def load_wr() -> pd.DataFrame:
    df = pd.read_csv(MASTER_DB_PATH)
    return df[df["position"] == "WR"].copy()


def build_qualified_pool(wr: pd.DataFrame) -> pd.DataFrame:
    """games_played >= MIN_GAMES, with within-season ppg_rank attached."""
    q = wr[wr["games_played"] >= MIN_GAMES].copy()
    q["ppg_rank"] = q.groupby("season")["ppg_ppr"].rank(ascending=False, method="min")
    return q


def build_cohort_followups(wr: pd.DataFrame, qualified: pd.DataFrame, cohort_n: int) -> pd.DataFrame:
    rows = []
    for following_season in range(FIRST_FOLLOWING_SEASON, LAST_FOLLOWING_SEASON + 1):
        prior_season = following_season - 1
        prior_pool = qualified[qualified["season"] == prior_season]
        if prior_pool.empty:
            continue
        cohort = prior_pool[prior_pool["ppg_rank"] <= cohort_n]
        following_all = wr[wr["season"] == following_season]
        following_qual = qualified[qualified["season"] == following_season]

        for _, prow in cohort.iterrows():
            rec = {
                "player_id": prow["player_id"],
                "player_name": prow["player_name"],
                "prior_season": prior_season,
                "following_season": following_season,
                "prior_ppg": prow["ppg_ppr"],
                "prior_ppg_rank": prow["ppg_rank"],
            }
            frow = following_all[following_all["player_id"] == prow["player_id"]]
            if frow.empty:
                rec["played_following_season"] = False
                for k in ("following_games", "following_ppg", "following_total_points",
                          "following_wr_finish", "following_overall_finish", "following_ppg_rank"):
                    rec[k] = np.nan
            else:
                f = frow.iloc[0]
                rec["played_following_season"] = True
                rec["following_games"] = f["games_played"]
                rec["following_ppg"] = f["ppg_ppr"]
                rec["following_total_points"] = f["fantasy_points_ppr"]
                rec["following_wr_finish"] = f["position_finish_ppr"]
                rec["following_overall_finish"] = f["overall_finish_ppr"]
                fq = following_qual[following_qual["player_id"] == prow["player_id"]]
                rec["following_ppg_rank"] = fq["ppg_rank"].iloc[0] if not fq.empty else np.nan
            rows.append(rec)

    out = pd.DataFrame(rows)
    out["yoy_ppg_change"] = out["following_ppg"] - out["prior_ppg"]
    out["yoy_ppg_rank_change"] = out["following_ppg_rank"] - out["prior_ppg_rank"]
    out["games_bucket"] = out["following_games"].apply(games_bucket)
    return out


def cohort_accounting(followups: pd.DataFrame) -> dict:
    total = len(followups)
    no_row = (~followups["played_following_season"]).sum()
    played = followups[followups["played_following_season"]]
    lt_min = (played["following_games"] < MIN_GAMES).sum()
    bucketed = (played["following_games"] >= MIN_GAMES).sum()
    return {
        "total_cohort_player_seasons": total,
        "no_following_season_row": int(no_row),
        "played_but_under_8_games": int(lt_min),
        "bucketed_8_to_17_games": int(bucketed),
    }


def summarize_bucket_group(g: pd.DataFrame) -> dict:
    n = len(g)
    row = {"n": n}
    row["avg_ppg"] = g["following_ppg"].mean()
    row["median_ppg"] = g["following_ppg"].median()
    row["avg_ppg_rank"] = g["following_ppg_rank"].mean()
    row["median_ppg_rank"] = g["following_ppg_rank"].median()
    for t in PPG_RANK_THRESHOLDS:
        row[f"pct_top{t}_ppg_rank"] = (g["following_ppg_rank"] <= t).mean() * 100
    row["avg_total_points"] = g["following_total_points"].mean()
    row["median_total_points"] = g["following_total_points"].median()
    row["avg_wr_finish"] = g["following_wr_finish"].mean()
    row["median_wr_finish"] = g["following_wr_finish"].median()
    row["avg_overall_finish"] = g["following_overall_finish"].mean()
    row["median_overall_finish"] = g["following_overall_finish"].median()
    for t in WR_FINISH_THRESHOLDS:
        row[f"pct_top{t}_wr_finish"] = (g["following_wr_finish"] <= t).mean() * 100
    row["avg_yoy_ppg_change"] = g["yoy_ppg_change"].mean()
    row["median_yoy_ppg_change"] = g["yoy_ppg_change"].median()
    row["avg_yoy_rank_change"] = g["yoy_ppg_rank_change"].mean()
    row["median_yoy_rank_change"] = g["yoy_ppg_rank_change"].median()
    return row


def summarize_by_bucket(followups: pd.DataFrame) -> pd.DataFrame:
    bucketed = followups[followups["games_bucket"] != "n/a"]
    bucketed = bucketed[bucketed["following_games"] >= MIN_GAMES]
    rows = []
    for b in GAMES_BUCKET_ORDER:
        g = bucketed[bucketed["games_bucket"] == b]
        row = {"games_played": b}
        row.update(summarize_bucket_group(g) if len(g) else {"n": 0})
        rows.append(row)
    return pd.DataFrame(rows)


def rate_table_markdown(summary: pd.DataFrame, label: str) -> str:
    headers = ["Games Played", "N", "Avg PPG", "Median PPG", "Avg PPG Rank", "Median PPG Rank",
               "%Top6 PPG", "%Top12 PPG", "%Top20 PPG", "%Top24 PPG",
               "Avg YoY PPG Chg", "Median YoY PPG Chg", "Avg YoY Rank Chg", "Median YoY Rank Chg"]
    lines = [f"**{label} -- rate, PPG-rank, and year-over-year change**", "",
             "| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for _, r in summary.iterrows():
        if r["n"] == 0:
            lines.append(f"| {r['games_played']} | 0 |" + " -- |" * (len(headers) - 2))
            continue
        lines.append(
            "| {gp} | {n} | {appg:.2f} | {mppg:.2f} | {ar:.1f} | {mr:.1f} | "
            "{t6:.1f}% | {t12:.1f}% | {t20:.1f}% | {t24:.1f}% | "
            "{ayc:+.2f} | {myc:+.2f} | {arc:+.1f} | {mrc:+.1f} |".format(
                gp=r["games_played"], n=int(r["n"]),
                appg=r["avg_ppg"], mppg=r["median_ppg"],
                ar=r["avg_ppg_rank"], mr=r["median_ppg_rank"],
                t6=r["pct_top6_ppg_rank"], t12=r["pct_top12_ppg_rank"],
                t20=r["pct_top20_ppg_rank"], t24=r["pct_top24_ppg_rank"],
                ayc=r["avg_yoy_ppg_change"], myc=r["median_yoy_ppg_change"],
                arc=r["avg_yoy_rank_change"], mrc=r["median_yoy_rank_change"],
            )
        )
    return "\n".join(lines)


def finish_table_markdown(summary: pd.DataFrame, label: str) -> str:
    headers = ["Games Played", "N", "Avg Total Pts", "Median Total Pts",
               "Avg WR Finish", "Median WR Finish", "Avg Overall Finish", "Median Overall Finish",
               "%Top12 WR", "%Top20 WR", "%Top24 WR"]
    lines = [f"**{label} -- totals and real season finish**", "",
             "| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for _, r in summary.iterrows():
        if r["n"] == 0:
            lines.append(f"| {r['games_played']} | 0 |" + " -- |" * (len(headers) - 2))
            continue
        lines.append(
            "| {gp} | {n} | {atp:.1f} | {mtp:.1f} | {awf:.1f} | {mwf:.0f} | {aof:.1f} | {mof:.0f} | "
            "{t12:.1f}% | {t20:.1f}% | {t24:.1f}% |".format(
                gp=r["games_played"], n=int(r["n"]),
                atp=r["avg_total_points"], mtp=r["median_total_points"],
                awf=r["avg_wr_finish"], mwf=r["median_wr_finish"],
                aof=r["avg_overall_finish"], mof=r["median_overall_finish"],
                t12=r["pct_top12_wr_finish"], t20=r["pct_top20_wr_finish"], t24=r["pct_top24_wr_finish"],
            )
        )
    return "\n".join(lines)


def twelve_thirteen_fourteen_list(top12_followups: pd.DataFrame) -> pd.DataFrame:
    sub = top12_followups[
        top12_followups["played_following_season"]
        & top12_followups["following_games"].isin([12, 13, 14])
    ].copy()
    sub["injury_absence_timing"] = (
        "not available in project data -- no weekly injury/inactive-designation "
        "dataset exists in this repo (checked data/raw/nflverse and data/manual/); "
        "not added per instruction not to bring in external data for this field"
    )
    cols = ["player_name", "prior_season", "following_season", "prior_ppg", "prior_ppg_rank",
            "following_games", "following_ppg", "following_ppg_rank", "following_total_points",
            "following_wr_finish", "following_overall_finish", "injury_absence_timing"]
    return sub[cols].sort_values(["following_games", "following_ppg"], ascending=[True, False])


def twelve_thirteen_fourteen_markdown(sub: pd.DataFrame) -> str:
    headers = ["Player", "Prior Season", "Following Season", "Prior PPG", "Prior PPG Rank",
               "Following Games", "Following PPG", "Following PPG Rank", "Following Total Pts",
               "WR Finish", "Overall Finish"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for _, r in sub.iterrows():
        lines.append(
            "| {name} | {ps} | {fs} | {pp:.2f} | {pr:.0f} | {fg} | {fp:.2f} | {fr:.0f} | {ft:.1f} | {wf:.0f} | {of:.0f} |".format(
                name=r["player_name"], ps=int(r["prior_season"]), fs=int(r["following_season"]),
                pp=r["prior_ppg"], pr=r["prior_ppg_rank"], fg=int(r["following_games"]),
                fp=r["following_ppg"], fr=r["following_ppg_rank"], ft=r["following_total_points"],
                wf=r["following_wr_finish"], of=r["following_overall_finish"],
            )
        )
    lines.append("")
    lines.append("Injury/absence timing: " + sub["injury_absence_timing"].iloc[0] if len(sub) else "")
    return "\n".join(lines)


def build_replacement_lookup(wr_all: pd.DataFrame) -> tuple[dict, list]:
    lookup = {}
    notes = []
    for season, sdf in wr_all.groupby("season"):
        for label, target in REPLACEMENT_ASSUMPTIONS.items():
            match = sdf[(sdf["position_finish_ppr"] == target) & sdf["ppg_ppr"].notna()]
            used_rank = target
            if match.empty:
                cand = sdf[(sdf["position_finish_ppr"] <= target) & sdf["ppg_ppr"].notna()]
                used_rank = cand["position_finish_ppr"].max()
                match = cand[cand["position_finish_ppr"] == used_rank]
                notes.append((int(season), label, target, int(used_rank)))
            lookup[(season, label)] = match["ppg_ppr"].mean()
    return lookup, notes


def add_adjusted_points(wr_all: pd.DataFrame, lookup: dict) -> pd.DataFrame:
    out = wr_all.copy()
    out["season_length"] = out["season"].apply(season_length)
    out["missed_games"] = (out["season_length"] - out["games_played"]).clip(lower=0)
    for label in REPLACEMENT_ASSUMPTIONS:
        repl_ppg = out.apply(lambda r, lab=label: lookup[(r["season"], lab)], axis=1)
        out[f"adjusted_points_{label}"] = out["fantasy_points_ppr"] + out["missed_games"] * repl_ppg
        out[f"adjusted_rank_{label}"] = out.groupby("season")[f"adjusted_points_{label}"].rank(
            ascending=False, method="min"
        )
    return out


def summarize_replacement_by_bucket(followups: pd.DataFrame, adjusted: pd.DataFrame, label: str) -> pd.DataFrame:
    merged = followups[followups["played_following_season"] & (followups["following_games"] >= MIN_GAMES)].merge(
        adjusted[["player_id", "season", f"adjusted_points_{label}", f"adjusted_rank_{label}"]],
        left_on=["player_id", "following_season"], right_on=["player_id", "season"], how="left",
    )
    rows = []
    for b in GAMES_BUCKET_ORDER:
        g = merged[merged["games_bucket"] == b]
        n = len(g)
        if n == 0:
            rows.append({"games_played": b, "n": 0})
            continue
        pts = g[f"adjusted_points_{label}"]
        rank = g[f"adjusted_rank_{label}"]
        row = {
            "games_played": b, "n": n,
            "avg_adjusted_points": pts.mean(), "median_adjusted_points": pts.median(),
            "avg_adjusted_rank": rank.mean(), "median_adjusted_rank": rank.median(),
        }
        for t in ROSTER_SLOT_THRESHOLDS:
            row[f"pct_top{t}_slot"] = (rank <= t).mean() * 100
        rows.append(row)
    return pd.DataFrame(rows)


def replacement_table_markdown(top12_summary: pd.DataFrame, top6_summary: pd.DataFrame, label: str, target_rank: int) -> str:
    headers = ["Cohort", "Games Played", "N", "Avg Adj Pts", "Median Adj Pts", "Avg Adj Rank", "Median Adj Rank",
               "%Top12 Slot", "%Top20 Slot", "%Top24 Slot", "%Top36 Slot"]
    lines = [f"**Replacement assumption: {label} (season's actual WR{target_rank} PPG)**", "",
             "| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for cohort_name, summary in (("top12", top12_summary), ("top6", top6_summary)):
        for _, r in summary.iterrows():
            if r["n"] == 0:
                lines.append(f"| {cohort_name} | {r['games_played']} | 0 |" + " -- |" * (len(headers) - 3))
                continue
            lines.append(
                "| {cn} | {gp} | {n} | {ap:.1f} | {mp:.1f} | {ar:.1f} | {mr:.1f} | "
                "{t12:.1f}% | {t20:.1f}% | {t24:.1f}% | {t36:.1f}% |".format(
                    cn=cohort_name, gp=r["games_played"], n=int(r["n"]),
                    ap=r["avg_adjusted_points"], mp=r["median_adjusted_points"],
                    ar=r["avg_adjusted_rank"], mr=r["median_adjusted_rank"],
                    t12=r["pct_top12_slot"], t20=r["pct_top20_slot"],
                    t24=r["pct_top24_slot"], t36=r["pct_top36_slot"],
                )
            )
    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wr = load_wr()
    qualified = build_qualified_pool(wr)

    followups = {}
    summaries = {}
    for name, n in COHORT_DEFS.items():
        fu = build_cohort_followups(wr, qualified, n)
        followups[name] = fu
        summaries[name] = summarize_by_bucket(fu)
        fu.to_csv(OUTPUT_DIR / f"wr_preseason_cohort_{name}_followups.csv", index=False)
        summaries[name].to_csv(OUTPUT_DIR / f"wr_preseason_cohort_{name}_bucket_summary.csv", index=False)

    print("=" * 100)
    print("PART 1: PRESEASON COHORT TRACKING")
    print("=" * 100)
    for name in COHORT_DEFS:
        print()
        print(rate_table_markdown(summaries[name], f"{name} cohort (prior-season PPG rank <= {COHORT_DEFS[name]})"))
        print()
        print(finish_table_markdown(summaries[name], f"{name} cohort (prior-season PPG rank <= {COHORT_DEFS[name]})"))
        acc = cohort_accounting(followups[name])
        print()
        print(f"Cohort accounting ({name}): {acc}")

    print()
    print("=" * 100)
    print("PART 2: TOP-12-PPG-COHORT PLAYERS WITH EXACTLY 12, 13, OR 14 FOLLOWING-SEASON GAMES")
    print("=" * 100)
    print()
    sub = twelve_thirteen_fourteen_list(followups["top12"])
    sub.to_csv(OUTPUT_DIR / "wr_preseason_cohort_top12_games_12_13_14_list.csv", index=False)
    print(twelve_thirteen_fourteen_markdown(sub))

    print()
    print("=" * 100)
    print("PART 3: REPLACEMENT-POINTS ANALYSIS")
    print("=" * 100)
    lookup, notes = build_replacement_lookup(wr)
    if notes:
        print()
        print("Rank-gap fallback used (no player finished at exactly the target rank that season):")
        for season, label, target, used in notes:
            print(f"  season={season} assumption={label} target_rank={target} -> used nearest rank {used}")

    outlier_check = wr[(wr["season"].apply(season_length) - wr["games_played"]) < 0]
    if len(outlier_check):
        print()
        print("Rows where games_played exceeds that season's schedule length (missed_games clipped to 0):")
        print(outlier_check[["season", "player_name", "games_played"]].to_string(index=False))

    adjusted = add_adjusted_points(wr, lookup)
    adjusted.to_csv(OUTPUT_DIR / "wr_all_seasons_adjusted_roster_slot_points.csv", index=False)

    for label, target_rank in REPLACEMENT_ASSUMPTIONS.items():
        top12_repl = summarize_replacement_by_bucket(followups["top12"], adjusted, label)
        top6_repl = summarize_replacement_by_bucket(followups["top6"], adjusted, label)
        top12_repl.to_csv(OUTPUT_DIR / f"wr_preseason_cohort_top12_replacement_{label}.csv", index=False)
        top6_repl.to_csv(OUTPUT_DIR / f"wr_preseason_cohort_top6_replacement_{label}.csv", index=False)
        print()
        print(replacement_table_markdown(top12_repl, top6_repl, label, target_rank))

    print()
    print(f"\nAll CSVs written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
