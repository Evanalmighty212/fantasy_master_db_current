"""
lib/dataset2/canonical_predictor_table.py

Dataset 2 canonical PRESEASON PREDICTOR table -- artifact 1 of the
three-artifact architecture approved 2026-07
(research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md §1a). Builds
ONLY the predictor table -- no outcome data (`star_by_value_*`,
`bust_*`) is read, imported, or joined anywhere in this module, per
that proposal's leakage boundary (§10). The outcome table and the
analysis view that joins the two are separate, not-yet-built
artifacts.

GRAIN: one row per (`prediction_season`, `player_id`) -- see
`build_canonical_predictor_table()`'s own docstring for exactly how
the spine is assembled (the real master population's own rows, UNION
family #9's own real "future" prediction-season rows).

WHAT'S INCLUDED, per instruction -- only implemented, approved,
preseason-facing traits, no null placeholders for anything not yet
built:
- Families #1 (NFL experience) and #1's position-relative z-score
- Family #2 (age curve: `fam2_age_at_week1_years`,
  `fam2_age_x_experience`, `fam2_age_position_z`) -- added 2026-07
  once schedules.csv was fetched and pinned via the established
  GitHub Actions path (see AGE INCLUSION below; this family was
  deferred in the prior round for exactly this reason, now resolved)
- Family #4 (NFL draft capital)
- Family #6, body-size portion (height/weight/BMI)
- Family #7 (prior-season finish: overall, positional, PPG)
- Family #8 (multi-year PPG trend, 2yr/3yr slope)
- Family #39 (prior-season games played / availability)
- Family #44 (player changed teams)
- Source A prior-season usage (targets/carries/receiving_yards/
  receiving_air_yards/passing_epa/rushing_epa/receiving_epa/
  receptions/receiving_yards_after_catch/target_share/air_yards_share/
  wopr) -- no single family number, a cross-cutting `srcA_` prefix is
  used (see NAMING below)
- Source B prior-season OFFENSIVE snaps and offense_pct ONLY -- per
  explicit instruction, narrower than snap_traits.py's full real
  output (which also has defense_snaps/st_snaps/games_active,
  available but deliberately excluded from this table this round, not
  because they're unimplemented)
- Family #9's full lagged, wide feature set (all window_ns, all
  position/metric/basis combinations, via
  lib.dataset2.partial_season_canonical)
- Family #10 (depth-chart status) -- included as a direct, real
  prerequisite of family #86 below, PRE-2025 SCHEMA ONLY (see AGE/2025
  EXCLUSION below)
- Family #86 (volume-fragility split, the portion implemented on top
  of family #10)
- Family #88 -- age/frame portion (`body_size_position_z`) AND the
  compact prior-season workload core (`fam88_prior_season_touches`,
  `fam88_prior_season_heavy_touch_workload`, added 2026-07); the
  remainder (multi-season touch history, postseason workload,
  age/frame-compound flags) is EXCLUDED, see DEFERRED FAMILIES below
- Family #18 -- receiving-efficiency CORE portion only
  (`fam18_prior_season_catch_rate`,
  `fam18_prior_season_receiving_yards_per_target`,
  `fam18_prior_season_yac_per_reception`, added 2026-07); no
  threshold/classification flag -- see
  lib.dataset2.receiving_efficiency_traits.py's own docstring for the
  full real design and the real YAC coverage audit it relies on

AGE (FAMILY #2) INCLUSION -- per explicit instruction (2026-07), age
was moved from deferred to Wave 1. Its real prerequisite
(`schedules.csv`, needed for real per-team Week-1 kickoff dates) was
fetched and pinned via the established GitHub Actions/nflverse_source.py
path (see `scripts/ci_fetch_schedules.py`,
`scripts/nflverse_source_manifest.json`'s `"schedules"` entry) --
7,548 real games, seasons 1999-2026, sha256-verified against the
pinned manifest hash. `build_canonical_predictor_table()`'s caller now
passes this real `schedule_df` through to
`build_experience_age_draft_traits()` (previously an empty placeholder
DataFrame -- see git history for the prior, disclosed-gap version of
this module). `fam2_age_at_week1_years`, `fam2_age_x_experience`, and
`fam2_age_position_z` are computed from it exactly like every other
family #1/#4/#6 column (preseason-safe by construction, no `_prior_`
lag needed -- see NAMING below) and carry real, disclosed missingness
(no players.csv birth_date match, or no resolvable real Week-1 game
for that player's team/season, -> null; never imputed or guessed --
see `_build_fam1_4_6_layer()`'s own docstring and
`experience_age_draft.py`'s MISSINGNESS POLICY). `experience_years`
(family #1) and `experience_position_z` never depended on schedule
data and were already included in every prior round.

FAMILY #10's 2025 real depth-chart schema branch is likewise excluded
for the same reason (its own preseason-snapshot selection needs real
Week-1 kickoff dates) -- family #10/#86 use ONLY the real 2006-2024
pre-2025-schema depth-chart files; 2025 rows get real, structural
nulls for every depth-chart-derived column, documented as a source-
coverage boundary (§ MISSINGNESS below), not folded into
DEFERRED_FAMILIES (the family itself IS included, just with a real,
dated coverage gap for its most recent season -- see
`family_coverage_notes` in the column registry).

DEFERRED FAMILIES -- approved but not includable this round, listed
with a real reason, never approximated (Family #2/age is NO LONGER
deferred -- see AGE INCLUSION above; this list matches DEFERRED_FAMILIES
below exactly):
- Source C / family #12+ (participation-derived predictors) --
  lib.dataset2.participation_traits.py only produces RAW PLAY and
  NORMALIZED PLAYER-PLAY grain output; no player-SEASON aggregate
  exists to lag into a preseason predictor at all (confirmed by
  reading that module directly this round -- its season/preseason
  aggregate layer was deliberately removed in an earlier round, see
  that module's own docstring).
- Family #88's workload sub-signal REMAINDER -- multi-season touch
  history ("multiple 300+ touch seasons"), real postseason workload
  ("heavy playoff workload"), and age/frame-compound flags. The
  COMPACT PRIOR-SEASON workload core (`fam88_prior_season_touches`,
  `fam88_prior_season_heavy_touch_workload`) IS now built and included,
  2026-07 -- the literal `"pending"` placeholder this family used to
  carry is gone entirely, see
  lib.dataset2.fragility_traits.py::build_workload_core_traits().
- Dataset 2B (bust) outcome fields -- not a predictor family at all
  (belongs in the separate outcome table, artifact 2), reserved by
  name only per the proposal's §10, not built here.

NAMING (per proposal §7): `{family_or_source_prefix}_{field}`.
Lag-derived columns (raw source season = prediction_season - 1)
carry `_prior_` in the name (e.g. `fam7_prior_overall_finish`,
`srcA_prior_season_targets`); columns that are preseason-safe BY
CONSTRUCTION (age/experience/draft capital/body-size/depth-chart --
their own `season` already IS the prediction season) carry no
`_prior_` segment. Family #9's own columns use its own established
`fam9_{team,active}_final_{n}_...` scheme with explicit
`observation_season`/`prediction_season` id columns instead of a
per-column prefix (see partial_season_canonical.py's docstring for
why). `srcA_`/`srcB_` are used for Source A/B base variables since
they aren't owned by one single family number.

MISSINGNESS: preserved exactly per source module's own semantics (see
each helper's docstring below) -- real zero, nullable-boolean `<NA>`,
non-applicable status, source-not-yet-covered, and no-prior-history
are never collapsed into each other. Every boolean-shaped canonical
column is cast to pandas nullable `"boolean"` dtype at assembly time
(never left as a raw float/object encoding that could silently read a
real `<NA>` as `False`).

DETERMINISM: `build_canonical_predictor_table()` returns rows sorted
by (`prediction_season`, `player_id`) and columns in a FIXED,
declared order (never dict/set iteration order) -- rebuilding from
identical inputs produces byte-identical CSV output (see
scripts/build_dataset2_canonical_predictor_table.py's own round-trip
check).

TEST SCOPE: tests/test_dataset2_canonical_predictor_table.py proves
grain (exactly one row per key, no collisions, no `_x`/`_y` merge
artifacts), leakage (no same-season value ever appears where a lagged
one is expected), and the missingness/normalization rules against
synthetic fixtures. Real-data integration numbers (row/column counts,
missingness breakdown, deferred-family inventory) are produced by
scripts/build_dataset2_canonical_predictor_table.py against the real
2006-2025 population, not by this test file.
"""

