"""
scripts/build_dataset2_analysis_view.py

Real-data driver for lib.dataset2.analysis_view -- builds artifact 3
of the three-artifact architecture
(research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md §1a) by joining
the already-written, already-canonicalized predictor and outcome
Parquet files. Reads only -- never recomputes any trait, SBV value, or
bust label; those are exclusively artifact 1's and artifact 2's own
responsibility.

Writes:
  - dataset2_analysis_view.parquet / .csv
  - dataset2_analysis_view_predictor_whitelist.csv
  - dataset2_analysis_view_target_registry.csv
  - dataset2_analysis_view_column_registry.csv
  - dataset2_analysis_view_join_audit_report.csv
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.analysis_view import build_dataset2_analysis_view
from lib.dataset2.bust_reference import validate_bust_reference
from config import (
    DATASET2_BUST_REFERENCE_PATH,
    SBV_FIRST_SCOREABLE_SEASON,
)

PREDICTOR_PARQUET_PATH = "data/exports/dataset2_canonical_predictor_table.parquet"
PREDICTOR_DICTIONARY_PATH = "data/exports/dataset2_canonical_predictor_table_data_dictionary.csv"
OUTCOME_PARQUET_PATH = "data/exports/dataset2_canonical_outcome_table.parquet"

OUTPUT_DIR = Path("data/exports")
VIEW_PARQUET_PATH = OUTPUT_DIR / "dataset2_analysis_view.parquet"
VIEW_CSV_PATH = OUTPUT_DIR / "dataset2_analysis_view.csv"
WHITELIST_PATH = OUTPUT_DIR / "dataset2_analysis_view_predictor_whitelist.csv"
TARGET_REGISTRY_PATH = OUTPUT_DIR / "dataset2_analysis_view_target_registry.csv"
COLUMN_REGISTRY_PATH = OUTPUT_DIR / "dataset2_analysis_view_column_registry.csv"
JOIN_AUDIT_PATH = OUTPUT_DIR / "dataset2_analysis_view_join_audit_report.csv"
BUST_REFERENCE_PATH = Path(DATASET2_BUST_REFERENCE_PATH)

# The prior expected count of 102 belonged to the pre-governed-source,
# pre-market-status, and pre-discovery-only-reference artifact state. The
# approved current pipeline deterministically produces 113 strict busts.
# The unavailable prior membership set prevents a one-to-one reconciliation
# of the 11-row difference; this constant records the accepted current-state
# validation baseline, not a claim that each transition was reconstructed.
EXPECTED_STRICT_BUST_POSITIVE_COUNT = 113
STRICT_BUST_COUNT_AUDIT_KEY = (
    f"bust_strict_below_replacement_label_positive_matches_{EXPECTED_STRICT_BUST_POSITIVE_COUNT}"
)

NON_REPORTABLE_EXACT_COUNT_TARGETS = {"bust_primary_label"}


def summarize_target_counts(view, targets):
    """Validate target-registry references and return descriptive counts.

    A null ``eligibility_column`` means the frozen registry defines no
    separate eligibility flag for that target (currently continuous
    ``lwi_score`` only).  In that case, non-null target values are the
    available analysis population; no eligibility rule is inferred.
    A named eligibility column, by contrast, must exist and remains the
    sole source of that target's eligible count.
    """
    counts = []
    for target in targets:
        target_column = target["target_column"]
        if target_column not in view.columns:
            raise RuntimeError(
                f"Target registry references missing target column: {target_column}"
            )

        eligibility_column = target["eligibility_column"]
        if eligibility_column is None or pd.isna(eligibility_column):
            n_eligible = int(view[target_column].notna().sum())
            eligibility_basis = "non_null_target_no_separate_eligibility_column"
        else:
            if eligibility_column not in view.columns:
                raise RuntimeError(
                    "Target registry references missing eligibility column: "
                    f"{eligibility_column} (target={target_column})"
                )
            n_eligible = int(view[eligibility_column].sum())
            eligibility_basis = eligibility_column

        n_positive = None
        if target["target_type"] == "binary" and target_column not in NON_REPORTABLE_EXACT_COUNT_TARGETS:
            n_positive = int((view[target_column] == True).sum())  # noqa: E712
        counts.append(
            {
                "target_column": target_column,
                "target_type": target["target_type"],
                "eligible_count": n_eligible,
                "positive_count": n_positive,
                "eligibility_basis": eligibility_basis,
            }
        )
    return counts


def load_governed_bust_reference(path: Path = BUST_REFERENCE_PATH) -> dict:
    """Load and validate the frozen discovery-only bust reference."""
    try:
        reference = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError(f"Governed bust reference is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Governed bust reference is unreadable or invalid JSON: {path}") from exc
    try:
        validate_bust_reference(reference)
    except ValueError as exc:
        raise RuntimeError(f"Governed bust reference validation failed: {exc}") from exc
    return reference


def build_mandatory_invariants(
    *, view, predictor_df, outcome_df, audit, bust_reference,
) -> dict[str, bool]:
    """Return semantic/governed acceptance invariants without target totals."""
    try:
        validate_bust_reference(bust_reference)
        governed_reference_valid = True
    except ValueError:
        governed_reference_valid = False
    outcome_seasons = pd.to_numeric(outcome_df["outcome_season"], errors="coerce")
    expected_primary_eligible = (
        outcome_df["has_real_market_adp"].fillna(False).astype(bool)
        & outcome_seasons.ge(SBV_FIRST_SCOREABLE_SEASON)
    )
    actual_primary_eligible = outcome_df["bust_primary_eligible"].fillna(False).astype(bool)
    strict_eligible = outcome_df["bust_strict_below_replacement_eligible"].fillna(False).astype(bool)
    primary_label_present = outcome_df["bust_primary_label"].notna()

    invariants = {
        "governed_bust_reference_valid": governed_reference_valid,
        "bust_primary_eligibility_rule_consistent": bool(actual_primary_eligible.equals(expected_primary_eligible)),
        "strict_bust_eligibility_matches_primary": bool(strict_eligible.equals(actual_primary_eligible)),
        "bust_primary_label_presence_matches_eligibility": bool(primary_label_present.equals(actual_primary_eligible)),
        "analysis_view_preserves_predictor_row_count": len(view) == len(predictor_df),
        "all_outcome_keys_preserved": audit["outcome_rows_no_predictor_match"] == 0,
        "future_targets_are_null": bool(audit["2026_all_targets_null"]),
        "deterministic_rebuild": bool(audit["deterministic_rebuild"]),
        "input_order_independent": bool(audit["input_order_independent"]),
        "no_duplicate_keys": audit["duplicate_key_count"] == 0,
        "no_x_y_suffix_columns": bool(audit["no_x_y_suffix_columns"]),
        "no_duplicate_column_names": bool(audit["no_duplicate_column_names"]),
        STRICT_BUST_COUNT_AUDIT_KEY: bool(audit[STRICT_BUST_COUNT_AUDIT_KEY]),
    }
    invariants.update({
        key: bool(value)
        for key, value in audit.items()
        if key.startswith("dtype_boolean_")
    })
    return invariants


def require_mandatory_invariants(invariants: dict[str, bool]) -> None:
    failed = sorted(name for name, passed in invariants.items() if not passed)
    if failed:
        raise RuntimeError(f"Mandatory analysis-view audit invariant(s) failed: {failed}")


def main():
    print("Loading already-built predictor and outcome artifacts (read-only, no recomputation)...")
    predictor_df = pd.read_parquet(PREDICTOR_PARQUET_PATH)
    predictor_registry = pd.read_csv(PREDICTOR_DICTIONARY_PATH)
    outcome_df = pd.read_parquet(OUTCOME_PARQUET_PATH)
    bust_reference = load_governed_bust_reference()
    print(f"  predictor: {len(predictor_df)} rows, {len(predictor_df.columns)} columns")
    print(f"  outcome:   {len(outcome_df)} rows, {len(outcome_df.columns)} columns")

    print("\nBuilding analysis view (join only)...")
    view, whitelist, targets, column_registry = build_dataset2_analysis_view(predictor_df, predictor_registry, outcome_df)

    # --- Determinism + input-order independence, verified against real data ---
    view_2, whitelist_2, targets_2, registry_2 = build_dataset2_analysis_view(predictor_df, predictor_registry, outcome_df)
    deterministic = view.to_csv(index=False) == view_2.to_csv(index=False) and whitelist == whitelist_2

    predictor_shuffled = predictor_df.sample(frac=1, random_state=42).reset_index(drop=True)
    outcome_shuffled = outcome_df.sample(frac=1, random_state=7).reset_index(drop=True)
    view_shuffled, *_ = build_dataset2_analysis_view(predictor_shuffled, predictor_registry, outcome_shuffled)
    view_sorted = view.sort_values(["prediction_season", "player_id"]).reset_index(drop=True)
    view_shuffled_sorted = view_shuffled.sort_values(["prediction_season", "player_id"]).reset_index(drop=True)
    order_independent = view_sorted.to_csv(index=False) == view_shuffled_sorted.to_csv(index=False)

    # --- Join audit: computed independently of the view's own internals,
    # cross-checking the join from both directions. ---
    predictor_keys = set(zip(predictor_df["prediction_season"], predictor_df["player_id"]))
    outcome_keys = set(zip(outcome_df["outcome_season"], outcome_df["player_id"]))
    predictor_only = predictor_keys - outcome_keys
    outcome_only = outcome_keys - predictor_keys

    print("\n" + "=" * 90)
    print("DATASET 2 ANALYSIS VIEW -- JOIN AUDIT")
    print("=" * 90)
    audit = {}
    audit["final_row_count"] = len(view)
    audit["column_count"] = len(view.columns)
    audit["duplicate_key_count"] = int(view.duplicated(subset=["prediction_season", "player_id"]).sum())
    audit["predictor_only_rows_no_outcome"] = len(predictor_only)
    audit["outcome_rows_no_predictor_match"] = len(outcome_only)
    audit["prediction_season_2026_row_count"] = int((view["prediction_season"] == 2026).sum())
    future = view[view["prediction_season"] == 2026]
    audit["2026_all_targets_null"] = bool(all(future[t["target_column"]].isna().all() for t in targets))
    audit["deterministic_rebuild"] = deterministic
    audit["input_order_independent"] = order_independent
    audit["no_x_y_suffix_columns"] = not any(c.endswith("_x") or c.endswith("_y") for c in view.columns)
    audit["no_duplicate_column_names"] = not view.columns.duplicated().any()
    audit["predictor_whitelist_size"] = len(whitelist)
    audit["target_registry_size"] = len(targets)

    for label, value in audit.items():
        print(f"{label}: {value}")

    print("\n--- Nullable boolean dtype check (every outcome boolean column) ---")
    from lib.dataset2.analysis_view import OUTCOME_NULLABLE_BOOLEAN_COLUMNS

    for col in OUTCOME_NULLABLE_BOOLEAN_COLUMNS:
        dtype_ok = str(view[col].dtype) == "boolean"
        print(f"  {col}: dtype={view[col].dtype}  ok={dtype_ok}")
        audit[f"dtype_boolean_{col}"] = dtype_ok

    print("\n--- Eligible / positive counts for every implemented target ---")
    target_counts = summarize_target_counts(view, targets)
    for counts in target_counts:
        col = counts["target_column"]
        n_eligible = counts["eligible_count"]
        n_true = counts["positive_count"]
        if counts["target_type"] == "binary" and n_true is not None:
            rate = n_true / n_eligible * 100 if n_eligible else float("nan")
            print(f"  {col}: eligible={n_eligible}  positive={n_true}  rate={rate:.1f}%")
            audit[f"{col}_eligible"] = n_eligible
            audit[f"{col}_positive"] = n_true
        elif counts["target_type"] == "binary":
            print(f"  {col}: eligible={n_eligible}  positive count intentionally not materialized")
            audit[f"{col}_eligible"] = n_eligible
        else:
            print(
                f"  {col}: available={n_eligible} "
                f"(continuous; basis={counts['eligibility_basis']})"
            )
            audit[f"{col}_eligible"] = n_eligible

    print("\n--- Required verification counts ---")
    bust_strict_true = int((view["bust_strict_below_replacement_label"] == True).sum())  # noqa: E712
    star_eligible = int(view["star_outcome_eligible"].sum())
    star_true = int((view["star_by_value_label"] == True).sum())  # noqa: E712
    print(
        "bust_strict_below_replacement_label positive count: "
        f"{bust_strict_true} (expected {EXPECTED_STRICT_BUST_POSITIVE_COUNT})"
    )
    print(f"star_outcome_eligible count: {star_eligible}")
    print(f"star_by_value_label positive count: {star_true}")
    audit[STRICT_BUST_COUNT_AUDIT_KEY] = bust_strict_true == EXPECTED_STRICT_BUST_POSITIVE_COUNT

    mandatory_invariants = build_mandatory_invariants(
        view=view,
        predictor_df=predictor_df,
        outcome_df=outcome_df,
        audit=audit,
        bust_reference=bust_reference,
    )
    audit.update(mandatory_invariants)
    require_mandatory_invariants(mandatory_invariants)

    # All construction, registry-reference, determinism, dtype, semantic,
    # governed-reference, and audit validation above completes before any
    # production artifact is written.
    # A validation failure therefore cannot promote a partial analysis-view
    # CSV, Parquet, registry, whitelist, or audit report.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    view.to_parquet(VIEW_PARQUET_PATH, index=False, engine="fastparquet")
    view.to_csv(VIEW_CSV_PATH, index=False)
    pd.DataFrame({"predictor_column": whitelist}).to_csv(WHITELIST_PATH, index=False)
    pd.DataFrame(targets).to_csv(TARGET_REGISTRY_PATH, index=False)
    column_registry.to_csv(COLUMN_REGISTRY_PATH, index=False)
    pd.DataFrame([audit]).T.rename(columns={0: "value"}).to_csv(JOIN_AUDIT_PATH)

    print(f"\nWrote:\n  {VIEW_PARQUET_PATH}\n  {VIEW_CSV_PATH}\n  {WHITELIST_PATH}\n  {TARGET_REGISTRY_PATH}\n  {COLUMN_REGISTRY_PATH}\n  {JOIN_AUDIT_PATH}")


if __name__ == "__main__":
    main()
