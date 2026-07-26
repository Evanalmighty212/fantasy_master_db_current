"""
tests/test_11_calculate_stars_by_value.py

Covers the pure population-shaping and build-completeness logic in
scripts/11_calculate_stars_by_value.py -- the SBV orchestration
scaffold. The module is a numbered file (invalid Python identifier),
loaded via importlib.

This is a SCAFFOLD, not the canonical build -- see the module's own
docstring for the build-completeness contract these tests protect:
a diagnostic run may complete with rows deferred; a canonical run must
refuse to write any output at all if anything is deferred, for any
reason. TestCheckBuildCompleteness is the most important class here --
it's the mechanism that makes it structurally impossible for a
canonical artifact to silently exclude rows.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "11_calculate_stars_by_value.py"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def load_module():
    spec = importlib.util.spec_from_file_location("calc_sbv", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = load_module()


def _pop_row(season, position, data_quality_flag, overall_adp, player_id="00-x"):
    adp_round = None if pd.isna(overall_adp) else int(-(-overall_adp // 12))  # ceil
    return {
        "season": season, "player_id": player_id, "player_name": "Test Player",
        "position": position, "data_quality_flag": data_quality_flag,
        "overall_adp": overall_adp, "adp_round": adp_round,
    }


def _ep_lookup_fixture():
    """Minimal real-shaped E_P lookup -- rounds 1-15 for every position,
    one season, matching the real fitted lookup's actual depth."""
    rows = []
    for pos in ("QB", "RB", "WR", "TE"):
        for rnd in range(1, 16):
            rows.append({"prediction_season": 2020, "position": pos, "draft_round": rnd, "expected_production": 100.0})
    return pd.DataFrame(rows)


class TestSplitProcessable:
    def test_matched_clean_row_always_processable_regardless_of_mfl(self):
        pop = pd.DataFrame([_pop_row(2013, "WR", "matched_clean", 24.0)])
        processable, deferred = MOD.split_processable(pop, _ep_lookup_fixture(), mfl_cache_seasons=())
        assert len(processable) == 1
        assert len(deferred) == 0

    def test_2010_no_adp_match_row_is_processable_without_mfl(self):
        """2010 uses mmc_2010_manual_overrides.csv, never MFL -- must
        never be deferred for missing MFL data."""
        pop = pd.DataFrame([_pop_row(2010, "RB", "no_adp_match", None)])
        processable, deferred = MOD.split_processable(pop, _ep_lookup_fixture(), mfl_cache_seasons=())
        assert len(processable) == 1
        assert len(deferred) == 0

    def test_no_adp_match_row_in_mfl_cached_season_is_processable(self):
        pop = pd.DataFrame([_pop_row(2015, "TE", "no_adp_match", None)])
        processable, deferred = MOD.split_processable(pop, _ep_lookup_fixture(), mfl_cache_seasons=(2015,))
        assert len(processable) == 1
        assert len(deferred) == 0

    def test_no_adp_match_row_in_uncached_season_is_deferred_with_reason(self):
        pop = pd.DataFrame([_pop_row(2013, "TE", "no_adp_match", None)])
        processable, deferred = MOD.split_processable(pop, _ep_lookup_fixture(), mfl_cache_seasons=(2015,))
        assert len(processable) == 0
        assert len(deferred) == 1
        assert deferred.iloc[0]["deferred_reason"] == MOD.DEFERRED_REASON_NO_MFL_DATA

    def test_round_too_deep_row_is_deferred_with_reason(self):
        pop = pd.DataFrame([_pop_row(2025, "QB", "matched_clean", 190.0)])  # round 16, lookup only has 1-15
        processable, deferred = MOD.split_processable(pop, _ep_lookup_fixture(), mfl_cache_seasons=())
        assert len(processable) == 0
        assert len(deferred) == 1
        assert deferred.iloc[0]["deferred_reason"] == MOD.DEFERRED_REASON_ROUND_TOO_DEEP

    def test_round_within_depth_is_processable(self):
        pop = pd.DataFrame([_pop_row(2025, "QB", "matched_clean", 170.0)])  # round 15, exactly at the edge
        processable, deferred = MOD.split_processable(pop, _ep_lookup_fixture(), mfl_cache_seasons=())
        assert len(processable) == 1
        assert len(deferred) == 0

    def test_row_matching_both_deferral_conditions_appears_exactly_once(self):
        """A no_adp_match/uncached-season row also has no adp_round
        (overall_adp is null for no_adp_match rows) -- the two
        deferral reasons are mutually exclusive by construction, but
        this test proves it mechanically, not just by assumption."""
        pop = pd.DataFrame([_pop_row(2013, "QB", "no_adp_match", None)])
        processable, deferred = MOD.split_processable(pop, _ep_lookup_fixture(), mfl_cache_seasons=())
        assert len(deferred) == 1  # not 2 -- never double-counted

    def test_mixed_population_partitions_correctly(self):
        pop = pd.DataFrame([
            _pop_row(2013, "WR", "matched_clean", 24.0, player_id="00-a"),
            _pop_row(2013, "TE", "no_adp_match", None, player_id="00-b"),
            _pop_row(2025, "QB", "matched_clean", 190.0, player_id="00-c"),
            _pop_row(2015, "RB", "no_adp_match", None, player_id="00-d"),
        ])
        processable, deferred = MOD.split_processable(pop, _ep_lookup_fixture(), mfl_cache_seasons=(2015,))
        assert set(processable["player_id"]) == {"00-a", "00-d"}
        assert set(deferred["player_id"]) == {"00-b", "00-c"}