import sys
from pathlib import Path

import pandas as pd

from lib.preseason_market_status import STATUSES as PRESEASON_MARKET_STATUS_VALUES

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import apply_source_coverage_null_mask, validate_columns
from lib.dataset2.depth_chart_traits import build_depth_chart_traits
from lib.dataset2.experience_age_draft import build_experience_age_draft_traits
from lib.dataset2.fragility_traits import build_durability_risk_traits, build_volume_fragility_traits, build_workload_core_traits
from lib.dataset2.receiving_efficiency_traits import build_receiving_efficiency_traits
from lib.dataset2.partial_season_canonical import (
    DEFAULT_WINDOW_NS,
    build_family9_observation_wide,
    build_family9_preseason_features,
)
from lib.dataset2.prior_finish_traits import build_prior_finish_traits
from lib.dataset2.prior_season_traits import build_prior_season_traits
from lib.dataset2.snap_traits import build_preseason_snap_features, build_raw_player_game_snaps, build_season_snap_usage
from lib.dataset2.usage_traits import build_preseason_usage_features, build_raw_season_usage
from config import DATASET2_SOURCE_A_TARGETS_COVERAGE_REASON, DATASET2_SOURCE_A_TARGETS_UNRELIABLE_OBSERVATION_SEASONS

MASTER_POPULATION_REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "position",
    "team",
    "games_played",
    "ppg_ppr",
    "overall_finish_ppr",
    "position_finish_ppr",
    "canonical_position_status",
    "canonical_position_authority",
    "historical_input_revision",
    "preseason_market_status",
    "preseason_market_status_sensitivity_30",
    "preseason_market_status_authority",
    "preseason_market_status_evidence_source",
    "preseason_market_status_evidence_summary",
)

PRESEASON_MARKET_METADATA_COLUMNS = (
    "preseason_market_status",
    "preseason_market_status_sensitivity_30",
    "preseason_market_status_authority",
    "preseason_market_status_evidence_source",
    "preseason_market_status_evidence_summary",
)

PLAYERS_REQUIRED_COLUMNS = ("gsis_id", "pfr_id", "birth_date", "rookie_season", "height", "weight", "draft_year", "draft_round", "draft_pick", "draft_team")

SCHEMA2025_EMPTY_COLUMNS = ("dt", "team", "gsis_id", "pos_grp", "pos_abb", "pos_rank")
SCHEDULE_EMPTY_COLUMNS = ("season", "game_type", "week", "gameday", "home_team", "away_team")
# Same column set, used to validate the REAL schedule_df passed into
# build_canonical_predictor_table() for family #2 (age) -- see that
# function and module docstring's AGE INCLUSION section.
SCHEDULE_REQUIRED_COLUMNS = SCHEDULE_EMPTY_COLUMNS

# Approved, implemented families this table cannot include this round
# -- a real reason each, never silently omitted. See module docstring.
# Family #2 (age) was REMOVED from this tuple 2026-07 once
# schedules.csv was fetched/pinned and wired in -- see module
# docstring's AGE INCLUSION section. Do not re-add it here without a
# new real reason.
DEFERRED_FAMILIES = (
    {
        "family_number": "12+ (Source C / participation)",
        "family_name": "Route/participation-derived predictors",
        "reason": "lib.dataset2.participation_traits.py only produces raw play-level and "
        "normalized player-play-level output -- no player-season aggregate exists to "
        "lag into a preseason predictor. Confirmed by reading that module directly.",
    },
    {
        "family_number": "88 (workload sub-signal, remainder)",
        "family_name": "Workload/durability risk -- multi-season touch history, real postseason "
        "workload, and age/frame-compound flags (the literal \"pending\" placeholder itself is "
        "GONE -- see below)",
        "reason": "The compact PRIOR-SEASON workload core (fam88_prior_season_touches, "
        "fam88_prior_season_heavy_touch_workload) IS now built and included, 2026-07 -- see "
        "lib.dataset2.fragility_traits.py::build_workload_core_traits(). Still deferred, per "
        "explicit instruction, and NOT approximated: \"multiple 300+ touch seasons\" (needs "
        "multi-season history, out of this round's single-prior-season scope), \"heavy playoff "
        "workload\" (needs real postseason data, out of scope for a REG-only module), and the "
        "age/frame-compound flags (\"age + high prior workload,\" \"small frame + workhorse "
        "role\" -- cross-family compounds, not approved this round).",
    },
)

# Source B this round is deliberately narrowed to offensive snaps and
# offense_pct only, per explicit instruction -- snap_traits.py's real
# defense_snaps/st_snaps/games_active fields ARE implemented and
# available, just not requested for this table.
_SRC_B_FIELDS = ("offense_snaps", "offense_pct")


def _cast_boolean_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Cast every column in `columns` to pandas' nullable "boolean"
    dtype -- never leaves a real <NA> readable as False. Safe to call
    on a column that's already nullable-boolean (no-op)."""
    for col in columns:
        df[col] = df[col].astype("boolean")
    return df


_POSITION_TOKENS = ("qb", "rb", "wr", "te")

# Real, found exception to the generic name-based inference below:
# fam86_team_qb_uncertainty's own name contains a "qb" segment (it's
# ABOUT the team's QB slot being tied), but per fragility_traits.py's
# own docstring it is broadcast to EVERY skill-position player on that
# team, not QB-only. Verified this is the ONLY real exception by
# checking every one of the real 438 columns produced by the 2026-07
# real-data run (435 before family #2/age was added later that same
# round, all 3 age columns correctly infer "ALL" -- no position token
# in their names) against this inference function -- no other column
# both (a) contains a position-token segment and (b) is actually
# scoped wider than that position.
_POSITION_SCOPE_OVERRIDES = {
    "fam86_team_qb_uncertainty": "ALL",
}


