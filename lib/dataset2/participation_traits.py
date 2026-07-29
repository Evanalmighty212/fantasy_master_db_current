"""
lib/dataset2/participation_traits.py

Dataset 2 opportunity/usage foundation, Source C Stage 1 -- APPROVED
(2026-07) in a NARROWED FOUNDATION ROLE, after a real-data review (see
research/dataset2/PARTICIPATION_SOURCE_SCOPE_ASSESSMENT_2026_07.md).
This module builds and preserves: raw play-level acquisition, explicit
schema-version handling, and normalized player-play-role participation
(with identity and duplicate-source-ID auditing in
`participation_identity.py` and `build_duplicate_source_id_report()`
below). It does NOT build any season-level trait or preseason predictor
feature -- see "WHAT WAS REMOVED" below.

NO APPROVED FIRST-WAVE DATASET 2 TRAIT CURRENTLY REQUIRES THIS MODULE.
It is retained as COVERAGE-LIMITED INFRASTRUCTURE for later, narrowly
scoped research that several later taxonomy hypotheses may plausibly
use: personnel/formation context, with/without-player analysis,
targeted-route-type outcomes, defenders-in-box context, and
pass-rusher-count context (all real fields this source uniquely
carries -- `offense_formation`/`offense_personnel`/`defense_personnel`/
`defenders_in_box`/`number_of_pass_rushers`/`route`, none of which exist
in Source A or B). None of these are implemented as traits yet.

ROUTE PARTICIPATION IS NOT SUPPORTED BY THIS SOURCE. Do not implement
or imply complete routes run, route participation, routes per
dropback, targets per route run, or alignment shares from
`pbp_participation` -- `route` is a real PLAY-level field describing
only the targeted receiver's route type, not a per-player list. Those
remain unavailable without a different source. See
research/dataset2/PARTICIPATION_ROUTE_DEFINITION_PROPOSAL_2026_07.md
for the full investigation. Family #9 thresholds are also out of scope
for this module.

WHAT WAS REMOVED (2026-07) AND WHY -- `build_season_participation_summary()`
and `build_preseason_participation_features()` (the season/preseason
possession-side aggregate layer) have been REMOVED from this module,
per an explicit decision, not left as dead code or a TODO. They
duplicated Source B's `snap_traits.py` season aggregates with WEAKER
and potentially MISLEADING possession-side semantics (see "REAL
FINDING" below): no reliable scrimmage-vs-special-teams split exists
in this source (tested and rejected -- see "SCRIMMAGE-VS-SPECIAL-TEAMS
SPLIT" below), so a `possession_side_plays_participated` season total
conflates true offensive scrimmage snaps with special-teams snaps
where the player's team had the ball, and would misrepresent player
usage if exposed as a preseason feature. **Source B remains the
canonical source for actual offensive snap counts and offensive snap
percentages.** Do not reintroduce a season/preseason possession-side
aggregate in this module without a new, explicit decision -- see
research/dataset2/PARTICIPATION_SOURCE_SCOPE_ASSESSMENT_2026_07.md for
the full rationale.

GRAIN, real and verified (research/dataset2/PARTICIPATION_SCHEMA_AUDIT_2026_07.md
has the full report):
- RAW input: one row per real PLAY (`nflverse_game_id` + `play_id`) --
  NOT per player-week, a real, structural difference from
  snap_counts/stats_player. Zero real duplicate (game_id, play_id)
  rows found in the full real 2016-2025 population; this module
  ACTIVELY CHECKS for one on every call and raises if found, per the
  same "duplicated/misaligned records are a top real risk" instruction
  already applied to Source B.
- NORMALIZED output: AT MOST one row per real (game_id, play_id,
  gsis_id, role) -- see "DUPLICATE SOURCE IDS" below for how a real,
  repeated ID within one play's own source list is collapsed to a
  single row rather than one row per raw occurrence.

NO SEASON/WEEK/GAME_TYPE COLUMN EXISTS in the raw source -- both are
derived from `nflverse_game_id` ("{season}_{week_token}_{away}_{home}",
verified real format). Postseason rows are NOT separately labeled; a
real `week_token` beyond that season's real REG week-slot count
(`lib.dataset2.common.season_length(season) + 1`, the same real
"+1 for the bye slot" fact already established for Source A) is a
real playoff game -- verified directly against real 2016 (week tokens
01-21) and 2022 (01-22) data. Excluded by default, per instruction;
`include_postseason=True` is available for a future analysis that
explicitly wants it.

TEAM ATTRIBUTION -- verified structurally sound, no crosswalk or
team-following logic needed (unlike Source B): `possession_team` is a
real PLAY-level field (which team has the ball on THIS specific play).
A possession-side row's team is `possession_team`; a non-possession-
side row's team is whichever of the two real game teams (parsed from
`nflverse_game_id`'s away/home tokens) is NOT `possession_team`. A
traded player is handled correctly for free -- each of their real
plays already carries its own real team attribution, there is no
separate player-to-team mapping to keep in sync.

REAL FINDING, WHY THIS MODULE USES "POSSESSION SIDE," NOT "OFFENSE"/
"DEFENSE" -- confirmed directly against a real row (Mecole Hardman,
2023 WK7 LAC@KC, play 205): on a real special-teams down, the source's
`defense_players` list is simply "the non-possessing team's
personnel," which includes real punt/kick RETURN-team players -- a
real WR return specialist shows up in that list even though he
obviously never played real defense. The `role` values on normalized
rows (`ROLE_POSSESSION`/`ROLE_NON_POSSESSION`) are named for exactly
this reason -- they mean which side of the ball a player's team was on
for a given real play, scrimmage or special teams alike,
undifferentiated, NOT literal football offense/defense. **Source B
remains the canonical source for actual offensive snap counts and
percentages** -- normalized rows from this module are not a substitute
and should not be aggregated into an offense/defense-snap-equivalent
count without accounting for this real semantic difference (this is
exactly why the season aggregate layer that used to do that was
removed -- see "WHAT WAS REMOVED" above).

SCRIMMAGE-VS-SPECIAL-TEAMS SPLIT -- INVESTIGATED, FOUND NOT RELIABLE,
NOT DERIVED. Tested two real candidate play-type filters against the
full real 2023 season before deciding: (1) `offense_formation` null as
a special-teams proxy, and (2) presence of a real specialist position
(P/K/LS) in `offense_positions`/`defense_positions` (26-column schema
only). Both were REJECTED: of the 9,209 real 2023 rows with a null
`offense_formation`, only 4,867 (52.9%) actually contain a real
specialist position -- the other 4,342 are null-formation rows with
completely ordinary offensive personnel (the single most common one,
"1 C, 2 G, 1 QB, 1 RB, 2 T, 1 TE, 3 WR" -- standard 11 personnel --
appears 479 times with a null formation, and those rows show
`number_of_pass_rushers == 0`/`defenders_in_box == 0`/`time_to_throw`
almost always null too, consistent with real RUN plays that simply
never got a formation tag, not special-teams plays). `offense_formation`
nullness reflects real NGS tracking-coverage GAPS in general, not play
type specifically, and the specialist-position signal only exists for
the 26-column (2023+) schema, not uniformly across 2016-2025. Per the
same reconstruct-or-defer rule already applied to Source A's `racr`
and Source B's `defense_pct`/`st_pct`: since no reliable real split was
found, no scrimmage-vs-special-teams trait is derived by this module.
`offense_formation`/`offense_personnel`/`defense_personnel`/
`defenders_in_box`/`number_of_pass_rushers` remain real, useful PLAY-
level context fields for future narrowly scoped research even though
they cannot reliably classify play type on their own.

REAL SCHEMA FORK AT 2023 -- see scripts/nflverse_source.py's own
PBP_PARTICIPATION_SCHEMA_FORK_SEASON comment for the full real
finding. This module supports BOTH real shapes: the 20-column shape
(real for 2016-2022) exposes only player IDs; the 26-column shape
(real for 2023-2025, the canonical file for season 2023) additionally
exposes real per-participant `names`/`positions`/`numbers`, verified
to be list-length-aligned with the player-ID list on every real row
checked (0/20,000 mismatches). Optional fields are null when the
source schema doesn't provide them, never fabricated.

SEMICOLON-LIST PARSING -- every edge case the instructions required is
tested; real occurrence rates (full real 2016-2025 population,
9,455,530 normalized rows) are stated explicitly, not assumed zero:
- Malformed token (doesn't match the real `00-XXXXXXX` gsis_id shape):
  **0 real occurrences**. If one ever occurs, it is KEPT with
  `has_malformed_token = True`, not dropped and not raised on.
- An ID appearing in BOTH offense_players and defense_players on one
  play: **0 real occurrences**. If one ever occurs, both role-rows get
  `cross_role_conflict = True` -- never silently resolved to one side.
- A player's real `gsis_id` not found in the population is preserved,
  never dropped -- see `participation_identity.py`.

DUPLICATE SOURCE IDS -- a REAL, NONZERO finding (470 real occurrences
across 2016-2025, 467 of them concentrated in 2019 -- see
PARTICIPATION_SCHEMA_AUDIT_2026_07.md for the full real investigation).
The raw source list is preserved completely unchanged in
`build_raw_play_data()`'s output. `normalize_participation()` collapses
a real repeated ID within one play's own source list to exactly ONE
output row (never one row per raw occurrence, so it structurally
cannot inflate a downstream count), while still disclosing the anomaly
on that one row:
- `source_occurrence_count`: how many times this ID appeared in the
  real raw list for this (play, role) -- 1 for the overwhelming
  majority of real rows, >1 only for the 470 real exceptions.
- `had_duplicate_source_id`: `source_occurrence_count > 1`.
When a duplicated ID's extended-schema fields (name/position/number)
differ across its raw occurrences, the FIRST real occurrence's values
are kept -- a documented, arbitrary-but-consistent choice, not a
reconciliation attempt. `build_duplicate_source_id_report()` reports
this anomaly by season and by role (whichever real source list --
`offense_players` or `defense_players` -- it occurred in).

TWO STRUCTURALLY SEPARATE THINGS THIS MODULE BUILDS:
1. RAW PLAY-LEVEL DATA (`build_raw_play_data()`).
2. NORMALIZED PLAYER-PLAY-ROLE PARTICIPATION (`normalize_participation()`),
   plus its own duplicate-source-ID audit
   (`build_duplicate_source_id_report()`).
No season-level or preseason-predictor layer is built here -- see
"WHAT WAS REMOVED" above.

TEST SCOPE: tests/test_dataset2_participation_traits.py proves
implementation correctness (list-parsing edge cases via synthetic
fixtures, both real schema shapes, postseason exclusion, team
attribution, the duplicate-source-id dedup) against synthetic fixtures
AND real 2016/2023/2019 examples.
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import season_length, validate_columns

RAW_REQUIRED_COLUMNS = (
    "nflverse_game_id",
    "play_id",
    "possession_team",
    "offense_players",
    "defense_players",
)

GSIS_ID_PATTERN = re.compile(r"^00-\d{7}$")

ROLE_POSSESSION = "possession"
ROLE_NON_POSSESSION = "non_possession"

RAW_PLAY_OUTPUT_COLUMNS = (
    "season",
    "week_token",
    "is_postseason",
    "nflverse_game_id",
    "play_id",
    "possession_team",
    "away_team",
    "home_team",
    "offense_players",
    "defense_players",
)

NORMALIZED_OUTPUT_COLUMNS = (
    "season",
    "week_token",
    "nflverse_game_id",
    "play_id",
    "gsis_id",
    "role",
    "team",
    "player_name",
    "player_position",
    "player_number",
    "has_malformed_token",
    "source_occurrence_count",
    "had_duplicate_source_id",
    "cross_role_conflict",
)

EXTENDED_SCHEMA_COLUMNS = (
    "offense_names",
    "offense_positions",
    "offense_numbers",
    "defense_names",
    "defense_positions",
    "defense_numbers",
)


def _parse_game_id(game_id: str):
    """"{season}_{week_token}_{away}_{home}" -> (season:int, week_token:str, away:str, home:str).
    Real, verified format -- see module docstring."""
    parts = game_id.split("_")
    if len(parts) != 4:
        raise ValueError(f"nflverse_game_id {game_id!r} does not match the real '{{season}}_{{week}}_{{away}}_{{home}}' shape")
    season_str, week_token, away, home = parts
    return int(season_str), week_token, away, home


def _is_postseason(season: int, week_token: str) -> bool:
    reg_max_week = season_length(season) + 1
    return int(week_token) > reg_max_week


def _split_list(value) -> list:
    """Splits a real semicolon-delimited field into tokens. A null or
    empty value -> []. Trailing/leading/double separators produce
    empty-string tokens, which are dropped here (a common, harmless
    CSV artifact) -- NOT the same thing as a malformed (non-gsis-id-
    shaped) token, which is preserved and flagged, not dropped."""
    if pd.isna(value) or value == "":
        return []
    return [tok for tok in value.split(";") if tok != ""]


def build_raw_play_data(raw_participation: pd.DataFrame, include_postseason: bool = False) -> pd.DataFrame:
    """
    RAW play-level data -- one row per real play, season/week/postseason
    derived from `nflverse_game_id`. Excludes postseason rows by
    default (`include_postseason=True` to keep them for a future
    analysis that explicitly wants them). ACTIVELY CHECKS for a
    duplicate (nflverse_game_id, play_id) pair and raises if found.
    """
    validate_columns(raw_participation, RAW_REQUIRED_COLUMNS, "raw_participation")

    out = raw_participation.copy()
    parsed = out["nflverse_game_id"].apply(_parse_game_id)
    out["season"] = parsed.apply(lambda t: t[0])
    out["week_token"] = parsed.apply(lambda t: t[1])
    out["away_team"] = parsed.apply(lambda t: t[2])
    out["home_team"] = parsed.apply(lambda t: t[3])
    out["is_postseason"] = out.apply(lambda r: _is_postseason(r["season"], r["week_token"]), axis=1)

    dupes = out[out.duplicated(subset=["nflverse_game_id", "play_id"], keep=False)]
    if len(dupes) > 0:
        raise RuntimeError(
            f"Found {len(dupes)} real rows with a duplicate (nflverse_game_id, play_id) "
            f"pair -- a real duplicate play record, which the full 2016-2025 real "
            f"population audit found zero of. Refusing to silently proceed:\n"
            f"{dupes[['nflverse_game_id', 'play_id']].to_string()}"
        )

    if not include_postseason:
        out = out[~out["is_postseason"]]

    present_extended = [c for c in EXTENDED_SCHEMA_COLUMNS if c in raw_participation.columns]
    return out[list(RAW_PLAY_OUTPUT_COLUMNS) + present_extended].reset_index(drop=True)


def normalize_participation(raw_play_data: pd.DataFrame) -> pd.DataFrame:
    """
    NORMALIZED player-play-role participation -- explodes
    `offense_players`/`defense_players` (and, when present, the six
    real 26-column-schema fields) into AT MOST one row per (play,
    gsis_id, role). `raw_play_data` should be build_raw_play_data()'s
    own output (or an equivalent DataFrame with at least
    RAW_PLAY_OUTPUT_COLUMNS, optionally the six 26-column-schema fields
    too).

    A real ID repeated within one play's own source list is collapsed
    to a single row (never one row per raw occurrence -- see
    `source_occurrence_count`/`had_duplicate_source_id` in the module
    docstring's "DUPLICATE SOURCE IDS" section). Malformed tokens and
    cross-role conflicts are FLAGGED, never dropped or raised on
    (unlike the structural per-play duplicate check in
    build_raw_play_data(), these are per-token anomalies, not identity
    violations).
    """
    has_extended_schema = "offense_names" in raw_play_data.columns

    rows = []
    for row in raw_play_data.itertuples(index=False):
        row_d = row._asdict()
        off_ids = _split_list(row_d.get("offense_players"))
        def_ids = _split_list(row_d.get("defense_players"))
        off_ids_set = set(off_ids)
        def_ids_set = set(def_ids)

        off_names = _split_list(row_d.get("offense_names")) if has_extended_schema else []
        off_positions = _split_list(row_d.get("offense_positions")) if has_extended_schema else []
        off_numbers = _split_list(row_d.get("offense_numbers")) if has_extended_schema else []
        def_names = _split_list(row_d.get("defense_names")) if has_extended_schema else []
        def_positions = _split_list(row_d.get("defense_positions")) if has_extended_schema else []
        def_numbers = _split_list(row_d.get("defense_numbers")) if has_extended_schema else []

        for role, ids, other_ids, names, positions, numbers, team in (
            (ROLE_POSSESSION, off_ids, def_ids_set, off_names, off_positions, off_numbers, row_d["possession_team"]),
            (
                ROLE_NON_POSSESSION,
                def_ids,
                off_ids_set,
                def_names,
                def_positions,
                def_numbers,
                row_d["away_team"] if row_d["possession_team"] == row_d["home_team"] else row_d["home_team"],
            ),
        ):
            # First occurrence index of each distinct id -> its
            # extended-schema fields; occurrence_count from the full
            # real list, per the module docstring's documented,
            # arbitrary-but-consistent "keep the first occurrence" rule.
            first_index = {}
            occurrence_count = {}
            for i, gsis_id in enumerate(ids):
                if gsis_id not in first_index:
                    first_index[gsis_id] = i
                occurrence_count[gsis_id] = occurrence_count.get(gsis_id, 0) + 1

            for gsis_id, i in first_index.items():
                rows.append(
                    {
                        "season": row_d["season"],
                        "week_token": row_d["week_token"],
                        "nflverse_game_id": row_d["nflverse_game_id"],
                        "play_id": row_d["play_id"],
                        "gsis_id": gsis_id,
                        "role": role,
                        "team": team,
                        "player_name": names[i] if i < len(names) else None,
                        "player_position": positions[i] if i < len(positions) else None,
                        "player_number": numbers[i] if i < len(numbers) else None,
                        "has_malformed_token": not bool(GSIS_ID_PATTERN.match(gsis_id)),
                        "source_occurrence_count": occurrence_count[gsis_id],
                        "had_duplicate_source_id": occurrence_count[gsis_id] > 1,
                        "cross_role_conflict": gsis_id in other_ids,
                    }
                )

    if not rows:
        return pd.DataFrame(columns=list(NORMALIZED_OUTPUT_COLUMNS))
    return pd.DataFrame(rows, columns=list(NORMALIZED_OUTPUT_COLUMNS))


def build_duplicate_source_id_report(normalized: pd.DataFrame) -> pd.DataFrame:
    """Reports the real duplicate-source-id anomaly by season and by
    role (which real source list -- offense_players/defense_players --
    it occurred in), from normalize_participation()'s own output.
    `n_affected_identities`: distinct (game, play, gsis_id, role) rows
    with had_duplicate_source_id=True. `total_excess_occurrences`: sum
    of (source_occurrence_count - 1) across those rows -- how many real
    raw list entries were collapsed away in total, not just how many
    identities were affected."""
    validate_columns(normalized, NORMALIZED_OUTPUT_COLUMNS, "normalized")

    affected = normalized[normalized["had_duplicate_source_id"]]
    if len(affected) == 0:
        return pd.DataFrame(columns=["season", "role", "n_affected_identities", "total_excess_occurrences"])

    report = (
        affected.groupby(["season", "role"])
        .agg(
            n_affected_identities=("gsis_id", "size"),
            total_excess_occurrences=("source_occurrence_count", lambda s: (s - 1).sum()),
        )
        .reset_index()
    )
    return report
