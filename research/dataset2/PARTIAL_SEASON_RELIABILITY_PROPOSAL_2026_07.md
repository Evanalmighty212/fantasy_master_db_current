# Family #9 Partial-Season Reliability Proposal — 2026-07

**Committed so far**: §0/§1 (bug fix, window redesign) in `c79eea0`;
§1a's exclusion audit and `team_game_window_status` in `292d7d2`. §1b
(the per-team-game/per-active-game rate split) and §2b item 1 (the
flat 3-primary/4-sensitivity active-game interpretability floor) were
committed in an earlier round. §2b items 2/3 (flat efficiency-volume
and meaningful-role thresholds) were **rejected as too low** and were
superseded by §2c/§2d/§2e, a revised three-concept framework (minimal
computability / efficiency sample-eligibility / meaningful role).

The active-game floor constants were renamed to explicit,
self-evident names (`DATASET2_PARTIAL_WINDOW_MIN_ACTIVE_GAMES_PRIMARY`
/ `_SENSITIVITY`, no "swap" semantics required to read them) and
committed in `667f633`. §2d's efficiency **sample-eligibility** flags
(explicitly not called "reliability" — see the terminology correction
in §2d) are **approved and committed** (`7f2b8bf`) in
`build_team_game_efficiency_traits()`/`build_active_game_efficiency_traits()`
in `lib/dataset2/partial_season_traits.py`, with the exact
exploratory/higher-volume thresholds given in this round's approval,
and tested (42/42 in this file). §2e's meaningful-role matrix was
reworked into a **three-concept structure** — role present /
meaningful role / strong-lead role — per instruction, after the
initial single-tier primary/sensitivity pass was rejected as
mislabeled. The revised matrix (candidate thresholds, real retained
counts, era/ADP composition, real player examples per §2e) is
**approved and implemented** in
`build_team_game_role_traits()`/`build_active_game_role_traits()`/
`build_team_game_snap_share_role_traits()`
(`lib/dataset2/partial_season_traits.py`), thresholds in `config.py`'s
`DATASET2_ROLE_THRESHOLDS_TEAM_GAME`/`_ACTIVE_GAME`/`_SNAP_SHARE`, and
tested. Team-game and active-game classifications stay separate for
every metric with both; no metric's flags are combined into a single
overall role label. See §2e's closing section for the full disclosure
of what these flags do and don't claim.

---

## 0. The week-boundary bug — FIXED and committed

`lib/dataset2/partial_season_traits.py` used `season_length()` (real
games played, 16 or 17) directly as the maximum real REG week number,
when real REG week numbers actually run one higher
(`season_length(season) + 1`) because every team's real bye consumes a
week-number slot without a played game.

Fixed via a new shared helper, `common.py::real_reg_week_slots()`,
reused by `participation_traits.py`'s `_is_postseason()` (refactored,
not duplicated). An audit of every other `lib/dataset2/*.py` module
found no other instance of the mistake.

Regression tests: a real 16-game season played across Weeks 1-17, a
real 17-game season played across Weeks 1-18, postseason exclusion at
both boundaries, and confirmation that final-4 logic never returns
more than 4 real team games.

---

## 1. The window redefinition — team-game sequence, not calendar week

Two structurally different window types, both committed:

**A. TEAM-GAME windows (PRIMARY late-season trait)** —
`build_team_game_final_n_traits()`, `build_team_game_half_split_traits()`.
A team's real final N (or first/second half of) REG games, built from
`build_team_game_index()` (derived from the FULL real weekly file — no
new schedule fetch). Every one of the team's real games in the window
counts, INCLUDING a game the player was inactive or recorded zero real
usage in — zero-filled, never dropped. Restricted to single-team
players — a traded player's "team's final N games" is genuinely
ambiguous; that comparison belongs to the separate trade-split
analysis (§4).

**B. ACTIVE-GAME windows (SECONDARY performance-when-active
diagnostic)** — `build_active_game_final_n_traits()`. The player's own
real final N games WITH real usage, in chronological order, wherever
in the season they fell. Immune to the week-boundary bug by
construction.

**First/second half** now split on each team's real chronological
game INDEX (`ceil(team_total_games / 2)`), not calendar week.

---

## 1a-0. Terminology clarification (requested) — three separate
concepts, not two

The prior round's summary conflated two different statements in a way
that read as contradictory: "final-4 team-game qualification requires
real usage in all four games" and "2,148 players with zero usage
remain represented" are BOTH true, but they describe two different
stages, not the same one. Stated explicitly and kept separate from
here on:

