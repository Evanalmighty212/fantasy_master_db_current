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

## 2a. 2025 integration is a blocking prerequisite, not future work

**Revision (2026-07, supersedes this section's original framing):** an
earlier draft of this plan proposed capping the first canonical build
at 2010-2024 and treating 2025 as optional, deferred future work. That
framing is rejected. **2025 is the most important completed season in
the dataset and its exclusion is not acceptable as a final production
boundary.** The final orchestration/output commit (formerly "Commit
10") does not land until 2025 is genuinely integrated -- real ADP
match, real acquisition-cost resolution, real score/label, not a
placeholder.

Two real blockers remain open, confirmed directly against the repo
(2026-07):

- **Zero canonical ADP coverage.** All 608 real 2025 player-season
  rows in the master DB carry `data_quality_flag = no_adp_match` and
  `adp_source = NaN`. `docs/ADP_SEASON_SOURCE_PLAN.csv` confirms the
  normal canonical pipeline (FantasyPros primary, FFC secondary)
  genuinely attempted 2025 and returned empty. `docs/ADP_SOURCE_MATRIX.md`'s
  2026-07 entry confirms two real candidates (MFL AUG15, FFToday's
  modern consensus page) were investigated and neither was promoted --
  see Phase 1 below for exactly why, and what's left to try.
- **Unsupported depth-chart schema.** `depth_charts_2025.csv` uses a
  different, undocumented-until-now schema (`dt`/`team`/`player_name`/
  `espn_id`/`gsis_id`/`pos_grp`/`pos_abb`/`pos_slot`/`pos_rank`) from
  the consistent 2006-2024 schema (`season`/`club_code`/`week`/
  `position`/`depth_team`/`gsis_id`); `acquisition_cost.py::apply_rookie_qb_depth_chart_correction()`
  raises `RuntimeError` for season 2025 by design (Commit 7) until this
  is mapped -- see Phase 2 below.

Both are open sourcing/schema problems, not gaps in already-built SBV
logic -- every formula and rule 2025 needs already exists as tested
code (Commits 5-9). Resolving them is real work (source selection has
a genuine, not-yet-obvious answer; the schema mapping is new code), but
neither reopens the *settled* production/E_P/MMC/labeling formulas
themselves -- see "Does any methodology decision need to reopen?"
below for the one narrow exception.

**Three-phase plan** (replaces the single "Commit 10" wiring step):

- **Phase 1** -- resolve canonical 2025 ADP: compare already-documented
  candidates, decide (or run a new experiment), then build and audit
  the real 2025 ADP match.
- **Phase 2** -- support the 2025 depth-chart schema: map the new
  columns to what `apply_rookie_qb_depth_chart_correction()` needs,
  narrowly (rookie-QB Week-1-starter check only, matching the existing
  2006-2024 scope -- not a general depth-chart schema migration).
- **Phase 3** -- rebuild: regenerate the ADP-matched population, the
  `E_P` lookup, and run the full labeling pipeline through 2025, once
  Phases 1-2 both land.

**Interim scaffolding, explicitly temporary.** While Phases 1-2 are in
progress, a season filter may still be used to keep 2025 out of any
build run early -- e.g. an interim `SBV_CANONICAL_BUILD_LAST_SEASON = 2024`
config constant, with a build-time exclusion report (row count, season,
reason) rather than a silent drop, exactly as previously specified.
**This is scaffolding for the transition, not a design decision to
preserve** -- the constant (or whatever mechanism replaces it) is
removed, not merely bumped, once Phase 3 lands; 2010-2025 becomes the
canonical range with no season-exclusion logic left over to maintain.
Kept as a single config constant + filter (not a general per-season
exclusion registry) for the same reason as before: exactly one season
is affected, for two known, already-being-resolved reasons -- a general
mechanism would be speculative generality for a problem that's actively
being closed out, not maintained indefinitely.

### Does any methodology decision need to reopen?

**No change to any settled formula** (production composite, `E_P`
fitting mechanics, MMC formula, the four-step routing order, the seven
statuses) is required by 2025 integration -- Commits 5-9 apply to 2025
rows exactly as written, once real inputs exist. **One narrow exception,
contingent entirely on which ADP source Phase 1 selects:**

- If the selected source produces ADP in the same units as every other
  season (a real mean-pick number, like FFC's historical `adp` field or
  MFL's raw mean pick), `adp_round()` (section 7's existing round
  derivation) applies unchanged -- no methodology reopening.
- If the selected source instead produces derived integer ranks (like
  FFToday's modern consensus page -- see Phase 1), using it as if it
  were mean-pick ADP would silently redefine what "round" means for
  2025 relative to every other season. That *would* require a real,
  reviewed methodology addition (a documented rank-to-round mapping, or
  an explicit decision that this source's shape disqualifies it) before
  any code consumes it -- not a decision to make inside implementation
  code.
- Separately, if the selected source needs a bias correction (see
  MFL's real, corroborated QB/TE early bias in Phase 1) rather than
  being used raw, the correction itself is new, undocumented
  methodology -- it does not exist today in any settled section -- and
  needs the same explicit review any other formula in this project
  gets, not a quiet implementation-time judgment call.

**A separate, real architectural question this plan cannot resolve
unilaterally:** `data_quality_flag`/`adp_source` are computed once, in
`scripts/04_build_master_dataset.py`, and consumed by *both*
`05_calculate_metrics.py` (LWI / Dataset 1's own eligibility gate) and
SBV's stage 09. If a 2025 ADP source is written into those same master-DB
columns, it becomes eligible for LWI/Dataset 1 too, not just SBV --
today, LWI already excludes essentially all of 2025 via the same gate
(608/608 `no_adp_match`), so promoting a 2025 source changes that
exclusion for both datasets at once, not SBV alone. This plan does not
assume either scope is correct -- see the standalone question raised
alongside this plan.

---

## 3. Existing code to reuse or modify

| Existing artifact | Disposition |
|---|---|
| `scripts/player_matching.py` | **Reuse as-is.** Already production-quality (override table, confidence tiers, `matched_clean`/`matched_needs_review`/`no_adp_match` classification). SBV consumes its output; does not modify it. |
| `scripts/nflverse_source.py` | **Reused as-is for usage stats; extended for `players` and `depth_charts` (Commit 2, landed).** Verified directly against the repo (not assumed from scratch research): this module already fetches the `stats_player` release at week grain (`stats_player_week_<season>.csv`, asset-ID pinned, sha256-verified, manifest covers 2006-2025 in full), and the already-cached local files already contain `attempts`/`carries`/`targets`/`receptions` -- exactly what the MMC usage-definition calibration needs. **No new fetch or asset pinning for usage stats** -- `acquisition_cost.py` calls the existing `fetch_and_normalize()` and sums the relevant columns per player/season itself. `players` (draft capital, single file, no season grain) and `depth_charts` (rookie-QB correction, season grain) were genuinely new -- confirmed no existing fetch mechanism for either -- and are now fetched via `fetch_players()`/`fetch_depth_chart(season)`, same asset-ID-pinning + sha256 verification + explicit-registration-only model as `stats_player`, registered for `players.csv` (single entry) and `depth_charts` seasons 2006-2025 (matching `config.SEASONS`). **Real finding from registering all 20 seasons: nflverse's `depth_charts_2025.csv` uses a completely different 12-column schema** (`dt`/`team`/`espn_id`/`pos_grp`/`pos_slot`/`pos_rank`, ~15x the row count of any other season -- apparently a different upstream vendor as of this migration) than the consistent 15-column schema verified identical across every one of 2006-2024. The 2025 file is still registered and fetchable (fetching is schema-agnostic by design), but no consumer code normalizes or interprets it yet -- `acquisition_cost.py` (Commit 7) will need to either handle both shapes or explicitly exclude 2025 until decided; not resolved by this commit. |
| `research/dataset3/production_weight_and_boundary_calibration.py::build_adp_aware_aatp()` | **Promote, with rewrites.** Correct logic, wrong location/config-coupling -- currently hardcodes `WINDOW=12`, `MIN_PRIOR_SEASONS=3`, the roster preset dict, etc. inline. Must be rewritten to read from the new `SBV_*` config constants instead of local hardcoded values before it's production code. |
| `research/dataset3/lib/replacement.py` | **Promoted verbatim (Commit 5, landed) to `lib/replacement.py`.** Logic unchanged -- only relocated, folded into Commit 5 as production.py's direct dependency rather than given its own commit, since production.py cannot function without it and cannot import from `research/`. |
| `research/dataset3/expected_production_by_round_investigation.py` | **Promote the fitting logic, not the script.** `adp_round()` helper and the expanding-window/QB_RB-offset/recency-weighting fit logic are correct and settled -- extract into a real module; the surrounding research script (comparison harnesses, print statements, CSV dumps for calibration) does not belong in production. |
| The rookie-QB depth-chart correction, the classifier, the 3-way corroboration | **Do not exist as saved code at all.** Every one of these was built and run as ad hoc Python in this conversation, writing to scratch space (`/private/tmp/.../scratchpad`), never committed anywhere. This is the single biggest gap between "settled methodology" and "implementable" -- see #4 and #9. |
| The MFL client | **Built (Commit 3, landed) at `scripts/mfl_client.py`, not `lib/stars_by_value/mfl_client.py` as originally sketched in section 4 below.** Deliberate placement correction, mirroring `nflverse_source.py`'s precedent: this module is pure fetch/cache/rate-limit infrastructure with no SBV business logic, same role as `nflverse_source.py`, so it lives alongside it in `scripts/` -- `lib/stars_by_value/` stays reserved for modules that actually apply SBV methodology (`production.py`, `expected_production.py`, `acquisition_cost.py`, `minimal_market_cost.py`, `labeling.py`). Fetches `TYPE=adp&PERIOD=AUG15` and `TYPE=players`, cache-first with an explicit `force_refresh`. **Real finding that shaped its design**: MFL's `TYPE=adp` report is a live, continuously-growing aggregate, not a frozen artifact -- confirmed directly, querying season 2023 live returned `totalDrafts=9,970` and Puka Nacua at rank 213/16%, versus `totalDrafts=7,923` and rank 209/18% recorded earlier in `docs/ADP_SOURCE_MATRIX.md` from a prior-date query. **Integrity model (revised once before landing, see below)**: a cache hit (hash matches) returns silently, no network call; a missing local file is fetched (bootstrap, not a replacement); a cache PRESENT but hash-MISMATCHED against the manifest raises loudly with no network call, naming `force_refresh=True` as the explicit way to accept new data -- normal (non-refresh) runs must never make an unexpected network request just because a local snapshot looks stale or was edited. `force_refresh=True` always fetches fresh and prints old-vs-new values when a snapshot is replaced. **`scripts/mfl_source_manifest.json` IS committed to git** (unlike the raw per-response JSON under `data/raw/mfl/`, which stays gitignored) -- a compact snapshot registry per season/endpoint (URL/params including `PERIOD=AUG15`, `retrieved_at`, `sha256`, `total_drafts`, `row_count`, `sbv_version`), with an explicit `note` field in the JSON itself clarifying that it documents the exact snapshot used but cannot, by itself, reproduce MFL's live report byte-for-byte -- a future immutable archive of the raw responses may be needed for full reproducibility. Rate-limiting constants live in `config.py`'s `SBV_*` block (`SBV_MFL_MIN_REQUEST_DELAY_SECONDS`, `SBV_MFL_MAX_RETRIES`, `SBV_MFL_BACKOFF_BASE_SECONDS`, `SBV_MFL_REQUEST_TIMEOUT_SECONDS`) as implementation metadata, not hardcoded in the client -- operational tunables, not methodology, per explicit direction. |

---

## 4. New modules required

```
lib/stars_by_value/
    __init__.py              # built (Commit 4, landed) -- first module in this package
    mmc_2010_overrides.py    # built (Commit 4, landed) -- section 8a loader/validator,
                             #      not named explicitly here at the time this section was
                             #      first written. Fetch/parse-only, no classifier logic.
    production.py           # built (Commit 5, landed) -- AATP/shrinkage/composite, promoted
                             #      from build_adp_aware_aatp() + ppg_eq_normalized_shrink()
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

**Season-coverage metadata, interim only (see section 2a).** While
Phases 1-2 are in progress, any build produced still records the
season range it actually covers -- a build-level metadata field
stamped alongside `sbv_version` (preferred) or, at minimum, an explicit
note in `stars_by_value_player_seasons_SCHEMA.md`: "prediction seasons
2010-2024; 2025 temporarily excluded pending 2025 ADP/depth-chart
integration, see `STARS_BY_VALUE_IMPLEMENTATION_PLAN.md` section 2a/13."
Prevents a future reader from mistaking an interim artifact's lack of
2025 rows for "2025 doesn't exist in the master DB yet." **The final
canonical artifact this project ships covers 2010-2025** -- this
metadata note describes an interim state, not the target.

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

**2025-specific reporting requirement, interim only (see section 2a).**
Until Phase 1 lands, if the upstream population passed to stage 09
contains any season-2025 rows, stage 09 must explicitly log/report
that 2025 contributed zero rows to any `prediction_season` fit, rather
than 2025 simply never appearing in the output lookup table with no
comment -- distinguishes "2025 was present in the input and
contributed nothing" from "2025 wasn't in the input at all." This
requirement, and the condition that triggers it, goes away once Phase
1 lands and 2025 has real `adp_matched` rows to fit from -- it is not
a permanent feature of stage 09.

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
4. **Landed** (revised once after review before landing -- see below).
   `data/manual/mmc_2010_manual_overrides.csv` (empty, headers only,
   generated by the loader itself so the header row can never drift
   out of sync with the code -- **14 columns**, matching section 8a's
   table exactly: `season`, `player_id`, `player_name`,
   `override_type`, `market_cost_status`, `adp_overall`, `adp_round`,
   `minimal_market_cost_approved`, `source`, `source_date`,
   `evidence_summary`, `confidence`, `approved_by`, `notes` -- an
   earlier chat summary of this commit miscounted it as 13, though no
   tracked file ever actually had that error; the count is now a
   permanent test invariant, not something to recount by hand) + the
   loader/validator (section 8a) at
   `lib/stars_by_value/mmc_2010_overrides.py` -- the first module in
   that package, not named explicitly in section 4 below at the time
   it was written -- + schema tests. Infrastructure only, nothing
   produces a row yet.
   **Two design corrections made after initial review, before this
   commit landed:**
   - The `season` rule is enforced against a NEW, dedicated
     `config.SBV_MMC_MANUAL_OVERRIDE_SEASONS = (2010,)` constant, not
     `SBV_FIRST_SCOREABLE_SEASON`. The two encode different concepts
     that only coincide in value today (temporal/study-scope
     eligibility vs. which cohort(s) need this override fallback at
     all) -- an earlier version of the loader conflated them, which
     would have made extending the study's start season and extending
     this override mechanism look like the same decision.
   - The "no override from classifier output alone" rule (rule #2) is
     mechanized via a new `SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES`
     config constant, checked as an EXACT match (after lowercase/
     whitespace/underscore normalization) against `source` -- NOT the
     case-insensitive substring/phrase match originally built. The
     substring version was rejected after review as overinclusive (a
     genuine independent source legitimately containing ordinary
     phrasing like "the team's own rookie status announcement" would
     have been rejected) and trivially evadable by rephrasing. The
     loader's own docstring documents this decision and its rationale;
     a regression test proves an ordinary sentence containing a
     reserved phrase is no longer rejected.
   Both corrections keep the loader deliberately independent of any
   classifier/scoring code -- verified by a test that greps its own
   imports.
5. **Landed.** `lib/stars_by_value/production.py` (promoted AATP/
   shrinkage/composite from two research sources -- `build_adp_aware_aatp()`
   in `production_weight_and_boundary_calibration.py` for AATP/PPG_AR/
   PPG_AR_eq, `ppg_eq_normalized_shrink()` in
   `normalized_shrinkage_comparison.py` for the k=5 shrinkage step --
   plus `lib/replacement.py`, promoted verbatim from
   `research/dataset3/lib/replacement.py` as production.py's direct
   dependency, folded into this commit since production.py cannot
   function without it and cannot import from `research/`). Tests
   compare against the real research implementation's output on the
   real 9,615-row 2007-2024 population (run in an isolated subprocess
   to avoid a real `lib`-package-name collision between
   `research/dataset3/lib/` and this project's new top-level `lib/`,
   confirmed to occur regardless of import order) -- exact match on
   every row, every computed column, not a spot-check on a few named
   examples. Population scoping (season range, `games_played >= 1`,
   position membership) was deliberately NOT carried into
   `production.py` -- see its module docstring -- so the module
   validates structural preconditions and raises loudly on violation
   rather than silently filtering; population scoping is upstream
   routing's job (not yet built).
6. **Landed.** `lib/stars_by_value/expected_production.py` + `scripts/09_fit_sbv_expected_production.py`
   (materialized lookup table, section 9) + leakage tests + version-check
   test. Oracle chain read in full (six chronological research
   scripts) -- see expected_production.py's own module docstring for
   which script supplies the round mapping, expanding-window
   mechanics, QB_RB offset selection, and the equal-vs-recency
   comparison. One synthesis had no single-script oracle: no research
   script runs a combined fit with QB recency-weighted while RB/WR/TE
   are simultaneously equal-weighted -- that combination is a direct
   reading of the final oracle script's own per-position MAE
   comparison, documented explicitly, not an independent invention.
   A real bug was caught by the oracle-parity test during this
   promotion (not left to silently ship): filtering to the ADP-matched
   population BEFORE calling `compute_aatp()` silently produces wrong
   replacement_ppg/AATP values, because `replacement_level_from_rank()`
   needs undrafted players present in the rank pool -- fixed by
   reordering `scripts/09` to compute AATP on the full population
   first, matching the oracle's own construction order exactly.
7. **Landed.** `lib/stars_by_value/acquisition_cost.py` (classifier +
   corroboration + 2010 fallback -- the real new-code effort, no
   research-script oracle) + tests against the 6 ground-truth cases.
   Prose settled record (docs/ADP_SOURCE_MATRIX.md "No-ADP remediation"
   parts 1-4) translated into an explicit routing table BEFORE
   implementation, reviewed and approved -- see acquisition_cost.py's
   own module docstring for the complete table and its two deliberate
   asymmetries (`ambiguous` + low MFL resolves to MMC exactly like
   `likely_undrafted`, since a non-committal classifier doesn't
   contradict a real low-prevalence signal; but classifier-alone can
   resolve `likely_drafted_missing_evidence` -> drafted-missing when
   MFL is merely unmatched, while it can NEVER resolve to MMC without
   real MFL corroboration -- a one-directional rule already settled
   before this commit). New `SBV_CLASSIFIER_*` and
   `SBV_MFL_MMC_CORROBORATION_THRESHOLD_PCT` config constants
   (threshold=20%, strict `<`) with `validate_sbv_config()` checks.
   Two real findings from this pass, not previously documented
   anywhere: (1) Kyren Williams 2023 and Gary Barnidge 2015 -- named
   regression cases with no prior classifier/MFL data on record --
   were queried live against the real MFL API and cross-checked
   against real nflverse draft capital; both are non-rookie-season
   players with no qualifying prior production (landing in
   `ambiguous`, not `likely_undrafted`), and Barnidge is a real
   "matched, zero selection" case (present in MFL's 2015 player
   directory, absent from the AUG15 ADP report entirely). (2) Mike
   Vick 2010's required `evidence_drafted_unresolved` outcome has no
   mechanical path from the classifier + the existing 2-type 2010
   override schema alone (the classifier itself lands him in
   `ambiguous`, matching the settled record's own admission that this
   miss was deliberately not patched) -- implemented as a narrow,
   explicitly named, individually tested historical exception
   (`VICK_2010_GSIS_ID`) rather than expanding the override schema
   for one case, per explicit direction. A `usable_adp` 2010 override
   does not produce an acquisition-cost status at all -- it returns
   the override's `adp_overall`/`adp_round` and the row exits to the
   normal ADP-scored path, confirmed as the intended contract.
8. **Landed.** `lib/stars_by_value/minimal_market_cost.py` + season-
   varying-`G` tests. Narrow single-formula module:
   `MMC_E_P(position, season) = opportunity_probability(position) *
   SBV_MMC_ROLE_CONDITIONAL_DISCOUNT * replacement_ppg(position) *
   season_length(season)` (reusing `production.py`'s `season_length()`
   rather than re-deriving the 16/17-game cutover a second time). The
   settled formula's "0.5" multiplier is `SBV_MMC_ROLE_CONDITIONAL_DISCOUNT`,
   a new, DEDICATED config constant -- a first draft of this module
   reused `SBV_PRODUCTION_WEIGHT_AATP` directly (the two happened to
   share the value 0.5), which was reviewed and rejected: they are
   different quantities (a role-conditional production discount vs.
   production.py's composite weight) that must be free to move
   independently if either is ever recalibrated, so coupling them
   -- even deliberately -- was a real risk not worth taking. Every
   other input was an already-settled `SBV_*` constant from Commit 1.
   Regression values verified against the exact settled constants
   (not the 1-decimal prose headlines in the methodology doc, which
   are rounded for readability): 16-game era QB/RB/WR/TE =
   29.14/21.72/33.63/18.17, 17-game era = 30.96/23.07/35.73/19.31.
9. **Landed.** `lib/stars_by_value/labeling.py` (status routing) + the
   full invariant test suite from #10. The wiring layer -- the first
   commit where Commits 5-8 are all exercised together. Implements the
   four-step order exactly (temporal/study-scope eligibility ->
   production gate, in-scope rows only -> acquisition-cost resolution,
   gate-clearing rows only -> score/label, the two scoreable statuses
   only), each step a hard early return, not a downstream filter --
   directly tested by mocking `acquisition_cost.classify_row()` to
   raise if called and confirming it's never invoked for out-of-scope
   or below-gate rows. The final composite `score = P - SBV_LAMBDA * E_P`
   (methodology section 6/10) is computed here for the first time --
   no earlier commit owned it, since it consumes both `production.py`'s
   `P` and either `expected_production.py`'s real lookup or
   `minimal_market_cost.py`'s substitute `E_P`, never duplicating
   either's formula. **One implementation-time interpretation, not a
   settled specification** -- confirmed by direct search, neither this
   plan nor `STARS_BY_VALUE_METHODOLOGY.md` ever specified a
   provenance value for a 2010 `usable_adp` override, only its status
   (`adp_scored`, already settled in section 8a). The 10-value
   provenance enum has no dedicated value for "adp_scored via a
   reviewed manual override" as distinct from a real canonical-source
   match, so `labeling.py` records `adp_matched_clean` -- the closest
   existing fit, not a derived rule. Documented explicitly, not left
   implicit, in `STARS_BY_VALUE_METHODOLOGY.md`'s 2010-cohort section
   (flagged for review if the override mechanism is ever actually
   used against a real row -- it has zero real rows today). Named-case
   regression tests reproduce the real settled scores from the
   methodology's reinforcement-check table exactly (Herbert 2020
   202.0, Cruz 2011 187.6, Nacua 2023 184.4, Kyren Williams 2023 232.6,
   Barnidge 2015 160.9, all label=1; Vick 2010 stays
   `unscoreable_drafted_adp_missing`, label=NULL, never label=0) --
   `P` values were solved backward from each real score, not invented.
   Does not write any output file (Parquet/CSV export is Commit 10's
   job, not this one).
10. **Revised (2026-07): no longer a single wiring commit.** 2025
    integration (section 13) is a blocking prerequisite, not deferred
    work -- replaced by Phase 1 (resolve + build + audit canonical 2025
    ADP), Phase 2 (2025 depth-chart schema mapping), and Phase 3
    (regenerate the ADP-matched population, the `E_P` lookup, and run
    the full pipeline through 2025) below. Each phase likely spans more
    than one commit on its own; exact boundaries proposed at the start
    of Phase 1, once the ADP-source decision is made -- see section 13
    for the full breakdown.
11. Wire `scripts/08`/`09`/`10`/`11` together, end-to-end integration
    test producing `stars_by_value_player_seasons.parquet` and the CSV
    convenience export + round-trip test, covering **2010-2025** -- no
    interim season-exclusion scaffolding left in the shipped pipeline.
12. Documentation: spec promotion, `ADP_SOURCE_MATRIX.md` closing
    entry (now also covering the 2025 ADP-source decision from Phase 1).

---

## What already exists vs. what must be built

- **Promotable with light rework**: `player_matching.py` and
  `nflverse_source.py` (reused outright).
- **Built (Commits 2-9, landed)**: `nflverse_source.py`'s `players`/`depth_charts`
  extensions, `scripts/mfl_client.py`, `lib/stars_by_value/mmc_2010_overrides.py`,
  `lib/stars_by_value/production.py`, `lib/replacement.py`,
  `lib/stars_by_value/expected_production.py`, `scripts/09_fit_sbv_expected_production.py`,
  `lib/stars_by_value/acquisition_cost.py` (classifier, rookie-QB
  depth-chart correction, 3-way MFL corroboration, 2010-cohort
  fallback), `lib/stars_by_value/minimal_market_cost.py`,
  `lib/stars_by_value/labeling.py` (the four-step wiring layer --
  every module above is now exercised together for the first time).
- **Must still be built**: end-to-end pipeline wiring
  (`scripts/08`/`10`/`11`, or equivalent) that assembles the real
  master-DB population, calls `labeling.label_rows()` across it, and
  writes the canonical Parquet/CSV outputs (decision #1/#5) -- deferred
  from Commit 9 by explicit instruction; `labeling.py` itself computes
  labels but writes no file. This is now purely orchestration, not new
  methodology or classification logic -- every formula and rule it
  will call already exists as tested code. **Revised (2026-07): this
  orchestration does not land until 2025 is genuinely integrated** --
  section 2a/13's three-phase plan (resolve canonical 2025 ADP, support
  the 2025 depth-chart schema, rebuild through 2025) is a blocking
  prerequisite, not deferred future work; a real, present-today
  condition (608/608 real 2025 rows are `no_adp_match`) makes this a
  live problem, not a hypothetical one. An interim season filter may be
  used only as temporary scaffolding while that work is underway, never
  as the shipped final boundary.

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

---

## 13. 2025 integration work plan (blocking prerequisite -- replaces the former "Commit 10")

Each phase below is marked at the item level: **[SOURCE-SELECTION
DECISION]** items are Evan's call, not something to resolve inside
implementation code; **[IMPLEMENTATION WORK]** items are mechanical
once a decision is made, in the same sense every other SBV module has
been ("every formula and rule already exists as tested code" applies
equally here once the two open questions below are answered).

### Phase 1 -- Resolve canonical 2025 ADP

**What's already documented** (2026-07 investigation,
`docs/ADP_SOURCE_MATRIX.md`, re-verified directly against the repo for
this revision, not assumed from memory):

| Candidate | Format | Scale-compatible with historical FFC `adp` field? | Position bias | Coverage | Existing tooling |
|---|---|---|---|---|---|
| **MFL AUG15** (per-league reconstruction, `research/diagnostics/mfl_pipeline/`) | Real mean-pick ADP (average pick across real drafts) | **Yes** -- same unit as every other season | **QB and TE priced ~20-28 ranks earlier than a 3-source consensus** (Sleeper/RTSports/ESPN), corroborated across 4 independent comparisons; RB/WR agree closely (~7 rank median diff, normal cross-source noise). Josh Allen: MFL puts him at ADP 6.3; every other source checked says 19-25. | 228 skill-position players overlapping FFToday's consensus (35 QB/72 RB/85 WR/36 TE) | `scripts/mfl_client.py` (production, Commit 3) fetches raw `TYPE=adp`; the *per-league reconstruction* needed to avoid superflex contamination lives only in `research/diagnostics/mfl_pipeline/` (research-only, 254 valid leagues already classified) |
| **FFToday modern page** (`25_adp_ppr.html`, Sleeper/RTSports/ESPN blend) | **Derived integer ranks (1-283)**, not fractional mean-pick ADP -- FFToday computes an `Avg` column from three platforms' own ranks | **No** -- treating a rank as mean-pick ADP would silently redefine what "round" means for 2025 only (see "Does any methodology decision need to reopen?" above) | Own embedded ESPN column cross-validates well against this project's independent ESPN benchmark (r=0.973, n=37) -- the blend itself looks internally credible, just not scale-compatible | Best in the entire project: 238 skill-position players (best of any source, any year -- FFC's own best year, 2010, was 187) | `research/diagnostics/adp_2025_investigation/compare_mfl_fftoday.py` already parses and compares it; no production parser exists (`scripts/parse_fftoday_adp.py` only handles the old 2007-2009 single-source archive template, a structurally different page) |
| **Direct Sleeper / RTSports acquisition** (bypassing FFToday's blend) | Unknown until fetched -- each platform's own native export, not a derived rank | Unknown -- would need to be checked, but at least removes one layer of undisclosed blending | Unknown -- not yet isolated from the blend | Unknown | **Not attempted.** Flagged in `docs/ADP_SOURCE_MATRIX.md`'s own "Next experiment" note as the most promising unexplored option -- never built |

**[SOURCE-SELECTION DECISION] Which source or blend is defensible as
canonical for 2025?** Neither already-investigated candidate clears
this project's own existing bar on its own:

- FFToday's blend has the exact opacity problem this project already
  used to *reject* FantasyPros as a source elsewhere in
  `ADP_SOURCE_MATRIX.md` (an undisclosed multi-platform blend, not an
  independent primary source) -- promoting it for 2025 while holding
  FantasyPros to that same standard would be an unexplained double
  standard, not a new precedent. Its rank-vs-mean-pick incompatibility
  is a second, independent disqualifier.
- MFL is scale-compatible and has real per-league provenance, but its
  QB/TE bias is now corroborated by four independent comparisons, not
  a fluke of one benchmark -- using it raw for those two positions
  would bias `E_P` fitting and, more specifically, misclassify exactly
  the rookie-QB cases the depth-chart correction exists to protect.

**Recommendation** (Evan's call to confirm, not decided here): attempt
direct Sleeper/RTSports acquisition first -- it is the one candidate
that hasn't already been evaluated against this project's standards
and found short, and `docs/ADP_SOURCE_MATRIX.md` already names it as
the concrete next step. If that proves infeasible (a real network
fetch, so subject to this project's existing GitHub Actions constraint
for external ADP/stats sources -- see the repo-conventions note in
`CLAUDE.md`) or also fails on inspection, the fallback is MFL AUG15
**with an explicit, reviewed QB/TE bias-correction methodology** -- not
MFL used raw, and not FFToday's blend, given the reasoning above.

**[SOURCE-SELECTION DECISION] Compatibility with the historical
FFC-based ADP scale.** Already answered per-candidate in the table
above; whichever source is chosen, the round-derivation question in
"Does any methodology decision need to reopen?" (section 2a) is decided
by this same choice, not separately.

**[SOURCE-SELECTION DECISION] Position-specific biases, especially
MFL's QB behavior.** Documented above (QB -28.2 / TE -23.0 median rank
vs. consensus, RB/WR ~-7 both). If MFL is the fallback choice, the
correction mechanism itself (how exactly QB/TE get adjusted) is a new
methodology decision, not an engineering detail -- flagged already in
section 2a.

**[SOURCE-SELECTION DECISION] Source provenance and confidence rules;
whether 2025 needs a distinct source label.** Yes -- confirmed by
directly checking `scripts/04_build_master_dataset.py`: `adp_source`
is a real, already-populated column (FFC/FFToday-2007-09/FantasyPros
per season today), so 2025 gets its own new value in that same column
(e.g. `mfl_aug15_qb_te_corrected` or `sleeper_rtsports_direct`,
depending on the choice above) rather than being folded into an
existing FFC-labeled row -- consistent with how every other
non-FFC-sourced season in this project is already labeled, not a new
precedent.

**[IMPLEMENTATION WORK] Build and audit the 2025 ADP matching result**,
once the source decision above is made:

1. Fetch/parse the chosen source into the same shape
   `player_matching.py` already expects (mirrors how FFToday's
   2007-2009 promotion worked -- `scripts/parse_fftoday_adp.py` is the
   existing precedent for "new source, same downstream contract").
2. Run the existing `player_matching.py` pipeline unchanged -- reuse,
   not modify, exactly as every other season does.
3. Report the resulting `matched_clean` / `matched_needs_review` /
   `no_adp_match` counts for 2025, same as any season's remediation
   report (`docs/ADP_SOURCE_MATRIX.md`'s "No-ADP remediation" sections
   are the precedent for this reporting format).
4. Name and resolve (or explicitly leave unresolved with a documented
   reason) any high-impact unmatched 2025 cases, same process as the
   2010-2024 remediation work already completed (Commits leading up to
   this one).
5. Sanity-check the resulting round distribution against adjacent
   seasons (2023, 2024) -- confirms the new source doesn't silently
   shift what "round 1" or "round 15" means for 2025 relative to the
   rest of the fitted history.

### Phase 2 -- Support the 2025 depth-chart schema

**[IMPLEMENTATION WORK] Column mapping**, verified directly against
the real 2025 file (not assumed):

| 2006-2024 concept | 2006-2024 column | 2025 equivalent | Notes |
|---|---|---|---|
| Player identifier | `gsis_id` | `gsis_id` | Same column name, same join key -- no remapping needed |
| Position | `position` | `pos_abb` (filter to `pos_abb == "QB"` for this narrow correction) | 2025's schema groups offense under `pos_grp == "3WR 1TE"` with `pos_abb` giving the specific position (`QB`/`RB`/`WR`/`TE`/etc., confirmed by direct inspection) |
| Starter/rank status | `depth_team` (`== 1` means starter) | `pos_rank` (`== 1` means starter, confirmed: e.g. Mahomes `pos_rank=1`, Oladokun `pos_rank=2`, Haener `pos_rank=3` for KC) | Same ordinal semantics, different column name. `pos_slot` is a template slot index, not a depth ordinal -- do not use it for starter determination |
| Week 1 snapshot | `week == 1`, `game_type == "REG"` (an explicit week label) | **No week label exists** -- 2025's file is a rolling daily snapshot feed (`dt`, 221 distinct dates, confirmed range 2025-08-03 through 2026-03-14, i.e. it keeps updating past the season itself) | The nearest working equivalent is picking the `dt` closest to (but not after) the real 2025 Week 1 kickoff date, mirroring the "AUG15"-style pre-kickoff convention this pipeline already uses for MFL (`SBV_MFL_PERIOD`) -- **this exact date choice is itself a small, explicit decision to confirm**, not assumed here: closest snapshot to kickoff vs. closest snapshot to the actual first regular-season Sunday are not necessarily the same `dt` |

**[IMPLEMENTATION WORK] Scope, unchanged from the existing
2006-2024 correction:** rookie QBs only, Week-1-starter check only --
per the methodology's own existing narrowness requirement (already
stated in "Research-only assumptions that must not silently enter
production," above) this is not an opportunity to generalize the
correction to other positions or other weeks; only the input-schema
translation changes.

**[IMPLEMENTATION WORK] Testing.** Every real 2025 rookie QB (drawn
from the `players` reference data already fetched in Commit 2, filtered
to `rookie_season == 2025` and `position == "QB"`) must be checked
against the mapped 2025 depth-chart logic and produce a result directly
comparable in shape (not necessarily identical value, since the
underlying data source differs) to how a 2024 rookie QB is resolved
today -- reusing `TestNamedCaseRegression`'s existing pattern (Commit 9)
as the template for a new, 2025-specific regression class.

### Phase 3 -- Rebuild with 2025 included

**[IMPLEMENTATION WORK]**, strictly after both phases above land:

1. Regenerate the master ADP-matched population (`scripts/04`) with
   2025's new source wired in.
2. Regenerate `data/processed/sbv_expected_production_lookup.parquet`
   (stage 09) -- 2025 becomes a real `prediction_season` for the first
   time, fit under the same expanding-window/QB_RB-offset/recency rules
   as every other season, no special-casing.
3. Run the full four-step labeling pipeline (stages 10-11) through
   2025 -- acquisition-cost resolution and MFL/FFToday corroboration
   now apply to genuine 2025 `no_adp_match` rows, not a structurally
   empty set.
4. Produce the canonical Parquet/CSV outputs covering **2010-2025**,
   with the interim exclusion scaffolding (section 2a) fully removed,
   not merely widened.
5. `TestNamedCaseRegression`-style spot checks against a small number
   of real, well-known 2025 players (mirroring how Herbert 2020 / Cruz
   2011 / Nacua 2023 anchor the 2010-2024 named-case tests) before this
   is considered done.

Each phase is independently reviewable and, per the existing
one-logical-change-per-commit convention, will likely span more than
one commit -- exact commit boundaries proposed at the start of Phase 1
once the source decision is made, not fixed in advance here.

---

## Phase 3 status (2026-07): scaffold built, canonical output NOT yet produced

Phase 3's numbered steps above are landed as a **runnable
orchestration scaffold**, not a completed canonical build. Real, real-
data-driven work done so far:

- `scripts/2025_adp_integration.py` -- wires the approved raw MFL
  AUG15 source into `adp_clean_2006_2025.csv` (step 1). Includes one
  narrow, individually-documented exclusion (Amari Cooper -> spurious
  "Darius Cooper" fuzzy match, see `docs/ADP_SOURCE_MATRIX.md`'s
  Commit D audit entry) -- same precedent as the Vick 2010 exception,
  not a generalized rejection mechanism.
- `scripts/04_build_master_dataset.py`, `scripts/09_fit_sbv_expected_production.py`,
  `scripts/05_calculate_metrics.py` -- run unmodified, real data,
  confirmed 2025 now flows through correctly (346 `matched_clean`, 0
  `matched_needs_review`, real E_P fitted for `prediction_season=2025`,
  real LWI eligibility computed). Historical (2006-2024) rows
  unaffected -- confirmed both by regression tests and a direct row-
  count match before/after.
- `scripts/11_calculate_stars_by_value.py` -- the orchestration piece
  flagged "must still be built" since Commit 9, now real and running,
  with an explicit **build-completeness contract**:
  - `--mode diagnostic` (default): may complete with rows deferred,
    writes to `SBV_DIAGNOSTIC_OUTPUT_PARQUET_PATH`/`_CSV_PATH` (never
    the canonical paths) plus a deferred-rows report.
  - `--mode canonical`: `check_build_completeness()` refuses to run at
    all -- raises, naming every reason and count -- if ANY row would
    be deferred. Confirmed against real data: canonical mode currently
    refuses (5,011 rows deferred), exactly as designed.
- Fixed two real bugs found while building this, both before treating
  any result as trustworthy: (1) `acquisition_cost.classify_row()`
  never threaded `team`/`schedule_df` through to the 2025 depth-chart
  correction -- fixed, regression-tested
  (`TestTeamScheduleDfPassthrough`). (2) The orchestration script's
  first draft built `history_df` from the current run's `processable`
  subset instead of the full population, silently narrowing
  `classify_draft_status()`'s prior-season lookback whenever a prior
  season's row happened to be deferred -- caught by an unexplained
  status-count shift between two runs, fixed, regression-tested
  (`TestHistoryDfUsesFullPopulation`).

**The 74-Star diagnostic result is a real, useful research artifact --
not the canonical output.** 5,011 of 10,659 real rows are currently
deferred, for two disclosed reasons, each its own follow-up:

- **Blocker A -- historical MFL backfill** (4,893 rows, 13 seasons
  2011-2024 excluding the 2 already cached, 2015/2023): needs the
  sanctioned explicit-refresh process (`scripts/mfl_client.py`, real
  MFL AUG15 fetches via GitHub Actions) to fetch and cache the missing
  seasons' ADP + player-directory snapshots. Not attempted locally --
  this project's own convention reserves real external fetches for
  that path.
- **Blocker B -- ADP rounds beyond the fitted E_P range** (118 rows,
  2025 only): MFL's real 2025 market reaches deeper (raw ADP up to
  ~357, round 30) than the E_P lookup's fitted depth (rounds 1-15,
  matching FFC's historical ~150-180-player coverage). Not
  extrapolated, capped, or substituted without an explicit methodology
  decision -- a real, open question, not an implementation detail.

Canonical output generation is blocked on resolving both, or on an
explicit decision to accept a scoped-down canonical population (e.g.
excluding certain seasons/rounds deliberately, which is a different,
explicit decision from silently deferring them). Not decided here.
