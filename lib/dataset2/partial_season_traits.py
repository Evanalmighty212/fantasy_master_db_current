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

MEANINGFUL-ROLE CLASSIFICATION -- approved and implemented 2026-07
(research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md §2e),
a DIFFERENT, further concept from efficiency sample-eligibility above:
efficiency asks "is there enough real volume to trust a RATE (yards
per target)"; role classification asks "is there enough real
OPPORTUNITY (targets/carries/attempts/snap share themselves) to call
this a meaningful fantasy role at all." Three ordered tiers --
`role_present` (recurring but potentially peripheral involvement),
`meaningful_role` (enough opportunity to plausibly matter for fantasy
production), `strong_lead_role` (starter-level or high-value
involvement) -- computed from a real, continuous per-game (or
snap-share) rate against `config.py`'s
`DATASET2_ROLE_THRESHOLDS_TEAM_GAME`/`_ACTIVE_GAME`/`_SNAP_SHARE`.
PREDEFINED DATASET 2 RESEARCH CLASSIFICATIONS, NOT A CLAIM THAT REAL
FOOTBALL OPPORTUNITY CHANGES DISCONTINUOUSLY AT THE EXACT CUTOFF -- a
player at 1.9 carries/team-game is not meaningfully different from one
at 2.0; the tiers exist to make cross-player/cross-season comparison
tractable, not to assert a bright structural line. Downstream analysis
should read the underlying continuous rate ALONGSIDE the tier flags
and consider sensitivity to the exact cutoff, not treat a tier flip as
itself the finding.

Built by `build_team_game_role_traits()`/`build_active_game_role_traits()`
(QB attempts, RB carries, RB/WR/TE targets) and
`build_team_game_snap_share_role_traits()` (position-specific
`offense_snap_share`, team-game basis only, Source B 2013+ coverage).
Same "raw counts always visible, only the derived field is ever
gated" discipline as every other trait in this module: the real
opportunity count and the per-game (or share) rate are ALWAYS present
for an applicable, covered row -- the three tier flags are additional,
non-destructive classifications layered on top, never a filter, and
NEVER silently combined into one another or into a single overall
"meaningful role" label across metrics. A player's snap-share role,
rushing role, and receiving role are reported completely independently
-- a strong snap-share role with a weak receiving role, or a strong
active-game role with a weak team-game role (a fragile or
recently-promoted player), is exactly the kind of finding this
independence is designed to surface, not average away. Any future
COMPOSITE concept (e.g. a "three-down RB" label combining rushing +
receiving + snap-share roles) is a deliberate, separate interaction
hypothesis to test on its own merits later -- never an automatic
consequence of building these three tiers.

TEAM-GAME vs. ACTIVE-GAME role classifications are DELIBERATELY
SEPARATE, per the same rationale as the dual-rate PPG split above:
per-team-game reflects sustained opportunity PLUS availability (a
committee back or an injury-interrupted stretch reads lower here even
in a real starter's season, since the denominator is the fixed real
window size, never floor-gated -- 0.0 for a genuinely zero-opportunity
applicable window, not null); per-active-game reflects opportunity
ONLY across the games the player was actually on the field for (0.0
when active games had real zero opportunity that metric, null only
when the player has zero real active games at all). Neither overrides
the other -- a player can be `strong_lead_role` on the active-game
basis while failing `role_present` on the team-game basis, which
plausibly identifies a high-upside player who is fragile or was
recently promoted into the role; that divergence is preserved and
readable, never resolved in either direction.

FOR WR SPECIFICALLY: `offense_snap_share` establishes real
PARTICIPATION but does NOT necessarily identify receiving HIERARCHY --
a WR can play a real strong-lead share of a team's offensive snaps
while a teammate absorbs the real target volume (blocking-heavy,
decoy, or possession-role usage). The real composition evidence
behind this (WR strong/lead-tier ADP composition spreads more evenly
across the snap-share candidates than RB's does under the same tiers)
is in the proposal doc §2e. Snap share and the separate WR
receiving-role targets thresholds must be read together, never as
substitutes for one another.

TEST SCOPE: tests/test_dataset2_partial_season_traits.py proves
implementation correctness (team-game vs. active-game window
construction, real 16/17-game-era boundary handling, inactive-game
zero-filling, traded-player exclusion, floor enforcement, efficiency
sample-eligibility, meaningful-role classification) against
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
    DATASET2_ROLE_THRESHOLDS_ACTIVE_GAME,
    DATASET2_ROLE_THRESHOLDS_SNAP_SHARE,
    DATASET2_ROLE_THRESHOLDS_TEAM_GAME,
)
from lib.dataset2.common import build_team_game_index, validate_columns

