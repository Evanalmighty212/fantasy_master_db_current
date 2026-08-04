"""
tests/test_dataset2_analysis_view.py

Protects lib/dataset2/analysis_view.py -- artifact 3 of the
three-artifact architecture. Proves: the join grain is exactly one row
per (prediction_season, player_id) with the predictor spine fully
preserved; unmatched (future) rows get null outcome fields -- NEVER
False; the four outcome states stay unambiguous; the predictor
whitelist and target registry are derived correctly and never include
labels/eligibility/reasons/assignment methods/SBV components; no
_x/_y suffixes or duplicate columns; determinism and input-order
independence; and mutation isolation between the two source tables.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
import scripts.build_dataset2_analysis_view as analysis_view_driver
from lib.dataset2.analysis_view import (
    OUTCOME_JOIN_STATUS_MATCHED,
    OUTCOME_JOIN_STATUS_NO_MATCH,
    TARGET_REGISTRY,
    build_dataset2_analysis_view,
)


class TestRequiredVerificationCounts:
    def test_strict_bust_expectation_tracks_directory_first_identity_repair(self):
        assert analysis_view_driver.EXPECTED_STRICT_BUST_POSITIVE_COUNT == 102
        assert analysis_view_driver.STRICT_BUST_COUNT_AUDIT_KEY.endswith("_matches_102")

    @pytest.mark.skipif(
        not analysis_view_driver.JOIN_AUDIT_PATH.exists(),
        reason="regenerated Dataset 2 analysis-view audit artifact is unavailable",
    )
    def test_live_audit_records_the_approved_strict_bust_count(self):
        audit = pd.read_csv(analysis_view_driver.JOIN_AUDIT_PATH, index_col=0)["value"]
        assert str(audit.loc[analysis_view_driver.STRICT_BUST_COUNT_AUDIT_KEY]).lower() == "true"
        assert "bust_strict_below_replacement_label_positive_matches_103" not in audit.index


def _predictor(*rows, extra_cols=None):
    """rows: (prediction_season, player_id, position, fam1_trait)."""
    out_rows = []
    for r in rows:
        ps, pid, pos, trait = r
        out_rows.append({
            "prediction_season": ps, "player_id": pid, "position": pos,
            "canonical_position_status": "adp_source",
            "canonical_position_authority": "adp_source_position",
            "historical_input_revision": "test-revision",
            "observation_season": ps - 1, "fam1_trait": trait,
        })
    cols = [
        "prediction_season", "player_id", "position", "canonical_position_status",
        "canonical_position_authority", "historical_input_revision", "observation_season", "fam1_trait",
    ]
    df = pd.DataFrame(out_rows, columns=cols) if out_rows else pd.DataFrame(columns=cols)
    return df


def _predictor_registry():
    return pd.DataFrame(
        [
            {"canonical_column": "prediction_season", "family_number": "N/A (spine)"},
            {"canonical_column": "player_id", "family_number": "N/A (spine)"},
            {"canonical_column": "position", "family_number": "N/A (spine)"},
            {"canonical_column": "canonical_position_status", "family_number": "N/A (spine)"},
            {"canonical_column": "canonical_position_authority", "family_number": "N/A (spine)"},
            {"canonical_column": "historical_input_revision", "family_number": "N/A (spine)"},
            {"canonical_column": "observation_season", "family_number": "N/A (spine)"},
            {"canonical_column": "fam1_trait", "family_number": "1"},
        ]
    )


def _outcome(*rows):
    """rows: (outcome_season, player_id, position, real_status, star_eligible, star_label,
    bust_eligible, bust_label, bust25, bust30, strict_eligible, strict_label, diag_eligible, diag_value)."""
    cols = (
        "outcome_season", "player_id", "position", "canonical_position_status",
        "canonical_position_authority", "historical_input_revision",
        "real_status", "has_real_market_adp", "adp_round",
        "star_outcome_eligible", "star_outcome_ineligibility_reason", "star_by_value_label",
        "sbv_score_available", "star_by_value_score",
        "bust_primary_eligible", "bust_primary_ineligibility_reason", "bust_primary_assignment_method",
        "bust_primary_label", "bust_primary_sensitivity_pct25_label", "bust_primary_sensitivity_pct30_label",
        "bust_strict_below_replacement_eligible", "bust_strict_below_replacement_ineligibility_reason",
        "bust_strict_below_replacement_label",
        "bust_historical_sensitivity_eligible", "bust_historical_sensitivity_ineligibility_reason",
        "bust_historical_sensitivity_label",
        "underperformance_diagnostic_eligible", "underperformance_diagnostic_ineligibility_reason",
        "underperformance_diagnostic_value",
    )
    if not rows:
        return pd.DataFrame(columns=cols)
    out_rows = []
    for r in rows:
        (os_, pid, pos, status, star_elig, star_lbl, bust_elig, bust_lbl, bust25, bust30,
         strict_elig, strict_lbl, diag_elig, diag_val) = r
        out_rows.append(
            {
                "outcome_season": os_, "player_id": pid, "position": pos, "real_status": status,
                "canonical_position_status": "adp_source",
                "canonical_position_authority": "adp_source_position",
                "historical_input_revision": "test-revision",
                "has_real_market_adp": True, "adp_round": 5,
                "star_outcome_eligible": star_elig, "star_outcome_ineligibility_reason": None if star_elig else "x",
                "star_by_value_label": star_lbl,
                "sbv_score_available": True, "star_by_value_score": 10.0,
                "bust_primary_eligible": bust_elig, "bust_primary_ineligibility_reason": None if bust_elig else "x",
                "bust_primary_assignment_method": "era_specific_g_score" if bust_elig else None,
                "bust_primary_label": bust_lbl,
                "bust_primary_sensitivity_pct25_label": bust25,
                "bust_primary_sensitivity_pct30_label": bust30,
                "bust_strict_below_replacement_eligible": strict_elig,
                "bust_strict_below_replacement_ineligibility_reason": None if strict_elig else "x",
                "bust_strict_below_replacement_label": strict_lbl,
                "bust_historical_sensitivity_eligible": True,
                "bust_historical_sensitivity_ineligibility_reason": None,
                "bust_historical_sensitivity_label": pd.NA,
                "underperformance_diagnostic_eligible": diag_elig,
                "underperformance_diagnostic_ineligibility_reason": None if diag_elig else "x",
                "underperformance_diagnostic_value": diag_val,
            }
        )
    return pd.DataFrame(out_rows, columns=cols)


class TestJoinGrain:
    def test_left_join_preserves_full_predictor_spine(self):
        predictor = _predictor((2015, "P1", "RB", 1.0), (2026, "P2", "WR", 2.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        assert len(view) == 2
        assert set(zip(view["prediction_season"], view["player_id"])) == {(2015, "P1"), (2026, "P2")}

    def test_no_duplicate_keys_in_view(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        assert view.duplicated(subset=["prediction_season", "player_id"]).sum() == 0

    def test_predictor_only_row_gets_no_outcome_row_matched_status(self):
        predictor = _predictor((2026, "FUTURE", "RB", 1.0))
        outcome = _outcome()
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        row = view.iloc[0]
        assert row["outcome_join_status"] == OUTCOME_JOIN_STATUS_NO_MATCH

    def test_matched_row_gets_outcome_matched_status(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        assert view.iloc[0]["outcome_join_status"] == OUTCOME_JOIN_STATUS_MATCHED


class TestOutcomeHandlingForUnmatchedRows:
    def test_every_target_and_eligibility_field_is_null_not_false(self):
        predictor = _predictor((2026, "FUTURE", "RB", 1.0))
        outcome = _outcome()
        view, _, targets, _ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        row = view.iloc[0]
        for target in targets:
            assert pd.isna(row[target["target_column"]]), f"{target['target_column']} should be null, not False"
            assert pd.isna(row[target["eligibility_column"]]), f"{target['eligibility_column']} should be null"

    def test_unmatched_boolean_columns_are_real_na_not_false(self):
        predictor = _predictor((2026, "FUTURE", "RB", 1.0))
        outcome = _outcome()
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        row = view.iloc[0]
        assert row["star_by_value_label"] is pd.NA or pd.isna(row["star_by_value_label"])
        # A real pd.NA raises on a direct boolean comparison rather than
        # silently resolving to False -- proves this is genuinely
        # missing, not a coerced False. A plain Python False would not
        # raise here.
        with pytest.raises(TypeError):
            bool(row["star_by_value_label"] != False)  # noqa: E712

    def test_four_outcome_states_are_distinguishable(self):
        predictor = _predictor(
            (2026, "NOTYET", "RB", 1.0),   # 1. outcome not yet available
            (2015, "INELIG", "RB", 1.0),   # 2. outcome exists, target ineligible
            (2015, "FALSE", "RB", 1.0),    # 3. outcome eligible, label False
            (2015, "TRUE", "RB", 1.0),     # 4. outcome eligible, label True
        )
        outcome = _outcome(
            (2015, "INELIG", "RB", "out_of_scope", False, None, False, None, None, None, False, None, False, None),
            (2015, "FALSE", "RB", "below_production_gate", True, False, True, False, False, False, True, False, True, -5.0),
            (2015, "TRUE", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0),
        )
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        by_id = view.set_index("player_id")

        notyet = by_id.loc["NOTYET"]
        assert notyet["outcome_join_status"] == OUTCOME_JOIN_STATUS_NO_MATCH
        assert pd.isna(notyet["star_outcome_eligible"])
        assert pd.isna(notyet["star_by_value_label"])

        inelig = by_id.loc["INELIG"]
        assert inelig["outcome_join_status"] == OUTCOME_JOIN_STATUS_MATCHED
        assert inelig["star_outcome_eligible"] == False  # noqa: E712
        assert pd.isna(inelig["star_by_value_label"])

        false_row = by_id.loc["FALSE"]
        assert false_row["star_outcome_eligible"] == True  # noqa: E712
        assert false_row["star_by_value_label"] == False  # noqa: E712
        assert not pd.isna(false_row["star_by_value_label"])

        true_row = by_id.loc["TRUE"]
        assert true_row["star_outcome_eligible"] == True  # noqa: E712
        assert true_row["star_by_value_label"] == True  # noqa: E712


class TestPredictorWhitelistAndTargetRegistry:
    def test_whitelist_excludes_spine_columns(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        _, whitelist, _, _ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        assert whitelist == ["fam1_trait"]
        for spine_col in ("prediction_season", "player_id", "position", "observation_season"):
            assert spine_col not in whitelist

    def test_whitelist_never_includes_any_outcome_column(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        view, whitelist, _, _ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        outcome_only_cols = set(view.columns) - {"prediction_season", "player_id", "position", "observation_season", "fam1_trait"}
        assert set(whitelist).isdisjoint(outcome_only_cols)

    def test_target_registry_matches_the_six_approved_targets(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        _, _, targets, _ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        target_cols = {t["target_column"] for t in targets}
        assert target_cols == {
            "star_by_value_label",
            "bust_primary_label",
            "bust_primary_sensitivity_pct25_label",
            "bust_primary_sensitivity_pct30_label",
            "bust_strict_below_replacement_label",
            "underperformance_diagnostic_value",
        }
        assert "bust_historical_sensitivity_label" not in target_cols
        assert all(t["usable_as_target"] for t in targets)

    def test_column_registry_marks_bust_historical_sensitivity_label_not_a_target(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        _, _, _, registry = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        row = registry[registry["canonical_column"] == "bust_historical_sensitivity_label"].iloc[0]
        assert row["role"] != "target_label"

    def test_column_registry_flags_assignment_method_and_reasons_as_non_predictor_roles(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        _, whitelist, _, registry = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        for col in ("bust_primary_assignment_method", "bust_primary_ineligibility_reason", "star_by_value_score"):
            assert col not in whitelist
            role = registry.loc[registry["canonical_column"] == col, "role"].iloc[0]
            assert role != "predictor"


class TestStructuralIntegrity:
    def test_equal_shared_metadata_is_retained_once_from_predictor(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        for column in ("canonical_position_status", "canonical_position_authority", "historical_input_revision"):
            assert list(view.columns).count(column) == 1
            assert view.loc[0, column] == predictor.loc[0, column]

    def test_shared_metadata_mismatch_fails_loudly(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        outcome.loc[0, "historical_input_revision"] = "different-revision"
        with pytest.raises(RuntimeError, match="Shared predictor/outcome spine metadata disagree"):
            build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)

    def test_predictor_only_2026_row_preserves_shared_metadata(self):
        predictor = _predictor((2026, "FUTURE", "WR", 1.0))
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), _outcome())
        row = view.iloc[0]
        assert row["canonical_position_status"] == "adp_source"
        assert row["canonical_position_authority"] == "adp_source_position"
        assert row["historical_input_revision"] == "test-revision"

    def test_no_x_y_suffix_columns(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        assert not any(c.endswith("_x") or c.endswith("_y") for c in view.columns)

    def test_no_duplicate_column_names(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        assert not view.columns.duplicated().any()

    def test_nullable_boolean_dtype_preserved_for_unmatched_rows(self):
        predictor = _predictor((2026, "FUTURE", "RB", 1.0))
        outcome = _outcome()
        view, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        assert str(view["bust_primary_label"].dtype) == "boolean"
        assert str(view["star_by_value_label"].dtype) == "boolean"

    def test_unexpected_column_collision_raises(self):
        predictor = _predictor((2015, "P1", "RB", 1.0))
        predictor = predictor.rename(columns={"fam1_trait": "star_by_value_score"})  # force a real collision
        registry = _predictor_registry()
        registry.loc[registry["canonical_column"] == "fam1_trait", "canonical_column"] = "star_by_value_score"
        outcome = _outcome((2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0))
        with pytest.raises(RuntimeError):
            build_dataset2_analysis_view(predictor, registry, outcome)


class TestDeterminismAndOrderIndependence:
    def _fixture(self):
        predictor = _predictor((2015, "P1", "RB", 1.0), (2016, "P2", "WR", 2.0), (2026, "P3", "TE", 3.0))
        outcome = _outcome(
            (2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0),
            (2016, "P2", "WR", "below_production_gate", True, False, True, False, False, False, True, False, True, -5.0),
        )
        return predictor, outcome

    def test_deterministic_rebuild(self):
        predictor, outcome = self._fixture()
        v1, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        v2, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        pd.testing.assert_frame_equal(v1, v2)

    def test_input_order_independence(self):
        predictor, outcome = self._fixture()
        v_forward, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome)
        v_reversed, *_ = build_dataset2_analysis_view(
            predictor.iloc[::-1].reset_index(drop=True), _predictor_registry(), outcome.iloc[::-1].reset_index(drop=True)
        )
        v_forward_sorted = v_forward.sort_values(["prediction_season", "player_id"]).reset_index(drop=True)
        v_reversed_sorted = v_reversed.sort_values(["prediction_season", "player_id"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(v_forward_sorted, v_reversed_sorted)


class TestMutationIsolation:
    def test_changing_an_outcome_value_does_not_change_predictor_columns(self):
        predictor = _predictor((2015, "P1", "RB", 1.0), (2016, "P2", "WR", 2.0))
        outcome_a = _outcome(
            (2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0),
            (2016, "P2", "WR", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0),
        )
        outcome_b = outcome_a.copy()
        outcome_b.loc[outcome_b["player_id"] == "P2", "star_by_value_label"] = False
        outcome_b.loc[outcome_b["player_id"] == "P2", "bust_primary_label"] = True

        view_a, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome_a)
        view_b, *_ = build_dataset2_analysis_view(predictor, _predictor_registry(), outcome_b)

        pd.testing.assert_frame_equal(
            view_a[["prediction_season", "player_id", "position", "observation_season", "fam1_trait"]],
            view_b[["prediction_season", "player_id", "position", "observation_season", "fam1_trait"]],
        )
        # Sanity: the outcome DID change for P2 -- proves this isn't a no-op fixture.
        assert view_a.set_index("player_id").loc["P2", "star_by_value_label"] != view_b.set_index("player_id").loc["P2", "star_by_value_label"]

    def test_changing_a_predictor_value_does_not_change_outcome_columns(self):
        predictor_a = _predictor((2015, "P1", "RB", 1.0), (2016, "P2", "WR", 2.0))
        predictor_b = predictor_a.copy()
        predictor_b.loc[predictor_b["player_id"] == "P2", "fam1_trait"] = 999.0

        outcome = _outcome(
            (2015, "P1", "RB", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0),
            (2016, "P2", "WR", "adp_scored", True, True, True, True, True, True, True, False, True, 5.0),
        )

        view_a, *_ = build_dataset2_analysis_view(predictor_a, _predictor_registry(), outcome)
        view_b, *_ = build_dataset2_analysis_view(predictor_b, _predictor_registry(), outcome)

        outcome_cols = [c for c in view_a.columns if c not in ("prediction_season", "player_id", "position", "observation_season", "fam1_trait")]
        pd.testing.assert_frame_equal(view_a[outcome_cols], view_b[outcome_cols])
        # Sanity: the predictor DID change for P2.
        assert view_a.set_index("player_id").loc["P2", "fam1_trait"] != view_b.set_index("player_id").loc["P2", "fam1_trait"]
