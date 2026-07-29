"""
nflverse_source.py

Raw-download + schema-normalization + integrity layer for nflverse
weekly player stats. Replaces the dependency on
`nfl_data_py.import_weekly_data()`, which reads from nflverse's
`player_stats` GitHub release -- DEPRECATED 2025-08-01, frozen, and
confirmed (during the migration this module implements) to never
receive 2025 or any future season. This module fetches directly from
the successor `stats_player` release instead.

Why this is its own module, not folded into 03_download_stats.py:
that script's job is season-level aggregation (already extensively
fixed and tested); this module's job is producing a clean, verified,
schema-normalized raw weekly table for it to consume. Keeping them
separate means the aggregation logic didn't have to change at all for
this migration, and this fetch/verify layer can be tested on its own.

PINNING: fetches by GITHUB RELEASE ASSET ID
(`api.github.com/.../releases/assets/{id}`), not by the tag+filename
URL (`.../releases/download/stats_player/stats_player_week_<season>.csv`).
This is a real, verified difference, not cosmetic: the tag+filename URL
always resolves to whatever asset CURRENTLY holds that name, so if
nflverse deletes and re-uploads a same-named file (their own workflow's
mechanism for publishing a correction -- confirmed to happen: 166 rows
were found corrected across 2006-2024 during this migration), that URL
silently starts serving the new bytes with no signal at the URL level.
An asset ID is tied to one specific, immutable uploaded object -- if
nflverse republishes, the OLD id either 404s (a loud, clear failure,
consistent with this project's fail-loud philosophy) or keeps serving
the exact original bytes. Either outcome is strictly better than
silent drift.

HONEST LIMIT ON THAT CLAIM (do not overstate this): GitHub does not
publicly document a permanence guarantee for release asset IDs. This
is the most stable identifier their API exposes, used because it is
verified to be more stable than the alternative, not because it is
proven immutable forever. Given that, the actual safety net is still
the sha256 check below, not the choice of URL -- see fetch_season_raw().

WHAT THIS MODULE DOES NOT DO: it does not independently archive nflverse's
raw bytes anywhere this project controls. The only local copy is the
gitignored cache under data/raw/nflverse/annual/ -- a fresh clone has
none of it and must re-fetch from GitHub. If GitHub ever fully removes
an asset (not just supersedes it), a fresh-clone rebuild for that
season would fail with a fetch error, not an integrity error -- a
real, disclosed limitation, not a defect. See "REPRODUCIBILITY" below.

REPRODUCIBILITY, exactly what happens on a fresh clone with no cache:
1. fetch_season_raw(season) finds no local file, downloads by the
   asset ID recorded in the COMMITTED manifest (scripts/nflverse_source_manifest.json).
2. Computes sha256 of what it got, compares to the manifest's recorded
   hash.
3. Match -> proceeds (this is the expected, normal case -- asset IDs
   pointing at content that hasn't changed reproduce byte-for-byte).
   Mismatch -> raises loudly, refuses to proceed silently.
   Asset genuinely gone (404 from GitHub) -> the download itself fails
   with an HTTPError, which is a different, equally loud failure mode
   (see "WHAT THIS MODULE DOES NOT DO" above) -- also never silent.

Integrity model, restated precisely:
  - Season in the manifest, hash matches -> proceed silently (the
    normal case, expected on every fresh clone as long as GitHub
    still serves that asset ID).
  - Season in the manifest, hash DIFFERS -> raise loudly, refuse to
    proceed.
  - Season NOT in the manifest -> refuse to proceed until someone
    deliberately calls register_manifest_entry() for it. A manifest
    entry is never written as a side effect of a normal fetch.

EXTENDED TO TWO MORE nflverse RELEASES (Stars-by-Value acquisition-cost
classifier, see research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md
section 3): `players` (draft capital) and `depth_charts` (rookie-QB
Week-1-starter correction). Same asset-ID pinning + sha256 verification
+ explicit-registration-only model as stats_player above, sharing this
module's low-level HTTP/hash/manifest-file primitives. Two real shape
differences from stats_player, each reflected below:
  - `players` is NOT season-grain -- nflverse publishes it as one file
    (players.csv) covering every player and every draft year at once,
    refreshed as a whole. There is no per-season asset to pin
    separately, so register_players_manifest_entry()/fetch_players()
    take no season argument, and the manifest stores a single
    top-level "players" entry rather than a "seasons" dict.
  - `depth_charts` IS season-grain (depth_charts_<season>.csv, one
    file per season, verified present for every season nflverse
    publishes from 2001 through the current season), so it mirrors
    stats_player's per-season pattern almost exactly -- its entries
    live under a "depth_charts": {"seasons": {...}} key, kept separate
    from stats_player's top-level "seasons" key so the two release's
    season-keyed entries can never collide.
Neither addition writes a normalize_*() step: unlike stats_player
(which needed a real REG-only filter and a team->recent_team rename to
match existing downstream expectations), both players.csv and
depth_charts_<season>.csv are consumed by brand-new SBV code with no
pre-existing schema to match, so fetch_players()/fetch_depth_chart()
return the raw parsed CSV as-is.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

GITHUB_API_BASE = "https://api.github.com/repos/nflverse/nflverse-data"
RELEASE_TAG = "stats_player"
ASSET_NAME_TEMPLATE = "stats_player_week_{season}.csv"
# Fallback ONLY -- used by register_manifest_entry() the first time a
# season is being registered and its asset ID isn't known yet. Never
# used by fetch_season_raw() once a manifest entry (with asset_id)
# exists, per the pinning rationale above.
TAG_FILENAME_URL_TEMPLATE = (
    f"https://github.com/nflverse/nflverse-data/releases/download/"
    f"{RELEASE_TAG}/{ASSET_NAME_TEMPLATE}"
)

# Bump this if nflverse changes the stats_player release's shape again
# (column names, season_type values, etc.) -- gives a single, explicit
# marker of which schema generation a cached file belongs to, the same
# way LWI_VERSION marks which formula produced an LWI score.
SCHEMA_VERSION = "nflverse_stats_player_v1"

CACHE_DIR = Path("data/raw/nflverse/annual")
MANIFEST_PATH = Path(__file__).resolve().parent / "nflverse_source_manifest.json"

# --- players (draft capital) -- single file, no season grain ---
PLAYERS_RELEASE_TAG = "players"
PLAYERS_ASSET_NAME = "players.csv"
# Bump if nflverse changes players.csv's column set (verified current
# columns include gsis_id, position, draft_year, draft_round,
# draft_pick, draft_team, rookie_season -- confirmed directly against
# a live download, 2026-07-25, 25,036 rows / 39 columns).
PLAYERS_SCHEMA_VERSION = "nflverse_players_v1"
PLAYERS_CACHE_PATH = Path("data/raw/nflverse/reference/players.csv")

# --- schedules (real per-team game dates -- 2025 rookie-QB depth-chart
# correction needs each team's actual Week 1 kickoff date, since
# depth_charts_2025.csv carries no week label) -- single file, no
# season grain, same shape as players.csv. Confirmed to exist via the
# public GitHub API, 2026-07 (release tag "schedules", asset
# "games.csv") before being wired in here.
SCHEDULES_RELEASE_TAG = "schedules"
SCHEDULES_ASSET_NAME = "games.csv"
# Bump if nflverse changes games.csv's column set (verified current
# columns include game_id, season, game_type, week, gameday, weekday,
# home_team, away_team -- confirmed directly against a live download,
# 2026-07-25).
SCHEDULES_SCHEMA_VERSION = "nflverse_schedules_v1"
SCHEDULES_CACHE_PATH = Path("data/raw/nflverse/reference/games.csv")

# --- depth_charts (rookie-QB Week-1-starter correction) -- season grain ---
DEPTH_CHARTS_RELEASE_TAG = "depth_charts"
DEPTH_CHARTS_ASSET_NAME_TEMPLATE = "depth_charts_{season}.csv"
# Bump if nflverse changes depth_charts's column set (verified current
# columns include season, club_code, week, game_type, depth_team,
# position, gsis_id -- confirmed identical for every one of 2006-2024,
# 2026-07-25).
#
# REAL, VERIFIED SCHEMA BREAK AT 2025: nflverse's depth_charts_2025.csv
# uses a completely different 12-column schema (dt, team, player_name,
# espn_id, gsis_id, pos_grp_id, pos_grp, pos_id, pos_name, pos_abb,
# pos_slot, pos_rank -- no week/game_type/depth_team/position columns
# at all, ~15x the row count of any other season, apparently a
# different upstream vendor/pipeline as of this migration). This
# module still registers and fetches 2025 (raw bytes, pinned and
# hash-verified like every other season -- fetching is schema-agnostic
# by design), but NO consumer code in this repo normalizes or
# interprets the 2025 shape yet. Anything that reads depth_team,
# game_type, position, or week from fetch_depth_chart(2025) will KeyError
# immediately -- a deliberate fail-loud outcome, not a bug, until a
# real decision is made about whether/how to support the new schema.
DEPTH_CHARTS_SCHEMA_VERSION = "nflverse_depth_charts_v1"
DEPTH_CHARTS_CACHE_DIR = Path("data/raw/nflverse/annual")

# Verified directly against 2006-2024 (5,227-row 2024 sample, then all
# 19 seasons): this rename is lossless -- 100% of team assignments
# agree between the old (recent_team) and new (team) release naming.
TEAM_COLUMN_RENAME = {"team": "recent_team"}

# --- snap_counts (Dataset 2 opportunity/usage foundation, Source B) --
# season grain, same shape as depth_charts. Confirmed via the public
# GitHub API and a real direct download, 2026-07: real columns are
# game_id, pfr_game_id, season, game_type, week, player, pfr_player_id,
# position, team, opponent, offense_snaps, offense_pct, defense_snaps,
# defense_pct, st_snaps, st_pct. Identifies players by `pfr_player_id`
# (Pro Football Reference format, e.g. "WillCh03"), NOT gsis_id --
# lib/dataset2/snap_identity.py crosswalks this via players.csv's own
# `pfr_id` column (verified 99.9% real match rate).
SNAP_COUNTS_RELEASE_TAG = "snap_counts"
SNAP_COUNTS_ASSET_NAME_TEMPLATE = "snap_counts_{season}.csv"
SNAP_COUNTS_SCHEMA_VERSION = "nflverse_snap_counts_v1"
SNAP_COUNTS_CACHE_DIR = Path("data/raw/nflverse/annual")

# REAL, VERIFIED COVERAGE GAP: the release tag nominally spans
# 2012-2025, but the real 2012 asset is a header-only file (154 bytes,
# zero data rows -- confirmed by downloading it directly, 2026-07).
# Real, usable coverage is 2013-2025. register_snap_counts_manifest_entry()
# refuses 2012 rather than silently caching an empty file as if it were
# real coverage -- see that function's own fail-loud check.
SNAP_COUNTS_EMPTY_SEASON = 2012
SNAP_COUNTS_FIRST_REAL_SEASON = 2013

# --- pbp_participation (Dataset 2 opportunity/usage foundation,
# Source C, Stage 1) -- PLAY-level grain (one row per real play, NOT
# per player-week like snap_counts/stats_player). Real columns
# (2016-2022 and the legacy 2023 file): nflverse_game_id, old_game_id,
# play_id, possession_team, offense_formation, offense_personnel,
# defenders_in_box, defense_personnel, number_of_pass_rushers,
# players_on_play, offense_players, defense_players, n_offense,
# n_defense, ngs_air_yards, time_to_throw, was_pressure, route,
# defense_man_zone_type, defense_coverage_type. `offense_players`/
# `defense_players` are semicolon-delimited real `gsis_id` lists (NOT
# pfr_id -- no crosswalk needed for this source, unlike snap_counts).
# There is no `season`/`week`/`game_type` column -- both are encoded in
# `nflverse_game_id` ("{season}_{week_token}_{away}_{home}", verified
# directly, e.g. "2016_01_CAR_DEN"), and postseason rows are NOT
# separately labeled -- a real week_token beyond that season's real
# REG week-slot count (lib.dataset2.common.season_length(season) + 1,
# the same real "+1 for the bye slot" fact already established for
# Source A) is a real playoff game. Verified directly: 2016 (16-game
# era) week tokens run 01-21 (17 REG-including-bye + 4 playoff
# rounds); 2022 (17-game era) run 01-22 (18 + 4) -- confirms the same
# +4-playoff-rounds pattern in both eras.
PBP_PARTICIPATION_RELEASE_TAG = "pbp_participation"
PBP_PARTICIPATION_ASSET_NAME_TEMPLATE = "pbp_participation_{season}.csv"
PBP_PARTICIPATION_SCHEMA_VERSION_OLD = "nflverse_pbp_participation_v1_20col"
PBP_PARTICIPATION_SCHEMA_VERSION_NEW = "nflverse_pbp_participation_v2_26col"
PBP_PARTICIPATION_CACHE_DIR = Path("data/raw/nflverse/annual")

# REAL, VERIFIED SCHEMA FORK AT 2023: nflverse published TWO real
# files under the "2023" asset name -- `pbp_participation_2023.csv`
# (49.9MB, the NEW 26-column schema, adding offense_names/
# defense_names/offense_positions/defense_positions/offense_numbers/
# defense_numbers on top of the original 20) and
# `pbp_participation_old_2023.csv` (19.7MB, the ORIGINAL 20-column
# schema matching 2016-2022 exactly). Real 2024/2025 file sizes
# (~49-50MB) match the NEW format, confirming it is what the release
# continues using going forward -- so `pbp_participation_2023.csv`
# (the NEW, 26-column file) is CANONICAL for season 2023 in this
# project, kept schema-consistent with 2024/2025 rather than with
# 2016-2022. `pbp_participation_old_2023.csv` is NOT registered or
# fetched by this module -- it is a legacy/transitional artifact, not
# a second real season of data. lib/dataset2/participation_traits.py
# supports BOTH real schema shapes (20-column, real for 2016-2022; and
# 26-column, real for 2023-2025) and is tested against real examples
# of each -- the 20-column shape does not go away, it's simply not
# season 2023's canonical file.
PBP_PARTICIPATION_OLD_2023_ASSET_NAME = "pbp_participation_old_2023.csv"
PBP_PARTICIPATION_SCHEMA_FORK_SEASON = 2023
PBP_PARTICIPATION_FIRST_REAL_SEASON = 2016


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"schema_version": SCHEMA_VERSION, "seasons": {}}


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _lookup_asset_id_by_name(release_tag: str, asset_name: str) -> dict:
    """Generic form behind _lookup_asset_id() below -- queries one
    release's asset list once and finds the entry with the given
    filename. Shared by all three releases this module fetches from
    (stats_player, players, depth_charts); only called by a
    register_*_manifest_entry() function, never by a bare fetch."""
    resp = requests.get(f"{GITHUB_API_BASE}/releases/tags/{release_tag}", timeout=30)
    resp.raise_for_status()
    assets = resp.json().get("assets", [])
    for a in assets:
        if a["name"] == asset_name:
            return {"asset_id": a["id"], "upstream_updated_at": a["updated_at"]}
    raise RuntimeError(f"No asset named {asset_name} found in the {release_tag} release.")


def _lookup_asset_id(season: int) -> dict:
    """Queries the release's asset list once and finds the entry for
    this season's file -- only called by register_manifest_entry(),
    never by a bare fetch."""
    return _lookup_asset_id_by_name(RELEASE_TAG, ASSET_NAME_TEMPLATE.format(season=season))


def _download_by_asset_id(asset_id: int, local_path: Path) -> None:
    url = f"{GITHUB_API_BASE}/releases/assets/{asset_id}"
    resp = requests.get(url, headers={"Accept": "application/octet-stream"}, timeout=120)
    resp.raise_for_status()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(resp.content)


def _download_by_tag_filename(season: int, local_path: Path) -> None:
    """Bootstrap-only path -- see module docstring's PINNING section."""
    url = TAG_FILENAME_URL_TEMPLATE.format(season=season)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(resp.content)


