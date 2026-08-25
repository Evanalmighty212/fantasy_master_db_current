"""
tests/test_ci_fetch_players.py

Covers scripts/ci_fetch_players.py (the players.csv CI refresh driver)
and .github/workflows/fetch_players.yml (the workflow that runs it).

No real network call and no real manifest mutation happens anywhere in
this file -- nflverse_source's actual HTTP/download functions are
monkeypatched to synthetic stubs throughout, and every manifest/cache
path used is a pytest tmp_path, never the real committed
scripts/nflverse_source_manifest.json or
data/raw/nflverse/reference/players.csv.

Each test protects a real requirement from the operational-readiness
review, not speculative coverage:
- the driver must touch ONLY the players registration/fetch path,
  never any other nflverse_source release (stats_player, schedules,
  depth_charts, snap_counts, pbp_participation) or any pipeline stage;
- a players refresh must change ONLY the manifest's "players" key --
  every other key must survive byte-for-byte, including at the JSON
  serialization level (not just Python dict equality), since a subtle
  int/float or key-order reformat would be invisible to `==` but real
  in the committed file;
- the summary file's sha256/row_count must agree with what was
  actually written to the candidate manifest and raw cache file;
- the workflow must be workflow_dispatch-only, read-only permissions,
  and contain no commit/push step -- this is a review-artifact
  workflow, never a self-committing one.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import nflverse_source  # noqa: E402
import ci_fetch_players  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "ci_fetch_players.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "fetch_players.yml"

# Every OTHER nflverse_source release's register/fetch functions -- none
# of these may ever be called by ci_fetch_players.py.
_OTHER_RELEASE_FUNCTIONS = (
    "register_manifest_entry", "fetch_season_raw", "fetch_and_normalize",
    "register_schedules_manifest_entry", "fetch_schedules_raw", "fetch_schedules",
    "register_depth_chart_manifest_entry", "fetch_depth_chart_raw", "fetch_depth_chart",
    "register_snap_counts_manifest_entry", "fetch_snap_counts_raw", "fetch_snap_counts",
    "register_pbp_participation_manifest_entry", "fetch_pbp_participation_raw", "fetch_pbp_participation",
)

# Pipeline-stage modules this driver must never import or reach.
_FORBIDDEN_PIPELINE_MODULE_NAMES = (
    "clean_adp", "download_stats", "build_master_dataset", "calculate_metrics",
    "generate_rankings", "build_dataset2_canonical_predictor_table",
    "canonical_predictor_table", "future_season_spine",
)


def _forbidden(name):
    def _raise(*args, **kwargs):
        raise AssertionError(f"{name} must not be called by ci_fetch_players.py")
    return _raise


def _sample_manifest():
    return {
        "schema_version": "nflverse_stats_player_v1",
        "seasons": {"2024": {"asset_id": 111, "sha256": "aaa", "row_count": 5000, "retrieved_at": "2026-01-01T00:00:00+00:00"}},
        "schedules": {"asset_id": 222, "sha256": "bbb", "row_count": 7548, "retrieved_at": "2026-07-30T20:10:49.594119+00:00"},
        "depth_charts": {"seasons": {"2024": {"asset_id": 333, "sha256": "ccc", "row_count": 100}}},
        "snap_counts": {"seasons": {"2024": {"asset_id": 444, "sha256": "ddd", "row_count": 200}}},
        "pbp_participation": {"seasons": {"2024": {"asset_id": 555, "sha256": "eee", "row_count": 300}}},
        # A value pair chosen specifically to catch a serialization-level
        # (not just Python == ) mutation: 1 and 1.0 are == in Python but
        # serialize to different JSON text ("1" vs "1.0").
        "an_integer_value": 1,
        "a_float_value": 1.0,
    }


class TestDriverTouchesOnlyThePlayersPath:
    def test_calling_main_never_reaches_any_other_release_function(self, tmp_path, monkeypatch):
        for fn_name in _OTHER_RELEASE_FUNCTIONS:
            monkeypatch.setattr(nflverse_source, fn_name, _forbidden(fn_name))

        players_cache = tmp_path / "players.csv"
        players_cache.write_text("gsis_id,position\np1,WR\np2,RB\n")

        def fake_register():
            return {
                "asset_id": 999, "upstream_updated_at": "2026-08-24T00:00:00Z",
                "asset_url": "https://example.invalid/players", "retrieved_at": "2026-08-24T12:00:00+00:00",
                "sha256": hashlib.sha256(players_cache.read_bytes()).hexdigest(),
                "schema_version": "nflverse_players_v1", "row_count": 2,
            }

        monkeypatch.setattr(nflverse_source, "register_players_manifest_entry", fake_register)

        import pandas as pd
        monkeypatch.setattr(nflverse_source, "fetch_players", lambda: pd.read_csv(players_cache))
        monkeypatch.setattr(ci_fetch_players, "SUMMARY_PATH", tmp_path / "players_fetch_summary.json")

        ci_fetch_players.main()  # must complete without tripping any _forbidden() call above

    def test_script_source_imports_only_nflverse_source_and_stdlib(self):
        tree = ast.parse(SCRIPT_PATH.read_text())
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
        forbidden_hits = {
            name for name in imported_names
            if any(forbidden in name for forbidden in _FORBIDDEN_PIPELINE_MODULE_NAMES)
        }
        assert forbidden_hits == set(), f"ci_fetch_players.py imports forbidden pipeline module(s): {forbidden_hits}"
        assert imported_names <= {"json", "sys", "pathlib", "nflverse_source"}

    def test_script_code_contains_no_reference_to_other_pipeline_scripts(self):
        # Checks CODE only (every AST node's own source segment via
        # ast.get_source_segment), not the module docstring/comments --
        # this script's own docstring legitimately NAMES several
        # forbidden scripts in prose to explain what it does NOT do
        # (e.g. "It imports nothing from ... 04_build_master_dataset.py"),
        # which a raw substring-on-full-text check would misfire on.
        tree = ast.parse(SCRIPT_PATH.read_text())
        source = SCRIPT_PATH.read_text()
        code_segments = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.Call, ast.Assign)):
                segment = ast.get_source_segment(source, node)
                if segment:
                    code_segments.append(segment)
        combined_code = "\n".join(code_segments)
        for forbidden in _FORBIDDEN_PIPELINE_MODULE_NAMES:
            assert forbidden not in combined_code, (
                f"ci_fetch_players.py's actual code (not docstring/comments) references "
                f"forbidden name {forbidden!r}"
            )


class TestManifestChangesOnlyThePlayersEntry:
    def test_other_manifest_keys_survive_byte_for_byte_through_serialization(self, tmp_path, monkeypatch):
        manifest_path = tmp_path / "nflverse_source_manifest.json"
        original = _sample_manifest()
        manifest_path.write_text(json.dumps(original, indent=2, sort_keys=True) + "\n")

        players_cache = tmp_path / "players.csv"
        monkeypatch.setattr(nflverse_source, "MANIFEST_PATH", manifest_path)
        monkeypatch.setattr(nflverse_source, "PLAYERS_CACHE_PATH", players_cache)
        monkeypatch.setattr(
            nflverse_source, "_lookup_asset_id_by_name",
            lambda tag, name: {"asset_id": 777, "upstream_updated_at": "2026-08-24T00:00:00Z"},
        )

        def fake_download(asset_id, local_path):
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text("gsis_id,position\np1,WR\np2,RB\np3,QB\n")

        monkeypatch.setattr(nflverse_source, "_download_by_asset_id", fake_download)

        nflverse_source.register_players_manifest_entry()

        updated = json.loads(manifest_path.read_text())
        assert "players" in updated
        assert updated["players"]["asset_id"] == 777
        assert updated["players"]["row_count"] == 3

        original_without_players = {k: v for k, v in original.items() if k != "players"}
        updated_without_players = {k: v for k, v in updated.items() if k != "players"}

        # Dict-level equality (would miss a silent 1 -> 1.0 reformat)...
        assert updated_without_players == original_without_players
        # ...AND serialization-level equality, using this project's own
        # exact _save_manifest() convention, so any formatting side
        # effect (key reorder, float/int coercion, whitespace) on any
        # OTHER key is caught even if it happened to compare == in Python.
        assert (
            json.dumps(updated_without_players, indent=2, sort_keys=True)
            == json.dumps(original_without_players, indent=2, sort_keys=True)
        )


class TestSummaryAgreesWithCandidateArtifacts:
    def test_summary_sha256_and_row_count_match_the_candidate_manifest_and_raw_file(self, tmp_path, monkeypatch):
        manifest_path = tmp_path / "nflverse_source_manifest.json"
        manifest_path.write_text(json.dumps(_sample_manifest(), indent=2, sort_keys=True) + "\n")
        players_cache = tmp_path / "players.csv"
        summary_path = tmp_path / "players_fetch_summary.json"

        monkeypatch.setattr(nflverse_source, "MANIFEST_PATH", manifest_path)
        monkeypatch.setattr(nflverse_source, "PLAYERS_CACHE_PATH", players_cache)
        monkeypatch.setattr(
            nflverse_source, "_lookup_asset_id_by_name",
            lambda tag, name: {"asset_id": 888, "upstream_updated_at": "2026-08-24T00:00:00Z"},
        )

        def fake_download(asset_id, local_path):
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text("gsis_id,position,status\np1,WR,ACT\np2,RB,ACT\np3,QB,UDF\np4,TE,ACT\n")

        monkeypatch.setattr(nflverse_source, "_download_by_asset_id", fake_download)
        monkeypatch.setattr(ci_fetch_players, "SUMMARY_PATH", summary_path)

        ci_fetch_players.main()

        summary = json.loads(summary_path.read_text())
        manifest = json.loads(manifest_path.read_text())
        real_sha256 = hashlib.sha256(players_cache.read_bytes()).hexdigest()
        real_row_count = sum(1 for _ in players_cache.open()) - 1

        assert summary["sha256"] == manifest["players"]["sha256"] == real_sha256
        assert summary["row_count"] == manifest["players"]["row_count"] == real_row_count == 4
        assert summary["asset_id"] == manifest["players"]["asset_id"] == 888
        assert summary["schema_version"] == manifest["players"]["schema_version"]
        assert summary["upstream_updated_at"] == manifest["players"]["upstream_updated_at"]
        assert summary["retrieved_at"] == manifest["players"]["retrieved_at"]
        assert set(summary.keys()) == {
            "asset_id", "upstream_updated_at", "retrieved_at", "sha256", "row_count", "schema_version",
        }


class TestWorkflowIsManualOnlyWithNoWriteOperation:
    def test_workflow_trigger_is_workflow_dispatch_only(self):
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text())
        # PyYAML parses the bare `on:` key as boolean True in YAML 1.1
        trigger_key = True if True in workflow else "on"
        triggers = workflow[trigger_key]
        assert set(triggers.keys()) == {"workflow_dispatch"}

    def test_workflow_permissions_are_read_only(self):
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text())
        assert workflow["permissions"] == {"contents": "read"}

    def test_workflow_runs_only_the_players_driver_script(self):
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text())
        jobs = workflow["jobs"]
        assert len(jobs) == 1
        steps = next(iter(jobs.values()))["steps"]
        run_steps = [s["run"] for s in steps if "run" in s]
        assert any("scripts/ci_fetch_players.py" in cmd for cmd in run_steps)
        forbidden_scripts = (
            "02_clean_adp.py", "03_download_stats.py", "04_build_master_dataset.py",
            "05_calculate_metrics.py", "06_generate_rankings.py", "ci_fetch_schedules.py",
            "ci_fetch_adp_phase1.py", "build_dataset2_canonical_predictor_table.py",
        )
        for cmd in run_steps:
            for forbidden in forbidden_scripts:
                assert forbidden not in cmd, f"workflow step invokes forbidden script: {cmd!r}"

    def test_workflow_contains_no_commit_or_push_operation(self):
        # Checks parsed `run:`/`uses:` step content only, not the raw
        # file text -- this workflow's own header comment legitimately
        # explains "there is no write token, git push, or git commit
        # step anywhere below" in prose, which a raw substring-on-full-
        # text check would misfire on. YAML comments are stripped by
        # yaml.safe_load(), so this is the actual executable content.
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text())
        steps = next(iter(workflow["jobs"].values()))["steps"]
        step_text = "\n".join(
            f"{step.get('run', '')} {step.get('uses', '')}" for step in steps
        )
        for forbidden_substring in ("git push", "git commit", "git add"):
            assert forbidden_substring not in step_text, (
                f"a workflow step contains a write/commit operation: {forbidden_substring!r}"
            )
        assert workflow.get("permissions", {}).get("contents") != "write"

    def test_workflow_uploads_exactly_the_three_expected_review_files(self):
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text())
        steps = next(iter(workflow["jobs"].values()))["steps"]
        upload_steps = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact")]
        assert len(upload_steps) == 1
        upload_with = upload_steps[0]["with"]
        assert upload_with["name"] == "players-candidate-snapshot-and-manifest"
        uploaded_paths = upload_with["path"].strip().splitlines()
        assert set(p.strip() for p in uploaded_paths) == {
            "data/raw/nflverse/reference/players.csv",
            "data/raw/nflverse/reference/players_fetch_summary.json",
            "scripts/nflverse_source_manifest.json",
        }
