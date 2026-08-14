import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MFL_2025_ADP_SOURCE

from lib.preseason_market_status import (
    ORDINARY,
    OVERRIDE_REQUIRED,
    RARE_MINIMAL,
    UNKNOWN,
    apply_preseason_market_status,
    classify_participation,
    load_market_status_overrides,
)


def test_vick_is_categorical_minimal_market_without_numeric_adp():
    overrides = load_market_status_overrides("data/manual/preseason_market_status_overrides.csv")
    rows = pd.DataFrame([{
        "season": 2010, "player_id": "00-0020245", "overall_adp": None,
        "match_type": None,
    }])
    result = apply_preseason_market_status(rows, overrides).iloc[0]
    assert result["preseason_market_status"] == RARE_MINIMAL
    assert pd.isna(result["overall_adp"])
    assert result["preseason_market_status_authority"] == "governed_manual_evidence"


def test_clean_observed_adp_is_ordinary_but_conflict_is_unknown():
    rows = pd.DataFrame([
        {"season": 2012, "player_id": "A", "overall_adp": 20.0, "match_type": "exact_name_position"},
        {"season": 2012, "player_id": "B", "overall_adp": 20.0, "match_type": "exact_name_position_mismatch"},
    ])
    empty = pd.DataFrame(columns=[
        "season", "player_id", "preseason_market_status", "evidence_source",
        "source_date", "evidence_summary", "approved_by",
    ])
    result = apply_preseason_market_status(rows, empty).set_index("player_id")
    assert result.loc["A", "preseason_market_status"] == ORDINARY
    assert result.loc["B", "preseason_market_status"] == UNKNOWN


def test_governed_participation_boundary_is_inclusive_without_changing_pick():
    assert classify_participation(0.35, ordinary_threshold=0.35) == ORDINARY
    assert classify_participation(0.3499, ordinary_threshold=0.35) == RARE_MINIMAL


def test_governed_participation_overrides_presence_in_source_list():
    rows = pd.DataFrame([{
        "season": 2025, "player_id": "DEEP", "overall_adp": 210.5,
        "match_type": "exact_name_position", "adp_source": MFL_2025_ADP_SOURCE,
        "draft_selection_count": 29, "draft_selection_denominator": 142,
        "draft_selection_rate": 29 / 142,
    }])
    empty = pd.DataFrame(columns=[
        "season", "player_id", "preseason_market_status", "evidence_source",
        "source_date", "evidence_summary", "approved_by",
    ])
    result = apply_preseason_market_status(rows, empty).iloc[0]
    assert result["preseason_market_status"] == RARE_MINIMAL
    assert result["overall_adp"] == 210.5  # conditional pick retained as provenance


def test_governed_142_denominator_and_35_30_boundaries_are_explicit():
    rows = pd.DataFrame([
        {"season": 2025, "player_id": "P50", "overall_adp": 180.0,
         "match_type": "exact_name_position", "adp_source": MFL_2025_ADP_SOURCE,
         "draft_selection_count": 50, "draft_selection_denominator": 142,
         "draft_selection_rate": 50 / 142},
        {"season": 2025, "player_id": "P43", "overall_adp": 190.0,
         "match_type": "exact_name_position", "adp_source": MFL_2025_ADP_SOURCE,
         "draft_selection_count": 43, "draft_selection_denominator": 142,
         "draft_selection_rate": 43 / 142},
        {"season": 2025, "player_id": "P42", "overall_adp": 200.0,
         "match_type": "exact_name_position", "adp_source": MFL_2025_ADP_SOURCE,
         "draft_selection_count": 42, "draft_selection_denominator": 142,
         "draft_selection_rate": 42 / 142},
    ])
    empty = pd.DataFrame(columns=list(OVERRIDE_REQUIRED))
    result = apply_preseason_market_status(rows, empty).set_index("player_id")
    assert result.loc["P50", "preseason_market_status"] == ORDINARY
    assert result.loc["P43", "preseason_market_status"] == RARE_MINIMAL
    assert result.loc["P43", "preseason_market_status_sensitivity_30"] == ORDINARY
    assert result.loc["P42", "preseason_market_status_sensitivity_30"] == RARE_MINIMAL


def test_governed_2025_missing_or_inconsistent_participation_fails_loudly():
    base = {"season": 2025, "player_id": "A", "overall_adp": 20.0,
            "match_type": "exact_name_position", "adp_source": MFL_2025_ADP_SOURCE}
    empty = pd.DataFrame(columns=list(OVERRIDE_REQUIRED))
    with pytest.raises(ValueError, match="lack participation provenance"):
        apply_preseason_market_status(pd.DataFrame([base]), empty)
    invalid = {**base, "draft_selection_count": 50, "draft_selection_denominator": 141,
               "draft_selection_rate": 50 / 142}
    with pytest.raises(ValueError, match="invalid participation provenance"):
        apply_preseason_market_status(pd.DataFrame([invalid]), empty)


def test_governed_participation_does_not_override_identity_conflict():
    row = {"season": 2025, "player_id": "CONFLICT", "overall_adp": 20.0,
           "match_type": "exact_name_position_mismatch", "adp_source": MFL_2025_ADP_SOURCE,
           "draft_selection_count": 100, "draft_selection_denominator": 142,
           "draft_selection_rate": 100 / 142}
    empty = pd.DataFrame(columns=list(OVERRIDE_REQUIRED))
    result = apply_preseason_market_status(pd.DataFrame([row]), empty).iloc[0]
    assert result["preseason_market_status"] == UNKNOWN
    assert result["preseason_market_status_sensitivity_30"] == UNKNOWN


def test_unmatched_2025_player_is_unknown_without_fabricated_participation():
    rows = pd.DataFrame([{"season": 2025, "player_id": "ABSENT", "overall_adp": None,
                          "match_type": None, "adp_source": None}])
    empty = pd.DataFrame(columns=list(OVERRIDE_REQUIRED))
    result = apply_preseason_market_status(rows, empty).iloc[0]
    assert result["preseason_market_status"] == UNKNOWN
    assert pd.isna(result["overall_adp"])
    assert "draft_selection_rate" not in result.index
