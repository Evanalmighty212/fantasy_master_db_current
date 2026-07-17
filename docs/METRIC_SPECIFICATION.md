# Metric Specification: League Winner Index (LWI)

This document formalizes the League Winner Index formula from
`docs/VERSION_1_SCOPE.md` BEFORE implementation (`05_calculate_metrics.py`).
Per the project's engineering principles, the formula and its exact
inputs should exist here first; the code should match this document,
not the other way around.

Target formula (from VERSION_1_SCOPE.md):
LWI = 46% ADP Value
+ 18% Fantasy Finish Total Points
+ 17% Points Per Game
+ 12% Positional Advantage
+  4% Playoff Performance
+  3% Consistency
  ---

## Known data gap -- read this before implementing

**Two of six components need weekly-level data that the pipeline does
not currently preserve.** `03_download_stats.py` downloads nflverse's
weekly data, but aggregates straight to season totals
(`games_played`, `fantasy_points_ppr`, `ppg_ppr`, finish ranks) and
discards the week-by-week detail. `Playoff Performance` and
`Consistency` are both inherently weekly-pattern metrics -- they
cannot be computed from the season-level `season_results_ppr_*.csv`
table as it currently exists.

**This needs to be resolved before those two components can be
implemented.** The two realistic options:
1. Extend `03_download_stats.py` to ALSO emit a weekly-level table
   (e.g. `data/raw/nflverse/weekly_results_ppr_<start>_<end>.csv`)
   alongside the season-level one it already produces.
2. Add a new script (`03b_download_weekly_results.py`) that re-derives
   weekly detail independently.

Option 1 is almost certainly better -- the weekly data is already
downloaded and sitting in memory inside `03_download_stats.py` before
it gets aggregated away; keeping a second output is cheap. This
document specifies the target metrics assuming that gap gets closed;
implementation of Priority 6/7 should close it as a prerequisite step,
not work around it.

Until that's built, `05_calculate_metrics.py` should compute the four
components that ARE possible today (ADP Value, Fantasy Finish Total
Points, Points Per Game, Positional Advantage = 93% of the total
weight) and explicitly flag Playoff Performance and Consistency as
`not_yet_computed` per row, rather than silently defaulting them to
zero (which would understate every player's LWI by a flat 7% in a way
that's easy to forget is a placeholder, not a real score).

---

## Scope: which rows get an LWI score

LWI requires an ADP baseline (see ADP Value below) -- it is a measure
of value RELATIVE TO DRAFT COST, which is meaningless for a player who
was never drafted. Therefore:

- **Only rows with `data_quality_flag` in (`matched_clean`,
  `matched_needs_review`) are eligible.** `no_adp_match` rows (7,131
  of 10,070 in the current master DB -- players who played but weren't
  matched to any ADP entry) do NOT get an LWI score. This is not a
  data-quality failure to fix later; it's the correct scope. A
  waiver-wire pickup with no draft cost cannot have a "value over
  draft cost" score by definition.
- **Minimum games-played threshold: 8 games.** A player who played 1-2
  games (season-ending injury, late-season call-up) shouldn't be
  scored on `ppg_ppr` alone -- a small sample of huge or terrible games
  produces a wildly unstable per-game average that isn't a meaningful
  signal. Rows below this threshold get `lwi_score = null` and
  `lwi_eligibility_flag = insufficient_games`, not a score computed
  from too little data. (8 games = half a 16-week season pre-2021,
  roughly half of a 17-week season post-2021 -- a round, defensible
  cutoff, not tuned to produce a particular result. Revisit if it
  turns out to exclude too many mid-season standouts.)

---

## Component 1: ADP Value (46% weight)

**What it measures**: how much better (or worse) a player performed
than their draft cost implied.

**Formula**:
adp_value_raw = positional_adp - position_finish_ppr
Positive = outperformed draft position (a "value" pick). Negative =
underperformed. Uses POSITIONAL rank on both sides (not overall) --
"RB12 who finished RB3" is the right comparison; "pick 45 overall who
finished 8th overall" mixes players across positions with very
different point distributions and isn't as clean a signal.

**Normalization**: min-max scale `adp_value_raw` to 0-100 WITHIN each
(season, position) group, since the raw range differs a lot by
position (a WR12->WR1 jump spans more rank-slots than a TE12->TE1
jump, since far fewer TEs get drafted at all).

**Why 46% weight**: this is explicitly the dominant factor per
VERSION_1_SCOPE.md's given weights -- the League Winner Index is
fundamentally about draft-value efficiency, not just "who scored the
most points" (that's a real-life explanation for why a raw
points-total leaderboard and an LWI leaderboard should look
noticeably different, and is worth calling out in any README/user-
facing explanation of the metric).

---

## Component 2: Fantasy Finish Total Points (18% weight)

**What it measures**: raw season point production, position-relative.

**Formula**: `fantasy_points_ppr`, min-max normalized to 0-100 WITHIN
each (season, position) group. Position-relative for the same reason
as above -- comparing a QB's 380 points to a TE's 180 points directly
would make every QB row automatically dominate this component
regardless of how good a fantasy season it actually was at the
position.

---

## Component 3: Points Per Game (17% weight)

