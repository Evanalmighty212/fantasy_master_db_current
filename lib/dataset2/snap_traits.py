"""
lib/dataset2/snap_traits.py

Dataset 2 opportunity/usage foundation, Source B (approved 2026-07,
research/dataset2/OPPORTUNITY_FOUNDATION_PROPOSAL_2026_07.md) --
snap-count traits, built on top of
lib.dataset2.snap_identity.crosswalk_snap_counts_identity()'s
identity-resolved real data.

REAL FINDINGS THIS MODULE IS BUILT ON (verified against the full real
2013-2025 REG-season `snap_counts` population -- see
research/dataset2/SNAP_COUNTS_IDENTITY_AUDIT_2026_07.md):
- Real coverage: 2013-2025 (2012's real asset is empty -- see
  scripts/nflverse_source.py's SNAP_COUNTS_EMPTY_SEASON).
- Grain: player-GAME (one row per player per real game). Zero real
  duplicate (gsis_id, game_id) rows found in the full real population
  -- this module still actively CHECKS for this on every call (see
  build_raw_player_game_snaps()) rather than only documenting the
  absence, since identity-matching and duplicate/misaligned snap
  records are the two highest real risks in this source.
- `game_type` includes real postseason rows (`WC`/`DIV`/`CON`/`SB`)
  alongside `REG` -- filtered to `REG` internally here, the same real
  bug class already found and fixed in Source A
  (`lib/dataset2/usage_traits.py`).
- `offense_pct`'s real per-game denominator is `max(offense_snaps)`
  for that (game_id, team) -- verified this reconciles against
  nflverse's real reported `offense_pct` with zero rows exceeding a
  0.01 discrepancy across the full real 2023 season (10,078 rows). The
  O-line/QB group reliably plays every real offensive snap, so the max
  observed player IS the real team offensive-play total.
- `defense_pct` and `st_pct` do NOT reliably reconstruct the same way.
  Real check against 2023: a max-based `defense_pct` recomputation
  diverges beyond rounding on 646/10,550 real rows (6.1%), sometimes
  substantially (e.g. a real 0.73 vs. a recomputed 1.00) -- caused by
  real high-rotation defensive games where NO single player reaches
  100% of real defensive snaps, so `max()` understates the true
  denominator. `st_pct` is far worse (16,363/18,055 real rows, 90.6%,
  mean discrepancy 0.068) -- special teams involves multiple distinct
  situational units (kickoff, punt, return, field goal) with different
  real play counts, not one unified platoon the way offense/base
  defense are. Per the same reconstruct-or-defer rule already applied
  to Source A's `racr`: `defense_pct` and `st_pct` are NOT output as
  season-level metrics. `defense_snaps` and `st_snaps` (real,
  unambiguous sums) ARE output.

THREE STRUCTURALLY SEPARATE THINGS, same design as Source A:

1. RAW PLAYER-GAME SNAP DATA (`build_raw_player_game_snaps()`): one
   row per real (gsis_id, game_id), identity-resolved, REG-only, every
   row from the source preserved -- including UNMATCHED rows (null
   `gsis_id`, real `identity_match_status`), which structurally cannot
   contribute to any specific player's season/preseason aggregate
   (there's no real player identity to attribute them to) but remain
   visible here and in the identity audit rather than silently vanishing.
2. SEASON-LEVEL AGGREGATES (`build_season_snap_usage()`): this
   season's own real totals -- SAME-SEASON DATA, never a preseason
   predictor for the season it describes. Plain column names.
3. PRESEASON PREDICTOR FEATURES (`build_preseason_snap_features()`):
   every season field strictly LAGGED to the PRIOR season via the same
   `lag_join()` already used by every other Dataset 2 lag-based module,
   `prior_season_*` prefixed.

TRADED PLAYERS: represented as player-SEASON rows (one row per
`(season, gsis_id)`), same grain as every other Dataset 2 module. The
`offense_pct` recomputation correctly follows a trade because the
team-game denominator lookup is resolved PER GAME using that game's
own real `team` value, then summed across the player's real games --
the same mechanism already verified correct for Source A's
`target_share`.

TEST SCOPE: tests/test_dataset2_snap_traits.py proves implementation
correctness against synthetic fixtures, including an exhaustive
leakage-proof check mirroring Source A's. Real-data integration and
coverage validation at the FULL 2006-2025 population level (this
module only covers 2013-2025 by real necessity) has not happened yet
-- same required checkpoint as every other Dataset 2 module.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import lag_join, validate_columns
from lib.dataset2.snap_identity import MATCH_STATUS_MATCHED, crosswalk_snap_counts_identity

SNAP_COUNTS_REQUIRED_COLUMNS = (
    "season",
    "week",
    "game_id",
    "game_type",
    "team",
    "pfr_player_id",
    "player",
    "offense_snaps",
    "defense_snaps",
    "st_snaps",
)

PLAYERS_REQUIRED_COLUMNS = ("gsis_id", "pfr_id")

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position")

RAW_GAME_OUTPUT_COLUMNS = (
    "season",
    "week",
    "game_id",
    "gsis_id",
    "pfr_player_id",
    "player",
    "team",
    "identity_match_status",
    "offense_snaps",
    "defense_snaps",
    "st_snaps",
)

# Real counts, summed across the season -- unambiguous.
SUM_FIELDS = ("offense_snaps", "defense_snaps", "st_snaps", "games_active")

# Season-level rate RECOMPUTED from real summed numerator/denominator
# -- see module docstring. defense_pct/st_pct are DEFERRED (not
# reconstructable), so this is intentionally a set of one.
RATE_FIELDS = ("offense_pct",)

SEASON_OUTPUT_COLUMNS = ("season", "player_id", "position") + SUM_FIELDS + RATE_FIELDS

PRESEASON_OUTPUT_COLUMNS = ("season", "player_id", "position") + tuple(
    f"prior_season_{f}" for f in SUM_FIELDS + RATE_FIELDS
)


def build_raw_player_game_snaps(snap_counts: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """
    RAW player-game grain, identity-resolved via
    lib.dataset2.snap_identity.crosswalk_snap_counts_identity(),
    filtered to REAL `game_type == 'REG'` rows only. Every row is
    preserved, matched or not -- an unmatched row keeps a null
    `gsis_id` and its real `identity_match_status`, it is never
    dropped here (see module and snap_identity.py docstrings).

    ACTIVELY CHECKS for duplicate (gsis_id, game_id) rows among matched
    rows and raises loudly if found -- per the approved instruction
    that duplicated/misaligned snap records are a top real risk to
    guard against, not just document as absent.
    """
    validate_columns(snap_counts, SNAP_COUNTS_REQUIRED_COLUMNS, "snap_counts")
    validate_columns(players, PLAYERS_REQUIRED_COLUMNS, "players")

    reg = snap_counts[snap_counts["game_type"] == "REG"].copy()
    crosswalked = crosswalk_snap_counts_identity(reg, players)

    matched = crosswalked[crosswalked["identity_match_status"] == MATCH_STATUS_MATCHED]
    dupes = matched[matched.duplicated(subset=["gsis_id", "game_id"], keep=False)]
    if len(dupes) > 0:
        raise RuntimeError(
            f"Found {len(dupes)} real rows with a duplicate (gsis_id, game_id) "
            f"pair after identity crosswalk -- a real duplicate/misaligned snap "
            f"record, which the full 2013-2025 real population audit found zero "
            f"of. Refusing to silently aggregate a duplicated game. Investigate "
            f"the real source rows before proceeding:\n"
            f"{dupes[['gsis_id', 'game_id', 'player', 'pfr_player_id']].to_string()}"
        )

    return crosswalked[list(RAW_GAME_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_season_snap_usage(population: pd.DataFrame, raw_player_game_snaps: pd.DataFrame) -> pd.DataFrame:
    """
    SEASON-level aggregates only -- this season's own real totals and
    the one reliably-recomputed rate (`offense_pct`). Plain column
    names, no prefix. SAME-SEASON DATA -- never use this season's own
    row as a predictor for that season; use
    build_preseason_snap_features() for that.

    `population` scopes which (season, player_id, position) rows are
    RETURNED (every row preserved, even a player with zero real
    snap-count rows). `raw_player_game_snaps` must be
    build_raw_player_game_snaps()'s own output (or equivalent) --
    unmatched rows (null `gsis_id`) are structurally excluded from
    every player's aggregate here, since there's no real player
    identity to attribute them to (they remain visible in the raw
    layer and the identity audit, never silently discarded there).
    """
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(raw_player_game_snaps, RAW_GAME_OUTPUT_COLUMNS, "raw_player_game_snaps")

    matched = raw_player_game_snaps[raw_player_game_snaps["gsis_id"].notna()].copy()

    team_game_totals = (
        matched.groupby(["game_id", "team"]).agg(_team_game_offense_total=("offense_snaps", "max")).reset_index()
    )
    matched = matched.merge(team_game_totals, on=["game_id", "team"], how="left")
    matched["_active_game"] = (
        (matched["offense_snaps"] > 0) | (matched["defense_snaps"] > 0) | (matched["st_snaps"] > 0)
    )

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )

    player_sums = (
        matched.groupby(["season", "gsis_id"])
        .agg(
            offense_snaps=("offense_snaps", "sum"),
            defense_snaps=("defense_snaps", "sum"),
            st_snaps=("st_snaps", "sum"),
            games_active=("_active_game", "sum"),
            _own_team_game_offense_total_sum=("_team_game_offense_total", "sum"),
        )
        .reset_index()
        .rename(columns={"gsis_id": "player_id"})
    )

    out = base.merge(player_sums, on=["season", "player_id"], how="left")
    for field in SUM_FIELDS:
        out[field] = out[field].fillna(0.0)

    out["offense_pct"] = out["offense_snaps"] / out["_own_team_game_offense_total_sum"].replace(0, np.nan)

    return out[list(SEASON_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_preseason_snap_features(season_snap_usage: pd.DataFrame) -> pd.DataFrame:
    """
    PRESEASON predictor features -- every field in `season_snap_usage`
    strictly lagged to the PRIOR season, via the same lag_join() used
    by every other Dataset 2 lag-based module. Every output column is
    prefixed `prior_season_*`. `season_snap_usage` must be
    build_season_snap_usage()'s own output (or equivalent) covering
    the FULL multi-season population.

    Rookie / pre-2013 handling: a player's first real season, or any
    season before real snap_counts coverage begins (2013), has no
    season N-1 row to lag from, so every field is null -- the correct,
    structural behavior, matching every other Dataset 2 lag-based
    module's rookie path.
    """
    validate_columns(season_snap_usage, SEASON_OUTPUT_COLUMNS, "season_snap_usage")

    working = season_snap_usage.drop_duplicates(subset=["season", "player_id"]).reset_index(drop=True)

    for field in SUM_FIELDS + RATE_FIELDS:
        working[f"prior_season_{field}"] = lag_join(working, field, 1)

    return working[list(PRESEASON_OUTPUT_COLUMNS)].reset_index(drop=True)
