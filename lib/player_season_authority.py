"""Season-aware player-position and franchise-team authority.

Raw provider values remain provenance.  These helpers add separately
named canonical fields without changing player identity or silently
turning an unresolved position case into an adjudicated one.
"""

from pathlib import Path

import pandas as pd

SKILL_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})
RESOLVED_CANONICAL_POSITION_STATUSES = frozenset(
    {"approved_override", "adp_source", "constrained_fallback"}
)
IDENTITY_CONFLICT_MATCH_TYPES = frozenset(
    {"exact_name_position_mismatch", "fuzzy_low_confidence"}
)
CANONICAL_POSITION_AUTHORITY_PATH = Path("data/manual/canonical_player_season_positions.csv")

# Canonical team codes use the franchise's season-accurate abbreviation.
# Raw provider values remain preserved separately; canonical_team() maps
# both historical and current aliases to the code valid in that season so
# a franchise rename is never mistaken for a player transaction and
# cross-source joins cannot miss on OAK/LV etc.
FRANCHISE_TEAM_ERAS = (
    ("OAK", "LV", 1900, 2019),
    ("STL", "LA", 1900, 2015),
    ("SD", "LAC", 1900, 2016),
)


def canonical_team(team, season):
    if pd.isna(team) or pd.isna(season):
        return pd.NA
    value = str(team).strip().upper()
    season = int(season)
    for historical, current, first, last in FRANCHISE_TEAM_ERAS:
        if value in {historical, current}:
            return historical if first <= season <= last else current
    return value


def add_canonical_team(df, raw_team_column, output_column="canonical_team"):
    if raw_team_column not in df.columns:
        raise ValueError(f"Missing raw team provenance column: {raw_team_column}")
    if "season" not in df.columns:
        raise ValueError("Missing season required for canonical team authority")
    out = df.copy()
    out[output_column] = [canonical_team(t, s) for t, s in zip(out[raw_team_column], out["season"])]
    return out


def load_canonical_position_authority(path=CANONICAL_POSITION_AUTHORITY_PATH):
    table = pd.read_csv(path, dtype=str)
    required = {
        "player_id", "start_season", "end_season",
        "canonical_fantasy_position", "decision_status", "authority", "notes",
    }
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError(f"Canonical position authority table is missing columns: {missing}")
    table["start_season"] = pd.to_numeric(table["start_season"], errors="raise").astype(int)
    table["end_season"] = pd.to_numeric(table["end_season"], errors="raise").astype(int)
    if (table["start_season"] > table["end_season"]).any():
        raise ValueError("Canonical position authority has start_season after end_season")
    allowed_status = {"approved", "unresolved"}
    if not set(table["decision_status"]).issubset(allowed_status):
        raise ValueError("Canonical position authority has an unsupported decision_status")
    approved = table["decision_status"] == "approved"
    if not table.loc[approved, "canonical_fantasy_position"].isin(SKILL_POSITIONS).all():
        raise ValueError("Approved canonical positions must be QB/RB/WR/TE")
    if table.loc[~approved, "canonical_fantasy_position"].notna().any():
        raise ValueError("Unresolved canonical-position rows must not contain a position")
    expanded = []
    for _, row in table.iterrows():
        for season in range(row["start_season"], row["end_season"] + 1):
            expanded.append((row["player_id"], season))
    if len(expanded) != len(set(expanded)):
        raise ValueError("Canonical position authority contains overlapping player-season ranges")
    return table


def canonical_position_resolved_mask(df):
    """Central resolved-position predicate for decision-bearing consumers."""
    required = {"canonical_fantasy_position", "canonical_position_status"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing canonical position fields: {missing}")
    return (
        df["canonical_fantasy_position"].isin(SKILL_POSITIONS)
        & df["canonical_position_status"].isin(RESOLVED_CANONICAL_POSITION_STATUSES)
    )


def resolved_canonical_position_population(df):
    """Return resolved rows with bare position explicitly canonical.

    Intended for decision-bearing consumers at a master-data boundary;
    it never substitutes processed/source position for unresolved rows.
    """
    out = df.loc[canonical_position_resolved_mask(df)].copy()
    out["position"] = out["canonical_fantasy_position"]
    return out


def _identity_conflict_mask(df):
    conflict = pd.Series(False, index=df.index)
    if "match_type" in df.columns:
        conflict |= df["match_type"].isin(IDENTITY_CONFLICT_MATCH_TYPES)
    if "data_quality_flag" in df.columns:
        conflict |= df["data_quality_flag"].eq("matched_needs_review")
    if "identity_join_status" in df.columns:
        conflict |= df["identity_join_status"].astype("string").str.startswith("unresolved", na=False)
    return conflict


def add_canonical_fantasy_position(df, authority_df):
    """Add canonical position plus explicit provenance/status.

    Authority order is an approved manual decision, then the ADP-source
    position, then a transparently labeled processed-results fallback.
    Explicit unresolved rows remain null and block those lower-priority
    defaults.
    """
    required = {"season", "player_id", "processed_position", "adp_source_position"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Player-season population is missing columns: {missing}")
    out = df.copy()
    out["canonical_fantasy_position"] = pd.NA
    out["canonical_position_status"] = "unresolved_missing_authority"
    out["canonical_position_authority"] = pd.NA

    identity_conflict = _identity_conflict_mask(out)
    adp_present = out["adp_source_position"].isin(SKILL_POSITIONS)
    adp_authority = adp_present & ~identity_conflict
    out.loc[adp_authority, "canonical_fantasy_position"] = out.loc[adp_authority, "adp_source_position"]
    out.loc[adp_authority, "canonical_position_status"] = "adp_source"
    out.loc[adp_authority, "canonical_position_authority"] = "adp_source_position"

    conflicted_adp = adp_present & identity_conflict
    out.loc[conflicted_adp, "canonical_position_status"] = "unresolved_identity_conflict"
    out.loc[conflicted_adp, "canonical_position_authority"] = "adp_source_position_with_identity_conflict"

    # Evan-approved constrained fallback: only clean rows with no ADP
    # authority reach this branch. Known manual conflicts/decisions are
    # represented in authority_df and overwrite this value below;
    # explicit unresolved rules overwrite it with null. It is a named,
    # auditable fallback, never claimed as independently verified
    # preseason evidence.
    processed_fallback = ~adp_present & ~identity_conflict & out["processed_position"].isin(SKILL_POSITIONS)
    out.loc[processed_fallback, "canonical_fantasy_position"] = out.loc[processed_fallback, "processed_position"]
    out.loc[processed_fallback, "canonical_position_status"] = "constrained_fallback"
    out.loc[processed_fallback, "canonical_position_authority"] = "processed_results_position_fallback"

    for _, rule in authority_df.iterrows():
        mask = (
            (out["player_id"] == rule["player_id"])
            & out["season"].between(int(rule["start_season"]), int(rule["end_season"]))
        )
        if rule["decision_status"] == "unresolved":
            out.loc[mask, "canonical_fantasy_position"] = pd.NA
            out.loc[mask, "canonical_position_status"] = "unresolved"
        else:
            out.loc[mask, "canonical_fantasy_position"] = rule["canonical_fantasy_position"]
            out.loc[mask, "canonical_position_status"] = "approved_override"
        out.loc[mask, "canonical_position_authority"] = rule["authority"]

    bad = out["canonical_fantasy_position"].notna() & ~out["canonical_fantasy_position"].isin(SKILL_POSITIONS)
    if bad.any():
        raise ValueError("Resolved canonical fantasy positions must be QB/RB/WR/TE")
    return out
