# Source A targets-coverage remediation audit (2026-07)

**Status: AUDIT ONLY. No code changed.** Full dependency inventory of
every canonical predictor derived directly or indirectly from Source A
`targets`, plus the real, audited `receiving_air_yards` finding that
widens the known gap. No predictor was tested against Star/bust
outcomes, no clustering threshold changed, no Family #20/#21 work
started.

---

## 1. Root cause, confirmed

Two raw nflverse weekly fields -- not just `targets` -- are essentially
untracked for real observation seasons 2006-2008, with a sharp, clean
break at 2009:

| Field | Seasons 2006-2008 | Seasons 2009-2025 |
|---|---|---|
| `targets` (real reception rows showing `targets==0`) | 99.5-99.6% | 0.0% every season |
| `receiving_air_yards` (real reception rows showing `==0`) | 99.6-99.7% | ~1.8-3.2% (a real, normal rate) |

**New finding this round**: `receiving_air_yards` has the identical
gap, previously undetected because family #18's own audit only checked
`receiving_yards_after_catch` (confirmed clean) and `receptions`
(confirmed clean), not `receiving_air_yards`. `passing_air_yards` (the
team-week denominator `air_yards_share` divides by) is INDEPENDENTLY
CLEAN across every season (0.2-1.0% real zero rate throughout,
verified directly, not assumed) -- but `air_yards_share`'s own
NUMERATOR is broken, so the ratio is not independently valid despite
its denominator being fine. This directly answers the "check whether
air-yards share is independently valid" instruction: **it is not** --
verified, not assumed.

Both gaps share a plausible real cause: `targets` and
`receiving_air_yards` both require real-time charting of the intended
target on EVERY pass attempt (including incompletions), which nflverse
did not have reliable historical data for before 2009. `receptions`,
`receiving_yards`, `receiving_yards_after_catch`, and `carries` are
simple counting stats present on every real completed/rushing play and
are NOT affected -- confirmed directly for `receiving_yards_after_catch`
in the prior round's audit, and receptions/receiving_yards/carries are
box-score-level counts with no real anomaly found when checked this
round.

---

## 2. Full affected-column inventory

### 2a. Source A base/derived columns (`lib/dataset2/usage_traits.py` -> `canonical_predictor_table.py::_build_srcA_layer`)