def _infer_position_scope(canonical_column: str) -> str:
    """Best-effort inference of which single position a canonical
    column meaningfully applies to, from its own canonical name --
    "ALL" for every column that genuinely applies uniformly across
    QB/RB/WR/TE (biographical, draft-capital, prior-season, depth-
    chart-status, family #9's non-position-scoped PPG/half-split/
    status columns, etc.). Used so a consumer auditing this table's
    missingness can distinguish a real position-inapplicable <NA>
    (e.g. a WR row's QB-passing-role columns) from every other real
    missingness cause -- see
    scripts/build_dataset2_canonical_predictor_table.py's own
    missingness section, and this round's real verification that only
    ONE column (`fam86_team_qb_uncertainty`, see
    _POSITION_SCOPE_OVERRIDES above) needed an explicit override
    against the naive per-token match."""
    if canonical_column in _POSITION_SCOPE_OVERRIDES:
        return _POSITION_SCOPE_OVERRIDES[canonical_column]
    for part in canonical_column.split("_"):
        if part in _POSITION_TOKENS:
            return part.upper()
    return "ALL"


def _registry_row(canonical_column, family_number, family_name, source, earliest, latest, dtype, missingness, observation_type, raw_column=None):
    return {
        "canonical_column": canonical_column,
        "family_number": family_number,
        "family_name": family_name,
        "source": source,
        "historical_coverage_earliest": earliest,
        "historical_coverage_latest": latest,
        "dtype": dtype,
        "missingness_semantics": missingness,
        "observation_type": observation_type,
        "source_raw_column": raw_column or canonical_column,
    }


def _build_fam1_4_6_layer(exp_age_draft_raw: pd.DataFrame, min_season: int, max_season: int):
    """Families #1 (experience, position-relative z-score), #2 (age
    curve, real per-team Week-1 kickoff date -- see module docstring's
    AGE INCLUSION), #4 (draft capital), #6 body-size portion -- all
    preseason-safe BY CONSTRUCTION (own `season` already is
    prediction_season, no lag). `exp_age_draft_raw` must already be
    build_experience_age_draft_traits()'s real output (built ONCE by
    the caller against the real schedule_df, not recomputed here) --
    see build_canonical_predictor_table()."""
    raw = exp_age_draft_raw

    rename = {
        "experience_years": "fam1_experience_years",
        "experience_position_z": "fam1_experience_position_z",
        "age_at_week1_years": "fam2_age_at_week1_years",
        "age_x_experience": "fam2_age_x_experience",
        "age_position_z": "fam2_age_position_z",
        "nfl_draft_year": "fam4_nfl_draft_year",
        "nfl_draft_round": "fam4_nfl_draft_round",
        "nfl_draft_pick": "fam4_nfl_draft_pick",
        "nfl_draft_team": "fam4_nfl_draft_team",
        "height_inches": "fam6_height_inches",
        "weight_lbs": "fam6_weight_lbs",
        "body_size_bmi": "fam6_body_size_bmi",
    }
    out = raw[["season", "player_id"] + list(rename.keys())].rename(columns=rename)

    registry = [
        _registry_row(
            rename["experience_years"], "1", "NFL experience curve", "players.csv",
            min_season, max_season, "Int64/float64",
            "No players.csv match -> null", "Same as prediction_season", "experience_years",
        ),
        _registry_row(
            rename["experience_position_z"], "1", "NFL experience curve (position z-score)", "players.csv",
            min_season, max_season, "float64",
            "No players.csv match, or single-row position group -> null",
            "Same as prediction_season", "experience_position_z",
        ),
        _registry_row(
            rename["age_at_week1_years"], "2", "Age curve", "players.csv + schedules.csv",
            min_season, max_season, "float64",
            "No players.csv birth_date match, or no resolvable real Week-1 game for that "
            "player's team/season -> null", "Same as prediction_season", "age_at_week1_years",
        ),
        _registry_row(
            rename["age_x_experience"], "2", "Age curve (age x experience interaction)", "players.csv + schedules.csv",
            min_season, max_season, "float64",
            "Either age_at_week1_years or experience_years null -> null",
            "Same as prediction_season", "age_x_experience",
        ),
        _registry_row(
            rename["age_position_z"], "2", "Age curve (position z-score)", "players.csv + schedules.csv",
            min_season, max_season, "float64",
            "No age_at_week1_years, or single-row position group -> null",
            "Same as prediction_season", "age_position_z",
        ),
    ]
    for field, canon in (("draft_year", "fam4_nfl_draft_year"), ("draft_round", "fam4_nfl_draft_round"), ("draft_pick", "fam4_nfl_draft_pick"), ("draft_team", "fam4_nfl_draft_team")):
        registry.append(
            _registry_row(
                canon, "4", "NFL draft capital", "players.csv", min_season, max_season,
                "float64/object", "Undrafted or no players.csv match -> null (not currently "
                "distinguished from each other -- a real open item)",
                "Same as prediction_season", field,
            )
        )
    for field, canon in (("height_inches", "fam6_height_inches"), ("weight_lbs", "fam6_weight_lbs"), ("body_size_bmi", "fam6_body_size_bmi")):
        registry.append(
            _registry_row(
                canon, "6", "Body-size profile", "players.csv", min_season, max_season,
                "float64", "No players.csv match -> null", "Same as prediction_season", field,
            )
        )
    return out, registry


def _build_fam7_layer(population: pd.DataFrame, min_season: int, max_season: int):
    raw = build_prior_finish_traits(population)
    rename = {
        "prior_overall_finish": "fam7_prior_overall_finish",
        "prior_positional_finish": "fam7_prior_positional_finish",
        "prior_ppg": "fam7_prior_ppg",
    }
    out = raw[["season", "player_id"] + list(rename.keys())].rename(columns=rename)
    registry = [
        _registry_row(
            canon, "7", "Previous-season finish", "master DB self-join",
            min_season + 1, max_season, "float64", "No season N-1 row -> null (rookie or gap year)",
            "prediction_season - 1", raw_col,
        )
        for raw_col, canon in rename.items()
    ]
    return out, registry


def _build_fam8_39_44_layer(population: pd.DataFrame, min_season: int, max_season: int):
    raw = build_prior_season_traits(population)
    rename = {
        "ppg_trend_2yr_slope": "fam8_prior_ppg_trend_2yr_slope",
        "ppg_trend_3yr_slope": "fam8_prior_ppg_trend_3yr_slope",
        "prior_season_games_played": "fam39_prior_season_games_played",
        "changed_team": "fam44_prior_changed_team",
    }
    out = raw[["season", "player_id"] + list(rename.keys())].rename(columns=rename)
    out = _cast_boolean_columns(out, ["fam44_prior_changed_team"])
    registry = [
        _registry_row(
            "fam8_prior_ppg_trend_2yr_slope", "8", "Multi-year production trend", "master DB self-join",
            min_season + 1, max_season, "float64", "<2 non-null lag points -> null (rookie or gap year)",
            "prediction_season - 1 and - 2", "ppg_trend_2yr_slope",
        ),
        _registry_row(
            "fam8_prior_ppg_trend_3yr_slope", "8", "Multi-year production trend", "master DB self-join",
            min_season + 1, max_season, "float64", "<2 non-null lag points -> null (rookie or gap year)",
            "prediction_season - 1, - 2, and - 3", "ppg_trend_3yr_slope",
        ),
        _registry_row(
            "fam39_prior_season_games_played", "39", "Prior-season availability", "master DB self-join",
            min_season + 1, max_season, "float64", "No season N-1 row -> null (rookie or gap year)",
            "prediction_season - 1", "prior_season_games_played",
        ),
        _registry_row(
            "fam44_prior_changed_team", "44", "Player changed teams", "master DB self-join",
            min_season + 1, max_season, "boolean (nullable)", "No season N-1 row -> null, never False (rookie)",
            "prediction_season vs. prediction_season - 1", "changed_team",
        ),
    ]
    return out, registry


