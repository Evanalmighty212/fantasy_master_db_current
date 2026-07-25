"""
lib/stars_by_value/minimal_market_cost.py

Minimal-market-cost expected production: the substitute numeric
baseline used wherever acquisition_cost.py (Commit 7) classifies a
row as minimal_market_cost_scored -- there is no real ADP round to
look up E_P(round) against for these rows, so this formula supplies
the substitute expectation instead.

FORMULA (research/dataset3/STARS_BY_VALUE_METHODOLOGY.md section 9, settled):
    MMC_E_P(position, season) = opportunity_probability(position)
                                 * SBV_MMC_ROLE_CONDITIONAL_DISCOUNT
                                 * replacement_ppg(position)
                                 * season_length(season)

SBV_MMC_ROLE_CONDITIONAL_DISCOUNT is its OWN dedicated config constant
(currently 0.5), deliberately separate from SBV_PRODUCTION_WEIGHT_AATP
even though the two currently share a value. They are different
quantities: this one is a role-conditional production discount ("if
this player gets real opportunity, they'd produce at roughly half
replacement-level rate", section 9); SBV_PRODUCTION_WEIGHT_AATP is the
AATP/PPG_AR_eq_shrunk composite weight in production.py. Reusing one
constant for both was considered and rejected -- they must be free to
move independently if either is ever recalibrated (see config.py's
comment on SBV_MMC_ROLE_CONDITIONAL_DISCOUNT).

SCOPE: this module computes exactly one number from (position,
season). It does not know about acquisition-cost classification,
scoring, or final labeling -- it never imports acquisition_cost.py or
labeling logic. It DOES reuse production.py's season_length() (the
single settled 16/17-game-era cutover), rather than re-deriving the
season-length rule a second time.
"""

import math
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import (
    SBV_MMC_OPPORTUNITY_PROBABILITY,
    SBV_MMC_REPLACEMENT_PPG,
    SBV_MMC_ROLE_CONDITIONAL_DISCOUNT,
    SBV_POSITIONS,
)
from lib.stars_by_value.production import season_length


def minimal_market_cost_expected_production(position: str, season: int) -> float:
    """MMC_E_P(position, season) -- see module docstring for the
    formula. Fails loudly (never guesses, never silently substitutes a
    default) on: an unsupported position, a non-integer season, a
    config dict missing an expected position key, or a non-finite
    result."""
    if position not in SBV_POSITIONS:
        raise ValueError(f"Unsupported position {position!r} -- must be one of {SBV_POSITIONS}")
    if not isinstance(season, int) or isinstance(season, bool):
        raise ValueError(f"season must be an integer, got {season!r} ({type(season).__name__})")

    if position not in SBV_MMC_OPPORTUNITY_PROBABILITY:
        raise ValueError(f"SBV_MMC_OPPORTUNITY_PROBABILITY is missing a key for position {position!r}")
    if position not in SBV_MMC_REPLACEMENT_PPG:
        raise ValueError(f"SBV_MMC_REPLACEMENT_PPG is missing a key for position {position!r}")

    opportunity_probability = SBV_MMC_OPPORTUNITY_PROBABILITY[position]
    replacement_ppg = SBV_MMC_REPLACEMENT_PPG[position]
    games = season_length(season)

    result = opportunity_probability * SBV_MMC_ROLE_CONDITIONAL_DISCOUNT * replacement_ppg * games

    if not math.isfinite(result):
        raise ValueError(
            f"minimal_market_cost_expected_production({position!r}, {season}) produced a "
            f"non-finite value ({result}) -- opportunity_probability={opportunity_probability}, "
            f"SBV_MMC_ROLE_CONDITIONAL_DISCOUNT={SBV_MMC_ROLE_CONDITIONAL_DISCOUNT}, "
            f"replacement_ppg={replacement_ppg}, season_length={games}"
        )

    return result
