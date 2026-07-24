"""
comparison_harness.py  (Dataset 3 research foundation, Deliverable 5)

Demo/CLI entry point for lib/comparison.py's ScoringDefinition harness.
Makes it easy to score the broad historical dataset under multiple
candidate definitions and compare annual/positional qualifying counts,
top historical seasons, and rank changes -- against BOTH current LWI
and the existing relative top-10%-by-position benchmark, which stays
available as a fallback/comparison point per the task's explicit
instruction, not replaced.

This file intentionally does NOT hardcode an absolute-impact formula.
The one non-LWI ScoringDefinition below (`demo_absolute_raw_points`)
is clearly labeled DEMO-ONLY: a fixed raw-points threshold, present
only to prove the harness can express a genuinely absolute (not
per-season, not per-position-relative) rule and show how differently
its annual counts behave from the relative benchmark's. It is not a
proposal.

Run this file directly to regenerate all comparison outputs. Import
lib/comparison.py directly (not this file) to build and evaluate a
real candidate definition once one exists.

Input:  research/output/dataset3/broad_historical_dataset.csv
Output: research/output/dataset3/comparison_annual_counts.csv
        research/output/dataset3/comparison_positional_counts.csv
        research/output/dataset3/comparison_top_seasons_current_lwi.csv
        research/output/dataset3/comparison_top_seasons_demo_absolute.csv
        research/output/dataset3/comparison_rank_changes.csv
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.comparison import (
    ScoringDefinition, evaluate_definition, annual_qualifying_counts,
    positional_qualifying_counts, top_historical_seasons, rank_change_vs_baseline,
    qualifying_set_overlap, top_pct_by_position_season_qualifier, absolute_threshold_qualifier,
)

BROAD_DATASET_PATH = Path("research/output/dataset3/broad_historical_dataset.csv")
OUTPUT_DIR = Path("research/output/dataset3")


def build_definitions():
    """
    Two definitions, both usable as-is, neither a proposal for the
    final methodology:

    - current_lwi: reproduces exactly what PREDICTION_SPECIFICATION.md
      Section 2 proposes today (score = lwi_score, qualify = top 10%
      by position by season) -- the benchmark this task explicitly
      says must be preserved, not deleted. Population is restricted to
      lwi_eligible rows ONLY (2,643 of the broad dataset's 10,068 --
      i.e. exactly the population PREDICTION_SPECIFICATION.md Section
      2 means by "eligible players"), not the broader
      undrafted/unresolved-inclusive population. VERIFIED, not just
      designed this way: this definition's output (293 total
      qualifiers across 2007-2024, split QB48/RB98/TE35/WR112, with
      the identical per-season sequence 17/17/17/18/15/10/15/16/17/16/
      15/18/18/17/17/15/17/18) is byte-for-byte identical to an
      independent direct computation of PREDICTION_SPECIFICATION.md's
      rule performed separately from this harness -- confirming this
      reproduces the EXISTING target definition exactly, not a
      broadened approximation of it.
    - demo_absolute_raw_points: a DEMO-ONLY absolute-impact-shaped
      rule (fixed threshold on raw season points, same number
      regardless of season or position) to exercise the harness's
      ability to express a non-relative definition, per the stated
      "different seasons can have different numbers of winners"
      direction. The threshold (200 points) was picked only to
      produce a comparably-sized qualifying set to current_lwi for a
      fair side-by-side demo -- not a proposed real threshold.
    """
    return [
        ScoringDefinition(
            name="current_lwi",
            score_fn=lambda df: df["lwi_score"],
            qualify_fn=top_pct_by_position_season_qualifier(0.10),
        ),
        ScoringDefinition(
            name="demo_absolute_raw_points",
            score_fn=lambda df: df["fantasy_points_ppr"],
            qualify_fn=absolute_threshold_qualifier(200.0),
        ),
    ]


def main():
    df = pd.read_csv(BROAD_DATASET_PATH)
    # Restricted to LWI-eligible rows for this demo run specifically,
    # so current_lwi and demo_absolute_raw_points are compared on the
    # identical population -- a real candidate definition wanting the
    # BROADER population (including undrafted/unresolved players) can
    # call evaluate_definition() directly against the full broad
    # dataset; nothing in lib/comparison.py requires LWI-eligibility.
    eligible = df[df["lwi_eligible"]].copy()

    for definition in build_definitions():
        eligible = evaluate_definition(eligible, definition)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Annual qualifying counts ===")
    annual = []
    for name in ["current_lwi", "demo_absolute_raw_points"]:
        counts = annual_qualifying_counts(eligible, f"{name}_qualifies")
        counts["definition"] = name
        annual.append(counts)
    annual_df = pd.concat(annual, ignore_index=True)
    annual_df.to_csv(OUTPUT_DIR / "comparison_annual_counts.csv", index=False)
    pivot = annual_df.pivot(index="season", columns="definition", values="n_qualifying")
    print(pivot.to_string())
    print(f"\nStd dev across seasons -- current_lwi: {pivot['current_lwi'].std():.2f}, "
          f"demo_absolute_raw_points: {pivot['demo_absolute_raw_points'].std():.2f}")

    print("\n=== Positional qualifying counts ===")
    positional = []
    for name in ["current_lwi", "demo_absolute_raw_points"]:
        counts = positional_qualifying_counts(eligible, f"{name}_qualifies")
        counts["definition"] = name
        positional.append(counts)
    positional_df = pd.concat(positional, ignore_index=True)
    positional_df.to_csv(OUTPUT_DIR / "comparison_positional_counts.csv", index=False)
    print(positional_df.groupby(["definition", "position"])["n_qualifying"].sum().to_string())

    print("\n=== Top 25 historical seasons per definition ===")
    top_lwi = top_historical_seasons(eligible, "current_lwi_score", n=25)
    top_lwi.to_csv(OUTPUT_DIR / "comparison_top_seasons_current_lwi.csv", index=False)
    top_abs = top_historical_seasons(eligible, "demo_absolute_raw_points_score", n=25)
    top_abs.to_csv(OUTPUT_DIR / "comparison_top_seasons_demo_absolute.csv", index=False)
    print("(written to CSV -- top-25 lists omitted from console for brevity)")

    print("\n=== Rank changes: demo_absolute_raw_points vs. current_lwi ===")
    rank_changes = rank_change_vs_baseline(
        eligible, "demo_absolute_raw_points_score", "current_lwi_score"
    )
    rank_changes.to_csv(OUTPUT_DIR / "comparison_rank_changes.csv", index=False)
    print("Biggest movers UP under the demo absolute rule vs. current LWI:")
    print(rank_changes.head(10).to_string(index=False))
    print("\nBiggest movers DOWN under the demo absolute rule vs. current LWI:")
    print(rank_changes.tail(10).to_string(index=False))

    print("\n=== Qualifying-set overlap: current_lwi vs. demo_absolute_raw_points ===")
    overlap = qualifying_set_overlap(eligible, "current_lwi_qualifies", "demo_absolute_raw_points_qualifies")
    for k, v in overlap.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
