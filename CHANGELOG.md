# Changelog

All notable changes to the League Winner Index (Dataset 1) are
recorded here. For the full "why" behind each decision, see
`docs/LWI_MODEL_CARD.md` (design history) and `docs/METRIC_SPECIFICATION.md`
(exact current formulas).

## Data source migration -- nflverse `stats_player` release (2006-2025)

**Not an LWI formula change -- `LWI_VERSION` stays 2.1.** This is a
data-provenance event: the underlying nflverse weekly stats source
changed, not any weight, threshold, or formula.

**Why**: `scripts/03_download_stats.py` depended on
`nfl_data_py.import_weekly_data()`, which reads nflverse's
`player_stats` GitHub release. That release was marked DEPRECATED
2025-08-01 and is frozen -- confirmed directly it will never receive
2025 or any later season. Migrated to nflverse's successor
`stats_player` release, fetched directly (new `scripts/nflverse_source.py`
module) rather than through `nfl_data_py`, which has not been updated
to point at the new release (latest PyPI version predates nflverse's
own migration).

**Verified before migrating, not assumed**:
- `team` (new release) vs. `recent_team` (old release, and this
  project's existing output schema): confirmed a pure, lossless
  rename -- 100% agreement across every season 2006-2024, not just a
  sample.
- `fantasy_points_ppr`: **166 individual weekly rows corrected**
  across 2006-2024 (of ~91,000 compared, ~0.18%) -- small, real stat
  corrections nflverse applied upstream after the old release was
  frozen. Per-season counts ranged 3-16 rows; max single-row
  difference 2.0-12.6 points depending on season.
- Downstream impact of those 166 rows: **165 affected player-seasons**
  (recomputing season totals via the exact existing aggregation
  logic), of which **34 show a `games_played` change** and **zero
  cross the `LWI_MIN_GAMES` (8) eligibility threshold** -- no
  player-season flips between scored and unscored. **~84 of the 165
  are currently LWI-eligible** (have a real production `lwi_score`),
  meaning their component inputs -- and therefore their exact score --
  shift by a small amount under the new source. Full row-level detail
  in `research/diagnostics/nflverse/old_vs_new_downstream_impact.csv`.
- REG-only filtering (excludes the new release's additional POST/
  playoff rows) and the team-column rename are both covered by new
  regression tests, `tests/test_nflverse_source.py`.

**Integrity mechanism added**: `scripts/nflverse_source_manifest.json`,
committed, records the exact GitHub release **asset ID** (not just a
URL), retrieval date, sha256, schema version, and upstream
`updated_at` timestamp for every season 2006-2025. Fetches by asset ID
rather than the tag+filename URL -- verified this is a real
difference: the tag+filename URL always resolves to whatever asset
*currently* holds that name, silently serving new bytes if nflverse
deletes and re-uploads (their actual mechanism for publishing a
correction); an asset ID is tied to one specific uploaded object, so a
future republish either 404s (loud, clear failure) or keeps serving
the original bytes. A future pipeline run additionally verifies the
downloaded file's hash against the manifest's recorded sha256 before
use -- if nflverse changes an asset's content in place, the pipeline
fails loudly rather than silently drifting, regardless of the ID
pinning. A manifest entry is only ever written by an explicit,
separate call (`register_manifest_entry()`), never as a side effect of
a normal run.

**Honest limits on this, stated explicitly rather than implied**:
- GitHub does not publicly document a permanence guarantee for release
  asset IDs -- this is the most stable identifier their API exposes,
  not a proven-forever guarantee. The sha256 check is the actual
  safety net; asset-ID pinning reduces how often it's needed, it
  doesn't replace it.
- This project does not independently archive nflverse's raw bytes
  anywhere -- the only local copy is the gitignored cache under
  `data/raw/nflverse/annual/`. A fresh clone has none of it and
  re-fetches from GitHub by asset ID.
- If GitHub ever fully removes an asset (not just supersedes it), a
  fresh-clone rebuild for that season fails with a fetch/HTTP error,
  not an integrity error -- a real, disclosed limitation, not a
  defect.
- Updating the manifest to accept a real upstream revision is always
  an explicit, reviewed action (`register_manifest_entry(season,
  force=True)`), never automatic.

**Verified directly, not just designed**: emptied the local cache for
two seasons (2010, 2025) and confirmed `fetch_season_raw()` re-downloads
from scratch by asset ID and reproduces the exact recorded hash --
this is the literal fresh-clone scenario. Reproduced offline (mocked
network) in `tests/test_nflverse_source.py`'s `TestEmptyCacheRetrieval`
for CI.

**2025 season**: now included in the master database and season-level
stats for the first time (full season, weeks 1-18 REG + real
postseason correctly excluded). **2025 ADP is a separate, not-yet-decided
question** -- this migration does not add or approve any 2025 ADP
source; 2025 rows remain `no_adp_match`/LWI-ineligible until that's
resolved.

## v2.1 -- current

### Added
- Leave-one-season-out (LOSO), monotonic (isotonic regression)
  expected-finish curve for Component 1, replacing within-season
  comparison -- avoids a player-season influencing its own baseline,
  and avoids the metric's meaning drifting year to year based on how
  strong that particular season's draft class happened to be.
- Overall-ADP-underperformance cap on Component 1 -- prevents a player
  from scoring well by beating a bad historical baseline (early picks
  bust often) while still having genuinely underperformed the actual
  pick spent on them (found via Arian Foster 2012: drafted 1.4
  overall, finished 12th).
- Winsorized (5th/95th percentile) min-max normalization for
  Component 4's final cross-position scaling.
- Transparency output columns (`positional_advantage_raw`,
  `positional_advantage_winsorized`) so Component 4's clipping is
  auditable, not hidden inside one opaque step.
- Standardized positional advantage for Component 4 -- PPG above
  replacement divided by the position's starter-tier IQR, not the raw
  difference.
- Undrafted-player representation: binary `adp_status`
  (drafted/undrafted) with separate `verification_status`
  (verified/unresolved), a fixed global-max-ADP+1 proxy for verified-
  undrafted players, and full observed-vs-modeled ADP schema in
  `04_build_master_dataset.py`.
- Dataset 5 (`no_adp_breakout_candidates.csv`): research/discovery list
  of currently-unresolved players with a real, strong statistical
  season, surfaced for verification research.
- `docs/LWI_MODEL_CARD.md` -- purpose, validation, interpretation,
  design history, limitations.
- `docs/PREDICTION_SPECIFICATION.md` -- target definition, evaluation
  metric, and validation protocol for the eventual predictive model
  (Dataset 3), written before any feature engineering begins.
- `06_generate_rankings.py`: all-time rankings, season champions,
  position leaderboards, biggest ADP values/busts, Dataset 5.
- 18 net new automated regression tests (35 -> 53), nearly all tied
  directly to a specific real bug found during this process, not
  written speculatively.

### Changed
- Component 1: overall ADP comparison replaces positional-only
  comparison -- a player can be positionally perfect (e.g. TE1
  drafted, TE1 finished) while their overall value collapsed relative
  to the whole draft pool (Gronkowski 2015: drafted 10th overall,
  finished 32nd) -- positional-only comparison was structurally blind
  to this.
- Component 2 (total points) and Component 3 (PPG): both replacement-
  adjusted and cross-position, not raw/positional percentile --
  positional-only percentile let a "best of a thin position" season
  score comparably to genuinely larger positional advantages
  elsewhere.
- Component 4 redesigned twice: first from unstandardized "PPG above
  replacement" to IQR-standardized (fixed a mathematical duplication
  with Component 3), then from plain min-max to winsorized min-max
  (fixed a cross-position outlier-contamination bug).
