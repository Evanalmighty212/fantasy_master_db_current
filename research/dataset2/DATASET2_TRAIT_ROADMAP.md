# Dataset 2 Trait Roadmap — APPROVED, first implementation wave underway

**Status: Roadmap and first-wave decisions APPROVED 2026-07. Families
#1/#2/#4/#6 (`lib/dataset2/experience_age_draft.py`), #8/#39/#44
(`lib/dataset2/prior_season_traits.py`), #7
(`lib/dataset2/prior_finish_traits.py` +
`lib/dataset2/prior_finish_analysis.py`), #9's sample-size portion
(`lib/dataset2/partial_season_traits.py`, minimum-opportunity floor
still deliberately pending), #10 (`lib/dataset2/depth_chart_traits.py`,
a tie-preserving design revised from the original scope after a real
2020/2025 data investigation — see §3f's update note and §6), and
#86-split/#88-split (`lib/dataset2/fragility_traits.py`, both
partial builds with explicitly-documented deferred portions) are
IMPLEMENTED** — see each family's entry in §6 for build detail and the
required real-data integration checkpoint (implementation correctness
and real-data validation are tracked as two separate,
not-yet-both-satisfied claims — see §6). This completes the entire
approved first implementation wave; every other family in this roadmap
remains proposal-only, not yet built. Responds to "FFRE
Dataset Trait Taxonomy — Reconciled Draft" (90
hypothesis families, 1658 trait entries, approved as the authoritative
hypothesis inventory). This document maps every one of the 90 families
to this repository's REAL, VERIFIED data inventory, assigns each to one
of five implementation tiers, and flags every conflict, ambiguity,
duplicate, and missing prerequisite found along the way. Per the
taxonomy's own instruction, no approved hypothesis is silently removed,
merged, reinterpreted, or deferred without being named explicitly below.

