"""
mfl_client.py

Rate-limited, disk-cached fetch layer for MyFantasyLeague's public API,
built for the Stars-by-Value acquisition-cost classifier's MFL
corroboration signal (see docs/ADP_SOURCE_MATRIX.md's "No-ADP
remediation" parts 3-4, and
research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md section 3).
This is a NEW production module, not a reuse of
research/diagnostics/mfl_pipeline/mfl_client.py -- that file is
explicitly isolated (see its own docstring), built for a different,
2025-specific per-league draft-reconstruction investigation. This
module only needs MFL's much simpler TYPE=adp and TYPE=players
aggregate reports, confirmed directly against the live API:
  - TYPE=adp&PERIOD=AUG15&JSON=1 -- one JSON object per season, with
    an "adp" key containing "totalDrafts" and a "player" list of
    {id, rank, averagePick, draftSelPct, draftsSelectedIn, minPick,
    maxPick}. "id" is MFL's own player id, NOT gsis_id.
  - TYPE=players&JSON=1 -- id -> {name, position, team} for that
    season's MFL player universe. Confirmed NOT season-invariant
    (2011's roster doesn't include players who entered the league
    later; even players present in multiple years show real id/name
    drift) -- must be fetched per season, unlike nflverse's single
    players.csv.

FETCH-ONLY, BY DESIGN: this module fetches and caches raw MFL JSON
responses. It does not normalize names, match players to gsis_id, or
make any acquisition-cost decision -- that belongs in
lib/stars_by_value/acquisition_cost.py (a later commit), reusing
player_matching.py's existing name-normalization logic rather than
duplicating it here.

INTEGRITY MODEL -- DELIBERATELY DIFFERENT FROM nflverse_source.py, IN
A SPECIFIC WAY, NOT ACROSS THE BOARD:
MFL's TYPE=adp report is a LIVE, CONTINUOUSLY-GROWING aggregate, not a
frozen historical artifact -- confirmed directly: querying season 2023
live returned totalDrafts=9,970 and Puka Nacua at rank 213 / 16%
draftSelPct, versus totalDrafts=7,923 and rank 209 / 18% recorded in
docs/ADP_SOURCE_MATRIX.md from an earlier pass on an earlier date.
There is no stable upstream hash to pin against the way there is for
nflverse's GitHub release assets. That fact shapes what a mismatch
MEANS here (it is not evidence of a problem the way it is for
nflverse), but it does NOT mean mismatches should be handled silently
-- normal runs must never make an unexpected network request just
because a local file looks stale, corrupted, or hand-edited:
  - Cache hit (local file present, hash matches the manifest entry) ->
    return it silently. No network call.
  - Cache MISSING (no local file at all -- a fresh clone, or a
    deliberately cleared cache) -> fetch it. This is not "replacing"
    anything; there is nothing local to compare against, and refusing
    to bootstrap would make the module unusable on a fresh clone.
  - Cache PRESENT but hash MISMATCHES the manifest entry -> raise
    loudly and refuse to fetch. This is the deliberate difference from
    the module's first design: a mismatch might mean the file was
    edited or corrupted, or it might just mean MFL's live report moved
    on since this was last recorded -- either way, deciding to accept
    new data is a deliberate act, not a side effect of calling
    fetch_adp()/fetch_players() normally. The error message names
    force_refresh=True as the explicit way to accept it.
  - force_refresh=True -> always fetches fresh and overwrites the
    local snapshot + manifest entry, regardless of the cache's current
    state. If the new values differ from whatever was previously
    recorded, both are printed so drift is visible, never silently
    swallowed.

COMMITTED SNAPSHOT REGISTRY, NOT DISPOSABLE BOOKKEEPING:
scripts/mfl_source_manifest.json IS committed to git (unlike the raw
per-response JSON under data/raw/mfl/, which stays gitignored -- see
CACHE_DIR below). Per season and endpoint it records: the exact URL/
query parameters used (including PERIOD=AUG15), the retrieval
timestamp, the sha256 of the cached file, totalDrafts (adp report
only), row count, and the SBV_VERSION in effect when it was fetched.
IMPORTANT LIMIT ON WHAT THIS PROVES: this registry documents the
EXACT SNAPSHOT this project used for a given season/endpoint -- it is
an audit trail, not a reproducibility mechanism. Because MFL's
TYPE=adp report is a live aggregate, re-fetching the same season later
will very likely NOT reproduce the same bytes, even with the URL and
every parameter identical (confirmed directly, see above). A future
immutable archive of the raw responses (e.g. committing sanitized
snapshots, or an external object store) would be needed for full
byte-for-byte reproducibility; this registry alone cannot provide it.

RATE LIMITING: serial requests only, a minimum delay enforced between
real network calls, bounded retry with exponential backoff -- values
read from config.py's SBV_MFL_MIN_REQUEST_DELAY_SECONDS /
SBV_MFL_MAX_RETRIES / SBV_MFL_BACKOFF_BASE_SECONDS /
SBV_MFL_REQUEST_TIMEOUT_SECONDS, not hardcoded here (see config.py's
comment on why these are implementation-metadata config rather than
module constants). Built fresh rather than importing
research/diagnostics/mfl_pipeline/mfl_client.py's already-proven
version of this same logic, per that module's own "ISOLATED -- never
wired into any production code" boundary. Unlike that isolated client
(which swallows failures into an {"_error": ...} sentinel so a large
per-league batch could continue past one bad league), this module
raises loudly on final failure -- it never runs that kind of large
batch (at most ~15 seasons x 2 endpoints for a real classifier run),
so fail-loud is the better default here, consistent with this
project's fail-loud philosophy.

PERIOD=AUG15 IS ALWAYS EXPLICIT: MFL's unparameterized default ADP
report blends in-season and post-breakout draft activity, confirmed
directly during the earlier investigation (see
docs/ADP_SOURCE_MATRIX.md's PERIOD-contamination finding) -- this
module never omits it.
"""

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (
    SBV_MFL_AVAILABLE_FROM_SEASON,
    SBV_MFL_BACKOFF_BASE_SECONDS,
    SBV_MFL_MAX_RETRIES,
    SBV_MFL_MIN_REQUEST_DELAY_SECONDS,
    SBV_MFL_PERIOD,
    SBV_MFL_REQUEST_TIMEOUT_SECONDS,
    SBV_VERSION,
)

