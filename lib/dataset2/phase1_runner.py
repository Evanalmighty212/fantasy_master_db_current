"""Dataset 2 Phase 1 Version 1 inference engine.

This module is deliberately artifact-agnostic: callers supply DataFrames and
governed predictor metadata. It contains no filesystem paths and cannot load a
real analysis view by itself. Tests use synthetic rows only; executing it on
accepted artifacts is a separate authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
from typing import Callable, Literal, Sequence

import numpy as np
import pandas as pd
from scipy.stats import chi2
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from statsmodels.regression.linear_model import OLS
from statsmodels.tools.tools import add_constant

from config import (
    DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE,
    DATASET2_BUST_REFERENCE_START_SEASON,
    DATASET2_DISCOVERY_END_SEASON,
    DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE,
    DATASET2_FIRTH_BOOTSTRAP_REPLICATES,
    DATASET2_LWI_MIN_ABS_STANDARDIZED_BETA,
    DATASET2_PHASE1_BH_Q,
    DATASET2_PHASE1_RANDOM_SEED,
    DATASET2_STRICT_BUST_OR_DECREASE_GATE,
    DATASET2_STRICT_BUST_OR_INCREASE_GATE,
    validate_dataset2_phase1_config,
)
from lib.dataset2.firth_logistic import _penalized_loglik, fit_firth_logistic
from lib.dataset2.phase1_analysis import (
    BootstrapReplicateError,
    benjamini_hochberg,
    eligibility_aware_expanding_windows,
    indexed_player_cluster_bootstrap,
    player_cluster_bootstrap,
    preseason_acquisition_stratum,
)

validate_dataset2_phase1_config()

PredictorKind = Literal["continuous", "binary", "categorical"]
Family = Literal["lwi", "star", "strict_bust"]


@dataclass(frozen=True)
class TargetDefinition:
    family: Family
    target_column: str
    eligibility_column: str | None
    binary: bool


PRIMARY_TARGETS: tuple[TargetDefinition, ...] = (
    TargetDefinition("lwi", "lwi_score", None, False),
    TargetDefinition("star", "star_by_value_label", "star_outcome_eligible", True),
    TargetDefinition(
        "strict_bust", "bust_strict_below_replacement_label",
        "bust_strict_below_replacement_eligible", True,
    ),
)

CONTROL_LEVELS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("position", ("QB", "RB", "WR", "TE"), "QB"),
    (
        "acquisition",
        (
            "ordinary_R1-2", "ordinary_R3-5", "ordinary_R6-10", "ordinary_R11+",
            "rare_minimal_market", "participation_unknown",
        ),
        "ordinary_R1-2",
    ),
    ("era", ("pre_2011", "2011_plus"), "pre_2011"),
)

FIXED_CATEGORICAL_REFERENCES = {
    "fam9_team_game_window_status": "applicable",
    "fam10_depth_chart_status": "starter",
}
FREQUENCY_DERIVED_TEAM_REFERENCES = {
    "fam10_depth_chart_team",
    "fam4_nfl_draft_team",
}


@dataclass(frozen=True)
class PredictorDefinition:
    column: str
    kind: PredictorKind
    cluster_id: str
    is_cluster_representative: bool
    reference_level: str | None = None


@dataclass(frozen=True)
class CategoricalReferenceRecord:
    predictor_column: str
    reference_level: str
    reference_frequency: int
    eligible_nonnull_n: int
    selection_method: str

    @property
    def reference_share(self) -> float:
        return self.reference_frequency / self.eligible_nonnull_n


@dataclass(frozen=True)
class PreflightRecord:
    family: Family
    predictor_column: str
    cluster_id: str
    predictor_kind: PredictorKind
    target_eligible_n: int
    predictor_nonnull_n: int
    distinct_value_count: int
    seasons_represented: int
    disposition: Literal["fit", "excluded_non_estimable"]
    governed_reason: str | None


@dataclass(frozen=True)
class EvidenceStatus:
    applicable_n: int
    positive_n: int | None
    negative_n: int | None
    seasons_represented: int
    max_single_season_share: float
    failed_gates: tuple[str, ...]

    @property
    def formal(self) -> bool:
        return not self.failed_gates


@dataclass(frozen=True)
class DesignSchema:
    predictor_columns: tuple[str, ...]
    control_levels: tuple[tuple[str, tuple[str, ...], str], ...]
    predictor_mean: float | None
    predictor_sd: float | None

    @property
    def control_columns(self) -> tuple[str, ...]:
        return tuple(
            f"{name}_{level}"
            for name, levels, reference in self.control_levels
            for level in levels
            if level != reference
        )


@dataclass(frozen=True)
class ModelResult:
    family: Family
    predictor: PredictorDefinition
    contrast_names: tuple[str, ...]
    estimates: tuple[float, ...]
    native_effects: tuple[float, ...]
    raw_outcome_effects: tuple[float, ...]
    confidence_intervals: tuple[tuple[float, float], ...]
    probability_differences: tuple[float, ...]
    primary_p_value: float
    evidence: EvidenceStatus
    practical_effect_passes: bool | None
    bootstrap_attempted: int | None
    bootstrap_successful: int | None
    bootstrap_failure_counts: tuple[tuple[str, int], ...] | None


@dataclass(frozen=True)
class IncrementalResult:
    family: Family
    predictor_column: str
    folds: int
    metrics: dict[str, float]


@dataclass(frozen=True)
class RobustnessResult:
    family: Family
    predictor_column: str
    full_estimates: tuple[float, ...]
    leave_one_season_out_estimates: tuple[tuple[int, tuple[float, ...]], ...]
    direction_status: tuple[str, ...]


@dataclass(frozen=True)
class Phase1Package:
    primary_results: pd.DataFrame
    incremental_results: tuple[IncrementalResult, ...]
    robustness_results: tuple[RobustnessResult, ...]
    categorical_references: tuple[CategoricalReferenceRecord, ...]
    preflight_ledger: tuple[PreflightRecord, ...]


def strict_bust_practical_effect_passes(odds_ratios: Sequence[float]) -> bool:
    values = np.asarray(odds_ratios, dtype=float)
    if values.size == 0 or np.any(~np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("strict-bust odds ratios must be finite and positive")
    return bool(
        np.any(values >= DATASET2_STRICT_BUST_OR_INCREASE_GATE)
        or np.any(values <= DATASET2_STRICT_BUST_OR_DECREASE_GATE)
    )


def null_centered_bootstrap_p_value(point: float, replicates: Sequence[float]) -> float:
    """Two-sided null-centered bootstrap p with finite-sample correction."""
    values = np.asarray(replicates, dtype=float)
    if not np.isfinite(point) or values.size == 0 or np.any(~np.isfinite(values)):
        raise ValueError("bootstrap point and replicates must be finite and nonempty")
    null_centered = values - point
    extreme = int(np.count_nonzero(np.abs(null_centered) >= abs(point)))
    return float((extreme + 1) / (values.size + 1))


def null_centered_joint_bootstrap_p_value(
    point: Sequence[float], replicates: Sequence[Sequence[float]],
) -> float:
    """One multivariate null-centered bootstrap test for a categorical predictor."""
    beta = np.asarray(point, dtype=float)
    draws = np.asarray(replicates, dtype=float)
    if beta.ndim != 1 or beta.size < 2 or draws.ndim != 2 or draws.shape[1] != beta.size:
        raise ValueError("joint bootstrap requires a coefficient vector and matching replicate matrix")
    if draws.shape[0] < 2 or np.any(~np.isfinite(beta)) or np.any(~np.isfinite(draws)):
        raise ValueError("joint bootstrap values must be finite with at least two replicates")
    covariance_inverse = np.linalg.pinv(np.cov(draws, rowvar=False, ddof=1))
    observed = float(beta @ covariance_inverse @ beta)
    centered = draws - beta
    replicate_statistics = np.einsum("ij,jk,ik->i", centered, covariance_inverse, centered)
    extreme = int(np.count_nonzero(replicate_statistics >= observed))
    return float((extreme + 1) / (len(draws) + 1))


def _validated_seasons(rows: pd.DataFrame) -> pd.Series:
    if "prediction_season" not in rows:
        raise ValueError("Phase 1 rows require prediction_season")
    if rows["prediction_season"].map(lambda value: isinstance(value, (bool, np.bool_))).any():
        raise ValueError("Phase 1 prediction seasons must not be boolean")
    numeric = pd.to_numeric(rows["prediction_season"], errors="coerce")
    if numeric.isna().any() or np.any(~np.isfinite(numeric)) or np.any(numeric % 1 != 0):
        raise ValueError("Phase 1 prediction seasons must be finite integers")
    numeric = numeric.astype(int)
    if (numeric > DATASET2_DISCOVERY_END_SEASON).any():
        bad = sorted(numeric[numeric > DATASET2_DISCOVERY_END_SEASON].unique())
        raise ValueError(f"protected holdout/application seasons supplied for fitting: {bad}")
    return numeric


def _discovery_target_rows(rows: pd.DataFrame, target: TargetDefinition) -> pd.DataFrame:
    """Select target-eligible discovery rows before predictor-specific null filtering."""
    seasons = _validated_seasons(rows)
    required = {target.target_column, "player_id", "position", "preseason_market_status", "adp_round"}
    if target.eligibility_column is not None:
        required.add(target.eligibility_column)
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f"Phase 1 input missing required columns: {missing}")
    selected = rows.loc[seasons.between(DATASET2_BUST_REFERENCE_START_SEASON, DATASET2_DISCOVERY_END_SEASON)].copy()
    if target.eligibility_column is not None:
        eligibility_values = set(selected[target.eligibility_column].dropna().unique())
        if not eligibility_values <= {0, 1, True, False}:
            raise ValueError(f"eligibility column must be boolean/0/1: {target.eligibility_column}")
        selected = selected.loc[selected[target.eligibility_column].fillna(False).astype(bool)].copy()
    if target.binary:
        _validated_target_values(selected, target)
    return selected.dropna(subset=[target.target_column, "player_id", "position"])


def _validated_target_values(rows: pd.DataFrame, target: TargetDefinition) -> pd.Series:
    """Validate target values without changing the governed eligibility population."""
    values = rows[target.target_column]
    if values.isna().any():
        raise ValueError(f"eligible target contains missing values: {target.target_column}")
    try:
        numeric = pd.to_numeric(values, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"target must be numeric: {target.target_column}") from exc
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError(f"target contains non-finite values: {target.target_column}")
    if target.binary and not set(pd.unique(numeric)) <= {0, 1}:
        raise ValueError(f"binary target must be 0/1: {target.target_column}")
    return numeric


def discovery_fit_rows(rows: pd.DataFrame, target: TargetDefinition, predictor_column: str) -> pd.DataFrame:
    """Select eligible 2010-2020 rows only, rejecting any supplied holdout."""
    if predictor_column not in rows:
        raise ValueError(f"Phase 1 input missing required columns: ['{predictor_column}']")
    selected = _discovery_target_rows(rows, target).dropna(subset=[predictor_column])
    if selected.empty:
        raise ValueError(f"no eligible 2010-2020 rows for {predictor_column} and {target.family}")
    _validated_target_values(selected, target)
    return selected


def resolve_categorical_references(
    rows: pd.DataFrame,
    predictors: Sequence[PredictorDefinition],
) -> tuple[tuple[PredictorDefinition, ...], tuple[CategoricalReferenceRecord, ...]]:
    """Resolve and audit categorical references without consulting outcomes."""
    seasons = _validated_seasons(rows)
    discovery = rows.loc[
        seasons.between(DATASET2_BUST_REFERENCE_START_SEASON, DATASET2_DISCOVERY_END_SEASON)
    ]
    resolved = []
    records = []
    for predictor in predictors:
        if predictor.kind != "categorical":
            resolved.append(predictor)
            continue
        if predictor.column not in discovery:
            raise ValueError(f"categorical predictor is absent from Phase 1 rows: {predictor.column}")
        values = discovery[predictor.column].dropna().astype(str)
        counts = values.value_counts()
        if counts.empty:
            raise ValueError(f"categorical reference cannot be derived from no eligible values: {predictor.column}")

        if predictor.column in FIXED_CATEGORICAL_REFERENCES:
            reference = FIXED_CATEGORICAL_REFERENCES[predictor.column]
            method = "fixed_governed_status_reference"
        elif predictor.column in FREQUENCY_DERIVED_TEAM_REFERENCES:
            ranked = sorted(counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
            reference = str(ranked[0][0])
            method = "most_frequent_discovery_category_alphabetical_tiebreak"
        elif predictor.reference_level is not None:
            reference = predictor.reference_level
            method = "explicit_predictor_definition"
        else:
            raise ValueError(f"categorical predictor has no governed reference rule: {predictor.column}")

        if predictor.reference_level is not None and predictor.reference_level != reference:
            raise ValueError(
                f"declared reference {predictor.reference_level!r} disagrees with governed "
                f"reference {reference!r} for {predictor.column}"
            )
        if reference not in counts:
            raise ValueError(f"governed categorical reference is absent for {predictor.column}: {reference}")
        resolved.append(replace(predictor, reference_level=reference))
        records.append(CategoricalReferenceRecord(
            predictor_column=predictor.column,
            reference_level=reference,
            reference_frequency=int(counts[reference]),
            eligible_nonnull_n=int(len(values)),
            selection_method=method,
        ))
    return tuple(resolved), tuple(records)


def validate_predictor_definitions(
    predictors: Sequence[PredictorDefinition], predictor_whitelist: Sequence[str],
) -> None:
    allowed = set(predictor_whitelist)
    seen: set[str] = set()
    forbidden = {target.target_column for target in PRIMARY_TARGETS} | {
        target.eligibility_column for target in PRIMARY_TARGETS if target.eligibility_column
    }
    for predictor in predictors:
        if predictor.column in seen:
            raise ValueError(f"duplicate predictor definition: {predictor.column}")
        seen.add(predictor.column)
        if predictor.column not in allowed:
            raise ValueError(f"predictor absent from governed whitelist: {predictor.column}")
        if predictor.column in forbidden or "outcome" in predictor.column or predictor.column.endswith("_label"):
            raise ValueError(f"outcome/leakage column cannot be a predictor: {predictor.column}")
        if predictor.kind == "categorical" and predictor.reference_level is None:
            raise ValueError(f"categorical predictor requires an explicit reference: {predictor.column}")
    for cluster_id in {predictor.cluster_id for predictor in predictors}:
        representatives = sum(
            predictor.is_cluster_representative
            for predictor in predictors
            if predictor.cluster_id == cluster_id
        )
        if representatives != 1:
            raise ValueError(
                f"cluster {cluster_id} requires exactly one representative; found {representatives}"
            )


def _control_design(
    rows: pd.DataFrame,
    levels_schema: tuple[tuple[str, tuple[str, ...], str], ...] | None = None,
) -> tuple[pd.DataFrame, tuple[tuple[str, tuple[str, ...], str], ...]]:
    acquisition = preseason_acquisition_stratum(rows)
    era = np.where(rows["prediction_season"].astype(int) < 2011, "pre_2011", "2011_plus")
    raw = pd.DataFrame({
        "position": rows["position"].astype(str),
        "acquisition": acquisition.astype(str),
        "era": era,
    }, index=rows.index)
    if levels_schema is None:
        selected = []
        for column, governed_levels, reference in CONTROL_LEVELS:
            observed = set(raw[column].unique())
            unexpected = sorted(observed - set(governed_levels))
            if unexpected:
                raise ValueError(f"unexpected {column} control levels: {unexpected}")
            observed_levels = tuple(level for level in governed_levels if level in observed)
            if not observed_levels:
                raise ValueError(f"no governed {column} control levels are present")
            effective_reference = reference if reference in observed else observed_levels[0]
            selected.append((column, observed_levels, effective_reference))
        levels_schema = tuple(selected)
    pieces = []
    for column, governed_levels, reference in levels_schema:
        observed = set(raw[column].unique())
        unexpected = sorted(observed - set(governed_levels))
        if unexpected:
            raise ValueError(f"unexpected {column} control levels: {unexpected}")
        for level in governed_levels:
            if level != reference:
                pieces.append((f"{column}_{level}", (raw[column] == level).astype(float)))
    design = pd.DataFrame(dict(pieces), index=rows.index)
    return design, levels_schema


def _predictor_design(
    rows: pd.DataFrame, predictor: PredictorDefinition, schema: DesignSchema | None = None,
) -> tuple[pd.DataFrame, float | None, float | None]:
    values = rows[predictor.column]
    if predictor.kind == "continuous":
        numeric = pd.to_numeric(values, errors="raise")
        mean = float(numeric.mean()) if schema is None else float(schema.predictor_mean)
        sd = float(numeric.std(ddof=1)) if schema is None else float(schema.predictor_sd)
        if not np.isfinite(sd) or sd <= 0:
            raise ValueError(f"continuous predictor has invalid discovery SD: {predictor.column}")
        design = pd.DataFrame({predictor.column: (numeric - mean) / sd}, index=rows.index)
        return design, mean, sd
    if predictor.kind == "binary":
        if not set(pd.unique(values)) <= {0, 1, True, False}:
            raise ValueError(f"binary predictor must be 0/1: {predictor.column}")
        return pd.DataFrame({predictor.column: values.astype(float)}, index=rows.index), None, None
    levels = values.astype(str)
    if schema is None and predictor.reference_level not in set(levels):
        raise ValueError(f"categorical reference is absent: {predictor.reference_level}")
    design = pd.get_dummies(levels, prefix=predictor.column, dtype=float)
    reference = f"{predictor.column}_{predictor.reference_level}"
    if schema is None and reference not in design:
        raise ValueError(f"categorical reference column is absent: {reference}")
    design = design.drop(columns=reference, errors="ignore")
    if schema is not None:
        unexpected = sorted(set(design.columns) - set(schema.predictor_columns))
        if unexpected:
            raise ValueError(f"unexpected categorical levels in validation/resample: {unexpected}")
        design = design.reindex(columns=list(schema.predictor_columns), fill_value=0.0)
    if design.shape[1] == 0:
        raise ValueError(f"categorical predictor has no contrast: {predictor.column}")
    return design, None, None


def _design(rows: pd.DataFrame, predictor: PredictorDefinition, schema: DesignSchema | None = None):
    predictor_frame, mean, sd = _predictor_design(rows, predictor, schema)
    controls, control_levels = _control_design(rows, None if schema is None else schema.control_levels)
    combined = pd.concat([predictor_frame, controls], axis=1)
    if combined.columns.duplicated().any():
        raise ValueError("predictor/control design columns collide")
    if schema is None:
        schema = DesignSchema(tuple(predictor_frame.columns), control_levels, mean, sd)
    return combined, schema


def preflight_phase1_estimability(
    rows: pd.DataFrame,
    predictors: Sequence[PredictorDefinition],
    predictor_whitelist: Sequence[str],
) -> tuple[PreflightRecord, ...]:
    """Validate every predictor-family design before any expensive fit.

    Genuine target-specific absence of predictor variation receives an explicit
    governed exclusion. Malformed data and unexplained design failures remain
    fail-loud and can never silently reduce a family's BH universe.
    """
    _validated_seasons(rows)
    resolved, _ = resolve_categorical_references(rows, predictors)
    validate_predictor_definitions(resolved, predictor_whitelist)
    records: list[PreflightRecord] = []
    failures: list[str] = []
    for predictor in resolved:
        for target in PRIMARY_TARGETS:
            context = f"family={target.family} predictor={predictor.column}"
            try:
                target_rows = _discovery_target_rows(rows, target)
                if predictor.column not in target_rows:
                    raise ValueError(f"Phase 1 input missing required columns: ['{predictor.column}']")
                fit_rows = target_rows.dropna(subset=[predictor.column]).copy()
                if fit_rows.empty:
                    records.append(PreflightRecord(
                        target.family, predictor.column, predictor.cluster_id, predictor.kind,
                        len(target_rows), 0, 0, 0, "excluded_non_estimable",
                        "no_nonnull_discovery_support",
                    ))
                    continue
                target_numeric = _validated_target_values(fit_rows, target)
                binary_target_has_contrast = (
                    not target.binary or int(target_numeric.nunique()) == 2
                )
                values = fit_rows[predictor.column]
                if predictor.kind == "continuous":
                    numeric = pd.to_numeric(values, errors="raise")
                    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
                        raise ValueError("continuous predictor contains non-finite values")
                    distinct = int(numeric.nunique())
                    if distinct < 2 or not np.isfinite(float(numeric.std(ddof=1))) or float(numeric.std(ddof=1)) <= 0:
                        records.append(PreflightRecord(
                            target.family, predictor.column, predictor.cluster_id, predictor.kind,
                            len(target_rows), len(fit_rows), distinct,
                            int(fit_rows["prediction_season"].nunique()),
                            "excluded_non_estimable", "continuous_zero_variation",
                        ))
                        continue
                elif predictor.kind == "binary":
                    if not set(pd.unique(values)) <= {0, 1, True, False}:
                        raise ValueError(f"binary predictor must be 0/1: {predictor.column}")
                    distinct = int(values.nunique())
                    if distinct != 2:
                        records.append(PreflightRecord(
                            target.family, predictor.column, predictor.cluster_id, predictor.kind,
                            len(target_rows), len(fit_rows), distinct,
                            int(fit_rows["prediction_season"].nunique()),
                            "excluded_non_estimable", "binary_no_discovery_contrast",
                        ))
                        continue
                elif predictor.kind == "categorical":
                    distinct = int(values.astype(str).nunique())
                    if distinct < 2:
                        records.append(PreflightRecord(
                            target.family, predictor.column, predictor.cluster_id, predictor.kind,
                            len(target_rows), len(fit_rows), distinct,
                            int(fit_rows["prediction_season"].nunique()),
                            "excluded_non_estimable", "categorical_no_discovery_contrast",
                        ))
                        continue
                else:
                    raise ValueError(f"unknown predictor kind: {predictor.kind}")
                predictor_design, _, _ = _predictor_design(fit_rows, predictor)
                matrix = predictor_design.to_numpy(dtype=float)
                if not np.isfinite(matrix).all():
                    raise ValueError("predictor design contains non-finite values")
                if np.linalg.matrix_rank(matrix) != matrix.shape[1]:
                    raise ValueError("predictor design is rank deficient or has zero variation")
                if not binary_target_has_contrast:
                    records.append(PreflightRecord(
                        target.family, predictor.column, predictor.cluster_id, predictor.kind,
                        len(target_rows), len(fit_rows), distinct,
                        int(fit_rows["prediction_season"].nunique()),
                        "excluded_non_estimable", "binary_target_no_discovery_contrast",
                    ))
                    continue
                records.append(PreflightRecord(
                    target.family, predictor.column, predictor.cluster_id, predictor.kind,
                    len(target_rows), len(fit_rows), distinct,
                    int(fit_rows["prediction_season"].nunique()), "fit", None,
                ))
            except (TypeError, ValueError) as exc:
                failures.append(f"{context}: {exc}")
    if failures:
        raise ValueError(
            "Phase 1 representative estimability preflight failed before fitting: "
            + " | ".join(failures)
        )
    return tuple(records)


def evidence_status(rows: pd.DataFrame, target: TargetDefinition, predictor: PredictorDefinition) -> EvidenceStatus:
    n = len(rows)
    failed: list[str] = []
    if n < 200:
        failed.append("applicable_n_below_200")
    seasons = rows["prediction_season"].astype(int)
    represented = int(seasons.nunique())
    concentration = float(seasons.value_counts(normalize=True).max())
    if represented < 5:
        failed.append("fewer_than_5_seasons")
    if concentration > 0.5:
        failed.append("single_season_share_above_0_50")
    positive = negative = None
    if target.binary:
        labels = rows[target.target_column]
        if not set(pd.unique(labels)) <= {0, 1, True, False}:
            raise ValueError(f"binary target must be 0/1: {target.target_column}")
        positive = int(labels.astype(bool).sum())
        negative = n - positive
        if min(positive, negative) < 10:
            failed.append("event_or_nonevent_below_10")
        if predictor.kind == "binary":
            cells = rows.assign(_p=rows[predictor.column].astype(int), _y=labels.astype(int)).groupby(["_p", "_y"]).size()
            if any(int(cells.get((p, y), 0)) < DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE for p in (0, 1) for y in (0, 1)):
                failed.append("binary_predictor_target_cell_below_10")
    if predictor.kind == "categorical" and (rows[predictor.column].value_counts() < 10).any():
        failed.append("categorical_level_below_10")
    return EvidenceStatus(n, positive, negative, represented, concentration, tuple(failed))


def _fit_lwi(rows: pd.DataFrame, target: TargetDefinition, predictor: PredictorDefinition, outcome_sd: float) -> ModelResult:
    design, schema = _design(rows, predictor)
    X = add_constant(design, has_constant="add")
    fit = OLS(rows[target.target_column].astype(float), X).fit(
        cov_type="cluster", cov_kwds={"groups": rows["player_id"]},
    )
    contrasts = schema.predictor_columns
    beta = np.asarray([fit.params[column] for column in contrasts], dtype=float)
    covariance = fit.cov_params().loc[list(contrasts), list(contrasts)].to_numpy()
    statistic = float(beta @ np.linalg.pinv(covariance) @ beta)
    p_value = float(chi2.sf(statistic, len(beta)))
    raw_ci = tuple((float(fit.conf_int().loc[c, 0]), float(fit.conf_int().loc[c, 1])) for c in contrasts)
    ci = tuple((low / outcome_sd, high / outcome_sd) for low, high in raw_ci)
    standardized = tuple(float(value / outcome_sd) for value in beta)
    native = tuple(
        float(value / schema.predictor_sd) if predictor.kind == "continuous" else float(value)
        for value in beta
    )
    practical = bool(any(abs(value) >= DATASET2_LWI_MIN_ABS_STANDARDIZED_BETA for value in standardized))
    return ModelResult(
        target.family, predictor, contrasts, standardized, native, tuple(float(v) for v in beta), ci,
        tuple(float("nan") for _ in contrasts), p_value, evidence_status(rows, target, predictor), practical, None, None, None,
    )


def _finite_diagnostic(value: float) -> float | None:
    numeric = float(value)
    return numeric if np.isfinite(numeric) else None


def _bootstrap_design_diagnostics(
    matrix: np.ndarray, sample_y: np.ndarray, names: tuple[str, ...], schema: DesignSchema,
) -> dict[str, object]:
    finite = bool(np.isfinite(matrix).all())
    rank = int(np.linalg.matrix_rank(matrix)) if finite else None
    condition = _finite_diagnostic(np.linalg.cond(matrix)) if finite and matrix.size else None
    target_values, target_counts = np.unique(sample_y, return_counts=True)
    name_to_index = {column: index for index, column in enumerate(names)}
    return {
        "reduced_design_row_count": int(matrix.shape[0]),
        "reduced_design_column_count": int(matrix.shape[1]),
        "reduced_design_rank": rank,
        "condition_number": condition,
        "target_class_support": {
            str(_finite_diagnostic(value)): int(count)
            for value, count in zip(target_values, target_counts)
        },
        "nuisance_control_nonzero_support": {
            column: int(np.count_nonzero(matrix[:, name_to_index[column]]))
            for column in schema.control_columns
            if column in name_to_index
        },
    }


def _firth_termination_diagnostics(fitted, design: dict[str, object]) -> dict[str, object]:
    iteration_tail = tuple({
        "iteration_number": int(record["iteration_number"]),
        "score_norm": _finite_diagnostic(record["score_norm"]),
        "newton_decrement": _finite_diagnostic(record["newton_decrement"]),
        "likelihood_change": _finite_diagnostic(record["likelihood_change"]),
        "maximum_coefficient_update": _finite_diagnostic(record["maximum_coefficient_update"]),
        "step_halving_count": int(record["step_halving_count"]),
        "termination_reason": str(record["termination_reason"]),
    } for record in fitted.iteration_tail)
    return {
        **design,
        "termination_reason": fitted.termination_reason,
        "iteration_count": int(fitted.n_iter),
        "final_score_norm": _finite_diagnostic(fitted.final_score_norm),
        "final_newton_decrement": _finite_diagnostic(fitted.final_newton_decrement),
        "final_likelihood_change": _finite_diagnostic(fitted.final_likelihood_change),
        "total_step_halvings": int(fitted.step_halving_count),
        "iteration_tail": iteration_tail,
    }


def _prepare_firth_bootstrap_design(
    sample_X: pd.DataFrame, sample_y: np.ndarray, schema: DesignSchema,
) -> tuple[pd.DataFrame, dict[str, int], dict[str, object]]:
    """Validate and reduce one resampled design without changing its tested signal."""
    zero_nuisance = [
        column for column in schema.control_columns
        if column in sample_X and bool((sample_X[column] == 0.0).all())
    ]
    reduced_X = sample_X.drop(columns=zero_nuisance)
    matrix = reduced_X.to_numpy(dtype=float)
    diagnostics = _bootstrap_design_diagnostics(
        matrix, sample_y, tuple(reduced_X.columns), schema,
    )
    diagnostics["nuisance_control_nonzero_support"] = {
        column: int(np.count_nonzero(sample_X[column].to_numpy(dtype=float)))
        for column in schema.control_columns
        if column in sample_X
    }
    if np.unique(sample_y).size < 2:
        raise BootstrapReplicateError(
            "missing_target_signal", "resample contains only one target class", diagnostics,
        )
    for column in schema.predictor_columns:
        if column not in sample_X or sample_X[column].nunique(dropna=False) <= 1:
            raise BootstrapReplicateError(
                "missing_predictor_contrast", f"tested contrast is absent: {column}", diagnostics,
            )
    if not np.isfinite(matrix).all():
        raise BootstrapReplicateError(
            "non_finite_likelihood", "bootstrap design contains non-finite values", diagnostics,
        )
    if np.linalg.matrix_rank(matrix) != matrix.shape[1]:
        raise BootstrapReplicateError(
            "rank_failure", "reduced bootstrap design is not full rank", diagnostics,
        )
    initial_loglik = _penalized_loglik(matrix, sample_y, np.zeros(matrix.shape[1], dtype=float))
    if not np.isfinite(initial_loglik):
        raise BootstrapReplicateError(
            "non_finite_likelihood", "initial penalized likelihood is non-finite", diagnostics,
        )
    return reduced_X, {column: index for index, column in enumerate(reduced_X.columns)}, diagnostics


def _prepare_firth_bootstrap_matrix(
    matrix: np.ndarray, sample_y: np.ndarray, names: tuple[str, ...], schema: DesignSchema,
) -> tuple[np.ndarray, dict[str, int], dict[str, object]]:
    name_to_index = {column: index for index, column in enumerate(names)}
    drop_indices = {
        name_to_index[column] for column in schema.control_columns
        if column in name_to_index and bool(np.all(matrix[:, name_to_index[column]] == 0.0))
    }
    keep_indices = [index for index in range(matrix.shape[1]) if index not in drop_indices]
    reduced = matrix[:, keep_indices]
    reduced_names = tuple(names[index] for index in keep_indices)
    diagnostics = _bootstrap_design_diagnostics(reduced, sample_y, reduced_names, schema)
    diagnostics["nuisance_control_nonzero_support"] = {
        column: int(np.count_nonzero(matrix[:, name_to_index[column]]))
        for column in schema.control_columns
        if column in name_to_index
    }
    if np.unique(sample_y).size < 2:
        raise BootstrapReplicateError(
            "missing_target_signal", "resample contains only one target class", diagnostics,
        )
    for column in schema.predictor_columns:
        if column not in name_to_index or np.unique(matrix[:, name_to_index[column]]).size <= 1:
            raise BootstrapReplicateError(
                "missing_predictor_contrast", f"tested contrast is absent: {column}", diagnostics,
            )
    if not np.isfinite(reduced).all():
        raise BootstrapReplicateError(
            "non_finite_likelihood", "bootstrap design contains non-finite values", diagnostics,
        )
    if np.linalg.matrix_rank(reduced) != reduced.shape[1]:
        raise BootstrapReplicateError(
            "rank_failure", "reduced bootstrap design is not full rank", diagnostics,
        )
    initial_loglik = _penalized_loglik(reduced, sample_y, np.zeros(reduced.shape[1], dtype=float))
    if not np.isfinite(initial_loglik):
        raise BootstrapReplicateError(
            "non_finite_likelihood", "initial penalized likelihood is non-finite", diagnostics,
        )
    return reduced, {column: index for index, column in enumerate(reduced_names)}, diagnostics


def _array_sha256(values: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(str(contiguous.dtype).encode("ascii"))
    digest.update(str(contiguous.shape).encode("ascii"))
    digest.update(contiguous.tobytes())
    return digest.hexdigest()


def _fit_firth(
    rows: pd.DataFrame, target: TargetDefinition, predictor: PredictorDefinition,
    *, replicates: int, seed: int, minimum_success_rate: float,
    checkpoint_directory: Path | None = None,
    checkpoint_identity: dict[str, object] | None = None,
    progress: Callable[[dict[str, object]], None] | None = None,
    _legacy_bootstrap_for_test: bool = False,
) -> ModelResult:
    design, schema = _design(rows, predictor)
    X_frame = add_constant(design, has_constant="add")
    names = tuple(X_frame.columns)
    y = rows[target.target_column].astype(float).to_numpy()

    original_fit = fit_firth_logistic(X_frame.to_numpy(dtype=float), y)
    if not original_fit.converged:
        raise RuntimeError(
            f"original Firth fit failed to converge for family={target.family} "
            f"predictor={predictor.column}"
        )
    original_coefficients = tuple(
        float(original_fit.beta[names.index(column)]) for column in schema.predictor_columns
    )

    def fit_coefficients(sample: pd.DataFrame) -> tuple[float, ...]:
        sample_design, _ = _design(sample, predictor, schema)
        sample_X = add_constant(sample_design, has_constant="add").reindex(columns=names, fill_value=0.0)
        sample_y = sample[target.target_column].astype(float).to_numpy()
        reduced_X, local_columns, diagnostics = _prepare_firth_bootstrap_design(
            sample_X, sample_y, schema,
        )
        matrix = reduced_X.to_numpy(dtype=float)
        fitted = fit_firth_logistic(matrix, sample_y)
        if not fitted.converged:
            raise BootstrapReplicateError(
                "nonconvergence", "Firth fit failed to converge",
                _firth_termination_diagnostics(fitted, diagnostics),
            )
        if not np.isfinite(fitted.beta).all():
            raise BootstrapReplicateError(
                "other_numerical_error", "Firth fit returned non-finite coefficients",
                _firth_termination_diagnostics(fitted, diagnostics),
            )
        return tuple(float(fitted.beta[local_columns[column]]) for column in schema.predictor_columns)

    context = f"family={target.family} predictor={predictor.column}"
    if _legacy_bootstrap_for_test:
        bootstrap = player_cluster_bootstrap(
            rows, player_column="player_id", fit=fit_coefficients, replicates=replicates,
            seed=seed, minimum_success_rate=minimum_success_rate,
            original=original_coefficients, context=context,
        )
    else:
        cached_matrix = X_frame.to_numpy(dtype=float)
        def fit_positions(row_positions: np.ndarray) -> tuple[float, ...]:
            sample_y = y[row_positions]
            reduced_matrix, local_columns, diagnostics = _prepare_firth_bootstrap_matrix(
                cached_matrix[row_positions], sample_y, names, schema,
            )
            fitted = fit_firth_logistic(reduced_matrix, sample_y)
            if not fitted.converged:
                raise BootstrapReplicateError(
                    "nonconvergence", "Firth fit failed to converge",
                    _firth_termination_diagnostics(fitted, diagnostics),
                )
            if not np.isfinite(fitted.beta).all():
                raise BootstrapReplicateError(
                    "other_numerical_error", "Firth fit returned non-finite coefficients",
                    _firth_termination_diagnostics(fitted, diagnostics),
                )
            return tuple(float(fitted.beta[local_columns[column]]) for column in schema.predictor_columns)

        player_hashes = pd.util.hash_pandas_object(
            rows["player_id"].astype("string"), index=False,
        ).to_numpy(dtype=np.uint64)
        signature = {
            **(checkpoint_identity or {}),
            "family": target.family,
            "target_column": target.target_column,
            "predictor_column": predictor.column,
            "predictor_kind": predictor.kind,
            "predictor_columns": list(schema.predictor_columns),
            "control_columns": list(schema.control_columns),
            "design_columns": list(names),
            "design_sha256": _array_sha256(cached_matrix),
            "target_sha256": _array_sha256(y),
            "player_order_sha256": _array_sha256(player_hashes),
        }
        bootstrap = indexed_player_cluster_bootstrap(
            rows["player_id"], fit_positions=fit_positions, original=original_coefficients,
            replicates=replicates, seed=seed, minimum_success_rate=minimum_success_rate,
            checkpoint_directory=checkpoint_directory, task_signature=signature,
            context=context, progress=progress,
        )
    point = np.asarray(bootstrap.original, dtype=float)
    draws = np.asarray(bootstrap.replicates, dtype=float)
    if len(point) == 1:
        p_value = null_centered_bootstrap_p_value(float(point[0]), draws[:, 0])
    else:
        p_value = null_centered_joint_bootstrap_p_value(point, draws)
    intervals = tuple((float(low), float(high)) for low, high in np.percentile(np.exp(draws), [2.5, 97.5], axis=0).T)
    odds_ratios = np.exp(point)

    full_design = add_constant(design, has_constant="add").reindex(columns=names, fill_value=0.0).to_numpy(dtype=float)
    full_fit = original_fit
    probability_differences = []
    for column in schema.predictor_columns:
        index = names.index(column)
        reference = full_design.copy()
        contrast = full_design.copy()
        if predictor.kind == "continuous":
            contrast[:, index] += 1.0
        else:
            for predictor_column in schema.predictor_columns:
                reference[:, names.index(predictor_column)] = 0.0
                contrast[:, names.index(predictor_column)] = 0.0
            contrast[:, index] = 1.0
        p0 = 1.0 / (1.0 + np.exp(-(reference @ full_fit.beta)))
        p1 = 1.0 / (1.0 + np.exp(-(contrast @ full_fit.beta)))
        probability_differences.append(float(np.mean(p1 - p0)))
    practical = None if target.family == "star" else strict_bust_practical_effect_passes(odds_ratios)
    return ModelResult(
        target.family, predictor, schema.predictor_columns, tuple(float(v) for v in odds_ratios),
        tuple(float(v) for v in odds_ratios), tuple(float(v) for v in point), intervals,
        tuple(probability_differences), p_value,
        evidence_status(rows, target, predictor), practical, bootstrap.attempted, bootstrap.successful,
        bootstrap.failure_counts,
    )


def _firth_point_estimates(
    rows: pd.DataFrame, target: TargetDefinition, predictor: PredictorDefinition,
) -> tuple[float, ...]:
    """Convergence-checked point refit for descriptive LOSO robustness."""
    design, schema = _design(rows, predictor)
    X = add_constant(design, has_constant="add")
    fitted = fit_firth_logistic(X.to_numpy(float), rows[target.target_column].astype(float).to_numpy())
    if not fitted.converged:
        raise RuntimeError("leave-one-season-out Firth fit failed to converge")
    return tuple(float(np.exp(fitted.beta[list(X.columns).index(column)])) for column in schema.predictor_columns)


def _predictions_for_fold(train, validation, target, predictor):
    augmented, schema = _design(train, predictor)
    controls, control_schema = _control_design(train)
    validation_augmented, _ = _design(validation, predictor, schema)
    validation_controls, _ = _control_design(validation, control_schema)
    y_train = train[target.target_column].astype(float).to_numpy()
    if target.binary:
        baseline_X = add_constant(controls, has_constant="add")
        augmented_X = add_constant(augmented, has_constant="add")
        baseline_fit = fit_firth_logistic(baseline_X.to_numpy(float), y_train)
        augmented_fit = fit_firth_logistic(augmented_X.to_numpy(float), y_train)
        if not baseline_fit.converged or not augmented_fit.converged:
            raise RuntimeError("expanding-window Firth fit failed")
        baseline_validation = add_constant(validation_controls, has_constant="add").reindex(columns=baseline_X.columns, fill_value=0.0)
        augmented_validation = add_constant(validation_augmented, has_constant="add").reindex(columns=augmented_X.columns, fill_value=0.0)
        baseline = 1.0 / (1.0 + np.exp(-(baseline_validation.to_numpy(float) @ baseline_fit.beta)))
        enhanced = 1.0 / (1.0 + np.exp(-(augmented_validation.to_numpy(float) @ augmented_fit.beta)))
    else:
        baseline_X = add_constant(controls, has_constant="add")
        augmented_X = add_constant(augmented, has_constant="add")
        baseline_fit = OLS(y_train, baseline_X).fit()
        augmented_fit = OLS(y_train, augmented_X).fit()
        baseline = baseline_fit.predict(add_constant(validation_controls, has_constant="add").reindex(columns=baseline_X.columns, fill_value=0.0))
        enhanced = augmented_fit.predict(add_constant(validation_augmented, has_constant="add").reindex(columns=augmented_X.columns, fill_value=0.0))
    return validation[target.target_column].astype(float).to_numpy(), np.asarray(baseline), np.asarray(enhanced)


def incremental_validation(rows, target: TargetDefinition, predictor: PredictorDefinition) -> IncrementalResult:
    eligibility = target.eligibility_column or "_phase1_lwi_eligible"
    fold_rows = rows.copy()
    if target.eligibility_column is None:
        fold_rows[eligibility] = fold_rows[target.target_column].notna()
    folds = eligibility_aware_expanding_windows(
        fold_rows, season_column="prediction_season", eligibility_column=eligibility,
    )
    observed, baseline, augmented = [], [], []
    for fold in folds:
        train = fold_rows[fold_rows["prediction_season"].isin(fold.training_seasons)]
        validation = fold_rows[fold_rows["prediction_season"] == fold.validation_season]
        train = discovery_fit_rows(train, target, predictor.column)
        validation = discovery_fit_rows(validation, target, predictor.column)
        y, base, trait = _predictions_for_fold(train, validation, target, predictor)
        observed.extend(y); baseline.extend(base); augmented.extend(trait)
    if not observed:
        raise RuntimeError(f"no expanding-window validation predictions for {predictor.column}/{target.family}")
    y = np.asarray(observed); base = np.asarray(baseline); trait = np.asarray(augmented)
    if target.binary:
        metrics = {
            "log_loss_improvement": float(log_loss(y, base, labels=[0, 1]) - log_loss(y, trait, labels=[0, 1])),
            "brier_improvement": float(brier_score_loss(y, base) - brier_score_loss(y, trait)),
        }
        if len(np.unique(y)) == 2:
            metrics["roc_auc_improvement"] = float(roc_auc_score(y, trait) - roc_auc_score(y, base))
            metrics["pr_auc_improvement"] = float(average_precision_score(y, trait) - average_precision_score(y, base))
    else:
        metrics = {
            "mae_improvement": float(mean_absolute_error(y, base) - mean_absolute_error(y, trait)),
            "rmse_improvement": float(np.sqrt(mean_squared_error(y, base)) - np.sqrt(mean_squared_error(y, trait))),
            "out_of_window_r2_improvement": float(r2_score(y, trait) - r2_score(y, base)),
        }
    return IncrementalResult(target.family, predictor.column, len(folds), metrics)


def apply_primary_family_fdr(results: Sequence[ModelResult]) -> dict[tuple[Family, str], float]:
    output: dict[tuple[Family, str], float] = {}
    for family in ("lwi", "star", "strict_bust"):
        family_results = [result for result in results if result.family == family and result.predictor.is_cluster_representative and result.evidence.formal]
        if not family_results:
            continue
        adjusted = benjamini_hochberg([result.primary_p_value for result in family_results])
        output.update({(family, result.predictor.column): float(q) for result, q in zip(family_results, adjusted)})
    return output


def assemble_results(results: Sequence[ModelResult]) -> pd.DataFrame:
    q_values = apply_primary_family_fdr(results)
    rows = []
    for result in results:
        q = q_values.get((result.family, result.predictor.column))
        fdr_pass = q is not None and q <= DATASET2_PHASE1_BH_Q
        practical = result.practical_effect_passes
        supported = bool(result.evidence.formal and fdr_pass and (practical is None or practical))
        rows.append({
            "family": result.family,
            "predictor_column": result.predictor.column,
            "cluster_id": result.predictor.cluster_id,
            "is_cluster_representative": result.predictor.is_cluster_representative,
            "contrast_names": result.contrast_names,
            "adjusted_effects": result.estimates,
            "native_unit_effects": result.native_effects,
            "raw_outcome_effects": result.raw_outcome_effects,
            "confidence_intervals": result.confidence_intervals,
            "absolute_probability_differences": result.probability_differences,
            "primary_p_value": result.primary_p_value,
            "q_value": q,
            "passes_fdr": fdr_pass,
            "passes_practical_effect": practical,
            "evidence_gate_status": "passes_all_gates" if result.evidence.formal else result.evidence.failed_gates,
            "supported": supported,
            "bootstrap_failure_counts": result.bootstrap_failure_counts,
        })
    return pd.DataFrame(rows)


def run_phase1(
    rows: pd.DataFrame,
    predictors: Sequence[PredictorDefinition],
    predictor_whitelist: Sequence[str],
    *,
    bootstrap_replicates: int = DATASET2_FIRTH_BOOTSTRAP_REPLICATES,
    seed: int = DATASET2_PHASE1_RANDOM_SEED,
    minimum_success_rate: float = DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE,
    synthetic_test_mode: bool = False,
    checkpoint_root: Path | None = None,
    checkpoint_identity: dict[str, object] | None = None,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> Phase1Package:
    """Run all three frozen primary families on caller-supplied rows only."""
    _validated_seasons(rows)  # reject holdout before any target-specific filtering
    predictors, categorical_references = resolve_categorical_references(rows, predictors)
    validate_predictor_definitions(predictors, predictor_whitelist)
    preflight_ledger = preflight_phase1_estimability(rows, predictors, predictor_whitelist)
    fit_pairs = {
        (record.family, record.predictor_column)
        for record in preflight_ledger
        if record.disposition == "fit"
    }
    if not synthetic_test_mode and (
        bootstrap_replicates != DATASET2_FIRTH_BOOTSTRAP_REPLICATES
        or seed != DATASET2_PHASE1_RANDOM_SEED
        or minimum_success_rate != DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE
    ):
        raise ValueError("non-frozen bootstrap settings are permitted only for synthetic tests")
    lwi_target = PRIMARY_TARGETS[0]
    lwi_population = rows.loc[
        rows["prediction_season"].between(DATASET2_BUST_REFERENCE_START_SEASON, DATASET2_DISCOVERY_END_SEASON)
        & rows[lwi_target.target_column].notna()
    ]
    outcome_sd = float(lwi_population[lwi_target.target_column].std(ddof=1))
    if not np.isfinite(outcome_sd) or outcome_sd <= 0:
        raise ValueError("frozen discovery LWI outcome SD must be positive")

    model_results: list[ModelResult] = []
    incrementals: list[IncrementalResult] = []
    robustness: list[RobustnessResult] = []
    for predictor in predictors:
        for target in PRIMARY_TARGETS:
            if (target.family, predictor.column) not in fit_pairs:
                continue
            fit_rows = discovery_fit_rows(rows, target, predictor.column)
            result = _fit_lwi(fit_rows, target, predictor, outcome_sd) if target.family == "lwi" else _fit_firth(
                fit_rows, target, predictor, replicates=bootstrap_replicates,
                seed=seed, minimum_success_rate=minimum_success_rate,
                checkpoint_directory=(
                    None if checkpoint_root is None else
                    Path(checkpoint_root) / f"{target.family}__{predictor.column}"
                ),
                checkpoint_identity=checkpoint_identity,
                progress=progress,
            )
            model_results.append(result)
            incrementals.append(incremental_validation(fit_rows, target, predictor))
            # Literal leave-one-season-out estimates; no unapproved numeric tier.
            fold_estimates = []
            for season in sorted(fit_rows["prediction_season"].unique()):
                subset = fit_rows[fit_rows["prediction_season"] != season]
                estimates = _fit_lwi(subset, target, predictor, outcome_sd).estimates if target.family == "lwi" else _firth_point_estimates(
                    subset, target, predictor,
                )
                fold_estimates.append((int(season), estimates))
            statuses = []
            for index, full in enumerate(result.estimates):
                null = 0.0 if target.family == "lwi" else 1.0
                signs = [np.sign(values[index] - null) == np.sign(full - null) for _, values in fold_estimates]
                statuses.append("all_folds_same_direction" if all(signs) else "mixed_fold_directions")
            robustness.append(RobustnessResult(target.family, predictor.column, result.estimates, tuple(fold_estimates), tuple(statuses)))
    return Phase1Package(
        assemble_results(model_results),
        tuple(incrementals),
        tuple(robustness),
        categorical_references,
        preflight_ledger,
    )
