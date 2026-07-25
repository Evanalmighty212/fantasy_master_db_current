# Stars-by-Value Implementation Plan (Approved plan, no code written yet)

**Status: planning document, approved; no code written.** This
proposes how to turn `STARS_BY_VALUE_METHODOLOGY.md` (sections 1-11,
all settled) into real pipeline code. `config.py` is untouched; this
file itself is unstaged, matching every other artifact produced during
this investigation. Do not begin writing code from this plan without a
separate, explicit go-ahead.

**Revision note**: the five open implementation decisions this plan
originally flagged (output artifact location, `E_P` caching, the 2010
override schema, reference-data fetching cadence, nullable-`Int8`
typing) are now resolved -- see the decision points inline below and
the closing "Decisions now settled" section. No open implementation
ambiguity remains as of this revision.

Verified against the actual repo structure before writing this (not
assumed): `config.py`'s existing `LWI_*` constant block and
`validate_lwi_config()` pattern, `scripts/01`-`07` numbered-stage
convention, `scripts/05_calculate_metrics.py` as the closest existing
analog (spec-driven, explicit eligibility scope, null-with-reason for
ineligible rows), `scripts/player_matching.py` and
`scripts/nflverse_source.py` as reusable infrastructure,
`research/dataset3/lib/replacement.py` as the (research-scoped)
replacement-level module, and `tests/` as one file per script.

---

## 1. Config constants and enums

New block in `config.py`, prefixed `SBV_` (Stars-by-Value) to avoid
any collision with the existing `LWI_*` block -- these are two
separate metrics on two separate specs (`METRIC_SPECIFICATION.md` vs.
`STARS_BY_VALUE_METHODOLOGY.md`), not variants of one.

```python
# --- Stars-by-Value (Dataset 3 historical label) ---
SBV_VERSION = "1.0"

# Sections 2-4: production composite
SBV_SHRINKAGE_K = 5
SBV_PRODUCTION_WEIGHT_AATP = 0.5
SBV_PRODUCTION_WEIGHT_PPG_EQ = 0.5

# Section 5: meaningful-production gate (p82.5), position floors -- fixed constants,
# NOT re-derived per season (Absolute Impact property)
SBV_PRODUCTION_GATE_FLOOR = {"QB": 142.599891, "RB": 113.712500, "WR": 98.105667, "TE": 66.679583}

# Replacement-level definition SBV uses (flex_rb_wr_heavy) -- DISTINCT from LWI's own
# LWI_REPLACEMENT_RANK_THRESHOLDS; do not conflate the two specs' replacement definitions.
SBV_REPLACEMENT_ROSTER_PRESET = "12_team_standard"
SBV_REPLACEMENT_RANK_CUTOFFS = {"QB": 12, "RB": 29, "WR": 29, "TE": 13}
SBV_REPLACEMENT_FLEX_ALLOCATION = {"RB": 0.45, "WR": 0.45, "TE": 0.10}
SBV_REPLACEMENT_WINDOW = 12

# Section 7: expected-AATP/production-by-round fitting
SBV_MIN_PRIOR_SEASONS = 3
SBV_TRUSTWORTHY_ADP_START_SEASON = 2007
SBV_FIRST_SCOREABLE_SEASON = 2010  # derived: SBV_TRUSTWORTHY_ADP_START_SEASON + SBV_MIN_PRIOR_SEASONS
SBV_ROUND_OFFSET_POSITIONS = {"QB", "RB"}       # QB_RB positional-offset variant
SBV_RECENCY_HALF_LIFE_YEARS = 5
SBV_RECENCY_POSITIONS = {"QB"}                  # recency weighting is QB-specific, not global

# Section 10: lambda + final Star thresholds
SBV_LAMBDA = 0.35
SBV_STAR_THRESHOLD = {"QB": 176.5, "RB": 188, "WR": 171, "TE": 134}

# Section 9: minimal-market-cost -- opportunity probability x replacement-implied rate
SBV_MMC_OPPORTUNITY_PROBABILITY = {"QB": 0.247, "RB": 0.290, "WR": 0.368, "TE": 0.285}
# "meaningful usage" definition used ONLY to calibrate the probabilities above --
# not consulted at scoring time; kept here for traceability/re-audit, not live use.
SBV_MMC_USAGE_DEFINITION = {
    "QB": {"stat": "attempts", "min": 100},
    "RB": {"stat": "touches", "min": 40},
    "WR": {"stat": "targets", "min": 20},
    "TE": {"stat": "targets", "min": 20},
}
SBV_MFL_AVAILABLE_FROM_SEASON = 2011
SBV_MFL_PERIOD = "AUG15"

# Section 11: status / provenance enums -- single source of truth, imported everywhere
# else that needs to validate or branch on these instead of restating the list.
SBV_STATUSES = (
    "adp_scored", "unscoreable_adp_needs_review", "minimal_market_cost_scored",
    "unscoreable_drafted_adp_missing", "unscoreable_ambiguous",
    "below_production_gate", "out_of_scope",
)
SBV_PROVENANCE_TYPES = (
    "adp_matched_clean", "adp_matched_needs_review",
    "mmc_verified_corroborated", "mmc_verified_2010_manual_override",
    "evidence_drafted_unresolved", "evidence_ambiguous_disagreement",
    "below_production_gate",
    "out_of_scope_non_skill_position", "out_of_scope_temporal_window",
    "out_of_scope_insufficient_participation",
)

def validate_sbv_config():
    """Fail loud, not silent -- mirrors validate_lwi_config()."""
    # position-completeness: every position-keyed dict has exactly {QB,RB,WR,TE}
    # 0 < SBV_LAMBDA < 1
    # SBV_FIRST_SCOREABLE_SEASON == SBV_TRUSTWORTHY_ADP_START_SEASON + SBV_MIN_PRIOR_SEASONS (derived, checked, not just asserted)
    # every SBV_MMC_OPPORTUNITY_PROBABILITY in (0, 1)
    # SBV_STATUSES / SBV_PROVENANCE_TYPES have no duplicates
```

