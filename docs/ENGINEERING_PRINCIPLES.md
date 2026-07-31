# Engineering Principles

This document explains *why* this project works the way it does, at
the level of the whole project, not any one dataset. It's the
reference [`CLAUDE.md`](../CLAUDE.md) points to for reasoning instead
of restating it, and the reference future dataset specs
([`LEAGUE_WINNER_TRAITS_SPEC.md`](LEAGUE_WINNER_TRAITS_SPEC.md),
[`PREDICTION_SPECIFICATION.md`](PREDICTION_SPECIFICATION.md), and
whatever Dataset 4+ eventually looks like) should inherit from rather
than re-deriving independently.

It does not duplicate [`README.md`](../README.md) (what the project is
and how to run it) or the dataset-specific specs
([`METRIC_SPECIFICATION.md`](METRIC_SPECIFICATION.md),
[`MATCHING_ARCHITECTURE.md`](MATCHING_ARCHITECTURE.md) -- the exact
current formulas and why they are what they are) or
[`CHANGELOG.md`](../CHANGELOG.md) /
[`LWI_MODEL_CARD.md`](LWI_MODEL_CARD.md) (the full evidence and
numbers behind past decisions). Those stay the authoritative source
for their own domains and are linked below rather than reproduced;
this document is about how decisions get made and code gets built
across all of them.

---

## The overarching goal

The goal of this project is not simply to produce rankings or models,
but to produce research that others -- including future versions of
this project -- can inspect, reproduce, challenge, and improve. The
code exists to faithfully implement documented methodology, not define
it. Everything below is a specific consequence of that one idea.

## Research-first development

This is a research project that happens to be implemented in code, not
a software project that happens to touch football data. Software
quality (clean code, tests, maintainability) still matters, but as a
means to trustworthy research conclusions, not the end itself.

Concretely: `METRIC_SPECIFICATION.md`, `MATCHING_ARCHITECTURE.md`, and
[`VERSION_1_SCOPE.md`](VERSION_1_SCOPE.md) all say some version of "if
code and spec disagree, the code has a bug." The documented methodology
is the thing that's actually correct or incorrect; the code is just an
implementation of it, and implementations can have bugs the spec
doesn't.

## Honest uncertainty

When evidence is incomplete, say so plainly rather than rounding up to
confidence: distinguish known facts from hypotheses, measured results
from intuition, and confirmed findings from proposals still awaiting
sign-off.

- The undrafted-player mechanism keeps `verification_status`
  (`verified`/`unresolved`) strictly separate from `adp_status`
  (`drafted`/`undrafted`) -- "we haven't checked yet" and "confirmed
  undrafted" are different claims, and conflating them would let an
  absence of evidence quietly pass as a finding.
- [`config.py`](../config.py) documents methodological values with
  their actual status; the SBV block explicitly distinguishes
  `[SETTLED METHODOLOGY]` from `[IMPLEMENTATION METADATA]`, while
  provisional values are labeled as such, rather than letting every
  number read as equally authoritative. `PREDICTION_SPECIFICATION.md`
  and `LEAGUE_WINNER_TRAITS_SPEC.md`
  apply the identical discipline at the document level -- every open
  decision is marked "a PROPOSAL requiring explicit sign-off," not a
  default silently locked in.

Where something genuinely isn't resolved, say so directly rather than
picking a plausible default and moving on.

## Evidence over expectation

Methodology and conclusions should follow the evidence, not preserve
expected or popular-looking rankings. If a result conflicts with
intuition or a prior design choice, surface and investigate the
conflict -- don't force the output to look familiar, and don't keep an
approach simply because changing it is inconvenient.

`LWI_MODEL_CARD.md` records a real instance of getting this wrong at
first (a Component 4 outlier-sensitivity bug initially logged as an
accepted limitation) and correcting course once it was recognized as a
real, fixable problem, not a cosmetic one -- see the model card for the
full history. **The failure mode this guards against**: treating "the
output still looks plausible" as evidence that a method is correct.
Plausible and correct are different claims, which is exactly why this
project's validation process (control groups, ablations, sensitivity
sweeps) checks the second one, not just the first.

This also means negative findings are worth documenting, not
discarding -- `LEAGUE_WINNER_TRAITS_SPEC.md`'s "Historical Findings"
bucket exists specifically so a clean negative result from Dataset 2's
trait research is recorded, not quietly dropped. Dataset 2 already
preserves negative structural findings -- for example, proposed
predictor distinctions that collapsed into outcome-free redundancy
analysis, documented in
[`research/dataset2/`](../research/dataset2/). No predictor-outcome
trait finding has yet been produced.

## Correctness over convenience

When a shortcut would make an output easier to produce but harder to
trust, this project takes the harder, more correct path:

