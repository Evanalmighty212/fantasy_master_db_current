# LWI Component Audit (Deliverable 1, Dataset 3 research foundation)

Read-only audit of `scripts/05_calculate_metrics.py` (v2.1, per
`docs/METRIC_SPECIFICATION.md`) as it exists today. Purpose: know
exactly where total points, PPG, games played/availability, VORP,
ADP value, and playoff production already enter the current formula,
and where real overlap exists, BEFORE designing any new absolute-
impact "stars by value" methodology on top of it. This document
recommends no new weights, no formula changes, and no replacement-
level redefinition -- it is an inventory, not a proposal.

Component weights for reference: **46% ADP Value / 18% Fantasy
Finish Total Points / 17% PPG / 12% Positional Advantage / 4%
Playoff Performance / 3% Consistency.**

---

## 1. Where each raw quantity enters the current formula

### Total points (`fantasy_points_ppr`)

- **Component 2 (18%, direct)**: `points_above_replacement =
  fantasy_points_ppr - replacement_points`, min-max normalized within
  season, cross-position. (`compute_component_2_fantasy_finish`,
  `05_calculate_metrics.py:197-213`)
- **Component 1 (46%, indirect)**: `overall_finish_ppr` -- the input
  Component 1 actually compares against ADP -- is itself just the
  season's rank-ordering of `fantasy_points_ppr` across all
  positions. Component 1 never touches raw points directly; it only
  ever sees them through this rank transform.
- **Component 6 (3%, indirect)**: weekly `fantasy_points_ppr` values
  feed `consistency_raw = mean / stdev` of the same underlying weekly
  point stream.

### PPG (`ppg_ppr`)

- **Component 3 (17%, direct)**: `ppg_above_replacement = ppg_ppr -
  replacement_ppg`, min-max normalized within season, cross-position.
  (`compute_component_3_ppg`, `05_calculate_metrics.py:216-231`)
