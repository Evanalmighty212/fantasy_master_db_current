"""
lib/dataset2/common.py

Shared utilities used by every Dataset 2 trait-construction module --
extracted 2026-07 when lag_join()'s logic was about to be duplicated a
second time (prior_finish_traits.py needing exactly what
prior_season_traits.py already had) and validate_columns() a fourth
time. Not a speculative abstraction -- real, exact duplication that
had already happened once and was about to happen again.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_END_SEASON,
    DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_START_SEASON,
    DATASET2_PREDICTOR_CLUSTERING_HISTORICAL_RANGE_END_SEASON,
    DATASET2_PREDICTOR_CLUSTERING_HISTORICAL_RANGE_START_SEASON,
    SBV_SEASON_LENGTH_16_GAME,
    SBV_SEASON_LENGTH_17_GAME,
    SBV_SEASON_LENGTH_ERA_CUTOFF,
    validate_dataset2_predictor_clustering_config,
)
from lib.player_season_authority import FRANCHISE_TEAM_ERAS, canonical_team

# family_number tag for identity/spine columns in the canonical
# predictor table's own data dictionary (prediction_season, player_id,
# position, observation_season) -- see
# lib/dataset2/analysis_view.py::_predictor_role(), which encodes the
# same real distinction for the analysis-view whitelist. Kept as its
# own constant here (not re-imported from analysis_view.py) since
# derive_predictor_whitelist_from_registry() below deliberately never
# reads the analysis view or anything view-derived.
DATASET2_SPINE_FAMILY_NUMBER = "N/A (spine)"


def season_length(season: int) -> int:
    """Real NFL season length by era -- 17 from
    config.SBV_SEASON_LENGTH_ERA_CUTOFF onward, 16 before. Reuses the
    SBV_* config constants directly (this is the same verified
    real-world fact SBV's own lib/stars_by_value/production.py::season_length()
    encodes, not a Dataset-2-specific number) rather than duplicating
    the era-cutoff literal in a second place.

    THIS IS REAL GAMES PLAYED, NOT THE MAXIMUM REAL REG WEEK NUMBER --
    see real_reg_week_slots() below. Using this function's return value
    directly as a max-week bound is a real, previously-committed bug
    (lib/dataset2/partial_season_traits.py, found and fixed 2026-07,
    see research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md):
    real REG week NUMBERS run 1..season_length(season)+1, one higher
    than the games-played count, because every team's real bye week
    consumes a week number without being a played game (verified
    directly: real 2015 weeks run 1-17 despite season_length(2015)==16;
    real 2021 weeks run 1-18 despite season_length(2021)==17)."""
    return SBV_SEASON_LENGTH_17_GAME if season >= SBV_SEASON_LENGTH_ERA_CUTOFF else SBV_SEASON_LENGTH_16_GAME


def real_reg_week_slots(season: int) -> int:
    """The real maximum REG week NUMBER for `season` -- season_length(season)
    + 1, accounting for the one week-number slot every team's real bye
    consumes without a played game. THE SHARED, CANONICAL way to bound
    or classify a real `week` column anywhere in Dataset 2 -- e.g. "is
    this week real postseason" (`week > real_reg_week_slots(season)`,
    the exact rule already proven in participation_traits.py's real
    2016/2022 week-range checks) or "what's the real week-number
    ceiling for this season." Do NOT use season_length() directly for
    this -- see that function's own docstring for the real bug this
    helper exists to prevent from recurring in a second module."""
    return season_length(season) + 1


def validate_columns(df: pd.DataFrame, required, label: str) -> None:
    """Fail-loud required-column check, shared by every Dataset 2
    trait/analysis module's public entry point."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