- `MATCHING_ARCHITECTURE.md`'s core rule -- when the algorithm isn't
  confident, flag and exclude, never guess -- trades completeness for
  correctness on purpose. A `no_adp_match` row is honest; a silently
  wrong match labeled `matched_clean` would corrupt every downstream
  analysis built on it.
- Stars-by-Value's build-completeness contract applies the same rule
  to an entire pipeline run: canonical output generation refuses to
  run at all if any row would need to be deferred, rather than
  quietly shipping an incomplete-but-plausible-looking file (see
  [`scripts/11_calculate_stars_by_value.py`](../scripts/11_calculate_stars_by_value.py)'s
  `check_build_completeness()`).

## Reproducibility and data provenance

Every number this project produces should be traceable back to a
specific input and a specific, versioned formula, not to "whatever the
script happened to do that day."

- `LWI_GLOBAL_MAX_OVERALL_ADP` and related proxy constants are
  **fixed**, computed once and revisited only deliberately -- if they
  recalculated automatically, every previously-scored undrafted
  player's modeled ADP would silently shift whenever new data arrived,
  breaking comparability across output versions. `lwi_config_fingerprint`
  exists so a later reader can tell whether two runs actually used the
  same config.
- The underlying nflverse data source is pinned by release **asset
  ID** plus a recorded sha256
  ([`scripts/nflverse_source_manifest.json`](../scripts/nflverse_source_manifest.json)),
  not a tag+filename URL, because the latter can silently start
  serving different bytes if the upstream source republishes a file
  under the same name. See `CHANGELOG.md`'s nflverse migration entry
  for the full verification history, including the fresh-clone test
  this mechanism was built to pass.

See `CHANGELOG.md`'s "2025 ADP provenance fix" as a worked example of
tracing, auditing, and disclosing a correction that changes downstream
outputs.

## Specification-first methodology

Every dataset in this project has been (or is being) specced before
it's built. `PREDICTION_SPECIFICATION.md` exists "before any feature
engineering happens," and `LEAGUE_WINNER_TRAITS_SPEC.md` states the
identical principle for Dataset 2 -- proposal documents in
`research/dataset2/` are written and reviewed before the analysis
script that implements them lands, not after.

In a research context, it's easy to unconsciously let the target
definition drift toward whatever the data makes convenient to predict.
Fixing the target and methodology in writing *before* looking at
results is what keeps later findings honest. Documentation is held to
the same correctness standard as code, not treated as optional polish
-- `CHANGELOG.md`'s "Fixed" section records at least one real
documentation-accuracy bug (stale stats in the model card) caught and
corrected the same way a code bug would be.

## Fail-loud validation, not silent fallback

`config.py`'s `validate_lwi_config()` and `validate_sbv_config()` run
at the start of their respective pipeline stages, not optional, not a
warning -- they raise immediately on invalid configuration rather than
letting a bad value quietly produce a plausible-looking wrong score.
The same posture shows up in the LWI component-availability policy: a
row missing any component gets `lwi_score = null` and an explicit
`incomplete_N_of_6` flag, never a score silently computed from
whatever components happened to be available.

The underlying belief: a loud failure costs a few minutes of
investigation; a silent wrong answer can sit in a "verified" dataset
indefinitely and corrupt everything built on top of it before anyone
notices.

## Sensitivity testing before calling anything "confirmed"

A tunable empirical value earns `CONFIRMED` only after being tested
against real data and at least one real alternative. `[SETTLED
METHODOLOGY]` means the governing methodology has been explicitly
approved; its evidentiary basis may be empirical, conceptual, or both
and should be documented accurately. The replacement-level rank
thresholds and Component 4's normalization method (see `config.py`'s
comments and `LWI_MODEL_CARD.md`) are both `CONFIRMED` on this basis,
with the tested alternatives and the actual tradeoff accepted recorded
alongside the constant, not just the winner.

Where a value is honestly not yet at that bar, `config.py` says so
directly -- e.g. Stars-by-Value's production-composite weight is
explicitly flagged "provisional... left open pending further
calibration," rather than borrowing the confidence of a value that
actually earned it.

## Generated data versus hand-maintained data

`data/` has exactly one exception to "everything here is
pipeline-regenerated and gitignored":
[`data/manual/`](../data/manual/). The dividing line is not "is this a
CSV file," it's "did a human decide this, or did a formula compute
it." Anything a script can reproduce from scratch should not be
committed; anything a human confirmed through research must be
committed, or it isn't actually persisted.

Stars-by-Value applies the same line inside its own manual-override
mechanism: a 2010 acquisition-cost override can only be created from a
real, independent source, never from the classifier's own reasoning
restated as external corroboration (see the
`SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES` check in `config.py`)
-- a human judgment call must not be quietly replaced by the formula it
exists to check.

## Configuration centralization

Every tunable number that affects an output lives in `config.py`,
never inline in a script. Centralizing every tunable value also
centralizes the *opportunity* to catch a bad one via
`validate_lwi_config()` / `validate_sbv_config()` -- a constant buried
inline has no single place to validate it against reasonable bounds.

