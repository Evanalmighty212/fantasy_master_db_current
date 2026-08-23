#!/usr/bin/env python3
"""Governed Dataset 2 Phase 2 holdout-confirmation execution.

Verifies the frozen Phase 1 source package's identity (git HEAD and
primary_results.csv checksum) before a single 2021-2025 holdout row is
loaded, reads each frozen candidate's discovery effect from that
package without recomputing it, fits each of the 32 frozen candidates
exactly once on holdout rows only (no bootstrap, no resampling), and
classifies each under the frozen Option B rule. Results remain under a
clearly named partial directory until the complete package and hash
manifest have been written successfully.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import (  # noqa: E402
    DATASET2_HOLDOUT_END_SEASON,
    DATASET2_HOLDOUT_START_SEASON,
    DATASET2_PHASE2_DISCOVERY_LWI_OUTCOME_SD,
    DATASET2_PHASE2_METHODOLOGY_VERSION,
)
from lib.dataset2.phase1_runner import (  # noqa: E402
    PredictorDefinition,
    validate_predictor_definitions,
)
from lib.dataset2.phase2_confirmation import (  # noqa: E402
    PHASE2_CANDIDATE_TRAITS,
    PHASE2_EXCLUDED_UNSTABLE_TRAITS,
    Phase2Candidate,
    verify_phase1_source_package,
)
from lib.dataset2.phase2_runner import (  # noqa: E402
    HoldoutConfirmationRecord,
    confirm_all_candidates,
)

EXPORTS = REPO_ROOT / "data" / "exports"
ANALYSIS_VIEW_CSV = EXPORTS / "dataset2_analysis_view.csv"
WHITELIST = EXPORTS / "dataset2_analysis_view_predictor_whitelist.csv"
INVENTORY = EXPORTS / "dataset2_trait_pipeline_predictor_inventory.csv"
CLUSTERS = EXPORTS / "dataset2_trait_pipeline_predictor_clusters.csv"
HOLDOUT_CSV_CHUNK_SIZE = 10_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True)


def resolve_phase1_source_identity(phase1_package_dir: Path) -> tuple[str, str]:
    """Read the git HEAD and primary_results.csv checksum a Phase 1 package records.

    Read-only: never inspects holdout-relevant content, only the
    package's own recorded provenance and a file checksum.
    """
    configuration_path = phase1_package_dir / "configuration.json"
    primary_results_path = phase1_package_dir / "primary_results.csv"
    if not configuration_path.is_file() or not primary_results_path.is_file():
        raise FileNotFoundError(
            "Phase 1 source package is missing configuration.json or "
            f"primary_results.csv: {phase1_package_dir}"
        )
    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    git_head = configuration.get("git_head")
    if not isinstance(git_head, str) or not git_head:
        raise ValueError(
            f"Phase 1 source package configuration.json has no git_head: {phase1_package_dir}"
        )
    return git_head, sha256(primary_results_path)


def read_discovery_effects(
    phase1_package_dir: Path, candidates: tuple[Phase2Candidate, ...],
) -> dict[tuple[str, str], float]:
    """Read each candidate's already-computed discovery effect; never recompute it."""
    primary = pd.read_csv(phase1_package_dir / "primary_results.csv")
    indexed = primary.set_index(["family", "predictor_column"])
    effects: dict[tuple[str, str], float] = {}
    missing = []
    for candidate in candidates:
        key = (candidate.family, candidate.predictor_column)
        if key not in indexed.index:
            missing.append(key)
            continue
        row = indexed.loc[key]
        if isinstance(row, pd.DataFrame):
            raise ValueError(f"duplicate Phase 1 result rows for {key}")
        if not bool(row["supported"]):
            raise ValueError(
                f"pinned Phase 1 package marks frozen Phase 2 candidate as not supported: {key}"
            )
        adjusted = json.loads(row["adjusted_effects"])
        if len(adjusted) != 1:
            raise ValueError(
                f"Phase 2 candidate {key} has {len(adjusted)} discovery contrasts; expected exactly 1"
            )
        effects[key] = float(adjusted[0])
    if missing:
        raise ValueError(f"pinned Phase 1 package is missing frozen Phase 2 candidates: {missing}")
    return effects