# Real, VERIFIED historical NFL franchise relocations where the real
# nflverse schedule file's own historical team code differs from this
# project's population team code for the SAME franchise in the SAME
# real season -- confirmed 2026-07 by auditing every population team
# code with no real Week-1 schedule match across all seasons (found
# exactly 5 unmatched codes: LV/LA/LAC, always relocation-driven, plus
# MIA/TB in 2017 specifically -- a real, unrelated case, see below).
# Season ranges are the real, non-overlapping eras each historical code
# was actually used in schedule_df, verified directly against every
# real season the code appears in (never assumed/approximated):
#   OAK appears in schedule_df for 1999-2019 only, LV for 2020+ only.
#   STL appears in schedule_df for 1999-2015 only, LA for 2016+ only.
#   SD  appears in schedule_df for 1999-2016 only, LAC for 2017+ only.
# This project's population team column always uses the CURRENT code
# (LV/LA/LAC) for every historical season -- never the historical code
# -- so this table only needs to translate schedule_df's historical
# code into the population's current code at lookup time.
#
# NOT a relocation case, deliberately NOT in this table: MIA and TB
# have real, genuine null Week-1 kickoffs for the 2017 season only --
# their real Week 1 game was postponed league-wide due to Hurricane
# Irma and never replayed as a real "Week 1" game (their real first
# games of that season were Week 2). This is real missing schedule
# data, not a team-code mismatch -- resolving it would mean guessing a
# kickoff date that was never real, which this module's own
# MISSINGNESS POLICY (see experience_age_draft.py) explicitly forbids.
HISTORICAL_TEAM_CODE_ALIASES = tuple(
    (current, historical, first, last)
    for historical, current, first, last in FRANCHISE_TEAM_ERAS
)


def _canonicalize_historical_team_code(team: str, season: int) -> str:
    """If `team` is a real, verified historical schedule code for
    `season` (see HISTORICAL_TEAM_CODE_ALIASES), returns this
    project's current/population code for the same real franchise --
    otherwise returns `team` unchanged. Deterministic (a pure function
    of `team` and `season`, no randomness/iteration-order dependence)
    and season-aware (only fires within each alias's own real,
    verified season range -- e.g. "OAK" in 2020 is NOT translated,
    since the real Raiders schedule code by then was already "LV").
    Used ONLY inside week1_kickoff_by_team()'s own per-season kickoff
    lookup -- never mutates schedule_df or population's own `team`
    column, and never touches any OTHER canonical team identity."""
    for current_code, historical_code, first_season, last_season in HISTORICAL_TEAM_CODE_ALIASES:
        if team == historical_code and first_season <= season <= last_season:
            return current_code
    return team


def canonicalize_team_column(df: pd.DataFrame, team_column="team") -> pd.DataFrame:
    """Return a copy with season-accurate canonical franchise codes.
    The caller's raw provider frame remains unchanged for provenance."""
    validate_columns(df, ("season", team_column), "team-coded source")
    out = df.copy()
    out[team_column] = [canonical_team(team, season) for team, season in zip(out[team_column], out["season"])]
    return out


def week1_kickoff_by_team(schedule_df: pd.DataFrame, season: int) -> dict:
    """Real per-team Week-1 REG-season kickoff date for `season`, keyed
    by team code -- same convention already proven in
    lib.stars_by_value.acquisition_cost.apply_rookie_qb_depth_chart_correction()
    (a real per-team date, not a shared project-wide approximation like
    "Sept 1"). A team with no Week-1 REG game in `schedule_df` for this
    season is simply absent from the returned dict -- the caller treats
    that as "kickoff date unknown" (null downstream), not an error.
    Extracted 2026-07 when a second Dataset 2 module
    (depth_chart_traits.py) needed exactly this logic, after
    experience_age_draft.py already had it.

    Each real Week-1 game's raw team code is kept in the returned dict
    AS-IS, and ALSO registered under its real, verified current/
    population code if the two differ for this season (see
    HISTORICAL_TEAM_CODE_ALIASES/_canonicalize_historical_team_code()
    above) -- additive, never a replacement, so either convention
    resolves to the same real date. Any other unmatched code (e.g. a
    team with a real, genuine schedule gap that season) is simply
    absent, exactly as before -- never guessed."""
    week1 = schedule_df[
        (schedule_df["season"] == season) & (schedule_df["game_type"] == "REG") & (schedule_df["week"] == 1)
    ]
    kickoff = {}
    for _, row in week1.iterrows():
        gameday = pd.to_datetime(row["gameday"])
        raw_home, raw_away = row["home_team"], row["away_team"]
        kickoff[raw_home] = gameday
        kickoff[raw_away] = gameday
        canon_home = _canonicalize_historical_team_code(raw_home, season)
        canon_away = _canonicalize_historical_team_code(raw_away, season)
        if canon_home != raw_home:
            kickoff[canon_home] = gameday
        if canon_away != raw_away:
            kickoff[canon_away] = gameday
    return kickoff


