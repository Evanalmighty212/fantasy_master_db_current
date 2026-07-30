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

TEAM-GAME WINDOWS ARE RESTRICTED TO SINGLE-TEAM PLAYERS, WITH AN
EXPLICIT STATUS FIELD, NOT A BARE BOOLEAN (revised 2026-07 per the
reliability proposal's exclusion audit -- see
research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md).
Every row gets `team_game_window_status`, one of:
- `TEAM_GAME_STATUS_APPLICABLE`: a single real team was identified and
  that team's real games were found -- `team_final_n_games` (or
  `first_half_team_games`/`second_half_team_games`) is populated,
  ALWAYS equal to the real window size. `team_final_n_active_games`
  can legitimately be 0 here -- that is a REAL, MEANINGFUL "rostered
  but had zero real usage across the window" fact, not missing data,
  and stays fully represented (zero-filled PPG/opportunity), never
  dropped from the population.
- `TEAM_GAME_STATUS_UNAVAILABLE_TRADED`: 2+ distinct real teams in
  `weekly_player` this season -- "the team's final N games" is
  genuinely ambiguous for a player who changed teams mid-season. That
  real comparison belongs to the separate trade-split analysis (see
  the reliability proposal doc's §4), not this module. Traded players
  ARE still fully available to `build_active_game_final_n_traits()`
  (which never filters by team) and to a dedicated trade-split
  analysis -- this status is scoped to TEAM-GAME windows specifically,
  not a claim the player is unanalyzable everywhere.
- `TEAM_GAME_STATUS_UNAVAILABLE_NO_TEAM_EVIDENCE`: zero real rows in
  `weekly_player` this season at all (never appeared in Source A's
  weekly file -- practice squad, unrostered, etc.) -- no team can be
  identified, so no team-game window can be looked up.
- `TEAM_GAME_STATUS_UNAVAILABLE_OTHER`: a defensive, disclosed
  catch-all -- a single real team WAS identified from `weekly_player`,
  but that team has no real games in `weekly_all_positions`'s
  `build_team_game_index()` output for this season (a real data
  inconsistency between the two inputs, or a genuine edge case, not
  silently treated as "applicable" with a null result).
Every trait field is null for every non-applicable status -- never
guessed or defaulted.

MINIMUM-SAMPLE FLOOR, real but DIFFERENT MEANING per window type:
- Team-game windows: `team_final_n_games`/`first_half_team_games`/
  `second_half_team_games` is ALWAYS exactly the window size by
  construction (a team-game window always contains exactly N of the
  team's real games). The real sample-size question here is instead
  "how many of those N real team games did the player actually have
  real usage in" -- `team_final_n_active_games` -- which is what the
  PRIMARY (>=3)/SENSITIVITY (>=4) floor is checked against (see
  config.py's DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY/SENSITIVITY).
- Active-game windows: `active_final_n_games` can be less than N (a
  player with only 2 real games all season can't produce a 4-game
  active window) -- the floor is checked against this count directly,
  same convention as the module's original design.

TWO DELIBERATELY SEPARATE RATES PER TEAM-GAME WINDOW, NEVER ONE
AMBIGUOUS "PPG" FIELD (added 2026-07 per the reliability proposal --
see research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md).
A single "PPG" field would conflate two real, different questions:
- `*_points_per_team_game` (e.g. `team_final_n_points_per_team_game`,
  `first_half_points_per_team_game`): real total points divided by the
  FIXED team-window size (`team_final_n_games`/`first_half_team_games`
  -- always the real window size, e.g. always 4 for a final-4 window,
  never the active-game count). ALWAYS DEFINED for any `applicable`
  row, INCLUDING 0.0 for a player with zero real usage across the
  entire window -- a real, meaningful "produced nothing across the
  team's real final N games" fact, not a missing value. NEVER
  floor-gated -- per the approved methodology, a raw per-team-game
  rate is availability/production information, not something that
  becomes "unreliable" just because the player didn't play much of the
  window; nulling it would hide the exact zero-role signal this field
  exists to preserve.
- `*_points_per_active_game` (e.g. `team_final_n_points_per_active_game`,
  `first_half_points_per_active_game`): real total points divided by
  the real ACTIVE-game count (`team_final_n_active_games`/
  `first_half_active_games`). Null whenever active games is 0 (no real
  games to average over) and floor-gated below the sensitivity floor,
  same convention as every other Dataset 2 active-game-based rate --
  this is the "how well did they play when they actually played" rate,
  and IS subject to the interpretability floor because dividing by a
  near-zero real sample is what's actually unstable.
Applied consistently to every team-game window this module builds:
final-4/6/8 (`build_team_game_final_n_traits()`) and first/second half
(`build_team_game_half_split_traits()`). ACTIVE-GAME windows
(`build_active_game_final_n_traits()`) keep a single PPG field --
there is no separate "team window size" concept there, the window IS
the active-game set by definition, so no ambiguity exists to resolve.

MEANINGFUL-ROLE OPPORTUNITY IS DELIBERATELY NOT IMPLEMENTED HERE YET.
`opportunity_qualified` is present in every PPG-style output row but
is ALWAYS the literal string OPPORTUNITY_STATUS_PENDING -- never
True/False, never silently defaulted to "qualified." See the
reliability proposal doc for the proposed continuous per-game/
snap-share meaningful-role measures; no threshold has been selected
or implemented as a flag.

EFFICIENCY SAMPLE-ELIGIBILITY -- approved and implemented 2026-07,
a DIFFERENT, narrower concept from meaningful-role opportunity above
(research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md §2d).
`build_team_game_efficiency_traits()`/`build_active_game_efficiency_traits()`
compute a real efficiency RATE (production ÷ opportunity, e.g. real
yards per real target) for one (position, metric_name) pair at a time
-- see `EFFICIENCY_METRICS` for the supported set and the real
(numerator, denominator) column each resolves to. Every row keeps its
real, zero-filled opportunity/production counts regardless of
eligibility (§2c's "minimal computability": the rate itself is null
ONLY when opportunity is literally 0, never gated by a volume
threshold). Two SEPARATE eligibility flags
(`*_efficiency_volume_eligible_exploratory`/`_sensitivity`, real
volumes from config.py's DATASET2_EFFICIENCY_VOLUME_EXPLORATORY/
SENSITIVITY) mark whether the real opportunity count clears an
approved minimum -- derived from real ODD/EVEN-WEEK split OBSERVED
HISTORICAL STABILITY (deliberately not called a formal statistical-
reliability estimate, since the real split also captures real role,
injury, QB, and opponent change across a season, not pure measurement
noise). NEITHER FLAG IS A CLAIM THE RATE IS RELIABLE -- real split-half
correlation for these football rate metrics stays modest even at the
SENSITIVITY volume; the flags mark where the observed rate stops being
dominated by a handful of plays, nothing stronger.

TEST SCOPE: tests/test_dataset2_partial_season_traits.py proves
implementation correctness (team-game vs. active-game window
construction, real 16/17-game-era boundary handling, inactive-game
zero-filling, traded-player exclusion, floor enforcement, efficiency
sample-eligibility) against
synthetic fixtures. tests/test_dataset2_common.py separately proves
`real_reg_week_slots()`/`build_team_game_index()` correctness, which
this module now relies on rather than re-deriving.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    DATASET2_EFFICIENCY_VOLUME_EXPLORATORY,
    DATASET2_EFFICIENCY_VOLUME_SENSITIVITY,
    DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY,
    DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_SENSITIVITY,
)
from lib.dataset2.common import build_team_game_index, validate_columns

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position")
WEEKLY_PLAYER_BASE_COLUMNS = ("season", "player_id", "week", "team")
WEEKLY_PLAYER_REQUIRED_COLUMNS = WEEKLY_PLAYER_BASE_COLUMNS + ("fantasy_points_ppr",)

# (position, metric_name) -> (numerator_col, denominator_col) in the
# real Source A weekly file. metric_name distinguishes RB's two real
# efficiency questions (rushing vs. receiving), which need different
# real columns. Matches config.py's DATASET2_EFFICIENCY_VOLUME_*
# dicts exactly (same keys) -- see that config for the real
# split-half-derived volume levels per pair.
EFFICIENCY_METRICS = {
    ("QB", "passing"): ("passing_epa", "attempts"),
    ("RB", "rushing"): ("rushing_yards", "carries"),
    ("RB", "receiving"): ("receiving_yards", "targets"),
    ("WR", "receiving"): ("receiving_yards", "targets"),
    ("TE", "receiving"): ("receiving_yards", "targets"),
}

OPPORTUNITY_STATUS_PENDING = "pending"

TEAM_GAME_STATUS_APPLICABLE = "applicable"
TEAM_GAME_STATUS_UNAVAILABLE_TRADED = "unavailable_traded"
TEAM_GAME_STATUS_UNAVAILABLE_NO_TEAM_EVIDENCE = "unavailable_no_team_evidence"
TEAM_GAME_STATUS_UNAVAILABLE_OTHER = "unavailable_other"

TEAM_GAME_FINAL_N_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "window_n",
    "team_game_window_status",
    "team_final_n_games",
    "team_final_n_active_games",
    "team_final_n_points_per_team_game",
    "team_final_n_points_per_active_game",
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
    "team_game_window_status",
    "first_half_team_games",
    "first_half_active_games",
    "first_half_points_per_team_game",
    "first_half_points_per_active_game",
    "first_half_sample_qualified_primary",
    "first_half_sample_qualified_sensitivity",
    "second_half_team_games",
    "second_half_active_games",
    "second_half_points_per_team_game",
    "second_half_points_per_active_game",
    "second_half_sample_qualified_primary",
    "second_half_sample_qualified_sensitivity",
    "opportunity_qualified",
)

EFFICIENCY_TEAM_GAME_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "metric_name",
    "window_n",
    "team_game_window_status",
    "team_final_n_games",
    "team_final_n_active_games",
    "team_final_n_opportunity",
    "team_final_n_production",
    "team_final_n_efficiency_rate",
    "team_final_n_efficiency_volume_eligible_exploratory",
    "team_final_n_efficiency_volume_eligible_sensitivity",
)