class TestCheckBuildCompleteness:
    """The canonical-mode gate -- must raise on ANY deferred row, must
    never silently proceed."""

    def test_empty_deferred_does_not_raise(self):
        MOD.check_build_completeness(pd.DataFrame(columns=["deferred_reason"]))  # should not raise

    def test_nonempty_deferred_raises(self):
        deferred = pd.DataFrame([{"deferred_reason": MOD.DEFERRED_REASON_NO_MFL_DATA}])
        with pytest.raises(RuntimeError, match="Canonical SBV build refused"):
            MOD.check_build_completeness(deferred)

    def test_error_names_every_distinct_reason_and_count(self):
        deferred = pd.DataFrame([
            {"deferred_reason": MOD.DEFERRED_REASON_NO_MFL_DATA},
            {"deferred_reason": MOD.DEFERRED_REASON_NO_MFL_DATA},
            {"deferred_reason": MOD.DEFERRED_REASON_ROUND_TOO_DEEP},
        ])
        with pytest.raises(RuntimeError) as exc_info:
            MOD.check_build_completeness(deferred)
        message = str(exc_info.value)
        assert MOD.DEFERRED_REASON_NO_MFL_DATA in message
        assert MOD.DEFERRED_REASON_ROUND_TOO_DEEP in message
        assert "2 row(s)" in message
        assert "1 row(s)" in message

    def test_never_called_implicitly_by_diagnostic_mode(self):
        """Sanity/documentation check: diagnostic mode's own code path
        (main(), --mode diagnostic) must not call this function --
        verified by source inspection, since a diagnostic run
        completing successfully with deferred rows is the whole point
        of the mode."""
        import inspect
        source = inspect.getsource(MOD.main)
        # check_build_completeness is only invoked inside the
        # `if args.mode == "canonical":` branch -- a crude but honest
        # structural check that it's conditional, not unconditional.
        assert "check_build_completeness" in source
        assert 'args.mode == "canonical"' in source


class TestHistoryDfUsesFullPopulation:
    """Real bug caught while re-running the scaffold: an earlier
    version built history_df from `processable` (the current run's
    scoreable subset) instead of the full population -- silently
    narrowing classify_draft_status()'s prior-season lookback whenever
    a player's PRIOR-season row happened to be deferred in the CURRENT
    run (e.g. missing MFL data for that prior season), even though the
    lookback should see real prior production regardless. Caught by
    comparing two runs' status breakdowns and finding an unexplained
    shift with no other change -- fixed before ever being treated as
    canonical. This is a structural/source check, not a full
    integration test (run_label_rows() does real file I/O) -- the real
    fix was confirmed empirically by re-running the scaffold against
    real data and observing the status breakdown stabilize."""

    def test_history_df_is_built_from_full_pop_not_processable(self):
        import inspect
        source = inspect.getsource(MOD.run_label_rows)
        history_line = next(line for line in source.splitlines() if "history_df =" in line)
        assert "full_pop[" in history_line, f"history_df must be built from full_pop, got: {history_line!r}"

    def test_run_label_rows_signature_requires_full_pop(self):
        import inspect
        sig = inspect.signature(MOD.run_label_rows)
        assert "full_pop" in sig.parameters


class TestOutputPathsNeverCollide:
    """Diagnostic and canonical writes must never target the same
    file -- also checked in config.validate_sbv_config(), duplicated
    here as a direct regression pin on this specific module's constants."""

    def test_diagnostic_and_canonical_parquet_paths_differ(self):
        import config
        assert config.SBV_DIAGNOSTIC_OUTPUT_PARQUET_PATH != config.SBV_OUTPUT_PARQUET_PATH

    def test_diagnostic_and_canonical_csv_paths_differ(self):
        import config
        assert config.SBV_DIAGNOSTIC_OUTPUT_CSV_PATH != config.SBV_OUTPUT_CSV_EXPORT_PATH
