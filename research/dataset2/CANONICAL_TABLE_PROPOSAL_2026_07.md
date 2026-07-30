# Dataset 2 Canonical First-Wave Predictor Table — Proposal (2026-07)

**Status: artifact 1 (predictor table) built.** The family #9 lag (§5)
and grain (§1) findings this proposal surfaced have been resolved --
`lib/dataset2/partial_season_canonical.py` implements the lagged, wide
family #9 preseason-feature layer, tested. **The canonical PRESEASON
PREDICTOR table (§1a artifact 1) is now implemented and run against
the real full 2006-2025 population** --
`lib/dataset2/canonical_predictor_table.py`,
`scripts/build_dataset2_canonical_predictor_table.py`, real output:
11,784 rows (11,175 real + 609 real future prediction_season=2026
rows), 435 columns, zero duplicate keys, deterministic rebuild
verified. The real SBV outcome-gap reconciliation (§3's four
categories) was run independently via
`scripts/audit_dataset2_outcome_gap.py` -- **NOT joined into the
predictor artifact**. **Artifacts 2 (outcome table) and 3 (analysis
view) are still not built** -- explicitly out of scope this round, see
the Stop point.

**Family #9 is complete and committed at `450a6cb`** (config-naming,
efficiency sample-eligibility, and three-tier role classification, all
approved).

**Status update (2026-07, commit `b821118`): artifact 2 (canonical
outcome table) is now built** —
`lib/dataset2/canonical_outcome_table.py`,
`scripts/build_dataset2_canonical_outcome_table.py`, real output:
11,175 rows, one row per (`outcome_season`, `player_id`). **What is
implemented**: the Star outcome (`star_outcome_eligible`,
`star_by_value_label`, `sbv_score_available`) and the full
eligibility/reason-code infrastructure for all three Dataset 2B outcome
dimensions (primary bust, strict-hybrid bust, historical-sensitivity
bust, and the extended underperformance diagnostic) — real counts:
`star_outcome_eligible` 8,537; `bust_primary_eligible` 2,677;
`bust_historical_sensitivity_eligible` 3,198;
`underperformance_diagnostic_eligible` 2,711 (see
`DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md` §0 for why
this is 2,711, not the 2,728 originally estimated). **What is NOT yet
implemented**: `bust_primary_label`, `bust_strict_label`, and
`bust_historical_sensitivity_label` are reserved columns, always null
this round (`implementation_status = reserved_not_computed`,
`usable_as_target = False` in the data dictionary) — no percentile
cutoff or absolute floor has been approved yet. See
`DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md` for the
real-data-backed candidate formulas under review. **Artifact 3
(analysis view) is still not built.**

---

## 0. What was inspected

Read directly, this round, not assumed from memory of building them:
`common.py`, `experience_age_draft.py`, `prior_season_traits.py`,
`prior_finish_traits.py` (+ `prior_finish_analysis.py`),
`usage_traits.py`, `snap_traits.py` (+ `snap_identity.py`),
`depth_chart_traits.py`, `fragility_traits.py`, `partial_season_traits.py`,
`participation_traits.py` (+ `participation_identity.py`). Also
inspected: `data/master/master_historical_db_with_lwi_2006_2025.csv`
(the population every module has been validated against),
`data/exports/stars_by_value_player_seasons.csv` (the real Dataset 2A
outcome source), `lib/stars_by_value/labeling.py`, and
`docs/LEAGUE_WINNER_TRAITS_SPEC.md` / the roadmap's Dataset 2B
decision. Real row counts below are all freshly computed against
these files this round, not carried over from an earlier session.

---

## 1a. Three-artifact architecture (revised 2026-07)

The original draft of this proposal implicitly assumed ONE wide table
carrying predictors, outcomes, and diagnostics together. Per
instruction, revised into **three separate artifacts**, each with its
own grain, its own build step, and its own file:

1. **Canonical PRESEASON PREDICTOR table** — one row per
   (`prediction_season`, `player_id`), the FULL eligible population
   (§3 — never restricted to rows SBV happens to score), every column
   knowable strictly before `prediction_season` begins. This is the
   artifact §1–§9 and §11 of this document describe, and the ONLY one
   of the three that `lib/dataset2/partial_season_canonical.py`
   contributes to today (family #9's slice of it).
2. **Canonical OUTCOME table** — one row per (`season`, `player_id`),
   built from `lib/stars_by_value`'s real Star export plus (once
   built) Dataset 2B's bust fields. Contains ONLY outcome/diagnostic
   columns and the real SBV/bust status vocabulary (§3, §10) — no
   predictor ever lives here, so there is no path by which an outcome
   build step could accidentally read from or leak into a predictor
   column.
3. **Dataset 2 ANALYSIS VIEW** — the join of (1) and (2), keyed on
   predictor `prediction_season == outcome season` and `player_id`,
   built fresh at analysis time (or materialized separately) rather
   than baked into the predictor table itself. This is where a
   consumer asks "did trait X predict outcome Y" — the predictor and
   outcome artifacts stay independently buildable, testable, and
   versionable, and the JOIN step itself becomes the one place that
   ever needs to reason about both at once, which is exactly where the
   leakage discipline in §10 needs to be enforced and tested.

**Why split rather than one wide table**: the earlier draft's join
(predictor LEFT JOIN outcome, all in one artifact) still works
mechanically, but conflating "build the predictors" with "attach the
outcome" in one script makes it easy for a future edit to accidentally
introduce a same-season or same-artifact dependency between the two.
Three artifacts with three separate build steps make that structurally
harder to do by accident, not just discouraged by convention — the
outcome table's own build script never even imports a predictor
module, and the predictor table's build script never imports
`lib/stars_by_value` at all (verified true of every module inspected
in §0 already, and proposed to remain a hard rule for whatever new
code assembles artifact 1).

---

## 1. Canonical row grain and unique key

