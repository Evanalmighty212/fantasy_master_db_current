"""
Shared replacement-level calculators for Dataset 3 research.

EXPLORATORY ONLY -- computes plausible replacement-level production
under STATED roster assumptions. Does not select a final replacement
definition for Dataset 3 or for LWI; every function takes its
assumptions as explicit parameters so different scenarios can be
compared side by side rather than one being silently baked in as the
default. This mirrors this project's existing disclosure standard for
LWI's own replacement thresholds (config.py's LWI_REPLACEMENT_RANK_THRESHOLDS
comment: "a CONCEPTUAL choice, not an empirical finding") -- same
honesty applies here, doubly so since nothing here is confirmed at all
yet.
"""

import numpy as np
import pandas as pd

# Roster assumption presets -- ALL explicit, none silently assumed.
# "starters" = literal lineup slots per team at that position, NOT
# counting the shared FLEX slot (RB/WR/TE eligible in most common
# formats). These are the two team counts the task asked for; add
# more presets here rather than hardcoding a new one elsewhere if a
# third format is ever needed.
ROSTER_PRESETS = {
    "10_team_standard": {"teams": 10, "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1}, "flex_slots": 1},
    "12_team_standard": {"teams": 12, "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1}, "flex_slots": 1},
}

# How the shared FLEX slot is presumed to split across RB/WR/TE.
# ILLUSTRATIVE, not measured -- a real, labeled judgment call, not an
# empirical finding.
FLEX_ALLOCATION_NONE = {"RB": 0.0, "WR": 0.0, "TE": 0.0}
FLEX_ALLOCATION_EVEN = {"RB": 1 / 3, "WR": 1 / 3, "TE": 1 / 3}
FLEX_ALLOCATION_RB_WR_HEAVY = {"RB": 0.45, "WR": 0.45, "TE": 0.10}


def replacement_rank_cutoff(preset: dict, position: str, flex_allocation: dict) -> int:
    """
    The starter-count RANK CUTOFF implied by a roster preset and a
    flex-allocation scenario -- e.g. "12-team standard, flex excluded,
    RB" = 2*12 = 24. A rank cutoff, not a production number by itself
    -- see replacement_level_from_rank for that. Rounded to the
    nearest whole rank (fractional flex allocations produce
    fractional cutoffs otherwise, which isn't a meaningful rank).
    """
    teams = preset["teams"]
    starters = preset["starters"].get(position, 0)
    cutoff = starters * teams
    cutoff += flex_allocation.get(position, 0.0) * preset["flex_slots"] * teams
    return int(round(cutoff))


def replacement_level_from_rank(
    df: pd.DataFrame,
    value_col: str,
    rank_col: str,
    cutoff_by_position: dict,
    window: int = 0,
    position_col: str = "position",
    season_col: str = "season",
) -> pd.Series:
    """
    Median of value_col among players ranked [cutoff, cutoff+window]
    at that position+season, per the given cutoff_by_position mapping.
    window=0 means "as close to exactly the cutoff rank as the real
    discrete rank data allows" rather than a window median -- caller's
    explicit choice, matching LWI's own compute_replacement_level()
    pattern (05_calculate_metrics.py) but parameterized rather than
    hardcoded, since no replacement definition is being selected here.
    """
    lookup = {}
    for (season, position), group in df.groupby([season_col, position_col]):
        cutoff = cutoff_by_position.get(position)
        if cutoff is None:
            lookup[(season, position)] = np.nan
            continue
        lo, hi = cutoff, cutoff + window
        windowed = group[(group[rank_col] >= lo) & (group[rank_col] <= hi)]
        lookup[(season, position)] = windowed[value_col].median() if len(windowed) > 0 else np.nan
    return df.apply(lambda r: lookup.get((r[season_col], r[position_col])), axis=1)
