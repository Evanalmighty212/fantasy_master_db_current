# Dataset 2 standardized first-wave trait-analysis pipeline — proposal (2026-07, revised)

**Status: PROPOSAL ONLY. No predictor has been tested against any
outcome/target in this document.** Every real computation performed
this round and prior rounds is a STRUCTURAL characterization of the
440-column predictor whitelist and the 4 targets' own aggregate base
rates — never a predictor-vs-outcome association test
(`research/dataset2/trait_analysis_pipeline_predictor_inventory.py`).
Phase 1 (the first actual predictor-vs-outcome pass) is proposed below
but **not executed**.

Decision-bearing clustering is built from the canonical predictor
table, never the joined analysis view. Its approved discovery-fit
population is the 8,161 rows with prediction seasons 2006-2020
inclusive. The canonical table remains full-range (11,784 rows,
prediction seasons 2006-2026; 444 columns), and the mechanically
derived predictor whitelist contains 440 columns.

**Revision note (discovery-fit implementation and artifact
reconciliation, 2026-07)**: commits `648ccad` and `7a64231` approved
and implemented the 2006-2020 discovery-fit boundary. All current
inventory, near-duplicate, clustering, representative-selection, and
overlap-floor results reported as decision-bearing below use only
those 8,161 canonical predictor rows. They never consult
`outcome_join_status` or any outcome, target, label, or eligibility
field. The current result is 143 clusters from 227 content columns;
membership is identical at overlap floors 30, 50, and 100. Earlier
434-predictor/133-cluster and full-range or outcome-matched figures in
the historical revision notes are retained only as superseded
decision history.

**SUPERSEDED historical revision note (third revision, 2026-07: age
included)**: family #2
(age) was moved from deferred to Wave 1 per explicit instruction, once
real `schedules.csv` (nflverse `games.csv`) was fetched/pinned via the
established GitHub Actions path — see revised §11.7. All predictor
inventory, near-duplicate, and clustering numbers throughout §1 and
§1.5 below are RECOMPUTED against the new 434-column whitelist
(431 + `fam2_age_at_week1_years`/`fam2_age_x_experience`/
`fam2_age_position_z`), verified deterministic (two independent runs,
byte-identical CSV output). No outcome/target was inspected to produce
any number in this revision.

**SUPERSEDED historical revision note (second revision)**: §1.5
(predictor clustering) was
now fully replaced. The originally-approved methodology (commit
`e648dcf`) produced a 69-member cluster driven by shared
eligibility/gating similarity and single-linkage chaining, per review.
The revised methodology (§1.5.1-1.5.4) adds a semantic pre-filter
parsed from the family #9 naming convention (concept = position ×
metric_category × volume-or-efficiency, computed BEFORE any statistic
runs), excludes eligibility columns from every similarity edge,
replaces raw boolean agreement with prevalence-aware Jaccard(positive)
+ phi, and replaces connected-components with complete linkage. Real
result (recomputed with age, see above): 133 clusters, 0 exceeding 10
members — the 69-member cluster is fully resolved. Two real bugs were
caught and fixed during this verification, both disclosed in §1.5.3 (a
semantic bug that would have wrongly attached a threshold flag to an
unrelated efficiency measure, and a determinism bug from Python's
hash-randomized set iteration). Everything else (§2 onward) is
unchanged from the prior revision (commit `e648dcf`, directionally
approved).

---

## 1. Real predictor inventory (current discovery-fit population, structural only)

Restricted solely by `prediction_season` to the 8,161 canonical
predictor rows from 2006-2020 inclusive. No joined analysis-view field
participates in selection.

