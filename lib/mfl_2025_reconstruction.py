"""Derive governed 2025 MFL acquisition evidence from explicit inputs.

The input cache objects are parsed/re-serialized audit snapshots, not
original HTTP wire bytes and not a recovered original governed package.
No default cache location is permitted: callers must supply both roots.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from config import MFL_2025_GOVERNED_LEAGUE_COUNT
from lib.source_governance import DEFAULT_MANIFEST_PATH, validate_2025_mfl_reconstruction

GOVERNED_LEAGUE_COUNT = MFL_2025_GOVERNED_LEAGUE_COUNT


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def derive_governed_2025_participation(
    *,
    archive_root: Path,
    cache_root: Path,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> pd.DataFrame:
    """Return one row per selected player; absent players stay absent."""
    package = validate_2025_mfl_reconstruction(
        archive_root=archive_root,
        manifest_path=manifest_path,
        cache_root=cache_root,
    )
    reconstruction = json.loads(package["reconstruction_manifest.json"].read_text())
    if reconstruction["included_league_count"] != GOVERNED_LEAGUE_COUNT:
        raise ValueError(f"governed 2025 denominator must be {GOVERNED_LEAGUE_COUNT}")

    with package["league_inclusion_ledger.csv"].open(newline="") as handle:
        included = [row for row in csv.DictReader(handle) if row["included"].lower() == "true"]
    if len(included) != GOVERNED_LEAGUE_COUNT:
        raise ValueError("included reconstruction ledger does not contain exactly 147 leagues")

    player_obj = json.loads((Path(cache_root) / reconstruction["player_directory_cache_file"]).read_text())
    players = {
        str(row["id"]): row
        for row in _as_list(player_obj.get("players", {}).get("player"))
        if row.get("id") is not None
    }
    leagues_by_player: dict[str, set[str]] = defaultdict(set)
    picks_by_player: dict[str, list[int]] = defaultdict(list)

    for league in included:
        league_id = league["league_id"]
        draft_obj = json.loads((Path(cache_root) / league["draft_cache_file"]).read_text())
        units = _as_list(draft_obj.get("draftResults", {}).get("draftUnit"))
        seen_in_league: set[str] = set()
        for unit in units:
            for pick in _as_list(unit.get("draftPick")):
                player_id = str(pick.get("player", "")).strip()
                if not player_id:
                    raise ValueError(f"league {league_id} has a draft pick without player identity")
                if player_id in seen_in_league:
                    raise ValueError(f"league {league_id} selected player {player_id} more than once")
                seen_in_league.add(player_id)
                try:
                    round_number = int(pick["round"])
                    pick_in_round = int(pick["pick"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"league {league_id} has an invalid pick coordinate") from exc
                if round_number < 1 or not 1 <= pick_in_round <= 12:
                    raise ValueError(f"league {league_id} has an out-of-range pick coordinate")
                leagues_by_player[player_id].add(league_id)
                picks_by_player[player_id].append((round_number - 1) * 12 + pick_in_round)

    rows = []
    for player_id in sorted(leagues_by_player):
        meta = players.get(player_id)
        if meta is None:
            raise ValueError(f"selected MFL player {player_id} is absent from governed player directory")
        selection_count = len(leagues_by_player[player_id])
        picks = picks_by_player[player_id]
        if selection_count != len(picks):
            raise ValueError(f"player {player_id} selection count disagrees with pick count")
        rows.append({
            "player_id": player_id,
            "player_name_original": meta.get("name", ""),
            "position": meta.get("position"),
            "team": meta.get("team"),
            "mfl_mean_adp": sum(picks) / len(picks),
            "times_drafted": selection_count,
            "draft_selection_count": selection_count,
            "draft_selection_denominator": GOVERNED_LEAGUE_COUNT,
            "draft_selection_rate": selection_count / GOVERNED_LEAGUE_COUNT,
            "mfl_reconstruction_identity": reconstruction["identity"],
        })
    return pd.DataFrame(rows)
