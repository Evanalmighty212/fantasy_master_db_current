#!/usr/bin/env python3
"""Governed, serial, resumable Dataset 2 Phase 1 discovery execution.

This entry point streams the accepted analysis-view CSV in bounded chunks,
retains only 2010-2020 rows and required columns, and invokes the runner's
unchanged discovery-only guard immediately before fitting. Results remain
under a clearly named partial directory until the complete package and hash
manifest have been written successfully.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
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
    DATASET2_BUST_REFERENCE_START_SEASON,
    DATASET2_DISCOVERY_END_SEASON,
    DATASET2_FIRTH_BOOTSTRAP_BATCH_SIZE,
    DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE,
    DATASET2_FIRTH_BOOTSTRAP_REPLICATES,
    DATASET2_PHASE1_RANDOM_SEED,
)
from lib.dataset2.phase1_analysis import require_discovery_only  # noqa: E402
from lib.dataset2.phase1_runner import (  # noqa: E402
    PredictorDefinition,
    preflight_phase1_estimability,
    run_phase1,
)

EXPORTS = REPO_ROOT / "data" / "exports"
ANALYSIS_VIEW = EXPORTS / "dataset2_analysis_view.parquet"
ANALYSIS_VIEW_CSV = EXPORTS / "dataset2_analysis_view.csv"
WHITELIST = EXPORTS / "dataset2_analysis_view_predictor_whitelist.csv"
INVENTORY = EXPORTS / "dataset2_trait_pipeline_predictor_inventory.csv"
CLUSTERS = EXPORTS / "dataset2_trait_pipeline_predictor_clusters.csv"
TARGET_REGISTRY = EXPORTS / "dataset2_analysis_view_target_registry.csv"
BUST_REFERENCE = REPO_ROOT / "data" / "processed" / "dataset2_bust_reference.json"
DISCOVERY_CSV_CHUNK_SIZE = 10_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True)


def governed_predictors() -> tuple[tuple[PredictorDefinition, ...], list[str]]:
    inventory = pd.read_csv(INVENTORY)
    clusters = pd.read_csv(CLUSTERS)
    whitelist = pd.read_csv(WHITELIST)["predictor_column"].tolist()
    representatives = clusters.loc[
        clusters["role"].eq("content") & clusters["is_representative"].astype(bool),
        ["cluster_id", "column"],
    ].merge(inventory[["column", "var_type"]], on="column", how="left", validate="one_to_one")
    representatives = representatives.sort_values(["cluster_id", "column"], kind="mergesort")
    if len(representatives) != 143 or representatives["cluster_id"].duplicated().any():
        raise ValueError("governed cluster artifacts must yield exactly 143 representatives")
    kind_map = {"continuous": "continuous", "boolean": "binary", "categorical/status": "categorical"}
    if representatives["var_type"].isna().any() or not set(representatives["var_type"]) <= set(kind_map):
        raise ValueError("representative inventory contains an unknown predictor type")
    predictors = tuple(
        PredictorDefinition(
            column=row.column,
            kind=kind_map[row.var_type],
            cluster_id=str(row.cluster_id),
            is_cluster_representative=True,
        )
        for row in representatives.itertuples(index=False)
    )
    return predictors, whitelist


def discovery_rows(predictors: tuple[PredictorDefinition, ...]) -> pd.DataFrame:
    required = {
        "prediction_season", "player_id", "position", "preseason_market_status", "adp_round",
        "lwi_score", "star_by_value_label", "star_outcome_eligible",
        "bust_strict_below_replacement_label", "bust_strict_below_replacement_eligible",
        *(predictor.column for predictor in predictors),
    }
    chunks = []
    for chunk in pd.read_csv(
        ANALYSIS_VIEW_CSV,
        usecols=sorted(required),
        chunksize=DISCOVERY_CSV_CHUNK_SIZE,
        low_memory=False,
        float_precision="round_trip",
    ):
        seasons = pd.to_numeric(chunk["prediction_season"], errors="raise")
        chunks.append(chunk.loc[seasons.between(
            DATASET2_BUST_REFERENCE_START_SEASON, DATASET2_DISCOVERY_END_SEASON,
        )].copy())
    if not chunks:
        raise ValueError("accepted analysis-view CSV yielded no chunks")
    rows = pd.concat(chunks, ignore_index=True)
    seasons = pd.to_numeric(rows["prediction_season"], errors="raise")
    rows = rows.loc[seasons.between(
        DATASET2_BUST_REFERENCE_START_SEASON, DATASET2_DISCOVERY_END_SEASON,
    )].copy()
    observed = sorted(rows["prediction_season"].astype(int).unique().tolist())
    expected = list(range(DATASET2_BUST_REFERENCE_START_SEASON, DATASET2_DISCOVERY_END_SEASON + 1))
    if observed != expected:
        raise ValueError(f"unexpected discovery season coverage: {observed}")
    return rows


def run_preflighted_phase1(rows, predictors, whitelist, **kwargs):
    """Complete estimability preflight, then final scope guard, then fitting."""
    preflight_phase1_estimability(rows, predictors, whitelist)
    require_discovery_only(rows)  # unchanged final backstop immediately before runner
    return run_phase1(rows, predictors, whitelist, **kwargs)


def write_package(package, output_directory: Path, configuration: dict[str, object]) -> None:
    primary = package.primary_results.copy().sort_values(
        ["family", "cluster_id", "predictor_column"], kind="mergesort",
    )
    for column in (
        "contrast_names", "adjusted_effects", "native_unit_effects", "raw_outcome_effects",
        "confidence_intervals", "absolute_probability_differences", "evidence_gate_status",
        "bootstrap_failure_counts",
    ):
        primary[column] = primary[column].map(stable_json)
    primary.to_csv(output_directory / "primary_results.csv", index=False, lineterminator="\n")
    pd.DataFrame([{
        "family": value.family,
        "predictor_column": value.predictor_column,
        "folds": value.folds,
        "metrics": stable_json(value.metrics),
    } for value in package.incremental_results]).sort_values(
        ["family", "predictor_column"], kind="mergesort",
    ).to_csv(output_directory / "incremental_validation.csv", index=False, lineterminator="\n")
    pd.DataFrame([{
        "family": value.family,
        "predictor_column": value.predictor_column,
        "full_estimates": stable_json(value.full_estimates),
        "leave_one_season_out_estimates": stable_json(value.leave_one_season_out_estimates),
        "direction_status": stable_json(value.direction_status),
    } for value in package.robustness_results]).sort_values(
        ["family", "predictor_column"], kind="mergesort",
    ).to_csv(output_directory / "robustness.csv", index=False, lineterminator="\n")
    pd.DataFrame([{**asdict(value), "reference_share": value.reference_share}
                  for value in package.categorical_references]).sort_values(
        "predictor_column", kind="mergesort",
    ).to_csv(output_directory / "categorical_references.csv", index=False, lineterminator="\n")
    pd.DataFrame([asdict(value) for value in package.preflight_ledger]).sort_values(
        ["family", "cluster_id", "predictor_column"], kind="mergesort",
    ).to_csv(output_directory / "preflight_ledger.csv", index=False, lineterminator="\n")
    (output_directory / "configuration.json").write_text(stable_json(configuration) + "\n", encoding="utf-8")
    paths = sorted(path for path in output_directory.iterdir() if path.is_file())
    (output_directory / "outputs.sha256").write_text(
        "\n".join(f"{sha256(path)}  {path.name}" for path in paths) + "\n", encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--checkpoint-dir", required=True, type=Path)
    args = parser.parse_args()
    for label, path in (("output", args.output_dir), ("checkpoint", args.checkpoint_dir)):
        if path.resolve().is_relative_to(REPO_ROOT.resolve()):
            raise ValueError(f"Phase 1 {label} directory must be outside the repository: {path}")
    git_status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True,
    )
    if git_status:
        raise RuntimeError("governed Phase 1 execution requires a clean Git working tree")
    if args.output_dir.exists():
        raise FileExistsError(f"Phase 1 output directory already exists: {args.output_dir}")
    partial = args.output_dir.with_name(args.output_dir.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"stale Phase 1 partial output requires review: {partial}")
    source_paths = (
        ANALYSIS_VIEW, ANALYSIS_VIEW_CSV, WHITELIST, INVENTORY,
        CLUSTERS, TARGET_REGISTRY, BUST_REFERENCE,
    )
    for path in source_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    input_hashes = {str(path.relative_to(REPO_ROOT)): sha256(path) for path in source_paths}
    predictors, whitelist = governed_predictors()
    rows = discovery_rows(predictors)
    post_read_hashes = {str(path.relative_to(REPO_ROOT)): sha256(path) for path in source_paths}
    if post_read_hashes != input_hashes:
        raise RuntimeError("Phase 1 governed inputs changed while they were being loaded")
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    progress_path = args.checkpoint_dir / "progress.jsonl"
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    checkpoint_identity = {
        "git_head": git_head,
        "input_hashes": input_hashes,
        "discovery_seasons": [DATASET2_BUST_REFERENCE_START_SEASON, DATASET2_DISCOVERY_END_SEASON],
    }

    def report_progress(record: dict[str, object]) -> None:
        line = stable_json(record)
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
        print(line, flush=True)

    package = run_preflighted_phase1(
        rows, predictors, whitelist,
        checkpoint_root=args.checkpoint_dir / "tasks",
        checkpoint_identity=checkpoint_identity,
        progress=report_progress,
    )
    partial.mkdir(parents=True, exist_ok=False)
    preflight_counts = {
        family: {
            "fit": sum(
                record.family == family and record.disposition == "fit"
                for record in package.preflight_ledger
            ),
            "excluded_non_estimable": sum(
                record.family == family and record.disposition == "excluded_non_estimable"
                for record in package.preflight_ledger
            ),
        }
        for family in ("lwi", "star", "strict_bust")
    }
    configuration = {
        "git_head": git_head,
        "input_hashes": input_hashes,
        "loaded_row_count": len(rows),
        "loaded_seasons": sorted(rows["prediction_season"].astype(int).unique().tolist()),
        "representatives_per_family": {family: len(predictors) for family in ("lwi", "star", "strict_bust")},
        "preflight_counts_by_family": preflight_counts,
        "bootstrap_replicates": DATASET2_FIRTH_BOOTSTRAP_REPLICATES,
        "bootstrap_minimum_success_rate": DATASET2_FIRTH_BOOTSTRAP_MIN_SUCCESS_RATE,
        "bootstrap_batch_size": DATASET2_FIRTH_BOOTSTRAP_BATCH_SIZE,
        "random_seed": DATASET2_PHASE1_RANDOM_SEED,
        "checkpoint_directory": str(args.checkpoint_dir.resolve()),
    }
    try:
        write_package(package, partial, configuration)
        os.replace(partial, args.output_dir)
    except Exception:
        if partial.exists() and not any(partial.iterdir()):
            shutil.rmtree(partial)
        raise


if __name__ == "__main__":
    main()
