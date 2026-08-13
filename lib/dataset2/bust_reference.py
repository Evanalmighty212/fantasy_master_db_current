"""Discovery-only fit and frozen application for Dataset 2 bust ranks.

This module deliberately knows nothing about predictor columns.  It fits
only on eligible 2010-2020 outcome rows, serializes the complete empirical
reference, and applies that immutable reference to any later rows without
re-ranking or recalibrating on them.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from config import (
    DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE,
    DATASET2_BUST_REFERENCE_END_SEASON,
    DATASET2_BUST_REFERENCE_START_SEASON,
    DATASET2_BUST_REFERENCE_VERSION,
)

REQUIRED_COLUMNS = (
    "outcome_season", "position", "adp_round", "games_played",
    "bust_primary_eligible", "score_like", "P",
)


def _bucket(adp_round: Any) -> str | None:
    from config import DATASET2_ADP_ROUND_BUCKETS

    if pd.isna(adp_round):
        return None
    for label, lo, hi in DATASET2_ADP_ROUND_BUCKETS:
        if adp_round >= lo and (hi is None or adp_round <= hi):
            return label
    return None


def _era(season: int) -> str:
    return "pre-2011" if season < 2011 else "2011+"


def _key(*values: Any) -> str:
    return "|".join(str(value) for value in values)


def _finite_sorted(values: pd.Series) -> list[float]:
    numeric = pd.to_numeric(values, errors="coerce")
    return sorted(float(value) for value in numeric[np.isfinite(numeric)])


def reference_sha256(reference: dict) -> str:
    payload = {key: value for key, value in reference.items() if key != "sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def fit_bust_reference(rows: pd.DataFrame) -> dict:
    """Fit the governed bust reference on eligible discovery rows only."""
    missing = sorted(set(REQUIRED_COLUMNS) - set(rows.columns))
    if missing:
        raise ValueError(f"bust reference input missing columns: {missing}")
    seasons = pd.to_numeric(rows["outcome_season"], errors="coerce")
    discovery = rows.loc[
        seasons.between(DATASET2_BUST_REFERENCE_START_SEASON, DATASET2_BUST_REFERENCE_END_SEASON)
        & rows["bust_primary_eligible"].fillna(False).astype(bool)
    ].copy()
    if discovery.empty:
        # Eligibility-only and automatic-zero-game unit/application
        # frames need no percentile distribution. A nonzero eligible
        # row still requires a separately fitted discovery reference.
        rankable = rows["bust_primary_eligible"].fillna(False).astype(bool) & (rows["games_played"] != 0) & (
            rows["score_like"].notna() | rows["P"].notna()
        )
        if rankable.any():
            raise ValueError("bust reference has no eligible 2010-2020 discovery rows")
        reference = {
            "reference_version": DATASET2_BUST_REFERENCE_VERSION,
            "fit_start_season": DATASET2_BUST_REFERENCE_START_SEASON,
            "fit_end_season": DATASET2_BUST_REFERENCE_END_SEASON,
            "eligible_fit_rows": 0,
            "minimum_era_cell_size": DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE,
            "rank_method": "average_inclusive_empirical",
            "era_score_distributions": {}, "pooled_score_distributions": {},
            "pooled_raw_p_distributions": {},
        }
        reference["sha256"] = reference_sha256(reference)
        return reference
    discovery["_bucket"] = discovery["adp_round"].map(_bucket)
    discovery["_era"] = discovery["outcome_season"].astype(int).map(_era)
    score_rows = discovery[(discovery["games_played"] != 0) & discovery["score_like"].notna()]
    raw_rows = discovery[(discovery["games_played"] != 0) & discovery["P"].notna()]

    era_scores: dict[str, list[float]] = {}
    pooled_scores: dict[str, list[float]] = {}
    pooled_raw_p: dict[str, list[float]] = {}
    for keys, group in score_rows.groupby(["position", "_bucket", "_era"], dropna=False):
        values = _finite_sorted(group["score_like"])
        if len(values) >= DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE:
            era_scores[_key(*keys)] = values
    for keys, group in score_rows.groupby(["position", "_bucket"], dropna=False):
        pooled_scores[_key(*keys)] = _finite_sorted(group["score_like"])
    for keys, group in raw_rows.groupby(["position", "_bucket"], dropna=False):
        pooled_raw_p[_key(*keys)] = _finite_sorted(group["P"])

    reference = {
        "reference_version": DATASET2_BUST_REFERENCE_VERSION,
        "fit_start_season": DATASET2_BUST_REFERENCE_START_SEASON,
        "fit_end_season": DATASET2_BUST_REFERENCE_END_SEASON,
        "eligible_fit_rows": int(len(discovery)),
        "minimum_era_cell_size": DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE,
        "rank_method": "average_inclusive_empirical",
        "era_score_distributions": era_scores,
        "pooled_score_distributions": pooled_scores,
        "pooled_raw_p_distributions": pooled_raw_p,
    }
    reference["sha256"] = reference_sha256(reference)
    return reference


def validate_bust_reference(reference: dict) -> None:
    if reference.get("reference_version") != DATASET2_BUST_REFERENCE_VERSION:
        raise ValueError("unexpected bust reference version")
    if reference.get("fit_start_season") != DATASET2_BUST_REFERENCE_START_SEASON or reference.get("fit_end_season") != DATASET2_BUST_REFERENCE_END_SEASON:
        raise ValueError("bust reference temporal window is not the governed 2010-2020 window")
    if reference.get("sha256") != reference_sha256(reference):
        raise ValueError("bust reference hash mismatch")


def empirical_average_percentile(value: float, distribution: list[float]) -> float:
    """Average-rank percentile against a frozen empirical distribution."""
    if not distribution or not np.isfinite(value):
        return np.nan
    values = np.asarray(distribution, dtype=float)
    less = int(np.searchsorted(values, value, side="left"))
    less_or_equal = int(np.searchsorted(values, value, side="right"))
    equal = less_or_equal - less
    # Reproduces pandas rank(pct=True, method="average") for fit rows;
    # a novel value receives its deterministic insertion rank.
    rank = less + ((equal + 1) / 2 if equal else 1)
    return min(rank / len(values), 1.0)


def apply_bust_reference(rows: pd.DataFrame, reference: dict) -> pd.DataFrame:
    """Return frozen percentiles/methods; values in ``rows`` never fit it."""
    validate_bust_reference(reference)
    out = pd.DataFrame(index=rows.index)
    out["bust_reference_percentile"] = pd.Series(pd.NA, index=rows.index, dtype="Float64")
    out["bust_primary_assignment_method"] = pd.Series(pd.NA, index=rows.index, dtype="object")
    eligible = rows["bust_primary_eligible"].fillna(False).astype(bool)
    for idx, row in rows.loc[eligible].iterrows():
        if row["games_played"] == 0:
            out.at[idx, "bust_primary_assignment_method"] = "automatic_zero_game"
            continue
        bucket = _bucket(row["adp_round"])
        era_key = _key(row["position"], bucket, _era(int(row["outcome_season"])))
        pooled_key = _key(row["position"], bucket)
        if pd.notna(row["score_like"]):
            if era_key in reference["era_score_distributions"]:
                distribution = reference["era_score_distributions"][era_key]
                method = "era_specific_g_score"
            else:
                distribution = reference["pooled_score_distributions"].get(pooled_key, [])
                method = "pooled_era_g_score_fallback"
            value = row["score_like"]
        elif pd.notna(row["P"]):
            distribution = reference["pooled_raw_p_distributions"].get(pooled_key, [])
            method = "g_raw_lookup_gap_fallback"
            value = row["P"]
        else:
            continue
        percentile = empirical_average_percentile(float(value), distribution)
        if np.isfinite(percentile):
            out.at[idx, "bust_reference_percentile"] = percentile
            out.at[idx, "bust_primary_assignment_method"] = method
    return out
