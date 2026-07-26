"""
tests/test_mfl_historical_backfill.py

Covers scripts/mfl_historical_backfill.py -- the CI-driven driver for
the 2011-2024 historical MFL backfill (see docs/ADP_SOURCE_MATRIX.md's
Blocker A entry). ALL tests here mock mfl_client.fetch_adp/fetch_players
-- no real network calls in normal test execution. This module is
designed to run on GitHub Actions (see
.github/workflows/fetch_mfl_historical.yml), not locally; these tests
verify the driver's OWN logic (per-season failure isolation, summary
shape, never forcing a refresh), not mfl_client.py's fetch behavior
itself (already covered by that module's own test suite).

TestParseSeasonsArg covers parse_seasons_arg() (added 2026-07): the
--seasons CLI argument that lets a one-off season (e.g. 2025) reuse
this same workflow instead of a second, near-duplicate one. Strict
validation is the point -- a malformed token, reversed range, or
unsupported season must raise with a clear message, never silently
drop or clamp anything.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import mfl_historical_backfill as backfill


def _adp_response(n_players=5, total_drafts=100):
    return {"adp": {"totalDrafts": str(total_drafts), "player": [{"id": str(i)} for i in range(n_players)]}}


def _players_response(n_players=5):
    return {"players": {"player": [{"id": str(i), "name": f"Test, Player{i}"} for i in range(n_players)]}}


class TestRunBackfillHappyPath:
    def test_all_seasons_succeed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backfill, "SUMMARY_PATH", tmp_path / "summary.csv")
        with patch("mfl_client.fetch_adp", return_value=_adp_response()) as mock_adp, \
             patch("mfl_client.fetch_players", return_value=_players_response()) as mock_players:
            summary = backfill.run_backfill(seasons=[2011, 2012])

        assert list(summary["season"]) == [2011, 2012]
        assert (summary["adp_status"] == "ok").all()
        assert (summary["players_status"] == "ok").all()
        assert mock_adp.call_count == 2
        assert mock_players.call_count == 2

    def test_row_counts_reflect_real_response_shape(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backfill, "SUMMARY_PATH", tmp_path / "summary.csv")
        with patch("mfl_client.fetch_adp", return_value=_adp_response(n_players=7)), \
             patch("mfl_client.fetch_players", return_value=_players_response(n_players=3)):
            summary = backfill.run_backfill(seasons=[2015])

        assert summary.iloc[0]["adp_row_count"] == 7
        assert summary.iloc[0]["players_row_count"] == 3

    def test_summary_written_to_disk(self, tmp_path, monkeypatch):
        summary_path = tmp_path / "summary.csv"
        monkeypatch.setattr(backfill, "SUMMARY_PATH", summary_path)
        with patch("mfl_client.fetch_adp", return_value=_adp_response()), \
             patch("mfl_client.fetch_players", return_value=_players_response()):
            backfill.run_backfill(seasons=[2011])

        assert summary_path.exists()
        assert len(pd.read_csv(summary_path)) == 1


class TestPerSeasonFailureIsolation:
    def test_one_season_failing_does_not_abort_the_run(self, tmp_path, monkeypatch):
        """A real integrity-mismatch or network error for ONE season
        must not stop the other seasons from being attempted --
        resumability and partial-progress are the whole point."""
        monkeypatch.setattr(backfill, "SUMMARY_PATH", tmp_path / "summary.csv")

        def flaky_adp(season):
            if season == 2013:
                raise RuntimeError("INTEGRITY CHECK FAILED for adp_2013_period_aug15.json")
            return _adp_response()

        with patch("mfl_client.fetch_adp", side_effect=flaky_adp), \
             patch("mfl_client.fetch_players", return_value=_players_response()):
            summary = backfill.run_backfill(seasons=[2011, 2013, 2014])

        assert list(summary["season"]) == [2011, 2013, 2014]
        assert summary[summary["season"] == 2011].iloc[0]["adp_status"] == "ok"
        assert summary[summary["season"] == 2013].iloc[0]["adp_status"] == "failed"
        assert "INTEGRITY CHECK FAILED" in summary[summary["season"] == 2013].iloc[0]["adp_error"]
        assert summary[summary["season"] == 2014].iloc[0]["adp_status"] == "ok"

    def test_adp_failure_does_not_prevent_players_fetch_for_same_season(self, tmp_path, monkeypatch):
        """The two fetches for one season are independent -- adp
        failing must not skip the players fetch."""
        monkeypatch.setattr(backfill, "SUMMARY_PATH", tmp_path / "summary.csv")
        with patch("mfl_client.fetch_adp", side_effect=RuntimeError("network error")), \
             patch("mfl_client.fetch_players", return_value=_players_response()) as mock_players:
            summary = backfill.run_backfill(seasons=[2011])

        assert summary.iloc[0]["adp_status"] == "failed"
        assert summary.iloc[0]["players_status"] == "ok"
        mock_players.assert_called_once_with(2011)


class TestNeverForcesRefresh:
    """mfl_client.py's integrity model requires force_refresh=True to
    be an explicit, deliberate act -- this driver must never pass it
    implicitly, which would silently accept a mismatched/replaced
    snapshot without a human decision."""

    def test_fetch_adp_called_without_force_refresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backfill, "SUMMARY_PATH", tmp_path / "summary.csv")
        with patch("mfl_client.fetch_adp", return_value=_adp_response()) as mock_adp, \
             patch("mfl_client.fetch_players", return_value=_players_response()):
            backfill.run_backfill(seasons=[2011])
        mock_adp.assert_called_once_with(2011)  # positional only -- no force_refresh kwarg

    def test_fetch_players_called_without_force_refresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backfill, "SUMMARY_PATH", tmp_path / "summary.csv")
        with patch("mfl_client.fetch_adp", return_value=_adp_response()), \
             patch("mfl_client.fetch_players", return_value=_players_response()) as mock_players:
            backfill.run_backfill(seasons=[2011])
        mock_players.assert_called_once_with(2011)


class TestSeasonRange:
    def test_default_seasons_are_2011_through_2024(self):
        assert backfill.SEASONS == list(range(2011, 2025))
        assert backfill.SEASONS[0] == 2011
        assert backfill.SEASONS[-1] == 2024
        assert len(backfill.SEASONS) == 14


class TestParseSeasonsArg:
    """Covers parse_seasons_arg() -- added 2026-07 so a one-off season
    (e.g. 2025) can be fetched via this same tested workflow/script
    instead of a second, near-duplicate one. See
    .github/workflows/fetch_mfl_historical.yml's new `seasons` input."""

    def test_empty_string_returns_the_default_2011_2024_range(self):
        assert backfill.parse_seasons_arg("") == backfill.SEASONS

    def test_blank_whitespace_returns_the_default_range(self):
        assert backfill.parse_seasons_arg("   ") == backfill.SEASONS

    def test_custom_default_is_honored_when_spec_is_empty(self):
        assert backfill.parse_seasons_arg("", default=[2020]) == [2020]

    def test_single_season(self):
        assert backfill.parse_seasons_arg("2025") == [2025]

    def test_comma_separated_seasons(self):
        assert backfill.parse_seasons_arg("2013,2017,2021") == [2013, 2017, 2021]

    def test_comma_separated_seasons_out_of_order_still_sorted(self):
        assert backfill.parse_seasons_arg("2021,2013,2017") == [2013, 2017, 2021]

    def test_range(self):
        assert backfill.parse_seasons_arg("2011-2014") == [2011, 2012, 2013, 2014]

    def test_mixed_range_and_single_season(self):
        assert backfill.parse_seasons_arg("2011-2014,2025") == [2011, 2012, 2013, 2014, 2025]

    def test_overlapping_range_and_single_season_deduplicated(self):
        """Duplicates across tokens are silently collapsed -- the
        contract is a unique, sorted OUTPUT, not rejecting duplicate
        input."""
        assert backfill.parse_seasons_arg("2011-2014,2013,2014") == [2011, 2012, 2013, 2014]

    def test_tolerates_whitespace_around_tokens(self):
        assert backfill.parse_seasons_arg(" 2013 , 2017 ") == [2013, 2017]

    def test_tolerates_trailing_comma(self):
        assert backfill.parse_seasons_arg("2013,2017,") == [2013, 2017]

    def test_invalid_syntax_raises_with_clear_message(self):
        with pytest.raises(ValueError, match=r"not a valid season"):
            backfill.parse_seasons_arg("abcd")

    def test_triple_hyphen_token_raises(self):
        with pytest.raises(ValueError, match=r"not a valid season"):
            backfill.parse_seasons_arg("2015-2016-2017")

    def test_malformed_year_length_raises(self):
        with pytest.raises(ValueError, match=r"not a valid season"):
            backfill.parse_seasons_arg("20155")

    def test_reversed_range_raises_with_clear_message(self):
        with pytest.raises(ValueError, match=r"reversed"):
            backfill.parse_seasons_arg("2020-2015")

    def test_unsupported_season_below_floor_raises(self):
        """MFL has no usable data before SBV_MFL_AVAILABLE_FROM_SEASON
        -- same floor mfl_client.fetch_adp() itself enforces."""
        with pytest.raises(ValueError, match=r"unsupported season 2005"):
            backfill.parse_seasons_arg("2005")

    def test_unsupported_season_above_ceiling_raises(self):
        with pytest.raises(ValueError, match=r"unsupported season 2099"):
            backfill.parse_seasons_arg("2099")

    def test_range_touching_an_unsupported_season_raises(self):
        with pytest.raises(ValueError, match=r"unsupported season 2010"):
            backfill.parse_seasons_arg("2010-2012")


class TestSeasonsArgNeverForcesRefresh:
    """The --seasons path must carry the same 'never force_refresh'
    guarantee as the default path -- TestNeverForcesRefresh above
    covers run_backfill() itself; this confirms a parsed --seasons
    list feeds into that same unchanged call."""

    def test_run_backfill_with_parsed_seasons_never_forces_refresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backfill, "SUMMARY_PATH", tmp_path / "summary.csv")
        seasons = backfill.parse_seasons_arg("2025")
        with patch("mfl_client.fetch_adp", return_value=_adp_response()) as mock_adp, \
             patch("mfl_client.fetch_players", return_value=_players_response()) as mock_players:
            backfill.run_backfill(seasons=seasons)
        mock_adp.assert_called_once_with(2025)
        mock_players.assert_called_once_with(2025)


class TestDoesNotTouchMasterDb:
    def test_module_does_not_import_master_dataset_builder(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(backfill))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "04_build_master_dataset" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                assert "04_build_master_dataset" not in (node.module or "")