POPULATION_REQUIRED_COLUMNS = ("season", "player_id", "position")
WEEKLY_PLAYER_BASE_COLUMNS = ("season", "player_id", "week", "team")
WEEKLY_PLAYER_REQUIRED_COLUMNS = WEEKLY_PLAYER_BASE_COLUMNS + ("fantasy_points_ppr",)

# Expected shape of Source B's snap-count input to the snap-share role
# builder: the CALLER is responsible for pre-filtering to matched rows
# (real gsis_id) and renaming gsis_id -> player_id -- the EXACT same
# preprocessing lib/dataset2/snap_traits.py's build_season_snap_usage()
# does internally, for consistency with that real-audit-validated
# max-based offense_pct reconstruction.
SNAP_ROLE_REQUIRED_COLUMNS = ("season", "week", "team", "player_id", "offense_snaps")

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

ROLE_TEAM_GAME_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "metric_name",
    "window_n",
    "team_game_window_status",
    "team_final_n_games",
    "team_final_n_active_games",
    "team_final_n_opportunity",
    "team_final_n_opportunity_per_team_game",
    "team_final_n_role_present",
    "team_final_n_meaningful_role",
    "team_final_n_strong_lead_role",
)

ROLE_ACTIVE_GAME_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "metric_name",
    "window_n",
    "active_final_n_games",
    "active_final_n_opportunity",
    "active_final_n_opportunity_per_active_game",
    "active_final_n_role_present",
    "active_final_n_meaningful_role",
    "active_final_n_strong_lead_role",
)

SNAP_SHARE_ROLE_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "window_n",
    "team_game_window_status",
    "team_final_n_games",
    "team_final_n_active_games",
    "team_final_n_offense_snaps",
    "team_final_n_team_offense_total",
    "team_final_n_has_snap_coverage",
    "team_final_n_offense_snap_share",
    "team_final_n_role_present",
    "team_final_n_meaningful_role",
    "team_final_n_strong_lead_role",
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


def _volume_eligible_flag(opportunity: pd.Series, min_value: float) -> pd.Series:
    """`opportunity >= min_value`, nullable-boolean-safe -- returns
    real `True`/`False` only where `opportunity` itself is real and
    known, `pd.NA` wherever `opportunity` is null. Deliberately NOT a
    plain `opportunity >= min_value` comparison, which silently turns
    a real null opportunity into `False` (the same real numpy/pandas
    comparison quirk `_role_tier_flags()` above already guards
    against -- extracted here 2026-07 during the Source A
    targets/receiving_air_yards coverage remediation so
    `*_efficiency_volume_eligible_exploratory`/`_sensitivity` get the
    identical protection, never a second, less-safe implementation)."""
    flag = pd.Series(pd.NA, index=opportunity.index, dtype="boolean")
    known = opportunity.notna()
    flag.loc[known] = opportunity.loc[known] >= min_value
    return flag


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
    out["team_final_n_efficiency_volume_eligible_exploratory"] = _volume_eligible_flag(
        out["team_final_n_opportunity"], exploratory_min
    )
    out["team_final_n_efficiency_volume_eligible_sensitivity"] = _volume_eligible_flag(
        out["team_final_n_opportunity"], sensitivity_min
    )

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
    out["active_final_n_efficiency_volume_eligible_exploratory"] = _volume_eligible_flag(
        out["active_final_n_opportunity"], exploratory_min
    )
    out["active_final_n_efficiency_volume_eligible_sensitivity"] = _volume_eligible_flag(
        out["active_final_n_opportunity"], sensitivity_min
    )

    out["position"] = position
    out["metric_name"] = metric_name
    out["window_n"] = n

    return out[list(EFFICIENCY_ACTIVE_GAME_OUTPUT_COLUMNS)].reset_index(drop=True)