def register_manifest_entry(season: int, force: bool = False) -> dict:
    """The ONLY function that writes or updates a manifest entry --
    always an explicit, deliberate call (run once per season as part
    of this migration, or again later if a real upstream correction
    is being knowingly accepted), never a side effect of a normal
    pipeline run. That separation is the whole integrity mechanism:
    a bare fetch can only VERIFY against this record, never silently
    rewrite it."""
    local_path = CACHE_DIR / f"stats_player_week_{season}.csv"
    asset_info = _lookup_asset_id(season)

    if force or not local_path.exists():
        _download_by_asset_id(asset_info["asset_id"], local_path)

    manifest = _load_manifest()
    with open(local_path, "rb") as f:
        row_count = sum(1 for _ in f) - 1  # minus header
    manifest["seasons"][str(season)] = {
        "asset_id": asset_info["asset_id"],
        "upstream_updated_at": asset_info["upstream_updated_at"],
        "asset_url": f"{GITHUB_API_BASE}/releases/assets/{asset_info['asset_id']}",
        "bootstrap_url": TAG_FILENAME_URL_TEMPLATE.format(season=season),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(local_path),
        "schema_version": SCHEMA_VERSION,
        "row_count": row_count,
    }
    _save_manifest(manifest)
    return manifest["seasons"][str(season)]