**Config-visibility principle applied here deliberately**: the
usage-threshold convention (100 attempts / 40 touches / 20 targets)
and the classifier's prior-production lookback thresholds (see #4
below) are explicitly disclosed in the methodology as *conventions,
not uniquely correct cutoffs* -- they must live in `config.py`, never
hardcoded inline in a script, precisely because the doc already flags
them as things a future reviewer might reasonably revisit.

---

## 2. Pipeline stage ordering (follows the settled routing sequence exactly)

Four numbered stages, continuing the existing `01`-`07` convention.
**Stage 08 is a deliberate, manually-triggered refresh step, not part
of a normal scoring run** -- see decision #4 below; stages 09-11 only
ever read already-fetched, already-pinned local files.

| Stage | Script | Trigger | Settled-methodology step |
|---|---|---|---|
| Fetch/refresh reference data | `scripts/08_fetch_sbv_reference_data.py` | Manual, explicit (`--refresh`) | Infrastructure for steps 3-4; never auto-invoked |
| Fit and cache `E_P` lookup tables | `scripts/09_fit_sbv_expected_production.py` | Part of an intentional build; re-run when inputs or `SBV_VERSION` change | Section 7, materialized once per build |
| Classify acquisition cost | `scripts/10_classify_sbv_acquisition_cost.py` | Normal pipeline run | Step 3: acquisition-cost resolution |
| Compute score + assign label | `scripts/11_calculate_stars_by_value.py` | Normal pipeline run | Steps 1, 2, 4: temporal scope -> gate -> score/label, consuming stages 09 and 10's output |

Step 1 (temporal/study-scope) and step 2 (production gate) both live
in `11_calculate_stars_by_value.py`, ahead of everything else in that
script -- literally the first two checks run, so that `below_production_gate`
is structurally impossible to assign to a pre-2010 row (matches the
methodology's "no case satisfies two status descriptions" resolution,
enforced by code structure, not just documentation).

Stage 09 (`E_P` fitting) has no dependency on stage 10 (acquisition-cost
classification) or vice versa -- fitting `E_P` by round only needs the
existing ADP-matched population, not the no-ADP-match classification
work. They're numbered sequentially for pipeline clarity, not because
one blocks the other; stage 11 is the only stage that needs both.

---

## 3. Existing code to reuse or modify