1. **Inclusion in the underlying team-game window dataset** —
   determined solely by `team_game_window_status`. A player is
   INCLUDED whenever status is `applicable` (a single real team was
   identified and that team's real games were found) — REGARDLESS of
   how much real usage they had in the window. The 2,148 zero-usage
   players are fully included at this stage: `team_final_n_games == 4`
   (the real window size), `team_final_n_active_games == 0` (the real
   fact). Only `unavailable_traded`/`unavailable_no_team_evidence`/
   `unavailable_other` rows are excluded from this stage, and that
   exclusion is about identity resolution (which team's games apply),
   never about how much the player played.
2. **Meeting the participation/interpretability floor** —
   `team_final_n_active_games ≥` the sample floor (4 primary, 3
   sensitivity). This is a SEPARATE, later question: given the player
   IS in the dataset (stage 1), is their real usage sample big enough
   for a RATE (PPG, snap share, catch rate, etc.) computed from it to
   be interpretable at all? A zero-usage player is included per stage
   1 but fails this floor — their raw fields stay populated (as real,
   informative zeros); only a RATE field gets nulled.
3. **Meeting the meaningful-role floor** — a further, stronger
   opportunity threshold (targets/carries/attempts/snap-share) checked
   only among players who already cleared stage 2, distinguishing a
   real substantial role from merely-interpretable involvement.

**A player with an applicable team-game window and zero usage is
never described as "excluded" in this document going forward** —
they are included (stage 1), and separately, correctly, reported as
not meeting the participation floor (stage 2). Excluded is reserved
for the real `unavailable_*` statuses only.

## 1a-1. Methodology: what gets a floor, and how

Per instruction, applied consistently from here on:

- **Raw team-game production, usage, availability, and role-loss
  traits get NO minimum opportunity floor.** `team_final_n_games`,
  `team_final_n_active_games`, and any future raw per-window
  target/carry/attempt/snap COUNT are exposed for every `applicable`
  row regardless of how small the real number is — a real zero is
  itself potentially predictive (a role disappearing is information,
  not noise to be filtered out) and must stay measurable. **This is
  already how the committed code behaves** — `_apply_floor()` only
  ever nulls the PPG (rate) output; it has never gated
  `team_final_n_games`/`team_final_n_active_games` themselves. No code
  change is needed for this principle; it's confirmed, not new.
- **Rate, share, and efficiency traits require the participation
  floor** (stage 2 above) — PPG is the one currently implemented
  (`_apply_floor()`, nulled below the sensitivity floor); the same
  rule would apply to any future rate field (e.g. a windowed catch
  rate or `offense_snap_share`) built on top of this module.
- **Meaningful-role thresholds (§2's candidate table) should produce a
  SEPARATE role-status flag, not a filter that removes low-opportunity
  players from the underlying dataset or from raw-trait analyses.**
  None of the candidate thresholds in the table below have been
  implemented as a filter anywhere in the committed code — the table
  is exploratory (which real threshold would flag which real
  population), not a description of rows being removed. If and when a
  meaningful-role flag is built, it should live as its own boolean/
  categorical column alongside the always-present raw fields, e.g.
  `meaningful_role_qualified`, not as a `WHERE` clause applied before
  the raw data is even exposed.
- **No single universal floor across all partial-season traits.**
  Different metrics (PPG vs. snap share vs. targets) and positions
  (QB vs. RB/WR/TE, per §2's finding below) warrant different real
  floors — forcing one threshold to serve every purpose would either
  be too loose for a rate calculation or too strict for a raw
  availability trait.

---

## 1a. Exclusion audit (new, requested before any floor is selected)

Every number below comes from running the real, committed library
functions (`build_team_game_final_n_traits()`,
`build_active_game_final_n_traits()`) against the full real 2006-2025
population (11,175 skill-position player-seasons) — via a new,
tested, NOT YET COMMITTED code change replacing the prior boolean
`team_game_window_applicable` with an explicit
`team_game_window_status` field (see below for why the boolean wasn't
enough).

### 1. Why the active-game population is more than twice the team-game
population — reconciled, not just described

The real driver is a STRUCTURAL zero-slack effect at `n=4`, not
primarily the trade exclusion. For the team-game final-4 window, the
sample floor `active_games ≥ 4` is checked against a window that is
ALWAYS exactly 4 real games — so at `n=4` specifically, clearing the
floor requires real usage in literally ALL 4 of the team's final
games, zero slack. The active-game window has no such constraint: it
can find its 4 qualifying games anywhere across the real season.

Verified directly by re-running both window builders at `n=4/6/8` and
computing the ratio of active-game-qualified to team-game-qualified
player-seasons:

| Window | Team-game qualified (active_games≥4) | Active-game qualified (games≥4) | Ratio |
|---|---|---|---|
| Final 4 (0 games of slack) | 4,115 | 9,126 | **2.22** |
| Final 6 (2 games of slack) | 6,111 | 9,126 | **1.49** |
| Final 8 (4 games of slack) | 7,057 | 9,126 | **1.29** |

The ratio shrinks monotonically as real slack increases — direct,
quantitative confirmation that the zero-slack structural effect, not
some other artifact, drives the gap. Decomposing the 5,011
player-seasons that qualify for active-game-final-4 but not
team-game-final-4: only **298 (5.9%)** are traded players (team-game
inapplicable entirely); the remaining **4,713 (94.1%)** are
SINGLE-TEAM players who had a real 4-game usage stretch somewhere in
the season that did not coincide with their team's specific final 4
games (e.g. productive in September, quiet or inactive down the real
stretch, or the reverse). Trade exclusion is real but secondary.

### 2. Counts excluded from team-game windows, by real cause

`team_game_window_status` (new field, replacing the prior boolean),
real counts at `n=4` across the full population (11,175):

| Status | n | Real meaning |
|---|---|---|
| `applicable` | 10,835 | Single real team identified, that team's real games found |
| `unavailable_traded` | 339 | 2+ distinct real teams this season |
| `unavailable_no_team_evidence` | 1 | Zero real weekly rows this season at all |
| `unavailable_other` | 0 | Defensive catch-all (single team found but that team has no real games in the index) — real, disclosed, simply not triggered by this population |

The single `unavailable_no_team_evidence` case is real and
identifiable: **Travis Hunter (WR, 2025)** — in the master DB
population but with zero real rows in the Source A weekly file this
season. **"No Source B coverage"** is a separate, metric-specific gap,
not a team-game-window-applicability status: `offense_snap_share`
requires Source B, real coverage 2013-2025 only (e.g. of the 1,118
team-game-applicable RB player-seasons, only 719 have any real
2013+ coverage to compute a snap share from at all — the touch-count
metrics from Source A remain available for the full 2006-2025 range
regardless).

### 3. True zero opportunity vs. unavailable data — confirmed
distinct, confirmed represented

Of the 10,835 `applicable` rows (single real team, that team's real
games found), **2,148 (19.8%) have `team_final_n_active_games == 0`**
— a real, meaningful "rostered for the team's real final 4 games, but
zero recorded usage in any of them" fact. These rows are NOT dropped
and NOT confused with `unavailable_*` — they carry
`team_game_window_status == "applicable"`, `team_final_n_games == 4`
(the real window size), and `team_final_n_active_games == 0` (the real
zero-usage fact), fully distinguishable from a genuinely inapplicable
row (which has every numeric field null). A new regression test
(`test_rostered_but_fully_inactive_player_represented_with_zero_not_dropped`)
proves this directly. Remaining applicable-population breakdown: 4,115
meet the primary sample floor (`active_games≥4`); 4,572 have partial
activity (1-3 of the 4 real window games).

### 4/5. Explicit status fields; traded players available elsewhere

`team_game_window_status` (§2 above) now distinguishes every real
non-applicable cause instead of collapsing them into one boolean — a
real, disclosed correction: the prior boolean could not tell a reader
whether a `False`/null row meant "traded" or "never appeared in the
data at all," two very different real situations. Traded players get
`unavailable_traded` for TEAM-GAME windows specifically, and remain
FULLY available elsewhere: a new regression test
(`test_traded_player_still_gets_a_valid_active_game_window`) confirms
`build_active_game_final_n_traits()` never filters by team at all, and
§4's trade-split analysis is built specifically for this population.

---

## 1b. Two deliberately separate rates, not one ambiguous PPG (new
code, tested, not yet committed)

Per instruction: a single "PPG" field conflated two real, different
questions. Every team-game window (final-4/6/8 AND first/second half —
applied consistently, since both use the same underlying aggregation)
now exposes TWO fields instead of one:

- **`*_points_per_team_game`** — real total points ÷ the FIXED team
  window size (`team_final_n_games`, always the real window size, e.g.
  always 4 for a final-4 window). **Never floor-gated.** A real,
  applicable player with zero usage across the whole window gets
  `0.0`, not null — e.g. `team_final_n_points_per_team_game == 0.0`
  for a real zero-active-game applicable row. Verified by two new
  tests: `test_fully_inactive_applicable_window_gets_zero_per_team_game_not_null`
  and `test_below_primary_floor_active_rate_is_nan_but_team_rate_is_not`.
- **`*_points_per_active_game`** — real total points ÷ the real
  ACTIVE-game count (`team_final_n_active_games`). Null when active
  games is 0, and floor-gated below the PRIMARY interpretability floor
  (3 active games — §2b below; a stricter SENSITIVITY flag at 4 is
  exposed separately, never a second nulling gate) — this is the "how
  well did they play when they actually played" rate, and the only one
  of the two where a small real sample makes the number itself
  unstable.

Active-game windows (`build_active_game_final_n_traits()`) keep a
single PPG field — there's no separate "team window size" concept
there, so no ambiguity to resolve.

909/909 tests passing (`python -m pytest tests/ -q --import-mode=importlib`).

---

## 2. Reliability floors: participation floor vs. meaningful-role
floor, distinguished, not one universal threshold

**Minimum-SAMPLE (participation) floor for the WINDOW itself** —
unchanged, already approved: **≥4 active games primary**, **≥3
sensitivity**, below 3 never usable. Checked against `*_active_games`
for team-game windows (not the window size, which is always exactly
N), and against the active-game window's own real count otherwise.
This is stage 2 of §1a-0's three-stage distinction — it governs
whether a RATE (PPG) is interpretable, not whether a player is in the
dataset.

**Two further, distinct concepts for the OPPORTUNITY layer, per
instruction — not one universal floor, and per §1a-1 neither is a
dataset filter**:
- **Participation floor** (for a rate/opportunity metric specifically,
  distinct from the games-based floor above): the lowest real bar
  needed for a metric like `offense_snap_share` to be interpretable —
  excludes a true statistical zero (0-1 real touches) from being
  read as a meaningful rate.
- **Meaningful-role floor**: a real, substantial role, not just
  non-zero involvement — proposed as a future SEPARATE flag (§1a-1),
  never as a row filter.
- A **moderate** middle tier is also shown below, since a binary
  lenient/strict choice would itself be an arbitrary simplification.

**Full compact table, every candidate, all three windows (final-4/6/8)
and both window types (team-game/active-game)**: see
`research/dataset2/PARTIAL_SEASON_FLOOR_CANDIDATE_TABLE_2026_07.md`
(144 real rows) — shown in full in chat for this round. The excerpt
below is the final-4/team-game slice only, kept here for the
QB-sensitivity finding's context.

### Compact decision table — TEAM-GAME final-4 window (base:
`applicable` AND `active_games≥4`), real counts, no selection made

| Position | Metric | Base n | Lenient (participation) | Moderate | Meaningful-role |
|---|---|---|---|---|---|
| QB | attempts | 486 | ≥15: 483 (99.4%) | ≥40: 483 (99.4%) | ≥60: 482 (99.2%) |
| RB | carries | 1,118 | ≥3: 1,049 (93.8%) | ≥8: 975 (87.2%) | ≥15: 844 (75.5%) |
| WR | targets | 1,790 | ≥2: 1,470 (82.1%) | ≥5: 1,385 (77.4%) | ≥8: 1,306 (73.0%) |
| TE | targets | 721 | ≥2: 641 (88.9%) | ≥5: 601 (83.4%) | ≥8: 517 (71.7%) |
| All (general, Source B 2013+ only) | `offense_snap_share` | varies (n with real coverage below) | ≥10% | ≥20% | ≥30% |

**Snap-share tier detail** (n with real 2013+ coverage / retained at
each tier): QB 307 coverage → 306 / 306 / 305; RB 719 → 662 / 591 /
490; WR 1,175 → 1,114 / 1,048 / 996; TE 500 → 496 / 483 / 463.

**Real, disclosed finding: QB's touch/share metrics barely move across
tiers (483→483→482 attempts; 306→306→305 snap-share)** — confirms
§1a's structural point differently: because the team-game `n=4` window
requires ALL 4 games active, a QB who clears the sample floor at all
is already, almost by construction, the real starter. For QB
specifically, the sample-floor decision (§ above) is doing nearly all
the real work; an opportunity overlay adds little. RB/WR/TE show real,
substantial movement across tiers (RB: 93.8%→87.2%→75.5%), where the
opportunity-floor decision matters much more.

**Real era/ADP composition, meaningful-role tier, RB carries≥15 (most
affected position)**: era 2011-2020 n=432, pre-2011 n=214, 2021+
n=198 — roughly proportional to population share. ADP: 300 of 844 no
real market ADP, 173 R6-10, 132 R1-2, 124 R3-5, 115 R11+ — no single
tier disproportionately excluded.

The ACTIVE-GAME window's own equivalent table, and the final-6/final-8
versions of both window types, are computed the same way and included
in full in `PARTIAL_SEASON_FLOOR_CANDIDATE_TABLE_2026_07.md` (and
shown in full in chat this round) — not omitted this time. The real
pattern holds across all of them: retained counts and percentiles grow
with window length; QB's low sensitivity to the opportunity overlay
and RB/WR/TE's higher sensitivity are consistent at every window size
and in both window types. Half-split tables were not recomputed this
round (the exclusion audit and three-window table were the specific
request) — available on request if wanted before threshold approval.

**No floor is selected here.** Per instruction, the lenient/moderate/
meaningful-role distinction is preserved as three genuinely different
concepts, not collapsed for convenience — which tier (or whether
different positions warrant different tiers, e.g. QB not needing an
opportunity overlay at all given the finding above) remains an open
decision.

---

## 2b. Reduced recommendation matrix (proposal — not implemented)

The 144 candidates collapse into three real recommendations, not 144
separate choices. **Raw production, raw opportunity, availability,
role-loss, and per-team-game rates get NO participation floor
anywhere in this matrix** — that principle (§1a-1) already governs the
committed code and isn't repeated as a "floor" below.

### 1. Per-active-game rate interpretability floor — ONE recommendation
for all three windows, not one per window

**Recommended: primary = 3 active games, sensitivity = 4 active
games, applied FLAT to final-4, final-6, AND final-8 (not scaled up
with window size).**

Your instinct (3 primary / 4 stricter) is **confirmed by the real
table, not challenged** — with one clarification: keeping both numbers
FLAT across window sizes, rather than scaling either up, is itself the
right way to satisfy "scale proportionally rather than requiring
perfect attendance by default." A flat absolute floor becomes
*relatively* more lenient as the window grows (4-of-4 = 100%
attendance at n=4, but 4-of-8 = only 50% attendance at n=8) — exactly
the direction "don't punish larger windows" should point.

| Window | Floor | Retained (of applicable) | Why this level, not the adjacent one |
|---|---|---|---|
| Final-4 | primary ≥3 | 5,939 (54.8%) | The already-approved project-wide "fewer than 3 games is never usable" floor (roadmap §6, from the original real retained-count analysis), reapplied here to active games specifically. Real, substantial gap vs. ≥4 (1,824 real player-seasons, 16.8 pts) — NOT a rounding difference, confirming 3 vs. 4 is a real, worthwhile distinction to keep separate. |
| Final-4 | sensitivity ≥4 | 4,115 (38.0%) | Full attendance is only demanding here because the window itself is small (4 games) — coincides with "no misses at all," which is a real, meaningfully stricter but not devastating cohort (still 4,115 real seasons). |
| Final-6 | primary ≥3 | 7,145 (65.9%) | Same absolute floor. Requiring the SAME 3-game minimum as final-4 costs nothing extra here — a real 3-game sample is equally interpretable regardless of the window it was drawn from. |
| Final-6 | sensitivity ≥4 | 6,111 (56.4%) | A real, substantially higher bar than primary (66%→56%) without approaching perfect attendance (would be ≥6, retaining only 3,405 / 31.4% — confirmed too punishing, see §ii below). |
| Final-8 | primary ≥3 | 7,839 (72.3%) | Same reasoning — flat floor, real interpretable sample regardless of window length. |
| Final-8 | sensitivity ≥4 | 7,057 (65.1%) | Meaningfully stricter than primary without the perfect-attendance cliff (≥8 retains only 2,895 / 26.7% — confirmed too punishing). |

**§ii — why NOT perfect attendance for final-6/8, confirmed with real
numbers**: requiring `active_games == window_size` retains only 31.4%
(final-6) and 26.7% (final-8) of the applicable population, roughly
HALF what the flat sensitivity floor (≥4) retains. A single missed
game for an ordinary reason (a coach's rest decision in a blowout, a
minor in-season tweak) would wrongly disqualify an otherwise clearly
startable player from the stricter cohort at these longer windows —
exactly the outcome your instruction warned against.

**ADP/era impact**: no material change at either floor, any window.
Real composition stays close to proportional (e.g. final-4 primary:
era 2011-2020/2021+/pre-2011 = 2,981/1,512/1,446 vs. the population's
own roughly 50/28/22 split; ADP: R1-2 349/5,939 = 5.9% at primary vs.
267/4,115 = 6.5% at sensitivity — moving the floor does not
disproportionately gain or lose early-round players at any window).

### 2/3. SUPERSEDED 2026-07 — efficiency-volume and meaningful-role
thresholds below were rejected as too low, kept for the record, not
deleted

The two tables that originally lived here (position/metric minimum
volumes for efficiency calculations, and one flat meaningful-role
threshold per role type: QB attempts ≥15, RB carries ≥3, WR/TE targets
≥2 for efficiency; RB carries ≥15 or WR/TE targets ≥8 for meaningful
role) were reviewed and **rejected, per instruction**: they establish
mathematical computability (a nonzero denominator), not reliable
efficiency or a meaningful role, and a single flat total is
particularly wrong applied unchanged across final-4/6/8 windows (a
"≥15 carries" bar means something very different in a 4-game window
than an 8-game one). Kept here as a real record of a rejected
approach, per this project's standing rule against silently discarding
decision history, rather than deleted. Superseded by §2c/§2d/§2e below,
which separate three concepts (minimal computability, efficiency
reliability via real split-half stability analysis, and meaningful
role via continuous per-game/snap-share measures) instead of
conflating them into "% of population retained."

---

## 2c. Concept 1 — minimal computability (not implemented, not a floor)

A rate is computable whenever its real denominator is nonzero — 1
carry, 1 target, 1 attempt is enough to produce a number. This is
already true of every raw opportunity field this module exposes (no
code change needed): nothing prevents computing `receiving_yards /
targets` for a 1-target player today. **Preserve the calculation where
useful — e.g. as an input to a larger aggregate — but never label a
computability-only rate "reliable" or "interpretable."** This concept
gets no threshold and no flag; it's the floor below which nothing
(concepts 2 or 3) applies. Stated explicitly here because the
superseded §2/§3 tables silently equated "computable" with
"reliable" — exactly the conflation being corrected.

---

## 2d. Concept 2 — efficiency SAMPLE-ELIGIBILITY, from real odd/even-week
OBSERVED HISTORICAL STABILITY — NOT a statistical-reliability estimate

**Terminology correction, per instruction**: the odd/even-week split
below is described as OBSERVED HISTORICAL STABILITY, not a pure
statistical-reliability estimate. A formal reliability estimate (in
the classical psychometric sense) assumes the underlying quantity is
otherwise constant and only the MEASUREMENT is noisy. That assumption
doesn't hold here: the real odd/even split also captures real changes
in role, injury status, starting QB, and opponent across a season —
so part of any observed instability is a real change in the player's
actual circumstances, not just sampling noise in the metric. The two
sample-eligibility levels below (§below) are correspondingly labeled
**sample-eligibility levels**, not proof either level makes the metric
reliable.

**Method** (unchanged): for every real player-season 2006-2025, split
real games into ODD-week and EVEN-week halves (a clean, order-
independent, real split — not the partial-season windows themselves,
which are about lag/timing, not stability measurement). Compute the
efficiency metric independently on each half, band players by real
TOTAL SEASON volume, and report two real, complementary signals per
band:
- **Split-half correlation** (Pearson r between the odd-half and
  even-half rate, across players in the band) — does this metric
  rank-order players consistently between two independent real
  samples? (Real role/injury/QB/opponent change across the season
  means this is an OBSERVED historical pattern, not a pure
  measurement-reliability figure.)
- **Coefficient of variation** (real season-level rate's std ÷ mean
  across players in the band, or raw std when the mean is near zero —
  see the QB note below) — a second, real, complementary signal: how
  extreme/volatile is the metric itself at this volume, regardless of
  whether it correlates across samples?

**Honest finding, stated up front**: split-half correlation for these
football rate stats is genuinely modest even at high real volume —
never approaching the 0.7+ that would usually be called "highly
reliable" in a classical psychometric sense. This is a real property
of these metrics (yards-per-carry, yards-per-target, and similar
per-touch rates are known to be volatile in real football, and the
season also brings real role/injury/QB/opponent churn — not an
artifact of this method) — **the levels below mark where the metric
becomes MINIMALLY worth reading at all, not where it becomes highly
predictive**, and per instruction, it remains acceptable and expected
for efficiency traits to stay unavailable (or eligible only at the
weaker "exploratory" level) for many real low-volume players.

**APPROVED AND IMPLEMENTED 2026-07** (`build_team_game_efficiency_traits()`/
`build_active_game_efficiency_traits()`, `config.py`'s
`DATASET2_EFFICIENCY_VOLUME_EXPLORATORY`/`_SENSITIVITY`): two real
eligibility levels, EXPLORATORY MINIMUM and HIGHER-VOLUME SENSITIVITY,
computed from the real window's own opportunity count (not the season
total used to build the tables below) and exposed as two separate
boolean flags per window (`*_efficiency_volume_eligible_exploratory`/
`_sensitivity`) — never a filter, the real opportunity/production
counts and the rate itself (whenever the real denominator is nonzero)
stay visible regardless of either flag.

### QB passing efficiency (EPA per attempt)

| Volume band (season attempts) | n (usable, nonzero both halves) | Split-half r | Season-rate mean | Season-rate std |
|---|---|---|---|---|
| 1-9 | 34 | -0.08 | -0.27 | 0.80 |
| 10-24 | 54 | 0.33 | -0.41 | 0.68 |
| 25-49 | 88 | 0.18 | -0.20 | 0.35 |
| 50-99 | 137 | 0.21 | -0.15 | 0.26 |
| 100-199 | 179 | 0.16 | -0.13 | 0.17 |
| 200+ | 695 | 0.50 | 0.04 | 0.15 |

QB's real mean sits near zero, so CV is misleading (division by a
near-zero mean exaggerates the ratio) — **raw std is the right signal
here**, and it drops cleanly and monotonically (0.80 → 0.15) as volume
rises. Split-half r also strengthens materially by the 200+ band
(0.50, the only band with a real, non-trivial historical pattern).
**Approved: exploratory minimum ≥50 real attempts** (std already down
to ~1/3 of the lowest band, a real, meaningful stabilization),
**higher-volume sensitivity ≥150 attempts** (real std continuing to
shrink, closer to where r itself becomes non-trivial). Given QB's
games floor already self-selects real starters (§1a), 50+ attempts is
reached quickly in practice — not a practically restrictive floor.

