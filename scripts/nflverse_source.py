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

# Verified directly against 2006-2024 (5,227-row 2024 sample, then all
# 19 seasons): this rename is lossless -- 100% of team assignments
# agree between the old (recent_team) and new (team) release naming.
TEAM_COLUMN_RENAME = {"team": "recent_team"}


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


def _lookup_asset_id(season: int) -> dict:
    """Queries the release's asset list once and finds the entry for
    this season's file -- only called by register_manifest_entry(),
    never by a bare fetch."""
    resp = requests.get(f"{GITHUB_API_BASE}/releases/tags/{RELEASE_TAG}", timeout=30)
    resp.raise_for_status()
    assets = resp.json().get("assets", [])
    name = ASSET_NAME_TEMPLATE.format(season=season)
    for a in assets:
        if a["name"] == name:
            return {"asset_id": a["id"], "upstream_updated_at": a["updated_at"]}
    raise RuntimeError(f"No asset named {name} found in the {RELEASE_TAG} release.")


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