| Dimension | Breakdown |
|---|---|
| **Variable type** | continuous: 221 · boolean: 214 · categorical/status: 5 |
| **Position scope** | RB: 130 · ALL: 91 · WR: 79 · TE: 76 · QB: 64 |
| **Family** | family #9: **385 of 440** · Source A base: 11 · family #86: 9 · family #10: 7 · family #4: 4 · families #2/#6/#7/#88: 3 each · families #1/#8 and Source B: 2 each · family #18: 3 · family #39/#44 and canonical metadata: 1 each |
| **Constancy within discovery fit** | 432 vary · 6 universally constant · 2 `discovery_fit_degenerate`: `fam86_wr_league_starter_group_size_norm`, `fam9_team_first_half_team_games` |
| **Near-duplicate continuous pairs** (`\|r\|>=0.95`) | 278 unrestricted descriptive pairs among the discovery-fit continuous columns |
| **Single-season concentration** (outcome-free: share of a trait's own non-null values in its single busiest real season) | **0 columns exceed 50%** — no predictor's apparent coverage is a one-season artifact |
| **Position-scoped low coverage** (`<50%` applicable, within the trait's own position population) | 65 columns |

Recomputed deterministically in 2026-07 against the current
440-column whitelist and approved discovery-fit population.

### 1.5 Outcome-free predictor clustering — REVISED (resolves the 69-member cluster)

**The prior version's clustering was flawed in exactly the way review
flagged: it let shared applicability/eligibility create similarity
edges, and its connected-components (single-linkage) merge let
distant, unrelated members chain together through intermediate ones.**
This section replaces it entirely. Methodology, findings, and the full
resolution below; implementation:
`research/dataset2/trait_analysis_pipeline_predictor_inventory.py`.

#### 1.5.1 Semantic structure, parsed from the family #9 naming convention

Every family #9 column (385 of 440 whitelist columns) is parsed —
**before any statistic runs** — into: `basis` (team-game vs.
active-game), `window` (`final_4`/`final_6`/`final_8`/`first_half`/
`second_half`), `position`, `metric_category` (e.g. `rushing`,
`receiving`, `passing`, `snap`), `metric_type` (the specific
measurement — `opportunity`, `production`, `efficiency_rate`,
`role_present`, etc.), and `kind` — one of:

- **`content`** (227 columns, recomputed on the discovery-fit
  population) — a real, continuous measurement.
- **`role_tier`** (117 columns) — `role_present`/`meaningful_role`/
  `strong_lead_role`: threshold flags derived from ONE underlying
  continuous measure, known by construction (this project's own
  three-tier framework), never independently inferred.
- **`eligibility`** (88 columns) — `*_volume_eligible_exploratory`/
  `*_volume_eligible_sensitivity`/`has_snap_coverage`/
  `sample_qualified_*`: gating flags, **excluded from every
  statistical similarity edge, always** — reported as associated
  metadata on their concept's cluster, never merged in as content.

Parser validated with **zero unparsed leftovers** against all 386 real
`fam9_*` whitelist columns before being trusted for anything.

**A `metric_family` split (volume vs. efficiency) was added within
`metric_category` after a real check caught a genuine error** (§1.5.3)
— "how much opportunity/role a player had" and "how efficient they
were with it" are different football questions that happen to share a
`(position, metric_category)` stem; they must not be treated as one
concept.

**`concept_key = (position, metric_category, metric_family)`** is the
ONLY basis on which two columns are even considered for a similarity
check — different base metrics (e.g. rushing vs. receiving) can never
merge regardless of any statistical coincidence, satisfying the
instruction directly.

#### 1.5.2 Revised similarity measures and linkage

- **Continuous-continuous**: Pearson `|r| >= 0.95`, computed ONLY on
  jointly-non-null rows within the same `concept_key`, `n >= 50`
  documented minimum overlap (5x this project's existing
  `DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE=10` floor — a pairwise
  similarity decision needs a larger floor than a single reported
  cell).
- **Boolean-boolean** (non-fam9 content booleans, e.g. `fam86_*`
  indicators): **Jaccard on POSITIVE cases only `>=0.70` AND phi
  (Pearson on the 0/1 encoding) `>=0.85`, BOTH required**, same `n>=50`
  minimum, same `concept_key` restriction (family-based for non-fam9
  columns, plus 2 manually-verified real cross-family links —
  `fam10_starter_group_size`~`fam86_wr_starter_group_size`, r=1.0000,
  literally the same real football fact from two family modules).
  Raw agreement was explicitly replaced — it is dominated by shared
  `False`, exactly the failure mode instruction named.
- **Linkage: COMPLETE, not connected components.** Within each
  `concept_key` group, `scipy`'s complete-linkage hierarchical
  clustering is cut at the distance matching the similarity threshold
  — this GUARANTEES every resulting cluster's WORST internal pairwise
  similarity still clears the bar. This is the direct structural fix:
  the original cluster was a single-linkage chain (A~B~C~D~...) whose
  distant members were never actually similar to each other; complete
  linkage cannot produce that.
- Missingness-pattern similarity is never itself a similarity edge —
  it is reported separately (§1.4's coverage/concentration fields), as
  metadata about a column, never as evidence two columns measure the
  same thing.

#### 1.5.3 A real bug caught by verification before trusting the result

Before finalizing, representative-to-member similarity was checked
directly rather than assumed. **Real finding**: `role_present`
correlates at **r=0.82** with the `opportunity` measure in its own
concept but only **r=-0.02** (no relationship at all) with
`efficiency_rate` — yet the first version of this clustering had
merged them into ONE cluster, because `(position, metric_category)`
alone doesn't distinguish "how much role/opportunity" from "how
efficient." Fixed by adding the `metric_family` split (§1.5.1) so
role-tier flags only ever attach to the volume/opportunity measure
they are actually constructed from. This is exactly the kind of
verification this review round asked for, and it caught a real error
the first version would have silently carried into representative
selection.

**A second real bug was caught and fixed during this round's own
development**: Python's per-process hash randomization for strings
made raw `set` iteration non-deterministic, producing two DIFFERENT
apparent results (0 vs. 3 clusters over 10 members) from two runs of
otherwise-identical code before the fix. All iteration is now via
`sorted()`; determinism verified by running the script twice and
diffing byte-identical output before any number below was trusted.

#### 1.5.4 Real, corrected result

**Current discovery-fit result (recomputed 2026-07).** The following
age discussion records why family #2 contributes two clusters:
2 new outcome-free clusters: `{fam2_age_at_week1_years,
fam2_age_x_experience}` (paired on real, expected collinearity -- the
interaction term is literally `age * experience`) and
`{fam2_age_position_z}` (a singleton -- no other column shares its
`(age, position-adjusted)` semantic concept). Every other family's
cluster membership is unaffected (age doesn't share a semantic concept
with any fam9/fam86/fam10/etc. column, so it can only ADD clusters,
never move existing members between them -- verified by inspecting the
full cluster CSV, not just the summary counts).

**432 varying columns → 143 clusters.** Sizes: 91 singletons, 38
of size 2-5, 14 of size 6-10, **0 exceeding 10 members** — the
69-member cluster remains fully resolved.

| Metric | Value |
|---|---|
| Content columns clustered | 227 |
| Role-tier columns attached by known construction | 117 |
| Eligibility columns excluded from all edges, attached as metadata | 88 |
| Pairs statistically checked (post semantic pre-filter) | 1,043 |
| Distinct semantic concepts | 35 |
| Largest real cluster | 10 members |

The previously verified boundary cases remain visible in the current
artifact: `fam9_active_final_6_te_receiving_efficiency_rate` and
`fam9_active_final_8_te_receiving_efficiency_rate` now occupy separate
singleton clusters, while the active final-4/final-6/final-8 QB
passing-efficiency trio remains together with
`fam9_active_final_4_qb_passing_efficiency_rate` as representative.

**Historical disclosed discrepancy, superseded by the current
artifact**: the
prior (431-column, pre-age) revision of this document stated "8
clusters tied" at the size-10 maximum. Re-running the SAME,
unmodified clustering script (`trait_analysis_pipeline_predictor_inventory.py`
— not touched by that round's age work) against the then-current data
now finds 12, all legitimate fam9 `{team,active} x {final_6} x
{position}_{metric}_meaningful_role` concepts, none involving age.
Since age cannot affect fam9 cluster membership (different, disjoint
semantic concepts) and no clustering code changed, this is most likely
a pre-existing staleness in that prior count rather than anything
caused by this round's change -- flagged for the record rather than
silently corrected without investigating its origin, per this
project's disclosure convention. Does not affect the 0-clusters-over-10
finding or any evidence-gate decision.

**Audit for every cluster exceeding 10 members: none exist.** The
8 clusters at the real maximum (10 members) are all the SAME
well-formed pattern — one real football concept (e.g. "WR receiving
opportunity") merging its `team`/`active` basis × `final_6`/`final_8`
window variants plus their attached role tiers. Worked example
(`data/exports/dataset2_trait_pipeline_predictor_clusters.csv`,
cluster containing `fam9_team_final_6_wr_receiving_opportunity`):

| Field | Value |
|---|---|
| Concept | `(WR, receiving, volume)` |
| Size | 10 |
| Members | `{team,active}` × `{final_6,final_8}` × `{opportunity, opportunity_per_team_game, role_present, meaningful_role, strong_lead_role}` (window/basis-appropriate subset) |
| Eligibility metadata attached (excluded from edges) | the corresponding `efficiency_volume_eligible_*` flags for this concept — reported, never merged in |
| Recommended representative | `fam9_team_final_6_wr_receiving_opportunity` — the raw continuous measure, per priority 1 (coverage) AND priority 5 (continuous over threshold flag) agreeing this time |
| Any edge removed as eligibility-driven? | Yes — by construction, eligibility columns never entered a similarity edge in the first place |

**Representative selection real result**: after the `metric_family`
fix, **zero clusters** select a threshold flag as representative — the
continuous source measure wins every time, resolving the earlier
close-call tension this same audit process surfaced (§1.5.3's fix
addressed the root cause rather than needing a tie-break override).

**Representative selection rule** (unchanged priority order, all
outcome-free, per instruction): (1) highest applicable coverage within
the trait's own position scope (§1.2); (2) prefer a continuous source
measure over a mechanically-derived threshold flag; (3) broader
historical season coverage; (4)/(5) fewer compounded assumptions,
proxied by shorter column name.

Full cluster membership + chosen representative + eligibility metadata:
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

**Superseded proposal**: grouped k-fold cross-validation (grouped by
`player_id`, so no player's seasons split across train/test folds
within a fold), run ONLY within the discovery window (§10) — never
touching holdout data, consistent with the rest of this pipeline.
Section 11.9 replaces this with approved expanding discovery windows.

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
| **Raw trait-target combinations** | 440 × 4 = 1,760 structural; 432 × 4 = 1,728 varying discovery-fit formulations | Full whitelist × all 4 targets; the 8 non-varying discovery-fit columns are excluded before testing |
| **Testable combinations after evidence gates** (§5) | Computed per target once Phase 1 actually runs (cannot be stated without touching outcome eligibility per trait — genuinely unknown until Phase 1) | Gate gate application is itself part of Phase 1, not precomputable outcome-free |
| **Predictor clusters** | **143** (semantic pre-filter + complete linkage; 0 clusters exceed 10 members) | Outcome-free, fit only on canonical predictor seasons 2006-2020 |
| **Primary FDR tests** | ≤ 143 × 4 = 572 nominal, reduced further per target by §5's gates | Cluster representatives only |
| **Within-cluster sensitivity tests** | The remaining clustered non-representative content/role formulations, tested only as secondary formulation/threshold sensitivities AFTER their cluster's representative already cleared Phase 2 | Never independently entered into the FDR budget |

**Superseded procedure**: Benjamini-Hochberg FDR control, **q=0.10**, applied to
the cluster-REPRESENTATIVE primary tests only (§1.5's representative
selection), **separately per target** (four independent FDR runs —
Star/primary-bust/strict-bust/diagnostic are different questions and
never share a correction budget, consistent with the approved round
1/2 bust-label work's own position on this).

Section 11.9 supersedes the four-run structure with three separate
families: continuous LWI, Star, and strict bust. Broad bottom-20% is
secondary/contextual rather than an independent primary FDR family.

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

**Superseded automatic-conjunction proposal.** A trait or cluster advances toward Dataset 3 candidacy on a given
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
Section 11.9 replaces this automatic robustness conjunction with
descriptive robustness tiers while retaining the approved family-wise
FDR and outcome-specific practical-effect rules.

---

## 11.5 Firth validation status — INDEPENDENT CROSS-CHECK COMPLETE (2026-07)

1. **91.3% empirical profile-CI coverage (150 sims, nominal 95%) —
   still documented as below nominal, per instruction, not rounded up
   to "close enough."** This is a real, disclosed property of
   profile-likelihood CIs at modest sample size, not a bug — the
   algorithm fix below did not change this number (it addressed a
   different, more severe failure mode specific to extreme/separated
   profile points, not this simulation's moderate-effect regime).
2. **Independent cross-check: COMPLETE, and it caught a real bug.**
   `.github/workflows/fetch_schedules_and_firth_crosscheck.yml`'s
   `firth-crosscheck` job ran R's `logistf` on the identical
   `ordinary`/`sparse`/`complete_separation` fixtures. The FIRST run
   found genuine disagreements (CI bounds off by 1-9 units on
   `complete_separation`) — root cause: this module's constrained
   (fixed-coefficient) refit, used internally by the CI/LR-test search,
   could report `converged=True` while still sitting on a real,
   verified-lower log-likelihood than the true conditional maximum, in
   the quasi-separated regime that arises when profiling pins one
   coefficient far from its MLE. Fixed by always cross-checking
   constrained fits against a robust general-purpose optimizer
   (`_fit_firth_constrained_scipy`) and keeping whichever result is
   higher — never trusting IRLS's own convergence flag alone. **After
   the fix, all 9 term comparisons across all 3 fixtures agree with R
   to under 1e-6** (coefficients, profile CIs, and LR p-values) —
   real, committed results at
   `research/dataset2/firth_crosscheck_results_2026_07/`, replayed as
   a permanent local regression test
   (`tests/test_firth_logistic.py::TestIndependentImplementationCrossCheck`,
   no longer skipped).

**Adjusted Star results are therefore no longer provisional on this
specific ground** — the independent cross-check the prior caution was
waiting on is done and passing. §5's other evidence gates (applicable
n, positive-case minimums, etc.) still apply as their own independent
requirements before any specific trait's adjusted result counts as
formal.

## 11.6 Three future outcome proposals — RECORDED, NOT IMPLEMENTED

Per instruction: documented here for future consideration, no design
work or implementation performed this round, and NONE of the existing
Tier 1 targets (`star_by_value_label`, `bust_primary_label`,
`bust_strict_below_replacement_label`) are changed by recording these.

1. **A broader Tier 2 / "high-value-hit" Star outcome** — a less
   restrictive companion to `star_by_value_label` capturing a wider
   band of real success (not just the current Star bar), to
   distinguish predictors of "clearly good value" from predictors that
   only catch the rarest top tier. Real motivation: `star_by_value_label`'s
   own 0.9% base rate (§1's real number) leaves very little room for
   Phase 1 to detect anything beyond the strongest possible effects,
   even with Firth's bias reduction — a broader outcome would trade
   some of that rarity for statistical power, as a genuinely different
   (not a replacement) research question.
2. **A position-relative severe-bust sensitivity that includes QBs
   fairly** — motivated by §1.5/§25's real, disclosed finding that the
   current `bust_strict_below_replacement_label`'s `P<0` floor is
   structurally NOT position-symmetric (zero QBs in the entire dataset
   ever clear it, since QB replacement level rarely goes negative even
   in a bad season) — a position-RELATIVE severe-bust definition (e.g.
   an extreme percentile within each position's own distribution,
   rather than one shared absolute floor) would let QB severe busts
   exist as a category at all.
3. **A material-cost bust sensitivity distinguishing costly early/mid-
   round failures from low-cost late-round misses** — motivated by
   §25's real prevalence finding that `bust_primary_label`'s rate is
   ALREADY roughly uniform across ADP buckets by construction (the
   percentile mechanism guarantees ~20% in every bucket) — a
   materially different question ("how much real fantasy-market cost
   did this failure represent") would need its own construction, not a
   re-read of the existing rate table, since a late-round miss and an
   early-round miss currently count equally toward the same label
   despite representing very different real stakes.

These remain proposals only — no eligibility population, threshold, or
column has been designed, and none will be built until explicitly
approved in a future round.

## 11.7 Age (family #2) — Wave 1 rebuild COMPLETE (2026-07)

**Decision reversed since the prior round, now fully executed.** Age
was moved to Wave 1 per explicit instruction. The blocking prerequisite
(`schedules.csv`, real per-team Week-1 kickoff dates) has been
fetched, pinned, and integrity-verified via the established GitHub
Actions path.

**Schedule source and coverage**: nflverse `games.csv`, fetched via
`.github/workflows/fetch_schedules_and_firth_crosscheck.yml`'s
`fetch-schedules` job (manually triggered, reviewed, and merged this
round) and `scripts/nflverse_source.py`'s
`register_schedules_manifest_entry()`/`fetch_schedules()` pin/fetch/
integrity-check machinery. 7,548 real games, seasons 1999-2026,
sha256-verified against the pinned hash recorded in
`scripts/nflverse_source_manifest.json`'s `"schedules"` entry
(`252ef81b...57f1f62`, asset id `495643391`). Zero nulls on any of
`season`/`week`/`gameday`/`home_team`/`away_team`/`game_type` in the
raw fetched file.

**Age coverage and missingness audit**, against the rebuilt canonical
predictor table (`data/exports/dataset2_canonical_predictor_table.parquet`,
11,784 rows). **Historical team-code crosswalk applied this round**
(see below) — the numbers here are POST-fix.

| Population | `fam2_age_at_week1_years` null rate |
|---|---|
| Full predictor table (11,784 rows, includes the 609 structurally-future 2026 rows that are null for every non-fam9 family, not just age) | 642 / 11,784 = 5.4% |
| Historical rows only (11,175 rows -- the outcome-join-eligible population §1's inventory is computed against) | 33 / 11,175 = 0.30% |

**Historical team-code crosswalk (this round's fix)**: the first pass
of this rebuild found 624 historical-row nulls (5.6%), audited and
traced to a real, verified cause -- the master population's team
column always uses the CURRENT/canonical code for a franchise (`LV`/
`LA`/`LAC`) even for historical pre-relocation seasons, while the real
nflverse schedule file uses whichever code was ACTUALLY in use that
season (`OAK`/`STL`/`SD`). A full audit of every population team code
with no real Week-1 schedule match, by season, found EXACTLY 5 codes
affected -- `LV`, `LA`, `LAC` (relocation-driven, 617 of the 624 rows)
plus `MIA`/`TB` in 2017 only (33 rows -- see below, not a code
mismatch). `lib/dataset2/common.py` now carries a deterministic,
season-aware `HISTORICAL_TEAM_CODE_ALIASES` table (Oakland→Las Vegas
Raiders 1999-2019, St. Louis→Los Angeles Rams 1999-2015, San Diego→Los
Angeles Chargers 1999-2016 -- the exact real season ranges each
historical code appears in the real schedule file, verified directly)
applied ONLY inside `week1_kickoff_by_team()`'s own per-season kickoff
lookup -- additively (the raw historical code still resolves too,
never replaced) and never touching population's own `team` column or
any other canonical team identity. Proven via
`tests/test_dataset2_common.py::TestHistoricalTeamCodeAliases` (8
tests: correct historical-date resolution for all 3 relocations,
season-aware boundary enforcement, no guessing for unverified codes,
determinism, no unrelated team-season affected) and
`tests/test_dataset2_experience_age_draft.py`'s new end-to-end
relocation test.

**Remaining 33 historical nulls, by reason** — every one traced, none
approximated: **0 missing a real players.csv `birth_date` match, 0
remaining relocation/team-code mismatches** (fully resolved by the
crosswalk above). All 33 are `MIA` (16) and `TB` (17) in the 2017
season specifically -- a real, genuine schedule gap, NOT a code
mismatch: the real MIA@TB Week-1 game was postponed league-wide due to
Hurricane Irma and never replayed as a real "Week 1" game (their real
first games of that season were Week 2, confirmed directly against the
real schedule file). Correctly left null per this project's
missingness policy -- guessing a kickoff date that was never real
would violate it. `fam1_experience_years` (needs only a `players.csv`
match, no schedule) has 0% historical missingness, confirming the
entire remaining 0.30% gap is this one real 2017 schedule anomaly, not
any residual match-quality issue.

**Historical age-rebuild counts (superseded by §1 and §11.8)**: 434
predictors (431 + 3 age
columns), 133 clusters, 0 exceeding 10 members (up from 431/131 --
see §1 and §1.5.4 for the full recomputed inventory/clustering
detail). Analysis view: 462 columns, 434-column predictor whitelist.
Rebuild verified deterministic (byte-identical CSV output across two
independent runs of both the predictor-table build and the
outcome-free inventory/clustering script) before any number above was
trusted.

**Confirmation that no target was opened**: the outcome table
(`data/exports/dataset2_canonical_outcome_table.parquet`) was not
recomputed or read by any step in this round except
`build_dataset2_analysis_view.py`'s existing read-only join. At that
time it re-verified hardcoded counts from the then-current artifact
state, including a broad-primary-bust total that was later superseded
by governed-source, market-status, and discovery-only-reference work.
That historical total is not a current acceptance criterion; current
validation uses the governed frozen-reference and label/eligibility
invariants instead.
No descriptive screening, regression, FDR calculation, or advancement
decision was run against any trait-outcome relationship.

**Explicitly NOT blocking Wave 1, still deferred exactly as before**:
family #88's workload/durability opportunity-based sub-signal
(`workload_qualified`, still the literal placeholder `"pending"`) and
Source C (participation-derived predictors, no player-season aggregate
exists yet) — see `DEFERRED_FAMILIES` (now 2 entries, family #2
removed).

**Separately disclosed, NOT touched this round**: `_build_fam10_86_layer()`
in `lib/dataset2/canonical_predictor_table.py` has its OWN, unrelated
empty-schedule usage (feeding `build_depth_chart_traits()`'s 2025
rookie-QB depth-chart-schema correction) — a distinct prerequisite from
age's, not part of this round's scope, and not silently fixed
alongside it. Still a real, open item for a future round if requested.

---

## 11.8 Source A targets/receiving-air-yards coverage remediation (2026-07) — discovery-fit reconciliation

**Historical note**: the older counts formerly reported in §1,
§1.5, and §9 (434 predictors,
133 clusters, 223 content columns, 274 near-duplicate pairs at
`|r|>=0.95`) predates BOTH family #18 (receiving efficiency) and family
#88's workload core, which were built and committed in the interim
(see `CHANGELOG.md`). Later 138/144-cluster and 276/266/320/478-pair
figures were full-range or outcome-matched diagnostics, not the
approved discovery-fit calibration. They are superseded for
decision-bearing Dataset 2 clustering, but remain useful only when
explicitly labeled with their historical population.

**The remediation itself**: `research/dataset2/SOURCE_A_TARGETS_COVERAGE_REMEDIATION_AUDIT_2026_07.md`
documents a real Source A data-quality gap — `targets` and
`receiving_air_yards` are ~99.5-99.7% zero-filled (not real zeros) in
the underlying nflverse weekly file for observation seasons 2006-2008
only, a clean break at 2009. A centralized, dtype-aware coverage mask
(`apply_source_coverage_null_mask()` in `lib/dataset2/common.py`) now
forces 149 audited, target-derived canonical columns (5 Source A
fields + 144 Family #9 receiving-opportunity/efficiency/role fields,
generated programmatically from the real `window_ns`, not hardcoded)
to real null for prediction seasons 2007-2009, replacing what were
previously invalid non-null (mostly zero) values. **45,240 cells**
changed from invalid non-null to null (3,980 Source A + 41,260 Family
#9); verified via a null-safe diff that 0 cells changed outside this
149-column/3-season scope in either direction. Column count is
unchanged (444/440) — the mask nulls values, never drops or adds
columns. Full test suite: 1,166 passed (up from 1,144, +22 new tests).

**Discovery-fit effect on clustering (recomputed directly from the
canonical predictor tables)**: the pre-remediation state was rebuilt
from commit `ce904af`, and both states were selected solely by
prediction seasons 2006-2020 (8,161 rows). The same current clustering
implementation was then applied to both states. No outcome or joined
analysis-view field entered either computation.

| Metric | Pre-remediation (post-fam18/88 baseline) | Post-remediation (current) |
|---|---|---|
| Population | 8,161 rows, prediction seasons 2006-2020 | 8,161 rows, prediction seasons 2006-2020 |
| Content columns | 227 | 227 (unchanged — mask affects values, not column set) |
| Final cluster count | 135 | **143** (+8) |
| Singleton clusters | 81 | 91 (+10) |
| Cluster size 2-5 / 6-10 / >10 | 40 / 13 / 1 | 38 / 14 / 0 |
| Largest cluster | 15 | 10 |
| `MIN_OVERLAP_N` 30/50/100 membership | identical at all three | identical at all three (stability holds) |
| Near-duplicate pairs `\|r\|>=0.95` | 294 | 278 (-16) |
| Near-neighbor pairs `0.90<=\|r\|<0.95` | 327 | 476 (+149) |

At each overlap floor, the 213 continuous columns produced identical
pre/post computable-pair sets: 13,797 pairs at 30, 13,794 at 50, and
13,707 at 100. The 268 category-changing pairs followed the same
transition matrix at every floor: 180 `<0.90 -> 0.90-0.95`, 48
`0.90-0.95 -> <0.90`, 17 `>=0.95 -> 0.90-0.95`, 11
`>=0.95 -> <0.90`, and 12 `<0.90 -> >=0.95`; none became newly
computable. Every changing pair touched at least one of the 149
remediated Source A-derived columns.
All other off-diagonal transitions were zero, including 0.90-0.95 -> >=0.95 and every transition to or from unavailable/below-floor.

**Interpretation**: forcing invalid non-null (mostly-zero) Source A
target/air-yards values to real null for 2007-2009 reduces the
pairwise jointly-non-null overlap used to compute correlations among
the affected Family #9 window-variant columns. Several pairs that were
previously artificially glued together at `|r|>=0.95` (partly on the
strength of a shared block of invalid zeros) now fall into the
0.90-0.95 band or lower once those invalid values are correctly
excluded — this is exactly the expected, correct consequence of
removing bad data from a correlation computation, not a clustering
regression. `MIN_OVERLAP_N` floor stability (30/50/100 all identical)
continues to hold post-remediation, confirming the cluster count shift
is a real correlation-strength effect, not an overlap-sample-size
artifact. No clustering threshold or default was changed to produce
this table — same script, same `NEAR_DUPLICATE_CORR_THRESHOLD=0.95`,
same complete-linkage cut.

Regenerated discovery-fit clustering artifacts (all deterministic,
byte-identical across two independent runs):
`data/exports/dataset2_trait_pipeline_predictor_inventory.csv`,
`data/exports/dataset2_trait_pipeline_near_duplicate_pairs.csv`,
`data/exports/dataset2_trait_pipeline_predictor_clusters.csv`.

---

## 11.9 Superseding approved Phase 1 inference freeze (2026-08)

**Methodology status: APPROVED by Evan.**

**Implementation status: PHASE 1 RUNNER IMPLEMENTED; REAL PHASE 1 NOT RUN.**

The following rules supersede conflicting proposals earlier in this
document while preserving those passages as decision history:

- Primary outcomes are continuous canonical LWI, Star, and strict bust.
  Strict bust is frozen-reference bottom-tail relative
  underperformance plus `P < 0`; broad bottom-20% becomes the
  secondary/contextual `relative_underperformance_bottom20`, with 25%
  and 30% variants retained as sensitivities.
- Bust calibration uses eligible 2010--2020 discovery rows only. Its
  empirical distributions, position x acquisition-cost/ADP-round x
  discovery-era cells, sparse/pooled routing, raw-production fallback,
  minimum-cell rules, and tie/midrank convention are frozen and
  versioned before 2021--2025 application. No holdout recalibration,
  reranking, routing reselection, or threshold change is permitted.
- The primary LWI practical-effect gate is an absolute adjusted
  contrast of at least 0.10 frozen discovery-outcome SD. With the
  current discovery SD of approximately 18.5406, that is approximately
  1.8541 raw LWI points. Continuous predictors use a one-discovery-
  period predictor-SD contrast, binary predictors use 1 versus 0, and
  categorical predictors use governed levels versus a predeclared
  reference. Report native-unit effects as well.
- Rare-Star Firth inference uses 2,000 player-cluster bootstrap
  replicates with a fixed recorded seed. Players and all their seasons
  are resampled together; repeated sampled players are retained
  correctly. Convergence, failed-replicate, and minimum-successful-fit
  safeguards fail loudly. The primary p-value is the two-sided,
  null-centered player-cluster bootstrap p-value with the standard
  finite-sample correction; sign-tail and bootstrap-t p-values are not
  used.
- Separate Benjamini-Hochberg `q = 0.10` correction applies within each
  of the three primary outcome families. Cross-outcome support is
  convergent evidence, not independent replication. Robustness is
  reported through descriptive tiers; the earlier automatic
  conjunction and any 80%-or-discard interpretation are superseded.
- Each candidate categorical predictor contributes one joint primary
  test to its outcome family's BH correction. Its governed
  category-versus-reference contrasts are reported as effect details,
  not as separate primary hypotheses. Acquisition-cost and position
  controls remain controls and do not enter the candidate FDR family.
  The fixed reference is `applicable` for
  `fam9_team_game_window_status` and `starter` for
  `fam10_depth_chart_status`. For `fam10_depth_chart_team` and
  `fam4_nfl_draft_team`, choose the most frequent non-null 2010--2020
  discovery category outcome-free, with alphabetical tie-breaking; the
  current governed discovery inputs select `CIN` for both. Record the
  chosen reference, frequency, denominator, and method in the run
  manifest, and fail loudly if a fixed reference is absent or a team
  reference cannot be derived.
- Temporal incremental validation uses expanding discovery windows,
  not the grouped random folds proposed in §8. The protected
  2021--2025 holdout remains untouched during fitting and tuning.
  Continuous-LWI validation reports out-of-window MAE, RMSE, and
  R-squared improvement for trait-plus-controls versus controls-only;
  all three are descriptive rather than automatic advancement gates.
- The discovery-era control is pre-2011 versus 2011+ within 2006--2020;
  no 2021+ era coefficient is fitted. Acquisition cost uses
  leakage-safe preseason categorical strata.

The strict-bust practical-effect gate is an adjusted Firth odds ratio of
at least `1.20` for an increase or at most the exact reciprocal
`1 / 1.20` for a decrease. Documentation may display that reciprocal as
approximately `0.83`, but governed code derives and uses the exact
reciprocal. Continuous predictors use a one-discovery-period-SD
increase; categorical predictors use the explicitly governed contrast.
The discovery-only diagnostic count is 54 of 1,746 eligible
(approximately 3.09%); it is not a claim about a Phase 1 result. Phase 1
remains unstarted. Dataset 3's separate split remains unresolved but is
not a Dataset 2 Phase 1 blocker.

## 12. Explicit stop point

**This document stops before Phase 1 begins.** No trait has been
tested against any of the 4 targets. The real work performed this
round is entirely structural/outcome-free: the age (family #2) rebuild
(§11.7), the revised, audited discovery-fit predictor clustering
(§1.5 and §11.8's 143-cluster remediated result, 0 exceeding 10
members), and the
targets' own aggregate discovery/holdout base counts (§4 — properties
of the targets alone, not of any trait-target association).
Artifacts:
`data/exports/dataset2_trait_pipeline_predictor_inventory.csv`,
`data/exports/dataset2_trait_pipeline_near_duplicate_pairs.csv`,
`data/exports/dataset2_trait_pipeline_predictor_clusters.csv`.
