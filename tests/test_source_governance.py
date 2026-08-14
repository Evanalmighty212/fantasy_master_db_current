import hashlib
import json
from pathlib import Path

import pytest

from lib.source_governance import (
    GovernedSourceError,
    load_source_manifest,
    validate_2011_fftoday_source,
    validate_2025_mfl_reconstruction,
)


def _write(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_live_manifest_records_exact_governed_fingerprints():
    sources = load_source_manifest()["sources"]
    ffc = sources["fftoday_ffc_2011_pre_kickoff"]
    assert ffc["sha256"] == "dd26ad40eecab0e3882b4cb9dce3521e7da2c41431ed77db1c3e58f9158d58f0"
    assert ffc["byte_count"] == 61275
    assert ffc["role"] == "canonical_2011_acquisition_source"
    assert ffc["timing_sensitivity"]["path"] == "data/raw/adp/ffc_adp_2011_ppr.json"
    assert ffc["timing_sensitivity"]["role"] == "timing_sensitivity_only_not_canonical"
    mfl = sources["mfl_2025_strict_142_cache_reconstruction"]
    assert mfl["included_league_count"] == 142
    assert mfl["included_genuine_player_pick_count"] == 27840
    assert mfl["window_end_exclusive_utc"] == "2025-09-05T00:20:00Z"
    assert "Not original HTTP wire bytes" in mfl["provenance_limit"]


def test_2025_validation_requires_caller_supplied_cache_root():
    with pytest.raises(TypeError, match="cache_root"):
        validate_2025_mfl_reconstruction()


def test_2011_validation_rejects_size_or_hash_mismatch(tmp_path):
    archive = tmp_path / "archive"
    manifest = tmp_path / "manifest.json"
    content = b"exact"
    rel = "ffc/source.html"
    _write(archive / rel, content)
    manifest.write_text(json.dumps({"manifest_version": 1, "sources": {
        "fftoday_ffc_2011_pre_kickoff": {
            "private_archive_relative_path": rel,
            "sha256": hashlib.sha256(content).hexdigest(),
            "byte_count": len(content),
            "timing_sensitivity": {
                "path": "data/raw/adp/ffc_adp_2011_ppr.json",
                "role": "timing_sensitivity_only_not_canonical",
                "sha256": "0619b681891046d3261f00eb280404ce249e75c7cd777eb271ae572dd4b58a6e",
                "byte_count": 49752,
            },
        }
    }}))
    assert validate_2011_fftoday_source(archive, manifest) == archive / rel
    (archive / rel).write_bytes(b"changed")
    with pytest.raises(GovernedSourceError, match="size mismatch|SHA-256 mismatch"):
        validate_2011_fftoday_source(archive, manifest)


def test_2025_validation_requires_hashes_count_and_provenance_flags(tmp_path):
    archive = tmp_path / "archive"
    root = archive / "mfl/package"
    files = {
        "included_league_ids.txt": b"1\n2\n",
        "league_inclusion_ledger.csv": (
            b"league_id,included,discovery_filter_ppr_redraft_real_12team,draft_complete,all_picks_in_window,valid_pick_count,expected_pick_count\n"
            b"1,true,true,true,true,1,1\n2,true,true,true,true,1,1\n"
        ),
        "reconstruction_manifest.json": json.dumps({
            "not_original_http_bytes": True,
            "not_original_audited_package": True,
            "included_league_count": 2,
            "included_genuine_player_pick_count": 2,
            "window_start_inclusive_utc": "start",
            "window_end_exclusive_utc": "end",
            "ordinary_market_participation_threshold": 0.35,
            "principal_sensitivity_participation_threshold": 0.30,
        }).encode(),
        "reconstruct_142.py": b"# deterministic fixture\n",
    }
    hashes = {name: _write(root / name, body) for name, body in files.items()}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"manifest_version": 1, "sources": {
        "mfl_2025_strict_142_cache_reconstruction": {
            "private_archive_relative_path": "mfl/package",
                "included_league_count": 2,
                "included_genuine_player_pick_count": 2,
                "window_start_inclusive_utc": "start",
                "window_end_exclusive_utc": "end",
                "ordinary_market_participation_threshold": 0.35,
                "principal_sensitivity_participation_threshold": 0.30,
            "included_league_ids_sha256": hashes["included_league_ids.txt"],
            "league_inclusion_ledger_sha256": hashes["league_inclusion_ledger.csv"],
            "reconstruction_manifest_sha256": hashes["reconstruction_manifest.json"],
            "reconstruction_script_filename": "reconstruct_142.py",
            "reconstruction_script_sha256": hashes["reconstruct_142.py"],
        }
    }}))
    assert set(validate_2025_mfl_reconstruction(
        archive, manifest, cache_root=tmp_path / "explicit-cache", validate_cache_objects=False,
    )) == set(files)
    (root / "included_league_ids.txt").write_text("1\n1\n")
    with pytest.raises(GovernedSourceError, match="SHA-256 mismatch"):
        validate_2025_mfl_reconstruction(
            archive, manifest, cache_root=tmp_path / "explicit-cache", validate_cache_objects=False,
        )
