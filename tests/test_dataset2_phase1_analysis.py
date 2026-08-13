import pandas as pd
import pytest

from lib.dataset2.phase1_analysis import (
    benjamini_hochberg,
    eligibility_aware_expanding_windows,
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
    with pytest.raises(RuntimeError, match="success rate"):
        player_cluster_bootstrap(rows, player_column="player_id", fit=fit, replicates=10)
