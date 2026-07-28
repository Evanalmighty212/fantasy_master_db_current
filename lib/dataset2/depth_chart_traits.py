"""
lib/dataset2/depth_chart_traits.py

Dataset 2 family #10 (projected depth-chart position) plus the
depth-chart-dependent sub-signals of families #86 and #88's approved
splits -- approved 2026-07 AFTER a real-data investigation
(research/dataset2/DATASET2_TRAIT_ROADMAP.md §6, family #10) found
that the two real nflverse depth-chart schema eras (2006-2024 vs.
2025) are not naturally comparable for every position, and settled a
tie-preserving design rather than forcing a strict order the source
data does not support.

REAL FINDINGS THIS DESIGN IS BUILT ON (verified directly, not assumed):
- Both schema eras include real special-teams rows tagged under the
  SAME position code as offensive skill players (e.g. a WR listed as
  a kick/punt returner, or a QB/TE on a field-goal unit). Filtering to
  genuine offensive rows is REQUIRED for all four positions, not just
  WR -- verified: pre-2025 `formation == 'Offense'` (checked against
  real 2020 data: 78 QB / 492 RB / 1,808 WR / 16 TE rows were tagged
  'Special Teams' or 'Defense' and would have been wrongly included
  without this filter); 2025 `pos_grp == '3WR 1TE'` (checked against
  real 2025 data: 100% of QB/RB/WR/TE rows fall under this exact
  label, zero exceptions -- the filter is both necessary and
  sufficient, not assumed to generalize from a single example).
- The pre-2025 schema's `depth_team` column does NOT give a clean,
  unique ordinal rank for every position. WR structurally lists
  multiple players (near-universally 3, checked across all 32 teams'
  2020 Week-1 depth charts) at `depth_team == 1` simultaneously -- this
  is not a data error, it reflects a real "3WR" base personnel
  package. RB and TE ALSO show real (less frequent, ~12-15% of teams
  in the same 2020 check) `depth_team == 1` ties, representing genuine
  committees (e.g. real 2020 examples: New England's James White/Sony
  Michel, Kansas City's Travis Kelce/Deon Yelder). QB does not show
  this pattern in the same check.
- The 2025 schema's `pos_rank` is a STRICT sequential ordinal with no
  ties, for every position, including RB and TE -- verified directly
  (no duplicate pos_rank found within any (team, dt) group for RB or
  TE in the real 2025 data). This means the 2025 vendor always breaks
  a tie into an arbitrary order, even in a real committee situation
  the pre-2025 schema would have honestly reported as tied. The two
  eras' "rank 1" are therefore NOT proven equivalent in tied cases.

DESIGN, following directly from the above (approved 2026-07):
1. Preserve the NATIVE rank exactly as each schema reports it --
   `depth_chart_native_rank` -- never re-ordered, never tie-broken by
   row order, alphabetization, ADP, snaps, or later production. Ties
   are real information, not a data-quality problem to paper over.
2. Build ONE standardized, era-comparable status
   (`depth_chart_status`: starter/backup/deeper) FROM that native
   rank, identically for both eras: rank 1 -> starter (ALL players
   tied at rank 1 are starters, none ranked ahead of another), rank 2
   -> backup, rank 3+ -> deeper. This is the primary era-comparable
   feature, not the native rank itself.
3. `depth_rank_tied`: True wherever more than one player shares the
   exact same native rank within that (season, team, position) group.
   Always False for 2025 rows (the vendor's schema structurally
   cannot produce a tie), which is itself a documented fact about the
   2025 source, not evidence the underlying role was genuinely
   unshared that year -- see `depth_chart_schema_era` below.
4. `starter_group_size`: the REAL, OBSERVED count of distinct players
   at native rank 1 for this row's (season, team, position) group.
   Broadcast to every row in that group (not just the starters
   themselves), so a bench player's row also shows how crowded their
   position's real starting group was.
5. `position_starter_count`: the FIXED structural reference value from
   config.DATASET2_DEPTH_CHART_STRUCTURAL_STARTER_COUNT (QB=RB=TE=1,
   WR=3) -- deliberately NOT derived from this row's own observed
   ties, so a real 2-player RB committee (`starter_group_size=2`
   against a structural `position_starter_count=1`) stays
   distinguishable from WR's normal 3-wide starting group
   (`starter_group_size=3` against `position_starter_count=3`, an
   unremarkable match).
6. `depth_chart_schema_era`: SCHEMA_ERA_HISTORICAL or
   SCHEMA_ERA_2025_STRICT_ORDER on every row, so downstream analysis
   can explicitly test whether an effect differs between the
   tie-preserving historical schema and the 2025 strict-order schema,
   rather than silently pooling two structurally different sources.

`depth_chart_native_rank` is a research feature ONLY where
`depth_rank_tied` is False (or, for 2025 rows, understood as a
vendor-forced order that cannot prove the role was unshared) -- this
module does not filter or warn on that basis itself, it only exposes
both fields honestly so a consumer can.

PRESEASON-TIMING VALIDATION (required, both eras):
- Pre-2025: exactly the `week == 1, game_type == 'REG'` snapshot,
  matching the already-established, already-tested convention.
- 2025: the latest `dt` snapshot on or before that TEAM's real 2025
  Week-1 REG kickoff date (from `schedule_df`), reusing the exact
  selection rule already proven in
  lib.stars_by_value.acquisition_cost.apply_rookie_qb_depth_chart_correction(),
  generalized here beyond that function's QB-only scope.

MISSINGNESS: a population row with no matching depth-chart row in
either era (not on any offensive personnel list at the preseason
snapshot -- inactive, practice squad, not yet on a roster) gets every
trait field null, never a guessed "deeper" default -- "no data" and
"confirmed 4th string" are different facts.

TEST SCOPE: tests/test_dataset2_depth_chart_traits.py proves
implementation correctness (offensive filtering, tie preservation,
status/group-size computation, snapshot selection) against synthetic
fixtures only. Real-data integration and coverage validation has not
happened yet -- same required checkpoint as this module's siblings,
see research/dataset2/DATASET2_TRAIT_ROADMAP.md §6.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import DATASET2_DEPTH_CHART_STRUCTURAL_STARTER_COUNT
from lib.dataset2.common import kickoff_lookup_table, validate_columns

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position")

PRE2025_REQUIRED_COLUMNS = (
    "season",
    "club_code",
    "week",
    "game_type",
    "formation",
    "gsis_id",
    "position",
    "depth_team",
)

SCHEMA2025_REQUIRED_COLUMNS = ("dt", "team", "gsis_id", "pos_grp", "pos_abb", "pos_rank")

SCHEDULE_REQUIRED_COLUMNS = ("season", "game_type", "week", "gameday", "home_team", "away_team")

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

DEPTH_CHART_STATUS_STARTER = "starter"
DEPTH_CHART_STATUS_BACKUP = "backup"
DEPTH_CHART_STATUS_DEEPER = "deeper"

SCHEMA_ERA_HISTORICAL = "historical_tie_preserving"
SCHEMA_ERA_2025_STRICT_ORDER = "2025_vendor_strict_order"

# 2025's real offensive personnel-package label, verified 2026-07 to
# cover 100% of real QB/RB/WR/TE rows with zero exceptions -- see
# module docstring.
SCHEMA2025_OFFENSIVE_PERSONNEL_GROUP = "3WR 1TE"

OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "depth_chart_team",
    "depth_chart_native_rank",
    "depth_chart_status",
    "depth_rank_tied",
    "starter_group_size",
    "position_starter_count",
    "depth_chart_schema_era",
)


def _pre2025_offensive_week1_long(depth_chart_pre2025_df: pd.DataFrame) -> pd.DataFrame:
    """Historical schema -> the common long format (season, team,
    position, player_id, native_rank, schema_era), filtered to REAL
    offensive rows at the real Week-1 REG snapshot, skill positions
    only. A player who appears more than once at this exact snapshot
    (a genuine rarity -- see module docstring) is deduplicated
    deterministically by keeping the first row after sorting, not left
    ambiguous."""
    validate_columns(depth_chart_pre2025_df, PRE2025_REQUIRED_COLUMNS, "depth_chart_pre2025_df")

    df = depth_chart_pre2025_df[
        (depth_chart_pre2025_df["formation"] == "Offense")
        & (depth_chart_pre2025_df["week"] == 1)
        & (depth_chart_pre2025_df["game_type"] == "REG")
        & (depth_chart_pre2025_df["position"].isin(SKILL_POSITIONS))
    ].copy()

    out = df.rename(
        columns={"club_code": "team", "gsis_id": "player_id", "depth_team": "native_rank"}
    )[["season", "team", "position", "player_id", "native_rank"]]
    out = out.sort_values(["season", "team", "position", "player_id"]).drop_duplicates(
        subset=["season", "player_id"], keep="first"
    )
    out["schema_era"] = SCHEMA_ERA_HISTORICAL
    return out.reset_index(drop=True)


def _select_2025_preseason_snapshot(depth_chart_2025_df: pd.DataFrame, schedule_df: pd.DataFrame) -> pd.DataFrame:
    """Per team, the latest real `dt` snapshot on or before that
    team's real 2025 Week-1 REG kickoff date -- the exact selection
    rule already proven in
    acquisition_cost.apply_rookie_qb_depth_chart_correction(),
    generalized here beyond that function's QB-only scope. A team with
    no resolvable kickoff date or no eligible snapshot is simply
    absent from the result (null downstream), never an error."""
    kickoff_by_team = kickoff_lookup_table(schedule_df, [2025]).set_index("team")["_kickoff_date"].to_dict()

    dc = depth_chart_2025_df.copy()
    dc["_date"] = pd.to_datetime(dc["dt"]).dt.tz_localize(None).dt.normalize()

    frames = []
    for team, kickoff in kickoff_by_team.items():
        team_dc = dc[dc["team"] == team]
        eligible = team_dc[team_dc["_date"] <= kickoff]
        if eligible.empty:
            continue
        snapshot_date = eligible["_date"].max()
        frames.append(team_dc[team_dc["_date"] == snapshot_date])

    if not frames:
        return dc.iloc[0:0]
    return pd.concat(frames, ignore_index=True)


def _2025_offensive_preseason_long(depth_chart_2025_df: pd.DataFrame, schedule_df: pd.DataFrame) -> pd.DataFrame:
    """2025 schema -> the common long format, filtered to REAL
    offensive rows (`pos_grp == SCHEMA2025_OFFENSIVE_PERSONNEL_GROUP`)
    at the correctly-selected preseason snapshot, skill positions
    only."""
    validate_columns(depth_chart_2025_df, SCHEMA2025_REQUIRED_COLUMNS, "depth_chart_2025_df")
    validate_columns(schedule_df, SCHEDULE_REQUIRED_COLUMNS, "schedule_df")

    snapshot = _select_2025_preseason_snapshot(depth_chart_2025_df, schedule_df)
    df = snapshot[
        (snapshot["pos_grp"] == SCHEMA2025_OFFENSIVE_PERSONNEL_GROUP) & (snapshot["pos_abb"].isin(SKILL_POSITIONS))
    ].copy()

    out = df.rename(columns={"gsis_id": "player_id", "pos_abb": "position", "pos_rank": "native_rank"})
    out["season"] = 2025
    out = out[["season", "team", "position", "player_id", "native_rank"]]
    out = out.sort_values(["season", "team", "position", "player_id"]).drop_duplicates(
        subset=["season", "player_id"], keep="first"
    )
    out["schema_era"] = SCHEMA_ERA_2025_STRICT_ORDER
    return out.reset_index(drop=True)


def _standardize(long_df: pd.DataFrame) -> pd.DataFrame:
    """Common-format long df (season, team, position, player_id,
    native_rank, schema_era) -> every OUTPUT_COLUMNS trait field.
    Never forces a strict order -- ties in `native_rank` are read
    directly from the source and preserved."""
    out = long_df.copy()
    out["depth_chart_native_rank"] = out["native_rank"]
    out["depth_chart_status"] = np.select(
        [out["native_rank"] == 1, out["native_rank"] == 2],
        [DEPTH_CHART_STATUS_STARTER, DEPTH_CHART_STATUS_BACKUP],
        default=DEPTH_CHART_STATUS_DEEPER,
    )

    group_cols = ["season", "team", "position"]
    out["depth_rank_tied"] = (
        out.groupby(group_cols + ["native_rank"])["player_id"].transform("nunique") > 1
    )

    starter_counts = (
        out[out["native_rank"] == 1]
        .groupby(group_cols)["player_id"]
        .nunique()
        .rename("starter_group_size")
    )
    out = out.merge(starter_counts, on=group_cols, how="left")
    out["starter_group_size"] = out["starter_group_size"].fillna(0).astype(int)

    out["position_starter_count"] = out["position"].map(DATASET2_DEPTH_CHART_STRUCTURAL_STARTER_COUNT)
    out["depth_chart_schema_era"] = out["schema_era"]
    out["depth_chart_team"] = out["team"]

    return out


def build_depth_chart_traits(
    population: pd.DataFrame,
    depth_chart_pre2025_df: pd.DataFrame,
    depth_chart_2025_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Builds family #10's standardized depth-chart status (and the
    #86/#88 sub-signals that depend on it) for every row in
    `population`. Every row in `population` is preserved -- a player
    with no matching real offensive depth-chart row at the preseason
    snapshot gets every trait field null, not a guessed default.

    `depth_chart_pre2025_df` and `depth_chart_2025_df` may each be an
    empty (but correctly-columned) DataFrame if that schema era isn't
    relevant to your population slice -- e.g. a 2006-2024-only
    population can pass an empty `depth_chart_2025_df`.
    """
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )

    pre2025_long = _pre2025_offensive_week1_long(depth_chart_pre2025_df)
    if len(depth_chart_2025_df) > 0:
        the_2025_long = _2025_offensive_preseason_long(depth_chart_2025_df, schedule_df)
    else:
        the_2025_long = pre2025_long.iloc[0:0]

    combined_long = pd.concat([pre2025_long, the_2025_long], ignore_index=True)
    standardized = _standardize(combined_long)

    out = base.merge(
        standardized[["season", "player_id"] + [c for c in OUTPUT_COLUMNS if c not in ("season", "player_id", "position")]],
        on=["season", "player_id"],
        how="left",
    )

    return out[list(OUTPUT_COLUMNS)].reset_index(drop=True)