### RB rushing efficiency (yards per carry)

| Volume band (season carries) | n | Split-half r | Mean | CV |
|---|---|---|---|---|
| 1-4 | 66 | 0.02 | 3.15 | 0.85 |
| 5-14 | 281 | 0.08 | 3.80 | 0.67 |
| 15-29 | 320 | 0.07 | 3.90 | 0.34 |
| 30-59 | 401 | 0.17 | 4.13 | 0.27 |
| 60-119 | 490 | 0.22 | 4.15 | 0.19 |
| 120+ | 781 | 0.26 | 4.28 | 0.14 |

CV roughly halves between the lowest bands and 15-29 carries (0.85/0.67
→ 0.34), then keeps improving gradually. **Approved: exploratory
minimum ≥15 real carries** (the first band with real, meaningful
stabilization), **higher-volume sensitivity ≥60 carries** (CV under
0.2, the clearest further inflection).

### RB receiving efficiency (yards per target)

| Volume band (season targets) | n | Split-half r | Mean | CV |
|---|---|---|---|---|
| 1-4 | 170 | -0.06 | 5.02 | 0.80 |
| 5-14 | 522 | 0.08 | 5.43 | 0.46 |
| 15-29 | 451 | 0.05 | 5.75 | 0.32 |
| 30-59 | 513 | 0.10 | 5.82 | 0.23 |
| 60+ | 202 | 0.03 | 6.17 | 0.17 |

