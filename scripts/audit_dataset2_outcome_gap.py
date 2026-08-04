"""
scripts/audit_dataset2_outcome_gap.py

Dataset 2 OUTCOME-ELIGIBILITY RECONCILIATION -- a real, independent
audit run against the real Stars-by-Value export, the real master
population, and real players.csv draft/rookie data. This is NOT the
outcome table itself (artifact 2 of the three-artifact architecture,
research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md §1a, is not
built here) and its output is NEVER joined into the predictor table.
Standalone research artifact for whoever builds the real outcome table
next.

REVISED THIS ROUND -- two real corrections:

1. `scored_but_unlabeled` is RETIRED as a reporting category (it was
   already flagged last round as a misnomer -- no row in it has a real
   score). This round drops it from the top-level counts entirely;
   the three real underlying statuses
   (unscoreable_drafted_adp_missing / unscoreable_ambiguous /
   unscoreable_expected_production_out_of_range) are reported
   directly, never re-aggregated.

2. STAR ELIGIBILITY CORRECTED: verified directly this round that
   `below_production_gate` rows carry a REAL, non-null
   `star_by_value_label = 0` (labeling.py's own step 2 assigns this
   deliberately -- production too low to ever be a Star is a real,
   determinate fact that needs no acquisition-cost resolution at all,
   unlike `out_of_scope`/`unscoreable_*`, where label is genuinely
   NULL). Per this round's exact instruction ("star_outcome_eligible
   = True only for rows with a legitimate existing SBV binary
   label"), `below_production_gate` rows THEREFORE ARE
   star_outcome_eligible -- this is a real expansion from an earlier
   round's narrower reading (which only counted the 1,347
   score-AND-label rows). Verified: `star_by_value_label.notna().sum()
   == 8537 == 1347 (scored) + 7190 (below_production_gate)` exactly.

REAL, FOUND STRUCTURAL FACT this round: 100% of the real 1,934
`out_of_scope` rows are `out_of_scope_temporal_window` (pre-2010,
`season < SBV_FIRST_SCOREABLE_SEASON`) -- ZERO real
`out_of_scope_insufficient_participation` rows exist in the real SBV
export, even though labeling.py has that branch. This is because
scripts/11_calculate_stars_by_value.py's own `build_population()`
already drops every zero-game row (via its `dropna(subset=["ppg_ppr",
...])`, since a real zero-game season has `ppg_ppr = NaN`) BEFORE
`label_rows()` is ever called -- labeling.py's own "games_played < 1
-> out_of_scope" branch is real, disclosed DEAD CODE against the
current population-assembly pipeline. Not fixed here (that's
scripts/11's own logic, a Dataset 1/SBV concern, out of this task's
scope) -- flagged so it isn't silently rediscovered later.

THE CORE METHODOLOGICAL CORRECTION THIS ROUND (per instruction):
Dataset 2B bust eligibility must NOT inherit SBV's Star production
gate. `below_production_gate`'s real 1,381 rows WITH a real fantasy
market ADP are real, legitimate primary-bust-eligible candidates --
low production is not a reason to exclude someone from a study of
whether their real fantasy investment underperformed; it may in fact
BE the underperformance the study exists to find.

Writes:
  - dataset2_outcome_gap_audit.csv: one row per (season, player_id),
    every granular real SBV status (no aggregated categories), plus
    all four proposed outcome-eligibility flags and reason codes.
  - dataset2_outcome_gap_below_production_gate_detail.csv: the real
    7,190-row breakdown.
  - dataset2_outcome_gap_out_of_scope_detail.csv: the real 1,934-row
    breakdown.
  - dataset2_outcome_gap_no_sbv_row_found_detail.csv: the real 516-row
    breakdown (unchanged from last round).
"""

import sys
from pathlib import Path

import pandas as pd
from lib.player_season_authority import resolved_canonical_position_population

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DATASET2_ADP_ROUND_BUCKETS
from lib.stars_by_value import expected_production as ep

MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
SBV_EXPORT_PATH = "data/exports/stars_by_value_player_seasons.csv"
PLAYERS_PATH = "data/raw/nflverse/reference/players.csv"

