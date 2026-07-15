"""
04_build_master_dataset.py

Priority 5: Build the Master Historical Database.

- Runs player identity matching (player_matching.py, Priority 4) between
  the clean ADP table (02) and nflverse season results (03).
- Joins them with RESULTS AS THE BASE POPULATION -- every player who
  actually had a season (per 03) gets a row, whether or not they were
  matched to an ADP entry. This is deliberate: "breakout/bust analysis"
  and "ADP value studies" (both required per docs/VERSION_1_SCOPE.md)
  need the full performance population, not just the drafted subset --
  an undrafted breakout player is exactly the kind of row this database
  exists to surface, not one to silently drop.
- Emits every validation report named in docs/VERSION_1_SCOPE.md:
  missing_adp_matches.csv, low_confidence_player_matches.csv,
  duplicate_player_matches.csv, season_coverage_report.csv,
  top_250_adp_coverage_report.csv.

Required output columns (per docs/VERSION_1_SCOPE.md):
  season, player_id, player_name, position, team, games_played,
  fantasy_points_ppr, ppg_ppr, overall_finish_ppr, position_finish_ppr,
  overall_adp, positional_adp, adp_source, adp_rank, data_quality_flag

Input:  data/raw/nflverse/season_results_ppr_<start>_<end>.csv
        data/processed/adp_clean_<start>_<end>.csv
        data/manual/player_name_overrides.csv (via player_matching.py)
Output: data/master/master_historical_db_<start>_<end>.csv (+ .xlsx)
        data/exports/validation/missing_adp_matches.csv
        data/exports/validation/low_confidence_player_matches.csv
        data/exports/validation/duplicate_player_matches.csv
        data/exports/validation/season_coverage_report.csv
        data/exports/validation/top_250_adp_coverage_report.csv
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

import pandas as pd

from config import SEASONS, TOP_N_ADP
import player_matching

RESULTS_PATH = Path(f"data/raw/nflverse/season_results_ppr_{SEASONS[0]}_{SEASONS[-1]}.csv")
ADP_PATH = Path(f"data/processed/adp_clean_{SEASONS[0]}_{SEASONS[-1]}.csv")
MASTER_DIR = Path("data/master")
VALIDATION_DIR = Path("data/exports/validation")

FINAL_COLUMNS = [
    "season", "player_id", "player_name", "position", "team",
    "games_played", "fantasy_points_ppr", "ppg_ppr",
    "overall_finish_ppr", "position_finish_ppr",
    "overall_adp", "positional_adp", "adp_source", "adp_rank",
    "data_quality_flag",
]


def flag_row(r):
    if pd.isna(r["overall_adp"]):
        return "no_adp_match"
    if r.get("match_type") in ("fuzzy_low_confidence", "exact_name_position_mismatch"):
        return "matched_needs_review"
    return "matched_clean"


def build_master_dataset():
    if not RESULTS_PATH.exists() or not ADP_PATH.exists():
        raise FileNotFoundError(
            f"Need both {RESULTS_PATH} (from 03_download_stats.py) and "
            f"{ADP_PATH} (from 02_clean_adp.py) to exist first."
        )

    results = pd.read_csv(RESULTS_PATH)
    adp = pd.read_csv(ADP_PATH)
    overrides = player_matching.load_overrides()

    print("Step 1: Running player identity matching (Priority 4)...")
    matched, missing, low_conf, dupes, out_of_scope = player_matching.match_players(
        adp, results, overrides
    )

    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    missing.to_csv(VALIDATION_DIR / "missing_adp_matches.csv", index=False)
    low_conf.to_csv(VALIDATION_DIR / "low_confidence_player_matches.csv", index=False)
    dupes.to_csv(VALIDATION_DIR / "duplicate_player_matches.csv", index=False)
    out_of_scope.to_csv(VALIDATION_DIR / "out_of_scope_adp_rows.csv", index=False)
    print(f"  Matched: {len(matched)}, Missing: {len(missing)}, "
          f"Low-confidence: {len(low_conf)}, Duplicates: {len(dupes)}")

    print("Step 2: Computing positional ADP rank...")
    matched = matched.copy()
    matched["positional_adp"] = (
        matched.groupby(["season", "position"])["overall_adp"]
        .rank(method="first", ascending=True)
        .astype("Int64")
    )

    print("Step 3: Checking for duplicate (season, player_id) in matched ADP...")
    dup_player_season = matched[
        matched.duplicated(subset=["season", "nflverse_player_id"], keep=False)
    ]
    if len(dup_player_season) > 0:
        dup_path = VALIDATION_DIR / "duplicate_adp_to_player_id_matches.csv"
        dup_player_season.to_csv(dup_path, index=False)
        print(f"  WARNING: {len(dup_player_season)} ADP rows mapped to the same "
              f"(season, player_id) as another ADP row -- see {dup_path}.")
        print(f"  These are EXCLUDED from the join entirely (not arbitrarily "
              f"resolved) -- picking one silently risks attaching a wrong "
              f"match's ADP data to a real player's results. Add an override "
              f"table entry once reviewed to resolve each case explicitly.")

    # Exclude BOTH sides of any collision, not just keep-first: a
    # (season, player_id) collision means at least one of the competing
    # matches is wrong, and we don't know which without a human looking
    # at it. Silently keeping "the first one" would mean roughly half
    # the time we'd attach a WRONG ADP value to a real player's results
    # row -- worse than just leaving it unmatched until resolved.
    collision_keys = set(
        zip(dup_player_season["season"], dup_player_season["nflverse_player_id"])
    )
    matched_clean = matched[
        ~matched.apply(lambda r: (r["season"], r["nflverse_player_id"]) in collision_keys, axis=1)
    ]

    adp_slim = (
        matched_clean
        [["season", "nflverse_player_id", "overall_adp", "adp_rank",
          "positional_adp", "source", "match_type", "match_confidence"]]
        .rename(columns={"nflverse_player_id": "player_id", "source": "adp_source"})
    )

    print("Step 4: Joining results (base population) with matched ADP...")
    master = results.merge(adp_slim, on=["season", "player_id"], how="left")

    master["data_quality_flag"] = master.apply(flag_row, axis=1)
    master = master.rename(columns={
        "player_display_name": "player_name",
        "primary_team": "team",
    })

    missing_cols = [c for c in FINAL_COLUMNS if c not in master.columns]
    if missing_cols:
        raise KeyError(f"Master dataset is missing expected columns: {missing_cols} "
                        f"-- check that 03_download_stats.py and player_matching.py "
                        f"still produce the fields this join depends on.")

    master_final = master[FINAL_COLUMNS].sort_values(["season", "overall_finish_ppr"])

    print("Step 5: Writing Master Historical Database...")
    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = MASTER_DIR / f"master_historical_db_{SEASONS[0]}_{SEASONS[-1]}.csv"
    master_final.to_csv(csv_path, index=False)

    xlsx_path = MASTER_DIR / f"master_historical_db_{SEASONS[0]}_{SEASONS[-1]}.xlsx"
    try:
        master_final.to_excel(xlsx_path, index=False)
    except Exception as e:
        print(f"  xlsx export skipped ({e}) -- CSV still written fine.")

    print("Step 6: Building season_coverage_report.csv...")
    coverage_rows = []
    for season in sorted(master_final["season"].unique()):
        sub = master_final[master_final["season"] == season]
        matched_count = int(sub["overall_adp"].notna().sum())
        coverage_rows.append({
            "season": season,
            "total_results_rows": len(sub),
            "matched_to_adp": matched_count,
            "unmatched_no_adp": len(sub) - matched_count,
            "match_rate_pct": round(matched_count / len(sub) * 100, 1) if len(sub) else 0,
        })
    pd.DataFrame(coverage_rows).to_csv(VALIDATION_DIR / "season_coverage_report.csv", index=False)

    print("Step 7: Building top_250_adp_coverage_report.csv...")
    top250_rows = []
    skill_positions = {"QB", "RB", "WR", "TE"}
    for season in sorted(adp["season"].unique()):
        season_adp = adp[(adp["season"] == season) & (adp["position"].isin(skill_positions))]
        season_top250 = season_adp[season_adp["adp_rank"] <= TOP_N_ADP]
        matched_names_this_season = set(
            matched.loc[matched["season"] == season, "player_name_original"]
        )
        matched_in_top250 = int(
            season_top250["player_name_original"].isin(matched_names_this_season).sum()
        )
        top250_rows.append({
            "season": season,
            "top250_adp_rows_available": len(season_top250),
            "matched_to_results": matched_in_top250,
            "coverage_status": (
                "top250_complete" if len(season_top250) >= TOP_N_ADP
                else "source_complete_below_250" if len(season_top250) > 0
                else "missing_season"
            ),
            "coverage_pct_of_available": (
                round(matched_in_top250 / len(season_top250) * 100, 1)
                if len(season_top250) else 0
            ),
        })
    pd.DataFrame(top250_rows).to_csv(VALIDATION_DIR / "top_250_adp_coverage_report.csv", index=False)

    print("Step 8: Building match_precision_report.csv (quality dashboard)...")
    # A dedicated, ongoing quality metric per season -- separate from
    # season_coverage_report's "did it match at all" and
    # top_250_adp_coverage_report's "did the drafted population match."
    # This one tracks HOW each match was made, so a future source change
    # that suddenly doubles the fuzzy-match rate or collision count gets
    # caught immediately rather than silently degrading match quality
    # while the raw match-rate percentage looks unchanged.
    precision_rows = []
    all_seasons = sorted(set(adp_scoped_seasons := adp[adp["position"].isin(skill_positions)]["season"].unique()))
    for season in all_seasons:
        season_matched = matched[matched["season"] == season]
        season_missing = missing[missing["season"] == season] if len(missing) else missing
        season_dupes = dupes[dupes["season"] == season] if len(dupes) else dupes
        season_collisions = dup_player_season[dup_player_season["season"] == season] if len(dup_player_season) else dup_player_season

        total_attempted = len(season_matched) + len(season_missing)
        counts = season_matched["match_type"].value_counts().to_dict() if len(season_matched) else {}

        precision_rows.append({
            "season": season,
            "total_attempted": total_attempted,
            "exact_name_position": counts.get("exact_name_position", 0),
            "exact_name_position_mismatch": counts.get("exact_name_position_mismatch", 0),
            "manual_override": counts.get("manual_override", 0),
            "fuzzy_high_confidence": counts.get("fuzzy_high_confidence", 0),
            "fuzzy_low_confidence": counts.get("fuzzy_low_confidence", 0),
            "missing_no_match": len(season_missing),
            "duplicate_needs_override": len(season_dupes),
            "collision_excluded_from_join": len(season_collisions),
            "clean_match_pct": (
                round(counts.get("exact_name_position", 0) / total_attempted * 100, 1)
                if total_attempted else 0
            ),
            "needs_review_pct": (
                round((counts.get("exact_name_position_mismatch", 0)
                       + counts.get("fuzzy_low_confidence", 0)
                       + len(season_dupes) + len(season_collisions)) / total_attempted * 100, 1)
                if total_attempted else 0
            ),
        })
    pd.DataFrame(precision_rows).to_csv(VALIDATION_DIR / "match_precision_report.csv", index=False)

    print(f"\nDone. Master Historical Database: {len(master_final)} rows -> {csv_path}")
    print(f"Seasons covered: {sorted(master_final['season'].unique().tolist())}")

    return master_final


def main():
    build_master_dataset()


if __name__ == "__main__":
    main()
