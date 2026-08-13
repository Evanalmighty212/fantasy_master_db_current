"""Outcome-safe Phase 1 analysis scaffolding.

Only generic mechanics live here.  No function loads repository artifacts,
and no predictor/outcome association is executed at import or by tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from config import (
    DATASET2_DISCOVERY_END_SEASON,
    DATASET2_DISCOVERY_START_SEASON,
    DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE,
    DATASET2_FIRTH_BOOTSTRAP_REPLICATES,
    DATASET2_HOLDOUT_START_SEASON,
    DATASET2_MIN_ELIGIBLE_SEASONS_BEFORE_VALIDATION,
    DATASET2_PHASE1_BH_Q,
    DATASET2_PHASE1_RANDOM_SEED,
    validate_dataset2_phase1_config,
)

validate_dataset2_phase1_config()


@dataclass(frozen=True)
class TemporalFold:
    validation_season: int
    training_seasons: tuple[int, ...]


@dataclass(frozen=True)
class BootstrapResult:
    original: object
    replicates: tuple[object, ...]
    attempted: int
    successful: int
    seed: int


def require_discovery_only(rows: pd.DataFrame, season_column: str = "prediction_season") -> None:
    seasons = pd.to_numeric(rows[season_column], errors="coerce")
    if seasons.isna().any() or not seasons.between(DATASET2_DISCOVERY_START_SEASON, DATASET2_DISCOVERY_END_SEASON).all():
        raise ValueError(
            f"Phase 1 fitting accepts only {DATASET2_DISCOVERY_START_SEASON}-"
            f"{DATASET2_DISCOVERY_END_SEASON}; protected {DATASET2_HOLDOUT_START_SEASON}+ rows are forbidden"
        )


def eligibility_aware_expanding_windows(
    rows: pd.DataFrame,
    *,
    season_column: str,
    eligibility_column: str,
    minimum_prior_seasons: int = DATASET2_MIN_ELIGIBLE_SEASONS_BEFORE_VALIDATION,
) -> tuple[TemporalFold, ...]:
    """Create prior-only folds after five seasons with eligible rows."""
    eligible = rows.loc[rows[eligibility_column].fillna(False).astype(bool)].copy()
    require_discovery_only(eligible.rename(columns={season_column: "prediction_season"}))
    seasons = sorted(pd.to_numeric(eligible[season_column], errors="raise").astype(int).unique())
    return tuple(
        TemporalFold(validation_season=season, training_seasons=tuple(seasons[:index]))
        for index, season in enumerate(seasons)
        if index >= minimum_prior_seasons
    )


def benjamini_hochberg(p_values: Iterable[float]) -> np.ndarray:
    """Return BH-adjusted q-values in original order."""
    values = np.asarray(list(p_values), dtype=float)
    if values.ndim != 1 or np.any(~np.isfinite(values)) or np.any((values < 0) | (values > 1)):
        raise ValueError("p-values must be a finite one-dimensional sequence in [0, 1]")
    order = np.argsort(values)
    ranked = values[order]
    adjusted = np.minimum.accumulate((ranked * len(values) / np.arange(1, len(values) + 1))[::-1])[::-1]
    result = np.empty_like(adjusted)
    result[order] = np.clip(adjusted, 0, 1)
    return result


def preseason_acquisition_stratum(rows: pd.DataFrame) -> pd.Series:
    """Leakage-safe categorical acquisition control; never imputes ADP."""
    required = {"preseason_market_status", "adp_round"}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f"acquisition strata input missing columns: {missing}")
    result = pd.Series("participation_unknown", index=rows.index, dtype="object")
    rare = rows["preseason_market_status"] == "rare_minimal_market"
    result.loc[rare] = "rare_minimal_market"
    ordinary = rows["preseason_market_status"] == "ordinary_market"
    rounds = pd.to_numeric(rows["adp_round"], errors="coerce")
    result.loc[ordinary & rounds.between(1, 2)] = "ordinary_R1-2"
    result.loc[ordinary & rounds.between(3, 5)] = "ordinary_R3-5"
    result.loc[ordinary & rounds.between(6, 10)] = "ordinary_R6-10"
    result.loc[ordinary & (rounds >= 11)] = "ordinary_R11+"
    if (ordinary & rounds.isna()).any():
        raise ValueError("ordinary-market rows require a real preseason ADP round; do not impute")
    return result


def player_cluster_bootstrap(
    rows: pd.DataFrame,
    *,
    player_column: str,
    fit: Callable[[pd.DataFrame], object],
    replicates: int = DATASET2_FIRTH_BOOTSTRAP_REPLICATES,
    seed: int = DATASET2_PHASE1_RANDOM_SEED,
    minimum_success_rate: float = DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE,
) -> BootstrapResult:
    """Run a player-cluster bootstrap around any convergence-aware fit.

    ``fit`` must raise on non-convergence. Resampled copies of a player are
    assigned unique bootstrap cluster IDs so duplicate draws remain distinct.
    """
    original = fit(rows.copy())
    players = pd.Index(rows[player_column].dropna().unique())
    if players.empty:
        raise ValueError("player-cluster bootstrap requires at least one player")
    rng = np.random.default_rng(seed)
    successful = []
    for _ in range(replicates):
        draws = rng.choice(players.to_numpy(), size=len(players), replace=True)
        pieces = []
        for draw_number, player in enumerate(draws):
            piece = rows.loc[rows[player_column] == player].copy()
            piece["_bootstrap_cluster_id"] = draw_number
            pieces.append(piece)
        sample = pd.concat(pieces, ignore_index=True)
        try:
            successful.append(fit(sample))
        except (RuntimeError, ValueError, np.linalg.LinAlgError):
            continue
    if len(successful) / replicates < minimum_success_rate:
        raise RuntimeError(
            f"bootstrap success rate {len(successful)}/{replicates} is below {minimum_success_rate:.1%}"
        )
    return BootstrapResult(original, tuple(successful), replicates, len(successful), seed)


def star_evidence_survives_bh(raw_p_value: float, family_p_values: Iterable[float]) -> bool:
    """Gate Star evidence on BH q<=0.10; effect sizes remain reported, not gated."""
    values = list(family_p_values)
    matches = [index for index, value in enumerate(values) if value == raw_p_value]
    if not matches:
        raise ValueError("raw_p_value must be included in family_p_values")
    return bool(benjamini_hochberg(values)[matches[0]] <= DATASET2_PHASE1_BH_Q)
