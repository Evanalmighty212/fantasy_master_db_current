"""Outcome-safe Phase 1 analysis scaffolding.

Only generic mechanics live here.  No function loads repository artifacts,
and no predictor/outcome association is executed at import or by tests.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from config import (
    DATASET2_DISCOVERY_END_SEASON,
    DATASET2_DISCOVERY_START_SEASON,
    DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE,
    DATASET2_FIRTH_BOOTSTRAP_REPLICATES,
    DATASET2_FIRTH_BOOTSTRAP_BATCH_SIZE,
    DATASET2_HOLDOUT_START_SEASON,
    DATASET2_MIN_ELIGIBLE_SEASONS_BEFORE_VALIDATION,
    DATASET2_PHASE1_BH_Q,
    DATASET2_PHASE1_RANDOM_SEED,
    validate_dataset2_phase1_config,
)

validate_dataset2_phase1_config()

BOOTSTRAP_FAILURE_CATEGORIES = (
    "rank_failure",
    "missing_predictor_contrast",
    "missing_target_signal",
    "non_finite_likelihood",
    "nonconvergence",
    "other_numerical_error",
)


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
    failure_counts: tuple[tuple[str, int], ...]


class BootstrapReplicateError(RuntimeError):
    """A classified, auditable failure of one bootstrap replicate."""

    def __init__(
        self, category: str, detail: str, diagnostics: dict[str, object] | None = None,
    ):
        super().__init__(detail)
        self.category = category
        self.diagnostics = diagnostics or {}


def _canonical_json(value: object) -> str:
    def convert(item):
        if isinstance(item, np.generic):
            return item.item()
        if isinstance(item, np.ndarray):
            return item.tolist()
        raise TypeError(f"Object of type {type(item).__name__} is not JSON serializable")
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=convert,
    )


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(_canonical_json(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _signature_hash(signature: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(signature).encode("utf-8")).hexdigest()


def _classified_bootstrap_fit(
    fit: Callable[[np.ndarray], object], row_positions: np.ndarray,
) -> tuple[str, object | None, dict[str, object] | None]:
    try:
        return "success", fit(row_positions), None
    except BootstrapReplicateError as exc:
        return exc.category, None, exc.diagnostics
    except np.linalg.LinAlgError:
        return "other_numerical_error", None, {"termination_reason": "linear_algebra_error"}
    except FloatingPointError:
        return "other_numerical_error", None, {"termination_reason": "floating_point_error"}
    except RuntimeError as exc:
        category = "nonconvergence" if "converg" in str(exc).lower() else "other_numerical_error"
        return category, None, {"termination_reason": "unclassified_runtime_error"}
    except ValueError:
        return "other_numerical_error", None, {"termination_reason": "unclassified_value_error"}


def _termination_reason_counts(records: dict[int, tuple[str, object | None, dict[str, object] | None]]):
    counts: Counter[str] = Counter()
    for status, _, diagnostics in records.values():
        if status == "success":
            continue
        reason = (diagnostics or {}).get("termination_reason") or "not_recorded"
        counts[str(reason)] += 1
    return dict(sorted(counts.items()))


def indexed_player_cluster_bootstrap(
    player_values: Iterable[object],
    *,
    fit_positions: Callable[[np.ndarray], object],
    original: object,
    replicates: int = DATASET2_FIRTH_BOOTSTRAP_REPLICATES,
    seed: int = DATASET2_PHASE1_RANDOM_SEED,
    minimum_success_rate: float = DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE,
    batch_size: int = DATASET2_FIRTH_BOOTSTRAP_BATCH_SIZE,
    checkpoint_directory: Path | None = None,
    task_signature: dict[str, object] | None = None,
    context: str = "bootstrap fit",
    progress: Callable[[dict[str, object]], None] | None = None,
) -> BootstrapResult:
    """Exact player-block bootstrap using cached row positions and resumable batches."""
    values = np.asarray(list(player_values), dtype=object)
    players = pd.Index(pd.Series(values, dtype="object").dropna().unique())
    if players.empty:
        raise ValueError("player-cluster bootstrap requires at least one player")
    if batch_size <= 0:
        raise ValueError("bootstrap batch size must be positive")
    row_blocks = tuple(np.flatnonzero(values == player) for player in players)
    signature = {
        **(task_signature or {}),
        "bootstrap_engine": "indexed_player_blocks_v1",
        "failure_diagnostic_schema": "failed_fit_diagnostics_v1",
        "replicates": replicates,
        "seed": seed,
        "minimum_success_rate": minimum_success_rate,
        "batch_size": batch_size,
        "player_count": len(players),
        "row_count": len(values),
    }
    signature_digest = _signature_hash(signature)
    if checkpoint_directory is not None:
        checkpoint_directory = Path(checkpoint_directory)
        manifest_path = checkpoint_directory / "task_manifest.json"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing != {"signature": signature, "signature_sha256": signature_digest}:
                raise RuntimeError(f"checkpoint signature mismatch for {context}")
        else:
            checkpoint_directory.mkdir(parents=True, exist_ok=True)
            _atomic_json(manifest_path, {"signature": signature, "signature_sha256": signature_digest})

    rng = np.random.default_rng(seed)
    records: dict[int, tuple[str, object | None, dict[str, object] | None]] = {}
    batch_count = (replicates + batch_size - 1) // batch_size
    for batch_number in range(batch_count):
        start = batch_number * batch_size
        stop = min(replicates, start + batch_size)
        batch_draws = [
            rng.choice(len(players), size=len(players), replace=True)
            for _ in range(start, stop)
        ]
        batch_path = None if checkpoint_directory is None else checkpoint_directory / f"batch_{start:04d}_{stop - 1:04d}.json"
        if batch_path is not None and batch_path.exists():
            payload = json.loads(batch_path.read_text(encoding="utf-8"))
            if payload.get("signature_sha256") != signature_digest or payload.get("start") != start or payload.get("stop") != stop:
                raise RuntimeError(f"invalid bootstrap checkpoint batch for {context}: {batch_path}")
            batch_records = payload.get("records", [])
            if len(batch_records) != stop - start:
                raise RuntimeError(f"incomplete bootstrap checkpoint batch for {context}: {batch_path}")
        else:
            batch_records = []
            for replicate_index, draws in zip(range(start, stop), batch_draws):
                positions = np.concatenate([row_blocks[int(draw)] for draw in draws])
                status, value, diagnostics = _classified_bootstrap_fit(fit_positions, positions)
                record = {
                    "replicate_index": replicate_index,
                    "status": status,
                    "value": value,
                }
                if status != "success":
                    record["diagnostics"] = diagnostics or {"termination_reason": "not_recorded"}
                batch_records.append(record)
            if batch_path is not None:
                _atomic_json(batch_path, {
                    "signature_sha256": signature_digest,
                    "start": start,
                    "stop": stop,
                    "records": batch_records,
                })
        for record in batch_records:
            index = int(record["replicate_index"])
            if index in records or not start <= index < stop:
                raise RuntimeError(f"duplicate/out-of-range bootstrap checkpoint record for {context}")
            records[index] = (
                str(record["status"]), record.get("value"), record.get("diagnostics"),
            )
        if progress is not None:
            success_so_far = sum(status == "success" for status, _, _ in records.values())
            failures_so_far = Counter(
                status for status, _, _ in records.values() if status != "success"
            )
            progress({
                "context": context,
                "completed_batches": batch_number + 1,
                "total_batches": batch_count,
                "attempted": len(records),
                "successful": success_so_far,
                "failure_counts": {
                    category: int(failures_so_far.get(category, 0))
                    for category in BOOTSTRAP_FAILURE_CATEGORIES
                },
                "termination_reason_counts": _termination_reason_counts(records),
            })

    if tuple(sorted(records)) != tuple(range(replicates)):
        raise RuntimeError(f"bootstrap checkpoint coverage is incomplete for {context}")
    failures: Counter[str] = Counter({category: 0 for category in BOOTSTRAP_FAILURE_CATEGORIES})
    successful = []
    for index in range(replicates):
        status, value, _ = records[index]
        if status == "success":
            successful.append(tuple(value) if isinstance(value, list) else value)
        elif status in failures:
            failures[status] += 1
        else:
            raise RuntimeError(f"unknown bootstrap failure category for {context}: {status}")
    failure_counts = tuple(sorted(failures.items()))
    if len(successful) / replicates < minimum_success_rate:
        termination_reasons = _termination_reason_counts(records)
        raise RuntimeError(
            f"bootstrap success rate {len(successful)}/{replicates} is below "
            f"{minimum_success_rate:.1%} for {context}; failures={dict(failure_counts)}; "
            f"termination_reasons={termination_reasons}"
        )
    result = BootstrapResult(original, tuple(successful), replicates, len(successful), seed, failure_counts)
    if checkpoint_directory is not None:
        _atomic_json(checkpoint_directory / "task_complete.json", {
            "signature_sha256": signature_digest,
            "attempted": replicates,
            "successful": len(successful),
            "failure_counts": dict(failure_counts),
            "termination_reason_counts": _termination_reason_counts(records),
        })
    return result


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
    original: object | None = None,
    context: str = "bootstrap fit",
) -> BootstrapResult:
    """Run a player-cluster bootstrap around any convergence-aware fit.

    ``fit`` must raise on non-convergence. Resampled copies of a player are
    assigned unique bootstrap cluster IDs so duplicate draws remain distinct.
    """
    if original is None:
        original = fit(rows.copy())
    players = pd.Index(rows[player_column].dropna().unique())
    if players.empty:
        raise ValueError("player-cluster bootstrap requires at least one player")
    rng = np.random.default_rng(seed)
    successful = []
    failures: Counter[str] = Counter({category: 0 for category in BOOTSTRAP_FAILURE_CATEGORIES})
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
        except BootstrapReplicateError as exc:
            failures[exc.category] += 1
            continue
        except np.linalg.LinAlgError:
            failures["other_numerical_error"] += 1
            continue
        except FloatingPointError:
            failures["other_numerical_error"] += 1
            continue
        except RuntimeError as exc:
            category = "nonconvergence" if "converg" in str(exc).lower() else "other_numerical_error"
            failures[category] += 1
            continue
        except ValueError:
            failures["other_numerical_error"] += 1
            continue
    failure_counts = tuple(sorted(failures.items()))
    if len(successful) / replicates < minimum_success_rate:
        raise RuntimeError(
            f"bootstrap success rate {len(successful)}/{replicates} is below "
            f"{minimum_success_rate:.1%} for {context}; failures={dict(failure_counts)}"
        )
    return BootstrapResult(
        original, tuple(successful), replicates, len(successful), seed, failure_counts,
    )


def star_evidence_survives_bh(raw_p_value: float, family_p_values: Iterable[float]) -> bool:
    """Gate Star evidence on BH q<=0.10; effect sizes remain reported, not gated."""
    values = list(family_p_values)
    matches = [index for index, value in enumerate(values) if value == raw_p_value]
    if not matches:
        raise ValueError("raw_p_value must be included in family_p_values")
    return bool(benjamini_hochberg(values)[matches[0]] <= DATASET2_PHASE1_BH_Q)
