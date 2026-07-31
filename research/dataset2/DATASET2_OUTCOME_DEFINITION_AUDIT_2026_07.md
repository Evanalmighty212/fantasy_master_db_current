# Dataset 2 outcome-definition / scope audit (2026-07)

**Status: DESCRIPTIVE ONLY.** Nothing in this document changes,
recomputes, or tests any predictor against `star_by_value_label`,
`bust_primary_label`, or `bust_strict_below_replacement_label`. Every
number below is either (a) a structural property of the OUTCOME
definitions themselves (a Star/bust label's own real distribution,
percentile mechanics, or eligibility population), or (b) a
predictor-family scope/effort estimate that never touches an outcome
column. Per instruction, Tier 1 (`star_by_value_label`,
`bust_primary_label`, `bust_strict_below_replacement_label`) is
UNCHANGED throughout. Phase 1 (trait-vs-outcome testing) has not
started.

**Every result below is a FINDING, not a change**:
- §1: Family #88's roadmap-stated blocker appears stale (the real
  ingredients already exist) — **no workload trait was implemented.**
- §2: The >=85% Star near-miss group is a **descriptive band only —
  no new Tier 2 label was created**, and `star_by_value_label` itself
  is unchanged.
- §3: The percentile-band examples are an **audit of the existing,
  already-approved `bust_primary_label` definition — not a new
  target**, and no threshold was changed.
- §5: The proposed material-cost ADP buckets were **compared against
  the current buckets — not adopted**; `config.DATASET2_ADP_ROUND_BUCKETS`
  is unchanged.
- §6b: The overlap-floor sweep is a **sensitivity check only — the
  committed script's `MIN_OVERLAP_N = 50` default was not modified**.
- Throughout: **no predictor was selected, ranked, or screened against
  any outcome column** — every predictor-side number (§1, §6) is
  computed from predictor data alone, and every outcome-side number
  (§2-5) is computed from outcome data alone; the two were never
  jointly modeled.

---

## 1. Family #88 — compact workload-core scope/effort audit

