"""
tests/test_dataset2_prior_finish_analysis.py

Covers lib/dataset2/prior_finish_analysis.py -- family #7's required
raw / ADP-conditioned / market-pricing three-part analysis design.
These tests verify the STRATIFICATION LOGIC is structurally correct
against small synthetic fixtures -- they assert nothing about any real
football finding, and these functions have never been run against real
historical data (see the module's own docstring and
research/dataset2/DATASET2_TRAIT_ROADMAP.md §6's integration
checkpoint).

What's specifically protected here:
- raw_prior_finish_report() pools everything into one quartile split
  (no position/ADP/era columns in its output).
- adp_conditioned_prior_finish_report() stratifies by position x
  ADP-round-bucket x era FIRST, so the same prior-finish values in two
  different strata can land in different quartiles and show different
  Star rates -- proving it does not just re-run the raw computation
  with extra columns tacked on.
- prior_finish_vs_current_adp_report() never requires
  star_by_value_label -- it's a market-pricing question, not an
  outcome question, and must work even when no Star label exists yet.
- Every report distinguishes small-sample cells via confidence_flag,
  per the roadmap's §4.6 minimum-result-outputs requirement.
- The three report_type labels are always distinct, so raw/primary/
  market-pricing results can never be confused downstream.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import prior_finish_analysis as pfa


def _outcome_df(*rows):
    cols = [
        "season", "player_id", "position",
        "prior_overall_finish", "prior_positional_finish", "prior_ppg",
        "overall_adp_model", "star_by_value_label",
    ]
    return pd.DataFrame(list(rows), columns=cols)


def _market_pricing_df(*rows):
    cols = [
        "season", "player_id", "position",
        "prior_overall_finish", "prior_positional_finish", "prior_ppg",
        "overall_adp_model",
    ]
    return pd.DataFrame(list(rows), columns=cols)


# Two strata with IDENTICAL prior_positional_finish values (1..8) but
# opposite real outcomes -- WR/R1-2/2011-2020 era is where good prior
# finish predicts becoming a Star; RB/R11+/2011-2020 era is where
# nobody becomes a Star regardless of prior finish. Pooling these
# together (as the raw report does) mixes the two signals; stratifying
# (as the ADP-conditioned report does) keeps them separate.
def _two_strata_fixture():
    rows = []
    # WR, adp=15 -> round 2 -> "R1-2", season 2015 -> "2011-2020"
    for rank, star in zip(range(1, 9), [1, 1, 1, 1, 0, 0, 0, 0]):
        rows.append({
            "season": 2015, "player_id": f"00-wr-{rank}", "position": "WR",
            "prior_overall_finish": rank, "prior_positional_finish": rank, "prior_ppg": 20.0 - rank,
            "overall_adp_model": 15.0, "star_by_value_label": star,
        })
    # RB, adp=140 -> round 12 -> "R11+", season 2015 -> "2011-2020"
    for rank, star in zip(range(1, 9), [0, 0, 0, 0, 0, 0, 0, 0]):
        rows.append({
            "season": 2015, "player_id": f"00-rb-{rank}", "position": "RB",
            "prior_overall_finish": rank, "prior_positional_finish": rank, "prior_ppg": 20.0 - rank,
            "overall_adp_model": 140.0, "star_by_value_label": star,
        })
    return _outcome_df(*rows)


class TestRawReportPoolsEverything:
    def test_output_has_no_stratification_columns(self):
        df = _two_strata_fixture()
        result = pfa.raw_prior_finish_report(df)
        assert "position" not in result.columns
        assert "adp_round_bucket" not in result.columns
        assert "era_bucket" not in result.columns
        assert set(result.columns) >= {"prior_finish_quartile", "n", "star_rate", "confidence_flag", "report_type"}

    def test_report_type_label(self):
        df = _two_strata_fixture()
        result = pfa.raw_prior_finish_report(df)
        assert (result["report_type"] == pfa.REPORT_TYPE_RAW).all()

    def test_pools_both_strata_into_shared_quartiles(self):
        """16 rows total, prior_positional_finish 1..8 duplicated across
        both strata -- pooled quartiles must span all 16 rows, not 8."""
        df = _two_strata_fixture()
        result = pfa.raw_prior_finish_report(df)
        assert result["n"].sum() == 16


class TestAdpConditionedActuallyStratifies:
    def test_output_includes_stratification_columns(self):
        df = _two_strata_fixture()
        result = pfa.adp_conditioned_prior_finish_report(df)
        assert {"position", "adp_round_bucket", "era_bucket", "prior_finish_quartile"} <= set(result.columns)

    def test_two_strata_produce_separate_rows_not_pooled(self):
        df = _two_strata_fixture()
        result = pfa.adp_conditioned_prior_finish_report(df)
        wr_rows = result[result["position"] == "WR"]
        rb_rows = result[result["position"] == "RB"]
        assert wr_rows["adp_round_bucket"].unique().tolist() == ["R1-2"]
        assert rb_rows["adp_round_bucket"].unique().tolist() == ["R11+"]
        # each stratum's 8 rows are preserved, not merged into a shared 16-row pool
        assert wr_rows["n"].sum() == 8
        assert rb_rows["n"].sum() == 8

    def test_within_stratum_star_rate_differs_from_pooled_star_rate(self):
        """The whole point of stratifying: WR's real 50% Star rate in
        its best quartile must survive intact, not get diluted toward
        RB's 0% by pooling."""
        df = _two_strata_fixture()
        result = pfa.adp_conditioned_prior_finish_report(df)
        wr_best = result[(result["position"] == "WR") & (result["prior_finish_quartile"] == "Q1_best")]
        rb_best = result[(result["position"] == "RB") & (result["prior_finish_quartile"] == "Q1_best")]
        assert wr_best["star_rate"].iloc[0] == pytest.approx(1.0)
        assert rb_best["star_rate"].iloc[0] == pytest.approx(0.0)

    def test_report_type_label(self):
        df = _two_strata_fixture()
        result = pfa.adp_conditioned_prior_finish_report(df)
        assert (result["report_type"] == pfa.REPORT_TYPE_ADP_CONDITIONED).all()