def fetch_season_raw(season: int) -> Path:
    """Downloads (or reuses a cached copy of) one season's raw weekly
    file BY ITS PINNED ASSET ID from the committed manifest, then
    verifies it against the manifest's recorded sha256 before
    returning the local path. Never writes the manifest itself. This
    is what a fresh clone with no cache actually does -- see module
    docstring's REPRODUCIBILITY section."""
    manifest = _load_manifest()
    recorded = manifest["seasons"].get(str(season))
    if recorded is None:
        raise RuntimeError(
            f"Season {season} has no entry in {MANIFEST_PATH.name}. If this "
            f"is a genuinely new season, call "
            f"register_manifest_entry({season}) deliberately to record its "
            f"baseline asset id and hash before it can be used by the "
            f"pipeline -- this is never done automatically."
        )

    local_path = CACHE_DIR / f"stats_player_week_{season}.csv"
    if not local_path.exists():
        _download_by_asset_id(recorded["asset_id"], local_path)

    file_hash = _sha256(local_path)
    if recorded["sha256"] != file_hash:
        raise RuntimeError(
            f"INTEGRITY CHECK FAILED for season {season}: the file at "
            f"{recorded['asset_url']} no longer matches the sha256 recorded "
            f"in {MANIFEST_PATH.name} (recorded {recorded['sha256'][:12]}..., "
            f"got {file_hash[:12]}...). Despite asset-ID pinning, nflverse "
            f"appears to have changed this specific asset's content -- "
            f"likely a real upstream stat correction (166 such rows were "
            f"found across 2006-2024 during the original migration, see "
            f"CHANGELOG.md). Do not silently proceed. Investigate what "
            f"changed, then deliberately call "
            f"register_manifest_entry({season}, force=True) to accept the "
            f"new data as the new baseline."
        )
    return local_path


