"""
04_build_master_dataset.py  [NOT YET IMPLEMENTED]

Purpose:
- Join data/raw/nflverse season results (from 03) with the cleaned ADP
  table (from 02) on player + season.
- Produce the one-row-per-player-season Master Historical Database
  described in docs/VERSION_1_SCOPE.md, with all required columns:
  season, player_id, player_name, position, team, games_played,
  fantasy_points_ppr, ppg_ppr, overall_finish_ppr, position_finish_ppr,
  overall_adp, positional_adp, adp_source, adp_rank, data_quality_flag.
- Emit the validation reports (missing_adp_matches.csv,
  low_confidence_player_matches.csv, duplicate_player_matches.csv,
  season_coverage_report.csv, top_250_adp_coverage_report.csv).

Input:  data/raw/nflverse/season_results_ppr_*.csv,
        data/processed/adp_clean_*.csv
Output: data/master/master_historical_db.csv (+ .xlsx),
        data/exports/validation/*.csv
"""

def main():
    raise NotImplementedError(
        "04_build_master_dataset.py has not been built yet. "
        "Requires 02_clean_adp.py and 03_download_stats.py to be complete."
    )


if __name__ == "__main__":
    main()
