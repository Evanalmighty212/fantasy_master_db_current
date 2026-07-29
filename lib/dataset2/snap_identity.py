"""
lib/dataset2/snap_identity.py

Dataset 2 opportunity/usage foundation, Source B -- the `pfr_player_id`
-> canonical `gsis_id` identity crosswalk, approved 2026-07
(research/dataset2/OPPORTUNITY_FOUNDATION_PROPOSAL_2026_07.md). The
real nflverse `snap_counts` release identifies players by
`pfr_player_id` (Pro Football Reference format, e.g. "WillCh03") and a
name string -- NOT `gsis_id`, the identity every other Dataset 2
module and the master DB use. This module is the ONLY place that
crosswalk happens.

REAL FINDINGS THIS MODULE IS BUILT ON (verified directly against the
full real 2013-2025 REG-season population, 310,475 rows -- see
research/dataset2/SNAP_COUNTS_IDENTITY_AUDIT_2026_07.md for the full
report):
- `players.csv.pfr_id` is a clean, real crosswalk: 0 duplicate
  `gsis_id` rows in `players.csv`, 0 real `pfr_id` values shared by
  more than one `gsis_id` (no one-to-many conflict on the source
  side), 0 cases of more than one real `pfr_player_id` value in
  `snap_counts` mapping to the same `gsis_id` (no many-to-one conflict
  either).
- Real overall match rate: 99.93% (310,256 / 310,475 real REG rows).
  Real per-season match rate never drops below 99.79%; real
  per-position match rate never drops below 99.46% (defensive line).
  The ~0.07% that don't match are real, individually-verifiable
  fringe/practice-squad players (spot-checked: names like "Robert
  James", "Jordan Miller" -- real players simply absent from, or with
  a null `pfr_id` in, `players.csv`).
- `players.csv` itself has 2,481 real rows (9.9%) with a null `pfr_id`
  -- these can never match regardless of the snap_counts side.

NEVER SILENTLY DROP a row this module can't match -- every function
here returns EVERY input row, matched or not, with `gsis_id` null on
an unmatched row. Dropping unmatched rows would silently bias any
downstream usage/opportunity trait toward established, well-documented
players and away from exactly the fringe/emerging players this
project's own "Undrafted player representation" principle
(README.md, `docs/METRIC_SPECIFICATION.md`) already treats as
something to represent honestly, not filter out.

TEST SCOPE: tests/test_dataset2_snap_identity.py proves implementation
correctness (crosswalk logic, conflict detection, missingness
handling) against synthetic fixtures. The real match-rate/conflict
numbers above were computed directly against the real, fully-fetched
2013-2025 population (this module's real acquisition, not a sample) --
see the identity audit doc for the full real report.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import validate_columns

SNAPS_REQUIRED_COLUMNS = ("pfr_player_id", "player")
PLAYERS_REQUIRED_COLUMNS = ("gsis_id", "pfr_id")

CROSSWALKED_OUTPUT_EXTRA_COLUMNS = ("gsis_id", "identity_match_status")

MATCH_STATUS_MATCHED = "matched"
MATCH_STATUS_UNMATCHED_NO_PFR_ID_IN_PLAYERS = "unmatched_no_pfr_id_in_players"
MATCH_STATUS_UNMATCHED_NULL_PFR_PLAYER_ID = "unmatched_null_pfr_player_id_in_source"


def crosswalk_snap_counts_identity(snap_counts: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """
    Adds `gsis_id` and `identity_match_status` to every row of
    `snap_counts` -- EVERY row is preserved, matched or not (see module
    docstring). `players` must be the real `players.csv` (or an
    equivalent DataFrame with `gsis_id`/`pfr_id`).

    A row with a null `pfr_player_id` in `snap_counts` itself is
    labeled `MATCH_STATUS_UNMATCHED_NULL_PFR_PLAYER_ID` (a source-side
    gap, not a crosswalk failure). A row whose real `pfr_player_id`
    simply isn't present among `players.csv`'s real (non-null) `pfr_id`
    values is labeled `MATCH_STATUS_UNMATCHED_NO_PFR_ID_IN_PLAYERS`.
    """
    validate_columns(snap_counts, SNAPS_REQUIRED_COLUMNS, "snap_counts")
    validate_columns(players, PLAYERS_REQUIRED_COLUMNS, "players")

    players_nonnull = players.dropna(subset=["pfr_id"])
    dupe_pfr_ids = players_nonnull[players_nonnull.duplicated(subset="pfr_id", keep=False)]
    if len(dupe_pfr_ids) > 0:
        raise RuntimeError(
            f"players.csv has {len(dupe_pfr_ids)} real rows sharing a duplicate "
            f"pfr_id value -- a one-to-many crosswalk conflict that would silently "
            f"fan out the merge below. Refusing to proceed silently; run "
            f"build_identity_audit() to see the exact conflicting rows before "
            f"deciding how to resolve them (this is a real-data situation to "
            f"investigate, not something this function guesses its way through)."
        )

    out = snap_counts.copy()
    before = len(out)
    out = out.merge(
        players_nonnull[["gsis_id", "pfr_id"]], left_on="pfr_player_id", right_on="pfr_id", how="left"
    )
    if len(out) != before:
        raise RuntimeError(
            f"Crosswalk merge changed row count ({before} -> {len(out)}) despite "
            f"the duplicate-pfr_id guard above passing -- this should be "
            f"structurally impossible and indicates a real, unexplained data "
            f"problem. Refusing to proceed."
        )
    out = out.drop(columns=["pfr_id"])

    out["identity_match_status"] = MATCH_STATUS_MATCHED
    out.loc[out["gsis_id"].isna() & out["pfr_player_id"].notna(), "identity_match_status"] = (
        MATCH_STATUS_UNMATCHED_NO_PFR_ID_IN_PLAYERS
    )
    out.loc[out["pfr_player_id"].isna(), "identity_match_status"] = MATCH_STATUS_UNMATCHED_NULL_PFR_PLAYER_ID

    return out


def build_identity_audit(snap_counts: pd.DataFrame, players: pd.DataFrame) -> dict:
    """
    Full identity audit, per the approved requirements -- returns a
    dict of DataFrames/scalars, never discards a row to compute it:

    - "crosswalked": crosswalk_snap_counts_identity()'s own output
      (every row, matched or not).
    - "match_summary": total / matched / unmatched counts and rate.
    - "match_rate_by_season", "match_rate_by_position": if `season`/
      `position` columns are present in `snap_counts`.
    - "unmatched_detail": unique unmatched (pfr_player_id, player)
      pairs with their real row counts -- never just a raw dropped list.
    - "duplicate_pfr_id_mappings": real rows in `players` where one
      pfr_id value is shared by more than one gsis_id (a one-to-many
      conflict on the source side -- checked directly, not assumed
      absent).
    - "many_to_one_conflicts": real cases where more than one distinct
      `pfr_player_id` value in `snap_counts` matched to the SAME
      `gsis_id` (checked directly against the real matched rows, not
      assumed absent).
    - "missing_player_ids": rows where `players.csv` itself has no
      `pfr_id` at all (a real, disclosed source-side gap distinct from
      an unmatched snap_counts row).
    """
    validate_columns(snap_counts, SNAPS_REQUIRED_COLUMNS, "snap_counts")
    validate_columns(players, PLAYERS_REQUIRED_COLUMNS, "players")

    players_nonnull = players.dropna(subset=["pfr_id"])
    duplicate_pfr_id_mappings = players_nonnull[players_nonnull.duplicated(subset="pfr_id", keep=False)].sort_values(
        "pfr_id"
    )

    crosswalked = crosswalk_snap_counts_identity(snap_counts, players)

    total = len(crosswalked)
    matched = int((crosswalked["identity_match_status"] == MATCH_STATUS_MATCHED).sum())
    match_summary = pd.DataFrame(
        [{"total_rows": total, "matched_rows": matched, "unmatched_rows": total - matched,
          "match_rate": matched / total if total else float("nan")}]
    )

    match_rate_by_season = (
        crosswalked.groupby("season")["identity_match_status"]
        .apply(lambda s: (s == MATCH_STATUS_MATCHED).mean())
        .rename("match_rate")
        .reset_index()
        if "season" in crosswalked.columns
        else None
    )
    match_rate_by_position = (
        crosswalked.groupby("position")["identity_match_status"]
        .apply(lambda s: (s == MATCH_STATUS_MATCHED).mean())
        .rename("match_rate")
        .reset_index()
        if "position" in crosswalked.columns
        else None
    )

    unmatched = crosswalked[crosswalked["identity_match_status"] != MATCH_STATUS_MATCHED]
    unmatched_detail = (
        unmatched.groupby(["pfr_player_id", "player", "identity_match_status"])
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values("row_count", ascending=False)
    )

    matched_rows = crosswalked[crosswalked["identity_match_status"] == MATCH_STATUS_MATCHED]
    per_gsis_pfr_count = matched_rows.groupby("gsis_id")["pfr_player_id"].nunique()
    many_to_one_gsis_ids = per_gsis_pfr_count[per_gsis_pfr_count > 1].index
    many_to_one_conflicts = matched_rows[matched_rows["gsis_id"].isin(many_to_one_gsis_ids)][
        ["gsis_id", "pfr_player_id", "player"]
    ].drop_duplicates().sort_values("gsis_id")

    missing_player_ids = players[players["pfr_id"].isna()][["gsis_id"]]

    return {
        "crosswalked": crosswalked,
        "match_summary": match_summary,
        "match_rate_by_season": match_rate_by_season,
        "match_rate_by_position": match_rate_by_position,
        "unmatched_detail": unmatched_detail,
        "duplicate_pfr_id_mappings": duplicate_pfr_id_mappings,
        "many_to_one_conflicts": many_to_one_conflicts,
        "missing_player_ids": missing_player_ids,
    }