def _build_srcA_layer(population: pd.DataFrame, weekly_all_season_types: pd.DataFrame, min_season: int, max_season: int):
    """Source A prior-season usage, full real field set -- no single
    family number owns these (families #15/#17/#18/#20/#22 all draw
    from this same base), hence the cross-cutting `srcA_` prefix (see
    module docstring's NAMING section). `receptions` added 2026-07 to
    unlock family #88's compact workload core -- same SUM/lag treatment
    as every other Source A field, no new semantics.

    Also returns the un-renamed `preseason` frame itself (plain
    `prior_season_*` column names) so family #88's own workload-core
    layer can reuse it directly -- same reuse-not-recompute pattern
    already used for Source B's `raw_games` (see
    `_build_srcB_layer`/family #9's `fam9_raw_snaps` below)."""
    raw_season = build_raw_season_usage(population, weekly_all_season_types)
    preseason = build_preseason_usage_features(raw_season)
    fields = ("targets", "carries", "receiving_yards", "receiving_air_yards", "passing_epa", "rushing_epa", "receiving_epa", "receptions", "target_share", "air_yards_share", "wopr")
    rename = {f"prior_season_{f}": f"srcA_prior_season_{f}" for f in fields}
    out = preseason[["season", "player_id"] + list(rename.keys())].rename(columns=rename)
    registry = [
        _registry_row(
            canon, "15/17/18/20/22 (Source A base variables, cross-cutting)", "Source A prior-season usage",
            "Source A weekly (REG only)", min_season + 1, max_season, "float64",
            "No season N-1 real row -> null; racr deliberately never output (deferred, reconstruct-or-defer rule)",
            "prediction_season - 1", raw_col,
        )
        for raw_col, canon in rename.items()
    ]
    return out, preseason, registry


def _build_srcB_layer(population: pd.DataFrame, snap_counts_all: pd.DataFrame, players_df: pd.DataFrame, min_season: int, max_season: int):
    """Source B prior-season OFFENSIVE snaps and offense_pct ONLY --
    narrower than snap_traits.py's real full output, per explicit
    instruction. See module docstring."""
    raw_games = build_raw_player_game_snaps(snap_counts_all, players_df)
    season_usage = build_season_snap_usage(population, raw_games)
    preseason = build_preseason_snap_features(season_usage)
    rename = {f"prior_season_{f}": f"srcB_prior_season_{f}" for f in _SRC_B_FIELDS}
    out = preseason[["season", "player_id"] + list(rename.keys())].rename(columns=rename)
    registry = [
        _registry_row(
            canon, "N/A (Source B base variable, cross-cutting)", "Source B prior-season offensive snap usage",
            "Source B snap_counts (REG only)", 2014, max_season, "float64",
            "Pre-2013 season N-1, or unmatched pfr_id that season -> null",
            "prediction_season - 1", raw_col,
        )
        for raw_col, canon in rename.items()
    ]
    return out, raw_games, registry


def _build_fam10_86_layer(population: pd.DataFrame, depth_chart_pre2025_df: pd.DataFrame, min_season: int, max_season: int):
    """Family #10 (depth-chart status, PRE-2025 schema only -- see
    module docstring's AGE/2025 EXCLUSION) and family #86 (volume
    fragility, built directly on top of #10's own output)."""
    empty_schedule = pd.DataFrame(columns=SCHEDULE_EMPTY_COLUMNS)
    empty_2025 = pd.DataFrame(columns=SCHEMA2025_EMPTY_COLUMNS)
    dc = build_depth_chart_traits(population, depth_chart_pre2025_df, empty_2025, empty_schedule)

    fam10_rename = {
        "depth_chart_team": "fam10_depth_chart_team",
        "depth_chart_native_rank": "fam10_depth_chart_native_rank",
        "depth_chart_status": "fam10_depth_chart_status",
        "depth_rank_tied": "fam10_depth_rank_tied",
        "starter_group_size": "fam10_starter_group_size",
        "position_starter_count": "fam10_position_starter_count",
        "depth_chart_schema_era": "fam10_depth_chart_schema_era",
    }
    fam10_out = dc[["season", "player_id"] + list(fam10_rename.keys())].rename(columns=fam10_rename)
    fam10_out = _cast_boolean_columns(fam10_out, ["fam10_depth_rank_tied"])

    frag = build_volume_fragility_traits(dc)
    fam86_rename = {
        "multiple_rank1_players": "fam86_multiple_rank1_players",
        "qb_starter_uncertainty": "fam86_qb_starter_uncertainty",
        "rb_committee_indicator": "fam86_rb_committee_indicator",
        "te_co_starter_indicator": "fam86_te_co_starter_indicator",
        "wr_starter_group_size": "fam86_wr_starter_group_size",
        "wr_starter_group_member": "fam86_wr_starter_group_member",
        "wr_league_starter_group_size_norm": "fam86_wr_league_starter_group_size_norm",
        "wr_starter_group_size_vs_league_norm": "fam86_wr_starter_group_size_vs_league_norm",
        "team_qb_uncertainty": "fam86_team_qb_uncertainty",
    }
    fam86_out = frag[["season", "player_id"] + list(fam86_rename.keys())].rename(columns=fam86_rename)
    fam86_bool_cols = [
        "fam86_multiple_rank1_players", "fam86_qb_starter_uncertainty", "fam86_rb_committee_indicator",
        "fam86_te_co_starter_indicator", "fam86_wr_starter_group_member", "fam86_team_qb_uncertainty",
    ]
    fam86_out = _cast_boolean_columns(fam86_out, fam86_bool_cols)

    coverage_note = (
        "2006-2024 real (pre-2025 schema); 2025 structurally null this round -- "
        "same schedules.csv prerequisite gap as family #2, see module docstring"
    )
    registry = [
        _registry_row(
            "fam10_depth_chart_team", "10", "Projected depth-chart position", "nflverse depth_charts",
            min_season, 2024, "object", "No matching preseason snapshot -> null; " + coverage_note,
            "Same as prediction_season", "depth_chart_team",
        ),
        _registry_row(
            "fam10_depth_chart_native_rank", "10", "Projected depth-chart position", "nflverse depth_charts",
            min_season, 2024, "float64", "No matching snapshot -> null; " + coverage_note,
            "Same as prediction_season", "depth_chart_native_rank",
        ),
        _registry_row(
            "fam10_depth_chart_status", "10", "Projected depth-chart position", "nflverse depth_charts",
            min_season, 2024, "object", "No matching snapshot -> null (never guessed \"deeper\"); " + coverage_note,
            "Same as prediction_season", "depth_chart_status",
        ),
        _registry_row(
            "fam10_depth_rank_tied", "10", "Projected depth-chart position", "nflverse depth_charts",
            min_season, 2024, "boolean (nullable)", "No matching snapshot -> null; always False for 2025-schema rows by construction (none present this round); " + coverage_note,
            "Same as prediction_season", "depth_rank_tied",
        ),
        _registry_row(
            "fam10_starter_group_size", "10", "Projected depth-chart position", "nflverse depth_charts",
            min_season, 2024, "float64", "No matching snapshot -> null; " + coverage_note,
            "Same as prediction_season", "starter_group_size",
        ),
        _registry_row(
            "fam10_position_starter_count", "10", "Projected depth-chart position", "config.py (fixed reference)",
            min_season, max_season, "float64", "Position not in the fixed QB/RB/WR/TE reference map -> null",
            "N/A (fixed structural constant)", "position_starter_count",
        ),
        _registry_row(
            "fam10_depth_chart_schema_era", "10", "Projected depth-chart position", "nflverse depth_charts",
            min_season, 2024, "object", "No matching snapshot -> null; " + coverage_note,
            "Same as prediction_season", "depth_chart_schema_era",
        ),
    ]
    for field, canon, pos_note in (
        ("multiple_rank1_players", "fam86_multiple_rank1_players", "All positions"),
        ("qb_starter_uncertainty", "fam86_qb_starter_uncertainty", "QB only, null elsewhere"),
        ("rb_committee_indicator", "fam86_rb_committee_indicator", "RB only, null elsewhere"),
        ("te_co_starter_indicator", "fam86_te_co_starter_indicator", "TE only, null elsewhere"),
        ("team_qb_uncertainty", "fam86_team_qb_uncertainty", "All positions, broadcast team-wide"),
    ):
        registry.append(
            _registry_row(
                canon, "86 (split, part)", "Volume fragility / competition", "depth_chart_traits.py output",
                min_season, 2024, "boolean (nullable)",
                f"No depth-chart data -> null; position-inapplicable -> null by design. {pos_note}; " + coverage_note,
                "Same as prediction_season", field,
            )
        )
    for field, canon, dtype in (
        ("wr_starter_group_size", "fam86_wr_starter_group_size", "float64"),
        ("wr_starter_group_member", "fam86_wr_starter_group_member", "boolean (nullable)"),
        ("wr_league_starter_group_size_norm", "fam86_wr_league_starter_group_size_norm", "float64"),
        ("wr_starter_group_size_vs_league_norm", "fam86_wr_starter_group_size_vs_league_norm", "float64"),
    ):
        registry.append(
            _registry_row(
                canon, "86 (split, part)", "Volume fragility (WR personnel-structure facts)", "depth_chart_traits.py output",
                min_season, 2024, dtype, "WR only, null elsewhere; no depth-chart data -> null; " + coverage_note,
                "Same as prediction_season", field,
            )
        )
    return fam10_out, fam86_out, registry


