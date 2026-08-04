"""
scripts/09_fit_sbv_expected_production.py

Stage 09: fits the Stars-by-Value expected-production-by-round lookup
table and materializes it to data/processed/sbv_expected_production_lookup.parquet
(decision #2 -- E_P is fit once per build into a versioned artifact;
scoring only ever joins against it, never refits inline). Explicit,
deliberate invocation only -- never triggered automatically by a
scoring run (same posture as Stage 08's fetch).

Population scoping happens HERE, not inside lib/stars_by_value/expected_production.py
(which only fits whatever population it's given, per its own module
docstring): reads the real production master DB (same MASTER_PATH
convention as scripts/05_calculate_metrics.py and
scripts/06_generate_rankings.py -- NOT the LWI-augmented file, since
SBV is fully additive and never depends on LWI's own computed
columns), derives adp_matched the same way research/dataset3/build_broad_historical_dataset.py
does (data_quality_flag in {matched_clean, matched_needs_review}),
computes AATP via lib.stars_by_value.production.compute_aatp(), computes
adp_round via lib.stars_by_value.expected_production.adp_round(), and
ONLY THEN filters to the ADP-matched rows for the round-fitting step
(round is undefined for a no_adp_match row) -- ALL trustworthy
ADP-matched rows, never capped by draft depth (Task 1 of the oracle
chain found capping at 200 hurts, not helps).

ORDER MATTERS, CONFIRMED BY A REAL BUG CAUGHT BY THE ORACLE-PARITY
TEST: compute_aatp() must run on the FULL population (games_played>=1,
all positions), THEN get filtered to adp_matched -- NOT the reverse.
replacement_level_from_rank() (inside compute_aatp()) computes
replacement PPG from a RANK WINDOW that includes undrafted players;
filtering to adp_matched first silently removes those players from the
rank pool, shifting who occupies each rank near the cutoff and
producing systematically wrong replacement_ppg / AATP values with no
error raised. Caught directly by tests/test_expected_production.py's
oracle-parity check (a small but real, non-noise, non-zero, per-row
constant discrepancy was NOT floating-point tolerance -- it was this
bug) -- an earlier version of this script had exactly this ordering
mistake.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import SEASONS
from lib.player_season_authority import resolved_canonical_position_population
from lib.stars_by_value import expected_production as ep
from lib.stars_by_value import production as prod

MASTER_PATH = Path(f"data/master/master_historical_db_{SEASONS[0]}_{SEASONS[-1]}.csv")
OUTPUT_PATH = Path("data/processed/sbv_expected_production_lookup.parquet")

DRAFTED_QUALITY_FLAGS = {"matched_clean", "matched_needs_review"}

_LOOKUP_DTYPES = {
    "prediction_season": "int16",
    "position": "category",
    "draft_round": "int8",
    "expected_production": "float64",
    "positional_offset_applied": "float64",
    "recency_weighted": "bool",
    "half_life_years": "float64",
    "sample_size": "int32",
    "sbv_version": "string",
}


def load_full_population() -> pd.DataFrame:
    """games_played>=1 only -- the master DB has 516 games_played==0
    rows with null ppg_ppr (undefined per-game rate), none of which are
    ever adp_matched, so excluding them here never changes which real
    players occupy the adp_matched round-fitting population. It DOES
    matter for compute_aatp(): its fail-loud validation correctly
    rejects null ppg_ppr, and games_played==0 rows would trip it
    regardless of position or adp_matched status. Position is NOT
    filtered here -- the master DB already tracks only QB/RB/WR/TE
    (confirmed directly), so every row already satisfies
    production.py's SBV_POSITIONS check."""
    if not MASTER_PATH.exists():
        raise RuntimeError(f"{MASTER_PATH} does not exist -- run the master-build pipeline first.")
    df = pd.read_csv(MASTER_PATH)
    df["adp_matched"] = df["data_quality_flag"].isin(DRAFTED_QUALITY_FLAGS)

    required = list(prod.REQUIRED_COLUMNS) + [
        "overall_adp_observed", "canonical_fantasy_position", "canonical_position_status",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"{MASTER_PATH} is missing required columns: {missing}")

    df = resolved_canonical_position_population(df)
    return df[df["games_played"] >= 1].copy()


def load_adp_matched_population() -> pd.DataFrame:
    """compute_aatp() runs on the FULL population FIRST (see module
    docstring's ORDER MATTERS note -- replacement_level_from_rank()
    needs undrafted players present in the rank pool), and only THEN
    is the result filtered down to adp_matched rows for round-fitting."""
    full_population = load_full_population()
    with_aatp = prod.compute_aatp(full_population)
    with_aatp["adp_round"] = with_aatp["overall_adp_observed"].apply(ep.adp_round)

    matched = with_aatp[with_aatp["adp_matched"]].copy()
    matched = matched.dropna(subset=["adp_round"])
    return matched


def finalize_dtypes(lookup: pd.DataFrame) -> pd.DataFrame:
    out = lookup.astype(_LOOKUP_DTYPES)
    out["fit_timestamp"] = pd.to_datetime(out["fit_timestamp"], utc=True)
    return out


def main():
    print(f"Loading ADP-matched, AATP-computed population from {MASTER_PATH}...")
    matched = load_adp_matched_population()
    print(f"Fitting population: {len(matched)} ADP-matched player-seasons "
          f"(all trustworthy ADP, no draft-depth cap -- Task 1 of the oracle chain)")

    lookup = ep.fit_expected_production(matched)
    lookup = finalize_dtypes(lookup)
    print(f"Fitted {len(lookup)} (prediction_season, position, draft_round) rows")

    ep.validate_lookup(lookup)
    print("Lookup table passed validate_lookup() (schema, non-empty, version, key-uniqueness)")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lookup.to_parquet(OUTPUT_PATH, index=False)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
