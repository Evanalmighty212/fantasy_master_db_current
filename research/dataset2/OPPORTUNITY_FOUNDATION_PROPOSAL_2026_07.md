# Opportunity/Usage Foundation — Proposal (NOT approved, no code written)

**Status: PROPOSAL ONLY.** Responds to the instruction to prioritize
the opportunity/usage foundation as the next Dataset 2 wave, before
college/coaching/contract/detailed-injury acquisition. Every claim
below was checked against real, live data — either already-cached
files in this repo, or real files/metadata fetched directly from
`nflverse/nflverse-data`'s public GitHub releases (read-only; the same
kind of research fetch already used earlier in this project for the
snap-count/participation release-catalog investigation). Nothing here
has been wired into `lib/dataset2/`, no manifest entries were added,
no code was written.

---

## Correction before anything else: family numbers in the request
don't match the roadmap

The family names given map to different numbers in
`DATASET2_TRAIT_ROADMAP.md` than the ones listed. Using the roadmap's
actual numbers throughout this document (not silently substituting
without saying so):

| Requested as | Roadmap's actual number | Roadmap's actual name |
|---|---|---|
| #14: target-earning ability | **#15** | Target-earning ability |
| #15: route participation | **#16** | Route participation |
| #16: air-yard profile | **#17** | Air-yard profile |
| #17: receiving efficiency | **#18** | Receiving efficiency |
| #18: carry profile | **#20** | Carry profile |
| #20: RB passing-game role | **#22** | Passing-game role for RBs |
| #86, #9 | #86, #9 | (these two matched already) |

(Roadmap's actual #14 is "Return-role interpretation" — unrelated to
targets, not part of this wave.)

---

## 1-4. Source, coverage, grain, schema issues, and what each field
unlocks

### A. Raw per-season weekly stats file (already cached locally,
zero new acquisition)

`data/raw/nflverse/annual/stats_player_week_{season}.csv`, 2006-2025,
**player-week grain**. Confirmed real header (145 columns) includes
`targets`, `carries`, `target_share`, `air_yards_share`, `wopr`,
`racr`, `pacr`, `passing_epa`, `rushing_epa`, `receiving_epa`, and the
`*_10`/`*_16`/`*_20`/`*_40` distance-bucket columns. Only
`fantasy_points_ppr` currently survives into the retained
`weekly_results_ppr_2006_2025.csv` — everything else is fetched, used
transiently in scripts, then dropped. **This is the single lowest-burden
item in this whole wave — the data is already on disk, nothing to
fetch.**

**Coverage, verified properly this time** (the roadmap's earlier "0.4%
populated in 2006" note was checked and found to be a methodology
error in that check, not a real gap — `target_share`/`wopr` are
correctly NULL for a row with zero real targets that week; scoped
correctly to real `targets > 0` rows): `target_share`, `air_yards_share`,
`wopr`, `receiving_epa` are **100% populated for every real
target-having row, every season 2006-2025** (spot-checked 2006, 2008,
2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2025). `racr` is
~99% (the ~1% gap is mathematically necessary — undefined when
`air_yards = 0`, not missing data). `rushing_epa` (real `carries > 0`
rows) and `passing_epa`/`pacr` (real `attempts > 0` rows) show the same
100%/~99.8% pattern across the same season spot-checks. **Full real
2006-2025 coverage confirmed for every field in this group**, once
retained.

**Distance-bucket columns (`receiving_10`/`16`/`20`/`40`, etc.) —
meaning now CONFIRMED, not just guessed**: checked real 2023 data,
`receiving_10 >= receiving_16 >= receiving_20 >= receiving_40` holds
for **100% of 18,643 real rows, zero violations**. This is a
cumulative "receptions/plays gaining at least N yards" count — an
explosiveness/play-length bucket, **not** red-zone-specific. Resolves
the roadmap's earlier open question with real evidence.

**Identity**: `player_id` in this file is the same `gsis_id` used
throughout this project. Verified: 100% of real 2023 master-DB rows
match this file's `player_id` directly. No crosswalk needed.

