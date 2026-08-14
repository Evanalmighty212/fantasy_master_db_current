"""Governed preseason market-status evidence, separate from numeric ADP."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from config import (
    MFL_2025_ADP_SOURCE,
    MFL_2025_GOVERNED_LEAGUE_COUNT,
    MFL_2025_ORDINARY_MARKET_PARTICIPATION,
    MFL_2025_PARTICIPATION_SENSITIVITY,
)
from lib.match_quality import is_clean_match_type, validate_observed_adp_match_types

ORDINARY = "ordinary_market"
RARE_MINIMAL = "rare_minimal_market"
UNKNOWN = "participation_unknown"
STATUSES = {ORDINARY, RARE_MINIMAL, UNKNOWN}
OVERRIDE_REQUIRED = (
    "season", "player_id", "preseason_market_status", "evidence_source",
    "source_date", "evidence_summary", "approved_by",
)


def load_market_status_overrides(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"player_id": str})
    missing = sorted(set(OVERRIDE_REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"market-status override file missing columns: {missing}")
    if frame.duplicated(["season", "player_id"]).any():
        raise ValueError("market-status overrides contain duplicate player-season keys")
    if not set(frame["preseason_market_status"]).issubset(STATUSES):
        raise ValueError("market-status override contains an unknown status")
    if frame[list(OVERRIDE_REQUIRED)].isna().any().any():
        raise ValueError("market-status override evidence fields may not be null")
    return frame


def classify_participation(
    draft_selection_rate: float | None,
    *,
    ordinary_threshold: float,
) -> str:
    """Classify governed participation while retaining observed pick data."""
    if draft_selection_rate is None or pd.isna(draft_selection_rate):
        return UNKNOWN
    rate = float(draft_selection_rate)
    if not 0 <= rate <= 1 or not 0 < ordinary_threshold <= 1:
        raise ValueError("participation rates and threshold must be in [0, 1]")
    return ORDINARY if rate >= ordinary_threshold else RARE_MINIMAL


def apply_preseason_market_status(rows: pd.DataFrame, overrides: pd.DataFrame) -> pd.DataFrame:
    """Add categorical status/provenance without fabricating numeric ADP.

    A clean observed ADP is ordinary-market evidence unless a governed
    override says otherwise. Missing or conflicted evidence remains unknown.
    """
    required = {"season", "player_id", "overall_adp", "match_type"}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f"market-status input missing columns: {missing}")
    out = rows.copy()
    out["preseason_market_status"] = UNKNOWN
    out["preseason_market_status_sensitivity_30"] = UNKNOWN
    out["preseason_market_status_authority"] = "no_governed_participation_evidence"
    observed = out["overall_adp"].notna()
    validate_observed_adp_match_types(out.loc[observed, "match_type"])
    clean = observed & out["match_type"].map(is_clean_match_type)
    out.loc[clean, "preseason_market_status"] = ORDINARY
    out.loc[clean, "preseason_market_status_sensitivity_30"] = ORDINARY
    out.loc[clean, "preseason_market_status_authority"] = "clean_observed_adp_source"

    source_column = "adp_source" if "adp_source" in out.columns else "source" if "source" in out.columns else None
    governed_2025 = out["season"].eq(2025)
    if source_column is not None:
        governed_2025 &= out[source_column].eq(MFL_2025_ADP_SOURCE)
    elif governed_2025.any():
        raise ValueError("2025 market-status input must identify its governed ADP source")

    participation_columns = {
        "draft_selection_count", "draft_selection_denominator", "draft_selection_rate",
    }
    missing_participation = sorted(participation_columns - set(out.columns))
    if governed_2025.any() and missing_participation:
        raise ValueError(f"governed 2025 rows lack participation provenance columns: {missing_participation}")
    if governed_2025.any():
        count = pd.to_numeric(out.loc[governed_2025, "draft_selection_count"], errors="coerce")
        denominator = pd.to_numeric(out.loc[governed_2025, "draft_selection_denominator"], errors="coerce")
        rate = pd.to_numeric(out.loc[governed_2025, "draft_selection_rate"], errors="coerce")
        valid = (
            count.notna() & denominator.notna() & rate.notna()
            & count.ge(1) & count.le(MFL_2025_GOVERNED_LEAGUE_COUNT)
            & count.mod(1).eq(0)
            & denominator.eq(MFL_2025_GOVERNED_LEAGUE_COUNT)
            & (rate - count / MFL_2025_GOVERNED_LEAGUE_COUNT).abs().le(1e-12)
        )
        if not valid.all():
            bad_keys = out.loc[governed_2025].loc[~valid.to_numpy(), ["season", "player_id"]].to_dict("records")
            raise ValueError(f"governed 2025 rows have invalid participation provenance: {bad_keys}")
        governed_clean = governed_2025 & clean
        clean_rate = pd.to_numeric(out.loc[governed_clean, "draft_selection_rate"], errors="raise")
        out.loc[governed_clean, "preseason_market_status"] = clean_rate.map(
            lambda value: classify_participation(value, ordinary_threshold=MFL_2025_ORDINARY_MARKET_PARTICIPATION)
        ).values
        out.loc[governed_clean, "preseason_market_status_sensitivity_30"] = clean_rate.map(
            lambda value: classify_participation(value, ordinary_threshold=MFL_2025_PARTICIPATION_SENSITIVITY)
        ).values
        out.loc[governed_clean, "preseason_market_status_authority"] = "governed_draft_participation_142_leagues"

    governed = overrides[list(OVERRIDE_REQUIRED)].copy()
    merged = out.merge(governed, on=["season", "player_id"], how="left", suffixes=("", "_override"), validate="many_to_one")
    has_override = merged["preseason_market_status_override"].notna()
    merged.loc[has_override, "preseason_market_status"] = merged.loc[has_override, "preseason_market_status_override"]
    merged.loc[has_override, "preseason_market_status_sensitivity_30"] = merged.loc[has_override, "preseason_market_status_override"]
    merged.loc[has_override, "preseason_market_status_authority"] = "governed_manual_evidence"
    merged["preseason_market_status_evidence_source"] = merged["evidence_source"]
    merged["preseason_market_status_evidence_summary"] = merged["evidence_summary"]
    return merged.drop(columns=["preseason_market_status_override"])
