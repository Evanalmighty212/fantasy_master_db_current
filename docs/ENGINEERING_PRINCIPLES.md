# Engineering Principles

This document explains *why* this project works the way it does, at
the level of the whole project, not any one dataset. It's the
reference `CLAUDE.md` points to for reasoning instead of restating it,
and the reference future dataset specs (`LEAGUE_WINNER_TRAITS_SPEC.md`,
`PREDICTION_SPECIFICATION.md`, and whatever Dataset 4+ eventually
looks like) should inherit from rather than re-deriving independently.

It does not duplicate `README.md` (what the project is and how to run
it) or the dataset-specific specs (`METRIC_SPECIFICATION.md`,
`MATCHING_ARCHITECTURE.md` -- the exact current formulas and why they
are what they are). Those stay the authoritative source for their own
domains; this document is about how decisions get made and code gets
built across all of them.

---

## The overarching goal

The goal of this project is not simply to produce rankings or models,
but to produce research that others -- including future versions of
this project -- can inspect, reproduce, challenge, and improve. Good
methodology should survive changes in tooling, programming languages,
and AI assistants. The code exists to faithfully implement documented
methodology, not define it.

Everything below is a specific consequence of that one idea.

## Research-first development

This is a research project that happens to be implemented in code, not
a software project that happens to touch football data. Traditional
software projects often optimize for maintainability, usability, and
feature delivery, whereas this project ultimately optimizes for
trustworthy research conclusions -- software quality (clean code, good
tests, maintainability) still matters here, but as a means to that
end, not the end itself; the code is just the mechanism that produces
the conclusions.

Concretely: `docs/METRIC_SPECIFICATION.md`, `MATCHING_ARCHITECTURE.md`,
and `VERSION_1_SCOPE.md` all say some version of "if code and spec
disagree, the code has a bug." That's the research-first posture made
literal -- the documented methodology is the thing that's actually
correct or incorrect; the code is just an implementation of it, and
implementations can have bugs the spec doesn't.

## Honest uncertainty

When evidence is incomplete, say so plainly rather than rounding up to
confidence:

- Distinguish known facts from hypotheses.
- Distinguish measured results from intuition.
- Distinguish confirmed findings from proposals still awaiting
  sign-off.
- Prefer stating "unknown" or "unresolved" over a confident-sounding
  guess.

This project already draws this line in several places, not as an
abstract ideal but as working practice:

- The undrafted-player mechanism keeps `verification_status`
  (`verified` vs. `unresolved`) strictly separate from `adp_status`
  (`drafted` vs. `undrafted`), specifically because "we haven't
  checked yet" and "confirmed undrafted" are different claims --
  conflating them would let an absence of evidence quietly pass as a
  finding.
- The replacement-level rank thresholds (QB12/RB34/WR42/TE12) are
  documented as "a conceptual choice, not an empirical finding" --
  real scoring-by-rank curves show no natural cliff at any threshold,
  so the model card is explicit that sensitivity testing proves
  *robustness to reasonable alternatives*, not that any one threshold
  is uniquely, empirically correct. Those are different claims, and
  the documentation doesn't blur them.
- The undrafted-proxy constant (194.5) is labeled "a reasonable,
  documented judgment call, not an empirically derived value" --
  confidence is stated at the level it's actually earned, not
  inflated to match the precision of the rest of the formula.
- `PREDICTION_SPECIFICATION.md` and `LEAGUE_WINNER_TRAITS_SPEC.md`
  both mark every open decision as "a PROPOSAL requiring explicit
  sign-off... not a default silently locked in" -- a proposal and a
  confirmed decision are different claims, kept visibly different
  until sign-off actually happens.

Where something genuinely isn't resolved -- the 7 unverified
undrafted-breakout candidates, the playoff bye-week edge case -- this
project says so directly rather than picking a plausible default and
moving on.

## Evidence over expectation

Methodology and conclusions should follow the evidence, not preserve
expected or popular-looking rankings. If a result conflicts with
intuition or a prior design choice, surface and investigate the
conflict -- don't force the output to look familiar, and don't
preserve an approach simply because it produces expected rankings or
because changing it is inconvenient.

