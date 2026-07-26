"""
tests/test_mfl_2025_adp_correction.py

Covers scripts/mfl_2025_adp_correction.py -- the 2026-07 fallback
design (see that module's docstring and config.py's MFL_2025_* block
for the full decision record). Raw MFL AUG15 mean_adp is canonical for
ALL FOUR positions; Method B survives only as a disclosed, NEVER-
CONSUMED QB/TE sensitivity rank.

TestSensitivityFieldNeverConsumedDownstream is the most important
class in this file: it mechanically enforces (by scanning real source,
not by trusting a docstring) that no scoring or eligibility path in
this codebase ever reads config.MFL_2025_SENSITIVITY_RANK_FIELD.

TestQuantileMapConstruction pins the v2 endpoint-preserving rank/(n-1)
behavior -- the fix applied after the v1 asymmetry (rank/n, where only
the training minimum reached its target bound exactly) was reviewed
and rejected in favor of a symmetric convention.

TestNamedCaseRegression pins the sensitivity rank's real, exact values
-- including Mark Andrews as a disclosed adverse case (every
independent source shows the correction pricing him worse, not
better; no player-specific override is applied to a position-level
policy).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from scripts.mfl_2025_adp_correction import (
    build_mfl_2025_adp_and_sensitivity,
    load_calibration,
    quantile_map,
)

CALIBRATION = load_calibration()
FIELD = config.MFL_2025_SENSITIVITY_RANK_FIELD


class TestCalibrationLoading:
    def test_loads_both_required_positions(self):
        cal = load_calibration()
        assert set(cal.keys()) == config.MFL_2025_CORRECTION_POSITIONS

    def test_qb_and_te_counts_match_the_frozen_study(self):
        cal = load_calibration()
        assert len(cal["QB"][0]) == 35
        assert len(cal["TE"][0]) == 36

    def test_missing_required_column_raises(self, tmp_path):
        bad = tmp_path / "bad_calibration.csv"
        pd.DataFrame({"position": ["QB"], "mfl_mean_adp": [1.0]}).to_csv(bad, index=False)
        with pytest.raises(ValueError, match="missing required columns"):
            load_calibration(str(bad))

    def test_zero_rows_for_a_required_position_raises(self, tmp_path):
        bad = tmp_path / "bad_calibration.csv"
        pd.DataFrame({
            "player_name_mfl_raw": ["Someone, TE"], "position": ["TE"],
            "mfl_mean_adp": [10.0], "consensus_avg_rank": [10.0], "n_drafts": [100],
        }).to_csv(bad, index=False)
        with pytest.raises(ValueError, match="zero rows for required position 'QB'"):
            load_calibration(str(bad))


class TestQuantileMapConstruction:
    """v2: endpoint-preserving rank/(n-1), fixed after the v1 rank/n
    asymmetry was reviewed and rejected -- both tails must now hit
    their target bound exactly, not just the minimum."""

    def test_source_minimum_maps_exactly_to_target_minimum(self):
        src, tgt = CALIBRATION["QB"]
        assert quantile_map(src.min(), src, tgt) == pytest.approx(tgt.min())

    def test_source_maximum_maps_exactly_to_target_maximum(self):
        """The v1 bug this fixes: under rank/n, the exact training
        maximum landed short of target.max() by 1/n of the percentile
        range. Under rank/(n-1) it must hit exactly."""
        src, tgt = CALIBRATION["QB"]
        assert quantile_map(src.max(), src, tgt) == pytest.approx(tgt.max())

    def test_te_endpoints_also_exact(self):
        src, tgt = CALIBRATION["TE"]
        assert quantile_map(src.min(), src, tgt) == pytest.approx(tgt.min())
        assert quantile_map(src.max(), src, tgt) == pytest.approx(tgt.max())

    def test_monotonic_non_decreasing(self):
        src, tgt = CALIBRATION["TE"]
        probe = np.linspace(src.min(), src.max(), 200)
        corrected = [quantile_map(v, src, tgt) for v in probe]
        assert all(b >= a for a, b in zip(corrected, corrected[1:]))

    def test_mismatched_array_lengths_raise(self):
        with pytest.raises(ValueError, match="same length"):
            quantile_map(10.0, np.array([1.0, 2.0]), np.array([1.0, 2.0, 3.0]))

    def test_empty_arrays_raise(self):
        with pytest.raises(ValueError, match="empty calibration array"):
            quantile_map(10.0, np.array([]), np.array([]))

    def test_single_point_array_does_not_divide_by_zero(self):
        result = quantile_map(5.0, np.array([5.0]), np.array([42.0]))
        assert result == pytest.approx(42.0)


class TestOutOfRangeClamping:
    def test_value_far_below_training_range_clamps_to_target_min(self):
        src, tgt = CALIBRATION["QB"]
        result = quantile_map(0.5, src, tgt)
        assert result == pytest.approx(tgt.min())
        assert result >= 0

    def test_value_far_above_training_range_clamps_to_target_max(self):
        src, tgt = CALIBRATION["TE"]
        assert quantile_map(10_000.0, src, tgt) == pytest.approx(tgt.max())

    def test_no_negative_output_across_a_wide_probe_range(self):
        for pos in ("QB", "TE"):
            src, tgt = CALIBRATION[pos]
            probe = np.linspace(-100, 1000, 500)
            assert all(quantile_map(v, src, tgt) >= 0 for v in probe)


class TestTiesResolveDeterministically:
    def test_identical_raw_inputs_produce_identical_output(self):
        src, tgt = CALIBRATION["QB"]
        assert quantile_map(50.0, src, tgt) == quantile_map(50.0, src, tgt)


class TestNamedCaseRegression:
    """Exact sensitivity-rank values from the real frozen calibration
    file, v2 (endpoint-preserving) construction. Full float64
    precision pulled directly from the calibration CSV, not
    retyped/rounded literals."""

    CAL_DF = pd.read_csv(config.MFL_2025_CORRECTION_CALIBRATION_PATH)

    def _raw(self, mfl_raw_name):
        row = self.CAL_DF[self.CAL_DF["player_name_mfl_raw"] == mfl_raw_name]
        assert len(row) == 1
        return row.iloc[0]["position"], row.iloc[0]["mfl_mean_adp"]

    @pytest.mark.parametrize("mfl_name,expected", [
        ("Allen, Josh", 21.30),
        ("Jackson, Lamar", 22.70),
        ("Burrow, Joe", 30.30),
        ("McBride, Trey", 27.00),
        ("Bowers, Brock", 19.70),
        ("Kelce, Travis", 60.70),
    ])
    def test_named_case_sensitivity_rank(self, mfl_name, expected):
        pos, raw = self._raw(mfl_name)
        src, tgt = CALIBRATION[pos]
        assert quantile_map(raw, src, tgt) == pytest.approx(expected, abs=1e-4)

    def test_mark_andrews_disclosed_adverse_case(self):
        """Every independent source (RTSports, ESPN, Sleeper) shows
        the correction pricing Andrews WORSE, not better, than raw MFL.
        No player-specific override is applied -- this test confirms
        he receives the ordinary sensitivity-rank treatment like every
        other TE, and pins the exact (known-suboptimal) value so a
        future change to this fact is visible, not silent. Since this
        field is never consumed downstream (see
        TestSensitivityFieldNeverConsumedDownstream), the adverse
        ordering has zero effect on any canonical output -- it exists
        only in the disclosed sensitivity field."""
        pos, raw = self._raw("Andrews, Mark")
        assert pos == "TE"
        src, tgt = CALIBRATION[pos]
        corrected = quantile_map(raw, src, tgt)
        assert corrected == pytest.approx(63.30, abs=1e-4)
        assert corrected < raw  # wrong direction vs. every independent source


class TestBuildMfl2025AdpAndSensitivity:
    def _population(self):
        return pd.DataFrame({
            "player_id": ["p1", "p2", "p3", "p4"],
            "player_name": ["QB Player", "TE Player", "RB Player", "WR Player"],
            "position": ["QB", "TE", "RB", "WR"],
            "mfl_mean_adp": [6.267015706806283, 27.36315789473684, 40.0, 55.0],
        })

    def test_overall_adp_is_raw_mfl_for_every_position(self):
        """The core fallback-design invariant: NO correction is written
        into overall_adp, for ANY position, including QB/TE."""
        pop = self._population()
        out = build_mfl_2025_adp_and_sensitivity(pop, calibration=CALIBRATION)
        assert list(out["overall_adp"]) == list(pop["mfl_mean_adp"])

    def test_overall_adp_mfl_raw_matches_overall_adp(self):
        out = build_mfl_2025_adp_and_sensitivity(self._population(), calibration=CALIBRATION)
        assert list(out["overall_adp"]) == list(out["overall_adp_mfl_raw"])

    def test_sensitivity_field_populated_only_for_qb_te(self):
        out = build_mfl_2025_adp_and_sensitivity(self._population(), calibration=CALIBRATION)
        qb_row = out[out["position"] == "QB"].iloc[0]
        te_row = out[out["position"] == "TE"].iloc[0]
        assert qb_row[FIELD] == pytest.approx(21.30, abs=1e-4)
        assert te_row[FIELD] == pytest.approx(19.70, abs=1e-4)

    def test_sensitivity_field_null_for_rb_wr(self):
        out = build_mfl_2025_adp_and_sensitivity(self._population(), calibration=CALIBRATION)
        for pos in ("RB", "WR"):
            row = out[out["position"] == pos].iloc[0]
            assert pd.isna(row[FIELD])

    def test_sensitivity_field_name_contains_rank_not_adp(self):
        assert "rank" in FIELD.lower()
        assert "adp" not in FIELD.lower()

    def test_adp_source_set_for_every_row(self):
        out = build_mfl_2025_adp_and_sensitivity(self._population(), calibration=CALIBRATION)
        assert (out["adp_source"] == config.MFL_2025_ADP_SOURCE).all()

    def test_missing_required_column_raises(self):
        bad = self._population().drop(columns=["mfl_mean_adp"])
        with pytest.raises(ValueError, match="missing required columns"):
            build_mfl_2025_adp_and_sensitivity(bad, calibration=CALIBRATION)

    def test_null_mfl_mean_adp_raises(self):
        bad = self._population()
        bad.loc[0, "mfl_mean_adp"] = None
        with pytest.raises(ValueError, match="null value"):
            build_mfl_2025_adp_and_sensitivity(bad, calibration=CALIBRATION)

    def test_does_not_mutate_input(self):
        pop = self._population()
        original = pop.copy()
        build_mfl_2025_adp_and_sensitivity(pop, calibration=CALIBRATION)
        pd.testing.assert_frame_equal(pop, original)

    def test_positional_adp_not_written(self):
        out = build_mfl_2025_adp_and_sensitivity(self._population(), calibration=CALIBRATION)
        assert "positional_adp" not in out.columns


class TestSensitivityFieldNeverConsumedDownstream:
    """The mechanical guarantee: no scoring or eligibility path in this
    codebase may ever read config.MFL_2025_SENSITIVITY_RANK_FIELD --
    checked by scanning real source files, not by trusting a
    docstring. If this test ever fails, someone wired the sensitivity
    field into a consumer and that is a real regression, not a false
    positive to silence."""

    CONSUMER_FILES = (
        "scripts/05_calculate_metrics.py",
        "scripts/04_build_master_dataset.py",
        "scripts/09_fit_sbv_expected_production.py",
        "lib/stars_by_value/production.py",
        "lib/stars_by_value/expected_production.py",
        "lib/stars_by_value/acquisition_cost.py",
        "lib/stars_by_value/minimal_market_cost.py",
        "lib/stars_by_value/labeling.py",
    )

    REPO_ROOT = Path(__file__).resolve().parent.parent

    @pytest.mark.parametrize("relpath", CONSUMER_FILES)
    def test_consumer_does_not_reference_sensitivity_field(self, relpath):
        path = self.REPO_ROOT / relpath
        if not path.exists():
            pytest.skip(f"{relpath} does not exist yet")
        source = path.read_text()
        assert config.MFL_2025_SENSITIVITY_RANK_FIELD not in source, (
            f"{relpath} references {config.MFL_2025_SENSITIVITY_RANK_FIELD!r} -- "
            f"the sensitivity field must never be consumed by a scoring or "
            f"eligibility path"
        )

    def test_field_name_itself_is_distinct_from_overall_adp(self):
        """Sanity check on the guarantee's own premise -- if the field
        were ever accidentally named identically to a real consumed
        column, the scan above would pass for the wrong reason."""
        assert config.MFL_2025_SENSITIVITY_RANK_FIELD not in (
            "overall_adp", "overall_adp_model", "overall_adp_observed", "positional_adp",
        )


class TestConfigValidation:
    def test_valid_config_passes(self):
        config.validate_mfl_2025_correction_config()

    def test_rb_in_positions_raises(self, monkeypatch):
        monkeypatch.setattr(config, "MFL_2025_CORRECTION_POSITIONS", {"QB", "TE", "RB"})
        with pytest.raises(ValueError, match="must not include RB or WR"):
            config.validate_mfl_2025_correction_config()

    def test_empty_positions_raises(self, monkeypatch):
        monkeypatch.setattr(config, "MFL_2025_CORRECTION_POSITIONS", set())
        with pytest.raises(ValueError, match="must not be empty"):
            config.validate_mfl_2025_correction_config()

    def test_sensitivity_field_name_containing_adp_raises(self, monkeypatch):
        monkeypatch.setattr(config, "MFL_2025_SENSITIVITY_RANK_FIELD", "mfl_2025_sensitivity_adp")
        with pytest.raises(ValueError, match="must NOT contain 'adp'"):
            config.validate_mfl_2025_correction_config()

    def test_empty_sensitivity_field_name_raises(self, monkeypatch):
        monkeypatch.setattr(config, "MFL_2025_SENSITIVITY_RANK_FIELD", "")
        with pytest.raises(ValueError, match="MFL_2025_SENSITIVITY_RANK_FIELD"):
            config.validate_mfl_2025_correction_config()


class TestNoForbiddenImports:
    """Production code must not IMPORT FROM research/ scratch paths --
    checks real ast.Import/ast.ImportFrom nodes, not arbitrary string
    constants (a naive string-match false-positives on this module's
    own docstring, which legitimately discusses research provenance by
    path -- this project already hit and fixed exactly that mistake
    once, in tests/test_expected_production.py)."""

    def test_module_has_no_research_import_statements(self):
        import ast
        import inspect
        from scripts import mfl_2025_adp_correction as mod

        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "research" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                assert "research" not in (node.module or "")
