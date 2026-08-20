"""
lib/dataset2/analysis_view.py

Dataset 2 canonical ANALYSIS VIEW -- artifact 3 of the three-artifact
architecture (research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md
§1a). The join of artifact 1 (canonical predictor table) and artifact
2 (canonical outcome table), keyed on
`predictor.prediction_season == outcome.outcome_season` AND
`player_id`. Grain: exactly one row per (`prediction_season`,
`player_id`) -- the predictor table's own spine, used unmodified as
the LEFT side, so every real predictor row survives the join,
including the 609 `prediction_season=2026` rows that have no possible
outcome yet.

THIS MODULE DOES NOT RECOMPUTE ANYTHING. It:
  - joins two already-canonicalized, already-tested tables,
  - preserves every predictor and outcome column unmodified (no new
    trait, no new SBV value, no new bust percentile, no new
    eligibility rule),
  - adds exactly ONE new column (`outcome_join_status`) purely to
    disambiguate "no outcome row exists yet" from the outcome table's
    own existing eligibility/label vocabulary -- a structural fact
    about the JOIN, not a new outcome determination,
  - and returns a predictor whitelist + target registry + full column
    registry so downstream modeling code never has to guess which
    columns are safe.

WHY A ROW CAN HAVE A NULL OUTCOME (never a False): for any
`prediction_season` beyond the real outcome data's coverage (today,
only 2026, family #9's own future extension --
`fam9_prediction_season_outcome_unavailable` on the predictor side
already flags this), the LEFT join finds no matching outcome row at
all. Every outcome-side column -- eligibility, reason, assignment
method, label -- is then null by construction (a plain unmatched-row
NaN from `pandas.merge(how="left")`), NEVER coerced to False. This is
verified, not assumed: every nullable-boolean outcome column is
explicitly re-cast to pandas "boolean" dtype after the merge, and
`outcome_join_status` records the fact plainly
(`"no_outcome_row_matched"`) so a caller never has to infer it from
column nullness alone.

FOUR STATES, kept unambiguous (the outcome table's own eligibility/
label pair already distinguishes 3 of these; `outcome_join_status`
adds the 4th):
  1. Outcome not yet available -- `outcome_join_status ==
     "no_outcome_row_matched"`. Every eligibility/label/reason field
     for every target is null.
  2. Outcome exists, target ineligible -- `outcome_join_status ==
     "outcome_matched"`, target's own `*_eligible` column is False,
     its `*_ineligibility_reason` is populated, its label is null.
  3. Outcome eligible, label False -- eligible column True, label
     False (a REAL False, e.g. a below-production-gate Star row).
  4. Outcome eligible, label True.

TARGET SAFETY: `TARGET_REGISTRY` records the three related primary
outcome families plus their predefined secondary/sensitivity and
diagnostic measures (per
research/dataset2/DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md):
continuous `lwi_score`, `star_by_value_label`, `bust_primary_label`,
`bust_primary_sensitivity_pct25_label`,
`bust_primary_sensitivity_pct30_label`,
`bust_strict_below_replacement_label`, and the continuous
`underperformance_diagnostic_value`. `bust_historical_sensitivity_label`
is deliberately NOT in this registry -- it remains
`reserved_not_computed` (see canonical_outcome_table.py), never a
usable target.

PREDICTOR WHITELIST: derived MECHANICALLY from the predictor table's
own already-built column registry (`family_number != "N/A (spine)"`)
-- never hand-picked here, never re-derived from scratch. The 4 spine
columns (`prediction_season`, `player_id`, `position`,
`observation_season`, canonical-position provenance, and
`historical_input_revision`) are `role="id"`, not predictors -- `position` in
particular is withheld from the whitelist by this same mechanical rule
(a deliberate, disclosed default: this project's established
convention is position-STRATIFIED analysis, not a raw pooled-position
categorical feature; a caller who wants position as a literal model
input can add it back explicitly, but it is not silently included).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import validate_columns
from lib.preseason_market_status import STATUSES as PRESEASON_MARKET_STATUS_VALUES

SHARED_SPINE_METADATA_COLUMNS = (
    "canonical_position_status", "canonical_position_authority", "historical_input_revision",
)
PRESEASON_MARKET_METADATA_COLUMNS = (
    "preseason_market_status", "preseason_market_status_sensitivity_30",
    "preseason_market_status_authority", "preseason_market_status_evidence_source",
    "preseason_market_status_evidence_summary",
)
PREDICTOR_REQUIRED_COLUMNS = (
    ("prediction_season", "player_id", "position")
    + SHARED_SPINE_METADATA_COLUMNS
    + PRESEASON_MARKET_METADATA_COLUMNS
)
OUTCOME_REQUIRED_COLUMNS = ("outcome_season", "player_id", "position") + SHARED_SPINE_METADATA_COLUMNS
PREDICTOR_COLUMN_REGISTRY_REQUIRED_COLUMNS = ("canonical_column", "family_number")

PREDICTOR_SPINE_COLUMNS = (
    "prediction_season", "player_id", "position", "canonical_position_status",
    "canonical_position_authority", "historical_input_revision",
    *PRESEASON_MARKET_METADATA_COLUMNS, "observation_season",
)
_OUTCOME_DROP_BEFORE_MERGE = ("position",) + SHARED_SPINE_METADATA_COLUMNS
_OUTCOME_RENAME_BEFORE_MERGE = {"outcome_season": "prediction_season"}

# Every nullable-boolean column on the outcome side -- re-cast
# explicitly after the merge so an unmatched row's NaN is guaranteed
# pandas <NA>, never coercible to a real False.
OUTCOME_NULLABLE_BOOLEAN_COLUMNS = (
    "has_real_market_adp",
    "star_outcome_eligible",
    "star_by_value_label",
    "sbv_score_available",
    "bust_primary_eligible",
    "bust_primary_label",
    "bust_primary_sensitivity_pct25_label",
    "bust_primary_sensitivity_pct30_label",
    "bust_strict_below_replacement_eligible",
    "bust_strict_below_replacement_label",
    "bust_historical_sensitivity_eligible",
    "bust_historical_sensitivity_label",
    "underperformance_diagnostic_eligible",
)

OUTCOME_JOIN_STATUS_MATCHED = "outcome_matched"
OUTCOME_JOIN_STATUS_NO_MATCH = "no_outcome_row_matched"

ROLE_ID = "id"
ROLE_PREDICTOR = "predictor"
ROLE_CONTROL = "control"
ROLE_PREDICTOR_METADATA = "predictor_metadata"
ROLE_TARGET_LABEL = "target_label"
ROLE_TARGET_CONTINUOUS = "target_continuous"
ROLE_TARGET_DIAGNOSTIC = "target_diagnostic"
ROLE_OUTCOME_ELIGIBILITY = "outcome_eligibility"
ROLE_OUTCOME_REASON = "outcome_ineligibility_reason"
ROLE_OUTCOME_ASSIGNMENT_METHOD = "outcome_assignment_method"
ROLE_OUTCOME_METADATA = "outcome_metadata"
ROLE_JOIN_STATUS = "join_status"

# The approved three-family hierarchy and predefined non-primary measures.
# bust_historical_sensitivity_label is DELIBERATELY excluded: reserved_not_computed, not usable.
TARGET_REGISTRY = (
    {
        "target_column": "lwi_score",
        "target_type": "continuous",
        "eligibility_column": None,
        "usable_as_target": True,
        "analysis_role": "primary",
        "fdr_family": "lwi",
        "description": "Canonical continuous LWI outcome; standardize within discovery analysis and report raw-scale effects too.",
    },
    {
        "target_column": "star_by_value_label",
        "target_type": "binary",
        "eligibility_column": "star_outcome_eligible",
        "usable_as_target": True,
        "analysis_role": "primary",
        "fdr_family": "star",
        "description": "Star-by-Value outcome label (real False for below-production-gate rows, not a missing value).",
    },
    {
        "target_column": "bust_primary_label",
        "target_type": "binary",
        "eligibility_column": "bust_primary_eligible",
        "usable_as_target": True,
        "analysis_role": "secondary_contextual",
        "fdr_family": "bust",
        "description": "Broad relative-underperformance bottom-20% label; contextual, not the primary bust outcome.",
    },
    {
        "target_column": "bust_primary_sensitivity_pct25_label",
        "target_type": "binary",
        "eligibility_column": "bust_primary_eligible",
        "usable_as_target": True,
        "analysis_role": "sensitivity",
        "fdr_family": "bust",
        "description": "Sensitivity: bottom 25%, same ranking pipeline as bust_primary_label -- not the primary target.",
    },
    {
        "target_column": "bust_primary_sensitivity_pct30_label",
        "target_type": "binary",
        "eligibility_column": "bust_primary_eligible",
        "usable_as_target": True,
        "analysis_role": "sensitivity",
        "fdr_family": "bust",
        "description": "Sensitivity: bottom 30%, same ranking pipeline as bust_primary_label -- not the primary target.",
    },
    {
        "target_column": "bust_strict_below_replacement_label",
        "target_type": "binary",
        "eligibility_column": "bust_strict_below_replacement_eligible",
        "usable_as_target": True,
        "analysis_role": "primary",
        "fdr_family": "bust",
        "description": "Primary strict-bust outcome: discovery-calibrated bottom 20% AND P<0.",
    },
    {
        "target_column": "underperformance_diagnostic_value",
        "target_type": "continuous",
        "eligibility_column": "underperformance_diagnostic_eligible",
        "usable_as_target": True,
        "analysis_role": "diagnostic",
        "fdr_family": None,
        "description": "Raw P - E_P, continuous. NOT the same as star_by_value_score (which uses SBV_LAMBDA).",
    },
)

# Roles for every outcome-table column that survives the merge
# (outcome_season and the outcome's own position are dropped/merged
# away before this point -- see _OUTCOME_DROP_BEFORE_MERGE /
# _OUTCOME_RENAME_BEFORE_MERGE).
_OUTCOME_COLUMN_ROLES = {
    "lwi_score": ROLE_TARGET_CONTINUOUS,
    "real_status": ROLE_OUTCOME_METADATA,
    "has_real_market_adp": ROLE_OUTCOME_METADATA,
    "adp_round": ROLE_OUTCOME_METADATA,
    "star_outcome_eligible": ROLE_OUTCOME_ELIGIBILITY,
    "star_outcome_ineligibility_reason": ROLE_OUTCOME_REASON,
    "star_by_value_label": ROLE_TARGET_LABEL,
    "sbv_score_available": ROLE_OUTCOME_METADATA,
    "star_by_value_score": ROLE_OUTCOME_METADATA,  # SBV component -- outcome-side only, never a predictor
    "bust_primary_eligible": ROLE_OUTCOME_ELIGIBILITY,
    "bust_primary_ineligibility_reason": ROLE_OUTCOME_REASON,
    "bust_primary_assignment_method": ROLE_OUTCOME_ASSIGNMENT_METHOD,
    "bust_primary_label": ROLE_TARGET_LABEL,
    "bust_primary_sensitivity_pct25_label": ROLE_TARGET_LABEL,
    "bust_primary_sensitivity_pct30_label": ROLE_TARGET_LABEL,
    "bust_strict_below_replacement_eligible": ROLE_OUTCOME_ELIGIBILITY,
    "bust_strict_below_replacement_ineligibility_reason": ROLE_OUTCOME_REASON,
    "bust_strict_below_replacement_label": ROLE_TARGET_LABEL,
    "bust_historical_sensitivity_eligible": ROLE_OUTCOME_ELIGIBILITY,
    "bust_historical_sensitivity_ineligibility_reason": ROLE_OUTCOME_REASON,
    "bust_historical_sensitivity_label": ROLE_OUTCOME_METADATA,  # reserved_not_computed, NOT a target
    "underperformance_diagnostic_eligible": ROLE_OUTCOME_ELIGIBILITY,
    "underperformance_diagnostic_ineligibility_reason": ROLE_OUTCOME_REASON,
    "underperformance_diagnostic_value": ROLE_TARGET_DIAGNOSTIC,
}


def _predictor_role(family_number: str) -> str:
    if family_number == "N/A (spine)":
        return ROLE_ID
    if family_number == "N/A (preseason control)":
        return ROLE_CONTROL
    if family_number == "N/A (preseason metadata)":
        return ROLE_PREDICTOR_METADATA
    return ROLE_PREDICTOR


def build_dataset2_analysis_view(
    predictor_df: pd.DataFrame,
    predictor_column_registry: pd.DataFrame,
    outcome_df: pd.DataFrame,
):
    """
    Builds the Dataset 2 analysis view: a LEFT join of `predictor_df`
    (the spine -- every real row survives) against `outcome_df`, keyed
    on (`prediction_season`==`outcome_season`, `player_id`). Returns
    `(view, predictor_whitelist, target_registry, column_registry)`.

    `predictor_column_registry` must be the predictor table's OWN
    already-built column registry (canonical_column/family_number/...)
    -- used only to derive the predictor whitelist mechanically, never
    recomputed here.
    """
    if "real_status" in predictor_df.columns:
        raise ValueError(
            "predictor_df contains outcome-side real_status; it cannot substitute for "
            "predictor-side preseason_market_status"
        )
    outcome_market_collisions = sorted(set(PRESEASON_MARKET_METADATA_COLUMNS) & set(outcome_df.columns))
    if outcome_market_collisions:
        raise ValueError(
            "outcome_df contains predictor-side preseason market metadata: "
            f"{outcome_market_collisions}; outcome-side substitution/collision is forbidden"
        )
    validate_columns(predictor_df, PREDICTOR_REQUIRED_COLUMNS, "predictor_df")
    validate_columns(outcome_df, OUTCOME_REQUIRED_COLUMNS, "outcome_df")
    validate_columns(predictor_column_registry, PREDICTOR_COLUMN_REGISTRY_REQUIRED_COLUMNS, "predictor_column_registry")
    historical = pd.to_numeric(predictor_df["prediction_season"], errors="coerce").le(2025)
    for column in ("preseason_market_status", "preseason_market_status_sensitivity_30"):
        if predictor_df.loc[historical, column].isna().any():
            raise ValueError(f"historical predictor rows require non-null predictor-side {column}")
        unexpected = sorted(
            set(predictor_df.loc[historical, column].astype(str)) - PRESEASON_MARKET_STATUS_VALUES
        )
        if unexpected:
            raise ValueError(f"historical predictor rows contain unknown {column} values: {unexpected}")
    if predictor_df.loc[historical, "preseason_market_status_authority"].isna().any():
        raise ValueError(
            "historical predictor rows require non-null predictor-side preseason_market_status_authority"
        )
    registry_market_rows = predictor_column_registry.loc[
        predictor_column_registry["canonical_column"].isin(PRESEASON_MARKET_METADATA_COLUMNS)
    ]
    if set(registry_market_rows["canonical_column"]) != set(PRESEASON_MARKET_METADATA_COLUMNS):
        raise ValueError("predictor registry is missing required preseason market metadata rows")
    expected_market_families = {
        "preseason_market_status": "N/A (preseason control)",
        **{
            column: "N/A (preseason metadata)"
            for column in PRESEASON_MARKET_METADATA_COLUMNS
            if column != "preseason_market_status"
        },
    }
    actual_market_families = registry_market_rows.set_index("canonical_column")["family_number"].to_dict()
    if actual_market_families != expected_market_families:
        raise ValueError(
            "predictor registry misclassifies preseason market metadata: "
            f"expected {expected_market_families}, got {actual_market_families}"
        )

    if predictor_df.duplicated(subset=["prediction_season", "player_id"]).any():
        raise RuntimeError("predictor_df has duplicate (prediction_season, player_id) keys -- not a valid spine.")
    if outcome_df.duplicated(subset=["outcome_season", "player_id"]).any():
        raise RuntimeError("outcome_df has duplicate (outcome_season, player_id) keys.")

    # These fields describe the shared player-season spine, not an
    # outcome. Validate them on every matched key before dropping only
    # the redundant outcome-side copies. Predictor-only application
    # rows retain the predictor values unchanged.
    shared = predictor_df[
        ["prediction_season", "player_id"] + list(SHARED_SPINE_METADATA_COLUMNS)
    ].merge(
        outcome_df[["outcome_season", "player_id"] + list(SHARED_SPINE_METADATA_COLUMNS)].rename(
            columns={"outcome_season": "prediction_season"}
        ),
        on=["prediction_season", "player_id"], how="inner", suffixes=("_predictor", "_outcome"),
        validate="one_to_one",
    )
    disagreements = []
    for column in SHARED_SPINE_METADATA_COLUMNS:
        left = shared[f"{column}_predictor"]
        right = shared[f"{column}_outcome"]
        bad = ~(left.eq(right) | (left.isna() & right.isna()))
        if bad.any():
            disagreements.extend(
                shared.loc[bad, ["prediction_season", "player_id"]]
                .assign(column=column, predictor_value=left[bad].values, outcome_value=right[bad].values)
                .to_dict("records")
            )
    if disagreements:
        raise RuntimeError(f"Shared predictor/outcome spine metadata disagree: {disagreements[:20]}")

    outcome_renamed = outcome_df.rename(columns=_OUTCOME_RENAME_BEFORE_MERGE).drop(columns=list(_OUTCOME_DROP_BEFORE_MERGE))

    join_keys = {"prediction_season", "player_id"}
    collisions = (set(predictor_df.columns) - join_keys) & (set(outcome_renamed.columns) - join_keys)
    if collisions:
        raise RuntimeError(
            f"Unexpected column collision between predictor and outcome tables: {sorted(collisions)} -- "
            "resolve explicitly before merging, never rely on pandas' default _x/_y suffixing."
        )

    view = predictor_df.merge(
        outcome_renamed,
        on=["prediction_season", "player_id"],
        how="left",
        validate="one_to_one",
    )

    if any(col.endswith("_x") or col.endswith("_y") for col in view.columns):
        raise RuntimeError("Merge produced _x/_y suffixed columns -- an unresolved real collision slipped through.")
    if view.columns.duplicated().any():
        raise RuntimeError("Merge produced duplicate column names.")

    for col in OUTCOME_NULLABLE_BOOLEAN_COLUMNS:
        view[col] = view[col].astype("boolean")

    view["outcome_join_status"] = np.where(
        view["real_status"].notna(), OUTCOME_JOIN_STATUS_MATCHED, OUTCOME_JOIN_STATUS_NO_MATCH
    )

    if view.duplicated(subset=["prediction_season", "player_id"]).any():
        raise RuntimeError("Analysis view has duplicate (prediction_season, player_id) keys after merge.")
    if len(view) != len(predictor_df):
        raise RuntimeError(
            f"Analysis view row count ({len(view)}) does not match the predictor spine ({len(predictor_df)}) -- "
            "the LEFT join must preserve every predictor row exactly once."
        )

    # --- Predictor whitelist: mechanical, from the predictor table's own registry ---
    registry = predictor_column_registry.copy()
    registry["role"] = registry["family_number"].apply(_predictor_role)
    registry["source_artifact"] = "predictor"
    predictor_whitelist = registry.loc[registry["role"] == ROLE_PREDICTOR, "canonical_column"].tolist()

    # --- Full column registry: predictor's (with role) + outcome's (role from the static map) + outcome_join_status ---
    outcome_registry_rows = [
        {"canonical_column": col, "role": role, "source_artifact": "outcome"}
        for col, role in _OUTCOME_COLUMN_ROLES.items()
    ]
    join_status_row = [{"canonical_column": "outcome_join_status", "role": ROLE_JOIN_STATUS, "source_artifact": "join"}]

    predictor_registry_cols = registry[["canonical_column", "role", "source_artifact"]].copy()
    for extra_col in ("family_number", "family_name", "source", "dtype", "missingness_semantics", "position_scope"):
        if extra_col in registry.columns:
            predictor_registry_cols[extra_col] = registry[extra_col]

    column_registry = pd.concat(
        [predictor_registry_cols, pd.DataFrame(outcome_registry_rows), pd.DataFrame(join_status_row)],
        ignore_index=True,
    )

    return view, predictor_whitelist, list(TARGET_REGISTRY), column_registry