def kickoff_lookup_table(schedule_df: pd.DataFrame, seasons) -> pd.DataFrame:
    """season/team/kickoff_date rows for every season in `seasons`,
    built by calling week1_kickoff_by_team() once per season (not once
    per population row -- that would recompute the same per-season
    dict thousands of times). Real, found bug fixed 2026-07: when
    `schedule_df` has zero real matching rows for every season
    requested (e.g. a genuinely empty `schedule_df` -- a real,
    disclosed environment gap, see
    research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md), the old
    empty-case `pd.DataFrame(columns=[...])` left `_kickoff_date` as
    object dtype with zero rows; merging that onto a real, non-empty
    population produced a NaN column that was NOT datetime64, and
    `experience_age_draft.py`'s own `_kickoff_date - birth_date`
    subtraction crashed with a real TypeError instead of producing the
    correct, real all-null `age_at_week1_years` result. Explicit dtypes
    below fix this without changing any real, non-empty-schedule
    behavior."""
    frames = []
    for season in sorted(set(seasons)):
        kickoff = week1_kickoff_by_team(schedule_df, season)
        if kickoff:
            frames.append(
                pd.DataFrame({"season": season, "team": list(kickoff.keys()), "_kickoff_date": list(kickoff.values())})
            )
    if not frames:
        return pd.DataFrame(
            {
                "season": pd.Series(dtype="int64"),
                "team": pd.Series(dtype="object"),
                "_kickoff_date": pd.Series(dtype="datetime64[ns]"),
            }
        )
    return pd.concat(frames, ignore_index=True)


def lag_join(df: pd.DataFrame, value_col: str, lag: int) -> pd.Series:
    """Value of `value_col` for this player at `season - lag`, aligned
    to df's row order via an explicit key-based merge (never positional
    alignment -- two independently-deduplicated frames are not
    guaranteed to share row order). `df` must have one row per
    (season, player_id) and must include `season`, `player_id`, and
    `value_col`. A player with no row at season-lag (rookie, or a
    genuine gap in the population) gets NaN -- never zero-filled or
    guessed."""
    lookup = df[["season", "player_id", value_col]].copy()
    lookup["season"] = lookup["season"] + lag
    lookup = lookup.rename(columns={value_col: "_lagged_value"})
    merged = df[["season", "player_id"]].merge(lookup, on=["season", "player_id"], how="left")
    return merged["_lagged_value"]


def build_team_game_index(weekly_all_positions: pd.DataFrame) -> pd.DataFrame:
    """Real (season, team, week) -> chronological `team_game_index`
    (1..G) and `team_total_games` (G), derived from the real REG weeks
    where AT LEAST ONE player recorded a real weekly row for that team
    -- no separate schedule fetch needed. `weekly_all_positions` must be
    the FULL weekly file (every position, not just skill positions --
    restricting first risks missing a real team-week, the same real
    risk already documented in Source A's own team-week-denominator
    audit) with at least `season`, `week`, `team`, `season_type`
    columns; filtered to REG internally.

    Verified directly against real data before this was written: a
    team's real REG week COUNT from this method exactly matches
    season_length(season) for every real team-season checked (real
    2015: 16; real 2021: 17) -- a real bye week correctly produces a
    gap in the raw week numbers (e.g. real 2015 New England: weeks
    1,2,3,5,6,...,17 -- week 4 is the real bye, absent, not a zero-row
    placeholder), which ranking the existing weeks 1..G correctly
    compresses out. This is the real, general building block for every
    Dataset 2 team-game-sequence window (final-N team games,
    team-game-index half-split) -- see partial_season_traits.py.
    """
    validate_columns(weekly_all_positions, ("season", "week", "team", "season_type"), "weekly_all_positions")

    reg = weekly_all_positions[weekly_all_positions["season_type"] == "REG"]
    team_weeks = reg[["season", "team", "week"]].drop_duplicates().sort_values(["season", "team", "week"])

    team_weeks["team_game_index"] = team_weeks.groupby(["season", "team"]).cumcount() + 1
    team_weeks["team_total_games"] = team_weeks.groupby(["season", "team"])["team_game_index"].transform("max")

    return team_weeks.reset_index(drop=True)


def within_group_zscore(df: pd.DataFrame, value_col: str, group_col: str) -> pd.Series:
    """How many standard deviations this row's value_col sits from the
    mean for its group_col, computed over the population passed in.
    NaN input propagates to NaN output -- never imputed. A group with
    zero variance (e.g. a single-row group) produces NaN for that
    group rather than a divide-by-zero, which is disclosed
    missingness, not a bug. Extracted 2026-07 when a second Dataset 2
    module (fragility_traits.py) needed exactly this position-adjusted
    pattern, after experience_age_draft.py already had it."""
    grouped = df.groupby(group_col)[value_col]
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0, float("nan"))
    return (df[value_col] - mean) / std


