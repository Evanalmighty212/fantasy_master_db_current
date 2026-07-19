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
   patterns actually correlate with becoming a league winner, informed
   by the target definition THIS document sets. Not yet built.
3. Predictive League Winner Probability (Dataset 3, this document's
   subject) -- a model trained on Dataset 2's findings, evaluated with
   strict time-based validation. Not yet built.

This document defines the target for step 3, which step 2's research
should be organized around answering.

---

## 1. What is the target?

**Proposed: probability of classification, not raw LWI regression.**

Two real options were on the table:
- **Regression**: predict a player's numeric LWI score directly.
- **Classification/probability**: predict the probability a player
  becomes a "league winner" (however defined below).

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

**Proposed target variable**:
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

---

## 2. What counts as a "league winner"? (the classification threshold)

**Proposed: top 10% of eligible players, by position, that season.**

Why by-position rather than one pool: LWI's own components are
already position-relative in several places (replacement-level
thresholds, positional VORP) -- a league-winner definition that pools
all positions together would let position-scarcity effects (already
captured inside LWI) double up with prediction-target effects. A
by-position top-10% keeps the definitions cleanly separated: LWI
already answers "how good was this season, accounting for position,"
the prediction target should just ask "was this among the best at
their position that year."

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
most directly about "of the players you told me were likely league
winners, how many actually were" -- that's precision at a realistic
draft-relevant cutoff (a typical league roster is ~15-16 players
across ~10-14 teams; top-25 predicted candidates is a reasonable
"who should I actually target" list size). ROC-AUC and calibration
(does a predicted 70% probability actually correspond to a ~70%
real hit rate) matter for trusting the model's outputs generally, but
Precision@25 is the metric that most directly answers "would this
have actually helped someone draft well," which is the project's
stated real goal.

**Also tracked, not primary**: Top-25 recall (of the season's ACTUAL
top-10%-by-position players, how many did the model's top-25 list
catch) -- precision and recall trade off against each other, and both
numbers should be reported together, not just precision alone.

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
preseason-available signals correlate with a player-season crossing
the top-10%-by-position-that-season threshold defined in section 2.
That keeps the traits research focused on what actually matters for
the eventual prediction task, rather than open-ended pattern-hunting
that might not connect to a well-defined target.

---

## Open decisions requiring explicit sign-off before Dataset 2 begins

1. Classification (proposed) vs. regression vs. ordinal/multi-tier
   target -- see section 1.
2. Top-10%-by-position threshold (proposed) vs. a different percentile
   or an absolute-score-based definition -- see section 2.
3. Preseason-only horizon (proposed) vs. building in-season updating
   into v1 -- see section 3.
4. Precision@25 as the primary metric (proposed) vs. a different
   headline metric (ROC-AUC, F1, calibration-first) -- see section 5.
5. The train/validate/test season boundaries themselves (2006-2018 /
   2019-2021 / 2022-2024, proposed) -- reasonable defaults, not derived
   from anything requiring this exact split.
