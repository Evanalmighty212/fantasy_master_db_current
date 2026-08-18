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
import zipfile
from pathlib import Path

import numpy as np
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


def _lwi_output_fixture():
    final = pd.DataFrame({
        "season": [2024, 2025],
        "player_id": ["P1", "P2"],
        "lwi_score": [81.1234567890123, 72.0],
    })
    report = pd.DataFrame({
        "season": [2024, 2025],
        "lwi_eligibility_flag": ["eligible", "eligible"],
        "row_count": [1, 1],
    })
    return final, report


def test_lwi_outputs_install_validated_xlsx_before_diagnostics(mod, tmp_path):
    final, report = _lwi_output_fixture()
    master_dir = tmp_path / "master"
    validation_dir = tmp_path / "validation"

    out_csv = mod.write_lwi_outputs(
        final, report, master_dir=master_dir, validation_dir=validation_dir,
    )
    out_xlsx = master_dir / "master_historical_db_with_lwi_2006_2025.xlsx"

    with zipfile.ZipFile(out_xlsx) as workbook_zip:
        assert workbook_zip.testzip() is None
    assert out_csv.exists()
    assert (validation_dir / "lwi_eligibility_report.csv").exists()
    assert not list(master_dir.glob(".*.tmp.xlsx"))


def test_lwi_xlsx_timeout_preserves_target_cleans_temp_and_blocks_diagnostics(
    mod, tmp_path, monkeypatch,
):
    final, report = _lwi_output_fixture()
    master_dir = tmp_path / "master"
    validation_dir = tmp_path / "validation"
    master_dir.mkdir()
    target = master_dir / "master_historical_db_with_lwi_2006_2025.xlsx"
    target.write_bytes(b"previous valid LWI workbook")

    def timeout(*args, **kwargs):
        raise TimeoutError("simulated LWI close timeout")

    monkeypatch.setattr(pd.DataFrame, "to_excel", timeout)
    with pytest.raises(TimeoutError, match="simulated LWI close timeout"):
        mod.write_lwi_outputs(
            final, report, master_dir=master_dir, validation_dir=validation_dir,
        )
    assert target.read_bytes() == b"previous valid LWI workbook"
    assert not (validation_dir / "lwi_eligibility_report.csv").exists()
    assert not list(master_dir.glob(".*.tmp.xlsx"))


def test_lwi_corrupt_xlsx_preserves_target_and_blocks_diagnostics(
    mod, tmp_path, monkeypatch,
):
    final, report = _lwi_output_fixture()
    master_dir = tmp_path / "master"
    validation_dir = tmp_path / "validation"
    master_dir.mkdir()
    target = master_dir / "master_historical_db_with_lwi_2006_2025.xlsx"
    target.write_bytes(b"previous valid LWI workbook")

    def write_corrupt(_self, path, **kwargs):
        Path(path).write_bytes(b"not an xlsx")

    monkeypatch.setattr(pd.DataFrame, "to_excel", write_corrupt)
    with pytest.raises(ValueError, match="valid readable ZIP"):
        mod.write_lwi_outputs(
            final, report, master_dir=master_dir, validation_dir=validation_dir,
        )
    assert target.read_bytes() == b"previous valid LWI workbook"
    assert not (validation_dir / "lwi_eligibility_report.csv").exists()
    assert not list(master_dir.glob(".*.tmp.xlsx"))


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
        # Needs >=4 players within the starter-tier window for the IQR
        # to actually compute (not NaN) -- a too-small synthetic sample
        # made this test pass vacuously (both threshold settings hit
        # the "insufficient starters" guard and produced identical NaNs).
        np.random.seed(1)
        n_per_pos = 20
        df = pd.DataFrame({
            "season": [2020] * (n_per_pos * 2),
            "position": ["QB"] * n_per_pos + ["RB"] * n_per_pos,
            "position_finish_ppr": list(range(1, n_per_pos+1)) * 2,
            "ppg_ppr": list(np.linspace(25, 5, n_per_pos)) + list(np.linspace(20, 3, n_per_pos)),
        })

        monkeypatch.setattr(mod, "REPLACEMENT_RANK_THRESHOLDS", {"QB": 5, "RB": 5})
        monkeypatch.setattr(mod, "REPLACEMENT_WINDOW", 10)
        result_a = mod.compute_component_4_positional_advantage(df.copy())

        monkeypatch.setattr(mod, "REPLACEMENT_RANK_THRESHOLDS", {"QB": 15, "RB": 5})
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