| Existing artifact | Disposition |
|---|---|
| `scripts/player_matching.py` | **Reuse as-is.** Already production-quality (override table, confidence tiers, `matched_clean`/`matched_needs_review`/`no_adp_match` classification). SBV consumes its output; does not modify it. |
| `scripts/nflverse_source.py` | **Reused as-is for usage stats; extended for `players` and `depth_charts` (Commit 2, landed).** Verified directly against the repo (not assumed from scratch research): this module already fetches the `stats_player` release at week grain (`stats_player_week_<season>.csv`, asset-ID pinned, sha256-verified, manifest covers 2006-2025 in full), and the already-cached local files already contain `attempts`/`carries`/`targets`/`receptions` -- exactly what the MMC usage-definition calibration needs. **No new fetch or asset pinning for usage stats** -- `acquisition_cost.py` calls the existing `fetch_and_normalize()` and sums the relevant columns per player/season itself. `players` (draft capital, single file, no season grain) and `depth_charts` (rookie-QB correction, season grain) were genuinely new -- confirmed no existing fetch mechanism for either -- and are now fetched via `fetch_players()`/`fetch_depth_chart(season)`, same asset-ID-pinning + sha256 verification + explicit-registration-only model as `stats_player`, registered for `players.csv` (single entry) and `depth_charts` seasons 2006-2025 (matching `config.SEASONS`). **Real finding from registering all 20 seasons: nflverse's `depth_charts_2025.csv` uses a completely different 12-column schema** (`dt`/`team`/`espn_id`/`pos_grp`/`pos_slot`/`pos_rank`, ~15x the row count of any other season -- apparently a different upstream vendor as of this migration) than the consistent 15-column schema verified identical across every one of 2006-2024. The 2025 file is still registered and fetchable (fetching is schema-agnostic by design), but no consumer code normalizes or interprets it yet -- `acquisition_cost.py` (Commit 7) will need to either handle both shapes or explicitly exclude 2025 until decided; not resolved by this commit. |
| `research/dataset3/production_weight_and_boundary_calibration.py::build_adp_aware_aatp()` | **Promote, with rewrites.** Correct logic, wrong location/config-coupling -- currently hardcodes `WINDOW=12`, `MIN_PRIOR_SEASONS=3`, the roster preset dict, etc. inline. Must be rewritten to read from the new `SBV_*` config constants instead of local hardcoded values before it's production code. |
| `research/dataset3/lib/replacement.py` | **Promote with minimal changes.** Already parameterized (takes roster/flex assumptions as explicit arguments, not hardcoded) -- close to production-ready as written. Move under a shared `lib/` (not `research/dataset3/lib/`) so both research and production code import the same module rather than forking it. |
| `research/dataset3/expected_production_by_round_investigation.py` | **Promote the fitting logic, not the script.** `adp_round()` helper and the expanding-window/QB_RB-offset/recency-weighting fit logic are correct and settled -- extract into a real module; the surrounding research script (comparison harnesses, print statements, CSV dumps for calibration) does not belong in production. |
| The rookie-QB depth-chart correction, the classifier, the 3-way corroboration | **Do not exist as saved code at all.** Every one of these was built and run as ad hoc Python in this conversation, writing to scratch space (`/private/tmp/.../scratchpad`), never committed anywhere. This is the single biggest gap between "settled methodology" and "implementable" -- see #4 and #9. |
| The MFL client | **Built (Commit 3, landed) at `scripts/mfl_client.py`, not `lib/stars_by_value/mfl_client.py` as originally sketched in section 4 below.** Deliberate placement correction, mirroring `nflverse_source.py`'s precedent: this module is pure fetch/cache/rate-limit infrastructure with no SBV business logic, same role as `nflverse_source.py`, so it lives alongside it in `scripts/` -- `lib/stars_by_value/` stays reserved for modules that actually apply SBV methodology (`production.py`, `expected_production.py`, `acquisition_cost.py`, `minimal_market_cost.py`, `labeling.py`). Fetches `TYPE=adp&PERIOD=AUG15` and `TYPE=players`, cache-first with an explicit `force_refresh`. **Real finding that shaped its design**: MFL's `TYPE=adp` report is a live, continuously-growing aggregate, not a frozen artifact -- confirmed directly, querying season 2023 live returned `totalDrafts=9,970` and Puka Nacua at rank 213/16%, versus `totalDrafts=7,923` and rank 209/18% recorded earlier in `docs/ADP_SOURCE_MATRIX.md` from a prior-date query. **Integrity model (revised once before landing, see below)**: a cache hit (hash matches) returns silently, no network call; a missing local file is fetched (bootstrap, not a replacement); a cache PRESENT but hash-MISMATCHED against the manifest raises loudly with no network call, naming `force_refresh=True` as the explicit way to accept new data -- normal (non-refresh) runs must never make an unexpected network request just because a local snapshot looks stale or was edited. `force_refresh=True` always fetches fresh and prints old-vs-new values when a snapshot is replaced. **`scripts/mfl_source_manifest.json` IS committed to git** (unlike the raw per-response JSON under `data/raw/mfl/`, which stays gitignored) -- a compact snapshot registry per season/endpoint (URL/params including `PERIOD=AUG15`, `retrieved_at`, `sha256`, `total_drafts`, `row_count`, `sbv_version`), with an explicit `note` field in the JSON itself clarifying that it documents the exact snapshot used but cannot, by itself, reproduce MFL's live report byte-for-byte -- a future immutable archive of the raw responses may be needed for full reproducibility. Rate-limiting constants live in `config.py`'s `SBV_*` block (`SBV_MFL_MIN_REQUEST_DELAY_SECONDS`, `SBV_MFL_MAX_RETRIES`, `SBV_MFL_BACKOFF_BASE_SECONDS`, `SBV_MFL_REQUEST_TIMEOUT_SECONDS`) as implementation metadata, not hardcoded in the client -- operational tunables, not methodology, per explicit direction. |

---

## 4. New modules required

```
lib/stars_by_value/
    __init__.py
    production.py           # AATP, shrinkage, composite -- promoted from build_adp_aware_aatp()
    expected_production.py  # section 7 fitting: expanding window, QB_RB offset, recency, no leakage;
                             # writes the materialized lookup table, does not refit at row-scoring time
    acquisition_cost.py     # NEW: classifier + depth-chart QB correction + 3-way MFL corroboration
                             #      + 2010-cohort fallback. Currently exists nowhere as real code.
    minimal_market_cost.py  # section 9: opportunity-based E_P, season-varying G
    labeling.py             # section 11: 4-step status routing, final schema assembly
```

`scripts/mfl_client.py` -- **built (Commit 3, landed), moved out of the
`lib/stars_by_value/` tree above.** Lean production MFL client
(rate-limited, cached, `PERIOD=AUG15` always explicit -- see the
PERIOD-contamination finding in `ADP_SOURCE_MATRIX.md`). NOT a reuse of
`research/diagnostics/mfl_pipeline/mfl_client.py`, which is explicitly
marked "ISOLATED -- never wired into any production code" and was
built for a different (2025 canonical-ADP) question -- same
rate-limiting/caching discipline, new module. Placed alongside
`nflverse_source.py` rather than under `lib/stars_by_value/` because
it is pure fetch/cache infrastructure with no SBV business logic, same
role as that module -- see section 3.

```

scripts/08_fetch_sbv_reference_data.py        # manual refresh step, see decision #4
scripts/09_fit_sbv_expected_production.py     # materializes the E_P lookup table, see decision #2
scripts/10_classify_sbv_acquisition_cost.py
scripts/11_calculate_stars_by_value.py

data/manual/mmc_2010_manual_overrides.csv     # new, empty-with-headers -- the rare override path, see decision #3
```

`acquisition_cost.py` deserves emphasis: the classifier (draft
capital + rookie status + prior-production lookback + the narrow
rookie-QB Week-1-starter depth-chart correction) and the whole 3-way
MFL corroboration framework are the largest pieces of *settled logic
with zero corresponding saved code*. Every version of this ran once,
in a scratch Python session, against files cached to `/tmp`, then was
described in prose in `ADP_SOURCE_MATRIX.md`. Writing `acquisition_cost.py`
is a real implementation effort, not a promotion of an existing
script.

