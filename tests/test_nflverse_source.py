"""
tests/test_nflverse_source.py

Covers scripts/nflverse_source.py -- the raw-download + normalization +
integrity layer that replaced nfl_data_py.import_weekly_data() (see
CHANGELOG.md for why: nflverse deprecated the release nfl_data_py read
from, 2025-08-01, frozen, confirmed it will never receive 2025+ data).

Each test protects a real, documented behavior this migration depends
on, not speculative coverage:
- normalize_weekly's REG-only filter and team->recent_team rename are
  the two concrete schema-compatibility facts the whole migration was
  verified against (see the module's own docstring and CHANGELOG.md's
  166-corrected-row / 0-eligibility-flip findings) -- a regression
  here would silently reintroduce playoff weeks into season totals or
  break every downstream team-based aggregation in 03_download_stats.py.
- The integrity-check tests protect the actual point of the manifest:
  that a season missing from it, or one whose asset no longer matches
  its recorded hash, must fail loudly rather than let the pipeline
  silently run on different data than what was verified.
- TestEmptyCacheRetrieval protects the literal "fresh clone" scenario
  a reviewer asked to be verified directly (no local cache file
  present) -- confirmed manually against the real GitHub API during
  the migration (2010 and 2025 both re-fetched clean from an emptied
  cache), reproduced here with a mocked network call so it runs
  offline in CI.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pandas as pd
import pytest

import nflverse_source as ns


@pytest.fixture
def synthetic_raw_csv(tmp_path):
    """A tiny raw file matching the real stats_player schema closely
    enough to exercise normalize_weekly: REG + POST rows, 'team' column
    (not 'recent_team')."""
    df = pd.DataFrame({
        "player_id": ["00-001", "00-001", "00-002", "00-002"],
        "player_display_name": ["Player A", "Player A", "Player B", "Player B"],
        "position": ["RB", "RB", "WR", "WR"],
        "season": [2024, 2024, 2024, 2024],
        "week": [1, 19, 1, 19],
        "season_type": ["REG", "POST", "REG", "POST"],
        "team": ["KC", "KC", "SF", "SF"],
        "fantasy_points_ppr": [10.0, 20.0, 5.0, 15.0],
    })
    path = tmp_path / "stats_player_week_2024.csv"
    df.to_csv(path, index=False)
    return path


def _fake_response(content: bytes):
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status = MagicMock()
    return resp


class TestNormalizeWeekly:
    def test_excludes_post_rows(self, synthetic_raw_csv):
        out = ns.normalize_weekly(synthetic_raw_csv)
        assert set(out["week"]) == {1}
        assert len(out) == 2

    def test_renames_team_to_recent_team(self, synthetic_raw_csv):
        out = ns.normalize_weekly(synthetic_raw_csv)
        assert "recent_team" in out.columns
        assert "team" not in out.columns
        assert set(out["recent_team"]) == {"KC", "SF"}


class TestIntegrityCheck:
    def test_raises_on_unrecorded_season(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        with pytest.raises(RuntimeError, match="no entry in"):
            ns.fetch_season_raw(1999)

    def test_raises_on_hash_mismatch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")
        local_path = tmp_path / "stats_player_week_1999.csv"

        with patch("nflverse_source._lookup_asset_id", return_value={"asset_id": 111, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(b"a,b\n1,2\n")):
            ns.register_manifest_entry(1999)

        # Simulate nflverse silently changing the asset's content after
        # the manifest was recorded -- exactly the "future upstream
        # correction" scenario this check exists to catch, regardless
        # of asset-ID pinning (see module docstring's honest limit on
        # that guarantee).
        local_path.write_text("a,b\n1,999\n")

        with pytest.raises(RuntimeError, match="INTEGRITY CHECK FAILED"):
            ns.fetch_season_raw(1999)

    def test_passes_when_hash_matches(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        with patch("nflverse_source._lookup_asset_id", return_value={"asset_id": 111, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(b"a,b\n1,2\n")):
            ns.register_manifest_entry(1999)

        result_path = ns.fetch_season_raw(1999)
        assert result_path == tmp_path / "stats_player_week_1999.csv"

    def test_register_is_the_only_writer(self, tmp_path, monkeypatch):
        """A bare fetch must never create or silently update a
        manifest entry -- register_manifest_entry is the only function
        that may."""
        monkeypatch.setattr(ns, "CACHE_DIR", tmp_path)
        manifest_path = tmp_path / "manifest.json"
        monkeypatch.setattr(ns, "MANIFEST_PATH", manifest_path)

        assert not manifest_path.exists()
        with pytest.raises(RuntimeError):
            ns.fetch_season_raw(1999)
        assert not manifest_path.exists()


class TestEmptyCacheRetrieval:
    """Reproduces the literal fresh-clone scenario: manifest is
    committed (has an entry with a real asset_id + recorded hash), but
    NO local cached CSV exists yet -- data/raw/nflverse/annual/ is
    gitignored, so this is genuinely what a fresh clone starts with."""

    def test_fetch_downloads_when_cache_is_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "CACHE_DIR", tmp_path)
        manifest_path = tmp_path / "manifest.json"
        monkeypatch.setattr(ns, "MANIFEST_PATH", manifest_path)

        content = b"a,b\n1,2\n"
        with patch("nflverse_source._lookup_asset_id", return_value={"asset_id": 222, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(content)):
            ns.register_manifest_entry(1999)

        local_path = tmp_path / "stats_player_week_1999.csv"
        local_path.unlink()  # simulate a fresh clone: manifest committed, cache absent
        assert not local_path.exists()

        with patch("requests.get", return_value=_fake_response(content)) as mock_get:
            result_path = ns.fetch_season_raw(1999)

        assert result_path.exists()
        assert result_path.read_bytes() == content
        # confirms the fetch actually went over the (mocked) network
        # rather than silently succeeding some other way
        mock_get.assert_called_once()

    def test_fetch_from_empty_cache_still_catches_mismatch(self, tmp_path, monkeypatch):
        """Same fresh-clone scenario, but GitHub now serves different
        bytes than what the committed manifest recorded -- must still
        raise, not silently accept whatever it downloaded."""
        monkeypatch.setattr(ns, "CACHE_DIR", tmp_path)
        manifest_path = tmp_path / "manifest.json"
        monkeypatch.setattr(ns, "MANIFEST_PATH", manifest_path)

        with patch("nflverse_source._lookup_asset_id", return_value={"asset_id": 222, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(b"a,b\n1,2\n")):
            ns.register_manifest_entry(1999)

        (tmp_path / "stats_player_week_1999.csv").unlink()

        with patch("requests.get", return_value=_fake_response(b"a,b\n1,999\n")):
            with pytest.raises(RuntimeError, match="INTEGRITY CHECK FAILED"):
                ns.fetch_season_raw(1999)