- **Component 4 (12%, direct, SAME numerator as Component 3)**: also
  starts from `ppg_above_replacement` (computed a second time inside
  `compute_component_4_positional_advantage`,
  `05_calculate_metrics.py:277-278` -- identical formula to Component
  3's line 230, just recomputed locally), then divides by
  `starter_ppg_iqr` and winsorizes before normalizing. See "Overlap"
  below -- this is the single most important structural fact in this
  audit.

### Games played / availability

**Revised per review: no EXPLICIT season-long availability term
exists, but an INDIRECT one does, and it's real, not negligible.**
The original draft of this audit said availability had "no
representation" in current LWI -- too strong. Corrected below, with
real numbers, not just the mechanism.

- **No direct, named "availability" term exists for the regular
  season.** `games_played` never appears as its own scored quantity
  outside the playoffs.
- **But Component 2 carries a real, measurable indirect availability
  penalty**, because `points_above_replacement = fantasy_points_ppr -
  replacement_points` and `replacement_points` is a fixed
  (season, position) constant -- it does NOT vary with the individual
  player's own games played. So two players with identical scoring
  RATE but different durability get different Component 2 scores,
  purely from games played. Verified directly against real
  2006-2024 eligible data (2,643 rows):
  - Raw correlation, `games_played` vs. `fantasy_finish_component`
    (Component 2): **0.558**.
  - Partial correlation, controlling for `ppg_ppr` (isolating the
    games-played effect from any confound with scoring rate):
    **0.558** -- essentially unchanged from the raw correlation,
    confirming this is a real, direct effect of durability itself,
    not an artifact of durable players also happening to score at a
    higher rate.
  - Same partial-correlation check for Component 3 (PPG-based, which
    is explicitly designed to divide games played out): **0.038** --
    correctly near zero, confirming Component 3 does NOT carry this
    effect (as intended) while Component 2 does.
  - **Concrete real example**: 2012 WR, Percy Harvin (9 games, 18.59
    PPG) vs. A.J. Green (16 games, 18.74 PPG) -- nearly identical
    scoring RATE, 7-game durability gap. Component 2 scores: Harvin
    27.1, Green 76.5 -- a 49-point gap on a 0-100 scale, driven almost
    entirely by games played, not scoring quality.
  - Component 1 inherits a smaller version of the same effect
    indirectly, since `overall_finish_ppr` (its target) is itself a
    rank of total points -- not independently verified with the same
    rigor here, since Component 1's LOSO/cap structure make a clean
    partial-correlation read less direct, but the same underlying
    mechanism (durability affects total points, which affects rank)
    applies.
- The **only EXPLICIT "played ÷ possible" term in the entire
  formula** is `playoff_availability` inside Component 5:
  `playoff_games_played / len(playoff_weeks)`, weighted at 25% of
  Component 5's 4% total weight -- **1.0% of the entire LWI score**,
  scoped only to the 3-week playoff window.
- **What's still genuinely missing, even accounting for the above**:
  missed games are never compared to what a REPLACEMENT would have
  produced in those specific missed weeks, anywhere in current LWI.
  Component 2's indirect penalty only reflects "this player
  accumulated fewer total points than a full season would have
  allowed" -- it says nothing about what a realistic replacement
  would have scored during the gap, which is the actual quantity the
  "realistic replacement production for missed games" direction is
  after. That remains a real, open gap, just a narrower one than the
  original draft implied.

**Why a new explicit availability term risks double-counting, not
just "adding a new signal"**: any new term that rewards games played
or penalizes missed games would be stacking on top of Component 2's
ALREADY-MEASURED 0.558 correlation with `games_played` -- not adding
availability information to a component that currently has none. A
new formula that (a) keeps something like Component 2's total-points-
above-replacement framing AND (b) adds an explicit availability/
replacement-during-absence term would be rewarding durability twice,
through two different mechanisms, unless one of the two is
deliberately redesigned to net out the other's effect first. This is
a real design fork for whoever builds the final formula: replace
Component 2's implicit penalty with an explicit one, or add an
explicit one and REMOVE Component 2's games-played sensitivity (e.g.
by using `ppg_above_replacement * min(games_played, full_season)`
instead of raw total points) -- doing neither, and simply adding an
availability term on top of Component 2 unchanged, would double-count.
No recommendation made here on which fork to take -- flagged so it
isn't accidentally done both ways at once.

### VORP / replacement level

- Components 2, 3, and 4 **all three** call the exact same shared
  helper, `compute_replacement_level()`
  (`05_calculate_metrics.py:117-139`), against the exact same
  `LWI_REPLACEMENT_RANK_THRESHOLDS` from `config.py`
  (`QB: 12, RB: 34, WR: 42, TE: 12`, `LWI_REPLACEMENT_WINDOW: 12`).
  The helper is deliberately shared (per its own docstring) so
  Components 2 and 4 can never silently drift into being the same
  formula on different columns without it being visible in one place.
- Practical implication for Dataset 3: **one config decision (the
  replacement-rank thresholds) simultaneously shapes 3 of 6
  components, worth 18% + 17% + 12% = 47% of total LWI weight.** If
  Deliverable 4's replacement-level exploration favors a different
  definition, that's a meaningfully different question from "what
  should Dataset 3 use" vs. "should this also change LWI itself" --
  worth keeping those two questions visibly separate rather than
  assuming a new replacement definition is a drop-in swap for the
  existing one.

### ADP value / acquisition cost

- **Component 1 only (46%)**. `overall_adp_model` (real ADP if
  drafted; the fixed global-max proxy, 194.5, if verified-undrafted)
  compared against a leave-one-season-out isotonic expected-finish
  curve, plus a hard cap if the player's actual finish was worse than
  their own actual ADP. No other component reads ADP at all.
- For undrafted players specifically, "acquisition cost" is a single
  fixed constant (194.5), not season-relative -- see
  `METRIC_SPECIFICATION.md`'s "Undrafted player representation"
  section for the full rationale.