`lib/dataset2/fragility_traits.py::build_durability_risk_traits()`
currently ships only the age/frame half of family #88
(`fam88_body_size_position_z`) — `workload_qualified` is the literal
placeholder string `"pending"` (see `DEFERRED_FAMILIES`).
`research/dataset2/DATASET2_TRAIT_ROADMAP.md` (§ "88 (split, part)")
records the real, intended sub-bullets: "age + high prior workload,"
"small frame + workhorse role" (compound flags), and separately a
touch-count sub-signal ("prior 350+ touch season," "multiple 300+
touch seasons," "heavy playoff workload").

**Real finding: the roadmap's stated blocker is now stale.** The
roadmap text says the touch-count sub-signal needs "the same
already-fetched-but-not-retained carries/targets columns as #20" —
written before Source A (`lib/dataset2/usage_traits.py`) was rebuilt.
Checked directly this round: `build_raw_season_usage()` ALREADY
retains real per-season `carries` and `targets` totals (its `SUM_FIELDS`
tuple), and these are already lagged into the canonical predictor
table as `srcA_prior_season_carries`/`srcA_prior_season_targets`. A
touch-count-based workload flag is therefore a CHEAP derived compound
on already-computed, already-lagged columns — not a new
data-acquisition effort.

**One real gap remains for an EXACT touch count**: fantasy "touches"
is conventionally `carries + receptions`, not `carries + targets`
(targets includes incompletions). `receptions` is confirmed present in
the raw weekly source file (`data/raw/nflverse/annual/stats_player_week_*.csv`)
but NOT currently in `usage_traits.py`'s `SUM_FIELDS`/`WEEKLY_REQUIRED_COLUMNS`.
Effort to close this: add `"receptions"` to both tuples (same pattern
as every other summed field) — a small, low-risk change, not a new
source.

**Compact core, scoped**: age/frame half (DONE) + touch-count half
(carries + targets as an interim proxy, or carries + receptions after
the one-line `usage_traits.py` addition) = a real, buildable "compact
Family 88 workload core." The injury-specific sub-bullets ("repeated
lower-body injuries," "returning from surgery") are explicitly OUT of
this compact core — they depend on the `injuries` release
(2009-2025, schema still unverified per the roadmap), a materially
larger, separate acquisition effort.

**Real prevalence estimate** (descriptive only, using
`srcA_prior_season_carries + srcA_prior_season_targets` as the interim
touch proxy, against the 7,864 real historical predictor-table rows
with any real prior-season usage data):

| Proxy-touch floor | n rows | % of rows with data |
|---|---|---|
| >= 250 | 312 | 4.0% |
| >= 300 | 167 | 2.1% |
| >= 350 | 55 | 0.7% |

By position, the >=300 rate is essentially an RB-only phenomenon (RB
8.2%; QB/WR/TE all real-zero under this proxy) — matches football
intuition (targets+carries concentrate touches on RBs; a real WR/TE
workload signal would need routes/snaps, not targets+carries, and a
real QB workload signal needs attempts, not carries+targets — this
proxy is RB-appropriate only, a real, disclosed scope limit of the
"cheap" version).

**Effort estimate**: age/frame half already built. Touch-count half
(interim carries+targets proxy) — LOW effort, no new fetch, a new
`lib/dataset2/fragility_traits.py` function reusing existing lagged
columns plus tests. Exact-touches version (carries+receptions) — LOW
effort, one `usage_traits.py` field addition (with its own test
update) plus the same durability-flag work. Injury-specific
sub-bullets — NOT part of the compact core; a separate, larger
acquisition-and-schema-audit effort, out of scope here.

**This is a scope/effort estimate only — no workload trait, flag, or
`usage_traits.py` field was implemented this round.** `workload_qualified`
remains the literal placeholder `"pending"`, and `DEFERRED_FAMILIES`
is unchanged.

---

## 2. Tier 1 Star decomposition and candidate Tier 2 near-miss groups

Real `star_by_value_label` positives (Tier 1, unchanged): **76** of
8,537 `star_outcome_eligible` rows (0.9%), per position threshold
`SBV_STAR_THRESHOLD = {"QB": 176.5, "RB": 188, "WR": 171, "TE": 134}`
(`config.py`).

### 2a. Tier 1 decomposition (descriptive, no new label)

| Position | n Star |
|---|---|
| RB | 32 |
| WR | 19 |
| TE | 14 |
| QB | 11 |

| Era | n Star |
|---|---|
| 2011-2020 | 46 |
| 2021+ | 29 |
| pre-2011 | 1 |

| ADP bucket | n Star |
|---|---|
| R1-2 | 42 |
| R3-5 | 14 |
| R6-10 | 9 |
| R11+ | 6 |

### 2b. Candidate Tier 2 "near-miss" group (NOT a label, illustrative bands only)

Real, eligible, non-Star rows whose `star_by_value_score` falls within
a real percentage of their position's own Star threshold:

| Band (% of position threshold) | n non-Star rows | Combined with 76 real Stars |
|---|---|---|
| >= 95% | 14 | 90 |
| >= 90% | 47 | 123 |
| >= 85% | 78 | 154 (1.8% of 8,537 eligible) |
| >= 80% | 111 | 187 |

Position split of the >=85% near-miss band (78 rows): QB 14, RB 27,
TE 11, WR 26.

Real player examples, >=90% of position Star threshold, non-Star (top
of band):

| Player | Position | Season | Score | Threshold | % of threshold |
|---|---|---|---|---|---|
| Arian Foster | RB | 2011 | 187.7 | 188 | 99.8% |
| Matt Forte | RB | 2013 | 187.2 | 188 | 99.6% |
| Davante Adams | WR | 2018 | 170.2 | 171 | 99.5% |
| Ezekiel Elliott | RB | 2016 | 186.0 | 188 | 98.9% |
| Wes Welker | WR | 2011 | 169.2 | 171 | 98.9% |
| Josh Jacobs | RB | 2022 | 185.2 | 188 | 98.5% |
| De'Von Achane | RB | 2025 | 184.8 | 188 | 98.3% |
| Rob Gronkowski | TE | 2014 | 131.2 | 134 | 97.9% |
| Josh Allen | QB | 2021 | 171.8 | 176.5 | 97.3% |
| Antonio Brown | WR | 2017 | 162.0 | 171 | 94.7% |

**Read for a candidate Tier 2 design** (per §11.6 proposal #1 of the
trait-analysis pipeline doc, recorded not implemented): a real
"high-value-hit" companion outcome capturing this near-miss band would
roughly double-to-triple the positive count available for Phase 1
screening (76 -> ~150-190 depending on the band chosen) while staying
concentrated in RB/WR — real statistical power gain, still no design
decision made here (threshold, exact band, and eligibility population
all remain open per the recorded proposal).

---

## 3. Bust percentile-band player examples (bottom 10% / 10-15% / 15-20% / just above 20%)

`bust_primary_label`'s own real ranking percentile (`pct_final`) is
computed internally by `_assign_bust_primary_labels()` but never
persisted to the final outcome table (only the boolean labels are).
Independently reproduced this round in
`research/dataset2/bust_percentile_band_audit_2026_07.py` — a
read-only script that calls the real, already-tested
`build_canonical_outcome_table()` for ground truth, separately
recomputes `pct_final` with the same mechanical groupby/rank logic,
and validates its own label reproduction against the real, persisted
`bust_primary_label` before trusting any number below.

**Validation: 2,677 comparable eligible rows, 0 disagreements.**

| Band | n rows | Example players (lowest pct_final first) |
|---|---|---|
| Bottom 10% (pct_final <= 0.10) | 254 | Kamar Aiken (WR, 2016), Maurice Jones-Drew (RB, 2014), Brett Favre (QB, 2010), Nelson Agholor (WR, 2015), Ty Montgomery (WR, 2019) |
| 10-15% | 127 | John Carlson (TE, 2010), Terrace Marshall Jr. (WR, 2021), Stevan Ridley (RB, 2013), Michael Floyd (WR, 2014), John Brown (WR, 2016) |
| 15-20% | 141 | Corey Davis (WR, 2017), Andre Ellington (RB, 2015), Marshawn Lynch (RB, 2015), Keenan Allen (WR, 2016), N'Keal Harry (TE, 2020) |
| Just above 20% (20-25%) | 137 | LeGarrette Blount (RB, 2018), Corey Coleman (WR, 2017), Jonathan Mingo (WR, 2023), C.J. Spiller (RB, 2014), Robert Woods (WR, 2022) |

Real, useful observation: the bottom-10% band includes several
real, once-productive veterans in decline seasons with clearly
negative `score_like` (Brett Favre 2010, Maurice Jones-Drew 2014) --
consistent with the bust label's own design intent. The 15-20% and
just-above-20% bands include real, closer-call seasons (Marshawn Lynch
2015's injury-shortened year, Keenan Allen 2016's own injury-shortened
year) -- both real positive `P` values, illustrating that a "primary
bust" near the 20% cutoff is not always a clearly bad real season, just
a real bottom-quintile-within-cell one. Purely descriptive; no
threshold changed.

---

## 4. Late-round expected-production audit — the 17 lookup-gap rows

`underperformance_diagnostic_ineligibility_reason ==
"expected_production_lookup_out_of_range"` covers **19 real rows**
total, per the existing, exposed
`_COLUMN_REGISTRY` documentation in
`scripts/build_dataset2_canonical_outcome_table.py`: "the 17-row gap
plus the 2 already-known unscoreable rows." Verified directly against
the real outcome table this round:

- **17 rows**: `real_status == "below_production_gate"` with a real
  ADP round that has NO fitted (season, position, round) `E_P` cell —
  the genuine new gap.
- **2 rows**: `real_status == "unscoreable_expected_production_out_of_range"`
  — already excluded from Star eligibility by a separate, pre-existing
  mechanism (not new information, but sharing the same root cause).

All 19 rows are real ADP round 15-17 (late round), confirming this is
structurally a late-round E_P-lookup coverage gap, not scattered
across the round distribution:

| ADP round | n |
|---|---|
| 15 | 3 (all outcome_season 2021) |
| 16 | 12 (all outcome_season 2025) |
| 17 | 4 (all outcome_season 2025) |

15 of the 19 rows are `outcome_season == 2025` — the real, current
season, where round-16/17 ADP simply has too few real matched
observations yet for a position/round `E_P` cell to be fit at all
(the same real cold-start pattern era-stratification's own
`DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE` gate exists to catch
elsewhere in this pipeline). Real player examples: Michael Wilson (WR,
2025, R16), Theo Johnson (TE, 2025, R16), Devin Singletary (RB, 2025,
R16), Darius Slayton (WR, 2025, R17), Miles Sanders (RB, 2025, R17).

**Distinct from `bust_primary_label`'s own lookup gap** (a different
mechanism, coincidentally also 19 rows this round, per §24 of the bust
label proposal doc's `g_raw_lookup_gap_fallback` — that gap falls back
to raw-`P` pooled ranking and IS still labeled; the 17+2 gap here means
the row has NO `underperformance_diagnostic_value` at all). Not
conflated in this audit.