Same real pattern, correlation weaker throughout (receiving-back
volume is real but small for most RBs). **Approved: exploratory
minimum ≥15 real targets, higher-volume sensitivity ≥30 targets.**

### WR/TE receiving efficiency (yards per target)

| Position | Volume band | n | Split-half r | Mean | CV |
|---|---|---|---|---|---|
| WR | 1-4 | 149 | 0.94* | 10.07 | 3.45* |
| WR | 5-14 | 501 | 0.00 | 6.72 | 0.54 |
| WR | 15-29 | 488 | 0.19 | 6.93 | 0.36 |
| WR | 30-59 | 705 | 0.15 | 7.38 | 0.25 |
| WR | 60-119 | 914 | 0.21 | 7.92 | 0.19 |
| WR | 120+ | 334 | 0.26 | 8.24 | 0.15 |
| TE | 1-4 | 152 | 0.10 | 6.15 | 0.83 |
| TE | 5-14 | 462 | 0.00 | 6.23 | 0.46 |
| TE | 15-29 | 349 | 0.08 | 6.87 | 0.29 |
| TE | 30-59 | 366 | 0.21 | 7.20 | 0.23 |
| TE | 60+ | 395 | 0.21 | 7.44 | 0.17 |

*The WR 1-4-target band's r=0.94 is a real, disclosed ARTIFACT, not a
genuine finding — its CV (3.45) is the highest of any band in this
whole analysis, meaning the "high correlation" comes from a handful of
extreme, coincidental ratios (e.g. 1 target for a long touchdown in
each half) at a volume too low to mean anything. **This is exactly why
a single correlation number should never be read alone** — always
check the CV alongside it, per instruction.