| Canonical column | Formula | Bad-value count (prediction_season 2007-2009, n=1,544 rows) | Proposed treatment |
|---|---|---|---|
| `srcA_prior_season_targets` | Real season sum of `targets` | 1,170 real non-null (unreliable) values | **1: force null** -- the raw count itself is confirmed unreliable at the source, not just a downstream ratio issue |
| `srcA_prior_season_receiving_air_yards` | Real season sum of `receiving_air_yards` | 1,170 real non-null (unreliable) values | **1: force null** -- same real source-tracking gap, newly confirmed this round |
| `srcA_prior_season_target_share` | `targets / team-week targets` (recomputed from real sums) | 235 real non-null (unreliable) values | **1: force null** -- numerator unreliable |
| `srcA_prior_season_air_yards_share` | `receiving_air_yards / team-week passing_air_yards` | Same population as target_share (real numerator broken; denominator independently clean but doesn't save the ratio) | **1: force null** -- numerator unreliable, despite the denominator being fine |
| `srcA_prior_season_wopr` | `1.5*target_share + 0.7*air_yards_share` | 235 real non-null (unreliable) values | **1: force null** -- both inputs unreliable |

Real, unambiguous, confirmed CLEAN and requiring no action (per
instruction, "unless separately disproven" -- checked, not assumed):
`srcA_prior_season_receptions`, `srcA_prior_season_receiving_yards`,
`srcA_prior_season_carries`, `srcA_prior_season_passing_epa`/
`rushing_epa`/`receiving_epa` (EPA fields were out of this round's
explicit scope -- the audit request is about `targets`-derived
predictors specifically -- and are not targets-denominated in any
case). **Correction (found during remediation implementation)**:
`receiving_yards_after_catch` itself is confirmed clean (see §1), but
it was never exposed as its own separate `srcA_prior_season_receiving_yards_after_catch`
canonical column -- family #18's own `receiving_efficiency_traits.py`
reads it directly from `_build_srcA_layer()`'s un-prefixed internal
`preseason` frame, not from a public `srcA_` column. The prior version
of this section incorrectly listed that column name as if it existed;
corrected here rather than silently left wrong.

### 2b. Family #18 (already remediated in commit `ce904af`)

| Canonical column | Status |
|---|---|
| `fam18_prior_season_catch_rate` | Already forced null for prediction_season 2007-2009 |
| `fam18_prior_season_receiving_yards_per_target` | Already forced null for prediction_season 2007-2009 |
| `fam18_prior_season_yac_per_reception` | Confirmed unaffected (receptions/YAC both clean) -- correctly left computed for all seasons, no change |

### 2c. Family #9 receiving-opportunity/efficiency/role columns (`lib/dataset2/partial_season_traits.py`)

`EFFICIENCY_METRICS[("RB","receiving")] = EFFICIENCY_METRICS[("WR","receiving")]
= EFFICIENCY_METRICS[("TE","receiving")] = ("receiving_yards", "targets")`
-- the denominator/opportunity column for these three (position, metric)
pairs is `targets`. `_resolve_role_metric()` reuses this SAME
denominator for the role-tier thresholds. QB passing (`attempts`) and
RB rushing (`carries`) use different, unaffected denominators. No
half-split (`first_half`/`second_half`) variant of these
position-specific metrics exists (checked directly -- family #9's
half-split traits are PPG-only).

**144 canonical columns affected**, every one of them a
`{team,active}_final_{4,6,8}_{rb,wr,te}_receiving_*` column:

| Column suffix pattern | Count | Formula | Real bad-value examples (prediction_season 2007-2009) |
|---|---|---|---|
| `_opportunity` | 18 (3 pos x 3 windows x 2 basis) | Real season-window sum of `targets` | e.g. `fam9_team_final_4_wr_receiving_opportunity`: 428 real non-null values |
| `_opportunity_per_team_game` / `_opportunity_per_active_game` | 18 | opportunity / real games in window | e.g. `fam9_team_final_4_wr_receiving_opportunity_per_team_game`: 428 real non-null values |
| `_efficiency_rate` | 18 | `production (receiving_yards) / opportunity (targets)`, `.replace(0, NaN)` on denominator | Mostly already null by coincidence (targets often literally 0, so the ratio's own zero-denominator guard already nulls most rows) -- but NOT all: e.g. `fam9_team_final_4_wr_receiving_efficiency_rate` still shows 2 real non-null (wrong) values, `fam9_active_final_8_te_receiving_efficiency_rate` shows 7 |
| `_efficiency_volume_eligible_exploratory` / `_sensitivity` | 36 | `opportunity >= config.DATASET2_EFFICIENCY_VOLUME_*[key]` | e.g. `fam9_team_final_4_wr_receiving_efficiency_volume_eligible_exploratory`: 428 real non-null (wrong) flag values |
| `_role_present` / `_meaningful_role` / `_strong_lead_role` | 54 | `_role_tier_flags(opportunity_per_X, thresholds)` -- see §3 below | e.g. `fam9_team_final_4_wr_receiving_role_present`: 428 real non-null (wrong) flag values; `fam9_team_final_6_rb_receiving_role_present`: 297 |

**Total real non-null (currently wrong) cells across all 144 affected
fam9 columns, in prediction_season 2007-2009: 41,260.**

**Proposed treatment: 1 (force null)** for all 144 -- reconstructing
from another source (option 2) is not available (no alternate historical
targets-charting source exists in this pipeline), and leaving them
computed (per instruction, do not preserve known-invalid values merely
for continuity) is explicitly ruled out.

**Confirmed UNCHANGED, no action needed**: the 18 `_production` columns
(`{team,active}_final_{4,6,8}_{rb,wr,te}_receiving_production` --
`receiving_yards`, not targets-denominated) and every `_rushing_`,
`_passing_`, `_snap_`, and PPG/points-basis family #9 column (carries,
attempts, snaps, and points are all separately clean, out of this
round's targets-specific scope, and explicitly protected per
instruction -- "preserve unrelated carries, snaps, points and
rushing-role traits").

---

## 3. Boolean-flag null-safety -- a real, reassuring design finding

`_role_tier_flags()` (`lib/dataset2/partial_season_traits.py`) is
**already implemented correctly** for this exact concern -- its own
docstring states: "Deliberately NOT computed via a plain `rate >=
threshold` comparison on a float Series, which would silently turn a
real NaN into False." It already returns pandas nullable-boolean `<NA>`
wherever its input `rate` is null, real `True`/`False` only where the
rate is real and known.

**This means the remediation's correctness depends entirely on making
the UPSTREAM `opportunity`/`opportunity_per_team_game`/
`opportunity_per_active_game` value null for the affected seasons** --
once that upstream value is null, `_role_tier_flags()` will correctly
propagate `<NA>` with no further code change needed in that function.
The `_efficiency_volume_eligible_*` flags (a plain `opportunity >=
min_value` comparison, not run through `_role_tier_flags()`) do NOT
have this same protection built in yet -- confirmed by reading
`build_team_game_efficiency_traits()`/`build_active_game_efficiency_traits()`
directly (lines ~786-787, ~846-849) -- these currently compute the
comparison directly on the raw `opportunity` sum. If `opportunity`
itself becomes null (rather than the comparison being separately
gated), a plain `>=` comparison against a real pandas `NaN` correctly
evaluates to `False` in pandas' own nullable-arithmetic semantics
**only if the Series is nullable dtype**; the current implementation
computes this on a plain (non-nullable) float sum, which needs
verification/explicit casting during remediation to avoid silently
reintroducing a real `False` where `<NA>` is required. **Flagged as an
implementation detail for the next round, not resolved here.**

---

## 4. Downstream clustering and export impact

**Yes, real downstream impact, not yet regenerated:**

- All 149 affected columns (5 srcA + 144 fam9) are members of the
  current 434-column predictor whitelist and were real inputs to the
  clustering run in `data/exports/dataset2_trait_pipeline_predictor_clusters.csv`
  (133 clusters, 0 exceeding 10 members) and the near-duplicate report
  (`data/exports/dataset2_trait_pipeline_near_duplicate_pairs.csv`,
  274 pairs at |r|>=0.95, plus the 309-pair 0.90-0.95 band from
  `research/dataset2/DATASET2_OUTCOME_DEFINITION_AUDIT_2026_07.md` §6a).
  Both were computed against the CURRENT (partially wrong) values for
  1,544 real rows -- correlation/Jaccard/phi similarity for any pair
  involving one of these 149 columns is provisional until the
  remediation lands and the inventory/clustering script is re-run.
- The overlap-floor sensitivity sweep
  (`research/dataset2/overlap_floor_clustering_sensitivity_2026_07.py`,
  §6b of the same audit doc) also ran against these same values --
  the STRUCTURAL finding (stable across MIN_OVERLAP_N=30/50/100) very
  likely still holds (the wrong values are wrong consistently, not
  randomly, so pairwise overlap counts themselves are largely
  unaffected), but this is not verified and should be re-run alongside
  the rest once remediated, not assumed.
- `research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md`
  §1/§1.5's real predictor/cluster counts and family breakdown table
  were computed against the same, currently-uncorrected values.

**Exports/artifacts needing regeneration once remediation is
implemented** (none regenerated this round -- audit only):

1. `data/exports/dataset2_canonical_predictor_table.{parquet,csv}` +
   its data dictionary (predictor table itself).
2. `data/exports/dataset2_analysis_view.{parquet,csv}` + its whitelist/
   registry/join-audit CSVs (depends on #1).
3. `data/exports/dataset2_trait_pipeline_predictor_inventory.csv` /
   `_near_duplicate_pairs.csv` / `_predictor_clusters.csv` (outcome-free
   inventory + clustering, depends on #2).
4. `research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md`
   (§1, §1.5, §9's real counts).
5. `research/dataset2/DATASET2_OUTCOME_DEFINITION_AUDIT_2026_07.md` §6
   (near-neighbor report, overlap-floor sensitivity) -- the STRUCTURAL
   conclusions likely hold but the exact pair/count numbers do not
   until re-run.
6. `research/dataset2/bust_percentile_band_audit_2026_07.py`'s own
   output is UNAFFECTED (outcome-only, no predictor columns touched) --
   explicitly confirmed, no regeneration needed for that one script.

---

## 5. Summary table

| Category | n columns | Treatment |
|---|---|---|
| srcA raw (targets, receiving_air_yards) | 2 | Force null, prediction_season 2007-2009 |
| srcA derived ratios (target_share, air_yards_share, wopr) | 3 | Force null, prediction_season 2007-2009 |
| fam9 receiving opportunity/efficiency/role (RB/WR/TE) | 144 | Force null, prediction_season 2007-2009 (booleans -> `<NA>`, never `False`) |
| fam18 catch_rate / yards_per_target | 2 | Already remediated (commit `ce904af`) |
| fam18 yac_per_reception | 1 | Confirmed unaffected, no action |
| fam9 `_production` (receiving_yards-based) | 18 | Confirmed unaffected, no action |
| fam9 rushing/passing/snap/points columns | (not separately re-audited) | Out of scope -- different denominators, explicitly protected |

**Total newly identified for remediation next round: 149 columns.**
**Total real, currently-wrong non-null cells across them (prediction_season
2007-2009): ~42,900** (41,260 fam9 + 1,640 srcA).

Stopping here, per instruction -- no remediation code written this
round.

---

## 6. Remediation implemented and validated (2026-07, same round -- REAL RESULT)

**Status: REMEDIATION COMPLETE.** The audit above was approved and the
remediation implemented the same round.

**Mechanism**: a single, reusable, dtype-aware
`apply_source_coverage_null_mask(df, columns, affected_seasons,
season_column, reason)` in `lib/dataset2/common.py`, applied once in
`canonical_predictor_table.py::build_canonical_predictor_table()`. The
149-column list is generated programmatically
(`SOURCE_A_TARGETS_UNRELIABLE_SRC_COLUMNS` +
`_fam9_targets_dependent_columns(window_ns)`, the latter parameterized
by the table's real `window_ns` so any future new window is
automatically covered) rather than hardcoded twice, and verified via a
dedicated regression test
(`test_column_inventory_matches_audit_expected_149_set` /
`test_full_window_set_matches_audited_149_total` in
`tests/test_dataset2_canonical_predictor_table.py`) to match this
audit's inventory exactly. `reason` is recorded as
`source_a_targets_and_receiving_air_yards_unreliable_2006_2008`
(`config.DATASET2_SOURCE_A_TARGETS_COVERAGE_REASON`) in the predictor
table's own data-dictionary `missingness_semantics` field for every
remediated column.

`_efficiency_volume_eligible_exploratory`/`_sensitivity` (both team-
and active-basis) were separately hardened with a new
`_volume_eligible_flag()` helper in `partial_season_traits.py`, mirroring
the already-correct `_role_tier_flags()` pattern, so unsupported
opportunity coverage produces nullable `<NA>` rather than risking a
silent `False`. Empirically confirmed a no-op against existing real
data (all 81 pre-existing tests in that file passed unchanged before
and after) -- pure defensive hardening, not a behavior change for
currently-covered seasons.

**Real, corrected cell count** (supersedes the ~42,900 estimate above,
computed via a proper null-safe before/after diff, not the earlier
verbal estimate): **45,240 cells** changed from invalid non-null to
null (3,980 srcA + 41,260 fam9). Verified via the same diff that 0
cells changed: (a) within the 149 columns outside prediction seasons
2007-2009, (b) within the 149 columns/affected seasons other than
going null, or (c) anywhere outside the 149-column list at all --
complete isolation confirmed in both directions.

**Predictor table**: 444 columns (unchanged -- the mask nulls values,
never drops/adds columns), 11,784 rows, 0 duplicate keys, deterministic
across two independent rebuilds (byte-identical CSV).

**Full test suite**: 1,166 passed (up from 1,144 pre-remediation --
22 new tests: 7 in `tests/test_dataset2_common.py`, 4 in
`tests/test_dataset2_partial_season_traits.py`, 11 in
`tests/test_dataset2_canonical_predictor_table.py`, the latter
including boolean-flag `<NA>`-not-`False` checks, prediction-season-2010
resumption, multi-team-aggregation-after-mask, row-order independence,
and the 149-column inventory regression test itself).

**Downstream regeneration (§4's action items 1-5, all completed this
round)**: analysis view rebuilt (outcome counts reconfirmed unchanged:
`bust_primary_label` positive=522, `bust_strict_below_replacement_label`
positive=103, `star_by_value_label` positive=76 -- outcome table was
never opened by this remediation); Wave 1 predictor inventory,
near-duplicate report, and frozen clustering output all rebuilt
(deterministic, byte-identical across two runs); `MIN_OVERLAP_N`
30/50/100 sensitivity re-swept (membership still identical at all three
floors -- stability holds); 0.90-0.95 near-neighbor band recomputed.
**Real effect on clustering**: cluster count rose from 138 (the
isolated pre-remediation, post-family-18/88 baseline, recomputed this
round by temporarily reverting the remediation code to separate its
effect from the unrelated interim family growth) to 144 -- an expected
consequence of correctly nulling previously-invalid values that had
been inflating overlap and correlation among target-derived Family #9
columns, not a clustering-methodology change. Full comparison table and
interpretation:
`research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md`
§11.8. `research/dataset2/bust_percentile_band_audit_2026_07.py`'s
output was, as predicted in §4 item 6, NOT regenerated (outcome-only,
unaffected).

Committed locally as two commits (coverage-remediation code/tests;
regenerated artifacts and doc updates), per instruction -- not pushed.
