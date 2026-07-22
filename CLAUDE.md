# CLAUDE.md

Operating instructions for Claude Code sessions in this repository.
Read this before making any non-trivial change. It states rules;
`docs/ENGINEERING_PRINCIPLES.md` explains why they exist.

## What this project is

A reproducible research pipeline, not a product. It builds a
historical fantasy football database (2006-2025) and computes the
League Winner Index (LWI) -- Dataset 1, complete. Two more datasets
(League Winner Traits, Predictive League Winner Probability) are
specced but not yet built. This is currently a single-owner research
project (Evan is the sole maintainer) -- there's no external
contributor process to coordinate with today. Documentation should
still stay understandable to a future human collaborator in case that
changes; write for "someone new to this codebase," not only for
future-Evan or a future Claude Code session.

**Research first, software second.** Code exists to faithfully
implement documented methodology. If a design choice looks
questionable, that is a methodology question to raise, not a code
detail to quietly patch around.

## Priority order when these are in tension

Correctness, reproducibility, transparency, and long-term
maintainability outrank convenience, cleverness, or speed. If a fix
is quick but makes an output harder to audit later, don't take it.

## Specs are authoritative

- `docs/METRIC_SPECIFICATION.md`, `docs/MATCHING_ARCHITECTURE.md`,
  `docs/PREDICTION_SPECIFICATION.md`,
  `docs/LEAGUE_WINNER_TRAITS_SPEC.md`, and `docs/VERSION_1_SCOPE.md`
  describe what the code is supposed to do. If code and spec
  disagree, assume the **code** has the bug -- don't quietly edit the
  spec to match whatever the code currently does.
- Write or update the spec before writing implementation, whenever
  practical. This project already does this: `PREDICTION_SPECIFICATION.md`
  and `LEAGUE_WINNER_TRAITS_SPEC.md` were both written before any
  Dataset 2/3 code exists, specifically so the target is fixed before
  research can unconsciously bend to fit whatever's easiest to build.
  Keep doing that for new work.
- Never silently change a documented formula, threshold, or matching
  rule to make code simpler or a test pass. If a spec seems wrong,
  say so and propose a spec change explicitly -- don't route around it.

## How Evan works, and how to work with him

- Evan is technically curious but not a professional software
  engineer. Explain unfamiliar Git, Python, statistical, or
  architectural concepts as they come up -- don't assume prior
  background.
- When more than one valid approach exists, lay out the tradeoffs and
  recommend one before making a consequential architectural or
  methodological call. Don't silently pick one and move on.
- Challenge assumptions when evidence or project logic points
  elsewhere. Agreeing by default is a failure mode here, not
  politeness.
- Never commit or push without explicit approval -- every time; a
  prior approval doesn't carry forward to the next change. Explain
  what a destructive or hard-to-reverse operation will actually do
  before running it.
- Keep commits small and scoped to one logical change. Run the
  relevant tests after any meaningful change, and report exactly which
  command was run and what it returned -- not just "tests pass."
- Don't delete or rewrite documented decision history (CHANGELOG's
  "Rejected" section, the Model Card's falsification history,
  config.py's inline rationale) just to make the current
  implementation read more cleanly. A rejected approach staying on
  record is what stops it from being silently retried later.

## Repo-specific conventions

(See `docs/ENGINEERING_PRINCIPLES.md` for the reasoning behind each.)

- **Tunable values live in `config.py`, not inline in scripts.** If a
  number affects an output (a threshold, a weight, a cap), it belongs
  there, with a comment on its status -- confirmed, or still an open
  question.
- **Tests exist to protect something real** -- a documented invariant
  or acceptance criterion (e.g. `TestComponentAvailabilityPolicy`,
  `TestConfigValidation` -- both verify policies stated in
  `METRIC_SPECIFICATION.md`/`config.py`, proven correct before any
  live incident), or a previously observed real bug (e.g.
  `TestIndexAlignmentRegression`, `TestNoDuplicateComponentFormulas`).
  What this project avoids is tests written just to inflate coverage
  numbers, with no traceable spec requirement, invariant, or bug
  behind them -- check a test class's docstring for what it's
  protecting before adding a new one, and give your own tests the
  same kind of docstring.
- **`data/manual/` is the only hand-maintained, git-tracked part of
  `data/`.** Everything else under `data/` (raw, processed, master,
  exports) is pipeline-regenerated and gitignored -- never hand-edit
  those, and never commit them.
- **The established, reproducible path for real network fetches**
  from external ADP/stats sources today is GitHub Actions (see
  `ci_fetch_adp_phase1.py` and the other `ci_*.py` scripts --
  purpose-built for CI runners with real outbound internet, not a
  robots.txt-respecting sandbox). Don't assume a different
  environment reaches those sources the same way without checking
  first -- if that ever changes, update this note and those scripts'
  docstrings together, don't let them silently drift apart.
- **When matching or joining data and confidence is low, flag and
  exclude -- never guess.** Explicit policy in
  `docs/MATCHING_ARCHITECTURE.md`; it trades completeness for
  correctness on purpose.
- **Config validation fails loud, not silent.** See
  `config.py`'s `validate_lwi_config()` -- bad configuration should
  raise immediately, never produce a plausible-looking wrong answer.
- **Version identifiers (e.g. `LWI_VERSION`) must uniquely identify
  which formula/methodology produced a given output** -- bump
  whenever a change, in `config.py` or in a script's formula logic,
  would make output non-comparable to the prior confirmed version.
  Related changes developed and landed together as one redesign
  effort can share a single bump (v2.0 bundled several component
  redesigns; v2.1 bundled the Component 4 standardization redesign
  together with its later winsorization fix) -- the bump marks
  reaching a new confirmed, production formula state, not every
  intermediate iteration on the way there.

## Before making an architectural or methodological decision

1. Check the relevant spec in `docs/` first -- is this already
   decided, and if so, why?
2. Check `CHANGELOG.md`'s "Rejected" section -- has this exact idea
   already been tried and abandoned? Don't silently re-litigate it
   without new evidence.
3. Read `docs/ENGINEERING_PRINCIPLES.md` if it's unclear how a new
   situation should be handled under this project's conventions.