**Approved, exploratory minimum ≥15 real targets for both positions;
higher-volume sensitivity DIFFERS by position**: **WR ≥40 targets**,
**TE ≥30 targets** — WR's real CV curve is still descending more
steeply through the 30-59 band (0.36→0.25) than TE's (0.29→0.23) at
the same volume, so WR is held to a real, slightly higher bar for the
stronger level rather than defaulting both positions to the same
number. Both real curves cross below ~0.25 CV close to where §2e's
meaningful-role candidates also land — a real, independent convergence
between the two different questions, not a coincidence to ignore, but
kept as two SEPARATE concepts per instruction (sample-eligibility here
vs. role substance in §2e), not merged into one threshold.

---

## 2e. Concept 3 — meaningful role, from continuous per-game measures,
not one flat total

Per instruction, no flat total threshold. Every candidate below is a
**continuous, per-game (or snap-share) rate** — proposed for further
discussion, no specific cutoff selected yet.

**Proposed continuous measures**:
- QB: pass attempts per active game
- RB: carries per team game AND per active game (both — they diverge
  meaningfully; team-game reflects real role even through inactive
  weeks, active-game reflects role when actually playing)
- WR/TE: targets per team game AND per active game
- All positions: `offense_snap_share` (already position-normalized,
  Source B 2013+ only)

**Real percentiles, team-game windows, base = primary-floor-qualified
(active_games≥3)**:

| Window | QB attempts/team-game (50th/90th) | RB carries/team-game (50th/90th) | WR targets/team-game (50th/90th) | TE targets/team-game (50th/90th) |
|---|---|---|---|---|
| Final-4 | 30.0 / 38.8 | 7.0 / 17.5 | 3.5 / 8.3 | 2.3 / 6.5 |
| Final-6 | 27.5 / 37.5 | 5.7 / 16.5 | 2.8 / 7.8 | 1.7 / 5.8 |
| Final-8 | 25.3 / 37.3 | 4.9 / 15.8 | 2.5 / 7.5 | 1.4 / 5.5 |

**Real finding confirming why per-game beats a flat total**: the
per-game rate's central tendency drifts only modestly across window
lengths (RB median carries/team-game: 7.0 → 5.7 → 4.9 for final-4/6/8
— some real drift from mixing in additional real games, but nowhere
near proportional to window length the way a flat total necessarily
is).

**Concrete classification-instability demonstration, requested**:
comparing a flat total (`carries≥15`) against a per-team-game rate
(`carries/team-game≥2.5`) for the SAME real RB population at each
window:

| Window | Flat ≥15 total | Rate ≥2.5/team-game | Both | Flat-only | Rate-only |
|---|---|---|---|---|---|
| Final-4 | 1,083 (68.0%) | 1,223 (76.8%) | 1,083 | 0 | **140** |
| Final-6 | 1,350 (70.6%) | 1,350 (70.6%) | 1,350 | 0 | 0 |
| Final-8 | 1,501 (72.7%) | 1,390 (67.3%) | 1,390 | **111** | 0 |

At final-4, the flat total is stricter than the rate (real 3.75
carries/game needed to clear 15 in only 4 games) — 140 real players
with a genuine ≥2.5/game role get WRONGLY excluded by the flat bar. At
final-8, the flat total flips to being LOOSER than the rate (15
carries over 8 games is only 1.875/game) — 111 real players with a
genuinely low per-game role get WRONGLY included. The two measures
only coincide at final-6 (15/6 = exactly 2.5/game) — a coincidence of
that specific window length, not evidence the flat total is sound in
general. This is real, concrete proof the flat-total approach silently
changes what "meaningful role" means depending on which window it's
applied to, exactly as instructed to check.

**Not yet selected**: which per-game/snap-share level constitutes
"meaningful," and whether team-game or active-game denominator (or
both, exposed separately) is the right basis per position.

**2026-07 status**: a first pass at this matrix (using a single
primary/sensitivity pair per role type) was reviewed and **rejected as
labeled** — most of the proposed "primary" thresholds identify
recurring involvement, not a fantasy-meaningful role, and several
"sensitivity" levels (RB rushing especially) were judged still too
low to represent a strong/lead role. Reworked below into three
concepts, per instruction. **The revised three-tier matrix below is
APPROVED AND IMPLEMENTED** (`build_team_game_role_traits()`,
`build_active_game_role_traits()`, `build_team_game_snap_share_role_traits()`
in `lib/dataset2/partial_season_traits.py`; `config.py`'s
`DATASET2_ROLE_THRESHOLDS_TEAM_GAME`/`_ACTIVE_GAME`/`_SNAP_SHARE`) with
the exact thresholds shown per position/metric below.

