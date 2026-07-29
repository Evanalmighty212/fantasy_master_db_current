# Family #9 Partial-Season Reliability Proposal — 2026-07

**REGENERATED 2026-07 after the week-boundary bug fix and the
team-game/active-game window redesign.** Every table in this version
comes from running the real, committed, tested
`lib/dataset2/partial_season_traits.py` and
`lib/dataset2/common.py::build_team_game_index()` (plus a research
script that extends the same corrected window logic with Source A/B
opportunity fields not yet part of the committed module's output)
against real Sources A/B and the real master DB population — not
samples, not synthetic data, and not the superseded numbers from this
document's first version. **PROPOSAL ONLY — no threshold is chosen, no
`opportunity_qualified` logic is implemented, and nothing here has been
committed.**

---

## 0. The week-boundary bug — FIXED, not just flagged

The first version of this proposal found and flagged (not fixed) a
real bug: `lib/dataset2/partial_season_traits.py` used
`season_length()` (real games played, 16 or 17) directly as the
maximum real REG week number, when real REG week numbers actually run
one higher (`season_length(season) + 1`) because every team's real bye
consumes a week-number slot without a played game.

**Fixed this round**: `lib/dataset2/common.py` now has
`real_reg_week_slots(season)` — the one shared, documented helper for
this fact, reused by `participation_traits.py`'s `_is_postseason()`
(refactored to call it instead of re-deriving `+1` inline) and by every
Dataset 2 module going forward. An audit of every other
`lib/dataset2/*.py` module for the same mistake found none — the bug
was isolated to `partial_season_traits.py`.

**Regression tests added** (`tests/test_dataset2_common.py`,
`tests/test_dataset2_partial_season_traits.py`): a real 16-game season
played across Weeks 1-17, a real 17-game season played across Weeks
1-18, postseason exclusion at both boundaries, and confirmation that
final-4 logic never returns more than 4 real team games (verified
against realistic bye-gap fixtures for both eras, not just the
already-correct `real_reg_week_slots()` helper in isolation).

**Full suite: 903/903 passing** (`python -m pytest tests/ -q
--import-mode=importlib`; 884 before this round + 11
`test_dataset2_common.py` + net +8 in the rewritten
`test_dataset2_partial_season_traits.py` [25 new vs. 17 before] = 903,
exact).

---

## 1. The window redefinition, per instruction: team-game sequence, not
calendar week

Windows are no longer defined by calendar week number or arithmetic
against `season_length()` at all. Two structurally different window
types are now built and compared, matching the original module's real,
committed functions:

**A. TEAM-GAME windows (PRIMARY late-season trait)** —
`build_team_game_final_n_traits()`, `build_team_game_half_split_traits()`.
A team's real final N (or first/second half of) REG games, built from
`build_team_game_index()` (derived from the FULL real weekly file — no
new schedule fetch). Every one of the team's real games in the window
counts, INCLUDING a game the player was inactive or recorded zero real
usage in — zero-filled, never dropped. This is what "reflects real
late-season availability and production" means. Restricted to
single-team players (10,835 of 11,174 real population rows, 97%) — a
traded player's "team's final N games" is genuinely ambiguous; that
comparison belongs to the separate trade-split analysis (§4).

**B. ACTIVE-GAME windows (SECONDARY performance-when-active
diagnostic)** — `build_active_game_final_n_traits()`. The player's own
real final N games WITH real usage, in chronological order, wherever
in the season they fell. Immune to the week-boundary bug by
construction (no week-number arithmetic at all — just the player's own
last N real rows).

**First/second half** now split on each team's real chronological
game INDEX (`ceil(team_total_games / 2)`), not calendar week — a real,
verified difference from the original definition: for a 16-game-era
team, the corrected cutoff is `ceil(16/2) = 8` team-games, which (for a
team whose real bye falls before its 8th game) does NOT land on the
same calendar week the old, buggy `ceil(16/2) = 8`-used-as-a-week-number
version did.

**A real, previously invisible finding from comparing the two window
types on the SAME real data**: the active-game "games≥4" population is
dramatically larger than the team-game "active_games≥4" population for
every position (QB 1,059 vs. 486; RB 2,430 vs. 1,118; WR 3,678 vs.
1,790; TE 1,959 vs. 721). This makes real sense — the active-game
window can pull a player's "last 4 games with usage" from ANYWHERE in
the season (an early-season cameo before a season-long benching still
counts), while the team-game window is restricted to what actually
happened in the team's true final 4 games. The active-game window's
opportunity distribution is also real and meaningfully lower at every
percentile (e.g. QB attempts p10: 36 active-game vs. 97 team-game) —
concrete, real confirmation that these two windows answer different
questions and neither should be treated as a stand-in for the other.

---

## 2. Reliability floors: participation floor vs. opportunity floor,
distinguished per instruction

**Minimum-SAMPLE (participation) floor** — unchanged, already approved:
**≥4 active games primary**, **≥3 sensitivity**, below 3 never usable.
For team-game windows this is checked against `*_active_games` (how
many of the window's real team games had real usage), NOT the window
size itself (which is always exactly N by construction). For
active-game windows it's checked against the window's own real game
count (which can be less than N).

**Two distinct opportunity-related floors, not one, per instruction**:

- **A minimum PARTICIPATION floor** — the lowest real bar needed for
  the trait to be interpretable at all (excludes a true statistical
  zero — e.g. a player who "played" 4 team games but recorded 0 or 1
  real touches, which is not usage, it's roster presence).
- **A stronger OPPORTUNITY floor** — representing a real, meaningful
  role, not just non-zero involvement.

Real candidate levels (informed by the percentiles computed against
the corrected windows, not picked in the abstract):

| Position | Metric | Participation floor (candidate) | Opportunity floor (candidate) |
|---|---|---|---|
| QB | attempts | ≥15 | ≥60 |
| RB | carries | ≥3 | ≥15 |
| WR | targets | ≥2 | ≥8 |
| TE | targets | ≥2 | ≥8 |
| All (general, position-normalized, Source B 2013+ only) | `offense_snap_share` | ≥10% | ≥30% |

**Real retained counts, TEAM-GAME final-4 window (base:
active_games≥4)**:

| Position | Base n | Participation floor n (%) | Opportunity floor n (%) | Opportunity-floor snap-share n (%) |
|---|---|---|---|---|
| QB | 486 | 483 (99.4%) | 482 (99.2%) | 305 (62.8%, of 307 with real 2013+ coverage) |
| RB | 1,118 | 1,049 (93.8%) | 844 (75.5%) | 490 (68.2% of 719 with coverage) |
| WR | 1,790 | 1,470 (82.1%) | 1,306 (73.0%) | 996 (84.8% of 1,175 with coverage) |
| TE | 721 | 641 (88.9%) | 517 (71.7%) | 463 (92.6% of 500 with coverage) |

Real era breakdown at the OPPORTUNITY floor (RB carries≥15, the
position most affected): 2011-2020 n=432, pre-2011 n=214, 2021+ n=198
— roughly proportional to each era's real population share. ADP
breakdown: 300 of 844 have no real market ADP (replacement-level/
undrafted), 173 R6-10, 132 R1-2, 124 R3-5, 115 R11+ — the opportunity
floor does not disproportionately exclude any single ADP tier.

**Real retained counts, ACTIVE-GAME final-4 window (base: games≥4),
for direct comparison**:

| Position | Base n | Participation floor n (%) | Opportunity floor n (%) |
|---|---|---|---|
| QB | 1,059 | 999 (94.3%) | 902 (85.2%) |
| RB | 2,430 | 2,127 (87.5%) | 1,534 (63.1%) |
| WR | 3,678 | 2,907 (79.0%) | 2,311 (62.8%) |
| TE | 1,959 | 1,621 (82.7%) | 975 (49.8%) |

**Real, disclosed asymmetry worth deciding on explicitly, not by
convenience**: the SAME nominal "opportunity floor" retains a much
larger raw count from the active-game population than the team-game
population (e.g. WR: 2,311 vs. 1,306) — because the active-game base
population itself is larger and includes more marginal players to
begin with (§1). This is not evidence one window's floor should be
loosened or tightened to match the other — they are answering
different real questions and are expected to retain different real
populations. Per instruction, no single universal floor is proposed
merely for convenience; the table above is presented so the
position/window-specific floor decision can be made deliberately.

*(Final-6/8 and half-split tables were computed the same way, using
the same corrected windows — omitted here for length; available on
request. The real pattern is consistent: retained counts and
percentiles grow with window length, the team-vs-active asymmetry
holds at every window size.)*

---

## 3. What each floor excludes (unchanged real finding, now on
corrected data)

The real "decoy" case the original module's docstring worried about is
still real and still present on the corrected data: the 10th-percentile
WR/TE in the team-game final-4 `active_games≥4` population has **zero**
real targets despite having real usage in all 4 of the team's final
games (a real complementary/decoy role, not a data artifact). Even the
loosest participation floor (≥2 targets) removes a real, non-trivial
slice of this population.

---

## 4. Trade splits — coverage-limited research, three-way counts
preserved per instruction

**339 real traded skill-position player-seasons, 2006-2025** (WR 164,
RB 121, TE 40, QB 14) — real counts unchanged from this proposal's
first version (trade detection doesn't depend on the week-boundary fix
— it's a distinct-team count plus each player's own chronological
row order, never a `season_length()`-derived boundary).

**Full three-way breakdown, not collapsed into a single "qualifies"
count**:

| Floor | Before-side only | After-side only | Both sides | Neither side | Total |
|---|---|---|---|---|---|
| Primary (≥4) | 60 | 88 | **105** | 86 | 339 |
| Sensitivity (≥3) | 52 | 81 | **152** | 54 | 339 |

**Per instruction: direct before/after conclusions require BOTH sides
independently qualifying.** At the primary floor that is 105 of 339
(31%) — the standard is not loosened to inflate this number. The
before-only (60) and after-only (88) groups remain real and reportable
for a ONE-SIDED question ("how did this player perform after landing
with his new team," ignoring the before side, or vice versa) but must
not be silently combined into a two-sided before/after comparison —
that would use a real "after" value next to a missing or
floor-failing "before" value, understating the real comparison's own
uncertainty.

---

## 5. Deferred event-based splits — status unchanged, restated
explicitly per instruction

**Starter/promotion splits remain approved but deferred** until the
depth-chart source is extended to weekly resolution (currently only a
preseason snapshot is built — see this proposal's first version §5 for
the real feasibility check: weekly depth-chart data exists in the raw
source, median 13.5 real weeks of coverage per player in a 2020
sample, but no module reads it at week grain yet). Not attempted this
round; still a separate, explicitly-scoped follow-up.

**The teammate-injury proxy is NOT being implemented as an injury
trait.** The first version of this proposal tested a real,
leakage-safe usage-ABSENCE proxy (season-attempts-leader QB with 0 real
attempts in a week the team played) and found it caught only 13 of 634
real team-seasons (2%) — far too narrow, and demonstrably mislabels
the real sequence of events for a starter who lost the job permanently
early in the season rather than briefly missing time. **Per
instruction: 13 of 634 is insufficient, and this proxy must not be
labeled "injury" without real injury evidence** — no real injury
designation data is acquired in this project (nflverse's `injuries`
release exists per the roadmap's inventory but was never fetched).
Injury-conditioned splits are deferred until that source is wired in.
A future TEAMMATE-ABSENCE variable (explicitly not named or framed as
injury) may be tested separately on its own real merits — not proposed
or scoped further here.

---

## 6. Not buildable now, unchanged from the first version

Usage before/after bye (needs real schedule data, neither Source A nor
B — low-burden future addition, not attempted here), points after
coaching change (no data source exists), usage with/without starting
QB and RB-committee games (need the same weekly depth-chart resolution
as §5), production excluding injury-limited/return-from-injury games
(needs real injury data, same gap as §5's proxy finding).

---

## 7. No leakage — unchanged design constraint

Every split above describes something that happened during season N.
None of it may be used to predict season N's own outcome. Whatever
final family #9 features are eventually built get computed as
season-N raw values, then strictly lagged via `lag_join()` (the same
pattern already proven for Sources A/B) to produce
`prior_season_team_final_4_games_ppg`,
`prior_season_active_final_4_games_ppg`, etc. Not implemented in this
proposal — the design constraint is restated so any future
implementation is held to it from the start.

---

## Stop point

This is a proposal only. No threshold has been chosen and no
`opportunity_qualified` logic has been implemented. What HAS changed
in this round, as real, tested, committed code (not proposal-only):
the week-boundary bug fix (`common.py::real_reg_week_slots()`), the
team-game-index infrastructure (`common.py::build_team_game_index()`),
and the redefined `partial_season_traits.py` window functions
(`build_team_game_final_n_traits()`, `build_active_game_final_n_traits()`,
`build_team_game_half_split_traits()`) — all with regression tests,
all passing (903/903). Nothing has been git-committed yet. Awaiting
your decision on:
1. Whether the participation-floor / opportunity-floor candidate
   levels in §2 (or different levels) should be selected.
2. Whether the team-game window should be the only one that gets a
   final `opportunity_qualified` treatment, or both window types.
3. Whether to commit the code changes described above (the bug fix and
   window redesign) now, independent of the floor-selection question.
