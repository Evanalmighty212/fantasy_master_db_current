# League Winner Traits Specification (Dataset 2)

Written before any trait-research code, per the same principle as
`METRIC_SPECIFICATION.md` and `PREDICTION_SPECIFICATION.md`: the spec
exists first, research matches it, not the other way around. Every
classification below is a PROPOSAL requiring sign-off.

**Purpose -- TWO distinct outputs, not one.** These are different
research questions with different audiences, and conflating them
makes it unclear later which conclusions are safe to use where:

1. **Predictive Traits**: "what information available before Week 1
   predicts becoming a league winner?" Output feeds Dataset 3's
   feature engineering directly -- every trait here gets tested
   against the leakage rule, the baseline/lift framework, and the
   "Predictive usefulness" summary table (see below).
2. **Historical Findings**: "what actually happened to historical
   league winners, and why?" Valuable as standalone research --
   articles, visualizations, write-ups -- even for patterns that are
   completely unusable as predictive features (in-season narratives,
   descriptive-only traits, anything that can't clear the leakage
   bar). Not every interesting finding needs to justify itself as a
   model feature to be worth publishing.

Bucket 3 below (descriptive-only) feeds Historical Findings
exclusively. Buckets 1 and 2, once tested, split between both outputs
-- a trait can be a compelling historical finding AND a validated
predictive feature, or compelling as history while failing the
predictive bar (see "Descriptive vs. predictive" section below for
exactly when that split happens).

Checked directly against the current schema
(`master_historical_db_with_lwi_2006_2025.csv`) before writing any
claim below about what's already available -- see each trait's
"source" line.

