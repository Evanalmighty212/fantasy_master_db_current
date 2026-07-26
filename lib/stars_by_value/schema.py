"""
lib/stars_by_value/schema.py

Generates data/exports/stars_by_value_player_seasons_SCHEMA.md (the
canonical SBV output's data dictionary) from a committed, explicit
column-metadata mapping -- NOT by introspecting one output file after
the fact. Added 2026-07 after finding config.SBV_OUTPUT_CSV_SCHEMA_PATH
was declared and its .md extension checked by validate_sbv_config(),
but nothing anywhere in the codebase actually wrote to it.

SOURCE OF TRUTH FOR THE COLUMN SET: the real, committed column list is
derived from labeling.OUTPUT_COLUMNS (the 8 columns label_rows() itself
produces) plus the identity columns 11_calculate_stars_by_value.py's
run_label_rows() merges in on top ("player_name", "position" -- season
and player_id are already in OUTPUT_COLUMNS as the join keys). This
module does not hardcode a separate list that could silently drift
from those two real sources -- see EXPECTED_COLUMNS below.

validate_schema_matches_columns() is the fail-loud guarantee: called
from write_canonical_output() before anything is written, so a
canonical build refuses to produce a Parquet/CSV pair and an
out-of-sync data dictionary together.

KNOWN SPEC GAP, DELIBERATELY NOT PAPERED OVER: research/dataset3/
STARS_BY_VALUE_METHODOLOGY.md and STARS_BY_VALUE_IMPLEMENTATION_PLAN.md
both document a star_by_value_evidence_notes column (free-text,
audit-only, explicitly never parsed by pipeline logic) that was never
actually implemented in labeling.OUTPUT_COLUMNS. This module documents
the REAL, current output only -- inventing that column here would just
create a second, different kind of drift (docs claiming a column
exists that the real Parquet/CSV don't have). The generated schema
doc's final section says so explicitly. Whether to implement the
column or update the spec is a separate decision, not made here.
"""

from pathlib import Path

import config
from lib.stars_by_value import labeling
from lib.stars_by_value import evidence_audit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The two real, committed sources that determine the actual output
# column set -- season/player_id are shared join keys so they're only
# listed once, in the order run_label_rows()'s merge actually produces
# (identity columns first, then labeling's own columns).
_IDENTITY_COLUMNS = ("season", "player_id", "player_name", "position")
EXPECTED_COLUMNS = _IDENTITY_COLUMNS + tuple(
    c for c in labeling.OUTPUT_COLUMNS if c not in _IDENTITY_COLUMNS
)

_STATUS_LIST_MD = "`, `".join(config.SBV_STATUSES)
_PROVENANCE_LIST_MD = "`, `".join(config.SBV_PROVENANCE_TYPES)
_POSITION_LIST_MD = "`, `".join(config.SBV_POSITIONS)

