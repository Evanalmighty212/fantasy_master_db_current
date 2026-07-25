"""
lib/stars_by_value/mmc_2010_overrides.py

Loader and validator for data/manual/mmc_2010_manual_overrides.csv --
the narrow, hand-maintained escape hatch for the 2010 cohort, whose
acquisition-cost status cannot be resolved by ADP matching or by MFL
corroboration (MFL has zero usable historical data before 2011,
confirmed directly -- see docs/ADP_SOURCE_MATRIX.md). Full schema and
validation rules are settled in
research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md section 8a.

SCOPE, DELIBERATELY NARROW: this module only parses and validates the
override CSV. It does not classify players, does not decide when an
override should exist, and must never be imported by classifier or
scoring logic in the other direction -- lib/stars_by_value/acquisition_cost.py
(a later commit) will READ this loader's output, but nothing here
knows anything about the classifier, MFL, or ADP matching. Keeping the
two separate means a bug in classification can never silently create
or accept an override, and a bug here can never silently change a
classification.

GENERIC, NOT HARDCODED: "only season 2010 is eligible for this
override mechanism" is settled methodology (section 11), not an
implementation detail -- enforced here against
config.SBV_MMC_MANUAL_OVERRIDE_SEASONS, a constant DEDICATED to this
mechanism (deliberately NOT config.SBV_FIRST_SCOREABLE_SEASON, even
though both currently equal 2010 -- see that constant's own comment in
config.py: they encode different concepts that only coincide in value
today, and conflating them would make extending the study's start
season and extending this override mechanism look like the same
decision when they are not).

SOURCE-VALUE CHECK IS NARROW ON PURPOSE (revised after review): section
8a rule #2 rejects a row whose 'source' field literally IS one of a
small set of internal-signal-name tokens (e.g. "classifier",
"draft_capital") -- an EXACT match after normalization, not a
substring/phrase search. A substring rule was tried and rejected: it
would reject a genuine independent source that happens to contain
ordinary phrases like "rookie status" (e.g. "cross-referenced against
the team's own rookie status announcement"), while being trivially
evadable by rephrasing. See config.py's comment on
SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES for the exact list.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES,
    SBV_MMC_2010_OVERRIDE_PATH,
    SBV_MMC_MANUAL_OVERRIDE_SEASONS,
)

OVERRIDE_PATH = Path(SBV_MMC_2010_OVERRIDE_PATH)

REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "player_name",
    "override_type",
    "market_cost_status",
    "adp_overall",
    "adp_round",
    "minimal_market_cost_approved",
    "source",
    "source_date",
    "evidence_summary",
    "confidence",
    "approved_by",
    "notes",
)

OVERRIDE_TYPES = ("usable_adp", "minimal_market_cost")
MARKET_COST_STATUSES = ("adp_scored", "minimal_market_cost_scored")
CONFIDENCE_LEVELS = ("high", "medium", "low")
REQUIRED_NON_EMPTY_FIELDS = ("player_id", "player_name", "source", "source_date", "evidence_summary", "approved_by")

# override_type -> the one market_cost_status it must produce (section 8a)
OVERRIDE_TYPE_TO_STATUS = {
    "usable_adp": "adp_scored",
    "minimal_market_cost": "minimal_market_cost_scored",
}


def load_overrides(path: Path = None) -> pd.DataFrame:
    """Loads the override table, creating it empty-with-headers if it
    doesn't exist yet -- mirrors player_matching.py's load_overrides()
    precedent for the other data/manual/ tables. Does NOT validate --
    call validate_overrides() separately so a caller can load and
    inspect before deciding whether to enforce."""
    target = Path(path) if path is not None else OVERRIDE_PATH
    if target.exists():
        return pd.read_csv(target, dtype=str)

    target.parent.mkdir(parents=True, exist_ok=True)
    empty = pd.DataFrame(columns=list(REQUIRED_COLUMNS))
    empty.to_csv(target, index=False)
    return empty


def _is_populated(value) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    return str(value).strip() != ""


def _parse_bool(value):
    """Returns True/False for a recognized boolean-ish string, or None
    if the field is blank/unpopulated. A value that IS populated but
    not recognized as true/false is treated as False (not a valid
    'approved') -- validate_overrides()'s enum-style checks don't
    apply here since this is a free-form CSV cell, not a fixed enum,
    but an unrecognized value will correctly fail the "exactly one
    path populated" check below rather than silently passing."""
    if not _is_populated(value):
        return None
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes"):
        return True
    if normalized in ("false", "0", "no"):
        return False
    return False


def _normalize_source_value(value) -> str:
    """Lowercase, strip, collapse internal whitespace, and treat
    spaces/underscores as equivalent -- so "Draft_Capital", "draft
    capital", and "draft  capital" all normalize the same way for the
    EXACT-match disallowed-source-value check. Deliberately does not
    strip punctuation or words -- a normal sentence containing one of
    these tokens amid other words will NOT normalize down to just the
    token, so it will not match (see module docstring)."""
    if not _is_populated(value):
        return ""
    normalized = str(value).strip().lower().replace("_", " ")
    return " ".join(normalized.split())


