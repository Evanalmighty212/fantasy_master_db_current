"""
human_review_export.py  (Dataset 3 research foundation, Deliverable 6)

Produces reviewable tables of historical player-seasons -- production
and acquisition cost side by side -- for manual "does this season
read as a star by value" judgment. No scoring or thresholding
decision is made here; this is a browsing aid, not a candidate metric.

THREE outputs, not two:
  - human_review_full.csv: EVERY QB/RB/WR/TE player-season with
    meaningful activity (same population as the broad historical
    dataset, games_played >= 1), nothing excluded. The
    completeness/source-of-truth file.
  - human_review_shortlist.csv: a narrower, RANK-based, POSITION-
    SPECIFIC subset for browsing. Uses 2x each position's existing
    LWI replacement threshold (imported from config.py, not
    re-typed, so this can never silently drift from LWI's own
    numbers) as the "generous" cutoff -- QB: 24, RB: 68, WR: 84,
    TE: 24. A single flat cutoff (e.g. position_finish_ppr <= 36,
    an earlier version of this file) does NOT scale correctly across
    positions with very different real depth: 36 is already 3x
    QB's own replacement level (12) but barely above RB's (34),
    meaning a flat cutoff would include far more "generous slack"
    for QB than for RB/WR -- exactly backwards, since the position
    with the shallowest roster-relevant pool (QB, 1 starter/team)
    needs the least padding, not the most.
  - human_review_shortlist_by_value.csv: a SECOND, independent
    shortlist that isn't rank-based at all -- games_played >= 8 AND
    the player beat their own overall ADP
    (overall_finish_minus_adp > 0), sorted by that margin. This
    centers cost outperformance directly, the way the rank-based
    shortlist above cannot (a player can rank outside the top 24-84
    at their position and still be a massive value relative to a
    very late cost -- the rank-based shortlist would miss them, this
    one won't).

**human_review_shortlist_by_value.csv NECESSARILY excludes every
unmatched/unresolved-ADP player-season** -- not a bug, a direct
consequence of what it measures. `overall_finish_minus_adp` requires a
real ADP to compare against; for `unresolved` rows (no ADP match),
that quantity is undefined (NaN), not zero or negative, so they can
never clear the ">0" filter. Verified directly: this file's
`draft_status` breakdown is 100% `drafted`, 0 `unresolved`. Those
excluded seasons are NOT lost from this research foundation --
they're still fully present in `human_review_full.csv` (all of them)
and in `human_review_shortlist.csv` (the rank-based one, which uses
`position_finish_ppr`, not ADP, so it doesn't have this limitation --
verified separately: that file's `draft_status` breakdown includes
both `drafted` and `unresolved` rows). Use the value shortlist for
"who beat their cost," and the rank-based shortlist or full export for
"including players current LWI can't price at all."

`overall_finish_minus_adp` (positive = beat overall draft slot,
negative = underperformed it) is carried straight through from
Component 1's existing `adp_value_raw` column -- reused, not
recomputed, so this file can never silently drift from what LWI
itself already uses for the same real quantity.

Input:  research/output/dataset3/broad_historical_dataset.csv
Output: research/output/dataset3/human_review_full.csv
        research/output/dataset3/human_review_shortlist.csv
        research/output/dataset3/human_review_shortlist_by_value.csv
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import LWI_REPLACEMENT_RANK_THRESHOLDS

BROAD_DATASET_PATH = Path("research/output/dataset3/broad_historical_dataset.csv")
OUTPUT_DIR = Path("research/output/dataset3")

SHORTLIST_MIN_GAMES = 8
# 2x each position's own LWI replacement threshold -- generous by
# construction (double what LWI itself treats as replacement level),
# but position-specific rather than one flat number applied to every
# position regardless of real depth differences. See module docstring.
SHORTLIST_RANK_MULTIPLIER = 2
SHORTLIST_MAX_POSITION_FINISH = {
    pos: threshold * SHORTLIST_RANK_MULTIPLIER
    for pos, threshold in LWI_REPLACEMENT_RANK_THRESHOLDS.items()
}

REVIEW_COLUMNS = [
    # identity
    "season", "player_name", "position", "team",
    # production
    "games_played", "fantasy_points_ppr", "ppg_ppr",
    "position_finish_ppr", "overall_finish_ppr",
    # acquisition cost
    "draft_status", "adp_matched", "overall_adp_observed", "positional_adp_observed",
    "overall_adp_model", "adp_source", "adp_value_raw",
    # current LWI, for context (not to be treated as the answer)
    "lwi_eligible", "lwi_score",
    "adp_value_component", "fantasy_finish_component", "ppg_component",
    "positional_advantage_component", "playoff_performance_component",
    "consistency_component",
]


def main():
    df = pd.read_csv(BROAD_DATASET_PATH)
    df = df.rename(columns={"adp_value_raw": "overall_finish_minus_adp"})
    # NOTE: this two-step map-then-filter order matters -- filtering
    # against df.columns BEFORE renaming "adp_value_raw" to its
    # post-rename name silently drops the column entirely (a real bug
    # caught during review: the original one-line version of this
    # checked membership before translating the name, so
    # "adp_value_raw" never matched post-rename df.columns and was
    # dropped without error).
    mapped_columns = ["overall_finish_minus_adp" if c == "adp_value_raw" else c for c in REVIEW_COLUMNS]
    cols = [c for c in mapped_columns if c in df.columns]

    full = df[cols].sort_values(["season", "position", "position_finish_ppr"], ascending=[False, True, True])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    full_path = OUTPUT_DIR / "human_review_full.csv"
    full.to_csv(full_path, index=False)
    print(f"human_review_full.csv: {len(full)} rows -> {full_path}")

    print(f"\nPosition-specific shortlist rank cutoffs (2x LWI replacement threshold): "
          f"{SHORTLIST_MAX_POSITION_FINISH}")
    rank_cutoff = full["position"].map(SHORTLIST_MAX_POSITION_FINISH)
    shortlist = full[
        (full["games_played"] >= SHORTLIST_MIN_GAMES)
        & (full["position_finish_ppr"] <= rank_cutoff)
    ]
    shortlist_path = OUTPUT_DIR / "human_review_shortlist.csv"
    shortlist.to_csv(shortlist_path, index=False)
    print(f"human_review_shortlist.csv: {len(shortlist)} rows -> {shortlist_path}")
    print(f"  by draft_status:\n{shortlist['draft_status'].value_counts().to_string()}")
    print(f"  by position:\n{shortlist['position'].value_counts().to_string()}")

    value_shortlist = full[
        (full["games_played"] >= SHORTLIST_MIN_GAMES)
        & (full["overall_finish_minus_adp"] > 0)
    ].sort_values(["season", "overall_finish_minus_adp"], ascending=[False, False])
    value_shortlist_path = OUTPUT_DIR / "human_review_shortlist_by_value.csv"
    value_shortlist.to_csv(value_shortlist_path, index=False)
    print(f"\nhuman_review_shortlist_by_value.csv: {len(value_shortlist)} rows "
          f"(games_played >= {SHORTLIST_MIN_GAMES}, beat own overall ADP) -> {value_shortlist_path}")
    print(f"  by draft_status:\n{value_shortlist['draft_status'].value_counts().to_string()}")
    print(f"  by position:\n{value_shortlist['position'].value_counts().to_string()}")

    only_in_value = set(value_shortlist.index) - set(shortlist.index)
    print(f"\nRows in the value shortlist NOT captured by the rank-based shortlist: {len(only_in_value)}"
          f" -- real examples of the rank-based cutoff missing a value story.")


if __name__ == "__main__":
    main()