**What it measures**: per-game production rate, position-relative.

**Formula**: `ppg_ppr`, min-max normalized to 0-100 WITHIN each
(season, position) group. Same position-relative logic as Component 2.
Only computed for rows meeting the 8-game minimum (see Scope above) --
this is the component the games-played floor protects most directly.

---

## Component 4: Positional Advantage (12% weight)

**What it measures**: how much a player outscored a "replacement
level" player at their position that season -- i.e. marginal value
over what was freely available, not just raw rank.

**Formula**:
replacement_level_ppg = median(ppg_ppr) for all players at this
position+season with position_finish_ppr
between [RANK_THRESHOLD] and [RANK_THRESHOLD + 12]
positional_advantage_raw = ppg_ppr - replacement_level_ppg
`RANK_THRESHOLD` (the "replacement level" cutoff rank) should be set
per position based on typical league roster construction -- this needs
one explicit decision before implementation, e.g.: QB12, RB30, WR36,
TE12 (rough 12-team-league-with-2-flex-ish starting-slot assumptions).
**This threshold is a real design choice, not a technical detail --
flag it for review before implementation rather than picking a number
silently.**

**Normalization**: min-max scale `positional_advantage_raw` to 0-100
within (season, position).

---

## Component 5: Playoff Performance (4% weight) -- BLOCKED on weekly data

**What it should measure**: performance specifically in fantasy
playoff weeks, since a League Winner Index should reward players who
performed when it mattered for actually winning a league, not just
compiled good full-season stats.

**Open design question, not yet decided**: which weeks count as
"playoffs" varies by league (commonly weeks 15-17, sometimes 14-16 or
15-16 depending on league format and season length changes -- e.g.
the 2021 expansion to 17 games shifted common playoff-week
conventions). This needs an explicit decision (likely: weeks 15-17 as
the default assumption, clearly documented as an assumption, with
sensitivity noted) once weekly data exists to compute it from at all.

**Formula (once weekly data exists)**:
playoff_ppg = mean(weekly fantasy_points_ppr for weeks 15-17)
playoff_performance_raw = playoff_ppg - ppg_ppr  (season-average)
Positive = player elevated in the playoffs relative to their own
season baseline. Normalize to 0-100 within (season, position).

**Status**: cannot be implemented until the weekly-data gap (see top
of this document) is closed.

---

## Component 6: Consistency (3% weight) -- BLOCKED on weekly data

**What it should measure**: week-to-week reliability -- a player who
scores 15 points every week is more valuable to a real fantasy manager
than one who alternates between 30 and 2, even at the same season
total.

**Formula (once weekly data exists)**:
consistency_raw = 1 / (coefficient_of_variation of weekly fantasy_points_ppr)
= mean(weekly_points) / stdev(weekly_points)
Higher = more consistent (lower relative variance). Normalize to 0-100
within (season, position). Weeks with 0 points due to bye weeks should
be EXCLUDED from this calculation (a bye week isn't "inconsistency,"
it's a scheduled non-event) -- only weeks the player was
active/eligible to play count.

**Status**: cannot be implemented until the weekly-data gap is closed.

---

## Final LWI formula
LWI = 0.46 * adp_value_normalized
+ 0.18 * fantasy_finish_normalized
+ 0.17 * ppg_normalized
+ 0.12 * positional_advantage_normalized
+ 0.04 * playoff_performance_normalized   [0 or excluded until built]
+ 0.03 * consistency_normalized            [0 or excluded until built]

  **Interim formula, until the weekly-data gap is closed** -- re-weight
the four available components proportionally rather than silently
scoring everyone out of a 93%-max ceiling:
LWI_interim = (0.46 * adp_value_normalized
+ 0.18 * fantasy_finish_normalized
+ 0.17 * ppg_normalized
+ 0.12 * positional_advantage_normalized) / 0.93

  This keeps the interim score on a real 0-100 scale while the two
weekly-dependent components are still unbuilt, and makes it visually
obvious (via a `lwi_component_coverage` flag = `interim_4_of_6` vs
`complete_6_of_6`) which scoring methodology produced any given row,
so interim and final scores are never silently compared as if
equivalent.

---

## Output schema (proposed)

Per (season, player_id) row, in addition to everything already in
`master_historical_db_*.csv`:
lwi_score                        (0-100, or null if ineligible)
lwi_eligibility_flag             (eligible / insufficient_games / no_adp_match)
lwi_component_coverage           (interim_4_of_6 / complete_6_of_6)
adp_value_component
fantasy_finish_component
ppg_component
positional_advantage_component
playoff_performance_component    (null until weekly data exists)
consistency_component            (null until weekly data exists)
---

## Open decisions requiring explicit sign-off before implementation

1. Replacement-level rank threshold per position (Component 4) --
   proposed QB12/RB30/WR36/TE12, not yet confirmed.
2. Playoff week definition (Component 5) -- proposed weeks 15-17,
   not yet confirmed, and may need to vary by season given the 2021
   17-game expansion.
3. Whether `lwi_score` should be published at all for rows still using
   the interim 4-component formula, or held back until all six
   components exist -- there's a real argument for either "show
   interim scores clearly labeled as such" or "don't publish until
   complete" and this is a product decision, not a technical one.
