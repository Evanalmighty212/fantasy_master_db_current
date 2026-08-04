# Matching Architecture

This is the permanent reference for how player identity matching works
(`scripts/player_matching.py`, used by `scripts/04_build_master_dataset.py`).
If matching behavior ever needs to change, change it here in spirit
first, then in code -- this document should never drift from what the
code actually does.

---

## Why this exists

ADP data (from FFC/FFToday) and nflverse results data identify players
by name only, from two completely independent sources with no shared
ID. Every match is therefore inferred, not looked up. This document
exists so that inference is principled and auditable, not ad hoc.

---

## Approved next architecture: separate identity, position, and team authority

**Methodology status: APPROVED by Evan (2026-07). Implementation
status: NOT YET IMPLEMENTED.** The matching strategy documented below
describes the current live code until the approved implementation is
reviewed and committed. No current generated artifact should be
described as already implementing this section.

Player identity, fantasy position, team identity, and football usage
are different facts and must not be collapsed into one field:

- **Player identity** answers which real person an ADP row describes.
  It is governed by a stable player ID resolved against a player/roster
  directory before the results join. Position disagreement is
  corroborating or review evidence only; it must never redirect the
  ADP row to a different player. A resolved player with no season
  results row remains `identity_resolved_no_results_row`, rather than
  being reassigned to a similar observed name. The real 2021 Michael
  Thomas-to-Mike Thomas failure is the regression case this rule must
  prevent.
- **ADP-source position** is the position printed by the contemporaneous
  ADP source. It is preserved unchanged for provenance and governs
  positional ADP ranking unless that source value is separately shown
  to be erroneous.
- **Official/team position** is the contemporaneous NFL/team-listed
  position. It is preserved separately as evidence and is not assumed
  to equal fantasy eligibility for a legitimate hybrid.
- **Canonical fantasy position** is one separately governed,
  preseason-frozen position per player-season. It governs positional
  finish, replacement comparison, LWI, Stars-by-Value/bust position
  cells, and position-specific Dataset 2 traits. It must be knowable
  before that season's Week 1; an in-season conversion cannot be
  backdated into a preseason predictor.
- **Usage roles** preserve the actual passing, rushing, receiving,
  return, and snap evidence as nonexclusive facts. Designed carries do
  not by themselves convert a receiver such as Deebo Samuel or Percy
  Harvin into a running back.

Canonical fantasy position follows this authority order: an approved
player-season override; otherwise verified contemporaneous fantasy/ADP
position when available and football-coherent; otherwise a documented
official/team position established by the preseason cutoff; otherwise
a predeclared named fantasy authority. For an otherwise clean
historical row with none of those authorities, Evan has approved the
explicitly named `processed_results_position_fallback`: it may carry
the processed results position into the canonical field only when
there is no approved override, explicit unresolved case, known
cross-position conflict, contrary ADP-source position, or contrary
manual evidence. Its authority and `constrained_fallback` status must
be stored on the row. It is an auditable coverage fallback, **not**
independently verified preseason evidence. Any stronger evidence,
approved override, or unresolved decision supersedes it; a materially
conflicting case stays unresolved until Evan decides.

Identity resolution is a prerequisite for ordinary ADP-source
position authority. An `exact_name_position_mismatch`, unresolved
identity-confidence case, or equivalent matching conflict must retain
an explicit unresolved/conflict status even when an ADP position is
present. That ADP value remains evidence, but it is not promoted to
clean canonical authority until the identity conflict is adjudicated;
an approved player-season override may resolve and supersede it.

The legacy bare `position` field is canonical-only. It is populated
from `canonical_fantasy_position` for resolved statuses and is null for
every unresolved status; it never falls back to processed results.
`processed_position` and the raw provider fields retain the historical
source values under their explicit names.

The approved player-season treatments are:

| Player | Canonical fantasy position treatment |
|---|---|
| N'Keal Harry | WR for 2019-2022 only. No approved correction for 2023 or 2024. |
| Cordarrelle Patterson | WR for 2013-2019; RB from 2021 onward. For 2020, use RB only if a contemporaneous preseason fantasy-position authority corroborates it; otherwise unresolved. |
| Dexter McCluster | WR in 2011; RB in 2012 and 2014-2016; WR in 2013. |
| Ty Montgomery | WR in 2016; RB from 2017 onward. |
| Terrelle Pryor | QB for 2011-2013; WR from 2015 onward. |
| Deebo Samuel and Percy Harvin | WR; rushing remains usage, not a position conversion. |
| Taysom Hill | 2023 unresolved pending a named fantasy-position authority. No other Hill season is decided by this entry. |

