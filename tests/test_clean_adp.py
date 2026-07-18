"""
tests/test_clean_adp.py

Covers scripts/02_clean_adp.py. The contamination-detection test is a
regression test for a real finding: FFC's 2007/2008 standard archives
claimed success with real metadata but spanned 659-1026 days instead
of a real single-season snapshot (see docs/ADP_SOURCE_MATRIX.md).
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "02_clean_adp.py"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw" / "adp").mkdir(parents=True)
    (tmp_path / "docs").mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("clean_adp", SCRIPT_PATH)
    m = importlib.util.module_from_spec(spec)
    sys.modules["clean_adp"] = m
    spec.loader.exec_module(m)
    return m


class TestNormalizeName:
    def test_strips_parenthetical_and_periods(self, mod):
        assert mod.normalize_name("Steve Smith(NYG)") == "steve smith"
        assert mod.normalize_name("T.J. Houshmandzadeh") == "tj houshmandzadeh"


class TestContaminationDetection:
    def _write_ffc_json(self, tmp_path, year, scoring, start_date, end_date, players):
        path = tmp_path / "data" / "raw" / "adp" / f"ffc_adp_{year}_{scoring}.json"
        payload = {
            "status": "Success",
            "meta": {
                "type": scoring, "teams": 12, "rounds": 15,
                "total_drafts": 500, "start_date": start_date, "end_date": end_date,
            },
            "players": players,
        }
        path.write_text(json.dumps(payload))

    def test_clean_short_snapshot_is_accepted(self, mod, tmp_path):
        # A real single-season window (e.g. 5 days, like the actual
        # verified 2010 FFC data).
        self._write_ffc_json(
            tmp_path, 2010, "ppr", "2010-09-03", "2010-09-08",
            [{"name": "Test Player", "position": "RB", "team": "AAA", "adp": 1.5}],
        )
        rows, flag, notes = mod.load_ffc_source(2010, "ppr")
        assert rows is not None
        assert flag == "verified_clean"

    def test_multi_year_contaminated_window_is_rejected(self, mod, tmp_path):
        # Regression test for the real 2007/2008 FFC finding: a window
        # spanning 659+ days is not a real single-season snapshot and
        # must be excluded, even though the response claims "Success"
        # with real-looking metadata.
        self._write_ffc_json(
            tmp_path, 2008, "standard", "2008-08-30", "2010-06-20",  # 659 days
            [{"name": "Test Player", "position": "RB", "team": "AAA", "adp": 1.5}],
        )
        rows, flag, notes = mod.load_ffc_source(2008, "standard")
        assert rows is None, "Contaminated multi-season window was not rejected"
        assert flag == "contaminated_multi_season"

    def test_success_status_with_zero_players_is_flagged_not_treated_as_empty(self, mod, tmp_path):
        # Regression test for the real 2007 anomaly: status=Success,
        # real metadata, but zero players -- a different, more
        # dangerous failure mode than a clean "no data" error, and
        # must be distinguished from it.
        self._write_ffc_json(tmp_path, 2007, "standard", "2007-08-29", "2010-06-20", [])
        rows, flag, notes = mod.load_ffc_source(2007, "standard")
        assert rows is None
        assert flag == "verified_wrong_format"

    def test_clean_error_response_is_distinguished_from_contamination(self, mod, tmp_path):
        path = tmp_path / "data" / "raw" / "adp" / "ffc_adp_2025_ppr.json"
        path.write_text(json.dumps({"status": "Error", "errors": "No ADP data found."}))
        rows, flag, notes = mod.load_ffc_source(2025, "ppr")
        assert rows is None
        assert flag == "verified_empty"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
