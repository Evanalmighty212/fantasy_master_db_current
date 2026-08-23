# Dataset 2 Phase 3 synthesis (2026-08-22)

**Status: SYNTHESIS DOCUMENT.** Read-only synthesis of the completed,
verified Dataset 2 Phase 1 discovery package (HEAD
`0e6a67014901456b15341eff9ab06bc563cbce74`) and Phase 2 holdout
confirmation package (HEAD `f2505cd756e33406a10a3384c27d6d7c7ce57846`).
This document performs no new computation -- every number below is
read directly from those two packages' `primary_results.csv`,
`robustness.csv`, and `confirmation_ledger.csv`. It does not authorize
building Dataset 3; see the open prerequisites in Section 5.

---

## Scope note: one trait at a time

Phase 1 and Phase 2 each tested traits **one at a time**. Every trait
below was fit in its own model (controlling for position, acquisition
path, and era) and confirmed against holdout independently of every
other trait. Nothing in this research jointly modeled two or more
traits together, and no interaction or combined effect between any
pair of traits was estimated or tested. The grouping below organizes
30 individually-validated associations by football theme; it is not a
joint model.

---

## 1. Six themes

**Theme A -- Established Season-Long Role and Production** *(7 traits)*
`fam7_prior_overall_finish`, `fam7_prior_positional_finish`,
`fam7_prior_ppg`, `fam88_prior_season_touches`,
`srcA_prior_season_receptions`, `srcA_prior_season_wopr`,
`srcB_prior_season_offense_pct`

- **Football meaning:** how central and productive the player was
  across their *entire* prior season -- finish rank, PPG, touches,
  receptions, weighted opportunity (WOPR), offensive snap share.
- **Cleanest representatives:** `fam7_prior_ppg` (0.116 discovery →
  0.127 holdout) and `srcA_prior_season_wopr` (tightest q-value of the
  group, 3.15e-4; 0.238 → 0.311).
- **Category:** season-long role and production.
- **Use it to infer:** a durable prior-year role and production level,
  as its own standalone association. **Don't use it to infer:**
  anything about a player without an established prior role, or that
  the role survives a team/context change.

**Theme B -- Recent Scoring Momentum** *(2 traits)*
`fam9_active_final_4_games_ppg`, `fam9_active_final_6_games_ppg`

- **Football meaning:** was the player scoring well specifically in the
  final 4-6 games of the prior season, distinct from their full-season
  average.
- **Cleanest representative:** `fam9_active_final_6_games_ppg`
  (q=1.03e-3, 0.126 → 0.141).
- **Category:** recent momentum -- a distinct trait from Theme A,
  individually confirmed on its own.
- **Use it to infer:** a late-season scoring rate is, on its own, an
  individually validated association with the outcome. **Don't use it
  to infer:** anything about how it behaves alongside Theme A -- that
  combination was never tested.

**Theme C -- Recent Individual Receiving Role (RB/WR)** *(8 confirmed traits)*
`fam9_active_final_4_wr_receiving_opportunity`,
`fam9_active_final_4_wr_receiving_production`,
`fam9_active_final_4_rb_receiving_production`,
`fam9_active_final_6_rb_receiving_opportunity`,
`fam9_active_final_6_rb_receiving_opportunity_per_active_game`,
`fam9_active_final_6_rb_receiving_production`,
`fam9_active_final_6_wr_receiving_opportunity`,
`fam9_active_final_6_wr_receiving_production`

- **Football meaning:** how much receiving work a specific RB or WR was
  getting late in the prior season, and how well they converted it.
- **Cleanest representatives:** `fam9_active_final_6_wr_receiving_opportunity`
  / `_production`.
- **Category:** individual role with a production/skill component.
- **Use it to infer:** a real, recent receiving role for a specific
  player, as its own association. **Don't use it to infer:** anything
  about RB receiving-opportunity signals as a general class -- the one
  trait in this family that did not replicate was the specific
  final-4-game RB receiving-opportunity cut (`fam9_active_final_4_rb_receiving_opportunity`;
  see Section 2). The other RB receiving-opportunity traits listed
  above, including the final-6-game version, are individually
  confirmed and are not implicated by that one trait's result.

**Theme D -- Team Offensive Pace/Scoring Environment** *(3 traits)*
`fam9_team_final_4_points_per_active_game`,
`fam9_team_final_4_points_per_team_game`,
`fam9_team_final_6_points_per_team_game`

- **Football meaning:** was the player's team scoring well late in the
  prior season -- a team-level trait, fit and confirmed independently
  of any individual-player trait.
- **Cleanest representative:** `fam9_team_final_4_points_per_team_game`
  (q=2.98e-4, 0.122 → 0.131, the tightest match anywhere in the
  confirmed set).
- **Category:** team context.
- **Use it to infer:** a hot late-season offense has its own validated,
  individual association with the outcome. **Don't use it to infer:**
  which specific player on that offense benefits -- that is a separate
  question, addressed only by Theme C/E's own individually-tested
  traits, not by combining this trait with those.

**Theme E -- Team Receiving-Scheme Context for RB/WR** *(9 confirmed traits)*
`fam9_team_final_4_rb_receiving_opportunity`, `_production`,
`_efficiency_rate`, `fam9_team_final_4_wr_receiving_opportunity`,
`_production`, `fam9_team_final_6_rb_receiving_opportunity`,
`_production`, `fam9_team_final_6_wr_receiving_opportunity`,
`_production`

