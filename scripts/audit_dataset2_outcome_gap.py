"""
scripts/audit_dataset2_outcome_gap.py

Dataset 2 OUTCOME GAP AUDIT -- a real, independent reconciliation of
the four outcome-availability categories proposed in
research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md §3, run against
the real Stars-by-Value export and the real master population. This
is NOT the outcome table itself (artifact 2 of the three-artifact
architecture is not built here, per instruction) and its output is
NEVER joined into the predictor table
(lib/dataset2/canonical_predictor_table.py imports nothing from
lib.stars_by_value and reads no file this script touches). This is a
standalone research artifact for later use by whoever builds the real
outcome table.

Explicitly required by this round's review, all done directly against
real data, never approximated:
  1. Define and COUNT `scored_but_unlabeled` (the SBV `unscoreable_*`
     statuses -- a real reason blocked a label, not a data gap).
  2. Investigate EVERY `no_sbv_row_found` case (the real predictor/SBV
     population mismatch) -- not just count it.
  3. Confirm no unmatched predictor row is ever classified `star=False`
     anywhere in this script's own output.

Writes data/exports/dataset2_outcome_gap_audit.csv (one row per
(season, player_id) in the real master population, every one of the
four category labels, never a bare boolean) and
data/exports/dataset2_outcome_gap_no_sbv_row_found_detail.csv (the
real 516-row investigation, full master-DB context per row).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))

MASTER_POPULATION_PATH = "data/master/master_historical_db_with_lwi_2006_2025.csv"
SBV_EXPORT_PATH = "data/exports/stars_by_value_player_seasons.csv"

OUTPUT_DIR = Path("data/exports")
AUDIT_PATH = OUTPUT_DIR / "dataset2_outcome_gap_audit.csv"
NO_SBV_ROW_DETAIL_PATH = OUTPUT_DIR / "dataset2_outcome_gap_no_sbv_row_found_detail.csv"

CATEGORY_SCORED_LABELED = "scored_labeled"
CATEGORY_SCORED_BUT_UNLABELED = "scored_but_unlabeled"
CATEGORY_OUT_OF_SCOPE_BY_SBV_DESIGN = "out_of_scope_by_sbv_design"
CATEGORY_NO_SBV_ROW_FOUND = "no_sbv_row_found"

_SCORED_LABELED_STATUSES = ("adp_scored", "minimal_market_cost_scored")
_SCORED_BUT_UNLABELED_STATUSES = (
    "unscoreable_drafted_adp_missing",
    "unscoreable_ambiguous",
    "unscoreable_expected_production_out_of_range",
)
_OUT_OF_SCOPE_STATUSES = ("out_of_scope", "below_production_gate")


def _categorize(status) -> str:
    if pd.isna(status):
        return CATEGORY_NO_SBV_ROW_FOUND
    if status in _SCORED_LABELED_STATUSES:
        return CATEGORY_SCORED_LABELED
    if status in _SCORED_BUT_UNLABELED_STATUSES:
        return CATEGORY_SCORED_BUT_UNLABELED
    if status in _OUT_OF_SCOPE_STATUSES:
        return CATEGORY_OUT_OF_SCOPE_BY_SBV_DESIGN
    raise ValueError(f"Unrecognized real star_by_value_status value: {status!r} -- update this script's category map, do not silently default it.")


def main():
    print("Loading real master population and real SBV export...")
    master = pd.read_csv(MASTER_POPULATION_PATH, low_memory=False)
    master = master[master["position"].isin(["QB", "RB", "WR", "TE"])]
    sbv = pd.read_csv(SBV_EXPORT_PATH, low_memory=False)

    merged = master[["season", "player_id", "player_name", "position", "games_played", "fantasy_points_ppr", "overall_adp", "adp_status", "data_quality_flag", "lwi_eligibility_flag"]].merge(
        sbv[["season", "player_id", "star_by_value_status", "star_by_value_label"]],
        on=["season", "player_id"],
        how="left",
    )
    merged["outcome_availability_category"] = merged["star_by_value_status"].apply(_categorize)

    # --- Explicit safety check: never let an unmatched row read as star=False ---
    unmatched = merged[merged["outcome_availability_category"] == CATEGORY_NO_SBV_ROW_FOUND]
    assert unmatched["star_by_value_label"].isna().all(), (
        "A no_sbv_row_found row has a non-null star_by_value_label -- this must never happen; "
        "an unmatched predictor row must never be classified star=False or star=True."
    )

    print("\n" + "=" * 90)
    print("OUTCOME-AVAILABILITY CATEGORY COUNTS (real, 2006-2025)")
    print("=" * 90)
    counts = merged["outcome_availability_category"].value_counts()
    print(counts.to_string())
    print(f"\nTotal real master population rows: {len(merged)}")
    print(f"star_by_value_label distribution WITHIN scored_labeled only:")
    print(merged[merged["outcome_availability_category"] == CATEGORY_SCORED_LABELED]["star_by_value_label"].value_counts(dropna=False).to_string())

    print("\n" + "=" * 90)
    print(f"{CATEGORY_SCORED_BUT_UNLABELED} -- real breakdown by underlying SBV status")
    print("=" * 90)
    unlabeled = merged[merged["outcome_availability_category"] == CATEGORY_SCORED_BUT_UNLABELED]
    print(unlabeled["star_by_value_status"].value_counts().to_string())

    print("\n" + "=" * 90)
    print(f"{CATEGORY_NO_SBV_ROW_FOUND} -- real investigation ({len(unmatched)} rows)")
    print("=" * 90)
    print("By season:")
    print(unmatched["season"].value_counts().sort_index().to_string())
    print("\nBy position:")
    print(unmatched["position"].value_counts().to_string())
    print("\nReal games_played distribution (min/max/mean):", unmatched["games_played"].min(), unmatched["games_played"].max(), unmatched["games_played"].mean())
    print("\nBy master DB data_quality_flag:")
    print(unmatched["data_quality_flag"].value_counts(dropna=False).to_string())
    print("\nBy master DB lwi_eligibility_flag:")
    print(unmatched["lwi_eligibility_flag"].value_counts(dropna=False).to_string())

    all_zero_games = (unmatched["games_played"] == 0).all()
    print(f"\nFINDING: every no_sbv_row_found row has games_played == 0: {all_zero_games}")
    if all_zero_games:
        print(
            "This is a real, sufficient explanation -- every one of these player-seasons has ZERO "
            "real games played, so the SBV pipeline never creates a status row for them at all "
            "(distinct from `below_production_gate`, which DOES get a row for players who played "
            "some but not enough real games). Not benign in the sense of 'ignorable' -- these are "
            "real, legitimate predictor rows (a player who was rostered but never played still has "
            "real preseason predictors) that will never have a real outcome to test against, which "
            "the outcome table's own build must represent explicitly, never silently."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(AUDIT_PATH, index=False)
    unmatched.to_csv(NO_SBV_ROW_DETAIL_PATH, index=False)
    print(f"\nWrote:\n  {AUDIT_PATH}\n  {NO_SBV_ROW_DETAIL_PATH}")


if __name__ == "__main__":
    main()
