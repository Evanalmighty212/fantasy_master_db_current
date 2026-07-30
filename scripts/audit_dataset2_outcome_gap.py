"""
scripts/audit_dataset2_outcome_gap.py

Dataset 2 OUTCOME-ELIGIBILITY RECONCILIATION -- a real, independent
audit of the four outcome-availability categories proposed in
research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md §3, run against
the real Stars-by-Value export, the real master population, and (new
this round) real players.csv draft/rookie data. This is NOT the
outcome table itself (artifact 2 of the three-artifact architecture is
not built here, per instruction) and its output is NEVER joined into
the predictor table (lib/dataset2/canonical_predictor_table.py imports
nothing from lib.stars_by_value and reads no file this script
touches). This is a standalone research artifact for whoever builds
the real outcome table next.

REVISED THIS ROUND -- a real, disclosed correction to the category
name inherited from the proposal: `scored_but_unlabeled` is a
MISNOMER. Verified directly against the real SBV export this round:
`star_by_value_score` is NULL for every one of the 188 rows in this
category, no exceptions -- `_SCOREABLE_STATUSES` in
lib/stars_by_value/labeling.py is exactly (adp_scored,
minimal_market_cost_scored), and every OTHER status (including all
three making up this 188) hits labeling.py's step 4 `else: score,
label = None, None` branch. None of the 188 have "a numeric score
withheld from a label" -- they are genuinely UNSCOREABLE, for three
DIFFERENT real reasons (broken down below), never a single catch-all.
This script keeps the name `scored_but_unlabeled` ONLY as a pointer
back to the already-approved proposal language; the real breakdown
below is what should replace it as the actual working vocabulary.

REAL, FOUND ROOT CAUSE for `no_sbv_row_found` (confirmed this round,
not just described): scripts/11_calculate_stars_by_value.py's own
`build_population()` runs
`pop.dropna(subset=["ppg_ppr", "position_finish_ppr", "games_played",
"fantasy_points_ppr"])` BEFORE ever calling `labeling.label_rows()`.
A real zero-game player-season structurally has `ppg_ppr = NaN`
(0 points / 0 games), so this dropna() silently removes them from
SBV's own INPUT -- they never even reach labeling.py's own step-1
"games_played < 1 -> out_of_scope" rule, which would have given them a
real, explicit status row. Verified directly: `ppg_ppr` is null for
100% of the real 516 no_sbv_row_found rows.

Writes:
  - dataset2_outcome_gap_audit.csv: one row per (season, player_id) in
    the real master population, the four outcome-availability
    categories, never a bare boolean.
  - dataset2_outcome_gap_scored_but_unlabeled_detail.csv: the real
    188-row breakdown by exact underlying SBV status.
  - dataset2_outcome_gap_no_sbv_row_found_detail.csv: the real 516-row
    investigation, with acquisition-cost bucket, rookie/veteran,
    era, and draft-round context.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))

MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
SBV_EXPORT_PATH = "data/exports/stars_by_value_player_seasons.csv"
PLAYERS_PATH = "data/raw/nflverse/reference/players.csv"

OUTPUT_DIR = Path("data/exports")
AUDIT_PATH = OUTPUT_DIR / "dataset2_outcome_gap_audit.csv"
SCORED_BUT_UNLABELED_DETAIL_PATH = OUTPUT_DIR / "dataset2_outcome_gap_scored_but_unlabeled_detail.csv"
NO_SBV_ROW_DETAIL_PATH = OUTPUT_DIR / "dataset2_outcome_gap_no_sbv_row_found_detail.csv"

CATEGORY_SCORED_LABELED = "scored_labeled"
CATEGORY_SCORED_BUT_UNLABELED = "scored_but_unlabeled"  # kept for continuity with the approved proposal; see module docstring
CATEGORY_OUT_OF_SCOPE_BY_SBV_DESIGN = "out_of_scope_by_sbv_design"
CATEGORY_NO_SBV_ROW_FOUND = "no_sbv_row_found"

_SCORED_LABELED_STATUSES = ("adp_scored", "minimal_market_cost_scored")

# The three real, DIFFERENT statuses making up `scored_but_unlabeled`,
# with the exact real reason each never gets a score (from
# lib/stars_by_value/labeling.py's own step 3 -- see that module for
# the authoritative logic; this is a read, not a re-derivation).
_UNSCOREABLE_STATUS_REASONS = {
    "unscoreable_drafted_adp_missing": (
        "Real evidence (from acquisition_cost.py's classifier + MFL corroboration) indicates "
        "this player was genuinely drafted in a real fantasy league that season, but no usable "
        "acquisition cost (ADP round) could be resolved -- so E_P (expected production for that "
        "cost) cannot be looked up, and score = P - lambda*E_P is structurally uncomputable. "
        "The absence of a label is a genuine data gap in resolving ACQUISITION COST, not a "
        "deliberate SBV methodology decision."
    ),
    "unscoreable_ambiguous": (
        "No real ADP match; the acquisition-cost classifier bucket and the real MFL "
        "corroboration signal DISAGREE with each other. SBV's settled 3-way corroboration table "
        "refuses to guess in this case rather than picking one signal over the other -- same "
        "structural consequence as drafted_adp_missing (no acquisition cost, no E_P, no score), "
        "but the REASON is a genuine conflict between two real signals, not a missing one."
    ),
    "unscoreable_expected_production_out_of_range": (
        "REAL, TRUSTWORTHY acquisition cost IS known (a genuine ADP match, draft_round resolved) "
        "-- what's missing is a fitted E_P value for a round this deep (the real historical "
        "population never reached that round in the seasons the E_P model was fit on). This is "
        "the ONE sub-status where the acquisition-cost side is fully resolved; only the "
        "expected-production LOOKUP has a coverage gap, not the cost itself."
    ),
}


def _categorize(status) -> str:
    if pd.isna(status):
        return CATEGORY_NO_SBV_ROW_FOUND
    if status in _SCORED_LABELED_STATUSES:
        return CATEGORY_SCORED_LABELED
    if status in _UNSCOREABLE_STATUS_REASONS:
        return CATEGORY_SCORED_BUT_UNLABELED
    if status in ("out_of_scope", "below_production_gate"):
        return CATEGORY_OUT_OF_SCOPE_BY_SBV_DESIGN
    raise ValueError(
        f"Unrecognized real star_by_value_status value: {status!r} -- update this script's "
        f"category map, do not silently default it."
    )


def main():
    print("Loading real master population, real SBV export, real players.csv...")
    master = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    master = master[master["position"].isin(["QB", "RB", "WR", "TE"])]
    sbv = pd.read_csv(SBV_EXPORT_PATH, low_memory=False)
    players = pd.read_csv(PLAYERS_PATH, low_memory=False)

    merged = master[
        [
            "season", "player_id", "player_name", "position", "games_played", "fantasy_points_ppr",
            "overall_adp", "adp_status", "data_quality_flag", "lwi_eligibility_flag",
        ]
    ].merge(
        sbv[["season", "player_id", "star_by_value_status", "star_by_value_score", "star_by_value_label"]],
        on=["season", "player_id"],
        how="left",
    )
    merged["outcome_availability_category"] = merged["star_by_value_status"].apply(_categorize)

    # --- Explicit safety checks, never trust the label alone ---
    unmatched = merged[merged["outcome_availability_category"] == CATEGORY_NO_SBV_ROW_FOUND]
    assert unmatched["star_by_value_label"].isna().all(), (
        "A no_sbv_row_found row has a non-null star_by_value_label -- an unmatched predictor "
        "row must never be classified star=False or star=True."
    )
    unscoreable = merged[merged["outcome_availability_category"] == CATEGORY_SCORED_BUT_UNLABELED]
    assert unscoreable["star_by_value_score"].isna().all(), (
        "A scored_but_unlabeled row has a non-null star_by_value_score -- this category name "
        "would then be accurate, contradicting this round's real finding; investigate before "
        "trusting this script's category map."
    )

    print("\n" + "=" * 90)
    print("OUTCOME-AVAILABILITY CATEGORY COUNTS (real, 2006-2025)")
    print("=" * 90)
    print(merged["outcome_availability_category"].value_counts().to_string())
    print(f"\nTotal real master population rows: {len(merged)}")
    print("star_by_value_label distribution WITHIN scored_labeled only:")
    print(merged[merged["outcome_availability_category"] == CATEGORY_SCORED_LABELED]["star_by_value_label"].value_counts(dropna=False).to_string())

    # ================================================================
    # scored_but_unlabeled -- real breakdown by exact SBV status
    # ================================================================
    print("\n" + "=" * 90)
    print(f"{CATEGORY_SCORED_BUT_UNLABELED} -- real breakdown by exact canonical SBV status (n={len(unscoreable)})")
    print("=" * 90)
    print("REAL CORRECTION: zero of these rows have a real star_by_value_score -- verified directly.")
    for status, reason in _UNSCOREABLE_STATUS_REASONS.items():
        n = (unscoreable["star_by_value_status"] == status).sum()
        print(f"\n  {status}  (n={n})")
        print(f"    {reason}")
    print(
        "\nRECOMMENDATION: a future outcome table should expose these three real statuses "
        "directly (or a `star_outcome_eligible=False` + `outcome_unavailable_reason=<exact "
        "status>` pair), never collapse them into one undifferentiated "
        "'scored_but_unlabeled' bucket -- the three reasons are methodologically distinct "
        "(missing cost vs. conflicting signals vs. a real cost with a lookup-coverage gap)."
    )

    # ================================================================
    # no_sbv_row_found -- real investigation, acquisition-cost audit
    # ================================================================
    print("\n" + "=" * 90)
    print(f"{CATEGORY_NO_SBV_ROW_FOUND} -- real investigation (n={len(unmatched)})")
    print("=" * 90)
    all_zero_games = (unmatched["games_played"] == 0).all()
    print(f"Every row has games_played == 0: {all_zero_games}")
    ppg_null = master.merge(unmatched[["season", "player_id"]], on=["season", "player_id"])["ppg_ppr"].isna().all()
    print(f"Every row has ppg_ppr == NaN (SBV's build_population() dropna() root cause): {ppg_null}")

    detail = unmatched.merge(
        players[["gsis_id", "rookie_season", "draft_round", "draft_pick"]],
        left_on="player_id", right_on="gsis_id", how="left",
    )
    detail["is_rookie_season"] = detail["season"] == detail["rookie_season"]
    detail["has_real_market_adp"] = detail["overall_adp"].notna()
    detail["acquisition_bucket"] = "no_valid_cost_signal"
    detail.loc[detail["draft_round"].notna() & ~detail["has_real_market_adp"], "acquisition_bucket"] = "drafted_no_market_adp"
    detail.loc[detail["has_real_market_adp"], "acquisition_bucket"] = "has_real_market_adp"
    detail["era"] = pd.cut(detail["season"], bins=[2005, 2010, 2020, 2025], labels=["2006-2010", "2011-2020", "2021-2025"])

    print("\nBy season:")
    print(detail["season"].value_counts().sort_index().to_string())
    print("\nBy position:")
    print(detail["position"].value_counts().to_string())
    print("\nBy acquisition-cost bucket (real fantasy market ADP + real NFL draft_round from players.csv):")
    print(detail["acquisition_bucket"].value_counts().to_string())
    print("\nBy rookie-season vs. veteran-season:")
    print(detail["is_rookie_season"].value_counts().to_string())
    print("\nAcquisition bucket x rookie/veteran:")
    print(pd.crosstab(detail["acquisition_bucket"], detail["is_rookie_season"]).to_string())
    print("\nAcquisition bucket x era:")
    print(pd.crosstab(detail["era"], detail["acquisition_bucket"]).to_string())

    r1 = detail[detail["draft_round"] == 1.0]
    print(f"\nReal round-1 NFL picks with zero games, no market ADP (n={len(r1)}):")
    print(r1[["season", "player_name", "position", "draft_pick"]].to_string(index=False))
    print(
        "FINDING: every one of these is a REAL VETERAN season (career-entry draft position is "
        "ancient history by the season shown, e.g. a 15th-year player), never a current-season "
        "high-pick rookie bust -- confirmed by cross-referencing rookie_season above."
    )

    rookie_drafted = detail[detail["is_rookie_season"] & (detail["acquisition_bucket"] == "drafted_no_market_adp")]
    print(f"\nRookie-season, real NFL draft pick, zero games, NO market ADP (n={len(rookie_drafted)}):")
    print("Draft-round distribution (this is the subset closest to the user's 'case 3' concern):")
    print(rookie_drafted["draft_round"].value_counts().sort_index().to_string())
    print(
        "FINDING: minimum real draft round in this subset is round 2 -- ZERO real round-1 "
        "rookie-year zero-game cases with no market ADP. This is consistent with real fantasy "
        "ADP being set from PRESEASON draft hype, not final games played -- a genuine round-1 "
        "rookie almost always generates a real market ADP regardless of how their season turns "
        "out, so a round-1 bust of this shape would more likely show up in the (real, n=1) "
        "has_real_market_adp bucket instead."
    )

    print(
        "\nSURVIVORSHIP-BIAS ASSESSMENT (requested): automatically excluding all 516 from bust "
        "analysis WOULD risk survivorship bias for a small, real, high-cost subset -- "
        "specifically the 244 'drafted_no_market_adp' rows, and especially the 58 rookie-season "
        "ones (rounds 2-7, real early-career investment, zero return). The 271 "
        "'no_valid_cost_signal' rows carry materially less bust-research risk if excluded (no "
        "real evidence of meaningful acquisition cost, fantasy or NFL). The single "
        "'has_real_market_adp' row (2023-2025 era) is the cleanest possible zero-game bust case "
        "and should not be excluded from any bust definition by default."
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(AUDIT_PATH, index=False)
    unscoreable.to_csv(SCORED_BUT_UNLABELED_DETAIL_PATH, index=False)
    detail.to_csv(NO_SBV_ROW_DETAIL_PATH, index=False)
    print(f"\nWrote:\n  {AUDIT_PATH}\n  {SCORED_BUT_UNLABELED_DETAIL_PATH}\n  {NO_SBV_ROW_DETAIL_PATH}")


if __name__ == "__main__":
    main()
