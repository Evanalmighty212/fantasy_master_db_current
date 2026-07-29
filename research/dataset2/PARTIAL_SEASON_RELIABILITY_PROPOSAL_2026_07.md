# Family #9 Partial-Season Reliability Proposal — 2026-07

**The bug fix and team-game-sequence redesign described in this
document's §0/§1 are APPROVED and COMMITTED** (`c79eea0`, "Fix Dataset
2 week-boundary bug and redefine family #9 windows by team-game
sequence"). This round adds the exclusion audit requested before any
floor is selected (§1a, new) and an explicit `team_game_window_status`
field (code change, tested, NOT yet committed — see §1a) replacing the
prior boolean `team_game_window_applicable`. **PROPOSAL ONLY beyond
what's already committed — no threshold is chosen, no
`opportunity_qualified` logic is implemented.**

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

§0/§1 (bug fix, window redesign) are committed (`c79eea0`). This
round's new work — the `team_game_window_status` field, its tests, and
the exclusion audit / floor decision table above — is real, tested
(907/907 passing, `python -m pytest tests/ -q --import-mode=importlib`),
and **NOT yet committed**, per instruction to stop again before
committing or selecting thresholds. Awaiting your decision on:
1. Whether to commit the `team_game_window_status` code change now
   (independent of any floor decision).
2. Which lenient/moderate/meaningful-role tier (or a different one, or
   different tiers per position given QB's low sensitivity to the
   opportunity overlay) to select for each position/metric.
3. Whether the team-game window, the active-game window, or both get a
   final `opportunity_qualified` treatment.
