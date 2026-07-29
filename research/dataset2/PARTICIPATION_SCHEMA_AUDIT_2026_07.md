# Source C Stage 1 — Schema, Identity & Duplicate Audit — 2026-07

**REVISED TWICE, 2026-07.** First revision, after a real-data review of
the initial Stage 1 submission: (1) the season aggregate field names
were renamed from `offense_plays_participated`/`defense_plays_participated`
to `possession_side_plays_participated`/`non_possession_side_plays_participated`
(they measure possession side, not football offense/defense — see the
Hardman finding below, which is WHY the rename happened); (2)
`normalize_participation()` began collapsing a real duplicated source
ID to one row (`source_occurrence_count`/`had_duplicate_source_id`)
instead of one row per raw occurrence; (3) `--import-mode=importlib`
was documented as open technical debt.

**Second revision, approving Stage 1 in a NARROWED FOUNDATION ROLE**:
the season/preseason possession-side aggregate layer described in this
document's original validation-table section has been REMOVED
(`build_season_participation_summary()`/`build_preseason_participation_features()`
no longer exist in `lib/dataset2/participation_traits.py`) — it
duplicated Source B with weaker, potentially misleading semantics.
**Source B remains canonical for actual offensive snap counts and
offensive snap percentages.** The validation-table numbers below are
kept as the historical record of what was verified before removal (the
real Dobbs/Hardman/Drake possession-side counts and the preseason-lag
check were real and correct at the time) — they no longer describe a
live output of this module. See
`research/dataset2/PARTICIPATION_SOURCE_SCOPE_ASSESSMENT_2026_07.md`
for the full rationale, including the tested-and-rejected
scrimmage/special-teams split and the acted-on removal recommendation.

