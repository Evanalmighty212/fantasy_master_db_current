# Dataset 2 standardized first-wave trait-analysis pipeline — proposal (2026-07, revised)

**Status: PROPOSAL ONLY. No predictor has been tested against any
outcome/target in this document.** Every real computation performed
this round and last round is a STRUCTURAL characterization of the
431-column predictor whitelist and the 4 targets' own aggregate base
rates — never a predictor-vs-outcome association test
(`research/dataset2/trait_analysis_pipeline_predictor_inventory.py`).
Phase 1 (the first actual predictor-vs-outcome pass) is proposed below
but **not executed**.

Built on the canonical analysis view at commit `04eaa4b`
(`data/exports/dataset2_analysis_view.parquet`, 11,784 rows, 459
columns, 431-column predictor whitelist, 6-target registry).

**Revision note**: this replaces the first version of this document.
The structural inventory (§1) was directionally approved; §2 onward is
substantially revised per instruction — ADP as a mandatory control,
expanded position handling, rare-outcome bias reduction, outcome-free
predictor clustering (extended beyond correlation), five-number
multiple-comparison reporting, explicit minimum evidence gates,
player/season dependence handling, incremental-usefulness diagnostics,
strengthened holdout protection, and a formal advancement standard.

---

## 1. Real predictor inventory (unchanged from the approved round, structural only)

Restricted to the 11,175 `outcome_join_status == "outcome_matched"`
rows.