**Unlocks**: #15 (target-earning ability — core), #17 (air-yard profile
— core), #20 (carry profile — core), #22 (passing-game role for RBs —
the target/carry portion), the touch-count sub-signal of #88 (already
flagged as pending in `fragility_traits.py`), and gives #18 (receiving
efficiency) its core `catch_rate`/`yards_per_target`/EPA-based inputs
directly.

### B. `snap_counts` (real nflverse release, NOT yet fetched into this
pipeline)

**Real coverage, CORRECTED**: the release tag nominally spans
2012-2025, but the **2012 file is empty** (154 bytes — header row
only, zero data rows; confirmed by downloading it directly). Real,
usable coverage is **2013-2025**, not 2012-2025 as the earlier
release-catalog investigation assumed from the tag name alone.
2013-2025 each have full, consistent real data (~2.1-2.4MB/season).

**Grain**: player-GAME (one row per player per real game — `game_id`,
`week`, `game_type` including REG and playoffs).

**Real columns**: `game_id, pfr_game_id, season, game_type, week,
player, pfr_player_id, position, team, opponent, offense_snaps,
offense_pct, defense_snaps, defense_pct, st_snaps, st_pct`.

**Identity issue, real and significant**: this file identifies players
by `pfr_player_id` (Pro Football Reference format, e.g. `WillCh03`)
and a name string — **not** `gsis_id`. Direct join on `player_id` will
silently fail. A real crosswalk exists and was verified: `players.csv`
already has a `pfr_id` column (already in use for nothing else in this
project yet). Tested against real 2013 data: **1,926 / 1,928 unique
players (99.9%) matched** via `players.csv.pfr_id ==
snap_counts.pfr_player_id`. Re-tested across the full real 2013-2025
REG-season population (310,475 rows): **99.9% match rate**, consistent.
This is a real, low-burden, well-validated join — one extra hop
through `players.csv`, not a blocker.

**Unlocks**: #16 (route participation — the snap-share half),
#22 (RB passing-game role — snap-based opportunity), the
snap-share sub-signal of #86's remaining volume-fragility split, and
is the natural source for family #9's snap-based opportunity floor
(see §6 below).

### C. `pbp_participation` (real nflverse release, NOT yet fetched)

**Real coverage confirmed**: 2016-2025, every season has a real,
substantial file (21-50MB). **No coverage gap found** (unlike
`snap_counts`'s 2012 surprise).

**Grain — this is the important finding**: **PLAY-level, not
player-week**. One row per play (`nflverse_game_id` + `play_id`), with
`offense_players`/`defense_players` as semicolon-delimited LISTS of
real `gsis_id` values participating in that specific play (confirmed:
this file DOES use `gsis_id`, unlike `snap_counts` — no crosswalk
needed for this source specifically). Getting a per-player, per-week
route count requires exploding these lists into player-play rows,
then aggregating — a genuinely bigger transformation than any other
source in this wave, not just "a new file to fetch."

**Real schema change found, previously undocumented**: 2023 has **two**
published versions. `pbp_participation_2023.csv` (49.9MB) is a real
**26-column** schema that adds `offense_names`, `defense_names`,
`offense_positions`, `defense_positions`, `offense_numbers`,
`defense_numbers` on top of the original 20; `pbp_participation_old_2023.csv`
(19.7MB) is the original **20-column** schema matching 2016-2022
exactly. File sizes for 2024/2025 (~49-50MB) match the new 26-column
format, confirming **the 26-column schema is what 2023 (new)/2024/2025
actually use going forward** — a real, mid-history schema addition
(additive, not breaking; all original columns are preserved), but one
that must be handled explicitly per season/file-name, not assumed
uniform across 2016-2025.

**Real coverage within a season**: 91.5% of real 2016 plays have a
usable, non-empty `offense_players` list (`n_offense > 0`). `route` is
populated on 38.7% of ALL plays that season — correctly null on
non-passing plays (run plays, etc.), not a gap; real route labels
confirmed (GO, FLAT, HITCH, CROSS, SCREEN, SLANT, OUT, POST, CORNER,
ANGLE — standard route-tree terms).

**Unlocks**: #16 (route participation — the actual route half, not
just snap share), #22's route-specific portion, and the
route-participation sub-signal of #86's remaining split.

