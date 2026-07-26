"""
lib/stars_by_value/evidence_audit.py

Owns the shape, validation, and required-coverage rule for the SBV
evidence-audit artifact (data/exports/stars_by_value_evidence_audit.csv)
-- added 2026-07 to replace the never-implemented star_by_value_evidence_notes
column design (rejected -- see research/dataset3/STARS_BY_VALUE_METHODOLOGY.md's
decision history) with a strictly one-way, separate artifact.

DESIGN (Option 3A, as decided): the audit payload for a row is built
during the SAME evaluation that determines its canonical SBV result --
labeling.assign_sbv_status() calls build_payload() at each of the 6
decision points below, using the SAME local status/provenance values
already computed for the canonical row, never re-derived by a second
pass. This makes it structurally impossible for the audit explanation
to name a different status/provenance than the canonical row actually
got.

ONE-WAY GUARANTEE: nothing in this module, or anywhere labeling.py
uses it, ever reads config.SBV_EVIDENCE_AUDIT_PATH or the audit
DataFrame back into a scoring/matching/labeling/modeling decision --
see tests/test_evidence_audit.py::TestNeverConsumedDownstream for the
mechanical guarantee (a repo-wide scan), not just this docstring's
promise.

COVERAGE RULE: an audit row is required exactly when a canonical row's
star_by_value_provenance_type is one of REQUIRED_AUDIT_PROVENANCE_TYPES
below -- the six provenance types that reflect a real classifier/
evidentiary judgment call (fuzzy match needing review, MFL-corroborated
acquisition cost, a specific 2010 manual override, unresolved drafted
evidence, genuine classifier/MFL disagreement, or a known cost with no
fitted E_P for that round). Every other provenance type (a clean ADP
match, a mechanical production-gate failure, a mechanical out-of-scope
exclusion) is fully explained by the canonical row's own structured
columns and must NOT have an audit row -- see validate_audit_coverage().
"""

import pandas as pd

EVIDENCE_AUDIT_COLUMNS = (
    "season",
    "player_id",
    "player_name",
    "star_by_value_status",
    "star_by_value_provenance_type",
    "evidence_type",
    "evidence_summary",
    "source_reference",
)

# One evidence_type per required provenance type -- MMC's two
# provenance types get two distinct evidence_types since they reflect
# substantively different evidence (a real classifier/MFL corroboration
# vs. a specific, individually-reviewed 2010 override).
EVIDENCE_TYPES = (
    "adp_match_needs_review",
    "mmc_corroborated_by_mfl",
    "mmc_2010_manual_override",
    "drafted_but_adp_unresolved",
    "classifier_mfl_disagreement",
    "round_beyond_fitted_ep_range",
)

# Plain string literals, not imported from labeling.py/acquisition_cost.py
# -- avoids a circular import (labeling.py imports FROM this module).
# TestRequiredProvenanceTypesAreRealConfigMembers pins these against
# config.SBV_PROVENANCE_TYPES so a typo or a renamed provenance
# constant is caught immediately, not silently.
REQUIRED_AUDIT_PROVENANCE_TYPES = (
    "adp_matched_needs_review",
    "mmc_verified_corroborated",
    "mmc_verified_2010_manual_override",
    "evidence_drafted_unresolved",
    "evidence_ambiguous_disagreement",
    "known_acquisition_cost_ep_out_of_fitted_range",
)

_EVIDENCE_TYPE_BY_PROVENANCE = {
    "adp_matched_needs_review": "adp_match_needs_review",
    "mmc_verified_corroborated": "mmc_corroborated_by_mfl",
    "mmc_verified_2010_manual_override": "mmc_2010_manual_override",
    "evidence_drafted_unresolved": "drafted_but_adp_unresolved",
    "evidence_ambiguous_disagreement": "classifier_mfl_disagreement",
    "known_acquisition_cost_ep_out_of_fitted_range": "round_beyond_fitted_ep_range",
}


def build_payload(season, player_id, player_name, status, provenance, evidence_summary, source_reference) -> dict:
    """Builds one audit-row dict. `status`/`provenance` must be the
    SAME values already decided for the canonical row -- this function
    does not re-derive them, only records them. `evidence_type` is
    looked up from `provenance` (a fixed 1:1 mapping), not passed in
    separately, so it can never disagree with the provenance it was
    built from."""
    if provenance not in REQUIRED_AUDIT_PROVENANCE_TYPES:
        raise ValueError(
            f"build_payload() called for provenance {provenance!r}, which is not in "
            f"REQUIRED_AUDIT_PROVENANCE_TYPES -- an audit row must only be built for "
            f"one of the six provenance types that genuinely need explanation."
        )
    return {
        "season": season,
        "player_id": player_id,
        "player_name": player_name,
        "star_by_value_status": status,
        "star_by_value_provenance_type": provenance,
        "evidence_type": _EVIDENCE_TYPE_BY_PROVENANCE[provenance],
        "evidence_summary": evidence_summary,
        "source_reference": source_reference,
    }


def empty_audit_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(EVIDENCE_AUDIT_COLUMNS))


