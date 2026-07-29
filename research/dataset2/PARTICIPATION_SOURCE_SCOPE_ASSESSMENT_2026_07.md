# Source C Scope Assessment — 2026-07

**DECIDED (2026-07): Source C Stage 1 is approved in a narrowed
foundation role.** This document originally posed the keep/remove
question open; it has since been answered. Kept, as coverage-limited
infrastructure for later research (not a general-purpose Dataset 2
trait pipeline): raw acquisition and provenance, explicit schema-version
handling, normalized player-play-role participation, identity auditing,
duplicate-source-ID auditing and defensive deduplication, and the real
personnel/formation/box-count/pass-rusher-count/targeted-route context
fields. Removed, per §3's recommendation below (acted on, not just
proposed): `build_season_participation_summary()` and
`build_preseason_participation_features()`. No Source C-derived trait
is implemented. The analysis below is preserved as the record of why,
not rewritten to read as though the answer were obvious from the
start.

---

## 1. What this source cannot do (recap)

Full route participation, routes-per-dropback, targets-per-route-run,
and alignment shares are **not recoverable** from `pbp_participation`
alone — see `PARTICIPATION_ROUTE_DEFINITION_PROPOSAL_2026_07.md`. Do
not build or imply any of these from this source.

---

## 2. What real, distinct capability does this source actually add to
this project?

Four candidate capabilities were evaluated:

### A. Possession-side presence at PLAY grain — real, distinct from
anything Source A/B provide

Sources A (weekly stats) and B (`snap_counts`) both stop at
player-GAME or player-WEEK grain. `pbp_participation`'s raw and
normalized layers are the only real source in this project with
player-PLAY grain. This genuinely supports research questions Source
A/B structurally cannot answer, e.g.:
- "How did this offense perform specifically on the plays player X was
  on the field for, vs. plays he wasn't" (a real with/without-player
  design).
- Personnel-package context: this file uniquely carries real
  `offense_formation`/`offense_personnel`/`defense_personnel`/
  `defenders_in_box`/`number_of_pass_rushers` fields that exist in NO
  other source this project has acquired.

**Verdict: real, distinct value. Not a duplicate of anything else.**

### B. Targeted-route type — narrow but real, distinct

Not available from any other source in this project. Real but scoped
to the ~42-45% of plays with a decided target. Not yet implemented
(proposal only).

**Verdict: real, distinct, narrow value.**

### C. Personnel context / "with-or-without-player" analysis — same as
A, restated as a research design rather than a data field

This is a use of capability A, not a separate one. Restating it here
because it's the most likely actual DATASET 2 application: e.g. does a
star WR's real snap-level presence change a scheme's real formation
tendency, independent of any route-count question. Genuinely requires
play-level grain; genuinely not something Source B's per-game
aggregates could support even in principle.

### D. Season/preseason possession-side aggregates (formerly
`possession_side_plays_participated`/`non_possession_side_plays_participated`
and their `prior_season_*` lags — REMOVED per §3 below)

**This was the one under real scrutiny.** Assessed directly against
Source B's existing, real, verified season aggregates:

| | Source B (`snap_traits.py`) | Source C (`participation_traits.py`) |
|---|---|---|
| Real offensive-snap count | `offense_snaps` — direct real sum from nflverse's own official snap-count release | `possession_side_plays_participated` — a real count, but CONFLATES true offensive scrimmage snaps with special-teams snaps where the player's team had the ball (e.g. a punt/kickoff/FG unit) |
| Real defensive-snap count | `defense_snaps` — direct real sum | No equivalent — `non_possession_side_plays_participated` conflates true defensive snaps with ST snaps where the player's team did NOT have the ball (e.g. punt/kickoff return) |
| Real special-teams count | `st_snaps` — direct real sum, already isolated | Not separable — tested two candidate play-type filters (`offense_formation` nullness; specialist-position presence) and found neither reliable (§ below) |
| Verification | Recomputed `offense_pct` matches nflverse's own reported value on 100% of a real 2023 sample (Source B audit) | No equivalent verification exists or is possible without a reliable play-type split |