- `LWI_VERSION` bumped 1.0 -> 2.0 -> 2.1 as these changes landed.

### Fixed
- **Component 3/4 duplication**: an earlier version had Components 3
  and 4 computing the mathematically IDENTICAL formula (Spearman
  correlation ~0.9999999, R-squared of 1.000 when Component 4 was
  regressed on Components 2+3) -- literally the same signal weighted
  twice. Fixed by standardizing Component 4's denominator, giving it a
  genuinely distinct job.
- **Cross-position outlier contamination**: Component 4's plain
  min-max normalization let a single extreme outlier in ONE position
  shift an UNRELATED player's score in a DIFFERENT position by 60+
  points, since the final scale was shared across all 4 positions
  within a season. Fixed via winsorization; verified the same test now
  shows 0.0.
- **Model Card documentation drift**: an earlier version of
  `LWI_MODEL_CARD.md` cited stale statistics from before the
  winsorization fix (known-winner median said "~24," should have been
  16; Component3-4 correlation said "0.878," should have been 0.942).
  Caught via a full release-verification pass measured directly
  against production output, not assumed from memory.
- **A GitHub Actions pipeline gap**: `run_full_pipeline.yml` never
  installed scikit-learn (required once Component 1 needed isotonic
  regression) and stopped after step 4, never running the actual LWI
  calculation or rankings generation steps. Found during a
  file-consolidation audit, not reported by any test.
