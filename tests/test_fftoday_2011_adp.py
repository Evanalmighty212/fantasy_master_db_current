import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import fftoday_2011_adp as adapter


def _html(*, metadata: str | None = None, rows: str | None = None) -> bytes:
    metadata = metadata or (
        "12-Team PPR Data Based On 374 Drafts between Sep. 4, 2011 and Sep. 5, 2011"
    )
    rows = rows or """
      <tr><td>Arian Foster</td><td>HOU</td><td>RB</td><td>1.4</td></tr>
      <tr><td>Aaron Rodgers</td><td>GB</td><td>QB</td><td>7.2</td></tr>
      <tr><td>Packers DST</td><td>GB</td><td>DEF</td><td>150.0</td></tr>
    """
    return f"""
    <html><body><div>{metadata}</div>
      <table><tr><th>Player</th><th>Team</th><th>Pos</th><th>Overall</th></tr>{rows}</table>
    </body></html>
    """.encode()


def test_parser_requires_governed_page_claims_and_extracts_skill_rows():
    rows = adapter.parse_governed_2011_html(_html())
    assert rows == [
        {"name": "Arian Foster", "position": "RB", "team": "HOU", "overall_adp": 1.4},
        {"name": "Aaron Rodgers", "position": "QB", "team": "GB", "overall_adp": 7.2},
    ]


@pytest.mark.parametrize("missing", ["374 Drafts", "12-Team", "PPR", "Sep. 4", "Sep. 5", "2011"])
def test_parser_fails_when_a_required_source_claim_is_missing(missing):
    metadata = "12-Team PPR Data Based On 374 Drafts between Sep. 4, 2011 and Sep. 5, 2011"
    with pytest.raises(ValueError, match="missing required source claim"):
        adapter.parse_governed_2011_html(_html(metadata=metadata.replace(missing, "REMOVED")))


def test_loader_validates_private_bytes_before_parsing(tmp_path, monkeypatch):
    source = tmp_path / "private.html"
    source.write_bytes(_html())
    calls = {}

    def validate(*, archive_root, manifest_path):
        calls.update(archive_root=archive_root, manifest_path=manifest_path)
        return source

    monkeypatch.setattr(adapter, "validate_2011_fftoday_source", validate)
    rows = adapter.load_governed_2011_adp(
        archive_root=tmp_path / "archive", manifest_path=tmp_path / "manifest.json",
    )
    assert len(rows) == 2
    assert calls == {
        "archive_root": tmp_path / "archive",
        "manifest_path": tmp_path / "manifest.json",
    }


def test_duplicate_player_position_team_rows_fail_loudly():
    duplicate = """
      <tr><td>Arian Foster</td><td>HOU</td><td>RB</td><td>1.4</td></tr>
      <tr><td>Arian Foster</td><td>HOU</td><td>RB</td><td>1.4</td></tr>
    """
    with pytest.raises(ValueError, match="duplicate"):
        adapter.parse_governed_2011_html(_html(rows=duplicate))