### Playoff production

- **Component 5 only (4%)**. Production and availability are scored
  separately, not blended: `0.75 * playoff_ppg_percentile + 0.25 *
  (playoff_availability * 100)`. No other component touches playoff
  weeks specifically -- they're included in the season-long totals
  Components 2/3/4/6 use, but never isolated as "did this happen in
  the playoffs" outside Component 5.

---

## 2. Overlap and possible double-counting

**(a) Components 3 and 4 share an identical numerator.** Both start
from `ppg_above_replacement` -- Component 3 uses it directly;
Component 4 divides it by `starter_ppg_iqr`. This was a known, real
bug in an earlier version (the two were mathematically IDENTICAL,
Spearman ~0.9999999, before Component 4 was standardized) and has
since been fixed and tested -- current Component 3/4 correlation is
0.942 (per the Model Card), with Component 4 retaining ~15.5% unique
variance. **Not literal duplication anymore, but still meaningfully
correlated from a shared root quantity.** Relevant to Dataset 3: a
new absolute-impact formula that ALSO uses "PPG above replacement" in
some form would be a third use of the same root input, on top of two
existing ones.

**(b) Components 2 and 3 are the same two raw ingredients
(`fantasy_points_ppr`, `games_played`, via `ppg_ppr =
fantasy_points_ppr / games_played`) in total vs. rate form.** Tested
as genuinely non-redundant (this is the whole reason Component 3 was
restored to replacement-adjusted after the Component 3/4 duplication
was fixed elsewhere), but both are downstream of the identical two
source columns.

**(c) Component 1 is correlated with Component 2 by construction, not
by accident.** `overall_finish_ppr` (Component 1's target) is the
rank-order of the same `fantasy_points_ppr` Component 2 uses
directly. They diverge specifically where draft cost and replacement
level disagree -- which is the intended, useful separation LWI is
built around, not a flaw. Worth naming anyway: a "stars by value"
formula that separately combines a production term and a cost term
is structurally similar to what Components 1 and 2 jointly already
do.

**(d) Component 6 (Consistency) is a third independent statistical
transform of the same weekly `fantasy_points_ppr` series** that
underlies both Components 2/3/4 (via season totals and PPG) --
coefficient of variation, computed within `(season, position)` rather
than cross-position. Not redundant with the others (different
statistic, different grouping), but drawn from the same underlying
weekly data as everything else.

**(e) Revised: availability is NOT an open slot free of overlap risk
-- Component 2 already carries a real, measured availability signal
(0.558 correlation with `games_played`, verified above), even though
no component names it as such.** A new EXPLICIT availability term
would be entering territory Component 2 already partially occupies,
not filling an empty slot. See the dedicated explanation in the
"games played / availability" section above for exactly why this
creates real double-counting risk if not handled deliberately.

---

## 3. What this means for designing a new absolute-impact methodology

Not a recommendation -- three structural facts worth carrying into
that design conversation when it happens:

1. Any new formula that scores "production above some baseline" is
   entering territory Components 2, 3, and 4 already occupy (47% of
   current LWI weight, all keyed to one shared replacement-threshold
   config). Reusing vs. redefining that replacement level is a real
   design fork, not a detail.
2. Any new formula that scores "acquisition cost" is entering
   Component 1's territory (46% of current LWI weight) -- and for
   undrafted players specifically, current cost is a single fixed
   constant, not season-relative.
3. Availability/missed-games treatment is **not** collision-free the
   way the first draft of this audit claimed -- Component 2 already
   carries a real, measured (0.558 correlation) indirect availability
   penalty. What current LWI has never done is model replacement
   production DURING specific missed games, in the playoffs or the
   regular season -- that part of the direction is genuinely new. But
   an explicit availability term layered on top of Component 2
   unchanged would double-count durability, not add a clean new
   signal -- see the double-counting explanation above for the two
   ways to avoid that.

No weights, thresholds, or formulas are recommended here, per the
task scope.
