# League Winner Index (LWI) v2.1 -- Model Card

**Status: FINAL.** Confirmed via release verification directly against
production output (not experimental scripts): false-positive median
596 (exact match to the winsor-5/95 experiment), unique variance
15.46% (vs. tested 15.5%), Component3-4 correlation 0.942 (exact
match). 48 regression tests passing, full pipeline reruns clean.

## Purpose

Ranks historical fantasy football seasons (2006-2024, PPR scoring) by
**league-winning value** -- how much a player outperformed the actual
draft capital spent on them -- rather than by raw fantasy production.
A player who was the consensus #1 overall pick and simply delivered
what was expected is a good season, but not automatically a
league-winning *value*; a player drafted late who massively
outproduced that cost is exactly what this metric is built to surface.

Built as `scripts/05_calculate_metrics.py`, part of the
`fantasy_master_db_current` pipeline (`fantasy_master_db_current`
repo).

---

## Components (46/18/17/12/4/3, per the original project scope)

| # | Weight | Component | What it measures |
|---|---|---|---|
| 1 | 46% | LOSO Monotonic EVA + ADP-underperformance cap | Return on overall draft capital, vs. a historically-grounded expectation, with a hard floor if the player underperformed their own actual pick |
| 2 | 18% | Total Points Above Replacement | Full-season cumulative production, credited above a realistic replacement-level baseline, cross-position |
| 3 | 17% | PPG Above Replacement | Weekly scoring rate above replacement, cross-position |
| 4 | 12% | Standardized Positional Scarcity | How *unusual* a player's PPG-above-replacement gap was, relative to how tightly bunched that position's starter tier normally is (IQR-standardized) |
| 5 | 4% | Playoff Performance | 75% playoff-weeks PPG percentile + 25% playoff availability |
| 6 | 3% | Consistency | Coefficient-of-variation of weekly scoring |

### Component 1 in detail

```
expected_finish = isotonic_regression(overall_adp -> overall_finish)
                   fit on all OTHER 18 seasons (leave-one-season-out,
                   monotonic-smoothed so noise never lets an earlier
                   pick have a worse expected finish than a later one)

eva_raw = expected_finish - actual_overall_finish
eva_component = minmax_normalize(eva_raw, within season)

if actual_overall_finish > actual_overall_adp:   # genuinely worse
    component_1 = min(eva_component, 40)          # than the real pick
else:
    component_1 = eva_component
```

The cap exists because EVA alone can score a player positively for
beating a *historically bad* baseline (early picks bust often) even
when they lost real value versus their *own actual* draft cost --
confirmed on Arian Foster's 2012 season (drafted 1.4 overall, finished
12th: `eva_raw = +28.8` but `direct_raw = -10.6`).

### Component 4 in detail

```
replacement_ppg = median(ppg) among players ranked
                   [threshold, threshold+12] at that position+season
                   (thresholds: QB12 / RB34 / WR42 / TE12)

ppg_above_replacement = player_ppg - replacement_ppg

starter_iqr = IQR(ppg) among players ranked 1..threshold
              (the "starter tier") at that position+season

standardized = ppg_above_replacement / starter_iqr
component_4 = winsorized_minmax_normalize(standardized,
               clip to [5th, 95th] percentile, across all positions, within season)
```

IQR was chosen over standard deviation (weaker: only 15.8% unique
variance vs. IQR's) and tested head-to-head against MAD (very
close: MAD scored marginally better on unique variance and
known-winner ranking, IQR meaningfully better on false-positive
separation). IQR was selected specifically because false-positive
separation was judged more important than a few extra ranking spots
on true positives -- see "Design decisions" below.

