"""
wr_elite_ppg_games_played_impact.py

Research script (NOT part of the production pipeline -- reads the
master database, writes nowhere production output is read from).

Follow-up to wr_games_played_impact.py. That script's population was
every WR player-season with 8-17 games played -- which mixes true
"missed time" cases in with fringe/backup/committee WRs whose few
games AND low points both came from a limited role, not injury. That
mixing means low-games buckets there were dragged down by players who
were never going to be productive regardless of health, so the
relationship between games played and finish couldn't be cleanly
attributed to missed time alone.

This script isolates production QUALITY from playing time by first
restricting to seasons that already cleared an elite per-game bar,
then asking how games played relates to finish only within that
elite-production group. This is a closer (though still imperfect --
see the selection-bias discussion in the printed report) proxy for
"how would an already-elite WR's finish be affected by missing
games" than the all-WR relationship is.

Population: WR player-seasons, 2006-2025, games_played >= 8 (the
same floor as the prior script, to keep tiny-sample hot streaks out
of the ranking pool -- e.g. 2 huge games would otherwise post a
false top-tier PPG).

Method: within each season, rank the qualified pool by ppg_ppr
descending and take the top 12 (primary group) and, separately, the
top 6 (sensitivity group, run second). Ties in ppg_ppr are broken by
an explicit stable sort (kind="stable"), which preserves original row
order for equal keys -- this project's other rank-based work
(overall_finish_ppr / position_finish_ppr, computed upstream in
05_calculate_metrics.py) uses its own tie-break convention; the
top-N selection here is independent of that and only affects which
side of an exact-tie cutoff a player lands on, which is rare at
PPG-level precision.

Two finish measures are reported and thresholded SEPARATELY, on
purpose:
  - position_finish_ppr: rank within WR only (WR1, WR2, ...)
  - overall_finish_ppr: rank across QB/RB/WR/TE combined
"Top 36 overall" is NOT "WR3" or any fixed WR-rank equivalent -- the
overall pool mixes positions in different proportions at different
depths, so a top-36-overall finish can correspond to a wide range of
WR ranks depending on the season's positional scoring environment.
"""

from pathlib import Path

import pandas as pd
from lib.player_season_authority import resolved_canonical_position_population

MASTER_DB_PATH = Path("data/master/master_historical_db_with_lwi_2006_2025.csv")
OUTPUT_DIR = Path("research/output")

MIN_GAMES = 8
GAMES_BUCKET_ORDER = ["17", "16", "15", "14", "13", "12", "8-11"]
WR_FINISH_THRESHOLDS = [12, 20, 24]
OVERALL_FINISH_THRESHOLDS = [12, 20, 36]


def load_qualified_wr_seasons() -> pd.DataFrame:
    df = pd.read_csv(MASTER_DB_PATH)
    df = resolved_canonical_position_population(df)
    wr = df[(df["position"] == "WR") & (df["games_played"] >= MIN_GAMES)].copy()
    return wr


def top_n_by_ppg(wr: pd.DataFrame, n: int) -> pd.DataFrame:
    """Top n WRs by ppg_ppr within each season (explicit stable sort tie-break)."""
    ranked = wr.sort_values(
        ["season", "ppg_ppr"],
        ascending=[True, False],
        kind="stable",
    )
    return ranked.groupby("season", group_keys=False).head(n).copy()


def games_bucket(games_played: int) -> str:
    if games_played >= 12:
        return str(games_played)
    return "8-11"


def summarize_by_games_bucket(elite: pd.DataFrame) -> pd.DataFrame:
    elite = elite.copy()
    elite["games_bucket"] = elite["games_played"].apply(games_bucket)

    rows = []
    for bucket in GAMES_BUCKET_ORDER:
        group = elite[elite["games_bucket"] == bucket]
        n = len(group)
        if n == 0:
            rows.append({"games_played": bucket, "n": 0})
            continue

        row = {
            "games_played": bucket,
            "n": n,
            "avg_ppg": group["ppg_ppr"].mean(),
            "median_ppg": group["ppg_ppr"].median(),
            "avg_total_points": group["fantasy_points_ppr"].mean(),
            "median_total_points": group["fantasy_points_ppr"].median(),
            "avg_wr_finish": group["position_finish_ppr"].mean(),
            "median_wr_finish": group["position_finish_ppr"].median(),
            "avg_overall_finish": group["overall_finish_ppr"].mean(),
            "median_overall_finish": group["overall_finish_ppr"].median(),
        }
        for t in WR_FINISH_THRESHOLDS:
            row[f"pct_top_{t}_wr"] = (group["position_finish_ppr"] <= t).mean() * 100
        for t in OVERALL_FINISH_THRESHOLDS:
            row[f"pct_top_{t}_overall"] = (group["overall_finish_ppr"] <= t).mean() * 100
        rows.append(row)

    return pd.DataFrame(rows)