def _build_fam88_layer(experience_age_draft_raw: pd.DataFrame, srcA_preseason: pd.DataFrame, min_season: int, max_season: int):
    """Family #88 -- age/frame portion (`fam88_body_size_position_z`,
    unchanged) MERGED with the compact PRIOR-SEASON workload core added
    2026-07 (`fam88_prior_season_touches`/`fam88_prior_season_heavy_touch_workload`,
    see lib/dataset2/fragility_traits.py::build_workload_core_traits()'s
    own docstring for the full real design and what's deliberately NOT
    built this round). `srcA_preseason` must be `_build_srcA_layer()`'s
    own un-prefixed `preseason` return value (plain `prior_season_*`
    names) -- built ONCE and shared, never recomputed a second time."""
    raw = build_durability_risk_traits(experience_age_draft_raw)
    age_frame_out = raw[["season", "player_id", "body_size_position_z"]].rename(
        columns={"body_size_position_z": "fam88_body_size_position_z"}
    )

    workload = build_workload_core_traits(srcA_preseason)
    workload_out = workload[["season", "player_id", "prior_season_touches", "prior_season_heavy_touch_workload"]].rename(
        columns={
            "prior_season_touches": "fam88_prior_season_touches",
            "prior_season_heavy_touch_workload": "fam88_prior_season_heavy_touch_workload",
        }
    )
    workload_out = _cast_boolean_columns(workload_out, ["fam88_prior_season_heavy_touch_workload"])

    out = age_frame_out.merge(workload_out, on=["season", "player_id"], how="outer")

    registry = [
        _registry_row(
            "fam88_body_size_position_z", "88 (split, part)", "Workload/durability risk (age/frame portion)",
            "experience_age_draft.py output", min_season, max_season, "float64",
            "No BMI (no players.csv match) -> null", "Same as prediction_season", "body_size_position_z",
        ),
        _registry_row(
            "fam88_prior_season_touches", "88 (split, part)", "Workload/durability risk (prior-season workload core)",
            "Source A weekly (REG only), via usage_traits.py", min_season + 1, max_season, "float64",
            "No season N-1 real row (rookie or gap year) -> null; real zero preserved when a real prior-season row "
            "exists with zero real carries/receptions", "prediction_season - 1", "carries + receptions",
        ),
        _registry_row(
            "fam88_prior_season_heavy_touch_workload", "88 (split, part)", "Workload/durability risk (prior-season workload core)",
            "Source A weekly (REG only), via usage_traits.py", min_season + 1, max_season, "boolean (nullable)",
            "Null wherever fam88_prior_season_touches is null (never guessed); threshold = "
            "config.DATASET2_FAM88_HEAVY_TOUCH_WORKLOAD_THRESHOLD (350)", "prediction_season - 1",
            "carries + receptions >= 350",
        ),
    ]
    return out, registry


def _build_fam18_layer(srcA_preseason: pd.DataFrame, min_season: int, max_season: int):
    """Family #18, receiving-efficiency CORE portion -- approved
    2026-07 (see lib/dataset2/receiving_efficiency_traits.py's own
    docstring for the full real design, the real YAC coverage audit,
    and what's deliberately NOT built this round -- no threshold/
    classification flag). `srcA_preseason` must be
    `_build_srcA_layer()`'s own un-prefixed `preseason` return value --
    built ONCE and shared, never recomputed a second time. The real
    denominator columns this family's ratios are computed from
    (`srcA_prior_season_targets`, `srcA_prior_season_receptions`) are
    already separate canonical columns in their own right (Source A
    base variables) -- deliberately NOT duplicated here, so low-sample
    ratios stay auditable against their own real denominators."""
    eff = build_receiving_efficiency_traits(srcA_preseason)
    rename = {
        "prior_season_catch_rate": "fam18_prior_season_catch_rate",
        "prior_season_receiving_yards_per_target": "fam18_prior_season_receiving_yards_per_target",
        "prior_season_yac_per_reception": "fam18_prior_season_yac_per_reception",
    }
    out = eff[["season", "player_id"] + list(rename.keys())].rename(columns=rename)

    registry = [
        _registry_row(
            "fam18_prior_season_catch_rate", "18", "Receiving efficiency (core)",
            "Source A weekly (REG only), via usage_traits.py", min_season + 1, max_season, "float64",
            "No season N-1 real row (rookie or gap year), or real zero prior-season targets -> null "
            "(never a guessed 0.0); prediction_season 2007-2009 FORCED null -- real, audited "
            "targets-tracking gap in observation seasons 2006-2008 (see "
            "config.DATASET2_TARGETS_UNRELIABLE_OBSERVATION_SEASONS)", "prediction_season - 1", "receptions / targets",
        ),
        _registry_row(
            "fam18_prior_season_receiving_yards_per_target", "18", "Receiving efficiency (core)",
            "Source A weekly (REG only), via usage_traits.py", min_season + 1, max_season, "float64",
            "No season N-1 real row, or real zero prior-season targets -> null (never a guessed 0.0); "
            "prediction_season 2007-2009 FORCED null -- same real targets-tracking gap as catch_rate",
            "prediction_season - 1", "receiving_yards / targets",
        ),
        _registry_row(
            "fam18_prior_season_yac_per_reception", "18", "Receiving efficiency (core)",
            "Source A weekly (REG only), via usage_traits.py", min_season + 1, max_season, "float64",
            "No season N-1 real row, or real zero prior-season receptions -> null; never a guessed 0.0. "
            "A real negative or zero YAC total with positive receptions produces the real calculated value.",
            "prediction_season - 1", "receiving_yards_after_catch / receptions",
        ),
    ]
    return out, registry


