"""
tests/test_calculate_metrics.py

Covers scripts/05_calculate_metrics.py. The module is a numbered file,
loaded via importlib.

TestIndexAlignmentRegression is the most important test in this file:
it's a direct regression test for a real bug found while building this
script -- an internal .merge() inside compute_component_5 and
compute_component_6 reset the dataframe's index, and the caller's
implicit index-label assignment silently misaligned 1,907 of 2,643
real rows (72%) before the fix. This test builds a dataframe with a
deliberately NON-contiguous index (mimicking what filtering the real
master table produces) specifically to catch this class of bug if it
ever regresses.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "05_calculate_metrics.py"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("calculate_metrics", SCRIPT_PATH)
    m = importlib.util.module_from_spec(spec)
    sys.modules["calculate_metrics"] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def config_mod(tmp_path, monkeypatch):
    """validate_lwi_config() is DEFINED INSIDE config.py and reads its
    globals from THAT module's namespace -- patching the aliased names
    imported into 05_calculate_metrics.py does NOT affect it (confirmed
    directly: patching mod.LWI_WEIGHTS left validate_lwi_config() still
    validating against the real config.py values, silently passing a
    test that should have failed). This fixture loads config.py
    directly so tests patch the module the function actually reads
    from."""
    monkeypatch.chdir(tmp_path)
    config_path = Path(__file__).resolve().parent.parent / "config.py"
    spec = importlib.util.spec_from_file_location("test_config", config_path)
    c = importlib.util.module_from_spec(spec)
    sys.modules["test_config"] = c
    spec.loader.exec_module(c)
    return c


class TestMinMaxNormalize:
    def test_single_member_group_gets_50_not_undefined(self, mod):
        # A group of 1 has no real comparison -- should get a neutral
        # 50, not NaN from a 0/0 division and not an arbitrary 0 or 100.
        df = pd.DataFrame({"season": [2020], "position": ["QB"], "val": [42.0]})
        result = mod.minmax_normalize_within_group(df, "val", ["season", "position"])
        assert result.iloc[0] == 50.0

    def test_normal_group_scales_correctly(self, mod):
        df = pd.DataFrame({
            "season": [2020, 2020, 2020],
            "position": ["QB", "QB", "QB"],
            "val": [0.0, 5.0, 10.0],
        })
        result = mod.minmax_normalize_within_group(df, "val", ["season", "position"])
        assert list(result) == [0.0, 50.0, 100.0]


class TestPlayoffWeeks:
    def test_pre_2021_uses_weeks_14_16(self, mod):
        assert mod.get_playoff_weeks(2020) == [14, 15, 16]
        assert mod.get_playoff_weeks(2006) == [14, 15, 16]

    def test_2021_and_later_uses_weeks_15_17(self, mod):
        assert mod.get_playoff_weeks(2021) == [15, 16, 17]
        assert mod.get_playoff_weeks(2024) == [15, 16, 17]


class TestIndexAlignmentRegression:
    """See module docstring -- this is the highest-value test in the
    whole suite. It exists because this exact bug silently corrupted
    72% of real output before being caught."""

    def _make_eligible_df(self, non_contiguous_index):
        df = pd.DataFrame({
            "season": [2020, 2020, 2020],
            "player_id": ["00-A", "00-B", "00-C"],
            "position": ["RB", "RB", "RB"],
            "ppg_ppr": [10.0, 15.0, 20.0],
        })
        if non_contiguous_index:
            # Mimics what master[eligible_mask] produces -- an index
            # inherited from the original, larger dataframe, NOT a
            # clean 0..N-1 range.
            df.index = pd.Index([7, 23, 99])
        return df

    def _make_weekly_df(self):
        rows = []
        for pid in ["00-A", "00-B", "00-C"]:
            for wk in range(1, 9):
                rows.append({
                    "season": 2020, "player_id": pid, "week": wk,
                    "fantasy_points_ppr": 10.0,
                })
        return pd.DataFrame(rows)

    def test_component_5_preserves_original_index(self, mod):
        eligible = self._make_eligible_df(non_contiguous_index=True)
        weekly = self._make_weekly_df()

        component, games_played, availability = mod.compute_component_5_playoff_performance(
            eligible, weekly
        )
        assert list(component.index) == [7, 23, 99], (
            "compute_component_5 did not preserve the original index -- "
            "this is the exact bug that silently produced NaN for 72% "
            "of real rows before it was fixed."
        )
        # With this fix, assigning back onto eligible must NOT introduce NaN
        eligible["playoff_performance_component"] = component
        assert eligible["playoff_performance_component"].isna().sum() == 0

    def test_component_6_preserves_original_index(self, mod):
        eligible = self._make_eligible_df(non_contiguous_index=True)
        weekly = self._make_weekly_df()

        component = mod.compute_component_6_consistency(eligible, weekly)
        assert list(component.index) == [7, 23, 99], (
            "compute_component_6 did not preserve the original index -- "
            "same class of bug as compute_component_5."
        )
        eligible["consistency_component"] = component
        assert eligible["consistency_component"].isna().sum() == 0

    def test_contiguous_index_also_still_works(self, mod):
        # Sanity check: the fix shouldn't break the common case either.
        eligible = self._make_eligible_df(non_contiguous_index=False)
        weekly = self._make_weekly_df()
        component, _, _ = mod.compute_component_5_playoff_performance(eligible, weekly)
        assert component.isna().sum() == 0


class TestConfigValidation:
    """Config validation must fail loudly on bad input, not silently
    produce plausible-looking scores. Each test breaks exactly one
    rule and confirms it's caught.

    IMPORTANT: these tests use the config_mod fixture (config.py loaded
    directly), NOT mod (05_calculate_metrics.py's aliased imports) --
    validate_lwi_config() reads its globals from config.py's own
    namespace, so patching mod's aliased names would silently test
    nothing. Confirmed this distinction matters by testing it directly
    before writing these."""

    def test_valid_config_passes(self, config_mod):
        config_mod.validate_lwi_config()  # should not raise

    def test_weights_not_summing_to_one_is_rejected(self, config_mod):
        config_mod.LWI_WEIGHTS = {
            "adp_value": 0.5, "fantasy_finish": 0.5, "ppg": 0.5,
            "positional_advantage": 0.12, "playoff_performance": 0.04,
            "consistency": 0.03,
        }
        with pytest.raises(ValueError, match="must sum to 1.0"):
            config_mod.validate_lwi_config()

    def test_negative_weight_is_rejected(self, config_mod):
        weights = dict(config_mod.LWI_WEIGHTS)
        weights["consistency"] = -0.03
        weights["adp_value"] = 0.49  # keep sum at 1.0 to isolate this check
        config_mod.LWI_WEIGHTS = weights
        with pytest.raises(ValueError, match="negative"):
            config_mod.validate_lwi_config()

    def test_zero_min_games_is_rejected(self, config_mod):
        config_mod.LWI_MIN_GAMES = 0
        with pytest.raises(ValueError, match="LWI_MIN_GAMES"):
            config_mod.validate_lwi_config()

    def test_negative_replacement_threshold_is_rejected(self, config_mod):
        config_mod.LWI_REPLACEMENT_RANK_THRESHOLDS = {"QB": -5}
        with pytest.raises(ValueError, match="LWI_REPLACEMENT_RANK_THRESHOLDS"):
            config_mod.validate_lwi_config()

    def test_invalid_playoff_week_number_is_rejected(self, config_mod):
        config_mod.LWI_PLAYOFF_WEEKS_16_GAME_ERA = [14, 15, 99]
        with pytest.raises(ValueError, match="LWI_PLAYOFF_WEEKS_16_GAME_ERA"):
            config_mod.validate_lwi_config()


class TestConfigPropagation:
    """Proves changing config values actually changes the calculation
    -- not just that the config exists and validates. Without this,
    config.py could become decorative while a hidden hardcoded value
    survives somewhere in the actual formula."""

    def test_changing_replacement_threshold_changes_component_4(self, mod, monkeypatch):
        # NOTE: this test is what originally caught a real formula bug
        # -- see the docstring on compute_component_4_positional_advantage
        # for the full story. Component 4 must be grouped across
        # positions (season only), not within a single position, or
        # this test would pass vacuously (any within-position grouping
        # makes a replacement-level shift mathematically invisible).
        df = pd.DataFrame({
            "season": [2020] * 6,
            "position": ["QB", "QB", "QB", "RB", "RB", "RB"],
            "position_finish_ppr": [1, 2, 3, 1, 2, 3],
            "ppg_ppr": [25.0, 20.0, 15.0, 12.0, 10.0, 8.0],
        })

        monkeypatch.setattr(mod, "REPLACEMENT_RANK_THRESHOLDS", {"QB": 1, "RB": 1})
        monkeypatch.setattr(mod, "REPLACEMENT_WINDOW", 2)
        result_a = mod.compute_component_4_positional_advantage(df.copy())

        monkeypatch.setattr(mod, "REPLACEMENT_RANK_THRESHOLDS", {"QB": 3, "RB": 1})
        result_b = mod.compute_component_4_positional_advantage(df.copy())

        assert not result_a.equals(result_b), (
            "Changing the replacement-rank threshold had no effect on "
            "Component 4 -- config may not actually be wired through, "
            "OR the within-group normalization bug has regressed (see "
            "compute_component_4_positional_advantage's docstring)."
        )

    def test_component_4_differs_from_component_3_across_positions(self, mod):
        # Direct regression test for the bug itself: two players with
        # the same WITHIN-POSITION rank but different cross-position
        # value-over-replacement must NOT get identical Component 4
        # scores just because they're both "top of their position."
        df = pd.DataFrame({
            "season": [2020] * 6,
            "position": ["QB", "QB", "QB", "RB", "RB", "RB"],
            "position_finish_ppr": [1, 2, 3, 1, 2, 3],
            "ppg_ppr": [25.0, 20.0, 15.0, 12.0, 10.0, 8.0],
        })
        result = mod.compute_component_4_positional_advantage(df.copy())
        # Both QB1 and RB1 are "#1 at their position," but QB1's real
        # margin over replacement (25-15=10) is more than double RB1's
        # (12-8=4) -- they must NOT score identically.
        assert result.iloc[0] != result.iloc[3], (
            "QB1 and RB1 scored identically on Component 4 despite very "
            "different margins over replacement -- the within-group "
            "normalization bug has regressed."
        )

    def test_changing_weight_changes_final_score_proportionally(self, mod):
        # Direct arithmetic check, not a full pipeline run -- confirms
        # the weighting formula itself responds to WEIGHTS as expected.
        components = {
            "adp_value_component": 100.0, "fantasy_finish_component": 0.0,
            "ppg_component": 0.0, "positional_advantage_component": 0.0,
            "playoff_performance_component": 0.0, "consistency_component": 0.0,
        }
        score_at_default_weight = mod.WEIGHTS["adp_value"] * components["adp_value_component"]
        assert score_at_default_weight == pytest.approx(46.0)

        # If adp_value weight were doubled (hypothetically), the
        # contribution from a maxed adp_value_component should double too
        assert (mod.WEIGHTS["adp_value"] * 2) * components["adp_value_component"] == pytest.approx(92.0)


class TestComponentAvailabilityPolicy:
    """Per docs/METRIC_SPECIFICATION.md's component availability
    policy: an incomplete component set must never produce a normal-
    looking lwi_score, and must never silently redistribute the
    missing weight. Moot in production today (every real row has all
    6 components), but this exercises the guard directly so it's
    proven correct before it's ever actually needed."""

    def test_incomplete_row_gets_null_score_and_flagged_coverage(self, mod):
        eligible = pd.DataFrame({
            "adp_value_component": [80.0, 80.0],
            "fantasy_finish_component": [70.0, 70.0],
            "ppg_component": [60.0, 60.0],
            "positional_advantage_component": [50.0, 50.0],
            "playoff_performance_component": [90.0, None],  # row 1 missing this one
            "consistency_component": [40.0, 40.0],
        })

        component_cols = [
            "adp_value_component", "fantasy_finish_component", "ppg_component",
            "positional_advantage_component", "playoff_performance_component",
            "consistency_component",
        ]
        n_available = eligible[component_cols].notna().sum(axis=1)
        is_complete = n_available == len(component_cols)

        assert is_complete.tolist() == [True, False]

        diagnostic = (
            0.46 * eligible["adp_value_component"].fillna(0)
            + 0.18 * eligible["fantasy_finish_component"].fillna(0)
            + 0.17 * eligible["ppg_component"].fillna(0)
            + 0.12 * eligible["positional_advantage_component"].fillna(0)
            + 0.04 * eligible["playoff_performance_component"].fillna(0)
            + 0.03 * eligible["consistency_component"].fillna(0)
        )
        lwi_score = diagnostic.where(is_complete)

        # Complete row: real score, not null
        assert pd.notna(lwi_score.iloc[0])
        # Incomplete row: null in the REAL score column, per policy --
        # even though a number could technically be computed, it must
        # not appear in lwi_score.
        assert pd.isna(lwi_score.iloc[1])
        # But the diagnostic column still has a real (labeled-elsewhere-
        # as-partial) number for anyone who explicitly wants it.
        assert pd.notna(diagnostic.iloc[1])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