Team fields follow the same separation. The provider's raw team value
must be retained unchanged as source provenance. A separately named,
season-accurate **canonical team** governs matching, team logic, joins,
and player-facing output. Canonical team construction must distinguish
historical franchise-code aliases (for example OAK/LV, STL/LA, and
SD/LAC) from a real player transaction and from a provider field that
was retrospectively updated. FFC raw team metadata is therefore never
silently overwritten and must not become an automatic identity
tie-breaker before its season accuracy is established.

---

## Normalization rules

Two separate normalization functions exist, deliberately not shared:

**`02_clean_adp.py`'s `normalize_name()`** -- used for the
`player_name_normalized` column stored in the clean ADP output, which
a human may read directly. Does:
- Strip trailing parenthetical team tags (`"Steve Smith(NYG)"` -> `"Steve Smith"`)
- Collapse whitespace
- Remove periods (`"T.J. Houshmandzadeh"` -> `"TJ Houshmandzadeh"`)
- Lowercase

**`player_matching.py`'s `normalize_name()`** -- used only internally
for comparison during matching. Does everything the above does, PLUS:
- Strips generational suffixes as whole words: Jr, Sr, II, III, IV
  (`"Robert Griffin III"` -> `"robert griffin"`)

The suffix-stripping is intentionally NOT in `02_clean_adp.py`'s
version. The stored `player_name_normalized` column is meant to be
readable ("who is this row about"), where keeping "III" as written is
more useful to a human. The matching-internal version is meant to
maximize correct matches, where the suffix is pure noise. If you ever
consolidate these into one function, you lose that distinction --
don't, unless you also change what the stored column is for.

---

## Matching strategy, in priority order

The first match found wins. Later stages are only attempted if earlier
ones produce no match.

### 1. Manual override table (highest priority, always checked first)

`data/manual/player_name_overrides.csv`. Columns: `season,
adp_player_name_original, position, nflverse_player_id, notes`.

A human said "this ADP name in this season is this nflverse
player_id," full stop. No further reasoning applied. This exists
specifically for cases the algorithm will never get right on its own
(see Collision Policy below) and is the intended long-term home for
resolving anything that lands in the review/duplicate reports.

### 2. Exact match on (season, normalized_name, position)

If exactly one nflverse player in that season, at that position, has
that normalized name: match, confidence 100, `match_type =
exact_name_position`. This is the large majority of real matches
(~97% of in-scope 2007-2024 rows).

### 3. Exact match on (season, normalized_name) alone, position ignored

If step 2 found zero candidates but exactly one nflverse player that
season has the matching name at ANY position: match, confidence 90,
`match_type = exact_name_position_mismatch`. Auto-matched, but ALSO
written to `low_confidence_player_matches.csv` for review -- a
position discrepancy between sources is a real signal worth a human's
attention even when the name match itself is solid (e.g. a
position-flexible player like Cordarrelle Patterson or Ty Montgomery
II, tagged differently by different sources in different years).

### 4. Fuzzy match within (season, position)

Uses `rapidfuzz.fuzz.ratio()` on normalized names, restricted to
candidates in the same season and position (never fuzzy-matches across
positions -- that would be a much more dangerous source of false
positives).

- **Score >= 92**: auto-match, `match_type = fuzzy_high_confidence`.
- **80 <= score < 92**: auto-match, but ALSO written to
  `low_confidence_player_matches.csv`, `match_type =
  fuzzy_low_confidence`.
- **Score < 80**: no match at this stage.

These thresholds were tuned empirically against real 2007-2024 data,
not chosen a priori. Known good catches at these thresholds: "Ted Ginn
Jr." -> "Ted Ginn" (84%), "Joshua Cribbs" -> "Josh Cribbs" (92%). Known
correctly-REJECTED near-miss: "Peyton Manning" vs "Eli Manning" scored
72% and correctly stayed unmatched (different real people, siblings,
both QBs -- a genuinely dangerous fuzzy-match trap that the floor
correctly avoided). Known gap: "Michael Vick" vs nflverse's "Mike
Vick" scores only 76%, just under the review floor, so it currently
lands in `missing_adp_matches.csv` rather than being caught for
review. Common-nickname normalization (Michael/Mike, Chris/Christopher,
etc.) is a known, not-yet-built improvement -- see Known Limitations.

### 5. No match at any stage

