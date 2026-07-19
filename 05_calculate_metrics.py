"""
05_calculate_metrics.py

Priority 6/7: calculate the League Winner Index (LWI) per
docs/METRIC_SPECIFICATION.md. This script implements the spec, not the
other way around -- if this code and that document ever disagree, the
document is authoritative and this code has a bug.

LWI = 46% ADP Value + 18% Fantasy Finish Total Points + 17% Points Per
      Game + 12% Positional Advantage + 4% Playoff Performance
      + 3% Consistency

Scope (per spec): only rows with data_quality_flag in (matched_clean,
matched_needs_review) AND games_played >= 8 are eligible. Everyone
else gets lwi_score = null with a reason, not a score computed from
data that can't support it.

Component 4 replacement-level rank thresholds (QB12/RB34/WR42/TE12)
are CONFIRMED -- a conceptual definition choice, sensitivity-tested
against real data but not itself an empirical finding. See
docs/METRIC_SPECIFICATION.md Component 4 for the full reasoning and
the distinction between "robust to threshold choice" (tested, true)
and "this specific threshold is empirically correct" (not a
meaningful claim, since no natural cliff exists in the data).

Input:  data/master/master_historical_db_<start>_<end>.csv
        data/raw/nflverse/weekly_results_ppr_<start>_<end>.csv
Output: data/master/master_historical_db_with_lwi_<start>_<end>.csv (+.xlsx)
        data/exports/validation/lwi_eligibility_report.csv
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from config import (
    SEASONS,
    LWI_WEIGHTS as WEIGHTS,
    LWI_MIN_GAMES as MIN_GAMES,
    LWI_ELIGIBLE_QUALITY_FLAGS as ELIGIBLE_QUALITY_FLAGS,
    LWI_REPLACEMENT_RANK_THRESHOLDS as REPLACEMENT_RANK_THRESHOLDS,
    LWI_REPLACEMENT_WINDOW as REPLACEMENT_WINDOW,
    LWI_ADP_UNDERPERFORM_CAP,
    LWI_PLAYOFF_WEEKS_16_GAME_ERA,
    LWI_PLAYOFF_WEEKS_17_GAME_ERA,
    LWI_PLAYOFF_ERA_CUTOFF_SEASON,
    LWI_VERSION,
    validate_lwi_config,
)

MASTER_PATH = Path(f"data/master/master_historical_db_{SEASONS[0]}_{SEASONS[-1]}.csv")
WEEKLY_PATH = Path(f"data/raw/nflverse/weekly_results_ppr_{SEASONS[0]}_{SEASONS[-1]}.csv")
MASTER_DIR = Path("data/master")
VALIDATION_DIR = Path("data/exports/validation")


def config_fingerprint():
    """
    Deterministic hash of every LWI_* config value that affects the
    calculation. Two output files with the same fingerprint were
    produced by an identical formula; different fingerprints mean the
    scores are not directly comparable even if lwi_version matches
    (e.g. during iteration before a version bump).
    """
    payload = {
        "weights": WEIGHTS,
        "min_games": MIN_GAMES,
        "eligible_quality_flags": sorted(ELIGIBLE_QUALITY_FLAGS),
        "replacement_thresholds": REPLACEMENT_RANK_THRESHOLDS,
        "replacement_window": REPLACEMENT_WINDOW,
        "adp_underperform_cap": LWI_ADP_UNDERPERFORM_CAP,
        "playoff_weeks_16_game_era": LWI_PLAYOFF_WEEKS_16_GAME_ERA,
        "playoff_weeks_17_game_era": LWI_PLAYOFF_WEEKS_17_GAME_ERA,
        "playoff_era_cutoff_season": LWI_PLAYOFF_ERA_CUTOFF_SEASON,
    }
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:12]


def minmax_normalize_within_group(df, value_col, group_cols):
    """Min-max scale value_col to 0-100 within each group. A group with
    only one member (min == max) gets 50 -- neither rewarded nor
    punished for having no comparison, rather than an undefined
    division or an arbitrary 0/100."""
    def _scale(s):
        lo, hi = s.min(), s.max()
        if hi == lo:
            return pd.Series(50.0, index=s.index)
        return (s - lo) / (hi - lo) * 100
    return df.groupby(group_cols)[value_col].transform(_scale)


def percentile_rank_within_group(df, value_col, group_cols):
    """Percentile rank (0-100) within each group. Used only for
    Component 5's production term -- see METRIC_SPECIFICATION.md for
    why percentile rank is used there instead of min-max."""
    return df.groupby(group_cols)[value_col].rank(pct=True) * 100


def get_playoff_weeks(season: int):
    """Per docs/METRIC_SPECIFICATION.md Component 5 -- resolved
    empirically against actual max-week-per-season in the real data.
    Values live in config.py, not hardcoded here."""
    return (
        LWI_PLAYOFF_WEEKS_16_GAME_ERA if season <= LWI_PLAYOFF_ERA_CUTOFF_SEASON
        else LWI_PLAYOFF_WEEKS_17_GAME_ERA
    )


def compute_replacement_level(df, value_col):
    """
    Shared helper: for each (season, position), the replacement level
    is the median of value_col among players ranked
    [REPLACEMENT_RANK_THRESHOLDS[position], +REPLACEMENT_WINDOW] by
    position_finish_ppr. Used by BOTH Component 2 (total points above
    replacement) and Component 4 (PPG above replacement / VORP) --
    extracted into one shared function specifically so the two
    components can never silently drift into being the same formula
    on different columns without it being obvious in one place.
    """
    lookup = {}
    for (season, position), group in df.groupby(["season", "position"]):
        threshold = REPLACEMENT_RANK_THRESHOLDS.get(position)
        if threshold is None:
            lookup[(season, position)] = np.nan
            continue
        window = group[
            (group["position_finish_ppr"] >= threshold)
            & (group["position_finish_ppr"] <= threshold + REPLACEMENT_WINDOW)
        ]
        lookup[(season, position)] = window[value_col].median() if len(window) > 0 else np.nan
    return df.apply(lambda r: lookup.get((r["season"], r["position"])), axis=1)


def compute_component_1_adp_value(df):
    """ADP Value -- LOSO monotonic EVA (Expected Value Added) plus an
    overall-ADP-underperformance cap. Final structure per extensive
    real-data testing -- see docs/METRIC_SPECIFICATION.md Component 1
    for the full history (positional-only -> blended -> pure overall
    min-max -> this).

    EVA: instead of comparing a player to this SEASON's own ADP
    distribution (which changes meaning year to year), build an
    empirical "expected finish given overall ADP" curve from the
    OTHER 18 seasons (leave-one-season-out, avoiding circularity --
    a player-season never influences its own baseline), smoothed
    with isotonic (monotonic) regression so noise never lets an
    earlier pick have a WORSE expected finish than a later one purely
    by sampling artifact. EVA = expected_finish - actual_finish
    (positive = beat the historical baseline for that draft slot).

    Cap: EVA alone can score a player positively for beating a bad
    historical baseline (e.g. early picks bust often) even when they
    lost value versus their OWN actual draft cost -- real case found
    in testing: Arian Foster 2012, drafted overall_adp=1.4, finished
    12th overall. eva_raw=+28.8 (beat the rough historical average for
    pick-1-ish slots) but direct_raw=-10.6 (genuinely worse than the
    actual pick spent on him). Verified this is not a bug in EVA's
    math -- it is EVA correctly answering a different question than
    "did this beat the actual pick." The cap adds direct accountability:
    if a player's overall finish is worse than their own overall ADP,
    their Component 1 score is capped below the midpoint (40) --
    verified via real-data testing to move Foster from rank 64 to
    rank 332-357 without materially affecting real known-value seasons.
    """
    # Use overall_adp_model (real ADP for drafted players; the fixed
    # proxy for verified-undrafted players) if present -- falls back to
    # overall_adp directly for synthetic/test data that doesn't set up
    # the full observed/modeled ADP schema, so this stays backward
    # compatible with existing tests.
    adp_col = "overall_adp_model" if "overall_adp_model" in df.columns else "overall_adp"

    df["expected_finish_loso"] = np.nan
    for held_out_season in df["season"].unique():
        train = df[df["season"] != held_out_season]
        iso = IsotonicRegression(increasing=True, out_of_bounds="clip")
        iso.fit(train[adp_col], train["overall_finish_ppr"])
        mask = df["season"] == held_out_season
        df.loc[mask, "expected_finish_loso"] = iso.predict(df.loc[mask, adp_col])

    df["eva_raw"] = df["expected_finish_loso"] - df["overall_finish_ppr"]
    df["adp_value_raw"] = df[adp_col] - df["overall_finish_ppr"]  # kept for the cap check + output
    eva_component = minmax_normalize_within_group(df, "eva_raw", ["season"])

    worse_than_own_adp = df["overall_finish_ppr"] > df[adp_col]
    capped = np.where(worse_than_own_adp, np.minimum(eva_component, LWI_ADP_UNDERPERFORM_CAP), eva_component)
    return pd.Series(capped, index=df.index)


def compute_component_2_fantasy_finish(df):
    """Total points ABOVE REPLACEMENT, normalized across all positions
    within a season. Distinct job from Component 4: this rewards
    full-season cumulative production AND availability (a durable
    player with more usable games scores higher here even at a lower
    per-game rate than a great-but-injured player) -- Component 4
    measures the PER-GAME (weekly lineup) advantage instead, which
    does NOT reward games played. See docs/METRIC_SPECIFICATION.md
    Component 2 for the full reasoning and the real-data test proving
    these two are NOT the same formula (R-squared of Component 4
    predicted from Components 2+3 is 0.897 under this structure --
    Component 4 retains real, non-redundant information -- versus
    1.000/fully redundant when Component 3 was ALSO replacement-
    adjusted PPG, which was mathematically identical to Component 4)."""
    df["replacement_points"] = compute_replacement_level(df, "fantasy_points_ppr")
    df["points_above_replacement"] = df["fantasy_points_ppr"] - df["replacement_points"]
    return minmax_normalize_within_group(df, "points_above_replacement", ["season"])


def compute_component_3_ppg(df):
    """PPG above replacement, normalized across all positions within a
    season -- "full B" structure. NOTE: this was previously reverted
    to positional percentile because it was found to be mathematically
    IDENTICAL to Component 4's old (unstandardized) formula. Restored
    to replacement-adjusted here because Component 4 has since been
    redesigned to STANDARDIZED positional advantage (see
    compute_component_4_positional_advantage below), which is no
    longer the same formula as this component -- verified via testing:
    Spearman correlation between this and the new Component 4 is 0.878
    (not ~1.0), and Component 4 retains 25% variance not explained by
    Components 2+3 (not 0%). See docs/METRIC_SPECIFICATION.md
    Component 3/4 for the full history of this back-and-forth."""
    df["replacement_ppg"] = compute_replacement_level(df, "ppg_ppr")
    df["ppg_above_replacement"] = df["ppg_ppr"] - df["replacement_ppg"]
    return minmax_normalize_within_group(df, "ppg_above_replacement", ["season"])


def compute_component_4_positional_advantage(df):
    """STANDARDIZED positional advantage -- PPG above replacement,
    divided by the IQR of PPG among "starter tier" players (ranked 1
    through the position's replacement threshold) at that position and
    season, THEN normalized across positions within season using
    WINSORIZED min-max (5th/95th percentile clip), not plain min-max.

    Why standardized (IQR division), not raw: the raw version (PPG
    above replacement, unstandardized) was found via testing to be
    mathematically IDENTICAL to Component 3 once Component 3 was also
    made replacement-adjusted (Spearman ~1.0, R-squared of 1.000 when
    regressed on Components 2+3 -- literally the same formula counted
    twice). Standardizing by the position's own starter-tier PPG
    spread asks a genuinely different question: not "how big was the
    gap" (Component 3's job) but "how UNUSUAL was that gap relative to
    how tightly bunched the position normally is" (this component's
    job). IQR was chosen over standard deviation (weaker: only 15.8%
    unique variance vs IQR's) and tested head-to-head against MAD
    (close, but IQR gave meaningfully better false-positive
    separation).

    Why WINSORIZED min-max, not plain min-max, for the final 0-100
    scale: plain min-max is highly sensitive to its own extremes --
    found via direct testing that a single wild outlier in ONE
    position's data could shift an UNRELATED player's score in a
    DIFFERENT position by 60+ points, because the final normalization
    is cross-position (shared range across all 4 positions within a
    season, needed for VORP-style comparability). Winsorizing at the
    5th/95th percentile before scaling clips that outlier's influence
    on the shared range to zero (verified: 0.0 point shift to an
    unrelated player in the same test that showed 60+ under plain
    min-max) while retaining most of the magnitude signal for the bulk
    of the distribution. Tested head-to-head against plain min-max,
    percentile rank, and 2.5/97.5 winsorizing -- 5/95 gave the best
    combination of outlier robustness and retained discriminative
    power (best known-winner and false-positive separation among the
    outlier-robust alternatives, though slightly lower "unique
    variance" than plain min-max -- 15.5% vs 25.0% -- a real, accepted
    tradeoff for eliminating the cross-position contamination bug).

    Verified via real-data testing: TE share of the real top-100 is
    ~6-7% under this final structure (vs 15% for an intermediate
    fallback and 5-16% for earlier variants tested)."""
    df["replacement_ppg"] = compute_replacement_level(df, "ppg_ppr")
    df["ppg_above_replacement"] = df["ppg_ppr"] - df["replacement_ppg"]

    spread_lookup = {}
    for (season, position), group in df.groupby(["season", "position"]):
        threshold = REPLACEMENT_RANK_THRESHOLDS.get(position)
        if threshold is None:
            spread_lookup[(season, position)] = np.nan
            continue
        starters = group[group["position_finish_ppr"] <= threshold]
        if len(starters) < 4:  # too few to get a meaningful IQR
            spread_lookup[(season, position)] = np.nan
            continue
        q75, q25 = starters["ppg_ppr"].quantile([0.75, 0.25])
        iqr = q75 - q25
        spread_lookup[(season, position)] = iqr if iqr > 0 else np.nan

    df["starter_ppg_iqr"] = df.apply(lambda r: spread_lookup.get((r["season"], r["position"])), axis=1)
    df["positional_advantage_raw"] = df["ppg_above_replacement"] / df["starter_ppg_iqr"]

    # WINSORIZED min-max (5/95), not plain min-max -- see this
    # function's docstring for the real outlier-sensitivity bug this
    # fixes. The winsorized (clipped, pre-scale) intermediate value is
    # kept as its own visible output column so the clipping itself is
    # transparent and auditable, not hidden inside one opaque
    # normalization step.
    def _winsorize(s):
        lo_bound, hi_bound = s.quantile(0.05), s.quantile(0.95)
        return s.clip(lo_bound, hi_bound)
    df["positional_advantage_winsorized"] = df.groupby("season")["positional_advantage_raw"].transform(_winsorize)
    return minmax_normalize_within_group(df, "positional_advantage_winsorized", ["season"])


def compute_component_5_playoff_performance(df, weekly):
    """Production/availability split per spec -- NOT a single blended
    raw average. See METRIC_SPECIFICATION.md Component 5."""
    original_index = df.index  # preserved below -- see note at bottom

    weekly = weekly.copy()
    weekly["playoff_weeks_for_season"] = weekly["season"].apply(get_playoff_weeks)
    weekly["is_playoff_week"] = weekly.apply(
        lambda r: r["week"] in r["playoff_weeks_for_season"], axis=1
    )
    playoff_weekly = weekly[weekly["is_playoff_week"]]

    playoff_agg = (
        playoff_weekly.groupby(["season", "player_id"])
        .agg(
            playoff_games_played=("week", "nunique"),
            playoff_points_sum=("fantasy_points_ppr", "sum"),
        )
        .reset_index()
    )
    playoff_agg["playoff_ppg"] = (
        playoff_agg["playoff_points_sum"] / playoff_agg["playoff_games_played"]
    )

    df = df.merge(playoff_agg[["season", "player_id", "playoff_games_played", "playoff_ppg"]],
                   on=["season", "player_id"], how="left")
    # CRITICAL: df.merge() resets the index to a fresh 0..N-1 range. The
    # caller assigns these results back onto the ORIGINAL eligible
    # dataframe by column, which aligns by index LABEL, not position --
    # if we don't restore the original index here, that assignment
    # silently misaligns most rows (found via testing: 1907 of 2643
    # rows ended up NaN or wrong from this exact bug before this fix).
    # Safe to reassign positionally here because a left-merge against a
    # (season, player_id)-deduplicated right table preserves row order
    # and count from the left side.
    df.index = original_index

    df["playoff_games_played"] = df["playoff_games_played"].fillna(0).astype(int)

    n_playoff_weeks = df["season"].apply(lambda s: len(get_playoff_weeks(s)))
    df["playoff_availability"] = df["playoff_games_played"] / n_playoff_weeks

    # Percentile rank of playoff_ppg, computed ONLY among players who
    # actually played a playoff game that season+position -- players
    # with 0 playoff games get percentile 0 (floor) directly, not an
    # undefined average, per spec.
    played_mask = df["playoff_games_played"] > 0
    df["playoff_ppg_percentile"] = 0.0
    df.loc[played_mask, "playoff_ppg_percentile"] = (
        df.loc[played_mask]
        .groupby(["season", "position"])["playoff_ppg"]
        .rank(pct=True) * 100
    )

    component = 0.75 * df["playoff_ppg_percentile"] + 0.25 * (df["playoff_availability"] * 100)
    return component, df["playoff_games_played"], df["playoff_availability"]


def compute_component_6_consistency(df, weekly):
    """Coefficient-of-variation-based consistency, per spec. weekly
    already excludes bye/inactive weeks by construction (see
    03_download_stats.py) -- no additional bye filtering needed here."""
    original_index = df.index  # see note in compute_component_5 above -- same fix needed here

    stats = (
        weekly.groupby(["season", "player_id"])["fantasy_points_ppr"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(columns={"mean": "_wk_mean", "std": "_wk_std", "count": "_wk_count"})
    )
    df = df.merge(stats, on=["season", "player_id"], how="left")
    df.index = original_index  # restore -- merge() reset it, see Component 5 for why this matters

    # Guard stdev == 0 (identical score every week -- genuinely maximal
    # consistency, not a division error) and count < 2 (can't compute a
    # meaningful stdev at all -- shouldn't occur given the 8-game
    # eligibility floor, but guarded defensively rather than assumed).
    df["consistency_raw"] = np.where(
        (df["_wk_count"] >= 2) & (df["_wk_std"] > 0),
        df["_wk_mean"] / df["_wk_std"],
        np.where((df["_wk_count"] >= 2) & (df["_wk_std"] == 0), np.inf, np.nan),
    )

    component = minmax_normalize_within_group(df, "consistency_raw", ["season", "position"])
    df.drop(columns=["_wk_mean", "_wk_std", "_wk_count"], inplace=True)
    return component


def calculate_lwi():
    print("Step 0: Validating LWI configuration...")
    validate_lwi_config()  # raises ValueError and halts on any invalid config -- not a warning

    if not MASTER_PATH.exists() or not WEEKLY_PATH.exists():
        raise FileNotFoundError(
            f"Need both {MASTER_PATH} (from 04_build_master_dataset.py) and "
            f"{WEEKLY_PATH} (from 03_download_stats.py) to exist first."
        )

    master = pd.read_csv(MASTER_PATH)
    weekly = pd.read_csv(WEEKLY_PATH)

    print("Step 1: Determining LWI eligibility...")
    # A row is ADP-eligible if EITHER it has a real drafted match
    # (data_quality_flag) OR it's a VERIFIED undrafted player (per the
    # product decision to include genuine undrafted breakouts in the
    # unified LWI, not exclude them -- see config.py's
    # LWI_GLOBAL_MAX_OVERALL_ADP documentation). A row that is simply
    # UNMATCHED and not yet researched (verification_status ==
    # 'unresolved') is NOT assumed undrafted -- it stays ineligible,
    # identically to the original no_adp_match behavior, until someone
    # actually verifies its status in data/manual/adp_status_verification.csv.
    has_real_adp_match = master["data_quality_flag"].isin(ELIGIBLE_QUALITY_FLAGS)
    is_verified_undrafted = (
        (master.get("verification_status") == "verified")
        & (master.get("adp_status") == "undrafted")
    )
    adp_eligible = has_real_adp_match | is_verified_undrafted

    master["lwi_eligibility_flag"] = "eligible"
    master.loc[~adp_eligible, "lwi_eligibility_flag"] = "no_adp_match"
    master.loc[
        adp_eligible & (master["games_played"] < MIN_GAMES),
        "lwi_eligibility_flag",
    ] = "insufficient_games"

    eligible_mask = master["lwi_eligibility_flag"] == "eligible"
    eligible = master[eligible_mask].copy()
    ineligible = master[~eligible_mask].copy()
    print(f"  Eligible: {len(eligible)} / {len(master)} total rows")
    n_verified_undrafted_eligible = (eligible.get("adp_status") == "undrafted").sum() if "adp_status" in eligible.columns else 0
    if n_verified_undrafted_eligible > 0:
        print(f"  ({n_verified_undrafted_eligible} of those are verified-undrafted players, "
              f"scored via the proxy ADP)")
    print(f"  Ineligible breakdown:\n{ineligible['lwi_eligibility_flag'].value_counts().to_string()}")

    eligible_keys = set(zip(eligible["season"], eligible["player_id"]))
    weekly_scoped = weekly[
        weekly.apply(lambda r: (r["season"], r["player_id"]) in eligible_keys, axis=1)
    ]

    print("Step 2: Component 1 -- ADP Value...")
    eligible["adp_value_component"] = compute_component_1_adp_value(eligible)

    print("Step 3: Component 2 -- Fantasy Finish Total Points...")
    eligible["fantasy_finish_component"] = compute_component_2_fantasy_finish(eligible)

    print("Step 4: Component 3 -- Points Per Game...")
    eligible["ppg_component"] = compute_component_3_ppg(eligible)

    print("Step 5: Component 4 -- Positional Advantage...")
    eligible["positional_advantage_component"] = compute_component_4_positional_advantage(eligible)

    print("Step 6: Component 5 -- Playoff Performance...")
    (eligible["playoff_performance_component"],
     eligible["playoff_games_played"],
     eligible["playoff_availability"]) = compute_component_5_playoff_performance(eligible, weekly_scoped)

    print("Step 7: Component 6 -- Consistency...")
    eligible["consistency_component"] = compute_component_6_consistency(eligible, weekly_scoped)

    print("Step 8: Calculating final LWI score...")
    component_cols = [
        "adp_value_component", "fantasy_finish_component", "ppg_component",
        "positional_advantage_component", "playoff_performance_component",
        "consistency_component",
    ]
    # Component availability policy (docs/METRIC_SPECIFICATION.md):
    # never silently redistribute a missing component's weight, and
    # never let an incomplete score masquerade as a normal one. Moot
    # today (every eligible row has all 6 components computed), but
    # this guard makes that an enforced invariant rather than an
    # assumption -- if a future data-source change ever breaks one
    # component again the way the weekly-data gap did, this catches it
    # instead of silently producing a misleadingly-normal-looking score.
    n_available = eligible[component_cols].notna().sum(axis=1)
    is_complete = n_available == len(component_cols)

    eligible["lwi_score_diagnostic"] = (
        WEIGHTS["adp_value"] * eligible["adp_value_component"].fillna(0)
        + WEIGHTS["fantasy_finish"] * eligible["fantasy_finish_component"].fillna(0)
        + WEIGHTS["ppg"] * eligible["ppg_component"].fillna(0)
        + WEIGHTS["positional_advantage"] * eligible["positional_advantage_component"].fillna(0)
        + WEIGHTS["playoff_performance"] * eligible["playoff_performance_component"].fillna(0)
        + WEIGHTS["consistency"] * eligible["consistency_component"].fillna(0)
    ).round(2)

    eligible["lwi_score"] = eligible["lwi_score_diagnostic"].where(is_complete)
    eligible["lwi_component_coverage"] = np.where(
        is_complete, "complete_6_of_6",
        "incomplete_" + n_available.astype(str) + "_of_" + str(len(component_cols)),
    )

    n_incomplete = (~is_complete).sum()
    if n_incomplete > 0:
        print(f"  WARNING: {n_incomplete} eligible rows have an incomplete component "
              f"set -- lwi_score left null for these, per the component availability "
              f"policy in docs/METRIC_SPECIFICATION.md. See lwi_score_diagnostic for "
              f"a labeled partial score if needed, but these should be excluded from "
              f"any ranking output by default.")

    # Scoring-version metadata: "LWI 82.4" means something different
    # under a different config, so every row records which formula
    # version and exact config produced it. Two files with the same
    # fingerprint used an identical formula; a version bump without a
    # fingerprint change would itself be a bug worth catching.
    fingerprint = config_fingerprint()
    eligible["lwi_version"] = LWI_VERSION
    eligible["lwi_config_fingerprint"] = fingerprint

    for col in ["lwi_score", "lwi_score_diagnostic", "adp_value_component", "fantasy_finish_component",
                "ppg_component", "positional_advantage_component",
                "playoff_performance_component", "consistency_component",
                "playoff_games_played", "playoff_availability",
                "lwi_component_coverage", "lwi_version", "lwi_config_fingerprint"]:
        if col not in ineligible.columns:
            ineligible[col] = None

    final = pd.concat([eligible, ineligible], ignore_index=True).sort_values(
        ["season", "overall_finish_ppr"]
    )

    print("Step 9: Writing output...")
    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = MASTER_DIR / f"master_historical_db_with_lwi_{SEASONS[0]}_{SEASONS[-1]}.csv"
    final.to_csv(out_csv, index=False)
    try:
        final.to_excel(MASTER_DIR / f"master_historical_db_with_lwi_{SEASONS[0]}_{SEASONS[-1]}.xlsx", index=False)
    except Exception as e:
        print(f"  xlsx export skipped ({e})")

    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    elig_report = (
        master.groupby(["season", "lwi_eligibility_flag"]).size()
        .reset_index(name="row_count")
    )
    elig_report.to_csv(VALIDATION_DIR / "lwi_eligibility_report.csv", index=False)

    print(f"\nDone. {len(eligible)} rows scored, {len(ineligible)} rows ineligible.")
    print(f"Master DB with LWI -> {out_csv}")
    print(f"Eligibility report -> {VALIDATION_DIR / 'lwi_eligibility_report.csv'}")
    print(f"\nNOTE: Component 4 uses replacement-level rank thresholds "
          f"({REPLACEMENT_RANK_THRESHOLDS}) -- confirmed per "
          f"docs/METRIC_SPECIFICATION.md, sensitivity-tested against real "
          f"data (0.9996 rank correlation across the most divergent "
          f"candidate configurations tested).")

    return final


def main():
    calculate_lwi()


if __name__ == "__main__":
    main()
