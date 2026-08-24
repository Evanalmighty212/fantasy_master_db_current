"""
lib/dataset2/future_season_spine.py

Governed roster spine for the CURRENT/live "future" prediction_season --
the one Dataset 2 season beyond master_population's own real-outcome
coverage (see canonical_predictor_table.py's own docstring on the
family #9 union). Implements the approved Option 3 design: a governed,
cutoff-dated preseason roster universe, verified to be a superset of
family #9's own independently-derived future-row set.

WHY THIS EXISTS: every lag-joined Dataset 2 family (fam7, fam8/39/44,
fam10/86, fam88, fam18, srcA, srcB, and fam1/2/4/6 via
build_experience_age_draft_traits) computes its output for exactly the
(season, player_id) rows present in `population`. `population` is
built strictly from `master_population` (real, completed-season
results only), so it never contains a row for next season -- these
families are never even ASKED to produce a value for the next
prediction_season, even though the SOURCE data they need (the most
recent completed season's real results) already exists. This module
extends `population` with one identity-only row per eligible player so
those already-correct lag-join builders can compute for real.

WHAT THIS MODULE DOES NOT DO: it never fabricates or estimates an
outcome-side value (ppg_ppr, overall_finish_ppr, etc.) for the extra
row -- those stay null, exactly like every other genuinely-unknowable
case this project already represents as null, never a guessed value.

SCOPE: this mechanism is used ONLY to construct the live spine for the
one prediction_season beyond master_population's own coverage. It must
never be applied to, or merged onto, any historical (already-real-
outcome) prediction_season row -- see
extend_population_with_future_spine()'s own guard and
tests/test_dataset2_future_season_spine.py::TestNoHistoricalContamination.

ROSTER STATUS IS METADATA, NOT A PREDICTOR, AND NOT A TABLE COLUMN
(Dataset 3 v1 decision, approved 2026-08-23; sidecar-only design
revised 2026-08-23 after review): the raw roster status this module
carries through (`roster_status_provenance_frame()`'s
`future_season_roster_status` column) is row provenance/eligibility
context only, returned as a small, separately-keyed sidecar frame --
it is NEVER merged into `build_canonical_predictor_table()`'s own
return value, in any form, not even as an all-null column on
historical rows. A DataFrame's column set is part of its schema, so
adding this column to the canonical table -- even with every
historical value null -- would make that table's historical export
schema-unequal to its pre-repair form, contradicting the byte-identical
historical-invariance guarantee this whole module exists to protect. A
caller that needs the future season's roster status calls
roster_status_provenance_frame() directly on the same
future_season_roster_spine it already holds, joining the result only
to whatever live 2026 prediction output it produces -- never to
data/exports/dataset2_canonical_predictor_table.*,
dataset2_analysis_view.*, or any Dataset 3 training input. It must
never be added to
data/exports/dataset2_analysis_view_predictor_whitelist.csv or
otherwise treated as a Dataset 2/3 feature, because no equivalent
cutoff-dated historical status snapshot exists for any 2006-2025
training row -- doing so would be a real, silent leakage/consistency
bug, not a stylistic preference.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

ROSTER_SNAPSHOT_REQUIRED_COLUMNS = ("gsis_id", "position", "latest_team", "status", "last_season")

# Statuses that, on their own, represent a real preseason roster/reserve
# presence -- included in the spine unconditionally. SUS is included
# per explicit instruction: a suspended player is still a real
# preseason fantasy decision, not a non-entity. UDF (undrafted free
# agent) added 2026-08-24: nflreadr's own dictionary_roster_status does
# not define this code at all, but every real UDF row in the committed
# players.csv snapshot has last_season equal to the current roster
# cycle and zero years of experience -- a genuinely current, unstale
# population by construction, so no recency gate is needed the way it
# is for NWT/RSN/RSR below.
GOVERNED_INCLUDE_STATUSES = frozenset({"ACT", "RES", "DEV", "PUP", "SUS", "UDF"})

# Statuses that represent genuinely out-of-scope players (released,
# retired, on an exempt/reserve/left list unrelated to football
# availability) -- excluded unconditionally, but always with a logged,
# governed reason, never a silent drop.
GOVERNED_EXCLUDE_STATUSES = frozenset({"CUT", "RET", "EXE", "RLS", "INA"})

# Statuses that are NOT themselves a governed include/exclude decision
# -- each requires the same recency check (see _classify_status) before
# admitting a player, rather than a blanket call. Confirmed 2026-08-24
# against nflreadr's own dictionary_roster_status
# (https://nflreadr.nflverse.com/articles/dictionary_roster_status.html,
# the actual maintainers of this data): NWT = "Rarely used, tends to
# indicate a waived player"; RSN = "Rarely used, tends to indicate a
# player is on the non-football injured reserve list"; RSR = "Rarely
# used, tends to indicate a player released from being on the injured
# reserve list". All three are real, rostered-or-recently-rostered
# designations, but the "rarely used" caveat matches what the real
# committed players.csv shows for each: the large majority of rows
# under all three codes are stale by years (NWT: 117 of 120 stale,
# verified 2026-08-23; RSN/RSR: comparable stale-majority pattern,
# verified 2026-08-24, including one real, current, fantasy-relevant
# player -- Joe Mixon, RSN, last_season 2025 -- among the stale
# majority), so a blanket include/exclude for any of the three would
# get real players wrong in one direction or the other. Any OTHER
# status value this project has not explicitly adjudicated is a
# fail-loud condition (see _classify_status), never a guess.
_RECENCY_GATED_STATUSES = frozenset({"NWT", "RSN", "RSR"})


@dataclass(frozen=True)
class RosterSpineResult:
    included: pd.DataFrame
    excluded: pd.DataFrame


def _classify_status(status: str, last_season, prediction_season: int, player_id: str) -> tuple[bool, str]:
    """Returns (included, reason). Raises on any status this project
    has not explicitly adjudicated -- never a silent guess. `player_id`
    is included in the raised error purely for operator diagnosis (so a
    real live run's failure names exactly who tripped it, not just
    which code) -- it plays no role in the classification itself."""
    if status in GOVERNED_INCLUDE_STATUSES:
        return True, f"included_status_{status}"
    if status in GOVERNED_EXCLUDE_STATUSES:
        return False, f"excluded_status_{status}"
    if status in _RECENCY_GATED_STATUSES:
        # Same recency mechanism for all three (see _RECENCY_GATED_STATUSES'
        # own comment for why), but the reason string stays status-specific
        # so the excluded ledger is auditable per real status code, not
        # collapsed into one ambiguous "stale" bucket.
        status_lower = status.lower()
        if pd.isna(last_season):
            return False, f"{status_lower}_no_last_season_excluded"
        if int(last_season) >= prediction_season - 1:
            return True, f"included_{status_lower}_recent"
        return False, f"{status_lower}_stale_last_season_excluded"
    raise ValueError(
        f"ungoverned roster status {status!r} for player_id {player_id!r} has no approved "
        "include/exclude decision -- add it to GOVERNED_INCLUDE_STATUSES or "
        "GOVERNED_EXCLUDE_STATUSES explicitly, or extend the NWT-style recency rule for it; "
        "this module must never silently guess a policy for an unrecognized status value"
    )


def build_future_season_roster_spine(
    roster_snapshot: pd.DataFrame,
    prediction_season: int,
    snapshot_retrieved_at: pd.Timestamp,
    week1_kickoff_earliest: pd.Timestamp,
) -> RosterSpineResult:
    """Builds the governed preseason roster spine for `prediction_season`.

    `roster_snapshot` must have ROSTER_SNAPSHOT_REQUIRED_COLUMNS (the
    real nflverse players.csv reference table, or a synthetic
    equivalent in tests). `snapshot_retrieved_at` is when the snapshot
    was actually taken; `week1_kickoff_earliest` is the earliest real
    per-team Week-1 kickoff date for `prediction_season` (the same
    schedule_df-derived date family #2's age computation already uses
    -- see canonical_predictor_table.py). The snapshot must be strictly
    before that instant, or this raises -- the spine must reflect
    information available when the prediction is made, never a later
    preseason/Week-1 state.

    Returns a RosterSpineResult: `included` (one row per admitted
    player: prediction_season, player_id, position, team,
    roster_status, inclusion_reason) and `excluded` (prediction_season,
    player_id, roster_status, exclusion_reason) for audit/logging --
    never a silent drop.
    """
    missing = sorted(set(ROSTER_SNAPSHOT_REQUIRED_COLUMNS) - set(roster_snapshot.columns))
    if missing:
        raise ValueError(f"roster_snapshot missing required columns: {missing}")
    if snapshot_retrieved_at >= week1_kickoff_earliest:
        raise ValueError(
            f"roster snapshot retrieved_at ({snapshot_retrieved_at}) is not strictly before "
            f"prediction_season {prediction_season}'s earliest real Week-1 kickoff "
            f"({week1_kickoff_earliest}) -- refusing to build a spine that could reflect "
            "in-season information"
        )

    working = roster_snapshot[list(ROSTER_SNAPSHOT_REQUIRED_COLUMNS)].copy()

    duplicate_mask = working["gsis_id"].duplicated(keep=False)
    duplicates = working.loc[duplicate_mask].copy()
    working = working.loc[~duplicate_mask].copy()

    included_rows = []
    excluded_rows = []
    for row in working.itertuples(index=False):
        included, reason = _classify_status(row.status, row.last_season, prediction_season, row.gsis_id)
        target = included_rows if included else excluded_rows
        target.append({
            "prediction_season": prediction_season,
            "player_id": row.gsis_id,
            "position": row.position,
            "team": row.latest_team,
            "roster_status": row.status,
            "reason": reason,
        })
    for row in duplicates.itertuples(index=False):
        excluded_rows.append({
            "prediction_season": prediction_season,
            "player_id": row.gsis_id,
            "position": row.position,
            "team": row.latest_team,
            "roster_status": row.status,
            "reason": "duplicate_gsis_id",
        })

    included = pd.DataFrame(
        included_rows,
        columns=["prediction_season", "player_id", "position", "team", "roster_status", "reason"],
    ).rename(columns={"reason": "inclusion_reason"})
    excluded = pd.DataFrame(
        excluded_rows,
        columns=["prediction_season", "player_id", "position", "team", "roster_status", "reason"],
    ).rename(columns={"reason": "exclusion_reason"})

    if included["player_id"].duplicated().any():
        raise ValueError("resolved roster spine contains a duplicate player_id -- this is a bug")

    return RosterSpineResult(included=included.reset_index(drop=True), excluded=excluded.reset_index(drop=True))


def verify_family9_superset(roster_spine_included: pd.DataFrame, family9_future_rows: pd.DataFrame) -> None:
    """Fails loudly unless every family #9 future-row key is present in
    the roster spine. family #9's own build_family9_preseason_features()
    derives its future-row set independently from real weekly game
    logs; the governed roster spine must be a verified superset of it,
    not merely a plausible one -- a roster source with its own coverage
    gap must never silently under-cover what real game logs already
    prove is a real, current player."""
    required = {"prediction_season", "player_id"}
    if not required <= set(roster_spine_included.columns) or not required <= set(family9_future_rows.columns):
        raise ValueError("both frames must have prediction_season and player_id columns")
    spine_keys = set(zip(roster_spine_included["prediction_season"], roster_spine_included["player_id"]))
    fam9_keys = set(zip(family9_future_rows["prediction_season"], family9_future_rows["player_id"]))
    missing = fam9_keys - spine_keys
    if missing:
        example = sorted(missing)[:10]
        raise ValueError(
            f"roster spine is missing {len(missing)} (prediction_season, player_id) key(s) that "
            f"family #9's real weekly-game-log derivation already proves are current players -- "
            f"example(s): {example}. The roster snapshot is stale or incomplete; it must not be "
            "used until this is resolved."
        )


def extend_population_with_future_spine(
    population: pd.DataFrame,
    roster_spine_included: pd.DataFrame,
    master_population_columns,
) -> pd.DataFrame:
    """Unions one identity-only row per spine player into `population`,
    keyed on (season, player_id) via the spine's own `prediction_season`
    -- so every existing lag-join builder that already operates on
    `population` can compute a real value for this season without any
    change to their own logic. Every non-identity column
    (games_played, ppg_ppr, overall_finish_ppr, position_finish_ppr,
    canonical_position_status/authority, historical_input_revision,
    every preseason_market_status_* field) is left null for the extra
    rows -- genuinely unknowable for a season that has not been played,
    never fabricated.

    Raises if any spine (season, player_id) key already exists in
    `population` -- that would mean the "future" season isn't actually
    future relative to this population, a sign of a caller error, not
    a case to silently overwrite.
    """
    columns = list(master_population_columns)
    for column in ("season", "player_id"):
        if column not in columns:
            raise ValueError(f"master_population_columns must include {column!r}")

    identity_columns = {"season", "player_id", "position", "team"} & set(columns)
    extra = pd.DataFrame(index=roster_spine_included.index)
    for column in columns:
        if column in identity_columns:
            continue
        # Typed-null fill matching population's own dtype for this
        # column, not a generic object-dtype pd.NA -- otherwise
        # pd.concat silently upcasts the whole column (e.g. a real
        # float64 outcome column) to object, corrupting every
        # historical row's dtype too, not just the new ones. A dtype
        # that cannot natively hold a null (plain int64/bool) uses its
        # nullable pandas equivalent instead -- still a real typed
        # null, never a fabricated value.
        source_dtype = population[column].dtype
        n = len(extra)
        if source_dtype.kind == "f":
            extra[column] = pd.Series([float("nan")] * n, index=extra.index, dtype=source_dtype)
        elif source_dtype.kind in ("i", "u"):
            extra[column] = pd.Series([pd.NA] * n, index=extra.index, dtype="Int64")
        elif source_dtype.kind == "b":
            extra[column] = pd.Series([pd.NA] * n, index=extra.index, dtype="boolean")
        else:
            try:
                extra[column] = pd.Series([pd.NA] * n, index=extra.index, dtype=source_dtype)
            except (TypeError, ValueError):
                extra[column] = pd.Series([None] * n, index=extra.index, dtype="object")
    extra["season"] = roster_spine_included["prediction_season"].to_numpy()
    extra["player_id"] = roster_spine_included["player_id"].to_numpy()
    if "position" in columns:
        extra["position"] = roster_spine_included["position"].to_numpy()
    if "team" in columns:
        extra["team"] = roster_spine_included["team"].to_numpy()
    extra = extra[columns]

    combined = pd.concat([population[columns], extra], ignore_index=True)
    if combined.duplicated(subset=["season", "player_id"]).any():
        raise ValueError(
            "future roster spine collides with an existing (season, player_id) row already in "
            "population -- the target prediction_season is not actually future relative to this "
            "population"
        )
    return combined


def roster_status_provenance_frame(roster_spine_included: pd.DataFrame) -> pd.DataFrame:
    """The metadata-only frame merged onto the FINAL predictor table by
    the caller, named `future_season_roster_status` so it is never
    mistaken for a `famN_*`/`srcA_*`/`srcB_*` predictor column. Every
    historical (non-spine) row gets null here by construction (a plain
    left-merge on prediction_season/player_id), not a fabricated
    "n/a" sentinel -- null already correctly means "no future-season
    roster status applies to this row" throughout this codebase's
    conventions.
    """
    return roster_spine_included[["prediction_season", "player_id", "roster_status"]].rename(
        columns={"roster_status": "future_season_roster_status"}
    )