# One entry per real output column. "populated_when"/"null_when" are
# plain-English descriptions of which star_by_value_status values
# leave the field non-null vs. null -- verified directly against real
# canonical-build output, not assumed from the labeling.py source
# alone (see tests/test_sbv_schema.py's cross-check against a real
# label_rows() call).
COLUMN_DOCS = (
    {
        "name": "season",
        "dtype": "int64",
        "nullable": False,
        "enum_values": None,
        "description": "The NFL season this player-season row corresponds to.",
        "populated_when": "every row.",
        "null_when": "never.",
        "safe_for_modeling": "Yes -- join key, always safe.",
        "provenance_notes": None,
    },
    {
        "name": "player_id",
        "dtype": "string",
        "nullable": False,
        "enum_values": None,
        "description": "nflverse gsis_id uniquely identifying the player.",
        "populated_when": "every row.",
        "null_when": "never.",
        "safe_for_modeling": "Yes -- join key, always safe.",
        "provenance_notes": None,
    },
    {
        "name": "player_name",
        "dtype": "string",
        "nullable": False,
        "enum_values": None,
        "description": "Player's display name, from the master DB's nflverse results at build time.",
        "populated_when": "every row.",
        "null_when": "never.",
        "safe_for_modeling": "Display only -- join/filter on player_id, not this field (names are not guaranteed unique).",
        "provenance_notes": None,
    },
    {
        "name": "position",
        "dtype": "string (enum)",
        "nullable": False,
        "enum_values": config.SBV_POSITIONS,
        "description": "The player's position for SBV scope purposes -- skill positions only.",
        "populated_when": "every row.",
        "null_when": "never.",
        "safe_for_modeling": "Yes.",
        "provenance_notes": None,
    },
    {
        "name": "star_by_value_status",
        "dtype": "string (enum)",
        "nullable": False,
        "enum_values": config.SBV_STATUSES,
        "description": (
            "Which of the mutually-exclusive SBV pipeline outcomes this row reached -- "
            "the primary, structured field for branching downstream pipeline logic. "
            "See research/dataset3/STARS_BY_VALUE_METHODOLOGY.md for the full decision tree."
        ),
        "populated_when": "every row -- exactly one status is always assigned.",
        "null_when": "never.",
        "safe_for_modeling": "Yes -- the primary field to branch on.",
        "provenance_notes": None,
    },
    {
        "name": "star_by_value_provenance_type",
        "dtype": "string (enum)",
        "nullable": False,
        "enum_values": config.SBV_PROVENANCE_TYPES,
        "description": (
            "Finer-grained than status -- which specific evidentiary path within a "
            "status produced this row (e.g. a real ADP match vs. MFL-corroborated "
            "acquisition cost vs. a documented 2010 manual override)."
        ),
        "populated_when": "every row.",
        "null_when": "never.",
        "safe_for_modeling": (
            "Yes -- structured and explicitly documented as safe to branch on "
            "(unlike the methodology spec's proposed free-text evidence_notes field, "
            "which is documented as human-audit-only and never implemented -- see "
            "\"Known gaps\" below)."
        ),
        "provenance_notes": None,
    },
    {
        "name": "star_by_value_score",
        "dtype": "float64",
        "nullable": True,
        "enum_values": None,
        "description": (
            "The raw SBV score: production (P) minus lambda times expected production "
            "(E_P), computed only when both a trustworthy acquisition cost and a fitted "
            "E_P lookup value are available."
        ),
        "populated_when": "status is `adp_scored` or `minimal_market_cost_scored`.",
        "null_when": (
            "status is `out_of_scope`, `below_production_gate`, `unscoreable_ambiguous`, "
            "`unscoreable_drafted_adp_missing`, or `unscoreable_expected_production_out_of_range`."
        ),
        "safe_for_modeling": (
            "Yes, but ONLY after filtering to non-null rows -- NULL must never be treated "
            "as zero, as \"below threshold\", or imputed."
        ),
        "provenance_notes": None,
    },
    {
        "name": "star_by_value_label",
        "dtype": "float64 (stores 0/1; pandas represents the null case as NaN)",
        "nullable": True,
        "enum_values": ("0", "1", None),
        "description": (
            "The binary Star determination: 1 if star_by_value_score >= "
            "star_by_value_threshold, 0 if scored but below threshold, 0 if the row "
            "failed the production gate outright (even without a numeric score), NULL "
            "if the row is genuinely unscoreable (no trustworthy cost, ambiguous "
            "evidence, or acquisition cost known but no E_P available for that round)."
        ),
        "populated_when": (
            "status is `adp_scored`, `minimal_market_cost_scored`, or "
            "`below_production_gate` (the last of these is always exactly 0)."
        ),
        "null_when": (
            "status is `out_of_scope`, `unscoreable_ambiguous`, "
            "`unscoreable_drafted_adp_missing`, or `unscoreable_expected_production_out_of_range`."
        ),
        "safe_for_modeling": (
            "Yes -- `WHERE star_by_value_label IS NOT NULL` is the documented, correct "
            "downstream modeling filter (research/dataset3/STARS_BY_VALUE_METHODOLOGY.md). "
            "NULL must never be treated as 0."
        ),
        "provenance_notes": None,
    },
    {
        "name": "star_by_value_production_gate_threshold",
        "dtype": "float64",
        "nullable": True,
        "enum_values": None,
        "description": (
            "The position's production-gate floor (P must clear this before "
            "acquisition-cost/Star scoring is even attempted). Populated even for rows "
            "that never reach a numeric score, so the gate this row faced (or would "
            "have faced) is always auditable when known."
        ),
        "populated_when": "every status except `out_of_scope`.",
        "null_when": "status is `out_of_scope` (the row was never in scope to face any gate).",
        "safe_for_modeling": "Informational/audit field -- not typically consumed directly by downstream models.",
        "provenance_notes": "Distinct from star_by_value_threshold -- this is the FIRST bar (production gate), not the final Star cutoff.",
    },
    {
        "name": "star_by_value_threshold",
        "dtype": "float64",
        "nullable": True,
        "enum_values": None,
        "description": (
            "The position's final Star-label cutoff score. Populated even for rows that "
            "never received a numeric score (`unscoreable_ambiguous`, "
            "`unscoreable_drafted_adp_missing`, `unscoreable_expected_production_out_of_range`) "
            "-- for those rows it documents what threshold this row WOULD have faced if "
            "scoreable, not a claim it was actually compared against one."
        ),
        "populated_when": "every status except `out_of_scope` and `below_production_gate`.",
        "null_when": (
            "status is `out_of_scope` (never in scope) or `below_production_gate` "
            "(never cleared the production gate, so the Star cutoff is not meaningful)."
        ),
        "safe_for_modeling": (
            "Informational/audit field -- combine with star_by_value_score if computing "
            "your own comparison; never assume a null value implies anything about the label."
        ),
        "provenance_notes": "Distinct from star_by_value_production_gate_threshold -- this is the FINAL Star cutoff, not the entry gate.",
    },
)


