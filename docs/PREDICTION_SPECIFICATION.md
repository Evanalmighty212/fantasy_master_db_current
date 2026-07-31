# Prediction Specification: Future League Winner Probability (Dataset 3)

This document formalizes the prediction task BEFORE any feature
engineering happens -- same principle as `METRIC_SPECIFICATION.md`:
the spec exists first, code matches it, not the other way around.
Every answer below is a PROPOSAL requiring explicit sign-off, exactly
like `METRIC_SPECIFICATION.md`'s open decisions -- not a default
silently locked in.

**Sequencing** (per agreed 3-phase structure):
1. Historical League Winner Index (Dataset 1) -- essentially complete.
2. League Winner Traits (Dataset 2) -- research into what preseason
   patterns actually correlate with receiving the historical
   Stars-by-Value Star label (`star_by_value_label == 1`), informed
   by the target definition THIS document sets. Not yet built.
3. Predictive League Winner Probability (Dataset 3, this document's
   subject) -- a model trained on Dataset 2's findings, evaluated with
   strict time-based validation. **The ground-truth labels this model
   will be trained and evaluated against are now settled and produced
   by the Stars-by-Value pipeline (2026-07, see terminology note
   below) -- the predictive MODEL itself (feature engineering,
   training, time validation) remains not yet built. Stars-by-Value is
   a prerequisite for Dataset 3, not Dataset 3 itself.**

This document defines the target for step 3, which step 2's research
should be organized around answering.

**UPDATE (2026-07): the target definition below has been superseded.**
Sections 1 and 2 originally proposed a season-relative "top N% of
eligible players by position, by LWI score" target. That proposal is
preserved below as decision history, not deleted -- but after a
dedicated methodology investigation
(`research/dataset3/STARS_BY_VALUE_METHODOLOGY.md`, now settled and
implemented as `scripts/11_calculate_stars_by_value.py`'s canonical
output), the REAL, CURRENT target is produced by **Stars-by-Value**
instead: an absolute-impact definition (real production vs. a real,
historically-grounded acquisition cost and position-specific
threshold), not a within-season percentile. This directly resolves
"Open decision #2" below, which had explicitly named "an
absolute-score-based definition" as the alternative under
consideration -- that alternative is what was chosen. See each
section below for exactly what changed and what didn't.

**Terminology, kept distinct throughout this document -- do not
conflate these three things:**
- **Stars-by-Value** -- the canonical, already-BUILT ground-truth
  **label-generation pipeline** (`scripts/11_calculate_stars_by_value.py
  --mode canonical`, backed by `lib/stars_by_value/`). It is a
  PREREQUISITE for Dataset 3, run once against completed historical
  seasons. It is NOT Dataset 3, and does not itself predict anything.
- **`star_by_value_label`** (a.k.a. "Star", the HISTORICAL label) --
  the per-player-season FACT that pipeline produces: 1, 0, or NULL,
  always about a season that has ALREADY happened and already has
  real production data. This is Dataset 3's training/eval ground
  truth -- what actually occurred, known with certainty after the
  fact.
- **The predictive model / "league-winner probability"** (Dataset 3
  itself, NOT YET BUILT) -- will eventually output a PROBABILITY,
  before a season starts, that a player-season WILL LATER receive
  `star_by_value_label == 1` once real results exist. A forecast
  about the future, evaluated against the historical label once that
  future season becomes historical.

Anywhere this document says "league winner" without further
qualification, check which of the last two it means from context --
most uses below have been made explicit, but treat any remaining
ambiguity as a documentation bug to fix, not a real distinction to
guess at.

---

## 1. What is the target?

**Proposed: probability of classification, not raw LWI regression.**

Two real options were on the table:
- **Regression**: predict a player's numeric LWI score directly.
- **Classification/probability**: predict the FUTURE probability that
  a player-season will receive the HISTORICAL "league winner" label
  (Star, `star_by_value_label == 1` -- see section 2 and the
  terminology note above) once that season has actually happened.