def resolve_phase2_predictor_definitions(
    candidates: tuple[Phase2Candidate, ...],
) -> dict[str, PredictorDefinition]:
    """Resolve kind/cluster_id for each candidate from the same governed
    inventory/cluster artifacts Phase 1 discovery used -- never hand-copied."""
    inventory = pd.read_csv(INVENTORY)
    clusters = pd.read_csv(CLUSTERS)
    representatives = clusters.loc[
        clusters["role"].eq("content") & clusters["is_representative"].astype(bool),
        ["cluster_id", "column"],
    ].merge(inventory[["column", "var_type"]], on="column", how="left", validate="one_to_one")
    kind_map = {"continuous": "continuous", "boolean": "binary", "categorical/status": "categorical"}
    by_column = {row.column: row for row in representatives.itertuples(index=False)}
    predictors: dict[str, PredictorDefinition] = {}
    missing = []
    for candidate in candidates:
        record = by_column.get(candidate.predictor_column)
        if record is None:
            missing.append(candidate.predictor_column)
            continue
        if record.var_type not in kind_map:
            raise ValueError(f"unknown predictor type for {candidate.predictor_column}: {record.var_type}")
        kind = kind_map[record.var_type]
        if kind == "categorical":
            raise ValueError(
                f"Phase 2 candidate {candidate.predictor_column} is categorical; "
                "categorical holdout fitting is unimplemented"
            )
        predictors[candidate.predictor_column] = PredictorDefinition(
            column=candidate.predictor_column, kind=kind, cluster_id=str(record.cluster_id),
            is_cluster_representative=True,
        )
    if missing:
        raise ValueError(f"frozen Phase 2 candidates are absent from governed predictor artifacts: {missing}")
    return predictors


def holdout_rows(required_columns: set[str]) -> pd.DataFrame:
    """Stream the accepted analysis-view CSV, retaining only 2021-2025 rows."""
    chunks = []
    for chunk in pd.read_csv(
        ANALYSIS_VIEW_CSV, usecols=sorted(required_columns), chunksize=HOLDOUT_CSV_CHUNK_SIZE,
        low_memory=False, float_precision="round_trip",
    ):
        seasons = pd.to_numeric(chunk["prediction_season"], errors="raise")
        chunks.append(chunk.loc[seasons.between(
            DATASET2_HOLDOUT_START_SEASON, DATASET2_HOLDOUT_END_SEASON,
        )].copy())
    if not chunks:
        raise ValueError("accepted analysis-view CSV yielded no chunks")
    rows = pd.concat(chunks, ignore_index=True)
    seasons = pd.to_numeric(rows["prediction_season"], errors="raise")
    rows = rows.loc[seasons.between(DATASET2_HOLDOUT_START_SEASON, DATASET2_HOLDOUT_END_SEASON)].copy()
    observed = sorted(rows["prediction_season"].astype(int).unique().tolist())
    expected = list(range(DATASET2_HOLDOUT_START_SEASON, DATASET2_HOLDOUT_END_SEASON + 1))
    if observed != expected:
        raise ValueError(f"unexpected holdout season coverage: {observed}")
    return rows


def write_confirmation_package(
    records: tuple[HoldoutConfirmationRecord, ...],
    output_directory: Path,
    configuration: dict[str, object],
) -> None:
    ledger = pd.DataFrame([{
        "family": record.family,
        "predictor_column": record.predictor_column,
        "discovery_effect": record.discovery_effect,
        "holdout_effect": record.holdout_effect,
        "holdout_n": record.holdout_n,
        "holdout_seasons_represented": record.holdout_seasons_represented,
        "verdict": record.verdict,
        "fit_failure_reason": record.fit_failure_reason,
    } for record in records]).sort_values(["family", "predictor_column"], kind="mergesort")
    ledger.to_csv(output_directory / "confirmation_ledger.csv", index=False, lineterminator="\n")
    (output_directory / "configuration.json").write_text(stable_json(configuration) + "\n", encoding="utf-8")
    paths = sorted(path for path in output_directory.iterdir() if path.is_file())
    (output_directory / "outputs.sha256").write_text(
        "\n".join(f"{sha256(path)}  {path.name}" for path in paths) + "\n", encoding="utf-8",
    )