**The final normalization step was later found to be a real bug and
fixed** -- plain min-max (used through an earlier rc) is highly
sensitive to its own extremes: verified directly that a single wild
outlier in ONE position's data could shift an UNRELATED player's score
in a DIFFERENT position by 60+ points, since the cross-position
normalization shares one range across all 4 positions within a season.
Fixed by winsorizing at the 5th/95th percentile before scaling --
tested head-to-head against plain min-max, percentile rank, and a
tighter 2.5/97.5 winsorization; 5/95 gave the best combination of
outlier robustness (0.0 point shift in the same test that showed 60+
before) and retained discriminative power. Real, accepted tradeoff:
unique variance dropped from 25.0% to 15.5% as a direct cost of fixing
the outlier vulnerability. The pre-clip raw value and the clipped
intermediate value are both kept as separate visible output columns
(`positional_advantage_raw`, `positional_advantage_winsorized`) so the
clipping itself is auditable, not hidden inside one opaque step.

---

## Validation performed

All tests run against real 2006-2024 data (2,643 eligible
player-seasons, `fantasy_master_db_current` repo).

**Known-winner control group** (real, well-documented breakout/value
seasons): Cooper Kupp 2021, Cam Newton 2011, Robert Griffin III 2012,
Josh Gordon 2013, Devonta Freeman 2015, David Johnson 2016, Alvin
Kamara 2017, Patrick Mahomes 2018, Lamar Jackson 2019, Peyton Hillis
2010. All 10 land in the top 3.2% of all eligible seasons under v2.1
(verified directly against production output); median rank 16, worst
rank 84 (David Johnson 2016).

**False-positive control group** (real, well-known "elite but not a
value pick" seasons): Arian Foster 2012, Rob Gronkowski 2015, Antonio
Brown 2017, Travis Kelce 2019, Dalvin Cook 2020. Median rank 596 of
2,643 (77th percentile), best (closest to top) rank 370 -- clearly
separated from the top tier, not mistaken for historic value picks.

**Ablation study**: removed each component one at a time and measured
top-100 rank movement. Impact scales proportionately with each
component's assigned weight (removing C1/46% caused massive movement,
57/100 top-100 overlap, median rank change 254; removing C5/4% and
C6/3% caused minimal movement, 96-98/100 overlap, median rank change
16-20) -- confirms no component is either dead weight or secretly
dominating beyond its intended share.

**Component independence**: found and fixed a real bug where an
earlier version of Components 3 and 4 were mathematically IDENTICAL
(Spearman correlation ~0.9999999, R-squared of 1.000 when Component 4
was regressed on Components 2+3 -- literally the same formula weighted
twice). Fixed by standardizing Component 4's denominator; final
Component3-Component4 correlation is 0.942 with Component 4 retaining
15.5% variance not explained by Components 2+3 (this dropped from an
initial 25% as a direct, accepted cost of the later winsorization fix
-- see "Component 4 in detail" above). Added a permanent
regression test (`TestNoDuplicateComponentFormulas`) generating
synthetic data and asserting no two of the 6 components exceed 0.999
correlation.

**Position balance**: top-100 position mix is WR36/RB33/QB25/TE6
(verified directly against production output) -- the most balanced of
every variant tested across this project's iteration (earlier
positional-only and unstandardized-VORP versions ranged from 5% to 16%
TE representation, both directions of distortion). Top-25: RB11/WR7/
QB5/TE2. Top-50: RB22/WR14/QB11/TE3. Top-250: WR90/QB68/RB67/TE25.

**Stability sweeps, all confirmed stable, verified directly against
production functions (not a parallel reimplementation)**:
- Minimum-games threshold (6/8/10): known-winner median 16-20,
  false-positive median 570-643 (stable)
- Playoff-window definition (era-appropriate / always weeks 14-16 /
  always weeks 15-17): known-winner median 16 (unchanged across all
  three), false-positive median 596-710 (stable)
- Standardization denominator (std/IQR/MAD): IQR selected on the
  precision-over-recall reasoning above, not because it was the only
  viable option

**Component 4 normalization comparison** (Component 1-3 held fixed;
real 2006-2024 data):