EFFICIENCY_ACTIVE_GAME_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "metric_name",
    "window_n",
    "active_final_n_games",
    "active_final_n_opportunity",
    "active_final_n_production",
    "active_final_n_efficiency_rate",
    "active_final_n_efficiency_volume_eligible_exploratory",
    "active_final_n_efficiency_volume_eligible_sensitivity",
)


def _apply_floor(active_games: pd.Series, rate: pd.Series):
    """Returns (rate_with_floor_enforced, qualified_primary, qualified_sensitivity).
    `rate` is set to NaN wherever active_games < PRIMARY floor (3) -- a
    <3-real-active-game sample is never interpretable, structurally,
    not just by convention. `qualified_sensitivity` (active_games >= 4)
    is a STRICTER, separately-exposed comparison flag on top of an
    already-shown rate -- never a second nulling gate (see
    config.py's DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY/SENSITIVITY,
    whose names are self-evident about which is the lower,
    interpretability-gating value and which is the stricter comparison
    -- no swapped-meaning history to know about). `active_games` is the
    count of games with REAL usage -- for a team-game window this is
    `*_active_games`, NOT the (always-full) window size. Used ONLY for
    a per-ACTIVE-game rate -- see `_compute_dual_rates()`, never
    applied to a per-team-game rate, which is deliberately never
    floor-gated."""
    qualified_primary = active_games >= DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY
    qualified_sensitivity = active_games >= DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_SENSITIVITY
    rate_enforced = np.where(qualified_primary, rate, np.nan)
    return rate_enforced, qualified_primary, qualified_sensitivity