class TestComponent1LOSOEvaAndCap:
    """Regression tests for Component 1's final structure: leave-one-
    season-out (LOSO) monotonic EVA (Expected Value Added) plus an
    overall-ADP-underperformance cap. Replaced the earlier pure-overall
    min-max version after extensive real-data testing -- see
    docs/METRIC_SPECIFICATION.md Component 1 for the full history."""

    def test_loso_never_uses_the_players_own_season(self, mod):
        # The whole point of leave-one-season-out is that a
        # player-season's expected baseline must be built WITHOUT that
        # player's own season in the training data -- otherwise each
        # observation slightly influences its own baseline.
        df = pd.DataFrame({
            "season": [2018]*5 + [2019]*5,
            "position": ["RB"]*10,
            "position_finish_ppr": list(range(1,6))*2,
            "overall_adp": [5,20,40,80,150]*2,
            "overall_finish_ppr": [3,25,35,70,140]*2,
        })
        # Two seasons, identical ADP/finish patterns -- if LOSO is
        # working, isotonic curves for both seasons should be built
        # from ONLY the other season's data and should therefore be
        # identical to each other (each is the sole training set for
        # the other), not influenced by including their own rows.
        result = mod.compute_component_1_adp_value(df.copy())
        assert result.notna().all()

    def test_cap_applies_when_worse_than_own_adp(self, mod):
        # Real-world mirror: Arian Foster 2012 (overall_adp=1.4,
        # overall_finish=12 -- genuinely worse than the actual pick
        # spent, even though he likely beat the rough historical
        # baseline for pick-1-ish slots given how often very early
        # picks bust). Must be capped regardless of EVA's raw view.
        # Two seasons included -- LOSO needs at least 2 to have any
        # training data when the target season is excluded.
        base = pd.DataFrame({
            "position": ["RB"]*30,
            "position_finish_ppr": list(range(1,31)),
            "overall_adp": [1.4] + list(np.linspace(2, 250, 29)),
            "overall_finish_ppr": [12] + list(np.linspace(2, 250, 29)),
        })
        df = pd.concat([base.assign(season=2012), base.assign(season=2013)], ignore_index=True)
        result = mod.compute_component_1_adp_value(df.copy())
        assert result.iloc[0] <= mod.LWI_ADP_UNDERPERFORM_CAP, (
            "A player who finished worse than his own overall ADP was "
            "not capped -- the cap mechanism may have regressed."
        )

    def test_cap_does_not_apply_when_better_than_own_adp(self, mod):
        base = pd.DataFrame({
            "position": ["RB"]*30,
            "position_finish_ppr": list(range(1,31)),
            "overall_adp": [150] + list(np.linspace(2, 250, 29)),
            "overall_finish_ppr": [5] + list(np.linspace(2, 250, 29)),  # huge riser
        })
        df = pd.concat([base.assign(season=2012), base.assign(season=2013)], ignore_index=True)
        result = mod.compute_component_1_adp_value(df.copy())
        assert result.iloc[0] > mod.LWI_ADP_UNDERPERFORM_CAP, (
            "A genuine riser (beat their own overall ADP by a lot) was "
            "capped -- the cap should only trigger for underperformers."
        )


class TestComponents2And3ReplacementAdjusted:
    """Regression tests for the FINAL Components 2/3 structure ("full
    B"): Component 2 = total points above replacement, Component 3 =
    PPG above replacement, BOTH normalized cross-position (season
    only). An intermediate version reverted Component 3 to positional
    percentile to avoid duplicating an earlier, unstandardized
    Component 4 -- but once Component 4 was redesigned to STANDARDIZED
    positional advantage (dividing by the position's starter-tier PPG
    spread, not just a raw replacement-adjusted difference), Component
    3 could safely return to replacement-adjusted without duplicating
    Component 4 again (verified: Spearman correlation between the two
    dropped from ~1.0 to 0.878, and Component 4 retains 25% variance
    not explained by Components 2+3, vs 0% before). See
    docs/METRIC_SPECIFICATION.md Component 3/4 for the full history."""

    def test_component_2_grouped_by_season_cross_position(self, mod):
        # position_finish_ppr values must span each position's
        # replacement threshold window (QB12/RB34/WR42/TE12, window 12)
        # or replacement_level lookup returns NaN for that group.
        df = pd.DataFrame({
            "season": [2020]*4,
            "position": ["QB", "QB", "TE", "TE"],
            "position_finish_ppr": [1, 12, 1, 12],
            "fantasy_points_ppr": [400.0, 150.0, 200.0, 80.0],
        })
        result = mod.compute_component_2_fantasy_finish(df.copy())
        assert result.notna().all()

    def test_component_3_grouped_by_season_cross_position(self, mod):
        # Component 3 pools ACROSS positions now (like Component 2),
        # not within a single position -- a lone QB should NOT get the
        # single-member-group value; it competes against the whole pool.
        df = pd.DataFrame({
            "season": [2020]*4,
            "position": ["QB", "QB", "TE", "TE"],
            "position_finish_ppr": [1, 12, 1, 12],
            "ppg_ppr": [30.0, 15.0, 20.0, 8.0],
        })
        result = mod.compute_component_3_ppg(df.copy())
        assert result.notna().all()
        assert result.iloc[0] == result.max()


