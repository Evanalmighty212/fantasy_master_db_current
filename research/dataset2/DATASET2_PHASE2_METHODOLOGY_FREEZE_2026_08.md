# Dataset 2 Phase 2 (protected holdout confirmation) — methodology freeze (2026-08-22)

**Status: METHODOLOGY APPROVED by Evan (2026-08-22). Implementation
status: NOT BUILT.** This document freezes the Phase 2 candidate set
and confirmation rule using only the completed Phase 1 discovery
package (HEAD `0e6a67014901456b15341eff9ab06bc563cbce74`) and existing
governing documentation. **No 2021–2025 holdout row has been loaded,
inspected, or fit against by anyone at the time this freeze was
written.** Per `research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md`
§10 ("Holdout protection"), advancement rules must be frozen using
discovery-season data alone before the holdout window is inspected
even once — this document is that freeze.

This is a decision record, not an implementation. The Phase 2 holdout
runner itself is out of scope for this document and has not been
authorized to build or launch.

---

## 1. Phase 2 candidate set

**Carried forward — 32 League Winner Index traits.** Every trait
marked `supported = True` in the completed Phase 1 discovery package's
`primary_results.csv` for the `lwi` family. Verified by direct read of
that file; not re-derived from a fresh Phase 1 run. The full list is
recorded as `PHASE2_CANDIDATE_TRAITS` in
`lib/dataset2/phase2_confirmation.py` and must not be edited outside a
new, explicitly dated revision of that constant plus this document.

**Source package provenance.** This candidate list was derived from
exactly one Phase 1 discovery package, identified by:

- Git HEAD: `0e6a67014901456b15341eff9ab06bc563cbce74`
- `primary_results.csv` sha256:
  `006d35d7c8b830ab6e1a8cffde6c92c57cfe6bbd741b0798c0a803e33765edb4`
  (from that run's own `outputs.sha256` manifest, itself verified
  against the file at freeze time)

Both values are recorded as `DATASET2_PHASE1_SOURCE_GIT_HEAD` and
`DATASET2_PHASE1_SOURCE_PRIMARY_RESULTS_SHA256` in `config.py`, pinned
by `validate_dataset2_phase2_config()`. A future Phase 2 holdout runner
must call `verify_phase1_source_package()` in
`lib/dataset2/phase2_confirmation.py` with the git HEAD and
`primary_results.csv` checksum of whatever Phase 1 package it is
actually pointed at, and must refuse to run if either does not match
these frozen values — the candidate list is not guaranteed to reflect
a different package's findings. Separately, `phase2_confirmation.py`
fingerprints `PHASE2_CANDIDATE_TRAITS` and
`PHASE2_EXCLUDED_UNSTABLE_TRAITS` themselves
(`_EXPECTED_CANDIDATE_LIST_SHA256`, checked at import time) so that an
accidental or unreviewed edit to either tuple fails loudly rather than
silently changing which traits Phase 2 evaluates.

**Excluded — 2 Star team-identity findings**, under the pipeline
proposal's existing "consistent football interpretation" manual review
provision (§11 item 4: "a qualitative, human/domain-review gate...
explicitly NOT automatable"):

- `fam10_depth_chart_team`
- `fam4_nfl_draft_team`

Both cleared Phase 1's formal statistical gates (evidence coverage,
family-wise FDR at `q < 0.10`). Both are excluded here because their
own **discovery-only** leave-one-season-out robustness check (already
computed and recorded in the Phase 1 output package's `robustness.csv`,
using only 2010–2020 data) showed a meaningful share of their
30-plus individual team-level contrasts flipping direction depending
on which discovery season was held out. A 30-plus-level team-identity
joint test is also not a single, actionable football trait in the
sense this research question is after. This exclusion decision uses
discovery-season evidence exclusively and is frozen here, before any
holdout data is opened, per §10's requirement. It is an application of
an existing manual-review provision, not a change to any automated
rule — no methodology amendment is required.

**Carried forward — 0 Strict Bust traits.** No Strict Bust trait
cleared Phase 1's discovery-side gates (0 of 105 fitted pairs were
`supported`), so none are eligible. This is a null result from Phase 1
itself, not an exclusion decision.

Total Phase 2 candidates: **32**.

---

## 2. Official Phase 2 confirmation rule (Option B: sign + magnitude-ratio band)

For each candidate trait, Phase 2 will:

1. Fit the same frozen Phase 1 model form (same predictor definition,
   same controls, same reference levels) **once** on 2021–2025 holdout
   rows only — a single point estimate, not a resampled/bootstrapped
   estimate.
2. Compare that holdout point estimate against the trait's already-computed
   Phase 1 discovery-window adjusted effect (read from the existing
   Phase 1 output package, never recomputed).
3. Classify the result:
   - **Confirmed** — the holdout effect has the same sign as the
     discovery effect, AND its absolute magnitude is between
     one-third (`1/3`) and three times (`3.0`) the discovery effect's
     absolute magnitude, inclusive.
   - **Contradicted** — a valid holdout estimate exists but falls
     outside that same-sign-and-magnitude-band condition (wrong sign,
     or magnitude ratio outside `[1/3, 3]`).
   - **Inconclusive** — the holdout fit could not produce a valid
     estimate at all (non-finite result, or a design/data condition
     that prevents fitting). A trait with `discovery_effect == 0` is
     undefined under this rule and must fail loudly rather than
     silently resolve to any of the three verdicts.
4. Holdout statistical significance (a p-value, confidence interval,
   or any measure of holdout-side precision) is **descriptive only**
   and is never required for, or capable of overriding, the
   confirmed/contradicted/inconclusive verdict above.

Frozen constants (added to `config.py`, validated by
`validate_dataset2_phase2_config()`):

- `DATASET2_HOLDOUT_MAGNITUDE_RATIO_MIN = 1/3`
- `DATASET2_HOLDOUT_MAGNITUDE_RATIO_MAX = 3.0`
- `DATASET2_PHASE2_METHODOLOGY_VERSION = "dataset2_phase2_holdout_confirmation_v1_2026_08"`

The rule's pure evaluation logic (no data loading, no fitting, no
holdout access) is implemented as `evaluate_holdout_confirmation()` in
`lib/dataset2/phase2_confirmation.py`, covered by synthetic-only tests.

---

## 3. Future uncertainty analysis (deferred, non-binding)

Option C from the decision memo — using holdout confidence/uncertainty
ranges rather than a fixed magnitude-ratio band — is **not** part of
the official Phase 2 verdict defined in §2. It may, at a later date,
be run purely as a **descriptive sensitivity analysis** alongside the
official verdicts. It must never change a confirmed/contradicted/
inconclusive verdict already reached under §2's rule; if it is ever
built, its output is reported side-by-side, not substituted in.

A genuine second confirmatory test — as opposed to a sensitivity
re-examination of the same 2021–2025 rows — requires new,
previously-unseen future-season data. Re-examining 2021–2025 under a
different rule after seeing how §2's verdicts came out would convert
that window into a second discovery set and destroy its purpose, per
§10's explicit prohibition on exactly this pattern.

---

## 4. What this document does not authorize

This freeze does not authorize building the Phase 2 holdout runner,
loading any 2021–2025 row, or launching Phase 2. Those remain separate,
explicit future decisions.