def apply_source_coverage_null_mask(
    df: pd.DataFrame, columns, affected_seasons, season_column: str, reason: str = None
) -> pd.DataFrame:
    """CENTRALIZED source-coverage remediation -- forces every column
    in `columns` to real null for every row where `df[season_column]`
    is in `affected_seasons`, dtype-aware (pandas nullable "boolean"
    columns get `pd.NA`, everything else gets `np.nan`) so a real
    unsupported-coverage row is NEVER misread as a real `False` or a
    real `0.0`. Extracted 2026-07 for the Source A
    targets/receiving_air_yards 2006-2008 remediation
    (research/dataset2/SOURCE_A_TARGETS_COVERAGE_REMEDIATION_AUDIT_2026_07.md)
    specifically so a single, auditable mechanism governs every
    affected column, rather than N separate hardcoded exceptions
    scattered across N builder functions -- any FUTURE target-derived
    predictor only needs to be added to its caller's own column list
    passed into this function, never a new bespoke masking
    implementation.

    Mutates and returns `df` (same convention as `_cast_boolean_columns`
    in canonical_predictor_table.py) -- callers that need the original
    unmasked frame should pass a copy. `reason` is accepted for
    call-site self-documentation only (e.g.
    `config.DATASET2_SOURCE_A_TARGETS_COVERAGE_REASON`) -- not stored
    on the frame itself, since this project's column registry (not the
    data) is where a missingness reason is recorded per column (see
    each `_registry_row()` call site's own `missingness_semantics`
    field).

    Raises loudly if `season_column` or any requested column is
    missing -- never silently no-ops on a caller typo."""
    if season_column not in df.columns:
        raise ValueError(f"apply_source_coverage_null_mask: {season_column!r} not in df.columns")
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"apply_source_coverage_null_mask: columns not in df: {sorted(missing)}")

    mask = df[season_column].isin(affected_seasons)
    for col in columns:
        if str(df[col].dtype) == "boolean":
            df.loc[mask, col] = pd.NA
        else:
            df.loc[mask, col] = np.nan
    return df


def _validated_prediction_season(predictor_df: pd.DataFrame, caller: str) -> pd.Series:
    """Shared, strengthened `prediction_season` validation for every
    Dataset 2 predictor-clustering season selector -- a single place
    so the two selectors below can never drift apart on what counts as
    a valid season. Raises loudly -- never silently drops or coerces
    -- on any of:

    - column missing entirely
    - boolean dtype (pandas classifies bool as "numeric," which would
      otherwise silently pass a plain is_numeric_dtype check)
    - any other non-numeric dtype (e.g. strings like "2006")
    - any null value
    - any non-finite value (inf/-inf)
    - any non-integer-valued entry (e.g. 2006.5) -- a real season
      number is always a whole year, never a fraction

    Returns the original `prediction_season` Series unchanged (its own
    dtype, not coerced) for the caller to build a boolean mask from --
    the float64 conversion above is a temporary internal copy used only
    for the finite/integer-value checks, never returned."""
    if "prediction_season" not in predictor_df.columns:
        raise ValueError(f"{caller}: 'prediction_season' not in predictor_df.columns")
    season = predictor_df["prediction_season"]
    if pd.api.types.is_bool_dtype(season) or not pd.api.types.is_numeric_dtype(season):
        raise ValueError(f"{caller}: 'prediction_season' must be numeric, got dtype {season.dtype}")
    if season.isna().any():
        raise ValueError(f"{caller}: 'prediction_season' contains null values")
    numeric = season.astype("float64")
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError(f"{caller}: 'prediction_season' contains non-finite values (inf/-inf)")
    if not (numeric == numeric.round()).all():
        raise ValueError(f"{caller}: 'prediction_season' contains non-integer-valued entries")
    return season