**Reasoning for classification**: LWI itself is a weighted composite
of 6 components, each individually normalized (min-max, winsorized
min-max, percentile rank depending on component) -- it's a well-
validated *label*, but predicting its exact numeric value precisely
would mean a model has to reproduce the quirks of that specific
composite formula, not just "is this player going to have a great
season." A probability is also directly what the eventual product
(Phase 3: "Chance to become a league winner," "Bust probability") is
built from -- classification is the native output format for that,
regression would need a second conversion step.

**ORIGINAL proposed target variable (SUPERSEDED 2026-07, preserved as
decision history -- see settled replacement immediately below)**:
```
is_league_winner = 1 if lwi_score >= that season's Nth percentile
                    among eligible players, else 0
```
See open question 2 for what N should be. This is deliberately
**season-relative**, not a fixed absolute LWI score cutoff -- checked
directly against real data: a "top 10%" cutoff ranged from 68.6 to
72.1 in raw LWI-score terms across three sample seasons (2010, 2018,
2023), confirming a fixed absolute threshold would NOT mean the same
thing in different years, given how several LWI components are
normalized relative to that season's own player pool.

**SETTLED target variable (2026-07), replacing the above**:
```
is_league_winner = star_by_value_label
    (1 = Star, 0 = scored but below threshold or failed the
    production gate; rows with star_by_value_label = NULL are
    excluded from the classification population entirely -- see
    below)
```
Source: `data/exports/stars_by_value_player_seasons.csv` /
`scripts/11_calculate_stars_by_value.py --mode canonical`, per the
settled methodology in
`research/dataset3/STARS_BY_VALUE_METHODOLOGY.md`. This is still a
**binary classification target** -- the reasoning above for
classification over raw-score regression is unchanged and still
applies, since `star_by_value_label` is itself already binary (1/0),
never a continuous score to regress against. What changed is HOW the
binary outcome is defined: not a within-season LWI percentile, but an
**absolute-impact** measure -- real production (`P`) minus a real,
historically-grounded expected production (`E_P`) for the acquisition
cost actually paid, compared against a fixed, position-specific
threshold (`config.SBV_STAR_THRESHOLD`), never a moving target that
depends on how strong that particular season's player pool happened
to be.

**Population note carried over from Stars-by-Value's own null-label
policy**: rows where `star_by_value_label` is `NULL` (statuses
`out_of_scope`, `unscoreable_adp_needs_review`,
`unscoreable_drafted_adp_missing`, `unscoreable_ambiguous`,
`unscoreable_expected_production_out_of_range`) represent genuinely
unknowable outcomes, not negatives -- they must be excluded from the
training/eval population entirely, the same way
`WHERE star_by_value_label IS NOT NULL` already governs SBV's own
downstream modeling rule. `label = 0` (a real negative, including
`below_production_gate`) is a true, informative example and must be
kept.

### Approved position/team input-governance revision

**Methodology status: APPROVED by Evan (2026-07). Implementation
status: NOT YET IMPLEMENTED.** Stars-by-Value and every downstream
Dataset 3 outcome or model must use the separately governed,
preseason-frozen `canonical_fantasy_position` defined in
[`MATCHING_ARCHITECTURE.md`](MATCHING_ARCHITECTURE.md). ADP-source
position governs positional ADP ranking and acquisition-cost provenance
unless that ADP-source value is itself shown erroneous. Canonical
fantasy position governs positional finish, replacement, production,
gates and thresholds, LWI position-relative components,
Stars-by-Value/bust production cells, and Dataset 2 position-normalized
traits. When ADP-source and canonical position differ, the discrepancy
must be explicitly adjudicated and documented; a mismatched positional
ADP rank and production cohort must never be used silently. Raw ADP
position, raw results position, official/team-listed position, and
actual usage roles remain separate evidence. A position disagreement
must never redirect an ADP row to a different player identity.

