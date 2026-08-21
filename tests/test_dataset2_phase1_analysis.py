import json

import numpy as np
import pandas as pd
import pytest

from lib.dataset2.phase1_analysis import (
    BootstrapReplicateError,
    benjamini_hochberg,
    eligibility_aware_expanding_windows,
    indexed_player_cluster_bootstrap,
    player_cluster_bootstrap,
    preseason_acquisition_stratum,
    require_discovery_only,
)


def test_expanding_windows_require_five_eligible_prior_seasons():
    rows = pd.DataFrame({"season": range(2010, 2021), "eligible": True})
    folds = eligibility_aware_expanding_windows(rows, season_column="season", eligibility_column="eligible")
    assert folds[0].validation_season == 2015
    assert folds[0].training_seasons == (2010, 2011, 2012, 2013, 2014)
    assert folds[-1].validation_season == 2020


def test_holdout_rows_fail_before_analysis():
    with pytest.raises(ValueError, match="protected"):
        require_discovery_only(pd.DataFrame({"prediction_season": [2020, 2021]}))


def test_bh_known_values():
    assert benjamini_hochberg([0.01, 0.04, 0.03]).round(3).tolist() == [0.03, 0.04, 0.04]


def test_acquisition_control_is_categorical_and_never_imputes_unknown_cost():
    rows = pd.DataFrame({
        "preseason_market_status": ["ordinary_market", "rare_minimal_market", "participation_unknown"],
        "adp_round": [2, None, None],
    })
    assert preseason_acquisition_stratum(rows).tolist() == [
        "ordinary_R1-2", "rare_minimal_market", "participation_unknown",
    ]


def test_cluster_bootstrap_is_seeded_and_preserves_whole_players():
    rows = pd.DataFrame({"player_id": ["A", "A", "B"], "value": [1, 2, 3]})
    seen = []
    def fit(frame):
        if "_bootstrap_cluster_id" in frame:
            assert frame.groupby("_bootstrap_cluster_id")["player_id"].nunique().max() == 1
            seen.append(tuple(frame["player_id"]))
        return len(frame)
    first = player_cluster_bootstrap(rows, player_column="player_id", fit=fit, replicates=20)
    first_seen = list(seen)
    seen.clear()
    second = player_cluster_bootstrap(rows, player_column="player_id", fit=fit, replicates=20)
    assert first.successful == 20
    assert first_seen == seen
    assert first.seed == second.seed == 20260808


def test_cluster_bootstrap_fails_loudly_below_success_floor():
    rows = pd.DataFrame({"player_id": ["A", "B"]})
    calls = {"n": 0}
    def fit(_frame):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("synthetic non-convergence")
        return "original converged"
    with pytest.raises(RuntimeError, match="nonconvergence.*10"):
        player_cluster_bootstrap(
            rows, player_column="player_id", fit=fit, replicates=10,
            context="family=star predictor=synthetic",
        )


def test_cluster_bootstrap_reports_classified_failure_summary_with_context():
    rows = pd.DataFrame({"player_id": ["A", "B"]})
    def fit(frame):
        if "_bootstrap_cluster_id" not in frame:
            return "original"
        raise BootstrapReplicateError("rank_failure", "synthetic rank failure")

    with pytest.raises(RuntimeError, match=r"family=star predictor=trait.*rank_failure.*4"):
        player_cluster_bootstrap(
            rows, player_column="player_id", fit=fit, replicates=4,
            context="family=star predictor=trait",
        )


def test_indexed_bootstrap_matches_legacy_draw_order_values_and_failures():
    rows = pd.DataFrame({
        "player_id": ["A", "A", "B", "C", "C"],
        "row_value": [10, 11, 20, 30, 31],
    })
    def evaluate(values):
        values = tuple(int(value) for value in values)
        if sum(values) % 5 == 0:
            raise BootstrapReplicateError("rank_failure", "synthetic classified failure")
        return values
    legacy = player_cluster_bootstrap(
        rows, player_column="player_id",
        fit=lambda sample: evaluate(sample["row_value"]),
        original=("original",), replicates=12, minimum_success_rate=0.0,
    )
    indexed = indexed_player_cluster_bootstrap(
        rows["player_id"],
        fit_positions=lambda positions: evaluate(rows.iloc[positions]["row_value"]),
        original=("original",), replicates=12, minimum_success_rate=0.0,
    )
    assert indexed.replicates == legacy.replicates
    assert indexed.failure_counts == legacy.failure_counts


def test_indexed_bootstrap_resume_matches_uninterrupted_exactly(tmp_path):
    players = pd.Series(["A", "A", "B", "C", "C"])
    values = np.array([10, 11, 20, 30, 31])
    fit = lambda positions: tuple(int(value) for value in values[positions])
    uninterrupted = indexed_player_cluster_bootstrap(
        players, fit_positions=fit, original=("original",),
        replicates=8, batch_size=2, checkpoint_directory=tmp_path / "fresh",
        task_signature={"fixture": "resume"},
    )
    interrupted_calls = {"count": 0}
    def interrupt_after_first_batch(_record):
        interrupted_calls["count"] += 1
        if interrupted_calls["count"] == 1:
            raise RuntimeError("synthetic interruption")
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        indexed_player_cluster_bootstrap(
            players, fit_positions=fit, original=("original",),
            replicates=8, batch_size=2, checkpoint_directory=tmp_path / "resumed",
            task_signature={"fixture": "resume"}, progress=interrupt_after_first_batch,
        )
    assert len(list((tmp_path / "resumed").glob("batch_*.json"))) == 1
    resumed = indexed_player_cluster_bootstrap(
        players, fit_positions=fit, original=("original",),
        replicates=8, batch_size=2, checkpoint_directory=tmp_path / "resumed",
        task_signature={"fixture": "resume"},
    )
    assert resumed == uninterrupted
    assert (tmp_path / "resumed" / "task_complete.json").is_file()


