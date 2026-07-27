"""
lib/dataset2/prior_finish_traits.py

Dataset 2 family #7 (previous-season finish) -- FEATURE CONSTRUCTION
ONLY. Produces prior_overall_finish, prior_positional_finish, and
prior_ppg via strictly-lagged (season N-1) self-joins against the
master DB's own history, using the same lag_join() helper as
lib/dataset2/prior_season_traits.py.

Deliberately does NOT contain any Star-rate/bust-rate reporting or
ADP-conditioning logic -- per the approved decision to keep feature
construction structurally separate from empirical analysis and
conclusions. See lib/dataset2/prior_finish_analysis.py for the three
required, separate analysis functions (raw / ADP-conditioned /
market-pricing) that CONSUME this module's output; nothing in this
module reports a rate or a finding.

ROOKIE HANDLING (matches docs/LEAGUE_WINNER_TRAITS_SPEC.md's "Rookies
need a separate feature path, not exclusion"): a player's first season
has no season N-1 row to lag from, so all three fields are null --
same convention as prior_season_traits.py, not a gap to fix.

TEST SCOPE: tests/test_dataset2_prior_finish_traits.py proves
implementation correctness against synthetic fixtures only. Real-data
integration and coverage validation has not happened yet -- same
required checkpoint as this module's siblings, see
research/dataset2/DATASET2_TRAIT_ROADMAP.md §6.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import lag_join, validate_columns

POPULATION_REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "position",
    "overall_finish_ppr",
    "position_finish_ppr",
    "ppg_ppr",
)

OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "prior_overall_finish",
    "prior_positional_finish",
    "prior_ppg",
)


def build_prior_finish_traits(population: pd.DataFrame) -> pd.DataFrame:
    """
    Builds family #7's three trait variables for every row in
    `population`. `population` must already be the caller's scoped
    Dataset 2 population and must contain every (season, player_id)
    row needed to look up the prior season -- same "pass the full
    multi-season population" requirement as prior_season_traits.py.

    Returns one row per (season, player_id, position) with every
    column in OUTPUT_COLUMNS.
    """
    validate_columns(population, POPULATION_REQUIRED_COLUMNS, "population")

    base = population[list(POPULATION_REQUIRED_COLUMNS)].drop_duplicates(
        subset=["season", "player_id"]
    ).reset_index(drop=True)

    base["prior_overall_finish"] = lag_join(base, "overall_finish_ppr", 1)
    base["prior_positional_finish"] = lag_join(base, "position_finish_ppr", 1)
    base["prior_ppg"] = lag_join(base, "ppg_ppr", 1)

    return base[list(OUTPUT_COLUMNS)].reset_index(drop=True)