def run_phase2_confirmation(phase1_package_dir: Path, output_dir: Path) -> None:
    """Orchestrate one governed Phase 2 run into a fresh, not-yet-existing output_dir.

    Isolated from main()'s CLI parsing and Git-tree/path scaffolding so
    the ordering guarantee -- Phase 1 source identity verified before any
    holdout row is loaded -- and the atomic-promotion behavior are both
    directly testable against synthetic, repo-external paths.
    """
    partial = output_dir.with_name(output_dir.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"stale Phase 2 partial output requires review: {partial}")

    # Verify the Phase 1 source package's identity before any holdout row is loaded.
    phase1_git_head, phase1_primary_results_sha256 = resolve_phase1_source_identity(phase1_package_dir)
    verify_phase1_source_package(phase1_git_head, phase1_primary_results_sha256)

    discovery_effects = read_discovery_effects(phase1_package_dir, PHASE2_CANDIDATE_TRAITS)
    predictors_by_column = resolve_phase2_predictor_definitions(PHASE2_CANDIDATE_TRAITS)
    whitelist = pd.read_csv(WHITELIST)["predictor_column"].tolist()
    validate_predictor_definitions(tuple(predictors_by_column.values()), whitelist)

    source_paths = (ANALYSIS_VIEW_CSV, WHITELIST, INVENTORY, CLUSTERS)
    for path in source_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    input_hashes = {str(path.relative_to(REPO_ROOT)): sha256(path) for path in source_paths}
    required_columns = {
        "prediction_season", "player_id", "position", "preseason_market_status", "adp_round",
        "lwi_score", "star_by_value_label", "star_outcome_eligible",
        "bust_strict_below_replacement_label", "bust_strict_below_replacement_eligible",
        *(candidate.predictor_column for candidate in PHASE2_CANDIDATE_TRAITS),
    }
    rows = holdout_rows(required_columns)
    post_read_hashes = {str(path.relative_to(REPO_ROOT)): sha256(path) for path in source_paths}
    if post_read_hashes != input_hashes:
        raise RuntimeError("Phase 2 governed inputs changed while they were being loaded")

    records = confirm_all_candidates(rows, PHASE2_CANDIDATE_TRAITS, predictors_by_column, discovery_effects)

    code_git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    verdict_counts = {
        verdict: sum(record.verdict == verdict for record in records)
        for verdict in ("confirmed", "contradicted", "inconclusive")
    }
    configuration = {
        "phase2_code_git_head": code_git_head,
        "phase2_methodology_version": DATASET2_PHASE2_METHODOLOGY_VERSION,
        "phase1_source_package_dir": str(phase1_package_dir.resolve()),
        "phase1_source_git_head": phase1_git_head,
        "phase1_source_primary_results_sha256": phase1_primary_results_sha256,
        "discovery_lwi_outcome_sd": DATASET2_PHASE2_DISCOVERY_LWI_OUTCOME_SD,
        "candidate_count": len(PHASE2_CANDIDATE_TRAITS),
        "excluded_unstable_trait_count": len(PHASE2_EXCLUDED_UNSTABLE_TRAITS),
        "holdout_seasons": [DATASET2_HOLDOUT_START_SEASON, DATASET2_HOLDOUT_END_SEASON],
        "holdout_row_count_loaded": len(rows),
        "input_hashes": input_hashes,
        "verdict_counts": verdict_counts,
    }
    partial.mkdir(parents=True, exist_ok=False)
    try:
        write_confirmation_package(records, partial, configuration)
        os.replace(partial, output_dir)
    except Exception:
        if partial.exists() and not any(partial.iterdir()):
            shutil.rmtree(partial)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase1-package-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    if args.output_dir.resolve().is_relative_to(REPO_ROOT.resolve()):
        raise ValueError(f"Phase 2 output directory must be outside the repository: {args.output_dir}")
    git_status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True,
    )
    if git_status:
        raise RuntimeError("governed Phase 2 execution requires a clean Git working tree")
    if args.output_dir.exists():
        raise FileExistsError(f"Phase 2 output directory already exists: {args.output_dir}")

    run_phase2_confirmation(args.phase1_package_dir, args.output_dir)


if __name__ == "__main__":
    main()
