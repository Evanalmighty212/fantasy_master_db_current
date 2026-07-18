Metric Specification: League Winner Index (LWI)
This document formalizes the League Winner Index formula from
docs/VERSION_1_SCOPE.md BEFORE implementation (05_calculate_metrics.py).
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

Known data gap -- read this before implementing
Two of six components need weekly-level data that the pipeline does
not currently preserve. 03_download_stats.py downloads nflverse's
weekly data, but aggregates straight to season totals
(games_played, fantasy_points_ppr, ppg_ppr, finish ranks) and
discards the week-by-week detail. Playoff Performance and
Consistency are both inherently weekly-pattern metrics -- they
cannot be computed from the season-level season_results_ppr_*.csv
table as it currently exists.
This needs to be resolved before those two components can be
implemented. The two realistic options:

Extend 03_download_stats.py to ALSO emit a weekly-level table
(e.g. data/raw/nflverse/weekly_results_ppr_<start>_<end>.csv)
alongside the season-level one it already produces.
Add a new script (03b_download_weekly_results.py) that re-derives
weekly detail independently.

Option 1 is almost certainly better -- the weekly data is already
downloaded and sitting in memory inside 03_download_stats.py before
it gets aggregated away; keeping a second output is cheap. This
document specifies the target metrics assuming that gap gets closed;
implementation of Priority 6/7 should close it as a prerequisite step,
not work around it.
Until that's built, 05_calculate_metrics.py should compute the four
components that ARE possible today (ADP Value, Fantasy Finish Total
Points, Points Per Game, Positional Advantage = 93% of the total
weight) and explicitly flag Playoff Performance and Consistency as
not_yet_computed per row, rather than silently defaulting them to
zero (which would understate every player's LWI by a flat 7% in a way
that's easy to forget is a placeholder, not a real score).

Scope: which rows get an LWI score
LWI requires an ADP baseline (see ADP Value below) -- it is a measure
of value RELATIVE TO DRAFT COST, which is meaningless for a player who
was never drafted. Therefore:

Only rows with data_quality_flag in (matched_clean,
matched_needs_review) are eligible. no_adp_match rows (7,131
of 10,070 in the current master DB -- players who played but weren't
matched to any ADP entry) do NOT get an LWI score. This is not a
data-quality failure to fix later; it's the correct scope. A
waiver-wire pickup with no draft cost cannot have a "value over
draft cost" score by definition.
Minimum games-played threshold: 8 games. A player who played 1-2
games (season-ending injury, late-season call-up) shouldn't be
scored on ppg_ppr alone -- a small sample of huge or terrible games
produces a wildly unstable per-game average that isn't a meaningful
signal. Rows below this threshold get lwi_score = null and
lwi_eligibility_flag = insufficient_games, not a score computed
from too little data. (8 games = half a 16-week season pre-2021,
roughly half of a 17-week season post-2021 -- a round, defensible
cutoff, not tuned to produce a particular result. Revisit if it
turns out to exclude too many mid-season standouts.)


Component 1: ADP Value (46% weight)
What it measures: how much better (or worse) a player performed
than their draft cost implied.
Formula:
adp_value_raw = positional_adp - position_finish_ppr
Positive = outperformed draft position (a "value" pick). Negative =
underperformed. Uses POSITIONAL rank on both sides (not overall) --
"RB12 who finished RB3" is the right comparison; "pick 45 overall who
finished 8th overall" mixes players across positions with very
different point distributions and isn't as clean a signal.
Normalization: min-max scale adp_value_raw to 0-100 WITHIN each
(season, position) group, since the raw range differs a lot by
position (a WR12->WR1 jump spans more rank-slots than a TE12->TE1
jump, since far fewer TEs get drafted at all).
Why 46% weight: this is explicitly the dominant factor per
VERSION_1_SCOPE.md's given weights -- the League Winner Index is
fundamentally about draft-value efficiency, not just "who scored the
most points" (that's a real-life explanation for why a raw
points-total leaderboard and an LWI leaderboard should look
noticeably different, and is worth calling out in any README/user-
facing explanation of the metric).

Component 2: Fantasy Finish Total Points (18% weight)
What it measures: raw season point production, position-relative.
Formula: fantasy_points_ppr, min-max normalized to 0-100 WITHIN
each (season, position) group. Position-relative for the same reason
as above -- comparing a QB's 380 points to a TE's 180 points directly
would make every QB row automatically dominate this component
regardless of how good a fantasy season it actually was at the
position.

Component 3: Points Per Game (17% weight)
What it measures: per-game production rate, position-relative.
Formula: ppg_ppr, min-max normalized to 0-100 WITHIN each
(season, position) group. Same position-relative logic as Component 2.
Only computed for rows meeting the 8-game minimum (see Scope above) --
this is the component the games-played floor protects most directly.

Component 4: Positional Advantage (12% weight)
What it measures: how much a player outscored a "replacement
level" player at their position that season -- i.e. marginal value
over what was freely available, not just raw rank.
Formula:
replacement_level_ppg = median(ppg_ppr) for all players at this
position+season with position_finish_ppr
between [RANK_THRESHOLD] and [RANK_THRESHOLD + 12]
positional_advantage_raw = ppg_ppr - replacement_level_ppg
RANK_THRESHOLD (the "replacement level" cutoff rank) should be set
per position based on typical league roster construction -- this needs
one explicit decision before implementation, e.g.: QB12, RB30, WR36,
TE12 (rough 12-team-league-with-2-flex-ish starting-slot assumptions).
This threshold is a real design choice, not a technical detail --
flag it for review before implementation rather than picking a number
silently.
Normalization: min-max scale positional_advantage_raw to 0-100
within (season, position).