- Two position-classification errors inherited from nflverse's own
  source data (Jordan Matthews and Devin Funchess both tagged TE for
  their entire careers despite playing WR) -- fixed via
  `data/manual/position_overrides.csv`, same override-table pattern
  used for player-name matching.

### Rejected (considered, explicitly decided against, worth recording)
- A 50/50 (then 75/25) blend of positional and overall ADP value for
  Component 1 -- superseded by moving to 100% overall once testing
  showed the positional component wasn't solving a problem Component 4
  didn't already cover, and was actively diluting the overall-value
  signal.
- MAD and standard deviation as Component 4's standardization
  denominator -- both tested head-to-head against IQR; IQR won on
  false-positive separation, which was judged more important than
  MAD's marginally better known-winner ranking (precision over
  recall).
- Percentile-rank and 2.5/97.5-winsorized normalization as
  alternatives to 5/95 winsorization for Component 4's final scaling
  -- both achieved similar outlier robustness but with meaningfully
  worse discriminative power.
- A three-state `adp_type` (drafted/undrafted/unknown) for the
  undrafted-player mechanism -- rejected in favor of a binary
  `adp_status` (drafted/undrafted) plus a separate `verification_status`
  (verified/unresolved), since "we haven't checked" and "confirmed
  undrafted" are different claims about *our data*, not different
  real-world states -- historically, every player was either drafted
  or not.
- Season-relative (rather than global) proxy ADP for verified-
  undrafted players -- rejected because it would unfairly reward
  players from seasons where the ADP source happened to be shallower,
  rewarding a property of the source rather than the player.
- A separate scoring path/model for undrafted players -- rejected in
  favor of one unified acquisition model, since a player taken with a
  draft's last pick and one who goes undrafted are usually separated
  by one manager's decision, not a fundamentally different acquisition
  mechanism.

## v1.0 -- prior baseline (superseded)

- Original 6-component formula per `docs/VERSION_1_SCOPE.md`: 46% ADP
  Value (positional comparison), 18% Fantasy Finish Total Points, 17%
  PPG, 12% Positional Advantage, 4% Playoff Performance, 3%
  Consistency.
- Core pipeline built: ADP acquisition (FFC API + FFToday archive),
  player identity matching, master dataset construction, weekly
  results extraction for playoff/consistency components.
- 35 regression tests, each anchored to a real bug found during
  construction (mid-season trade row-splitting, special-teams-TD
  games_played undercounting, pandas merge index misalignment, and
  others).

## Known future work (not yet started)

- Verification research for Dataset 5 candidates against additional
  historical ADP sources (MFL, RTSports, Underdog, etc.).
- Dataset 2 (League Winner Traits): research into which preseason-
  available signals correlate with becoming a league winner.
- Dataset 3 (Predictive League Winner Probability): a model trained on
  Dataset 2's findings, per `docs/PREDICTION_SPECIFICATION.md`.
