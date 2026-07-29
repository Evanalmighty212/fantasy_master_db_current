"""
lib/dataset2/participation_identity.py

Dataset 2 Source C Stage 1 -- the identity audit `pbp_participation`
still needs even though it requires NO crosswalk. Unlike Source B
(`snap_counts`, keyed by `pfr_player_id`, a different ID system than
the master DB's `player_id`), `pbp_participation` natively reports
real `gsis_id` values -- the SAME ID system the master DB's
`player_id` column already uses (confirmed directly: Source B's own
crosswalk resolves `pfr_id` -> a `gsis_id`-shaped `player_id`). So a
row here is either a direct, real `(season, gsis_id)` match against
the population or it is not -- there is no mapping step that could
itself introduce ambiguity the way Source B's `pfr_id` lookup could.

That does NOT mean every real ID resolves. Three real, distinct
non-match situations must stay distinguishable, never collapsed into
one "unmatched" bucket:
1. The `gsis_id` never appears in the population at all (e.g. real
   long-snappers, or any real participant not in the master DB's
   scope).
2. The `gsis_id` is a KNOWN player elsewhere in the population, but
   not for THIS season (e.g. real off-year / not-rostered-in-DB gaps).
3. The token itself is malformed (flagged upstream by
   `participation_traits.normalize_participation()`'s
   `has_malformed_token`) -- structurally can't match anything.

No row is ever dropped for being unmatched -- every row from
`normalize_participation()`'s output gets a `match_status` label and
is retained in `audit_detail()`'s row-level output.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import validate_columns

NORMALIZED_REQUIRED_COLUMNS = ("season", "gsis_id", "has_malformed_token")
POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position")

MATCH_STATUS_MATCHED = "matched"
MATCH_STATUS_UNMATCHED_MALFORMED_TOKEN = "unmatched_malformed_token"
MATCH_STATUS_UNMATCHED_UNKNOWN_ID = "unmatched_id_not_in_population_any_season"
MATCH_STATUS_UNMATCHED_WRONG_SEASON = "unmatched_known_id_different_season"


def _classify(row, known_ids_any_season: set, season_id_pairs: set) -> str:
    if row["has_malformed_token"]:
        return MATCH_STATUS_UNMATCHED_MALFORMED_TOKEN
    if (row["season"], row["gsis_id"]) in season_id_pairs:
        return MATCH_STATUS_MATCHED
    if row["gsis_id"] in known_ids_any_season:
        return MATCH_STATUS_UNMATCHED_WRONG_SEASON
    return MATCH_STATUS_UNMATCHED_UNKNOWN_ID


def audit_detail(normalized: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    """Row-level identity audit -- one row per input row (never
    deduplicated or dropped), with a `match_status` and, when matched,
    the population's real `position` attached."""
    validate_columns(normalized, NORMALIZED_REQUIRED_COLUMNS, "normalized")
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")

    pop = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"])
    known_ids_any_season = set(pop["player_id"])
    season_id_pairs = set(zip(pop["season"], pop["player_id"]))

    out = normalized.copy()
    out["match_status"] = out.apply(lambda r: _classify(r, known_ids_any_season, season_id_pairs), axis=1)

    out = out.merge(
        pop.rename(columns={"player_id": "gsis_id", "position": "population_position"}),
        on=["season", "gsis_id"],
        how="left",
    )
    return out


def build_identity_audit(normalized: pd.DataFrame, population: pd.DataFrame):
    """Returns (summary_by_season, summary_by_position, unmatched_detail).

    - summary_by_season: real match-rate by season, over DISTINCT
      (season, gsis_id) pairs (an audit of player identities, not of
      raw play-participation row volume, which would over-weight
      high-snap players).
    - summary_by_position: same, grouped by the real population
      `position` where known; unmatched-with-no-known-position rows
      are grouped under a literal "unknown" bucket, never dropped.
    - unmatched_detail: every distinct (season, gsis_id, match_status)
      that did not match, with an occurrence count -- never silently
      discarded.
    """
    detail = audit_detail(normalized, population)
    distinct = detail.drop_duplicates(subset=["season", "gsis_id"]).copy()

    summary_by_season = (
        distinct.groupby("season")["match_status"]
        .apply(lambda s: (s == MATCH_STATUS_MATCHED).sum() / len(s))
        .rename("match_rate")
        .reset_index()
    )

    distinct["audit_position"] = distinct["population_position"].fillna("unknown")
    summary_by_position = (
        distinct.groupby("audit_position")["match_status"]
        .apply(lambda s: (s == MATCH_STATUS_MATCHED).sum() / len(s))
        .rename("match_rate")
        .reset_index()
    )

    unmatched = distinct[distinct["match_status"] != MATCH_STATUS_MATCHED]
    unmatched_detail = (
        unmatched.groupby(["season", "gsis_id", "match_status"]).size().rename("n_plays_involved").reset_index()
    )

    return summary_by_season, summary_by_position, unmatched_detail