def normalize_weekly(raw_path: Path) -> pd.DataFrame:
    """Filters to REG season only and renames team -> recent_team, so
    output matches exactly what 03_download_stats.py already expects
    -- no downstream logic in that script needs to change."""
    df = pd.read_csv(raw_path, low_memory=False)
    df = df[df["season_type"] == "REG"].copy()
    df = df.rename(columns=TEAM_COLUMN_RENAME)
    return df


def fetch_and_normalize(season: int) -> pd.DataFrame:
    path = fetch_season_raw(season)
    return normalize_weekly(path)


# --- players (draft capital) -- single file, no season grain ---


def register_players_manifest_entry(force: bool = False) -> dict:
    """The ONLY function that writes or updates the "players" manifest
    entry -- same integrity model as register_manifest_entry() above,
    see module docstring's PINNING/REPRODUCIBILITY sections. There is
    no per-season asset here (see "EXTENDED TO TWO MORE..." in the
    module docstring), so this stores one entry, not a seasons dict."""
    asset_info = _lookup_asset_id_by_name(PLAYERS_RELEASE_TAG, PLAYERS_ASSET_NAME)

    if force or not PLAYERS_CACHE_PATH.exists():
        _download_by_asset_id(asset_info["asset_id"], PLAYERS_CACHE_PATH)

    manifest = _load_manifest()
    with open(PLAYERS_CACHE_PATH, "rb") as f:
        row_count = sum(1 for _ in f) - 1  # minus header
    manifest["players"] = {
        "asset_id": asset_info["asset_id"],
        "upstream_updated_at": asset_info["upstream_updated_at"],
        "asset_url": f"{GITHUB_API_BASE}/releases/assets/{asset_info['asset_id']}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(PLAYERS_CACHE_PATH),
        "schema_version": PLAYERS_SCHEMA_VERSION,
        "row_count": row_count,
    }
    _save_manifest(manifest)
    return manifest["players"]


