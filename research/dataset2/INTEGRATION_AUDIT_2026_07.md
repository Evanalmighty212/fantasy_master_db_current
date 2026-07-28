# Dataset 2 First-Wave Integration Audit — 2026-07

Real-data integration checkpoint for the completed first implementation
wave, covering families #1, #2, #4, #6, #7, #8, #9, #10, #39, #44, and
the implemented portions of #86 and #88, per
`research/dataset2/DATASET2_TRAIT_ROADMAP.md` §6's standing
"implementation correctness vs. real-data integration" requirement.

Every number below was computed by running the actual, committed
`lib/dataset2/` modules against real data already cached in this
repository (`data/master/`, `data/raw/nflverse/reference/players.csv`,
`data/raw/nflverse/weekly_results_ppr_2006_2025.csv`,
`data/raw/nflverse/annual/depth_charts_{2006..2024}.csv`) — not
synthetic fixtures, not estimates. No code in `lib/dataset2/` was
changed as a result of this audit beyond two documentation-only
docstring/comment additions (noted below); no new methodology was
decided.

**Environment constraint, disclosed up front**: `schedules.csv`
(`games.csv`) is not cached in this sandbox (confirmed absent; real
fetches for this file go through the established GitHub Actions path,
per `CLAUDE.md`). This blocks real validation of two things: family
#2's `age_at_week1_years` (needs real per-team Week-1 kickoff dates),
and family #10's 2025 schema branch (needs the same). Everything else
in this audit — including #1/#4/#6, all of #7/#8/#39/#44, all of #9,
#10's full 2006-2024 real history, and #86/#88 — was validated against
real data with no such gap.

---

## 1. Passed checks

### #1 / #4 / #6 (`lib/dataset2/experience_age_draft.py`, real
`players.csv` join, 11,175 real skill-position player-seasons)
- **Match rate**: 11,175 / 11,175 (100.0%) joined to `players.csv` on
  `player_id`/`gsis_id`. Zero duplicate `gsis_id` rows in `players.csv`
  itself.
- **Missing birth dates**: 0 / 11,175 (0.00%), all eras.
- **Missing/malformed `rookie_season`**: 0 missing; 0 rows with
  `rookie_season > season` (which would be impossible).
- **Negative experience**: 0 rows. `experience_years` range 0-22, real
  and plausible.
- **Height/weight/BMI**: real range 65-80in / 153-304lb / BMI
  22.5-37.9 — all within plausible human-football-player bounds, zero
  flagged as implausible under a generous (<60in, >85in, <130lb,
  >400lb, BMI<15, BMI>45) sanity check.
- **Draft capital**: 28.0% missing `nfl_draft_round`/`pick`/`year`
  together (0 mismatches between the three — never one populated
  without the others) — consistent with the real, expected share of
  undrafted players in this population.
- **Position-adjusted z-scores**: `experience_position_z` correctly
  centered (mean ≈0, std=1) within every position group.
- Row count preserved exactly: 11,175 in, 11,175 out.

### #7 (`lib/dataset2/prior_finish_traits.py`, same real population)
- **Lag-alignment**: checked EXHAUSTIVELY (not sampled) across all
  11,175 rows — `prior_overall_finish` equals the real
  `overall_finish_ppr` from exactly `season - 1` with **zero
  mismatches**.
- **No same-season leakage**: confirmed structurally by the exhaustive
  check above. 38 rows where `prior_overall_finish` happens to equal
  the player's OWN current-season finish were individually inspected
  — all are real coincidental repeat performances by consistent
  players (e.g. a player finishing rank 5 in back-to-back real
  seasons), not a duplicated or leaked value.
- **Rookie nulls**: season 2006 (earliest possible season, no prior
  data can exist) is 100.0% null for all three prior-finish fields, as
  expected.
- **Distributions**: `prior_positional_finish` real ranges by position
  (QB 1-83, RB 1-154, TE 1-131, WR 1-233) match each position's real
  roster depth — plausible, not flagged.

### #8 / #39 / #44 (`lib/dataset2/prior_season_traits.py`)
- **`changed_team` spot-checked against real, known player movements**:
  Tom Brady's real 2020 NE→TB move, Christian McCaffrey's real 2022
  CAR→SF trade, and Odell Beckham Jr.'s real 2019/2021/2024 moves were
  all correctly flagged `1.0`; every real stay-with-team season for
  these players was correctly `0.0`. Two genuine data gaps (Le'Veon
  Bell's real 2018 holdout season, OBJ's real ACL-injury-missed 2022
  season) correctly produced `NaN`, never a guessed value.
