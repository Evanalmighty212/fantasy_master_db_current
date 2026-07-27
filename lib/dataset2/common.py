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
