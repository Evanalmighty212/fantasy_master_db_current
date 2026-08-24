"""Synthetic-only safeguards for the --live-2026-spine opt-in path in
scripts/build_dataset2_canonical_predictor_table.py.

No real players.csv/games.csv content and no real network fetch is
touched anywhere in this file -- every manifest entry, schedule row,
and roster snapshot below is synthetic, and nflverse_source's real
fetch functions are monkeypatched out entirely. See
tests/test_dataset2_future_season_spine.py and
tests/test_dataset2_canonical_predictor_table.py::TestFutureSeasonRosterSpine
for the already-committed, already-tested core this file only wires
into a CLI entry point.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import pytest

import nflverse_source
from scripts import build_dataset2_canonical_predictor_table as entrypoint
from lib.dataset2.canonical_predictor_table import build_canonical_predictor_table
from lib.dataset2.future_season_spine import RosterSpineResult, build_future_season_roster_spine
from test_dataset2_canonical_predictor_table import (
    AAA_2015_WEEKS,
    _depth_chart,
    _players,
    _population,
    _rb_weekly_rows,
    _roster_spine,
    _schedule as _lib_schedule,
    _snap_counts,
    _weekly,
)

PREDICTION_SEASON = 2026


_SCHEDULE_COLUMNS = ("season", "game_type", "week", "gameday", "home_team", "away_team")


def _schedule(rows):
    """rows: (season, week, gameday, home_team, away_team) -- REG game_type."""
    if not rows:
        return pd.DataFrame(columns=_SCHEDULE_COLUMNS)
    return pd.DataFrame([
        {"season": s, "game_type": "REG", "week": w, "gameday": g, "home_team": h, "away_team": a}
        for s, w, g, h, a in rows
    ])


def _manifest(players=True, schedules=True, retrieved_at="2026-08-01T00:00:00+00:00"):
    manifest = {"schema_version": "x", "seasons": {}}
    if players:
        manifest["players"] = {"retrieved_at": retrieved_at, "sha256": "abc", "asset_id": 1}
    if schedules:
        manifest["schedules"] = {"retrieved_at": "2026-01-01T00:00:00+00:00", "sha256": "def", "asset_id": 2}
    return manifest


def _forbidden(name):
    def _raise(*args, **kwargs):
        raise AssertionError(f"{name} must not be called")
    return _raise


class TestMissingOrInvalidProvenanceFailsBeforeBuild:
    def test_missing_players_manifest_entry_raises_before_build(self, monkeypatch):
        monkeypatch.setattr(nflverse_source, "_load_manifest", lambda: _manifest(players=False))
        monkeypatch.setattr(entrypoint, "build_canonical_predictor_table", _forbidden("build_canonical_predictor_table"))
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="players.csv has no entry"):
            entrypoint.load_live_2026_spine_inputs(PREDICTION_SEASON)

    def test_missing_schedules_manifest_entry_raises_before_build(self, monkeypatch):
        monkeypatch.setattr(nflverse_source, "_load_manifest", lambda: _manifest(schedules=False))
        monkeypatch.setattr(entrypoint, "build_canonical_predictor_table", _forbidden("build_canonical_predictor_table"))
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match=r"schedules \(games\.csv\) has no entry"):
            entrypoint.load_live_2026_spine_inputs(PREDICTION_SEASON)

    def test_checksum_invalid_players_raises_before_build(self, monkeypatch):
        monkeypatch.setattr(nflverse_source, "_load_manifest", lambda: _manifest())

        def raise_integrity(*a, **k):
            raise RuntimeError("INTEGRITY CHECK FAILED for players.csv: recorded abc..., got def...")
        monkeypatch.setattr(nflverse_source, "fetch_players_raw", raise_integrity)
        monkeypatch.setattr(entrypoint, "build_canonical_predictor_table", _forbidden("build_canonical_predictor_table"))
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="players.csv provenance verification failed"):
            entrypoint.load_live_2026_spine_inputs(PREDICTION_SEASON)

    def test_checksum_invalid_schedules_raises_before_build(self, monkeypatch):
        monkeypatch.setattr(nflverse_source, "_load_manifest", lambda: _manifest())
        monkeypatch.setattr(nflverse_source, "fetch_players_raw", lambda: "irrelevant_path.csv")

        def raise_integrity(*a, **k):
            raise RuntimeError("INTEGRITY CHECK FAILED for games.csv: recorded abc..., got def...")
        monkeypatch.setattr(nflverse_source, "fetch_schedules_raw", raise_integrity)
        monkeypatch.setattr(entrypoint, "build_canonical_predictor_table", _forbidden("build_canonical_predictor_table"))
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="schedules provenance verification failed"):
            entrypoint.load_live_2026_spine_inputs(PREDICTION_SEASON)

    def test_resolve_live_2026_spine_propagates_provenance_failure_without_building(self, monkeypatch):
        # Through the actual seam main() calls -- proves the ordering
        # holds end-to-end, not just inside load_live_2026_spine_inputs.
        monkeypatch.setattr(nflverse_source, "_load_manifest", lambda: _manifest(players=False))
        monkeypatch.setattr(entrypoint, "build_canonical_predictor_table", _forbidden("build_canonical_predictor_table"))
        master_population = pd.DataFrame({"season": [2025]})
        with pytest.raises(entrypoint.LiveSpineProvenanceError):
            entrypoint.resolve_live_2026_spine(True, master_population)


class TestMissingLocalCacheFailsBeforeDownload:
    """Protects the operational correction: --live-2026-spine must never
    attempt a network download in a local run. The guard must be our own
    explicit check, not reliance on this sandbox's lack of outbound
    internet -- so these tests prove fetch_players_raw()/
    fetch_schedules_raw() are never even CALLED when the local cache file
    is absent, not merely that they'd fail if called."""

    def test_missing_players_cache_raises_before_any_fetch_call(self, tmp_path, monkeypatch):
        monkeypatch.setattr(nflverse_source, "_load_manifest", lambda: _manifest())
        monkeypatch.setattr(nflverse_source, "PLAYERS_CACHE_PATH", tmp_path / "no_such_players.csv")
        monkeypatch.setattr(nflverse_source, "fetch_players_raw", _forbidden("fetch_players_raw"))
        monkeypatch.setattr(nflverse_source, "fetch_schedules_raw", _forbidden("fetch_schedules_raw"))
        monkeypatch.setattr(entrypoint, "build_canonical_predictor_table", _forbidden("build_canonical_predictor_table"))
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="players.csv is not present locally"):
            entrypoint.load_live_2026_spine_inputs(PREDICTION_SEASON)

    def test_missing_schedules_cache_raises_before_any_fetch_call(self, tmp_path, monkeypatch):
        monkeypatch.setattr(nflverse_source, "_load_manifest", lambda: _manifest())
        monkeypatch.setattr(nflverse_source, "PLAYERS_CACHE_PATH", tmp_path / "players.csv")
        (tmp_path / "players.csv").write_text("gsis_id\n")  # players cache present
        monkeypatch.setattr(nflverse_source, "SCHEDULES_CACHE_PATH", tmp_path / "no_such_games.csv")
        monkeypatch.setattr(nflverse_source, "fetch_players_raw", _forbidden("fetch_players_raw"))
        monkeypatch.setattr(nflverse_source, "fetch_schedules_raw", _forbidden("fetch_schedules_raw"))
        monkeypatch.setattr(entrypoint, "build_canonical_predictor_table", _forbidden("build_canonical_predictor_table"))
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="schedules \\(games\\.csv\\) is not present locally"):
            entrypoint.load_live_2026_spine_inputs(PREDICTION_SEASON)

    def test_missing_cache_produces_no_output_write(self, tmp_path, monkeypatch):
        # End-to-end through resolve_live_2026_spine (the seam main() uses):
        # a missing local cache must halt before write_live_spine_outputs
        # -- and before build_canonical_predictor_table -- ever runs.
        monkeypatch.setattr(nflverse_source, "_load_manifest", lambda: _manifest())
        monkeypatch.setattr(nflverse_source, "PLAYERS_CACHE_PATH", tmp_path / "no_such_players.csv")
        monkeypatch.setattr(nflverse_source, "fetch_players_raw", _forbidden("fetch_players_raw"))
        monkeypatch.setattr(entrypoint, "build_canonical_predictor_table", _forbidden("build_canonical_predictor_table"))
        monkeypatch.setattr(entrypoint, "write_live_spine_outputs", _forbidden("write_live_spine_outputs"))
        master_population = pd.DataFrame({"season": [2025]})
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="players.csv is not present locally"):
            entrypoint.resolve_live_2026_spine(True, master_population)