### Three-tier role classification — APPROVED AND IMPLEMENTED

1. **Role present** — recurring but potentially peripheral involvement
   (the old "primary" candidates, retained largely as-is where not
   otherwise noted).
2. **Meaningful role** — enough opportunity to plausibly matter for
   fantasy production.
3. **Strong/lead role** — starter-level or high-value involvement.

Per-team-game and per-active-game stay **separate, non-merged**
measures throughout, per instruction. Retained counts are shown across
final-4/6/8; composition is era/ADP-bucket counts among qualifiers at
final-4 (ADP-bucket counts undercount the qualifying population since
most player-seasons in this dataset have no real market ADP —
undrafted/deep-league players are common at the lower tiers); examples
are real player-seasons across the full 2006-2025 population within a
narrow band on each side of the cutoff (not limited to 2023, to give a
fuller and more recognizable set of names — sourced the same way as
the earlier round's 2023-only examples).

**QB passing role**

| Basis | Role present | Meaningful | Strong/lead |
|---|---|---|---|
| attempts/active-game | **≥ 20** | **≥ 25** | **≥ 30** |

- Retained (base 1,525 QB active-game rows): final-4 970 (63.6%) /
  793 (52.0%) / 531 (34.8%); final-6 978 (64.1%) / 819 (53.7%) / 539
  (35.3%); final-8 984 (64.5%) / 832 (54.6%) / 540 (35.4%). Stable
  across window length.
- Composition, final-4: role-present era 2011-2020/2021+/pre-2011 =
  474/251/245, ADP (of the minority with a real market ADP) R6-10 186,
  R11+ 157, R3-5 74, R1-2 31. Strong/lead era 297/125/109, ADP R6-10
  125, R11+ 90, R3-5 53, R1-2 22 — composition shifts only modestly
  tier to tier; no tier is disproportionately early-round or
  late-round.
- Examples: role-present cutoff (20) — just below, **Andy Dalton**
  (2022, 19.75), **Gus Frerotte** (2007, 19.75); just above, **Tyler
  Huntley** (2022, 20.0), **J.T. O'Sullivan** (2008, 20.0). Meaningful
  cutoff (25) — just below, **Colt McCoy** (2021, 24.75); just above,
  **Jake Plummer** (2006, 25.0), **Deshaun Watson** (2024, 25.0).
  Strong/lead cutoff (30) — just below, **Robert Griffin III** (2013,
  29.75), **Aaron Rodgers** (2022, 29.75); just above, **Kerry
  Collins** (2006, 30.0), **Blaine Gabbert** (2012, 30.0). The
  strong/lead tier includes real spot-starter/backup seasons alongside
  clear starters (Gabbert, Collins) — a reminder that a 4-game snapshot
  of attempts/active-game measures same-season role, not career
  quality.

**RB rushing role**

| Basis | Role present | Meaningful | Strong/lead |
|---|---|---|---|
| carries/team-game | **≥ 2.0** | **≥ 5.0** | **≥ 10.0** |
| carries/active-game | **≥ 3.0** | **≥ 7.0** | **≥ 12.0** |

- Team-game retained (base 2,787): final-4 1,494 (53.6%) / 1,033
  (37.1%) / 593 (21.3%); final-6 1,507 (54.1%) / 1,028 (36.9%) / 578
  (20.7%); final-8 1,512 (54.3%) / 1,027 (36.8%) / 585 (21.0%).
- Active-game retained (base 2,908): final-4 1,854 (63.8%) / 1,176
  (40.4%) / 646 (22.2%); final-6 1,874 (64.4%) / 1,163 (40.0%) / 655
  (22.5%); final-8 1,882 (64.7%) / 1,152 (39.6%) / 650 (22.4%).
- Composition, team-game final-4: role-present era 751/387/356
  (2011-2020/2021+/pre-2011), ADP R6-10 276, R1-2 196, R3-5 191, R11+
  183. Strong/lead era 295/140/158, ADP **R1-2 161** (now the largest
  ADP group, up from 4th at role-present) — a real, meaningful
  composition shift: the strong/lead tier concentrates real early-round
  draft capital much more than role-present does, exactly the pattern
  you'd expect from a genuine lead-back cutoff.
- Examples, team-game basis: role-present cutoff (2.0) — just below,
  **D'Onta Foreman** (2018, 1.75); just above, **Cordarrelle Patterson**
  (2013, 2.0), **Leon Washington** (2014, 2.0). Meaningful cutoff (5.0)
  — just below, **Doug Martin** (2017, 4.75), **Jerick McKinnon**
  (2022, 4.75); just above, **Dion Lewis** (2018, 5.0). Strong/lead
  cutoff (10.0) — just below, **Tevin Coleman** (2016, 9.75), **Michael
  Carter** (2025, 9.75); just above, **Joe Mixon** (2024, 10.0),
  **De'Von Achane** (2023, 10.0) — real, recognizable lead backs
  landing right at the strong/lead line.
- Examples, active-game basis: meaningful cutoff (7.0) — just below,
  **LaMichael James** (2012, 6.75); just above, **Devontae Booker**
  (2016, 7.0), **Mike Davis** (2015, 7.0). Strong/lead cutoff (12.0) —
  just below, **Justin Forsett** (2015, 11.75); just above, **Josh
  Jacobs** (2025, 12.0), **Dion Lewis** (2016, 12.0).
- The team-game vs. active-game split remains real and expected (§2e
  above): a committee back or one returning from injury reads lower on
  the team-game basis than the active-game basis, since the team-game
  denominator counts weeks he didn't play.

**RB receiving role**

| Basis | Role present | Meaningful | Strong/lead |
|---|---|---|---|
| targets/team-game | **≥ 1.0** | **≥ 2.0** | **≥ 3.0** |
| targets/active-game | **≥ 1.0** | **≥ 2.0** | **≥ 3.0** |

- Team-game retained (base 2,787): final-4 1,074 (38.5%) / 646 (23.2%)
  / 384 (13.8%); final-6 1,075 (38.6%) / 644 (23.1%) / 370 (13.3%);
  final-8 1,074 (38.5%) / 649 (23.3%) / 366 (13.1%).
- Active-game retained (base 2,908): final-4 1,591 (54.7%) / 973
  (33.5%) / 571 (19.6%); final-6 1,583 (54.4%) / 959 (33.0%) / 562
  (19.3%); final-8 1,582 (54.4%) / 965 (33.2%) / 565 (19.4%).
- Composition, team-game final-4: role-present ADP R6-10 201, R1-2
  161, R3-5 152, R11+ 122; strong/lead ADP **R1-2 99** becomes the
  largest group (was 2nd at role-present) — real, if less pronounced
  than the rushing-role shift, since receiving work concentrates in a
  real subset of early-round pass-catching backs.
- Examples, team-game basis: role-present cutoff (1.0) — just below,
  **Royce Freeman** (2020, 0.75), **Josh Jacobs** (2019, 0.75); just
  above, **Joe Mixon** (2017, 1.0), **Frank Gore** (2019, 1.0).
  Meaningful cutoff (2.0) — just below, **Cedric Benson** (2009, 1.75);
  just above, **Khalil Herbert** (2023, 2.0). Strong/lead cutoff (3.0)
  — just below, **Alfred Blue** (2018, 2.75); just above, **Chester
  Taylor** (2009, 3.0), **Jerick McKinnon** (2015, 3.0).
- These per-game numbers stay modest even at strong/lead (3.0
  targets/game ≈ 12 targets over a 4-game window) — real, and
  consistent with RBs rarely leading receiving volume the way WR/TE do;
  a 3.0-target/game back is nonetheless a real, meaningfully-involved
  pass-catching option, not a marginal one.

**WR receiving role**

| Basis | Role present | Meaningful | Strong/lead |
|---|---|---|---|
| targets/team-game | **≥ 2.0** | **≥ 4.0** | **≥ 6.0** |
| targets/active-game | **≥ 3.0** | **≥ 5.0** | **≥ 7.0** |

- Team-game retained (base 4,174): final-4 1,751 (42.0%) / 1,178
  (28.2%) / 642 (15.4%); final-6 1,764 (42.3%) / 1,163 (27.9%) / 639
  (15.3%); final-8 1,780 (42.6%) / 1,156 (27.7%) / 634 (15.2%).
- Active-game retained (base 4,338): final-4 2,025 (46.7%) / 1,242
  (28.6%) / 620 (14.3%); final-6 2,017 (46.5%) / 1,233 (28.4%) / 617
  (14.2%); final-8 2,012 (46.4%) / 1,221 (28.1%) / 596 (13.7%).
- Composition, team-game final-4: role-present ADP R6-10 301, R3-5
  219, R11+ 211, R1-2 132; strong/lead ADP shifts toward **R3-5 150**
  becoming the largest group, R1-2 rising to 107 (from last place) —
  a real, meaningful early-round concentration at the top tier.
- Examples, team-game basis: role-present cutoff (2.0) — just below,
  **Marquise Goodwin** (2021, 1.75); just above, **Ted Ginn** (2018,
  2.0). Meaningful cutoff (4.0) — just below, **Torry Holt** (2009,
  3.75), **Dez Bryant** (2015, 3.75); just above, **Kenny Britt**
  (2015, 4.0). Strong/lead cutoff (6.0) — just below, **Kelvin
  Benjamin** (2016, 5.75), **Anquan Boldin** (2016, 5.75); just above,
  **Donald Driver** (2009, 6.0), **Allen Hurns** (2015, 6.0).
- Examples, active-game basis: meaningful cutoff (5.0) — just below,
  **Adam Thielen** (2018, 4.75), **JuJu Smith-Schuster** (2019, 4.75);
  just above, **Isaac Bruce** (2009, 5.0). Strong/lead cutoff (7.0) —
  just below, **John Brown** (2014, 6.75); just above, **Reggie
  Wayne** (2009, 7.0), **Doug Baldwin** (2014, 7.0) — real, clearly
  lead-WR seasons landing right at the strong/lead line, a good sign
  the cutoff is tracking a real distinction.

**TE receiving role**

| Basis | Role present | Meaningful | Strong/lead |
|---|---|---|---|
| targets/team-game | **≥ 1.5** | **≥ 3.0** | **≥ 5.0** |
| targets/active-game | **≥ 2.0** | **≥ 4.0** | **≥ 6.0** |

- Team-game retained (base 2,363): final-4 856 (36.2%) / 501 (21.2%)
  / 242 (10.2%); final-6 851 (36.0%) / 490 (20.7%) / 236 (10.0%);
  final-8 854 (36.1%) / 493 (20.9%) / 224 (9.5%).
- Active-game retained (base 2,403): final-4 1,037 (43.2%) / 493
  (20.5%) / 213 (8.9%); final-6 1,032 (42.9%) / 491 (20.4%) / 205
  (8.5%); final-8 1,031 (42.9%) / 491 (20.4%) / 202 (8.4%).
- Composition, team-game final-4: role-present ADP R11+ 105, R6-10
  103, R3-5 49, R1-2 11; strong/lead ADP R6-10 59, R11+ 45, R3-5 33,
  R1-2 8 — TE draft capital stays concentrated in the mid-to-late
  rounds across all tiers, a real, disclosed reflection of how TEs are
  drafted in this era mix (few real early-round TE seasons in the
  underlying population to begin with).
- Examples, team-game basis: role-present cutoff (1.5) — just below,
  **Cameron Brate** (2022, 1.25); just above, **Dwayne Allen** (2015,
  1.5). Meaningful cutoff (3.0) — just below, **Greg Olsen** (2019,
  2.75); just above, **Cade Otton** (2023, 3.0). Strong/lead cutoff
  (5.0) — just below, **O.J. Howard** (2019, 4.75), **Dalton Kincaid**
  (2023, 4.75); just above, **David Njoku** (2018, 5.0), **Hayden
  Hurst** (2020, 5.0).
- Examples, active-game basis: meaningful cutoff (4.0) — just below,
  **Austin Hooper** (2018, 3.75); just above, **Jace Amaro** (2016,
  4.0). Strong/lead cutoff (6.0) — just below, **Hunter Henry** (2017,
  5.75); just above, **Greg Olsen** (2009, 6.0), **Noah Fant** (2024,
  6.0).

**Offensive snap role** (team-game basis, `offense_snap_share`,
Source B 2013+ coverage only)

| Position | Role present | Meaningful | Strong/lead |
|---|---|---|---|
| QB | **≥ 0.30** | **≥ 0.60** | **≥ 0.80** |
| RB | **≥ 0.20** | **≥ 0.45** | **≥ 0.60** |
| WR | **≥ 0.30** | **≥ 0.55** | **≥ 0.70** |
| TE | **≥ 0.30** | **≥ 0.50** | **≥ 0.65** |

- Retained, QB (base 758/827/880 final-4/6/8): role-present 76.6% /
  75.1% / 74.8%; meaningful 67.4% / 65.8% / 64.3%; strong/lead 57.9% /
  56.2% / 55.5%.
- Retained, RB (base 1,508/1,584/1,671): role-present 62.2% / 60.9% /
  58.9%; meaningful 28.8% / 28.3% / 26.6%; strong/lead 13.4% / 12.4% /
  12.3%.
- Retained, WR (base 2,315/2,460/2,550): role-present 66.6% / 64.7% /
  63.8%; meaningful 47.9% / 45.7% / 44.5%; strong/lead 32.6% / 32.2% /
  30.6%.
- Retained, TE (base 1,367/1,433/1,470): role-present 64.7% / 63.4% /
  63.4%; meaningful 38.3% / 38.1% / 37.3%; strong/lead 23.8% / 22.1% /
  22.2%.
- Composition, final-4: RB strong/lead ADP shifts sharply toward **R1-2
  82** (largest group, from 3rd at role-present) — the clearest
  composition shift of any position, matching a real lead-back
  identification. WR strong/lead ADP spreads more evenly (R6-10 161,
  R3-5 137) — snap share alone doesn't isolate the true WR1 as sharply
  as it does the workhorse RB, a real, disclosed finding rather than a
  flaw (WR usage is more target-share-driven than snap-share-driven at
  the top).
- Examples: QB strong/lead (0.80) — just below, **Mike Glennon**
  (2020, 0.796); just above, **Drew Lock** (2021, 0.801), **Sam
  Howell** (2023, 0.801). RB strong/lead (0.60) — just below, **Miles
  Sanders** (2019, 0.599); just above, **Austin Ekeler** (2021, 0.600),
  **Rex Burkhead** (2016, 0.600). WR strong/lead (0.70) — just below,
  **DeVonta Smith** (2021, 0.699), **Alshon Jeffery** (2015, 0.699);
  just above, **Randall Cobb** (2016, 0.700), **Tyler Boyd** (2016,
  0.700). TE strong/lead (0.65) — just below, **Evan Engram** (2018,
  0.648); just above, **Pat Freiermuth** (2021, 0.650), **Dawson
  Knox** (2019, 0.651).
- Retained shares decline gradually across final-4/6/8 rather than
  collapsing, the same rate-based stability seen throughout this
  section — expected, not a new finding.

**APPROVED AND IMPLEMENTED 2026-07**: every threshold above is now
built as a real, tested role-tier classification --
`build_team_game_role_traits()`/`build_active_game_role_traits()`
(QB/RB/WR/TE opportunity-per-game metrics) and
`build_team_game_snap_share_role_traits()` (position-specific snap
share) in `lib/dataset2/partial_season_traits.py`, thresholds sourced
from `config.py`'s `DATASET2_ROLE_THRESHOLDS_TEAM_GAME`/`_ACTIVE_GAME`/
`_SNAP_SHARE`. Per instruction: (1) these are PREDEFINED DATASET 2
RESEARCH CLASSIFICATIONS, not a claim that real opportunity changes
discontinuously at the exact cutoff -- downstream analysis should read
the continuous rate alongside the tier flags, with sensitivity checks
around a cutoff where it matters; (2) team-game and active-game
classifications stay fully separate, never merged, for every metric
that has both bases; (3) no metric's tier flags are combined with any
other metric's into one overall `meaningful_role`/`strong_role` label
-- a player's snap-share role, rushing role, and receiving role are
independently readable, and a divergence between them (e.g. a strong
active-game role without sustained team-game availability) is a real,
preserved finding, not resolved or averaged away; (4) for WR
specifically, `offense_snap_share` establishes real participation but
does not identify receiving hierarchy -- read alongside the separate
WR receiving-role targets thresholds, never as a substitute (see
module docstring). Any future COMPOSITE concept (e.g. a "three-down
RB" label combining rushing + receiving + snap-share roles) is a
deliberate, separate interaction hypothesis to test on its own merits
-- not an automatic consequence of this implementation, and not
attempted here.

---

## 3. What each candidate threshold would flag differently (not
"exclude" — see §1a-0)

The real "decoy" case is still present on the corrected data: the
10th-percentile WR/TE in the team-game final-4 `active_games≥4`
population has **zero** real targets despite real usage in all 4 of
the team's final games (a real complementary/decoy role, fully present
in the raw dataset per §1a-1). Even the lenient candidate (≥2 targets)
would separate out a real, non-trivial slice of this population if
built as a role-status flag.

