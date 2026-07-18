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
`RANK_THRESHOLD` (the "replacement level" cutoff rank) -- CONFIRMED:
QB12 / RB34 / WR42 / TE12. This is a CONCEPTUAL definition choice, not
an empirical finding -- see the note below the normalization section
for why, and why it should not be described as "empirically
validated."

**Normalization -- CORRECTED, real bug found and fixed via testing**:
min-max scale `positional_advantage_raw` to 0-100 across ALL positions
within a season, NOT within (season, position). This was originally
implemented grouped by (season, position), which is a genuine
methodological bug, not a style choice: subtracting a per-position
CONSTANT (the replacement level) and then min-max normalizing WITHIN
THAT SAME POSITION GROUP mathematically erases the constant entirely
-- min-max normalization (and z-score, and percentile rank) only
depends on relative spacing within the group, which a uniform shift
doesn't change. This made Component 4 silently IDENTICAL to Component
3 for every row, regardless of what `RANK_THRESHOLD` was set to --
proven directly with plain arithmetic (shifting a series by 18 vs. by
14 before min-max normalizing produces bit-identical output). The
whole point of a replacement-level comparison is to let value be
compared ACROSS positions on a shared baseline-adjusted scale (the
same idea as "Value Over Replacement Player" in other sports
analytics) -- grouping by position again defeats that structurally.

Verified against real data after the fix (this finding is about the
GROUPING bug specifically, independent of which threshold values are
used -- see below for the separate threshold-choice discussion): the
correlation between Component 3 and Component 4 dropped from a
perfect 1.0 (proving they were mathematically identical before) to
0.86-0.99 depending on position. The real top-10 LWI list shifted
meaningfully once fixed -- several historically-scarce TE seasons
(Gronkowski 2011, Jordan Reed 2015) moved up, which is the expected,
correct behavior of a positional-scarcity-aware metric, not noise.

**Replacement thresholds -- how QB12/RB34/WR42/TE12 was chosen, and
why "empirically validated" is the WRONG way to describe it.** Real
historical scoring-by-rank curves (2006-2024) show NO natural cliff at
any candidate threshold for any position -- every position decays
steeply through its elite tier, then smoothly and continuously, with
no second discontinuity marking "starter" vs. "waiver level." That
means no threshold choice can be empirically PROVEN correct; the
choice is fundamentally conceptual (what does "freely available"
mean?), not something the data can settle on its own.

The conceptual reasoning for QB12/RB34/WR42/TE12: QB and TE both have
fast-replenishing replacement pools (streaming QBs, thin but
undifferentiated TE waiver options), so the "last mandatory starter"
and "freely available player" roughly coincide at rank 12 for both.
RB and WR do not -- fantasy managers systematically hoard bench RBs
(handcuffs, committees, injury insurance) and rosterable WRs (bye-week
streaming, PPR floor plays) well past their teams' mandatory starting
slots, so a "last starter" cutoff (RB30, WR36) understates how deep
"not actually available on waivers" goes. RB34/WR42 sit deeper than
the naive starter-slot count without overshooting into pure
bench-filler territory -- this is a working compromise between
plausible interpretations, not a hidden true value.

**What WAS empirically tested, and should be described this way**:
whether the LWI model's overall behavior is stable across reasonable
alternative threshold choices -- not whether any specific threshold is
"correct." Tested QB12/RB30/WR36/TE12 (starter-level) against
QB12/RB34/WR42/TE12 (the chosen compromise) and QB12/RB36/WR42/TE12
(deeper waiver-level), using real 2006-2024 data:
- Rank correlation between the two most divergent configurations:
  0.9996.
- Top-25 set overlap: 23 of 25 players identical.
- Top-100 set overlap: 97 of 100 players identical.
- Median rank movement across all 2,643 eligible player-seasons: 8
  places (95th percentile: 49).
- Per-season #1 (the literal "league winner" identification) changed
  in 2 of 18 seasons under the most extreme comparison -- but both
  were already razor-margin races (0.02 and ~0.1 points on a 100-point
  scale, e.g. DeAngelo Williams vs. Steve Slaton in 2008) that could
  plausibly tip either way from minor input changes, not cases of a
  clear #1 being meaningfully displaced.

