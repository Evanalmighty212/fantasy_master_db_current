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

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.analysis_view import build_dataset2_analysis_view

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

# The pre-directory-first artifact contained 103 strict busts because
# 2021 Mike Thomas (CIN) was incorrectly assigned Michael Thomas's ADP.
# The approved directory-first identity repair makes Mike Thomas correctly
# bust-ineligible, so the canonical regenerated count is 102.
EXPECTED_STRICT_BUST_POSITIVE_COUNT = 102
STRICT_BUST_COUNT_AUDIT_KEY = (
    f"bust_strict_below_replacement_label_positive_matches_{EXPECTED_STRICT_BUST_POSITIVE_COUNT}"
)


def main():
    print("Loading already-built predictor and outcome artifacts (read-only, no recomputation)...")
    predictor_df = pd.read_parquet(PREDICTOR_PARQUET_PATH)
    predictor_registry = pd.read_csv(PREDICTOR_DICTIONARY_PATH)
    outcome_df = pd.read_parquet(OUTCOME_PARQUET_PATH)
    print(f"  predictor: {len(predictor_df)} rows, {len(predictor_df.columns)} columns")
    print(f"  outcome:   {len(outcome_df)} rows, {len(outcome_df.columns)} columns")

    print("\nBuilding analysis view (join only)...")
    view, whitelist, targets, column_registry = build_dataset2_analysis_view(predictor_df, predictor_registry, outcome_df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    view.to_parquet(VIEW_PARQUET_PATH, index=False, engine="fastparquet")
    view.to_csv(VIEW_CSV_PATH, index=False)
    pd.DataFrame({"predictor_column": whitelist}).to_csv(WHITELIST_PATH, index=False)
    pd.DataFrame(targets).to_csv(TARGET_REGISTRY_PATH, index=False)
    column_registry.to_csv(COLUMN_REGISTRY_PATH, index=False)

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
    for t in targets:
        col = t["target_column"]
        elig_col = t["eligibility_column"]
        if t["target_type"] == "binary":
            n_eligible = int(view[elig_col].sum())
            n_true = int((view[col] == True).sum())  # noqa: E712
            print(f"  {col}: eligible={n_eligible}  positive={n_true}  rate={n_true / n_eligible * 100:.1f}%")
            audit[f"{col}_eligible"] = n_eligible
            audit[f"{col}_positive"] = n_true
        else:
            n_eligible = int(view[elig_col].sum())
            print(f"  {col}: eligible={n_eligible} (continuous -- no positive count)")
            audit[f"{col}_eligible"] = n_eligible

    print("\n--- Required verification counts ---")
    bust_primary_true = int((view["bust_primary_label"] == True).sum())  # noqa: E712
    bust_strict_true = int((view["bust_strict_below_replacement_label"] == True).sum())  # noqa: E712
    star_eligible = int(view["star_outcome_eligible"].sum())
    star_true = int((view["star_by_value_label"] == True).sum())  # noqa: E712
    print(f"bust_primary_label positive count: {bust_primary_true} (expected 522)")
    print(
        "bust_strict_below_replacement_label positive count: "
        f"{bust_strict_true} (expected {EXPECTED_STRICT_BUST_POSITIVE_COUNT})"
    )
    print(f"star_outcome_eligible count: {star_eligible}")
    print(f"star_by_value_label positive count: {star_true}")
    audit["bust_primary_label_positive_matches_522"] = bust_primary_true == 522
    audit[STRICT_BUST_COUNT_AUDIT_KEY] = bust_strict_true == EXPECTED_STRICT_BUST_POSITIVE_COUNT

    pd.DataFrame([audit]).T.rename(columns={0: "value"}).to_csv(JOIN_AUDIT_PATH)

    print(f"\nWrote:\n  {VIEW_PARQUET_PATH}\n  {VIEW_CSV_PATH}\n  {WHITELIST_PATH}\n  {TARGET_REGISTRY_PATH}\n  {COLUMN_REGISTRY_PATH}\n  {JOIN_AUDIT_PATH}")


if __name__ == "__main__":
    main()
