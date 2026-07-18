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

Open decisions from the spec that this implementation makes a default
choice on -- FLAGGED here and in the output, not buried:
  - Component 4 replacement-level rank thresholds: QB12/RB30/WR36/TE12
    (proposed in spec, not yet formally confirmed).

Input:  data/master/master_historical_db_<start>_<end>.csv
        data/raw/nflverse/weekly_results_ppr_<start>_<end>.csv
Output: data/master/master_historical_db_with_lwi_<start>_<end>.csv (+.xlsx)
        data/exports/validation/lwi_eligibility_report.csv
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from config import (
    SEASONS,
    LWI_WEIGHTS as WEIGHTS,
    LWI_MIN_GAMES as MIN_GAMES,
    LWI_ELIGIBLE_QUALITY_FLAGS as ELIGIBLE_QUALITY_FLAGS,
    LWI_REPLACEMENT_RANK_THRESHOLDS as REPLACEMENT_RANK_THRESHOLDS,
    LWI_REPLACEMENT_WINDOW as REPLACEMENT_WINDOW,
    LWI_PLAYOFF_WEEKS_16_GAME_ERA,
    LWI_PLAYOFF_WEEKS_17_GAME_ERA,
    LWI_PLAYOFF_ERA_CUTOFF_SEASON,
)

MASTER_PATH = Path(f"data/master/master_historical_db_{SEASONS[0]}_{SEASONS[-1]}.csv")
WEEKLY_PATH = Path(f"data/raw/nflverse/weekly_results_ppr_{SEASONS[0]}_{SEASONS[-1]}.csv")
MASTER_DIR = Path("data/master")
VALIDATION_DIR = Path("data/exports/validation")


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


def compute_component_1_adp_value(df):
    df["adp_value_raw"] = df["positional_adp"] - df["position_finish_ppr"]
    return minmax_normalize_within_group(df, "adp_value_raw", ["season", "position"])


def compute_component_2_fantasy_finish(df):
    return minmax_normalize_within_group(df, "fantasy_points_ppr", ["season", "position"])


def compute_component_3_ppg(df):
    return minmax_normalize_within_group(df, "ppg_ppr", ["season", "position"])


def compute_component_4_positional_advantage(df):
    """Replacement level = median ppg_ppr of players ranked
    [threshold, threshold+window] at that position+season, per spec."""
    replacement_lookup = {}
    for (season, position), group in df.groupby(["season", "position"]):
        threshold = REPLACEMENT_RANK_THRESHOLDS.get(position)
        if threshold is None:
            replacement_lookup[(season, position)] = np.nan
            continue
        window = group[
            (group["position_finish_ppr"] >= threshold)
            & (group["position_finish_ppr"] <= threshold + REPLACEMENT_WINDOW)
        ]
        replacement_lookup[(season, position)] = (
            window["ppg_ppr"].median() if len(window) > 0 else np.nan
        )

    df["_replacement_level_ppg"] = df.apply(
        lambda r: replacement_lookup.get((r["season"], r["position"])), axis=1
    )
    df["positional_advantage_raw"] = df["ppg_ppr"] - df["_replacement_level_ppg"]
    result = minmax_normalize_within_group(df, "positional_advantage_raw", ["season", "position"])
    df.drop(columns=["_replacement_level_ppg"], inplace=True)
    return result


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
    if not MASTER_PATH.exists() or not WEEKLY_PATH.exists():
        raise FileNotFoundError(
            f"Need both {MASTER_PATH} (from 04_build_master_dataset.py) and "
            f"{WEEKLY_PATH} (from 03_download_stats.py) to exist first."
        )

    master = pd.read_csv(MASTER_PATH)
    weekly = pd.read_csv(WEEKLY_PATH)

    print("Step 1: Determining LWI eligibility...")
    master["lwi_eligibility_flag"] = "eligible"
    master.loc[
        ~master["data_quality_flag"].isin(ELIGIBLE_QUALITY_FLAGS), "lwi_eligibility_flag"
    ] = "no_adp_match"
    master.loc[
        (master["data_quality_flag"].isin(ELIGIBLE_QUALITY_FLAGS))
        & (master["games_played"] < MIN_GAMES),
        "lwi_eligibility_flag",
    ] = "insufficient_games"

    eligible_mask = master["lwi_eligibility_flag"] == "eligible"
    eligible = master[eligible_mask].copy()
    ineligible = master[~eligible_mask].copy()
    print(f"  Eligible: {len(eligible)} / {len(master)} total rows")
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
    eligible["lwi_score"] = (
        WEIGHTS["adp_value"] * eligible["adp_value_component"]
        + WEIGHTS["fantasy_finish"] * eligible["fantasy_finish_component"]
        + WEIGHTS["ppg"] * eligible["ppg_component"]
        + WEIGHTS["positional_advantage"] * eligible["positional_advantage_component"]
        + WEIGHTS["playoff_performance"] * eligible["playoff_performance_component"]
        + WEIGHTS["consistency"] * eligible["consistency_component"]
    ).round(2)
    eligible["lwi_component_coverage"] = "complete_6_of_6"

    for col in ["lwi_score", "adp_value_component", "fantasy_finish_component",
                "ppg_component", "positional_advantage_component",
                "playoff_performance_component", "consistency_component",
                "playoff_games_played", "playoff_availability",
                "lwi_component_coverage"]:
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
    print(f"\nNOTE: Component 4 uses UNCONFIRMED replacement-level rank "
          f"thresholds ({REPLACEMENT_RANK_THRESHOLDS}) -- see "
          f"docs/METRIC_SPECIFICATION.md open decision #1.")

    return final


def main():
    calculate_lwi()


if __name__ == "__main__":
    main()