**Correct framing for this decision**: replacement thresholds are
defined as QB12/RB34/WR42/TE12 based on a conceptual reading of
"freely available" under typical 12-team PPR roster construction.
Sensitivity testing across reasonable alternatives showed LWI rankings
are highly robust to the specific thresholds chosen. These are two
separate claims -- the first is a judgment call, the second is a
tested fact -- and neither should be used to imply the other.

---

## Component 5: Playoff Performance (4% weight)

**What it should measure**: performance specifically in fantasy
playoff weeks, since a League Winner Index should reward players who
performed when it mattered for actually winning a league, not just
compiled good full-season stats.

**Playoff week definition -- RESOLVED**, verified against the actual
weekly data rather than assumed:

Seasons 2006-2020 (confirmed max week = 17, 16-game NFL seasons):
    playoff_weeks = [14, 15, 16]
Seasons 2021-2024 (confirmed max week = 18, 17-game NFL seasons):
    playoff_weeks = [15, 16, 17]

Rationale: this mirrors how fantasy platforms (ESPN, Yahoo, Sleeper)
actually shifted their own default playoff-week settings when the NFL
expanded in 2021 -- both definitions use the same RELATIVE position
(the final 3 weeks before the last week of the season, which real NFL
teams often treat as low-stakes/rest-starters, and which fantasy
leagues have therefore always excluded from playoffs regardless of era).

**Known limitation, stated plainly rather than hidden**: this is a
chosen convention, not a universal truth. Individual leagues vary --
some run playoffs across different week counts, some use different
cutoffs entirely for different league sizes. If this ever needs to
support league-specific playoff windows rather than one dataset-wide
assumption, that's a real scope change, not a tweak.

**Formula -- production and availability scored separately, not
blended into one raw average.** A player who played 1 of 3 playoff
weeks and scored huge should NOT rank like a dominant three-week
playoff performer -- a real fantasy manager needed them available for
all three weeks, not just one:

playoff_games_played = count of playoff_weeks where the player has a
                        row in weekly_results_ppr (i.e. genuinely played)
playoff_availability = playoff_games_played / len(playoff_weeks)   # 0, 1/3, 2/3, or 1

if playoff_games_played > 0:
    playoff_ppg = mean(fantasy_points_ppr across the weeks they DID play
                  within the window)  -- NOT divided by 3; a rate among
                  games actually played, matching how ppg_ppr is defined
                  everywhere else in this spec
    playoff_ppg_percentile = percentile rank of playoff_ppg within
                              (season, position), among players with
                              playoff_games_played > 0
else:
    playoff_ppg_percentile = 0   # no games played -> floor, avoids an
                                   undefined average rather than a
                                   silently-skipped row

playoff_performance_raw = 0.75 * playoff_ppg_percentile
                         + 0.25 * playoff_availability
