# Fantasy Research Engine v1.0 Scope

## Mission

Build a reproducible fantasy football research engine that generates a Master Historical Database for PPR fantasy football seasons.

The database should support:
- League Winner Index
- ADP value studies
- breakout and bust analysis
- historical rankings research
- player archetype analysis

---

## v1.0 Season Scope

- Seasons: 2006–2025
- Scoring: PPR only
- Positions: QB, RB, WR, TE
- Draft universe: Top 250 preseason ADP per season

---

## v1.0 Required Outputs

### 1. Master Historical Database

One row = one player-season.

Required columns:

- season
- player_id
- player_name
- position
- team
- games_played
- fantasy_points_ppr
- ppg_ppr
- overall_finish_ppr
- position_finish_ppr
- overall_adp
- positional_adp
- adp_source
- adp_rank
- data_quality_flag

---

### 2. League Winner Index

Formula:

- 46% ADP Value
- 18% Fantasy Finish Total Points
- 17% Points Per Game
- 12% Positional Advantage
- 4% Playoff Performance
- 3% Consistency

---

### 3. Validation Reports

Required validation files:

- missing_adp_matches.csv
- low_confidence_player_matches.csv
- duplicate_player_matches.csv
- season_coverage_report.csv
- top_250_adp_coverage_report.csv

---

## v1.0 Required Data Sources

### Already Working

- nflverse / nfl_data_py weekly data
- season-level PPR fantasy scoring
- player IDs from nflverse

### Still Needed

- complete historical PPR ADP source
- 2025 fantasy results backfill if nflverse remains unavailable
- player ID matching between ADP source and nflverse

---

## v1.0 Not Included Yet

These are v1.1 or later:

- coaching changes
- Vegas win totals
- offensive line rankings
- preseason hype/narrative tracking
- injury history
- advanced efficiency metrics
- dynasty ADP
- best ball ADP
- non-PPR scoring

---

## Definition of Done

v1.0 is complete when:

1. Every season from 2006–2025 has a Top 250 PPR ADP table.
2. Every ADP player is matched to a season-result row or flagged for review.
3. The Master Historical Database exports to CSV and Excel.
4. League Winner Index is calculated for every eligible player-season.
5. Validation reports are generated automatically.
6. The full project can be rebuilt with one command:

python run_pipeline.py