def _compute_dual_rates(total: pd.Series, team_games: pd.Series, active_games: pd.Series):
    """From a real, zero-filled point total and the two real
    denominators, returns (points_per_team_game, points_per_active_game,
    qualified_primary, qualified_sensitivity) -- see the module
    docstring's "TWO DELIBERATELY SEPARATE RATES" section for exactly
    what each means and why neither substitutes for the other.
    `points_per_team_game` is NEVER floor-gated (0.0 for a real,
    fully-inactive applicable window, not null); `points_per_active_game`
    IS floor-gated via `_apply_floor()` and is null when active_games
    is 0."""
    points_per_team_game = total / team_games
    points_per_active_game_raw = total / active_games.replace(0, np.nan)
    points_per_active_game, qualified_primary, qualified_sensitivity = _apply_floor(
        active_games, points_per_active_game_raw
    )
    return points_per_team_game, points_per_active_game, qualified_primary, qualified_sensitivity


def _player_team_status(population: pd.DataFrame, weekly_player: pd.DataFrame) -> pd.DataFrame:
    """Every (season, player_id) in `population` -> (team,
    team_game_window_status). `team` is set only when status is
    APPLICABLE (exactly one real team found in `weekly_player`); null
    for TRADED (2+ distinct real teams) and NO_TEAM_EVIDENCE (zero real
    rows this season) -- see the module docstring's status field
    section for what each value means. Never guesses a team, never
    drops a population row."""
    counts = weekly_player.groupby(["season", "player_id"])["team"].nunique().rename("n_teams")
    first_team = weekly_player.groupby(["season", "player_id"])["team"].first().rename("team")
    joined = pd.concat([counts, first_team], axis=1).reset_index()

    base_keys = population[["season", "player_id"]].drop_duplicates()
    out = base_keys.merge(joined, on=["season", "player_id"], how="left")
    out["n_teams"] = out["n_teams"].fillna(0).astype(int)

    out["team_game_window_status"] = np.select(
        [out["n_teams"] == 0, out["n_teams"] == 1, out["n_teams"] >= 2],
        [
            TEAM_GAME_STATUS_UNAVAILABLE_NO_TEAM_EVIDENCE,
            TEAM_GAME_STATUS_APPLICABLE,
            TEAM_GAME_STATUS_UNAVAILABLE_TRADED,
        ],
        default="",
    )
    out.loc[out["n_teams"] != 1, "team"] = None
    return out[["season", "player_id", "team", "team_game_window_status"]]


