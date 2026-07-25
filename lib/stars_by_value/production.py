"""
lib/stars_by_value/production.py

Production composite: AATP, normalized-reliability shrinkage, and the
50/50 composite P. Promoted (Commit 5) from two research sources,
treated as the oracle for this promotion -- see
tests/test_production.py for the row-by-row comparisons against both:
  - research/dataset3/production_weight_and_boundary_calibration.py::build_adp_aware_aatp()
    -- AATP, PPG_AR, PPG_AR_eq (unshrunk). This module's compute_aatp()
    is a direct parameterization of that function: every hardcoded
    constant there (WINDOW=12, the 2021/16/17 season-length cutover,
    POSITIONS, FLEX_ALLOCATION_RB_WR_HEAVY, the "12_team_standard"
    preset) is replaced here by the matching SBV_* config constant,
    confirmed by test to hold the identical value. The formula itself
    is untouched.
  - research/dataset3/normalized_shrinkage_comparison.py::ppg_eq_normalized_shrink()
    -- PPG_AR_eq_shrunk = PPG_AR * (G+k) * (g/(g+k)), k=SBV_SHRINKAGE_K.
    Same formula, k read from config instead of a literal.
  - The 50/50 composite weights (SBV_PRODUCTION_WEIGHT_AATP /
    SBV_PRODUCTION_WEIGHT_PPG_EQ) match production_weight_and_boundary_calibration.py's
    own "50_50" baseline exactly.

POPULATION SCOPING IS DELIBERATELY NOT THIS MODULE'S JOB (a decision
made explicitly before this commit landed, not a silent omission): the
research function bundled row-wise AATP computation together with
population scoping specific to ITS OWN calibration comparison
(games_played >= 1, position in POSITIONS, season BETWEEN 2007 AND
2024). Nothing in STARS_BY_VALUE_METHODOLOGY.md ties the AATP formula
itself to a season ceiling, and section 11's settled 4-step processing
order already assigns temporal/study-scope eligibility to a different,
not-yet-built module (labeling.py, step 1) -- not to production.py.
Hardcoding <=2024 here would silently stop this module from scoring
any future season. So this module trusts its caller for population
scoping and instead VALIDATES its input's STRUCTURAL preconditions
(required columns present and non-null, position values within
SBV_POSITIONS) and RAISES loudly if violated -- it never silently
drops or filters a row itself. games_played is deliberately NOT
required to be >= 1: the formula is well-defined for games_played=0
(a degenerate but mathematically valid input), and whether such rows
belong in the scored population is upstream routing's decision, not
this module's.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    SBV_POSITIONS,
    SBV_PRODUCTION_WEIGHT_AATP,
    SBV_PRODUCTION_WEIGHT_PPG_EQ,
    SBV_REPLACEMENT_FLEX_ALLOCATION,
    SBV_REPLACEMENT_ROSTER_PRESET,
    SBV_REPLACEMENT_WINDOW,
    SBV_SEASON_LENGTH_16_GAME,
    SBV_SEASON_LENGTH_17_GAME,
    SBV_SEASON_LENGTH_ERA_CUTOFF,
    SBV_SHRINKAGE_K,
    SEASONS,
)
from lib.replacement import ROSTER_PRESETS, replacement_level_from_rank, replacement_rank_cutoff

# Mirrors scripts/05_calculate_metrics.py's own WEEKLY_PATH pattern
# (SEASONS[0]/SEASONS[-1], not a literal year range) -- this is the
# same weekly-participation file the existing LWI pipeline already
# produces and consumes, not a new SBV-specific artifact.
WEEKLY_PATH = Path(f"data/raw/nflverse/weekly_results_ppr_{SEASONS[0]}_{SEASONS[-1]}.csv")

REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "position",
    "games_played",
    "fantasy_points_ppr",
    "ppg_ppr",
    "position_finish_ppr",
    "adp_matched",
)
_REQUIRED_NUMERIC_COLUMNS = ("season", "games_played", "fantasy_points_ppr", "ppg_ppr", "position_finish_ppr")


def season_length(season: int) -> int:
    """17 from SBV_SEASON_LENGTH_ERA_CUTOFF onward, 16 before --
    verified historical fact (not derived from max(games_played)),
    same values as the research version's verified_season_length()."""
    return SBV_SEASON_LENGTH_17_GAME if season >= SBV_SEASON_LENGTH_ERA_CUTOFF else SBV_SEASON_LENGTH_16_GAME


