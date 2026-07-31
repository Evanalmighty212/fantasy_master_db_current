"""
lib/dataset2/receiving_efficiency_traits.py

Dataset 2 family #18 (receiving efficiency), CORE portion only --
approved 2026-07 (research/dataset2/DATASET2_TRAIT_ROADMAP.md §5 Tier
2, family 18: "Core fields (catch_rate, yards_per_target,
yac_per_reception) derivable from already-fetched columns once
retained"). Man/zone-specific efficiency (depends on unverified
`ftn_charting`/coverage-charting data) is explicitly OUT of this
round's scope, not approximated.

Builds on lib.dataset2.usage_traits.py's own already-lagged, already-
REG-only, already-traded-player-aggregated Source A preseason
features -- this module performs no aggregation of its own, only a
same-row RATIO of already-correct, already-summed season totals. Every
one of usage_traits.py's own real guarantees (REG-only aggregation,
traded-player-correct summing across teams, real-zero-vs-null
denominators) is inherited automatically, not re-derived here.

THREE RATIOS, each a season-total-over-season-total ratio computed
AFTER full-season aggregation -- NEVER an average of weekly ratios
(a weekly average is mathematically wrong for a ratio metric: a player
who goes 1-for-1 in a 1-target week and 9-for-19 in a 19-target week
has a real season catch rate of 10/20=50%, not the naive average of
100% and 47.4%=73.7% -- see this module's own test suite for the
exact worked case):

- `prior_season_catch_rate` = `prior_season_receptions /
  prior_season_targets`. Real receiving-efficiency measure, but
  influenced by real confounds this module does NOT control for --
  target depth (a screen-pass-heavy usage profile inflates catch rate
  independent of hands/route-running skill), quarterback play, and
  offensive role. Reported as a hypothesis trait, not an established
  causal skill measure. REAL, AUDITED COVERAGE BOUNDARY (2026-07,
  found while validating this round's real rebuild, NOT assumed):
  `targets` in the raw nflverse weekly file is essentially untracked
  for real observation seasons 2006-2008 -- 99.5-99.6% of real
  player-weeks with a real reception show `targets == 0` in each of
  those three seasons (a real recording gap, not a real football
  outcome), vs. a clean 0.0% in every season 2009 onward, a sharp,
  discrete break. Forced NULL for `prediction_season` 2007-2009 (see
  `_apply_targets_coverage_floor()` below) -- NOT computed from the
  real but unreliable underlying counts, per this project's flag-and-
  exclude policy. See `config.DATASET2_TARGETS_UNRELIABLE_OBSERVATION_SEASONS`.
- `prior_season_receiving_yards_per_target` = `prior_season_receiving_yards
  / prior_season_targets`. Same real confounds as catch rate, AND the
  same real 2006-2008 `targets`-unreliability coverage floor applies
  (same reason -- same denominator).
- `prior_season_yac_per_reception` = `prior_season_receiving_yards_after_catch
  / prior_season_receptions`. Especially role- and scheme-dependent --
  a real, disclosed confound, not pure player skill (a slot receiver
  on a screen-heavy offense will show real elevated YAC/reception
  regardless of individual after-catch ability). See
  usage_traits.py's own YAC coverage audit (module docstring) for the
  real coverage finding this trait relies on -- 0% null, a real stable
  zero rate, full 2006-2025 coverage confirmed by direct season-by-
  season inspection, not assumed from the column merely existing.

MISSINGNESS -- real, never guessed, matching this project's standing
policy:
- Zero real `prior_season_targets` -> `prior_season_catch_rate` and
  `prior_season_receiving_yards_per_target` are NULL, never `0.0` (a
  player with zero real targets has an undefined, not zero, catch
  rate -- dividing by a real zero is not the same claim as "caught
  none of zero targets, therefore 0%").
- Zero real `prior_season_receptions` -> `prior_season_yac_per_reception`
  is NULL, never `0.0`, for the same reason.
- A real, valid NEGATIVE or zero `prior_season_receiving_yards_after_catch`
  total, paired with POSITIVE real receptions, produces the real
  calculated ratio (including a real negative or zero result) -- never
  suppressed or floored, since this is a real, disclosed, possible
  football outcome (see usage_traits.py's own YAC audit).
- No real season N-1 row at all (rookie, or a genuine gap year) ->
  every `prior_season_*` INPUT is null together (usage_traits.py's own
  `lag_join()` key-miss behavior), so every ratio here is null too --
  never a guessed value for a player with no real prior-season
  history.
- Missing Source A coverage for any other reason (no real weekly rows
  that season) is indistinguishable from "real season with zero
  targets/receptions" at this layer -- both correctly produce NULL
  ratios, consistent with every other Dataset 2 lag-based module.
- `prediction_season` 2007-2009 (i.e. `season` in this module's own
  input/output naming -- lagged FROM real observation seasons
  2006-2008): `prior_season_catch_rate` and
  `prior_season_receiving_yards_per_target` are FORCED NULL
  unconditionally, even where the real (unreliable) underlying counts
  would otherwise produce a computable value -- see the real coverage
  audit above. `prior_season_yac_per_reception` is NOT affected (its
  own real audit found clean, full 2006-2025 coverage -- a different
  denominator, a different real finding).

DELIBERATELY NOT BUILT THIS ROUND: no "efficient receiver" threshold,
percentile, or classification flag of any kind. No cutoff has been
approved for these full-season traits -- the continuous ratios and
their real underlying denominator columns (already preserved
separately as `srcA_prior_season_targets`/`srcA_prior_season_receptions`
in the canonical predictor table) are the complete, approved scope
this round.

TEST SCOPE: tests/test_dataset2_receiving_efficiency_traits.py proves
implementation correctness against synthetic fixtures, including the
load-bearing "naive weekly average would be wrong" case.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import validate_columns
from config import DATASET2_TARGETS_UNRELIABLE_OBSERVATION_SEASONS

# The real, audited-unreliable OBSERVATION seasons translated to the
# PREDICTION seasons they get lagged into (prediction_season ==
# observation_season + 1) -- the frame this module receives is already
# keyed by prediction_season (see build_receiving_efficiency_traits()'s
# own docstring), so this is the set actually checked against `season`.
_TARGETS_UNRELIABLE_PREDICTION_SEASONS = frozenset(
    s + 1 for s in DATASET2_TARGETS_UNRELIABLE_OBSERVATION_SEASONS
)

RECEIVING_EFFICIENCY_REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "position",
    "prior_season_targets",
    "prior_season_receptions",
    "prior_season_receiving_yards",
    "prior_season_receiving_yards_after_catch",
)

RECEIVING_EFFICIENCY_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "prior_season_catch_rate",
    "prior_season_receiving_yards_per_target",
    "prior_season_yac_per_reception",
)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """numerator / denominator, NULL wherever denominator is null OR
    exactly zero -- never a guessed 0.0 (same `replace(0, np.nan)`
    pattern already used for target_share/air_yards_share in
    usage_traits.py). A real, non-zero (including real negative)
    numerator over a real positive denominator produces the real
    calculated value, never suppressed or floored."""
    return numerator / denominator.replace(0, np.nan)


def build_receiving_efficiency_traits(preseason_usage_df: pd.DataFrame) -> pd.DataFrame:
    """#18, receiving-efficiency CORE portion. `preseason_usage_df`
    must be build_preseason_usage_features()'s own output (or an
    equivalent frame with the same columns) -- see module docstring
    for the full real design, missingness policy, and what's
    deliberately not built this round."""
    validate_columns(preseason_usage_df, RECEIVING_EFFICIENCY_REQUIRED_COLUMNS, "preseason_usage_df")

    out = preseason_usage_df[list(RECEIVING_EFFICIENCY_REQUIRED_COLUMNS)].copy()

    out["prior_season_catch_rate"] = _safe_ratio(out["prior_season_receptions"], out["prior_season_targets"])
    out["prior_season_receiving_yards_per_target"] = _safe_ratio(
        out["prior_season_receiving_yards"], out["prior_season_targets"]
    )
    out["prior_season_yac_per_reception"] = _safe_ratio(
        out["prior_season_receiving_yards_after_catch"], out["prior_season_receptions"]
    )

    # Real, audited coverage floor -- `targets` is essentially
    # untracked in the real 2006-2008 raw source (see module docstring
    # and config.DATASET2_TARGETS_UNRELIABLE_OBSERVATION_SEASONS).
    # Forced null unconditionally for the affected prediction seasons,
    # even where the real (unreliable) counts would otherwise produce
    # a computable value -- never silently ships a real-but-wrong
    # ratio. yac_per_reception is untouched (different denominator,
    # confirmed clean by its own real audit).
    unreliable = out["season"].isin(_TARGETS_UNRELIABLE_PREDICTION_SEASONS)
    out.loc[unreliable, "prior_season_catch_rate"] = np.nan
    out.loc[unreliable, "prior_season_receiving_yards_per_target"] = np.nan

    return out[list(RECEIVING_EFFICIENCY_OUTPUT_COLUMNS)].reset_index(drop=True)
