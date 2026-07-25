"""
lib/replacement.py

Shared replacement-level calculators. Promoted verbatim (Stars-by-Value
Commit 5) from research/dataset3/lib/replacement.py -- the logic below
is UNCHANGED from that research version, only relocated out of
research/ so production code (lib/stars_by_value/production.py) can
depend on it without importing from research/. See
research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md section 3 for
the promotion decision.

Roster-preset and flex-allocation assumptions here (ROSTER_PRESETS,
FLEX_ALLOCATION_*) are still explicit, named judgment calls, same as
in the research version -- production.py resolves WHICH preset/
allocation to use via config.py's SBV_REPLACEMENT_ROSTER_PRESET /
SBV_REPLACEMENT_FLEX_ALLOCATION (the settled choice), not by editing
the constants here. This module still holds the actual preset
DEFINITIONS (team count, starters per position, flex slot count)
because config.py currently only stores the settled preset's NAME, not
its shape -- config.py's own SBV_REPLACEMENT_RANK_CUTOFFS is the
already-computed result of applying replacement_rank_cutoff() to the
"12_team_standard" preset below with SBV_REPLACEMENT_FLEX_ALLOCATION;
a regression test in tests/test_production.py proves those two stay
consistent.
"""

import numpy as np
import pandas as pd

# Roster assumption presets -- ALL explicit, none silently assumed.
# "starters" = literal lineup slots per team at that position, NOT
# counting the shared FLEX slot (RB/WR/TE eligible in most common
# formats). Add more presets here rather than hardcoding a new one
# elsewhere if a third format is ever needed.
ROSTER_PRESETS = {
    "10_team_standard": {"teams": 10, "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1}, "flex_slots": 1},
    "12_team_standard": {"teams": 12, "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1}, "flex_slots": 1},
}

# How the shared FLEX slot is presumed to split across RB/WR/TE.
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
    explicit choice, parameterized rather than hardcoded.
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