**The scrimmage-vs-special-teams split was investigated (per item 2 of
your request) and found NOT reliable** — see the full real test in
`participation_traits.py`'s module docstring: `offense_formation`
nullness looked like a natural real proxy, but 4,342 of the 9,209 real
2023 null-formation rows have completely ordinary offensive personnel
(most commonly standard 11-personnel) and no specialist position
present — these are real, ordinary run/pass plays that simply lack a
formation tag, not special-teams plays. Since this is a real, disclosed
NGS tracking-coverage gap rather than a play-type signal, deriving
`scrimmage_offense_plays_participated`/`scrimmage_defense_plays_participated`/
`special_teams_plays_participated` from it would output a plausible-
looking but wrong split — exactly what the reconstruct-or-defer rule
(already applied to Source A's `racr` and Source B's `defense_pct`/
`st_pct`) says not to do. **These three fields are not derived.**

**Conclusion**: without a reliable scrimmage/ST split, the season/preseason
aggregate layer's real output — `possession_side_plays_participated`/
`non_possession_side_plays_participated` — is a strictly WEAKER,
CONFLATED version of a question Source B already answers precisely and
with a verified real reconciliation. It adds no real information Source
B doesn't already have in cleaner form, for the specific "how much did
this player play on offense/defense/special-teams" question.

---

## 3. Recommendation — ACTED ON (2026-07)

**Kept**: `build_raw_play_data()` and `normalize_participation()`
(the raw and normalized layers), plus
`lib/dataset2/participation_identity.py` (the identity audit),
`build_duplicate_source_id_report()`, and the real acquisition/manifest
infrastructure in `nflverse_source.py`. These support capability A/B/C
above, which are real and not duplicated anywhere else in this project.
Classified explicitly as COVERAGE-LIMITED INFRASTRUCTURE for later,
narrowly scoped research (a specific with/without-player study, a
targeted-route-type trait, a personnel-context analysis) — not a
general-purpose Dataset 2 trait pipeline the way Sources A/B are, and
no trait is implemented on top of it yet.

**Removed**: `build_season_participation_summary()` and
`build_preseason_participation_features()` — the season/preseason
possession-side aggregate layer. It duplicated Source B with weaker,
conflated, and potentially MISLEADING possession-side semantics
(§2.D above): exposing `possession_side_plays_participated` as a
preseason player-usage feature would have risked a future consumer
mistaking it for a true offensive-snap count, when `snap_traits.py`'s
`offense_snaps`/`defense_snaps`/`st_snaps` is the real, correct,
already-verified answer to that question. **Source B remains canonical
for actual offensive snap counts and offensive snap percentages.** This
was not a "someday cleanup" item — per this project's own standing rule
("don't retain infrastructure solely because it was already built"),
carrying a known-weaker, potentially misleading duplicate forward was
itself the thing to avoid. The two functions, their tests, and the
`SUM_FIELDS`/`SEASON_OUTPUT_COLUMNS`/`PRESEASON_OUTPUT_COLUMNS`/
`POPULATION_REQUIRED_COLUMNS` constants that existed only to support
them have been deleted from `lib/dataset2/participation_traits.py` and
`tests/test_dataset2_participation_traits.py`.

---

## 4. Does the remaining scope (raw/normalized/identity only) justify
keeping Source C? — DECIDED: yes, as infrastructure, not as a trait
source

**Correction (2026-07): no approved first-wave Dataset 2 trait
currently REQUIRES Source C — that is a different, narrower claim than
"no trait can consume it."** The acquisition and identity-audit
infrastructure is already built, real, tested, and produces zero-cost
ongoing maintenance burden (same pinned/manifest pattern as every other
nflverse source this project uses), so the marginal cost of keeping the
raw/normalized/identity layers is low. Several LATER taxonomy
hypotheses may plausibly use its real personnel and play-context
fields once they're scoped and approved:
- Personnel/formation context (`offense_formation`/`offense_personnel`/
  `defense_personnel`) for any future formation-tendency or
  scheme-context hypothesis.
- With/without-player analysis, using the play-level grain no other
  source in this project has.
- Targeted-route-type outcomes (§2.B), for a future route-tree-tendency
  hypothesis.
- Defenders-in-box context (`defenders_in_box`), for a future run-funnel
  or box-count-related hypothesis.
- Pass-rusher-count context (`number_of_pass_rushers`), for a future
  pass-protection or pressure-context hypothesis.

None of these is implemented, scheduled, or approved as a trait yet —
this section documents plausible future use, not a commitment to build
any of them. The module's role for now is exactly what §1's opening
states: coverage-limited infrastructure, kept because it's real,
tested, low-cost to maintain, and unlocks options later taxonomy work
may want — not because building it created an obligation to use it
immediately.
