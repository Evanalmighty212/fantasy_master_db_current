"""Regression tests for the frozen Dataset 2 Phase 2 candidate set and rule.

Anchored to research/dataset2/DATASET2_PHASE2_METHODOLOGY_FREEZE_2026_08.md:
the candidate list must exactly match the 32 lwi traits marked
supported=True in the completed Phase 1 discovery package, the 2 star
traits excluded for direction-flip instability must stay excluded, and
evaluate_holdout_confirmation() must implement the frozen Option B rule
(same sign, magnitude ratio in [1/3, 3]) with no data access of any kind.
"""

from __future__ import annotations

import math

import pytest

from config import (
    DATASET2_PHASE1_SOURCE_GIT_HEAD,
    DATASET2_PHASE1_SOURCE_PRIMARY_RESULTS_SHA256,
)
from lib.dataset2.phase2_confirmation import (
    PHASE2_CANDIDATE_TRAITS,
    PHASE2_EXCLUDED_UNSTABLE_TRAITS,
    _candidate_list_fingerprint,
    _EXPECTED_CANDIDATE_LIST_SHA256,
    evaluate_holdout_confirmation,
    verify_phase1_source_package,
)


class TestFrozenCandidateSet:
    def test_candidate_count_is_32(self):
        assert len(PHASE2_CANDIDATE_TRAITS) == 32

    def test_all_candidates_are_lwi_family(self):
        assert all(c.family == "lwi" for c in PHASE2_CANDIDATE_TRAITS)

    def test_candidate_predictor_columns_are_unique(self):
        columns = [c.predictor_column for c in PHASE2_CANDIDATE_TRAITS]
        assert len(columns) == len(set(columns))

    def test_excluded_unstable_traits_are_the_two_star_team_identity_findings(self):
        excluded_keys = {(c.family, c.predictor_column) for c in PHASE2_EXCLUDED_UNSTABLE_TRAITS}
        assert excluded_keys == {
            ("star", "fam10_depth_chart_team"),
            ("star", "fam4_nfl_draft_team"),
        }

    def test_excluded_traits_do_not_overlap_candidate_set(self):
        candidate_keys = {(c.family, c.predictor_column) for c in PHASE2_CANDIDATE_TRAITS}
        excluded_keys = {(c.family, c.predictor_column) for c in PHASE2_EXCLUDED_UNSTABLE_TRAITS}
        assert candidate_keys.isdisjoint(excluded_keys)

    def test_no_strict_bust_candidates(self):
        assert all(c.family != "strict_bust" for c in PHASE2_CANDIDATE_TRAITS)
        assert all(c.family != "strict_bust" for c in PHASE2_EXCLUDED_UNSTABLE_TRAITS)


class TestEvaluateHoldoutConfirmationRatioBand:
    def test_ratio_exactly_one_third_is_confirmed(self):
        assert evaluate_holdout_confirmation(0.30, 0.10) == "confirmed"

    def test_ratio_exactly_three_is_confirmed(self):
        assert evaluate_holdout_confirmation(0.10, 0.30) == "confirmed"

    def test_ratio_one_is_confirmed(self):
        assert evaluate_holdout_confirmation(0.20, 0.20) == "confirmed"

    def test_ratio_just_below_one_third_is_contradicted(self):
        assert evaluate_holdout_confirmation(0.30, 0.30 * (1 / 3) - 1e-6) == "contradicted"

    def test_ratio_just_above_three_is_contradicted(self):
        assert evaluate_holdout_confirmation(0.10, 0.10 * 3 + 1e-6) == "contradicted"


class TestEvaluateHoldoutConfirmationSign:
    def test_opposite_sign_is_contradicted_even_with_matching_magnitude(self):
        assert evaluate_holdout_confirmation(0.20, -0.20) == "contradicted"

    def test_both_negative_same_direction_uses_magnitude_ratio(self):
        assert evaluate_holdout_confirmation(-0.20, -0.20) == "confirmed"
        assert evaluate_holdout_confirmation(-0.20, -1.0) == "contradicted"


class TestEvaluateHoldoutConfirmationInconclusive:
    def test_none_holdout_effect_is_inconclusive(self):
        assert evaluate_holdout_confirmation(0.20, None) == "inconclusive"

    def test_nan_holdout_effect_is_inconclusive(self):
        assert evaluate_holdout_confirmation(0.20, float("nan")) == "inconclusive"

    def test_infinite_holdout_effect_is_inconclusive(self):
        assert evaluate_holdout_confirmation(0.20, float("inf")) == "inconclusive"
        assert evaluate_holdout_confirmation(0.20, float("-inf")) == "inconclusive"