---

## 5. ADP bucket comparison — current vs. proposed material-cost buckets

Current (`config.DATASET2_ADP_ROUND_BUCKETS`) vs. proposed material-cost
buckets (§11.6 proposal #3 of the trait-analysis pipeline doc, recorded
not implemented), both computed over the real 2,677
`bust_primary_eligible` population — descriptive re-bucketing only, no
new label:

**Current buckets:**

| Bucket | n | primary bust | rate | strict bust | rate |
|---|---|---|---|---|---|
| R1-2 | 381 | 75 | 19.7% | 0 | 0.0% |
| R3-5 | 570 | 110 | 19.3% | 1 | 0.2% |
| R6-10 | 972 | 190 | 19.5% | 43 | 4.4% |
| R11+ | 754 | 147 | 19.5% | 59 | 7.8% |

**Proposed material-cost buckets:**

| Bucket | n | primary bust | rate | strict bust | rate |
|---|---|---|---|---|---|
| R1-2 | 381 | 75 | 19.7% | 0 | 0.0% |
| R3-5 | 570 | 110 | 19.3% | 1 | 0.2% |
| R6-9 | 777 | 139 | 17.9% | 28 | 3.6% |
| R10-14 | 913 | 192 | 21.0% | 71 | 7.8% |
| R15+ | 36 | 6 | 16.7% | 3 | 8.3% |