This project has a real, documented instance of getting this wrong at
first and then correcting course: an earlier version's Component 4
outlier sensitivity (a single wild outlier in one position could shift
an unrelated player's score in a different position by 60+ points) was
initially treated as an accepted, documented limitation rather than
fixed. The model card records this directly, struck through: "~~Cross-
position min-max sensitivity~~ -- FOUND AND FIXED, not an open
limitation... This was initially (incorrectly) treated as an accepted,
documented limitation rather than fixed -- corrected after review."
That correction is the principle in action: evidence of a real problem
eventually overrode the temptation to just write it down and move on.

The Component 3/4 duplication fix is the same pattern from the other
direction: once testing proved two components were mathematically
identical (Spearman ~0.9999999), the response was to redesign
Component 4 and accept a real, measured cost (unique variance dropped
from 25.0% to 15.5% after the later winsorization fix) -- not to keep
the simpler formula because its rankings still looked reasonable.

**The failure mode this guards against**: treating "the output still
looks plausible" as evidence that a method is correct. Plausible and
correct are different claims -- the known-winner/false-positive
control groups, ablation studies, and sensitivity sweeps in this
project's validation process exist specifically to check the second
one, not just the first.

This also means negative findings are worth documenting, not
discarding. If Dataset 2's trait research tests a plausible signal and
finds no real correlation, that null result is itself valuable
research output -- it rules out a hypothesis for good, and prevents
future work (or a future Claude Code session) from re-testing the same
dead end from scratch. `LEAGUE_WINNER_TRAITS_SPEC.md`'s "Historical
Findings" bucket already makes room for exactly this kind of result;
treat a clean negative the same as a positive finding worth recording,
not as a failed experiment to quietly drop.

## Correctness over convenience

When a shortcut would make an output easier to produce but harder to
trust, this project has consistently taken the harder, more correct
path:

- `MATCHING_ARCHITECTURE.md`'s core rule -- "when the algorithm isn't
  confident, don't guess, flag it and exclude it" -- explicitly trades
  completeness for correctness. A `no_adp_match` row is honest; a
  silently wrong match sitting in the master dataset labeled
  `matched_clean` would quietly corrupt every downstream analysis
  built on it.
- The join-collision policy (Chris Henry/Chris Perry, 2007: two real
  players both plausibly matched to the same nflverse ID) excludes
  *both* sides rather than keeping the higher-confidence one. An
  earlier version kept the first occurrence; that was found to be
  wrong roughly half the time and changed.
- Component 1's ADP-underperformance cap exists because the more
  "convenient" pure-EVA formula could score a real underperformer
  (Arian Foster, 2012) positively for beating a bad historical
  baseline, even though he was worse than his own actual draft slot.
  The extra complexity of the cap was accepted specifically because
  the simpler version produced a wrong-feeling answer on a real case.

## Reproducibility and data provenance

Every number this project produces should be traceable back to a
specific input and a specific, versioned formula -- not to "whatever
the script happened to do that day."

- `LWI_GLOBAL_MAX_OVERALL_ADP` and `LWI_GLOBAL_MAX_POSITIONAL_ADP` are
  **fixed constants**, computed once from the real 2006-2025 dataset,
  not recalculated automatically on every run. If they were, every
  previously-scored undrafted player's modeled ADP would silently
  shift whenever new ADP data was added, breaking any comparison
  between output versions. Revisit them deliberately, never
  automatically.
- `lwi_config_fingerprint` (a hash of every `LWI_*` config value used)
  is written into the output specifically so a later reader can tell
  whether two runs are actually comparable.
- The undrafted-player mechanism wasn't just designed, it was
  *verified*: James Robinson's 2020 season was temporarily added as a
  real test case, the full pipeline was rerun, the result was checked
  for a credible (not just plausible-looking) score, and then the test
  entry was reverted and production was confirmed to return to
  byte-identical output. Design intent alone was not treated as
  sufficient evidence that the mechanism worked.

## Specification-first methodology

Every dataset in this project has been (or is being) specced before
it's built, not documented after the fact to describe whatever got
built. `PREDICTION_SPECIFICATION.md` says this directly: it exists
"before any feature engineering happens," and every answer in it is
"a PROPOSAL requiring explicit sign-off... not a default silently
locked in." `LEAGUE_WINNER_TRAITS_SPEC.md` states the identical
principle for Dataset 2.

The reason this matters more here than in typical software work: in a
research context, it's easy to unconsciously let the target definition
drift toward whatever the data makes convenient to predict. Fixing the
target and the methodology in writing *before* looking at results is
what keeps later findings honest.

Documentation is part of the implementation, not an afterthought -- it
is held to the same correctness standard as code, not treated as
optional polish. This project has already caught and fixed a real
documentation bug the same way it fixes a code bug: an earlier version
of `LWI_MODEL_CARD.md` cited stale statistics from before the
winsorization fix (a known-winner median that should have read 16, not
the old ~24; a Component3-4 correlation that should have read 0.942,
not 0.878), caught via a full release-verification pass measured
directly against production output, and recorded in `CHANGELOG.md`'s
"Fixed" section alongside the code fixes it accompanied -- not
dismissed as a lesser, cosmetic issue.

## Fail-loud validation, not silent fallback

`config.py`'s `validate_lwi_config()` is called at the start of
`05_calculate_metrics.py`, not optional, not a warning: it raises
immediately on invalid configuration rather than letting a bad value
quietly produce a plausible-looking wrong score. The same posture
shows up in the LWI component-availability policy: a row missing any
of the 6 components gets `lwi_score = null` and an explicit
`incomplete_N_of_6` flag -- it is never silently computed from 5 of 6
components and shown as if it were a normal, complete score.

The underlying belief: a loud failure costs a few minutes of
investigation; a silent wrong answer can sit in a "verified" dataset
indefinitely and corrupt everything built on top of it before anyone
notices.

## Sensitivity testing before calling anything "confirmed"

`config.py` marks certain values `CONFIRMED (was: proposed default)`
-- and that label is earned, not assumed. The replacement-level rank
thresholds (QB12/RB34/WR42/TE12) were sensitivity-tested against real
2006-2024 data before being confirmed: 0.9996 rank correlation between
the most divergent candidate configurations, top-25 set overlap 23/25,
top-100 overlap 97/100, per-season #1 changing in only 2 of 18 seasons
(both already razor-margin races). That's a claim about *robustness to
reasonable alternatives*, not a claim that the chosen threshold is
uniquely, empirically correct -- the model card and metric spec are
both explicit that no natural cliff exists in the data to justify one
threshold over another.

The same discipline applies to Component 4's normalization: plain
min-max, percentile rank, 2.5/97.5 winsorization, and 5/95
winsorization were all tested head-to-head on the same real data
before 5/95 was confirmed, with the actual tradeoffs (dropped unique
variance from 25.0% to 15.5% as the real, accepted cost of fixing a
60+-point cross-position contamination bug) recorded, not glossed
over.

**The standard going forward**: a config value only earns "confirmed"
status after being tested against real data and compared against at
least one real alternative -- not after simply seeming reasonable.

## Generated data versus hand-maintained data

`data/` has exactly one exception to "everything here is
pipeline-regenerated and gitignored": `data/manual/`. That folder
(`player_name_overrides.csv`, `position_overrides.csv`,
`adp_status_verification.csv`) is git-tracked specifically because it
represents accumulated human research and judgment that no script can
regenerate -- losing it would mean losing real work, not just losing a
cache.

The dividing line is not "is this a CSV file," it's "did a human decide
this, or did a formula compute it." Anything a script can reproduce
from scratch should not be committed (it just adds noise and drift
risk to the repo); anything a human confirmed through research must be
committed (or it's not actually persisted).

## Configuration centralization

Every tunable number that affects an LWI output lives in `config.py`,
never inline in a script -- weights, thresholds, caps, playoff-week
definitions, the undrafted-proxy constants. The reason isn't just
tidiness: `config.py`'s own docstring states the actual justification --
centralizing every tunable value also centralizes the *opportunity* to
catch a bad one via `validate_lwi_config()`. A constant buried inline
in a script has no single place to validate it against reasonable
bounds; a constant in `config.py` does.

## Regression tests anchored to real bugs

This project has a stated rule against writing speculative tests "in
case something goes wrong." Every meaningful test here exists because
something *did* go wrong first, or because a documented invariant
needed to be proven correct before it was ever actually load-bearing:

- `TestIndexAlignmentRegression` exists because an internal
  `.merge()` silently misaligned 1,907 of 2,643 real rows (72%) before
  it was caught -- the test deliberately builds a non-contiguous index
  specifically to catch that exact class of bug again.
- `TestNoDuplicateComponentFormulas` exists because Components 3 and 4
  were once mathematically identical (Spearman ~0.9999999) without
  anyone noticing until it was directly tested for.
- `TestComponentAvailabilityPolicy` exists to prove a documented spec
  policy (`METRIC_SPECIFICATION.md`'s component-availability rule)
  holds "before it's ever actually needed," not in response to an
  incident.
- The test suite grew from 35 (v1.0) to 53 (v2.1) tests, and the
  changelog is explicit that "nearly all of them" trace to a specific
  real bug or documented policy, not speculative coverage.

The practical implication for future work: if you find a real bug,
write a regression test that would have caught it, in the same commit
as the fix. If you write a new documented invariant or acceptance
criterion, test that it actually holds. Don't add tests for inputs
that can't occur just to raise a coverage number.

## Preservation of decision history

`CHANGELOG.md` has a "Rejected" section, not just "Added/Changed/Fixed"
-- explicitly recording ideas that were considered, tried, and
abandoned (the 50/50 then 75/25 positional/overall blend for
Component 1; MAD and standard deviation as Component 4's denominator;
a three-state `adp_type` instead of the binary
status/verification-status split). `config.py`'s own inline comments
preserve the same kind of history for constants that were tuned rather
than guessed.

This is deliberate, not incidental: without a record of what was
already tried and rejected, and *why*, a future session (human or
Claude) is at real risk of quietly re-proposing and re-implementing an
already-abandoned approach, burning real effort to rediscover a
conclusion that already exists. Rejected-and-recorded is cheap
insurance against that. Never delete this history to make the current
implementation look simpler or more inevitable than the process that
produced it actually was.

## Explicit tradeoff analysis

Nearly every nontrivial choice in this codebase is recorded with its
actual competing alternatives and the specific reason one won, not
just the winner in isolation. IQR vs. standard deviation vs. MAD for
Component 4's standardization is the clearest example: all three were
tested head-to-head on real data, standard deviation was clearly
weakest, and IQR was chosen over the closer alternative (MAD)
specifically because false-positive separation was judged more
important than a few extra ranking spots of recall -- an explicit,
named priority judgment, not an unstated default.

The pattern to follow: when a consequential choice has more than one
reasonable answer, name the alternatives that were considered, what
was measured to compare them, and the specific reason the chosen one
won -- even (especially) when the answer is close.

## Small, reviewable changes

Nothing in this repository should land as one large, hard-to-audit
change. The natural unit of work here is one logical change -- one bug
fix, one new component, one spec update -- each independently
reviewable and each with its own commit message explaining the *why*.
This mirrors how the LWI formula itself evolved: each version bump
(1.0 -> 2.0 -> 2.1) is traceable to specific, individually-justified
changes in the changelog, not one undifferentiated rewrite.

## How these principles carry into Datasets 2 and 3

Dataset 1 (LWI) is the proof that this way of working produces a
trustworthy result -- 53 regression tests, a documented falsification
history, sensitivity-tested config values, and a model card that
states its own limitations rather than hiding them. Datasets 2 and 3
inherit every principle above unchanged; nothing about moving from a
descriptive metric to predictive modeling relaxes them. Concretely:

- **Dataset 2 (League Winner Traits)**: `LEAGUE_WINNER_TRAITS_SPEC.md`
  already separates "Predictive Traits" from "Historical Findings" so
  a purely descriptive, non-predictive finding never gets silently
  reused as a modeling feature without clearing the leakage rule first
  -- this is the specification-first and correctness-over-convenience
  principles applied to a new kind of output.
- **Dataset 3 (Predictive League Winner Probability)**: strict
  time-based validation is non-negotiable for the same reason
  leave-one-season-out matters for Component 1 -- a model's evaluation
  must never be allowed to peek at data it wouldn't have had access to
  in real time. Every modeling choice (target definition, features,
  evaluation metric) should go through the same sensitivity-testing
  and explicit-tradeoff standard used for Dataset 1's config values
  before anything gets called "confirmed."
- Any real bug found while building either dataset gets a regression
  test in the same commit as the fix, following the exact pattern
  `tests/test_calculate_metrics.py` and `tests/test_undrafted_proxy.py`
  already established.
- Any rejected approach gets recorded (in that dataset's own changelog
  entry, or a new one if `CHANGELOG.md` is split by dataset later) --
  don't let Dataset 2/3 lose the "Rejected" discipline just because
  it's a new file.
- If evidence from Dataset 2's research contradicts an intuition this
  project has carried since Dataset 1 (e.g. an assumed predictive
  signal turns out not to hold up), that's exactly the "evidence over
  expectation" principle applying to new territory -- surface the
  conflict and let it change the plan, don't quietly bury a
  disappointing result.