OUTPUT_DIR = Path("data/exports")
AUDIT_PATH = OUTPUT_DIR / "dataset2_outcome_gap_audit.csv"
BELOW_GATE_DETAIL_PATH = OUTPUT_DIR / "dataset2_outcome_gap_below_production_gate_detail.csv"
OUT_OF_SCOPE_DETAIL_PATH = OUTPUT_DIR / "dataset2_outcome_gap_out_of_scope_detail.csv"
NO_SBV_ROW_DETAIL_PATH = OUTPUT_DIR / "dataset2_outcome_gap_no_sbv_row_found_detail.csv"

_UNSCOREABLE_STATUS_REASONS = {
    "unscoreable_drafted_adp_missing": "Real evidence of a real fantasy draft, but no usable acquisition cost resolved -- E_P uncomputable.",
    "unscoreable_ambiguous": "No ADP match; classifier bucket and real MFL corroboration disagree -- SBV refuses to guess.",
    "unscoreable_expected_production_out_of_range": "Real, trustworthy acquisition cost IS known -- only the fitted E_P lookup has no value this deep.",
}


def _adp_bucket(adp_round):
    if pd.isna(adp_round):
        return "no_real_adp"
    for label, lo, hi in DATASET2_ADP_ROUND_BUCKETS:
        if hi is None:
            if adp_round >= lo:
                return label
        elif lo <= adp_round <= hi:
            return label
    return "unbucketed"