---

## 5. Required inputs and joins

**Decision #4 -- reference-data fetching is an explicit refresh, never
part of a normal scoring run.** `08_fetch_sbv_reference_data.py` is
invoked deliberately (e.g. `python scripts/08_fetch_sbv_reference_data.py --refresh`),
writes pinned local files plus a manifest (mirroring the existing
`nflverse_source_manifest.json` asset-ID + sha256 pattern), and is the
*only* stage that ever makes a live external call. Stages 09-11 read
exclusively from the resulting local files under `data/raw/`; if a
required file is missing, they fail loudly with "run stage 08 first,"
never attempt a silent fetch. This is precondition for reproducibility:
identical code run twice against unpinned live endpoints could
otherwise produce different results, or fail outright if a historical
endpoint (MFL's 2010-and-earlier gap is the concrete precedent) simply
stops responding.

| Input | Source | Local artifact (after stage 08) | Used by |
|---|---|---|---|
| `weekly_results_ppr_2006_2025.csv` | existing `data/raw/nflverse/` | already present | `production.py` (first-active-week) |
| `player_matches.csv` / master DB | existing `scripts/04` output | already present | everywhere (adp_round, data_quality_flag, games_played, fantasy_points_ppr) |
| nflverse `stats_player` release, week grain (attempts/carries/targets) | **already fetched, already cached** -- `nflverse_source.py::fetch_and_normalize()`, no change needed | `data/raw/nflverse/annual/stats_player_week_<season>.csv`, manifest covers 2006-2025 | Recalibrating the frozen opportunity probabilities, **calibration-only** -- never read by `minimal_market_cost.py` at normal scoring time (decision #2/#8). Verified directly against the repo: confirmed present, not a new fetch (see section 3). |
| nflverse `players` release (draft_round, draft_pick, rookie_season) | genuinely new, fetched via `nflverse_source.py::fetch_players()` (Commit 2, landed) | `data/raw/nflverse/reference/players.csv`, single manifest entry (no season grain) | `acquisition_cost.py` classifier |
| nflverse `depth_charts` release, per season | genuinely new, fetched via `nflverse_source.py::fetch_depth_chart(season)` (Commit 2, landed) | `data/raw/nflverse/annual/depth_charts_<season>.csv`, manifest covers 2006-2025 -- **2025 uses a different, not-yet-normalized schema, see section 3** | `acquisition_cost.py`, rookie-QB correction only |
| MFL `PERIOD=AUG15` ADP + player directory, 2011+ | genuinely new, fetched via `scripts/mfl_client.py::fetch_adp(season)`/`fetch_players(season)` (Commit 3, landed) | Raw JSON at `data/raw/mfl/adp_<season>_period_aug15.json`, `data/raw/mfl/players_<season>.json` -- gitignored, **not cross-environment-reproducible by design** (MFL's report is a live aggregate, see section 3). The COMMITTED record is `scripts/mfl_source_manifest.json` -- a compact snapshot registry (url/params, retrieved_at, sha256, total_drafts, row_count, sbv_version per season/endpoint), documenting exactly what was used without being able to reproduce it byte-for-byte. | `acquisition_cost.py` corroboration, name-matched against our master DB via `player_matching.py`'s existing normalization (not `mfl_client.py`, which is fetch-only) |
| `data/manual/player_name_overrides.csv` | existing, already has the Vick 2011-2013 rows added this investigation (currently unstaged) | n/a -- hand-maintained | ADP matching (via `player_matching.py`) |
| `data/manual/mmc_2010_manual_overrides.csv` | new, manual, rare | n/a -- hand-maintained | `acquisition_cost.py`, 2010-cohort fallback only, see decision #3 |

---

## 6. Output columns, dtypes, and canonical artifact paths

**Decision #1 -- separate canonical output, not merged into the LWI
master table.** `data/processed/stars_by_value_player_seasons.parquet`
is the canonical SBV artifact for this first implementation. It is
*not* joined into `master_historical_db_with_lwi_2006_2025.csv`. A
later, separately-approved integration stage may join selected SBV
columns into the master export once the standalone artifact has been
validated -- easier to inspect, regenerate, and compare in isolation
than a change embedded in the existing master pipeline, and it can't
destabilize LWI's own output by construction (nothing writes to that
file at all).

**Decision #5 -- Parquet is the canonical typed artifact; CSV is a
convenience export only.**

| Artifact | Path | Role |
|---|---|---|
| Canonical, typed | `data/processed/stars_by_value_player_seasons.parquet` | Source of truth. `star_by_value_label` stored as `Int8` (pandas/pyarrow nullable integer) -- Parquet preserves this exactly, unlike CSV. |
| Convenience export | `data/exports/stars_by_value_player_seasons.csv` | Generated *from* the Parquet file, never authored independently. `star_by_value_label` renders as `1`, `0`, or blank. Not authoritative for dtype -- a round-trip test (`pd.read_csv(..., dtype={"star_by_value_label": "Int8", ...})`) must reproduce the Parquet values exactly, or the export step fails. |
| Schema reference | `data/exports/stars_by_value_player_seasons_SCHEMA.md` | Data dictionary accompanying the CSV export -- column names, dtypes, allowed enum values, and a pointer back to `STARS_BY_VALUE_METHODOLOGY.md` section 11 for full semantics. |

Column list (from the settled Section 11 schema):

| Column | Dtype (Parquet) | Notes |
|---|---|---|
| `star_by_value_label` | `Int8`, nullable | |
| `star_by_value_score` | `float64` (NaN = NULL) | |
| `star_by_value_status` | `category` / string, values restricted to `config.SBV_STATUSES` | |
| `star_by_value_production_gate_threshold` | `float64` (NaN = NULL) | |
| `star_by_value_threshold` | `float64` (NaN = NULL) | |
| `star_by_value_provenance_type` | `category` / string, values restricted to `config.SBV_PROVENANCE_TYPES` | |
| `star_by_value_evidence_notes` | `string`, nullable | never read by pipeline logic downstream, audit-only |

**Auxiliary columns recommended alongside the seven official ones**
(matches this project's existing practice of keeping LWI's intermediate
components visible in the master DB rather than only the final score):
`sbv_production_composite` (`P`), `sbv_aatp`, `sbv_ppg_ar_eq_shrunk`,
`sbv_expected_production` (`E_P`, whichever source produced it),
`sbv_games_played_capped`, `sbv_G_season`. These make every status/label
independently auditable from the output file alone, without re-running
the pipeline.

---

## 7. Implementing the seven statuses and provenance values

`labeling.py` implements the four-step order as a single ordered
function, roughly:

```python
def assign_sbv_status(row, expected_production_lookup, mmc_constants) -> SbvResult:
    # Step 1: temporal/study-scope eligibility
    if row.season < config.SBV_FIRST_SCOREABLE_SEASON:
        return out_of_scope(provenance="out_of_scope_temporal_window")
    if row.position not in config.SBV_PRODUCTION_GATE_FLOOR:
        return out_of_scope(provenance="out_of_scope_non_skill_position")
    if row.games_played < 1:
        return out_of_scope(provenance="out_of_scope_insufficient_participation")

    # Step 2: production gate (P already computed upstream by production.py)
    if row.P < config.SBV_PRODUCTION_GATE_FLOOR[row.position]:
        return below_production_gate(row)   # label=0, score=NULL, gate threshold populated, star threshold NULL

    # Step 3: acquisition-cost resolution (gate-clearing rows only)
    if row.data_quality_flag == "matched_clean":
        return adp_scored(row, expected_production_lookup)          # -> step 4
    if row.data_quality_flag == "matched_needs_review":
        return unscoreable_adp_needs_review(row)                    # both thresholds populated, score/label NULL
    # no_adp_match:
    return resolve_acquisition_cost(row, mmc_constants)             # classifier + MFL (+ 2010 fallback) -> step 4 or unscoreable
```

Each branch function is a small, independently testable unit -- this
is deliberate: the test plan (#10) tests these branches individually,
not only end-to-end.

---

## 8. Season-varying minimal-market-cost constants

`minimal_market_cost.py` reuses the **existing** `verified_season_length()`
function already defined in `production_weight_and_boundary_calibration.py`
(16 games through 2020, 17 from 2021) -- do not reimplement this a
second time; import the one function everywhere `G(season)` is needed
(sections 2 and 9 must never drift apart).

```python
def minimal_market_cost_expected_production(position: str, season: int) -> float:
    G = verified_season_length(season)
    return (
        config.SBV_MMC_OPPORTUNITY_PROBABILITY[position]
        * 0.5
        * SETTLED_REPLACEMENT_PPG[position]   # equal-weighted full-history constant, frozen
        * G
    )
```

`SETTLED_REPLACEMENT_PPG` (14.746 / 9.361 / 11.423 / 7.970 for
QB/RB/WR/TE) is itself a frozen, already-calibrated constant -- it
belongs in `config.py` alongside `SBV_MMC_OPPORTUNITY_PROBABILITY`,
never recomputed live from `stats_player` data at scoring time
(decision #4 -- `stats_player` is a calibration-only, explicit-refresh
input, not something stage 11 reads).

---

## 8a. 2010 manual-override schema (decision #3)

**New file**: `data/manual/mmc_2010_manual_overrides.csv` -- narrow,
hand-maintained, git-tracked (alongside `player_name_overrides.csv`
and `position_overrides.csv`, the other two files in `data/manual/`).
Starts **empty** (headers only) at implementation time -- it is not
pre-populated with Vick 2010 or any other row; every row it ever gets
is a deliberate, reviewed, documented act, not a migration of existing
findings.

| Column | Type | Required | Notes |
|---|---|---|---|
| `season` | `int` | yes | Must equal `2010` -- this mechanism is sanctioned only for the 2010 cohort by settled methodology (section 11). Using it for another season would need a new methodology decision, not just a new row. |
| `player_id` | `string` | yes | nflverse `gsis_id`, the join key |
| `player_name` | `string` | yes | human-readable, audit convenience only, not a join key |
| `override_type` | `enum {usable_adp, minimal_market_cost}` | yes | Which of the two mutually exclusive paths this row supplies |
| `market_cost_status` | `enum {adp_scored, minimal_market_cost_scored}` | yes | The final `star_by_value_status` this override will cause -- must agree with `override_type` (`usable_adp` -> `adp_scored`, `minimal_market_cost` -> `minimal_market_cost_scored`) |
| `adp_overall` | `float`, nullable | only if `override_type == usable_adp` | The recovered canonical overall pick |
| `adp_round` | `int`, nullable | only if `override_type == usable_adp` | Derived from `adp_overall` the same way as everywhere else in this pipeline |
| `minimal_market_cost_approved` | `bool`, nullable | only if `override_type == minimal_market_cost` | `TRUE` only when approved; never `TRUE` alongside populated `adp_overall`/`adp_round` |
| `source` | `string` | **yes, mandatory** | Named, citable source (e.g. "MyFantasyLeague direct query," "NFL.com draft do-over article") |
| `source_date` | `date` | **yes, mandatory** | Snapshot/publication date of the source, as precise as available |
| `evidence_summary` | `string` | **yes, mandatory** | The specific evidence, e.g. a direct quote or a described query result -- not a restatement of the classifier's own reasoning |
| `confidence` | `enum {high, medium, low}` | yes | Human-assigned |
| `approved_by` | `string` | yes | Who signed off -- an explicit accountability record even in a single-maintainer project |
| `notes` | `string`, nullable | no | |

**Validation rules** (enforced by a loader that raises on violation,
not just documented):

1. **Exactly one of** {`adp_overall`/`adp_round` populated} **or**
   {`minimal_market_cost_approved = TRUE`} per row, never both, never
   neither -- `override_type` and the populated fields must agree.
2. **No override may be created from classifier output alone.**
   `evidence_summary` and `source` must reference something the
   automated classifier does not already consider (draft capital,
   rookie status, and the prior-production heuristic are exactly what
   the classifier already tried and failed to resolve for 2010 --
   citing them again is not new evidence). This is a process rule
   enforced at review time, not something a loader can fully check
   mechanically, but the loader does reject any row whose
   `evidence_summary` is empty or whose `source` duplicates a known
   classifier-internal signal name.
3. `source` and `evidence_summary` are schema-level `NOT NULL` --
   empty or missing values fail validation outright.
4. **Vick 2010 remains `unscoreable_drafted_adp_missing`** -- no row
   for him exists in this file at implementation time. The existing
   NFL.com "14th round" citation is a real, named source but a single
   restated number with no snapshot date, scoring format, or
   underlying table -- it does not currently meet this project's
   source-quality bar for a canonical ADP value (the same bar applied
   throughout `ADP_SOURCE_MATRIX.md`). He stays there unless a future
   source is judged sufficient under that same standard -- not
   promoted by this schema's mere existence.

---

## 9. Expanding-window / recency-weighted `E_P` fitting -- materialized, not refit per row

**Decision #2 -- `E_P` is fit once per build into a versioned lookup
artifact; stage 11 only ever performs a join against it, never refits
inside row-level logic.** `scripts/09_fit_sbv_expected_production.py`
implements section 7 exactly, and is a distinct pipeline stage from
final scoring specifically so the (comparatively expensive,
methodology-sensitive) fitting step is auditable as its own artifact.

**Canonical artifact**: `data/processed/sbv_expected_production_lookup.parquet`

| Column | Dtype | Meaning |
|---|---|---|
| `prediction_season` | `int16` | The target season `Y` this row's `E_P` applies to |
| `position` | `category` | QB/RB/WR/TE |
| `draft_round` | `int8` | |
| `expected_production` | `float64` | Fitted `E_P(round, position)` for `prediction_season` |
| `positional_offset_applied` | `float64`, nullable | The `QB_RB` offset amount folded into this cell, `NULL` where no offset applies |
| `recency_weighted` | `bool` | Whether recency weighting was applied for this `(prediction_season, position)` |
| `half_life_years` | `float64`, nullable | `5.0` where `recency_weighted`, else `NULL` |
| `sample_size` | `int32` | `n` training rows (prior seasons only) behind this fitted cell |
| `sbv_version` | `string` | Stamped from `config.SBV_VERSION` at fit time |
| `fit_timestamp` | `timestamp` | When this row was generated |

Every row for every `(prediction_season, position, draft_round)` from
`SBV_FIRST_SCOREABLE_SEASON` through the latest fittable season is
generated in one build pass -- **fit via honest expanding windows
only**, exactly as section 7 requires: the training data behind
`prediction_season = Y` is strictly seasons `< Y`, minimum
`SBV_MIN_PRIOR_SEASONS` (3) of them, never leave-one-season-out, and
never any season `>= Y`. This is checked mechanically by
`TestNoLeakageInExpectedProduction` (below), not just documented.

**Cache invalidation and regeneration rules**:

- The lookup table is **not** a permanent, hand-maintained constant --
  it must be regenerated whenever (a) `config.SBV_VERSION` changes,
  (b) any of the fitting-relevant config (`SBV_ROUND_OFFSET_POSITIONS`,
  `SBV_RECENCY_HALF_LIFE_YEARS`, `SBV_RECENCY_POSITIONS`,
  `SBV_MIN_PRIOR_SEASONS`) changes, or (c) the upstream ADP-matched
  population it's fit from changes (a new season's data lands, or a
  correction is made to existing matched rows).
- Enforced, not just advised: stage 11 reads the lookup table's
  `sbv_version` column and compares it against the *running* code's
  `config.SBV_VERSION` before using it. Mismatch -> fail loudly
  ("stale `E_P` lookup table, re-run stage 09"), never silently score
  against an outdated fit.
- Regeneration is part of stage 09's own explicit invocation (same
  "deliberate, not automatic" posture as stage 08's fetch, decision
  #4) -- a normal stage 11 scoring run never triggers a refit itself.

---

## 10. Test plan (one test class per settled invariant)

| Test | What it protects |
|---|---|
| `TestSbvConfigValidation` | `validate_sbv_config()` catches malformed config the way `validate_lwi_config()` already does |
| `TestProductionGateFloorValues` | Section 5 floors match config exactly, position-complete |
| `TestGateRunsBeforeCostResolution` | A synthetic gate-failing `matched_clean` row never receives a computed score |
| `TestPre2010NeverBelowGate` | Step 1 strictly precedes step 2 -- a synthetic pre-2010, gate-failing row is `out_of_scope`, never `below_production_gate` |
| `TestMatchedNeedsReviewRouting` | Needs-review + gate-pass -> `unscoreable_adp_needs_review`, both thresholds populated, score/label `NULL`; needs-review + gate-fail -> ordinary `below_production_gate` |
| `TestMmcSeasonVaryingG` | `G=16` used for a 2019 row, `G=17` for a 2023 row, matching the exact recomputed constants in section 9 |
| `TestMmcRequiresCorroboration` | Classifier output alone, without MFL agreement, never produces `minimal_market_cost_scored` for a 2011+ row |
| `Test2010CohortFallback` | No override file entry -> `unscoreable_ambiguous`; override file entry -> `minimal_market_cost_scored` with `mmc_verified_2010_manual_override` provenance; classifier alone insufficient |
| `TestVick2010StaysDraftedMissing` | Regression-pins the specific documented decision so a future refactor can't silently flip it without a new PR discussion |
| `TestLabelScoreConsistency` | `score` is `NULL` with `label=0` **only** when `status == below_production_gate`; `label=1` implies `score >= threshold`; `label=0` scoreable implies `score < threshold` |
| `TestSevenStatusesExhaustiveAndExclusive` | Every row in a full pipeline run gets exactly one status, never zero, never two |
| `TestNoLeakageInExpectedProduction` | `E_P` fit for season `Y` is provably unaffected by perturbing any season `>= Y` in the input |
| `TestExpectedProductionLookupVersionCheck` | Stage 11 refuses to score against a lookup table whose `sbv_version` doesn't match the running `config.SBV_VERSION` |
| `TestNoSilentNullToZeroCoercion` | No pipeline step ever `.fillna(0)`s a `star_by_value_label` column |
| `TestNamedCaseRegression` | Herbert 2020 / Cruz 2011 / Nacua 2023 / Williams 2023 / Barnidge 2015 all resolve to `label=1`; a small set of known non-Stars resolve to `label=0` -- the face-validity findings from this investigation, pinned as regression tests, not just prose |
| `TestReplacementPpgMatchesSettled` | Equal-weighted full-history replacement PPG matches the exact section-9 constants |
| `TestThresholdsMatchSettled` | Section 10 values, exact |
| `TestMmcOverrideSchemaValidation` | The 2010 override loader rejects a row missing `source`/`evidence_summary`, rejects a row with both `adp_overall` and `minimal_market_cost_approved=TRUE` populated, and rejects any `season != 2010` |
| `TestCsvExportRoundTrip` | `pd.read_csv(export_path, dtype={"star_by_value_label": "Int8", ...})` reproduces the canonical Parquet file's values exactly |

---

## 11. Regeneration impact on existing outputs

- **LWI / Dataset 1 (`master_historical_db_with_lwi_2006_2025.csv`)**:
  unaffected. SBV is fully additive and writes to entirely separate
  artifacts (decision #1) -- reads the same upstream matched-player
  data but never modifies LWI's own computation or output file.
- **New canonical artifact**: `data/processed/stars_by_value_player_seasons.parquet`
  (decision #1), joinable back to the LWI file via `(season, player_id)`
  if and when a later, separately-approved stage does that join. Not
  merged into the master table in this first implementation.
- **Row count**: SBV's scope is *broader* than LWI's (down to
  `games_played >= 1`, not LWI's 8-game floor), so this artifact will
  have more rows than LWI's eligible population, most of them
  `out_of_scope`/`below_production_gate` outside the labeled core --
  matches how LWI already nulls-with-a-reason rather than filtering
  rows out entirely.
- **`research/output/dataset3/*.csv`**: remain historical research
  artifacts (gitignored, regenerable). Production code must not read
  from these paths at runtime -- every dependency promoted into `lib/stars_by_value/`
  must resolve to a real, committed/fetched input, not a scratch or
  research-output file.
- **`research/diagnostics/mfl_pipeline/`**: untouched. Explicitly
  marked isolated for the 2025 investigation; the new production MFL
  client is a separate module, not a repurposing of that one.
- **`data/processed/sbv_expected_production_lookup.parquet`**: new,
  regenerated by stage 09 per the invalidation rules in section 9 --
  not touched by stages 08, 10, or a normal stage 11 run.

---

## 12. Documentation changes and commit sequence

**Documentation**:
- `config.py`: new `SBV_*` block + `validate_sbv_config()`, with the
  same inline-rationale-comment convention already used for `LWI_*`.
- Recommend (not doing yet): once implementation begins in earnest,
  promote `STARS_BY_VALUE_METHODOLOGY.md` to `docs/STARS_BY_VALUE_SPECIFICATION.md`,
  mirroring how `METRIC_SPECIFICATION.md` is LWI's authoritative spec
  location -- code should implement a `docs/` spec, per this project's
  own stated convention, not a `research/` working document.
- One final `ADP_SOURCE_MATRIX.md` decision-history entry noting
  implementation planning is complete and referencing this plan file.

**Smallest sensible commit sequence** (each independently reviewable,
each leaves the repo in a working state):

0. **Documentation-only checkpoint** -- the approved methodology,
   this plan, `ADP_SOURCE_MATRIX.md` changes, and the verified Vick
   name overrides. No code. See the standalone proposal below; this
   is commit zero, before any of the numbered code commits start.
1. `config.py` `SBV_*` constants + `validate_sbv_config()` + config
   test -- pure addition, no behavior change anywhere else.
2. **Landed.** `nflverse_source.py` extensions (`players` and `depth_charts`
   fetches only -- `stats_player` reuses the existing `fetch_and_normalize()`
   as-is, confirmed already present, see section 3) + tests --
   infrastructure only, nothing consumes it yet. Surfaced a real,
   previously-unknown schema break in `depth_charts_2025.csv` (see
   section 3) that Commit 7 (`acquisition_cost.py`) will need to
   address.
3. **Landed.** New MFL client (`scripts/mfl_client.py`, placed
   alongside `nflverse_source.py` rather than `lib/stars_by_value/` as
   originally sketched -- see section 4) + tests -- infrastructure
   only, fetch-only by design (no name matching/corroboration logic,
   deferred to Commit 7's `acquisition_cost.py`). No fetch script yet
   (`scripts/08_fetch_sbv_reference_data.py` is still Commit 10's
   wiring step). Surfaced a real finding that shaped the design: MFL's
   `TYPE=adp` report is a live, continuously-growing aggregate, not a
   frozen artifact -- see section 3 -- so its integrity model and
   manifest-commit treatment deliberately differ from
   `nflverse_source.py`'s.
4. `data/manual/mmc_2010_manual_overrides.csv` (empty, headers only) +
   the loader/validator (section 8a) + schema tests -- infrastructure,
   nothing produces a row yet.
5. `lib/stars_by_value/production.py` (promoted AATP/shrinkage/composite)
   + tests that reproduce the already-verified research numbers
   exactly, as a regression pin.
6. `lib/stars_by_value/expected_production.py` + `scripts/09_fit_sbv_expected_production.py`
   (materialized lookup table, section 9) + leakage tests + version-check
   test.
7. `lib/stars_by_value/acquisition_cost.py` (classifier + corroboration
   + 2010 fallback -- the real new-code effort) + tests against the 6
   ground-truth cases.
8. `lib/stars_by_value/minimal_market_cost.py` + season-varying-`G`
   tests.
9. `lib/stars_by_value/labeling.py` (status routing) + the full
   invariant test suite from #10.
10. Wire `scripts/08`/`09`/`10`/`11` together, end-to-end integration
    test producing `stars_by_value_player_seasons.parquet` and the CSV
    convenience export + round-trip test.
11. Documentation: spec promotion, `ADP_SOURCE_MATRIX.md` closing
    entry.

---

## What already exists vs. what must be built

- **Promotable with light rework**: `production.py` logic (AATP,
  shrinkage, composite), `replacement.py`, `expected_production_by_round_investigation.py`'s
  fitting logic, `player_matching.py` and `nflverse_source.py` (reused
  outright).
- **Built (Commits 2-3, landed)**: `nflverse_source.py`'s `players`/`depth_charts`
  extensions, `scripts/mfl_client.py`.
- **Must still be written from scratch**: the classifier, the
  depth-chart correction, the 3-way MFL corroboration, the 2010-cohort
  fallback, the status-routing/labeling module. None of this exists as
  saved code today -- all of it ran once, in this conversation,
  against scratch-space files.

## Research-only assumptions that must not silently enter production

- The classifier's "3 prior seasons, games>=4 & points>=80" lookback
  threshold was a hand-chosen heuristic during calibration, never
  itself swept the way lambda or k were -- must be a named, visible
  config constant, not an inline magic number.
- The `SBV_MMC_USAGE_DEFINITION` thresholds are explicitly documented
  as "a convention, not a uniquely correct cutoff" -- same requirement.
- The rookie-QB depth-chart correction is deliberately narrow (QB
  rookies only, Week-1-starter check only) -- must not be silently
  generalized to other positions without new evidence and a new
  approval, exactly as the methodology states.
- `SBV_MMC_OPPORTUNITY_PROBABILITY` and the equal-weighted replacement
  PPG constants are **frozen** calibration outputs -- production code
  must never silently recompute them from a live re-fetch of
  `stats_player`/MFL data on a normal run. Re-fetching feeds new
  seasons' *classification*, not a rolling recalibration of already-settled
  constants.
- Every "cached to scratch space" input referenced anywhere in the
  methodology doc (`/private/tmp/...`) is not a valid production
  source -- each one needs a real fetch path (#5) before any promoted
  module can depend on it.

## Decisions now settled (previously open ambiguity)

| # | Decision | Resolution |
|---|---|---|
| 1 | Output artifact location | Separate canonical Parquet (`data/processed/stars_by_value_player_seasons.parquet`), not merged into the LWI master table. A later, separately-approved stage may join selected columns in. |
| 2 | `E_P` caching | Materialized, versioned lookup table (`data/processed/sbv_expected_production_lookup.parquet`), fit once per build by stage 09, consumed (never refit) by stage 11. Regenerated on `SBV_VERSION`/fitting-config/upstream-data change; version-checked, not silently trusted. |
| 3 | 2010 override schema | Dedicated `data/manual/mmc_2010_manual_overrides.csv`, full field list and validation rules in section 8a. Starts empty; classifier output alone can never populate it. |
| 4 | Reference-data fetching | Stage 08 is an explicit, manually-triggered refresh (`--refresh`). Stages 09-11 read only pinned local files, never call MFL/nflverse live on a normal run. |
| 5 | Nullable `Int8` typing | Parquet is canonical (preserves nullable `Int8` exactly). CSV is a generated convenience export with a mandatory round-trip test and an accompanying schema/data-dictionary file -- never treated as authoritative for dtype. |

**No open implementation ambiguity remains.** Every item on the prior
list has a concrete artifact path, schema, and regeneration rule
attached, not just a stated preference -- and none of the five
resolutions required reopening any settled methodology section.