- **Rookie nulls**: season 2006 is 100.0% null for
  `prior_season_games_played` and `changed_team`, as expected.
- **Trend-slope missingness investigated, not just observed**: real
  data shows `ppg_trend_3yr_slope` (47.1% missing) has LESS
  missingness than `ppg_trend_2yr_slope` (51.2% missing), which looks
  backwards at first glance. Traced to a specific real player with a
  real gap season — the 3yr window can produce a valid slope from any
  2-of-3 available lag points, while the 2yr window strictly needs its
  own two specific points — confirmed correct, not a bug.
- Row count preserved: 11,175 in, 11,175 out for both modules.

### #9 (`lib/dataset2/partial_season_traits.py`, real
`weekly_results_ppr_2006_2025.csv`, 11,175 skill-position rows)
- **Retained counts**: PRIMARY floor (≥4 games/half) retains 46.2% of
  the real population; SENSITIVITY floor (≥3) retains 53.3% — closely
  matching the original cutoff-analysis estimates.
- **Structural null enforcement checked exhaustively**: 0 rows below
  the sensitivity floor have a non-null PPG; 0 rows at-or-above it
  have a null PPG.
- **`opportunity_qualified`**: exclusively the literal string
  `"pending"` for every real row — never silently interpreted as
  passed.
- **Games accounted for exactly**: `first_half_games +
  second_half_games` equals the real total `games_played` for every
  single one of the 11,175 rows, zero exceptions — confirms no games
  are lost or double-counted across the split boundary (see Warning
  #2 for the real, non-bug caveat this uncovered).

### #10 (`lib/dataset2/depth_chart_traits.py`, real
`depth_charts_2006.csv` through `depth_charts_2024.csv`, 701,856 raw
rows, 10,566 real skill-position player-seasons 2006-2024)
- Row count preserved: 10,566 in, 10,566 out. Zero duplicate
  `(season, player_id)` keys.
- **Missingness is concentrated in the expected, correct direction**:
  unmatched rows have a real median `games_played` of 2 (mean 3.87)
  vs. 11 (mean 9.94) for matched rows, and only 4.8% of unmatched rows
  even have a real ADP — strong evidence that non-matches are
  genuinely fringe/low-involvement players, not a systemic match
  failure.