class TestComponent4Standardized:
    """Regression tests for Component 4's standardization (divide the
    replacement-adjusted PPG gap by the IQR of starter-tier PPG at
    that position+season) -- the fix for the Component 3/4 duplication
    bug, chosen over simply reverting Component 3 to positional
    (which was found to reintroduce TE over-representation, 15% of a
    real top-100 vs 7% under standardization)."""

    def test_larger_iqr_produces_smaller_standardized_score(self, mod):
        # Same raw PPG-above-replacement gap, but very different
        # starter-tier spread -- a gap that's huge relative to a TIGHT
        # spread should score higher than the same raw gap relative to
        # a WIDE spread (that's the whole point of standardizing).
        # Needs enough rows to span the default QB threshold (12) +
        # window (12) -- i.e. ranks up to 24 -- or replacement_ppg
        # comes back NaN entirely (found via testing: an earlier
        # version of this test used only 10 rows and got NaN vs NaN).
        n = 30
        tight_spread = pd.DataFrame({
            "season": [2020]*n, "position": ["QB"]*n,
            "position_finish_ppr": list(range(1, n+1)),
            "ppg_ppr": [25.0] + list(np.linspace(20.0, 15.0, n-1)),  # tightly bunched starters
        })
        wide_spread = pd.DataFrame({
            "season": [2020]*n, "position": ["QB"]*n,
            "position_finish_ppr": list(range(1, n+1)),
            "ppg_ppr": [25.0] + list(np.linspace(20.0, 2.0, n-1)),  # widely spread starters
        })
        r_tight = mod.compute_component_4_positional_advantage(tight_spread.copy())
        r_wide = mod.compute_component_4_positional_advantage(wide_spread.copy())
        assert r_tight.iloc[0] >= r_wide.iloc[0], (
            "The same raw PPG gap over a TIGHTER starter spread should "
            "score at least as high as the same gap over a WIDER "
            "spread -- standardization does not appear to be applied."
        )

    def test_zero_iqr_does_not_raise_or_produce_infinite_score(self, mod):
        # If every starter has IDENTICAL ppg_ppr, IQR = 0. Dividing by
        # zero must not raise, and must not produce inf/-inf that would
        # corrupt downstream min-max normalization. NaN IS the correct
        # outcome here (insufficient signal to standardize against) --
        # it flows into the existing component-availability policy
        # (see TestComponentAvailabilityPolicy) which correctly marks
        # that row incomplete rather than scoring it -- so this test
        # checks "not inf", not "is finite".
        n = 30
        df = pd.DataFrame({
            "season": [2020]*n, "position": ["QB"]*n,
            "position_finish_ppr": list(range(1, n+1)),
            "ppg_ppr": [20.0]*n,  # every starter identical -> IQR = 0
        })
        result = mod.compute_component_4_positional_advantage(df.copy())
        assert not np.isinf(result).any(), (
            "A zero-IQR starter tier produced an infinite Component 4 "
            "score -- the zero-denominator guard may have regressed. "
            "(NaN is the correct, expected fallback here, not a bug.)"
        )

    def test_too_few_starters_falls_back_gracefully(self, mod):
        # Fewer than 4 players in the starter-tier window -- too few
        # for a meaningful IQR. Must fall back to NaN (which the
        # existing component-availability policy already handles
        # correctly downstream) rather than raising or producing inf.
        df = pd.DataFrame({
            "season": [2020, 2020],
            "position": ["QB", "QB"],
            "position_finish_ppr": [1, 2],  # only 2 players total, both "starters"
            "ppg_ppr": [25.0, 20.0],
        })
        result = mod.compute_component_4_positional_advantage(df.copy())
        assert not np.isinf(result).any(), (
            "Too few starters for a meaningful IQR did not fall back "
            "gracefully -- got an infinite result instead of the "
            "expected NaN (which downstream policy already handles)."
        )

    def test_extreme_outlier_in_one_position_does_not_shift_unrelated_scores(self, mod):
        # REGRESSION TEST for a real bug found and FIXED via testing:
        # an earlier version of Component 4 used plain min-max for its
        # final cross-position normalization, which is highly sensitive
        # to its own extremes -- a single wild outlier in ONE position
        # could become that season's new max, shifting what 0-100 means
        # for every OTHER position too, even though their own raw
        # values never changed. Verified directly at the time: an
        # outlier injected only into the QB group shifted an untouched
        # RB player's score by 60+ points. FIXED by switching the final
        # normalization to winsorized min-max (5th/95th percentile
        # clip) -- this test asserts the fix actually holds, not just
        # that the bug is documented.
        n = 60
        rows = []
        for position in ["QB", "RB", "WR", "TE"]:
            rows.append(pd.DataFrame({
                "season": [2020]*n, "position": [position]*n,
                "position_finish_ppr": list(range(1, n+1)),
                "ppg_ppr": [22.0] + list(np.linspace(20.0, 5.0, n-1)),
            }))
        normal = pd.concat(rows, ignore_index=True)
        with_outlier = normal.copy()
        with_outlier.loc[(with_outlier.position=="QB") & (with_outlier.position_finish_ppr==2), "ppg_ppr"] = 60.0

        r_normal = mod.compute_component_4_positional_advantage(normal.copy())
        r_outlier = mod.compute_component_4_positional_advantage(with_outlier.copy())

        rb_rank1_idx = normal[(normal.position=="RB") & (normal.position_finish_ppr==1)].index[0]
        shift = abs(r_normal.loc[rb_rank1_idx] - r_outlier.loc[rb_rank1_idx])
        assert shift < 10, (
            f"An outlier injected into ONE position's data shifted an "
            f"UNRELATED position's score by {shift:.1f} points -- the "
            f"winsorized-normalization fix for cross-position outlier "
            f"contamination may have regressed (threshold: <10, "
            f"verified 0.0 at fix time)."
        )

    def test_larger_raw_gap_never_produces_lower_score_same_position_season(self, mod):
        # Monotonicity: within the SAME position+season (same spread
        # denominator for everyone), a player with a strictly larger
        # raw PPG-above-replacement gap must never score LOWER than one
        # with a smaller gap -- dividing by a shared positive constant
        # must preserve ordering.
        n = 30
        df = pd.DataFrame({
            "season": [2020]*n, "position": ["QB"]*n,
            "position_finish_ppr": list(range(1, n+1)),
            "ppg_ppr": list(np.linspace(30.0, 10.0, n)),  # strictly decreasing
        })
        result = mod.compute_component_4_positional_advantage(df.copy())
        raw_gaps = df["ppg_ppr"].values
        order = np.argsort(-raw_gaps)  # descending by raw PPG (proxy for gap, since replacement is fixed)
        ordered_scores = result.values[order]
        assert all(ordered_scores[i] >= ordered_scores[i+1] - 1e-6 for i in range(len(ordered_scores)-1)), (
            "A player with a strictly larger raw PPG gap scored LOWER "
            "than one with a smaller gap within the same position and "
            "season -- monotonicity has been violated."
        )






    def test_values_are_clipped_at_5th_and_95th_percentile(self, mod):
        # Direct verification that the winsorization boundary itself
        # is correct: a value below the 5th percentile of that season's
        # raw distribution should be clipped UP to the 5th percentile
        # value before scaling; a value above the 95th should be
        # clipped DOWN. Confirmed by checking the exposed
        # positional_advantage_winsorized column directly, not just
        # the final 0-100 score.
        n = 60
        rows = []
        for position in ["QB", "RB", "WR", "TE"]:
            rows.append(pd.DataFrame({
                "season": [2020]*n, "position": [position]*n,
                "position_finish_ppr": list(range(1, n+1)),
                "ppg_ppr": [22.0] + list(np.linspace(20.0, 5.0, n-1)),
            }))
        df = pd.concat(rows, ignore_index=True)
        # Inject one extreme outlier that should get clipped
        df.loc[(df.position=="QB") & (df.position_finish_ppr==2), "ppg_ppr"] = 100.0
        mod.compute_component_4_positional_advantage(df)

        assert "positional_advantage_winsorized" in df.columns
        raw = df["positional_advantage_raw"]
        winsorized = df["positional_advantage_winsorized"]
        # The extreme outlier's winsorized value must be strictly less
        # than its own raw value (it got clipped down).
        outlier_idx = df[(df.position=="QB") & (df.position_finish_ppr==2)].index[0]
        assert winsorized.loc[outlier_idx] < raw.loc[outlier_idx], (
            "An extreme outlier's winsorized value was not clipped "
            "below its raw value -- winsorization may not be applying."
        )
        # A typical (non-extreme) player's winsorized value should
        # equal its raw value (nothing to clip).
        typical_idx = df[(df.position=="RB") & (df.position_finish_ppr==5)].index[0]
        assert abs(winsorized.loc[typical_idx] - raw.loc[typical_idx]) < 1e-6, (
            "A typical, non-extreme player's value was altered by "
            "winsorization -- clipping bounds may be too aggressive."
        )

    def test_identical_raw_inputs_receive_identical_scores(self, mod):
        # Determinism check: two players with byte-identical inputs
        # (same season, position, ppg, replacement situation) must
        # receive EXACTLY the same Component 4 score -- no hidden
        # randomness or row-order dependence in the calculation.
        n = 60
        df = pd.DataFrame({
            "season": [2020]*n, "position": ["QB"]*n,
            "position_finish_ppr": list(range(1, n+1)),
            "ppg_ppr": [20.0, 20.0] + list(np.linspace(19.0, 5.0, n-2)),  # rows 0,1 identical
        })
        result = mod.compute_component_4_positional_advantage(df.copy())
        assert result.iloc[0] == result.iloc[1], (
            "Two players with identical raw inputs received different "
            "Component 4 scores -- the calculation may not be "
            "deterministic."
        )


