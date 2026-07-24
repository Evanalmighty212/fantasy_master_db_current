"""
wr_games_played_impact.py

Research script (NOT part of the production pipeline -- reads the
master database, writes nowhere production output is read from).

Question: how does the number of games a WR actually plays in a
season relate to that season's fantasy output and overall finish?

Population: every WR player-season in the master database with
8-17 games played, 2006-2024 (2025 not yet in nflverse). Uses the
FULL WR population, not just LWI-eligible rows -- games played,
points, and finish are real on-field outcomes independent of
whether that player-season could be matched to an ADP source, so
restricting to LWI-eligible rows would drop real data for no reason
relevant to this question.

Note on the games_played=17 bucket: it is not exclusively the
2021+ 17-game-season population. One 2019 row (a player traded
mid-season who happened to dodge both teams' bye weeks) also has
games_played=17. Real, verified against raw weekly data, not a bug
-- left in rather than silently excluded, but worth knowing before
reading that row's stats as "a full modern season."

"overall finish" below is overall_finish_ppr (rank across ALL
positions that season), matching what was asked for -- not
position_finish_ppr (rank within WR only, i.e. "WR12"/"WR24").
"""

from pathlib import Path

import pandas as pd

MASTER_DB_PATH = Path("data/master/master_historical_db_with_lwi_2006_2025.csv")
OUTPUT_CSV_PATH = Path("research/output/wr_games_played_impact.csv")

GAMES_PLAYED_RANGE = range(17, 7, -1)  # 17 down to 8, inclusive
TOP_N_THRESHOLDS = [12, 20, 24, 36]


def load_wr_seasons() -> pd.DataFrame:
    df = pd.read_csv(MASTER_DB_PATH)
    wr = df[(df["position"] == "WR") & (df["games_played"].isin(GAMES_PLAYED_RANGE))].copy()
    return wr


def summarize_by_games_played(wr: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for gp in GAMES_PLAYED_RANGE:
        season_group = wr[wr["games_played"] == gp]
        n = len(season_group)
        if n == 0:
            continue

        row = {
            "games_played": gp,
            "n_wr_seasons": n,
            "avg_fantasy_points": season_group["fantasy_points_ppr"].mean(),
            "avg_ppg": season_group["ppg_ppr"].mean(),
            "avg_overall_finish": season_group["overall_finish_ppr"].mean(),
            "median_overall_finish": season_group["overall_finish_ppr"].median(),
        }
        for n_top in TOP_N_THRESHOLDS:
            pct = (season_group["overall_finish_ppr"] <= n_top).mean() * 100
            row[f"pct_top_{n_top}_overall"] = pct
        rows.append(row)

    return pd.DataFrame(rows)


def to_markdown_table(summary: pd.DataFrame) -> str:
    headers = [
        "Games Played", "N", "Avg Fantasy Pts", "Avg PPG",
        "Avg Overall Finish", "Median Overall Finish",
        "% Top 12", "% Top 20", "% Top 24", "% Top 36",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for _, r in summary.iterrows():
        lines.append(
            "| {gp} | {n} | {pts:.1f} | {ppg:.2f} | {avgf:.1f} | {medf:.0f} | "
            "{t12:.1f}% | {t20:.1f}% | {t24:.1f}% | {t36:.1f}% |".format(
                gp=int(r["games_played"]),
                n=int(r["n_wr_seasons"]),
                pts=r["avg_fantasy_points"],
                ppg=r["avg_ppg"],
                avgf=r["avg_overall_finish"],
                medf=r["median_overall_finish"],
                t12=r["pct_top_12_overall"],
                t20=r["pct_top_20_overall"],
                t24=r["pct_top_24_overall"],
                t36=r["pct_top_36_overall"],
            )
        )
    return "\n".join(lines)


def main():
    wr = load_wr_seasons()
    summary = summarize_by_games_played(wr)

    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_CSV_PATH, index=False)

    print(to_markdown_table(summary))
    print(f"\nWrote {OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    main()
