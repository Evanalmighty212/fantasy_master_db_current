"""Synthetic-only safeguards for the governed Phase 2 confirmation entry point.

No real 2021-2025 holdout row and no real governed inventory/cluster
artifact is read anywhere in this file -- every path the entry point
would normally read from data/exports/ is monkeypatched to a small
synthetic file written into tmp_path.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from lib.dataset2.phase1_runner import PredictorDefinition
from lib.dataset2.phase2_confirmation import Phase2Candidate
from lib.dataset2.phase2_runner import HoldoutConfirmationRecord
from scripts import run_dataset2_phase2_confirmation as entrypoint


class TestResolvePhase1SourceIdentity:
    def test_reads_git_head_and_hashes_primary_results(self, tmp_path):
        phase1_dir = tmp_path / "phase1_package"
        phase1_dir.mkdir()
        (phase1_dir / "configuration.json").write_text(json.dumps({"git_head": "abc123"}))
        content = "family,predictor_column\nlwi,trait\n"
        (phase1_dir / "primary_results.csv").write_text(content)

        git_head, checksum = entrypoint.resolve_phase1_source_identity(phase1_dir)

        assert git_head == "abc123"
        assert checksum == hashlib.sha256(content.encode("utf-8")).hexdigest()

    def test_raises_when_files_are_missing(self, tmp_path):
        phase1_dir = tmp_path / "empty"
        phase1_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            entrypoint.resolve_phase1_source_identity(phase1_dir)

    def test_raises_when_configuration_has_no_git_head(self, tmp_path):
        phase1_dir = tmp_path / "phase1_package"
        phase1_dir.mkdir()
        (phase1_dir / "configuration.json").write_text(json.dumps({}))
        (phase1_dir / "primary_results.csv").write_text("x")
        with pytest.raises(ValueError, match="no git_head"):
            entrypoint.resolve_phase1_source_identity(phase1_dir)


class TestSourcePackageMismatchOrdering:
    """Anchored to the requirement that source-package identity is verified
    before any holdout row can be loaded."""

    def test_mismatched_source_package_is_rejected_before_holdout_rows_loads(self, monkeypatch, tmp_path):
        phase1_dir = tmp_path / "phase1_package"
        phase1_dir.mkdir()
        (phase1_dir / "configuration.json").write_text(json.dumps({"git_head": "f" * 40}))
        (phase1_dir / "primary_results.csv").write_text("not the pinned package")

        def fail_if_called(*args, **kwargs):
            raise AssertionError("holdout_rows must not be called before source-package verification")
        monkeypatch.setattr(entrypoint, "holdout_rows", fail_if_called)

        output_dir = tmp_path / "phase2_output"
        with pytest.raises(ValueError, match="source package identity mismatch"):
            entrypoint.run_phase2_confirmation(phase1_dir, output_dir)
        assert not output_dir.exists()
        assert not output_dir.with_name(output_dir.name + ".partial").exists()


class TestReadDiscoveryEffects:
    def test_returns_pinned_adjusted_effects_for_supported_candidates(self, tmp_path):
        candidates = entrypoint.PHASE2_CANDIDATE_TRAITS[:2]
        phase1_dir = tmp_path / "phase1_package"
        phase1_dir.mkdir()
        frame = pd.DataFrame([
            {
                "family": candidate.family, "predictor_column": candidate.predictor_column,
                "supported": True, "adjusted_effects": json.dumps([0.5 + index * 0.1]),
            }
            for index, candidate in enumerate(candidates)
        ])
        frame.to_csv(phase1_dir / "primary_results.csv", index=False)

        effects = entrypoint.read_discovery_effects(phase1_dir, candidates)

        assert effects[(candidates[0].family, candidates[0].predictor_column)] == pytest.approx(0.5)
        assert effects[(candidates[1].family, candidates[1].predictor_column)] == pytest.approx(0.6)

    def test_raises_when_a_frozen_candidate_is_absent_from_the_package(self, tmp_path):
        candidates = entrypoint.PHASE2_CANDIDATE_TRAITS[:2]
        phase1_dir = tmp_path / "phase1_package"
        phase1_dir.mkdir()
        frame = pd.DataFrame([{
            "family": candidates[0].family, "predictor_column": candidates[0].predictor_column,
            "supported": True, "adjusted_effects": json.dumps([0.5]),
        }])
        frame.to_csv(phase1_dir / "primary_results.csv", index=False)
        with pytest.raises(ValueError, match="missing frozen Phase 2 candidates"):
            entrypoint.read_discovery_effects(phase1_dir, candidates)

    def test_raises_when_a_candidate_is_marked_not_supported(self, tmp_path):
        candidates = entrypoint.PHASE2_CANDIDATE_TRAITS[:1]
        phase1_dir = tmp_path / "phase1_package"
        phase1_dir.mkdir()
        frame = pd.DataFrame([{
            "family": candidates[0].family, "predictor_column": candidates[0].predictor_column,
            "supported": False, "adjusted_effects": json.dumps([0.5]),
        }])
        frame.to_csv(phase1_dir / "primary_results.csv", index=False)
        with pytest.raises(ValueError, match="not supported"):
            entrypoint.read_discovery_effects(phase1_dir, candidates)

    def test_raises_on_a_multi_contrast_candidate(self, tmp_path):
        candidates = entrypoint.PHASE2_CANDIDATE_TRAITS[:1]
        phase1_dir = tmp_path / "phase1_package"
        phase1_dir.mkdir()
        frame = pd.DataFrame([{
            "family": candidates[0].family, "predictor_column": candidates[0].predictor_column,
            "supported": True, "adjusted_effects": json.dumps([0.1, 0.2]),
        }])
        frame.to_csv(phase1_dir / "primary_results.csv", index=False)
        with pytest.raises(ValueError, match="expected exactly 1"):
            entrypoint.read_discovery_effects(phase1_dir, candidates)


class TestResolvePhase2PredictorDefinitions:
    def test_resolves_kind_and_cluster_from_governed_artifacts(self, monkeypatch, tmp_path):
        candidates = (Phase2Candidate("lwi", "trait_a"), Phase2Candidate("lwi", "trait_b"))
        inventory = pd.DataFrame([
            {"column": "trait_a", "var_type": "continuous"},
            {"column": "trait_b", "var_type": "boolean"},
        ])
        clusters = pd.DataFrame([
            {"cluster_id": "c1", "column": "trait_a", "role": "content", "is_representative": True},
            {"cluster_id": "c2", "column": "trait_b", "role": "content", "is_representative": True},
        ])
        inventory.to_csv(tmp_path / "inventory.csv", index=False)
        clusters.to_csv(tmp_path / "clusters.csv", index=False)
        monkeypatch.setattr(entrypoint, "INVENTORY", tmp_path / "inventory.csv")
        monkeypatch.setattr(entrypoint, "CLUSTERS", tmp_path / "clusters.csv")

        predictors = entrypoint.resolve_phase2_predictor_definitions(candidates)

        assert predictors["trait_a"].kind == "continuous"
        assert predictors["trait_a"].cluster_id == "c1"
        assert predictors["trait_b"].kind == "binary"
        assert predictors["trait_b"].cluster_id == "c2"

    def test_rejects_a_categorical_candidate(self, monkeypatch, tmp_path):
        candidates = (Phase2Candidate("lwi", "trait_a"),)
        inventory = pd.DataFrame([{"column": "trait_a", "var_type": "categorical/status"}])
        clusters = pd.DataFrame([
            {"cluster_id": "c1", "column": "trait_a", "role": "content", "is_representative": True},
        ])
        inventory.to_csv(tmp_path / "inventory.csv", index=False)
        clusters.to_csv(tmp_path / "clusters.csv", index=False)
        monkeypatch.setattr(entrypoint, "INVENTORY", tmp_path / "inventory.csv")
        monkeypatch.setattr(entrypoint, "CLUSTERS", tmp_path / "clusters.csv")
        with pytest.raises(ValueError, match="categorical"):
            entrypoint.resolve_phase2_predictor_definitions(candidates)

    def test_raises_when_a_candidate_is_absent_from_governed_artifacts(self, monkeypatch, tmp_path):
        candidates = (Phase2Candidate("lwi", "missing_trait"),)
        inventory = pd.DataFrame([{"column": "trait_a", "var_type": "continuous"}])
        clusters = pd.DataFrame([
            {"cluster_id": "c1", "column": "trait_a", "role": "content", "is_representative": True},
        ])
        inventory.to_csv(tmp_path / "inventory.csv", index=False)
        clusters.to_csv(tmp_path / "clusters.csv", index=False)
        monkeypatch.setattr(entrypoint, "INVENTORY", tmp_path / "inventory.csv")
        monkeypatch.setattr(entrypoint, "CLUSTERS", tmp_path / "clusters.csv")
        with pytest.raises(ValueError, match="absent from governed predictor artifacts"):
            entrypoint.resolve_phase2_predictor_definitions(candidates)


def _analysis_rows(seasons) -> pd.DataFrame:
    n = len(seasons)
    return pd.DataFrame({
        "prediction_season": seasons,
        "player_id": [f"p{i}" for i in range(n)],
        "trait": np.linspace(-1.0, 1.0, n),
        "lwi_score": np.linspace(-1.0, 1.0, n),
    })


class TestHoldoutRows:
    def test_selects_only_2021_through_2025(self, monkeypatch, tmp_path):
        source = _analysis_rows(list(range(2018, 2026)))
        path = tmp_path / "analysis.csv"
        source.to_csv(path, index=False)
        monkeypatch.setattr(entrypoint, "ANALYSIS_VIEW_CSV", path)
        monkeypatch.setattr(entrypoint, "HOLDOUT_CSV_CHUNK_SIZE", 3)

        rows = entrypoint.holdout_rows({"prediction_season", "player_id", "trait", "lwi_score"})

        assert sorted(rows["prediction_season"].unique()) == list(range(2021, 2026))

    def test_raises_when_a_holdout_season_is_missing(self, monkeypatch, tmp_path):
        source = _analysis_rows(list(range(2021, 2025)))  # 2025 missing
        path = tmp_path / "analysis.csv"
        source.to_csv(path, index=False)
        monkeypatch.setattr(entrypoint, "ANALYSIS_VIEW_CSV", path)
        with pytest.raises(ValueError, match="unexpected holdout season coverage"):
            entrypoint.holdout_rows({"prediction_season", "player_id", "trait", "lwi_score"})


class TestWriteConfirmationPackage:
    def test_writes_ledger_configuration_and_a_matching_hash_manifest(self, tmp_path):
        records = (
            HoldoutConfirmationRecord("lwi", "trait_a", 0.5, 0.5, 120, 5, "confirmed", None),
            HoldoutConfirmationRecord("lwi", "trait_b", 0.5, None, 0, 0, "inconclusive", "no eligible rows"),
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        entrypoint.write_confirmation_package(records, output_dir, {"a": 1})

        ledger = pd.read_csv(output_dir / "confirmation_ledger.csv")
        assert set(ledger["predictor_column"]) == {"trait_a", "trait_b"}
        assert json.loads((output_dir / "configuration.json").read_text()) == {"a": 1}
        manifest_lines = (output_dir / "outputs.sha256").read_text().strip().splitlines()
        assert len(manifest_lines) == 2
        for line in manifest_lines:
            digest, name = line.split("  ", 1)
            assert entrypoint.sha256(output_dir / name) == digest


class TestRunPhase2ConfirmationAtomicPromotion:
    """Everything up through confirm_all_candidates is monkeypatched to a
    synthetic single-candidate fixture; this class exercises only the
    write/promote mechanics, which must never depend on any real
    governed data or real Phase 1 package."""

    def _wire_common_mocks(self, monkeypatch, tmp_path, phase1_dir):
        monkeypatch.setattr(entrypoint, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(entrypoint.subprocess, "check_output", lambda *a, **k: "fake_code_git_head\n")
        phase1_dir.mkdir()
        (phase1_dir / "configuration.json").write_text(json.dumps({"git_head": "irrelevant"}))
        (phase1_dir / "primary_results.csv").write_text("irrelevant")
        for name in ("analysis.csv", "inventory.csv", "clusters.csv"):
            (tmp_path / name).write_text("placeholder\n")
        (tmp_path / "whitelist.csv").write_text("predictor_column\ntrait_a\n")
        monkeypatch.setattr(entrypoint, "ANALYSIS_VIEW_CSV", tmp_path / "analysis.csv")
        monkeypatch.setattr(entrypoint, "WHITELIST", tmp_path / "whitelist.csv")
        monkeypatch.setattr(entrypoint, "INVENTORY", tmp_path / "inventory.csv")
        monkeypatch.setattr(entrypoint, "CLUSTERS", tmp_path / "clusters.csv")
        candidate = Phase2Candidate("lwi", "trait_a")
        predictor = PredictorDefinition("trait_a", "continuous", "c1", True)
        monkeypatch.setattr(entrypoint, "PHASE2_CANDIDATE_TRAITS", (candidate,))
        monkeypatch.setattr(entrypoint, "verify_phase1_source_package", lambda *a, **k: None)
        monkeypatch.setattr(entrypoint, "read_discovery_effects", lambda *a, **k: {("lwi", "trait_a"): 0.5})
        monkeypatch.setattr(
            entrypoint, "resolve_phase2_predictor_definitions", lambda *a, **k: {"trait_a": predictor},
        )
        monkeypatch.setattr(entrypoint, "validate_predictor_definitions", lambda *a, **k: None)
        fake_rows = pd.DataFrame({"prediction_season": [2021, 2022], "trait_a": [1.0, 2.0]})
        monkeypatch.setattr(entrypoint, "holdout_rows", lambda *a, **k: fake_rows)
        fake_record = HoldoutConfirmationRecord("lwi", "trait_a", 0.5, 0.5, 2, 2, "confirmed", None)
        monkeypatch.setattr(entrypoint, "confirm_all_candidates", lambda *a, **k: (fake_record,))

    def test_success_promotes_output_and_leaves_no_partial(self, monkeypatch, tmp_path):
        phase1_dir = tmp_path / "phase1_package"
        self._wire_common_mocks(monkeypatch, tmp_path, phase1_dir)
        output_dir = tmp_path / "phase2_output"

        entrypoint.run_phase2_confirmation(phase1_dir, output_dir)

        assert output_dir.exists()
        assert not output_dir.with_name(output_dir.name + ".partial").exists()
        ledger = pd.read_csv(output_dir / "confirmation_ledger.csv")
        assert ledger.loc[0, "verdict"] == "confirmed"
        manifest_lines = (output_dir / "outputs.sha256").read_text().strip().splitlines()
        assert len(manifest_lines) == 2

    def test_failure_before_any_file_write_promotes_nothing_and_cleans_up(self, monkeypatch, tmp_path):
        phase1_dir = tmp_path / "phase1_package"
        self._wire_common_mocks(monkeypatch, tmp_path, phase1_dir)

        def raising_writer(*args, **kwargs):
            raise RuntimeError("simulated write failure")
        monkeypatch.setattr(entrypoint, "write_confirmation_package", raising_writer)
        output_dir = tmp_path / "phase2_output"

        with pytest.raises(RuntimeError, match="simulated write failure"):
            entrypoint.run_phase2_confirmation(phase1_dir, output_dir)

        assert not output_dir.exists()
        assert not output_dir.with_name(output_dir.name + ".partial").exists()

    def test_failure_after_partial_write_leaves_partial_for_review_not_promoted(self, monkeypatch, tmp_path):
        phase1_dir = tmp_path / "phase1_package"
        self._wire_common_mocks(monkeypatch, tmp_path, phase1_dir)

        def partially_writing_then_raising(records, output_directory, configuration):
            (output_directory / "confirmation_ledger.csv").write_text("partial\n")
            raise RuntimeError("simulated failure after partial write")
        monkeypatch.setattr(entrypoint, "write_confirmation_package", partially_writing_then_raising)
        output_dir = tmp_path / "phase2_output"

        with pytest.raises(RuntimeError, match="simulated failure after partial write"):
            entrypoint.run_phase2_confirmation(phase1_dir, output_dir)

        assert not output_dir.exists()
        partial = output_dir.with_name(output_dir.name + ".partial")
        assert partial.exists()
        assert (partial / "confirmation_ledger.csv").exists()

    def test_refuses_to_run_over_a_stale_partial_directory(self, tmp_path):
        phase1_dir = tmp_path / "phase1_package"  # deliberately never created; unreached
        output_dir = tmp_path / "phase2_output"
        output_dir.with_name(output_dir.name + ".partial").mkdir(parents=True)

        with pytest.raises(FileExistsError, match="stale Phase 2 partial output"):
            entrypoint.run_phase2_confirmation(phase1_dir, output_dir)