| Method | Unaffected-player shift (synthetic outlier test) | Unique variance | Known-winner median | False-positive median |
|---|---|---|---|---|
| Plain min-max (earlier rc) | 60-69 pts | 25.0% | 24 | 683 |
| Percentile rank | 0.0-0.4 pts | 15.2% | 14 | 631 |
| Winsor 2.5/97.5 | 0.0 pts | 18.5% | 22 | 585 |
| **Winsor 5/95 (chosen)** | **0.0 pts** | 15.5% | **16** | **596** |

Winsor 5/95 was chosen over the other robust alternatives because it
had zero synthetic cross-position contamination (matching winsor
2.5/97.5 and beating plain min-max decisively), better known-winner
AND false-positive separation than winsor 2.5/97.5, preserved
existing position balance across all four cutoffs (25/50/100/250,
checked directly), and retained more magnitude information than pure
percentile ranking (which converts Component 4 into an almost purely
ordinal signal, at odds with its purpose of capturing how large an
unusual advantage was, not just its rank).

**53 automated regression tests** (48 for the core LWI formula, grown
from an original 35; plus 5 more specifically for the undrafted-player
proxy mechanism in `tests/test_undrafted_proxy.py`), most tied
directly to a real bug found in this process -- see
`tests/test_calculate_metrics.py` and `tests/test_undrafted_proxy.py`.

---

## Undrafted player representation

**Design decision, finalized**: LWI measures league-winning value, not
merely return on draft investment -- an undrafted player absolutely
can be the biggest league winner of a season (James Robinson 2020 is
close to the canonical example). Excluding undrafted breakouts
entirely would make a metric literally named "League Winner Index"
measure something narrower than its own name implies.

**Mechanism**: ONE unified model, not a separate scoring path. A
VERIFIED undrafted player gets a modeled overall ADP (the global
maximum observed ADP across all 2006-2025 seasons, plus 1 -- fixed at
194.5, not season-relative) and then flows through the exact same
Component 1-6 pipeline as every drafted player. Binary
`adp_status` (drafted/undrafted) with a separate `verification_status`
(verified/unresolved) -- explicitly NOT a third "unknown" ADP state,
since "we haven't checked yet" and "confirmed undrafted" are different
claims that must never be conflated.

**Verified directly, not just designed**: temporarily added James
Robinson 2020 as a real mechanism test, reran the full pipeline,
confirmed he became eligible (2,643 -> 2,644 rows) and received a
real, credible score (81.74, rank 83 of 2,644) reflecting a genuine
value story rather than some broken extreme -- then reverted the test
entry and confirmed production returns to byte-identical output.

**Dataset 5 ("No-ADP Breakout Candidates")** now exists as the
research pipeline for this: 470 currently-`unresolved` players with a
top-24 positional finish, surfaced specifically to be checked against
additional historical ADP sources (MFL, RTSports, Underdog, etc.) and
either confirmed `verified`/`undrafted` (and scored) or found to have
been drafted somewhere our current source just doesn't reach.

**Remaining open work**: none of the 7 originally-discussed candidates
below are yet verified -- they're all still `unresolved`, correctly
excluded from LWI until someone actually checks additional sources for
each:

- Michael Vick, 2010
- Victor Cruz, 2011
- Justin Forsett, 2014
- James Robinson, 2020
- Puka Nacua, 2023
- Kyren Williams, 2023
- Geno Smith, 2022

All 7 are confirmed absent from this project's current ADP source
specifically (FFC/FFToday, which cover only the top ~92-214 drafted
players per year) -- confirmed via direct lookup against the raw
source data, ruling out a matching failure. But "absent from our
source" and "undrafted everywhere" are different claims; this
verification research is currently the single largest remaining gap
in the whole project, larger than any remaining formula question.

**Known limitation of the mechanism itself**: the fixed global-max
proxy (194.5) was not derived from anything beyond "one manager's
last-round decision is usually what separates the final pick from an
undrafted player" -- a reasonable, documented judgment call, not an
empirically derived value. Revisit if evidence suggests it's
miscalibrated once more players are actually verified and scored.