Component 5: Playoff Performance (4% weight)
What it should measure: performance specifically in fantasy
playoff weeks, since a League Winner Index should reward players who
performed when it mattered for actually winning a league, not just
compiled good full-season stats.
Playoff week definition -- RESOLVED, verified against the actual
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
Known limitation, stated plainly rather than hidden: this is a
chosen convention, not a universal truth. Individual leagues vary --
some run playoffs across different week counts, some use different
cutoffs entirely for different league sizes. If this ever needs to
support league-specific playoff windows rather than one dataset-wide
assumption, that's a real scope change, not a tweak.
Formula -- production and availability scored separately, not
blended into one raw average. A player who played 1 of 3 playoff
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
Open sub-issue: byes landing inside the playoff window. NFL bye
weeks typically fall well before week 14, but it's not structurally
guaranteed -- a bye landing on week 14 specifically (the first playoff
week in the 2006-2020 definition) is a rare but real possibility.
weekly_results_ppr_*.csv as currently built has no way to distinguish
"missed this week because of a bye" from "missed this week because of
injury/inactive" -- both simply produce no row for that week. Right
now, playoff_availability would count a bye the same as a missed
game, which isn't quite right (a bye isn't a fantasy-relevant
availability failure the way an injury is). Properly fixing this needs
team schedule/bye-week data, which isn't in the pipeline yet (likely
source: nfl_data_py.import_schedules(), not yet integrated or
access-tested). Flagging as a known gap rather than silently treating
every missing week the same; low-impact given how rarely a bye
actually lands in weeks 14-17, but worth fixing properly before
treating playoff_availability as fully authoritative.
Status: cannot be implemented until the weekly-data gap (see top
of this document) is closed. NOTE: as of the 03_download_stats.py
update that added weekly_results_ppr_*.csv, this gap IS closed --
this component is now unblocked and ready for implementation (modulo
the bye-week sub-issue above, which is a refinement, not a blocker).

Component 6: Consistency (3% weight) -- BLOCKED on weekly data
What it should measure: week-to-week reliability -- a player who
scores 15 points every week is more valuable to a real fantasy manager
than one who alternates between 30 and 2, even at the same season
total.
Formula (once weekly data exists):
consistency_raw = 1 / (coefficient_of_variation of weekly fantasy_points_ppr)
= mean(weekly_points) / stdev(weekly_points)
Higher = more consistent (lower relative variance). Normalize to 0-100
within (season, position). Weeks with 0 points due to bye weeks should
be EXCLUDED from this calculation (a bye week isn't "inconsistency,"
it's a scheduled non-event) -- only weeks the player was
active/eligible to play count.
Status: cannot be implemented until the weekly-data gap is closed.
NOTE: as of the 03_download_stats.py update that added
weekly_results_ppr_*.csv, this gap IS closed -- this component is
now unblocked and ready for implementation.

Final LWI formula
LWI = 0.46 * adp_value_normalized
+ 0.18 * fantasy_finish_normalized
+ 0.17 * ppg_normalized
+ 0.12 * positional_advantage_normalized
+ 0.04 * playoff_performance_normalized   [0 or excluded until built]
+ 0.03 * consistency_normalized            [0 or excluded until built]
Interim formula, until the weekly-data gap is closed -- re-weight
the four available components proportionally rather than silently
scoring everyone out of a 93%-max ceiling:
LWI_interim = (0.46 * adp_value_normalized
+ 0.18 * fantasy_finish_normalized
+ 0.17 * ppg_normalized
+ 0.12 * positional_advantage_normalized) / 0.93
This keeps the interim score on a real 0-100 scale while the two
weekly-dependent components are still unbuilt, and makes it visually
obvious (via a lwi_component_coverage flag = interim_4_of_6 vs
complete_6_of_6) which scoring methodology produced any given row,
so interim and final scores are never silently compared as if
equivalent.

Output schema (proposed)
Per (season, player_id) row, in addition to everything already in
master_historical_db_*.csv:
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

Open decisions requiring explicit sign-off before implementation

Replacement-level rank threshold per position (Component 4) --
proposed QB12/RB30/WR36/TE12, not yet confirmed.
Playoff week definition (Component 5) -- RESOLVED: weeks 14-16
for 2006-2020 seasons, weeks 15-17 for 2021-2024 seasons, verified
against actual max-week-per-season in the real weekly data.
Formula also resolved: 75% playoff PPG percentile + 25% playoff
availability (games played / 3), rather than a single blended raw
average -- prevents one huge game in a 1-of-3-played playoff stretch
from scoring like a full three-week dominant performance.
NEW, smaller: bye weeks landing inside the playoff window (rare but
possible for week 14 specifically) currently can't be distinguished
from a genuine missed/injured week in playoff_availability --
needs team schedule data not yet in the pipeline
(nfl_data_py.import_schedules(), untested for access). Low-impact
given rarity, but real -- see Component 5 for detail.
Whether lwi_score should be published at all for rows still using
the interim 4-component formula, or held back until all six
components exist -- there's a real argument for either "show
interim scores clearly labeled as such" or "don't publish until
complete" and this is a product decision, not a technical one.

