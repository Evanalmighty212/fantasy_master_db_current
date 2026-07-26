"""
lib/stars_by_value/acquisition_cost.py

The Stars-by-Value acquisition-cost classifier: rule-based draft-status
classification, the narrow rookie-QB depth-chart correction, 3-way MFL
corroboration (2011+), and the 2010-cohort fallback. Genuinely new
implementation, not a promotion -- no research script computes this
end to end; the specification is the prose settled record in
docs/ADP_SOURCE_MATRIX.md's "No-ADP remediation" parts 1-4, translated
into an explicit routing table and reviewed before this module was
written.

SCOPE: this module classifies a single no-ADP-match, gate-clearing row
into one of: a real acquisition-cost STATUS/PROVENANCE pair (for the
four "unscoreable"/"minimal-market-cost" outcomes), or a real
ADP_OVERALL/ADP_ROUND value (only via a 2010 `usable_adp` override,
which routes the row back to the NORMAL adp-scored path instead --
this module does not compute a score itself either way). Population
scoping (which rows are gate-clearing, no-ADP-match candidates in the
first place) is the caller's job, same convention as production.py and
expected_production.py.

THE FULL ROUTING TABLE (reviewed and approved before implementation):

2011+ (classifier_bucket, mfl_result) -> (status, provenance):
  (likely_undrafted, matched_low)                  -> MMC, mmc_verified_corroborated
  (likely_undrafted, matched_zero)                 -> MMC, mmc_verified_corroborated
  (likely_undrafted, matched_high)                 -> ambiguous, evidence_ambiguous_disagreement
  (likely_undrafted, unmatched)                    -> ambiguous, evidence_ambiguous_disagreement
  (ambiguous, matched_low)                         -> MMC, mmc_verified_corroborated
  (ambiguous, matched_zero)                        -> MMC, mmc_verified_corroborated
  (ambiguous, matched_high)                        -> ambiguous, evidence_ambiguous_disagreement
  (ambiguous, unmatched)                           -> ambiguous, evidence_ambiguous_disagreement
  (likely_drafted_missing_evidence, matched_low)   -> ambiguous, evidence_ambiguous_disagreement
  (likely_drafted_missing_evidence, matched_zero)  -> ambiguous, evidence_ambiguous_disagreement
  (likely_drafted_missing_evidence, matched_high)  -> drafted_missing, evidence_drafted_unresolved
  (likely_drafted_missing_evidence, unmatched)     -> drafted_missing, evidence_drafted_unresolved

Two deliberate asymmetries, not oversights:
  - `ambiguous` is non-committal, not an affirmative claim -- a clear
    low-MFL signal stands uncontradicted and resolves to MMC, exactly
    like `likely_undrafted`. This is the resolution approved for this
    commit; it treats "ambiguous" + high MFL differently (NOT resolved
    to drafted_missing) since no settled example supports extending the
    principle in that direction, and every documented
    "confirmed_or_likely_drafted" case sits at 58-94%, not "merely not
    low" -- so `ambiguous` + `matched_high` stays at
    evidence_ambiguous_disagreement, not evidence_drafted_unresolved.
  - `unmatched` MFL: classifier-alone IS allowed to resolve
    likely_drafted_missing_evidence -> drafted_missing (settled
    precedent: MFL-unmatched rows "fall back to classifier alone,
    lower confidence"), but classifier-alone is NEVER allowed to grant
    MMC -- likely_undrafted + unmatched stays ambiguous, per the
    explicit, one-directional "classifier output alone never grants
    MMC" rule.

2010 (MFL structurally unavailable -- never attempted, not "unmatched"):
  - Named exception: Mike Vick (VICK_2010_GSIS_ID) -> drafted_missing,
    evidence_drafted_unresolved, regardless of classifier bucket.
  - Valid override, override_type=minimal_market_cost -> MMC,
    mmc_verified_2010_manual_override.
  - Valid override, override_type=usable_adp -> NOT an
    acquisition-cost resolution; returns adp_overall/adp_round, row
    exits to the normal ADP-scored path.
  - Otherwise (no override, not Vick) -> ambiguous,
    evidence_ambiguous_disagreement, REGARDLESS of classifier bucket --
    per the settled "classifier output alone is never sufficient... for
    any season," which for 2010 is a blanket policy (MFL structurally
    can't corroborate ANY 2010 row), stricter than the 2011+ unmatched
    case (which reflects an individual name-match miss, not a
    season-wide data gap).

NAME MATCHING: exact normalized-name + position match only, reusing
scripts/player_matching.py's normalize_name() verbatim -- no fuzzy
scoring for MFL (the settled record only ever describes exact matches
with collisions excluded, never fuzzy-resolved, a real disclosed
asymmetry from FFC's fuzzy-tier matching, not an oversight). Multiple
surviving candidates after normalized-name+position matching ->
excluded, routed to "unmatched" -- never guessed (this is the exact,
disclosed handling of real collisions like two same-era same-position
"Steve Smith"s).

"MATCHED, ZERO SELECTION" vs. "UNMATCHED": a player found in MFL's
player DIRECTORY (fetch_players) but absent from that season's
TYPE=adp player list is a real, meaningful data point -- draftSelPct=0%,
selected in zero real drafts -- not a match failure. A player not
found in the directory at all is "unmatched": no MFL signal, falls
back to classifier-alone.

2025 DEPTH-CHART SCHEMA BREAK: the rookie-QB depth-chart correction
fails loudly, not silently, if ever invoked for season 2025 (see
nflverse_source.py's module docstring for the schema break itself) --
no known candidate needs it yet, and building a second parser for a
one-off, currently-unneeded schema is speculative work deferred until
a real case requires it.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from config import (
    SBV_CLASSIFIER_DAY_1_2_MAX_ROUND,
    SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_GAMES,
    SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_POINTS,
    SBV_CLASSIFIER_PRIOR_SEASONS_LOOKBACK,
    SBV_MFL_AVAILABLE_FROM_SEASON,
    SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT,
)
from player_matching import normalize_name

# --- Classifier buckets ---------------------------------------------------
BUCKET_LIKELY_UNDRAFTED = "likely_undrafted"
BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE = "likely_drafted_missing_evidence"
BUCKET_AMBIGUOUS = "ambiguous"
CLASSIFIER_BUCKETS = (BUCKET_LIKELY_UNDRAFTED, BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, BUCKET_AMBIGUOUS)

# --- MFL result categories -------------------------------------------------
MFL_MATCHED_LOW = "matched_low"
MFL_MATCHED_ZERO = "matched_zero"
MFL_MATCHED_HIGH = "matched_high"
MFL_UNMATCHED = "unmatched"
MFL_RESULTS = (MFL_MATCHED_LOW, MFL_MATCHED_ZERO, MFL_MATCHED_HIGH, MFL_UNMATCHED)

# --- Status / provenance (reused from config.py's settled enums) ---------
STATUS_MMC = "minimal_market_cost_scored"
STATUS_DRAFTED_MISSING = "unscoreable_drafted_adp_missing"
STATUS_AMBIGUOUS = "unscoreable_ambiguous"

PROVENANCE_MMC_CORROBORATED = "mmc_verified_corroborated"
PROVENANCE_MMC_2010_OVERRIDE = "mmc_verified_2010_manual_override"
PROVENANCE_DRAFTED_UNRESOLVED = "evidence_drafted_unresolved"
PROVENANCE_AMBIGUOUS_DISAGREEMENT = "evidence_ambiguous_disagreement"

# --- Named historical exception (2010 cohort) -----------------------------
VICK_2010_GSIS_ID = "00-0020245"
VICK_2010_EXCEPTION_NOTE = (
    "Mike Vick, 2010: NFL.com's 'Fantasy draft do-over' piece quotes his real, "
    "contemporaneous 2010 draft position directly ('Michael Vick, QB, Philadelphia "
    "Eagles (2010 ADP: 14th round)') -- a real number in a named source, but with no "
    "snapshot date, scoring format, or league size given, and absent from FFC's "
    "214-player 2010 canonical file -- does not meet this project's override-quality "
    "bar (docs/ADP_SOURCE_MATRIX.md, 'No-ADP remediation' part 2). The automated "
    "classifier lands this row in 'ambiguous' (his last real production before 2010 "
    "was 2006 -- he missed 2007-2009 entirely -- four years outside even an extended "
    "lookback), which the settled record explicitly declines to patch further "
    "('6 examples is too small a set to keep tuning rules against without "
    "overfitting', part 3). This narrow, named exception is the documented "
    "alternative: a real, citable source confirms drafted status even though it "
    "can't supply a usable number. If additional cases of this type are found, "
    "replace this one-off with a generalized, structured mechanism -- do not "
    "broaden the 2010 override schema preemptively for a single case."
)

# --- Routing table: 2011+ -------------------------------------------------
_ROUTING_2011_PLUS = {
    (BUCKET_LIKELY_UNDRAFTED, MFL_MATCHED_LOW): (STATUS_MMC, PROVENANCE_MMC_CORROBORATED),
    (BUCKET_LIKELY_UNDRAFTED, MFL_MATCHED_ZERO): (STATUS_MMC, PROVENANCE_MMC_CORROBORATED),
    (BUCKET_LIKELY_UNDRAFTED, MFL_MATCHED_HIGH): (STATUS_AMBIGUOUS, PROVENANCE_AMBIGUOUS_DISAGREEMENT),
    (BUCKET_LIKELY_UNDRAFTED, MFL_UNMATCHED): (STATUS_AMBIGUOUS, PROVENANCE_AMBIGUOUS_DISAGREEMENT),
    (BUCKET_AMBIGUOUS, MFL_MATCHED_LOW): (STATUS_MMC, PROVENANCE_MMC_CORROBORATED),
    (BUCKET_AMBIGUOUS, MFL_MATCHED_ZERO): (STATUS_MMC, PROVENANCE_MMC_CORROBORATED),
    (BUCKET_AMBIGUOUS, MFL_MATCHED_HIGH): (STATUS_AMBIGUOUS, PROVENANCE_AMBIGUOUS_DISAGREEMENT),
    (BUCKET_AMBIGUOUS, MFL_UNMATCHED): (STATUS_AMBIGUOUS, PROVENANCE_AMBIGUOUS_DISAGREEMENT),
    (BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, MFL_MATCHED_LOW): (STATUS_AMBIGUOUS, PROVENANCE_AMBIGUOUS_DISAGREEMENT),
    (BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, MFL_MATCHED_ZERO): (STATUS_AMBIGUOUS, PROVENANCE_AMBIGUOUS_DISAGREEMENT),
    (BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, MFL_MATCHED_HIGH): (STATUS_DRAFTED_MISSING, PROVENANCE_DRAFTED_UNRESOLVED),
    (BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE, MFL_UNMATCHED): (STATUS_DRAFTED_MISSING, PROVENANCE_DRAFTED_UNRESOLVED),
}


def classify_draft_status(season: int, gsis_id: str, players_df: pd.DataFrame, history_df: pd.DataFrame) -> str:
    """Rules, in order (docs/ADP_SOURCE_MATRIX.md part 3):
    1. QB, rookie this season -> likely_undrafted (subject to the
       rookie-QB depth-chart correction, applied separately below).
    2. Rookie this season, skill position, undrafted or Day 3
       (draft_round > SBV_CLASSIFIER_DAY_1_2_MAX_ROUND) -> likely_undrafted.
    3. Rookie this season, Day 1-2 (draft_round <= SBV_CLASSIFIER_DAY_1_2_MAX_ROUND)
       -> likely_drafted_missing_evidence.
    4. Non-rookie with at least one of the prior
       SBV_CLASSIFIER_PRIOR_SEASONS_LOOKBACK seasons individually
       clearing games>=SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_GAMES and
       points>=SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_POINTS -> likely_drafted_missing_evidence.
    5. Everything else -- including a gsis_id with no players.csv row,
       or unresolvable rookie/draft-capital fields -- -> ambiguous.
       Never guessed, never raises.
    """
    player_rows = players_df[players_df["gsis_id"] == gsis_id]
    if player_rows.empty:
        return BUCKET_AMBIGUOUS
    player_row = player_rows.iloc[0]

    rookie_season = player_row.get("rookie_season")
    draft_round = player_row.get("draft_round")
    position = player_row.get("position")

    is_rookie_this_season = pd.notna(rookie_season) and int(rookie_season) == season

    if is_rookie_this_season:
        if position == "QB":
            return BUCKET_LIKELY_UNDRAFTED
        if pd.isna(draft_round) or int(draft_round) > SBV_CLASSIFIER_DAY_1_2_MAX_ROUND:
            return BUCKET_LIKELY_UNDRAFTED
        return BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE

    prior_seasons = list(range(season - SBV_CLASSIFIER_PRIOR_SEASONS_LOOKBACK, season))
    prior_rows = history_df[(history_df["player_id"] == gsis_id) & (history_df["season"].isin(prior_seasons))]
    qualifies = (
        (prior_rows["games_played"] >= SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_GAMES)
        & (prior_rows["fantasy_points_ppr"] >= SBV_CLASSIFIER_PRIOR_PRODUCTION_MIN_POINTS)
    ).any()
    if qualifies:
        return BUCKET_LIKELY_DRAFTED_MISSING_EVIDENCE

    return BUCKET_AMBIGUOUS


def is_qb_rookie_this_season(season: int, gsis_id: str, players_df: pd.DataFrame) -> bool:
    player_rows = players_df[players_df["gsis_id"] == gsis_id]
    if player_rows.empty:
        return False
    row = player_rows.iloc[0]
    return (
        row.get("position") == "QB"
        and pd.notna(row.get("rookie_season"))
        and int(row["rookie_season"]) == season
    )


def apply_rookie_qb_depth_chart_correction(
    bucket: str, season: int, gsis_id: str, is_qb_rookie: bool, depth_chart_df,
    team: str = None, schedule_df=None,
) -> str:
    """Only fires when bucket==likely_undrafted AND is_qb_rookie==True
    (rule 1 fired). Real Week-1-starter status for this gsis_id ->
    'ambiguous'. Anything else, including absence from the relevant
    snapshot -> stays likely_undrafted. Never generalized to other
    positions or a general drafted/undrafted signal -- depth-chart
    status was tested for that broader purpose and found weak (Vick
    2010, OBJ 2014, Cruz 2011, Herbert 2020, and Nacua 2023 all showed
    depth_team=2 despite being real, different draft-cost cases).

    2006-2024: week==1, game_type=="REG", position=="QB", depth_team==1
    on the consistent 15-column schema.

    2025 (validated 2026-07, see docs/ADP_SOURCE_MATRIX.md's
    depth-chart-schema entry): depth_charts_2025.csv has no week label
    at all -- it's a rolling daily snapshot feed (`dt`), a different,
    incompatible 12-column schema (`gsis_id`/`team`/`pos_abb`/
    `pos_rank`, no `week`/`game_type`/`position`/`depth_team`). Mapped
    as: gsis_id -> gsis_id (unchanged), position -> pos_abb=="QB",
    starter status -> pos_rank==1, "Week 1" -> the latest available
    depth-chart snapshot on or before this player's TEAM's real first
    regular-season game (from nflverse's `schedules` release, not a
    shared project-wide date approximation -- every 2025 rookie QB
    already checked resolves identically to the earlier shared-date
    approximation, confirming this is not a live sensitivity, but the
    real per-team date is what ships). Requires `team` and
    `schedule_df` (nflverse_source.fetch_schedules()'s output) for
    season 2025 -- raises if either is missing rather than silently
    falling back to the pre-2025 schema, which would silently
    mis-parse a structurally different file."""
    if not is_qb_rookie or bucket != BUCKET_LIKELY_UNDRAFTED:
        return bucket

    if season == 2025:
        if depth_chart_df is None or len(depth_chart_df) == 0:
            return bucket
        if not team or schedule_df is None:
            raise RuntimeError(
                "Rookie-QB depth-chart correction for season 2025 requires both "
                "'team' and 'schedule_df' (nflverse_source.fetch_schedules()) -- "
                "the 2025 schema has no week label, so the real per-team kickoff "
                "date is required to pick the right snapshot. Refusing to "
                "silently fall back to the pre-2025 schema's week/game_type "
                "columns, which do not exist in depth_charts_2025.csv."
            )
        week1_games = schedule_df[
            (schedule_df["season"] == 2025) & (schedule_df["game_type"] == "REG")
            & (schedule_df["week"] == 1)
            & ((schedule_df["home_team"] == team) | (schedule_df["away_team"] == team))
        ]
        if week1_games.empty:
            return bucket
        kickoff = pd.to_datetime(week1_games.iloc[0]["gameday"])
        dc = depth_chart_df.copy()
        dc["date"] = pd.to_datetime(dc["dt"]).dt.tz_localize(None).dt.normalize()
        eligible_dates = dc.loc[dc["date"] <= kickoff, "date"]
        if eligible_dates.empty:
            return bucket
        snapshot_date = eligible_dates.max()
        snap = dc[
            (dc["date"] == snapshot_date) & (dc["team"] == team)
            & (dc["pos_abb"] == "QB") & (dc["gsis_id"] == gsis_id)
        ]
        if snap.empty:
            return bucket
        if (snap["pos_rank"] == 1).any():
            return BUCKET_AMBIGUOUS
        return bucket

    if depth_chart_df is None or len(depth_chart_df) == 0:
        return bucket
    week1_reg = depth_chart_df[
        (depth_chart_df["week"] == 1)
        & (depth_chart_df["game_type"] == "REG")
        & (depth_chart_df["position"] == "QB")
        & (depth_chart_df["gsis_id"] == gsis_id)
    ]
    if week1_reg.empty:
        return bucket
    if (week1_reg["depth_team"] == 1).any():
        return BUCKET_AMBIGUOUS
    return bucket


def _mfl_name_to_normalized(mfl_name: str) -> str:
    """MFL's player directory uses 'Last, First' -- reorder to 'First
    Last' before applying normalize_name(), so it is comparable to
    master-DB-style names."""
    if "," in mfl_name:
        last, first = mfl_name.split(",", 1)
        return normalize_name(f"{first.strip()} {last.strip()}")
    return normalize_name(mfl_name)


def match_mfl_player(player_name: str, position: str, mfl_players_response: dict):
    """Returns (mfl_id_or_None, match_status), match_status in
    {"matched", "unmatched", "collision"}. Exact normalized-name +
    position match only -- no fuzzy scoring (settled policy: the
    record only ever describes exact matches with collisions excluded,
    never fuzzy-resolved). Multiple surviving candidates -> "collision"
    (never guessed at, matching the real disclosed "two Steve Smiths"
    precedent)."""
    target = normalize_name(player_name)
    candidates = [
        p for p in mfl_players_response.get("players", {}).get("player", [])
        if _mfl_name_to_normalized(p.get("name", "")) == target and p.get("position") == position
    ]
    if len(candidates) == 0:
        return None, "unmatched"
    if len(candidates) > 1:
        return None, "collision"
    return candidates[0]["id"], "matched"


def resolve_mfl_result(mfl_id, match_status: str, mfl_adp_response: dict) -> str:
    """"collision" is folded into MFL_UNMATCHED -- both mean "no
    reliable MFL signal, fall back to classifier alone." A player
    found in the directory but absent from the ADP report's player
    list is MFL_MATCHED_ZERO (draftSelPct=0%), not unmatched -- see
    module docstring."""
    if match_status != "matched":
        return MFL_UNMATCHED
    players = mfl_adp_response.get("adp", {}).get("player", [])
    record = next((p for p in players if p.get("id") == mfl_id), None)
    if record is None:
        return MFL_MATCHED_ZERO
    pct = float(record["draftSelPct"])
    if pct < SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT:
        return MFL_MATCHED_LOW
    return MFL_MATCHED_HIGH


def route_2011_plus(classifier_bucket: str, mfl_result: str):
    """Returns (status, provenance) per the settled routing table --
    see module docstring."""
    key = (classifier_bucket, mfl_result)
    if key not in _ROUTING_2011_PLUS:
        raise ValueError(f"No routing rule for (classifier_bucket={classifier_bucket!r}, mfl_result={mfl_result!r})")
    return _ROUTING_2011_PLUS[key]


def route_2010(gsis_id: str, overrides_2010_df: pd.DataFrame) -> dict:
    """Returns {"status", "provenance", "adp_overall", "adp_round"}.
    classifier_bucket does NOT drive this decision (see module
    docstring) except through the named Vick exception -- per the
    settled "classifier output alone is never sufficient... for any
    season," which for 2010 is a blanket policy, not merely a
    per-row fallback."""
    if gsis_id == VICK_2010_GSIS_ID:
        return {
            "status": STATUS_DRAFTED_MISSING,
            "provenance": PROVENANCE_DRAFTED_UNRESOLVED,
            "adp_overall": None,
            "adp_round": None,
        }

    override_rows = overrides_2010_df[
        (overrides_2010_df["season"].astype(str) == "2010") & (overrides_2010_df["player_id"] == gsis_id)
    ]
    if len(override_rows) > 1:
        raise ValueError(f"Multiple 2010 override rows found for player_id={gsis_id!r} -- must be at most one")

    if len(override_rows) == 1:
        row = override_rows.iloc[0]
        if row["override_type"] == "minimal_market_cost":
            return {
                "status": STATUS_MMC,
                "provenance": PROVENANCE_MMC_2010_OVERRIDE,
                "adp_overall": None,
                "adp_round": None,
            }
        if row["override_type"] == "usable_adp":
            return {
                "status": None,
                "provenance": None,
                "adp_overall": float(row["adp_overall"]),
                "adp_round": int(float(row["adp_round"])),
            }
        raise ValueError(f"Unknown override_type {row['override_type']!r} for player_id={gsis_id!r}")

    return {
        "status": STATUS_AMBIGUOUS,
        "provenance": PROVENANCE_AMBIGUOUS_DISAGREEMENT,
        "adp_overall": None,
        "adp_round": None,
    }


def classify_row(
    season: int,
    gsis_id: str,
    player_name: str,
    position: str,
    players_df: pd.DataFrame,
    history_df: pd.DataFrame,
    depth_chart_df=None,
    mfl_adp_response=None,
    mfl_players_response=None,
    overrides_2010_df=None,
) -> dict:
    """Orchestrates the full classification for one no-ADP-match,
    gate-clearing row. Returns a dict: season, player_id,
    classifier_bucket, mfl_result, status, provenance, adp_overall,
    adp_round. For 2010 rows, classifier_bucket is still computed and
    returned (audit trail) but does not drive status/provenance except
    via the Vick exception -- see route_2010()."""
    bucket = classify_draft_status(season, gsis_id, players_df, history_df)

    if season == 2010:
        if overrides_2010_df is None:
            raise ValueError("overrides_2010_df is required for season=2010 rows")
        result = route_2010(gsis_id, overrides_2010_df)
        return {
            "season": season,
            "player_id": gsis_id,
            "classifier_bucket": bucket,
            "mfl_result": None,
            **result,
        }

    if season < SBV_MFL_AVAILABLE_FROM_SEASON:
        raise ValueError(
            f"season={season} is before SBV_MFL_AVAILABLE_FROM_SEASON "
            f"({SBV_MFL_AVAILABLE_FROM_SEASON}) and is not 2010 -- no routing rule defined"
        )
    if mfl_adp_response is None or mfl_players_response is None:
        raise ValueError(f"mfl_adp_response and mfl_players_response are required for season={season} rows")

    qb_rookie = is_qb_rookie_this_season(season, gsis_id, players_df)
    bucket = apply_rookie_qb_depth_chart_correction(bucket, season, gsis_id, qb_rookie, depth_chart_df)

    mfl_id, match_status = match_mfl_player(player_name, position, mfl_players_response)
    mfl_result = resolve_mfl_result(mfl_id, match_status, mfl_adp_response)

    status, provenance = route_2011_plus(bucket, mfl_result)
    return {
        "season": season,
        "player_id": gsis_id,
        "classifier_bucket": bucket,
        "mfl_result": mfl_result,
        "status": status,
        "provenance": provenance,
        "adp_overall": None,
        "adp_round": None,
    }