**Real finding**: `bust_primary_label`'s rate stays roughly uniform
(16.7-21.0%) under BOTH bucket schemes — confirms §11.6's own
prediction that re-bucketing alone does not surface a material-cost
distinction (the percentile mechanism guarantees ~20% per cell by
construction, regardless of how the cells are drawn). The
`bust_strict_below_replacement_label` rate DOES climb with round under
both schemes (0% -> 7-8%), but the proposed split's headline benefit is
isolating the real, tiny (n=36) R15+ tail from the current R11+
bucket's much larger (n=754), cost-heterogeneous group — R11+ mixes
moderate real draft capital (R11-14, real strict rate 7.8%) with
near-costless dart-throws (R15+, real strict rate 8.3%, similar rate
but a materially different real dollar/pick cost). Confirms the
proposal's own conclusion: a real material-cost sensitivity needs its
own construction (e.g. weighting by real ADP-round cost directly)
rather than a re-read of the existing rate table under finer buckets —
finer buckets alone don't create the distinction, they just isolate a
much smaller, more homogeneous tail.

---

## 6. Predictor-clustering sensitivity — near-neighbor report and overlap-floor sweep

### 6a. 0.90-0.95 near-neighbor report (real, computed)

Real Pearson correlation pairs among the 216 continuous whitelist
columns with `0.90 <= |r| < 0.95` (just below the existing
`NEAR_DUPLICATE_CORR_THRESHOLD = 0.95` used for both the near-duplicate
report and clustering's own similarity edges), computed over the same
11,175-row real, outcome-matched population, pairwise-complete-case
per pair:

**309 pairs** found in this band (vs. 274 pairs already at/above 0.95).
Real, notable finding: `fam1_experience_position_z <->
fam2_age_position_z` at r=0.9475 — age and experience's own
position-adjusted forms are near-neighbors just below the current
threshold, consistent with `measure_age_experience_collinearity()`'s
own real, reported correlation (a genuine, expected relationship, not
a red flag). The rest of the top pairs are overwhelmingly fam9
window/basis variants of the same underlying concept (e.g.
`fam9_active_final_4_te_receiving_opportunity_per_active_game` <->
`fam9_active_final_8_te_receiving_opportunity`, r=0.9500) — the same
real pattern the existing >=0.95 clusters already capture, just one
step further out. Full pair list available on request (not yet
written to a `data/exports/` artifact this round — this was a direct,
ad hoc query, not yet wired into
`trait_analysis_pipeline_predictor_inventory.py`'s own output).

**Sensitivity read**: lowering `NEAR_DUPLICATE_CORR_THRESHOLD` from
0.95 to 0.90 would roughly double the pairs considered "near-duplicate"
(274 -> 583 cumulative) and — since clustering's own complete-linkage
similarity edges reuse this same threshold for continuous columns —
would very likely merge some of today's 133 clusters together
(plausible candidates: the fam9 window-variant families already
identified above, and the fam1/fam2 position-z pair). This was NOT
re-run as a full clustering pass this round (see 6b) — only the raw
pair list at the lower threshold was computed.

### 6b. Overlap-floor clustering sensitivity at 30/50/100 — REAL RESULT

**Definition, precise**: `MIN_OVERLAP_N` is the minimum number of
shared applicable player-season observations required before a
predictor PAIR's similarity is even used as a clustering edge — a
PAIRWISE floor on the two columns' jointly-non-null rows (`real[[a,
b]].dropna()`'s row count), never a per-predictor sample-size filter
and never a similarity-value/percentage threshold (that's a separate,
already-existing parameter, `NEAR_DUPLICATE_CORR_THRESHOLD`/
`BOOLEAN_JACCARD_THRESHOLD`/`BOOLEAN_PHI_THRESHOLD`, untouched by this
sweep). This is exactly `MIN_OVERLAP_N` in
`trait_analysis_pipeline_predictor_inventory.py` (currently `50` in
the committed script — used both as `min_periods` for continuous
Pearson correlation and as the boolean-pair joint-non-null floor in
`boolean_pair_similarity()`).

Re-run this round via
`research/dataset2/overlap_floor_clustering_sensitivity_2026_07.py` —
a read-only sweep that monkeypatches the already-imported, unmodified
production script's `MIN_OVERLAP_N` global for each of the three runs
(the committed script's own default of 50 is never edited or
adopted-as-changed), calling the SAME real `build_predictor_clusters()`
against the SAME real, outcome-free `real`/`inv` inputs each time:

| `MIN_OVERLAP_N` (pairwise shared-observation floor) | Clusters | Singletons | Size 2-5 | Size 6-10 | >10 | Largest |
|---|---|---|---|---|---|---|
| 30 | 133 | 79 | 40 | 14 | 0 | 10 |
| 50 (committed default) | 133 | 79 | 40 | 14 | 0 | 10 |
| 100 | 133 | 79 | 40 | 14 | 0 | 10 |

**Real result, a FINDING not a change**: sweeping the pairwise
shared-observation floor at 30, 50, and 100 produced IDENTICAL
133-cluster memberships and size distributions — cluster count, size
distribution, AND exact membership (every single cluster's content
set) are byte-for-byte identical at all three floors, confirmed via a
direct membership-set comparison, not just matching summary counts.
This means every real predictor pair that clusters together under the
committed 50-row floor already shares well over 100 real jointly-non-null
rows; raising or lowering the floor within this range changes nothing
about the 133-cluster/0-over-10 result. The committed script's own
`MIN_OVERLAP_N = 50` default was NOT modified — this sweep only ever
ran against a monkeypatched, in-memory copy of the module global, for
this descriptive comparison alone.

**SUPERSEDED (2026-07, Source A coverage remediation)**: the 133-cluster
figure above predates both family #18/#88 (built after this audit) and
the Source A targets/receiving-air-yards coverage remediation (149
target-derived columns forced null for prediction seasons 2007-2009 —
see `research/dataset2/SOURCE_A_TARGETS_COVERAGE_REMEDIATION_AUDIT_2026_07.md`).
Re-run against the current, remediated predictor table: **144 clusters**,
0 exceeding 10 members, `MIN_OVERLAP_N` 30/50/100 membership still
identical at all three floors (stability holds). The 0.90-0.95
near-neighbor band also shifted: 478 pairs (vs. 266 at `|r|>=0.95`),
computed the same way as §6a below but against the remediated table's
213 continuous whitelist columns. Full comparison table, including the
isolated pre-remediation baseline (138 clusters, computed this round by
temporarily reverting the remediation code to separate its effect from
the unrelated family #18/#88 growth) and the interpretation of why
cluster count rose, is in
`research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md`
§11.8. Not re-executed as a fresh 30/50/100 sweep narrative here to
avoid duplicating that section — see §11.8 for the authoritative
current numbers.

---

## 7. Scope note

Every number above was computed directly against the real, current
(post-age-rebuild, post-team-code-crosswalk) canonical predictor and
outcome tables. Nothing here changes `bust_primary_label`,
`bust_strict_below_replacement_label`, `star_by_value_label`, the
predictor whitelist, or the cluster assignments — this is a read-only
audit layer on top of the frozen Wave 1 state. No commit has been made
for this round's work; this document,
`research/dataset2/bust_percentile_band_audit_2026_07.py`, and
`research/dataset2/overlap_floor_clustering_sensitivity_2026_07.py`
are all new, uncommitted files.
