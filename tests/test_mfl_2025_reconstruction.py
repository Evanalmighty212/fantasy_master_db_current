import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.mfl_2025_reconstruction import derive_governed_2025_participation


def test_derives_147_league_participation_and_keeps_absent_players_absent(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    cache = tmp_path / "cache"
    archive.mkdir()
    cache.mkdir()
    (cache / "players.json").write_text(json.dumps({"players": {"player": [
        {"id": "A", "name": "Alpha, Alice", "position": "WR", "team": "AAA"},
        {"id": "B", "name": "Absent, Bob", "position": "RB", "team": "BBB"},
    ]}}))
    ledger_lines = ["league_id,included,draft_cache_file"]
    for index in range(147):
        filename = f"draft_{index}.json"
        ledger_lines.append(f"L{index},true,{filename}")
        picks = [{"player": "A", "round": "1", "pick": str(index % 12 + 1)}] if index < 52 else []
        (cache / filename).write_text(json.dumps({"draftResults": {"draftUnit": {"draftPick": picks}}}))
    ledger = archive / "league_inclusion_ledger.csv"
    ledger.write_text("\n".join(ledger_lines) + "\n")
    manifest = archive / "reconstruction_manifest.json"
    manifest.write_text(json.dumps({
        "identity": "synthetic-147", "included_league_count": 147,
        "player_directory_cache_file": "players.json",
    }))

    captured = {}
    def validate(**kwargs):
        captured.update(kwargs)
        return {"reconstruction_manifest.json": manifest, "league_inclusion_ledger.csv": ledger}
    monkeypatch.setattr("lib.mfl_2025_reconstruction.validate_2025_mfl_reconstruction", validate)

    result = derive_governed_2025_participation(
        archive_root=archive, cache_root=cache, manifest_path=tmp_path / "public.json",
    )
    assert captured["archive_root"] == archive
    assert captured["cache_root"] == cache
    assert len(result) == 1
    assert result.iloc[0]["player_id"] == "A"
    assert result.iloc[0]["draft_selection_count"] == 52
    assert result.iloc[0]["draft_selection_denominator"] == 147
    assert result.iloc[0]["draft_selection_rate"] == pytest.approx(52 / 147)
    assert result.iloc[0]["times_drafted"] == 52