def _role_tier_flags(rate: pd.Series, thresholds: tuple):
    """From a real, continuous per-game (or share) `rate` and a
    (role_present, meaningful_role, strong_lead_role) threshold tuple,
    returns three pandas NULLABLE-boolean Series -- True/False only
    where `rate` itself is real and known, `pd.NA` wherever `rate` is
    null. Deliberately NOT computed via a plain `rate >= threshold`
    comparison on a float Series, which would silently turn a real
    NaN into False (numpy/pandas comparison quirk) -- exactly the kind
    of guessed/defaulted value the module docstring's "every trait
    field is null for every non-applicable status" rule forbids.
    Thresholds increase strictly tier to tier (checked at test time,
    not here), so a real strong_lead_role=True row is always also
    meaningful_role=True and role_present=True."""
    role_present_min, meaningful_min, strong_lead_min = thresholds
    known = rate.notna()

    def _flag(min_value):
        flag = pd.Series(pd.NA, index=rate.index, dtype="boolean")
        flag.loc[known] = rate.loc[known] >= min_value
        return flag

    return _flag(role_present_min), _flag(meaningful_min), _flag(strong_lead_min)


def _resolve_role_metric(position: str, metric_name: str, thresholds_by_key: dict):
    """Real opportunity column (reused from EFFICIENCY_METRICS's own
    (numerator, denominator) mapping -- role classification only ever
    needs the denominator/opportunity side, never the numerator) plus
    the real (role_present, meaningful_role, strong_lead_role)
    threshold tuple for this (position, metric_name) on the caller's
    chosen basis (`thresholds_by_key` is one of
    DATASET2_ROLE_THRESHOLDS_TEAM_GAME/_ACTIVE_GAME). Raises loudly for
    an unsupported pair rather than silently returning an empty
    result -- e.g. QB has no team-game entry by design (see module
    docstring), so requesting it here is a real caller error, not a
    legitimate empty case."""
    key = (position, metric_name)
    if key not in EFFICIENCY_METRICS:
        raise ValueError(
            f"No opportunity column defined for (position, metric_name)={key!r}; "
            f"see EFFICIENCY_METRICS for the supported set."
        )
    if key not in thresholds_by_key:
        raise ValueError(
            f"No role-tier thresholds defined for (position, metric_name)={key!r} on this "
            f"basis; see config.py's DATASET2_ROLE_THRESHOLDS_TEAM_GAME/_ACTIVE_GAME for the "
            f"supported set (QB has no team-game entry by design -- see module docstring)."
        )
    _, opportunity_col = EFFICIENCY_METRICS[key]
    return opportunity_col, thresholds_by_key[key]