# --- Source A targets/receiving_air_yards coverage remediation (2026-07) ---
#
# Full, audited dependency inventory:
# research/dataset2/SOURCE_A_TARGETS_COVERAGE_REMEDIATION_AUDIT_2026_07.md.
# `targets` and `receiving_air_yards` are essentially untracked in the
# real raw nflverse weekly file for real OBSERVATION seasons 2006-2008
# (see config.DATASET2_SOURCE_A_TARGETS_UNRELIABLE_OBSERVATION_SEASONS's
# own docstring for the real audit numbers) -- every canonical column
# whose real formula divides by, sums, or gates on either field is
# FORCED NULL for `prediction_season` 2007-2009 via the ONE centralized
# `apply_source_coverage_null_mask()` call in
# `build_canonical_predictor_table()` below, never a scattered
# per-column exception.
#
# Deliberately EXCLUDES `fam18_prior_season_catch_rate`/
# `fam18_prior_season_receiving_yards_per_target` -- those were already
# remediated by their OWN dedicated logic in
# `lib/dataset2/receiving_efficiency_traits.py` (unchanged here, so
# this centralized pass never double-transforms an already-correct
# result; nulling an already-null cell would be a harmless no-op
# either way, but exclusion keeps the two mechanisms cleanly separate
# and independently auditable).
SOURCE_A_TARGETS_UNRELIABLE_SRC_COLUMNS = (
    "srcA_prior_season_targets",
    "srcA_prior_season_receiving_air_yards",
    "srcA_prior_season_target_share",
    "srcA_prior_season_air_yards_share",
    "srcA_prior_season_wopr",
)

# Family #9's real EFFICIENCY_METRICS mapping (lib/dataset2/partial_season_traits.py)
# uses `targets` as the receiving-opportunity denominator for RB/WR/TE
# receiving specifically (QB passing uses `attempts`, RB rushing uses
# `carries` -- both unaffected, never included here). Every one of
# these 8 suffixes, per basis, is built FROM that same real
# `targets`-denominated opportunity value -- `_production` (receiving_yards,
# NOT targets) is the one sibling column deliberately NOT listed, per
# the audit.
_FAM9_TARGETS_DEPENDENT_POSITIONS = ("rb", "wr", "te")
_FAM9_TARGETS_DEPENDENT_TEAM_BASIS_SUFFIXES = (
    "receiving_opportunity",
    "receiving_opportunity_per_team_game",
    "receiving_efficiency_rate",
    "receiving_efficiency_volume_eligible_exploratory",
    "receiving_efficiency_volume_eligible_sensitivity",
    "receiving_role_present",
    "receiving_meaningful_role",
    "receiving_strong_lead_role",
)
_FAM9_TARGETS_DEPENDENT_ACTIVE_BASIS_SUFFIXES = (
    "receiving_opportunity",
    "receiving_opportunity_per_active_game",
    "receiving_efficiency_rate",
    "receiving_efficiency_volume_eligible_exploratory",
    "receiving_efficiency_volume_eligible_sensitivity",
    "receiving_role_present",
    "receiving_meaningful_role",
    "receiving_strong_lead_role",
)


def _fam9_targets_dependent_columns(window_ns):
    """Generates the real, targets-dependent family #9 canonical
    column names for exactly the `window_ns` this table was actually
    built with -- NEVER a fixed/hardcoded list, so a future window_n
    (or a test fixture's deliberately narrower `window_ns`) is
    automatically covered without a human remembering to update a
    second list by hand. 8 suffixes x 2 basis x 3 positions x
    len(window_ns) columns -- 144 for the real, approved
    `window_ns=(4, 6, 8)`."""
    cols = []
    for n in window_ns:
        for pos in _FAM9_TARGETS_DEPENDENT_POSITIONS:
            for suffix in _FAM9_TARGETS_DEPENDENT_TEAM_BASIS_SUFFIXES:
                cols.append(f"fam9_team_final_{n}_{pos}_{suffix}")
            for suffix in _FAM9_TARGETS_DEPENDENT_ACTIVE_BASIS_SUFFIXES:
                cols.append(f"fam9_active_final_{n}_{pos}_{suffix}")
    return cols


