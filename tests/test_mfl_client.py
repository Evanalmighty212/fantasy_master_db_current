"""
tests/test_mfl_client.py

Covers scripts/mfl_client.py -- the rate-limited, disk-cached fetch
layer for MFL's TYPE=adp and TYPE=players reports, built for the
Stars-by-Value acquisition-cost classifier's MFL corroboration signal.

Each test protects a real, documented design decision from the
module's own docstring, not speculative coverage:
- TestIntegrityModel is the single most important class here: it
  proves the approved integrity contract -- a cache hit returns
  silently with no network call; a missing local file is fetched
  (bootstrap, not a replacement); a cache PRESENT but hash-mismatched
  against the manifest raises loudly and makes NO network call,
  instructing the caller to pass force_refresh=True; force_refresh=True
  always fetches fresh and overwrites regardless of the cache's
  current state. This replaced an earlier design (silent re-fetch on
  mismatch) after explicit review -- a regression here would silently
  reintroduce unexpected network requests into normal (non-refresh)
  runs.
- TestCommittedRegistry protects the compact snapshot registry schema
  (url, retrieved_at, sha256, total_drafts, row_count, sbv_version per
  season/endpoint) and that it's meant to be committed, not disposable
  -- see the module's MANIFEST_NOTE constant.
- TestPeriodAlwaysExplicit protects the PERIOD=AUG15 contamination
  finding -- the unparameterized default MFL report blends in-season
  activity, confirmed directly during the earlier investigation.
- TestSeasonFloor protects SBV_MFL_AVAILABLE_FROM_SEASON=2011 -- MFL
  has zero real drafts before that year at any query period.
- TestRateLimiting/TestRetry protect the same "never hammer MFL's
  servers" discipline documented in the module docstring: serial
  requests, a real minimum delay between calls, bounded retry with
  backoff, and a loud final failure (deliberately NOT the isolated
  research client's {"_error": ...} sentinel -- see module docstring
  for why this module's batch size doesn't need that).
- TestDiscoverValidatedSeasons protects discover_validated_seasons()
  (added 2026-07): the season-availability list must come from the
  manifest + real on-disk hashes at run time, never a hardcoded list a
  caller has to remember to edit -- this is what let
  11_calculate_stars_by_value.py drop its MFL_CACHE_SEASONS constant
  entirely.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

import mfl_client as mc


def _fake_response(json_body: dict, status_ok: bool = True):
    resp = MagicMock()
    resp.json.return_value = json_body
    if status_ok:
        resp.raise_for_status = MagicMock()
    else:
        resp.raise_for_status = MagicMock(side_effect=Exception("HTTP error"))
    return resp


ADP_BODY = {"adp": {"totalDrafts": "100", "player": [{"id": "1", "rank": "1", "draftSelPct": "50"}]}}
ADP_BODY_V2 = {"adp": {"totalDrafts": "150", "player": [{"id": "1", "rank": "1", "draftSelPct": "55"}]}}
PLAYERS_BODY = {"players": {"player": [{"id": "1", "name": "Doe, Jane", "position": "WR", "team": "KC"}]}}


@pytest.fixture(autouse=True)
def _fast_and_isolated(tmp_path, monkeypatch):
    """Every test gets an isolated cache dir/manifest and zero rate-limit
    delay -- these tests exercise the retry/cache LOGIC, not real
    timing, and must not actually sleep."""
    monkeypatch.setattr(mc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(mc, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(mc, "SBV_MFL_MIN_REQUEST_DELAY_SECONDS", 0)
    monkeypatch.setattr(mc, "SBV_MFL_BACKOFF_BASE_SECONDS", 0)
    monkeypatch.setattr(mc, "SBV_MFL_MAX_RETRIES", 3)
    monkeypatch.setattr(mc, "SBV_MFL_REQUEST_TIMEOUT_SECONDS", 5)
    mc._last_request_time[0] = 0.0
    return tmp_path


class TestSeasonFloor:
    def test_fetch_adp_rejects_season_before_2011(self):
        with pytest.raises(ValueError, match="no usable historical ADP data"):
            mc.fetch_adp(2010)

    def test_fetch_adp_accepts_2011(self):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)) as mock_get:
            mc.fetch_adp(2011)
        mock_get.assert_called_once()


class TestPeriodAlwaysExplicit:
    def test_adp_url_includes_period_aug15(self):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)) as mock_get:
            mc.fetch_adp(2020)
        called_url = mock_get.call_args[0][0]
        assert "TYPE=adp" in called_url
        assert "PERIOD=AUG15" in called_url
        assert "JSON=1" in called_url

    def test_players_url_has_no_period_param(self):
        """TYPE=players has no preseason-snapshot concept -- PERIOD
        only applies to TYPE=adp."""
        with patch("requests.get", return_value=_fake_response(PLAYERS_BODY)) as mock_get:
            mc.fetch_players(2020)
        called_url = mock_get.call_args[0][0]
        assert "TYPE=players" in called_url
        assert "PERIOD" not in called_url


class TestIntegrityModel:
    """The approved integrity contract -- see class docstring at
    module top. This is the highest-priority coverage in this file."""

    def test_valid_cache_returns_with_no_network_call(self):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)) as mock_get:
            mc.fetch_adp(2020)  # first fetch, writes cache
            data = mc.fetch_adp(2020)  # second call: must be a pure cache hit
        assert data == ADP_BODY
        mock_get.assert_called_once()

    def test_mismatched_cache_raises_and_makes_no_network_call(self, tmp_path):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)

        # Simulate local corruption or a hand-edit -- NOT an upstream change.
        (tmp_path / "adp_2020_period_aug15.json").write_text('{"tampered": true}')

        with patch("requests.get") as mock_get:
            with pytest.raises(RuntimeError, match="LOCAL SNAPSHOT MISMATCH"):
                mc.fetch_adp(2020)
        mock_get.assert_not_called()

    def test_mismatch_error_names_force_refresh_as_the_fix(self, tmp_path):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)
        (tmp_path / "adp_2020_period_aug15.json").write_text('{"tampered": true}')

        with pytest.raises(RuntimeError, match=r"force_refresh=True"):
            mc.fetch_adp(2020)

    def test_mismatched_cache_with_force_refresh_fetches_and_replaces(self, tmp_path):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)
        (tmp_path / "adp_2020_period_aug15.json").write_text('{"tampered": true}')

        with patch("requests.get", return_value=_fake_response(ADP_BODY_V2)) as mock_get:
            data = mc.fetch_adp(2020, force_refresh=True)

        assert data == ADP_BODY_V2
        mock_get.assert_called_once()
        assert json.loads((tmp_path / "adp_2020_period_aug15.json").read_text()) == ADP_BODY_V2

    def test_missing_cache_file_is_fetched_not_treated_as_mismatch(self, tmp_path):
        """No local file at all (fresh clone, or a cleared cache) is a
        bootstrap, not a replacement -- must fetch without needing
        force_refresh and without raising."""
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)

        (tmp_path / "adp_2020_period_aug15.json").unlink()

        with patch("requests.get", return_value=_fake_response(ADP_BODY)) as mock_get:
            data = mc.fetch_adp(2020)  # no force_refresh -- must not raise
        assert data == ADP_BODY
        mock_get.assert_called_once()

    def test_force_refresh_always_fetches_even_with_a_valid_cache(self):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)) as mock_get:
            mc.fetch_adp(2020)
            mc.fetch_adp(2020, force_refresh=True)
        assert mock_get.call_count == 2

    def test_players_and_adp_mismatches_are_independent(self, tmp_path):
        """A mismatch on one report/season must not affect the other."""
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)
        with patch("requests.get", return_value=_fake_response(PLAYERS_BODY)):
            mc.fetch_players(2020)

        (tmp_path / "adp_2020_period_aug15.json").write_text('{"tampered": true}')

        with pytest.raises(RuntimeError, match="LOCAL SNAPSHOT MISMATCH"):
            mc.fetch_adp(2020)

        with patch("requests.get") as mock_get:
            data = mc.fetch_players(2020)  # unaffected, still a valid cache hit
        assert data == PLAYERS_BODY
        mock_get.assert_not_called()


class TestCommittedRegistry:
    """The manifest is a compact, COMMITTED snapshot registry (see
    module docstring), not disposable bookkeeping -- these tests
    protect its exact schema and the explicit reproducibility caveat."""

    def test_entry_schema_has_all_required_fields(self, tmp_path):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        entry = manifest["adp"]["seasons"]["2020"]
        assert set(entry) == {"url", "retrieved_at", "sha256", "total_drafts", "row_count", "sbv_version"}
        assert entry["total_drafts"] == "100"
        assert entry["row_count"] == 1
        assert entry["sbv_version"] == mc.SBV_VERSION
        assert "TYPE=adp" in entry["url"] and "PERIOD=AUG15" in entry["url"]

    def test_players_entry_has_null_total_drafts(self, tmp_path):
        """total_drafts is adp-only -- "where applicable" per the
        approved schema."""
        with patch("requests.get", return_value=_fake_response(PLAYERS_BODY)):
            mc.fetch_players(2020)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        entry = manifest["players"]["seasons"]["2020"]
        assert entry["total_drafts"] is None
        assert entry["row_count"] == 1


class TestDiscoverValidatedSeasons:
    """Covers mfl_client.discover_validated_seasons() -- added 2026-07
    to replace 11_calculate_stars_by_value.py's hardcoded
    MFL_CACHE_SEASONS tuple, which itself had to be manually widened
    each time a new season's data was backfilled (first (2015, 2023),
    then a manually-edited 2011-2024). This function derives the
    available-season list from the manifest + real on-disk hashes at
    run time, so no caller needs a per-season code edit ever again."""

    def _fetch_season(self, season, adp_body=None, players_body=None):
        """Bootstraps a real, validated season via the normal fetch
        path (mocked network) -- writes both the local file and its
        manifest entry exactly as a real run would."""
        with patch("requests.get", return_value=_fake_response(adp_body or ADP_BODY)):
            mc.fetch_adp(season)
        with patch("requests.get", return_value=_fake_response(players_body or PLAYERS_BODY)):
            mc.fetch_players(season)

    def test_no_manifest_returns_empty(self):
        assert mc.discover_validated_seasons() == []

    def test_newly_fetched_season_is_discovered_automatically(self):
        """No SEASONS list anywhere -- fetching a season is sufficient
        for discover_validated_seasons() to report it, with no source
        change."""
        assert mc.discover_validated_seasons() == []
        self._fetch_season(2013)
        assert mc.discover_validated_seasons() == [2013]

    def test_a_second_newly_fetched_season_is_also_discovered_automatically(self):
        self._fetch_season(2013)
        self._fetch_season(2019)
        assert mc.discover_validated_seasons() == [2013, 2019]

    def test_season_missing_players_report_is_excluded(self):
        """Only adp fetched -- classify_row() needs both reports, so a
        season with just one is not usable."""
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2014)
        assert mc.discover_validated_seasons() == []

    def test_season_missing_adp_report_is_excluded(self):
        with patch("requests.get", return_value=_fake_response(PLAYERS_BODY)):
            mc.fetch_players(2014)
        assert mc.discover_validated_seasons() == []

    def test_season_with_manifest_entry_but_missing_local_file_is_excluded(self):
        """Manifest says it was fetched, but the file itself isn't on
        disk (e.g. a fresh clone with the manifest committed but
        data/raw/mfl/ gitignored and not repopulated) -- must not be
        reported as available."""
        self._fetch_season(2016)
        (mc.CACHE_DIR / "adp_2016_period_aug15.json").unlink()
        assert mc.discover_validated_seasons() == []

    def test_season_with_hash_mismatched_file_is_excluded(self):
        """The file on disk doesn't match what the manifest recorded
        -- same real-world case TestIntegrityModel's mismatch test
        covers for fetch_adp() itself, but here it must just be
        silently excluded from discovery, not raised (discovery is
        read-only; a caller that needs this season fetched calls
        fetch_adp() directly and gets the loud error)."""
        self._fetch_season(2017)
        (mc.CACHE_DIR / "adp_2017_period_aug15.json").write_text('{"tampered": true}')
        assert mc.discover_validated_seasons() == []

    def test_valid_season_alongside_mismatched_season_only_returns_the_valid_one(self):
        self._fetch_season(2016)
        self._fetch_season(2017)
        (mc.CACHE_DIR / "adp_2017_period_aug15.json").write_text('{"tampered": true}')
        assert mc.discover_validated_seasons() == [2016]

    def test_2025_is_discovered_when_its_valid_snapshot_is_present(self):
        """The real, current-season case this whole change was for:
        2025 is treated like any other season -- no special-casing, no
        code edit required once a validated snapshot exists for it."""
        self._fetch_season(2025)
        assert mc.discover_validated_seasons() == [2025]

    def test_returns_sorted_seasons_regardless_of_fetch_order(self):
        self._fetch_season(2024)
        self._fetch_season(2012)
        self._fetch_season(2018)
        assert mc.discover_validated_seasons() == [2012, 2018, 2024]

    def test_manifest_includes_reproducibility_caveat_note(self, tmp_path):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert "cannot" in manifest["note"] and "reproduc" in manifest["note"].lower()

    def test_adp_and_players_seasons_are_keyed_separately(self, tmp_path):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)
        with patch("requests.get", return_value=_fake_response(PLAYERS_BODY)):
            mc.fetch_players(2020)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert "2020" in manifest["adp"]["seasons"]
        assert "2020" in manifest["players"]["seasons"]
        assert manifest["adp"]["seasons"]["2020"] != manifest["players"]["seasons"]["2020"]

    def test_drift_is_printed_when_a_snapshot_is_replaced(self, capsys):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)
        with patch("requests.get", return_value=_fake_response(ADP_BODY_V2)):
            mc.fetch_adp(2020, force_refresh=True)

        out = capsys.readouterr().out
        assert "snapshot replaced" in out
        assert "100" in out and "150" in out

    def test_no_print_when_forced_refetch_is_identical(self, capsys):
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020)
        with patch("requests.get", return_value=_fake_response(ADP_BODY)):
            mc.fetch_adp(2020, force_refresh=True)

        assert capsys.readouterr().out == ""


class TestRetry:
    def test_retries_then_succeeds(self):
        fail_resp = _fake_response({}, status_ok=False)
        ok_resp = _fake_response(ADP_BODY)
        with patch("requests.get", side_effect=[fail_resp, ok_resp]) as mock_get, \
             patch("time.sleep"):
            data = mc.fetch_adp(2020)
        assert data == ADP_BODY
        assert mock_get.call_count == 2

    def test_raises_after_exhausting_retries(self):
        fail_resp = _fake_response({}, status_ok=False)
        with patch("requests.get", return_value=fail_resp) as mock_get, \
             patch("time.sleep"):
            with pytest.raises(RuntimeError, match="Failed to fetch"):
                mc.fetch_adp(2020)
        assert mock_get.call_count == mc.SBV_MFL_MAX_RETRIES

    def test_failed_attempt_never_writes_cache_or_manifest(self, tmp_path):
        fail_resp = _fake_response({}, status_ok=False)
        with patch("requests.get", return_value=fail_resp), patch("time.sleep"):
            with pytest.raises(RuntimeError):
                mc.fetch_adp(2020)
        assert not (tmp_path / "adp_2020_period_aug15.json").exists()
        assert not (tmp_path / "manifest.json").exists()


class TestRateLimiting:
    def test_throttle_sleeps_when_called_too_soon(self, monkeypatch):
        monkeypatch.setattr(mc, "SBV_MFL_MIN_REQUEST_DELAY_SECONDS", 10)
        mc._last_request_time[0] = time.monotonic()

        with patch("time.sleep") as mock_sleep:
            mc._throttle()

        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] <= 10

    def test_no_sleep_when_enough_time_has_passed(self, monkeypatch):
        monkeypatch.setattr(mc, "SBV_MFL_MIN_REQUEST_DELAY_SECONDS", 0.001)
        mc._last_request_time[0] = time.monotonic() - 10

        with patch("time.sleep") as mock_sleep:
            mc._throttle()

        mock_sleep.assert_not_called()

    def test_requests_are_strictly_serial_within_one_fetch(self):
        """Not literal thread-safety proof, just confirms the retry
        loop never launches concurrent requests -- one call to
        requests.get per attempt, in sequence."""
        with patch("requests.get", return_value=_fake_response(ADP_BODY)) as mock_get:
            mc.fetch_adp(2020)
        assert mock_get.call_count == 1