| Dimension | Breakdown |
|---|---|
| **Variable type** | continuous: 213 · boolean: 213 · categorical/status: 5 |
| **Position scope** | RB: 130 · ALL: 82 · WR: 79 · TE: 76 · QB: 64 |
| **Family** | family #9: **385 of 431 (89.3%)** · Source A base (#15/17/18/20/22): 10 · family #86: 9 · family #10: 7 · family #4: 4 · families #6/#7: 3 each · families #1/#8: 2 each · family #39/#44/#88: 1 each |
| **Constant columns** (`n_unique<=1`, excluded from all testing) | 6: `fam10_depth_chart_schema_era`, `fam9_team_final_4_games`, `fam9_team_final_6_games`, `fam9_team_final_8_games`, `fam9_team_second_half_team_games`, `fam9_prediction_season_outcome_unavailable` |
| **Near-duplicate continuous pairs** (`\|r\|>=0.95`) | 270 pairs, involving 159 of 205 continuous columns (77.6%) |
| **Single-season concentration** (outcome-free: share of a trait's own non-null values in its single busiest real season) | **0 columns exceed 50%** — no predictor's apparent coverage is a one-season artifact |
| **Position-scoped low coverage** (`<50%` applicable, within the trait's own position population) | 56 real columns |

Full detail unchanged from the approved round — see the prior version
of §1 in git history (commit history for this file) for the complete
discussion; this revision's new material starts at §1.5.

### 1.5 Outcome-free predictor clustering (extended per instruction)

**Every edge type below reads only predictor columns and predictor
column NAMES — never a target, eligibility, or label column.** Four
real, disclosed edge types, unioned via union-find over the 425
non-constant predictor columns:

| Edge type | What it detects | Real count |
|---|---|---|
| 1. Continuous-continuous Pearson `\|r\|>=0.95` | Statistical near-duplication (§1) | 270 edges |
| 2. **Boolean-boolean agreement `>=95%`** (on jointly-non-null rows, `n>=30` required) | Two boolean columns that are almost always the same value | 140 edges (9,045 pairs checked) |
| 3. **Known family #9 tier vocabulary** | `_role_present` / `_meaningful_role` / `_strong_lead_role` are progressively stricter thresholds on ONE underlying continuous share/rate — documented by this project's own three-tier framework (`partial_season_traits.py`), not merely inferred | 39 stems merged |
| 4. **Known trailing-window variants** | Same position+metric across `final_4`/`final_6`/`final_8`/`first_half`/`second_half` — the same underlying stat over overlapping game spans, known by construction | 123 stems merged |

**Real result: 425 non-constant columns collapse to 76 clusters** — a
82.1% reduction. Cluster sizes: 29 singletons, 24 clusters of 2-5, 15
of 6-10, 8 larger than 10 (largest: 69 members).

**Real caveat, disclosed not hidden**: the largest cluster (69 members)
is dominated by edge type 2 (boolean agreement) merging many
`*_volume_eligible_exploratory`/`*_volume_eligible_sensitivity`/
`*_role_present`-style flags across DIFFERENT metrics that happen to
share the same underlying sample-size GATING condition (e.g., "did
this player have enough active games in the window") rather than
genuinely redundant CONTENT. This is a real limitation of a pure
agreement-rate heuristic — it can merge traits whose ELIGIBILITY
overlaps without their SIGNAL being the same question. **Proposed
mitigation**: before Phase 2, a manual review pass on any cluster
larger than 10 members, confirming the boolean-agreement edges within
it are genuine content redundancy and not shared-gating coincidence;
oversized clusters failing this check are split before representative
selection. This review touches only predictor structure, never
outcomes.

**Representative selection rule** (priority order, all outcome-free,
per instruction):
1. Highest applicable coverage within the trait's own position scope
   (§1.2).
2. Prefer a continuous source measure over a mechanically-derived
   threshold flag (the `_role_present`/`_meaningful_role`/
   `_strong_lead_role` suffix family) — the underlying share/rate
   carries strictly more information than any one threshold cut of it.
3. Broader historical season coverage (more distinct real seasons
   with a non-null value).
4. Fewer compounded assumptions / more direct/interpretable — operationalized
   as the shorter of the two column names as a real, mechanical proxy
   (a raw metric name is reliably shorter than its per-game/
   per-team-game-normalized or tier-derived variant in this project's
   established naming convention — verified true for every real
   near-duplicate pair inspected).

Full cluster membership + chosen representative:
`data/exports/dataset2_trait_pipeline_predictor_clusters.csv`.

---

## 2. Evaluation methodology — ADP, position, and era are mandatory controls

**ADP is a mandatory control/stratification/calibration variable in
every primary adjusted analysis — never itself a discovery predictor.**
It is not in the predictor whitelist (§3, artifact 3's own design) and
this proposal makes explicit that it must never be added there or
compared on a trait leaderboard: ADP is real fantasy-market
information a trait must show something BEYOND, not a trait competing
for the same slot.

**Two-tier reporting for every trait**:
- **Descriptive layer** (unadjusted): raw Star/bust rate by trait
  value or quantile, exactly as in the prior version of this proposal.
  Always shown, never treated as the primary finding.
- **Primary/adjusted layer**: every formal association test (§2's
  table below) is run as a regression with the trait as the variable
  of interest and **ADP, position, and era as mandatory covariates in
  every model** — never optional, never trait-specific. Concretely:

  `target ~ trait + ADP_round + position + era_bucket [+ trait:position interaction where §3 permits]`

  using `DATASET2_ADP_ROUND_BUCKETS` and `DATASET2_ERA_BOUNDARIES`
  (both reused directly from config, not new constants) for the
  categorical ADP/era terms, and `position` as a categorical covariate
  (never a continuous proxy).

| Predictor type | Target type | Adjusted model | Primary effect size | Rare-outcome handling |
|---|---|---|---|---|
| Boolean | Binary | Logistic regression, trait + ADP-bucket + position + era | Adjusted odds ratio (trait coefficient) | Firth's bias-reduced logistic regression — see §5 |
| Continuous | Binary | Logistic regression, same covariates | Adjusted odds ratio per real, reported unit (e.g. per 1 SD of the trait) | Firth's, same trigger rule |
| Boolean/Continuous | Continuous (`underperformance_diagnostic_value`) | OLS, same covariates | Adjusted standardized coefficient (β) | N/A — Firth's applies to binary targets only; robust (HC3) standard errors used instead, see §7 |
| Categorical/status | Binary | Logistic regression with the category as a factor, same covariates | Adjusted odds ratio per category vs. a reference category | Firth's, same trigger rule |

Descriptive-only quantile-binned rates, AUC, Cohen's d, Spearman ρ
(the prior version's §2 methods) remain as the DESCRIPTIVE layer,
always reported, never the primary claim.

---

## 3. Position analysis — pooled, position-specific, and interaction

Per instruction, not fully-separate position models only. Every trait
produces all three:

1. **Pooled adjusted estimate controlling for position** (§2's model,
   `position` as a covariate) — the default headline estimate for
   traits with `position_scope=ALL` or multi-position applicability.
2. **Position-specific descriptive estimates** — always computed and
   reported (raw rate, applicable n, per position), regardless of
   whether a formal position-specific test is possible.
3. **Position-interaction test where sample size permits** — a
   `trait:position` interaction term added to §2's model, testing
   whether the trait's effect genuinely differs by position rather
   than just differing in raw rate due to composition. **Gated
   explicitly**: run only when every position level has at least the
   Firth-trigger threshold (§5) of positive target cases within that
   position AND the trait's own position-scoped applicable coverage
   (§1.2) — otherwise the interaction term is flagged
   `interaction_test_unavailable_insufficient_n`, and only the
   descriptive per-position table is reported for that position.

**Formal per-position analyses are explicitly marked, never silently
omitted**: `position_analysis_status ∈ {"formal", "descriptive_only"}`
per position per trait×target, driven by §5's positive-count gate.

---

## 4. Rare-outcome handling — bias-reduced estimation

**Real grounding, target-only aggregate counts (no predictor
involved)**, discovery window (`prediction_season < 2021`) vs. holdout
(`>= 2021`):

| Target | Discovery: eligible / positive | Holdout: eligible / positive |
|---|---|---|
| `star_by_value_label` | 5,725 / **47** | 2,812 / 29 |
| `bust_primary_label` | 1,750 / 339 | 927 / 183 |
| `bust_strict_below_replacement_label` | 1,750 / 54 | 927 / 49 |

**47 discovery-window Star positives (76 total across all real
seasons) is genuinely rare-event territory** for a 4+ covariate
adjusted regression (trait + ADP-bucket + position + era, several of
which are multi-level categoricals contributing more than one
parameter). Standard maximum-likelihood logistic regression is known
to produce biased, overconfident coefficient estimates and can fail to
converge entirely under this few events (Firth 1993; the
"Hauck-Donner"/separation problem is a real risk here, not a
theoretical one, given several boolean predictors will have
near-perfect or perfect separation against only 47 positives).

**Proposed method: Firth's bias-reduced (penalized-likelihood) logistic
regression** for every binary-target adjusted model, applied
UNCONDITIONALLY whenever the trigger rule below fires — not merely
recommended as an option:

- **Trigger rule**: Firth's method is REQUIRED whenever the applicable
  positive-case count (within the model's own applicable population)
  is below 20, OR the events-per-variable ratio (positives ÷ number of
  model parameters, including all covariate levels) is below 10 — the
  standard EPV heuristic from the logistic-regression literature
  (Peduzzi et al. 1996), reused here rather than invented.
- Given `star_by_value_label`'s real discovery-window count (47), and
  a model with trait + ADP-bucket (4 levels) + position (4 levels) +
  era (2 levels within discovery) ≈ 10 parameters, EPV ≈ 4.7 — well
  under 10. **Firth's method is therefore required for every
  `star_by_value_label` adjusted test**, not just recommended.
- `bust_primary_label` (339 discovery positives, EPV≈34) and
  `bust_strict_below_replacement_label` (54 discovery positives,
  EPV≈5.4) are evaluated individually per trait — `bust_strict`
  crosses the Firth trigger for many traits, `bust_primary` generally
  does not.

**When even Firth's cannot support a stable estimate**: if the
applicable positive count is below 10 (regardless of Firth's), the
adjusted estimate is computed and reported but flagged
`formal_inference_insufficient` — descriptive rates and Firth's point
estimate are shown, but the trait cannot advance past Phase 2 (§9) on
that target regardless of its p/q-value. This is a hard floor, not a
soft warning.

---

## 5. Minimum evidence gates

Every gate below is justified against either a standard statistical
convention (EPV rule, minimum-cell-count convention) or this project's
own already-established constant (`DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE=10`),
reused rather than invented where a reuse is defensible.

| Gate | Minimum | Justification |
|---|---|---|
| **Applicable sample size** (for formal adjusted testing) | `n >= 200` | Supports a 4+ parameter adjusted model (trait + ADP-bucket + position + era) without instability; below this, only the descriptive layer is reported |
| **Positive target cases** (for a STABLE, non-Firth adjusted estimate) | `n >= 20` positive AND `n >= 20` negative in the applicable population | Standard minimum for asymptotic logistic-regression validity; below 20 positives, Firth's is REQUIRED (§4) |
| **Positive target cases** (floor below which even Firth's result is descriptive-only) | `n >= 10` positive | Firth's method reduces bias but cannot manufacture information; below 10 real events, no adjusted estimate is treated as formal regardless of q-value |
| **Positive/negative trait cases** (boolean predictor, for the 2×2/adjusted cell to be meaningful at all) | `n >= 10` in EACH of the four trait×target cells | Reuses `DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE` directly, consistent with this project's existing small-cell convention |
| **Category sizes** (categorical/status predictors, 5 columns) | `n >= 10` per category entering the model; smaller categories pooled into an explicit `"other"` level or excluded | Same reused constant |
| **Seasons represented** | `n >= 5` distinct real `prediction_season` values with a non-null trait value | A trait present in fewer real seasons cannot be era-split (§ prior version's era requirement) meaningfully at all |
| **Single-season concentration** | `max_single_season_share <= 0.5` (§1) | A trait whose non-null values are majority-concentrated in one season cannot support the era-stability check (§9) regardless of any other gate |

**Enforcement**: a predictor (or cluster representative) failing ANY
gate remains in the DESCRIPTIVE output (§6) with the specific gate(s)
it failed named explicitly — it is excluded from the standard
adjusted/FDR leaderboard, never silently dropped from the dataset
entirely.

---

## 6. Standardized per-trait output schema (revised)

Builds on the prior version's schema with the additions this round
requires:

| Field | Meaning |
|---|---|
| *(all fields from the prior version's §4 remain — applicable_n, positive_n/negative_n, raw rates, baseline_rate, position/ADP/era-conditioned results, threshold-sensitivity result, coverage_warning, missingness_semantics)* | |
| `cluster_id`, `is_cluster_representative` | From §1.5 |
| `adjusted_effect_size`, `adjusted_effect_type` | Odds ratio / standardized β, per §2's model |
| `adjustment_method` | `"standard_mle"` or `"firth_bias_reduced"`, per §4's trigger rule |
| `evidence_gate_status` | `"passes_all_gates"` or a list of failed gates from §5 |
| `position_analysis_status` (per position) | `"formal"` / `"descriptive_only"`, per §3 |
| `player_clustered_p_value`, `player_clustered_ci` | Per §7 |
| `season_resampling_stability` | Per §7 |
| `incremental_log_loss_delta`, `incremental_brier_delta`, `incremental_roc_auc_delta`, `incremental_pr_auc_delta` | Per §8, vs. the ADP+position+era baseline |
| `q_value` | FDR-adjusted, cluster-representative tests only (§9) |
| `advancement_status` | Per §11 |

---

## 7. Dependence and uncertainty

**Repeated player-seasons are real and structural**: the same
`player_id` legitimately appears in multiple rows (different real
seasons), violating the independence assumption plain logistic/OLS
standard errors rely on.

- **Primary method**: player-clustered (sandwich/robust) standard
  errors, clustering on `player_id`, for every adjusted model in §2
  (standard `cov_type="cluster"` in `statsmodels`, no new machinery to
  build).
- **Season/era controls**: already mandatory per §2 (era-bucket
  covariate in every model).
- **Season-level resampling sensitivity**: leave-one-season-out
  re-estimation — refit the adjusted model once per real discovery
  season with that season fully removed, and report whether the
  trait's adjusted effect sign and approximate magnitude survive.
  Directly operationalizes the `single_season_concentration` gate
  (§5, §1) as an ACTIVE robustness check, not just a static filter — a
  trait whose effect disappears when any one season is dropped fails
  this check regardless of its pooled q-value.

---

## 8. Incremental usefulness diagnostics (trait screening, NOT Dataset 3 modeling)

**Baseline model, fixed and identical for every trait**: `target ~
ADP_round + position + era_bucket` (no trait). Every candidate trait's
diagnostic is the DELTA versus this same baseline, never an absolute
score.

| Diagnostic | Applies to | Purpose |
|---|---|---|
| Log loss (delta) | Binary targets | Calibrated-probability improvement |
| Brier score (delta) | Binary targets | Calibration + discrimination, less sensitive to rare-event log-loss blowup than log loss alone |
| ROC-AUC (delta) | Binary targets, where baseline prevalence supports it | Rank-discrimination improvement |
| **Precision-recall AUC (delta)** | Binary targets, **especially `star_by_value_label`** | ROC-AUC is known to look artificially strong under severe class imbalance (§4's 0.9% Star base rate) — PR-AUC is the more honest diagnostic here |

**Estimation**: grouped k-fold cross-validation (grouped by
`player_id`, so no player's seasons split across train/test folds
within a fold), run ONLY within the discovery window (§10) — never
touching holdout data, consistent with the rest of this pipeline.

**Explicit scope limit, stated per instruction**: these four
diagnostics answer "does this trait add anything measurable beyond
what the market (ADP) and position/era already tell us" as a
SCREENING signal. They are not a model-selection process, not a
feature-importance ranking, and not the start of Dataset 3's actual
predictive model — Dataset 3's own model form, feature set, and
validation design are separate, future decisions.

---

## 9. Multiple comparisons — five-number reporting

| Count | Real/expected value | Basis |
|---|---|---|
| **Raw trait-target combinations** | 431 × 4 = 1,724 | Full whitelist × all 4 targets |
| **Testable combinations after evidence gates** (§5) | Computed per target once Phase 1 actually runs (cannot be stated without touching outcome eligibility per trait — genuinely unknown until Phase 1) | Gate gate application is itself part of Phase 1, not precomputable outcome-free |
| **Predictor clusters** | 76 (+ any splits from the §1.5 oversized-cluster review) | Outcome-free, computed this round |
| **Primary FDR tests** | ≤ 76 × 4 = 304 nominal, reduced further per target by §5's gates | Cluster representatives only |
| **Within-cluster sensitivity tests** | The remaining 425−76=349 non-representative members, tested only as secondary formulation/threshold sensitivities AFTER their cluster's representative already cleared Phase 2 | Never independently entered into the FDR budget |

**Procedure**: Benjamini-Hochberg FDR control, **q=0.10**, applied to
the cluster-REPRESENTATIVE primary tests only (§1.5's representative
selection), **separately per target** (four independent FDR runs —
Star/primary-bust/strict-bust/diagnostic are different questions and
never share a correction budget, consistent with the approved round
1/2 bust-label work's own position on this).

**FDR is a discovery FILTER, never proof and never the ranking
criterion** — unchanged from the prior version, restated because it's
foundational: a cluster's `q_value` gates whether it is even eligible
for Phase 3 (§10-11); ranking among FDR-survivors is by the composite
criterion in the prior version's §5 (effect size → robustness →
holdout replication), now extended to require §11's full advancement
standard.

Non-representative cluster members that a representative's cluster
clears Phase 2 are examined ONLY as secondary formulation/threshold
sensitivities (e.g., does the `_meaningful_role` tier flag show the
same direction as its cluster's continuous representative?) — never
re-entered as independent discoveries.

---

## 10. Holdout protection (strengthened)

Reuses `DATASET2_ERA_BOUNDARIES=(2011,2021)`: discovery
`prediction_season<2021` (1,750 `bust_primary_eligible` rows, 65%),
holdout `>=2021` (927 rows, 35%).

**Everything below must be FROZEN using discovery-season data alone,
before the holdout window's target values are inspected even once**:
- Cluster membership and representative selection (§1.5) — already
  outcome-free by construction, so this is automatically satisfied.
- Evidence-gate thresholds (§5).
- Model forms — which covariates, Firth's trigger rule (§4),
  interaction-test conditions (§3).
- Transformations (quantile binning edges, any standardization).
- Advancement rules (§11).

**Holdout is used exactly once per candidate, for confirmation only.**
Explicitly prohibited: using a holdout result to go back and adjust a
gate threshold, add/remove a covariate, or reselect a cluster
representative, then re-checking holdout again — that converts the
holdout into a second discovery set and destroys its purpose. If a
pipeline redesign is genuinely needed after seeing holdout results,
the ENTIRE holdout window must be treated as burned for that
redesign's traits and a new, disjoint validation season range would be
required — not something this round authorizes or anticipates
needing.

**Disclosed power limitation, restated**: `bust_strict_below_replacement_label`
holdout has only 49 real positive cases (927 eligible) — thin for a
reliable replication check specifically on that target. A trait that
replicates on `bust_primary_label`/both sensitivities but shows an
inconclusive (not necessarily contradictory) holdout result on
`bust_strict` should be read as power-limited, not rejected, per the
advancement standard's own explicit accommodation (§11).

---

## 11. Advancement standard

A trait or cluster advances toward Dataset 3 candidacy on a given
target only when ALL of the following hold — this is a conjunction,
not a scorecard:

1. **Adequate evidence coverage** — passes every §5 gate for that
   target.
2. **Meaningful adjusted effect size** — the §2 adjusted (ADP+position+
   era-controlled) effect, not the raw/descriptive one, with a CI that
   excludes the null.
3. **Discovery FDR survival** — `q < 0.10` on the cluster-
   representative test (§9).
4. **Consistent football interpretation** — a qualitative, human/
   domain-review gate: does the direction and rough magnitude make
   football sense, or does it look like a statistical artifact? This
   is explicitly NOT automatable and is flagged as a manual review
   step in Phase 4, not something the pipeline itself certifies.
5. **Acceptable era/threshold robustness** — era-stable (§7's leave-
   one-season-out check) AND, for bust targets, consistent across
   20%/25%/30%/strict (prior version's threshold-sensitivity field).
6. **Holdout effect in the expected direction** (§10) — same sign,
   plausible magnitude on the untouched 2021+ window; not required to
   independently clear significance given real holdout power limits
   (especially for `bust_strict`), but must not contradict the
   discovery-window direction.
7. **Evidence of incremental usefulness beyond ADP, position, and era**
   (§8) — a real, non-trivial improvement on at least one of the four
   diagnostics versus the fixed baseline; a trait that is fully
   redundant with what ADP/position/era already encode does not
   advance no matter how strong its raw association looks.

Traits/clusters satisfying all seven are compiled into the Phase 4
final candidate list for Dataset 3, with the full standardized output
(§6) and every caveat carried forward — not a bare list of names.

---

## 12. Explicit stop point

**This document stops before Phase 1 begins.** No trait has been
tested against any of the 4 targets. The real work performed this
round (like last round) is entirely structural/outcome-free: the
extended predictor clustering (§1.5, 76 clusters) and the targets' own
aggregate discovery/holdout base counts (§4 — properties of the
targets alone, not of any trait-target association). Artifacts:
`data/exports/dataset2_trait_pipeline_predictor_inventory.csv`,
`data/exports/dataset2_trait_pipeline_near_duplicate_pairs.csv`,
`data/exports/dataset2_trait_pipeline_predictor_clusters.csv`.
