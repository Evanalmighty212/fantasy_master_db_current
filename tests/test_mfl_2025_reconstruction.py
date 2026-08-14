import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.mfl_2025_reconstruction import (
    derive_governed_2025_participation,
    normalize_governed_league_picks,
)


def test_derives_142_league_participation_and_keeps_absent_players_absent(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    cache = tmp_path / "cache"
    archive.mkdir()
    cache.mkdir()
    (cache / "players.json").write_text(json.dumps({"players": {"player": [
        {"id": "A", "name": "Alpha, Alice", "position": "WR", "team": "AAA"},
        {"id": "B", "name": "Absent, Bob", "position": "RB", "team": "BBB"},
    ]}}))
    ledger_lines = ["league_id,included,draft_cache_file,expected_pick_count"]
    for index in range(142):
        filename = f"draft_{index}.json"
        ledger_lines.append(f"L{index},true,{filename},1")
        picks = [{"player": "A", "round": "1", "pick": str(index % 12 + 1)}]
        (cache / filename).write_text(json.dumps({"draftResults": {"draftUnit": {"draftPick": picks}}}))
    ledger = archive / "league_inclusion_ledger.csv"
    ledger.write_text("\n".join(ledger_lines) + "\n")
    manifest = archive / "reconstruction_manifest.json"
    manifest.write_text(json.dumps({
        "identity": "synthetic-142", "included_league_count": 142,
        "included_genuine_player_pick_count": 142,
        "player_directory_cache_file": "players.json",
    }))

    captured = {}
    def validate(**kwargs):
        captured.update(kwargs)
        return {"reconstruction_manifest.json": manifest, "league_inclusion_ledger.csv": ledger}
    monkeypatch.setattr("lib.mfl_2025_reconstruction.validate_2025_mfl_reconstruction", validate)
    monkeypatch.setattr("lib.mfl_2025_reconstruction.MFL_2025_GOVERNED_VALID_PICK_COUNT", 142)

    result = derive_governed_2025_participation(
        archive_root=archive, cache_root=cache, manifest_path=tmp_path / "public.json",
    )
    assert captured["archive_root"] == archive
    assert captured["cache_root"] == cache
    assert len(result) == 1
    assert result.iloc[0]["player_id"] == "A"
    assert result.iloc[0]["draft_selection_count"] == 142
    assert result.iloc[0]["draft_selection_denominator"] == 142
    assert result.iloc[0]["draft_selection_rate"] == pytest.approx(1.0)
    assert result.iloc[0]["times_drafted"] == 142


def test_repeated_skipped_placeholders_fail_before_duplicate_validation():
    picks = [
        {"player": "----", "comments": "[Pick skipped by Commissioner]", "round": "1", "pick": "1"},
        {"player": "----", "comments": "[Pick skipped by Commissioner]", "round": "1", "pick": "2"},
    ]
    with pytest.raises(ValueError, match="non-player skipped-pick placeholder"):
        normalize_governed_league_picks(picks, player_ids={"A"}, league_id="L", expected_pick_count=2)


def test_real_duplicate_player_still_fails_loudly():
    picks = [
        {"player": "A", "comments": "", "round": "1", "pick": "1"},
        {"player": "A", "comments": "", "round": "1", "pick": "2"},
    ]
    with pytest.raises(ValueError, match="selected player A more than once"):
        normalize_governed_league_picks(picks, player_ids={"A"}, league_id="L", expected_pick_count=2)


def test_valid_pick_count_and_directory_identity_are_enforced():
    one = [{"player": "A", "comments": "", "round": "1", "pick": "1"}]
    with pytest.raises(ValueError, match="1 genuine picks; expected 2"):
        normalize_governed_league_picks(one, player_ids={"A"}, league_id="L", expected_pick_count=2)
    with pytest.raises(ValueError, match="unresolved player identity '0801'"):
        normalize_governed_league_picks(
            [{"player": "0801", "comments": "", "round": "1", "pick": "1"}],
            player_ids={"A"}, league_id="44425", expected_pick_count=1,
        )