- **All 5 real QB rank-1 ties across 19 seasons (2006-2024) individually
  verified as real, documented situations**, not data artifacts — most
  notably the real 2019 Carolina Panthers QB competition (Cam Newton /
  Kyle Allen / Will Grier all tied at rank 1, a well-documented real
  situation following Newton's foot injury). This directly confirms
  the tie-preserving design does what it's for: surfacing genuine
  preseason uncertainty rather than hiding or arbitrarily resolving it.
- `starter_group_size == 0` cases (18 rows, 0.2%) correctly and
  honestly reflect real depth-chart snapshots where no player was ever
  listed at rank 1 for that team/position — not a computation error.

### #86 / #88 (`lib/dataset2/fragility_traits.py`)
- **Cross-module consistency confirmed**: `team_qb_uncertainty` fires
  ONLY in seasons 2019 (3.5%) and 2022 (3.4%), zero everywhere else —
  exactly matching #10's independently-found 5 real QB-tie cases.
- `body_size_position_z`: correctly centered per position (mean ≈0,
  std=1); the most extreme real outliers (a real 6'4"/285lb QB, a real
  6'2"/295lb TE) were individually inspected and are plausible, if
  unusually large-framed, real players — not data errors.
- `workload_qualified`: exclusively `"pending"` for every real row.

---

## 2. Warnings — acceptable, documented, not blocking

1. **Age (#2) and #10's 2025 schema branch could not be validated
   against real per-team kickoff dates in this environment** —
   `schedules.csv` is not cached here (see environment constraint
   above). #1/#4/#6 were still validated using the real library
   function (with a placeholder schedule that doesn't affect those
   three families' output). Re-run `age_at_week1_years` and the 2025
   depth-chart branch in an environment with real `schedules.csv`
   before trusting them.
2. **#9's "half split" does not guarantee an even real game count per
   half** — it's a calendar-week boundary, and real bye-week timing
   means an individual team's split can run roughly 7-9 games per half
   instead of a clean 8-8 (verified: `first_half_games +
   second_half_games` always equals the true season total, so no games
   are lost — just unevenly distributed between the two halves).
   Not previously disclosed; added a documentation note to
   `lib/dataset2/partial_season_traits.py` (no logic change).
3. **#10's missingness rises from ~16-20% (pre-2021) to ~23-29%
   (2021+)**. Investigated: driven by real low-involvement players in
   both eras (consistent direction), but the exact reason for the
   era-level increase (deeper real ADP-population coverage in recent
   years, more roster churn in 17-game seasons, or both) was not fully
   root-caused. Non-blocking; worth revisiting if #10-derived traits
   show an unexplained era effect later.
4. **One pre-existing, unrelated data-quality anomaly**: a single real
   2025 master-DB row (Rashid Shaheed) shows `games_played = 18`,
   exceeding the real 17-game season length. This is an upstream
   master-DB issue, not Dataset 2 code, and currently has ZERO effect
   on any Dataset 2 output (no season 2026 exists yet to lag from it) —
   but will silently produce a wrong `prior_season_games_played` once
   2026 data arrives, unless corrected upstream first.
5. `starter_group_size == 0` (18 real rows) is a real, if unusual,
   state — worth knowing it exists, not itself actionable.

---

## 3. Failures requiring code changes

**None.** No implementation bugs were found in this audit. Every
module's real-data behavior matched its documented design exactly;
where a real number looked surprising at first glance (the #8 trend-
slope missingness pattern, the #9 half-split asymmetry, #10's 5 QB
ties), direct investigation confirmed correct, explainable behavior
rather than a defect. Two documentation-only additions were made (see
Warnings #2 and Decision #1) — no test changes were needed since no
behavior changed.

---

## 4. Methodological decisions requiring approval

### Decision 1 (significant): the WR structural starter-count constant
does not match most of the real historical data

`config.DATASET2_DEPTH_CHART_STRUCTURAL_STARTER_COUNT["WR"] = 3` was
set from a single real 2020 spot-check plus the 2025 schema's own
`"3WR 1TE"` label. Checked now against the FULL real 2006-2024 history:
real WR `starter_group_size` was **2, not 3, in 85-99% of team-seasons
from 2006-2012**, and only becomes the real majority around **2023-2024
(59-64%)**. This reflects a real, gradual, well-documented shift in NFL
base-personnel usage (increasing "11 personnel"/3-WR-base adoption
over the 2010s-2020s) — not a data error.

**Real, measured impact**: currently **zero** effect on
`committee_uncertainty` (`lib/dataset2/fragility_traits.py`), because
that flag only fires when `starter_group_size` EXCEEDS the structural
constant, and WR's real historical deviation is a SHORTFALL (2 vs. an
expected 3), not an excess. But `position_starter_count` itself is
still an inaccurate REFERENCE VALUE for roughly the first decade of
data, which could matter to any future consumer that uses it
differently (a ratio, or a both-directions deviation flag).

**Options, not resolved here**:
- (a) Keep the single fixed constant, with this limitation now
  explicitly documented in `config.py`.
- (b) Make `position_starter_count` era-varying for WR — requires
  picking real era boundaries from data, the same kind of
  real-data-grounded threshold decision as family #9's sample-size
  floors.
- (c) Something else you'd prefer.

Not deciding this inline, per the standing rule this whole project has
followed: no new numeric threshold gets picked without your review.

### Decision 2 (minor, flagged for awareness only): #9's split
definition is calendar-week-based, not game-count-based

See Warning #2. This was an implicit consequence of the original
approved design (never explicitly decided one way or the other), not
a new discovery that changes anything by itself. No action needed
unless a strictly game-count-balanced split (e.g. "first N/2 games
actually played" rather than "games in calendar weeks 1..N/2") is
wanted instead — that would be a real methodology change, flagged here
only so it isn't silently assumed settled.

---

## Appendix: exact commands / population used

- Population: `data/master/master_historical_db_with_lwi_2006_2025.csv`
  filtered to `position in (QB, RB, WR, TE)` — 11,175 rows, matching
  the master DB's own skill-position scope exactly (no additional
  filtering applied).
- `players.csv`: `data/raw/nflverse/reference/players.csv`, real file,
  no modifications.
- Weekly data: `data/raw/nflverse/weekly_results_ppr_2006_2025.csv`,
  filtered to skill positions.
- Depth charts: all 19 real `data/raw/nflverse/annual/depth_charts_{season}.csv`
  files for 2006-2024, concatenated (701,856 raw rows before
  filtering). 2025's schema was NOT included in this run (see
  environment constraint).
- Every module was invoked via its real, committed public function
  (`build_experience_age_draft_traits()`, `build_prior_finish_traits()`,
  `build_prior_season_traits()`, `build_half_split_traits()`,
  `build_depth_chart_traits()`, `build_volume_fragility_traits()`,
  `build_durability_risk_traits()`) — not reimplemented or
  approximated for this audit.
