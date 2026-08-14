"""Parser for the governed pre-kickoff 2011 FFToday-hosted FFC page."""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from lib.source_governance import DEFAULT_MANIFEST_PATH, validate_2011_fftoday_source

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}
EXPECTED_DRAFT_COUNT = 374


def _normalized_text(soup: BeautifulSoup) -> str:
    return " ".join(soup.get_text(" ", strip=True).split())


def _has_expected_draft_window(text: str) -> bool:
    """Recognize only the governed Sept. 4-5 window after its source label.

    The preserved page uses ``374 drafts between 9/4 - 9/5``. The
    written-month form remains supported for equivalent archival markup;
    neither pattern accepts a widened, reversed, or different window.
    """
    september_4 = r"(?:9/4(?:/2011|/11)?|sep(?:tember)?\.?\s*4(?:th)?(?:,?\s*2011)?)"
    september_5 = r"(?:9/5(?:/2011|/11)?|sep(?:tember)?\.?\s*5(?:th)?(?:,?\s*2011)?)"
    return bool(re.search(
        rf"\b{EXPECTED_DRAFT_COUNT}\s+drafts?\s+between\s+"
        rf"{september_4}\s*(?:-|and|to|through)\s*{september_5}\b",
        text.lower(),
    ))


def _require_page_claims(text: str) -> None:
    lower = text.lower()
    expected_window = _has_expected_draft_window(lower)
    checks = {
        "12-team format": bool(re.search(r"12\s*[- ]?team", lower)),
        "PPR scoring": "ppr" in lower or "point per reception" in lower,
        "374-draft sample": bool(re.search(
            rf"\b{EXPECTED_DRAFT_COUNT}\b[^.]{{0,30}}\bdrafts?\b|"
            rf"\bdrafts?\b[^.]{{0,30}}\b{EXPECTED_DRAFT_COUNT}\b",
            lower,
        )),
        "September 4 boundary": expected_window,
        "September 5 boundary": expected_window,
        "2011 season/date": "2011" in lower,
    }
    missing = [label for label, present in checks.items() if not present]
    if missing:
        raise ValueError(f"governed 2011 page is missing required source claim(s): {missing}")


def _cell_text(cell) -> str:
    return " ".join(cell.get_text(" ", strip=True).split())


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _extract_table_rows(soup: BeautifulSoup) -> list[dict]:
    """Find the semantic Player/Pos/Team/Overall table without fixed indexes."""
    candidates: list[list[dict]] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_index = None
        header_names = None
        for index, row in enumerate(rows):
            cells = row.find_all(["th", "td"], recursive=False)
            names = [_normalized_header(_cell_text(cell)) for cell in cells]
            if {"player", "team", "pos", "overall"}.issubset(names):
                header_index, header_names = index, names
                break
        if header_names is None:
            continue
        extracted = []
        for row in rows[header_index + 1:]:
            cells = row.find_all("td", recursive=False)
            if len(cells) != len(header_names):
                continue
            values = dict(zip(header_names, [_cell_text(cell) for cell in cells]))
            position = values["pos"].upper()
            if position not in SKILL_POSITIONS:
                continue
            try:
                overall = float(values["overall"])
            except ValueError:
                continue
            if not values["player"] or not values["team"] or overall <= 0:
                raise ValueError("governed 2011 page contains an invalid player row")
            extracted.append({
                "name": values["player"], "position": position,
                "team": values["team"], "overall_adp": overall,
            })
        if extracted:
            candidates.append(extracted)
    if not candidates:
        raise ValueError("governed 2011 page has no parseable Player/Team/Pos/Overall table")
    rows = max(candidates, key=len)
    identities = [(row["name"], row["position"], row["team"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("governed 2011 page contains duplicate player-position-team rows")
    return rows


def parse_governed_2011_html(html: bytes) -> list[dict]:
    """Parse already-validated bytes; useful for deterministic fixtures."""
    soup = BeautifulSoup(html, "lxml")
    _require_page_claims(_normalized_text(soup))
    return _extract_table_rows(soup)


def load_governed_2011_adp(
    *, archive_root: Path, manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> list[dict]:
    """Validate the private snapshot before parsing its exact bytes."""
    source_path = validate_2011_fftoday_source(
        archive_root=archive_root, manifest_path=manifest_path,
    )
    return parse_governed_2011_html(source_path.read_bytes())