def fetch_players_raw() -> Path:
    """Downloads (or reuses a cached copy of) players.csv BY ITS
    PINNED ASSET ID from the committed manifest, then verifies it
    against the manifest's recorded sha256 before returning the local
    path. Never writes the manifest itself."""
    manifest = _load_manifest()
    recorded = manifest.get("players")
    if recorded is None:
        raise RuntimeError(
            f"players.csv has no entry in {MANIFEST_PATH.name}. Call "
            f"register_players_manifest_entry() deliberately to record "
            f"its baseline asset id and hash before it can be used by "
            f"the pipeline -- this is never done automatically."
        )

    if not PLAYERS_CACHE_PATH.exists():
        _download_by_asset_id(recorded["asset_id"], PLAYERS_CACHE_PATH)

    file_hash = _sha256(PLAYERS_CACHE_PATH)
    if recorded["sha256"] != file_hash:
        raise RuntimeError(
            f"INTEGRITY CHECK FAILED for players.csv: the file at "
            f"{recorded['asset_url']} no longer matches the sha256 recorded "
            f"in {MANIFEST_PATH.name} (recorded {recorded['sha256'][:12]}..., "
            f"got {file_hash[:12]}...). Do not silently proceed. Investigate "
            f"what changed, then deliberately call "
            f"register_players_manifest_entry(force=True) to accept the new "
            f"data as the new baseline."
        )
    return PLAYERS_CACHE_PATH


def fetch_players() -> pd.DataFrame:
    """Raw players.csv as-is -- no normalize step, see module
    docstring's "EXTENDED TO TWO MORE..." section for why."""
    path = fetch_players_raw()
    return pd.read_csv(path, low_memory=False)


# --- schedules (real per-team game dates) -- single file, no season grain ---