def to_markdown_table(summary: pd.DataFrame, label: str) -> str:
    headers = [
        "Games Played", "N", "Avg PPG", "Median PPG",
        "Avg Total Pts", "Median Total Pts",
        "Avg WR Finish", "Median WR Finish",
        "Avg Overall Finish", "Median Overall Finish",
        "% Top12 WR", "% Top20 WR", "% Top24 WR",
        "% Top12 Ovr", "% Top20 Ovr", "% Top36 Ovr",
    ]
    lines = [f"**{label}**", "", "| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for _, r in summary.iterrows():
        if r["n"] == 0:
            lines.append(f"| {r['games_played']} | 0 |" + " -- |" * (len(headers) - 2))
            continue
        lines.append(
            "| {gp} | {n} | {appg:.2f} | {mppg:.2f} | {atp:.1f} | {mtp:.1f} | "
            "{awf:.1f} | {mwf:.0f} | {aof:.1f} | {mof:.0f} | "
            "{t12w:.1f}% | {t20w:.1f}% | {t24w:.1f}% | "
            "{t12o:.1f}% | {t20o:.1f}% | {t36o:.1f}% |".format(
                gp=r["games_played"], n=int(r["n"]),
                appg=r["avg_ppg"], mppg=r["median_ppg"],
                atp=r["avg_total_points"], mtp=r["median_total_points"],
                awf=r["avg_wr_finish"], mwf=r["median_wr_finish"],
                aof=r["avg_overall_finish"], mof=r["median_overall_finish"],
                t12w=r["pct_top_12_wr"], t20w=r["pct_top_20_wr"], t24w=r["pct_top_24_wr"],
                t12o=r["pct_top_12_overall"], t20o=r["pct_top_20_overall"], t36o=r["pct_top_36_overall"],
            )
        )
    return "\n".join(lines)


def thirteen_game_list(elite_top12: pd.DataFrame) -> pd.DataFrame:
    cols = ["player_name", "season", "ppg_ppr", "fantasy_points_ppr",
            "position_finish_ppr", "overall_finish_ppr", "lwi_score"]
    sub = elite_top12[elite_top12["games_played"] == 13][cols].copy()
    return sub.sort_values("ppg_ppr", ascending=False)


def thirteen_game_list_markdown(thirteen: pd.DataFrame) -> str:
    headers = ["Player", "Season", "PPG", "Total Pts", "WR Finish", "Overall Finish", "LWI"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for _, r in thirteen.iterrows():
        lwi = "n/a" if pd.isna(r["lwi_score"]) else f"{r['lwi_score']:.1f}"
        lines.append(
            "| {name} | {season} | {ppg:.2f} | {pts:.1f} | {wf} | {of} | {lwi} |".format(
                name=r["player_name"], season=int(r["season"]),
                ppg=r["ppg_ppr"], pts=r["fantasy_points_ppr"],
                wf=int(r["position_finish_ppr"]), of=int(r["overall_finish_ppr"]),
                lwi=lwi,
            )
        )
    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wr = load_qualified_wr_seasons()

    elite_top12 = top_n_by_ppg(wr, 12)
    elite_top6 = top_n_by_ppg(wr, 6)

    summary_top12 = summarize_by_games_bucket(elite_top12)
    summary_top6 = summarize_by_games_bucket(elite_top6)

    summary_top12.to_csv(OUTPUT_DIR / "wr_elite_ppg_top12_by_games_played.csv", index=False)
    summary_top6.to_csv(OUTPUT_DIR / "wr_elite_ppg_top6_by_games_played.csv", index=False)

    thirteen = thirteen_game_list(elite_top12)
    thirteen.to_csv(OUTPUT_DIR / "wr_elite_ppg_top12_thirteen_games_list.csv", index=False)

    print(to_markdown_table(summary_top12, "Primary: Top-12-by-PPG WR seasons, grouped by games played"))
    print()
    print(to_markdown_table(summary_top6, "Sensitivity: Top-6-by-PPG WR seasons, grouped by games played"))
    print()
    print("**Every top-12-PPG WR season with exactly 13 games played**")
    print()
    if len(thirteen) == 0:
        print("(none)")
    else:
        print(thirteen_game_list_markdown(thirteen))

    print(f"\nWrote {OUTPUT_DIR}/wr_elite_ppg_top12_by_games_played.csv")
    print(f"Wrote {OUTPUT_DIR}/wr_elite_ppg_top6_by_games_played.csv")
    print(f"Wrote {OUTPUT_DIR}/wr_elite_ppg_top12_thirteen_games_list.csv")


if __name__ == "__main__":
    main()
