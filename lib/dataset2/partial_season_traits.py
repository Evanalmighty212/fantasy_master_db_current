"""
lib/dataset2/partial_season_traits.py

Dataset 2 family #9 (partial-season production splits) -- SAMPLE-SIZE
PORTION ONLY. REWRITTEN 2026-07 after a real, confirmed bug was found
in the original window logic (see
research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md §0):
the original version used `season_length()` (real GAMES played, 16 or
17) directly as the maximum real REG week NUMBER, which is wrong by
one -- real REG week numbers run 1..season_length(season)+1 because
every team's real bye week consumes a week-number slot without a
played game (verified directly: real 2015 weeks run 1-17 despite
season_length(2015)==16). Verified directly against the ORIGINAL
committed code before rewriting: `build_final_n_games_traits(n=4)`
against real 2015 data returned windows as large as 5 games, not 4.

THIS REWRITE ALSO CHANGES THE WINDOW DEFINITION ITSELF, per instruction
-- not just the boundary arithmetic. Windows are no longer defined by
calendar week number at all. Two structurally different window types
are now built, kept separate (never collapsed into one column), because
they answer different real questions:

1. TEAM-GAME windows (`build_team_game_final_n_traits()`,
   `build_team_game_half_split_traits()`) -- the PRIMARY late-season
   trait. A team's real final N (or first/second half of) REG games,
   built from `lib.dataset2.common.build_team_game_index()` (derived
   from the full real weekly file, no separate schedule fetch needed).
   Every one of the team's real games in the window counts, INCLUDING
   a game where the player was inactive or recorded zero real usage --
   those get zero-filled, never dropped. This is what "reflects real
   late-season availability and production" means: a player who got
   benched or hurt for 2 of his team's final 4 games shows that
   reality in this window, not just his stats from the 2 games he
   happened to play.

2. ACTIVE-GAME windows (`build_active_game_final_n_traits()`) -- a
   SECONDARY, performance-when-active diagnostic. The player's own
   real final N games with a real weekly row (chronological order),
   regardless of how many real team games that spanned. Immune to the
   week-boundary bug BY CONSTRUCTION -- it never does week-number
   arithmetic at all, just takes the player's own last N real rows in
   week order.

TEAM-GAME WINDOWS ARE RESTRICTED TO SINGLE-TEAM PLAYERS. A player with
2+ distinct real teams in `weekly_player` this season is explicitly
EXCLUDED from team-game windows (`team_game_window_applicable=False`,
every trait field null, never guessed or defaulted) -- "the team's
final N games" is genuinely ambiguous for a player who changed teams
mid-season. That real comparison belongs to a separate trade-split
analysis (see the reliability proposal doc's §4), not this module.

MINIMUM-SAMPLE FLOOR, real but DIFFERENT MEANING per window type:
- Team-game windows: `team_final_n_games`/`first_half_team_games`/
  `second_half_team_games` is ALWAYS exactly the window size by
  construction (a team-game window always contains exactly N of the
  team's real games). The real sample-size question here is instead
  "how many of those N real team games did the player actually have
  real usage in" -- `team_final_n_active_games` -- which is what the
  PRIMARY (>=4)/SENSITIVITY (>=3) floor is checked against.
- Active-game windows: `active_final_n_games` can be less than N (a
  player with only 2 real games all season can't produce a 4-game
  active window) -- the floor is checked against this count directly,
  same convention as the module's original design.

MINIMUM-OPPORTUNITY IS DELIBERATELY NOT IMPLEMENTED HERE.
`opportunity_qualified` is present in every output row but is ALWAYS
the literal string OPPORTUNITY_STATUS_PENDING -- never True/False,
never silently defaulted to "qualified." See the reliability proposal
doc for real candidate opportunity floors (general snap-share +
position-specific touch metrics); no threshold has been selected.

TEST SCOPE: tests/test_dataset2_partial_season_traits.py proves
implementation correctness (team-game vs. active-game window
construction, real 16/17-game-era boundary handling, inactive-game
zero-filling, traded-player exclusion, floor enforcement) against
synthetic fixtures. tests/test_dataset2_common.py separately proves
`real_reg_week_slots()`/`build_team_game_index()` correctness, which
this module now relies on rather than re-deriving.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY, DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY
from lib.dataset2.common import build_team_game_index, validate_columns

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position")
WEEKLY_PLAYER_REQUIRED_COLUMNS = ("season", "player_id", "week", "team", "fantasy_points_ppr")

OPPORTUNITY_STATUS_PENDING = "pending"

TEAM_GAME_FINAL_N_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "window_n",
    "team_game_window_applicable",
    "team_final_n_games",
    "team_final_n_active_games",
    "team_final_n_games_ppg",
    "team_final_n_sample_qualified_primary",
    "team_final_n_sample_qualified_sensitivity",
    "opportunity_qualified",
)

ACTIVE_GAME_FINAL_N_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "window_n",
    "active_final_n_games",
    "active_final_n_games_ppg",
    "active_final_n_sample_qualified_primary",
    "active_final_n_sample_qualified_sensitivity",
    "opportunity_qualified",
)

TEAM_GAME_HALF_SPLIT_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "team_game_window_applicable",
    "first_half_team_games",
    "first_half_active_games",
    "first_half_ppg",
    "first_half_sample_qualified_primary",
    "first_half_sample_qualified_sensitivity",
    "second_half_team_games",
    "second_half_active_games",
    "second_half_ppg",
    "second_half_sample_qualified_primary",
    "second_half_sample_qualified_sensitivity",
    "opportunity_qualified",
)


def _apply_floor(active_games: pd.Series, ppg: pd.Series):
    """Returns (ppg_with_floor_enforced, qualified_primary, qualified_sensitivity).
    ppg is set to NaN wherever active_games < SENSITIVITY floor -- a
    <3-real-game sample is never a usable finding, structurally, not
    just by convention. `active_games` is the count of games with REAL
    usage -- for a team-game window this is `*_active_games`, NOT the
    (always-full) window size."""
    qualified_primary = active_games >= DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY
    qualified_sensitivity = active_games >= DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY
    ppg_enforced = np.where(qualified_sensitivity, ppg, np.nan)
    return ppg_enforced, qualified_primary, qualified_sensitivity


def _player_single_team(weekly_player: pd.DataFrame) -> pd.DataFrame:
    """(season, player_id) -> their one real team for the season, ONLY
    for players with exactly one distinct real team in `weekly_player`.
    A traded player (2+ distinct real teams) or a player with zero real
    rows is simply absent from the result, never guessed -- team-game
    windows require an unambiguous "the team" to look up that team's
    real games."""
    counts = weekly_player.groupby(["season", "player_id"])["team"].nunique()
    single_ids = counts[counts == 1].index
    first_team = weekly_player.groupby(["season", "player_id"])["team"].first()
    return first_team.loc[single_ids].rename("team").reset_index()


def _scope_to_team_games(
    population: pd.DataFrame, weekly_player: pd.DataFrame, weekly_all_positions: pd.DataFrame
):
    """Shared setup for every team-game-window builder: `base`
    (population scope), `player_team` (single-team players only), and
    `team_game_index` (every real team's real REG games, chronologically
    indexed, bye-gap-compressed -- see common.build_team_game_index())."""
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(weekly_player, WEEKLY_PLAYER_REQUIRED_COLUMNS, "weekly_player")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )
    player_team = _player_single_team(weekly_player)
    team_game_index = build_team_game_index(weekly_all_positions)
    return base, player_team, team_game_index


def _aggregate_team_window(
    base: pd.DataFrame,
    player_team: pd.DataFrame,
    window_weeks: pd.DataFrame,
    weekly_player: pd.DataFrame,
    label_prefix: str,
    games_col: str,
    active_col: str,
    ppg_col: str,
):
    """`window_weeks`: (season, team, week[, half]) -- the specific
    real team-games in scope. Joins each single-team player to their
    team's real games in the window, zero-fills any game with no real
    player row (inactive/no usage -- never dropped), and aggregates.
    Returns a DataFrame keyed on (season, player_id[, half]) with
    `games_col`/`active_col`/`ppg_col` (raw, floor not yet applied)."""
    group_keys = ["season", "player_id"] + (["half"] if "half" in window_weeks.columns else [])

    scoped = player_team.merge(window_weeks, on=["season", "team"], how="inner")
    merged = scoped.merge(
        weekly_player[["season", "player_id", "week", "fantasy_points_ppr"]],
        on=["season", "player_id", "week"],
        how="left",
        indicator=True,
    )
    merged["_active"] = merged["_merge"] == "both"
    merged["fantasy_points_ppr"] = merged["fantasy_points_ppr"].fillna(0.0)

    agg = (
        merged.groupby(group_keys)
        .agg(**{games_col: ("week", "nunique"), active_col: ("_active", "sum"), "_total": ("fantasy_points_ppr", "sum")})
        .reset_index()
    )
    agg[ppg_col] = agg["_total"] / agg[games_col].replace(0, np.nan)
    return agg.drop(columns=["_total"])


def build_team_game_final_n_traits(
    population: pd.DataFrame, weekly_player: pd.DataFrame, weekly_all_positions: pd.DataFrame, n: int
) -> pd.DataFrame:
    """PRIMARY late-season trait: the player's own (single) team's real
    final `n` REG games, zero-filling any game the player didn't record
    real usage in (inactive, healthy scratch, etc. -- cause not
    distinguished, only the real fact of zero usage that game).
    Traded players get `team_game_window_applicable=False` and every
    other field null."""
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    base, player_team, team_game_index = _scope_to_team_games(population, weekly_player, weekly_all_positions)

    tgi = team_game_index.copy()
    tgi["_games_from_end"] = tgi["team_total_games"] - tgi["team_game_index"]
    final_n_weeks = tgi[tgi["_games_from_end"] < n][["season", "team", "week"]]

    agg = _aggregate_team_window(
        base,
        player_team,
        final_n_weeks,
        weekly_player,
        "team_final_n",
        "team_final_n_games",
        "team_final_n_active_games",
        "team_final_n_games_ppg",
    )

    out = base.merge(player_team, on=["season", "player_id"], how="left")
    out["team_game_window_applicable"] = out["team"].notna()
    out = out.merge(agg, on=["season", "player_id"], how="left")

    (
        out["team_final_n_games_ppg"],
        out["team_final_n_sample_qualified_primary"],
        out["team_final_n_sample_qualified_sensitivity"],
    ) = _apply_floor(out["team_final_n_active_games"], out["team_final_n_games_ppg"])

    out["window_n"] = n
    out["opportunity_qualified"] = OPPORTUNITY_STATUS_PENDING

    return out[list(TEAM_GAME_FINAL_N_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_active_game_final_n_traits(population: pd.DataFrame, weekly_player: pd.DataFrame, n: int) -> pd.DataFrame:
    """SECONDARY performance-when-active diagnostic: the player's own
    real final `n` games WITH real usage, chronological order. Never
    does week-number arithmetic (immune to the real week-boundary bug
    by construction) -- structurally cannot return more than `n` real
    rows: `_rank_from_end < n` selects at most `n` of a player's own
    real weekly rows regardless of how many real calendar weeks they
    span."""
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(weekly_player, WEEKLY_PLAYER_REQUIRED_COLUMNS, "weekly_player")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )

    w = weekly_player.sort_values(["season", "player_id", "week"])
    w = w.assign(_rank_from_end=w.groupby(["season", "player_id"]).cumcount(ascending=False))
    in_window = w[w["_rank_from_end"] < n]

    agg = (
        in_window.groupby(["season", "player_id"])
        .agg(active_final_n_games=("week", "count"), _total=("fantasy_points_ppr", "sum"))
        .reset_index()
    )

    out = base.merge(agg, on=["season", "player_id"], how="left")
    out["active_final_n_games"] = out["active_final_n_games"].fillna(0).astype(int)
    ppg_raw = out["_total"] / out["active_final_n_games"].replace(0, np.nan)

    (
        out["active_final_n_games_ppg"],
        out["active_final_n_sample_qualified_primary"],
        out["active_final_n_sample_qualified_sensitivity"],
    ) = _apply_floor(out["active_final_n_games"], ppg_raw)

    out["window_n"] = n
    out["opportunity_qualified"] = OPPORTUNITY_STATUS_PENDING

    return out[list(ACTIVE_GAME_FINAL_N_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_team_game_half_split_traits(
    population: pd.DataFrame, weekly_player: pd.DataFrame, weekly_all_positions: pd.DataFrame
) -> pd.DataFrame:
    """First-half vs. second-half PPG, split by each team's real
    chronological REG game INDEX (`ceil(team_total_games / 2)`), NOT
    calendar week number -- a team's real bye shifts every later game's
    calendar week without changing its real game-index position, so
    this is NOT the same split the original (buggy) week-number version
    produced. Zero-fills any team game the player had no real usage in,
    same as build_team_game_final_n_traits(). Traded players get
    `team_game_window_applicable=False`."""
    base, player_team, team_game_index = _scope_to_team_games(population, weekly_player, weekly_all_positions)

    tgi = team_game_index.copy()
    tgi["_cutoff"] = np.ceil(tgi["team_total_games"] / 2)
    tgi["half"] = np.where(tgi["team_game_index"] <= tgi["_cutoff"], "first_half", "second_half")
    half_weeks = tgi[["season", "team", "week", "half"]]

    agg = _aggregate_team_window(
        base, player_team, half_weeks, weekly_player, "half", "_games", "_active_games", "_ppg"
    )

    out = base.merge(player_team, on=["season", "player_id"], how="left")
    out["team_game_window_applicable"] = out["team"].notna()

    for half, prefix in (("first_half", "first_half"), ("second_half", "second_half")):
        half_agg = agg[agg["half"] == half].drop(columns=["half"]).rename(
            columns={"_games": f"{prefix}_team_games", "_active_games": f"{prefix}_active_games", "_ppg": f"{prefix}_ppg"}
        )
        out = out.merge(half_agg, on=["season", "player_id"], how="left")
        (
            out[f"{prefix}_ppg"],
            out[f"{prefix}_sample_qualified_primary"],
            out[f"{prefix}_sample_qualified_sensitivity"],
        ) = _apply_floor(out[f"{prefix}_active_games"], out[f"{prefix}_ppg"])

    out["opportunity_qualified"] = OPPORTUNITY_STATUS_PENDING

    return out[list(TEAM_GAME_HALF_SPLIT_OUTPUT_COLUMNS)].reset_index(drop=True)