def validate_overrides(df: pd.DataFrame) -> None:
    """Raises ValueError listing every violation found across every
    row (not just the first), mirroring validate_sbv_config()'s
    collect-then-raise style. An empty table (0 rows) always passes --
    this file starts empty and every row is a deliberate future act,
    not a default state to reject."""
    errors = []
    disallowed_source_values = {_normalize_source_value(v) for v in SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES}

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"mmc_2010_manual_overrides.csv is missing required columns: {missing_cols}")

    for idx, row in df.iterrows():
        label = f"row {idx} (player_id={row.get('player_id')!r})"

        # --- season: generic check against the dedicated override-season
        # constant, not SBV_FIRST_SCOREABLE_SEASON and not a bare literal ---
        season_raw = row.get("season")
        season = None
        try:
            season = int(season_raw)
        except (TypeError, ValueError):
            errors.append(f"{label}: season must be an integer, got {season_raw!r}")
        if season is not None and season not in SBV_MMC_MANUAL_OVERRIDE_SEASONS:
            errors.append(
                f"{label}: season must be one of {SBV_MMC_MANUAL_OVERRIDE_SEASONS} -- this "
                f"override mechanism is sanctioned only for that cohort by settled "
                f"methodology (section 11); using it for another season needs a new "
                f"methodology decision, not just a new row. Got {season}."
            )

        # --- required non-empty string fields ---
        for field in REQUIRED_NON_EMPTY_FIELDS:
            if not _is_populated(row.get(field)):
                errors.append(f"{label}: '{field}' is required and must not be empty")

        # --- enums, validated against explicit allowed values ---
        override_type = row.get("override_type")
        if override_type not in OVERRIDE_TYPES:
            errors.append(f"{label}: override_type must be one of {OVERRIDE_TYPES}, got {override_type!r}")

        market_cost_status = row.get("market_cost_status")
        if market_cost_status not in MARKET_COST_STATUSES:
            errors.append(
                f"{label}: market_cost_status must be one of {MARKET_COST_STATUSES}, "
                f"got {market_cost_status!r}"
            )

        confidence = row.get("confidence")
        if confidence not in CONFIDENCE_LEVELS:
            errors.append(f"{label}: confidence must be one of {CONFIDENCE_LEVELS}, got {confidence!r}")

        # --- override_type <-> market_cost_status agreement ---
        if override_type in OVERRIDE_TYPE_TO_STATUS and market_cost_status in MARKET_COST_STATUSES:
            expected_status = OVERRIDE_TYPE_TO_STATUS[override_type]
            if market_cost_status != expected_status:
                errors.append(
                    f"{label}: override_type={override_type!r} must pair with "
                    f"market_cost_status={expected_status!r}, got {market_cost_status!r}"
                )

        # --- exactly one of {adp fields} or {mmc approval}, matching override_type ---
        has_adp = _is_populated(row.get("adp_overall")) or _is_populated(row.get("adp_round"))
        mmc_approved = _parse_bool(row.get("minimal_market_cost_approved"))
        has_mmc = mmc_approved is True

        if has_adp and has_mmc:
            errors.append(
                f"{label}: cannot populate both adp_overall/adp_round AND "
                f"minimal_market_cost_approved=TRUE -- exactly one path per row"
            )
        elif not has_adp and not has_mmc:
            errors.append(
                f"{label}: must populate either adp_overall/adp_round (usable_adp) or "
                f"minimal_market_cost_approved=TRUE (minimal_market_cost) -- neither found"
            )
        elif override_type == "usable_adp" and not has_adp:
            errors.append(f"{label}: override_type=usable_adp requires adp_overall/adp_round to be populated")
        elif override_type == "minimal_market_cost" and not has_mmc:
            errors.append(f"{label}: override_type=minimal_market_cost requires minimal_market_cost_approved=TRUE")

        # --- source must not literally BE a classifier-internal signal name
        # (section 8a rule #2) -- exact match after normalization, NOT a
        # substring/phrase search, see module docstring ---
        normalized_source = _normalize_source_value(row.get("source"))
        if normalized_source in disallowed_source_values:
            errors.append(
                f"{label}: source {row.get('source')!r} is a classifier-internal signal "
                f"name, not an independent source -- section 8a rule #2 requires evidence "
                f"the automated classifier does not already consider"
            )

    # --- reject duplicate (season, player_id) rows ---
    if "season" in df.columns and "player_id" in df.columns and len(df) > 0:
        key = list(zip(df["season"].astype(str), df["player_id"].astype(str)))
        seen = set()
        duplicate_keys = set()
        for pair in key:
            if pair in seen:
                duplicate_keys.add(pair)
            seen.add(pair)
        if duplicate_keys:
            errors.append(
                f"Duplicate (season, player_id) rows found: {sorted(duplicate_keys)} -- "
                f"each player/season may appear at most once"
            )

    if errors:
        raise ValueError(
            "mmc_2010_manual_overrides.csv failed validation "
            f"({len(errors)} issue{'s' if len(errors) != 1 else ''}):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