class TestCutoffTimezoneHandling:
    def test_naive_gameday_normalizes_to_utc(self):
        schedule = _schedule([(2026, 1, "2026-09-04", "AAA", "BBB")])
        result = entrypoint._earliest_week1_kickoff_utc_date(schedule, 2026)
        assert result == pd.Timestamp("2026-09-04", tz="UTC")
        assert result.tzinfo is not None

    def test_earliest_across_multiple_teams_is_selected(self):
        schedule = _schedule([
            (2026, 1, "2026-09-05", "AAA", "BBB"),
            (2026, 1, "2026-09-04", "CCC", "DDD"),
        ])
        result = entrypoint._earliest_week1_kickoff_utc_date(schedule, 2026)
        assert result == pd.Timestamp("2026-09-04", tz="UTC")

    def test_tz_aware_retrieved_at_strictly_before_cutoff_is_accepted(self):
        cutoff = pd.Timestamp("2026-09-04", tz="UTC")
        entrypoint._verify_snapshot_before_cutoff("2026-08-01T00:00:00+00:00", cutoff)  # must not raise

    def test_same_calendar_date_is_rejected_not_accepted(self):
        # "Strictly before," not "on or before" -- a snapshot taken the
        # same UTC calendar day as kickoff is refused.
        cutoff = pd.Timestamp("2026-09-04", tz="UTC")
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="not strictly before"):
            entrypoint._verify_snapshot_before_cutoff("2026-09-04T00:00:00+00:00", cutoff)

    def test_date_after_cutoff_is_rejected(self):
        cutoff = pd.Timestamp("2026-09-04", tz="UTC")
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="not strictly before"):
            entrypoint._verify_snapshot_before_cutoff("2026-09-05T12:00:00+00:00", cutoff)

    def test_non_utc_timezone_is_correctly_converted_before_comparing(self):
        # 2026-09-03 21:00 US/Eastern (UTC-4 in September) == 2026-09-04
        # 01:00 UTC -- a naive "compare the date string" would wrongly
        # accept this as strictly before a 2026-09-04 UTC cutoff.
        cutoff = pd.Timestamp("2026-09-04", tz="UTC")
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="not strictly before"):
            entrypoint._verify_snapshot_before_cutoff("2026-09-03T21:00:00-04:00", cutoff)

    def test_timezone_naive_retrieved_at_is_refused_not_assumed_utc(self):
        cutoff = pd.Timestamp("2026-09-04", tz="UTC")
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="no timezone"):
            entrypoint._verify_snapshot_before_cutoff("2026-08-01T00:00:00", cutoff)

    def test_no_week1_games_in_schedule_raises(self):
        schedule = _schedule([])
        with pytest.raises(entrypoint.LiveSpineProvenanceError, match="No real Week 1"):
            entrypoint._earliest_week1_kickoff_utc_date(schedule, 2026)


