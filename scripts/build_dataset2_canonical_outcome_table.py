"""
scripts/build_dataset2_canonical_outcome_table.py

Real-data driver for lib.dataset2.canonical_outcome_table -- builds
artifact 2 of the three-artifact architecture
(research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md §1a) and writes
it deterministically to data/exports/ (gitignored, pipeline-
regenerated, per CLAUDE.md). NEVER joined with the canonical predictor
table -- that join is artifact 3, still not built.

Reuses lib.stars_by_value.production.compute_production() directly
(never reimplemented) to get real P values for the population this
outcome table needs -- every row with a real, non-null `ppg_ppr`
(i.e., every row that could ever reach SBV's own production-gate
check), which excludes the 516 real zero-game rows (they have
`ppg_ppr = NaN` -- handled instead by the automatic zero-game bust
rule inside canonical_outcome_table.py, not by this driver).

As of the 2026-07 label-implementation round, this also produces the
real, computed `bust_primary_label` /
`bust_primary_sensitivity_pct25_label` /
`bust_primary_sensitivity_pct30_label` /
`bust_strict_below_replacement_label` values (approved formula, see
research/dataset2/DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md
§23) -- master_population must include `games_played` (the automatic
zero-game rule needs it directly, not just as a proxy for missing P).

Writes:
  - dataset2_canonical_outcome_table.parquet / .csv
  - dataset2_canonical_outcome_table_data_dictionary.csv
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.canonical_outcome_table import OUTCOME_OUTPUT_COLUMNS, build_canonical_outcome_table
from lib.stars_by_value import production as prod

MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
SBV_EXPORT_PATH = "data/exports/stars_by_value_player_seasons.csv"
PLAYERS_PATH = "data/raw/nflverse/reference/players.csv"
EP_LOOKUP_PATH = "data/processed/sbv_expected_production_lookup.parquet"

OUTPUT_DIR = Path("data/exports")
PARQUET_PATH = OUTPUT_DIR / "dataset2_canonical_outcome_table.parquet"
CSV_PATH = OUTPUT_DIR / "dataset2_canonical_outcome_table.csv"
DICTIONARY_PATH = OUTPUT_DIR / "dataset2_canonical_outcome_table_data_dictionary.csv"

_COLUMN_REGISTRY = [
    {"canonical_column": "outcome_season", "meaning": "The real season the outcome describes (never a lagged/prediction season -- this artifact is outcomes only).", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "player_id", "meaning": "gsis_id, matches the predictor table's own player_id.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "position", "meaning": "From the master population.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "real_status", "meaning": "The granular real SBV status, or 'no_sbv_row_found' -- never an aggregated category.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "has_real_market_adp", "meaning": "True iff a real fantasy market ADP exists (overall_adp non-null).", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "adp_round", "meaning": "ceil(overall_adp / TEAMS), via lib.stars_by_value.expected_production.adp_round() -- null if no real ADP.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "star_outcome_eligible", "meaning": "True wherever a real, non-null star_by_value_label exists -- includes below_production_gate (real, deliberate label=False).", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "star_outcome_ineligibility_reason", "meaning": "Null iff eligible; else one of: out_of_scope_temporal_window, zero_games_excluded_from_sbv_population, acquisition_cost_unresolved_drafted, acquisition_cost_unresolved_ambiguous, expected_production_lookup_out_of_range.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "star_by_value_label", "meaning": "Real, nullable boolean -- False is a real, deliberate value (below_production_gate), never confused with <NA> (ineligible). This is the Star outcome and eligibility infrastructure -- fully implemented.", "implementation_status": "implemented", "usable_as_target": True},
    {"canonical_column": "sbv_score_available", "meaning": "True only for adp_scored/minimal_market_cost_scored -- SEPARATE from star_outcome_eligible; a below-gate row is eligible with no score.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "star_by_value_score", "meaning": "Real SBV score, only where sbv_score_available.", "implementation_status": "implemented", "usable_as_target": True},
    {"canonical_column": "bust_primary_eligible", "meaning": "True iff real market ADP AND outcome_season >= 2010. Does NOT require clearing SBV's production gate.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "bust_primary_ineligibility_reason", "meaning": "Null iff eligible; else one of: pre_2010_temporal_window_real_adp, mmc_no_real_adp_round_peer_group, acquisition_cost_unresolved_drafted, acquisition_cost_unresolved_ambiguous, no_real_fantasy_adp_below_production_gate, no_real_fantasy_adp_pre_2010, zero_games_nfl_draft_capital_not_fantasy_adp, zero_games_no_valid_cost_signal.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "bust_primary_assignment_method", "meaning": "Categorical, null if ineligible: era_specific_g_score (ranked within real position x ADP-bucket x era cell, n>=DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE), pooled_era_g_score_fallback (era cell too small, ranked pooled across era instead -- mechanical, pre-specified), g_raw_lookup_gap_fallback (no fitted E_P cell, ranked on raw P within the pooled cell instead), automatic_zero_game (games_played==0, bypasses ranking entirely). Shared by bust_primary_label, both sensitivities, and bust_strict_below_replacement_label -- describes the ranking mechanism, not a per-threshold decision.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "bust_primary_label", "meaning": "Bottom 20% within (position, ADP bucket, era) via bust_primary_assignment_method's mechanism -- IMPLEMENTED, approved formula per research/dataset2/DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md §23. Real nullable boolean; null iff bust_primary_eligible is False.", "implementation_status": "implemented", "usable_as_target": True},
    {"canonical_column": "bust_primary_sensitivity_pct25_label", "meaning": "Same population/ranking as bust_primary_label, bottom 25% cutoff instead of 20% -- a named SENSITIVITY, never the primary label.", "implementation_status": "implemented", "usable_as_target": True},
    {"canonical_column": "bust_primary_sensitivity_pct30_label", "meaning": "Same population/ranking as bust_primary_label, bottom 30% cutoff -- a named SENSITIVITY, never the primary label.", "implementation_status": "implemented", "usable_as_target": True},
    {"canonical_column": "bust_strict_below_replacement_eligible", "meaning": "Same population as bust_primary_eligible.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "bust_strict_below_replacement_ineligibility_reason", "meaning": "Same as bust_primary_ineligibility_reason.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "bust_strict_below_replacement_label", "meaning": "bust_primary_label (bottom 20%) AND P<0 (real, parameter-free below-replacement floor -- P is already defined relative to replacement level). Zero-game rows get automatic True by the same replacement-level argument. Explicitly named to be unambiguous: 'primary bust AND below replacement level', not a generic 'strict' label.", "implementation_status": "implemented", "usable_as_target": True},
    {"canonical_column": "bust_historical_sensitivity_eligible", "meaning": "True iff real market ADP, WITHOUT the >=2010 restriction -- a named, explicit sensitivity population including the 521 real pre-2010-ADP rows.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "bust_historical_sensitivity_ineligibility_reason", "meaning": "Same reason vocabulary as bust_primary, minus the pre-2010 branch (never fires here).", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "bust_historical_sensitivity_label", "meaning": "RESERVED, always <NA> this round -- see the bust-label operationalization proposal.", "implementation_status": "reserved_not_computed", "usable_as_target": False},
    {"canonical_column": "underperformance_diagnostic_eligible", "meaning": "True for adp_scored/minimal_market_cost_scored/below_production_gate WITH a real, non-extrapolated E_P value. Computed before any production-gate check. Three counts, kept distinct: 2,728 = theoretically eligible (real ADP + measurable production); 2,711 = computationally eligible under the CURRENT fitted E_P lookup (this column's real True count); 17 = ineligible from the 2,728 solely because their real ADP round has no fitted (season, position) E_P cell -- not extrapolated around, per instruction.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "underperformance_diagnostic_ineligibility_reason", "meaning": "Null iff eligible; else one of: outside_diagnostic_population (not adp_scored/mmc_scored/below_production_gate), no_usable_fantasy_acquisition_cost (below_production_gate row with NO real ADP at all -- never had a cost to look up), expected_production_lookup_out_of_range (real ADP exists but the fitted E_P lookup has no cell for that season/position/round -- the 17-row gap plus the 2 already-known unscoreable rows; kept a DISTINCT reason from no_usable_fantasy_acquisition_cost, never conflated), production_composite_unavailable.", "implementation_status": "implemented", "usable_as_target": False},
    {"canonical_column": "underperformance_diagnostic_value", "meaning": "Real P - E_P (raw, unweighted -- NOT the same as star_by_value_score, which uses SBV_LAMBDA). Null unless eligible.", "implementation_status": "implemented", "usable_as_target": True},
]


def _load_master_population() -> pd.DataFrame:
    df = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    return df[df["position"].isin(["QB", "RB", "WR", "TE"])]


def _load_sbv() -> pd.DataFrame:
    return pd.read_csv(SBV_EXPORT_PATH, low_memory=False)


def _load_players() -> pd.DataFrame:
    return pd.read_csv(PLAYERS_PATH, low_memory=False)


def _load_ep_lookup() -> pd.DataFrame:
    return pd.read_parquet(EP_LOOKUP_PATH)


def _compute_production(master_population: pd.DataFrame) -> pd.DataFrame:
    """Real P for every row this outcome table's diagnostic could ever
    need -- every row with a real, non-null ppg_ppr (excludes the 516
    real zero-game rows, which are outside the diagnostic's own
    population anyway -- see canonical_outcome_table.py docstring).
    Reuses production.compute_production() directly, never
    reimplemented."""
    pop = master_population.dropna(subset=["ppg_ppr", "position_finish_ppr", "games_played", "fantasy_points_ppr"]).copy()
    pop["adp_matched"] = pop["data_quality_flag"].isin(["matched_clean", "matched_needs_review"])
    prod_input = pop[["season", "player_id", "position", "games_played", "fantasy_points_ppr", "ppg_ppr", "position_finish_ppr", "adp_matched"]].copy()
    return prod.compute_production(prod_input)[["season", "player_id", "P"]]


def main():
    print("Loading real master population, SBV export, players.csv, E_P lookup...")
    master_population = _load_master_population()
    sbv_status = _load_sbv()
    players_df = _load_players()
    ep_lookup = _load_ep_lookup()

    print("Computing real P (production composite) via lib.stars_by_value.production.compute_production()...")
    production_df = _compute_production(master_population)
    print(f"  P computed for {len(production_df)} real rows (excludes {len(master_population) - len(production_df)} real zero-game rows with null ppg_ppr)")

    print("\nBuilding canonical outcome table...")
    outcome_table = build_canonical_outcome_table(master_population, sbv_status, players_df, ep_lookup, production_df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outcome_table.to_parquet(PARQUET_PATH, index=False, engine="fastparquet")
    outcome_table.to_csv(CSV_PATH, index=False)
    pd.DataFrame(_COLUMN_REGISTRY).to_csv(DICTIONARY_PATH, index=False)

    # --- Determinism check ---
    outcome_table_2 = build_canonical_outcome_table(master_population, sbv_status, players_df, ep_lookup, production_df)
    deterministic = (
        outcome_table.to_csv(index=False) == outcome_table_2.to_csv(index=False)
        and list(outcome_table.columns) == list(outcome_table_2.columns)
    )

    print("\n" + "=" * 90)
    print("CANONICAL OUTCOME TABLE -- SUMMARY")
    print("=" * 90)
    print(f"Row count: {len(outcome_table)}")
    print(f"Column count: {len(outcome_table.columns)}")
    print(f"Deterministic rebuild: {deterministic}")
    print(f"Duplicate (outcome_season, player_id) keys: {outcome_table.duplicated(subset=['outcome_season','player_id']).sum()}")

    print("\n--- Eligibility counts (real) ---")
    print(f"star_outcome_eligible:                  {outcome_table['star_outcome_eligible'].sum()}")
    print(f"  of which sbv_score_available:          {outcome_table['sbv_score_available'].sum()}")
    print(f"bust_primary_eligible:                   {outcome_table['bust_primary_eligible'].sum()}")
    print(f"bust_strict_below_replacement_eligible:   {outcome_table['bust_strict_below_replacement_eligible'].sum()}")
    print(f"bust_historical_sensitivity_eligible:     {outcome_table['bust_historical_sensitivity_eligible'].sum()}")
    print(f"underperformance_diagnostic_eligible:     {outcome_table['underperformance_diagnostic_eligible'].sum()}")

    print("\n--- star_outcome_ineligibility_reason breakdown ---")
    print(outcome_table["star_outcome_ineligibility_reason"].value_counts(dropna=False).to_string())
    print("\n--- bust_primary_ineligibility_reason breakdown ---")
    print(outcome_table["bust_primary_ineligibility_reason"].value_counts(dropna=False).to_string())
    print("\n--- bust_historical_sensitivity_ineligibility_reason breakdown ---")
    print(outcome_table["bust_historical_sensitivity_ineligibility_reason"].value_counts(dropna=False).to_string())
    print("\n--- underperformance_diagnostic_ineligibility_reason breakdown ---")
    print(outcome_table["underperformance_diagnostic_ineligibility_reason"].value_counts(dropna=False).to_string())

    # --- Reason-code completeness check, printed not just tested ---
    for eligible_col, reason_col in (
        ("star_outcome_eligible", "star_outcome_ineligibility_reason"),
        ("bust_primary_eligible", "bust_primary_ineligibility_reason"),
        ("bust_strict_below_replacement_eligible", "bust_strict_below_replacement_ineligibility_reason"),
        ("bust_historical_sensitivity_eligible", "bust_historical_sensitivity_ineligibility_reason"),
        ("underperformance_diagnostic_eligible", "underperformance_diagnostic_ineligibility_reason"),
    ):
        eligible_with_reason = (outcome_table[eligible_col] & outcome_table[reason_col].notna()).sum()
        ineligible_without_reason = ((~outcome_table[eligible_col].astype(bool)) & outcome_table[reason_col].isna()).sum()
        print(f"\n{eligible_col}: eligible-with-reason={eligible_with_reason}  ineligible-without-reason={ineligible_without_reason}")

    print("\n" + "=" * 90)
    print("BUST LABELS -- real counts and assignment-method totals")
    print("=" * 90)
    for label_col in (
        "bust_primary_label",
        "bust_primary_sensitivity_pct25_label",
        "bust_primary_sensitivity_pct30_label",
        "bust_strict_below_replacement_label",
    ):
        n_true = (outcome_table[label_col] == True).sum()  # noqa: E712
        n_eligible = outcome_table["bust_primary_eligible"].sum()
        print(f"{label_col}: {n_true} of {n_eligible} eligible ({n_true / n_eligible * 100:.1f}%)")

    print("\n--- bust_primary_assignment_method (population of bust_primary_eligible rows) ---")
    print(outcome_table["bust_primary_assignment_method"].value_counts(dropna=False).to_string())

    # An eligible row with no assignment method (games_played != 0, P
    # also null) would be an undocumented real-data gap outside all
    # four mechanisms -- verified empty against real data, not assumed.
    unhandled = outcome_table["bust_primary_eligible"] & outcome_table["bust_primary_assignment_method"].isna()
    print(f"\nEligible rows with NO assignment method (undocumented gap, expected 0): {unhandled.sum()}")

    print(f"\nWrote:\n  {PARQUET_PATH}\n  {CSV_PATH}\n  {DICTIONARY_PATH}")


if __name__ == "__main__":
    main()
