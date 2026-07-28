# Source A Aggregation-Semantics Audit — 2026-07

Requested before approving Source B. Every claim below was checked
against real data (`data/raw/nflverse/annual/stats_player_week_2023.csv`,
the real, already-cached master DB) — not assumed. This audit found
real problems in the first version of `lib/dataset2/usage_traits.py`
(committed as `cdb3ede`) and the module has been REVISED as a result —
this is not a "confirmed as-is" audit, per your own conditional
instruction ("if this audit confirms the current implementation...
otherwise... necessary corrections").

---

## Summary of what changed

1. **Postseason rows were not excluded — a real bug, now fixed.** The
   raw weekly file contains real `season_type == 'POST'` rows (837 in
   2023 alone) mixed with `'REG'` rows. The first version aggregated
   whatever was passed in with no filter. Now filtered to `REG`
   internally, not left to the caller.
2. **`target_share`/`air_yards_share`/`wopr` were naively averaged
   across weeks — mathematically wrong, now recomputed from real
   summed numerators/denominators.** Verified against real 2023 data
   that this reconstruction reconciles EXACTLY against nflverse's own
   real weekly values (see field-by-field detail below).
3. **`racr` could not be reliably reconstructed and is now deferred**
   (not output at all) — its real underlying inputs (`receiving_yards`,
   `receiving_air_yards`) are preserved as plain sums instead, per the
   approved reconstruct-or-defer rule.
4. **The module now requires the FULL raw weekly file (all positions),
   not just skill positions**, for the team-level denominators to be
   correct — verified this matters with real data (below).

---

## Per-field audit

### `targets` — SUM
- **Source column**: `targets` in `stats_player_week_{season}.csv`.
- **Meaning/unit**: count of real passing targets thrown to this
  player in a game.
- **Season aggregation**: SUM across real REG weeks.
- **Why valid**: a real count; season total = sum of real weekly
  counts, by definition. No ambiguity.
- **Missing-value handling**: 0 real weekly rows → season total 0 (a
  real fact — the player recorded zero targets — not missing data).
- **Traded players**: summed across ALL real weeks regardless of
  team; no team-level denominator involved for this field itself.
- **Preseason feature type**: lagged COUNT (`prior_season_targets` =
  the real prior-season total).

### `carries` — SUM
Same as `targets` in every respect (real count, unambiguous sum,
0-when-absent, lagged count as a predictor).

### `receiving_yards` — SUM
- **Source column**: `receiving_yards`.
- **Meaning/unit**: real yards gained on receptions, per game.
- **Season aggregation**: SUM. Real, additive, unambiguous.
- **Missing-value handling**: 0 when absent (real fact).
- **Traded players**: summed regardless of team.
- **Preseason feature type**: lagged COUNT/total.
- **Note**: retained specifically so `racr`'s real inputs are
  preserved even though the ratio itself is deferred (see below).

### `receiving_air_yards` — SUM
Same as `receiving_yards` (real yards the ball traveled in the air on
targets to this player, additive, unambiguous sum). Also doubles as
the real numerator for `air_yards_share`'s recomputation.

### `passing_epa` / `rushing_epa` / `receiving_epa` — SUM, every EPA
field explicitly validated
- **Source columns**: `passing_epa`, `rushing_epa`, `receiving_epa`.
- **Meaning/unit**: real Expected Points Added, attributed to this
  player, accumulated across that week's real plays.
- **Season aggregation**: SUM.
- **Why valid, verified not assumed**: real weekly EPA values are
  already per-week TOTALS (a sum over that week's real plays), not
  per-play averages — confirmed by checking that weekly `receiving_epa`
  scales with real weekly target volume (players with 20+ real targets
  in a 2023 week show EPA in the 5-17 range, consistent with a
  per-play EPA around 0.3-0.85 summed over ~20 plays; a bounded
  per-play average would not scale with volume this way). Summing real
  weekly totals gives the real season total — the same additive logic
  as counts, just for a continuous value.
- **Missing-value handling**: 0 when the player had no real activity
  that week contributing to this EPA type.
- **Traded players**: summed regardless of team (EPA is
  player-attributed, not team-relative).
- **Preseason feature type**: lagged prior-season TOTAL (a real sum,
  not a per-play efficiency rate).

### `target_share` — RECOMPUTED (season sum ÷ season sum), NOT averaged
- **Source columns used for recomputation**: `targets` (player,
  summed) and `targets` (ALL players on that player's real team that
  week, summed — the real team-week total).
- **Meaning/unit**: the real share of the team's targets this player
  captured.
- **Season aggregation, verified real formula**: `season target_share
  = player's season targets / sum of (that week's real team-week
  target total, for every week the player actually played, using
  THAT WEEK's own real team)`. Checked against real 2023 weekly data:
  this reconciles EXACTLY (max discrepancy 5.5e-16, float-precision
  noise) against nflverse's own real per-week `target_share` values —
  confirming this IS the real underlying formula, not an
  approximation.
- **Why NOT a naive average**: a naive average of weekly ratios weights
  every week equally regardless of real volume, which is not what a
  season share means and does not match nflverse's real convention.
  Demonstrated with a real synthetic case in the test suite
  (`TestTargetShareRecomputedNotAveraged`): a player who is 50% of a
  heavy-volume week and 10% of a token week has a real season share of
  36.7%, not the naive average's 30%.
- **Missing-value handling**: NaN when the player has zero real weekly
  rows (undefined, not 0 — a real 0% share is a different fact from
  "never played").
- **Traded players — explicitly verified against a real trade**: Chase
  Claypool, real 2023 CHI (weeks 1-3) → MIA (weeks 7-18). Because the
  denominator lookup uses each week's own real `team`, his season
  share correctly reflects targets captured relative to whichever
  team's real pool was available that week — computed by hand against
  the real data (21 real targets over his real weeks, 351 real
  combined team-week targets across those same weeks) = **0.059829**,
  and the module's real output for Claypool matches this to full
  precision. Full table below.
- **A real, disclosed scope decision**: `weekly` must be the FULL raw
  file across ALL positions for the team-week denominator to be
  correct — verified against real 2023 data that restricting to
  skill positions before summing team totals silently drops 135 real
  targets and 66 real passing-air-yards of season volume attributed to
  non-skill-tagged rows. `population` still scopes which rows are
  RETURNED; only the denominator computation needs the full file.
- **Preseason feature type**: lagged RECOMPUTED SHARE (the season-level
  recomputation above, computed once for the prior season, then lagged
  whole — never re-averaged at lag time).

### `air_yards_share` — RECOMPUTED, denominator corrected
- **Source columns used**: `receiving_air_yards` (player, summed) and
  `passing_air_yards` (team-week, summed).
- **Meaning/unit**: the real share of the team's real passing air
  yards this player was targeted with.
- **Season aggregation, verified real formula, corrected during this
  audit**: the FIRST version used summed `receiving_air_yards` as the
  team-level denominator — checked against real 2023 data and found
  to UNDERCOUNT (mean real discrepancy 0.0067, max 0.9 against
  nflverse's real values). The real denominator is team-week
  `passing_air_yards` (the QB-side total, which includes real
  incompletions/spikes not credited to any receiver). Switching to
  this denominator reconciles EXACTLY (same float-precision level as
  `target_share`).
- **Missing-value handling**: NaN when the player has zero real weekly
  rows.
- **Traded players**: same team-week-lookup mechanism as `target_share`
  — correctly follows a trade.
- **Preseason feature type**: lagged RECOMPUTED SHARE.

### `wopr` — RECOMPUTED from the recomputed shares above
- **Formula, verified real**: `1.5 * target_share + 0.7 *
  air_yards_share` — nflverse's own published formula. Checked
  against real 2023 weekly WOPR values using the real weekly shares:
  reconciles EXACTLY. Applying the identical formula to the
  season-level RECOMPUTED shares (rather than to weekly values) is the
  same real formula one level up, not a new approximation.
- **Missing-value handling**: NaN whenever either input share is NaN.
- **Traded players**: inherits correct behavior from the two shares it
  combines.
- **Preseason feature type**: lagged RECOMPUTED WEIGHTED RATE.

### `racr` — DEFERRED, not output
- **What was tried**: a naive player-level `receiving_yards /
  receiving_air_yards` recomputation, checked against real 2023 weekly
  `racr` values. Diverges badly on real rows with negative or
  near-zero `receiving_air_yards` (max absolute discrepancy 38.0 on a
  real row). A second hypothesis ("treat non-positive air yards as
  racr = 0") was also tested directly against real data and still
  diverges on 532 of 17,806 real 2023 rows (some real rows have a
  genuine non-zero racr even with negative air yards, e.g. -3.29,
  -21.5 — not the simple zero-floor the hypothesis predicted).
- **Conclusion**: the real, exact per-row formula nflverse uses could
  not be reliably reverse-engineered from the data available in this
  pipeline within this investigation.
- **Action taken, per the approved rule**: NO season-level `racr`
  column is output. `receiving_yards` and `receiving_air_yards` (both
  real, unambiguous sums, validated above) ARE output, so a future
  consumer can compute their own ratio once/if the real formula is
  confirmed — the underlying inputs are preserved, the inaccurate
  derived metric is not manufactured.

---

## The five explicit checks requested

1. **Player-season totals, player-team-season rows, or both?**
   Player-season totals only (one row per `(season, player_id)`, same
   grain as every other Dataset 2 module) — NOT split into separate
   rows per team. Verified this doesn't lose accuracy: because the
   team-week denominator lookup is resolved per-week using that week's
   real team, a single blended season share still correctly reflects
   "opportunity captured relative to whichever real team pool was
   available that week."
2. **Do team-level denominators follow the player across teams
   correctly?** Yes — verified by hand against a real 2023 trade (see
   `target_share` above); the module's real output matches the
   hand-computed value to full precision.
3. **Can duplicate player-week records occur?** Checked directly
   against real 2023 data: zero duplicate `(player_id, week)` rows
   within `REG`. Not defended against in code, since no real
   occurrence was found — if this pipeline's real data ever produces
   one, `groupby().sum()` would silently double-count it. Disclosed in
   the module's own docstring as a real, known limitation of this
   version, not a decision.
4. **Are postseason rows excluded?** Now yes (was the real bug found
   and fixed this audit — see Summary above).
5. **Are partial-season and missing-week records distinguished from
   genuine zeros?** Yes, and verified consistent with how family #9's
   `partial_season_traits.py` already handles this: the raw weekly
   file only has a row for a week the player actually recorded real
   statistical activity — a week with no row means no real game
   activity that week (bye, inactive, not yet on a roster), while a
   real row with `targets == 0` (e.g. a real RB carry-only week) is a
   genuine, real zero. Count fields sum real zeros correctly either
   way; rate fields stay NaN only when NO real weeks exist at all, not
   merely because some weeks had zero targets.

---

## Real-data validation table (2023 season, real `stats_player_week_2023.csv`)

Includes Chase Claypool, the real mid-season-traded player
(CHI weeks 1-3 → MIA weeks 7-18):

| Player | Pos | targets | carries | receiving_yards | receiving_air_yards | target_share | air_yards_share | wopr |
|---|---|---|---|---|---|---|---|---|
| Josh Allen | QB | 0 | 111 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 |
| Christian McCaffrey | RB | 83 | 272 | 564 | 153 | 0.1861 | 0.0406 | 0.3076 |
| Tyreek Hill | WR | 171 | 6 | 1,799 | 1,847 | 0.3270 | 0.4379 | 0.7970 |
| Travis Kelce | TE | 121 | 0 | 984 | 807 | 0.2270 | 0.2258 | 0.4986 |
| **Chase Claypool** | WR | 21 | 0 | 77 | 230 | **0.0598** | 0.0845 | 0.1489 |

Claypool's `target_share` hand-verified: 21 real targets across his
real weeks (2, 8, 4 for CHI; 0, 2, 0, 0, 2, 0, 1, 2 for MIA) ÷ 351
(the sum of each of those specific weeks' real team-week target
totals, CHI's for weeks 1-3, MIA's for weeks 7-18) = **0.059829...**,
matching the module's real output exactly.

---

## Test-count question — fully reconciled, not just re-asserted

The suite went from **655** (verified directly: checked out via a git
worktree at the real commit `dd4a944~1`, the state immediately before
any Dataset 2 work began, and ran `pytest --collect-only`) to **804**
now (after this audit's revision added 4 net tests to
`test_dataset2_usage_traits.py`, 16→20). Full accounting, every number
verified, not estimated:

- **655** — real baseline, confirmed via git worktree.
- **+ 125** — the 8 Dataset 2 test files that existed before this
  audit (19+19+21+17+17+4+12+16).
- **+ 20** — NOT a Dataset 2 test file. `tests/test_no_isolated_research_dependency.py`
  is a real, pre-existing repo-wide guardrail test that auto-discovers
  every `.py` file under `scripts/` and `lib/` via `rglob("*.py")` and
  runs 2 parametrized checks per file. It grew from 60 to 80 tests
  because this session added exactly 10 new files under
  `lib/dataset2/` (`__init__.py`, `common.py`,
  `experience_age_draft.py`, `prior_season_traits.py`,
  `prior_finish_traits.py`, `prior_finish_analysis.py`,
  `partial_season_traits.py`, `depth_chart_traits.py`,
  `fragility_traits.py`, `usage_traits.py`) — 10 × 2 = 20, an exact
  match. A real, harmless, mechanical side effect of an existing
  guardrail scaling with the codebase, not a new test file, not
  something written this session, and not a problem.
- **+ 4** — this audit's revision (`test_dataset2_usage_traits.py`
  16 → 20 tests).
- **655 + 125 + 20 + 4 = 804.** Exact.
