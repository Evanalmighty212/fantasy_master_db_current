"""
06_generate_rankings.py

Turns the scored master database (05_calculate_metrics.py's output)
into actual ranking/leaderboard outputs -- the "something a person
reads" step, not just more raw data.

Scope rule, per the component availability policy in
docs/METRIC_SPECIFICATION.md: rankings are built ONLY from rows with
lwi_component_coverage == complete_6_of_6. An incomplete-component row
is a different measurement than a complete one and must not be ranked
alongside them, even though today (all components built) this filter
is a no-op -- it's here so it stays correct if that ever changes.

Outputs (all under data/exports/rankings/):
  all_time_lwi_rankings.csv       -- every eligible player-season, ranked
  season_champions.csv            -- the #1 LWI score per season (the
                                      literal "league winner" for that year)
  position_leaderboards.csv       -- top 25 all-time per position
  biggest_adp_values.csv          -- top 10 per season by ADP-value component
                                      (biggest outperformance of draft cost)
  biggest_adp_busts.csv           -- bottom 10 per season by ADP-value component
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import SEASONS

MASTER_WITH_LWI_PATH = Path(
    f"data/master/master_historical_db_with_lwi_{SEASONS[0]}_{SEASONS[-1]}.csv"
)
MASTER_PATH = Path(f"data/master/master_historical_db_{SEASONS[0]}_{SEASONS[-1]}.csv")
OUT_DIR = Path("data/exports/rankings")

TOP_N_LEADERBOARD = 25
TOP_N_ADP_VALUE = 10


def load_rankable_rows():
    if not MASTER_WITH_LWI_PATH.exists():
        raise FileNotFoundError(
            f"{MASTER_WITH_LWI_PATH} not found -- run 05_calculate_metrics.py first."
        )
    df = pd.read_csv(MASTER_WITH_LWI_PATH)

    # Per the component availability policy: only complete scores are
    # ranked. A row with an incomplete component set is a genuinely
    # different measurement, not a lesser version of the same one --
    # mixing them into one leaderboard would silently misrepresent both.
    before = len(df)
    rankable = df[
        (df["lwi_eligibility_flag"] == "eligible")
        & (df["lwi_component_coverage"] == "complete_6_of_6")
    ].copy()
    print(f"Loaded {before} total rows -> {len(rankable)} rankable "
          f"(eligible + complete_6_of_6) rows")
    return rankable


def build_all_time_rankings(df):
    ranked = df.sort_values("lwi_score", ascending=False).reset_index(drop=True)
    ranked.insert(0, "all_time_rank", ranked.index + 1)
    cols = ["all_time_rank", "season", "player_name", "position", "team",
            "lwi_score", "overall_adp", "overall_finish_ppr",
            "fantasy_points_ppr", "ppg_ppr"]
    return ranked[cols]


def build_season_champions(df):
    """The literal 'League Winner' per season -- the #1 LWI score each
    year. This is arguably the single most direct answer to what this
    whole project set out to measure."""
    idx = df.groupby("season")["lwi_score"].idxmax()
    champions = df.loc[idx].sort_values("season")
    cols = ["season", "player_name", "position", "team", "lwi_score",
            "overall_adp", "overall_finish_ppr", "fantasy_points_ppr"]
    return champions[cols]


def build_position_leaderboards(df):
    rows = []
    for position in ["QB", "RB", "WR", "TE"]:
        pos_df = df[df["position"] == position].sort_values(
            "lwi_score", ascending=False
        ).head(TOP_N_LEADERBOARD)
        pos_df = pos_df.copy()
        pos_df.insert(0, "position_rank", range(1, len(pos_df) + 1))
        rows.append(pos_df)
    combined = pd.concat(rows, ignore_index=True)
    cols = ["position", "position_rank", "season", "player_name", "team",
            "lwi_score", "overall_adp", "overall_finish_ppr"]
    return combined[cols]


def build_adp_value_extremes(df):
    """Biggest value picks and biggest busts per season, by the ADP
    Value component specifically (not overall LWI) -- this answers a
    narrower, different question than the LWI leaderboard: not "who
    had the best season overall" but "who most beat or missed their
    specific draft cost."""
    value_rows, bust_rows = [], []
    for season, group in df.groupby("season"):
        top_value = group.sort_values("adp_value_raw", ascending=False).head(TOP_N_ADP_VALUE)
        top_bust = group.sort_values("adp_value_raw", ascending=True).head(TOP_N_ADP_VALUE)
        value_rows.append(top_value)
        bust_rows.append(top_bust)

    cols = ["season", "player_name", "position", "team", "overall_adp",
            "overall_finish_ppr", "adp_value_raw", "fantasy_points_ppr", "lwi_score"]
    values = pd.concat(value_rows, ignore_index=True).sort_values(
        ["season", "adp_value_raw"], ascending=[True, False]
    )[cols]
    busts = pd.concat(bust_rows, ignore_index=True).sort_values(
        ["season", "adp_value_raw"], ascending=[True, True]
    )[cols]
    return values, busts


def build_no_adp_breakout_candidates():
    """
    Dataset 5: "Historical No-ADP Breakout Candidates" -- players who
    are currently verification_status='unresolved' (no ADP match, and
    NOT yet researched/confirmed as genuinely undrafted vs. simply
    missing from our current source's depth) but who had a genuinely
    strong statistical season worth investigating.

    This is a DISCOVERY/research list, not a scored ranking -- these
    players are explicitly excluded from LWI until someone verifies
    their real draft status (see data/manual/adp_status_verification.csv
    and config.py's LWI_GLOBAL_MAX_OVERALL_ADP documentation for the
    full reasoning). The threshold here (top 24 at position, 8+ games)
    is deliberately generous -- better to surface a few candidates that
    turn out to have been drafted-but-missed than to silently miss a
    real James Robinson/Victor Cruz/Puka Nacua-type story.
    """
    master = pd.read_csv(MASTER_PATH)
    unresolved = master[
        (master["verification_status"] == "unresolved")
        & (master["games_played"] >= 8)
        & (master["position_finish_ppr"] <= 24)
    ].copy()
    unresolved = unresolved.sort_values(["season", "position", "position_finish_ppr"])
    cols = ["season", "player_name", "position", "team", "games_played",
            "fantasy_points_ppr", "ppg_ppr", "overall_finish_ppr", "position_finish_ppr"]
    return unresolved[cols]


def generate_rankings():
    df = load_rankable_rows()
    if len(df) == 0:
        raise ValueError(
            "No rankable rows found (0 rows are both eligible and "
            "complete_6_of_6) -- check that 05_calculate_metrics.py ran "
            "correctly before treating this as a real empty result."
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building all-time rankings...")
    all_time = build_all_time_rankings(df)
    all_time.to_csv(OUT_DIR / "all_time_lwi_rankings.csv", index=False)
    print(f"  {len(all_time)} rows -> {OUT_DIR / 'all_time_lwi_rankings.csv'}")

    print("Building season champions (the literal 'league winner' per year)...")
    champions = build_season_champions(df)
    champions.to_csv(OUT_DIR / "season_champions.csv", index=False)
    print(f"  {len(champions)} seasons -> {OUT_DIR / 'season_champions.csv'}")

    print("Building position leaderboards...")
    leaderboards = build_position_leaderboards(df)
    leaderboards.to_csv(OUT_DIR / "position_leaderboards.csv", index=False)
    print(f"  {len(leaderboards)} rows -> {OUT_DIR / 'position_leaderboards.csv'}")

    print("Building ADP value extremes (biggest values and busts)...")
    values, busts = build_adp_value_extremes(df)
    values.to_csv(OUT_DIR / "biggest_adp_values.csv", index=False)
    busts.to_csv(OUT_DIR / "biggest_adp_busts.csv", index=False)
    print(f"  {len(values)} rows -> {OUT_DIR / 'biggest_adp_values.csv'}")
    print(f"  {len(busts)} rows -> {OUT_DIR / 'biggest_adp_busts.csv'}")

    print("Building Dataset 5 -- No-ADP Breakout Candidates (research list, not scored)...")
    no_adp_candidates = build_no_adp_breakout_candidates()
    no_adp_candidates.to_csv(OUT_DIR / "no_adp_breakout_candidates.csv", index=False)
    print(f"  {len(no_adp_candidates)} rows -> {OUT_DIR / 'no_adp_breakout_candidates.csv'}")
    print(f"  (unresolved players with a top-24 positional finish -- research "
          f"candidates for data/manual/adp_status_verification.csv, not yet "
          f"scored in LWI)")

    print(f"\nDone. All ranking outputs written to {OUT_DIR}/")
    return {
        "all_time": all_time,
        "champions": champions,
        "leaderboards": leaderboards,
        "values": values,
        "busts": busts,
        "no_adp_candidates": no_adp_candidates,
    }


def main():
    generate_rankings()


if __name__ == "__main__":
    main()