### D. Man/zone coverage data (`ftn_charting`) — explicitly OUT of
this wave

Referenced by #18's man/zone-specific efficiency sub-bullets and
family #19 (still Tier 5, taxonomy-tagged low-priority). Not
re-investigated here — no change to its existing "exists, coverage
unverified" status. Not part of this wave's scope.

---

## 5. Fields that sound available but aren't actually reliable
enough to use (yet)

- **`snap_counts` for 2012**: the release tag implies 2012-2025
  coverage; the real file is empty. Treat real coverage as **2013-2025**
  only.
- **`pbp_participation`'s pre-2023 file for 2023 specifically**: two
  versions exist for the same season. Whichever ETL is eventually
  built must explicitly pick the 26-column (`pbp_participation_2023.csv`)
  version to stay consistent with 2024/2025, not the `_old_2023`
  20-column one — a real, easy-to-get-wrong detail if not disclosed.
- **`route` (from `pbp_participation`) as a per-player route COUNT**:
  the field is real and well-populated on real pass plays, but turning
  "one route string per play" into "how many routes did player X run
  this week" requires the same player-list-explosion work as snap
  participation, done correctly against `offense_players` — this is
  not a simple column read, and should not be assumed trivial just
  because the raw field itself is populated.
- **Man/zone coverage (`ftn_charting`)**: still genuinely unverified,
  not part of this wave (see D above) — flagging again so it isn't
  quietly assumed to be part of "route participation" just because
  it's adjacent.

---

## Proposed sequencing, by real acquisition burden (lowest first)