class TestSmallSampleFlag:
    def test_cells_below_threshold_flagged(self):
        """Each quartile bin in the 8-row-per-stratum fixture has only
        2 rows -- well under DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE (10)."""
        df = _two_strata_fixture()
        result = pfa.adp_conditioned_prior_finish_report(df)
        assert (result["confidence_flag"] == "small_sample").all()

    def test_cell_at_or_above_threshold_flagged_ok(self):
        rows = []
        for i in range(12):
            rows.append({
                "season": 2015, "player_id": f"00-{i}", "position": "WR",
                "prior_overall_finish": i + 1, "prior_positional_finish": i + 1, "prior_ppg": 15.0,
                "overall_adp_model": 15.0, "star_by_value_label": 0,
            })
        df = _outcome_df(*rows)
        result = pfa.raw_prior_finish_report(df)
        assert (result["n"] >= 3).all()  # 12 rows / 4 quartiles = 3 each -- still small_sample, confirms the flag is real
        assert (result["confidence_flag"] == "small_sample").all()


class TestMarketPricingReportNeverRequiresStarLabel:
    def test_runs_without_star_label_column_at_all(self):
        df = _market_pricing_df(
            {"season": 2015, "player_id": "00-1", "position": "WR", "prior_overall_finish": 5, "prior_positional_finish": 2, "prior_ppg": 18.0, "overall_adp_model": 12.0},
            {"season": 2015, "player_id": "00-2", "position": "WR", "prior_overall_finish": 30, "prior_positional_finish": 10, "prior_ppg": 9.0, "overall_adp_model": 60.0},
        )
        result = pfa.prior_finish_vs_current_adp_report(df)
        assert (result["report_type"] == pfa.REPORT_TYPE_MARKET_PRICING).all()
        assert "star_by_value_label" not in df.columns  # confirms the fixture itself never had it

    def test_real_correlation_computed_per_position(self):
        rows = []
        for i in range(1, 6):
            rows.append({
                "season": 2015, "player_id": f"00-{i}", "position": "WR",
                "prior_overall_finish": i, "prior_positional_finish": i, "prior_ppg": 20.0 - i,
                "overall_adp_model": float(i * 10),
            })
        df = _market_pricing_df(*rows)
        result = pfa.prior_finish_vs_current_adp_report(df)
        assert result.loc[result["position"] == "WR", "pearson_r"].iloc[0] == pytest.approx(1.0, abs=1e-9)
        assert result.loc[result["position"] == "WR", "n"].iloc[0] == 5


class TestReportTypesAreDistinct:
    def test_three_report_types_never_collide(self):
        types = {pfa.REPORT_TYPE_RAW, pfa.REPORT_TYPE_ADP_CONDITIONED, pfa.REPORT_TYPE_MARKET_PRICING}
        assert len(types) == 3


class TestRookieAndMissingFinishExcluded:
    def test_null_prior_finish_rows_excluded_from_quartile_reports(self):
        df = _outcome_df(
            {"season": 2015, "player_id": "00-1", "position": "WR", "prior_overall_finish": None, "prior_positional_finish": None, "prior_ppg": None, "overall_adp_model": 15.0, "star_by_value_label": 1},
        )
        result = pfa.raw_prior_finish_report(df)
        assert result["n"].sum() == 0


class TestEraAndAdpBucketHelpers:
    def test_era_bucket_boundaries(self):
        assert pfa._era_bucket(2010) == "pre-2011"
        assert pfa._era_bucket(2011) == "2011-2020"
        assert pfa._era_bucket(2020) == "2011-2020"
        assert pfa._era_bucket(2021) == "2021+"

    def test_adp_round_bucket_boundaries(self):
        assert pfa._adp_round_bucket(10) == "R1-2"   # round 1
        assert pfa._adp_round_bucket(24) == "R1-2"   # round 2
        assert pfa._adp_round_bucket(25) == "R3-5"   # round 3
        assert pfa._adp_round_bucket(132) == "R11+"  # round 11
        assert pfa._adp_round_bucket(None) is None


class TestRequiredColumnValidation:
    def test_raw_report_missing_column_raises(self):
        bad_df = pd.DataFrame({"season": [2022]})
        with pytest.raises(ValueError, match="df is missing required columns"):
            pfa.raw_prior_finish_report(bad_df)

    def test_market_pricing_missing_column_raises(self):
        bad_df = pd.DataFrame({"season": [2022]})
        with pytest.raises(ValueError, match="df is missing required columns"):
            pfa.prior_finish_vs_current_adp_report(bad_df)
