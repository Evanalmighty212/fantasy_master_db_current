import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import fftoday_2011_adp as adapter


def _html(*, metadata: str | None = None, rows: str | None = None) -> bytes:
    metadata = metadata or (
        "Average Draft Position (ADP) All Positions - 9/6/11 ADP History 2011 "
        "Courtesy of: Fantasy Football Calculator Data Based On: "
        "374 drafts between 9/4 - 9/5 12 Teams, PPR Scoring"
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


def test_written_month_equivalent_is_also_accepted():
    metadata = (
        "12-Team PPR 2011 Data Based On: "
        "374 drafts between September 4, 2011 and September 5, 2011"
    )
    assert len(adapter.parse_governed_2011_html(_html(metadata=metadata))) == 2


@pytest.mark.parametrize("bad_window", [
    "374 drafts between 9/3 - 9/5",
    "374 drafts between 9/4 - 9/6",
    "374 drafts between 9/5 - 9/4",
    "374 drafts between 9/4 - 9/15",
    "374 drafts between 9/4/10 - 9/5/10",
])
def test_wrong_numeric_draft_windows_fail(bad_window):
    metadata = f"2011 12 Teams, PPR Scoring Data Based On: {bad_window}"
    with pytest.raises(ValueError, match="September 4 boundary|September 5 boundary"):
        adapter.parse_governed_2011_html(_html(metadata=metadata))


@pytest.mark.parametrize("metadata", [
    "2011 12 Teams, PPR Scoring Data Based On: 473 drafts between 9/4 - 9/5",
    "2011 10 Teams, PPR Scoring Data Based On: 374 drafts between 9/4 - 9/5",
    "2011 12 Teams, Standard Scoring Data Based On: 374 drafts between 9/4 - 9/5",
    "12 Teams, PPR Scoring Data Based On: 374 drafts between 9/4 - 9/5",
])
def test_other_governed_page_claims_still_fail_when_wrong(metadata):
    with pytest.raises(ValueError, match="missing required source claim"):
        adapter.parse_governed_2011_html(_html(metadata=metadata))


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