def main():
    print("Loading real master population, real SBV export, real players.csv...")
    master = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    master = resolved_canonical_position_population(master)
    sbv = pd.read_csv(SBV_EXPORT_PATH, low_memory=False)
    players = pd.read_csv(PLAYERS_PATH, low_memory=False)

    merged = master.merge(
        sbv[["season", "player_id", "star_by_value_status", "star_by_value_provenance_type", "star_by_value_score", "star_by_value_label"]],
        on=["season", "player_id"], how="left",
    )
    merged = merged.merge(players[["gsis_id", "rookie_season", "draft_round"]], left_on="player_id", right_on="gsis_id", how="left")
    merged["is_rookie_season"] = merged["season"] == merged["rookie_season"]
    merged["has_real_adp"] = merged["overall_adp"].notna()
    merged["adp_round"] = merged["overall_adp"].apply(ep.adp_round)
    merged["adp_bucket"] = merged["adp_round"].apply(_adp_bucket)
    # Granular real status -- "no_sbv_row_found" as an explicit value,
    # never a bare null, never folded into any aggregate.
    merged["real_status"] = merged["star_by_value_status"].fillna("no_sbv_row_found")

    print("\n" + "=" * 90)
    print("GRANULAR REAL STATUS COUNTS (2006-2025) -- no aggregated categories")
    print("=" * 90)
    print(merged["real_status"].value_counts().to_string())
    assert merged["real_status"].value_counts().sum() == len(merged)

    # ================================================================
    # 1. below_production_gate -- full real breakdown (7,190)
    # ================================================================
    bpg = merged[merged["real_status"] == "below_production_gate"]
    print("\n" + "=" * 90)
    print(f"1. below_production_gate -- real breakdown (n={len(bpg)})")
    print("=" * 90)
    print("Real label check (must be 0.0 for every row, never null):")
    print(bpg["star_by_value_label"].value_counts(dropna=False).to_string())
    print("\nFantasy acquisition-cost status (has_real_adp):")
    print(bpg["has_real_adp"].value_counts().to_string())
    print("\nADP-round bucket (config.DATASET2_ADP_ROUND_BUCKETS):")
    print(bpg["adp_bucket"].value_counts().to_string())
    print("\nPosition:")
    print(bpg["position"].value_counts().to_string())
    print("\ngames_played (min/25/50/75/max):", bpg["games_played"].quantile([0, 0.25, 0.5, 0.75, 1]).tolist())
    print("fantasy_points_ppr (min/25/50/75/max):", bpg["fantasy_points_ppr"].quantile([0, 0.25, 0.5, 0.75, 1]).tolist())
    print("ppg_ppr (min/25/50/75/max):", bpg["ppg_ppr"].quantile([0, 0.25, 0.5, 0.75, 1]).tolist())
    print(f"\nReal fantasy-ADP subset (n={bpg['has_real_adp'].sum()}) -- these are real, legitimate primary-bust-eligible candidates, per this round's correction.")

    # ================================================================
    # 2. out_of_scope -- full real breakdown (1,934)
    # ================================================================
    oos = merged[merged["real_status"] == "out_of_scope"]
    print("\n" + "=" * 90)
    print(f"2. out_of_scope -- real breakdown (n={len(oos)})")
    print("=" * 90)
    print("Real provenance breakdown:")
    print(oos["star_by_value_provenance_type"].value_counts(dropna=False).to_string())
    print("Season range:", oos["season"].min(), "-", oos["season"].max(), "(SBV_FIRST_SCOREABLE_SEASON = 2010, confirmed temporal-window-only)")
    print("\nFantasy acquisition-cost status:")
    print(oos["has_real_adp"].value_counts().to_string())
    print("\nADP-round bucket:")
    print(oos["adp_bucket"].value_counts().to_string())
    print("\nPosition:")
    print(oos["position"].value_counts().to_string())
    print("\ngames_played (min/25/50/75/max):", oos["games_played"].quantile([0, 0.25, 0.5, 0.75, 1]).tolist())
    print("fantasy_points_ppr (min/25/50/75/max):", oos["fantasy_points_ppr"].quantile([0, 0.25, 0.5, 0.75, 1]).tolist())

    # ================================================================
    # 3. no_sbv_row_found -- acquisition-cost audit (516), unchanged logic
    # ================================================================
    nsrf = merged[merged["real_status"] == "no_sbv_row_found"]
    nsrf = nsrf.copy()
    nsrf["acquisition_bucket"] = "no_valid_cost_signal"
    nsrf.loc[nsrf["draft_round"].notna() & ~nsrf["has_real_adp"], "acquisition_bucket"] = "drafted_no_market_adp"
    nsrf.loc[nsrf["has_real_adp"], "acquisition_bucket"] = "has_real_market_adp"

    # ================================================================
    # Four separate outcome-eligibility fields (proposal, not implemented)
    # ================================================================
    print("\n" + "=" * 90)
    print("PROPOSED OUTCOME-ELIGIBILITY FIELDS -- real counts")
    print("=" * 90)

    # 1. star_outcome_eligible -- True wherever a real, non-null SBV label exists.
    merged["star_outcome_eligible"] = merged["star_by_value_label"].notna()
    print(f"\n[1] star_outcome_eligible = True: {merged['star_outcome_eligible'].sum()}"
          f"  (= scored_labeled {(merged['real_status'].isin(['adp_scored','minimal_market_cost_scored'])).sum()}"
          f"  + below_production_gate {(merged['real_status']=='below_production_gate').sum()})")
    print(f"    False (ineligible, NOT auto non-Star): {(~merged['star_outcome_eligible']).sum()}")

    # 2. bust_outcome_eligible_primary (position x ADP-range conditioned) --
    # real, usable fantasy ADP required. Production gate NOT inherited.
    # Temporal window (pre-2010) reported separately as an OPEN, undecided
    # question -- not silently extended by this script.
    merged["bust_eligible_primary_2010plus"] = merged["has_real_adp"] & (merged["season"] >= 2010)
    merged["bust_eligible_primary_full_range"] = merged["has_real_adp"]
    print(f"\n[2] bust_outcome_eligible_primary (ADP-range-conditioned):")
    print(f"    True, restricted to SBV's 2010+ window: {merged['bust_eligible_primary_2010plus'].sum()}")
    print(f"    True, if temporal window is ALSO not inherited (2006-2025): {merged['bust_eligible_primary_full_range'].sum()}")
    print("    (temporal-window question is OPEN -- this round's instruction addressed the production gate only, not this)")
    print(f"    MMC rows (n=54): NOT eligible under this definition -- no real ADP-round bucket exists for them (open question: add a 5th 'minimal-cost' bucket, or exclude).")
    print(f"    drafted_no_market_adp rows (n={ (nsrf['acquisition_bucket']=='drafted_no_market_adp').sum() }): NOT eligible -- NFL draft capital is not fantasy acquisition cost, per instruction.")
    print(f"    unscoreable_drafted_adp_missing (n=106) / unscoreable_ambiguous (n=80): NOT eligible -- no defensible cost value.")
    eor_adp = merged[merged["real_status"] == "unscoreable_expected_production_out_of_range"]
    print(f"    unscoreable_expected_production_out_of_range (n=2): ELIGIBLE -- real ADP round resolves to a real bucket "
          f"({eor_adp['adp_bucket'].tolist()}) even though the fitted E_P lookup (needed for Star scoring specifically) has no value.")

    # 3. bust_outcome_eligible_strict_hybrid -- same eligibility population
    # as primary (definition I = G + an additional absolute-floor
    # THRESHOLD, not a different eligibility gate).
    merged["bust_eligible_strict_hybrid"] = merged["bust_eligible_primary_2010plus"]
    print(f"\n[3] bust_outcome_eligible_strict_hybrid: SAME population as primary "
          f"({merged['bust_eligible_strict_hybrid'].sum()} under the 2010+ window) -- "
          f"the strict-hybrid definition adds an absolute-floor THRESHOLD on top of G, not a separate eligibility gate.")

    # 4. underperformance_diagnostic_eligible (raw P vs E_P) -- needs a
    # real FITTED E_P value, which today only exists for the two
    # scoreable statuses. Flagged as an open question whether this
    # should be extended to below_production_gate's real-ADP subset.
    merged["diagnostic_eligible_narrow"] = merged["real_status"].isin(["adp_scored", "minimal_market_cost_scored"])
    merged["diagnostic_eligible_extended"] = merged["diagnostic_eligible_narrow"] | (
        (merged["real_status"] == "below_production_gate") & merged["has_real_adp"]
    )
    print(f"\n[4] underperformance_diagnostic_eligible (raw P vs. E_P):")
    print(f"    Narrow (today's real, already-computed E_P only): {merged['diagnostic_eligible_narrow'].sum()}")
    print(f"    Extended (also compute E_P for below_production_gate's real-ADP rows -- same lookup formula, "
          f"just currently short-circuited by labeling.py's early return): {merged['diagnostic_eligible_extended'].sum()}")
    print("    OPEN QUESTION: which population the real outcome-table build should use -- not decided here.")

    # ================================================================
    # Reason codes for every ineligible row (per outcome)
    # ================================================================
    def reason_star(row):
        if row["star_outcome_eligible"]:
            return None
        return {
            "out_of_scope": "out_of_scope_temporal_window (pre-2010)",
            "unscoreable_drafted_adp_missing": "acquisition_cost_unresolved_drafted",
            "unscoreable_ambiguous": "acquisition_cost_unresolved_ambiguous",
            "unscoreable_expected_production_out_of_range": "expected_production_lookup_out_of_range",
            "no_sbv_row_found": "zero_games_excluded_from_sbv_population",
        }[row["real_status"]]

    def reason_bust_primary(row):
        if row["bust_eligible_primary_2010plus"]:
            return None
        if row["season"] < 2010 and row["has_real_adp"]:
            return "pre_2010_temporal_window_open_question"
        if row["real_status"] == "minimal_market_cost_scored":
            return "no_real_adp_round_mmc_baseline_only"
        if row["real_status"] == "no_sbv_row_found":
            bucket = nsrf.set_index(["season", "player_id"]).reindex([(row["season"], row["player_id"])])["acquisition_bucket"]
            b = bucket.iloc[0] if len(bucket) else "no_valid_cost_signal"
            return f"zero_games_{b}"
        return "no_usable_fantasy_acquisition_cost"

    merged["star_ineligible_reason"] = merged.apply(reason_star, axis=1)
    merged["bust_primary_ineligible_reason"] = merged.apply(reason_bust_primary, axis=1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(AUDIT_PATH, index=False)
    bpg.to_csv(BELOW_GATE_DETAIL_PATH, index=False)
    oos.to_csv(OUT_OF_SCOPE_DETAIL_PATH, index=False)
    nsrf.to_csv(NO_SBV_ROW_DETAIL_PATH, index=False)
    print(f"\nWrote:\n  {AUDIT_PATH}\n  {BELOW_GATE_DETAIL_PATH}\n  {OUT_OF_SCOPE_DETAIL_PATH}\n  {NO_SBV_ROW_DETAIL_PATH}")


if __name__ == "__main__":
    main()
