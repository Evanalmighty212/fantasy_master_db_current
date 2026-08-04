"""
tests/test_dataset2_discovery_fit_clustering.py

Protects the Dataset 2 predictor-clustering discovery-fit methodology
LOCKED 2026-07 (commit 648ccad, see docs/LEAGUE_WINNER_TRAITS_SPEC.md's
"Predictor-clustering discovery/holdout boundary" section):
research/dataset2/trait_analysis_pipeline_predictor_inventory.py and
research/dataset2/overlap_floor_clustering_sensitivity_2026_07.py are
one-off research scripts, not lib/ modules -- this project's usual
convention doesn't hold loose research scripts to test coverage. This
file is a deliberate, narrow exception: the discovery-fit sourcing
these two scripts now share is DECISION-BEARING methodology (governs
which predictor clusters/representatives Phase 1 will ever see), not
exploratory analysis, so it gets the same regression protection a
lib/ module would.

Real-data integration checks only -- no predictor is tested against
any outcome/target column here (predictor-vs-outcome association
testing is Phase 1, not yet authorized).

AVAILABILITY GUARD: every fixture below reads real, gitignored,
pipeline-regenerated artifacts from data/exports/ (see CLAUDE.md's
"Generated data versus hand-maintained data") that do not exist on a
fresh clone until the Dataset 2 canonical build scripts have been run.
The whole module is skipped -- with a clear reason -- if any required
artifact is missing, rather than failing with a raw FileNotFoundError.
Pure unit tests belong in tests/test_dataset2_common.py instead, which
has no such guard because it never reads a real file.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent / "research" / "dataset2"))

import config
import trait_analysis_pipeline_predictor_inventory as tapi

_REQUIRED_ARTIFACTS = (
    tapi.PREDICTOR_TABLE_PATH,
    tapi.PREDICTOR_DICTIONARY_PATH,
)
_MISSING_ARTIFACTS = [p for p in _REQUIRED_ARTIFACTS if not Path(p).exists()]

pytestmark = pytest.mark.skipif(
    bool(_MISSING_ARTIFACTS),
    reason=(
        "Dataset 2 canonical predictor-table artifacts not present on this "
        f"checkout (missing: {_MISSING_ARTIFACTS}) -- these are gitignored, "
        "pipeline-regenerated files, not present on a fresh clone. Run "
        "scripts/build_dataset2_canonical_predictor_table.py to regenerate "
        "them, then re-run this test module."
    ),
)

_OUTCOME_TABLE_PATH = "data/exports/dataset2_canonical_outcome_table.parquet"
_OUTCOME_ARTIFACT_MISSING = not Path(_OUTCOME_TABLE_PATH).exists()


@pytest.fixture(scope="module")
def discovery_fit_real():
    return tapi.load_discovery_fit_predictor_table()


@pytest.fixture(scope="module")
def discovery_fit_historical():
    return tapi.load_historical_predictor_rows()


@pytest.fixture(scope="module")
def discovery_fit_registry():
    return tapi.load_predictor_dictionary()


@pytest.fixture(scope="module")
def discovery_fit_whitelist(discovery_fit_registry):
    return tapi.derive_predictor_whitelist_from_registry(discovery_fit_registry)


@pytest.fixture(scope="module")
def discovery_fit_inv(discovery_fit_real, discovery_fit_whitelist, discovery_fit_registry):
    inv = tapi.build_inventory(discovery_fit_real, discovery_fit_whitelist, discovery_fit_registry)
    inv = tapi.add_position_scoped_applicable_n(inv, discovery_fit_real)
    return inv


@pytest.fixture(scope="module")
def discovery_fit_inv_with_constancy(discovery_fit_inv, discovery_fit_historical, discovery_fit_real):
    """The FULL, export-ready inventory (every whitelist column, not a
    filtered constant-columns reporting copy) with constancy_status
    persisted, via the same tapi.add_constancy_status() wiring
    __main__ itself uses."""
    return tapi.add_constancy_status(discovery_fit_inv, discovery_fit_historical, discovery_fit_real)


@pytest.fixture(scope="module")
def discovery_fit_clusters(discovery_fit_real, discovery_fit_inv):
    return tapi.build_predictor_clusters(discovery_fit_real, discovery_fit_inv)


class TestDiscoveryFitSourcing:
    def test_exactly_8156_live_discovery_fit_rows_after_unresolved_exclusions(self, discovery_fit_real):
        historical_pre_authority_count = 8161
        discovery_era_unresolved_identity_conflicts = 4
        discovery_era_unresolved_position_authority = 1  # Patterson 2020
        assert len(discovery_fit_real) == (
            historical_pre_authority_count
            - discovery_era_unresolved_identity_conflicts
            - discovery_era_unresolved_position_authority
        )

    def test_canonical_predictor_artifact_used_as_source(self):
        assert tapi.PREDICTOR_TABLE_PATH == "data/exports/dataset2_canonical_predictor_table.parquet"

    def test_discovery_fit_rows_never_carry_outcome_join_status(self, discovery_fit_real):
        """Structural proof the loader read the canonical predictor
        table, not the joined analysis view -- the canonical table has
        no such column at all."""
        assert "outcome_join_status" not in discovery_fit_real.columns

    def test_discovery_fit_season_range_matches_config(self, discovery_fit_real):
        assert discovery_fit_real["prediction_season"].min() == config.DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_START_SEASON
        assert discovery_fit_real["prediction_season"].max() == config.DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_END_SEASON

    def test_whitelist_derived_from_canonical_registry(self, discovery_fit_whitelist, discovery_fit_registry):
        expected = sorted(
            discovery_fit_registry.loc[
                discovery_fit_registry["family_number"] != "N/A (spine)", "canonical_column"
            ].tolist()
        )
        assert discovery_fit_whitelist == expected
        assert len(discovery_fit_whitelist) == 440

    @pytest.mark.skipif(
        _OUTCOME_ARTIFACT_MISSING,
        reason=(
            f"{_OUTCOME_TABLE_PATH} not present on this checkout -- gitignored, "
            "pipeline-regenerated file, not present on a fresh clone. Run "
            "scripts/build_dataset2_canonical_outcome_table.py to regenerate "
            "it, then re-run this test."
        ),
    )
    def test_live_canonical_predictor_schema_has_no_exact_outcome_side_fields(self):
        predictor_df = pd.read_parquet(tapi.PREDICTOR_TABLE_PATH)
        outcome_df = pd.read_parquet(_OUTCOME_TABLE_PATH)
        overlap = set(predictor_df.columns) & set(outcome_df.columns)
        expected_shared_columns = {
            "player_id",
            "position",
            "canonical_position_status",
            "canonical_position_authority",
            "historical_input_revision",
        }
        assert overlap <= expected_shared_columns
        assert "outcome_join_status" not in predictor_df.columns

    def test_whitelist_does_not_blanket_ban_real_eligible_named_predictors(self, discovery_fit_whitelist):
        eligible_named = [c for c in discovery_fit_whitelist if "eligib" in c.lower()]
        assert len(eligible_named) > 0, "real predictor-side *_eligible_* columns must survive whitelist derivation"


class TestDiscoveryFitDeterminism:
    def test_deterministic_cluster_membership(self, discovery_fit_real, discovery_fit_inv):
        clusters_a, _, _ = tapi.build_predictor_clusters(discovery_fit_real, discovery_fit_inv)
        clusters_b, _, _ = tapi.build_predictor_clusters(discovery_fit_real, discovery_fit_inv)
        members_a = {frozenset(v["content"]) for cid, v in clusters_a.items() if cid != -1}
        members_b = {frozenset(v["content"]) for cid, v in clusters_b.items() if cid != -1}
        assert members_a == members_b

    def test_deterministic_representative_selection(self, discovery_fit_real, discovery_fit_inv):
        clusters_a, _, _ = tapi.build_predictor_clusters(discovery_fit_real, discovery_fit_inv)
        clusters_b, _, _ = tapi.build_predictor_clusters(discovery_fit_real, discovery_fit_inv)
        reps_a = {
            frozenset(v["content"]): tapi.select_cluster_representative(v["content"], discovery_fit_inv)
            for cid, v in clusters_a.items()
            if cid != -1 and v["content"]
        }
        reps_b = {
            frozenset(v["content"]): tapi.select_cluster_representative(v["content"], discovery_fit_inv)
            for cid, v in clusters_b.items()
            if cid != -1 and v["content"]
        }
        assert reps_a == reps_b


class TestDiscoveryFitDegenerateColumns:
    """The two predictors identified as constant-only-within-discovery-fit
    (real variance across the full, positively-defined 2006-2025
    historical predictor population) -- must be tagged distinctly,
    never described as universally constant, and PERSISTED in the
    full, export-ready inventory (constancy_status on `inv` itself),
    never limited to a throwaway filtered reporting copy."""

    def test_constancy_status_column_present_on_full_export_ready_inventory(self, discovery_fit_inv_with_constancy):
        assert "constancy_status" in discovery_fit_inv_with_constancy.columns
        # every real whitelist column gets a status, not just the constant ones
        assert len(discovery_fit_inv_with_constancy) == 440
        assert discovery_fit_inv_with_constancy["constancy_status"].notna().all()

    def test_fam9_team_first_half_team_games_is_discovery_fit_degenerate(self, discovery_fit_inv_with_constancy):
        row = discovery_fit_inv_with_constancy.loc[
            discovery_fit_inv_with_constancy["column"] == "fam9_team_first_half_team_games"
        ]
        assert row["constancy_status"].iloc[0] == "discovery_fit_degenerate"

    def test_fam86_wr_league_starter_group_size_norm_is_discovery_fit_degenerate(self, discovery_fit_inv_with_constancy):
        row = discovery_fit_inv_with_constancy.loc[
            discovery_fit_inv_with_constancy["column"] == "fam86_wr_league_starter_group_size_norm"
        ]
        assert row["constancy_status"].iloc[0] == "discovery_fit_degenerate"

    def test_total_constant_columns_under_discovery_fit_is_8(self, discovery_fit_inv_with_constancy):
        const_cols = discovery_fit_inv_with_constancy[discovery_fit_inv_with_constancy["n_unique"] <= 1]
        assert len(const_cols) == 8

    def test_six_of_eight_are_universally_constant_not_degenerate(self, discovery_fit_inv_with_constancy):
        const_cols = discovery_fit_inv_with_constancy[discovery_fit_inv_with_constancy["n_unique"] <= 1]
        universal = const_cols[const_cols["constancy_status"] == "universally_constant"]
        degenerate = const_cols[const_cols["constancy_status"] == "discovery_fit_degenerate"]
        assert len(universal) == 6
        assert len(degenerate) == 2
        assert set(universal["column"]).isdisjoint(set(degenerate["column"]))

    def test_varying_columns_tagged_varies_never_omitted(self, discovery_fit_inv_with_constancy):
        varying = discovery_fit_inv_with_constancy[discovery_fit_inv_with_constancy["n_unique"] > 1]
        assert len(varying) == 440 - 8
        assert (varying["constancy_status"] == "varies").all()


class TestDiscoveryFitClusteringResult:
    """Expected verified behavior of the discovery-fit (2006-2020)
    clustering result, re-verified fresh in this test run against the
    exact same real data used to derive these numbers during planning."""

    def test_content_columns_227(self, discovery_fit_clusters):
        _, _, stats = discovery_fit_clusters
        assert stats["n_content_columns"] == 227

    def test_144_current_clusters_become_143_discovery_fit_clusters(self, discovery_fit_clusters):
        clusters, _, _ = discovery_fit_clusters
        real_clusters = {cid: v for cid, v in clusters.items() if cid != -1}
        assert len(real_clusters) == 143

    def test_te_efficiency_rate_cluster_splits_into_singletons(self, discovery_fit_clusters, discovery_fit_inv):
        clusters, _, _ = discovery_fit_clusters
        member_sets = {frozenset(v["content"]) for cid, v in clusters.items() if cid != -1}
        pair = frozenset(
            {"fam9_active_final_6_te_receiving_efficiency_rate", "fam9_active_final_8_te_receiving_efficiency_rate"}
        )
        assert pair not in member_sets
        assert frozenset({"fam9_active_final_6_te_receiving_efficiency_rate"}) in member_sets
        assert frozenset({"fam9_active_final_8_te_receiving_efficiency_rate"}) in member_sets

    def test_qb_efficiency_rate_cluster_intact_with_new_representative(self, discovery_fit_clusters, discovery_fit_inv):
        clusters, _, _ = discovery_fit_clusters
        trio = frozenset(
            {
                "fam9_active_final_4_qb_passing_efficiency_rate",
                "fam9_active_final_6_qb_passing_efficiency_rate",
                "fam9_active_final_8_qb_passing_efficiency_rate",
            }
        )
        member_sets = {frozenset(v["content"]) for cid, v in clusters.items() if cid != -1}
        assert trio in member_sets  # membership unchanged
        representative = tapi.select_cluster_representative(sorted(trio), discovery_fit_inv)
        assert representative == "fam9_active_final_4_qb_passing_efficiency_rate"