- **Football meaning:** how much a team's offense as a whole leaned on
  RB/WR receiving work late in the prior season.
- **Cleanest representatives:** `fam9_team_final_4_rb_receiving_production`
  and `fam9_team_final_6_rb_receiving_production` (both q=2.98e-4).
  `fam9_team_final_4_rb_receiving_efficiency_rate` is the weakest
  member of this theme (q=0.061, borderline).
- **Category:** team context (scheme), conceptually related to Theme C
  but tested as an entirely separate set of traits.
- **Use it to infer:** a scheme that structurally features RB/WR
  receiving work has its own individually validated association.
  **Don't use it to infer:** which player benefits, and don't use the
  snap-share version of this idea at all (see Section 2).

**Theme F -- Team-Change / Stability Risk** *(1 trait)*
`fam44_prior_changed_team`

- **Football meaning:** did the player change teams before the season
  in question. Confirmed cleanly on its own (q=2.98e-4, -0.301
  discovery → -0.180 holdout).
- **Category:** acquisition risk.
- **Use it to infer:** a modest, individually validated headwind.
  **Don't use it to infer:** anything about how this trait combines
  with the destination team's Theme D/E context -- that combination
  has not been tested (see prerequisite 3 below).

---

## 2. Non-inputs

These are explicitly **not** to be used as positive scoring inputs in
any future framework:

- **The 2 contradicted traits:**
  - `fam9_active_final_4_rb_receiving_opportunity` -- right direction,
    but far weaker in holdout than discovery (ratio ≈0.19, below the
    1/3 confirmation floor).
  - `fam9_team_final_4_wr_snap_team_offense_total` -- sign flipped
    (mildly negative in discovery, flat/slightly positive in holdout).

  Both were discovery-robust (`all_folds_same_direction`, decent
  q-values) -- this is precisely why the holdout confirmation step
  exists.

- **The 2 excluded unstable Star team-identity traits:**
  `fam10_depth_chart_team` and `fam4_nfl_draft_team` -- excluded before
  Phase 2 for discovery-only direction instability across their own
  leave-one-season-out folds. Never reached holdout. Not confirmed,
  not contradicted -- simply never validated.

- **The null Strict Bust result:** zero of 105 fitted Strict Bust
  pairs cleared Phase 1's own discovery gates. This is a genuine null
  result, not an oversight -- there is no validated "bust risk"
  shortcut anywhere in this research to date.

---

## 3. Practical four-question checklist

**This is a reasoning aid for organizing which individually-validated
traits apply to a player. It is not a validated scoring formula, not a
weighting scheme, and not an evidence-based ordering rule.** No step
produces a number, and the sequence below is for readability only --
Phase 1/Phase 2 did not validate this or any other priority ordering
among the four questions.

1. **Baseline (Theme A):** What do we know about this player's role
   and production across last season, in full?
2. **Trajectory (Theme B, C):** What do their recent momentum and
   recent individual role traits individually show?
3. **Environment (Theme D, E):** What do their team's context traits
   individually show -- and is that the current team, or a team
   they've since left?
4. **Stability (Theme F):** Is there a team-change flag on this player?

---

## 4. Research limits

- **Observational, not causal.** Every theme above describes an
  association between a preseason-knowable trait and league-winning
  outcomes -- none of it establishes why.
- **One trait at a time.** Phase 1 and Phase 2 validated 30 individual
  associations, each controlling for standard covariates and each
  confirmed independently against holdout. No joint model was fit, and
  no interaction or combined effect between any two traits has been
  estimated or validated.
- **Overlapping (correlated) traits.** Themes C and E describe closely
  related ideas (individual vs. team receiving role) built from
  correlated underlying data -- each is individually validated, but
  they are not independent evidence of separate things.
- **No validated breakout or bust shortcut.** Nothing here identifies
  an emerging player without a prior-season baseline, and Strict Bust
  produced zero validated traits.

---

## 5. Open Dataset 3 prerequisites

Four methodology decisions remain open before this synthesis could
inform Dataset 3 feature engineering:

1. **Formal feature exclusions.** A documented, ratified decision to
   exclude the 2 contradicted traits, the 2 excluded unstable Star
   traits, and (given the null result) all Strict Bust traits from
   Dataset 3's feature set. This document recommends that exclusion
   but does not itself ratify it.
2. **Preseason leakage re-verification.** Explicit re-verification that
   every Theme A-F trait satisfies the Dataset 2 leakage rule (every
   input dated before that season's Week 1) for Dataset 3 use
   specifically, rather than assuming Phase 1/Phase 2's own governed
   scope carries over unchanged.
3. **Team-context treatment for players who changed teams.** How
   Theme D/E (team context) should be computed for a player who
   changed teams (Theme F) -- old team's context, new team's, both, or
   something else. This question has no answer in the completed
   research and needs an explicit decision before Dataset 3 feature
   engineering can treat these traits together for such players.
4. **Correlated-feature reduction.** A feature-selection/
   multicollinearity decision for Themes C and E in particular (7-9
   correlated traits each, drawn from overlapping underlying data) --
   Dataset 3 almost certainly should not ingest all 30 confirmed
   traits as independent features.