API_BASE_TEMPLATE = "https://api.myfantasyleague.com/{season}/export"

CACHE_DIR = Path("data/raw/mfl")
# Raw per-response JSON stays gitignored, same convention as data/raw/
# elsewhere in this project -- only the compact registry below is
# committed.

MANIFEST_PATH = Path(__file__).resolve().parent / "mfl_source_manifest.json"
# COMMITTED to git -- a compact snapshot registry, not disposable local
# bookkeeping. See module docstring's "COMMITTED SNAPSHOT REGISTRY"
# section for exactly what it does and does not guarantee.

MANIFEST_NOTE = (
    "This registry documents the exact MFL snapshot used for each season/endpoint "
    "at the time it was fetched (URL and query parameters, retrieval timestamp, "
    "sha256, totalDrafts where applicable, row count, sbv_version). MFL's "
    "underlying reports are live, continuously-growing aggregates -- re-fetching "
    "the same season later will very likely NOT reproduce the same bytes "
    "(confirmed directly: season 2023's totalDrafts grew from 7,923 to 9,970 "
    "between two real queries on different dates, see mfl_client.py's module "
    "docstring). This registry proves what was used; it cannot by itself "
    "recreate the original bytes. A future immutable archive of the raw "
    "responses may be needed for full reproducibility."
)

_last_request_time = [0.0]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"note": MANIFEST_NOTE, "adp": {"seasons": {}}, "players": {"seasons": {}}}


def _save_manifest(manifest: dict) -> None:
    manifest["note"] = MANIFEST_NOTE  # always current, never hand-edited out of sync
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _throttle() -> None:
    elapsed = time.monotonic() - _last_request_time[0]
    if elapsed < SBV_MFL_MIN_REQUEST_DELAY_SECONDS:
        time.sleep(SBV_MFL_MIN_REQUEST_DELAY_SECONDS - elapsed)


def _get_json(url: str) -> dict:
    """Serial, rate-limited, retrying GET for one MFL JSON endpoint.
    Raises RuntimeError on final failure -- see module docstring for
    why this differs from the isolated research client's behavior."""
    last_error = None
    for attempt in range(SBV_MFL_MAX_RETRIES):
        _throttle()
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=SBV_MFL_REQUEST_TIMEOUT_SECONDS,
            )
            _last_request_time[0] = time.monotonic()
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            _last_request_time[0] = time.monotonic()
            if attempt < SBV_MFL_MAX_RETRIES - 1:
                time.sleep(SBV_MFL_BACKOFF_BASE_SECONDS * (2 ** attempt))
    raise RuntimeError(f"Failed to fetch {url} after {SBV_MFL_MAX_RETRIES} attempts: {last_error}")