def build_team_game_role_traits(
    population: pd.DataFrame,
    weekly_player: pd.DataFrame,
    weekly_all_positions: pd.DataFrame,
    n: int,
    position: str,
    metric_name: str,
) -> pd.DataFrame:
    """Real per-team-game-window MEANINGFUL-ROLE classification (see
    module docstring's "MEANINGFUL-ROLE CLASSIFICATION" section) --
    sustained opportunity PLUS availability, since the denominator is
    the FIXED real team-window size (`team_final_n_games`), never the
    active-game count. `team_final_n_opportunity_per_team_game` is
    NEVER floor-gated -- 0.0, not null, for a real zero-opportunity
    applicable window, same convention as `team_final_n_points_per_team_game`.
    The three tier flags (`team_final_n_role_present`/
    `_meaningful_role`/`_strong_lead_role`) are computed directly from
    that rate via `_role_tier_flags()` -- nullable booleans, null only
    for a non-applicable `team_game_window_status` row, never a second
    filter on top of the always-visible raw counts."""
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")
    opportunity_col, thresholds = _resolve_role_metric(position, metric_name, DATASET2_ROLE_THRESHOLDS_TEAM_GAME)

    validate_columns(weekly_player, WEEKLY_PLAYER_BASE_COLUMNS + (opportunity_col,), "weekly_player")
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
        {opportunity_col: "team_final_n_opportunity"},
    )

    out = base.merge(player_team, on=["season", "player_id"], how="left")
    out = out.merge(agg, on=["season", "player_id"], how="left")
    out["team_game_window_status"] = _downgrade_unmatched_applicable(out, "team_final_n_games")

    out["team_final_n_opportunity_per_team_game"] = out["team_final_n_opportunity"] / out["team_final_n_games"]

    (
        out["team_final_n_role_present"],
        out["team_final_n_meaningful_role"],
        out["team_final_n_strong_lead_role"],
    ) = _role_tier_flags(out["team_final_n_opportunity_per_team_game"], thresholds)

    out["position"] = position
    out["metric_name"] = metric_name
    out["window_n"] = n

    return out[list(ROLE_TEAM_GAME_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_active_game_role_traits(
    population: pd.DataFrame, weekly_player: pd.DataFrame, n: int, position: str, metric_name: str
) -> pd.DataFrame:
    """Real per-active-game-window MEANINGFUL-ROLE classification --
    opportunity ONLY across the player's own real final `n` games WITH
    a real weekly row (identical active-game selection as
    build_active_game_final_n_traits()/build_active_game_efficiency_traits()).
    `active_final_n_opportunity_per_active_game` is 0.0 (not null) for
    a player with real active games but zero real opportunity in this
    metric across them (a real, meaningful "on the field, no role"
    finding), and null only when the player has zero real active games
    at all this season (`active_final_n_games == 0`, nothing to divide
    by). See build_team_game_role_traits() for what the tier flags do
    and don't claim -- identical semantics here, on the active-game
    basis."""
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")
    opportunity_col, thresholds = _resolve_role_metric(position, metric_name, DATASET2_ROLE_THRESHOLDS_ACTIVE_GAME)

    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")
    validate_columns(weekly_player, WEEKLY_PLAYER_BASE_COLUMNS + (opportunity_col,), "weekly_player")

    position_population = population[population["position"] == position]
    base = position_population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(
        subset=["season", "player_id"]
    ).reset_index(drop=True)

    w = weekly_player.sort_values(["season", "player_id", "week"])
    w = w.assign(_rank_from_end=w.groupby(["season", "player_id"]).cumcount(ascending=False))
    in_window = w[w["_rank_from_end"] < n]

    agg = (
        in_window.groupby(["season", "player_id"])
        .agg(active_final_n_games=("week", "count"), active_final_n_opportunity=(opportunity_col, "sum"))
        .reset_index()
    )

    out = base.merge(agg, on=["season", "player_id"], how="left")
    out["active_final_n_games"] = out["active_final_n_games"].fillna(0).astype(int)
    out["active_final_n_opportunity"] = out["active_final_n_opportunity"].fillna(0.0)

    out["active_final_n_opportunity_per_active_game"] = out["active_final_n_opportunity"] / out[
        "active_final_n_games"
    ].replace(0, np.nan)

    (
        out["active_final_n_role_present"],
        out["active_final_n_meaningful_role"],
        out["active_final_n_strong_lead_role"],
    ) = _role_tier_flags(out["active_final_n_opportunity_per_active_game"], thresholds)

    out["position"] = position
    out["metric_name"] = metric_name
    out["window_n"] = n

    return out[list(ROLE_ACTIVE_GAME_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_team_game_snap_share_role_traits(
    population: pd.DataFrame,
    weekly_player: pd.DataFrame,
    weekly_all_positions: pd.DataFrame,
    raw_snaps: pd.DataFrame,
    n: int,
    position: str,
) -> pd.DataFrame:
    """Real per-team-game-window offensive-snap-share MEANINGFUL-ROLE
    classification -- team-game basis only (no active-game snap-share
    variant proposed or built). `weekly_player`/`weekly_all_positions`
    resolve the real team-game window and `team_game_window_status`
    EXACTLY the same way as every other builder in this module (Source
    A remains the single authority for team identity/window
    membership); `raw_snaps` supplies the real snap counts (Source B,
    2013+ coverage, expected pre-filtered to matched rows and renamed
    -- see SNAP_ROLE_REQUIRED_COLUMNS) used only for the numerator/
    denominator of the share itself.

    DENOMINATOR IS REAL-TEAM-GAME-LEVEL, NOT PLAYER-ROW-LEVEL: for each
    real (season, team, week) in the window, the team's real total
    offensive plays is `max(offense_snaps)` among matched players that
    game -- the same real, audit-verified reconstruction
    lib/dataset2/snap_traits.py's build_season_snap_usage() already
    uses for the season-level `offense_pct` (the O-line/QB group
    reliably plays every real offensive snap). This total is summed
    across the window's real team-games INDEPENDENT of whether THIS
    player himself has a real snap-count row that week -- a team's
    real offensive-play total for the week doesn't depend on any one
    player's individual availability, so a player inactive for part of
    the window still gets the real, full team denominator, only a real
    (correctly zero-filled) 0 contribution to his own numerator that
    week.

    MISSING SOURCE B COVERAGE IS EXPLICIT, NOT SILENTLY ZEROED:
    `team_final_n_has_snap_coverage` is False whenever the real,
    summed team-offense-total across the window is zero or entirely
    absent (pre-2013 seasons, or any other real Source B gap) --
    `team_final_n_offense_snap_share` and all three tier flags stay
    null in that case, never computed against a missing or
    structurally-zero denominator. `team_final_n_offense_snaps` (the
    raw numerator) still zero-fills the normal way for any in-window
    week the player has no real snap-count row, consistent with every
    other raw window sum in this module -- it is
    `has_snap_coverage`/`offense_snap_share` that carry the
    "no real Source B data here" distinction, not the raw count.

    FOR WR: see module docstring -- snap share establishes real
    participation, not receiving hierarchy. Read alongside the
    separate WR receiving-role targets thresholds
    (build_team_game_role_traits()), never as a substitute for them.
    """
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")
    if position not in DATASET2_ROLE_THRESHOLDS_SNAP_SHARE:
        raise ValueError(
            f"No snap-share role thresholds defined for position={position!r}; see "
            f"config.py's DATASET2_ROLE_THRESHOLDS_SNAP_SHARE for the supported set."
        )
    thresholds = DATASET2_ROLE_THRESHOLDS_SNAP_SHARE[position]

    validate_columns(weekly_player, WEEKLY_PLAYER_REQUIRED_COLUMNS, "weekly_player")
    validate_columns(raw_snaps, SNAP_ROLE_REQUIRED_COLUMNS, "raw_snaps")

    position_population = population[population["position"] == position]
    base, player_team, team_game_index = _scope_to_team_games(position_population, weekly_player, weekly_all_positions)

    tgi = team_game_index.copy()
    tgi["_games_from_end"] = tgi["team_total_games"] - tgi["team_game_index"]
    final_n_weeks = tgi[tgi["_games_from_end"] < n][["season", "team", "week"]]

    games_agg = _aggregate_team_window(
        player_team,
        final_n_weeks,
        weekly_player,
        "team_final_n_games",
        "team_final_n_active_games",
        {"fantasy_points_ppr": "_dummy_total"},
    ).drop(columns=["_dummy_total"])

    snap_agg = _aggregate_team_window(
        player_team,
        final_n_weeks,
        raw_snaps,
        "_snap_games",
        "_snap_active_games",
        {"offense_snaps": "team_final_n_offense_snaps"},
    )[["season", "player_id", "team_final_n_offense_snaps"]]

    team_game_totals = (
        raw_snaps.groupby(["season", "team", "week"])["offense_snaps"]
        .max()
        .rename("_team_game_offense_total")
        .reset_index()
    )
    team_window_totals = final_n_weeks.merge(team_game_totals, on=["season", "team", "week"], how="left")
    team_window_totals["_team_game_offense_total"] = team_window_totals["_team_game_offense_total"].fillna(0.0)
    team_totals = (
        team_window_totals.groupby(["season", "team"])["_team_game_offense_total"]
        .sum()
        .rename("team_final_n_team_offense_total")
        .reset_index()
    )

    out = base.merge(player_team, on=["season", "player_id"], how="left")
    out = out.merge(games_agg, on=["season", "player_id"], how="left")
    out["team_game_window_status"] = _downgrade_unmatched_applicable(out, "team_final_n_games")
    out = out.merge(snap_agg, on=["season", "player_id"], how="left")
    out = out.merge(team_totals, on=["season", "team"], how="left")

    applicable_mask = out["team_game_window_status"] == TEAM_GAME_STATUS_APPLICABLE

    out["team_final_n_has_snap_coverage"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out.loc[applicable_mask, "team_final_n_has_snap_coverage"] = (
        out.loc[applicable_mask, "team_final_n_team_offense_total"].fillna(0.0) > 0
    )

    out["team_final_n_offense_snap_share"] = np.nan
    coverage_mask = applicable_mask & (out["team_final_n_has_snap_coverage"] == True)  # noqa: E712
    out.loc[coverage_mask, "team_final_n_offense_snap_share"] = (
        out.loc[coverage_mask, "team_final_n_offense_snaps"] / out.loc[coverage_mask, "team_final_n_team_offense_total"]
    )

    (
        out["team_final_n_role_present"],
        out["team_final_n_meaningful_role"],
        out["team_final_n_strong_lead_role"],
    ) = _role_tier_flags(out["team_final_n_offense_snap_share"], thresholds)

    out["position"] = position
    out["window_n"] = n

    return out[list(SNAP_SHARE_ROLE_OUTPUT_COLUMNS)].reset_index(drop=True)