def validate_schema_matches_columns(actual_columns) -> None:
    """Fails loudly if the real output DataFrame's columns and this
    module's documented schema have drifted apart -- called from
    write_canonical_output() BEFORE anything is written, so a drift
    never produces a Parquet/CSV pair alongside a stale or incomplete
    data dictionary."""
    documented = {c["name"] for c in COLUMN_DOCS}
    actual = set(actual_columns)

    missing_from_output = documented - actual  # documented but the real output doesn't have it
    undocumented_in_output = actual - documented  # real output has it but it's not documented

    if missing_from_output or undocumented_in_output:
        problems = []
        if missing_from_output:
            problems.append(f"documented in schema.py but MISSING from real output: {sorted(missing_from_output)}")
        if undocumented_in_output:
            problems.append(f"present in real output but UNDOCUMENTED in schema.py: {sorted(undocumented_in_output)}")
        raise RuntimeError(
            "SBV output schema has drifted from lib/stars_by_value/schema.py's "
            "COLUMN_DOCS -- refusing to write canonical output until this is fixed:\n  "
            + "\n  ".join(problems)
        )


def render_schema_markdown() -> str:
    lines = [
        "# Stars-by-Value canonical output -- data dictionary",
        "",
        "Generated deterministically by `lib/stars_by_value/schema.py` from a "
        "committed column-metadata mapping (`COLUMN_DOCS`), not by inspecting one "
        "output file. Regenerated on every `--mode canonical` run of "
        "`scripts/11_calculate_stars_by_value.py`; `validate_schema_matches_columns()` "
        "refuses to write canonical output at all if the real output columns and this "
        "document have drifted apart.",
        "",
        f"**Positions in scope**: `{_POSITION_LIST_MD}`",
        "",
        f"**Statuses** ({len(config.SBV_STATUSES)}): `{_STATUS_LIST_MD}`",
        "",
        f"**Provenance types** ({len(config.SBV_PROVENANCE_TYPES)}): `{_PROVENANCE_LIST_MD}`",
        "",
        "---",
        "",
    ]

    for col in COLUMN_DOCS:
        lines.append(f"## `{col['name']}`")
        lines.append("")
        lines.append(f"- **Type**: {col['dtype']}")
        lines.append(f"- **Nullable**: {'Yes' if col['nullable'] else 'No -- required, always populated'}")
        if col["enum_values"]:
            values_md = ", ".join(f"`{v}`" if v is not None else "`NULL`" for v in col["enum_values"])
            lines.append(f"- **Allowed values**: {values_md}")
        lines.append(f"- **Meaning**: {col['description']}")
        lines.append(f"- **Populated (non-null) when**: {col['populated_when']}")
        lines.append(f"- **Null when**: {col['null_when']}")
        lines.append(f"- **Safe for downstream modeling**: {col['safe_for_modeling']}")
        if col["provenance_notes"]:
            lines.append(f"- **Note**: {col['provenance_notes']}")
        lines.append("")

    lines += [
        "---",
        "",
        evidence_audit.render_evidence_audit_markdown(),
        "---",
        "",
        "## Resolved spec gap: `star_by_value_evidence_notes`",
        "",
        "`research/dataset3/STARS_BY_VALUE_METHODOLOGY.md` and "
        "`STARS_BY_VALUE_IMPLEMENTATION_PLAN.md` originally documented a "
        "`star_by_value_evidence_notes` free-text column on the main SBV dataset. "
        "It was never implemented, and was formally REJECTED 2026-07 in favor of "
        "the separate evidence-audit artifact above -- see both docs' preserved "
        "decision history for the original proposal and the rejection reasoning. "
        "The main SBV Parquet/CSV stays strictly structured; case-specific "
        "explanation lives only in `stars_by_value_evidence_audit.csv`.",
        "",
    ]
    return "\n".join(lines)