class TestDefaultBehaviorUnchanged:
    def test_resolve_live_2026_spine_returns_none_without_touching_machinery(self, monkeypatch):
        monkeypatch.setattr(entrypoint, "load_live_2026_spine_inputs", _forbidden("load_live_2026_spine_inputs"))
        monkeypatch.setattr(entrypoint, "build_governed_live_2026_spine", _forbidden("build_governed_live_2026_spine"))
        master_population = pd.DataFrame({"season": [2025]})
        result = entrypoint.resolve_live_2026_spine(False, master_population)
        assert result is None

    def test_default_argparse_flag_is_false(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--live-2026-spine", action="store_true")
        args = parser.parse_args([])
        assert args.live_2026_spine is False


class TestFamily9SupersetFailureHaltsLivePath:
    def test_incomplete_spine_raises_before_any_output_is_produced(self, tmp_path, monkeypatch):
        # Mirrors tests/test_dataset2_canonical_predictor_table.py's own
        # TestFutureSeasonRosterSpine::test_spine_missing_a_real_family9_future_row_raises,
        # exercised through this script's own write_live_spine_outputs()
        # so the ordering (spine resolved, THEN passed to the real
        # build, which itself halts before any output file is written)
        # is proven end-to-end, not just inside the library.
        pop = _population((2025, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1998-01-01", 2020, 70, 210, 2020, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2025, "P1", AAA_2015_WEEKS, "AAA"))
        # P1 has real 2025 weekly data, so family #9 will independently
        # derive a real prediction_season=2026 row for them -- a spine
        # that omits P1 fails the superset check.
        incomplete_spine = _roster_spine(2026, [("P2", "WR", "SEA", "ACT")])

        with pytest.raises(ValueError, match="missing"):
            build_canonical_predictor_table(
                pop, players, weekly, weekly, _snap_counts([]), _depth_chart([]), _lib_schedule([]),
                window_ns=(4,), future_season_roster_spine=incomplete_spine,
            )

        monkeypatch.setattr(entrypoint, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(entrypoint, "LIVE_SPINE_INCLUDED_PATH", tmp_path / "included.csv")
        monkeypatch.setattr(entrypoint, "LIVE_SPINE_EXCLUDED_PATH", tmp_path / "excluded.csv")
        monkeypatch.setattr(entrypoint, "LIVE_SPINE_SIDECAR_PATH", tmp_path / "sidecar.csv")
        monkeypatch.setattr(entrypoint, "LIVE_SPINE_HASH_MANIFEST_PATH", tmp_path / "spine.sha256")
        # write_live_spine_outputs is only ever reached AFTER a
        # successful build_canonical_predictor_table call in main() --
        # since that call raised above, no output file should exist.
        assert not (tmp_path / "included.csv").exists()


class TestSidecarAndExclusionLedgerNeverEnterCanonicalTable:
    def test_sidecar_and_excluded_ledger_are_written_as_separate_files_not_merged(self, tmp_path, monkeypatch):
        pop = _population((2025, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1998-01-01", 2020, 70, 210, 2020, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2025, "P1", AAA_2015_WEEKS, "AAA"))
        spine = _roster_spine(2026, [("P1", "RB", "AAA", "SUS")])
        out, registry, _ = build_canonical_predictor_table(
            pop, players, weekly, weekly, _snap_counts([]), _depth_chart([]), _lib_schedule([]),
            window_ns=(4,), future_season_roster_spine=spine,
        )
        assert "future_season_roster_status" not in out.columns
        assert "future_season_roster_status" not in set(registry["canonical_column"])

        included_path = tmp_path / "included.csv"
        excluded_path = tmp_path / "excluded.csv"
        sidecar_path = tmp_path / "sidecar.csv"
        hash_path = tmp_path / "spine.sha256"
        monkeypatch.setattr(entrypoint, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(entrypoint, "LIVE_SPINE_INCLUDED_PATH", included_path)
        monkeypatch.setattr(entrypoint, "LIVE_SPINE_EXCLUDED_PATH", excluded_path)
        monkeypatch.setattr(entrypoint, "LIVE_SPINE_SIDECAR_PATH", sidecar_path)
        monkeypatch.setattr(entrypoint, "LIVE_SPINE_HASH_MANIFEST_PATH", hash_path)

        excluded = pd.DataFrame([{
            "prediction_season": 2026, "player_id": "P2", "position": "WR", "team": "SEA",
            "roster_status": "CUT", "exclusion_reason": "excluded_status_CUT",
        }])
        spine_result = RosterSpineResult(included=spine, excluded=excluded)
        entrypoint.write_live_spine_outputs(spine_result)

        assert included_path.exists() and excluded_path.exists() and sidecar_path.exists() and hash_path.exists()
        sidecar_df = pd.read_csv(sidecar_path)
        assert list(sidecar_df.columns) == ["prediction_season", "player_id", "future_season_roster_status"]
        excluded_df = pd.read_csv(excluded_path)
        assert excluded_df.iloc[0]["exclusion_reason"] == "excluded_status_CUT"
        # This test never calls anything that writes CSV_PATH/PARQUET_PATH
        # (the real canonical-table export paths) -- `out` above (asserted
        # column-free of future_season_roster_status) is the only thing
        # that would ever be written there, and it was never merged with
        # the sidecar/excluded frames at any point in this test.


class TestUnknownStatusFailsLoudWithIdentity:
    def test_unknown_status_error_names_the_status_and_player(self):
        # ZZZ is a synthetic status that will never be real -- RSN is now
        # governed (recency-gated), so it can no longer serve as "the
        # unknown status" example. See lib/dataset2/future_season_spine.py's
        # _RECENCY_GATED_STATUSES.
        snapshot = pd.DataFrame([{
            "gsis_id": "00-9999999", "position": "WR", "latest_team": "SEA",
            "status": "ZZZ", "last_season": 2020,
        }])
        with pytest.raises(ValueError) as exc_info:
            build_future_season_roster_spine(
                snapshot, PREDICTION_SEASON,
                pd.Timestamp("2026-08-01", tz="UTC"), pd.Timestamp("2026-09-04", tz="UTC"),
            )
        message = str(exc_info.value)
        assert "ZZZ" in message
        assert "00-9999999" in message