---

## 4. Trade splits — coverage-limited research, three-way counts
preserved

**339 real traded skill-position player-seasons, 2006-2025** (WR 164,
RB 121, TE 40, QB 14).

| Floor | Before-side only | After-side only | Both sides | Neither side | Total |
|---|---|---|---|---|---|
| Primary (≥4) | 60 | 88 | **105** | 86 | 339 |
| Sensitivity (≥3) | 52 | 81 | **152** | 54 | 339 |

Direct before/after conclusions require BOTH sides independently
qualifying (105 of 339, 31%, at the primary floor) — the standard is
not loosened to inflate this number. Before-only/after-only groups
remain real and reportable for one-sided questions only.

---

## 5. Deferred event-based splits

**Starter/promotion splits remain approved but deferred** until the
depth-chart source is extended to weekly resolution.

**The teammate-injury proxy is NOT being implemented as an injury
trait.** The tested usage-absence proxy caught only 13 of 634 real
team-seasons (2%) — insufficient, and it must not be labeled "injury"
without real injury evidence, which this project does not have wired
in. A future TEAMMATE-ABSENCE variable (not framed as injury) may be
tested separately on its own merits — not scoped further here.

---

## 6. Not buildable now

Usage before/after bye (needs real schedule data), points after
coaching change (no data source), usage with/without starting QB and
RB-committee games (need weekly depth-chart resolution), production
excluding injury-limited/return-from-injury games (needs real injury
data).

