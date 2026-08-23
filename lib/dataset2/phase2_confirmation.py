"""Dataset 2 Phase 2 frozen candidate set and holdout-confirmation rule.

Implements only the decisions recorded in
research/dataset2/DATASET2_PHASE2_METHODOLOGY_FREEZE_2026_08.md: which
Phase 1 traits are eligible for 2021-2025 holdout confirmation, and the
Option B confirmation rule (same direction, magnitude within [1/3, 3]
of the discovery effect).

This module never loads, fits, or otherwise touches 2021-2025 holdout
data -- it is pure bookkeeping and arithmetic over caller-supplied
numbers, the same artifact-free design already used by
lib/dataset2/phase1_runner.py. Building the actual holdout runner that
would call this module with real fitted values is a separate, not yet
authorized, piece of work.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

from config import (
    DATASET2_HOLDOUT_MAGNITUDE_RATIO_MAX,
    DATASET2_HOLDOUT_MAGNITUDE_RATIO_MIN,
    DATASET2_PHASE1_SOURCE_GIT_HEAD,
    DATASET2_PHASE1_SOURCE_PRIMARY_RESULTS_SHA256,
    validate_dataset2_phase2_config,
)

validate_dataset2_phase2_config()

Family = Literal["lwi", "star", "strict_bust"]
ConfirmationVerdict = Literal["confirmed", "contradicted", "inconclusive"]


@dataclass(frozen=True)
class Phase2Candidate:
    family: Family
    predictor_column: str


# Frozen 2026-08-22: every League Winner Index trait marked
# supported=True in the completed Phase 1 discovery package (HEAD
# 0e6a67014901456b15341eff9ab06bc563cbce74's primary_results.csv).
# Verified by direct read of that file; do not regenerate from a
# fresh Phase 1 run. Any change to this list requires a new, dated
# revision of this constant and of the methodology-freeze document.
PHASE2_CANDIDATE_TRAITS: tuple[Phase2Candidate, ...] = (
    Phase2Candidate("lwi", "fam44_prior_changed_team"),
    Phase2Candidate("lwi", "fam7_prior_overall_finish"),
    Phase2Candidate("lwi", "fam7_prior_positional_finish"),
    Phase2Candidate("lwi", "fam7_prior_ppg"),
    Phase2Candidate("lwi", "fam88_prior_season_touches"),
    Phase2Candidate("lwi", "fam9_active_final_4_games_ppg"),
    Phase2Candidate("lwi", "fam9_active_final_4_rb_receiving_opportunity"),
    Phase2Candidate("lwi", "fam9_active_final_4_rb_receiving_production"),
    Phase2Candidate("lwi", "fam9_active_final_4_wr_receiving_opportunity"),
    Phase2Candidate("lwi", "fam9_active_final_4_wr_receiving_production"),
    Phase2Candidate("lwi", "fam9_active_final_6_games_ppg"),
    Phase2Candidate("lwi", "fam9_active_final_6_rb_receiving_opportunity"),
    Phase2Candidate("lwi", "fam9_active_final_6_rb_receiving_opportunity_per_active_game"),
    Phase2Candidate("lwi", "fam9_active_final_6_rb_receiving_production"),
    Phase2Candidate("lwi", "fam9_active_final_6_wr_receiving_opportunity"),
    Phase2Candidate("lwi", "fam9_active_final_6_wr_receiving_production"),
    Phase2Candidate("lwi", "fam9_team_final_4_points_per_active_game"),
    Phase2Candidate("lwi", "fam9_team_final_4_points_per_team_game"),
    Phase2Candidate("lwi", "fam9_team_final_4_rb_receiving_efficiency_rate"),
    Phase2Candidate("lwi", "fam9_team_final_4_rb_receiving_opportunity"),
    Phase2Candidate("lwi", "fam9_team_final_4_rb_receiving_production"),
    Phase2Candidate("lwi", "fam9_team_final_4_wr_receiving_opportunity"),
    Phase2Candidate("lwi", "fam9_team_final_4_wr_receiving_production"),
    Phase2Candidate("lwi", "fam9_team_final_4_wr_snap_team_offense_total"),
    Phase2Candidate("lwi", "fam9_team_final_6_points_per_team_game"),
    Phase2Candidate("lwi", "fam9_team_final_6_rb_receiving_opportunity"),
    Phase2Candidate("lwi", "fam9_team_final_6_rb_receiving_production"),
    Phase2Candidate("lwi", "fam9_team_final_6_wr_receiving_opportunity"),
    Phase2Candidate("lwi", "fam9_team_final_6_wr_receiving_production"),
    Phase2Candidate("lwi", "srcA_prior_season_receptions"),
    Phase2Candidate("lwi", "srcA_prior_season_wopr"),
    Phase2Candidate("lwi", "srcB_prior_season_offense_pct"),
)

# Frozen 2026-08-22: excluded under the "consistent football
# interpretation" manual review provision. Both cleared Phase 1's
# formal statistical gates, but their own discovery-only leave-one-
# season-out robustness check showed direction flips across a
# meaningful share of their many team-level contrasts, and a
# 30-plus-level team-identity joint test is not a single actionable
# football trait. This is a discovery-only judgment, frozen before any
# 2021-2025 row is loaded.
PHASE2_EXCLUDED_UNSTABLE_TRAITS: tuple[Phase2Candidate, ...] = (
    Phase2Candidate("star", "fam10_depth_chart_team"),
    Phase2Candidate("star", "fam4_nfl_draft_team"),
)


def _candidate_list_fingerprint(
    candidates: tuple[Phase2Candidate, ...],
    excluded: tuple[Phase2Candidate, ...],
) -> str:
    """Deterministic sha256 over the frozen candidate/excluded sets' contents."""
    lines = [
        f"{group}|{c.family}|{c.predictor_column}"
        for group, members in (("candidate", candidates), ("excluded", excluded))
        for c in sorted(members, key=lambda x: (x.family, x.predictor_column))
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# Frozen 2026-08-22: sha256 fingerprint of PHASE2_CANDIDATE_TRAITS and
# PHASE2_EXCLUDED_UNSTABLE_TRAITS as originally recorded. Checked at
# import time below. Any edit to either tuple -- adding, removing, or
# reclassifying a trait -- changes this fingerprint and must fail
# loudly rather than pass silently; update this constant only alongside
# a new, explicitly dated revision of both tuples and the methodology
# freeze document, never to make an accidental edit disappear.
_EXPECTED_CANDIDATE_LIST_SHA256 = (
    "fc13b3effb9401d7ad57b641b85d06d28c2c698b14fd65a16493cb669929a364"
)

if (
    _candidate_list_fingerprint(PHASE2_CANDIDATE_TRAITS, PHASE2_EXCLUDED_UNSTABLE_TRAITS)
    != _EXPECTED_CANDIDATE_LIST_SHA256
):
    raise ValueError(
        "PHASE2_CANDIDATE_TRAITS or PHASE2_EXCLUDED_UNSTABLE_TRAITS in "
        "lib/dataset2/phase2_confirmation.py no longer matches its frozen "
        "fingerprint (_EXPECTED_CANDIDATE_LIST_SHA256). This module's "
        "candidate list is a frozen decision record -- if this change was "
        "intentional, update the fingerprint together with a new, "
        "explicitly dated revision of research/dataset2/"
        "DATASET2_PHASE2_METHODOLOGY_FREEZE_2026_08.md; do not silently "
        "recompute the fingerprint to make this error disappear."
    )


def verify_phase1_source_package(git_head: str, primary_results_sha256: str) -> None:
    """Fail loudly unless a Phase 1 package matches the one this candidate list came from.

    A future Phase 2 holdout runner must call this before using
    PHASE2_CANDIDATE_TRAITS or PHASE2_EXCLUDED_UNSTABLE_TRAITS, passing
    the git HEAD and primary_results.csv sha256 of whatever Phase 1
    output package it has been pointed at. Any mismatch means that
    package is not the one this candidate list was derived from, and
    the list must not be assumed to reflect its findings.
    """
    errors = []
    if git_head != DATASET2_PHASE1_SOURCE_GIT_HEAD:
        errors.append(
            f"Phase 1 package git HEAD {git_head!r} does not match the frozen "
            f"source {DATASET2_PHASE1_SOURCE_GIT_HEAD!r} that PHASE2_CANDIDATE_TRAITS "
            "was derived from"
        )
    if primary_results_sha256 != DATASET2_PHASE1_SOURCE_PRIMARY_RESULTS_SHA256:
        errors.append(
            f"Phase 1 package primary_results.csv sha256 {primary_results_sha256!r} "
            "does not match the frozen source "
            f"{DATASET2_PHASE1_SOURCE_PRIMARY_RESULTS_SHA256!r} that "
            "PHASE2_CANDIDATE_TRAITS was derived from"
        )
    if errors:
        raise ValueError(
            "Phase 1 source package identity mismatch -- refusing to run Phase 2 "
            "against a different Phase 1 package than the one the frozen "
            "candidate list was derived from:\n  - " + "\n  - ".join(errors)
        )


def evaluate_holdout_confirmation(
    discovery_effect: float, holdout_effect: float | None,
) -> ConfirmationVerdict:
    """Apply the frozen Option B rule to one candidate's two point estimates.

    ``discovery_effect`` is the trait's already-computed Phase 1
    adjusted effect -- never recomputed here. ``holdout_effect`` is a
    single, caller-supplied point estimate from one refit on 2021-2025
    rows, or None/non-finite if no valid estimate could be produced.
    This function performs no data loading, fitting, or resampling --
    it is pure arithmetic over the two numbers it is given.
    """
    if discovery_effect == 0.0:
        raise ValueError("a zero discovery effect has no defined direction or ratio")
    if holdout_effect is None or not math.isfinite(holdout_effect):
        return "inconclusive"
    same_direction = (holdout_effect > 0) == (discovery_effect > 0)
    ratio = abs(holdout_effect) / abs(discovery_effect)
    if (
        same_direction
        and DATASET2_HOLDOUT_MAGNITUDE_RATIO_MIN <= ratio <= DATASET2_HOLDOUT_MAGNITUDE_RATIO_MAX
    ):
        return "confirmed"
    return "contradicted"
