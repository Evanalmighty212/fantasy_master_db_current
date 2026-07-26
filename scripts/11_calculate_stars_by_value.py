"""
scripts/11_calculate_stars_by_value.py

Commit E, step 4: end-to-end SBV orchestration -- assembles the real
master-DB population, computes P (production.py), builds adp_round for
ADP-scored rows, and calls labeling.label_rows() across the population.
This is the orchestration piece flagged as "must still be built" since
Commit 9 -- every formula and rule it calls already exists as tested
code; this is the first time they're run together against real data.

BUILD-COMPLETENESS CONTRACT (2026-07, added after the first diagnostic
run found real, structural gaps -- see below):

  - `--mode diagnostic` (the default): may complete with rows
    DEFERRED (not scored) -- missing MFL AUG15 corroboration data for
    a historical season. Writes to
    SBV_DIAGNOSTIC_OUTPUT_PARQUET_PATH / SBV_DIAGNOSTIC_OUTPUT_CSV_PATH
    and a deferred-rows report -- NEVER the canonical artifact paths.
    A diagnostic run's result is a research artifact, not a claim that
    SBV is complete for any season.
  - `--mode canonical`: refuses to run at all if ANY row would need to
    be deferred for ANY reason -- check_build_completeness() raises
    loudly, naming every reason and its row count, before any output
    is written. Only writes to the real canonical
    SBV_OUTPUT_PARQUET_PATH / SBV_OUTPUT_CSV_EXPORT_PATH once the
    population is provably complete. This is deliberate: a canonical
    artifact that silently excluded thousands of rows would look
    "done" while actually being wrong for every downstream consumer
    that doesn't know to check for gaps.

REAL, DISCLOSED SCOPE LIMIT found by the first diagnostic run
(2026-07): acquisition_cost.py's classify_row() fails loudly (by
design, not a bug) if a 2011+, no_adp_match, gate-clearing row is
processed without real MFL AUG15 corroboration data for that season.
Locally cached MFL responses exist for only 2 historical seasons
(2015, 2023). Fetching the other 13 historical seasons live would mean
many new external API calls -- reserved for the sanctioned GitHub
Actions path per this project's own convention, not attempted here
(see "Historical MFL backfill" as its own follow-up).

RESOLVED (2026-07, second pass): 118 real 2025 rows had `adp_round > 15`,
beyond the E_P lookup's fitted depth (matching FFC's historical
~150-180-player coverage; MFL's real 2025 market reaches much deeper).
These are NO LONGER deferred by this script -- labeling.py now
resolves them natively to the settled
`unscoreable_expected_production_out_of_range` status (score=NULL,
label=NULL, both thresholds populated -- a real, trustworthy
acquisition cost with no E_P available for that round, not silently
capped or MMC-substituted). See docs/ADP_SOURCE_MATRIX.md's Blocker B
entry for the full methodology record -- of those 118, only 8 clear
the production gate at all, and none of the 8 can reach the Star
threshold even under the most generous conceivable E_P (E_P=0), so
this resolution changes zero Star labels.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import config
from lib.stars_by_value import production as prod
from lib.stars_by_value import expected_production as ep
from lib.stars_by_value import labeling
import nflverse_source

MASTER_PATH = REPO_ROOT / f"data/master/master_historical_db_{config.SEASONS[0]}_{config.SEASONS[-1]}.csv"
EP_LOOKUP_PATH = REPO_ROOT / config.SBV_EXPECTED_PRODUCTION_LOOKUP_PATH
MFL_CACHE_SEASONS = (2015, 2023)  # real cached MFL AUG15 responses -- see module docstring

DEFERRED_REASON_NO_MFL_DATA = "no cached MFL AUG15 data for this season"
# NOTE: the former DEFERRED_REASON_ROUND_TOO_DEEP category no longer
# exists -- labeling.py now resolves those rows natively to the
# settled unscoreable_expected_production_out_of_range status instead
# of deferring them (see split_processable()'s docstring below).


# --- Pure population-shaping logic (no file I/O) -- directly unit-testable ---


def split_processable(pop: pd.DataFrame, ep_lookup: pd.DataFrame, mfl_cache_seasons=MFL_CACHE_SEASONS):
    """Splits pop into (processable, deferred). deferred carries a
    'deferred_reason' column -- never silently dropped, never guessed
    at. A row can only be deferred for a reason listed at module scope
    above (DEFERRED_REASON_*), so check_build_completeness() can name
    exactly what's missing.

    NOTE (2026-07): rows whose adp_round exceeds the E_P lookup's
    fitted depth are NO LONGER deferred here -- labeling.py now
    resolves them natively to the settled
    unscoreable_expected_production_out_of_range status (score=NULL,
    label=NULL, both thresholds populated, real trustworthy
    acquisition cost but no E_P available for that round). They flow
    through as processable, not deferred -- ep_lookup is still an
    argument only for backward compatibility with existing call sites."""
    needs_mfl = (
        (pop["data_quality_flag"] == "no_adp_match")
        & (pop["season"] >= config.SBV_MFL_AVAILABLE_FROM_SEASON)
        & (pop["season"] != 2010)
    )
    mfl_cached_mask = pop["season"].isin(mfl_cache_seasons)
    deferred = pop[needs_mfl & ~mfl_cached_mask].copy()
    deferred["deferred_reason"] = DEFERRED_REASON_NO_MFL_DATA
    processable = pop[~(needs_mfl & ~mfl_cached_mask)].copy()
    return processable, deferred


def check_build_completeness(deferred: pd.DataFrame) -> None:
    """The canonical-mode gate: raises loudly if ANY row is deferred,
    naming every distinct reason and its count. Never called by
    diagnostic mode. This is the mechanism that makes it structurally
    impossible for a canonical build to silently drop rows -- a
    diagnostic run reports gaps; a canonical run refuses to exist
    until there are none."""
    if len(deferred) == 0:
        return
    reasons = deferred.groupby("deferred_reason").size()
    detail = "\n".join(f"  - {reason}: {count} row(s)" for reason, count in reasons.items())
    raise RuntimeError(
        f"Canonical SBV build refused: {len(deferred)} row(s) would be deferred, "
        f"not scored. Canonical output must never silently exclude rows -- either "
        f"resolve the underlying gap(s) below and re-run, or run with "
        f"--mode diagnostic to get a labeled, non-canonical partial result:\n{detail}"
    )


# --- I/O: population assembly, reference-data loading, writing outputs ---


def load_mfl_cached(season: int):
    import json
    adp_path = REPO_ROOT / f"data/raw/mfl/adp_{season}_period_aug15.json"
    players_path = REPO_ROOT / f"data/raw/mfl/players_{season}.json"
    if not adp_path.exists() or not players_path.exists():
        return None, None
    return json.loads(adp_path.read_text()), json.loads(players_path.read_text())


def build_population():
    master = pd.read_csv(MASTER_PATH, low_memory=False)
    pop = master[master["position"].isin(config.SBV_POSITIONS)].copy()
    pop["adp_matched"] = pop["data_quality_flag"].isin(["matched_clean", "matched_needs_review"])
    pop = pop.dropna(subset=["ppg_ppr", "position_finish_ppr", "games_played", "fantasy_points_ppr"])

    prod_input = pop[["season", "player_id", "position", "games_played",
                       "fantasy_points_ppr", "ppg_ppr", "position_finish_ppr", "adp_matched"]].copy()
    with_p = prod.compute_production(prod_input)
    pop = pop.merge(with_p[["season", "player_id", "P"]], on=["season", "player_id"], how="left")

    pop["adp_round"] = pop["overall_adp"].apply(ep.adp_round)
    return pop


def run_label_rows(processable: pd.DataFrame, ep_lookup: pd.DataFrame, full_pop: pd.DataFrame):
    """full_pop must be the COMPLETE population (including rows
    deferred THIS run) -- classify_draft_status()'s prior-season
    lookback needs to see a player's real prior-season production
    regardless of whether that PRIOR row happens to be deferred in the
    CURRENT scoring pass. Using only `processable` here was a real bug
    caught by comparing two runs' status breakdowns (unscoreable_ambiguous/
    minimal_market_cost_scored/unscoreable_drafted_adp_missing counts
    shifted between runs with no other change) -- fixed before this
    was ever treated as canonical."""
    players_df = nflverse_source.fetch_players()
    history_df = full_pop[["season", "player_id", "games_played", "fantasy_points_ppr"]]
    overrides_2010_df = pd.read_csv(REPO_ROOT / config.SBV_MMC_2010_OVERRIDE_PATH)

    depth_charts_by_season = {}
    for season in processable["season"].unique():
        if season == 2025:
            continue  # 2025's schema needs schedule_df, handled separately below
        dc_path = REPO_ROOT / f"data/raw/nflverse/annual/depth_charts_{season}.csv"
        if dc_path.exists():
            depth_charts_by_season[season] = pd.read_csv(dc_path, low_memory=False)

    mfl_adp_by_season, mfl_players_by_season = {}, {}
    for season in MFL_CACHE_SEASONS:
        adp_resp, players_resp = load_mfl_cached(season)
        if adp_resp is not None:
            mfl_adp_by_season[season] = adp_resp
            mfl_players_by_season[season] = players_resp

    schedule_df = None
    schedules_path = REPO_ROOT / "data/raw/nflverse/reference/games.csv"
    if schedules_path.exists():
        schedule_df = pd.read_csv(schedules_path, low_memory=False)

    result = labeling.label_rows(
        processable, ep_lookup,
        players_df=players_df, history_df=history_df,
        depth_charts_by_season=depth_charts_by_season,
        mfl_adp_by_season=mfl_adp_by_season, mfl_players_by_season=mfl_players_by_season,
        overrides_2010_df=overrides_2010_df,
        schedule_df=schedule_df,
    )
    return processable[["season", "player_id", "player_name", "position"]].merge(
        result, on=["season", "player_id"], how="inner",
    )


def write_diagnostic_output(out: pd.DataFrame, deferred: pd.DataFrame):
    parquet_path = REPO_ROOT / config.SBV_DIAGNOSTIC_OUTPUT_PARQUET_PATH
    csv_path = REPO_ROOT / config.SBV_DIAGNOSTIC_OUTPUT_CSV_PATH
    deferred_path = REPO_ROOT / config.SBV_DEFERRED_ROWS_REPORT_PATH

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(parquet_path, index=False)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(csv_path, index=False)
    deferred_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["season", "player_id", "player_name", "position", "overall_adp", "deferred_reason"]
    deferred[[c for c in cols if c in deferred.columns]].to_csv(deferred_path, index=False)

    print(f"[DIAGNOSTIC -- NOT canonical] Wrote {parquet_path} ({len(out)} rows)")
    print(f"[DIAGNOSTIC -- NOT canonical] Wrote {csv_path}")
    print(f"Wrote {deferred_path} ({len(deferred)} rows deferred, not scored)")


def write_canonical_output(out: pd.DataFrame):
    parquet_path = REPO_ROOT / config.SBV_OUTPUT_PARQUET_PATH
    csv_path = REPO_ROOT / config.SBV_OUTPUT_CSV_EXPORT_PATH
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(parquet_path, index=False)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(csv_path, index=False)
    print(f"[CANONICAL] Wrote {parquet_path} ({len(out)} rows, zero deferred)")
    print(f"[CANONICAL] Wrote {csv_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["diagnostic", "canonical"], default="diagnostic")
    args = parser.parse_args()

    print(f"Mode: {args.mode}")
    print("Step 1: Assembling real master-DB population, computing P...")
    pop = build_population()
    print(f"  {len(pop)} real rows (positions {config.SBV_POSITIONS}, non-null required fields)")

    ep_lookup = pd.read_parquet(EP_LOOKUP_PATH)
    processable, deferred = split_processable(pop, ep_lookup)
    print(f"Step 2: Population split -- {len(processable)} processable now, {len(deferred)} deferred")
    if len(deferred):
        print("  Deferred by reason:")
        print(deferred.groupby("deferred_reason").size().to_string())

    if args.mode == "canonical":
        print("Step 3: Checking build-completeness contract (canonical mode)...")
        check_build_completeness(deferred)  # raises if len(deferred) > 0 -- never reaches Step 4 otherwise

    print("Step 4: Running labeling.label_rows() on the processable population...")
    out = run_label_rows(processable, ep_lookup, full_pop=pop)

    print("\nFinal status breakdown (processable population only):")
    print(out["star_by_value_status"].value_counts())
    print(f"\nStars (label=1): {(out['star_by_value_label']==1).sum()}")

    if args.mode == "diagnostic":
        write_diagnostic_output(out, deferred)
    else:
        write_canonical_output(out)


if __name__ == "__main__":
    main()