def validate_audit_coverage(canonical_df: pd.DataFrame, audit_df: pd.DataFrame) -> None:
    """The fail-loud coverage guarantee, checked before any canonical
    artifact is written:
      1. exactly 0 or 1 audit row per (season, player_id) -- no duplicates.
      2. every audit row's (season, player_id) exists in canonical_df
         exactly once -- no orphaned audit rows.
      3. every canonical row whose provenance requires an audit row
         (REQUIRED_AUDIT_PROVENANCE_TYPES) has EXACTLY one -- none missing.
      4. every canonical row whose provenance does NOT require one has
         ZERO -- no stray rows for statuses that are already fully
         explained by structured columns.
      5. a canonical-vs-audit status/provenance consistency check --
         should be structurally guaranteed by build_payload() being
         called with the same local values, but checked directly here
         too as a real regression pin, not just an assumption.
    """
    key_cols = ["season", "player_id"]

    # 1. duplicates within audit_df itself
    dupe_mask = audit_df.duplicated(subset=key_cols, keep=False)
    if dupe_mask.any():
        dupes = audit_df.loc[dupe_mask, key_cols].drop_duplicates()
        raise RuntimeError(
            f"Evidence audit has duplicate (season, player_id) rows -- expected at "
            f"most one audit row per player-season:\n{dupes.to_string(index=False)}"
        )

    canonical_keys = set(zip(canonical_df["season"], canonical_df["player_id"]))
    audit_keys = set(zip(audit_df["season"], audit_df["player_id"]))

    # 2. orphaned audit rows (no matching canonical row)
    orphaned = audit_keys - canonical_keys
    if orphaned:
        raise RuntimeError(
            f"Evidence audit has {len(orphaned)} row(s) whose (season, player_id) does "
            f"not exist in the canonical SBV output: {sorted(orphaned)[:10]}"
        )

    # 3 & 4: required-status coverage, both directions
    required_mask = canonical_df["star_by_value_provenance_type"].isin(REQUIRED_AUDIT_PROVENANCE_TYPES)
    required_keys = set(zip(
        canonical_df.loc[required_mask, "season"], canonical_df.loc[required_mask, "player_id"],
    ))
    not_required_keys = canonical_keys - required_keys

    missing = required_keys - audit_keys
    if missing:
        raise RuntimeError(
            f"Evidence audit is missing {len(missing)} required row(s) -- every canonical "
            f"row with a provenance in REQUIRED_AUDIT_PROVENANCE_TYPES must have exactly "
            f"one audit row: {sorted(missing)[:10]}"
        )

    stray = audit_keys & not_required_keys
    if stray:
        raise RuntimeError(
            f"Evidence audit has {len(stray)} row(s) for a canonical status/provenance "
            f"that does NOT require explanation (already fully covered by structured "
            f"columns) -- only genuinely unusual statuses may appear: {sorted(stray)[:10]}"
        )

    # 5. status/provenance consistency (should be guaranteed by construction)
    merged = audit_df.merge(
        canonical_df[["season", "player_id", "star_by_value_status", "star_by_value_provenance_type"]],
        on=key_cols, how="inner", suffixes=("_audit", "_canonical"),
    )
    mismatched = merged[
        (merged["star_by_value_status_audit"] != merged["star_by_value_status_canonical"])
        | (merged["star_by_value_provenance_type_audit"] != merged["star_by_value_provenance_type_canonical"])
    ]
    if len(mismatched):
        raise RuntimeError(
            f"Evidence audit has {len(mismatched)} row(s) whose recorded status/provenance "
            f"disagrees with the canonical row's real status/provenance -- this should be "
            f"structurally impossible (see module docstring); investigate immediately:\n"
            f"{mismatched[key_cols].to_string(index=False)}"
        )


def render_evidence_audit_markdown() -> str:
    """Rendered as a section appended to the main SCHEMA.md by
    lib/stars_by_value/schema.py -- kept here, not duplicated, so the
    artifact's own module is the single source of truth for its shape."""
    lines = [
        "## Evidence audit artifact -- `stars_by_value_evidence_audit.csv`",
        "",
        "A separate, strictly one-way artifact. **No scoring, matching, "
        "labeling, or modeling code may ever read this file or its "
        "in-memory equivalent** -- see "
        "`tests/test_evidence_audit.py::TestNeverConsumedDownstream` for the "
        "mechanical guarantee. Generated during the SAME evaluation that "
        "produces the canonical SBV row (not a second reconstruction pass), "
        "so the recorded status/provenance can never drift from the real "
        "canonical result.",
        "",
        "**Join keys**: `season`, `player_id` -- 0 or 1 audit row per "
        "player-season, and every audit row joins to exactly one canonical "
        "SBV row.",
        "",
        f"**Coverage rule**: an audit row exists if and only if the canonical "
        f"row's `star_by_value_provenance_type` is one of: "
        f"`{'`, `'.join(REQUIRED_AUDIT_PROVENANCE_TYPES)}`. Every other "
        f"provenance type is already fully explained by the canonical row's "
        f"structured columns and must have zero audit rows.",
        "",
        "| Column | Type | Notes |",
        "|---|---|---|",
        "| `season` | int64 | join key |",
        "| `player_id` | string | join key |",
        "| `player_name` | string | denormalized, for human scanning only |",
        "| `star_by_value_status` | string (enum) | denormalized copy of the canonical row's status -- validated to match, never independently derived |",
        "| `star_by_value_provenance_type` | string (enum) | denormalized copy, same validation |",
        f"| `evidence_type` | string (enum, {len(EVIDENCE_TYPES)} values) | structured, NOT free text -- one of `{'`, `'.join(EVIDENCE_TYPES)}` |",
        "| `evidence_summary` | string, free text | human-audit only, never parsed by pipeline logic |",
        "| `source_reference` | string | pointer to the specific grounding fact (classifier bucket/MFL result, an override table, a fitted-round comparison) |",
        "",
    ]
    return "\n".join(lines)