Every "available"/"not available" claim in this document was checked
directly against real files in this repository (see "Verified data
inventory" below) — not assumed, not carried over from memory, and in
several places **correcting** claims in the existing
`docs/LEAGUE_WINNER_TRAITS_SPEC.md`.

### Canonical family numbering — verified 2026-07 against the source
taxonomy directly

This roadmap's family numbers were re-checked directly against
`FFRE Dataset Trait Taxonomy — Reconciled Draft` (the original source
document, not this roadmap's own prior notes) after a chat message
referenced several opportunity/usage families by the wrong number. The
taxonomy document is the canonical source; this roadmap's numbers
**already matched it exactly** — the mismatch was in that one chat
message, not in this roadmap. Recorded here as a permanent reference so
it doesn't recur, per the standing rule: **when a family's number and
name conflict, the family NAME is authoritative until reconciled** —
never silently renumber a family to match a number that was used
incorrectly elsewhere.

Quick lookup for the families most referenced in the opportunity/usage
work (§6's next wave) — verified directly against the taxonomy's own
section headers:

| # | Name |
|---|---|
| 9 | Partial-season production |
| 14 | Return-role interpretation |
| 15 | Target-earning ability |
| 16 | Route participation |
| 17 | Air-yard profile |
| 18 | Receiving efficiency |
| 20 | Carry profile |
| 22 | Passing-game role for running backs |
| 86 | Volume fragility |

---

## 1. Relationship to the existing `docs/LEAGUE_WINNER_TRAITS_SPEC.md`

That document is NOT superseded — it remains authoritative for
methodology (leakage rule, missingness policy, era/position controls,
winner-rate/baseline/lift testing framework, the two-output split into
Predictive Traits vs. Historical Findings). This roadmap is
**additive**: it reconciles that spec's original "Bucket 1 / Bucket 2 /
Bucket 3" data-availability framework with the new taxonomy's
five-tier PRIORITY framework, which answer different questions:

- **Bucket 1/2/3** (existing spec) = "is this trait's data available
  right now, without new sourcing?" — a data-engineering axis.
- **Tier** (this roadmap, per the new taxonomy) = "how soon should this
  be worked on, and how much historical depth does it realistically
  have?" — a prioritization axis.

A trait can be Bucket 1 (available) AND Tier 2 (coverage-limited) at
the same time — e.g. `wopr` is sitting in already-fetched raw files
today (Bucket 1, once retained) but a downstream advanced-efficiency
metric like "missed tackles forced" likely only has reliable
historical depth from the NextGenStats era onward (Tier 2), even
though both would use the same acquisition mechanism.

**Two corrections to the existing spec's Bucket 2, found while
building this roadmap** (see "Verified data inventory" below):
1. Real age/birthdate and NFL draft capital (round/pick) are marked
   "not in current schema, unverified" in the existing spec's Bucket
   2. **They are actually already present** in
   `data/raw/nflverse/reference/players.csv` (fetched via
   `nflverse_source.fetch_players()`), just not yet joined into any
   trait-building population. This moves families #2 and #4 from
   "needs new sourcing" to "needs a pipeline wiring step" — a much
   lower acquisition burden than the existing spec implied.
2. `target_share`, `air_yards_share`, `wopr`, `racr`, and full
   passing/rushing/receiving EPA columns are already present in the
   raw per-season weekly stats files nflverse provides (confirmed
   directly against `data/raw/nflverse/annual/stats_player_week_2024.csv`'s
   real header) — richer than the existing spec's "targets/carries are
   used transiently then dropped" note implied. Retaining them is
   still real, moderate pipeline work (per the existing spec), but the
   ceiling of what's retainable is higher than previously documented.

---

## 2. Verified data inventory (checked directly, 2026-07)

| Source | What's actually in it | Historical coverage |
|---|---|---|
| `data/raw/nflverse/reference/players.csv` | `birth_date`, `height`, `weight`, `college_name`, `college_conference`, `draft_year`, `draft_round`, `draft_pick`, `draft_team`, `years_of_experience`, `rookie_season`, `position` | Full roster, not season-keyed (a player's row is current-as-of-fetch, not per-season — real limitation for trend features, see §5) |
| `data/raw/nflverse/annual/stats_player_week_{season}.csv` (raw, per season, gitignored) | Full passing/rushing/receiving box score, `target_share`, `air_yards_share`, `wopr`, `racr`, EPA for all three phases, first downs, distance-bucket columns (`rushing_10/12/20/40`, `receiving_10/16/20/40`, `passing_10/16/20/40` — **meaning unverified, likely play-length buckets, NOT confirmed to be red-zone-specific; do not assume without checking nflverse's own column glossary**) | 2006-2025, but only `fantasy_points_ppr` is currently RETAINED into `weekly_results_ppr_2006_2025.csv` — everything else is fetched, used transiently, then dropped (confirmed, matches existing spec) |
| `data/raw/nflverse/reference/games.csv` (schedules) | `game_id, season, game_type, week, gameday, weekday, home_team, away_team` — **confirmed, nothing else**. No venue, weather, Vegas line, or dome/turf data anywhere in this file. | 2006-2025 |
| `data/raw/nflverse/annual/depth_charts_{season}.csv` | `season, club_code, week, game_type, depth_team, position, gsis_id`, names | 2006-2024 on one schema; **2025 is a CONFIRMED, real schema break** (different vendor: `dt, team, player_name, pos_grp, pos_slot, pos_rank`, no `week`/`game_type`/`depth_team`/`position` at all) — already causes a fail-loud KeyError if read with the old schema (`nflverse_source.py`'s own docstring). **RESOLVED (see 3f, revised)**: a defensible field mapping exists and this project has already proven it once. |
| Master DB (`master_historical_db_with_lwi_2006_2025.csv`) | `fantasy_points_ppr`, `ppg_ppr`, `position_finish_ppr`, `games_played`, `overall_adp_model`, `positional_adp_model`, `team`, `position`, LWI score + all 6 decomposed components, `adp_status`, `verification_status` | 2006-2025 |
| SBV output (`stars_by_value_player_seasons.csv`) | `star_by_value_label`, `star_by_value_score`, status/provenance | 2006-2025, per-season |
| `data/processed/sbv_expected_production_lookup.parquet` | `expected_production` (E_P) keyed by `(prediction_season, position, draft_round)`, plus `sample_size`/`sbv_version` | Same coverage as SBV scoring |
| **nflverse `snap_counts` release** (GitHub `nflverse/nflverse-data`, confirmed live 2026-07 via the public releases API) | Per-player-week offensive/defensive/ST snap counts and snap share | **2012-2025**, confirmed by real asset-name inspection — NOT currently integrated into this pipeline (new fetch, but same established GitHub-release mechanism already used for players/schedules/depth_charts) |
| **nflverse `pbp_participation` release** (same catalog) | Play-by-play personnel/participation, the real source for route participation | **2016-2025**, confirmed by real asset-name inspection — NOT integrated; a materially shorter real history than snap counts |
| **nflverse `injuries` release** (same catalog) | Weekly injury-report designations (real injury type/status, not just games-missed) | **2009-2025**, confirmed by real asset-name inspection — NOT integrated |
| **nflverse `combine` release** (same catalog) | Combine drill results | Exists as a single file, not season-keyed per release tag; **real per-season depth NOT yet verified** (would need to open the file itself) |
| **nflverse `contracts` release** (same catalog) | A single "historical_contracts" file | Exists; **real per-season/per-player depth NOT yet verified** |
| **nflverse `ftn_charting` release** (same catalog) | Third-party charting, the likely source for man/zone coverage splits (family #19) | Exists; coverage years NOT yet verified — flagged, not assumed |
| College stats, recruiting rankings, coaching history, Vegas lines, weather | **CONFIRMED ABSENT.** No file, script, or fetch mechanism anywhere in this repository touches any of these, and no nflverse release covers them either. All genuinely require new, separate external sourcing. |

---

## 3. Conflicts, ambiguities, duplicates, and missing prerequisites found

**No approved hypothesis was removed, merged without disclosure, or
silently deferred.** Everything below is a finding to resolve via your
review, not a decision already made.

### 3a. Terminology collision risk (real, not yet a bug)
This project already heavily overloads "draft"/"ADP"/"acquisition
cost" for the FANTASY draft context (SBV's whole methodology is built
on fantasy acquisition cost). The taxonomy's Section B introduces REAL
NFL draft capital (round/pick a player was selected by an NFL team) as
a separate hypothesis family. The taxonomy itself keeps these
conceptually separate (Section B vs. Section O), but nothing in this
repo's naming conventions currently distinguishes them at the code
level. **ADOPTED (2026-07, approved by user)**: every real-NFL-draft
field built for family #4 (and anywhere else real draft capital
appears, e.g. #29's QB-experience context) uses an explicit
`nfl_draft_*` prefix — `nfl_draft_round`, `nfl_draft_pick`,
`nfl_draft_year`, `nfl_draft_team`. `overall_adp`/`positional_adp`/
`acquisition_cost_*` remain reserved exclusively for fantasy-market
cost. This is now a binding naming convention for Dataset 2
implementation, not just a recommendation.

### 3b. Historical-finish-rank features vs. the SBV target — checked, NOT a real conflict
Sections A and C use rank-based historical-finish language extensively
("top-10 positional season," "top-25 overall finish") as INPUT
features describing past seasons. Dataset 3's target is the separate,
settled, absolute-threshold SBV Star label
(`star_by_value_label`), not a percentile rank. These don't conflict —
the taxonomy is free to use rank-based descriptors as FEATURES
regardless of what the TARGET is defined as — but it's worth stating
explicitly once, here, given how much this project's documentation has
emphasized never blurring historical-label vs. target-definition
concepts. No action needed beyond this note.

### 3c. Section C substantially overlaps the existing spec's Bucket 1
Family #7 (previous-season finish) and family #8 (multi-year trend)
are, at the variable level, mostly ALREADY-DEFINED fields
(`fantasy_points_ppr`, `ppg_ppr`, `position_finish_ppr`, `games_played`,
`lwi_score` and its 6 components) from the existing spec's Bucket 1,
plus a smaller set of genuinely new derived variants (rolling
trend/slope across 2-3 years, career floor/ceiling). Per the
general-representation rule, these consolidate into: the existing
Bucket-1 fields (reused, not re-acquired) + a small number of new
trend/slope computations built ON TOP of them. No new sourcing
required for either family.

### 3d. `players.csv` is not season-keyed — a real prerequisite gap
`players.csv` gives a player's CURRENT height/weight/college/draft
info, not a snapshot as of each season. For most of these fields
(birthdate, draft round, college) this is fine — they don't change
over a career. But it means this table alone cannot support
season-varying fields like `years_of_experience` "as of season N"
without deriving it from `rookie_season` + `season` arithmetic
(straightforward) rather than trusting the table's own
`years_of_experience` column (which reflects "as of now," not "as of
that historical season"). Flagging this so family #1's exact-years-of-
experience variant is built correctly (derived, not read directly).

### 3e. Snap counts / route participation — RESOLVED as fetchable, real coverage years confirmed
**Investigated directly (2026-07)** via a live, read-only query
against GitHub's public releases API
(`api.github.com/repos/nflverse/nflverse-data`, confirmed reachable
from this sandbox for metadata) — this is the same catalog
`nflverse_source.py` already points at for players/schedules/depth
charts, just different release tags within it, not a new source or
new fetch mechanism.

Confirmed real, by asset-name inspection:
- **`snap_counts`**: 2012-2025. Per-player-week offense/defense/ST
  snap counts and snap share — resolves family #16 (route
  participation's snap-share half) and the snap-share sub-signal of
  family #86.
- **`pbp_participation`**: 2016-2025. Play-by-play personnel data —
  the real source for ROUTE participation specifically (distinct from
  snap count; a player can be on the field without running a route).
  Materially shorter history than snap counts — a real, disclosed
  coverage limit, not a gap.
- **`injuries`**: 2009-2025. Weekly injury-report designations (real
  injury TYPE and status, not just games-missed) — this is new
  leverage for family #40-43, previously Tier 5 for lack of any
  injury-detail source, and unblocks the Dataset 2B injury-vs-
  performance bust split discussed in §3j below.
- **`combine`** and **`contracts`**: confirmed to exist as single,
  non-season-keyed files. Real per-record depth (which seasons/players
  they actually cover) is **NOT yet verified** — would require opening
  the files themselves, a small next step, not assumed here either
  way.
- **`ftn_charting`**: confirmed to exist; likely the real source for
  family #19's man/zone coverage splits. Coverage years **NOT yet
  verified**.

**This changes several families' acquisition-burden assessment** —
"new external sourcing, doesn't exist" becomes "new release tag on an
already-established fetch mechanism, needs schema/coverage
verification then wiring." Families #13, #15 (partially), #16, #22,
#86 (route/snap sub-signals), and #40-43 (injury detail) move to a
materially lower burden below. `combine`/`contracts`/`ftn_charting`
remain flagged unverified rather than assumed usable — the taxonomy's
coverage-aware rule requires disclosing WHY coverage is uncertain, not
just that it is.

### 3f. Depth-chart 2025 schema break — RESOLVED, a defensible mapping exists and this project has already proven it once
**Investigated directly (2026-07), per your instruction not to guess.**
Loaded the real `depth_charts_2025.csv` (554,216 rows) and inspected
real `dt`/`team`/`pos_grp`/`pos_id`/`pos_rank`/`pos_slot` values.
Findings:
- Every team uses a single, unified offensive personnel group
  (`pos_grp == '3WR 1TE'` for all 32 teams) — there's no ambiguity
  about which personnel group corresponds to "the offense."
- `pos_rank` gives a clean starter-then-backup ordering within each
  position (`pos_abb`) — rank 1 is the starter for QB/RB/TE, and WR's
  three starter slots combine sensibly via `pos_slot`.
- `dt` is a rolling, roughly-daily scrape snapshot (not week-numbered
  like 2006-2024), so "Week 1 depth chart" has to be resolved as "the
  latest snapshot on or before that team's real Week-1 kickoff date,"
  not read off a `week` column that doesn't exist in this schema.

**This exact mapping has already been built and empirically validated
once**, in `lib/stars_by_value/acquisition_cost.py`'s
`apply_rookie_qb_depth_chart_correction()` — its own docstring records
that "every 2025 rookie QB already checked resolves identically to the
earlier shared-date approximation, confirming this is not a live
sensitivity." That function currently only fires for a narrow
QB-rookie-starter binary check, but the underlying mapping (team +
`pos_abb` + `pos_rank` + the real per-team kickoff date from
`nflverse_source.fetch_schedules()`) generalizes directly to any
position and any depth-chart-based trait.

**Recommendation**: Dataset 2's depth-chart traits (family #10, #14,
Category T) should REUSE/generalize this proven mapping rather than
re-deriving new 2025-schema-parsing logic from scratch. This resolves
the schema break with real evidence rather than a guess, and upgrades
family #10 from "moderate burden, 2025 needs a real decision" to "low
burden, decision already made and validated once — needs generalizing
beyond the QB-only case." Families #10/#12/#14/Category T's tier
entries below are updated accordingly.

**UPDATE (2026-07, at actual implementation time)**: the snapshot-
selection mapping above (team + real Week-1 kickoff date → the right
`dt`) held up exactly as described and IS what family #10 uses. But a
SEPARATE, deeper investigation at build time — checking real tie rates
across all 32 teams' 2020 depth charts, not just one example team —
found the "combine sensibly via `pos_slot`" characterization above was
incomplete: the pre-2025 schema's `depth_team` column does NOT give a
clean ordinal for every position (WR structurally ties ~3 players at
rank 1; RB/TE tie less often but genuinely, in real committee
situations), while 2025's `pos_rank` is a strict ordinal that never
ties, even in those same committee cases. This is a real,
previously-undiscovered wrinkle beyond the snapshot-timing question
this section originally resolved — see family #10's entry in §6 for
the full finding and the tie-preserving design it produced. Not
correcting the text above (per CLAUDE.md's decision-history
preservation rule) — recording the refinement here instead.

### 3g. College data (Section B.5 and all its sub-buckets) is the single largest acquisition-burden cluster
By raw bullet count, family #5 plus its four sub-buckets (college
metrics, passing-game role for RBs, college accolades, college
coaching, family background) is the largest block in the entire
taxonomy — several hundred trait entries. Zero college-stats
infrastructure exists in this repo today. This is a real, large,
separate sourcing project, not a small extension of anything that
exists. Flagged here, not silently shrunk — every sub-bucket is
preserved in Tier 5 below.

### 3h. No duplicate/redundant hypothesis families found beyond what the taxonomy already self-flags
The taxonomy's own document already marks several exact redundancies
inline (e.g. family 19 vs. family 18's "Efficiency versus man/zone"
entries; family 57's "[later/questionable]" duplicates of family 56).
No ADDITIONAL cross-family duplication was found beyond consolidations
already required by the general-representation and
threshold-sensitivity rules (documented per-family in §5 below, not
here, so each is traceable to its specific family).

### 3i. Section Z (families 86-89) is Dataset 2B's own core material and deserves explicit sourcing/coverage treatment, not just "the negative side of 2A"
Families 86-89 (volume fragility, efficiency regression risk, workload/
durability risk, environment deterioration) are each internally a
COMPOSITE of signals already assessed elsewhere in this roadmap (e.g.
family 88's touch-count portion depends on the same weekly-column
retention as family #20; its injury portion depends on the same unbuilt
injury database as family #40). Rather than re-deriving new
acquisition logic for these four families, each is split below across
the tier its constituent signals already belong to, with the split
stated explicitly per family so no sub-signal is silently dropped.

### 3j. Dataset 2B outcome design — bust-definition candidates (NO cutoff selected)

Per your instruction, this inspects the real SBV architecture and the
real historical distribution of acquisition-cost-relative outcomes,
proposes several mathematically compatible bust definitions, and shows
real counts/composition for each. **Nothing here is a final decision —
every number below is descriptive, for your review.**

**Primary concept (as instructed): acquisition-cost-relative
underperformance.** SBV already computes
`star_by_value_score = P - SBV_LAMBDA * E_P` (`SBV_LAMBDA = 0.35`) and
a position-specific `star_by_value_threshold` (the Star cutoff). The
natural "how far below the Star bar" measure is
`score_minus_threshold = star_by_value_score - star_by_value_threshold`
— negative means below the bar, and this is already denominated in the
same acquisition-cost-relative units the Star label itself uses, so it
requires no new modeling.

Real distribution, `data/exports/stars_by_value_player_seasons.csv`,
1347 scored rows: mean −80.9, std 43.3. (For reference, only 76/1347 ≈
5.6% clear the Star bar — the distribution is bottom-heavy by
construction, most player-seasons sit below the threshold.)

*Percentile-based candidates* (bottom N% of `score_minus_threshold`
among all scored rows):

| Cutoff | n | % of scored population |
|---|---|---|
| Bottom 5% | 68 | 5.0% |
| Bottom 10% | 135 | 10.0% |
| Bottom 15% | 202 | 15.0% |
| Bottom 20% | 270 | 20.0% |
| Bottom 25% | 337 | 25.0% |

Bottom 10% composition (n=135): WR 75, RB 49, QB 7, TE 4 — 100%
`adp_matched_clean` provenance (i.e., every current candidate-bust row
in this window is a player who cost a real, known fantasy-draft price
and then fell into the bottom decile relative to that price's Star
bar — not a minimal-market-cost/undrafted row). Bottom 20% (n=270):
WR 135, RB 86, QB 26, TE 23, same 100%-real-ADP provenance.

*Fixed-point-gap candidates* (`score_minus_threshold <= -X`, a flat
distance instead of a percentile):

| Gap | n | % of scored population |
|---|---|---|
| ≥30 pts below threshold | 1174 | 87.2% |
| ≥50 pts below threshold | 1069 | 79.4% |
| ≥75 pts below threshold | 843 | 62.6% |

**This candidate family doesn't work at any of these gap sizes** —
because the whole distribution's mean already sits ~81 points below
threshold (most player-seasons simply don't clear the Star bar), a
flat point-gap captures 60-90% of the entire scored population, not a
meaningfully distinct "bust" tail. A fixed-gap definition could still
be made to work, but only at a much larger, less intuitive gap than
30-75 points — flagged as a real finding against this candidate
family, not silently dropped from consideration.

**Secondary diagnostic (as instructed, kept distinct from the
primary): raw underperformance vs. modeled E_P, unweighted by
`SBV_LAMBDA` and not expressed relative to the position threshold.**
Computed directly by running the existing, already-tested
`lib/stars_by_value/production.py::compute_production()` against the
real, ADP-matched master-DB population (season/position/games_played/
`fantasy_points_ppr`/`ppg_ppr`/`position_finish_ppr`), then joining
`data/processed/sbv_expected_production_lookup.parquet` on
`(season, position, draft_round)` — no new modeling code, just
invoking the existing pipeline's own functions on real data, the same
way the primary distribution above was computed.

`raw_diag = P - E_P`, 2657 matched rows with a valid E_P lookup: mean
−85.8, std 54.4, median −90.0. (Median below zero for the same
structural reason as the primary distribution — E_P represents a
central tendency, and outcome distributions are right-skewed by a
smaller number of standout seasons, so a "typical" season sits below
its round's expectation even before any bust framing is applied.)

**Real overlap check, same joined population (n=1293), both measures'
bottom-20% cutoffs applied**: primary bottom-20% n=259, secondary
bottom-20% n=259, **overlap = 146 rows (56.4%)**. This confirms your
instruction that these are genuinely distinct outcomes, not
restatements of each other — 43.6% of either set is NOT flagged by the
other measure.

- **Primary-only** (acquisition-cost-relative bust, NOT a raw-E_P
  underperformer): skews RB/WR (RB 59, WR 52, TE 2, QB 0), median ADP
  71.6. Real examples: Chris Johnson 2011, Devonta Freeman 2017, Najee
  Harris 2022, Le'Veon Bell 2019, Joe Mixon 2020 — a recognizable
  pattern of early/mid-round RBs who fell hard relative to what their
  specific draft cost demanded, even though their raw production
  wasn't necessarily far below a generic positional expectation.
- **Secondary-only** (raw underperformer vs. modeled E_P, NOT an
  acquisition-cost-relative bust): skews QB/TE (QB 59, TE 34, WR 19,
  RB 1), median ADP 60.3. Real examples: Julio Jones 2017, Travis
  Kelce 2023, Josh Allen 2025, Peyton Manning 2014, Mike Vick 2011 — a
  different pattern: established, often elite-track-record players who
  underperformed their own modeled expectation in a given year, but
  whose absolute output often still cleared the position-specific
  bust bar their draft cost implied.

This is a real, useful distinction for Dataset 2B: the PRIMARY measure
better matches "acquisition cost validated a real risk," while the
SECONDARY measure better matches "a well-established player had a
down year relative to their own track record" — plausibly different
preseason predictors (workload/depth-chart risk for the former,
age/injury-recovery/scheme-change signals for the latter), which is
exactly the distinction your instruction anticipated.

**Injury-caused vs. performance-caused busts**: not yet computable
with real numbers — this pipeline has no injury-type data wired in
today. It is now a real, buildable next step rather than a dead end:
§3e above confirms nflverse's `injuries` release (weekly injury-report
designations, 2009-2025) exists and is fetchable via the established
mechanism. Once wired, the natural split is games-missed-with-a-real-
injury-designation vs. bust-with-full-availability (`games_played`
near the season max) — but this requires the new `injuries` source to
be integrated first, which has not happened. Flagged as a dependency,
not silently assumed solvable today.

**Per your follow-up instruction, bottom-10%/bottom-20% is NOT selected
here.** Below are five real, computed definition families —
global percentile, season-specific percentile, position×ADP-specific
percentile, practical/absolute shortfall, and a hybrid — compared
directly on the same population so you can see how each changes the
count and TYPE of players flagged, before any cutoff is chosen.

**F. Season-specific percentile** (bottom 20% computed WITHIN each
season separately, instead of pooled across 2006-2025 — tests whether
pooling silently favors/disfavors any era):
- n flagged: 275 (vs. 270 for the pooled/global version)
- **92.6% overlap with the global-pooled bottom-20% set** — the two
  are nearly interchangeable in this data. Real finding: SBV's
  threshold is already fixed per position (not season-varying — see
  the position-threshold table below), so pooling across seasons
  doesn't meaningfully distort which players land in the tail. Era
  stratification matters less here than it might for a trait whose
  own distribution shifts across eras.

**G. Position × ADP-range-specific percentile** (bottom 20% computed
WITHIN each position × ADP-bucket cell — buckets: R1-2/R3-5/R6-10/R11+,
n=1293 ADP-matched rows):
- n flagged: 264
- Composition: WR 104, RB 74, TE 44, QB 42 — by ADP bucket: R6-10 (83),
  R3-5 (79), R1-2 (66), R11+ (36)
- **Only 82.2% overlap with the global-pooled bottom-20%** — a real,
  meaningful difference. Pooling across all positions/ADP ranges
  together under-represents QB and TE in the flagged set (26 QB / 23 TE
  under the global version vs. 42 QB / 44 TE here) because QB/TE have
  fewer drafted roster slots and a different score distribution shape
  than RB/WR — position/ADP-conditioning corrects for that, which is
  exactly the concern your position/ADP-stratification instruction was
  aimed at.

**H. Practical/absolute shortfall** (shortfall expressed as a
percentage of the player's OWN position threshold —
`-score_minus_threshold / star_by_value_threshold * 100` — rather than
a flat point gap, since position thresholds themselves differ in
magnitude: QB 176.5, RB 188.0, TE 134.0, WR 171.0):

| Floor | n | % of scored population |
|---|---|---|
| ≥20% below own threshold | 1160 | 86.1% |
| ≥30% below own threshold | 1063 | 78.9% |
| ≥40% below own threshold | 923 | 68.5% |
| ≥50% below own threshold | 739 | 54.9% |

**This alone has the same problem as the flat-point-gap candidate,
for the same underlying reason**: the median player-season already
sits 44-58% below its own position's threshold (mean 42-53% by
position), so even a 50%-below-threshold floor still captures over
half the population. A position-normalized absolute floor is more
defensible in principle than a flat point gap (it accounts for QB/RB
thresholds being larger in magnitude than TE's), but it still isn't a
usable STANDALONE bust definition in this data — it needs to be paired
with a relative-standing filter to produce a meaningfully distinct
tail. That pairing is exactly definition I below.

**I. Hybrid** (position×ADP-specific bottom-20%, definition G, AND a
minimum absolute-shortfall floor):

| Absolute floor added on top of G | n |
|---|---|
| ≥30-60% (no effect) | 264 (same as G alone) |
| ≥65% | 236 |
| ≥70% | 192 |

**Real finding**: in this data, position/ADP-conditioned relative
standing (G) and absolute shortfall are already highly correlated —
every row in G's bottom-20% already clears at least a 61.5% shortfall,
so an absolute floor only starts to matter above ~65%. At a 70% floor,
the hybrid drops 72 of G's 264 rows (27%) — these are the "relatively
bad within their position/ADP peer group, but not catastrophically bad
in absolute terms" borderline cases. Whether that 27% should count as
busts is a real, substantive question for your review, not something
this document resolves.

**Summary — five candidate bust-definition families compared, no
cutoff selected**:

| Definition | n (bottom-20%-equivalent) | What it corrects for | Real weakness found |
|---|---|---|---|
| A. Global percentile | 270 | Nothing extra — simplest baseline | Pools across position/ADP/era, may misrepresent QB/TE |
| B. Fixed point gap | 843-1174 (30/50/75 pt) | Nothing — not percentile-based | Poorly calibrated at intuitive gaps (60-87% of population) |
| C. Raw P−E_P (secondary diagnostic) | 259 (of 1293) | A different question (vs. own track record, not vs. acquisition cost) | Not identical to A by design (56.4% overlap) — a distinct diagnostic, not a bust-definition replacement |
| F. Season-specific percentile | 275 | Era pooling | Minimal difference from A in this data (92.6% overlap) |
| G. Position × ADP percentile | 264 | Position/ADP pooling | Meaningfully different from A (82.2% overlap) — best-corrected relative-standing candidate so far |
| H. Practical/absolute shortfall (%-of-threshold) | 739-1160 (20-50% floor) | Flat-point-gap's position-scale blindness | Same core problem as B — median player is already far below threshold |
| I. Hybrid (G + absolute floor) | 192-264 (65-70% floor) | Both position/ADP pooling AND requires a real absolute shortfall | Only diverges from G at floors above ~65% — most explicit and most defensible combination tested, but narrows the definition further |

Injury-caused/performance-caused separation remains a documented open
dependency on integrating the newly-confirmed `injuries` release, not
a decision made here.

**DECISION (2026-07, approved) — Dataset 2B bust outcome fields.**
Not a single label. Three separate, stored fields, so the primary
definition can be reconsidered later without reconstructing anything:
- **`bust_label_primary`** = definition **G** (position × ADP-range
  conditioned percentile). This is the primary Dataset 2B outcome used
  for Star-adjacent bust research.
- **`bust_label_strict_hybrid`** = definition **I** (G plus an absolute
  shortfall floor) — stored as a STRICTER SENSITIVITY ANALYSIS, run
  alongside the primary, never used to remove a player from the
  primary label. A player can be `bust_label_primary == 1` and
  `bust_label_strict_hybrid == 0` at the same time — that's the
  intended, informative case (a borderline bust under the strict
  reading), not an error to reconcile.
- **`underperformance_diagnostic`** = definition **C** (raw P vs.
  modeled E_P) — stored as a SECONDARY DIAGNOSTIC, never as the primary
  bust label, per the roadmap's earlier distinct-outcome finding
  (56.4% overlap with G at the 20% level — a real, different signal,
  not a restatement).

Exact numeric percentile cutoffs (definition G's within-cell
percentile, definition I's absolute-floor percentage) are implementation
details to fix when Dataset 2B's outcome-labeling module is actually
built, not re-decided here — the 20%-equivalent examples shown above
(G n=264, I n=192-264 depending on floor) are illustrative, not final.

---

## 4. Global rules — how they're applied in this roadmap

- **Threshold-sensitivity rule**: every family with a list of
  rank/count cutoffs (e.g. family #3's "never had a top-5/10/15/25/30
  positional season") is implemented as ONE continuous or ordinal
  variable (e.g. "best positional finish rank ever achieved," or
  "seasons since first top-N finish" as a parametrized sweep), tested
  across the listed thresholds, not as N independent columns. Flagged
  explicitly per family below where this applies.
- **General-representation rule**: consolidations are named per family
  in §5, not silently applied.
- **Coverage-aware rule**: every Tier 2/5 family's assignment below
  states WHY its coverage is limited, not just that it is.
- **Bidirectional, player-relative, distinct-outcome (2A vs. 2B),
  shared-trait/separate-analysis rules**: apply uniformly to every
  family in every tier — restated per-family only where a family is
  definitionally one-directional (e.g. "vacated opportunity" is
  structurally a positive-only signal for the inheriting player) or
  where 2A/2B applicability is asymmetric.

---

## 4.5. Research Priority hierarchy (S/A/B) — a SECOND, distinct ranking from Implementation Tier

Per your instruction, this roadmap keeps two genuinely separate
rankings. **Implementation Tier (§5)** answers "how soon CAN this be
built, given data availability and acquisition burden?" **Research
Priority (below)** answers "how much does this MATTER, if built?" An
easy-to-build trait never automatically outranks a harder trait with
substantially greater likely predictive value — the two axes are
reported side by side per family in §6, not collapsed into one score.

**S tier** (highest): driven by (1) potential predictive value — is
there a plausible, specific football mechanism connecting this trait
to becoming a Star or a bust, not just a correlation-shaped hope — and
(2) acquisition burden, considered here only as a tiebreaker between
two S-caliber hypotheses, never as the primary driver (that would
collapse this ranking back into Implementation Tier).

**A tier**: driven by (1) usefulness for Dataset 2A specifically and
(2) usefulness for Dataset 2B specifically. A trait that plausibly
helps explain becoming a Star OR predicting a bust — including a
trait that's one-directional by the taxonomy's own bidirectional rule
— lands here if it doesn't already clear the S-tier bar on mechanism
strength.

**B tier**: driven by (1) historical coverage depth, (2) distinctness
from traits already in the roadmap (a trait that's mostly redundant
with an S/A-tier trait, per the general-representation rule, ranks
lower even if individually plausible), and (3) position applicability
(a trait relevant to one position only starts with a structurally
smaller usable sample than one relevant across all four skill
positions).

**Leakage risk is explicitly NOT part of this ranking.** Per your
instruction, it is a methodological GUARDRAIL, not a measure of
football importance: a high-leakage-risk hypothesis (e.g. family #61,
beat-reporter consensus, or family #77's ambiguity discount) can be
genuinely S-tier on football mechanism while still requiring that its
eventual results be flagged as non-credible unless every input can be
tied to timestamped information genuinely available before that
season's fantasy-draft cutoff. Both facts are reported per family in
§6 — high research priority and a leakage guardrail are not in
tension, they answer different questions.

**Evidence status — approved 2026-07, not yet actionable.** S/A/B is a
**pre-analysis expectation**, not an empirical conclusion, and stays on
the record unchanged after testing (never silently rewritten to match
whatever the result turned out to be — this project doesn't overwrite
prior judgment calls, it adds a new field alongside them, matching the
same preserve-don't-overwrite convention CLAUDE.md already applies to
CHANGELOG's "Rejected" section and the LWI Model Card's falsification
history). Once a family has actually been analyzed, a SEPARATE
`evidence_status` field is added — `Supported` / `Mixed` / `Unsupported`
/ `Inconclusive` — so the original theory-driven S/A/B rating and the
eventual empirical finding are never confused with each other. Nothing
has been analyzed yet, so no family below carries an `evidence_status`
value yet; this is a standing commitment for when results exist, not a
retroactive relabeling of the S/A/B ratings already assigned in §6.

## 4.6. Minimum result outputs — required for every analyzed trait, once analysis begins

Per your instruction, every trait's eventual analysis (not required
yet, since no analysis has been run — this states the standard for
when it is) must report at least:

- **Sample size**
- **Star rate** (share of the analyzed population that is
  `star_by_value_label == 1`)
- **Comparable baseline Star rate** (the Star rate for a matched
  comparison population, not the raw unconditional rate — see
  stratification below)
- **Bust rate** (per whichever Dataset 2B definition is eventually
  approved from §3j, once selected)
- **ADP-range splits**
- **Confidence in the finding**

Comparisons must control or stratify by AT LEAST: **position**, **ADP
range**, and **era** — this is what stops a trait from being credited
merely because it correlates with cheaper players, expensive players,
a specific position, or a specific historical period, rather than with
becoming a Star or a bust. This extends (does not replace) the
existing `docs/LEAGUE_WINNER_TRAITS_SPEC.md`'s own era-boundary
convention (pre-2011 / 2011-2020 / 2021+ as the initial default split).

**"Confidence" must distinguish explicitly between these five, not be
reported as one undifferentiated number**:
1. Small-sample uncertainty (few observations, wide plausible range)
2. Weak effect size (large sample, but the lift over baseline is small)
3. Inconsistent effects across eras or positions (real in one slice,
   absent or reversed in another)
4. High missingness (the trait's own input data has real coverage
   gaps, independent of the outcome sample size)
5. High leakage risk (per §4.5's guardrail — a real effect that can't
   be trusted as preseason-actionable without timestamp verification)

---

## 5. The five-tier roadmap

Every one of the 90 numbered families appears exactly once below,
tagged with its taxonomy letter/number. "2A/2B" marks which Dataset 2
output(s) the family is expected to feed (most families feed both,
since a trait can simultaneously be a Star predictor and a bust-risk
predictor in the opposite direction — the bidirectional rule already
requires testing both).

### TIER 1 — Core historical traits
*Full or near-full 2006-2025 coverage achievable now or with
low/moderate pipeline work (no new external sourcing). Highest
priority.*

| # | Family | Source / burden | Coverage | Leakage risk | 2A/2B |
|---|---|---|---|---|---|
| 1 | NFL experience curve | `players.csv.rookie_season` + season arithmetic (derive years-of-experience per season, per §3d) — low burden | Full | None (fixed at season start) | Both |
| 2 | Age curve | `players.csv.birth_date` — low burden (join + Week-1-date arithmetic) | Full | None | Both |
| 4 | NFL draft capital | `players.csv.draft_year/round/pick` — low burden (join) | Full | None | Both |
| 6 | Body-size profile (height/weight/BMI only — renamed from "Athletic profile," see §6; combine drills split out below) | `players.csv.height/weight` — low burden; BMI derived | Full | None | Both |
| 7 | Previous-season finish | Already available (existing spec Bucket 1) | Full (89.7% have a valid prior season per existing spec; rookies need the separate path already defined there) | None (strictly lagged) | Both |
| 8 | Multi-year production trend | Built from existing per-season fields (fantasy_points_ppr, ppg_ppr) — low burden | Full for 2+ year trends; 3-year trend reduces further at career starts | None | Both |
| 9 | Partial-season production | `weekly_results_ppr_2006_2025.csv` (per-week PPR points already retained) — low/moderate burden for splits (first-half/second-half, final-N-games) | Full | None (all pre-dates the FOLLOWING season being predicted) | Both |
| 39 | Prior-season availability (durability) | `games_played` already available | Full | None | Both |
| 44 | Player changed teams | `team` column, season N vs. N-1, already available | Full | None | Both |
| 49 | Absolute ADP | `overall_adp_model`/`positional_adp_model` already available | Full | None (set pre-Week-1 by construction) | Both |
| 10 | Projected depth-chart position | `depth_charts_{season}.csv` — **low burden (revised)**: 2025-schema mapping already proven once in `acquisition_cost.py`, needs generalizing beyond the QB-only case, not re-deriving (§3f) | Full 2006-2025, including 2025 via the proven mapping | Low, if truly a preseason (not in-season) snapshot — verify snapshot timing | Both |
| 86 (split, part) | Volume fragility — the depth-chart/competition-driven sub-signals only ("committee uncertainty," "high competition," "coaching uncertainty," "QB uncertainty") | Built from #4/#10/#12's already-Tier-1/2 fields once those exist | Same as #10/#12 | Same as #10/#12 | 2B primarily (per the distinct-outcome rule, tested against bust risk, not just "not 2A") |
| 88 (split, part) | Workload and durability risk — the age/frame-only sub-signals ("age plus high workload" using age, "small frame plus workhorse role" using height/weight) | `players.csv` fields already available (Tier 1) | Full | None | 2B primarily |

**Note on family #10**: upgraded to full-coverage Tier 1 (was "2006-2024
clean, 2025 needs a decision" in the prior draft) now that the 2025
schema mapping is confirmed defensible and already validated once in
`acquisition_cost.py` — see §3f.

**Note on the #86/#88 splits**: only the sub-signals that reduce
entirely to already-Tier-1 fields are listed here. Their remaining
sub-signals (route/snap-dependent for #86; touch-count and
injury-dependent for #88) appear in Tiers 2 and 5 respectively, below
— see §3i.

---

### TIER 2 — Coverage-limited historical traits
*Real, well-defined, computable, but with genuinely limited historical
depth or a verified partial pipeline gap. Second priority — build once
Tier 1 is validated.*

| # | Family | Source / burden | Coverage | Leakage risk | 2A/2B |
|---|---|---|---|---|---|
| 15 | Target-earning ability | Weekly file has `target_share`/`targets` already fetched, not retained — moderate pipeline work; man/zone-coverage sub-bullets depend on the unverified `ftn_charting` release, not on route participation | Retainable fields: full 2006-2025 once wired; man/zone splits: unverified | None if strictly lagged | Both |
| 16 | Route participation | **Revised (§3e)**: nflverse `pbp_participation` (route data) and `snap_counts` (snap share) confirmed fetchable, same mechanism as players/schedules/depth_charts — moderate burden (new release tags to wire in, not a nonexistent source) | `pbp_participation` 2016-2025; `snap_counts` 2012-2025 — real, disclosed shorter history than the 2006-2025 master DB | None if lagged | Both |
| 17 | Air-yard profile | `receiving_air_yards`/`air_yards_share`/`racr`/`wopr` already fetched, not retained — moderate burden | Full 2006-2025 once wired (these are NOT NGS-only metrics in nflverse's box-score release, per the verified header) | None if lagged | Both |
| 18 | Receiving efficiency | Core fields (`catch_rate`, `yards_per_target`, `yac_per_reception`) derivable from already-fetched columns once retained; man/zone-specific efficiency depends on #19/coverage-charting data (separate, more limited source) | Core: full once wired; coverage-specific: limited | None if lagged | Both |
| 20 | Carry profile | `carries`, yardage, TD columns already fetched, not retained — moderate burden; red-zone/goal-line-specific carry shares need verification of what the `*_10`/`*_20` distance-bucket columns actually represent (see inventory note) | Core: full once wired; red-zone-specific: unverified | None if lagged | Both |
| 21 | Rushing efficiency | Core (yards/carry, EPA) as above; advanced metrics (missed tackles forced, yards after contact, success rate, stuff rate) likely need NextGenStats-era data with materially shorter real history | Core: full once wired; advanced: likely 2016+ only, unverified exact start year | None if lagged | Both |
| 22 | Passing-game role for RBs | Subset of #15/#16 applied to RB position — same prerequisites, same revised burden | Same as #15/#16 | None if lagged | Both |
| 23 | Red-zone role | Depends on verifying the distance-bucket columns noted above, or a genuinely separate red-zone-specific data cut | Unverified | None if lagged | Both |
| 24 | Touchdown regression | Core TD totals available now (already retained via fantasy points construction indirectly, though raw `*_tds` columns need explicit retention); "touchdowns above expectation" needs an expected-TD model this project doesn't have yet (a real, separate build, not just a sourcing gap) | TD totals: full; expectation model: not built | None if lagged | Both |
| 50 | ADP movement | Cross-season ADP comparison already available (Tier-1-equivalent); WITHIN-offseason movement (e.g. "major late-camp rise") needs multiple ADP snapshots per season, which this project does not currently retain per-snapshot | Cross-season: full; intra-offseason: none currently | None if lagged | Both |
| 51 | ADP disagreement | This project already has real historical multi-source ADP data (FFC/FFToday/MFL) per `docs/ADP_SOURCE_MATRIX.md`'s extensive record, but coverage differs by source and season (not uniform 2006-2025) — genuinely coverage-limited, not a new-sourcing question | Real but uneven across sources/eras — needs the exact per-source coverage table before use | None if all sources are genuinely preseason snapshots (verify per source, per existing spec's own rule) | Both |
| 52 | Value relative to projections | Depends on having independent PROJECTIONS (not just ADP) as a historical record — unverified whether this project has ever retained third-party season projections historically, likely a real, separate gap | Unverified, likely limited/absent | None if lagged | Both |
| 86 (split, part) | Volume fragility — the route/snap-share sub-signals ("low route participation," "low snap share," "low first-read share") | Same revised source as #16 (§3e) — moderate burden, not unresolved | Same as #16: `pbp_participation` 2016-2025, `snap_counts` 2012-2025 | None if lagged | 2B primarily |
| 87 | Efficiency regression risk | Derivable from the same already-fetched-but-not-retained weekly columns as #18/#21/#24 (TD rate, YPC, YPT, catch rate, EPA/success rate) | Full once wired | None if lagged | 2B primarily |
| 88 (split, part) | Workload and durability risk — the touch-count sub-signals ("prior 350+ touch season," "multiple 300+ touch seasons," "heavy playoff workload") | Derivable from the same already-fetched-but-not-retained carries/targets columns as #20 | Full once wired | None if lagged | 2B primarily |

---

### TIER 3 — Low-priority exploratory traits
*Real and buildable, but either explicitly taxonomy-flagged low
priority, a threshold/interaction refinement of a Tier 1/2 core
variable that should wait for the core variable to be validated first,
or a re-combination (Category T, much of Category Y) that depends on
several not-yet-validated base families.*

| # | Family | Why Tier 3 |
|---|---|---|
| 3 | Breakout timing | Threshold-sensitivity rule: this is a dense parameterization of family #7/#8's core variables (best-finish-rank-ever, years-since-best-season) across many thresholds — build as ONE swept variable once #7/#8 are validated, not before |
| 11 | Vacated opportunity | Real and valuable, but depends on #15/#20's target/carry-share fields being wired in first (built on top of them) |
| 12 | Competition quality | Depends on depth-chart (#10) and draft-capital (#4) fields; a second-order combination, build after both are validated |
| 13 | Role versatility | Same revised source as #16 (§3e), but combinatorial on top of it — still waits for #16 to be built and validated first, now a real (not unresolved) dependency |
| 14 | Return-role interpretation | Niche, small population; depends on special-teams data not yet verified as retained |
| 45 | Teammate departures | Real, depends on #11 (vacated opportunity) being built first — a named-player refinement of the same underlying signal |
| 46 | Teammate additions | Same as #45, opposite direction |
| 68 | Opportunity concentration | Team-level aggregation on top of #15/#20 — build after those are validated |
| 69 | Team stability | Team-level aggregation on top of #10/#44 |
| 70 | Teammate fragility | Depends on injury-history data (Tier 5, §3g-adjacent) for its strongest form; a weaker version is buildable from #39 alone now, but the family as specified leans on unbuilt injury infrastructure |
| 62 | Role uncertainty | Meta-variable built FROM the variance/dispersion of #10-#13; needs those first |
| 63 | Projection dispersion | Depends on #52's unverified projections-history gap |
| 64–67 | Position-specific hypotheses (QB/RB/WR/TE) | Explicitly re-combinations of already-listed Category A–L variables per position — the taxonomy's own framing ("beyond general traits") means these are refinements to test AFTER the general traits, not instead of them |
| 78–85 | Interaction hypotheses (Category Y) | The taxonomy's own header states individual traits "may be weak alone but powerful in combination" — interactions are only meaningful once the base variables they combine have been tested individually first |
| 89 | Environment deterioration | A meta-combination of QB/O-line/coordinator downgrade (#29-32, #37, #34 — mostly Tier 5), team scoring decline (#25, Tier 5), tougher schedule (#54, Tier 5), reduced pace/pass volume (#26/#27, Tier 2/5 split), reduced red-zone role (#23, Tier 2), contract uncertainty (#47, Tier 5), and role demotion (#10, Tier 1) — build only after its constituent parts exist, per the same logic as #62/#63/#77 |
| 6 (split, part) | Athletic profile (true combine-drill sub-signals: 40-yard, vertical, etc. — this is the only part of family #6 that earns the "athletic" label, per §6's renaming decision) | **Revised (§3e)**: nflverse `combine` release confirmed to exist (was "no source" in the prior draft) — real per-season/per-player depth NOT yet verified, so this stays a coverage-limited exploratory item rather than moving to Tier 1/2 alongside height/weight/BMI |
| 47 (partial) | Contract status — "Recently restructured contract" | Explicitly taxonomy-tagged `[low priority]` |
| 54 (partial) | Strength of schedule — "Bye-week timing" | Explicitly taxonomy-tagged `[low priority; test in current Dataset 2 project]` |
| 75 (partial) | Name and brand inputs — "Rookie hype", recruiting-program prestige | Explicitly taxonomy-tagged `[candidate input only]` — treat as a derived-attention input, not a standalone feature, per the family's own hypothesis text |

---

### TIER 4 — Prospective-only traits
*The taxonomy explicitly tags these `[prospective-only]` — collect
reliably going forward; do not attempt to reconstruct the full
2006-2025 historical record.*

| # | Family | Note |
|---|---|---|
| 59 | Training-camp role | Most bullets explicitly tagged `[prospective-only]` in the source document; the non-tagged bullets (e.g. "running with first team," "camp injury") could theoretically be historically reconstructed from beat coverage, but that reconstruction effort is itself Tier 5, not Tier 4 |
| 60 | Preseason-game usage | Same pattern — several bullets explicitly tagged, the rest share the same real-time-reporting dependency |
| 61 | Beat-reporter consensus | Almost entirely explicitly tagged `[prospective-only]`; inherently a real-time signal that can't be honestly reconstructed after the fact without survivorship bias in what got reported |

---

### TIER 5 — Last-priority / future research
*Preserve fully, do not build now. Either explicitly taxonomy-tagged
`[last-priority, coverage-limited]`/`[later/questionable]`, or requires
a genuinely new, large, currently-nonexistent external data source with
no verified historical depth.*

| # | Family | Why Tier 5 |
|---|---|---|
| 19 | Man/zone receiving performance | Explicitly taxonomy-tagged `[last-priority, coverage-limited]`. **Revised note (§3e)**: nflverse `ftn_charting` release confirmed to exist and is the likely real source, but its coverage years are unverified — stays Tier 5 per the taxonomy's own tag regardless, this note just records that a real candidate source now exists |
| 56 | Schedule-defense microtypes | Explicitly taxonomy-tagged `[later/questionable]` |
| 5 | College production (+ all 4 sub-buckets: metrics, RB passing-game role, accolades, coaching, family background) | Single largest acquisition-burden cluster in the entire taxonomy (§3g) — no college-stats infrastructure exists in this repo at all |
| 33 | Head-coach change | No coaching-history data source exists |
| 34 | Offensive-coordinator change | Same |
| 35 | Play-caller change | Same |
| 36 | Scheme fit | Depends on coaching/scheme classification data that doesn't exist; also inherently the most subjective family in the taxonomy (risks failing the existing spec's "too subjective to reproduce" predictive-eligibility exclusion) |
| 37 | Offensive-line quality | Needs a real O-line grading source (e.g. PFF-style); none exists here |
| 38 | Blocking environment by player type | Depends on #37 |
| 40 | Injury type | **Revised (§3e)**: nflverse `injuries` release confirmed to exist, real weekly injury-report designations, 2009-2025 — moves from "no source exists" to "new release tag, coverage/schema verification needed." Still Tier 5 for now (unverified schema, and shorter-than-full history), but no longer blocked on a nonexistent source |
| 41 | Recovery stage | Depends on #40; same revised, not-yet-verified source |
| 42 | Injury history burden | Depends on #40; a coarse version (career games missed) is buildable from #39 alone (Tier 1) — the injury-type-detail version now depends on a real, confirmed-existing 2009-2025 source rather than nothing |
| 43 | Health-related market overreaction | Depends on #40-42 plus historical ADP-source granularity — still Tier 5, furthest downstream of an unverified chain |
| 88 (split, part) | Workload and durability risk — the injury-specific sub-signals ("repeated lower-body injuries," "returning from surgery," "short offseason" tied to a specific injury) | Depends on the same `injuries` release as #40-42 (now confirmed to exist, 2009-2025, schema unverified) |
| 47 (remainder) | Contract status | No contracts database exists in THIS repo, but nflverse's `contracts` release (single "historical_contracts" file) is confirmed to exist (§3e) — real per-player/per-season depth NOT yet verified, stays Tier 5 pending that check |
| 48 | Organizational investment | Depends on #47's same unverified source |
| 25 | Projected scoring environment (Vegas totals, projected pace/plays) | No Vegas-odds or projections-history source exists |
| 26 | Pace and play volume | Partially derivable from already-fetched play-count columns once retained (Tier 2-adjacent for the retained-column portion), but "projected pace" and coordinator/coach pace HISTORY need external play-caller data (Tier 5) — **split family, flagged explicitly, not silently demoted as a whole** |
| 27 | Pass/rush tendency | Same split as #26 — descriptive share is derivable once weekly columns are retained; "scheme change" judgment needs external classification |
| 28 | Game-script sensitivity | Needs the Vegas/point-differential projections this repo doesn't have |
| 29–32 | Quarterback environment (continuity, quality, career stage, rushing) | Core continuity (#29, "same starting QB") is actually near-Tier-1 (derivable from team+position joins), but quality/career-stage/rushing sub-bullets lean on advanced QB metrics and coaching context not yet sourced — **flagged as a split family**, not uniformly Tier 5 |
| 54 (remainder) | Strength of schedule | Needs opponent defensive-strength modeling this project hasn't built, plus weather/dome data absent entirely |
| 55 | Travel and schedule disruption | No travel-distance/timezone data source exists |
| 57 | Fantasy playoff environment | Depends on #54's unresolved opponent-strength modeling |
| 58 | Venue environment | Confirmed absent from `games.csv` (§2) — needs an entirely separate static venue-facts table |
| 71 | Team defense quality | No defensive-strength data source/model exists |
| 72 | Non-offensive scoring context | Depends on #71 |
| 73 | Non-injury availability (suspensions, holdouts) | No transaction/suspension database exists |
| 53 | Public sentiment and narrative | Explicitly the kind of subjective, hard-to-reproduce signal the existing spec's predictive-eligibility rule is built to exclude by default; preserved for research, not prioritized |
| 75 (remainder) | Name and brand inputs | Same subjectivity concern beyond the Tier-3 candidate-input note above |
| 76 | Market attention and reputation | Same |
| 77 | Ambiguity discount | Real hypothesis, but its inputs (unsettled depth chart, unsettled QB, etc.) are themselves built from Tier 1-3 families — this is a META-combination that should wait until those exist, AND its subjective "ambiguity" framing needs a reproducible operational definition first |
| 74 | Recency bias | Real and buildable from ADP+finish history already available, but conceptually closer to a RESEARCH/behavioral-economics angle than a Star/bust predictor — preserved, deprioritized pending a decision on whether this belongs in Dataset 2A/2B at all or is pure Historical Findings |
| 90 | Confidence in the trait itself (meta-features) | This is a LENS to apply to every other family once built (data quality, source count, missingness, reproducibility), not a standalone family — genuinely last, since it has nothing to evaluate until other families exist |

---

## 6. Recommended first implementation wave — individual family level

**APPROVED for families 1, 2, 4, 6, 7, 8, 9, 39, 44, 10, the identified
split of 86, and the identified split of 88 (2026-07).** Family #49 is
handled separately as mandatory infrastructure, not a build-and-test
family (see its entry below). **Implementation is underway in small,
reviewable slices, not all at once.**
- **Slice 1** (families #1, #2, #4, #6 — the "players.csv cluster"):
  **BUILT** — `lib/dataset2/experience_age_draft.py`,
  `tests/test_dataset2_experience_age_draft.py` (19 tests).
- **Slice 2a** (families #8, #39, #44 — the "master-DB self-join
  cluster," strictly-lagged season-over-season derivations): **BUILT**
  — `lib/dataset2/prior_season_traits.py`,
  `tests/test_dataset2_prior_season_traits.py` (12 tests). #44 is the
  plain binary `changed_team` flag only, per the approved sequencing —
  transaction/context subtypes are a later, separate addition.
  Full suite as of slice 2a: 692/692 passing, no regressions.
- **Slice 2b** (family #7 — prior-season finish, with the required
  raw/ADP-conditioned/market-pricing three-part analysis design):
  **BUILT** — `lib/dataset2/prior_finish_traits.py` (feature
  construction only), `lib/dataset2/prior_finish_analysis.py` (the
  three separate analysis functions), 21 new tests. A shared
  `lib/dataset2/common.py` (`validate_columns()`, `lag_join()`) was
  extracted from slices 1/2a during this slice to avoid a third/fourth
  duplicate of identical logic — a mechanical refactor, re-verified
  against slices 1/2a's existing tests before proceeding, no behavior
  change. Full suite as of slice 2b: 719/719 passing, no regressions.
- **Slice 3** (family #9's sample-size portion — half-split and
  parametrized final-N-games PPG, primary ≥4/sensitivity ≥3 game
  floors exposed separately, minimum-opportunity explicitly pending):
  **BUILT** — `lib/dataset2/partial_season_traits.py`, 17 new tests.
  Full suite as of slice 3: 738/738 passing, no regressions.
- **Slice 4** (family #10, the depth-chart-dependent split of #86,
  and the age/frame split of #88 — the depth-chart cluster): **BUILT**
  — `lib/dataset2/depth_chart_traits.py` (19 tests) and
  `lib/dataset2/fragility_traits.py` (13 tests). Real 2020/2025
  nflverse data, inspected at build time, revised #10's original
  binary/ordinal scope into a tie-preserving design — see §3f's update
  note and #10's entry below for the full real-evidence writeup. Both
  `common.py` helpers (`kickoff_lookup_table()`,
  `within_group_zscore()`) were extracted a second/third time in this
  slice for the same reason as slices 2b/3 — real duplication avoided,
  not speculative. Full suite as of slice 4: 774/774 passing, no
  regressions. **This completes the entire approved first
  implementation wave.**

Research Priority uses the S/A/B hierarchy from §4.5 — a SEPARATE axis
from Implementation Tier, not a re-statement of it.

**What "BUILT" means for every slice so far, and what it doesn't
(2026-07).** All tests across slices 1/2a/2b prove **implementation
correctness only** — derivation and stratification logic verified
against small, hand-constructed synthetic fixtures with known,
hand-checked expected outputs. They say nothing about **real-data
integration or coverage** — none of these modules has been run against
the real `players.csv`/`schedules`/master-DB population in this
environment (that data isn't cached in this sandbox; real fetches go
through the established GitHub Actions path per CLAUDE.md). Those are
two different claims, and only the first is currently true for any
family built so far. Family #7's analysis functions carry an
ADDITIONAL distinct gap beyond the other modules': even once run
against real data, their OUTPUT is not itself a validated football
finding until a human reviews it — the raw/ADP-conditioned/
market-pricing reports are reproducible computations, not conclusions,
until that review happens.

**Required integration checkpoint — RUN 2026-07, see
`research/dataset2/INTEGRATION_AUDIT_2026_07.md` for the full,
real-data audit report (passed checks / accepted warnings / zero
implementation failures found / two methodological decisions flagged
for approval, most significantly that the WR structural
starter-count constant doesn't match real 2006-2012 data).** Age (#2)
and #10's 2025 branch remain unvalidated — `schedules.csv` is not
cached in this sandbox; re-run those two specifically once it's
available. Every other item below was checked against real data in
that audit. Original checklist, preserved for reference:
1. Match rate to `players.csv` (what fraction of the real population
   joins successfully on `player_id`/`gsis_id`)
2. Missing birth dates (real count/rate, and whether concentrated in
   any era or position)
3. Missing or malformed `rookie_season` values
4. Missing team/Week-1-schedule matches (real count/rate of teams or
   team-seasons absent from `schedules`)
5. `experience_years` and `age_at_week1_years` distributions by
   position and season (do they look like real, plausible curves, not
   an artifact of the join logic)
6. Duplicate player matches (more than one `players.csv` row resolving
   to the same `player_id`)
7. Impossible values — negative experience, implausible ages
   (e.g. well under 20 or over 50), and heights/weights/BMI outside a
   plausible human-football-player range
8. (slice 2a) Real `ppg_trend_2yr_slope`/`ppg_trend_3yr_slope`
   distributions by position/era, and the real share of rows null due
   to insufficient history (rookies/sophomores) vs. any unexpected gap
9. (slice 2a) Real `changed_team` base rate by position/era, and
   confirmation the rate is plausible (not inflated by a team-code
   inconsistency, e.g. relocated/renamed franchises)
10. (slice 2b) Real `prior_overall_finish`/`prior_positional_finish`/
    `prior_ppg` coverage and distribution by position/era
11. (slice 2b) Once run against real data, a human review of
    `adp_conditioned_prior_finish_report()`'s actual output — cell
    counts, whether `DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE=10` turns
    out to be a sensible real threshold or needs revisiting, and
    whether the quartile-collapsing limitation noted in
    `prior_finish_analysis.py`'s own docstring (tied prior-finish
    values shrinking a stratum below 4 real bins) materially affects
    real cells
12. (slice 4) Real match rate for `depth_chart_traits.py` across the
    FULL 2006-2025 population (this design was validated against 2020
    and 2025 only at build time) — confirm the offensive-personnel
    filter and tie-rate patterns found in 2020 generalize across other
    seasons, not just that one
13. (slice 4) Real distribution of `committee_uncertainty` and
    `team_qb_uncertainty` by position/era — how often each actually
    fires, and whether `starter_group_size`/`position_starter_count`
    ever diverge in an unexpected way (e.g. a position other than
    QB/RB/TE showing a real, non-WR-structural tie)
14. (slice 4) Real `body_size_position_z` distribution by position —
    sanity-check against known real height/weight ranges per position

This checkpoint was a required step of pipeline integration, now
satisfied for every module except age (#2) and #10's 2025 branch (see
`INTEGRATION_AUDIT_2026_07.md`'s environment-constraint note) — tests
passing alone was never sufficient evidence on its own, real data was
required and has now been run.

**#1 — NFL experience curve — BUILT (2026-07)**
- Implementation: `lib/dataset2/experience_age_draft.py::build_experience_age_draft_traits()`,
  column `experience_years`
- Initial trait: years of NFL experience as of that season, derived
  as `season - rookie_season` (per §3d — NOT the table's own
  `years_of_experience` column, which reflects today, not that
  historical season; the built module's `players_df` schema doesn't
  even include that column, so a regression that tried to read it
  would fail loudly, not silently)
- Source/seasons: `players.csv.rookie_season` — full 2006-2025
- 2A/2B: Both
- Research priority: **A** — real, standard mechanism (rookie/
  sophomore volatility, prime-age plateau), but a well-known covariate
  more than a novel differentiator (S/A/B rating preserved as the
  pre-analysis expectation per the roadmap's approved decision — see
  §6's "evidence status" note below; not yet empirically tested)
- Burden: Low (join + arithmetic) — DONE
- Leakage: None (fixed at season start)
- **Also built (approved 2026-07): joint/interaction and
  position-adjusted forms** — `age_x_experience` (interaction term),
  `experience_position_z` (z-scored within position)
- Decision needed: none

**#2 — Age curve — BUILT (2026-07)**
- Implementation: same module, column `age_at_week1_years`
- Initial trait: age as of that season's real per-team Week-1 kickoff
  date (from `birth_date` + `schedules`, NOT a flat Sept-1
  approximation — verified by a real regression test using two teams
  with different 2022 kickoff dates)
- Source/seasons: `players.csv.birth_date` + `schedules` — full
  2006-2025 (subject to `schedules` being fetched; not yet run against
  real data in this environment, only against test fixtures — see §6's
  implementation note below)
- 2A/2B: Both
- Research priority: **B** — real signal, but likely substantially
  correlated with #1's experience curve; genuine incremental value
  over #1 needs to be tested, not assumed (rating preserved as
  pre-analysis, per the roadmap's approved decision)
- Burden: Low — DONE
- Leakage: None
- **Status, stated explicitly (2026-07)**: this family is APPROVED, not
  an open research decision. What remains is one implementation
  prerequisite — running the real per-team Week-1 kickoff-date
  computation against real `schedules.csv` data (not yet available in
  this sandbox) to confirm the already-implemented, already-tested
  logic behaves correctly on real dates, the same way #1/#4/#6 already
  were. This is a validation step, not a conceptual question.
- **Approved decision applied**: age and experience are treated as
  DISTINCT hypotheses, not collapsed or deduplicated before testing.
  `measure_age_experience_collinearity()` in the same module MEASURES
  their real Pearson/Spearman correlation and reports it — it is never
  called anywhere that would drop either column, which
  `TestCollinearityNeverDropsTraits` in the test file verifies as a
  standing regression guard.
- Decision needed: none — collinearity is measured, not adjudicated,
  per the approved decision

**#4 — NFL draft capital — BUILT (2026-07)**
- Implementation: same module, columns `nfl_draft_year`,
  `nfl_draft_round`, `nfl_draft_pick`, `nfl_draft_team`
- Initial traits: `nfl_draft_round`, `nfl_draft_pick`, plus
  `nfl_draft_year`/`nfl_draft_team` (per the adopted `nfl_draft_*`
  naming convention, §3a — a real regression test asserts no output
  column name contains "adp" or "acquisition")
- Source/seasons: `players.csv.draft_year/round/pick/team` — full
  2006-2025
- 2A/2B: Both
- Research priority: **S** — a specific, real mechanism distinct from
  fantasy ADP (real organizational investment/opportunity), not
  redundant with acquisition cost
- Burden: Low (join) — DONE
- Leakage: None
- Decision needed: none

**#6 — Body-size profile (renamed from "Athletic profile" — approved
2026-07) — BUILT (2026-07)**
- Implementation: same module, columns `height_inches`, `weight_lbs`,
  `body_size_bmi` — a real regression test asserts no output column
  name contains "athletic"
- Naming decision: this Tier-1 build is described as a **body-size
  profile** (height, weight, derived BMI only), not an "athletic
  profile" — the taxonomy's family #6 concept includes real athleticism
  (speed/explosiveness/agility via combine drills), and calling a
  height/weight-only build "athletic profile" would overstate what it
  actually measures. The combine-drill sub-signals stay a separate,
  Tier-3, coverage-unverified item (§5, "6 (split, part)") and only get
  folded back into a genuine "athletic profile" label if/when verified
  combine metrics are actually included.
- Initial traits: height, weight, derived BMI
- Source/seasons: `players.csv.height/weight` — full 2006-2025
- 2A/2B: Both
- Research priority: **B** — height/weight alone is a weak standalone
  predictor; likely more useful as a position-fit control than a
  standalone Star/bust signal
- Burden: Low — DONE
- Leakage: None
- Decision needed: none

**#7 — Previous-season finish — BUILT (2026-07): feature construction
+ analysis functions, NOT yet run on real data**
- Implementation: `lib/dataset2/prior_finish_traits.py::build_prior_finish_traits()`
  builds `prior_overall_finish`/`prior_positional_finish`/`prior_ppg`
  ONLY — no rate/report logic. `lib/dataset2/prior_finish_analysis.py`
  holds the three required, structurally separate analysis functions
  (`raw_prior_finish_report()`, `adp_conditioned_prior_finish_report()`,
  `prior_finish_vs_current_adp_report()`) — feature construction and
  empirical analysis are two different modules, per your instruction
  to keep them separate. Each analysis function accepts a `finish_col`
  parameter so overall finish, positional finish, and PPG can each be
  tested independently, exactly as instructed. 21 tests (4 + 17)
  verify the STRATIFICATION LOGIC (ADP-conditioned genuinely
  stratifies by position × ADP-round-bucket × era rather than pooling;
  small cells are flagged; the market-pricing function never requires
  the Star label) against synthetic fixtures — **no real historical
  data has been run through any of these functions yet**, so no
  empirical finding about prior finish exists. That's a required,
  separate next step (§6's integration checkpoint, extended below to
  cover this module too).
- Initial traits: prior-season overall finish, prior-season positional
  finish rank, and prior-season PPG (all three, not just positional
  finish as the earlier draft scoped it — per your instruction to test
  whether each independently adds information); rookies use the
  existing spec's separate rookie path
- Source/seasons: `position_finish_ppr`, `fantasy_points_ppr`,
  `ppg_ppr` — full, 89.7% have a valid prior season per the existing
  spec
- 2A/2B: Both
- Research priority: **S** on raw mechanism strength (production
  autocorrelation is one of the best-established patterns in fantasy
  research)
- Burden: None (already available)
- Leakage: None (strictly lagged)
- **Required analysis design (your decision, now binding for this
  family specifically)**: two results are reported, not one, and they
  are not interchangeable —
  1. **Raw relationship** (prior finish/PPG vs. Star/bust rate,
     unconditioned) — reported for descriptive completeness only, NOT
     the headline finding.
  2. **ADP-conditioned relationship** (prior finish/PPG vs. Star/bust
     rate, among players comparable on CURRENT-season ADP, position,
     and era) — this is the primary result. Tests whether prior
     overall finish, prior positional finish, and prior PPG each add
     information beyond what the market (current ADP) already prices
     in, not whether prior success correlates with future success in
     general (which ADP alone would likely already explain).
  3. **A third, separate hypothesis is preserved, not collapsed into
     the above**: prior-season finish vs. CURRENT-season ADP itself —
     i.e., does the market under- or over-react to a player's prior
     finish when setting this season's price? This is a market-pricing
     question, distinct from whether prior finish predicts the SBV
     Star/bust outcome, and must be reported as its own result, not
     folded into finding #2.

**#8 — Multi-year production trend — BUILT (2026-07)**
- Implementation: `lib/dataset2/prior_season_traits.py::build_prior_season_traits()`,
  columns `ppg_trend_2yr_slope`/`ppg_trend_3yr_slope` — a real OLS
  slope over the non-null lag points in each window; fewer than 2 real
  points (rookie/sophomore) yields null, never a fabricated slope
- Initial trait: 2-3 year rolling trend/slope in `ppg_ppr`; 3-year
  variant naturally has fewer eligible rows at career starts
- Source/seasons: `fantasy_points_ppr`, `ppg_ppr` — full
- 2A/2B: Both
- Research priority: **A** — real, plausible incremental signal
  (trajectory beyond a single point-in-time snapshot)
- Burden: Low (derived computation) — DONE
- Leakage: None
- Decision needed: none

**#9 — Partial-season production splits — SAMPLE-SIZE PORTION BUILT
(2026-07); minimum-opportunity floor still PENDING, by design**
- Implementation: `lib/dataset2/partial_season_traits.py::build_half_split_traits()`
  and `::build_final_n_games_traits()` (parametrized by `n`). 17 tests.
  `opportunity_qualified` is the literal string `"pending"` on every
  row — never True/False, never silently treated as qualified. A
  window's PPG value is set to null whenever it has fewer than
  `config.DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY` (3) games —
  a structural guarantee, not just a flag a downstream consumer has to
  remember to check.
- **DECISION (2026-07, approved)**: minimum-SAMPLE floor is **≥4
  games, primary** (`config.DATASET2_PARTIAL_SEASON_MIN_GAMES_PRIMARY`)
  — chosen for a more credible sample while retaining 48.4% of the
  real population with reasonably proportional era coverage. **≥3
  games is a documented sensitivity comparison**
  (`config.DATASET2_PARTIAL_SEASON_MIN_GAMES_SENSITIVITY`), exposed as
  a SEPARATE qualification column, never substituted for the primary.
  Fewer than 3 games is never a usable partial-season finding at all —
  no lower fallback tier exists. **This is a provisional design, not a
  final eligibility rule** — a games-played floor alone can still
  include a player who was active but had a negligible role.
- Initial traits: first-half vs. second-half PPG split; final-N-games
  PPG (threshold-sensitivity rule: implement as one parametrized
  window, not many fixed splits)
- **Required build detail (approved 2026-07)**: every split-window PPG
  computation must apply a minimum-SAMPLE requirement AND a
  minimum-OPPORTUNITY requirement. Real candidate cutoffs and real
  retained counts were analyzed below BEFORE any split logic was
  written, per your instruction — the sample-size portion is now
  approved and built (above); the minimum-opportunity portion remains
  explicitly deferred (below), not fabricated.

  **Minimum-SAMPLE candidates — real data, `weekly_results_ppr_2006_2025.csv`,
  skill positions only, n=10,659 total player-seasons 2006-2025:**

  *First-half/second-half split* (season-length-aware halves,
  16-game era pre-2021, 17-game era from 2021; floor applies to BOTH
  halves):

  | Min games/half | n retained | % of population |
  |---|---|---|
  | ≥1 | 7,999 | 75.0% |
  | ≥2 | 6,867 | 64.4% |
  | ≥3 | 5,955 | 55.9% |
  | ≥4 | 5,160 | 48.4% |
  | ≥5 | 4,405 | 41.3% |
  | ≥6 | 3,604 | 33.8% |

  Floor≥3 by position: WR 2,448 / RB 1,600 / TE 1,259 / QB 648 (QB's
  TOTAL population is 1,522, so this retains 42.6% of QBs vs. 59.7% of
  WRs — QB retention is already lower here). Floor≥4 by position: WR
  2,138 / RB 1,409 / TE 1,052 / QB 561 (QB retention drops to 36.9% of
  its own population vs. 52.2% for WR) — **QB retention shrinks
  fastest as the floor rises**, most likely because the QB population
  includes many backup/emergency-QB seasons with genuinely few games,
  not a flaw in the floor itself. Floor≥3 by era: 2011-2020 n=3,002 /
  2021+ n=1,576 / pre-2011 n=1,377 (roughly proportional to each era's
  real season count, no glaring era skew).

  *Final-N-games split* (floor = min games within the trailing N
  weeks):

  | Window | Floor | n retained | % of population |
  |---|---|---|---|
  | Final 4 | ≥2 | 7,204 | 67.6% |
  | Final 4 | ≥3 | 5,984 | 56.1% |
  | Final 4 | ≥4 (every game) | 4,827 | 45.3% |
  | Final 6 | ≥3 | 6,828 | 64.1% |
  | Final 6 | ≥5 | 4,980 | 46.7% |
  | Final 6 | ≥6 (every game) | 3,948 | 37.0% |
  | Final 8 | ≥4 | 6,570 | 61.6% |
  | Final 8 | ≥7 | 4,198 | 39.4% |
  | Final 8 | ≥8 (every game) | 3,108 | 29.2% |

  **Minimum-OPPORTUNITY candidates — CANNOT be computed with real
  numbers yet.** Per the verified data inventory (§2), target/carry
  share and snap counts are either fetched-but-not-retained
  (`target_share`/`carries`, Tier 2) or not yet wired in at all
  (`snap_counts`, §3e) — this is the SAME retention/wiring dependency
  already documented for families #15/#16/#20, not a new gap. Proposing
  a numeric opportunity floor without real data to test it against
  would be a guess, which the coverage-aware and "flag and exclude,
  never guess" rules both prohibit. **Recommendation: the minimum-
  SAMPLE floor can be decided and implemented independently now; the
  minimum-OPPORTUNITY floor should wait for the #15/#20 weekly-column
  retention work, and until then #9's split should be built with the
  sample-size floor only, clearly labeled as not yet opportunity-
  filtered** — this is a real, disclosed limitation, not silently
  dropped.

  **Cutoff APPROVED (sample-size only) — see decision above.**
- Source/seasons: `weekly_results_ppr_2006_2025.csv` — full
- 2A/2B: Both
- Research priority: **A** — plausible ("finishing strong" as a
  signal), but real risk of a weak or noisy effect size — flagged as
  a likely small-effect-size result even if the direction is real
- Burden: Low/moderate (per-week aggregation) — sample-size portion
  DONE; opportunity portion blocked on #15/#16/#20 retention work
- Leakage: None (all pre-dates the season being predicted)
- Decision needed: **RESOLVED for sample size (2026-07)**. Still open:
  the exact minimum-opportunity floor, deferred until targets/carries/
  routes/snaps are retained and real distributions can be examined —
  do not characterize this family's PPG output as a final,
  opportunity-qualified finding until that floor is added.

**#39 — Prior-season availability (durability) — BUILT (2026-07)**
- Implementation: same module, column `prior_season_games_played`
- Initial trait: games played in the prior season (already available)
- Source/seasons: `games_played` — full
- 2A/2B: Both
- Research priority: **A** — durability persistence is real but
  typically a modest effect size in fantasy research, not a strong
  standalone differentiator
- Burden: None — DONE
- Leakage: None
- Decision needed: none

**#44 — Player changed teams — sequencing APPROVED (2026-07) — BUILT
(binary flag only)**
- Implementation: same module, column `changed_team` — null for a
  player's first season (no prior team to compare against), never
  False; a real test guards this (`TestChangedTeam::test_rookie_is_null_not_false`)
- Initial trait: binary team-change flag, `team` season N vs. N-1
- Source/seasons: `team` — full
- 2A/2B: Both
- Research priority: **B** — real but structurally heterogeneous (a
  trade into a better opportunity, a trade into worse one, and
  unrestricted free agency are very different situations bundled into
  one binary flag as specified)
- Burden: None — DONE
- Leakage: None
- Decision needed: **RESOLVED 2026-07** — plain binary `changed_team`
  flag built first (matches the taxonomy's own family definition, per
  the "don't silently reinterpret" rule); transaction and context
  subtypes (trade vs. free agency, opportunity direction) are added
  only afterward, using documented source coverage, and must not delay
  the binary trait, which is already done. Consistent with how #45/#46
  (teammate departures/additions) are already scoped as downstream
  refinements.

**#49 — Absolute ADP — ROLE SETTLED (2026-07, approved), not a Tier-1
"trait to test" in the same sense as the others**
- Role: `overall_adp_model` / `positional_adp_model` is a **mandatory
  control, stratification variable, baseline-calibration variable, and
  eventual Dataset 3 model feature** — not a Dataset 2A trait
  candidate to be tested for its own raw association with the Star
  label.
- Source/seasons: full, already available
- 2A/2B: infrastructure for both, not a standalone finding for either
- Research priority: **not rated S/A/B — this decision supersedes
  that framing.** Per your instruction, ADP's raw association with
  `star_by_value_label` is NOT reported as an ordinary Dataset 2A
  discovery, because acquisition cost is part of the SBV target's own
  construction (`star_by_value_score` and `star_by_value_threshold`
  are both defined relative to it) — a raw ADP→Star correlation would
  be partly mechanical, not a novel finding about what predicts
  becoming a Star.
- Burden: None
- Leakage: None (set pre-Week-1 by construction)
- **What IS required, standing methodology from here forward**:
  1. Descriptively report Star rate and bust rate BY ADP range (e.g.
     the four buckets already used in §3j: R1-2/R3-5/R6-10/R11+) — a
     real, useful baseline table, but explicitly labeled descriptive
     calibration, not a "finding."
  2. Every OTHER trait's evaluation in Dataset 2 must be conducted
     within or controlling for comparable ADP ranges (this is now the
     same requirement as §4.6's position/ADP/era stratification rule,
     restated here specifically for ADP because it's the trait most at
     risk of being mistaken for an independent discovery when it
     mechanically overlaps the target).
  3. Retained as a feature for the eventual Dataset 3 predictive model
     (a legitimate, expected input there — Dataset 3 predicts the
     Star label directly, so using ADP as one input among many is
     standard, not circular, in that context specifically).

**#10 — Projected depth-chart position — BUILT (2026-07), tie-preserving
design after a real-data investigation revised the original scope**
- Implementation: `lib/dataset2/depth_chart_traits.py::build_depth_chart_traits()`.
  19 tests. **DESIGN REVISED from the original binary/ordinal framing**
  after real 2020 and 2025 depth-chart data showed the two schema eras
  are NOT naturally comparable for every position — see the module's
  own docstring for the full real-evidence writeup. Settled, approved
  design:
  - `depth_chart_native_rank`: the real, UNMODIFIED rank each schema
    reports (`depth_team` pre-2025, `pos_rank` 2025) — ties preserved
    exactly as given, never re-ordered by row order, alphabetization,
    ADP, snaps, or later production.
  - `depth_chart_status` (starter/backup/deeper): the PRIMARY
    era-comparable feature, built identically from native rank in both
    eras — ALL players tied at rank 1 are starters, none ranked ahead
    of another.
  - `depth_rank_tied`, `starter_group_size` (real, observed count at
    rank 1), `position_starter_count` (FIXED structural reference —
    `config.DATASET2_DEPTH_CHART_STRUCTURAL_STARTER_COUNT`, QB=RB=TE=1,
    WR=3 — deliberately NOT derived from any team's own observed ties,
    so a real 2-player RB committee stays distinguishable from WR's
    routine 3-wide group even though both may share native rank 1).
  - `depth_chart_schema_era`: labels every row as
    `historical_tie_preserving` or `2025_vendor_strict_order`, so later
    analysis can explicitly test whether an effect differs by schema
    era rather than silently pooling two structurally different
    sources.
  - **No pre-2025 WR ordinal rank was built** — the real 2025
    sequential WR rank is retained as source data (via
    `depth_chart_native_rank` on 2025 rows only) but is explicitly
    coverage-limited/deferred for cross-era WR-ordinal analysis until
    multiple seasons exist or an older compatible source is found.
  - Offensive-personnel filtering (`formation == 'Offense'` pre-2025,
    `pos_grp == '3WR 1TE'` 2025) is REQUIRED and verified for all four
    positions, not just WR — real data confirmed special-teams rows
    (kick/punt returners, FG-unit players) appear under the same
    position codes as offensive skill players in both eras.
- Initial trait: standardized starter/backup/deeper status as of the
  real per-team Week-1 kickoff date
- Source/seasons: `depth_charts_{season}.csv`, full 2006-2025 including
  2025 via the proven snapshot-selection mapping (§3f) — reuses/
  generalizes `apply_rookie_qb_depth_chart_correction()`'s
  already-validated logic
- 2A/2B: Both
- Research priority: **S** — one of the more standard, well-supported
  predictive signals in fantasy analysis (starter vs. backup
  projection)
- Burden: Low — DONE
- Leakage: **Verification implemented, not just documented** — pre-2025
  uses exactly `week == 1, game_type == 'REG'`; 2025 selects the latest
  real snapshot on or before that team's real Week-1 kickoff date, via
  the same proven mechanism as `acquisition_cost.py`. Both paths are
  covered by real regression tests (`TestPreseasonTimingValidation`),
  including a case proving a later-week promotion is never used.
- **Status, stated explicitly (2026-07)**: this family is APPROVED, not
  an open research decision — the tie-preserving design itself is
  settled and implemented. What remains is two implementation
  prerequisites: (1) running the 2025 snapshot-selection branch against
  real `schedules.csv` data (not yet available in this sandbox) to
  prove every real 2025 snapshot used genuinely predates that team's
  real Week-1 kickoff — the pre-2025 `week == 1` path needs no such
  check, since it doesn't depend on schedule dates at all; (2) the
  generalized (beyond-QB) real-data validation is currently limited to
  the full 2006-2024 pre-2025 population (already run, see
  `INTEGRATION_AUDIT_2026_07.md`) — the 2025-schema generalization
  itself is implemented and tested against synthetic fixtures, but not
  yet run against real 2025 data for the same reason.
- Decision needed: none — the tie-preserving design is settled and
  implemented

**#86 (split, part) — Volume fragility, position-aware rank-1-tie
sub-signals — REVISED (2026-07) after the integration audit; PARTIAL
(the #12-dependent portion is still deferred)**
- **REVISION, approved 2026-07**: the original single, universal
  `committee_uncertainty` column is REMOVED and replaced. The
  integration audit found it was correct for QB/RB/TE but WRONG for
  WR — multiple rank-1 WRs reflect real, historically-shifting base
  offensive personnel structure (real WR `starter_group_size` was 2,
  not 3, in 85-99% of team-seasons 2006-2012, only becoming
  majority-3 around 2023-2024), not role uncertainty the way a real
  RB/TE committee does. See
  `research/dataset2/INTEGRATION_AUDIT_2026_07.md` for the full
  finding.
- Implementation: `lib/dataset2/fragility_traits.py::build_volume_fragility_traits()`.
  21 tests. New columns:
  - `multiple_rank1_players` — the NEUTRAL source fact for every
    position (real `starter_group_size > 1`), no interpretation.
  - `qb_starter_uncertainty` / `rb_committee_indicator` /
    `te_co_starter_indicator` — position-SCOPED (populated only for
    their own position, null elsewhere); for QB/RB/TE this is
    mechanically identical to the neutral fact, since their
    structural starter count is genuinely 1 in both real eras.
  - `wr_starter_group_size` / `wr_starter_group_member` — WR
    membership/count facts, explicitly NOT framed as uncertainty.
  - `wr_league_starter_group_size_norm` — the REAL, EMPIRICAL
    per-season league-wide mode of WR `starter_group_size`, computed
    fresh from data every season (never a fixed constant). Real-data
    check: this tracks the actual personnel shift exactly — 2.0 for
    every season 2006-2022, flipping to 3.0 in 2023-2024, entirely
    from real data, no threshold picked.
  - `wr_starter_group_size_vs_league_norm` — this team's real
    deviation from that season's real norm, purely descriptive.
  - `team_qb_uncertainty` — UNCHANGED (QB-specific, not affected by
    the WR finding).
  - `config.DATASET2_DEPTH_CHART_STRUCTURAL_STARTER_COUNT` is
    UNCHANGED and still required — `depth_chart_traits.py`'s
    `position_starter_count` output (explicitly preserved) and the
    three QB/RB/TE indicators above still depend on it being 1 for
    those three positions. Only its former role as WR's
    committee-detection gate was removed.
  - Real-data check (full 2006-2024 population): `qb_starter_uncertainty`
    fires only in 2019 (4.5%) and 2022 (2.9%) — matching the same 5
    real QB-tie cases the integration audit already verified.
    `rb_committee_indicator` real rate ranges 3-26% by season;
    `te_co_starter_indicator` ranges 8-47% by season — both plausible,
    no WR contamination (confirmed: 0 WR rows have any of the three
    indicators populated; 0 QB/RB/TE rows have any WR-specific field
    populated).
- Initial traits: as listed above (the #10-dependent portion only)
- Source/seasons: same as #10
- 2A/2B: 2B primarily
- Research priority: **A** — plausible 2B-specific mechanism
- Burden: Low — DONE for the #10-dependent portion
- Leakage: Same as #10
- Decision needed: none for the built portion; #12-dependent expansion
  waits for #12

**#88 (split, part) — Workload/durability risk, age/frame sub-signals
— BUILT (2026-07), workload-gated portion explicitly PENDING**
- Implementation: `lib/dataset2/fragility_traits.py::build_durability_risk_traits()`,
  column `body_size_position_z` (BMI z-scored within position, same
  pattern as #1/#2's z-scores) and `workload_qualified` (always the
  literal string `"pending"`, same pattern as family #9's
  `opportunity_qualified`). 13 tests (shared file with #86-split).
  **Deliberately does NOT build a binary "age+frame risk" flag** —
  the roadmap's original sub-bullets ("age + HIGH WORKLOAD," "small
  frame + WORKHORSE role") both need a real touch/target workload
  proxy this pipeline doesn't retain yet (same Tier-2 dependency as
  #9/#16/#20), and picking a numeric age/BMI threshold without real
  data to test it against would be exactly the kind of invented
  cutoff this project's process has consistently required real-data
  grounding and approval for (matching #9's own floor-approval
  process) — not something to invent inline.
- Initial traits: "age + high prior workload," "small frame + workhorse
  role" — compound flags from #2 (age) × workload proxy × #6 (height/
  weight)
- Source/seasons: `players.csv` fields — full
- 2A/2B: 2B primarily
- Research priority: **A** — plausible durability-risk mechanism,
  compound on #2/#6/a workload proxy (the workload proxy itself needs
  the weekly-column retention work, not yet done — so this family's
  full form is really a Tier 1/Tier 2 hybrid, flagged here rather than
  silently treated as fully Tier 1)
- Burden: Low for the age/frame half — DONE; the workload half needs
  the weekly-column retention work noted under Tier 2 (#87/#88
  touch-count split)
- Leakage: None
- Decision needed: none for the built portion; workload-gated flag and
  its exact thresholds wait for real data, same as #9

---

## 6.5. Classifications I'm least confident about

Flagging these explicitly, as requested — these are the calls where I
have real uncertainty, not settled findings:

1. ~~**#49 (Absolute ADP) as a Dataset 2 feature**~~ — **RESOLVED
   2026-07**: settled as a mandatory control/stratification/baseline
   variable, not an ordinary Dataset 2A finding. See #49's entry in §6.
2. ~~**#7 (Previous-season finish)'s marginal value over ADP**~~ —
   **RESOLVED 2026-07**: settled as a required raw-vs-ADP-conditioned
   dual report, with the ADP-conditioned result as primary, plus a
   preserved separate market-pricing hypothesis. See #7's entry in §6.
3. **#1 vs. #2 (experience curve vs. age curve) collinearity** — I
   expect real overlap but haven't tested it; could mean one of these
   two families is mostly redundant with the other in practice, even
   though the taxonomy treats them as separate hypotheses.
4. **The S/A/B ratings themselves, generally** — these are football-
   mechanism judgment calls, not derived from any data run yet (no
   Dataset 2 analysis has been executed — these are pre-analysis
   priority estimates, exactly the kind of thing §4.6's "confidence"
   categories will eventually let us check for real once traits are
   built and tested).
5. **Family #44's bundled binary framing** — I recommended building it
   as specified (plain binary) before sub-typing by opportunity
   direction, but I'm not fully confident that's the right sequencing
   versus building the sub-typed version directly; open to your read.

---

## 6.6. Second wave: opportunity/usage foundation (approved 2026-07)

Full source investigation, sequencing (A → B → C), and family #9
partial-window opportunity-floor requirements:
`research/dataset2/OPPORTUNITY_FOUNDATION_PROPOSAL_2026_07.md`.

**Source A — BUILT (2026-07), REVISED after a real-data
aggregation-semantics audit**: `lib/dataset2/usage_traits.py`. Full
audit report: `research/dataset2/USAGE_AGGREGATION_AUDIT_2026_07.md`.

The FIRST version (16 tests, committed as `cdb3ede`) aggregated
`target_share`/`air_yards_share`/`wopr` as a naive weekly AVERAGE and
did not filter real postseason rows out of the source weekly file —
both were REAL, CONFIRMED problems, not theoretical concerns: real
postseason rows are present in `stats_player_week_{season}.csv`
(837 in 2023 alone) and would have silently inflated a "season"
aggregate; a naive weekly average of a share metric is not the same
number as the real season share and does not match nflverse's own
convention. The REVISED version (20 tests) instead:
- Filters to `season_type == 'REG'` internally.
- RECOMPUTES `target_share`/`air_yards_share`/`wopr` from real summed
  numerators and denominators (player's season sum ÷ the real
  team-week totals for the specific weeks that player played, looked
  up via that week's own real team — correctly follows a mid-season
  trade). Verified against real 2023 data to reconcile EXACTLY
  (float-precision level) against nflverse's own real weekly values —
  including finding and fixing that `air_yards_share`'s real
  denominator is team-week `passing_air_yards`, not summed
  `receiving_air_yards` as first assumed.
- DEFERS `racr` entirely (not output) — real investigation found its
  exact per-row formula could not be reliably reconstructed from
  available data; `receiving_yards`/`receiving_air_yards` (its real
  underlying inputs) are preserved as plain sums instead, per the
  approved reconstruct-or-defer rule.
- Requires the FULL raw weekly file (all positions) as input, not just
  skill positions — verified real 2023 data that skill-only team
  totals silently undercount (135 real targets, 66 real
  passing-air-yards of real season volume come from non-skill-tagged
  rows).

`passing_epa`/`rushing_epa`/`receiving_epa` were explicitly re-verified
as real per-week TOTALS (not per-play averages) — summing them across
the season was already correct and unchanged by this revision.

Per the approved design, THREE structurally separate things, never
merged: `build_raw_season_usage()` (this season's own real totals,
plain column names), `build_preseason_usage_features()` (the same
fields strictly lagged to the PRIOR season only, `prior_season_*`
prefixed — the only output safe to use as a preseason predictor), and
same-season outcome data (simply `build_raw_season_usage()`'s own
output for the season being predicted — never re-wrapped, the naming
convention is the whole safeguard). Includes an exhaustive (not
sampled) leakage-proof check and a test that mutating a season's own
raw value never changes that season's `prior_season_*` output — both
unaffected by this revision. Real-data validation: a real 2023 traded
player (Chase Claypool, CHI weeks 1-3 → MIA weeks 7-18) hand-verified
against the module's real output to full precision — see the audit doc
for the full table. Unlocks the base variables for #15, #17, #20, #22
(target/carry half), #18's core inputs, and #88's touch-count
sub-signal — no derived interaction or threshold beyond the raw
aggregates built yet, per the approved scope.

**Test count, fully reconciled**: 655 (real, git-worktree-verified
pre-Dataset-2 baseline) + 125 (8 pre-audit Dataset 2 test files) + 20
(NOT a new test file — `test_no_isolated_research_dependency.py`, a
pre-existing repo-wide guardrail that auto-parametrizes 2 checks per
`lib/`/`scripts/` file and grew exactly in step with the 10 new
`lib/dataset2/*.py` files this session added) + 4 (this audit's net
test increase) = **804**, exact, no gap.

**Source B — BUILT (2026-07)**: real acquisition + identity crosswalk +
traits. Full report: `research/dataset2/SNAP_COUNTS_IDENTITY_AUDIT_2026_07.md`.

- **Real acquisition**: all 13 real `snap_counts` seasons (2013-2025)
  fetched and cached via `scripts/nflverse_source.py`'s established
  asset-ID-pinned, sha256-verified mechanism (new
  `register_snap_counts_manifest_entry()`/`fetch_snap_counts()`,
  mirroring `depth_charts` exactly). Season 2012 is refused outright
  (real, confirmed empty asset), not silently skipped.
- **Identity crosswalk**: `lib/dataset2/snap_identity.py`. Real match
  rate 99.93% across the full 2013-2025 population (324,611 rows),
  never below 99.79% by season or 99.49% by position. Zero duplicate-
  `pfr_id` (one-to-many) or many-to-one conflicts found in real data —
  but both are ACTIVELY CHECKED on every call, not just documented as
  absent, and a real one-to-many conflict raises loudly rather than
  silently fanning out the merge. Every unmatched row is preserved
  with a real, specific `identity_match_status`, never dropped.
- **Traits**: `lib/dataset2/snap_traits.py`, mirroring Source A's raw/
  season/preseason separation exactly. Real, verified findings: the
  raw layer actively checks for (not just documents) duplicate
  `(gsis_id, game_id)` rows and raises if found (zero found in the
  real full population); postseason rows are filtered internally
  (same real bug class as Source A); `offense_pct` is RECOMPUTED from
  a real max-based team-game denominator (verified exact against real
  2023 data), while `defense_pct`/`st_pct` are DEFERRED entirely — real
  investigation found their true denominators are NOT reliably
  reconstructable (defense: 6.1% real discrepancy from rotation-heavy
  games where no player anchors 100%; special teams: 90.6% real
  discrepancy from multiple distinct situational units) — their real
  underlying counts (`defense_snaps`/`st_snaps`) ARE output instead,
  per the same reconstruct-or-defer rule already applied to Source A's
  `racr`. `games_active` counts only real games with nonzero snap
  activity. 31 new tests (13 + 18), including an exhaustive leakage-
  proof check mirroring Source A's. Real validation: Christian
  McCaffrey's real 2022 CAR→SF mid-season trade hand-verified end to
  end, including the preseason lag (2023's `prior_season_offense_snaps`
  exactly matches 2022's real `offense_snaps`).
- **Full suite: 839/839 passing.**

**Source C** (`pbp_participation`, real coverage 2016-2025, play-level,
real 2023 schema fork found) — NOT yet built, per the approved
sequencing (does not begin until Source A and B are reviewed — B is
now built and awaiting review). Family #9's partial-window opportunity
floors (final-N-games, starter-status, before/after injury or
promotion/trade, half-split) and any route-participation/role
derivation from snap data are explicitly NOT selected/derived yet, per
instruction — stopping for review before either.

---

## 7. What this document does NOT do

- Does not write, modify, or run any code.
- Does not touch `config.py`, `docs/LEAGUE_WINNER_TRAITS_SPEC.md`, or
  any production pipeline file.
- Does not commit anything to git.
- Does not decide the exact era boundaries, significance thresholds,
  or trait-testing mechanics — those remain governed by the existing
  `docs/LEAGUE_WINNER_TRAITS_SPEC.md`'s own "Open decisions" section.
