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

TestPlayersFetch and TestDepthChartFetch cover the players/depth_charts
extension added for the Stars-by-Value acquisition-cost classifier
(see STARS_BY_VALUE_IMPLEMENTATION_PLAN.md section 3). Same integrity
model as stats_player above, so the same three behaviors matter here
too: unrecorded season/no-players-entry raises, hash mismatch raises,
and an empty local cache with a still-valid manifest entry re-fetches
cleanly. Not re-testing normalize_weekly-equivalent logic here because
there isn't one -- both fetch_players() and fetch_depth_chart() return
the raw parsed CSV as-is (see module docstring).
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


class TestPlayersFetch:
    """players.csv is NOT season-grain (one file, all draft years) --
    these tests protect the single-entry manifest shape (manifest["players"],
    not a seasons dict) and the same fail-loud integrity behaviors as
    stats_player, adapted for that shape."""

    def test_raises_on_unregistered_players_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "PLAYERS_CACHE_PATH", tmp_path / "players.csv")
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        with pytest.raises(RuntimeError, match="no entry in"):
            ns.fetch_players_raw()

    def test_register_then_fetch_passes_when_hash_matches(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "players.csv"
        monkeypatch.setattr(ns, "PLAYERS_CACHE_PATH", cache_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        content = b"gsis_id,position,draft_round\n00-001,QB,1\n"
        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 333, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(content)):
            ns.register_players_manifest_entry()

        result_path = ns.fetch_players_raw()
        assert result_path == cache_path
        assert result_path.read_bytes() == content

    def test_raises_on_hash_mismatch(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "players.csv"
        monkeypatch.setattr(ns, "PLAYERS_CACHE_PATH", cache_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 333, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(b"gsis_id,position\n00-001,QB\n")):
            ns.register_players_manifest_entry()

        cache_path.write_text("gsis_id,position\n00-001,RB\n")  # simulate upstream drift

        with pytest.raises(RuntimeError, match="INTEGRITY CHECK FAILED"):
            ns.fetch_players_raw()

    def test_fetch_downloads_when_cache_is_empty(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "players.csv"
        monkeypatch.setattr(ns, "PLAYERS_CACHE_PATH", cache_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        content = b"gsis_id,position\n00-001,QB\n"
        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 444, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(content)):
            ns.register_players_manifest_entry()

        cache_path.unlink()  # simulate a fresh clone: manifest committed, cache absent

        with patch("requests.get", return_value=_fake_response(content)) as mock_get:
            result_path = ns.fetch_players_raw()

        assert result_path.exists()
        assert result_path.read_bytes() == content
        mock_get.assert_called_once()

    def test_fetch_players_returns_dataframe(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "players.csv"
        monkeypatch.setattr(ns, "PLAYERS_CACHE_PATH", cache_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        content = b"gsis_id,position,draft_round\n00-001,QB,1\n00-002,RB,\n"
        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 555, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(content)):
            ns.register_players_manifest_entry()

        out = ns.fetch_players()
        assert list(out["gsis_id"]) == ["00-001", "00-002"]
        assert list(out["position"]) == ["QB", "RB"]


class TestDepthChartFetch:
    """depth_charts IS season-grain like stats_player, but keyed under
    manifest["depth_charts"]["seasons"] rather than the top-level
    "seasons" key -- these tests protect that the two namespaces don't
    collide and that the same fail-loud integrity behaviors hold."""

    def test_raises_on_unrecorded_season(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "DEPTH_CHARTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        with pytest.raises(RuntimeError, match="no entry in"):
            ns.fetch_depth_chart_raw(1999)

    def test_register_then_fetch_passes_when_hash_matches(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "DEPTH_CHARTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        content = b"season,club_code,week,game_type,depth_team,position,gsis_id\n1999,KC,1,REG,1,QB,00-001\n"
        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 666, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(content)):
            ns.register_depth_chart_manifest_entry(1999)

        result_path = ns.fetch_depth_chart_raw(1999)
        assert result_path == tmp_path / "depth_charts_1999.csv"
        assert result_path.read_bytes() == content

    def test_stats_player_and_depth_chart_season_keys_do_not_collide(self, tmp_path, monkeypatch):
        """The exact scenario the separate manifest namespace exists to
        prevent: registering the same season number for both releases
        must not let one entry clobber the other."""
        monkeypatch.setattr(ns, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "DEPTH_CHARTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        with patch("nflverse_source._lookup_asset_id", return_value={"asset_id": 111, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(b"a,b\n1,2\n")):
            ns.register_manifest_entry(2020)

        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 777, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(b"c,d\n3,4\n")):
            ns.register_depth_chart_manifest_entry(2020)

        stats_path = ns.fetch_season_raw(2020)
        depth_path = ns.fetch_depth_chart_raw(2020)
        assert stats_path.read_bytes() == b"a,b\n1,2\n"
        assert depth_path.read_bytes() == b"c,d\n3,4\n"

    def test_raises_on_hash_mismatch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "DEPTH_CHARTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")
        local_path = tmp_path / "depth_charts_1999.csv"

        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 888, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(b"a,b\n1,2\n")):
            ns.register_depth_chart_manifest_entry(1999)

        local_path.write_text("a,b\n1,999\n")  # simulate upstream drift

        with pytest.raises(RuntimeError, match="INTEGRITY CHECK FAILED"):
            ns.fetch_depth_chart_raw(1999)

    def test_fetch_downloads_when_cache_is_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "DEPTH_CHARTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        content = b"season,club_code,week,game_type,depth_team,position,gsis_id\n1999,KC,1,REG,1,QB,00-001\n"
        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 999, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(content)):
            ns.register_depth_chart_manifest_entry(1999)

        (tmp_path / "depth_charts_1999.csv").unlink()

        with patch("requests.get", return_value=_fake_response(content)) as mock_get:
            result_path = ns.fetch_depth_chart_raw(1999)

        assert result_path.exists()
        assert result_path.read_bytes() == content
        mock_get.assert_called_once()

    def test_fetch_depth_chart_returns_dataframe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ns, "DEPTH_CHARTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr(ns, "MANIFEST_PATH", tmp_path / "manifest.json")

        content = (
            b"season,club_code,week,game_type,depth_team,position,gsis_id\n"
            b"1999,KC,1,REG,1,QB,00-001\n"
            b"1999,KC,1,REG,2,QB,00-002\n"
        )
        with patch("nflverse_source._lookup_asset_id_by_name", return_value={"asset_id": 1010, "upstream_updated_at": "t"}), \
             patch("requests.get", return_value=_fake_response(content)):
            ns.register_depth_chart_manifest_entry(1999)

        out = ns.fetch_depth_chart(1999)
        assert list(out["depth_team"]) == [1, 2]
        assert list(out["gsis_id"]) == ["00-001", "00-002"]