**Prior-season availability, checked at the player-season level (the
correct unit), not unique-player count**: of 2,643 eligible player-
seasons, **2,371 (89.7%) have a valid immediate prior season**, 248
(9.4%) are genuine first appearances (rookies, or possibly players
whose real careers started before this dataset's 2006 floor --
can't distinguish those two sub-cases without pre-2006 data), and 24
(0.9%) are real gap years (player has earlier data but skipped the
immediately preceding season, most plausibly injury or a year outside
the league). This means lagged features are broadly usable but
**rookies cannot simply be dropped** -- see the dedicated rookie path
after the bucket definitions below.

---

## The four buckets, and the rule that sorts them

A trait can be in exactly one of these:

1. **Available now** -- computable from existing data today, zero new
   sourcing required.
2. **Requires new sourcing** -- real, well-defined trait, but the data
   doesn't exist in this pipeline yet.
3. **Descriptive only** -- interesting for understanding WHY a season
   happened, but can never be a predictive feature (it's not knowable
   before the season, or it IS the outcome being measured).
4. **Predictive-eligible** -- NOT a separate data-availability bucket;
   it's a cross-cutting label. A trait is predictive-eligible if and
   only if it is knowable in full before that season's Week 1. Traits
   from bucket 1 or 2 can be predictive-eligible; bucket 3 traits
   never are, by definition.

**The mechanical rule for bucket 4** (this is the guardrail, stated
precisely so it can't be fudged later): a trait computed for player P,
season N is predictive-eligible for season N ONLY IF every input to
that computation is dated before N's Week 1 kickoff. Prior-season
totals: fine. Current-season ADP: fine (set before Week 1). Anything
touching `weekly_results_ppr` rows where `season == N`: never eligible
for predicting N, only for predicting N+1 onward. No exceptions,
including for traits that "feel" preseason but technically use
in-season data (e.g. "final ADP" snapshots taken after Week 1 games
started would NOT qualify -- verify snapshot timing per source before
trusting this).

---

## Bucket 1: Available now (no new sourcing)

| Trait | Computation | Notes |
|---|---|---|
| Prior-season production, itemized separately (not one row) | `fantasy_points_ppr`, `ppg_ppr`, `position_finish_ppr` from season N-1 | These are conceptually different signals (total output vs. rate vs. positional rank) and should be tested as separate candidate features, not bundled into a single "production" trait |
| Prior-season target share / rush share | **NOT currently available -- verified directly**: `weekly_results_ppr_2006_2025.csv` retains only `fantasy_points_ppr` per player-week; the underlying targets/carries/attempts columns nflverse actually provides are used transiently by `03_download_stats.py` (for the games-played calculation) and then dropped, not stored. This is neither pure Bucket 1 (zero new work) nor Bucket 2 (a genuinely new external source) -- it needs a **pipeline modification** to retain columns nflverse already supplies, plus a team-level attempt/target total to compute a real share. Real, moderate engineering work, not new sourcing. |
| Prior-season snap share / route participation | **Unverified, not claimed available.** May exist in nflverse's separate snap-counts/participation tables (not currently integrated into this pipeline) -- needs an actual check before treating this as buildable, not an assumption. |
| Prior-season LWI, decomposed | `lwi_score` from N-1 AND each underlying component separately (`fantasy_finish_component`, `ppg_component`, `positional_advantage_component`, `consistency_component`, `playoff_performance_component`, `adp_value_component`, plus raw prior `overall_adp_model`) | **Candidate feature requiring empirical validation, not presumed strong.** Prior LWI combines several things that may not repeat the same way -- a player can post a huge LWI once because they were dramatically undervalued, but ADP typically corrects the following year, making a repeat *value* season structurally harder even if the player's underlying quality repeats. Whether prior LWI predicts LESS future value than its components would suggest (because the market catches up) is something to discover empirically, not assume. Including the decomposed components alongside the combined score lets research distinguish "this player is genuinely good" from "this player was a one-time value story" -- testing whether the COMBINED score adds anything the components don't already capture is itself one of the first things to check. |
| Prior-season durability | `games_played` from season N-1 | |
| ADP itself (current season) | `overall_adp_model`, `positional_adp_model` | Already the "market's own preseason prediction" -- a natural baseline to beat |
| ADP change year-over-year | season N's ADP vs. season N-1's ADP for the same player | Requires the player to have both years present |
| Team change | `team` column, season N vs. N-1 | Simple equality check; doesn't yet explain *why* the team changed (trade, free agency, etc. -- that's bucket 2) |
| Position | `position` | Already a stratification variable throughout LWI itself |
| Age proxy: seasons of NFL history in this dataset | count of prior seasons present for this `player_id` | Left-censored for players whose careers started before 2006 -- a real limitation, not a bug, since the dataset only starts there |
| Prior-season consistency | `consistency_component` from season N-1 | |
| Prior-season playoff performance | `playoff_performance_component` from season N-1 | |
| Draft-value trajectory | prior-season `adp_value_component` (did they beat their OWN prior ADP) | |
| Undrafted-breakout flag | prior season's `adp_status == 'undrafted'` and high finish | A very specific, real pattern this project already found -- see `LWI_MODEL_CARD.md`'s known undrafted-breakout stories |

---

## Bucket 2: Requires new sourcing

| Trait | Why it's not available now | Rough source |
|---|---|---|
| Real age / birthdate | Not in current schema | Likely available via `nfl_data_py` roster data, unverified -- needs a real check, not an assumption |
| NFL draft capital (round/pick, different from fantasy ADP) | Not in current schema | Likely available via `nfl_data_py.import_draft_picks()` or similar, unverified |
| Coaching / offensive coordinator changes | No coaching data in pipeline at all | Needs an external source; not something nflverse's weekly stats naturally carries |
| Depth-chart competition entering the season | No roster-depth data in pipeline | Same |
| Injury history / recovery timeline | Not in current schema (some injury data may exist in nflverse, unverified) | Needs a real check |
| Contract-year status | No contract data in pipeline | Needs an external source |
| Offensive line / supporting-cast quality changes | No roster-composition data in pipeline | Needs an external source |
| QB change (for pass-catchers/RBs) | Not directly flagged, though derivable from team-level QB data if sourced | Related to coaching/roster bucket above |

---

## Bucket 3: Descriptive only (never predictive features)

| Trait | Why it's descriptive-only |
|---|---|
| The season's own LWI score/component breakdown | This IS the outcome being explained, not a predictor of itself |
| In-season weekly performance for that same season | Not knowable before Week 1 by definition |
| Playoff performance for that same season | Same -- happens at the end of the season being measured |
| Any injury that occurred during the season being measured | Only knowable in hindsight for that season |
| Narrative "why it happened" analysis (e.g. "opportunity from a teammate's injury") | Valuable for understanding LWI's historical results and for Dataset 2's own write-up, but not a clean, structured predictive feature |

These traits are still worth researching and writing up -- they're
exactly the material that makes Dataset 2 valuable as *research*, per
the original framing ("what predicts LWI" needs "what actually
happened and why" as its foundation) -- they just never graduate into
Dataset 3's feature set.

---

## Rookies need a separate feature path, not exclusion

The ~9.4% of eligible player-seasons with no prior NFL data at all
(see the player-season-level availability numbers above) are
disproportionately likely to include real league-winner stories -- a
rookie breakout is one of the most naturally "undervalued" profiles
ADP can produce. Dropping them from Dataset 2 research entirely would
bias the findings against exactly the pattern most worth finding.
Proposed rookie-specific trait path:

- NFL draft capital (round/pick) -- bucket 2, requires new sourcing
- Age at draft / season start -- bucket 2
- College production (target share, yards, TDs) -- bucket 2, would
  need a college stats source, a real, separate sourcing question
- Expected preseason depth-chart role (starter vs. committee vs. deep
  bench) -- bucket 2
- Fantasy ADP -- bucket 1 even for rookies, since ADP exists
  regardless of NFL history; already available today

---

## How each trait will be tested against LWI

**The core principle: every trait is compared against the eligible
baseline population, never reported as a raw percentage among winners
alone.** "45% of league winners were second-year players" is close to
meaningless on its own -- if second-year players are also 45% of the
whole eligible population, that trait has zero enrichment. The useful
version: "second-year players were 45% of league winners but only 20%
of the eligible population, a 2.25x relative rate" -- that's a real
signal.

**For categorical/binary traits** (team change: yes/no, undrafted-
breakout flag, second-year player: yes/no): compute, within position
strata, all of:
- **Winner rate**: % of this trait-group that received the historical
  "Star" label (`star_by_value_label == 1`, produced by the
  Stars-by-Value pipeline -- Dataset 3's settled target per
  `docs/PREDICTION_SPECIFICATION.md`'s 2026-07 update, superseding the
  top-10%-by-position-LWI definition this line originally referenced)
  the following season
- **Baseline rate**: % of the WHOLE eligible population (regardless of
  trait) that became a league winner
- **Relative rate / lift**: winner rate ÷ baseline rate -- the actual
  enrichment number
- **Sample size**: how many player-seasons carry this trait, reported
  alongside every result, never omitted

A basic significance check (rank-sum or proportions test) accompanies
each -- not for publication rigor, but because "the difference could
easily be noise" is a real, checkable question at this project's
sample sizes (many traits will only apply to a few dozen player-
seasons per era), not something to eyeball.

**For continuous traits** (prior-season PPG, ADP change, etc.):
correlation with the FOLLOWING season's LWI score, computed within
`(season, position)` strata BY DEFAULT -- for the same reason LWI's
own components avoid raw cross-position/cross-era comparison (it
conflates a trait's real effect with positional/era scoring-scale
differences that have nothing to do with the trait itself). This is a
default, not an absolute rule: a question that is SPECIFICALLY about
cross-position effects (e.g. "which position produces league winners
most often?") is a legitimate, different question that intentionally
pools across positions -- stratification is the right default for
isolating a trait's own effect, not a blanket requirement for every
analysis.

**Every test reports its own sample size**, not just an aggregate
across all traits.

---

## Descriptive vs. predictive: two different questions, both worth answering

**Descriptive traits** answer: "what characteristics did historical
league winners have?" (age, position, experience, draft range, prior
production, games played) -- useful for understanding the history,
valuable as research and as Dataset 2's own write-up, but a trait
being descriptively common among winners does NOT by itself mean it's
predictively useful (see the baseline/lift framework above -- a trait
common among winners AND common among everyone else adds nothing).

**Predictive traits** answer: "did knowing this before the season
improve our ability to identify the league winner?" -- this is the
lift/enrichment number itself, not the raw description.

**Explicit rule for graduating a trait from descriptive to
predictive-eligible**: being knowable before Week 1 (the bucket-4 rule
above) is necessary but not sufficient. A trait is excluded from the
later predictive model, even if technically knowable in advance, if
it is:
- **Unstable** -- its measured effect varies substantially across the
  era sub-groups tested (see "Controlling for era and position
  effects" below), suggesting the correlation isn't a real, durable
  pattern
- **Unavailable historically** -- can't be reconstructed for enough of
  the 2006-2025 range to test properly (e.g. a data source that only
  covers recent seasons)
- **Too subjective to reproduce** -- e.g. a qualitative judgment about
  "expected role" that can't be consistently defined the same way
  across every season and researcher

---

## Missingness policy

**"Unknown" must never silently become zero, average, or false.**
Each bucket-1/2 trait needs an explicit, written handling rule before
it's used in any testing.

**Every missing value needs its CAUSE recorded, not just its
absence** -- these are genuinely different situations, and treating
them the same silently discards information:
- **Missing because rookie**: no prior-season data exists at all (see
  the rookie path above) -- expected, structural, not an error.
- **Missing because the trait is genuinely unavailable** for that
  player-season (e.g. a bucket-2 trait not yet sourced for that era)
  -- a real data gap, distinct from a rookie's structural absence.
- **Missing because of injury** (e.g. no weekly rows because the
  player didn't play) -- this is itself informative and should
  usually be its own flagged category, not merged with "no data."
- **Missing because the player was inactive/off a roster** for
  reasons unrelated to injury (healthy scratch, practice squad,
  retired mid-season, etc.) -- distinct again from the injury case.

**Handling rules, once cause is known**:
- A continuous trait with no available value for a player-season:
  excluded from that specific trait's test (not imputed to the
  population mean, which would silently bias the correlation toward
  zero) -- report the exclusion count, broken down by cause where
  possible, alongside the result.
- A binary/categorical trait with no available value: gets its own
  explicit "unknown" category in results, not folded into the "false"
  or "no" group by default.
- Any trait where missingness itself might correlate with the outcome
  (e.g. injury-history missingness concentrated among obscure bench
  players who happen to have low LWI anyway) gets flagged explicitly --
  missingness that isn't random can bias a lift calculation just as
  much as a real effect would.

---

## Controlling for era and position effects

Two real, verified distortions to guard against, both already
encountered building LWI itself:

1. **Position**: LWI's own components are heavily position-relative
   (replacement thresholds, VORP). A trait's real effect must be
   measured WITHIN position, not pooled -- pooling would let a trait
   that happens to correlate with position (e.g. "age" skews younger
   at RB than QB league-wide) masquerade as a real predictive signal
   when it's actually just re-detecting position effects LWI already
   accounts for.
2. **Era**: real scoring environments changed substantially over
   2006-2025 (passing volume increases, PPR adoption, rule changes).
   A raw year-over-year trait value (e.g. "ADP change of +15") may not
   mean the same thing in 2008 vs. 2022 the same way a raw LWI score
   doesn't (see `METRIC_SPECIFICATION.md`'s Component 1 -- this is
   exactly why LOSO/season-relative comparison was necessary there).
   Proposed default: test each trait's correlation/hit-rate BOTH
   pooled across all seasons AND within era sub-groups (e.g. pre-2011
   vs. 2011-2020 vs. 2021+, roughly matching known real rule-change eras -- treated as INITIAL
   DEFAULT eras, not fixed boundaries; revisit if evidence suggests
   different breakpoints without that being a violation of this spec)
   to check whether a trait's apparent effect is stable or era-
   dependent before trusting it.

---

## Avoiding in-season information leakage

Restating the bucket-4 rule as an explicit process step, since this is
the single most important guardrail for Dataset 2 to actually be
useful for Dataset 3 later:

1. Every trait proposed for bucket 4 gets a written "as-of date" --
   the latest possible date its value could be known, matched against
   that season's actual Week 1 kickoff.
2. Any trait whose as-of date falls on or after Week 1 kickoff is
   automatically bucket 3 (descriptive only), no exceptions.
3. ADP snapshot timing specifically needs verification per source
   (FFC, FFToday, etc.) -- if any source's "preseason" snapshot was
   actually captured after Week 1 games began in some year, that
   year's ADP is NOT predictive-eligible even though ADP as a concept
   generally is. Check this before assuming all ADP data qualifies.
4. This mirrors the leave-one-season-out principle already built into
   Component 1 -- a trait must never have access to information that
   wouldn't genuinely have been available at decision time.

---

## Predictor-clustering discovery/holdout boundary -- APPROVED 2026-07

**Methodology status: APPROVED (Evan, 2026-07). Implementation status:
IMPLEMENTED.** Commit `7a64231` makes the canonical predictor table
the sole clustering source and applies the season-only discovery-fit
selector below. The predictor inventory, near-duplicate, cluster, and
overlap-floor artifacts were regenerated under that implementation in
2026-07; their current decision-bearing population is prediction
seasons 2006-2020.

**Discovery-fit population**: prediction seasons 2006-2020, inclusive.
Every decision-bearing predictor-inventory, similarity, near-duplicate,
redundancy, clustering, and representative-selection computation must
be fit exclusively on this population.

**Protected evaluation holdout**: prediction seasons 2021-2025,
inclusive. Must never influence cluster membership, similarity
estimates, or representative selection while this methodology is
locked -- reserved for Phase 1 evaluation.

**2026 application rows**: excluded from clustering calibration
entirely because they are the future application cohort, not
historical discovery observations. They remain available in the
canonical predictor table for producing 2026 predictions.

**Population selection must be outcome-independent, structurally, not
just behaviorally.** Eligibility for the discovery-fit population
depends solely on `prediction_season`. It must never consult
`outcome_join_status` or any outcome, target, label, or
outcome-eligibility field -- even where the resulting row set would
happen to be identical either way. This is a stronger requirement than
"produces the same rows today": the selection mechanism itself must be
incapable of depending on outcome availability, so a future change to
outcome coverage can never silently reshape the discovery-fit
population.

**Full-range diagnostics may exist alongside the discovery-fit
artifacts, but under a separately identified name, and must never
influence Phase 1 development or feature decisions.** A full-range
(2006-2025) descriptive view of predictor structure is allowed to
exist as a diagnostic; it is not a substitute for, and must not be
silently blended with, the discovery-fit clustering used to select
Phase 1 candidates.

**Future production refit (not authorized now)**: after final Phase 1
evaluation and methodology lock, a separately identified production
refit may use data through 2025 to inform actual 2026 predictions.
That refit is a distinct, future decision -- its existence is
anticipated here only so the discovery-fit naming doesn't have to be
revisited later; it is explicitly not authorized or implemented by
this section.

**Distinct from Dataset 3's own tentative temporal split.**
`docs/PREDICTION_SPECIFICATION.md` section 6 proposes a *different*,
still-unresolved train/validate/test boundary (2006-2018 / 2019-2021 /
2022-2024) for the eventual Dataset 3 model itself -- a separate
decision, for a separate purpose (model evaluation, not predictor
redundancy screening), with different cut points and terminal seasons.
Dataset 2's approved 2006-2020 discovery boundary governs Dataset 2
predictor analysis and Phase 1. Dataset 3's tentative split remains a
separate unresolved decision that must be finalized before Dataset 3
model development or evaluation, not before Dataset 2 Phase 1.

---

## Predictive usefulness summary (the actual deliverable)

Dataset 2 ultimately exists to answer one question per trait: **should
this become a predictive feature?** Without a single place recording
that conclusion, someone later has to re-read the entire research
write-up to find out. Every trait tested gets one row here once
research is actually run:

| Trait | Available Preseason | Predictive Lift | Stable Across Eras | Recommended for Dataset 3 |
|---|---|---|---|---|
| *(filled in as research completes -- template only, no rows yet)* | Yes/No | e.g. "2.3x, n=210" | Yes/No/Mixed | Yes/No/Maybe + one-line reason |

This table is the actual bridge to Dataset 3 -- its "Recommended"
column, once populated, is what feature engineering reads directly,
rather than re-deriving conclusions from the underlying research prose.

---

## Open decisions requiring explicit sign-off

0. **Not a Dataset 2 decision, flagged here only to route it
   correctly**: whether Dataset 3's eventual model predicts a
   continuous LWI score, a league-winner probability, or both in
   parallel (a continuous board for full rankings plus a simple
   publishable probability) belongs in
   `docs/PREDICTION_SPECIFICATION.md`'s target definition (currently
   proposes classification only) -- not decided here, since Dataset 2's
   trait research is useful either way and shouldn't be blocked on it.

1. The exact era boundaries for era-effect testing (proposed:
   pre-2011 / 2011-2020 / 2021+) -- explicitly INITIAL DEFAULTS, not
   fixed boundaries, so later evidence can shift them without
   contradicting this document.
2. Whether to pursue the bucket-2 traits requiring genuinely new
   external sourcing (coaching changes, depth charts, contract
   status) now, or defer them and build Dataset 2's first pass purely
   from bucket 1 -- the latter is faster and requires zero new data
   engineering; the former is likely more predictive but is real,
   separate work.
3. The significance threshold/method for categorical trait testing --
   proposed a basic rank-sum/proportions test, not a specific p-value
   cutoff, since this is research prioritization, not a publication
   claim.