**One row per (`season`, `player_id`), skill positions only
(QB/RB/WR/TE).** Verified this is already the universal grain of
every *predictor-producing* module: `experience_age_draft.py`,
`prior_season_traits.py`, `prior_finish_traits.py`,
`usage_traits.py`, `snap_traits.py`, `depth_chart_traits.py`,
`fragility_traits.py` all state "one row per (season, player_id[,
position])" in their own docstrings and all `drop_duplicates(subset=
["season", "player_id"])` before returning. Checked directly against
the real master population: **zero duplicate (season, player_id) keys**
in `master_historical_db_with_lwi_2006_2025.csv`'s 11,175 rows.

**`partial_season_traits.py` (family #9) does NOT share this grain by
default** — this is the first real finding, not an assumption:
- `build_team_game_final_n_traits()` / `build_active_game_final_n_traits()`
  / `build_team_game_efficiency_traits()` / `build_active_game_efficiency_traits()`
  / `build_team_game_role_traits()` / `build_active_game_role_traits()`
  / `build_team_game_snap_share_role_traits()` all include a `window_n`
  column and are called once per window length (4/6/8) — three calls,
  three frames, same (season, player_id) key repeated across them.
- The efficiency and role builders additionally include a `metric_name`
  column and are scoped to one `position` per call (e.g. `("RB",
  "rushing")`, `("WR", "receiving")`) — calling across every supported
  (position, metric_name) pair multiplies the row count further.
- Only `build_team_game_half_split_traits()` already returns one row
  per (season, player_id) — first/second half are columns, not rows.

**RESOLVED AND IMPLEMENTED 2026-07**:
`lib/dataset2/partial_season_canonical.py::build_family9_observation_wide()`
pivots every one of these into a single wide row per (season,
player_id) — every window_n/(position, metric_name)/basis combination
becomes a distinct, canonically-named column, e.g.
`build_team_game_role_traits(..., n=4, position="RB",
metric_name="rushing")`'s `team_final_n_meaningful_role` becomes the
canonical column `fam9_team_final_4_rb_rushing_meaningful_role`; the
same call with `n=6` becomes
`fam9_team_final_6_rb_rushing_meaningful_role`. This is a real,
disclosed multiplication of column count (see §11 — a real 2015
single-RB fixture with `window_ns=(4,6,8)` and Source B present
produces 388 real columns), not a lossy reduction — every window/
metric/basis combination the raw modules can produce stays available,
just as separate named columns instead of separate rows. A position-
inapplicable column (e.g. `fam9_*_qb_passing_*` columns for a WR row)
is null by construction, not by policy — see §6. The exact
(raw_column → canonical_column) mapping is a real, generated byproduct
of that same construction loop (its second return value), never a
separately hand-maintained list that could drift — see §7's revision.
Tested in `tests/test_dataset2_partial_season_canonical.py`'s
`TestGrainAndNaming` (no duplicate keys, no column-name collisions,
canonical naming spot-checks, team-game/active-game preserved
separately, applicable zeroes preserved, `team_game_window_status`
semantics preserved).

---

## 2. Included seasons

**2006–2025**, matching the master population's own real range
(verified: `season.min()==2006`, `season.max()==2025` on the real
file). Two real, disclosed coverage sub-boundaries within that range
that do NOT shrink the row grain but DO leave real columns
structurally null before their source begins:
- **Source B (`snap_traits.py`) real coverage is 2013–2025** — 2012 is
  a confirmed-empty real nflverse asset (`SNAP_COUNTS_EMPTY_SEASON`,
  `scripts/nflverse_source.py`). Every snap-derived column (raw and
  preseason-lagged snap fields, plus family #9's
  `team_final_n_offense_snap_share`/role columns) is structurally null
  for 2006–2012, and — for the *preseason* (lagged) snap columns —
  also null for 2013 itself (no real season-2012 row to lag from).
- **The 2025 depth-chart schema branch requires `schedules.csv`**,
  which is not cached in this sandbox (confirmed absent this round,
  same environment constraint the 2026-07 integration audit already
  disclosed). Family #10/#86/#88's 2025 rows cannot be validated here
  until that file is available via the established GitHub Actions
  fetch path — not a design gap, an environment gap.

No proposal to truncate the season range to avoid these gaps — per
`docs/MATCHING_ARCHITECTURE.md`'s "flag and exclude, never guess"
rule, the coverage boundary is represented as real, dated nulls (see
§6/§7), not by shrinking the table to only the seasons where every
source has data.

---

## 3. Eligible player population

**Proposed: the full skill-position master population — 11,175 rows,
2006–2025, QB/RB/WR/TE, no additional filter.** This is the exact
population already used to validate every predictor module in the
2026-07 integration audit, so adopting it as the canonical population
requires no new scoping decision.

**A real, different, NARROWER population already exists and must NOT
be silently substituted**: `docs/LEAGUE_WINNER_TRAITS_SPEC.md` reports
"2,643 eligible player-seasons" for its own trend-testing baseline, and
the real Stars-by-Value export
(`data/exports/stars_by_value_player_seasons.csv`) has only **10,659**
rows against the master population's 11,175 — a real, confirmed
**516-row gap**: every one of those 516 (season, player_id) keys exists
in the predictor population with **zero** matching SBV row at all (not
even an unscoreable one — checked directly this round, set difference
in both directions: 516 master-only, 0 SBV-only). SBV's own
`star_by_value_status` further splits its 10,659 rows into
`below_production_gate` (7,190), `out_of_scope` (1,934),
`adp_scored`/`minimal_market_cost_scored` (1,293 + 54 = 1,347, the
only rows with a real 0/1 `star_by_value_label` — 8,461 labeled 0, 76
labeled 1), and three small `unscoreable_*` statuses (188 combined).

**Proposed rule, stated explicitly so it can't be silently violated
later**: the PREDICTOR table's population is the broad 11,175-row set,
never restricted to SBV's "scoreable" subset. This is the direct
mechanism for "accidental loss of minimal-market-cost players" (§12)
— MMC players are already a real, named SBV status
(`minimal_market_cost_scored`,
`PROVENANCE_MMC_CORROBORATED`/`PROVENANCE_MMC_2010_OVERRIDE`) with 54
real rows; a predictor-side inner join against SBV would silently drop
them (and 462 other non-MMC rows) from the canonical table entirely,
which must never happen — predictors must remain available for every
skill-position player-season regardless of whether that season is
outcome-scoreable.

**Revised 2026-07 — explicit outcome-AVAILABILITY status, not a bare
null**: per instruction, the OUTCOME table (§1a, artifact 2) must not
let the 516-row gap (or any other non-scoreable case) silently read as
"not a Star" — a null `star_by_value_label` is genuinely ambiguous
between "we don't know" and "known non-Star," and this project's
missingness policy (`docs/LEAGUE_WINNER_TRAITS_SPEC.md`'s "unknown
must never silently become zero, average, or false") already forbids
exactly that collapse. Proposed outcome-availability categories,
reconciled against SBV's REAL, EXISTING status architecture rather
than inventing a parallel one:

| Outcome-availability category (proposed) | Real SBV `star_by_value_status` values it covers | Real count (2006-2025) | Meaning |
|---|---|---|---|
| `scored_labeled` | `adp_scored`, `minimal_market_cost_scored` | 1,347 | Real 0/1 `star_by_value_label` exists (1,271 real 0s, 76 real 1s within this group) |
| `scored_but_unlabeled` | `unscoreable_drafted_adp_missing`, `unscoreable_ambiguous`, `unscoreable_expected_production_out_of_range` | 188 | SBV attempted scoring, a real known reason blocked a label — the reason itself is informative, not a data gap |
| `out_of_scope_by_sbv_design` | `out_of_scope`, `below_production_gate` | 9,124 | SBV's own eligibility gate excluded this player-season on purpose (not enough real production to even evaluate) — a real, deliberate scope boundary, not missing data |
| `no_sbv_row_found` | *(no matching row at all)* | 516 | The real, confirmed predictor/outcome population MISMATCH this round found — genuinely unexplained from the predictor side alone; flagged for follow-up investigation (not decided in this proposal), never silently merged into any of the three categories above |

Every predictor-table row gets exactly one of these four categories in
the outcome table (or, more precisely, in the JOIN between them — see
§1a artifact 3) — **none of the four may be read or reported as "this
player-season was not a Star."** Only `scored_labeled` rows carry a
real, usable 0/1 label; the other three are explicitly "we cannot say"
for three DIFFERENT real reasons, each preserved as its own category
per `docs/LEAGUE_WINNER_TRAITS_SPEC.md`'s missingness-cause rule (§6).

---

## 4. How Source A, Source B, and the first-wave families join

Every module already expects (and this proposal keeps) the same
contract: **caller scopes the population, module computes traits onto
it, caller joins the result back by (season, player_id)** — verified
directly in every module's docstring (`prior_season_traits.py`:
"`population` must already be the caller's scoped Dataset 2 population
... this module just computes"; identical language in
`prior_finish_traits.py`, `experience_age_draft.py`). No module
performs its own population filtering beyond position/season scoping
already implied by its inputs.

Proposed join sequence:
1. **Base population**: the 11,175-row master slice (`season`,
   `player_id`, `position`, plus every column the downstream modules
   need directly from it — `team`, `games_played`, `fantasy_points_ppr`,
   `ppg_ppr`, `overall_finish_ppr`, `position_finish_ppr` — all
   confirmed present on the real master file this round).
2. **Source A (Source A itself has no identity crosswalk step)** —
   `usage_traits.py`'s `weekly` input already uses `player_id` values
   that match the master population directly (confirmed: no crosswalk
   module exists for Source A, unlike Source B). Build
   `build_raw_season_usage()` for every season in scope, then
   `build_preseason_usage_features()` on the FULL multi-season result
   (not a single-season slice — `lag_join()` needs season N-1's row
   present in the same frame it's called on).
3. **Source B** — `snap_traits.py` requires the pfr_id crosswalk step
   FIRST (`snap_identity.py::crosswalk_snap_counts_identity()`) to
   resolve `pfr_player_id` to the master population's `gsis_id`-based
   `player_id` before `build_raw_player_game_snaps()` can even run —
   this is a real, required extra step Source A does not have.
4. **Non-family-#9 first-wave modules** — `experience_age_draft.py`,
   `prior_season_traits.py`, `prior_finish_traits.py`,
   `depth_chart_traits.py`, `fragility_traits.py` each called once
   against the full population, each returning one row per (season,
   player_id) already — straight left-join onto the base population,
   no pivot needed.
5. **Family #9** — **RESOLVED AND IMPLEMENTED 2026-07**:
   `build_family9_observation_wide()` calls every builder across every
   window_n/(position, metric_name) combination and pivots into
   canonically-named columns (§1); `build_family9_preseason_features()`
   then lags the result (§5). What remains for the canonical predictor
   table itself is simply left-joining THAT function's output onto the
   base population by (`prediction_season`, `player_id`) — no new
   pivot/lag logic needed at table-build time.
6. **Every join is a LEFT join from the base population outward** —
   never inner, never right. A predictor module returning fewer rows
   than the population it was given would itself be a bug (none does,
   per each module's own "every row in population is preserved"
   docstring language), but the canonical-table build should assert
   this explicitly rather than trust it silently (see §12).

---

## 5. Critical finding: family #9's output is NOT yet a preseason
predictor, and must not be joined onto the same season's row as one

Checked directly this round, not assumed: **`partial_season_traits.py`
contains zero calls to `lag_join()` or any `prior_season_*` handling**
(grepped the full file). Every one of its outputs — team-game/
active-game PPG, efficiency rate, role-tier classification, snap
share — describes **season N's own in-season split** (e.g. "the
player's final 4 games of season N"). This is structurally identical
to `usage_traits.py`'s `build_raw_season_usage()` layer: real,
same-season data that is explicitly NOT a preseason predictor for the
season it describes.

This matches the very first instruction that opened family #9's work
in an earlier round of this project: *"These partial-season values
must become lagged preseason traits for the following season"* — a
requirement that was stated up front and has not yet been built. Every
round of family #9 work since then (the week-boundary fix, the
team-game/active-game redesign, the dual-rate split, efficiency
sample-eligibility, and this round's role classification) built and
tested the SAME-SEASON computation correctly, but the LAG step itself
was never in scope for any of those approvals — re-reading each
round's instructions confirms none of them asked for it.

**If the canonical table joined family #9's raw output onto the same
season's row as a predictor, that would be textbook same-season
leakage** — using a player's real December performance to "predict"
that same season's outcome.

**RESOLVED AND IMPLEMENTED 2026-07**:
`lib/dataset2/partial_season_canonical.py::build_family9_preseason_features()`
closes this gap. Deliberately NOT `lag_join()`'s "look up a different
row at season-lag for a given target row" pattern (there is no target
population to look up against here) — instead a direct, ROW-FOR-ROW
relabeling: every real observation row's own `season` becomes
`observation_season`, and `prediction_season = observation_season +
1`, every trait value carried through unchanged. Because each output
row is sourced from exactly ONE input row, a mutation to one
observation-season row can only ever change the one preseason row it
maps to — proven directly in
`tests/test_dataset2_partial_season_canonical.py`'s `TestLagLeakage`
(mutation isolation both directions, rookie/no-prior-data nulls on a
real left-join, and the final-historical-season future-row case, all
passing). Column names use `observation_season`/`prediction_season` as
explicit id columns rather than a `prior_season_*` prefix baked into
every one of the ~130 per-window trait columns (a real naming-scheme
revision from this section's original draft, made once the actual
row-shift implementation made a per-column prefix redundant — the id
columns already carry that information for the whole row). See §13's
updated build order for what's left (the canonical predictor table
itself, artifact 1 of §1a, still not built).

---

## 6. Missingness taxonomy — source-coverage vs. real zero/false vs.
rookie vs. status

Every module already distinguishes SOME of these, but not with one
shared vocabulary. Proposed canonical taxonomy, mapped to what each
module already does (verified per-module, not assumed uniform):

| Real cause | Example | How it should read in the canonical table |
|---|---|---|
| **Rookie / no prior season to lag from** | `prior_season_traits.py`, `prior_finish_traits.py`, `usage_traits.py`'s preseason layer, `snap_traits.py`'s preseason layer | Null, by construction of `lag_join()` — never zero, never False. Distinguishable from other nulls via a `seasons_of_prior_data` count (proposed metadata column, §7) rather than an per-field guess. |
| **Real, structural zero (applicable, zero usage)** | family #9's `team_final_n_points_per_team_game == 0.0` for a rostered player with zero real usage across the window | A REAL value, not null. Verified this is already correct and tested (`test_fully_inactive_applicable_window_gets_zero_per_team_game_not_null`). Must not be reinterpreted as missing at canonical-build time. |
| **Source-coverage gap (structural, dated)** | Source B pre-2013; 2025 depth-chart branch without `schedules.csv` | Null, PLUS an explicit coverage-boundary fact recorded once per source/season in the provenance layer (§7), not re-derived per row by a consumer guessing "is this season before or after 2013." |
| **Identity/team-resolution failure** | family #9's `team_game_window_status` (`unavailable_traded`/`unavailable_no_team_evidence`/`unavailable_other`); Source B's `identity_match_status` (unmatched pfr_id) | Null trait value PLUS a real, named status column already exists per-module — proposed: carry that status column through to the canonical table unmodified (e.g. `fam9_team_game_window_status`), never collapse it into a bare null. |
| **Genuinely unscoreable outcome (SBV)** | `star_by_value_status in (out_of_scope, below_production_gate, unscoreable_*)` | Null `star_by_value_label` PLUS the real status string carried through — see §10. |
| **No matching depth-chart/players.csv/schedule row** | `experience_age_draft.py`, `depth_chart_traits.py` | Null, disclosed in each module's own "MISSINGNESS" docstring section as "kept, never dropped." No separate status column exists per-module here today — proposed as a gap to close in §13 if this distinction turns out to matter empirically (not decided in this proposal). |

**One real, concrete risk found this round, explicitly listed since
the request calls for it**: several MODULES encode a boolean trait as
`float64` 0.0/1.0/NaN (`fragility_traits.py`'s
`multiple_rank1_players`, `qb_starter_uncertainty`,
`team_qb_uncertainty`, etc., all via `.astype(float)`/`np.where`), while
family #9's NEWER role-tier flags use pandas' nullable `"boolean"`
dtype (`pd.NA` for unknown, real `True`/`False` otherwise). Both are
internally safe within their own module (a `NaN`/`pd.NA` never
silently reads as `False` inside that module's own code), but they are
**not interchangeable once combined into one canonical table** — a
consumer that does `df["multiple_rank1_players"] == True` gets correct
behavior on either encoding, but `df["multiple_rank1_players"].astype(bool)`
on the float/NaN encoding would silently turn a real "unknown" into
`True` (`bool(np.nan) is True` in Python). **Proposed rule**: every
boolean-shaped canonical column is written using pandas' nullable
`"boolean"` dtype at canonical-build time, regardless of which
module's internal encoding it came from — a real, disclosed
normalization step, not a silent behavior change to the source module
(which keeps its own internal encoding; only the canonical-table
BUILD step casts on the way out).

---

## 7. Naming conventions

**Real, found inconsistency across modules, not assumed away**:
- `usage_traits.py`/`snap_traits.py` prefix every lagged predictor
  `prior_season_*` (e.g. `prior_season_target_share`).
- `prior_season_traits.py` does this for `prior_season_games_played`
  but NOT for `ppg_trend_2yr_slope`/`ppg_trend_3yr_slope`/`changed_team`
  — all three are equally lag-derived (verified: each calls
  `lag_join()` internally) but don't carry the prefix.
- `prior_finish_traits.py` uses a different prefix entirely
  (`prior_overall_finish`, `prior_positional_finish`, `prior_ppg` — no
  `_season_` in the middle).
- `depth_chart_traits.py`/`experience_age_draft.py` traits carry NO
  temporal prefix at all, because (per §5's distinction) they are
  preseason-safe by construction, not by lag — their "season" column
  already IS the prediction season.

**Proposed canonical naming scheme** (applied at table-build time; no
proposal to rename anything inside the source modules themselves,
consistent with never silently changing a module's own documented
output):
- `{family_number}_{module_short_name}_{field}` for every predictor
  column, e.g. `fam1_experience_years`, `fam8_ppg_trend_2yr_slope`,
  `fam9_team_final_4_rb_rushing_meaningful_role`. The family number
  prefix makes the column-level inventory (§11) directly greppable
  against this document and the roadmap.
- Every column whose value is LAGGED (i.e., its raw source season is
  N-1, N-2, or N-3 relative to the row's own `season`) additionally
  carries `_prior_` somewhere in the family-scoped segment — e.g.
  `fam8_prior_ppg_trend_2yr_slope` — regardless of whether the SOURCE
  module's own column name already said `prior_season_*`. This
  resolves the real inconsistency above without touching source code.
- Every column whose value is preseason-safe BY CONSTRUCTION (age,
  draft capital, depth chart, body size) carries no `_prior_` segment
  — its own `season` IS the prediction season, and mislabeling it as
  "prior" would be actively wrong.
- Family #9's `window_n`/`metric_name`/`position`-scoped columns
  encode all three directly in the name per §1's pivot proposal
  (`fam9_{team|active}_final_{n}_{position_lower}_{metric_name}_{tier}`),
  not abbreviated, so a reader never has to cross-reference this
  document to know which window or metric a column describes.
- **Real, deliberate exception, decided during implementation**:
  family #9's lagged columns do NOT carry a `_prior_` segment the way
  this section's general rule above would otherwise require. Once
  `build_family9_preseason_features()` was actually written (§5), it
  became clear that embedding `_prior_` into every one of the ~130
  per-window trait columns would be pure redundant noise — the row's
  own explicit `observation_season`/`prediction_season` id columns
  already state, ONCE, that every trait column on that row is a
  lagged (`prediction_season = observation_season + 1`) value. This is
  a real, disclosed deviation from the general naming rule above,
  scoped specifically to family #9 because of its column-count
  multiplicity — the general `_prior_`-in-every-column-name rule still
  applies to every OTHER family's lagged columns (§8/§11), which don't
  have this problem.
- `family9_canonical_column_mapping` — every canonical family #9
  column's exact source is a real, generated artifact (the second
  return value of `build_family9_observation_wide()`), not a
  hand-written table in this document — see §11's note on where to
  find it.

---

## 8. Provenance and coverage metadata

Proposed as a small, FIXED set of metadata columns living alongside
the predictor columns, not duplicated per-trait:
- `population_source_version` — the exact master-DB filename/row-count
  fingerprint the table was built from (mirrors LWI's own
  `lwi_config_fingerprint` convention already on the master file).
- `fam9_team_game_window_status` — carried through verbatim from
  family #9 (§6), since it already distinguishes traded/no-evidence/
  other in a way a bare null can't.
- `source_b_coverage_era` — `"covered_2013_plus"` /
  `"uncovered_pre_2013"`, one column, computed once from `season`, so
  no consumer has to re-derive "is 2013 the right cutoff" per query.
- `depth_chart_schema_era` — already exists as a family #10 OUTPUT
  column (`SCHEMA_ERA_HISTORICAL`/`SCHEMA_ERA_2025_STRICT_ORDER`);
  proposed to keep it under its existing name rather than duplicate it
  into the metadata block, since it is already trait-adjacent, not a
  pure build-provenance fact.
- `seasons_of_prior_data` — count of real prior seasons available for
  this player as of this row's season (0 for a true rookie, capped at
  however many lag windows the table actually uses) — proposed so
  "missing because rookie" (§6) is distinguishable from "missing
  because of a genuine gap year" (the real 0.9%/24-player-season case
  `LEAGUE_WINNER_TRAITS_SPEC.md` already found) without a consumer
  re-deriving it from raw lag columns.
- `star_by_value_status` / `star_by_value_provenance_type` — carried
  through from the SBV export verbatim (§10), not re-encoded.

---

## 9. Keeping raw traits, threshold classifications, and outcome
labels distinguishable

Revised 2026-07: this is now BOTH a column-naming/type discipline
WITHIN artifact 1 (the predictor table), AND a structural, ARTIFACT-
level separation per §1a — predictor and outcome columns don't just
look different, they live in genuinely different, independently-built
tables (artifacts 1 and 2), joined only in artifact 3.

**Within the predictor table**:
- **Raw continuous traits** (counts, rates, z-scores, slopes): plain
  numeric dtype (`float64`), never a string, never pre-bucketed.
  Example: `fam9_team_final_4_rb_rushing_opportunity_per_team_game`.
- **Threshold/tier classifications**: nullable pandas `"boolean"`
  dtype — **IMPLEMENTED 2026-07** for family #9 in
  `partial_season_canonical.py` (§6's masking fix, verified in
  `TestBooleanNormalization`) — and their name always states which
  underlying continuous trait and which approved tier they classify,
  e.g. `fam9_team_final_4_rb_rushing_meaningful_role` is unambiguous
  about being a classification OF
  `fam9_team_final_4_rb_rushing_opportunity_per_team_game`, both
  columns present side by side, never one replacing the other.
- **Status/provenance fields** (§7/§8): string dtype, drawn from a
  fixed, named set of constants per column (never a free-text value),
  e.g. `fam9_team_game_window_status` — real, implemented, carried
  through as its own column, not collapsed into the boolean masking it
  also drives.

**Across artifacts**: outcome/diagnostic columns
(`star_by_value_*`, `bust_*` — see §10) never appear in artifact 1 at
all — there is no column-name collision to guard against because
there is no shared table for one to happen in. A consumer building
artifact 3 (the join) is the only place these two vocabularies ever
meet, and that join is a single, auditable step (§1a).

---

## 10. Attaching Dataset 2A Star, Dataset 2B bust, and secondary
diagnostics without leaking into predictors

**Dataset 2A (Star) is real, built, and already at the correct grain
— lives ONLY in artifact 2 (the outcome table, §1a), never in artifact
1.** `data/exports/stars_by_value_player_seasons.csv`: one row per
(season, player_id), 10,659 real rows, columns
`star_by_value_status`/`_provenance_type`/`_score`/`_label`/
`_production_gate_threshold`/`_threshold`. Proposed: the outcome
table's build step reads this export directly, adds the four
`outcome_availability_category` values from §3's revised table, and
that is its entire output — no predictor logic anywhere in that build
step. Artifact 3 (the join) is where predictor row `(prediction_season
= N, player_id = X)` meets outcome row `(season = N, player_id = X)` —
i.e., row X's predictors are things known BEFORE season N, and its
outcome describes what happened DURING season N. This is the correct
predictor→outcome direction and requires no additional lag at join
time (SBV's own label is already computed from season N's own
results, attached to season N's own row).

**Dataset 2B (bust) is DESIGNED but NOT YET BUILT.** The roadmap
records an approved 2026-07 decision for three named fields —
`bust_label_primary` (definition G, position×ADP-range-conditioned
percentile), `bust_label_strict_hybrid` (definition I, G plus an
absolute-floor sensitivity check — informative when it disagrees with
the primary, e.g. `bust_label_primary==1` and
`bust_label_strict_hybrid==0` is a real, expected "borderline bust"
case, not an error), and `underperformance_diagnostic` (definition C,
raw production vs. modeled expected production — a SEPARATE signal,
56.4% overlap with G at the illustrative 20% level, not a restatement)
— but exact percentile cutoffs are explicitly left as "implementation
details to fix when Dataset 2B's outcome-labeling module is actually
built," which has not happened.

**Revised 2026-07 — reservation scope narrowed, per instruction**: the
three bust field names are reserved in this document's schema/data-
dictionary sections (§11's inventory) and in whatever future data
dictionary accompanies artifact 2 — **NOT as actual all-null columns
added to any production table today.** The earlier draft's "reserve
the name, populate with null / `not_yet_built`" proposal is withdrawn:
adding three permanently-null columns to a real, shipped table before
their real build exists would itself be a small, silent piece of
schema drift (a consumer could reasonably assume a present column
means a real, if temporarily-empty, pipeline exists behind it). The
three names, their intended dtype (nullable boolean for the two
labels, float for the diagnostic), and their intended grain
(artifact-2, one row per (season, player_id), same as
`star_by_value_label`) are documented here and in §11 so the eventual
build has an already-agreed target — but they are added to artifact 2
only once Dataset 2B's real outcome-labeling module exists and
produces real values.

**Leakage boundary, stated as an explicit rule for this section**: no
outcome or diagnostic column (`star_by_value_*`, `bust_*`,
`underperformance_diagnostic`) may ever be read as an INPUT to any
predictor column's own computation. Per §1a, this is now enforced
STRUCTURALLY as well as by convention: artifact 1's build step has no
code path that could even import from `lib/stars_by_value/` or read an
outcome column, since outcome data lives in a separate artifact built
by a separate script. Every predictor module inspected in §0 already
independently satisfies this rule (none of them import from
`lib/stars_by_value/`), so the three-artifact split doesn't change any
existing module's behavior — it makes the SAME rule harder to violate
by accident in whatever new code assembles artifact 1.

**`prior_finish_analysis.py` is not a column source.** It's a
downstream reporting module (raw/ADP-conditioned/market-pricing Star
rate stratification) that CONSUMES `prior_finish_traits.py`'s output
plus ADP plus the Star label — useful as a validation pattern for how
2A analysis should read this table later, but it does not itself
belong in the column inventory below.

---

## 11. Column-level inventory

Family-number-prefixed per §7. `window_n`/`metric_name`/`position`
dimensions are stated as multiplicities rather than fully expanded
(expanding every literal instance here would be several hundred
rows). **For family #9 specifically, the exact expansion is a real,
generated artifact** — `build_family9_observation_wide()`'s second
return value (`column_mapping`, a DataFrame of every {raw_column,
canonical_column} pair actually used) — never a hand-maintained copy
in this document. A real, minimal fixture (1 RB, `window_ns=(4,6,8)`,
Source B present) produces 388 real observation-wide columns this
round; the exact count for a full real population depends only on
which positions are present, not on anything this document would need
to be kept in sync with.

| Trait (pattern) | Family | Source | Raw source season | Prediction season | Earliest–latest coverage | Position | Missingness meaning | 2A/2B/Both | Kind |
|---|---|---|---|---|---|---|---|---|---|
| `fam1_experience_years` | #1 | players.csv | N (constructive, no lag) | N | 2006–2025 | QB/RB/WR/TE | No players.csv match → null | Both (predictor) | Continuous |
| `fam2_age_at_week1_years`, `fam2_age_x_experience`, `fam2_age_position_z` | #2 | players.csv + schedules.csv | N | N | 2006–2025 (schedules.csv gap — §2) | QB/RB/WR/TE | No birth_date or no resolvable Week-1 kickoff → null | Both | Continuous |
| `fam1_experience_position_z` | #1 | players.csv | N | N | 2006–2025 | QB/RB/WR/TE | Same as above | Both | Continuous |
| `fam4_nfl_draft_year/_round/_pick/_team` | #4 | players.csv | N (fixed at draft) | N | 2006–2025 | QB/RB/WR/TE | Undrafted/no players.csv match → null (undrafted is real, not a gap — not currently distinguished from "no match," a real open item, see §13) | Both | Metadata/continuous |
| `fam6_height_inches/_weight_lbs/_body_size_bmi` | #6 (body-size portion) | players.csv | N | N | 2006–2025 | QB/RB/WR/TE | No players.csv match → null | Both | Continuous |
| `fam8_prior_ppg_trend_2yr_slope`, `fam8_prior_ppg_trend_3yr_slope` | #8 | master DB self-join | N-1..N-2 (2yr) / N-1..N-3 (3yr) | N | 2007+ (2yr, needs 1 prior season) / 2008+ (3yr) | QB/RB/WR/TE | <2 non-null lag points → null (rookie or gap year) | Both | Continuous |
| `fam39_prior_season_games_played` | #39 | master DB self-join | N-1 | N | 2007–2025 | QB/RB/WR/TE | No season N-1 row → null | Both | Continuous |
| `fam44_prior_changed_team` | #44 | master DB self-join | N-1 vs. N-1's team | N | 2007–2025 | QB/RB/WR/TE | Rookie → null (never False) | Both | Nullable boolean |
| `fam7_prior_overall_finish`, `fam7_prior_positional_finish`, `fam7_prior_ppg` | #7 | master DB self-join | N-1 | N | 2007–2025 | QB/RB/WR/TE | No season N-1 row → null | Both | Continuous |
| `fam15/17/18/20/22_prior_season_{targets,carries,receiving_yards,receiving_air_yards,passing_epa,rushing_epa,receiving_epa,target_share,air_yards_share,wopr}` | #15/#17/#18/#20/#22 (Source A base variables) | Source A weekly, REG only | N-1 | N | 2007–2025 | QB/RB/WR/TE (rate fields recomputed from real team-week sums) | No season N-1 real row → null; racr deliberately never output (deferred, §"reconstruct-or-defer" in usage_traits.py) | Both | Continuous |
| `fam_snapB_prior_season_{offense_snaps,defense_snaps,st_snaps,games_active,offense_pct}` | Source B base variables (no single family number — cross-cutting) | Source B snap_counts, REG only | N-1 | N | 2014–2025 (needs a real N-1 row, and 2013 is the earliest real N-1) | QB/RB/WR/TE | Pre-2013 season N-1, or unmatched pfr_id that season → null; `defense_pct`/`st_pct` deliberately never output (deferred) | Both | Continuous |
| `fam10_depth_chart_team/_native_rank/_status/_tied/_starter_group_size/_position_starter_count/_schema_era` | #10 | nflverse depth_charts (both schema eras) | N (preseason snapshot) | N | 2006–2025 (2025 branch needs schedules.csv — §2) | QB/RB/WR/TE | No matching preseason snapshot row → null, never a guessed "deeper" | Both | Mixed: continuous rank, nullable boolean tie flag, status strings |
| `fam86_multiple_rank1_players`, `_qb_starter_uncertainty`, `_rb_committee_indicator`, `_te_co_starter_indicator`, `_team_qb_uncertainty` | #86 (split, part) | depth_chart_traits.py output | N | N | 2006–2025 | QB/RB/TE (position-scoped null elsewhere) | No depth-chart data → null; position-inapplicable → null by design | Both | Float-encoded boolean (§6 normalization needed) |
| `fam86_wr_starter_group_size`, `_wr_starter_group_member`, `_wr_league_starter_group_size_norm`, `_wr_starter_group_size_vs_league_norm` | #86 (split, part) | depth_chart_traits.py output | N | N | 2006–2025 | WR only | No depth-chart data → null | Both | Continuous / float-encoded boolean |
| `fam88_body_size_position_z` | #88 (split, part) | experience_age_draft.py output | N | N | 2006–2025 | QB/RB/WR/TE | No BMI → null | Both | Continuous |
| `fam88_workload_qualified` | #88 (split, part) | placeholder | N/A | N/A | N/A | QB/RB/WR/TE | Always the literal string `"pending"` — not yet a real trait | Neither yet | Status placeholder |
| `fam9_team_final_{4,6,8}_points_per_team_game/_per_active_game`, `_sample_qualified_primary/_sensitivity`, `_games`, `_active_games`, `fam9_team_game_window_status` | #9 | Source A weekly, via team-game windows | observation_season N | **prediction_season N+1 — RESOLVED §5** | 2006–2025 (obs.) → 2007–2026 (pred.) | QB/RB/WR/TE | Zero-usage-but-applicable → real 0.0 (never null); non-applicable status → nullable-boolean `<NA>` (§9's implemented masking fix); rookie/no-observation → null on left-join | Both (predictor, artifact 1) | Continuous + nullable boolean + status |
| `fam9_active_final_{4,6,8}_games_ppg`, `_games`, `_sample_qualified_primary/_sensitivity` | #9 | Source A weekly, via active-game windows | observation_season N | prediction_season N+1 | 2006–2025 (obs.) → 2007–2026 (pred.) | QB/RB/WR/TE | Real zero-active-games → real False (not masked, §9); rookie → null | Both (predictor) | Continuous + nullable boolean |
| `fam9_team_first_half`/`second_half_points_per_team_game/_per_active_game` + qualifiers | #9 | Source A weekly, half-split | observation_season N | prediction_season N+1 | 2006–2025 (obs.) → 2007–2026 (pred.) | QB/RB/WR/TE | Same pattern as final-N team-game | Both (predictor) | Continuous + nullable boolean |
| `fam9_{team,active}_final_{4,6,8}_{position}_{metric}_efficiency_rate/_opportunity/_production/_efficiency_volume_eligible_exploratory/_sensitivity` | #9 | Source A weekly, efficiency | observation_season N | prediction_season N+1 | 2006–2025 (obs.) (5 position/metric pairs × 3 windows × 2 bases = 30 concrete column groups) | Position-scoped per metric (QB passing / RB rushing / RB receiving / WR receiving / TE receiving) | Zero opportunity → rate null, counts real 0.0; non-applicable (team basis) → `<NA>` | Both (predictor) | Continuous + nullable boolean |
| `fam9_{team,active}_final_{4,6,8}_{position}_{metric}_opportunity_per_team_game/_per_active_game`, `_role_present/_meaningful_role/_strong_lead_role` | #9 | Source A weekly, role classification | observation_season N | prediction_season N+1 | 2006–2025 (obs.) (team: 4 pairs, active: 5 pairs × 3 windows) | Position-scoped per metric | Same pattern as efficiency | Both (predictor) | Continuous + nullable boolean (3 tiers) |
| `fam9_team_final_{4,6,8}_{position}_snap_offense_snap_share`, `_has_snap_coverage`, `_role_present/_meaningful_role/_strong_lead_role` | #9 | Source B snap counts, via team-game windows | observation_season N | prediction_season N+1 | 2013–2025 (obs.) (4 positions × 3 windows) | QB/RB/WR/TE | Pre-2013 or no team coverage → `has_snap_coverage=False` (real fact), share/`<NA>` role tiers; non-applicable status → `<NA>` | Both (predictor) | Continuous + nullable boolean |
| `fam9_prediction_season_outcome_unavailable` | #9 (canonicalization metadata, not a predictor) | `partial_season_canonical.py` | N/A | Computed per prediction_season | Whenever prediction_season exceeds the input's own max observation_season | QB/RB/WR/TE | Never null — always True/False | Neither (build metadata) | Boolean |
| `star_by_value_status/_provenance_type/_score/_label/_production_gate_threshold/_threshold`, `outcome_availability_category` | N/A — Dataset 2A outcome | `lib/stars_by_value` pipeline | N/A | N | 2006–2025 | QB/RB/WR/TE | `outcome_availability_category` ∈ {`scored_labeled`, `scored_but_unlabeled`, `out_of_scope_by_sbv_design`, `no_sbv_row_found`} — §3's revised table; label only real for `scored_labeled` | **2A outcome (artifact 2), never a predictor input** | Status + score + nullable label |
| `bust_label_primary`, `bust_label_strict_hybrid`, `underperformance_diagnostic` | N/A — Dataset 2B outcome | Not yet built (§10) | N/A | N | N/A | QB/RB/WR/TE | **Reserved in this document's schema/data-dictionary only — NOT added as columns to any production table (§10's revised policy)** | **2B outcome (artifact 2, once built)** | Reserved name only, no column exists yet |

---

## 12. Explicit tests to write for the canonical-table build (not
written yet — proposed scope)

1. **Duplicate player-season keys**: assert
   `df.duplicated(subset=["season","player_id"]).sum() == 0` on the
   FINAL joined table, not just on each source frame individually —
   a many-to-one join bug in any single step (e.g. an un-deduplicated
   family #9 pivot) could reintroduce duplicates that no individual
   module's own tests would catch.
2. **Same-season leakage**: for every lagged column, assert its real
   underlying value is NEVER equal to that same player's OWN
   same-season raw value in a way that implies the lag didn't actually
   shift — concretely, reuse each module's own raw-vs-preseason pair
   (e.g. `usage_traits.py`'s `build_raw_season_usage()` vs.
   `build_preseason_usage_features()`) and assert
   `preseason.loc[season=N] == raw.loc[season=N-1]` exactly, for every
   lagged family. **DONE for family #9** —
   `tests/test_dataset2_partial_season_canonical.py`'s `TestLagLeakage`
   proves this directly (mutation-isolation in both directions, not
   just an equality check against a fixed fixture) — still needed for
   every OTHER lagged family once the artifact-1 build script actually
   assembles them together (§13).
3. **Accidental loss of minimal-market-cost players**: assert every
   one of SBV's 54 real `minimal_market_cost_scored` (season,
   player_id) rows is present in artifact 3 (the joined analysis view)
   with its full predictor set from artifact 1 (not just its outcome
   label from artifact 2) — a real, checkable regression test using
   the real SBV export, not a synthetic fixture.
4. **Players changing teams**: reuse family #9's own traded-player
   fixture pattern (`TEAM_GAME_STATUS_UNAVAILABLE_TRADED`) at the
   canonical-table level — assert a real traded player's row has (a)
   real, non-null active-game-basis predictors, (b) null team-game-
   basis predictors for that specific season, and (c) a real,
   non-null `fam44_prior_changed_team` flag the FOLLOWING season.
5. **Rookies with no prior-season NFL data**: assert every rookie row
   (season == real rookie_season) has every lagged predictor null AND
   `seasons_of_prior_data == 0` AND every preseason-safe-by-construction
   predictor (age, draft capital, depth chart) still POPULATED — a
   rookie should never look like a player with no data at all, only a
   player with no NFL history.
6. **Source-coverage boundaries (snap data 2013+)**: assert every
   Source-B-derived column is null for season ≤ 2012 and that
   `source_b_coverage_era` correctly reads `"uncovered_pre_2013"` for
   those rows and `"covered_2013_plus"` from 2013 on — including the
   lagged case (season 2013's OWN predictors need season-2012 snap
   data, which doesn't exist, so 2013's PRESEASON snap columns should
   also be null, one year later than the raw boundary).
7. **Nullable booleans converted incorrectly to `False`**: assert, for
   every boolean-shaped canonical column, that `pd.NA`/null values
   round-trip correctly through whatever persistence format the table
   is actually saved in (parquet preserves pandas' nullable `"boolean"`
   dtype; CSV does not — a real, concrete risk flagged in §6 that
   needs a real round-trip test, not just an in-memory assertion,
   before choosing the storage format in §13) — specifically assert
   `pd.read_<format>(path)["some_flag"].isna().sum() == expected`
   rather than trusting the in-memory dtype alone.

---

## 13. Proposed build order

1. ~~Close the family #9 lag gap first (§5)~~ — **DONE.**
   `lib/dataset2/partial_season_canonical.py` implements both the
   grain pivot (`build_family9_observation_wide()`) and the lag
   (`build_family9_preseason_features()`), tested (17/17 in
   `tests/test_dataset2_partial_season_canonical.py`).
2. **Build artifact 2 (canonical outcome table)** — smaller and
   lower-risk than artifact 1: read the real SBV export, add the four
   `outcome_availability_category` values (§3), reserve (schema-only,
   §10) the three Dataset 2B names. No dependency on family #9 or any
   predictor module.
3. **Build artifact 1 (canonical PRESEASON PREDICTOR table)** — a new,
   explicit module (location TBD, not decided here) that: loads the
   base population (§3), runs Sources A/B acquisition + identity
   crosswalk (§4), calls every non-family-#9 predictor module once,
   left-joins `build_family9_preseason_features()`'s own output by
   (`prediction_season`, `player_id`) — no new pivot/lag logic needed
   here, that work is already done — and applies the general
   `_prior_`-naming rule (§7) to every OTHER family's lagged columns
   (family #9's own columns already carry no per-column prefix, by the
   revised rule in §7).
4. **Build artifact 3 (analysis view)** — the join of (2) and (3) onto
   (1)'s output, kept as its own step/script so the leakage boundary
   (§10) stays structurally enforced, not just conventionally.
5. **Write the remaining §12 tests** (items 1, 3–7 — item 2 is done for
   family #9) against artifacts 1/2/3 together, using a small real
   slice of the actual source files.
6. **Run the real 2006-2025 population through artifacts 1–3 once**,
   producing real row/column counts and a real missingness breakdown
   per column (mirroring the 2026-07 integration audit's own format)
   — present that before choosing a final persistence format or
   committing any of the three tables.
7. **Decide persistence format** (parquet vs. CSV) informed directly
   by §12 item 7's nullable-boolean round-trip test result, not
   decided in advance of that test.

---

## Stop point (updated — canonical predictor table round)

**Committed in an earlier round**: this proposal document, and
`lib/dataset2/partial_season_canonical.py` /
`tests/test_dataset2_partial_season_canonical.py` (family #9's grain
pivot and lag layer).

**Built and run this round**: `lib/dataset2/canonical_predictor_table.py`
(artifact 1 — the canonical PRESEASON PREDICTOR table),
`scripts/build_dataset2_canonical_predictor_table.py` (real-data
driver), `scripts/audit_dataset2_outcome_gap.py` (the independent SBV
outcome-gap reconciliation, never joined into the predictor artifact),
and `tests/test_dataset2_canonical_predictor_table.py`. A real, found
bug (`lib/dataset2/common.py::kickoff_lookup_table()` crashing on a
genuinely empty schedule, exactly this environment's real condition)
was fixed. A second real bug, found only by running against the FULL
real population (no single-season synthetic fixture could have caught
it) — the future-prediction-season spine extension was creating a
phantom row for every retired player's own last season, not just the
dataset's real 2025→2026 boundary — was found and fixed, with a
regression test. Real output: 11,784 rows, 435 columns, 2006–2026
prediction-season coverage, zero duplicate keys, deterministic
rebuild verified. Full suite passing (1002/1002).

**NOT implemented, per instruction — stopping here**: artifacts 2
(outcome table) and 3 (analysis view). The outcome-gap audit is a
standalone research artifact for whoever builds artifact 2 next, not
a step toward joining it into artifact 1.