1. **Weekly advanced-stats retention** (source A) — data already
   local, same identity system already in use, zero new fetch/manifest
   work. Lowest burden, unlocks the most families (#15, #17, #20, #22's
   target/carry half, #18's core, #88's touch-count sub-signal).
2. **`snap_counts` acquisition** (source B) — new fetch + manifest
   entry (same mechanism already proven for players/schedules/depth_charts),
   plus the real, validated `pfr_id` crosswalk. Moderate burden.
   Unlocks #16's snap-share half, #22's snap-based portion, #86's
   snap-share sub-signal, and family #9's snap-based opportunity floor.
3. **`pbp_participation` acquisition + route ETL** (source C) — new
   fetch + manifest entry, PLUS a genuinely new play-level-to-player-week
   aggregation step (explode `offense_players`, handle the real 2023
   schema fork). Highest burden in this wave. Unlocks #16's route half
   and #86's route-participation sub-signal.

## Proposed small first commit

**Scope: source A only** — a new `lib/dataset2/usage_traits.py`
(name provisional) that takes the existing Dataset 2 `population`
input plus the raw `stats_player_week_{season}.csv` files (already
local, one per season, same pattern already used for
`weekly_results_ppr` in `partial_season_traits.py`), and builds
SEASON-LEVEL aggregates only — real season totals/rates for `targets`,
`carries`, `target_share` (season-weighted), `air_yards_share`,
`wopr`, `racr`, `receiving_epa`/`rushing_epa`/`passing_epa`. **No
derived interactions, no thresholds, no efficiency ratios beyond what
these raw aggregates already are.** Mirrors the same
"caller-scopes-population, this module just computes" convention and
missingness policy (never zero-fill a real target-less season; null
stays null) already used by every other `lib/dataset2/` module.
Deliberately does NOT touch `snap_counts` or `pbp_participation` in
this first commit — those become their own, separately-reviewable
commits per the sequencing above, consistent with the small-commit
pattern used throughout this project so far.

---

## 6. Family #9 real candidate opportunity floors by position

Per the standing rule (no numeric threshold gets picked without your
review, same process already used for #9's sample-size floors), these
are candidates only — **nothing selected**. Computed against the real
2013-2025 population (real `snap_counts` fetched and matched via the
verified `pfr_id` crosswalk; real `carries`/`targets`/dropbacks-proxy
from the already-local weekly stats files).

**QB** (n=988 real player-seasons 2013-2025) — real `offense_snaps`
and a real dropbacks proxy (`attempts + sacks_suffered`; a true
"starts" field is not directly available in any source checked this
wave, flagging that gap honestly rather than approximating it further):

| Floor | Snaps ≥ | n retained | Dropbacks ≥ | n retained |
|---|---|---|---|---|
| Minimal | 1 | 986 (99.8%) | 1 | 953 (96.5%) |
| Low | 50 | 776 (78.5%) | 50 | 677 (68.5%) |
| Moderate | 100 | 662 (67.0%) | 100 | 577 (58.4%) |
| Higher | 200 | 565 (57.2%) | 200 | 469 (47.5%) |
| Strict | 300 | 508 (51.4%) | 300 | 391 (39.6%) |

**RB** (n=1,963) — real `offense_snaps`, real `carries`, and real
`carries + targets` combined:

| Floor | Snaps ≥ | n | Carries ≥ | n | Carries+Tgts ≥ | n |
|---|---|---|---|---|---|---|
| Minimal | 1 | 1,912 (97.4%) | 1 | 1,811 (92.3%) | 1 | 1,875 (95.5%) |
| Low | 50 | 1,439 (73.3%) | 25 | 1,183 (60.3%) | 25 | 1,307 (66.6%) |
| Moderate | 100 | 1,203 (61.3%) | 50 | 924 (47.1%) | 50 | 1,061 (54.0%) |
| Higher | 200 | 879 (44.8%) | 100 | 610 (31.1%) | 100 | 757 (38.6%) |
| Strict | 300 | 659 (33.6%) | 150 | 422 (21.5%) | 150 | 547 (27.9%) |

**WR** (n=2,951) — real `offense_snaps` and real `targets` (a route-count
floor isn't available yet — that's gated on the `pbp_participation` ETL
in step 3 above; targets are the best real proxy available today):

| Floor | Snaps ≥ | n retained | Targets ≥ | n retained |
|---|---|---|---|---|
| Minimal | 1 | 2,896 (98.1%) | 1 | 2,782 (94.3%) |
| Low | 50 | 2,433 (82.4%) | 10 | 2,114 (71.6%) |
| Moderate | 100 | 2,163 (73.3%) | 25 | 1,629 (55.2%) |
| Higher | 200 | 1,810 (61.3%) | 50 | 1,145 (38.8%) |
| Strict | 300 | 1,518 (51.4%) | 75 | 771 (26.1%) |

**TE** (n=1,645) — real `offense_snaps` and real `targets`:

| Floor | Snaps ≥ | n retained | Targets ≥ | n retained |
|---|---|---|---|---|
| Minimal | 1 | 1,629 (99.0%) | 1 | 1,553 (94.4%) |
| Low | 50 | 1,433 (87.1%) | 10 | 1,051 (63.9%) |
| Moderate | 100 | 1,293 (78.6%) | 25 | 669 (40.7%) |
| Higher | 200 | 1,047 (63.6%) | 50 | 380 (23.1%) |
| Strict | 300 | 859 (52.2%) | 75 | 216 (13.1%) |

**No floor selected.** These are real, computed candidates for your
review — a "moderate" snap-based floor (100-200 depending on position)
looks like a reasonable starting range across all four positions, but
that's an observation, not a recommendation to lock in.

---

## Open, unresolved integration checkpoints (unchanged, not blocking
this wave)

Per the standing instruction: family #2's `age_at_week1_years` and
family #10's 2025 depth-chart branch remain unvalidated against real
per-team schedule data — `schedules.csv`/`games.csv` is still not
cached in this sandbox. They may be run through GitHub Actions or
another environment with that data. This proposal does not touch
either and does not resolve that gap; both stay explicitly open.
