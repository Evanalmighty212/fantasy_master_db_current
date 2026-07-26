"""
tests/test_evidence_audit.py

Covers lib/stars_by_value/evidence_audit.py -- the shape, validation,
and required-coverage rule for the SBV evidence-audit artifact
(data/exports/stars_by_value_evidence_audit.csv), added 2026-07 to
replace the never-implemented star_by_value_evidence_notes column
design (rejected -- see research/dataset3/STARS_BY_VALUE_METHODOLOGY.md's
decision history).

TestNeverConsumedDownstream is the most important class here: it
mechanically enforces (by scanning real source files, not trusting a
docstring) that no scoring/matching/labeling/modeling code ever reads
config.SBV_EVIDENCE_AUDIT_PATH or imports this module for any purpose
other than building/writing/documenting it. tests/test_labeling.py's
TestAuditPayloadBuiltDuringSameEvaluation covers the OTHER direction
(assign_sbv_status() builds a correct payload) -- this file covers the
artifact's own shape/validation logic in isolation.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from lib.stars_by_value import evidence_audit as audit


def _canonical_row(season, player_id, status, provenance):
    return {
        "season": season, "player_id": player_id,
        "star_by_value_status": status, "star_by_value_provenance_type": provenance,
        "star_by_value_score": None, "star_by_value_label": None,
        "star_by_value_production_gate_threshold": None, "star_by_value_threshold": None,
    }


class TestRequiredProvenanceTypesAreRealConfigMembers:
    """Pins REQUIRED_AUDIT_PROVENANCE_TYPES (plain string literals, to
    avoid a circular import with labeling.py) against the real
    config.SBV_PROVENANCE_TYPES enum -- a typo or a renamed provenance
    constant must be caught immediately."""

    def test_every_required_type_is_a_real_provenance_type(self):
        for provenance in audit.REQUIRED_AUDIT_PROVENANCE_TYPES:
            assert provenance in config.SBV_PROVENANCE_TYPES, f"{provenance!r} is not a real SBV provenance type"

    def test_required_types_are_exactly_six(self):
        assert len(audit.REQUIRED_AUDIT_PROVENANCE_TYPES) == 6

    def test_evidence_type_mapping_covers_every_required_provenance(self):
        for provenance in audit.REQUIRED_AUDIT_PROVENANCE_TYPES:
            assert provenance in audit._EVIDENCE_TYPE_BY_PROVENANCE
        assert set(audit._EVIDENCE_TYPE_BY_PROVENANCE.values()) == set(audit.EVIDENCE_TYPES)


class TestBuildPayload:
    def test_builds_a_well_formed_payload(self):
        payload = audit.build_payload(
            2020, "00-x", "Test Player", "minimal_market_cost_scored", "mmc_verified_corroborated",
            evidence_summary="test summary", source_reference="test source",
        )
        assert set(payload.keys()) == set(audit.EVIDENCE_AUDIT_COLUMNS)
        assert payload["evidence_type"] == "mmc_corroborated_by_mfl"

    def test_raises_for_a_provenance_not_requiring_audit(self):
        with pytest.raises(ValueError, match="not in REQUIRED_AUDIT_PROVENANCE_TYPES"):
            audit.build_payload(
                2020, "00-x", "Test Player", "adp_scored", "adp_matched_clean",
                evidence_summary="should never be called for this provenance", source_reference="n/a",
            )

    def test_evidence_type_derived_from_provenance_not_passed_in(self):
        """evidence_type can never disagree with the provenance it was
        built from, because it's looked up, not accepted as an argument."""
        payload = audit.build_payload(
            2020, "00-x", "Test Player", "unscoreable_ambiguous", "evidence_ambiguous_disagreement",
            evidence_summary="x", source_reference="y",
        )
        assert payload["evidence_type"] == "classifier_mfl_disagreement"


