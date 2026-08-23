"""Synthetic-only tests for the Dataset 2 Phase 2 holdout-confirmation runner.

No real 2021-2025 holdout row is loaded anywhere in this file -- every
row below is synthetically generated with a fixed seed, exactly like
tests/test_dataset2_phase1_runner.py does for discovery-season rows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.dataset2.phase1_runner import PRIMARY_TARGETS, PredictorDefinition
from lib.dataset2.phase2_confirmation import Phase2Candidate
from lib.dataset2.phase2_runner import (
    _single_holdout_point_estimate,
    _validated_holdout_seasons,
    confirm_all_candidates,
    confirm_candidate,
    holdout_fit_rows,
)


def _holdout_rows(seasons=range(2021, 2026), players_per_season=36, seed=20260822) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    player_number = 0
    for season in seasons:
        for _ in range(players_per_season):
            trait = rng.normal()
            rows.append({
                "prediction_season": season,
                "player_id": f"player_{player_number:03d}",
                "position": ("QB", "RB", "WR", "TE")[player_number % 4],
                "preseason_market_status": "ordinary_market",
                "adp_round": 1 + player_number % 15,
                "trait": trait,
                "lwi_score": 8.0 * trait + rng.normal(scale=2.0),
                "star_by_value_label": int(rng.random() < 0.16 + 0.02 * (trait > 0)),
                "star_outcome_eligible": True,
                "bust_strict_below_replacement_label": int(rng.random() < 0.15 + 0.25 * (trait > 0)),
                "bust_strict_below_replacement_eligible": True,
            })
            player_number += 1
    return pd.DataFrame(rows)


def _lwi_predictor(column: str = "trait") -> PredictorDefinition:
    return PredictorDefinition(column=column, kind="continuous", cluster_id="cluster_001", is_cluster_representative=True)


class TestValidatedHoldoutSeasons:
    """Anchored to the requirement that a 2010-2020 discovery row must never
    silently enter a Phase 2 holdout fit."""

    def test_accepts_rows_entirely_within_2021_2025(self):
        rows = _holdout_rows()
        result = _validated_holdout_seasons(rows)
        assert set(result.unique()) <= set(range(2021, 2026))

    def test_rejects_a_discovery_season_row(self):
        rows = _holdout_rows()
        leaked = rows.copy()
        leaked.loc[0, "prediction_season"] = 2020
        with pytest.raises(ValueError, match="non-holdout seasons"):
            _validated_holdout_seasons(leaked)

    def test_rejects_a_season_beyond_the_holdout_window(self):
        rows = _holdout_rows()
        leaked = rows.copy()
        leaked.loc[0, "prediction_season"] = 2026
        with pytest.raises(ValueError, match="non-holdout seasons"):
            _validated_holdout_seasons(leaked)

    def test_rejects_missing_prediction_season_column(self):
        rows = _holdout_rows().drop(columns=["prediction_season"])
        with pytest.raises(ValueError, match="prediction_season"):
            _validated_holdout_seasons(rows)


class TestHoldoutFitRows:
    def test_selects_only_target_eligible_holdout_rows(self):
        rows = _holdout_rows()
        target = PRIMARY_TARGETS[0]
        fit_rows = holdout_fit_rows(rows, target, "trait")
        assert set(fit_rows["prediction_season"].unique()) <= set(range(2021, 2026))
        assert fit_rows["trait"].notna().all()

    def test_raises_when_no_eligible_rows_remain(self):
        rows = _holdout_rows()
        rows["missing_trait"] = np.nan
        target = PRIMARY_TARGETS[0]
        with pytest.raises(ValueError, match="no eligible 2021-2025 rows"):
            holdout_fit_rows(rows, target, "missing_trait")

    def test_raises_when_predictor_column_is_absent(self):
        rows = _holdout_rows()
        target = PRIMARY_TARGETS[0]
        with pytest.raises(ValueError, match="missing required columns"):
            holdout_fit_rows(rows, target, "not_a_real_column")


class TestSingleHoldoutPointEstimateRejectsCategorical:
    def test_categorical_predictor_is_rejected(self):
        rows = _holdout_rows()
        predictor = PredictorDefinition(
            "trait", "categorical", "cluster_001", True, reference_level="x",
        )
        with pytest.raises(ValueError, match="categorical predictors"):
            _single_holdout_point_estimate(rows, PRIMARY_TARGETS[0], predictor)


class TestConfirmCandidateVerdicts:
    """Integration coverage: a real (synthetic) single fit feeding the frozen
    Option B rule, not just the pure rule in isolation."""

    def test_confirmed_when_discovery_effect_equals_the_holdout_effect(self):
        rows = _holdout_rows()
        predictor = _lwi_predictor()
        candidate = Phase2Candidate("lwi", "trait")
        probe = confirm_candidate(rows, candidate, predictor, discovery_effect=1.0)
        assert probe.fit_failure_reason is None
        assert probe.holdout_effect is not None and probe.holdout_effect != 0.0

        record = confirm_candidate(rows, candidate, predictor, discovery_effect=probe.holdout_effect)
        assert record.verdict == "confirmed"
        assert record.holdout_effect == probe.holdout_effect
        assert record.holdout_n > 0
        assert record.holdout_seasons_represented == 5

    def test_contradicted_when_holdout_effect_flips_sign(self):
        rows = _holdout_rows()
        predictor = _lwi_predictor()
        candidate = Phase2Candidate("lwi", "trait")
        probe = confirm_candidate(rows, candidate, predictor, discovery_effect=1.0)

        record = confirm_candidate(rows, candidate, predictor, discovery_effect=-probe.holdout_effect)
        assert record.verdict == "contradicted"

    def test_contradicted_when_holdout_effect_magnitude_is_far_outside_the_band(self):
        rows = _holdout_rows()
        predictor = _lwi_predictor()
        candidate = Phase2Candidate("lwi", "trait")
        probe = confirm_candidate(rows, candidate, predictor, discovery_effect=1.0)

        record = confirm_candidate(rows, candidate, predictor, discovery_effect=probe.holdout_effect * 10.0)
        assert record.verdict == "contradicted"

    def test_inconclusive_when_holdout_predictor_has_no_variation(self):
        rows = _holdout_rows()
        rows["constant_trait"] = 5.0
        predictor = _lwi_predictor("constant_trait")
        candidate = Phase2Candidate("lwi", "constant_trait")

        record = confirm_candidate(rows, candidate, predictor, discovery_effect=1.0)

        assert record.holdout_effect is None
        assert record.verdict == "inconclusive"
        assert record.fit_failure_reason is not None
        assert record.holdout_n > 0

    def test_inconclusive_when_holdout_design_is_rank_deficient(self):
        """statsmodels' OLS silently returns an arbitrary coefficient split
        across collinear columns rather than raising (confirmed separately
        against raw statsmodels output below); the runner's own rank check
        must catch this before it can masquerade as a real effect."""
        rows = _holdout_rows()
        # position is one of the model's controls: an exact linear function
        # of position is an exact linear combination of {intercept, position
        # dummies}, making the full design matrix rank-deficient.
        position_effect = {"QB": 1.0, "RB": 2.0, "WR": 3.0, "TE": 4.0}
        rows["collinear_trait"] = rows["position"].map(position_effect)
        predictor = _lwi_predictor("collinear_trait")
        candidate = Phase2Candidate("lwi", "collinear_trait")

        record = confirm_candidate(rows, candidate, predictor, discovery_effect=1.0)

        assert record.holdout_effect is None
        assert record.verdict == "inconclusive"
        assert record.fit_failure_reason is not None and "rank-deficient" in record.fit_failure_reason

    def test_inconclusive_when_no_eligible_holdout_rows_exist(self):
        rows = _holdout_rows()
        rows["missing_trait"] = np.nan
        predictor = _lwi_predictor("missing_trait")
        candidate = Phase2Candidate("lwi", "missing_trait")

        record = confirm_candidate(rows, candidate, predictor, discovery_effect=1.0)

        assert record.holdout_effect is None
        assert record.holdout_n == 0
        assert record.holdout_seasons_represented == 0
        assert record.verdict == "inconclusive"

    def test_raises_on_predictor_candidate_column_mismatch(self):
        rows = _holdout_rows()
        predictor = _lwi_predictor("trait")
        candidate = Phase2Candidate("lwi", "a_different_column")
        with pytest.raises(ValueError, match="does not match"):
            confirm_candidate(rows, candidate, predictor, discovery_effect=1.0)

    def test_dispatches_to_firth_point_estimate_for_a_non_lwi_family(self):
        rows = _holdout_rows()
        predictor = PredictorDefinition("binary_trait", "binary", "cluster_001", True)
        rows["binary_trait"] = (rows["trait"] > 0).astype(int)
        candidate = Phase2Candidate("strict_bust", "binary_trait")

        record = confirm_candidate(rows, candidate, predictor, discovery_effect=2.0)

        assert record.fit_failure_reason is None
        assert record.holdout_effect is not None
        assert np.isfinite(record.holdout_effect) and record.holdout_effect > 0.0


class TestConfirmAllCandidates:
    def test_runs_every_candidate_and_preserves_order(self):
        rows = _holdout_rows()
        rows["other_trait"] = rows["trait"] * 2.0
        candidates = (Phase2Candidate("lwi", "trait"), Phase2Candidate("lwi", "other_trait"))
        predictors = {"trait": _lwi_predictor("trait"), "other_trait": _lwi_predictor("other_trait")}
        discovery_effects = {("lwi", "trait"): 1.0, ("lwi", "other_trait"): 1.0}

        records = confirm_all_candidates(rows, candidates, predictors, discovery_effects)

        assert [record.predictor_column for record in records] == ["trait", "other_trait"]
        assert all(record.fit_failure_reason is None for record in records)

    def test_rejects_discovery_season_leakage_before_fitting_any_candidate(self):
        rows = _holdout_rows()
        leaked = rows.copy()
        leaked.loc[0, "prediction_season"] = 2010
        candidate = Phase2Candidate("lwi", "trait")
        with pytest.raises(ValueError, match="non-holdout seasons"):
            confirm_all_candidates(leaked, (candidate,), {"trait": _lwi_predictor()}, {("lwi", "trait"): 1.0})

    def test_raises_when_a_candidate_has_no_pinned_discovery_effect(self):
        rows = _holdout_rows()
        candidate = Phase2Candidate("lwi", "trait")
        with pytest.raises(ValueError, match="no pinned Phase 1 discovery effect"):
            confirm_all_candidates(rows, (candidate,), {"trait": _lwi_predictor()}, {})

    def test_raises_when_a_candidate_has_no_resolved_predictor_definition(self):
        rows = _holdout_rows()
        candidate = Phase2Candidate("lwi", "trait")
        with pytest.raises(ValueError, match="no resolved predictor definition"):
            confirm_all_candidates(rows, (candidate,), {}, {("lwi", "trait"): 1.0})