Requested before Source C Stage 1's foundation is reviewed. Every
number below comes from running the real, committed
`lib/dataset2/participation_traits.py` and
`lib/dataset2/participation_identity.py` against the REAL, fully
acquired `pbp_participation` data (2016-2025, fetched and cached via
`scripts/nflverse_source.py`'s asset-ID-pinned, sha256-verified
mechanism) and the real master DB population — not samples, not
synthetic data. Route participation, targets-per-route, alignment
traits, and family #9 thresholds are explicitly NOT part of this
stage — see
`research/dataset2/PARTICIPATION_ROUTE_DEFINITION_PROPOSAL_2026_07.md`
for that separate, implementation-free investigation (STATUS: NOT
SUPPORTED from this source — see that document's banner).

---

## Acquisition: raw files preserved unchanged

All 10 real seasons (2016-2025) fetched and registered via
`scripts/nflverse_source.py`'s `register_pbp_participation_manifest_entry()`
/ `fetch_pbp_participation()`, recorded in
`scripts/nflverse_source_manifest.json` under a new `"pbp_participation"`
key. Files live at
`data/raw/nflverse/annual/pbp_participation_{season}.csv`, gitignored
like every other raw cache file.

**Real schema fork at 2023, confirmed and handled explicitly**: two
files are published for 2023 — `pbp_participation_old_2023.csv`
(19.7MB, 20-column, matches 2016-2022) and `pbp_participation_2023.csv`
(49.9MB, 26-column, adds `offense_names`/`defense_names`/
`offense_positions`/`defense_positions`/`offense_numbers`/
`defense_numbers`). 2024/2025 file sizes (~49-50MB) confirm the
26-column shape is canonical going forward, so the fetch mechanism
registers `pbp_participation_2023.csv` (new), never `_old_2023`. Both
real shapes are exercised by the test suite
(`tests/test_dataset2_participation_traits.py::TestNormalizeExtendedSchema`
covers the 26-column path; every other normalize test runs on the
20-column shape).

---

## Grain, confirmed real

- **Raw input**: one row per real PLAY (`nflverse_game_id` + `play_id`).
  Real row counts: 45,184 (2025, smallest) to 50,714 (2021, largest).
- **Normalized output**: one row per real (game_id, play_id, gsis_id,
  role). Real total across all 10 seasons, REG-only: **9,455,530 rows**.

### Duplicate-play detection — real, active, zero exceptions

`build_raw_play_data()` doesn't just document the absence of a
duplicate `(nflverse_game_id, play_id)` pair — it ACTIVELY CHECKS after
every real season's REG filtering and raises a `RuntimeError` if found,
the same standing policy already applied to Source B's snap records.
Run directly against all 10 real seasons: **zero raised, every
season.**

### Postseason exclusion — confirmed against real week-token ranges

Real week tokens: 2016 run 01-21 (17 REG week-slots incl. bye + 4
playoff rounds), 2022 run 01-22 (18 REG week-slots + 4 playoff
rounds) — both exactly matching `season_length(season) + 1` as the
real REG/postseason boundary, the identical rule already proven for
Source A. `build_raw_play_data()` filters to REG by default; real REG
row counts range from 43,049 (2025) to 48,416 (2021).

---

## Semicolon-list parsing — full real 2016-2025 population, all edge
cases checked, none assumed

| Edge case | Real occurrences (2016-2025, 9,455,530 normalized rows) |
|---|---|
| Malformed token (non-`00-XXXXXXX` shape) | **0** |
| ID appearing in both offense_players AND defense_players on one play | **0** |
| ID duplicated within one play's own real source list | **470** distinct affected identities |

The third row is a real, disclosed exception to the "checked clean"
pattern the other two show, and is reported here in full rather than
smoothed over:

**470 real within-list duplicates, concentrated almost entirely in
2019** (467 of 470; 2 in 2024, 1 in 2025), by season and role, from
`build_duplicate_source_id_report()` run against the full real
2016-2025 population:

| Season | Role | Affected identities | Total excess occurrences |
|---|---|---|---|
| 2019 | non_possession | 467 | 467 |
| 2024 | non_possession | 1 | 1 |
| 2024 | possession | 1 | 1 |
| 2025 | non_possession | 1 | 1 |

Inspected directly: in 2019, real gsis_id `00-0035718` (not a
fantasy-relevant position — not found in the master DB population
under any season) appears twice in a single play's real
`defense_players` list on `2019_05_NYJ_PHI` play 196, and the same
pattern recurs across roughly 10 real 2019 games. This looks like a
real, localized data quirk in that specific nflverse release (not
something this project can diagnose further without contacting the
source), not a defect in the parsing logic.

**Why this cannot silently distort anything, REVISED design**: raw
source lists are preserved completely unchanged in
`build_raw_play_data()`'s output. `normalize_participation()` now
collapses a real duplicated ID to exactly ONE row per (play, gsis_id,
role) — never one row per raw occurrence — while disclosing the
anomaly via `source_occurrence_count` (how many times it appeared in
the real raw list) and `had_duplicate_source_id`. This makes
inflation structurally impossible at the normalized-row level, not
just at the season-aggregate level: verified directly on the real 2019
case above — gsis_id `00-0035718` produces exactly 590 real normalized
rows across the season (one per real distinct play, matching its 590
real distinct plays exactly, not the 1,057 raw list-entry occurrences
that existed before this revision's dedup), of which 467 carry
`had_duplicate_source_id == True` and `source_occurrence_count == 2`
disclosing exactly which plays had the real raw anomaly. This specific
ID is outside the fantasy population, so
it never reaches a Dataset 2 trait output regardless, but the
collapsing logic itself is proven correct against this real example,
not just a synthetic one. Tests: `TestNormalizeDuplicateSourceIds` in
`tests/test_dataset2_participation_traits.py`.

---

## Identity audit — full real 2016-2025 population

Unlike Source B, `pbp_participation` needs no crosswalk: it natively
reports real `gsis_id` values, the same ID system the master DB's
`player_id` already uses.

| Metric | Value |
|---|---|
| Total distinct real (season, gsis_id) identities, 2016-2025 | 56,713 |
| Overall match rate (all real participants vs. the master DB
  population) | 27.6% |
| Match rate for QB | **100.0%** |
| Match rate for RB | **100.0%** |
| Match rate for WR | **100.0%** |
| Match rate for TE | **100.0%** |
| Unmatched, ID never in population any season | 15,135 |
| Unmatched, known ID but different season | 221 |

**The 27.6% overall figure is not a data-quality problem — it's a real
scope mismatch, confirmed directly.** `pbp_participation` records
EVERY real on-field participant (all 22 real players per play: O-line,
D-line, DBs, LBs, specialists), while the master DB population is
deliberately scoped to four fantasy-relevant positions
(QB/RB/WR/TE). Restricted to exactly those positions, the real match
rate is a clean, perfect 100.0% for all four — no crosswalk ambiguity,
no partial matches, confirmed by running the real audit function
itself, not asserted.

**"Known ID, different season" (221 real cases), inspected directly** —
these are real skill players who ARE in the master DB for other
seasons but not the specific season in question: e.g. real gsis_id
`00-0028063` (Taiwan Jones, RB) is in the master DB for 2011-2013,
2015-2022 but genuinely absent for 2023; `00-0031299` (Jordan
Matthews, WR) for 2014-2019 and 2024 but not 2020-2023. These are real,
disclosed master-DB coverage gaps for fringe/deep-roster players in
specific off-years — not a participation-data defect, and never
silently dropped: `build_identity_audit()`'s `unmatched_detail`
preserves every one of these 221 real identities with its own
distinguishing `match_status`, separate from the 15,135 real
never-in-population IDs (defensive/O-line/specialist players entirely
outside the master DB's scope).

---

## Real-data validation table (2023 season, includes a real mid-season
trade) — HISTORICAL RECORD; the fields validated here no longer exist
as module output (see the "Second revision" note above)

This validation was real and correct when the season aggregate layer
existed; it's preserved here as the record of that verification, not
as documentation of a current output. The underlying raw/normalized
layers these counts were computed FROM are still real, still tested,
and still produce identical play-level data — only the season-summing
step (`build_season_participation_summary()`) that turned them into
`possession_side_plays_participated`/`non_possession_side_plays_participated`
has been removed.

| Player | Position | Real trade | possession_side_plays_participated (former field) | non_possession_side_plays_participated (former field) |
|---|---|---|---|---|
| Joshua Dobbs | QB | ARI (548 plays) → MIN (322 plays), real 2023 trade | **870** (548+322, correctly summed across both teams) | 0 |
| Mecole Hardman | WR | KC (142 plays) → NYJ (32 plays), real 2023 trade | 174 | **17** |
| Kenyan Drake | RB | BAL (12 plays) → GB (5 plays), real 2023 trade | 17 | 0 |

Dobbs's real trade validates the same team-attribution design proven
structurally sound in the module docstring: each of his real plays
already carries its own real team, so his season total correctly sums
across both teams with no separate crosswalk step needed (unlike
Source B's `pfr_id` situation).

**Hardman's nonzero non-possession-side count was a real, important
finding — and is EXACTLY WHY this whole layer was ultimately
removed rather than merely renamed**: inspected directly
(`2023_07_LAC_KC`, play 205) — Hardman (KC WR/return specialist)
appears in that play's real `defense_players` (source) list because KC
did not have possession on that snap (a real special-teams down). The
source's own "offense"/"defense" list names mean **possession side**,
not literal football offense/defense — on real special-teams plays,
the non-possessing team's return-unit personnel land in the
`defense_players` source list regardless of their real position. The
first revision renamed the season fields to disclose this; the second
revision concluded that disclosure alone wasn't enough given the
field's weak, conflated real-world meaning relative to Source B, and
removed the season/preseason layer entirely. `role` on normalized rows
(`ROLE_POSSESSION`/`ROLE_NON_POSSESSION`) still carries this real
distinction at the PLAY level, where it's an honest, disclosed fact
about a single play rather than a season total that could be
misread as a snap count. **Source B remains the canonical source for
actual offensive snap counts and offensive snap percentages.**

**Preseason lag was hand-verified against real data before removal**:
Dobbs's 2023 `prior_season_possession_side_plays_participated` (143.0)
matched his real 2022 `possession_side_plays_participated` (143.0)
exactly, confirming the raw/season/preseason separation and its
leakage-proof lag worked correctly against real data at the time. This
lag layer, and the season layer beneath it, no longer exist in the
module — see the "REMOVED" note above.

---

## Full suite

**Canonical full-suite command, recorded explicitly:**

```
python -m pytest tests/ -q --import-mode=importlib
```

Bare `python -m pytest tests/ -q` is NOT supported and should not be
claimed as such while the collision below is open.

**TECHNICAL DEBT, open, not resolved by this slice**: `research/dataset3/lib/`
and this project's top-level `lib/` are both literally named `lib`.
Confirmed directly (not assumed) by stashing all of this slice's
changes and re-running the bare command: the same 21 collection errors
occur on the clean, already-committed tree, so this is a **pre-existing
condition, not something introduced by Source C**. Root cause
(documented in `tests/test_production.py`'s own header comment):
pytest's default import mode collides the two same-named packages in
`sys.modules`, whichever gets imported first "wins" the name for the
rest of the process. `--import-mode=importlib` works around this by
giving each test module its own import namespace. This is not fixed
here — the real fix would be renaming one of the two `lib` packages
(a nontrivial, cross-cutting rename this task's scope does not cover)
or restructuring how `tests/test_production.py` subprocess-isolates
its import (see that file's own header for why it already works around
this the hard way). Flagging this explicitly as open technical debt,
not a solved problem, so it doesn't get silently reintroduced or
forgotten.

**884/884 passing**, current as of the final, narrowed Stage 1 commit
(`python -m pytest tests/ -q --import-mode=importlib`). Reconciled
exactly: 839 before Source C + 31
`test_dataset2_participation_traits.py` tests (the narrowed foundation:
raw acquisition, normalization, duplicate-source-id dedup and its
report — no season/preseason tests remain) + 10
`test_dataset2_participation_identity.py` tests + 4 guardrail
auto-scale (2 new `lib/dataset2/*.py` files) = 884. (Intermediate
revisions reached 886/886 and then 892/892 while the now-removed
season/preseason tests still existed; both counts are superseded by
this one.)

---

## Explicitly NOT done, per instruction

No route-participation, targets-per-route, alignment-trait, or family
#9 threshold derivation — see the separate route-definition proposal
document for that investigation (proposal only, not implemented). No
season-level or preseason-predictor trait of any kind (removed, not
merely deferred — see the "Second revision" note above). No Source C
Stage 2 work. Source C is retained as coverage-limited infrastructure
for later, narrowly scoped research (personnel/formation context,
with/without-player analysis, targeted-route-type outcomes,
defenders-in-box context, pass-rusher-count context) — no approved
first-wave Dataset 2 trait currently requires it, and none is
implemented here.