def build_canonical_predictor_table(
    master_population: pd.DataFrame,
    players_df: pd.DataFrame,
    weekly_all_season_types: pd.DataFrame,
    weekly_reg_only: pd.DataFrame,
    snap_counts_all: pd.DataFrame,
    depth_chart_pre2025_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    window_ns=DEFAULT_WINDOW_NS,
):
    """
    Builds the canonical PRESEASON PREDICTOR table -- one row per
    (`prediction_season`, `player_id`).

    SPINE: the real master population's own (`season`, `player_id`)
    keys (renamed `prediction_season`), UNIONED with any additional
    (`prediction_season`, `player_id`) keys family #9's own
    `build_family9_preseason_features()` produces that the master
    population does not already have -- this is how a real "future"
    prediction_season row (the most recent real observation season +
    1) is retained even though the master population itself only
    covers real, played seasons. For those extra rows, every OTHER
    family's columns are correctly null (no matching population row
    to compute them from -- there is nothing else knowable about a
    genuinely future season except what family #9's own lag already
    captured), NOT a fabricated/guessed value.

    `master_population` must have MASTER_POPULATION_REQUIRED_COLUMNS.
    `schedule_df` must have SCHEDULE_REQUIRED_COLUMNS -- the real
    nflverse `games.csv` (season/game_type/week/gameday/home_team/
    away_team), used for family #2's real per-team Week-1 kickoff date
    (see module docstring's AGE INCLUSION). Passing an empty
    placeholder (`pd.DataFrame(columns=SCHEDULE_REQUIRED_COLUMNS)`) is
    still valid and produces real, disclosed all-null age columns --
    but this function itself never constructs that placeholder; the
    caller decides.
    `weekly_all_season_types` is the FULL real Source A weekly file
    (REG + POST rows both present -- usage_traits.py filters REG
    internally). `weekly_reg_only` is the SAME real source PRE-FILTERED
    to `season_type == "REG"` -- required separately because
    partial_season_traits.py's active-game builders have no
    `season_type` column in their own required-columns contract and do
    not filter it themselves (confirmed by reading that module's code
    this round); passing the unfiltered file to it risks a real
    postseason game silently entering what's meant to be a regular-
    season split.

    Returns (predictor_table, column_registry, deferred_families):
    `predictor_table` sorted by (prediction_season, player_id) with a
    fixed column order (determinism, see module docstring);
    `column_registry` a DataFrame data dictionary (one row per
    canonical column); `deferred_families` = DEFERRED_FAMILIES as a
    DataFrame.
    """
    if "real_status" in master_population.columns:
        raise ValueError(
            "master_population contains outcome-side real_status; predictor-side preseason market "
            "metadata must come from preseason_market_status, never an outcome substitution"
        )
    validate_columns(master_population, MASTER_POPULATION_REQUIRED_COLUMNS, "master_population")
    for column in ("preseason_market_status", "preseason_market_status_sensitivity_30"):
        if master_population[column].isna().any():
            raise ValueError(f"master_population {column} may not be null for historical rows")
        unexpected = sorted(set(master_population[column].astype(str)) - PRESEASON_MARKET_STATUS_VALUES)
        if unexpected:
            raise ValueError(f"master_population {column} contains unknown values: {unexpected}")
    if master_population["preseason_market_status_authority"].isna().any():
        raise ValueError("master_population preseason_market_status_authority may not be null")
    validate_columns(players_df, PLAYERS_REQUIRED_COLUMNS, "players_df")
    validate_columns(schedule_df, SCHEDULE_REQUIRED_COLUMNS, "schedule_df")

    population = master_population[list(MASTER_POPULATION_REQUIRED_COLUMNS)].drop_duplicates(
        subset=["season", "player_id"]
    ).reset_index(drop=True)
    min_season = int(population["season"].min())
    max_season = int(population["season"].max())

    registry_rows = []

    # Built ONCE against the real schedule_df and shared by both the
    # fam1/2/4/6 layer and fam88's body-size-position-z (which only
    # needs the BMI columns, not age itself, but takes the same raw
    # frame rather than recomputing it a second time).
    exp_age_draft_raw = build_experience_age_draft_traits(population, players_df, schedule_df)

    fam1_4_6, reg = _build_fam1_4_6_layer(exp_age_draft_raw, min_season, max_season)
    registry_rows += reg
    fam7, reg = _build_fam7_layer(population, min_season, max_season)
    registry_rows += reg
    fam8_39_44, reg = _build_fam8_39_44_layer(population, min_season, max_season)
    registry_rows += reg
    srcA, srcA_preseason, reg = _build_srcA_layer(population, weekly_all_season_types, min_season, max_season)
    registry_rows += reg
    srcB, raw_matched_snaps, reg = _build_srcB_layer(population, snap_counts_all, players_df, min_season, max_season)
    registry_rows += reg
    fam10, fam86, reg = _build_fam10_86_layer(population, depth_chart_pre2025_df, min_season, max_season)
    registry_rows += reg

    fam88, reg = _build_fam88_layer(exp_age_draft_raw, srcA_preseason, min_season, max_season)
    registry_rows += reg

    fam18, reg = _build_fam18_layer(srcA_preseason, min_season, max_season)
    registry_rows += reg

    # Family #9's own raw_snaps expects matched, renamed rows -- reuse
    # the SAME real matched frame Source B's own preseason layer
    # already built, rather than re-crosswalking a second time.
    fam9_raw_snaps = raw_matched_snaps[raw_matched_snaps["gsis_id"].notna()][
        ["season", "week", "team", "gsis_id", "offense_snaps"]
    ].rename(columns={"gsis_id": "player_id"})

    fam9_observation, fam9_mapping = build_family9_observation_wide(
        population, weekly_reg_only, weekly_all_season_types, fam9_raw_snaps, window_ns=window_ns
    )
    fam9_preseason = build_family9_preseason_features(fam9_observation)
    fam9_registry = [
        _registry_row(
            row["canonical_column"], "9", "Partial-season production splits (lagged, wide)",
            "Source A/B weekly, via lib.dataset2.partial_season_canonical", min_season + 1, max_season + 1,
            "float64/boolean/object (see column name)",
            "See partial_season_canonical.py's own docstring (applicable-zero preserved, "
            "team-game-basis <NA> masking, active-game-basis real zeroes)",
            "prediction_season = observation_season + 1", row["raw_column"],
        )
        for _, row in fam9_mapping.iterrows()
    ]
    registry_rows += fam9_registry
    registry_rows.append(
        _registry_row(
            "fam9_prediction_season_outcome_unavailable", "9 (canonicalization metadata)",
            "Partial-season production splits", "partial_season_canonical.py", min_season + 1, max_season + 1,
            "boolean", "Never null -- True exactly when prediction_season exceeds the max real observation_season",
            "N/A (build metadata)", "fam9_prediction_season_outcome_unavailable",
        )
    )

    # --- Spine: master population's own keys, UNIONED with family #9's real future rows ---
    #
    # Real bug found and fixed this round, running against the full
    # real 2006-2025 population (never triggered by any single-season
    # synthetic fixture): naively adding EVERY family #9 key not
    # already in the spine also added a PHANTOM "if they had played
    # next season" row for every player whose OWN final active season
    # predates the dataset's real max -- e.g. a player who retired
    # after 2015 got a real prediction_season=2016 row with real fam9
    # data, even though 2016 will never have a real outcome for them
    # (they were retired, not "outcome not yet available"). The
    # intended case (per instruction: "the final historical
    # observation season may produce a future prediction-season
    # feature row") is specifically about the DATASET's own overall
    # most recent real season, not every individual player's personal
    # last season -- restricting the extra-key rule to
    # `prediction_season > population's own real max season` keeps
    # exactly the intended case (real count: 609 real 2026 rows against
    # the full real population) and drops the ~2,700 real phantom
    # retired-player rows the naive version produced.
    authority_columns = [
        "canonical_position_status", "canonical_position_authority", "historical_input_revision",
    ]
    spine = population[
        ["season", "player_id", "position"] + authority_columns + list(PRESEASON_MARKET_METADATA_COLUMNS)
    ].rename(
        columns={"season": "prediction_season"}
    )
    fam9_keys = fam9_preseason[["prediction_season", "player_id", "position"]]
    extra_keys = fam9_keys.merge(
        spine[["prediction_season", "player_id"]], on=["prediction_season", "player_id"], how="left", indicator=True
    )
    extra_keys = extra_keys[
        (extra_keys["_merge"] == "left_only") & (extra_keys["prediction_season"] > max_season)
    ][["prediction_season", "player_id", "position"]]
    prior_authority = population[["season", "player_id"] + authority_columns].copy()
    prior_authority["prediction_season"] = prior_authority["season"] + 1
    extra_keys = extra_keys.merge(
        prior_authority[["prediction_season", "player_id"] + authority_columns],
        on=["prediction_season", "player_id"], how="left",
    )
    spine = pd.concat([spine, extra_keys], ignore_index=True).drop_duplicates(subset=["prediction_season", "player_id"])

    out = spine.copy()
    for frame in (fam1_4_6, fam7, fam8_39_44, srcA, srcB, fam10, fam86, fam88, fam18):
        frame = frame.rename(columns={"season": "prediction_season"})
        incoming = set(frame.columns) - {"prediction_season", "player_id"}
        collisions = incoming & (set(out.columns) - {"prediction_season", "player_id", "position", *authority_columns})
        if collisions:
            raise RuntimeError(f"Canonical column-name collision(s): {sorted(collisions)}")
        out = out.merge(frame, on=["prediction_season", "player_id"], how="left")

    fam9_cols = [c for c in fam9_preseason.columns if c not in ("observation_season", "player_id", "prediction_season", "position")]
    collisions = set(fam9_cols) & set(out.columns)
    if collisions:
        raise RuntimeError(f"Canonical column-name collision(s) with family #9: {sorted(collisions)}")
    out = out.merge(
        fam9_preseason[["prediction_season", "player_id", "observation_season"] + fam9_cols],
        on=["prediction_season", "player_id"],
        how="left",
    )

    if len(out.columns) != len(set(out.columns)):
        dupes = out.columns[out.columns.duplicated()].tolist()
        raise RuntimeError(f"Canonical column-name collision(s) detected in final table: {dupes}")

    column_order = (
        ["prediction_season", "player_id", "position"] + authority_columns
        + list(PRESEASON_MARKET_METADATA_COLUMNS) + ["observation_season"]
        + [c for c in fam1_4_6.columns if c not in ("season", "player_id")]
        + [c for c in fam7.columns if c not in ("season", "player_id")]
        + [c for c in fam8_39_44.columns if c not in ("season", "player_id")]
        + [c for c in srcA.columns if c not in ("season", "player_id")]
        + [c for c in srcB.columns if c not in ("season", "player_id")]
        + [c for c in fam10.columns if c not in ("season", "player_id")]
        + [c for c in fam86.columns if c not in ("season", "player_id")]
        + [c for c in fam88.columns if c not in ("season", "player_id")]
        + [c for c in fam18.columns if c not in ("season", "player_id")]
        + fam9_cols
    )
    identity_columns = (
        ["prediction_season", "player_id", "position"] + authority_columns
        + list(PRESEASON_MARKET_METADATA_COLUMNS) + ["observation_season"]
    )
    out = out[identity_columns + [c for c in column_order if c not in identity_columns]]
    out = out.sort_values(["prediction_season", "player_id"]).reset_index(drop=True)

    # --- Source A targets/receiving_air_yards coverage remediation ---
    # ONE centralized, auditable mask -- see SOURCE_A_TARGETS_UNRELIABLE_SRC_COLUMNS/
    # _fam9_targets_dependent_columns()'s own docstrings above for the
    # full real dependency inventory and rationale.
    source_a_targets_unreliable_prediction_seasons = tuple(
        s + 1 for s in DATASET2_SOURCE_A_TARGETS_UNRELIABLE_OBSERVATION_SEASONS
    )
    source_a_targets_unreliable_columns = list(SOURCE_A_TARGETS_UNRELIABLE_SRC_COLUMNS) + _fam9_targets_dependent_columns(
        window_ns
    )
    out = apply_source_coverage_null_mask(
        out,
        source_a_targets_unreliable_columns,
        source_a_targets_unreliable_prediction_seasons,
        "prediction_season",
        reason=DATASET2_SOURCE_A_TARGETS_COVERAGE_REASON,
    )
    for row in registry_rows:
        if row["canonical_column"] in source_a_targets_unreliable_columns:
            row["missingness_semantics"] = (
                row["missingness_semantics"]
                + f"; ALSO forced null for prediction_season in {source_a_targets_unreliable_prediction_seasons} "
                f"(real, audited Source A coverage gap -- reason: {DATASET2_SOURCE_A_TARGETS_COVERAGE_REASON!r}, "
                "see research/dataset2/SOURCE_A_TARGETS_COVERAGE_REMEDIATION_AUDIT_2026_07.md)"
            )

    registry_rows.insert(
        0,
        _registry_row(
            "prediction_season", "N/A (spine)", "Table identity", "master population / family #9 union",
            min_season + 1, max_season + 1, "int64", "Never null (spine key)", "N/A (identity)", "season",
        ),
    )
    registry_rows.insert(
        1,
        _registry_row(
            "player_id", "N/A (spine)", "Table identity", "master population / family #9 union",
            min_season, max_season + 1, "object", "Never null (spine key)", "N/A (identity)", "player_id",
        ),
    )
    registry_rows[2:2] = [
        _registry_row(
            "position", "N/A (spine)", "Table identity", "master population / family #9 union",
            min_season, max_season + 1, "object", "Never null (spine key)", "N/A (identity)", "position",
        ),
        _registry_row(
            "canonical_position_status", "N/A (spine)", "Position-authority provenance",
            "master population / prior observation for future application rows",
            min_season, max_season + 1, "object", "Never null for resolved rows",
            "N/A (identity metadata)", "canonical_position_status",
        ),
        _registry_row(
            "canonical_position_authority", "N/A (spine)", "Position-authority provenance",
            "master population / prior observation for future application rows",
            min_season, max_season + 1, "object", "Never null for resolved rows",
            "N/A (identity metadata)", "canonical_position_authority",
        ),
        _registry_row(
            "historical_input_revision", "N/A (spine)", "Input-governance revision",
            "master population / prior observation for future application rows",
            min_season, max_season + 1, "object", "Never null",
            "Metadata only; prohibited as a model predictor", "historical_input_revision",
        ),
        _registry_row(
            "preseason_market_status", "N/A (preseason control)",
            "Preseason acquisition-cost control", "governed master player-season input",
            min_season, max_season, "object",
            "Never null for historical master rows; future application-only rows may be null",
            "Same-season preseason evidence; control only, never a candidate predictor",
            "preseason_market_status",
        ),
        _registry_row(
            "preseason_market_status_sensitivity_30", "N/A (preseason metadata)",
            "Preseason acquisition-cost sensitivity metadata", "governed master player-season input",
            min_season, max_season, "object",
            "Never null for historical master rows; future application-only rows may be null",
            "Metadata for the governed 30% sensitivity; prohibited as a candidate predictor",
            "preseason_market_status_sensitivity_30",
        ),
        _registry_row(
            "preseason_market_status_authority", "N/A (preseason metadata)",
            "Preseason acquisition-cost provenance", "governed master player-season input",
            min_season, max_season, "object",
            "Never null for historical master rows; future application-only rows may be null",
            "Provenance metadata; prohibited as a model predictor",
            "preseason_market_status_authority",
        ),
        _registry_row(
            "preseason_market_status_evidence_source", "N/A (preseason metadata)",
            "Preseason acquisition-cost provenance", "governed master player-season input",
            min_season, max_season, "object",
            "May be null when no manual evidence source applies",
            "Provenance metadata; prohibited as a model predictor",
            "preseason_market_status_evidence_source",
        ),
        _registry_row(
            "preseason_market_status_evidence_summary", "N/A (preseason metadata)",
            "Preseason acquisition-cost provenance", "governed master player-season input",
            min_season, max_season, "object",
            "May be null when no manual evidence summary applies",
            "Provenance metadata; prohibited as a model predictor",
            "preseason_market_status_evidence_summary",
        ),
    ]
    registry_rows.insert(
        11,
        _registry_row(
            "observation_season", "N/A (spine)", "Table identity",
            "family #9's own observation season (see partial_season_canonical.py)",
            min_season, max_season, "int64",
            "Always prediction_season - 1 when present; null for any row with no real family #9 "
            "observation data",
            "N/A (identity)", "observation_season",
        ),
    )

    column_registry = pd.DataFrame(registry_rows)
    column_registry["position_scope"] = column_registry["canonical_column"].apply(_infer_position_scope)
    deferred_families = pd.DataFrame(DEFERRED_FAMILIES)
    return out, column_registry, deferred_families
