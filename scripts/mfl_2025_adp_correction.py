"""
scripts/mfl_2025_adp_correction.py

Builds the canonical 2025 ADP value and the QB/TE sensitivity-ordering
field from a real 2025 MFL AUG15 ADP population. Placed alongside
mfl_client.py/player_matching.py/nflverse_source.py -- this feeds the
whole master DB (both LWI's overall_adp_model and SBV's expected-
production fitting), not an SBV-only adjustment.

REVISED 2026-07 (supersedes this module's original "corrects
overall_adp" design -- see config.py's MFL_2025_* block for the full
decision record):

  A historical FFC rank-to-ADP reconstruction study asked whether
  Method B's quantile-mapped output (mathematically rank-scale, not
  genuine mean-pick ADP -- see below) could be converted onto a
  defensible ADP scale using a historically validated curve. Four
  candidate curves were walk-forward validated against real FFC
  ADP, 2014-2024. None beat the naive "rank IS the ADP" baseline on
  any metric. Per the pre-committed fallback rule, NO correction is
  written into overall_adp:

  - overall_adp = raw MFL AUG15 mean_adp, for ALL FOUR positions
    (QB/RB/WR/TE alike) -- genuine mean-pick units, historically
    comparable, the safest canonical numeric cost. This does NOT
    establish raw MFL is unbiased for QB/TE -- it establishes that no
    tested conversion of the corrected ordering onto an ADP scale is
    more defensible than leaving the units alone.
  - mfl_2025_sensitivity_market_rank = Method B's quantile-mapped
    value, QB/TE only, RB/WR NULL. A RANK, not an ADP -- named
    accordingly (config.validate_mfl_2025_correction_config() rejects
    any field name containing "adp"). Disclosed, auditable, and NEVER
    CONSUMED by any scoring or eligibility path -- see
    TestSensitivityFieldNeverConsumedDownstream in this module's test
    suite for the mechanical guarantee, not just a documentation
    promise.

WHY METHOD B'S OUTPUT IS RANK-SCALE, NOT ADP-SCALE (unchanged from the
prior investigation, restated because it's the reason the sensitivity
field is named as a rank): quantile mapping produces output values
drawn from the TARGET distribution -- here, FFToday's avg_rank, an
average of Sleeper/RTSports/ESPN integer platform RANKS, not real
draft-pick positions. The source's only contribution is a percentile;
MFL's real mean-pick units are discarded the moment percentile_of() is
computed. Correlating well with independent rank sources (the
two-round validation study) is evidence the ORDERING is realistic. It
is not evidence the NUMERIC VALUE is a valid ADP estimate -- conflating
those two claims was the error this revision corrects.

QUANTILE-MAPPING CONSTRUCTION (sensitivity field only):
  Training data: the 71-row (35 QB + 36 TE) frozen calibration file
  data/manual/mfl_2025_qb_te_adp_correction_calibration.csv, promoted
  from the real MFL<->FFToday-consensus overlap this project already
  validated -- not read live from research/ at runtime.

  Fit: within each position, sort the raw MFL mean_adp training values
  ascending (source order statistics) and, independently, sort the
  matched consensus avg_rank training values ascending (target order
  statistics) -- matched by RANK POSITION, not by "this specific
  player's own target." This corrects DISTRIBUTION SHAPE, not a
  per-player correspondence, which is why it applies to any real 2025
  QB/TE, not just the 71 training players.

  Apply: percentile of a raw value v is np.searchsorted(source, v,
  side="left") / (n - 1) -- ENDPOINT-PRESERVING (v2, revised from v1's
  rank/n): a value equal to the source minimum maps to percentile
  exactly 0.0 (target.min()), and a value equal to the source maximum
  maps to percentile exactly 1.0 (target.max()), symmetric at both
  tails. v1 used rank/n, under which only the minimum reached its
  target bound exactly and the maximum landed short of it -- a real,
  avoidable asymmetry, fixed here rather than merely documented (see
  docs/ADP_SOURCE_MATRIX.md's endpoint-behavior review). Percentile is
  still clipped to [0, 1] before interpolating, so a value can never
  fall outside [target.min(), target.max()] regardless of how far
  outside the training range the raw input sits.

  Ties: side="left" searchsorted means genuinely tied raw inputs
  always resolve to the FIRST/lowest matching index -- tied inputs
  deterministically produce IDENTICAL outputs, never an arbitrary
  secondary tiebreak.

  Missing positions: quantile_map() is never called for a position
  outside MFL_2025_CORRECTION_POSITIONS -- the sensitivity field is
  simply NaN for every other position. load_calibration() raises
  loudly if a required position has zero training rows.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (
    MFL_2025_ADP_SOURCE,
    MFL_2025_CORRECTION_CALIBRATION_PATH,
    MFL_2025_CORRECTION_METHOD_NAME,
    MFL_2025_CORRECTION_POSITIONS,
    MFL_2025_SENSITIVITY_RANK_FIELD,
)

REQUIRED_CALIBRATION_COLUMNS = (
    "player_name_mfl_raw",
    "position",
    "mfl_mean_adp",
    "consensus_avg_rank",
    "n_drafts",
)
REQUIRED_INPUT_COLUMNS = ("player_id", "player_name", "position", "mfl_mean_adp")


def load_calibration(path: str = None) -> dict:
    """Loads the frozen quantile-mapping calibration and returns
    {position: (sorted_source_array, sorted_target_array)} for every
    position in MFL_2025_CORRECTION_POSITIONS. Raises loudly if the
    file is missing required columns or a required position has zero
    calibration rows -- never silently skips a position."""
    path = path if path is not None else MFL_2025_CORRECTION_CALIBRATION_PATH
    cal = pd.read_csv(path)

    missing = [c for c in REQUIRED_CALIBRATION_COLUMNS if c not in cal.columns]
    if missing:
        raise ValueError(f"calibration file {path} is missing required columns: {missing}")

    result = {}
    for pos in MFL_2025_CORRECTION_POSITIONS:
        sub = cal[cal["position"] == pos]
        if len(sub) == 0:
            raise ValueError(
                f"calibration file {path} has zero rows for required position {pos!r} -- "
                f"cannot build a quantile map for a position with no training data"
            )
        result[pos] = (
            np.sort(sub["mfl_mean_adp"].to_numpy(dtype=float)),
            np.sort(sub["consensus_avg_rank"].to_numpy(dtype=float)),
        )
    return result


def quantile_map(raw_value: float, source: np.ndarray, target: np.ndarray) -> float:
    """Position-specific quantile mapping, v2 -- endpoint-preserving
    rank/(n-1). See module docstring's "QUANTILE-MAPPING CONSTRUCTION"
    section for the full, reviewed specification."""
    if len(source) != len(target):
        raise ValueError(
            f"source and target calibration arrays must be the same length, "
            f"got {len(source)} and {len(target)}"
        )
    n = len(source)
    if n == 0:
        raise ValueError("cannot quantile-map against an empty calibration array")

    idx = np.searchsorted(source, raw_value, side="left")
    pct = idx / (n - 1) if n > 1 else 0.0
    pct = min(max(pct, 0.0), 1.0)
    return float(np.interp(pct, np.linspace(0.0, 1.0, n), target))


def build_mfl_2025_adp_and_sensitivity(df: pd.DataFrame, calibration: dict = None) -> pd.DataFrame:
    """Builds the canonical 2025 ADP value and the QB/TE sensitivity
    rank from a real 2025 MFL ADP population (any mix of positions).

    Input df must have columns: player_id, player_name, position,
    mfl_mean_adp (the raw MFL value, every row, every position).
    Optionally n_drafts (MFL's own sample-size/selection metadata,
    carried through as provenance if present).

    Adds, to a copy of df:
      - overall_adp: raw MFL mean_adp, UNCHANGED, for every position
        -- this IS the canonical value the rest of the pipeline
        consumes. No correction is applied here, by design (see module
        docstring).
      - overall_adp_mfl_raw: an exact, defensive copy of overall_adp --
        kept distinct so a future, unrelated change to overall_adp
        can never silently lose the original MFL number.
      - mfl_2025_sensitivity_market_rank
        (config.MFL_2025_SENSITIVITY_RANK_FIELD): Method B's
        quantile-mapped RANK value for QB/TE rows, NaN for every other
        position. Never consumed downstream -- see this module's test
        suite's TestSensitivityFieldNeverConsumedDownstream.
      - adp_source: MFL_2025_ADP_SOURCE for every row.

    Does NOT write positional_adp -- recomputing the position-scoped
    rank is the caller's responsibility (mirrors production.py's
    "population scoping is the caller's job" precedent), and not yet
    wired into scripts/04_build_master_dataset.py.
    """
    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"build_mfl_2025_adp_and_sensitivity input is missing required columns: {missing}")
    if df["mfl_mean_adp"].isna().any():
        n = df["mfl_mean_adp"].isna().sum()
        raise ValueError(f"build_mfl_2025_adp_and_sensitivity input has {n} null value(s) in 'mfl_mean_adp'")

    calibration = calibration if calibration is not None else load_calibration()

    out = df.copy()
    out["overall_adp"] = out["mfl_mean_adp"].astype(float)
    out["overall_adp_mfl_raw"] = out["mfl_mean_adp"].astype(float)
    out["adp_source"] = MFL_2025_ADP_SOURCE
    out[MFL_2025_SENSITIVITY_RANK_FIELD] = np.nan

    for pos in MFL_2025_CORRECTION_POSITIONS:
        mask = out["position"] == pos
        if not mask.any():
            continue
        source, target = calibration[pos]
        out.loc[mask, MFL_2025_SENSITIVITY_RANK_FIELD] = out.loc[mask, "mfl_mean_adp"].apply(
            lambda v: quantile_map(v, source, target)
        )

    return out
