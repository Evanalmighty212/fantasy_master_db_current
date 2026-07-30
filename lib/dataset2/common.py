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
    the era-cutoff literal in a second place.

    THIS IS REAL GAMES PLAYED, NOT THE MAXIMUM REAL REG WEEK NUMBER --
    see real_reg_week_slots() below. Using this function's return value
    directly as a max-week bound is a real, previously-committed bug
    (lib/dataset2/partial_season_traits.py, found and fixed 2026-07,
    see research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md):
    real REG week NUMBERS run 1..season_length(season)+1, one higher
    than the games-played count, because every team's real bye week
    consumes a week number without being a played game (verified
    directly: real 2015 weeks run 1-17 despite season_length(2015)==16;
    real 2021 weeks run 1-18 despite season_length(2021)==17)."""
    return SBV_SEASON_LENGTH_17_GAME if season >= SBV_SEASON_LENGTH_ERA_CUTOFF else SBV_SEASON_LENGTH_16_GAME


def real_reg_week_slots(season: int) -> int:
    """The real maximum REG week NUMBER for `season` -- season_length(season)
    + 1, accounting for the one week-number slot every team's real bye
    consumes without a played game. THE SHARED, CANONICAL way to bound
    or classify a real `week` column anywhere in Dataset 2 -- e.g. "is
    this week real postseason" (`week > real_reg_week_slots(season)`,
    the exact rule already proven in participation_traits.py's real
    2016/2022 week-range checks) or "what's the real week-number
    ceiling for this season." Do NOT use season_length() directly for
    this -- see that function's own docstring for the real bug this
    helper exists to prevent from recurring in a second module."""
    return season_length(season) + 1


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
    dict thousands of times). Real, found bug fixed 2026-07: when
    `schedule_df` has zero real matching rows for every season
    requested (e.g. a genuinely empty `schedule_df` -- a real,
    disclosed environment gap, see
    research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md), the old
    empty-case `pd.DataFrame(columns=[...])` left `_kickoff_date` as
    object dtype with zero rows; merging that onto a real, non-empty
    population produced a NaN column that was NOT datetime64, and
    `experience_age_draft.py`'s own `_kickoff_date - birth_date`
    subtraction crashed with a real TypeError instead of producing the
    correct, real all-null `age_at_week1_years` result. Explicit dtypes
    below fix this without changing any real, non-empty-schedule
    behavior."""
    frames = []
    for season in sorted(set(seasons)):
        kickoff = week1_kickoff_by_team(schedule_df, season)
        if kickoff:
            frames.append(
                pd.DataFrame({"season": season, "team": list(kickoff.keys()), "_kickoff_date": list(kickoff.values())})
            )
    if not frames:
        return pd.DataFrame(
            {
                "season": pd.Series(dtype="int64"),
                "team": pd.Series(dtype="object"),
                "_kickoff_date": pd.Series(dtype="datetime64[ns]"),
            }
        )
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


def build_team_game_index(weekly_all_positions: pd.DataFrame) -> pd.DataFrame:
    """Real (season, team, week) -> chronological `team_game_index`
    (1..G) and `team_total_games` (G), derived from the real REG weeks
    where AT LEAST ONE player recorded a real weekly row for that team
    -- no separate schedule fetch needed. `weekly_all_positions` must be
    the FULL weekly file (every position, not just skill positions --
    restricting first risks missing a real team-week, the same real
    risk already documented in Source A's own team-week-denominator
    audit) with at least `season`, `week`, `team`, `season_type`
    columns; filtered to REG internally.

    Verified directly against real data before this was written: a
    team's real REG week COUNT from this method exactly matches
    season_length(season) for every real team-season checked (real
    2015: 16; real 2021: 17) -- a real bye week correctly produces a
    gap in the raw week numbers (e.g. real 2015 New England: weeks
    1,2,3,5,6,...,17 -- week 4 is the real bye, absent, not a zero-row
    placeholder), which ranking the existing weeks 1..G correctly
    compresses out. This is the real, general building block for every
    Dataset 2 team-game-sequence window (final-N team games,
    team-game-index half-split) -- see partial_season_traits.py.
    """
    validate_columns(weekly_all_positions, ("season", "week", "team", "season_type"), "weekly_all_positions")

    reg = weekly_all_positions[weekly_all_positions["season_type"] == "REG"]
    team_weeks = reg[["season", "team", "week"]].drop_duplicates().sort_values(["season", "team", "week"])

    team_weeks["team_game_index"] = team_weeks.groupby(["season", "team"]).cumcount() + 1
    team_weeks["team_total_games"] = team_weeks.groupby(["season", "team"])["team_game_index"].transform("max")

    return team_weeks.reset_index(drop=True)


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
