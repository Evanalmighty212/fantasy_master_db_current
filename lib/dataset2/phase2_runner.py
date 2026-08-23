"""Dataset 2 Phase 2 holdout-confirmation single-fit runner.

Deliberately artifact-agnostic, like lib/dataset2/phase1_runner.py:
callers supply DataFrames, already-resolved PredictorDefinition
objects, and each candidate's already-computed Phase 1 discovery
effect. This module contains no filesystem paths and cannot load a
real holdout analysis view by itself; loading governed inputs and
writing an output package is the entry point's job
(scripts/run_dataset2_phase2_confirmation.py).

Implements only Section 2 of
research/dataset2/DATASET2_PHASE2_METHODOLOGY_FREEZE_2026_08.md: one
single point-estimate refit per candidate trait on 2021-2025 holdout
rows only (no bootstrap, no resampling), reusing the exact fitting
functions Phase 1 discovery already uses and tests
(lib.dataset2.phase1_runner._fit_lwi / _firth_point_estimates),
compared against the trait's pinned Phase 1 discovery effect via
lib.dataset2.phase2_confirmation.evaluate_holdout_confirmation().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from statsmodels.tools.tools import add_constant

from config import (
    DATASET2_HOLDOUT_END_SEASON,
    DATASET2_HOLDOUT_START_SEASON,
    DATASET2_PHASE2_DISCOVERY_LWI_OUTCOME_SD,
    validate_dataset2_phase2_config,
)
from lib.dataset2.phase1_runner import (
    PRIMARY_TARGETS,
    PredictorDefinition,
    TargetDefinition,
    _design,
    _fit_lwi,
    _firth_point_estimates,
    _validated_target_values,
)
from lib.dataset2.phase2_confirmation import (
    ConfirmationVerdict,
    Phase2Candidate,
    evaluate_holdout_confirmation,
)

validate_dataset2_phase2_config()

_TARGET_BY_FAMILY: dict[str, TargetDefinition] = {target.family: target for target in PRIMARY_TARGETS}

# Exceptions the holdout single-fit path can legitimately raise for a
# holdout population that cannot support this trait's fit (rank
# deficiency, zero variation, a Firth fit that fails to converge, a
# missing governed reference level, and similar data-insufficiency
# conditions already raised by _design()/_fit_lwi()/_firth_point_estimates()
# in lib.dataset2.phase1_runner). Anything else propagates as a real bug.
_EXPECTED_FIT_FAILURE_TYPES = (TypeError, ValueError, RuntimeError, np.linalg.LinAlgError)


@dataclass(frozen=True)
class HoldoutConfirmationRecord:
    family: str
    predictor_column: str
    discovery_effect: float
    holdout_effect: float | None
    holdout_n: int
    holdout_seasons_represented: int
    verdict: ConfirmationVerdict
    fit_failure_reason: str | None


def _validated_holdout_seasons(rows: pd.DataFrame) -> pd.Series:
    """Fail loudly on any row outside the protected 2021-2025 holdout window.

    Regression coverage: guards against 2010-2020 discovery-season rows
    (or any other out-of-window season) silently entering a Phase 2 fit.
    """
    if "prediction_season" not in rows:
        raise ValueError("Phase 2 holdout rows require prediction_season")
    if rows["prediction_season"].map(lambda value: isinstance(value, (bool, np.bool_))).any():
        raise ValueError("Phase 2 holdout prediction seasons must not be boolean")
    numeric = pd.to_numeric(rows["prediction_season"], errors="coerce")
    if numeric.isna().any() or np.any(~np.isfinite(numeric)) or np.any(numeric % 1 != 0):
        raise ValueError("Phase 2 holdout prediction seasons must be finite integers")
    numeric = numeric.astype(int)
    out_of_window = numeric[
        (numeric < DATASET2_HOLDOUT_START_SEASON) | (numeric > DATASET2_HOLDOUT_END_SEASON)
    ]
    if not out_of_window.empty:
        bad = sorted(out_of_window.unique())
        raise ValueError(
            "non-holdout seasons supplied for Phase 2 fitting (discovery-season "
            f"leakage or an out-of-range season): {bad}"
        )
    return numeric


def _holdout_target_rows(rows: pd.DataFrame, target: TargetDefinition) -> pd.DataFrame:
    """Select target-eligible 2021-2025 rows only; mirrors _discovery_target_rows."""
    _validated_holdout_seasons(rows)
    required = {target.target_column, "player_id", "position", "preseason_market_status", "adp_round"}
    if target.eligibility_column is not None:
        required.add(target.eligibility_column)
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f"Phase 2 holdout input missing required columns: {missing}")
    seasons = pd.to_numeric(rows["prediction_season"], errors="raise").astype(int)
    selected = rows.loc[seasons.between(DATASET2_HOLDOUT_START_SEASON, DATASET2_HOLDOUT_END_SEASON)].copy()
    if target.eligibility_column is not None:
        eligibility_values = set(selected[target.eligibility_column].dropna().unique())
        if not eligibility_values <= {0, 1, True, False}:
            raise ValueError(f"eligibility column must be boolean/0/1: {target.eligibility_column}")
        selected = selected.loc[selected[target.eligibility_column].fillna(False).astype(bool)].copy()
    if target.binary:
        _validated_target_values(selected, target)
    return selected.dropna(subset=[target.target_column, "player_id", "position"])


def holdout_fit_rows(rows: pd.DataFrame, target: TargetDefinition, predictor_column: str) -> pd.DataFrame:
    """Select eligible 2021-2025 rows only for one candidate; mirrors discovery_fit_rows."""
    if predictor_column not in rows:
        raise ValueError(f"Phase 2 holdout input missing required columns: ['{predictor_column}']")
    selected = _holdout_target_rows(rows, target).dropna(subset=[predictor_column])
    if selected.empty:
        raise ValueError(f"no eligible 2021-2025 rows for {predictor_column} and {target.family}")
    _validated_target_values(selected, target)
    return selected


def _validated_full_rank_holdout_design(rows: pd.DataFrame, predictor: PredictorDefinition) -> None:
    """Fail loudly on a holdout design too degenerate for either fitting path to trust.

    _fit_lwi()'s OLS and _firth_point_estimates()'s Firth solver do not
    themselves guarantee a rank check: a rank-deficient design does not
    reliably raise (statsmodels' OLS silently returns an arbitrary,
    non-unique coefficient split across collinear columns via a
    pseudo-inverse rather than erroring), which would let a genuinely
    non-estimable holdout population masquerade as a legitimate
    holdout_effect instead of the inconclusive verdict it should produce.
    A small holdout subset is far more likely to hit this than the much
    larger discovery population Phase 1's own preflight already guards.
    """
    design, _ = _design(rows, predictor)
    matrix = add_constant(design, has_constant="add").to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError(f"holdout design contains non-finite values for {predictor.column}")
    if np.linalg.matrix_rank(matrix) != matrix.shape[1]:
        raise ValueError(f"holdout design is rank-deficient for {predictor.column}")


def _single_holdout_point_estimate(
    rows: pd.DataFrame, target: TargetDefinition, predictor: PredictorDefinition,
) -> float:
    """One non-resampled point estimate, on the same scale as the pinned
    Phase 1 discovery adjusted_effects column for this predictor's family.

    LWI: raw OLS beta divided by the pinned discovery-window outcome SD
    (DATASET2_PHASE2_DISCOVERY_LWI_OUTCOME_SD), exactly the normalization
    _fit_lwi() already applies -- this call supplies the frozen constant
    in place of a freshly-computed one so both periods are expressed in
    the same units. Star/Strict Bust: the odds ratio _firth_point_estimates()
    already returns, needing no further scaling.
    """
    if predictor.kind == "categorical":
        raise ValueError(
            "Phase 2 holdout fitting does not support categorical predictors: "
            "reference-level freezing across the discovery/holdout boundary is "
            f"unimplemented: {predictor.column}"
        )
    _validated_full_rank_holdout_design(rows, predictor)
    if target.family == "lwi":
        result = _fit_lwi(rows, target, predictor, DATASET2_PHASE2_DISCOVERY_LWI_OUTCOME_SD)
        if len(result.estimates) != 1:
            raise ValueError(
                f"Phase 2 candidate {predictor.column} produced {len(result.estimates)} "
                "contrasts; only single-contrast candidates are supported"
            )
        return float(result.estimates[0])
    estimates = _firth_point_estimates(rows, target, predictor)
    if len(estimates) != 1:
        raise ValueError(
            f"Phase 2 candidate {predictor.column} produced {len(estimates)} contrasts; "
            "only single-contrast candidates are supported"
        )
    if predictor.column not in estimates:
        raise ValueError(f"holdout fit produced no estimate for contrast {predictor.column}")
    return float(estimates[predictor.column])


def confirm_candidate(
    rows: pd.DataFrame,
    candidate: Phase2Candidate,
    predictor: PredictorDefinition,
    discovery_effect: float,
) -> HoldoutConfirmationRecord:
    """Fit one candidate once on holdout rows and classify it under Option B.

    A holdout population that cannot support this candidate's fit (too
    few rows, zero variation, non-convergence) yields holdout_effect=None
    and verdict="inconclusive" rather than raising -- one bad candidate
    must never abort the other 31. Any exception outside
    _EXPECTED_FIT_FAILURE_TYPES still propagates, so a real bug is never
    silently absorbed as a data-insufficiency result.
    """
    if predictor.column != candidate.predictor_column:
        raise ValueError(
            f"predictor definition {predictor.column!r} does not match "
            f"candidate {candidate.predictor_column!r}"
        )
    target = _TARGET_BY_FAMILY[candidate.family]
    holdout_effect: float | None = None
    fit_failure_reason: str | None = None
    holdout_n = 0
    holdout_seasons_represented = 0
    try:
        fit_rows = holdout_fit_rows(rows, target, candidate.predictor_column)
        holdout_n = int(len(fit_rows))
        holdout_seasons_represented = int(fit_rows["prediction_season"].nunique())
        holdout_effect = _single_holdout_point_estimate(fit_rows, target, predictor)
    except _EXPECTED_FIT_FAILURE_TYPES as exc:
        fit_failure_reason = str(exc)
    verdict = evaluate_holdout_confirmation(discovery_effect, holdout_effect)
    return HoldoutConfirmationRecord(
        family=candidate.family,
        predictor_column=candidate.predictor_column,
        discovery_effect=discovery_effect,
        holdout_effect=holdout_effect,
        holdout_n=holdout_n,
        holdout_seasons_represented=holdout_seasons_represented,
        verdict=verdict,
        fit_failure_reason=fit_failure_reason,
    )


def confirm_all_candidates(
    rows: pd.DataFrame,
    candidates: Sequence[Phase2Candidate],
    predictors_by_column: Mapping[str, PredictorDefinition],
    discovery_effects: Mapping[tuple[str, str], float],
) -> tuple[HoldoutConfirmationRecord, ...]:
    """Run the frozen holdout-confirmation fit for every supplied candidate.

    Rejects any non-holdout row before any candidate is fit, not merely
    inside each individual fit, so a leakage bug cannot masquerade as an
    isolated single-candidate failure.
    """
    _validated_holdout_seasons(rows)
    records = []
    for candidate in candidates:
        key = (candidate.family, candidate.predictor_column)
        if key not in discovery_effects:
            raise ValueError(f"no pinned Phase 1 discovery effect available for {key}")
        if candidate.predictor_column not in predictors_by_column:
            raise ValueError(f"no resolved predictor definition for {candidate.predictor_column}")
        records.append(confirm_candidate(
            rows, candidate, predictors_by_column[candidate.predictor_column],
            discovery_effects[key],
        ))
    return tuple(records)