def test_indexed_bootstrap_rejects_checkpoint_signature_drift(tmp_path):
    players = pd.Series(["A", "B"])
    indexed_player_cluster_bootstrap(
        players, fit_positions=lambda positions: tuple(positions), original=(),
        replicates=2, batch_size=1, checkpoint_directory=tmp_path,
        task_signature={"version": 1},
    )
    with pytest.raises(RuntimeError, match="signature mismatch"):
        indexed_player_cluster_bootstrap(
            players, fit_positions=lambda positions: tuple(positions), original=(),
            replicates=2, batch_size=1, checkpoint_directory=tmp_path,
            task_signature={"version": 2},
        )


def test_indexed_bootstrap_progress_reports_bounded_batches_and_failures():
    players = pd.Series(["A", "B"])
    progress = []
    def fail(_positions):
        raise BootstrapReplicateError("nonconvergence", "synthetic")
    with pytest.raises(RuntimeError, match="0/4"):
        indexed_player_cluster_bootstrap(
            players, fit_positions=fail, original=(), replicates=4,
            batch_size=2, minimum_success_rate=0.99, progress=progress.append,
            context="family=star predictor=fixture",
        )
    assert [record["attempted"] for record in progress] == [2, 4]
    assert progress[-1]["failure_counts"]["nonconvergence"] == 4
    assert progress[-1]["termination_reason_counts"] == {"not_recorded": 4}
    assert progress[-1]["completed_batches"] == progress[-1]["total_batches"] == 2


@pytest.mark.parametrize("category", [
    "rank_failure", "missing_predictor_contrast", "missing_target_signal",
    "non_finite_likelihood", "nonconvergence", "other_numerical_error",
])
def test_indexed_bootstrap_checkpoints_diagnostics_for_every_failure_category(tmp_path, category):
    diagnostics = {
        "termination_reason": f"synthetic_{category}",
        "iteration_count": 17,
        "final_score_norm": 0.25,
        "final_newton_decrement": 0.125,
        "final_likelihood_change": 1e-9,
        "total_step_halvings": 23,
        "reduced_design_row_count": 4,
        "reduced_design_column_count": 3,
        "reduced_design_rank": 3,
        "condition_number": 12.5,
        "target_class_support": {"0.0": 2, "1.0": 2},
        "nuisance_control_nonzero_support": {"control": 2},
        "iteration_tail": [{
            "iteration_number": 17,
            "score_norm": 0.25,
            "newton_decrement": 0.125,
            "likelihood_change": 1e-9,
            "maximum_coefficient_update": 0.02,
            "step_halving_count": 1,
            "termination_reason": f"synthetic_{category}",
        }],
    }
    def fail(_positions):
        raise BootstrapReplicateError(category, "synthetic", diagnostics)

    result = indexed_player_cluster_bootstrap(
        pd.Series(["A", "B"]), fit_positions=fail, original=(),
        replicates=1, batch_size=1, minimum_success_rate=0.0,
        checkpoint_directory=tmp_path / category,
    )
    assert result.successful == 0
    payload = json.loads((tmp_path / category / "batch_0000_0000.json").read_text())
    record = payload["records"][0]
    assert record == {
        "replicate_index": 0, "status": category, "value": None,
        "diagnostics": diagnostics,
    }
    assert not ({"coefficient", "coefficients", "beta"} & set(record))
    manifest = json.loads((tmp_path / category / "task_manifest.json").read_text())
    assert manifest["signature"]["failure_diagnostic_schema"] == "failed_fit_diagnostics_v2_iteration_tail_20"


def test_success_checkpoint_record_format_is_unchanged_when_failures_have_diagnostics(tmp_path):
    calls = {"count": 0}
    def mixed(_positions):
        calls["count"] += 1
        if calls["count"] == 2:
            raise BootstrapReplicateError(
                "nonconvergence", "synthetic", {"termination_reason": "max_iterations"},
            )
        return (1.25,)
    indexed_player_cluster_bootstrap(
        pd.Series(["A", "B"]), fit_positions=mixed, original=(),
        replicates=2, batch_size=2, minimum_success_rate=0.5,
        checkpoint_directory=tmp_path,
    )
    records = json.loads((tmp_path / "batch_0000_0001.json").read_text())["records"]
    assert records[0] == {"replicate_index": 0, "status": "success", "value": [1.25]}
    assert records[1]["value"] is None
    assert records[1]["diagnostics"] == {"termination_reason": "max_iterations"}


def test_success_gate_error_aggregates_termination_reasons(tmp_path):
    reasons = iter(["max_iterations", "line_search_failure"])
    def fail(_positions):
        raise BootstrapReplicateError(
            "nonconvergence", "synthetic", {"termination_reason": next(reasons)},
        )
    with pytest.raises(RuntimeError, match=r"termination_reasons=.*line_search_failure.*max_iterations"):
        indexed_player_cluster_bootstrap(
            pd.Series(["A", "B"]), fit_positions=fail, original=(),
            replicates=2, batch_size=2, minimum_success_rate=0.99,
            checkpoint_directory=tmp_path,
        )