def register_schedules_manifest_entry(force: bool = False) -> dict:
    """The ONLY function that writes or updates the "schedules"
    manifest entry -- same integrity model as
    register_players_manifest_entry() above. One entry, not a seasons
    dict -- games.csv covers every season in one file."""
    asset_info = _lookup_asset_id_by_name(SCHEDULES_RELEASE_TAG, SCHEDULES_ASSET_NAME)

    if force or not SCHEDULES_CACHE_PATH.exists():
        _download_by_asset_id(asset_info["asset_id"], SCHEDULES_CACHE_PATH)

    manifest = _load_manifest()
    with open(SCHEDULES_CACHE_PATH, "rb") as f:
        row_count = sum(1 for _ in f) - 1
    manifest["schedules"] = {
        "asset_id": asset_info["asset_id"],
        "upstream_updated_at": asset_info["upstream_updated_at"],
        "asset_url": f"{GITHUB_API_BASE}/releases/assets/{asset_info['asset_id']}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(SCHEDULES_CACHE_PATH),
        "schema_version": SCHEDULES_SCHEMA_VERSION,
        "row_count": row_count,
    }
    _save_manifest(manifest)
    return manifest["schedules"]


def fetch_schedules_raw() -> Path:
    """Downloads (or reuses a cached copy of) games.csv BY ITS PINNED
    ASSET ID from the committed manifest, then verifies it against the
    manifest's recorded sha256 before returning the local path. Never
    writes the manifest itself."""
    manifest = _load_manifest()
    recorded = manifest.get("schedules")
    if recorded is None:
        raise RuntimeError(
            f"games.csv has no entry in {MANIFEST_PATH.name}. Call "
            f"register_schedules_manifest_entry() deliberately to record "
            f"its baseline asset id and hash before it can be used by "
            f"the pipeline -- this is never done automatically."
        )

    if not SCHEDULES_CACHE_PATH.exists():
        _download_by_asset_id(recorded["asset_id"], SCHEDULES_CACHE_PATH)

    file_hash = _sha256(SCHEDULES_CACHE_PATH)
    if recorded["sha256"] != file_hash:
        raise RuntimeError(
            f"INTEGRITY CHECK FAILED for games.csv: the file at "
            f"{recorded['asset_url']} no longer matches the sha256 recorded "
            f"in {MANIFEST_PATH.name} (recorded {recorded['sha256'][:12]}..., "
            f"got {file_hash[:12]}...). Do not silently proceed. Investigate "
            f"what changed, then deliberately call "
            f"register_schedules_manifest_entry(force=True) to accept the new "
            f"data as the new baseline."
        )
    return SCHEDULES_CACHE_PATH


def fetch_schedules() -> pd.DataFrame:
    """Raw games.csv as-is -- no normalize step, same convention as
    fetch_players()."""
    path = fetch_schedules_raw()
    return pd.read_csv(path, low_memory=False)


# --- depth_charts (rookie-QB Week-1-starter correction) -- season grain ---


def register_depth_chart_manifest_entry(season: int, force: bool = False) -> dict:
    """The ONLY function that writes or updates a depth_charts manifest
    entry -- mirrors register_manifest_entry() above exactly, just
    keyed under manifest["depth_charts"]["seasons"] instead of the
    top-level "seasons" key stats_player uses, so the two releases'
    season-keyed entries can never collide."""
    local_path = DEPTH_CHARTS_CACHE_DIR / f"depth_charts_{season}.csv"
    asset_info = _lookup_asset_id_by_name(
        DEPTH_CHARTS_RELEASE_TAG, DEPTH_CHARTS_ASSET_NAME_TEMPLATE.format(season=season)
    )

    if force or not local_path.exists():
        _download_by_asset_id(asset_info["asset_id"], local_path)

    manifest = _load_manifest()
    manifest.setdefault("depth_charts", {"seasons": {}})
    with open(local_path, "rb") as f:
        row_count = sum(1 for _ in f) - 1  # minus header
    manifest["depth_charts"]["seasons"][str(season)] = {
        "asset_id": asset_info["asset_id"],
        "upstream_updated_at": asset_info["upstream_updated_at"],
        "asset_url": f"{GITHUB_API_BASE}/releases/assets/{asset_info['asset_id']}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(local_path),
        "schema_version": DEPTH_CHARTS_SCHEMA_VERSION,
        "row_count": row_count,
    }
    _save_manifest(manifest)
    return manifest["depth_charts"]["seasons"][str(season)]


