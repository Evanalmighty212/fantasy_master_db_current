"""
league_winner_value_signal_and_floor_calibration.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Two focused follow-ups to league_winner_label_framework_comparison.py.
Does NOT select thresholds, weights, or implement the final label.

PART 1: does surplus over expected PAR add championship-roster signal
CONDITIONAL on production, not just via differently-sized binary
groups? The earlier "lift" comparison wasn't apples-to-apples --
production-only labeled ~124 players in the overlap seasons, combined
frameworks ~62-68. Two honest approaches here instead:
  1a. Stratify by within-position PAR tercile (fixes production
      roughly constant), then split each stratum by surplus around its
      own median -- does the higher-surplus half show a higher
      championship-roster rate than the lower-surplus half, within the
      SAME production band?
  1b. Logistic regression: Model A (par_pctl + position) vs. Model B
      (par_pctl + surplus_pctl + position), both features normalized
      WITHIN POSITION (percentile rank) specifically so this analysis
      doesn't reintroduce the cross-position raw-PAR scale problem
      already identified. Compared via a likelihood-ratio test
      (in-sample) and leave-one-season-out cross-validated AUC / Brier
      score / log-loss (out-of-sample). Season fixed effects were NOT
      added as model terms -- 8 seasons against ~150-200 positive
      cases is too few parameters-to-data to support 8 dummy
      variables reliably; LOSO-by-season CV serves the "does this
      generalize across seasons" purpose instead, without overfitting
      a full fixed-effects spec.

PART 2: production floor calibration sweep, p80-p95 in 2.5-point
steps, holding the value gate fixed (surplus > 0, per instruction).
Reports population size, annual variation, entering/leaving boundary
players between adjacent levels, Jaccard stability across the whole
grid, and championship-roster rates -- NOT used to pick a floor that
maximizes the benchmark rate, per explicit instruction.

Output: research/output/dataset3/value_signal_banded_comparison.csv
        research/output/dataset3/value_signal_logistic_comparison.csv
        research/output/dataset3/floor_calibration_sweep.csv
        research/output/dataset3/floor_calibration_boundary_movers.csv
        research/output/dataset3/floor_calibration_stability.csv
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expected_production_by_round_investigation import POSITIONS
from league_winner_label_framework_comparison import build_population, normalize_name

OUTPUT_DIR = Path("research/output/dataset3")
ESPN_PATH = Path("research/benchmarks/espn_championship_rosters/championship_roster_players.csv")
MIN_N = 5


def load_data():
    pop = build_population()  # ADP-matched, round-assigned, 2010-2024, honest expanding window, QB_TE_WR expected PAR
    espn = pd.read_csv(ESPN_PATH)
    espn = espn[espn["position"].isin(POSITIONS)].copy()
    espn["player_norm"] = espn["player_name"].apply(normalize_name)
    pop["player_norm"] = pop["player_name"].apply(normalize_name)
    espn_seasons = set(espn["season"].unique()) & set(pop["season"].unique())
    pop["on_champ_roster"] = pop.set_index(["season", "player_norm"]).index.isin(
        espn.set_index(["season", "player_norm"]).index
    )
    overlap = pop[pop["season"].isin(espn_seasons)].copy()
    return pop, overlap, sorted(espn_seasons)


def within_position_pctl(df: pd.DataFrame, col: str, ref: pd.DataFrame = None) -> pd.Series:
    """Percentile rank of col, computed within each position, using ref
    (a stable reference population) if given, else df itself."""
    ref = df if ref is None else ref
    out = pd.Series(index=df.index, dtype=float)
    for pos in POSITIONS:
        ref_vals = ref[ref["position"] == pos][col]
        out.loc[df["position"] == pos] = df.loc[df["position"] == pos, col].apply(
            lambda v: (ref_vals < v).mean() * 100
        )
    return out


def part1_banded(pop: pd.DataFrame, overlap: pd.DataFrame):
    print("\n" + "=" * 70)
    print("PART 1a: banded comparison -- fix production (within-position PAR tercile), vary surplus")
    print("=" * 70)

    pop = pop.copy()
    for pos in POSITIONS:
        mask = pop["position"] == pos
        pop.loc[mask, "par_tercile"] = pd.qcut(pop.loc[mask, "par"], 3, labels=["Low", "Mid", "High"])
    overlap = overlap.merge(pop[["season", "player_id", "par_tercile"]], on=["season", "player_id"], how="left")

    rows = []
    for pos in POSITIONS + ["ALL"]:
        sub_pop = overlap if pos == "ALL" else overlap[overlap["position"] == pos]
        for tercile in ["Low", "Mid", "High"]:
            band = sub_pop[sub_pop["par_tercile"] == tercile]
            if len(band) < MIN_N * 2:
                continue
            med = band["surplus"].median()
            high_val = band[band["surplus"] > med]
            low_val = band[band["surplus"] <= med]
            if len(high_val) < MIN_N or len(low_val) < MIN_N:
                continue
            rows.append({
                "scope": pos, "par_tercile": tercile,
                "n_low_value": len(low_val), "champ_rate_low_value": round(low_val["on_champ_roster"].mean(), 3),
                "n_high_value": len(high_val), "champ_rate_high_value": round(high_val["on_champ_roster"].mean(), 3),
                "diff": round(high_val["on_champ_roster"].mean() - low_val["on_champ_roster"].mean(), 3),
            })
    banded_df = pd.DataFrame(rows)
    banded_df.to_csv(OUTPUT_DIR / "value_signal_banded_comparison.csv", index=False)
    print(banded_df.to_string(index=False))
    return banded_df


def part1_logistic(pop: pd.DataFrame, overlap: pd.DataFrame, espn_seasons: list):
    print("\n" + "=" * 70)
    print("PART 1b: logistic regression -- production alone vs. production + surplus")
    print("=" * 70)

    overlap = overlap.copy()
    overlap["par_pctl"] = within_position_pctl(overlap, "par", ref=pop) / 100
    overlap["surplus_pctl"] = within_position_pctl(overlap, "surplus", ref=pop) / 100
    pos_dummies = pd.get_dummies(overlap["position"], prefix="pos", drop_first=True)
    y = overlap["on_champ_roster"].astype(int).values

    overlap["par_x_surplus"] = overlap["par_pctl"] * overlap["surplus_pctl"]
    X_a = pd.concat([overlap[["par_pctl"]], pos_dummies], axis=1).values
    X_b = pd.concat([overlap[["par_pctl", "surplus_pctl"]], pos_dummies], axis=1).values
    # Model C: adds an INTERACTION term -- motivated directly by 1a's finding that
    # surplus only discriminates within the High production tercile, not Low/Mid.
    # A plain additive model (B) assumes surplus's effect is constant across all
    # production levels; this tests whether allowing it to depend on production
    # level specifically recovers the banded signal that B's coefficient missed.
    X_c = pd.concat([overlap[["par_pctl", "surplus_pctl", "par_x_surplus"]], pos_dummies], axis=1).values

    def fit_and_loglik(X, y):
        model = LogisticRegression(C=1e6, max_iter=2000)
        model.fit(X, y)
        p = model.predict_proba(X)[:, 1]
        p = np.clip(p, 1e-10, 1 - 1e-10)
        loglik = np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))
        return model, loglik, X.shape[1]

    model_a, loglik_a, k_a = fit_and_loglik(X_a, y)
    model_b, loglik_b, k_b = fit_and_loglik(X_b, y)
    model_c, loglik_c, k_c = fit_and_loglik(X_c, y)
    lr_ab = 2 * (loglik_b - loglik_a)
    p_ab = stats.chi2.sf(lr_ab, k_b - k_a)
    lr_bc = 2 * (loglik_c - loglik_b)
    p_bc = stats.chi2.sf(lr_bc, k_c - k_b)
    print(f"In-sample log-likelihood: A (production only) = {loglik_a:.2f}, "
          f"B (production + surplus, additive) = {loglik_b:.2f}, "
          f"C (production + surplus + interaction) = {loglik_c:.2f}")
    print(f"LR test B vs A (does adding surplus additively improve fit?): LR={lr_ab:.3f}, p={p_ab:.4f}")
    print(f"LR test C vs B (does allowing surplus's effect to depend on production level improve fit further?): "
          f"LR={lr_bc:.3f}, p={p_bc:.4f}")
    print(f"Model B surplus_pctl coefficient: {model_b.coef_[0][1]:.4f}")
    print(f"Model C interaction coefficient (par_pctl x surplus_pctl): {model_c.coef_[0][2]:.4f} "
          f"(positive = surplus matters MORE at higher production levels)")

    print(f"\nLeave-one-season-out cross-validation ({len(espn_seasons)} seasons) -- "
          f"a model-comparison exercise on a small fixed benchmark, not a deployed forecaster, "
          f"so non-chronological CV is the correct honest tool here, not a leakage concern.")
    cv_rows = []
    preds_a, preds_b, preds_c, y_true_all = [], [], [], []
    for held_out in espn_seasons:
        train_mask = overlap["season"] != held_out
        test_mask = overlap["season"] == held_out
        if train_mask.sum() < 20 or test_mask.sum() < MIN_N:
            print(f"  season {held_out}: skipped (insufficient n)")
            continue
        y_train, y_test = y[train_mask.values], y[test_mask.values]
        if y_train.sum() < 2 or y_train.sum() == len(y_train):
            print(f"  season {held_out}: skipped (degenerate training labels)")
            continue

        ma = LogisticRegression(C=1e6, max_iter=2000).fit(X_a[train_mask.values], y_train)
        mb = LogisticRegression(C=1e6, max_iter=2000).fit(X_b[train_mask.values], y_train)
        mc = LogisticRegression(C=1e6, max_iter=2000).fit(X_c[train_mask.values], y_train)
        pa = ma.predict_proba(X_a[test_mask.values])[:, 1]
        pb = mb.predict_proba(X_b[test_mask.values])[:, 1]
        pc = mc.predict_proba(X_c[test_mask.values])[:, 1]
        preds_a.extend(pa); preds_b.extend(pb); preds_c.extend(pc); y_true_all.extend(y_test)

    y_true_all = np.array(y_true_all)
    preds_a = np.array(preds_a)
    preds_b = np.array(preds_b)
    preds_c = np.array(preds_c)
    result = {
        "n_test_rows": len(y_true_all), "n_positive": int(y_true_all.sum()),
        "auc_A_production_only": roc_auc_score(y_true_all, preds_a),
        "auc_B_production_plus_surplus": roc_auc_score(y_true_all, preds_b),
        "auc_C_production_surplus_interaction": roc_auc_score(y_true_all, preds_c),
        "brier_A_production_only": brier_score_loss(y_true_all, preds_a),
        "brier_B_production_plus_surplus": brier_score_loss(y_true_all, preds_b),
        "brier_C_production_surplus_interaction": brier_score_loss(y_true_all, preds_c),
        "logloss_A_production_only": log_loss(y_true_all, preds_a, labels=[0, 1]),
        "logloss_B_production_plus_surplus": log_loss(y_true_all, preds_b, labels=[0, 1]),
        "logloss_C_production_surplus_interaction": log_loss(y_true_all, preds_c, labels=[0, 1]),
    }
    print(pd.Series(result).to_string())
    pd.DataFrame([result]).to_csv(OUTPUT_DIR / "value_signal_logistic_comparison.csv", index=False)
    return result, lr_stat, p_value


def part2_floor_calibration(pop: pd.DataFrame, overlap: pd.DataFrame):
    print("\n" + "=" * 70)
    print("PART 2: production floor calibration sweep (value gate fixed: surplus > 0)")
    print("=" * 70)

    percentiles = [80, 82.5, 85, 87.5, 90, 92.5, 95]
    sweep_rows = []
    gated_sets = {}
    floor_examples = {}
    for pctl in percentiles:
        floor = {pos: pop[pop["position"] == pos]["par"].quantile(pctl / 100) for pos in POSITIONS}
        p = pop.copy()
        p["prod_floor"] = p["position"].map(floor)
        p["gated"] = (p["par"] >= p["prod_floor"]) & (p["surplus"] > 0)
        gated = p[p["gated"]]
        gated_sets[pctl] = set(gated.set_index(["season", "player_id"]).index)

        per_season = gated.groupby("year").size()
        row = {"percentile": pctl, "total_winners": len(gated),
               "min_per_season": int(per_season.min()) if len(per_season) else 0,
               "max_per_season": int(per_season.max()) if len(per_season) else 0,
               "seasons_with_zero": p["year"].nunique() - per_season.shape[0]}
        for pos in POSITIONS:
            row[f"n_{pos}"] = (gated["position"] == pos).sum()
            row[f"floor_{pos}"] = round(floor[pos], 1)

        overlap_p = overlap.copy()
        overlap_p["prod_floor"] = overlap_p["position"].map(floor)
        overlap_p["gated"] = (overlap_p["par"] >= overlap_p["prod_floor"]) & (overlap_p["surplus"] > 0)
        row["n_in_overlap"] = overlap_p["gated"].sum()
        row["champ_rate_in_overlap"] = round(overlap_p[overlap_p["gated"]]["on_champ_roster"].mean(), 3) if overlap_p["gated"].sum() >= MIN_N else np.nan
        sweep_rows.append(row)

        # boundary example: the single LOWEST-PAR player who still clears this floor, per position
        boundary = gated.loc[gated.groupby("position")["par"].idxmin()][["position", "season", "player_name", "par", "surplus"]]
        floor_examples[pctl] = boundary

    sweep_df = pd.DataFrame(sweep_rows)
    sweep_df.to_csv(OUTPUT_DIR / "floor_calibration_sweep.csv", index=False)
    print(sweep_df.to_string(index=False))

    print("\n--- Boundary examples: lowest-PAR player who still clears the floor, at p80 vs. p95 ---")
    print("p80:")
    print(floor_examples[80].to_string(index=False))
    print("p95:")
    print(floor_examples[95].to_string(index=False))

    print("\n--- Entering/leaving players between adjacent floor levels ---")
    mover_rows = []
    for i in range(len(percentiles) - 1):
        lo, hi = percentiles[i], percentiles[i + 1]
        leaving = gated_sets[lo] - gated_sets[hi]
        name_lookup = pop.set_index(["season", "player_id"])[["player_name", "position", "par"]]
        for idx in leaving:
            r = name_lookup.loc[idx]
            mover_rows.append({"from_pctl": lo, "to_pctl": hi, "direction": "leaves_as_floor_tightens",
                                "season": idx[0], "player_name": r["player_name"], "position": r["position"], "par": round(r["par"], 1)})
    movers_df = pd.DataFrame(mover_rows)
    movers_df.to_csv(OUTPUT_DIR / "floor_calibration_boundary_movers.csv", index=False)
    print(f"{len(movers_df)} total (season, player) exits across all adjacent-step comparisons "
          f"(p80->p82.5->...->p95). Sample:")
    print(movers_df.head(15).to_string(index=False))

    print("\n--- Stability: Jaccard overlap of adjacent floor levels ---")
    stab_rows = []
    for i in range(len(percentiles) - 1):
        lo, hi = percentiles[i], percentiles[i + 1]
        overlap_n = len(gated_sets[lo] & gated_sets[hi])
        union_n = len(gated_sets[lo] | gated_sets[hi])
        stab_rows.append({"from_pctl": lo, "to_pctl": hi, "jaccard": round(overlap_n / union_n, 3) if union_n else np.nan})
    stab_df = pd.DataFrame(stab_rows)
    stab_df.to_csv(OUTPUT_DIR / "floor_calibration_stability.csv", index=False)
    print(stab_df.to_string(index=False))

    return sweep_df, movers_df, stab_df


def main():
    pop, overlap, espn_seasons = load_data()
    print(f"Full population (2010-2024): {len(pop)}. Overlap-season population "
          f"({espn_seasons}): {len(overlap)}, positive (on champ roster): {overlap['on_champ_roster'].sum()}")

    part1_banded(pop, overlap)
    part1_logistic(pop, overlap, espn_seasons)
    part2_floor_calibration(pop, overlap)

    print(f"\nWrote 5 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
