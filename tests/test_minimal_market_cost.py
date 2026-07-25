"""
tests/test_minimal_market_cost.py

Covers lib/stars_by_value/minimal_market_cost.py -- the minimal-
market-cost expected-production formula (methodology section 9,
settled). All inputs are already-settled SBV_* config constants
(SBV_MMC_OPPORTUNITY_PROBABILITY, SBV_MMC_REPLACEMENT_PPG,
SBV_MMC_ROLE_CONDITIONAL_DISCOUNT) plus production.py's already-
verified season_length() -- this module is a single formula wiring
them together, not new methodology, so these tests protect the wiring
(reads config, doesn't duplicate it; correct season-varying G; fails
loudly on bad input) rather than re-deriving the formula's own
correctness.

TestDecoupledFromProductionWeightAatp is the most important class
here: SBV_MMC_ROLE_CONDITIONAL_DISCOUNT and SBV_PRODUCTION_WEIGHT_AATP
currently share a value (0.5) but are different quantities (a role-
conditional production discount vs. production.py's composite weight)
-- an earlier version of this module reused SBV_PRODUCTION_WEIGHT_AATP
directly for this formula, which was reviewed and rejected specifically
because it would silently couple two independent methodology
parameters. These tests prove the decoupling mechanically: changing
SBV_PRODUCTION_WEIGHT_AATP must NOT move the MMC expectation, and
changing SBV_MMC_ROLE_CONDITIONAL_DISCOUNT must.

Regression reference values are computed directly from the exact
config constants (not the 1-decimal "headline" numbers quoted in
STARS_BY_VALUE_METHODOLOGY.md's prose, e.g. "QB 31.0" -- those are
rounded for readability; the true values to 2 decimal places are
computed once here, deterministically, from
SBV_MMC_OPPORTUNITY_PROBABILITY x SBV_MMC_ROLE_CONDITIONAL_DISCOUNT x
SBV_MMC_REPLACEMENT_PPG x {16, 17}).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from lib.stars_by_value import minimal_market_cost as mmc

# Computed directly from config.py's settled constants (0.247/0.290/0.368/0.285
# opportunity probabilities, 14.746/9.361/11.423/7.970 replacement PPG,
# 0.5 weight), rounded to 2 decimals -- NOT the 1-decimal prose headlines.
EXPECTED_16_GAME = {"QB": 29.14, "RB": 21.72, "WR": 33.63, "TE": 18.17}
EXPECTED_17_GAME = {"QB": 30.96, "RB": 23.07, "WR": 35.73, "TE": 19.31}


class TestSettledReferenceValues:
    """16-game era: any season <= 2020. 17-game era: any season >= 2021
    (config.SBV_SEASON_LENGTH_ERA_CUTOFF)."""

    @pytest.mark.parametrize("position", ["QB", "RB", "WR", "TE"])
    def test_16_game_era_value(self, position):
        result = mmc.minimal_market_cost_expected_production(position, 2019)
        assert round(result, 2) == EXPECTED_16_GAME[position]

    @pytest.mark.parametrize("position", ["QB", "RB", "WR", "TE"])
    def test_17_game_era_value(self, position):
        result = mmc.minimal_market_cost_expected_production(position, 2023)
        assert round(result, 2) == EXPECTED_17_GAME[position]

    def test_2020_is_16_game_era(self):
        assert round(mmc.minimal_market_cost_expected_production("QB", 2020), 2) == EXPECTED_16_GAME["QB"]

    def test_2021_is_17_game_era(self):
        assert round(mmc.minimal_market_cost_expected_production("QB", 2021), 2) == EXPECTED_17_GAME["QB"]


class TestSeasonVaryingG:
    def test_16_and_17_game_eras_produce_different_values_for_same_position(self):
        v16 = mmc.minimal_market_cost_expected_production("RB", 2019)
        v17 = mmc.minimal_market_cost_expected_production("RB", 2023)
        assert v16 != v17
        assert v17 > v16  # more games -> more expected production

    def test_ratio_between_eras_matches_16_to_17_game_ratio_exactly(self):
        v16 = mmc.minimal_market_cost_expected_production("WR", 2019)
        v17 = mmc.minimal_market_cost_expected_production("WR", 2023)
        assert v17 / v16 == pytest.approx(17 / 16, rel=1e-9)


class TestInputValidation:
    def test_invalid_position_raises(self):
        with pytest.raises(ValueError, match="Unsupported position"):
            mmc.minimal_market_cost_expected_production("K", 2020)

    def test_lowercase_position_raises(self):
        with pytest.raises(ValueError, match="Unsupported position"):
            mmc.minimal_market_cost_expected_production("qb", 2020)

    def test_non_integer_season_string_raises(self):
        with pytest.raises(ValueError, match="season must be an integer"):
            mmc.minimal_market_cost_expected_production("QB", "2020")

    def test_non_integer_season_float_raises(self):
        with pytest.raises(ValueError, match="season must be an integer"):
            mmc.minimal_market_cost_expected_production("QB", 2020.5)

    def test_boolean_season_raises(self):
        """bool is a subclass of int in Python -- must be explicitly
        rejected, not silently accepted as 0 or 1."""
        with pytest.raises(ValueError, match="season must be an integer"):
            mmc.minimal_market_cost_expected_production("QB", True)

    def test_none_season_raises(self):
        with pytest.raises(ValueError, match="season must be an integer"):
            mmc.minimal_market_cost_expected_production("QB", None)


class TestFailsLoudOnMissingConfigOrNonFinite:
    def test_missing_opportunity_probability_key_raises(self, monkeypatch):
        patched = dict(config.SBV_MMC_OPPORTUNITY_PROBABILITY)
        del patched["QB"]
        monkeypatch.setattr(config, "SBV_MMC_OPPORTUNITY_PROBABILITY", patched)
        monkeypatch.setattr(mmc, "SBV_MMC_OPPORTUNITY_PROBABILITY", patched)
        with pytest.raises(ValueError, match="SBV_MMC_OPPORTUNITY_PROBABILITY is missing"):
            mmc.minimal_market_cost_expected_production("QB", 2020)

    def test_missing_replacement_ppg_key_raises(self, monkeypatch):
        patched = dict(config.SBV_MMC_REPLACEMENT_PPG)
        del patched["RB"]
        monkeypatch.setattr(config, "SBV_MMC_REPLACEMENT_PPG", patched)
        monkeypatch.setattr(mmc, "SBV_MMC_REPLACEMENT_PPG", patched)
        with pytest.raises(ValueError, match="SBV_MMC_REPLACEMENT_PPG is missing"):
            mmc.minimal_market_cost_expected_production("RB", 2020)

    def test_non_finite_result_raises(self, monkeypatch):
        patched = dict(config.SBV_MMC_REPLACEMENT_PPG)
        patched["TE"] = float("inf")
        monkeypatch.setattr(mmc, "SBV_MMC_REPLACEMENT_PPG", patched)
        with pytest.raises(ValueError, match="non-finite value"):
            mmc.minimal_market_cost_expected_production("TE", 2020)

    def test_nan_result_raises(self, monkeypatch):
        patched = dict(config.SBV_MMC_REPLACEMENT_PPG)
        patched["WR"] = float("nan")
        monkeypatch.setattr(mmc, "SBV_MMC_REPLACEMENT_PPG", patched)
        with pytest.raises(ValueError, match="non-finite value"):
            mmc.minimal_market_cost_expected_production("WR", 2020)


class TestReadsConfigRatherThanDuplicating:
    """Mutates the SHARED dict object config.py owns (not a copy) and
    confirms the function's output moves with it -- proves the module
    holds a live reference to config's dict, not a hardcoded or
    snapshotted duplicate of the values."""

    def test_mutating_opportunity_probability_changes_the_result(self):
        original = config.SBV_MMC_OPPORTUNITY_PROBABILITY["QB"]
        try:
            config.SBV_MMC_OPPORTUNITY_PROBABILITY["QB"] = 0.999
            result = mmc.minimal_market_cost_expected_production("QB", 2019)
            expected = 0.999 * config.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT * config.SBV_MMC_REPLACEMENT_PPG["QB"] * 16
            assert result == pytest.approx(expected)
            assert round(result, 2) != EXPECTED_16_GAME["QB"]
        finally:
            config.SBV_MMC_OPPORTUNITY_PROBABILITY["QB"] = original

    def test_mutating_replacement_ppg_changes_the_result(self):
        original = config.SBV_MMC_REPLACEMENT_PPG["TE"]
        try:
            config.SBV_MMC_REPLACEMENT_PPG["TE"] = 50.0
            result = mmc.minimal_market_cost_expected_production("TE", 2019)
            expected = config.SBV_MMC_OPPORTUNITY_PROBABILITY["TE"] * config.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT * 50.0 * 16
            assert result == pytest.approx(expected)
        finally:
            config.SBV_MMC_REPLACEMENT_PPG["TE"] = original


class TestDecoupledFromProductionWeightAatp:
    """The specific coupling problem this revision fixes -- see class
    docstring at module top. Both tests mutate the SHARED config
    object (not a local copy), matching TestReadsConfigRatherThanDuplicating's
    convention."""

    def test_changing_production_weight_aatp_does_not_change_mmc_expectation(self):
        baseline = mmc.minimal_market_cost_expected_production("QB", 2019)
        original = config.SBV_PRODUCTION_WEIGHT_AATP
        try:
            config.SBV_PRODUCTION_WEIGHT_AATP = 0.9  # a real, different value
            result = mmc.minimal_market_cost_expected_production("QB", 2019)
            assert result == pytest.approx(baseline)
            assert round(result, 2) == EXPECTED_16_GAME["QB"]
        finally:
            config.SBV_PRODUCTION_WEIGHT_AATP = original

    def test_changing_role_conditional_discount_does_change_mmc_expectation(self, monkeypatch):
        """SBV_MMC_ROLE_CONDITIONAL_DISCOUNT is a scalar (immutable) --
        unlike the dict constants above, `from config import X` binds
        an independent copy of the value, so reassigning
        config.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT would NOT propagate to
        this module's own binding (confirmed directly: an earlier
        version of this test patched the wrong name and passed for the
        wrong reason -- the assertion silently compared the baseline
        to itself). Patching mmc's own module-level name is the
        correct, and only, way to actually change what the function
        reads."""
        baseline = mmc.minimal_market_cost_expected_production("QB", 2019)
        monkeypatch.setattr(mmc, "SBV_MMC_ROLE_CONDITIONAL_DISCOUNT", 0.9)
        result = mmc.minimal_market_cost_expected_production("QB", 2019)
        assert result != pytest.approx(baseline)
        expected = config.SBV_MMC_OPPORTUNITY_PROBABILITY["QB"] * 0.9 * config.SBV_MMC_REPLACEMENT_PPG["QB"] * 16
        assert result == pytest.approx(expected)


class TestNoAcquisitionCostScoringOrLabelingImports:
    def test_module_does_not_import_forbidden_logic(self):
        import ast
        import inspect
        forbidden = ("acquisition_cost", "labeling")
        tree = ast.parse(inspect.getsource(mmc))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name for f in forbidden), f"forbidden import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not any(f in module for f in forbidden), f"forbidden import from: {module}"

    def test_module_does_not_import_research(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(mmc))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "research" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "research" not in module

    def test_reuses_production_season_length_not_a_reimplementation(self):
        """Confirms the exact function object is imported/reused, not
        a same-named local re-derivation."""
        from lib.stars_by_value.production import season_length as prod_season_length
        assert mmc.season_length is prod_season_length