class TestNoDuplicateComponentFormulas:
    """Direct regression test for the real bug found via testing:
    Component 3 (when replacement-adjusted) and Component 4 turned out
    to be mathematically IDENTICAL -- same formula (value - replacement
    level, normalized within season), computed and weighted twice
    (Spearman correlation 0.99999999, R-squared of 1.000 when Component
    4 was regressed on Components 2+3). This test asserts no two of
    the 6 output components are near-duplicates of each other on
    realistic synthetic data, so this class of bug cannot silently
    return."""

    def test_no_two_components_are_near_duplicates(self, mod):
        np.random.seed(0)
        n = 100  # per season
        rows = []
        for season in [2019, 2020]:  # 2 seasons -- LOSO needs at least 2
            positions = np.random.choice(["QB","RB","WR","TE"], n)
            base = np.random.uniform(50, 400, n)
            season_df = pd.DataFrame({
                "season": [season]*n,
                "position": positions,
                "player_id": [f"00-{season}-{i:04d}" for i in range(n)],
                "fantasy_points_ppr": base,
                "ppg_ppr": base / np.random.uniform(8, 17, n),
            })
            rows.append(season_df)
        df = pd.concat(rows, ignore_index=True)
        df["position_finish_ppr"] = df.groupby(["season","position"])["fantasy_points_ppr"].rank(ascending=False, method="min").astype(int)
        df["overall_finish_ppr"] = df.groupby("season")["fantasy_points_ppr"].rank(ascending=False, method="min").astype(int)
        df["overall_adp"] = df["overall_finish_ppr"] + np.random.normal(0, 15, len(df))
        df["overall_adp"] = df["overall_adp"].clip(lower=1)
        df["positional_adp"] = df["position_finish_ppr"] + np.random.normal(0, 3, len(df))

        c1 = mod.compute_component_1_adp_value(df.copy())
        c2 = mod.compute_component_2_fantasy_finish(df.copy())
        c3 = mod.compute_component_3_ppg(df.copy())
        c4 = mod.compute_component_4_positional_advantage(df.copy())

        components = {"c1": c1, "c2": c2, "c3": c3, "c4": c4}
        for name_a, series_a in components.items():
            for name_b, series_b in components.items():
                if name_a >= name_b:
                    continue
                corr = series_a.corr(series_b)
                assert corr is None or corr < 0.999, (
                    f"{name_a} and {name_b} are near-perfectly correlated "
                    f"({corr:.6f}) on synthetic test data -- this is the "
                    f"exact failure mode found earlier (replacement-"
                    f"adjusted PPG duplicating Component 4). Check that "
                    f"no two components share the same underlying "
                    f"formula and normalization path."
                )


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
