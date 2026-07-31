# CLAUDE.md

Operating instructions for Claude Code sessions in this repository.
This file states rules; `docs/ENGINEERING_PRINCIPLES.md` explains why
they exist -- read that when a rule's reasoning isn't obvious.

## What this project is

A reproducible research pipeline (2006-2025 fantasy football), not a
software product -- **research first, software second**. Code exists
to implement documented methodology, not define it. Dataset 1 (League
Winner Index) and Stars-by-Value (Dataset 3's label pipeline) are
complete; Dataset 2 (League Winner Traits) has active research
underway in `research/dataset2/`; Dataset 3's predictive model is
specced but not built. Evan is the sole maintainer, but write
documentation for a future human collaborator, not only future-Evan or
a future Claude session.

Correctness, reproducibility, transparency, and long-term
maintainability outrank convenience or speed.

## Non-negotiables

- **Specs are authoritative.** `docs/METRIC_SPECIFICATION.md`,
  `docs/MATCHING_ARCHITECTURE.md`, `docs/PREDICTION_SPECIFICATION.md`,
  `docs/LEAGUE_WINNER_TRAITS_SPEC.md`, `docs/VERSION_1_SCOPE.md`
  describe what the code should do. If code and spec disagree, assume
  the code is wrong -- never quietly edit the spec to match the code.
- **Spec before implementation**, whenever practical. New Dataset 2
  trait families must have their methodology documented and reviewed
  before implementation or outcome analysis, with the decision record
  kept under `research/dataset2/` or the governing specification as
  appropriate.
- **No silent methodology changes.** Never change a documented
  formula, threshold, or matching rule to make code simpler or a test
  pass. If a spec seems wrong, say so and propose a change explicitly.
- **Explain unfamiliar concepts.** Evan is technically curious but not
  a professional engineer -- explain unfamiliar Git, Python,
  statistical, or architectural concepts as they come up.
- **Present tradeoffs before consequential decisions.** When more than
  one valid approach exists, lay out tradeoffs and recommend one
  before making an architectural or methodological call.
- **Challenge assumptions.** Agreeing by default is a failure mode
  here. Push back when evidence or project logic points elsewhere.
- **Never commit or push without explicit approval, every time.** A
  prior approval doesn't carry forward. Explain what a destructive or
  hard-to-reverse operation will do before running it.
- **Small, single-purpose commits.** One logical change per commit.
  Run relevant tests after any meaningful change and report the exact
  command and result, not just "tests pass."
- **Preserve decision history.** Don't delete or rewrite CHANGELOG's
  "Rejected" section, the Model Card's falsification history, or
  `config.py`'s inline rationale to make current code read more
  cleanly.

## Repo-specific facts

- **Tunables live in `config.py`**, with their documented status --
  never inline in a script. See ENGINEERING_PRINCIPLES.md's
  "Configuration centralization."
- **Config validation fails loud.** `validate_lwi_config()` /
  `validate_sbv_config()` raise on bad config rather than producing a
  plausible-looking wrong answer. See "Fail-loud validation."
- **`data/manual/` is the only hand-maintained, git-tracked part of
  `data/`.** Everything else is pipeline-regenerated and gitignored --
  never hand-edit or commit it. See "Generated data versus
  hand-maintained data."
- **Tests protect something real** -- a documented invariant or a
  previously observed bug, named in the test's docstring. See
  "Regression tests anchored to real bugs."
- **Low-confidence matches get flagged and excluded, never guessed.**
  Policy in `docs/MATCHING_ARCHITECTURE.md`.
- **The established path for real network fetches from ADP/stats
  sources is GitHub Actions** (`ci_*.py` scripts) -- don't assume
  another environment reaches those sources the same way without
  checking first.
- **Version identifiers (`LWI_VERSION`, `SBV_VERSION`) must uniquely
  identify the formula/methodology that produced an output** -- bump
  on any change that breaks comparability with the prior confirmed
  version.
- **Dataset 2 traits split into "Predictive" and "Historical
  Findings."** A descriptive, non-preseason-knowable finding never
  becomes a Dataset 3 feature without clearing the leakage rule in
  `docs/LEAGUE_WINNER_TRAITS_SPEC.md` (every input dated before that
  season's Week 1).

## Before a methodological decision

1. Check the relevant `docs/` spec -- is this already decided, and
   why?
2. Check `CHANGELOG.md`'s "Rejected" section -- has this exact idea
   already been tried and abandoned? Do not silently re-litigate
   rejected approaches without new evidence.
3. Read `docs/ENGINEERING_PRINCIPLES.md` if it's unclear how a new
   situation fits this project's conventions.