class TestEvaluateHoldoutConfirmationZeroDiscoveryEffect:
    def test_zero_discovery_effect_raises(self):
        with pytest.raises(ValueError):
            evaluate_holdout_confirmation(0.0, 0.10)

    def test_zero_discovery_effect_raises_even_with_none_holdout(self):
        with pytest.raises(ValueError):
            evaluate_holdout_confirmation(0.0, None)


class TestCandidateListFingerprint:
    """Guards against a silent, unreviewed edit to the frozen candidate/excluded tuples.

    Protects the invariant recorded in
    research/dataset2/DATASET2_PHASE2_METHODOLOGY_FREEZE_2026_08.md that
    PHASE2_CANDIDATE_TRAITS and PHASE2_EXCLUDED_UNSTABLE_TRAITS are a
    frozen decision record, not code that can drift.
    """

    def test_current_lists_match_the_frozen_fingerprint(self):
        assert (
            _candidate_list_fingerprint(PHASE2_CANDIDATE_TRAITS, PHASE2_EXCLUDED_UNSTABLE_TRAITS)
            == _EXPECTED_CANDIDATE_LIST_SHA256
        )

    def test_fingerprint_changes_if_a_candidate_is_added(self):
        from lib.dataset2.phase2_confirmation import Phase2Candidate

        tampered = PHASE2_CANDIDATE_TRAITS + (Phase2Candidate("lwi", "not_a_real_trait"),)
        assert (
            _candidate_list_fingerprint(tampered, PHASE2_EXCLUDED_UNSTABLE_TRAITS)
            != _EXPECTED_CANDIDATE_LIST_SHA256
        )

    def test_fingerprint_changes_if_a_candidate_is_removed(self):
        tampered = PHASE2_CANDIDATE_TRAITS[1:]
        assert (
            _candidate_list_fingerprint(tampered, PHASE2_EXCLUDED_UNSTABLE_TRAITS)
            != _EXPECTED_CANDIDATE_LIST_SHA256
        )

    def test_fingerprint_changes_if_an_excluded_trait_moves_to_candidates(self):
        moved_candidates = PHASE2_CANDIDATE_TRAITS + (PHASE2_EXCLUDED_UNSTABLE_TRAITS[0],)
        moved_excluded = PHASE2_EXCLUDED_UNSTABLE_TRAITS[1:]
        assert (
            _candidate_list_fingerprint(moved_candidates, moved_excluded)
            != _EXPECTED_CANDIDATE_LIST_SHA256
        )

    def test_fingerprint_is_order_independent_within_each_group(self):
        reordered_candidates = tuple(reversed(PHASE2_CANDIDATE_TRAITS))
        reordered_excluded = tuple(reversed(PHASE2_EXCLUDED_UNSTABLE_TRAITS))
        assert (
            _candidate_list_fingerprint(reordered_candidates, reordered_excluded)
            == _EXPECTED_CANDIDATE_LIST_SHA256
        )


class TestVerifyPhase1SourcePackage:
    """Guards against running Phase 2 against a different Phase 1 package.

    A future holdout runner is required to call
    verify_phase1_source_package() with the git HEAD and
    primary_results.csv checksum of whatever Phase 1 package it has
    actually been pointed at.
    """

    def test_matching_identity_does_not_raise(self):
        verify_phase1_source_package(
            DATASET2_PHASE1_SOURCE_GIT_HEAD,
            DATASET2_PHASE1_SOURCE_PRIMARY_RESULTS_SHA256,
        )

    def test_wrong_git_head_raises(self):
        with pytest.raises(ValueError, match="git HEAD"):
            verify_phase1_source_package(
                "f" * 40,
                DATASET2_PHASE1_SOURCE_PRIMARY_RESULTS_SHA256,
            )

    def test_wrong_checksum_raises(self):
        with pytest.raises(ValueError, match="sha256"):
            verify_phase1_source_package(
                DATASET2_PHASE1_SOURCE_GIT_HEAD,
                "0" * 64,
            )

    def test_both_wrong_raises_with_both_reasons(self):
        with pytest.raises(ValueError) as exc_info:
            verify_phase1_source_package("f" * 40, "0" * 64)
        message = str(exc_info.value)
        assert "git HEAD" in message
        assert "sha256" in message
