"""
lib/dataset2/common.py

Shared utilities used by every Dataset 2 trait-construction module --
extracted 2026-07 when lag_join()'s logic was about to be duplicated a
second time (prior_finish_traits.py needing exactly what
prior_season_traits.py already had) and validate_columns() a fourth
time. Not a speculative abstraction -- real, exact duplication that
had already happened once and was about to happen again.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import SBV_SEASON_LENGTH_16_GAME, SBV_SEASON_LENGTH_17_GAME, SBV_SEASON_LENGTH_ERA_CUTOFF


def season_length(season: int) -> int:
    """Real NFL season length by era -- 17 from
    config.SBV_SEASON_LENGTH_ERA_CUTOFF onward, 16 before. Reuses the
    SBV_* config constants directly (this is the same verified
    real-world fact SBV's own lib/stars_by_value/production.py::season_length()
    encodes, not a Dataset-2-specific number) rather than duplicating
    the era-cutoff literal in a second place."""
    return SBV_SEASON_LENGTH_17_GAME if season >= SBV_SEASON_LENGTH_ERA_CUTOFF else SBV_SEASON_LENGTH_16_GAME


def validate_columns(df: pd.DataFrame, required, label: str) -> None:
    """Fail-loud required-column check, shared by every Dataset 2
    trait/analysis module's public entry point."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def week1_kickoff_by_team(schedule_df: pd.DataFrame, season: int) -> dict:
    """Real per-team Week-1 REG-season kickoff date for `season`, keyed
    by team code -- same convention already proven in
    lib.stars_by_value.acquisition_cost.apply_rookie_qb_depth_chart_correction()
    (a real per-team date, not a shared project-wide approximation like
    "Sept 1"). A team with no Week-1 REG game in `schedule_df` for this
    season is simply absent from the returned dict -- the caller treats
    that as "kickoff date unknown" (null downstream), not an error.
    Extracted 2026-07 when a second Dataset 2 module
    (depth_chart_traits.py) needed exactly this logic, after
    experience_age_draft.py already had it."""
    week1 = schedule_df[
        (schedule_df["season"] == season) & (schedule_df["game_type"] == "REG") & (schedule_df["week"] == 1)
    ]
    kickoff = {}
    for _, row in week1.iterrows():
        gameday = pd.to_datetime(row["gameday"])
        kickoff[row["home_team"]] = gameday
        kickoff[row["away_team"]] = gameday
    return kickoff


def kickoff_lookup_table(schedule_df: pd.DataFrame, seasons) -> pd.DataFrame:
    """season/team/kickoff_date rows for every season in `seasons`,
    built by calling week1_kickoff_by_team() once per season (not once
    per population row -- that would recompute the same per-season
    dict thousands of times)."""
    frames = []
    for season in sorted(set(seasons)):
        kickoff = week1_kickoff_by_team(schedule_df, season)
        if kickoff:
            frames.append(
                pd.DataFrame({"season": season, "team": list(kickoff.keys()), "_kickoff_date": list(kickoff.values())})
            )
    if not frames:
        return pd.DataFrame(columns=["season", "team", "_kickoff_date"])
    return pd.concat(frames, ignore_index=True)


def lag_join(df: pd.DataFrame, value_col: str, lag: int) -> pd.Series:
    """Value of `value_col` for this player at `season - lag`, aligned
    to df's row order via an explicit key-based merge (never positional
    alignment -- two independently-deduplicated frames are not
    guaranteed to share row order). `df` must have one row per
    (season, player_id) and must include `season`, `player_id`, and
    `value_col`. A player with no row at season-lag (rookie, or a
    genuine gap in the population) gets NaN -- never zero-filled or
    guessed."""
    lookup = df[["season", "player_id", value_col]].copy()
    lookup["season"] = lookup["season"] + lag
    lookup = lookup.rename(columns={value_col: "_lagged_value"})
    merged = df[["season", "player_id"]].merge(lookup, on=["season", "player_id"], how="left")
    return merged["_lagged_value"]


def within_group_zscore(df: pd.DataFrame, value_col: str, group_col: str) -> pd.Series:
    """How many standard deviations this row's value_col sits from the
    mean for its group_col, computed over the population passed in.
    NaN input propagates to NaN output -- never imputed. A group with
    zero variance (e.g. a single-row group) produces NaN for that
    group rather than a divide-by-zero, which is disclosed
    missingness, not a bug. Extracted 2026-07 when a second Dataset 2
    module (fragility_traits.py) needed exactly this position-adjusted
    pattern, after experience_age_draft.py already had it."""
    grouped = df.groupby(group_col)[value_col]
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0, float("nan"))
    return (df[value_col] - mean) / std