def _build_entry(report: str, url: str, data: dict, local_path: Path) -> dict:
    if report == "adp":
        adp = data.get("adp", {})
        total_drafts = adp.get("totalDrafts")
        row_count = len(adp.get("player", []))
    else:
        total_drafts = None
        row_count = len(data.get("players", {}).get("player", []))
    return {
        "url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(local_path),
        "total_drafts": total_drafts,
        "row_count": row_count,
        "sbv_version": SBV_VERSION,
    }


def _fetch_cached(season: int, report: str, url: str, local_path: Path, force_refresh: bool) -> dict:
    """Shared cache logic behind fetch_adp()/fetch_players(). See
    module docstring's INTEGRITY MODEL section: cache hit -> return
    silently; cache missing -> fetch (bootstrap, not a replacement);
    cache present but mismatched -> raise and require force_refresh=True;
    force_refresh=True -> always fetch fresh."""
    manifest = _load_manifest()
    manifest.setdefault(report, {"seasons": {}})
    recorded = manifest[report]["seasons"].get(str(season))

    if not force_refresh and recorded is not None and local_path.exists():
        current_hash = _sha256(local_path)
        if current_hash == recorded["sha256"]:
            return json.loads(local_path.read_text())
        raise RuntimeError(
            f"LOCAL SNAPSHOT MISMATCH for MFL {report} season {season}: the cached "
            f"file at {local_path} does not match the sha256 recorded in "
            f"{MANIFEST_PATH.name} (recorded {recorded['sha256'][:12]}..., got "
            f"{current_hash[:12]}...). This does NOT necessarily mean anything is "
            f"wrong upstream -- MFL's {report} report is a live, continuously-growing "
            f"aggregate (see module docstring), so the file may simply have moved on "
            f"since it was last recorded, or it may have been edited or corrupted "
            f"locally. Either way, refusing to silently re-fetch and replace it -- "
            f"normal runs must never make an unexpected network request just because "
            f"a local snapshot looks stale. If you intend to deliberately accept new "
            f"data for this season, call fetch_{report}({season}, force_refresh=True)."
        )

    old_entry = recorded  # None on a genuine first fetch
    data = _get_json(url)

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(json.dumps(data))

    new_entry = _build_entry(report, url, data, local_path)
    manifest[report]["seasons"][str(season)] = new_entry
    _save_manifest(manifest)

    if old_entry is not None:
        old_compare = {"total_drafts": old_entry.get("total_drafts"), "row_count": old_entry.get("row_count")}
        new_compare = {"total_drafts": new_entry["total_drafts"], "row_count": new_entry["row_count"]}
        if old_compare != new_compare:
            print(
                f"mfl_client: {report} season {season} snapshot replaced -- "
                f"{old_compare} -> {new_compare}. Expected for a live MFL endpoint "
                f"(see module docstring), not a sign of a problem, but the "
                f"committed registry entry for this season is about to change -- "
                f"review the diff before committing."
            )

    return data


def fetch_adp(season: int, force_refresh: bool = False) -> dict:
    """Raw TYPE=adp&PERIOD=AUG15 response for one season, cache-first.
    Never omits PERIOD -- see module docstring."""
    if season < SBV_MFL_AVAILABLE_FROM_SEASON:
        raise ValueError(
            f"MFL has no usable historical ADP data before "
            f"{SBV_MFL_AVAILABLE_FROM_SEASON} at any query period (confirmed "
            f"directly, see docs/ADP_SOURCE_MATRIX.md) -- got season {season}."
        )
    url = f"{API_BASE_TEMPLATE.format(season=season)}?TYPE=adp&PERIOD={SBV_MFL_PERIOD}&JSON=1"
    local_path = CACHE_DIR / f"adp_{season}_period_{SBV_MFL_PERIOD.lower()}.json"
    return _fetch_cached(season, "adp", url, local_path, force_refresh)


def fetch_players(season: int, force_refresh: bool = False) -> dict:
    """Raw TYPE=players response for one season, cache-first. NOT
    season-invariant -- see module docstring."""
    url = f"{API_BASE_TEMPLATE.format(season=season)}?TYPE=players&JSON=1"
    local_path = CACHE_DIR / f"players_{season}.json"
    return _fetch_cached(season, "players", url, local_path, force_refresh)