This extends to keeping unrelated specs' constants from bleeding into
each other: LWI's and Stars-by-Value's replacement-level definitions
are independently calibrated and intentionally different, even though
both are conceptually "replacement level." `TestNoAccidentalLwiReuse`
exists to prove SBV code never reads an `LWI_*` constant, or vice
versa, even where a name or shape coincides -- centralization is only
safe if it's also namespaced correctly.

## Regression tests anchored to real bugs

A test in this project exists to protect something real: a previously
observed bug, or a documented invariant/acceptance criterion that
needs to be proven correct before it's ever actually load-bearing.
What's avoided is writing tests speculatively, "in case something goes
wrong," with no traceable bug or invariant behind them -- e.g.
`TestIndexAlignmentRegression` (a real `.merge()` misalignment bug),
`TestNoDuplicateComponentFormulas` (two components found mathematically
identical), and `TestComponentAvailabilityPolicy` (proves a documented
spec policy holds before it's ever needed). See each test class's own
docstring for what it protects, and give new tests the same kind of
docstring.

The practical implication for future work: if you find a real bug,
write a regression test that would have caught it, in the same commit
as the fix. If you add a new documented invariant or acceptance
criterion, write a test proving it holds. Don't add tests for inputs
that can't occur just to raise a coverage number.

## Preservation of decision history

`CHANGELOG.md` has a "Rejected" section, not just
"Added/Changed/Fixed" -- ideas considered, tried, and abandoned (e.g.
alternate Component 1 blends, alternate Component 4 denominators) stay
on record with the reason they lost. `config.py`'s own inline comments
preserve the same kind of history for individual constants that were
renamed or re-derived rather than reused.

Without a record of what was already tried and rejected, and why, a
future session (human or Claude) risks quietly re-proposing an
already-abandoned approach. Never delete this history to make the
current implementation look simpler or more inevitable than the
process that actually produced it -- this applies equally to
methodological *corrections*: when a past limitation was found to have
been mischaracterized rather than fixed, that mischaracterization
stays on the record, struck through, not silently erased.

## Explicit tradeoff analysis

Nearly every nontrivial choice in this codebase is recorded with its
actual competing alternatives and the specific reason one won, not
just the winner in isolation -- see `config.py`'s comment on IQR vs.
standard deviation vs. MAD for Component 4's standardization as a
representative example: all three were tested head-to-head, and the
one chosen won on an explicitly named priority (false-positive
separation over marginal recall), not by default.

The pattern to follow: when a consequential choice has more than one
reasonable answer, name the alternatives considered, what was measured
to compare them, and the specific reason the chosen one won -- even
(especially) when the answer is close.

## Small, reviewable changes

Nothing in this repository should land as one large, hard-to-audit
change. The natural unit of work here is one logical change -- one bug
fix, one new component, one spec update, one new Dataset 2 trait
family -- each independently reviewable with its own commit message
explaining the *why*. The LWI version history (1.0 -> 2.0 -> 2.1, each
bump traceable to specific, individually-justified changes in
`CHANGELOG.md`) and Dataset 2's sequence of narrow, named commits both
follow this same discipline.

## How these principles carry into Datasets 2 and 3

Dataset 1 (LWI) and Stars-by-Value are working examples: this way of
working produces a trustworthy result. Dataset 2's active research
(`research/dataset2/`) is already inheriting every principle above in
practice, and Dataset 3 will too once modeling begins:

- **Dataset 2**: `LEAGUE_WINNER_TRAITS_SPEC.md` separates "Predictive
  Traits" from "Historical Findings" so a purely descriptive finding
  never gets silently reused as a modeling feature without clearing
  the leakage rule first -- specification-first and
  correctness-over-convenience applied directly.
- **Dataset 3** requires strict prior-only outcome validation: a model
  may use evaluation-season inputs genuinely known by the prediction
  cutoff, such as preseason ADP, but must never use that season's
  outcomes or in-season information, nor information from any later
  season. This is stricter than LWI Component 1's retrospective LOSO
  design, which prevents self-influence but may use later seasons.
  Every modeling choice should clear the same sensitivity-testing and
  explicit-tradeoff bar used for Dataset 1 and Stars-by-Value before
  being called "confirmed."
- Any real bug found while building Dataset 2 or 3 gets a regression
  test in the same commit as the fix, following the pattern
  [`tests/test_calculate_metrics.py`](../tests/test_calculate_metrics.py)
  already established. Any rejected approach gets recorded the same
  way `CHANGELOG.md` already does for Dataset 1.
- If evidence from Dataset 2's research contradicts an intuition
  carried since Dataset 1, that's "evidence over expectation" applying
  to new territory -- surface the conflict and let it change the plan,
  don't quietly bury a disappointing result.