def _validate_input(df: pd.DataFrame) -> None:
    """Fails loudly on structurally invalid input rather than silently
    dropping rows -- see module docstring. Population-scoping
    decisions (season range, games_played >= 1) are deliberately NOT
    checked here."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"production.py input is missing required columns: {missing}")

    for col in _REQUIRED_NUMERIC_COLUMNS:
        if df[col].isna().any():
            n = df[col].isna().sum()
            raise ValueError(f"production.py input has {n} null value(s) in required column '{col}'")

    bad_positions = set(df["position"].unique()) - set(SBV_POSITIONS)
    if bad_positions:
        raise ValueError(
            f"production.py input contains position(s) outside SBV_POSITIONS: {sorted(bad_positions)} "
            f"-- population scoping (which positions to score) is the caller's responsibility, not "
            f"this module's; filter before calling, don't rely on this function to drop them."
        )

    if df["adp_matched"].dtype != bool:
        raise ValueError(
            f"production.py input's 'adp_matched' column must be boolean dtype, got {df['adp_matched'].dtype}"
        )


def compute_aatp(df: pd.DataFrame, weekly_path: Path = None) -> pd.DataFrame:
    """Adds G, games_played_capped, first_active_week, eligible_games,
    games_missed_eligible, replacement_ppg, AATP, PPG_AR, PPG_AR_eq to
    a copy of df. Direct parameterization of build_adp_aware_aatp()'s
    computation (not its population-scoping) -- see module docstring."""
    _validate_input(df)
    out = df.copy()

    out["G"] = out["season"].apply(season_length)
    out["games_played_capped"] = out[["games_played", "G"]].min(axis=1)

    weekly_path = Path(weekly_path) if weekly_path is not None else WEEKLY_PATH
    weekly = pd.read_csv(weekly_path, usecols=["season", "player_id", "week"])
    first_week = weekly.groupby(["season", "player_id"])["week"].min().rename("first_active_week")
    out = out.merge(first_week, on=["season", "player_id"], how="left")

    # meaningful-ADP: full season eligible. Undrafted: eligible only from first_active_week onward.
    eligible_games = np.where(
        out["adp_matched"],
        out["G"],
        (out["G"] - out["first_active_week"] + 1).clip(lower=out["games_played_capped"]),
    )
    # fallback for rows with no weekly match found (rare) -- treat as full season, disclosed
    eligible_games = np.where(out["first_active_week"].isna(), out["G"], eligible_games)
    out["eligible_games"] = eligible_games
    out["games_missed_eligible"] = (out["eligible_games"] - out["games_played_capped"]).clip(lower=0)

    preset = ROSTER_PRESETS[SBV_REPLACEMENT_ROSTER_PRESET]
    cutoffs = {pos: replacement_rank_cutoff(preset, pos, SBV_REPLACEMENT_FLEX_ALLOCATION) for pos in SBV_POSITIONS}
    out["replacement_ppg"] = replacement_level_from_rank(
        out, value_col="ppg_ppr", rank_col="position_finish_ppr", cutoff_by_position=cutoffs, window=SBV_REPLACEMENT_WINDOW,
    )

    out["AATP"] = out["fantasy_points_ppr"] + out["replacement_ppg"] * out["games_missed_eligible"]
    out["PPG_AR"] = out["ppg_ppr"] - out["replacement_ppg"]
    out["PPG_AR_eq"] = out["PPG_AR"] * out["G"]
    return out


def compute_shrunk_ppg_eq(df: pd.DataFrame) -> pd.Series:
    """PPG_AR_eq_shrunk = PPG_AR * (G+k) * g/(g+k), k=SBV_SHRINKAGE_K --
    identical formula to normalized_shrinkage_comparison.py's
    ppg_eq_normalized_shrink(), k read from config instead of a
    literal. Requires PPG_AR, games_played_capped, G already present
    (i.e. called after compute_aatp())."""
    k = SBV_SHRINKAGE_K
    g = df["games_played_capped"]
    G = df["G"]
    return df["PPG_AR"] * (G + k) * (g / (g + k))


def compute_production_composite(df: pd.DataFrame) -> pd.Series:
    """P = SBV_PRODUCTION_WEIGHT_AATP * AATP + SBV_PRODUCTION_WEIGHT_PPG_EQ * PPG_AR_eq_shrunk
    (currently 0.5/0.5). Requires AATP and PPG_AR_eq_shrunk already
    present."""
    return SBV_PRODUCTION_WEIGHT_AATP * df["AATP"] + SBV_PRODUCTION_WEIGHT_PPG_EQ * df["PPG_AR_eq_shrunk"]


def compute_production(df: pd.DataFrame, weekly_path: Path = None) -> pd.DataFrame:
    """Full pipeline: AATP/PPG_AR/PPG_AR_eq, PPG_AR_eq_shrunk, and the
    final production composite P, added to a copy of df."""
    out = compute_aatp(df, weekly_path=weekly_path)
    out["PPG_AR_eq_shrunk"] = compute_shrunk_ppg_eq(out)
    out["P"] = compute_production_composite(out)
    return out
