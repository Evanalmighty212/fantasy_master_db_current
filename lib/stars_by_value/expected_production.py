"""
lib/stars_by_value/expected_production.py

Expected-AATP-by-round fitting: honest expanding windows, QB/RB
positional offsets, QB-only recency weighting. Promoted (Commit 6)
from the chronological research chain in research/dataset3/ -- see
this module's promotion notes below for exactly which script supplies
which piece, since (confirmed by reading the full chain, not assumed)
no single research script implements the complete settled design in
one place.

ORACLE CHAIN (read in full, chronological, each building on the last):
  1. expected_production_by_round_investigation.py -- descriptive only,
     no fitting. Supplies the ROUND MAPPING: adp_round(adp, teams=12) =
     ceil(adp/teams), reused unchanged by every later script in the
     chain (imported from expected_production_tables.py originally).
  2. expected_production_position_adjustment_investigation.py --
     first position-offset test, LOSO (leave-one-season-out) validated.
     LOSO leaks future seasons into fitting and is NOT what production
     uses -- superseded on this point by script 5 below.
  3. expected_production_position_adjustment_residual_diagnostics.py --
     compares constant 4-position offset vs. QB-only vs. QB_RB, still
     under LOSO. This is where QB_RB emerges as a candidate, not yet
     the final selection (still LOSO, still raw fantasy_points_ppr).
  4. expected_production_replacement_adjusted_retest.py -- re-tests
     the above against points_above_replacement (NOT the eventual AATP
     target) using a NEW expanding-window walk_forward() (first
     appearance of the honest, non-leaking fitting procedure this
     module promotes). Confirms the offset/recency findings aren't an
     artifact of the raw-points target specifically -- per this
     project's own documented principle that structural findings must
     be re-tested under a new target, never assumed to transfer.
  5. expected_production_temporal_validation.py -- confirms LOSO
     specifically leaks (quantifies it) and settles expanding-window
     walk-forward as the honest replacement, still on raw
     fantasy_points_ppr, QB_RB offset, comparing equal vs. recency
     weighting APPLIED UNIFORMLY to both QB and RB together.
  6. aatp_round_refit_and_short_season_calibration.py -- THE FINAL
     oracle for the actual production target: reuses
     production_weight_and_boundary_calibration.py's build_adp_aware_aatp()
     (AATP, not raw points or PAR) and re-confirms, under this final
     construction: (a) use ALL trustworthy ADP observations, capping
     at 200 tested and rejected (Task 1); (b) the exact expanding-window
     fit_round_means()/fit_offsets()/walk_forward() this module's
     _fit_round_means()/_fit_offsets() are a direct parameterization
     of (Task 3); (c) QB_RB remains the selected offset variant,
     reconfirmed statistically indistinguishable from all_four; (d)
     equal-vs-recency comparison BROKEN DOWN BY POSITION SCOPE --
     this is the table (aatp_equal_vs_recency.csv) that reveals QB
     benefits from recency (this project's methodology doc cites
     MAE 44.60->40.51, p<0.0001) while RB/WR do not (p=0.11, p=0.98).

THE ONE THING NO SINGLE SCRIPT DOES, SYNTHESIZED HERE: script 6 runs
walk_forward() ONCE with scheme="equal" and ONCE with scheme="recency"
-- each run applies its scheme UNIFORMLY to the pooled round-mean fit
AND to every position's offset fit. It never runs a SINGLE combined fit
where QB's baseline+offset are recency-weighted while RB/WR/TE's are
simultaneously equal-weighted -- that specific combined production
behavior is a direct, mechanical reading of script 6's own per-position
MAE comparison (its whole point is to show which POSITIONS benefit),
not an independent invention: fit_expected_production() below runs
_fit_round_means()/_fit_offsets() under BOTH schemes (exactly script
6's own functions, parameterized instead of hardcoded), then for each
position independently selects the recency-scheme pipeline's numbers
if that position is in SBV_RECENCY_POSITIONS, else the equal-scheme
pipeline's -- i.e., "use recency's answer for QB rows, equal's answer
for everyone else," which is exactly what script 6's own comparison
measures and validates, just not previously wired into one function.

NO CAPPING, NO SIMPLIFICATION: per Task 1, capping the fitting
population at adp_rank<=200 was tested and rejected (starves round
14/15 to as few as 3 training rows in some folds, no accuracy
benefit) -- this module never caps; the caller passes ALL trustworthy
ADP-matched rows.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    SBV_MIN_PRIOR_SEASONS,
    SBV_POSITIONS,
    SBV_RECENCY_HALF_LIFE_YEARS,
    SBV_RECENCY_POSITIONS,
    SBV_ROUND_OFFSET_POSITIONS,
    SBV_VERSION,
    TEAMS,
)

REQUIRED_COLUMNS = ("season", "position", "adp_round", "AATP")

LOOKUP_SCHEMA_COLUMNS = (
    "prediction_season",
    "position",
    "draft_round",
    "expected_production",
    "positional_offset_applied",
    "recency_weighted",
    "half_life_years",
    "sample_size",
    "sbv_version",
    "fit_timestamp",
)

LOOKUP_KEY_COLUMNS = ("prediction_season", "position", "draft_round")


def adp_round(adp, teams: int = TEAMS):
    """ceil(adp/teams) -- identical to expected_production_tables.py's
    adp_round(), reused unchanged across every script in the oracle
    chain. teams defaults to config.TEAMS (project-wide, currently 12),
    not re-hardcoded."""
    if pd.isna(adp):
        return None
    return int(np.ceil(adp / teams))


def _season_weight(season: int, asof_year: int, scheme: str, half_life_years: float) -> float:
    """Identical to script 6's season_weight() -- age=(asof_year-1)-season
    (0 = most recent prior season), half-life decay for "recency"."""
    if scheme == "equal":
        return 1.0
    if scheme == "recency":
        age = (asof_year - 1) - season
        return 0.5 ** (age / half_life_years)
    raise ValueError(f"unknown weighting scheme: {scheme!r}")


def _validate_input(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"expected_production.py input is missing required columns: {missing}")
    for col in ("season", "AATP"):
        if df[col].isna().any():
            raise ValueError(f"expected_production.py input has null values in required column '{col}'")
    if df["adp_round"].isna().any():
        raise ValueError(
            "expected_production.py input has null adp_round values -- caller must "
            "compute adp_round (this module's adp_round()) for every row before fitting"
        )
    bad_positions = set(df["position"].unique()) - set(SBV_POSITIONS)
    if bad_positions:
        raise ValueError(
            f"expected_production.py input contains position(s) outside SBV_POSITIONS: "
            f"{sorted(bad_positions)}"
        )


def _fit_round_means(train: pd.DataFrame, asof_year: int, scheme: str, half_life_years: float) -> dict:
    """Direct parameterization of script 6's fit_round_means()."""
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: _season_weight(s, asof_year, scheme, half_life_years))
    return {int(r): np.average(g["AATP"], weights=g["w"]) for r, g in t.groupby("adp_round")}


