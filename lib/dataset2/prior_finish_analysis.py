"""
lib/dataset2/prior_finish_analysis.py

Family #7's three-part analysis design, approved 2026-07
(research/dataset2/DATASET2_TRAIT_ROADMAP.md §6) -- kept structurally
separate from lib/dataset2/prior_finish_traits.py's feature
construction. Consumes that module's output plus current-season ADP
and the Star label; produces no conclusions on its own, only
structured, reproducible reports for a human to interpret.

Three functions, deliberately not one, so raw description, the
primary conditioned result, and the market-pricing hypothesis can
never be confused with each other -- each output carries its own
`report_type` label:

1. raw_prior_finish_report() -- DESCRIPTIVE ONLY. Star rate by
   prior-finish quartile, pooled across all position/ADP/era. Reported
   for completeness; never the primary finding.
2. adp_conditioned_prior_finish_report() -- PRIMARY RESULT. Stratifies
   by position x current-ADP-round-bucket x era FIRST, then computes
   the prior-finish quartile and Star rate WITHIN each stratum. Tests
   whether prior finish adds information among comparable players, not
   whether prior success correlates with future success in general
   (which current ADP likely already explains on its own).
3. prior_finish_vs_current_adp_report() -- the SEPARATE market-pricing
   hypothesis: does current-season ADP already price in prior finish
   (a question about the market, not about the Star/bust outcome).
   Never folded into #2.

Each accepts a `finish_col` parameter (defaults to
"prior_positional_finish") so prior overall finish, prior positional
finish, and prior PPG can each be tested independently, per the
approved instruction to test whether each adds information on its
own -- this module does not privilege one over the others.

CONFIDENCE: every stratified cell reports `n` and a `confidence_flag`
("small_sample" below config.DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE,
else "ok") per the roadmap's §4.6 minimum-result-outputs requirement --
a rate is never reported without its sample size alongside it.

KNOWN LIMITATION, disclosed not silently absorbed: quartile binning
uses pandas' qcut with duplicates="drop", so a stratum with heavily
tied prior-finish values can collapse to fewer than 4 real bins. This
means bin COUNT is not guaranteed uniform across every stratum --
acceptable for this first implementation, but worth knowing before
comparing bin-to-bin across strata.

TEST SCOPE: tests/test_dataset2_prior_finish_analysis.py proves the
STRATIFICATION LOGIC is structurally correct against small synthetic
fixtures (the ADP-conditioned function actually stratifies rather than
pooling; small cells are flagged; the three functions are genuinely
separate code paths). These functions have NOT been run against real
historical data -- that is a required, separate step, same as every
other Dataset 2 module's integration checkpoint
(research/dataset2/DATASET2_TRAIT_ROADMAP.md §6). No empirical
finding about prior finish is asserted anywhere in this module or its
tests.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import DATASET2_ADP_ROUND_BUCKETS, DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE, DATASET2_ERA_BOUNDARIES, TEAMS
from lib.dataset2.common import validate_columns

STAR_LABEL_REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "position",
    "prior_overall_finish",
    "prior_positional_finish",
    "prior_ppg",
    "overall_adp_model",
    "star_by_value_label",
)

MARKET_PRICING_REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "position",
    "prior_overall_finish",
    "prior_positional_finish",
    "prior_ppg",
    "overall_adp_model",
)

REPORT_TYPE_RAW = "raw_descriptive"
REPORT_TYPE_ADP_CONDITIONED = "adp_conditioned_primary"
REPORT_TYPE_MARKET_PRICING = "market_pricing_hypothesis"


def _era_bucket(season) -> str:
    """pre-{lo} / {lo}-{hi-1} / {hi}+, from config.DATASET2_ERA_BOUNDARIES
    -- see that constant's own comment for its status (initial default,
    not finalized)."""
    lo, hi = DATASET2_ERA_BOUNDARIES
    if pd.isna(season):
        return None
    if season < lo:
        return f"pre-{lo}"
    if season < hi:
        return f"{lo}-{hi - 1}"
    return f"{hi}+"


def _adp_round_bucket(adp) -> str:
    """Maps a current-season ADP value to one of
    config.DATASET2_ADP_ROUND_BUCKETS via adp_round = ceil(adp/TEAMS).
    None if adp is null or falls outside every configured bucket
    (should not happen given R11+ is unbounded above, but a positive
    adp is still required)."""
    if pd.isna(adp) or adp <= 0:
        return None
    rnd = int(np.ceil(adp / TEAMS))
    for label, lo, hi in DATASET2_ADP_ROUND_BUCKETS:
        if hi is None:
            if rnd >= lo:
                return label
        elif lo <= rnd <= hi:
            return label
    return None


def _prior_finish_quartile(series: pd.Series) -> pd.Series:
    """Rank-based quartile of `series` (Q1_best = lowest/best finish
    number ... Q4_worst = highest/worst), computed over exactly the
    values passed in -- the caller controls what population the
    quartile is relative to (pooled for the raw report, within-stratum
    for the ADP-conditioned report). Fewer than 4 non-null values in
    `series` cannot support a real quartile split -- returns all-NaN
    rather than a degenerate bin."""
    valid = series.dropna()
    if len(valid) < 4:
        return pd.Series(np.nan, index=series.index)
    return pd.qcut(series, 4, labels=["Q1_best", "Q2", "Q3", "Q4_worst"], duplicates="drop")


def _summarize(df: pd.DataFrame, group_cols) -> pd.DataFrame:
    """Sample size / Star rate per group, plus a confidence flag --
    the minimum-result-outputs fields required by
    research/dataset2/DATASET2_TRAIT_ROADMAP.md §4.6. Never reports a
    rate without n alongside it."""
    grouped = df.groupby(group_cols, observed=True)["star_by_value_label"]
    out = grouped.agg(n="count", star_rate="mean").reset_index()
    out["confidence_flag"] = np.where(out["n"] < DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE, "small_sample", "ok")
    return out


def raw_prior_finish_report(df: pd.DataFrame, finish_col: str = "prior_positional_finish") -> pd.DataFrame:
    """DESCRIPTIVE ONLY -- unconditioned Star rate by prior-finish
    quartile, pooled across all position/ADP/era. Per the approved
    decision, report for completeness; never treat this as the primary
    finding (see adp_conditioned_prior_finish_report() for that).
    Rows with a null `finish_col` (rookies, or genuinely missing data)
    are excluded from the quartile computation -- they have no
    prior-finish value to bucket, not a value being discarded."""
    validate_columns(df, STAR_LABEL_REQUIRED_COLUMNS, "df")
    working = df.copy()
    working["prior_finish_quartile"] = _prior_finish_quartile(working[finish_col])
    working = working.dropna(subset=["prior_finish_quartile"])
    result = _summarize(working, ["prior_finish_quartile"])
    result["report_type"] = REPORT_TYPE_RAW
    return result


def adp_conditioned_prior_finish_report(df: pd.DataFrame, finish_col: str = "prior_positional_finish") -> pd.DataFrame:
    """PRIMARY RESULT. Stratifies by position x current-ADP-round-bucket
    x era FIRST, then computes the prior-finish quartile and Star rate
    WITHIN each stratum -- this within-stratum quartile computation is
    the structural difference from raw_prior_finish_report()'s pooled
    quartile, verified by
    tests/test_dataset2_prior_finish_analysis.py's
    TestAdpConditionedActuallyStratifies."""
    validate_columns(df, STAR_LABEL_REQUIRED_COLUMNS, "df")
    working = df.copy()
    working["adp_round_bucket"] = working["overall_adp_model"].apply(_adp_round_bucket)
    working["era_bucket"] = working["season"].apply(_era_bucket)
    working = working.dropna(subset=["adp_round_bucket", "era_bucket"])

    working["prior_finish_quartile"] = working.groupby(
        ["position", "adp_round_bucket", "era_bucket"], observed=True
    )[finish_col].transform(_prior_finish_quartile)
    working = working.dropna(subset=["prior_finish_quartile"])

    result = _summarize(working, ["position", "adp_round_bucket", "era_bucket", "prior_finish_quartile"])
    result["report_type"] = REPORT_TYPE_ADP_CONDITIONED
    return result


def prior_finish_vs_current_adp_report(df: pd.DataFrame, finish_col: str = "prior_positional_finish") -> pd.DataFrame:
    """The SEPARATE market-pricing hypothesis: does current-season ADP
    already reflect prior finish. Tested directly as a per-position
    correlation (ADP scale differs by position) -- deliberately does
    NOT read or require star_by_value_label, since this question is
    about the market's pricing behavior, not about the Star/bust
    outcome (never folded into adp_conditioned_prior_finish_report())."""
    validate_columns(df, MARKET_PRICING_REQUIRED_COLUMNS, "df")
    rows = []
    for position, g in df.groupby("position", observed=True):
        valid = g.dropna(subset=[finish_col, "overall_adp_model"])
        if len(valid) < 2:
            rows.append(
                {"position": position, "n": len(valid), "pearson_r": np.nan, "confidence_flag": "small_sample"}
            )
            continue
        r = valid[finish_col].corr(valid["overall_adp_model"], method="pearson")
        rows.append(
            {
                "position": position,
                "n": len(valid),
                "pearson_r": float(r),
                "confidence_flag": "small_sample" if len(valid) < DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE else "ok",
            }
        )
    result = pd.DataFrame(rows)
    result["report_type"] = REPORT_TYPE_MARKET_PRICING
    return result