---

## 7. No leakage — design constraint, unchanged

Whatever final family #9 features are eventually built get computed as
season-N raw values, then strictly lagged via `lag_join()` to produce
`prior_season_team_final_4_games_ppg`, etc. Not implemented in this
proposal.

---

## Stop point

**Committed**: §0/§1 bug fix and window redesign (`c79eea0`); §1a
exclusion audit and `team_game_window_status` (`292d7d2`); §1b's
per-team-game/per-active-game rate split and the flat 3-primary/4-
sensitivity active-game interpretability floor (an earlier round);
the active-game floor constant rename to explicit,
non-"swap"-dependent names (`667f633`); §2d's efficiency
sample-eligibility flags (`7f2b8bf`) — `build_team_game_efficiency_traits()`
and `build_active_game_efficiency_traits()` in
`lib/dataset2/partial_season_traits.py`, using the approved exact
thresholds (`config.py`'s `DATASET2_EFFICIENCY_VOLUME_EXPLORATORY`/
`_SENSITIVITY`: QB ≥50/≥150 attempts; RB rushing ≥15/≥60 carries; RB
receiving ≥15/≥30 targets; WR receiving ≥15/≥40 targets; TE receiving
≥15/≥30 targets), neutral "eligible" terminology throughout, raw
volumes/rates never gated or deleted by either flag; §2e's three-tier
meaningful-role classification (this round) — **role present**
(recurring but potentially peripheral), **meaningful role** (enough
opportunity to plausibly matter for fantasy production), **strong/lead
role** (starter-level or high-value involvement) — implemented in
`build_team_game_role_traits()`/`build_active_game_role_traits()`
(QB passing attempts; RB carries and targets; WR/TE targets, each on
team-game AND active-game bases, kept fully separate) and
`build_team_game_snap_share_role_traits()` (position-specific
`offense_snap_share`, team-game basis), thresholds in `config.py`'s
`DATASET2_ROLE_THRESHOLDS_TEAM_GAME`/`_ACTIVE_GAME`/`_SNAP_SHARE`
exactly as approved. No metric's tier flags are combined into one
overall role label; raw opportunity counts and continuous per-game/
share rates stay fully visible regardless of tier. 81/81 tests in
this file; full suite 959/959
(`python -m pytest tests/ -q --import-mode=importlib`).

**Deliberately not built this round**: any COMPOSITE role concept
(e.g. a "three-down RB" label combining rushing + receiving +
snap-share roles) — per instruction, a future interaction hypothesis
to test on its own merits, not an automatic consequence of this
implementation.