def _fit_offsets(
    train: pd.DataFrame, round_means: dict, asof_year: int, scheme: str, half_life_years: float, positions,
) -> dict:
    """Direct parameterization of script 6's fit_offsets()."""
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: _season_weight(s, asof_year, scheme, half_life_years))
    t["pooled_pred"] = t["adp_round"].map(round_means)
    t["residual"] = t["AATP"] - t["pooled_pred"]
    offsets = {}
    for pos in positions:
        sub = t[(t["position"] == pos) & t["residual"].notna()]
        offsets[pos] = np.average(sub["residual"], weights=sub["w"]) if len(sub) else np.nan
    return offsets


def _sample_size(train: pd.DataFrame, rnd: int, position: str) -> int:
    """Real training-row count behind this specific (round, position)
    cell -- NOT the pooled round mean's total row count across all
    positions. Not filtered on a minimum-n threshold -- low-n cells are
    stored and flagged via this column, never silently excluded (per
    Task 3's round-15 finding: reported, not dropped)."""
    return int(((train["adp_round"] == rnd) & (train["position"] == position)).sum())


def fit_expected_production(
    matched: pd.DataFrame,
    min_prior_seasons: int = SBV_MIN_PRIOR_SEASONS,
    offset_positions=SBV_ROUND_OFFSET_POSITIONS,
    recency_positions=SBV_RECENCY_POSITIONS,
    half_life_years: float = SBV_RECENCY_HALF_LIFE_YEARS,
) -> pd.DataFrame:
    """
    Fits E_P(prediction_season, position, draft_round) for every
    prediction_season with at least min_prior_seasons of strictly-prior
    training data, honest expanding window (never leave-one-season-out).
    `matched` must already be the ADP-matched, AATP-computed,
    adp_round-assigned population -- this function does not scope
    population (which rows count as "trustworthy ADP") itself, matching
    production.py's own "caller scopes population, this module just
    computes" convention. Requirement #3 (no draft-depth cap) is
    satisfied by NOT filtering here -- whatever `matched` contains is
    used in full.

    For each position: uses the "recency"-scheme round-mean+offset
    pipeline if that position is in recency_positions, else the
    "equal"-scheme pipeline -- see module docstring's synthesis note.
    """
    _validate_input(matched)

    fit_timestamp = pd.Timestamp.now(tz="UTC")
    rows = []
    for asof_year in sorted(matched["season"].unique()):
        train = matched[matched["season"] < asof_year]
        if train["season"].nunique() < min_prior_seasons:
            continue

        equal_round_means = _fit_round_means(train, asof_year, "equal", half_life_years)
        equal_offsets = _fit_offsets(train, equal_round_means, asof_year, "equal", half_life_years, offset_positions)

        if recency_positions:
            recency_round_means = _fit_round_means(train, asof_year, "recency", half_life_years)
            recency_offsets = _fit_offsets(
                train, recency_round_means, asof_year, "recency", half_life_years, offset_positions
            )
        else:
            recency_round_means, recency_offsets = {}, {}

        rounds_in_train = sorted(int(r) for r in train["adp_round"].dropna().unique())

        for position in SBV_POSITIONS:
            use_recency = position in recency_positions
            round_means = recency_round_means if use_recency else equal_round_means
            offsets = recency_offsets if use_recency else equal_offsets
            raw_offset = offsets.get(position) if position in offset_positions else None
            offset = None if raw_offset is None or (isinstance(raw_offset, float) and np.isnan(raw_offset)) else raw_offset

            for rnd in rounds_in_train:
                baseline = round_means.get(rnd)
                if baseline is None or (isinstance(baseline, float) and np.isnan(baseline)):
                    continue
                expected_production = baseline + (offset if offset is not None else 0.0)
                rows.append({
                    "prediction_season": int(asof_year),
                    "position": position,
                    "draft_round": rnd,
                    "expected_production": float(expected_production),
                    "positional_offset_applied": offset,
                    "recency_weighted": use_recency,
                    "half_life_years": half_life_years if use_recency else None,
                    "sample_size": _sample_size(train, rnd, position),
                    "sbv_version": SBV_VERSION,
                    "fit_timestamp": fit_timestamp,
                })

    return pd.DataFrame(rows, columns=list(LOOKUP_SCHEMA_COLUMNS))


