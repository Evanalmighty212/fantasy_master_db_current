"""Fail-loud validation for privately retained governed source inputs.

The committed manifest records public-safe fingerprints. Raw provider
bytes and per-league records remain in controlled private storage.
Validation never fetches, repairs, substitutes, or rewrites a source.
"""

from __future__ import annotations

import hashlib
import json
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = REPO_ROOT / "scripts/preseason_source_manifest.json"
DEFAULT_PRIVATE_ARCHIVE_ROOT = Path.home() / ".ffre_private_archive"


class GovernedSourceError(RuntimeError):
    """A governed source is absent, malformed, or fingerprint-mismatched."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_source_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict:
    data = json.loads(Path(path).read_text())
    if data.get("manifest_version") != 1 or not isinstance(data.get("sources"), dict):
        raise GovernedSourceError(f"Invalid governed-source manifest structure: {path}")
    return data


def _require_file(path: Path, expected_hash: str, expected_size: int | None = None) -> None:
    if not path.is_file():
        raise GovernedSourceError(f"Governed source file is missing: {path}")
    actual_size = path.stat().st_size
    if expected_size is not None and actual_size != expected_size:
        raise GovernedSourceError(
            f"Governed source size mismatch for {path}: expected {expected_size}, got {actual_size}"
        )
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise GovernedSourceError(
            f"Governed source SHA-256 mismatch for {path}: expected {expected_hash}, got {actual_hash}"
        )


def validate_2011_fftoday_source(
    archive_root: Path = DEFAULT_PRIVATE_ARCHIVE_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> Path:
    entry = load_source_manifest(manifest_path)["sources"]["fftoday_ffc_2011_pre_kickoff"]
    path = Path(archive_root) / entry["private_archive_relative_path"]
    _require_file(path, entry["sha256"], entry["byte_count"])
    sensitivity = entry["timing_sensitivity"]
    if sensitivity.get("role") != "timing_sensitivity_only_not_canonical":
        raise GovernedSourceError("2011 September 6-9 source must remain timing sensitivity only")
    _require_file(REPO_ROOT / sensitivity["path"], sensitivity["sha256"], sensitivity["byte_count"])
    return path


def validate_2025_mfl_reconstruction(
    archive_root: Path = DEFAULT_PRIVATE_ARCHIVE_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    *,
    cache_root: Path,
    validate_cache_objects: bool = True,
) -> dict[str, Path]:
    entry = load_source_manifest(manifest_path)["sources"]["mfl_2025_strict_147_cache_reconstruction"]
    root = Path(archive_root) / entry["private_archive_relative_path"]
    expected = {
        "included_league_ids.txt": entry["included_league_ids_sha256"],
        "league_inclusion_ledger.csv": entry["league_inclusion_ledger_sha256"],
        "reconstruction_manifest.json": entry["reconstruction_manifest_sha256"],
        "reconstruct_147.py": entry["reconstruction_script_sha256"],
    }
    paths = {}
    for name, digest in expected.items():
        path = root / name
        _require_file(path, digest)
        paths[name] = path

    ids = [line.strip() for line in paths["included_league_ids.txt"].read_text().splitlines() if line.strip()]
    if len(ids) != entry["included_league_count"] or len(set(ids)) != len(ids):
        raise GovernedSourceError(
            "Governed MFL included-league list must contain exactly "
            f"{entry['included_league_count']} unique IDs; got {len(ids)} rows/{len(set(ids))} unique"
        )
    reconstruction = json.loads(paths["reconstruction_manifest.json"].read_text())
    if reconstruction.get("not_original_http_bytes") is not True or reconstruction.get("not_original_audited_package") is not True:
        raise GovernedSourceError("MFL reconstruction manifest must retain both provenance-limit flags")
    if reconstruction.get("included_league_count") != entry["included_league_count"]:
        raise GovernedSourceError("MFL reconstruction included-league count disagrees with committed manifest")
    for field in (
        "window_start_inclusive_utc", "window_end_exclusive_utc",
        "ordinary_market_participation_threshold", "principal_sensitivity_participation_threshold",
    ):
        if reconstruction.get(field) != entry.get(field):
            raise GovernedSourceError(f"MFL reconstruction {field} disagrees with committed manifest")
    with paths["league_inclusion_ledger.csv"].open(newline="") as handle:
        ledger = list(csv.DictReader(handle))
    included = [row for row in ledger if row.get("included", "").lower() == "true"]
    ledger_ids = [row["league_id"] for row in included]
    if ledger_ids != ids:
        raise GovernedSourceError("MFL included-league IDs do not exactly match the ordered inclusion ledger")
    required_true = ("discovery_filter_ppr_redraft_real_12team", "draft_complete", "all_picks_in_window")
    for field in required_true:
        if any(row.get(field, "").lower() != "true" for row in included):
            raise GovernedSourceError(f"MFL included ledger row violates {field}")
    if validate_cache_objects:
        cache_root = Path(cache_root)
        _require_file(
            cache_root / reconstruction["discovery_cache_file"],
            reconstruction["discovery_cache_sha256"], reconstruction["discovery_cache_size"],
        )
        _require_file(
            cache_root / reconstruction["player_directory_cache_file"],
            reconstruction["player_directory_cache_sha256"], reconstruction["player_directory_cache_size"],
        )
        for row in included:
            _require_file(cache_root / row["config_cache_file"], row["config_cache_sha256"], int(row["config_cache_size"]))
            _require_file(cache_root / row["draft_cache_file"], row["draft_cache_sha256"], int(row["draft_cache_size"]))
    return paths
