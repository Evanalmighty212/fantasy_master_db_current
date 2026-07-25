"""
league_winner_label_framework_comparison.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Compares candidate frameworks for combining (1) a position-specific
absolute production floor and (2) value relative to draft-round
expectation (QB_TE_WR-adjusted expected PAR) into a single
league-winner label. Does NOT select weights, thresholds, or
implement a final label -- every numeric gate/threshold here is
ILLUSTRATIVE, used only to generate comparable evidence across
frameworks, and is labeled as such throughout.

Population: ADP-matched, round-assigned player-seasons, 2010-2024 (the
honest expanding-window test years -- 2007-2009 can't get an
out-of-sample expected-PAR estimate under MIN_PRIOR_SEASONS=3, so they
are correctly absent here, not silently dropped). This is a smaller,
different population than the production-floor-only calibration work
two turns ago (which used the full games_played>=1 population,
2007-2024, 9615 rows) -- undrafted players have no acquisition cost,
so they structurally cannot appear in any framework that requires a
value-over-draft-cost term. That's a disclosed, real population
constraint, not an oversight.

Illustrative gates shared across every framework compared, so
differences below are attributable to the COMBINATION method, not to
different gate choices:
  - Production floor: p90 of PAR within position, on this population.
  - Value floor (minimum gate): surplus = actual_PAR - QB_TE_WR
    expected_PAR > 0 (per the task's own suggestion -- "likely
    positive surplus").

Frameworks compared:
  A. Dual hard floors    -- production floor AND a SEPARATE, stricter
                             value floor (calibrated here to produce a
                             similarly-sized population to the other
                             frameworks, for a fair comparison).
  B. Gated continuous     -- production floor AND minimal value floor
                             (surplus>0) as ELIGIBILITY gates, then a
                             continuous combined score with an
                             illustrative fixed threshold (each form's
                             own median among gated players) determines
                             final status. Five combination forms
                             tested, not just 50/50.
  C. Tiered rubric        -- discrete production tiers x discrete
                             value tiers, explicit qualifying-cell
                             table, allowing extraordinary production
                             to compensate for modest value and vice
                             versa, by explicit design choice.
  D. Multiplicative        -- geometric mean of PAR and surplus,
                             computed ONLY within the already-gated
                             (hence guaranteed non-negative) population
                             -- this is what makes it mathematically
                             defensible here, unlike applying it to the
                             full population (which includes negative
                             values on both axes).

Output: research/output/dataset3/label_framework_population_sizes.csv
        research/output/dataset3/label_framework_boundary_cases.csv
        research/output/dataset3/label_framework_robustness.csv
        research/output/dataset3/label_framework_championship_comparison.csv
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expected_production_by_round_investigation import POSITIONS
from replacement_par_position_adjustment_selection import (
    walk_forward_all_variants, VARIANTS,
)
from expected_production_replacement_adjusted_retest import load_par_round_population, PAR_COL

OUTPUT_DIR = Path("research/output/dataset3")
ESPN_PATH = Path("research/benchmarks/espn_championship_rosters/championship_roster_players.csv")
PRODUCTION_FLOOR_PCTL = 0.90


def normalize_name(s) -> str:
    return re.sub(r"[.']", "", str(s)).lower().strip()


def build_population() -> pd.DataFrame:
    df = load_par_round_population()
    preds = walk_forward_all_variants(df, "equal")
    preds = preds.rename(columns={"pred_QB_TE_WR": "expected_par"})
    preds["surplus"] = preds[PAR_COL] - preds["expected_par"]
    preds["par"] = preds[PAR_COL]
    return preds[["test_year", "season", "player_id", "player_name", "position", "adp_round", "par", "expected_par", "surplus"]].rename(
        columns={"test_year": "year"}
    )


def compute_gates(pop: pd.DataFrame) -> tuple:
    floor = {pos: pop[pop["position"] == pos]["par"].quantile(PRODUCTION_FLOOR_PCTL) for pos in POSITIONS}
    pop = pop.copy()
    pop["prod_floor"] = pop["position"].map(floor)
    pop["pass_production"] = pop["par"] >= pop["prod_floor"]
    pop["pass_value"] = pop["surplus"] > 0
    pop["gated"] = pop["pass_production"] & pop["pass_value"]
    return pop, floor


def percentile_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True) * 100


def build_frameworks(pop: pd.DataFrame) -> pd.DataFrame:
    gated = pop[pop["gated"]].copy()
    gated["par_pctl"] = percentile_rank(gated["par"])
    gated["surplus_pctl"] = percentile_rank(gated["surplus"])

    # --- B. Gated continuous: 5 combination forms ---
    gated["score_equal"] = 0.5 * gated["par_pctl"] + 0.5 * gated["surplus_pctl"]
    gated["score_prod_weighted"] = 0.7 * gated["par_pctl"] + 0.3 * gated["surplus_pctl"]
    gated["score_value_weighted"] = 0.3 * gated["par_pctl"] + 0.7 * gated["surplus_pctl"]
    gated["score_raw_additive"] = gated["par"] + gated["surplus"]
    gated["score_multiplicative"] = np.sqrt(gated["par"].clip(lower=0) * gated["surplus"].clip(lower=0))

    forms = ["score_equal", "score_prod_weighted", "score_value_weighted", "score_raw_additive", "score_multiplicative"]
    for form in forms:
        gated[f"win_{form}"] = gated[form] >= gated[form].median()

    # --- A. Dual hard floors: separate, stricter value floor per position ---
    # calibrated to the median surplus among PRODUCTION-passers (not double-gated),
    # for a population size comparable to the gated-continuous forms above.
    prod_passers = pop[pop["pass_production"]].copy()
    strict_value_floor = {pos: prod_passers[prod_passers["position"] == pos]["surplus"].median() for pos in POSITIONS}
    pop = pop.copy()
    pop["strict_value_floor"] = pop["position"].map(strict_value_floor)
    pop["win_dual_hard_floors"] = pop["pass_production"] & (pop["surplus"] >= pop["strict_value_floor"])

    # --- C. Tiered rubric ---
    prod_tiers, value_tiers = {}, {}
    for pos in POSITIONS:
        sub_prod = prod_passers[prod_passers["position"] == pos]["par"]
        prod_tiers[pos] = {"p75": sub_prod.quantile(0.75), "p90": sub_prod.quantile(0.90)}
        sub_val = pop[(pop["position"] == pos) & (pop["surplus"] > 0)]["surplus"]
        value_tiers[pos] = {"p50": sub_val.quantile(0.50), "p90": sub_val.quantile(0.90)}

    def prod_tier(row):
        if not row["pass_production"]:
            return "below_floor"
        t = prod_tiers[row["position"]]
        if row["par"] >= t["p90"]:
            return "elite"
        if row["par"] >= t["p75"]:
            return "strong"
        return "adequate"

    def value_tier(row):
        if row["surplus"] <= 0:
            return "non_positive"
        t = value_tiers[row["position"]]
        if row["surplus"] >= t["p90"]:
            return "massive"
        if row["surplus"] >= t["p50"]:
            return "strong"
        return "modest"

    pop["prod_tier"] = pop.apply(prod_tier, axis=1)
    pop["value_tier"] = pop.apply(value_tier, axis=1)
    QUALIFYING_CELLS = {
        ("elite", "modest"), ("elite", "strong"), ("elite", "massive"),
        ("strong", "strong"), ("strong", "massive"),
        ("adequate", "massive"),
    }
    pop["win_tiered_rubric"] = pop.apply(lambda r: (r["prod_tier"], r["value_tier"]) in QUALIFYING_CELLS, axis=1)

    # merge gated-continuous winner flags back onto the full population (non-gated players are simply False)
    win_cols = [f"win_{form}" for form in forms]
    gated_flags = gated[["season", "player_id"] + win_cols].copy()
    pop = pop.merge(gated_flags, on=["season", "player_id"], how="left")
    for col in win_cols:
        pop[col] = pop[col].fillna(False)

    return pop, gated, forms, strict_value_floor, prod_tiers, value_tiers


def main():
    print("Building ADP-matched, round-assigned, QB_TE_WR-expected-PAR population (2010-2024, honest expanding window)...")
    raw_pop = build_population()
    pop, floor = compute_gates(raw_pop)
    print(f"Population: {len(pop)} player-seasons")
    print(f"Production floor (p90 within position): {floor}")
    print(f"Gated (pass BOTH production floor and positive surplus): {pop['gated'].sum()} of {len(pop)}")

    pop, gated, forms, strict_value_floor, prod_tiers, value_tiers = build_frameworks(pop)
    print(f"Dual-hard-floors strict value floor (median surplus among production-passers): {strict_value_floor}")

    all_frameworks = [f"win_{f}" for f in forms] + ["win_dual_hard_floors", "win_tiered_rubric"]
    label_map = {
        "win_score_equal": "B_gated_50_50", "win_score_prod_weighted": "B_gated_70_30_prod",
        "win_score_value_weighted": "B_gated_30_70_value", "win_score_raw_additive": "B_gated_raw_additive",
        "win_score_multiplicative": "D_multiplicative_gated", "win_dual_hard_floors": "A_dual_hard_floors",
        "win_tiered_rubric": "C_tiered_rubric",
    }

    print("\n=== 1. Population feasibility: total winners, per-position, per-season stats ===")
    feas_rows = []
    for col in all_frameworks:
        winners = pop[pop[col]]
        per_season = winners.groupby("year").size()
        n_seasons = pop["year"].nunique()
        row = {"framework": label_map[col], "total_winners": len(winners),
               "min_per_season": int(per_season.min()) if len(per_season) else 0,
               "max_per_season": int(per_season.max()) if len(per_season) else 0,
               "seasons_with_zero": n_seasons - per_season.shape[0]}
        for pos in POSITIONS:
            row[f"n_{pos}"] = (winners["position"] == pos).sum()
        feas_rows.append(row)
    feas_df = pd.DataFrame(feas_rows)
    feas_df.to_csv(OUTPUT_DIR / "label_framework_population_sizes.csv", index=False)
    print(feas_df.to_string(index=False))

    print("\n=== 2. Boundary-case review: real historical examples ===")
    cases = {}
    early_high_par = pop[(pop["adp_round"] <= 2)]
    cases["expensive_superstar_modest_surplus"] = early_high_par[
        (early_high_par["par"] >= early_high_par["par"].quantile(0.85))
        & (early_high_par["surplus"] > 0) & (early_high_par["surplus"] <= early_high_par[early_high_par["surplus"]>0]["surplus"].quantile(0.25))
    ].nlargest(3, "par")

    late_round = pop[pop["adp_round"] >= 10]
    cases["late_round_bargain_enormous_surplus"] = late_round[
        (late_round["pass_production"]) & (late_round["surplus"] > 0)
    ].nlargest(3, "surplus")

    cases["low_production_huge_pct_beat"] = pop[
        (~pop["pass_production"]) & (pop["expected_par"] < 0) & (pop["par"] > 0)
        & ((pop["par"] - pop["expected_par"]) / pop["expected_par"].abs().clip(lower=1) > 2)
    ].nlargest(3, "surplus")

    cases["elite_producer_fails_to_beat_expectation"] = pop[
        (pop["adp_round"] <= 3) & (pop["pass_production"]) & (pop["surplus"] <= 0)
    ].nsmallest(3, "surplus")

    boundary_rows = []
    for case_name, sub in cases.items():
        for _, r in sub.iterrows():
            row = {"case": case_name, "season": r["season"], "player_name": r["player_name"],
                   "position": r["position"], "adp_round": r["adp_round"], "par": round(r["par"], 1),
                   "surplus": round(r["surplus"], 1)}
            for col in all_frameworks:
                row[label_map[col]] = bool(r[col]) if col in r else False
            boundary_rows.append(row)
    boundary_df = pd.DataFrame(boundary_rows)
    boundary_df.to_csv(OUTPUT_DIR / "label_framework_boundary_cases.csv", index=False)
    print(boundary_df.to_string(index=False))

    print("\n=== 3. Neighborhood robustness: perturb production floor (p85/p90/p95) ===")
    robust_rows = []
    baseline_winners = {label_map[c]: set(pop[pop[c]].set_index(["season", "player_id"]).index) for c in all_frameworks}
    for pctl in [0.85, 0.90, 0.95]:
        floor_p = {pos: raw_pop[raw_pop["position"] == pos]["par"].quantile(pctl) for pos in POSITIONS}
        pop_p = raw_pop.copy()
        pop_p["prod_floor"] = pop_p["position"].map(floor_p)
        pop_p["pass_production"] = pop_p["par"] >= pop_p["prod_floor"]
        pop_p["pass_value"] = pop_p["surplus"] > 0
        pop_p["gated"] = pop_p["pass_production"] & pop_p["pass_value"]
        gated_p = pop_p[pop_p["gated"]].copy()
        gated_p["score_equal"] = 0.5 * percentile_rank(gated_p["par"]) + 0.5 * percentile_rank(gated_p["surplus"])
        winners_p = set(gated_p[gated_p["score_equal"] >= gated_p["score_equal"].median()].set_index(["season", "player_id"]).index)
        base = baseline_winners["B_gated_50_50"]
        overlap = len(winners_p & base) / max(len(winners_p | base), 1)
        robust_rows.append({"production_floor_pctl": pctl, "n_winners": len(winners_p), "jaccard_vs_p90_baseline": round(overlap, 3)})
    robust_df = pd.DataFrame(robust_rows)
    robust_df.to_csv(OUTPUT_DIR / "label_framework_robustness.csv", index=False)
    print(robust_df.to_string(index=False))

    print("\n=== 4. Championship-roster benchmark comparison ===")
    espn = pd.read_csv(ESPN_PATH)
    espn = espn[espn["position"].isin(POSITIONS)].copy()
    espn["player_norm"] = espn["player_name"].apply(normalize_name)
    espn_seasons = set(espn["season"].unique())
    pop["player_norm"] = pop["player_name"].apply(normalize_name)
    overlap_pop = pop[pop["season"].isin(espn_seasons)].copy()
    overlap_pop["on_champ_roster"] = overlap_pop.set_index(["season", "player_norm"]).index.isin(
        espn.set_index(["season", "player_norm"]).index
    )
    print(f"Overlap seasons with usable ESPN benchmark: {sorted(espn_seasons & set(pop['season'].unique()))}, n={len(overlap_pop)}")

    champ_rows = []
    prod_only_col = "pass_production"
    for label, col in [("production_only", prod_only_col)] + [(label_map[c], c) for c in all_frameworks]:
        mask = overlap_pop[col].astype(bool)
        winners = overlap_pop[mask]
        non_winners = overlap_pop[~mask]
        champ_rows.append({
            "framework": label, "n_winners_in_overlap": len(winners),
            "champ_roster_rate_among_winners": round(winners["on_champ_roster"].mean(), 4) if len(winners) else np.nan,
            "champ_roster_rate_among_non_winners": round(non_winners["on_champ_roster"].mean(), 4) if len(non_winners) else np.nan,
        })
    champ_df = pd.DataFrame(champ_rows)
    champ_df["lift"] = (champ_df["champ_roster_rate_among_winners"] / champ_df["champ_roster_rate_among_non_winners"]).round(2)
    champ_df.to_csv(OUTPUT_DIR / "label_framework_championship_comparison.csv", index=False)
    print(champ_df.to_string(index=False))

    print(f"\nWrote 4 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