---

## Known limitations

**~~Cross-position min-max sensitivity~~ -- FOUND AND FIXED, not an
open limitation.** An earlier version's Component 4 used plain min-max
for its final cross-position normalization, which is highly sensitive
to its own extremes -- verified directly that a single wild outlier in
one position could shift an unrelated player's score in a different
position by 60+ points. This was initially (incorrectly) treated as an
accepted, documented limitation rather than fixed -- corrected after
review: the underlying formula was switched to winsorized min-max
(5th/95th percentile clip), which reduced the same test's shift to
0.0. See "Component 4 in detail" above for the fix and its real,
accepted cost (unique variance dropped from 25.0% to 15.5%).

**Replacement-level thresholds (QB12/RB34/WR42/TE12) are a conceptual
choice, not an empirical finding.** Real scoring-by-rank curves show
no natural "cliff" at any candidate threshold for any position, so no
specific threshold can be proven correct by the data alone.
Sensitivity-tested and confirmed the model is robust to reasonable
alternative choices (0.9996 rank correlation across the most divergent
configurations tested) -- but that's a claim about robustness, not
about any one threshold being the uniquely right answer.

---

## Design decisions and why (the falsification history)

Nearly every major structural change in this model was driven by a
concrete, real finding, not a hunch:

1. **Positional-only ADP comparison → overall comparison.** Found that
   comparing a player only to others at their own position let
   positionally-perfect-but-overall-declining seasons (Gronkowski
   2015: TE1→TE1 positionally, but drafted 10th overall, finished
   32nd) score as if they'd met expectations, when a real manager who
   spent an early pick on them experienced a real letdown.
2. **Overall min-max → LOSO monotonic EVA.** A player's ADP value
   comparison changing meaning based on how the rest of THAT season's
   draft class performed was judged less principled than comparing
   against an empirical, out-of-sample historical expectation for that
   exact draft slot.
3. **EVA alone → EVA + cap.** Found EVA could score a player positively
   for beating a bad historical baseline even when they lost value
   versus their own actual draft cost (Arian Foster 2012). The cap
   adds direct accountability to the actual pick spent, not just the
   historical average outcome for that neighborhood of picks.
4. **Components 2/3 raw/positional → replacement-adjusted → the
   Component 3/4 duplication bug → standardized Component 4.** Making
   production components replacement-adjusted (to fix QB
   over-domination from raw point totals) accidentally made Component
   3 mathematically identical to the (then-unstandardized) Component
   4. Standardizing Component 4 by the position's own scoring spread
   gave it a genuinely distinct job (not "how big was the gap" but
   "how unusual was that gap for this position") and resolved the
   duplication while also fixing an intermediate fallback's TE
   over-representation problem.
5. **IQR over standard deviation and MAD.** All three were tested
   head-to-head on real data. Standard deviation was clearly weakest.
   IQR vs. MAD was close; IQR was chosen specifically for its stronger
   false-positive separation, on the explicit judgment that precision
   (not letting a Kelce-2019-type season back toward the top) matters
   more than a few ranking spots of recall on true positives.

---

## What's next (per this model card's own recommendation)

1. **Verification research** for the 7 known undrafted-breakout
   candidates (and the broader Dataset 5 list) against additional
   historical ADP sources -- the mechanism to include them once
   confirmed now exists; this is purely research work now, not a
   design question.
2. **Dataset 2 (League Winner Traits)**: research into what preseason-
   available patterns actually correlate with becoming a league
   winner, per `docs/PREDICTION_SPECIFICATION.md`'s target definition.
3. **Dataset 3 (Predictive League Winner Probability)**: a model
   trained on Dataset 2's findings, strictly time-validated.
4. Use the finalized LWI to evaluate historical drafts and compare
   against simpler baseline metrics (raw points, raw ADP rank).