def validate_lookup(lookup: pd.DataFrame, running_sbv_version: str = SBV_VERSION) -> None:
    """Reusable lookup validation/version-check -- this commit's caller
    is scripts/09 itself (sanity-checking what it just wrote); a later
    scoring stage will be this function's main consumer, reading the
    lookup and calling this before trusting it. Raises loudly, never
    silently scores against a stale or malformed lookup."""
    missing = [c for c in LOOKUP_SCHEMA_COLUMNS if c not in lookup.columns]
    if missing:
        raise ValueError(f"E_P lookup is missing required columns: {missing}")

    if lookup.empty:
        raise ValueError("E_P lookup is empty -- refusing to treat an empty table as valid")

    stale_versions = set(lookup["sbv_version"].unique()) - {running_sbv_version}
    if stale_versions:
        raise ValueError(
            f"STALE E_P LOOKUP TABLE: contains sbv_version {sorted(stale_versions)}, "
            f"but the running code is SBV_VERSION={running_sbv_version!r}. Re-run "
            f"scripts/09_fit_sbv_expected_production.py before scoring -- never silently "
            f"score against an outdated fit."
        )

    dupes = lookup.duplicated(subset=list(LOOKUP_KEY_COLUMNS), keep=False)
    if dupes.any():
        dupe_keys = lookup.loc[dupes, list(LOOKUP_KEY_COLUMNS)].drop_duplicates()
        raise ValueError(
            f"E_P lookup has duplicate (prediction_season, position, draft_round) rows: "
            f"{dupe_keys.to_dict('records')}"
        )