def filter_to_discovery_fit_predictor_rows(predictor_df: pd.DataFrame) -> pd.DataFrame:
    """The ONE, centralized discovery-fit row selector for Dataset 2
    predictor-clustering work (predictor inventory, similarity,
    near-duplicate, redundancy, clustering, representative selection)
    -- methodology locked 2026-07, see
    docs/LEAGUE_WINNER_TRAITS_SPEC.md's "Predictor-clustering
    discovery/holdout boundary" section (commit 648ccad).

    Selection depends SOLELY on `prediction_season`, restricted to
    [DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_START_SEASON,
    ..._END_SEASON] inclusive -- never `outcome_join_status` or any
    outcome/label/target/eligibility field. This is enforced
    structurally, not just behaviorally: `predictor_df` is expected to
    be (or behave like) the canonical predictor table itself, which
    has no such column at all -- callers must never pass the joined
    analysis view here. Even a caller who mutates in extra
    outcome-shaped columns onto `predictor_df` cannot change this
    function's row selection, since only `prediction_season` is ever
    read.

    Pure: does not mutate `predictor_df` (returns a copy), preserves
    original row order and every column. See
    _validated_prediction_season() for the exact malformed-input
    rejection rules."""
    season = _validated_prediction_season(predictor_df, "filter_to_discovery_fit_predictor_rows")
    validate_dataset2_predictor_clustering_config()
    start = DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_START_SEASON
    end = DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_END_SEASON
    mask = (season >= start) & (season <= end)
    return predictor_df.loc[mask].copy()


def filter_to_historical_predictor_rows(predictor_df: pd.DataFrame) -> pd.DataFrame:
    """Positive, explicit selector for the full HISTORICAL predictor
    population -- prediction_season in
    [DATASET2_PREDICTOR_CLUSTERING_HISTORICAL_RANGE_START_SEASON,
    ..._END_SEASON] inclusive (2006-2025 as configured). Used ONLY as
    the comparator population for classify_column_constancy()'s
    discovery_fit_degenerate detection -- never for clustering fit
    itself (see filter_to_discovery_fit_predictor_rows() for that).

    Deliberately POSITIVE, not "every row except 2026": a negative/
    exclusionary definition would silently include any future stray
    out-of-range row (a pre-2006 or post-2026 data error) instead of
    excluding it. Same outcome-independence guarantee as
    filter_to_discovery_fit_predictor_rows() -- selection depends
    solely on `prediction_season`, never any outcome-side column.

    Pure: does not mutate `predictor_df` (returns a copy), preserves
    original row order and every column. See
    _validated_prediction_season() for the exact malformed-input
    rejection rules."""
    season = _validated_prediction_season(predictor_df, "filter_to_historical_predictor_rows")
    validate_dataset2_predictor_clustering_config()
    start = DATASET2_PREDICTOR_CLUSTERING_HISTORICAL_RANGE_START_SEASON
    end = DATASET2_PREDICTOR_CLUSTERING_HISTORICAL_RANGE_END_SEASON
    mask = (season >= start) & (season <= end)
    return predictor_df.loc[mask].copy()


def derive_predictor_whitelist_from_registry(registry: pd.DataFrame) -> list:
    """Mechanically derives the predictor-column whitelist from the
    canonical predictor table's own data dictionary
    (`canonical_column`/`family_number`), excluding identity/spine
    fields (`family_number == DATASET2_SPINE_FAMILY_NUMBER`) -- never a
    hand-maintained list, and never the analysis-view whitelist (which
    is derived from the joined view, not the predictor table alone).

    Sorted for deterministic downstream iteration order -- this
    project's own documented hash-randomization determinism bug (see
    research/dataset2/trait_analysis_pipeline_predictor_inventory.py's
    module docstring) makes unsorted set/list construction a real,
    previously-caught failure mode here, not a hypothetical one."""
    validate_columns(registry, ("canonical_column", "family_number"), "registry")
    return sorted(
        registry.loc[registry["family_number"] != DATASET2_SPINE_FAMILY_NUMBER, "canonical_column"].tolist()
    )


def classify_column_constancy(full_range_df: pd.DataFrame, fit_df: pd.DataFrame, columns) -> dict:
    """Per-column constancy classification across two populations of
    the SAME predictor table -- never conflates a column that is
    constant everywhere with one that is only constant within the
    narrower discovery-fit window. Returns {column: status}, where
    status is one of:

    - "varies": more than one real non-null value in `fit_df`.
    - "universally_constant": at most one real non-null value in BOTH
      `full_range_df` and `fit_df`.
    - "discovery_fit_degenerate": at most one real non-null value in
      `fit_df` but genuine variance (more than one real non-null
      value) in `full_range_df` -- real information exists for this
      column, it simply doesn't vary within the approved discovery
      window. Must be reported as its own status, never silently
      folded into "universally_constant" or omitted from an inventory
      that reports constant columns."""
    result = {}
    for col in columns:
        fit_n = fit_df[col].dropna().nunique()
        if fit_n > 1:
            result[col] = "varies"
            continue
        full_n = full_range_df[col].dropna().nunique()
        result[col] = "discovery_fit_degenerate" if full_n > 1 else "universally_constant"
    return result