(Both terms are already 0-1; scale the result to 0-100 for the
component, consistent with every other component's output range.)

Note this deliberately uses PERCENTILE rank for the production term
rather than the min-max scaling used elsewhere in this spec -- a
3-week sample is small and noisy enough that a single monster game can
distort a min-max range badly; percentile rank is more robust to that
kind of outlier at this sample size. This is an intentional
methodological difference for this one component, not an
inconsistency to "fix" later.

**Open sub-issue: byes landing inside the playoff window (documented
limitation, not urgent).** NFL bye weeks typically fall well before
week 14, but it's not structurally guaranteed -- a bye landing on week
14 specifically (the first playoff week in the 2006-2020 definition)
is a rare but real possibility. `weekly_results_ppr_*.csv` as
currently built has no way to distinguish "missed this week because of
a bye" from "missed this week because of injury/inactive" -- both
simply produce no row for that week, and both are currently treated
identically: zero production, reduced availability.

**Why this isn't just low-priority but conceptually imprecise**: a bye
week and an injury absence aren't the same kind of missing data. An
injury means the player had a real opportunity to produce and didn't
(a genuine performance gap). A bye means there was no game for that
team at all that week -- no opportunity existed to convert or miss.
Treating a bye as equivalent to a missed opportunity is, if anything,
HARSHER than treating an injury that way, since the player did nothing
wrong and had no chance to. The eventual correct fix is real team
schedule/bye-week data (likely source: `nfl_data_py.import_schedules()`,
not yet integrated or access-tested) to exclude bye weeks from the
playoff window's denominator entirely rather than counting them as a
missed opportunity.

**Decision: leave the calculation as-is for now, don't block current
work on it.** The impact is uncommon (byes rarely land in weeks 14-17
specifically), confined to a small number of historical rows, and
unlikely to materially change the League Winner Index's broad
conclusions. This is tracked here as a known limitation and backlog
item, not forgotten -- future schedule-data integration should
distinguish team byes from player-level missed games in
`playoff_availability`.

**Status**: unblocked and ready for implementation (modulo the
bye-week sub-issue above, which is a real but low-priority documented
limitation, not a blocker).

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
NOTE: as of the `03_download_stats.py` update that added
`weekly_results_ppr_*.csv`, this gap IS closed -- this component is
now unblocked and ready for implementation.

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

## Component availability policy

Moot today (all 6 components are implemented, and every eligible row
gets a real value for each one), but the policy is stated here now, in
case a future data-source change ever breaks one component again the
way the weekly-data gap did:

- **Never silently redistribute a missing component's weight.** A
  score computed from 5 of 6 components is a DIFFERENT measurement
  than one computed from all 6 -- re-weighting to still land on a
  0-100 scale would make the two look directly comparable when they
  aren't.
- **Incomplete scores are never shown in the ordinary `lwi_score`
  column.** That column means "the real, complete score" or nothing.
  An incomplete row gets `lwi_score = null` and
  `lwi_component_coverage` set to something other than
  `complete_6_of_6` (e.g. `incomplete_5_of_6`), not a number that
  looks like a normal score.
- **Incomplete rows are excluded from rankings by default.** Any
  future ranking/leaderboard output (`06_generate_rankings.py`) should
  filter to `lwi_component_coverage == complete_6_of_6` unless
  diagnostics are explicitly requested.
- **A diagnostic partial score MAY be retained separately**, clearly
  labeled with its component coverage (e.g. a `lwi_score_diagnostic`
  column noting `5/6 components available`), for someone who wants to
  look anyway -- but never in the main column, and never silently
  treated as equivalent to a complete score.

The failure mode this policy exists to prevent: a score of 78
calculated from six components and a score of 78 calculated from five
would look identical in a leaderboard, even though they're different
measurements built on different information. Silence there is worse
than an honest gap.

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
playoff_games_played             (0-3, diagnostic detail behind the component above)
playoff_availability             (0, 0.33, 0.67, or 1 -- diagnostic detail)
consistency_component            (null until weekly data exists)

---

## Open decisions requiring explicit sign-off before implementation

1. ~~Replacement-level rank threshold per position (Component 4)~~ --
   CONFIRMED: QB12/RB34/WR42/TE12. Important distinction in how this
   is described (a real correction made during review -- an earlier
   draft of this section incorrectly called QB12/RB30/WR36/TE12
   "empirically validated," which conflated two different claims):
   the specific threshold values are a CONCEPTUAL choice based on what
   "freely available" means under typical 12-team PPR roster
   construction -- real scoring data shows no natural cliff at any
   candidate value, so no threshold can be empirically proven correct.
   What WAS empirically tested and confirmed is that the LWI model's
   overall behavior is robust to reasonable alternative choices (0.9996
   rank correlation between the most divergent configurations tested,
   23/25 and 97/100 top-25/top-100 set overlap, 2/18 season-winner
   flips and both were already razor-margin races). See Component 4
   above for the full writeup and the reasoning for RB34/WR42 over the
   originally-proposed RB30/WR36.
2. ~~Playoff week definition (Component 5)~~ -- RESOLVED: weeks 14-16
   for 2006-2020 seasons, weeks 15-17 for 2021-2024 seasons, verified
   against actual max-week-per-season in the real weekly data.
   Formula also resolved: 75% playoff PPG percentile + 25% playoff
   availability (games played / 3), rather than a single blended raw
   average -- prevents one huge game in a 1-of-3-played playoff stretch
   from scoring like a full three-week dominant performance.
3. NEW, smaller: bye weeks landing inside the playoff window (rare but
   possible for week 14 specifically) currently can't be distinguished
   from a genuine missed/injured week in `playoff_availability` --
   needs team schedule data not yet in the pipeline
   (`nfl_data_py.import_schedules()`, untested for access). Low-impact
   given rarity, but real -- see Component 5 for detail.
4. Whether `lwi_score` should be published at all for rows still using
   the interim 4-component formula, or held back until all six
   components exist -- there's a real argument for either "show
   interim scores clearly labeled as such" or "don't publish until
   complete" and this is a product decision, not a technical one.