def _scope_to_team_games(
    population: pd.DataFrame, weekly_player: pd.DataFrame, weekly_all_positions: pd.DataFrame
):
    """Shared setup for every team-game-window builder: `base`
    (population scope), `player_team` (every population row's team +
    team_game_window_status), and `team_game_index` (every real team's
    real REG games, chronologically indexed, bye-gap-compressed -- see
    common.build_team_game_index()). Validates only the BASE identity
    columns (season/player_id/week/team) -- callers validate whatever
    additional value column(s) they specifically need (PPG builders:
    `fantasy_points_ppr`; efficiency builders: the resolved
    numerator/denominator columns for that metric), since different
    builders need different real Source A columns."""
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(weekly_player, WEEKLY_PLAYER_BASE_COLUMNS, "weekly_player")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(subset=["season", "player_id"]).reset_index(
        drop=True
    )
    player_team = _player_team_status(base, weekly_player)
    team_game_index = build_team_game_index(weekly_all_positions)
    return base, player_team, team_game_index


def _downgrade_unmatched_applicable(out: pd.DataFrame, matched_games_col: str) -> pd.Series:
    """A row marked APPLICABLE (single real team found) but with no
    real games found for that team in `team_game_index` is a genuine
    "other causes" case (module docstring's `TEAM_GAME_STATUS_UNAVAILABLE_OTHER`)
    -- reclassified here rather than silently left as "applicable" with
    a null result."""
    return np.where(
        (out["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE) & out[matched_games_col].isna(),
        TEAM_GAME_STATUS_UNAVAILABLE_OTHER,
        out["team_game_window_status"],
    )


def _aggregate_team_window(
    player_team: pd.DataFrame,
    window_weeks: pd.DataFrame,
    weekly_player: pd.DataFrame,
    games_col: str,
    active_col: str,
    value_cols: dict,
):
    """`window_weeks`: (season, team, week[, half]) -- the specific
    real team-games in scope. Joins each single-team player to their
    team's real games in the window, zero-fills any game with no real
    player row (inactive/no usage -- never dropped), and aggregates.
    `value_cols`: {real source column in `weekly_player`: output total
    column name} -- EVERY entry is summed with the same zero-fill
    treatment (one column for a PPG builder: `{"fantasy_points_ppr":
    "..."}`; two for an efficiency builder, numerator AND denominator:
    `{"receiving_yards": "...", "targets": "..."}`). Returns a
    DataFrame keyed on (season, player_id[, half]) with `games_col`
    (real window size), `active_col` (real active-game count), and one
    output column per `value_cols` entry -- NO rate is computed here.
    Callers compute their own rate on top of these raw fields so a
    per-team-game rate and a per-active-game (or efficiency) rate stay
    deliberately separate computations, never derived from each
    other."""
    group_keys = ["season", "player_id"] + (["half"] if "half" in window_weeks.columns else [])

    scoped = player_team.merge(window_weeks, on=["season", "team"], how="inner")
    merged = scoped.merge(
        weekly_player[["season", "player_id", "week"] + list(value_cols.keys())],
        on=["season", "player_id", "week"],
        how="left",
        indicator=True,
    )
    merged["_active"] = merged["_merge"] == "both"
    for src_col in value_cols:
        merged[src_col] = merged[src_col].fillna(0.0)

    agg_kwargs = {games_col: ("week", "nunique"), active_col: ("_active", "sum")}
    for src_col, out_col in value_cols.items():
        agg_kwargs[out_col] = (src_col, "sum")

    return merged.groupby(group_keys).agg(**agg_kwargs).reset_index()


def build_team_game_final_n_traits(
    population: pd.DataFrame, weekly_player: pd.DataFrame, weekly_all_positions: pd.DataFrame, n: int
) -> pd.DataFrame:
    """PRIMARY late-season trait: the player's own (single) team's real
    final `n` REG games, zero-filling any game the player didn't record
    real usage in (inactive, healthy scratch, etc. -- cause not
    distinguished, only the real fact of zero usage that game -- a real
    `team_final_n_active_games == 0` is a meaningful "rostered, zero
    role" finding, kept fully represented, not dropped). Non-applicable
    rows (traded, no real team evidence, or the defensive "other"
    catch-all) get every trait field null -- see module docstring's
    `team_game_window_status` section for exactly what each value
    means."""
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    validate_columns(weekly_player, WEEKLY_PLAYER_REQUIRED_COLUMNS, "weekly_player")
    base, player_team, team_game_index = _scope_to_team_games(population, weekly_player, weekly_all_positions)

    tgi = team_game_index.copy()
    tgi["_games_from_end"] = tgi["team_total_games"] - tgi["team_game_index"]
    final_n_weeks = tgi[tgi["_games_from_end"] < n][["season", "team", "week"]]

    agg = _aggregate_team_window(
        player_team,
        final_n_weeks,
        weekly_player,
        "team_final_n_games",
        "team_final_n_active_games",
        {"fantasy_points_ppr": "_team_final_n_total"},
    )

    out = base.merge(player_team, on=["season", "player_id"], how="left")
    out = out.merge(agg, on=["season", "player_id"], how="left")
    out["team_game_window_status"] = _downgrade_unmatched_applicable(out, "team_final_n_games")

    (
        out["team_final_n_points_per_team_game"],
        out["team_final_n_points_per_active_game"],
        out["team_final_n_sample_qualified_primary"],
        out["team_final_n_sample_qualified_sensitivity"],
    ) = _compute_dual_rates(out["_team_final_n_total"], out["team_final_n_games"], out["team_final_n_active_games"])

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
    same as build_team_game_final_n_traits(). Non-applicable rows
    (traded, no real team evidence, or the defensive "other" catch-all)
    get `team_game_window_status` set accordingly and every trait field
    null -- see module docstring."""
    validate_columns(weekly_player, WEEKLY_PLAYER_REQUIRED_COLUMNS, "weekly_player")
    base, player_team, team_game_index = _scope_to_team_games(population, weekly_player, weekly_all_positions)

    tgi = team_game_index.copy()
    tgi["_cutoff"] = np.ceil(tgi["team_total_games"] / 2)
    tgi["half"] = np.where(tgi["team_game_index"] <= tgi["_cutoff"], "first_half", "second_half")
    half_weeks = tgi[["season", "team", "week", "half"]]

    agg = _aggregate_team_window(
        player_team, half_weeks, weekly_player, "_games", "_active_games", {"fantasy_points_ppr": "_total"}
    )

    matched_players = agg[["season", "player_id"]].drop_duplicates()
    matched_players["_matched"] = 1.0

    out = base.merge(player_team, on=["season", "player_id"], how="left")
    out = out.merge(matched_players, on=["season", "player_id"], how="left")
    out["team_game_window_status"] = _downgrade_unmatched_applicable(out, "_matched")
    out = out.drop(columns=["_matched"])

    for half, prefix in (("first_half", "first_half"), ("second_half", "second_half")):
        half_agg = agg[agg["half"] == half].drop(columns=["half"]).rename(
            columns={"_games": f"{prefix}_team_games", "_active_games": f"{prefix}_active_games", "_total": f"{prefix}_total"}
        )
        out = out.merge(half_agg, on=["season", "player_id"], how="left")
        (
            out[f"{prefix}_points_per_team_game"],
            out[f"{prefix}_points_per_active_game"],
            out[f"{prefix}_sample_qualified_primary"],
            out[f"{prefix}_sample_qualified_sensitivity"],
        ) = _compute_dual_rates(out[f"{prefix}_total"], out[f"{prefix}_team_games"], out[f"{prefix}_active_games"])
        out = out.drop(columns=[f"{prefix}_total"])

    out["opportunity_qualified"] = OPPORTUNITY_STATUS_PENDING

    return out[list(TEAM_GAME_HALF_SPLIT_OUTPUT_COLUMNS)].reset_index(drop=True)


def _resolve_efficiency_metric(position: str, metric_name: str):
    key = (position, metric_name)
    if key not in EFFICIENCY_METRICS:
        raise ValueError(
            f"No efficiency metric defined for (position, metric_name)={key!r}; "
            f"see EFFICIENCY_METRICS for the supported set."
        )
    numerator_col, denominator_col = EFFICIENCY_METRICS[key]
    exploratory_min = DATASET2_EFFICIENCY_VOLUME_EXPLORATORY[key]
    sensitivity_min = DATASET2_EFFICIENCY_VOLUME_SENSITIVITY[key]
    return numerator_col, denominator_col, exploratory_min, sensitivity_min


def build_team_game_efficiency_traits(
    population: pd.DataFrame,
    weekly_player: pd.DataFrame,
    weekly_all_positions: pd.DataFrame,
    n: int,
    position: str,
    metric_name: str,
) -> pd.DataFrame:
    """Real per-team-game-window efficiency (e.g. yards per target),
    for the team's real final `n` REG games -- same team-game
    window/status machinery as build_team_game_final_n_traits(), with
    an EFFICIENCY rate in place of a points rate.

    SAMPLE-ELIGIBILITY, NOT A RELIABILITY PROOF (see module docstring's
    "EFFICIENCY SAMPLE-ELIGIBILITY" section and
    config.py's DATASET2_EFFICIENCY_VOLUME_EXPLORATORY/SENSITIVITY):
    `*_efficiency_volume_eligible_exploratory`/`*_sensitivity` flag
    whether the real window OPPORTUNITY count (the metric's real
    denominator, e.g. targets) clears the approved volume level --
    they do NOT claim the resulting rate is statistically reliable,
    only that it clears a real, disclosed minimum before being read as
    even an exploratory signal.

    MINIMAL COMPUTABILITY, ALWAYS PRESERVED: `team_final_n_opportunity`/
    `team_final_n_production` (the real, zero-filled denominator/
    numerator sums) are populated for every `applicable` row regardless
    of either eligibility flag -- only `team_final_n_efficiency_rate`
    itself is null, and only when the real opportunity count is
    literally zero (division undefined), never gated by a volume
    threshold. A player below both eligibility flags still gets a real
    rate here if their opportunity is nonzero; the flags describe how
    much to trust it, they don't hide it.
    """
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")
    numerator_col, denominator_col, exploratory_min, sensitivity_min = _resolve_efficiency_metric(
        position, metric_name
    )

    validate_columns(
        weekly_player, WEEKLY_PLAYER_BASE_COLUMNS + (numerator_col, denominator_col), "weekly_player"
    )
    position_population = population[population["position"] == position]
    base, player_team, team_game_index = _scope_to_team_games(position_population, weekly_player, weekly_all_positions)

    tgi = team_game_index.copy()
    tgi["_games_from_end"] = tgi["team_total_games"] - tgi["team_game_index"]
    final_n_weeks = tgi[tgi["_games_from_end"] < n][["season", "team", "week"]]

    agg = _aggregate_team_window(
        player_team,
        final_n_weeks,
        weekly_player,
        "team_final_n_games",
        "team_final_n_active_games",
        {denominator_col: "team_final_n_opportunity", numerator_col: "team_final_n_production"},
    )

    out = base.merge(player_team, on=["season", "player_id"], how="left")
    out = out.merge(agg, on=["season", "player_id"], how="left")
    out["team_game_window_status"] = _downgrade_unmatched_applicable(out, "team_final_n_games")

    out["team_final_n_efficiency_rate"] = out["team_final_n_production"] / out["team_final_n_opportunity"].replace(
        0, np.nan
    )
    out["team_final_n_efficiency_volume_eligible_exploratory"] = out["team_final_n_opportunity"] >= exploratory_min
    out["team_final_n_efficiency_volume_eligible_sensitivity"] = out["team_final_n_opportunity"] >= sensitivity_min

    out["position"] = position
    out["metric_name"] = metric_name
    out["window_n"] = n

    return out[list(EFFICIENCY_TEAM_GAME_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_active_game_efficiency_traits(
    population: pd.DataFrame, weekly_player: pd.DataFrame, n: int, position: str, metric_name: str
) -> pd.DataFrame:
    """Real per-active-game-window efficiency, over the player's own
    real final `n` games WITH a real weekly row (same active-game
    selection as build_active_game_final_n_traits() -- a real row
    counts as "active" even if that specific week's opportunity in
    THIS metric happens to be 0, consistent with every other
    active-game window in this module). See
    build_team_game_efficiency_traits()'s docstring for what the
    eligibility flags do and don't claim -- identical semantics here.
    """
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")
    numerator_col, denominator_col, exploratory_min, sensitivity_min = _resolve_efficiency_metric(
        position, metric_name
    )

    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(
        weekly_player, WEEKLY_PLAYER_BASE_COLUMNS + (numerator_col, denominator_col), "weekly_player"
    )

    position_population = population[population["position"] == position]
    base = position_population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(
        subset=["season", "player_id"]
    ).reset_index(drop=True)

    w = weekly_player.sort_values(["season", "player_id", "week"])
    w = w.assign(_rank_from_end=w.groupby(["season", "player_id"]).cumcount(ascending=False))
    in_window = w[w["_rank_from_end"] < n]

    agg = (
        in_window.groupby(["season", "player_id"])
        .agg(
            active_final_n_games=("week", "count"),
            active_final_n_opportunity=(denominator_col, "sum"),
            active_final_n_production=(numerator_col, "sum"),
        )
        .reset_index()
    )

    out = base.merge(agg, on=["season", "player_id"], how="left")
    out["active_final_n_games"] = out["active_final_n_games"].fillna(0).astype(int)
    out["active_final_n_opportunity"] = out["active_final_n_opportunity"].fillna(0.0)
    out["active_final_n_production"] = out["active_final_n_production"].fillna(0.0)

    out["active_final_n_efficiency_rate"] = out["active_final_n_production"] / out[
        "active_final_n_opportunity"
    ].replace(0, np.nan)
    out["active_final_n_efficiency_volume_eligible_exploratory"] = (
        out["active_final_n_opportunity"] >= exploratory_min
    )
    out["active_final_n_efficiency_volume_eligible_sensitivity"] = (
        out["active_final_n_opportunity"] >= sensitivity_min
    )

    out["position"] = position
    out["metric_name"] = metric_name
    out["window_n"] = n

    return out[list(EFFICIENCY_ACTIVE_GAME_OUTPUT_COLUMNS)].reset_index(drop=True)