Raw provider team values likewise remain unchanged provenance. A
separately named, season-accurate canonical team governs identity
corroboration, team logic, joins, and player-facing output; historical
franchise aliases, real transactions, and stale provider metadata must
remain distinguishable.

When corrected canonical position or team inputs change a previously
published Stars-by-Value label or downstream outcome, the regenerated
label receives an explicit new historical-label/reproducibility
revision. This does not change the Stars-by-Value formula or its
thresholds. It prevents outputs built from different input facts from
appearing interchangeable merely because the formula is unchanged.

---

## 2. What counts as a "league winner"? (the classification threshold)

**ORIGINAL proposal (SUPERSEDED 2026-07, preserved as decision
history): top 10% of eligible players, by position, that season.**

Why by-position rather than one pool: LWI's own components are
already position-relative in several places (replacement-level
thresholds, positional VORP) -- a league-winner definition that pools
all positions together would let position-scarcity effects (already
captured inside LWI) double up with prediction-target effects. A
by-position top-10% keeps the definitions cleanly separated: LWI
already answers "how good was this season, accounting for position,"
the prediction target should just ask "was this among the best at
their position that year."

**SETTLED (2026-07): position-specific ABSOLUTE thresholds
(`config.SBV_STAR_THRESHOLD`: QB 176.5, RB 188, WR 171, TE 134),
gated by a position-specific production floor
(`config.SBV_PRODUCTION_GATE_FLOOR`), computed by the Stars-by-Value
pipeline.** The by-position REASONING above is preserved and still
holds -- positions are kept separate for exactly the same
scarcity-effect reason -- but the MECHANISM changed from a percentile
within that season's pool to a fixed, historically-grounded absolute
score. A player-season IS a Star (a HISTORICAL fact, computed once
that season's real results exist) if it clears the production gate
AND `P - lambda * E_P >= SBV_STAR_THRESHOLD[position]`; see
`research/dataset3/STARS_BY_VALUE_METHODOLOGY.md` for the full formula
and `data/exports/stars_by_value_player_seasons_SCHEMA.md` for the
output schema. **This is the definition Dataset 3's eventual model
will be trained to PREDICT in advance, for a season that hasn't
happened yet -- Stars-by-Value itself never predicts anything; it only
computes this fact after the season is over.**

**Alternative considered and rejected for v1**: multiple threshold
tiers (top 5% / top 25% / top 50%) as an ordinal target, or a
continuous percentile-rank regression target. Both are real, arguably
richer options -- deferred to a v2 refinement once a v1 binary
classifier's calibration is understood, rather than adding that
complexity before there's evidence it's needed.

---

## 3. What is the prediction horizon?

**Proposed: preseason-only for v1.** Predict before the season starts,
using only information available at that time (prior-season stats,
ADP, age, situational changes, etc.) -- no in-season updating.

**Reasoning**: this matches the primary stated use case ("help me
draft") most directly, and avoids a substantial added complexity
class (rolling retraining, avoiding in-season data leaking backward
into what should be a "preseason" prediction, defining what "week N
prediction" even means). Explicitly deferring in-season updating to a
later phase, not rejecting it -- it's a real, valuable v2 feature.

---

## 4. What is the unit of analysis?

**Proposed: player-season**, matching exactly how LWI itself (the
training label) is already defined. No ambiguity here -- this should
just inherit LWI's existing unit.

---

## 5. What is the evaluation metric?

**Proposed: Precision@25 as the primary headline metric, calibration
and ROC-AUC as supporting diagnostics.**

Reasoning: a fantasy manager drafting from this model's output cares
most directly about "of the players you told me were likely to become
Stars, how many actually did (received `star_by_value_label == 1`
once the season played out)" -- that's precision at a realistic
draft-relevant cutoff (a typical league roster is ~15-16 players
across ~10-14 teams; top-25 predicted candidates is a reasonable
"who should I actually target" list size). ROC-AUC and calibration
(does a predicted 70% probability actually correspond to a ~70%
real hit rate) matter for trusting the model's outputs generally, but
Precision@25 is the metric that most directly answers "would this
have actually helped someone draft well," which is the project's
stated real goal.

**Also tracked, not primary**: Top-25 recall (of the season's ACTUAL
Stars-by-Value Stars -- `star_by_value_label == 1`, per section 2's
settled definition -- how many did the model's top-25 list catch) --
precision and recall trade off against each other, and both numbers
should be reported together, not just precision alone.

---

## 6. Validation protocol

**Proposed: strict time-based split, not random cross-validation.**

```
Train: 2006-2018
Validate (hyperparameter tuning): 2019-2021
Test (final, touched once): 2022-2024
```

A random train/test split would leak future information into
training (e.g., a 2015 season's features could be validated against a
2010 season's outcome, which is not how this model would ever
actually be used). Time-based splitting is the only protocol that
honestly mirrors real deployment: predicting a season that hasn't
happened yet, using only what was knowable before it started.

**Also required before declaring this stable**: the 2022-2024 test
set should be touched only once, at the very end -- if results are
poor, retreat to the 2019-2021 validation set to iterate, don't repeatedly
re-test against 2022-2024 (that turns it into a de facto validation
set through repeated peeking, undermining what it's for).

---

## 7. Deployment assumptions

**Proposed, deferred pending Phase 2/3 build-out**: model output should
be a per-player-season probability plus a small number of interpretable
sub-scores (e.g., "upside probability," "bust risk," matching the
Phase 3 product vision already discussed), NOT a black-box single
number -- this preserves the same interpretability standard already
established for LWI itself (transparency columns, Model Card, "why is
X ranked above Y" answerability). Full design deferred until Dataset 2
(League Winner Traits) research reveals which features are actually
predictive -- premature to lock in a deployment format before knowing
what the model can actually explain.

---

## What happens next, per this spec

Dataset 2 (League Winner Traits) research should be organized around
THIS document's target definition -- specifically, exploring which
preseason-available signals correlate with a player-season becoming a
Stars-by-Value Star (`star_by_value_label == 1`, section 2's settled
definition). That keeps the traits research focused on what actually
matters for the eventual prediction task, rather than open-ended
pattern-hunting that might not connect to a well-defined target.

---

## Open decisions requiring explicit sign-off before Dataset 2 begins

1. Classification (proposed) vs. regression vs. ordinal/multi-tier
   target -- see section 1.
2. ~~Top-10%-by-position threshold (proposed) vs. a different
   percentile or an absolute-score-based definition -- see section
   2.~~ **RESOLVED 2026-07**: absolute-score-based, via the settled
   Stars-by-Value methodology -- see section 2.
3. Preseason-only horizon (proposed) vs. building in-season updating
   into v1 -- see section 3.
4. Precision@25 as the primary metric (proposed) vs. a different
   headline metric (ROC-AUC, F1, calibration-first) -- see section 5.
5. The train/validate/test season boundaries themselves (2006-2018 /
   2019-2021 / 2022-2024, proposed) -- reasonable defaults, not derived
   from anything requiring this exact split. **Not resolved or
   superseded by** the separate, APPROVED Dataset 2 predictor-clustering
   discovery/holdout boundary (2006-2020 discovery-fit / 2021-2025
   protected holdout -- see `docs/LEAGUE_WINNER_TRAITS_SPEC.md`'s
   "Predictor-clustering discovery/holdout boundary" section, 2026-07).
   That decision governs Dataset 2 predictor analysis and Phase 1.
   Dataset 3 uses different cut points and terminal seasons for a
   separate purpose; its tentative split remains unresolved and must
   be finalized before Dataset 3 model development or evaluation, not
   before Dataset 2 Phase 1.