Written to `missing_adp_matches.csv` with the best fuzzy score found
(even if below the review floor) and its closest candidate name, so a
human reviewing the report can see what the algorithm considered and
rejected, not just that it gave up.

---

## Duplicate / collision handling

A "duplicate" in matching (`duplicate_player_matches.csv`) is
different from a "collision" in the join (see below) -- they happen at
different stages and are handled differently.

**Matching-stage duplicates**: if step 2 or step 3 finds MORE than one
candidate (a genuine name collision within a season/position -- e.g.
two different real "Steve Smith"s, both WRs, active in the same era;
two different "Adrian Peterson"s, both RBs), the ADP row is NOT
auto-matched to either. It's written to `duplicate_player_matches.csv`
for a human to resolve via the override table. Picking one
arbitrarily would silently attach the wrong player's ADP data to a
real performance row roughly half the time -- worse than leaving it
unmatched.

**Join-stage collisions** (in `04_build_master_dataset.py`, not
`player_matching.py`): after matching, it's possible for two DIFFERENT
ADP rows to have been matched (via different paths -- e.g. one exact,
one fuzzy) to the SAME `(season, nflverse_player_id)`. This is a
strong signal that at least one of the two matches is simply wrong.

**Real example that surfaced this exact case**: in 2007, "Chris Henry"
(RB, Tennessee) matched exactly (`exact_name_position`, confidence
100) to nflverse player_id `00-0025437`. Separately, "Chris Perry" (RB,
Cincinnati -- a real, different player) fuzzy-matched at 81.8%
confidence to that SAME player_id. Both matches individually looked
plausible in isolation; only checking for the collision revealed one
of them had to be wrong.

**Policy**: when this happens, BOTH sides of the collision are
excluded from the join entirely (not "keep the higher-confidence one,"
not "keep first") -- resulting master-DB rows get `data_quality_flag =
no_adp_match` rather than either being silently corrupted. This was a
deliberate design change made after finding the Chris Henry/Chris
Perry case in testing; an earlier version of the code kept the first
occurrence, which would have (approximately half the time) attached
wrong ADP data to a real player's results row. Collisions are logged
to `duplicate_adp_to_player_id_matches.csv` for the same override-table
resolution path as matching-stage duplicates.

---

## Rationale for excluding ambiguous joins

The unifying principle across all of the above: **when the algorithm
isn't confident, don't guess -- flag it and exclude it from the
confident output.** This trades completeness for correctness. A
`no_adp_match` row is honest and easy to spot; a wrong match silently
sitting in the master dataset labeled `matched_clean` is not, and
would quietly corrupt any downstream analysis (League Winner Index,
ADP value studies, etc.) built on top of it without any visible
warning sign.

This also means the review reports (`missing_adp_matches.csv`,
`low_confidence_player_matches.csv`, `duplicate_player_matches.csv`,
`duplicate_adp_to_player_id_matches.csv`) are not a "nice to have" --
they're where the genuinely ambiguous cases live, and the override
table is the intended mechanism for resolving them over time as
someone reviews and confirms each one.

---

## Manual override workflow

1. Review the flagged reports (missing / low-confidence / duplicate /
   collision).
2. For any row you can confidently resolve, add a line to
   `data/manual/player_name_overrides.csv`:
   `season, adp_player_name_original, position, nflverse_player_id, notes`.
   Use the ADP name EXACTLY as it appears in `player_name_original`
   (not normalized) -- the lookup re-normalizes it internally.
3. Re-run `02_clean_adp.py` -> `03_download_stats.py` ->
   `04_build_master_dataset.py` (or the full pipeline). The override
   table is checked first, before any algorithmic matching, so it will
   take precedence automatically.
4. This file is hand-maintained and persistent -- it is NOT
   regenerated by any script, and (per `.gitignore`) is meant to be
   committed, unlike everything else under `data/`.

---

## Known limitations (not yet fixed)

- No common-nickname normalization (Michael/Mike, Chris/Christopher,
  Joshua/Josh handled only when the fuzzy score happens to clear the
  floor -- "Michael Vick"/"Mike Vick" at 76% currently does not).
- Fuzzy matching is O(n) per ADP row against the season+position pool
  (a linear scan, not indexed) -- fine at current data volumes
  (~150-200 players/season/position pool), would need revisiting if
  scope ever expanded significantly.
- No matching against multiple candidate nflverse IDs when a player
  changed primary position mid-career in ways that span the
  season+position exact-match key (partially mitigated by step 3, but
  not exhaustively).
