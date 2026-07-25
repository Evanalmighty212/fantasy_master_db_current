"""
production_weight_and_boundary_calibration.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Builds the corrected, ADP-aware AATP construction (verified season
length, geo-clipped rejected, weighted-sum provisional, ADP-aware
active window provisional), then runs the three calibration tasks
requested on top of it. Does NOT select final weights, boundaries, or
implement anything -- config.py untouched.

ADP-aware active window, implemented precisely (not approximated) using
real weekly participation data (data/raw/nflverse/weekly_results_ppr_2006_2025.csv,
which per this project's own documented convention has NO rows for
weeks a player had no real involvement -- exactly what's needed to
find a true first-active-week):
  - meaningful-ADP (adp_matched) players: missed-game credit for the
    WHOLE season (games_missed = G - games_played), i.e. Week 1 onward.
  - undrafted players: missed-game credit only for games from their
    first verified active week onward -- weeks before that are
    excluded entirely (no real credit, no replacement credit), since
    they were never a real fantasy consideration during that window.

PART A: production weight comparison (AATP vs. PPG_AR_season_equiv).
PART B: meaningful-ADP boundary comparison -- top 200 vs. actual
        reliable per-season depth. Checked empirically first: real
        per-season depth in this dataset ranges 92 (2012) to 211
        (2007), NEVER reaching config.py's TOP_N_ADP=250 cap in any
        season -- so "top 250" and "actual reliable depth" are
        mathematically IDENTICAL here, not two distinct candidates.
        The only genuinely distinct comparison is top 200 vs. the
        status quo (adp_matched, which already equals reliable depth).
PART C: expected-AATP-by-round, refit from scratch (expanding window,
        equal weighting, pooled -- not yet position-adjusted, matching
        the same incremental sequencing already used when PAR replaced
        raw points).

Output: research/output/dataset3/weight_calibration_comparison.csv
        research/output/dataset3/weight_calibration_championship.csv
        research/output/dataset3/adp_boundary_comparison.csv
        research/output/dataset3/adp_boundary_affected_players.csv
        research/output/dataset3/aatp_round_curve_refit.csv
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.replacement import ROSTER_PRESETS, FLEX_ALLOCATION_RB_WR_HEAVY, replacement_rank_cutoff, replacement_level_from_rank
from expected_production_by_round_investigation import POSITIONS, adp_round

OUTPUT_DIR = Path("research/output/dataset3")
BROAD_DATASET_PATH = OUTPUT_DIR / "broad_historical_dataset.csv"
WEEKLY_PATH = Path("data/raw/nflverse/weekly_results_ppr_2006_2025.csv")
ESPN_PATH = Path("research/benchmarks/espn_championship_rosters/championship_roster_players.csv")
PRESET = ROSTER_PRESETS["12_team_standard"]
WINDOW = 12
MIN_PRIOR_SEASONS = 3
MIN_N = 5


def verified_season_length(season: int) -> int:
    return 17 if season >= 2021 else 16


def normalize_name(s) -> str:
    return re.sub(r"[.']", "", str(s)).lower().strip()


def build_adp_aware_aatp() -> pd.DataFrame:
    df = pd.read_csv(BROAD_DATASET_PATH)
    df = df[(df["games_played"] >= 1) & (df["position"].isin(POSITIONS)) & (df["season"].between(2007, 2024))].copy()
    df["G"] = df["season"].apply(verified_season_length)
    df["games_played_capped"] = df[["games_played", "G"]].min(axis=1)

    weekly = pd.read_csv(WEEKLY_PATH, usecols=["season", "player_id", "week"])
    first_week = weekly.groupby(["season", "player_id"])["week"].min().rename("first_active_week")
    df = df.merge(first_week, on=["season", "player_id"], how="left")

    # meaningful-ADP: full season eligible. Undrafted: eligible only from first_active_week onward.
    eligible_games = np.where(
        df["adp_matched"], df["G"],
        (df["G"] - df["first_active_week"] + 1).clip(lower=df["games_played_capped"])
    )
    # fallback for undrafted rows with no weekly match found (rare) -- treat as full season, disclosed
    n_fallback = (~df["adp_matched"] & df["first_active_week"].isna()).sum()
    print(f"Undrafted rows with no weekly-data match (fallback to full-season eligibility): {n_fallback}")
    eligible_games = np.where(df["first_active_week"].isna(), df["G"], eligible_games)
    df["eligible_games"] = eligible_games
    df["games_missed_eligible"] = (df["eligible_games"] - df["games_played_capped"]).clip(lower=0)

    cutoffs = {pos: replacement_rank_cutoff(PRESET, pos, FLEX_ALLOCATION_RB_WR_HEAVY) for pos in POSITIONS}
    df["replacement_ppg"] = replacement_level_from_rank(
        df, value_col="ppg_ppr", rank_col="position_finish_ppr", cutoff_by_position=cutoffs, window=WINDOW,
    )
    df["AATP"] = df["fantasy_points_ppr"] + df["replacement_ppg"] * df["games_missed_eligible"]
    df["PPG_AR"] = df["ppg_ppr"] - df["replacement_ppg"]
    df["PPG_AR_eq"] = df["PPG_AR"] * df["G"]
    return df


def part_a_weights(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("PART A: production weight comparison")
    print("=" * 70)

    weights = {
        "50_50": (0.5, 0.5),
        "60_40_AATP": (0.6, 0.4),
        "40_60_AATP": (0.4, 0.6),
        "lwi_near_equal": (18 / 35, 17 / 35),
    }
    print(f"lwi_near_equal weights: {weights['lwi_near_equal']} -- vs 50_50: {weights['50_50']} "
          f"(distinct: {weights['lwi_near_equal'] != weights['50_50']}, difference: "
          f"{abs(weights['lwi_near_equal'][0]-0.5):.4f})")

    d = df.copy()
    for name, (w1, w2) in weights.items():
        d[f"prod_{name}"] = w1 * d["AATP"] + w2 * d["PPG_AR_eq"]

    baseline = "prod_50_50"
    rows = []
    for name in weights:
        if name == "50_50":
            continue
        spearman_r = d[baseline].corr(d[f"prod_{name}"], method="spearman")
        top25_base = set(d.nlargest(25, baseline).set_index(["season", "player_id"]).index)
        top25_alt = set(d.nlargest(25, f"prod_{name}").set_index(["season", "player_id"]).index)
        top100_base = set(d.nlargest(100, baseline).set_index(["season", "player_id"]).index)
        top100_alt = set(d.nlargest(100, f"prod_{name}").set_index(["season", "player_id"]).index)
        rows.append({
            "weight_set": name, "spearman_vs_50_50": round(spearman_r, 4),
            "top25_overlap": f"{len(top25_base & top25_alt)}/25",
            "top100_overlap": f"{len(top100_base & top100_alt)}/100",
        })
    comp_df = pd.DataFrame(rows)
    comp_df.to_csv(OUTPUT_DIR / "weight_calibration_comparison.csv", index=False)
    print(comp_df.to_string(index=False))

    print("\n--- Boundary case: CMC 2020 (few games, elite rate) vs. Rodgers 2015 (many games, modest rate) ---")
    cmc = d[(d["season"] == 2020) & (d["player_name"] == "Christian McCaffrey")]
    rodg = d[(d["season"] == 2015) & (d["player_name"] == "Aaron Rodgers")]
    for name in weights:
        col = f"prod_{name}"
        c_val = cmc[col].values[0] if len(cmc) else np.nan
        r_val = rodg[col].values[0] if len(rodg) else np.nan
        print(f"  {name}: CMC 2020={c_val:.1f}, Rodgers 2015={r_val:.1f}, CMC ranks higher: {c_val > r_val}")

    print("\n--- Championship-roster performance (reported, NOT used to pick weights) ---")
    espn = pd.read_csv(ESPN_PATH)
    espn = espn[espn["position"].isin(POSITIONS)].copy()
    espn["player_norm"] = espn["player_name"].apply(normalize_name)
    d["player_norm"] = d["player_name"].apply(normalize_name)
    espn_seasons = set(espn["season"].unique()) & set(d["season"].unique())
    overlap = d[d["season"].isin(espn_seasons)].copy()
    overlap["on_champ_roster"] = overlap.set_index(["season", "player_norm"]).index.isin(
        espn.set_index(["season", "player_norm"]).index
    )
    champ_rows = []
    for name in weights:
        col = f"prod_{name}"
        top100 = overlap.nlargest(100, col)
        rest = overlap[~overlap.index.isin(top100.index)]
        champ_rows.append({
            "weight_set": name, "champ_rate_top100": round(top100["on_champ_roster"].mean(), 3),
            "champ_rate_rest": round(rest["on_champ_roster"].mean(), 3),
        })
    champ_df = pd.DataFrame(champ_rows)
    champ_df.to_csv(OUTPUT_DIR / "weight_calibration_championship.csv", index=False)
    print(champ_df.to_string(index=False))


def part_b_adp_boundary(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("PART B: meaningful-ADP boundary comparison")
    print("=" * 70)
    print("\nReal per-season reliable depth (max adp_rank actually matched):")
    depth = df[df["adp_matched"]].groupby("season")["adp_rank"].max()
    print(depth.to_string())
    seasons_over_200 = depth[depth > 200]
    print(f"\nSeasons where real depth exceeds 200 (where top_200 vs. status-quo actually differ): "
          f"{seasons_over_200.to_dict()}")
    print("Real depth never reaches config.py's TOP_N_ADP=250 cap in any season -- "
          "'top 250' and 'actual reliable depth' are mathematically identical here, not distinct candidates.")

    d = df.copy()
    d["meaningful_reliable_depth"] = d["adp_matched"]  # status quo, == top_250 == reliable depth (verified above)
    d["meaningful_top_200"] = d["adp_matched"] & (d["adp_rank"] <= 200)

    changed = d[d["meaningful_reliable_depth"] != d["meaningful_top_200"]]
    print(f"\nPlayer-seasons where the two boundaries disagree: {len(changed)} of {len(d)}")
    print(changed[["season", "player_name", "position", "adp_rank", "fantasy_points_ppr"]]
          .sort_values(["season", "adp_rank"]).to_string(index=False))

    comp_rows = []
    for name, col in [("reliable_depth_status_quo", "meaningful_reliable_depth"), ("top_200", "meaningful_top_200")]:
        comp_rows.append({"definition": name, "n_meaningful": d[col].sum()})
    pd.DataFrame(comp_rows).to_csv(OUTPUT_DIR / "adp_boundary_comparison.csv", index=False)
    changed.to_csv(OUTPUT_DIR / "adp_boundary_affected_players.csv", index=False)


def part_c_refit_round_curve(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("PART C: expected-AATP-by-round, refit from scratch")
    print("=" * 70)

    matched = df[df["adp_matched"]].copy()
    matched["adp_round"] = matched["overall_adp_observed"].apply(adp_round)

    results = []
    for asof_year in sorted(matched["season"].unique()):
        train = matched[matched["season"] < asof_year]
        if train["season"].nunique() < MIN_PRIOR_SEASONS:
            continue
        test = matched[matched["season"] == asof_year].copy()
        if test.empty:
            continue
        round_means = train.groupby("adp_round")["AATP"].mean().to_dict()
        test["expected_AATP"] = test["adp_round"].map(round_means)
        results.append(test)
    preds = pd.concat(results, ignore_index=True).dropna(subset=["expected_AATP"])
    print(f"Test population (expanding window, 2010-2024): {len(preds)} rows")

    pooled = preds.groupby("adp_round")["AATP"].agg(["count", "mean", "median"]).reset_index()
    pooled.to_csv(OUTPUT_DIR / "aatp_round_curve_refit.csv", index=False)
    print(pooled.round(1).to_string(index=False))

    violations = []
    rs = pooled.sort_values("adp_round").reset_index(drop=True)
    for i in range(1, len(rs)):
        if rs.loc[i, "mean"] > rs.loc[i - 1, "mean"]:
            violations.append((int(rs.loc[i - 1, "adp_round"]), int(rs.loc[i, "adp_round"])))
    print(f"\nMonotonicity violations: {violations}")
    print(f"Stays positive throughout: {(pooled['mean'] > 0).all()}")

    print("\nPosition composition by round:")
    mix = matched.groupby(["adp_round", "position"]).size().unstack(fill_value=0)
    mix_pct = mix.div(mix.sum(axis=1), axis=0) * 100
    print(mix_pct.round(0).to_string())


def main():
    print("Building ADP-aware AATP population (2007-2024, verified season lengths, weekly-data active window)...")
    df = build_adp_aware_aatp()
    print(f"Population: {len(df)} player-seasons")

    part_a_weights(df)
    part_b_adp_boundary(df)
    part_c_refit_round_curve(df)

    print(f"\nWrote 5 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