def fetch_depth_chart_raw(season: int) -> Path:
    """Downloads (or reuses a cached copy of) one season's raw
    depth_charts file BY ITS PINNED ASSET ID from the committed
    manifest, then verifies it against the manifest's recorded sha256
    before returning the local path. Never writes the manifest
    itself."""
    manifest = _load_manifest()
    recorded = manifest.get("depth_charts", {}).get("seasons", {}).get(str(season))
    if recorded is None:
        raise RuntimeError(
            f"depth_charts season {season} has no entry in {MANIFEST_PATH.name}. "
            f"If this is a genuinely new season, call "
            f"register_depth_chart_manifest_entry({season}) deliberately to "
            f"record its baseline asset id and hash before it can be used by "
            f"the pipeline -- this is never done automatically."
        )

    local_path = DEPTH_CHARTS_CACHE_DIR / f"depth_charts_{season}.csv"
    if not local_path.exists():
        _download_by_asset_id(recorded["asset_id"], local_path)

    file_hash = _sha256(local_path)
    if recorded["sha256"] != file_hash:
        raise RuntimeError(
            f"INTEGRITY CHECK FAILED for depth_charts season {season}: the "
            f"file at {recorded['asset_url']} no longer matches the sha256 "
            f"recorded in {MANIFEST_PATH.name} (recorded "
            f"{recorded['sha256'][:12]}..., got {file_hash[:12]}...). Do not "
            f"silently proceed. Investigate what changed, then deliberately "
            f"call register_depth_chart_manifest_entry({season}, force=True) "
            f"to accept the new data as the new baseline."
        )
    return local_path


def fetch_depth_chart(season: int) -> pd.DataFrame:
    """Raw depth_charts_<season>.csv as-is -- no normalize step, see
    module docstring's "EXTENDED TO TWO MORE..." section for why."""
    path = fetch_depth_chart_raw(season)
    return pd.read_csv(path, low_memory=False)


# --- snap_counts (Dataset 2 opportunity/usage foundation, Source B) ---


def register_snap_counts_manifest_entry(season: int, force: bool = False) -> dict:
    """The ONLY function that writes or updates a snap_counts manifest
    entry -- mirrors register_depth_chart_manifest_entry() exactly,
    keyed under manifest["snap_counts"]["seasons"]. Refuses season
    2012 outright (real, confirmed empty asset -- see
    SNAP_COUNTS_EMPTY_SEASON's own comment) rather than silently
    caching a header-only file as if it were real coverage."""
    if season == SNAP_COUNTS_EMPTY_SEASON:
        raise ValueError(
            f"snap_counts season {SNAP_COUNTS_EMPTY_SEASON} is a real, confirmed "
            f"empty asset (header row only, zero data rows) -- not a genuine "
            f"coverage year. Refusing to register it. Real snap_counts coverage "
            f"starts at {SNAP_COUNTS_FIRST_REAL_SEASON}."
        )

    local_path = SNAP_COUNTS_CACHE_DIR / f"snap_counts_{season}.csv"
    asset_info = _lookup_asset_id_by_name(
        SNAP_COUNTS_RELEASE_TAG, SNAP_COUNTS_ASSET_NAME_TEMPLATE.format(season=season)
    )

    if force or not local_path.exists():
        _download_by_asset_id(asset_info["asset_id"], local_path)

    manifest = _load_manifest()
    manifest.setdefault("snap_counts", {"seasons": {}})
    with open(local_path, "rb") as f:
        row_count = sum(1 for _ in f) - 1  # minus header
    manifest["snap_counts"]["seasons"][str(season)] = {
        "asset_id": asset_info["asset_id"],
        "upstream_updated_at": asset_info["upstream_updated_at"],
        "asset_url": f"{GITHUB_API_BASE}/releases/assets/{asset_info['asset_id']}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(local_path),
        "schema_version": SNAP_COUNTS_SCHEMA_VERSION,
        "row_count": row_count,
    }
    _save_manifest(manifest)
    return manifest["snap_counts"]["seasons"][str(season)]


def fetch_snap_counts_raw(season: int) -> Path:
    """Downloads (or reuses a cached copy of) one season's raw
    snap_counts file BY ITS PINNED ASSET ID from the committed
    manifest, then verifies it against the manifest's recorded sha256
    before returning the local path. Never writes the manifest
    itself."""
    manifest = _load_manifest()
    recorded = manifest.get("snap_counts", {}).get("seasons", {}).get(str(season))
    if recorded is None:
        raise RuntimeError(
            f"snap_counts season {season} has no entry in {MANIFEST_PATH.name}. "
            f"If this is a genuinely new season, call "
            f"register_snap_counts_manifest_entry({season}) deliberately to "
            f"record its baseline asset id and hash before it can be used by "
            f"the pipeline -- this is never done automatically."
        )

    local_path = SNAP_COUNTS_CACHE_DIR / f"snap_counts_{season}.csv"
    if not local_path.exists():
        _download_by_asset_id(recorded["asset_id"], local_path)

    file_hash = _sha256(local_path)
    if recorded["sha256"] != file_hash:
        raise RuntimeError(
            f"INTEGRITY CHECK FAILED for snap_counts season {season}: the "
            f"file at {recorded['asset_url']} no longer matches the sha256 "
            f"recorded in {MANIFEST_PATH.name} (recorded "
            f"{recorded['sha256'][:12]}..., got {file_hash[:12]}...). Do not "
            f"silently proceed. Investigate what changed, then deliberately "
            f"call register_snap_counts_manifest_entry({season}, force=True) "
            f"to accept the new data as the new baseline."
        )
    return local_path


