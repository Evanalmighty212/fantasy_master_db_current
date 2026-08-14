"""Shared semantic classification for player-identity match outcomes."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


# These literals are emitted by scripts/player_matching.py. Clean means the
# identity was explicitly adjudicated or met the governed high-confidence
# rule; review-only matches must never be silently promoted into this set.
CLEAN_MATCH_TYPES = frozenset({
    "manual_override",
    "roster_directory_exact",
    "exact_name_position",
    "fuzzy_high_confidence",
})
REVIEW_MATCH_TYPES = frozenset({
    "exact_name_position_mismatch",
    "fuzzy_low_confidence",
})
KNOWN_MATCH_TYPES = CLEAN_MATCH_TYPES | REVIEW_MATCH_TYPES


def is_clean_match_type(match_type: object) -> bool:
    """Return whether a matcher literal is governed high-confidence evidence."""
    return isinstance(match_type, str) and match_type in CLEAN_MATCH_TYPES


def validate_observed_adp_match_types(match_types: Iterable[object]) -> None:
    """Fail if an observed-ADP row carries an unknown or missing match type."""
    unknown = sorted({str(value) for value in match_types if value not in KNOWN_MATCH_TYPES})
    if unknown:
        raise ValueError(f"observed ADP rows contain unknown match_type values: {unknown}")


def data_quality_flag(overall_adp: object, match_type: object) -> str:
    """Map observed ADP and match semantics to the master quality contract."""
    if pd.isna(overall_adp):
        return "no_adp_match"
    validate_observed_adp_match_types([match_type])
    return "matched_clean" if is_clean_match_type(match_type) else "matched_needs_review"