class TestValidateAuditCoverage:
    def test_passes_for_correct_coverage(self):
        canonical = pd.DataFrame([
            _canonical_row(2020, "00-a", "adp_scored", "adp_matched_clean"),
            _canonical_row(2020, "00-b", "unscoreable_ambiguous", "evidence_ambiguous_disagreement"),
        ])
        audit_df = pd.DataFrame([
            audit.build_payload(2020, "00-b", "Player B", "unscoreable_ambiguous", "evidence_ambiguous_disagreement",
                                 evidence_summary="x", source_reference="y"),
        ])
        audit.validate_audit_coverage(canonical, audit_df)  # must not raise

    def test_passes_with_empty_audit_df_when_nothing_required(self):
        canonical = pd.DataFrame([
            _canonical_row(2020, "00-a", "adp_scored", "adp_matched_clean"),
            _canonical_row(2020, "00-b", "below_production_gate", "below_production_gate"),
        ])
        audit.validate_audit_coverage(canonical, audit.empty_audit_df())  # must not raise

    def test_raises_on_duplicate_audit_rows(self):
        canonical = pd.DataFrame([_canonical_row(2020, "00-b", "unscoreable_ambiguous", "evidence_ambiguous_disagreement")])
        row = audit.build_payload(2020, "00-b", "Player B", "unscoreable_ambiguous", "evidence_ambiguous_disagreement",
                                   evidence_summary="x", source_reference="y")
        audit_df = pd.DataFrame([row, row])
        with pytest.raises(RuntimeError, match="duplicate"):
            audit.validate_audit_coverage(canonical, audit_df)

    def test_raises_on_orphaned_audit_row(self):
        canonical = pd.DataFrame([_canonical_row(2020, "00-a", "adp_scored", "adp_matched_clean")])
        orphan = audit.build_payload(2020, "00-nonexistent", "Ghost", "unscoreable_ambiguous", "evidence_ambiguous_disagreement",
                                      evidence_summary="x", source_reference="y")
        audit_df = pd.DataFrame([orphan])
        with pytest.raises(RuntimeError, match="orphan|does not exist"):
            audit.validate_audit_coverage(canonical, audit_df)

    def test_raises_on_missing_required_row(self):
        canonical = pd.DataFrame([_canonical_row(2020, "00-b", "unscoreable_ambiguous", "evidence_ambiguous_disagreement")])
        with pytest.raises(RuntimeError, match="missing"):
            audit.validate_audit_coverage(canonical, audit.empty_audit_df())

    def test_raises_on_stray_row_for_non_required_status(self):
        canonical = pd.DataFrame([_canonical_row(2020, "00-a", "adp_scored", "adp_matched_clean")])
        # Hand-construct a stray row bypassing build_payload()'s own guard,
        # to test validate_audit_coverage()'s independent check too.
        stray = {
            "season": 2020, "player_id": "00-a", "player_name": "Player A",
            "star_by_value_status": "adp_scored", "star_by_value_provenance_type": "adp_matched_clean",
            "evidence_type": "adp_match_needs_review", "evidence_summary": "x", "source_reference": "y",
        }
        audit_df = pd.DataFrame([stray])
        with pytest.raises(RuntimeError, match="does NOT require explanation"):
            audit.validate_audit_coverage(canonical, audit_df)

    def test_raises_on_status_provenance_mismatch(self):
        """Should be structurally impossible via build_payload(), but
        checked directly as a real regression pin."""
        canonical = pd.DataFrame([_canonical_row(2020, "00-b", "unscoreable_ambiguous", "evidence_ambiguous_disagreement")])
        mismatched = audit.build_payload(2020, "00-b", "Player B", "unscoreable_ambiguous", "evidence_ambiguous_disagreement",
                                          evidence_summary="x", source_reference="y")
        mismatched["star_by_value_status"] = "minimal_market_cost_scored"  # tampered post-construction
        audit_df = pd.DataFrame([mismatched])
        with pytest.raises(RuntimeError, match="disagrees"):
            audit.validate_audit_coverage(canonical, audit_df)


class TestNeverConsumedDownstream:
    """The one-way guarantee: no scoring/matching/labeling/modeling
    code may ever read config.SBV_EVIDENCE_AUDIT_PATH or import this
    module for anything beyond building/writing/documenting the
    artifact. Checked by scanning real source files, not by trusting
    the module docstring's promise."""

    CONSUMER_FILES = (
        "scripts/04_build_master_dataset.py",
        "scripts/05_calculate_metrics.py",
        "scripts/09_fit_sbv_expected_production.py",
        "lib/stars_by_value/production.py",
        "lib/stars_by_value/expected_production.py",
        "lib/stars_by_value/acquisition_cost.py",
        "lib/stars_by_value/minimal_market_cost.py",
    )

    REPO_ROOT = Path(__file__).resolve().parent.parent

    @pytest.mark.parametrize("relpath", CONSUMER_FILES)
    def test_consumer_does_not_reference_evidence_audit_path(self, relpath):
        path = self.REPO_ROOT / relpath
        if not path.exists():
            pytest.skip(f"{relpath} does not exist yet")
        source = path.read_text()
        assert "SBV_EVIDENCE_AUDIT_PATH" not in source, f"{relpath} references SBV_EVIDENCE_AUDIT_PATH"
        assert "evidence_audit" not in source, f"{relpath} references the evidence_audit module"

    def test_labeling_only_builds_payloads_never_reads_the_path_config(self):
        """labeling.py legitimately imports evidence_audit (to build
        payloads) -- but must never reference the file PATH, since
        building a payload and reading the written artifact back are
        two very different things."""
        source = (self.REPO_ROOT / "lib/stars_by_value/labeling.py").read_text()
        assert "SBV_EVIDENCE_AUDIT_PATH" not in source

    def test_acquisition_cost_and_minimal_market_cost_do_not_import_evidence_audit(self):
        """The classifier modules that DECIDE status/provenance must
        never import the artifact that only records those decisions
        after the fact -- that would risk a feedback loop."""
        for relpath in ("lib/stars_by_value/acquisition_cost.py", "lib/stars_by_value/minimal_market_cost.py"):
            source = (self.REPO_ROOT / relpath).read_text()
            assert "evidence_audit" not in source


class TestRenderEvidenceAuditMarkdown:
    def test_mentions_the_join_keys_and_coverage_rule(self):
        md = audit.render_evidence_audit_markdown()
        assert "season" in md and "player_id" in md
        assert "Coverage rule" in md

    def test_every_evidence_type_appears(self):
        md = audit.render_evidence_audit_markdown()
        for et in audit.EVIDENCE_TYPES:
            assert et in md

    def test_states_the_one_way_guarantee(self):
        md = audit.render_evidence_audit_markdown()
        assert "No scoring, matching, labeling, or modeling code" in md