def fetch_snap_counts(season: int) -> pd.DataFrame:
    """Raw snap_counts_<season>.csv as-is -- no normalize step, same
    convention as fetch_depth_chart()/fetch_players()."""
    path = fetch_snap_counts_raw(season)
    return pd.read_csv(path, low_memory=False)


# --- pbp_participation (Dataset 2 opportunity/usage foundation,
# Source C, Stage 1) ---


def register_pbp_participation_manifest_entry(season: int, force: bool = False) -> dict:
    """The ONLY function that writes or updates a pbp_participation
    manifest entry -- mirrors register_snap_counts_manifest_entry()
    exactly, keyed under manifest["pbp_participation"]["seasons"]. For
    season 2023 specifically, always fetches the real NEW 26-column
    file (`pbp_participation_2023.csv`) -- the canonical one, per this
    module's own PBP_PARTICIPATION_SCHEMA_FORK_SEASON comment --
    `pbp_participation_old_2023.csv` is never registered here."""
    local_path = PBP_PARTICIPATION_CACHE_DIR / f"pbp_participation_{season}.csv"
    asset_info = _lookup_asset_id_by_name(
        PBP_PARTICIPATION_RELEASE_TAG, PBP_PARTICIPATION_ASSET_NAME_TEMPLATE.format(season=season)
    )

    if force or not local_path.exists():
        _download_by_asset_id(asset_info["asset_id"], local_path)

    schema_version = (
        PBP_PARTICIPATION_SCHEMA_VERSION_NEW
        if season >= PBP_PARTICIPATION_SCHEMA_FORK_SEASON
        else PBP_PARTICIPATION_SCHEMA_VERSION_OLD
    )

    manifest = _load_manifest()
    manifest.setdefault("pbp_participation", {"seasons": {}})
    with open(local_path, "rb") as f:
        row_count = sum(1 for _ in f) - 1  # minus header
    manifest["pbp_participation"]["seasons"][str(season)] = {
        "asset_id": asset_info["asset_id"],
        "upstream_updated_at": asset_info["upstream_updated_at"],
        "asset_url": f"{GITHUB_API_BASE}/releases/assets/{asset_info['asset_id']}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(local_path),
        "schema_version": schema_version,
        "row_count": row_count,
    }
    _save_manifest(manifest)
    return manifest["pbp_participation"]["seasons"][str(season)]


def fetch_pbp_participation_raw(season: int) -> Path:
    """Downloads (or reuses a cached copy of) one season's raw
    pbp_participation file BY ITS PINNED ASSET ID from the committed
    manifest, then verifies it against the manifest's recorded sha256
    before returning the local path. Never writes the manifest
    itself."""
    manifest = _load_manifest()
    recorded = manifest.get("pbp_participation", {}).get("seasons", {}).get(str(season))
    if recorded is None:
        raise RuntimeError(
            f"pbp_participation season {season} has no entry in {MANIFEST_PATH.name}. "
            f"If this is a genuinely new season, call "
            f"register_pbp_participation_manifest_entry({season}) deliberately to "
            f"record its baseline asset id and hash before it can be used by "
            f"the pipeline -- this is never done automatically."
        )

    local_path = PBP_PARTICIPATION_CACHE_DIR / f"pbp_participation_{season}.csv"
    if not local_path.exists():
        _download_by_asset_id(recorded["asset_id"], local_path)

    file_hash = _sha256(local_path)
    if recorded["sha256"] != file_hash:
        raise RuntimeError(
            f"INTEGRITY CHECK FAILED for pbp_participation season {season}: the "
            f"file at {recorded['asset_url']} no longer matches the sha256 "
            f"recorded in {MANIFEST_PATH.name} (recorded "
            f"{recorded['sha256'][:12]}..., got {file_hash[:12]}...). Do not "
            f"silently proceed. Investigate what changed, then deliberately "
            f"call register_pbp_participation_manifest_entry({season}, force=True) "
            f"to accept the new data as the new baseline."
        )
    return local_path


def fetch_pbp_participation(season: int) -> pd.DataFrame:
    """Raw pbp_participation_<season>.csv as-is -- no normalize step,
    same convention as fetch_depth_chart()/fetch_snap_counts(). Callers
    needing a schema-uniform view across the 2023 fork should use
    lib.dataset2.participation_traits, which handles both real shapes
    explicitly rather than silently assuming one."""
    path = fetch_pbp_participation_raw(season)
    return pd.read_csv(path, low_memory=False)
