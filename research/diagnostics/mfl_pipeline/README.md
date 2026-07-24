# MFL clean-1QB ADP diagnostic pipeline (ISOLATED)

Investigates whether a genuinely clean, source-verified 2025 preseason
single-QB PPR ADP dataset could be reconstructed from MyFantasyLeague's
per-league API, after an earlier pass found MFL's own aggregate ADP
report has no way to exclude superflex/2-QB leagues. **This pipeline
was never wired into the canonical ADP pipeline and is not used by
anything under `scripts/`.**

## Final decision (2026-07)

- **2025 remains included** in production, weekly, playoff-period, and
  championship-roster analyses -- unaffected by this investigation
  either way.
- **2025 remains excluded from primary ADP-dependent fitting.** No
  sufficiently comparable canonical ADP source was recovered.
- **ESPN's partial 2025 ADP remains usable only within the
  championship-roster benchmark** (`research/benchmarks/espn_championship_rosters/`)
  -- not as a general-purpose 2025 ADP source.
- **MFL is preserved as a secondary, platform-specific sensitivity
  dataset, not canonical history.** This pipeline and its outputs may
  be revisited later; they are not deleted, just not promoted to
  canonical.

## Final documented interpretation

1. **MFL's platform-specific 2025 market selected quarterbacks
   substantially earlier than ESPN's.** This held up across every
   verification performed -- see "What was audited" below -- and is
   not explained by a pipeline bug found so far.
2. **The remaining difference may reflect platform users, platform
   rankings/defaults, or unobservable format characteristics.** This
   pipeline cannot distinguish between those explanations with the
   data available from MFL's public API.
3. **ESPN disagreement does not by itself prove MFL's data is
   incorrect.** ESPN is one platform's market, not ground truth.
4. **That measurement difference does make MFL unsuitable as the sole
   canonical continuation of the historical FFC/FFToday series** --
   not because MFL is "wrong," but because a real, substantial,
   unexplained divergence from every other source this project has
   used means treating it as a like-for-like continuation of 2007-2024
   would silently change what "ADP" means for 2025 without that change
   being understood, let alone disclosed.

## What was audited (summary -- see git history / prior session
transcript for the full step-by-step investigation)

- **Pick-order reconstruction**: verified byte-exact against real
  chronological draft timestamps (every checked pick's computed
  `overall_pick` matched its true chronological rank). Not the bug.
- **Pick provenance**: found that a meaningful share of MFL "picks"
  are not real-time human selections -- MFL's own `comments` field
  discloses this. Corrected to a neutral, six-category taxonomy (see
  `fetch_drafts.py`) after an earlier draft over-labeled
  commissioner-entered and externally-imported picks as presumptively
  fake, which they are not. Every provenance variant (native-live
  only, native-live + commissioner/imported, all-non-keeper,
  auto-default-rank-only) was compared -- **the QB gap persists at
  essentially the same magnitude across all of them** (median abs
  diff 10.09-12.62 picks depending on variant), meaning provenance
  filtering does not explain the gap.
- **Per-league behavioral audit**: found 43 of 254 configuration-valid
  1-QB leagues show unusually early QB drafting (2+ QBs in the first
  12 picks). Manually inspected several of these leagues' full raw
  config -- found no additional field explaining it; their starting
  lineup requirement is genuinely 1-QB. **These leagues are NOT
  excluded from the primary estimate** -- excluding leagues based on
  how they drafted, when their configuration is verified valid, would
  circularly force MFL to resemble ESPN rather than measure MFL's
  actual market. That exclusion is reported ONLY as a separate,
  clearly-labeled sensitivity variant
  (`SENSITIVITY_all_non_keeper_excluding_early_qb_leagues`), never as
  the primary estimate.
- **24 leagues manually inspected in full** (starting lineup, every
  flex/OP slot's position eligibility, QB min/max, taxi squad, salary
  cap, franchise count) -- classifier's config-level logic confirmed
  correct on every one checked.

## Pipeline stages (run in this order)

1. `discover_leagues.py` -- league discovery via MFL's own aggregate
   ADP report's league-selector (verified filter-derived, not a
   static site list: 586 leagues for FC=12/PPR/redraft/non-mock/AUG15+
   vs. 2,595 for a looser pull).
2. `classify_leagues.py` -- fetches each league's real config via
   `TYPE=league`, classifies clean-1QB vs. excluded with a named
   reason. Superflex check parses the QB slot's real MAX capacity
   (handles ranges like `"1-2"`), not just string-equality to `"1"`,
   and separately checks for composite QB-eligible slot names.
   **Result: 254 of 586 leagues (43.3%) classified clean-1QB.**
3. `fetch_drafts.py` -- fetches real draft results (per-pick Unix
   timestamps) for clean leagues, filters to the Aug15-kickoff window
   using real timestamps (not the report-level filter's label), tags
   every pick with one of six provenance categories. **Does not
   pre-filter to one "winning" category** -- that choice is made
   explicitly, per-variant, in the next stage.
4. `run_sensitivity_analysis.py` -- builds the ADP estimate under 4
   provenance variants (all drawn from the full 254-league set) plus 1
   clearly-labeled sensitivity-only variant, and compares each against
   the real ESPN 2025 benchmark. See that script's docstring for the
   exact variant definitions.

## Rate-limiting / caching / resumability

All network access goes through `mfl_client.py`: every response is
cached to disk keyed by exact URL, requests are strictly serial, a
minimum delay is enforced between real network calls, and failures
retry with bounded exponential backoff. Every stage is resumable:
re-running any script re-reads the cache for anything already
fetched.

## Known, disclosed limitations

- **Best-ball**: no explicit field found in MFL's league-config schema
  for this -- not independently excluded.
- **The 43 early-QB leagues remain genuinely unexplained** -- config
  verified valid 1-QB, no additional field found after a full manual
  JSON dump, yet real elite starting QBs were drafted in bulk in round
  1. Neither confirmed contamination nor confirmed organic strategy.
- **2025 kickoff timestamp**: 2025-09-04 00:00 UTC is an explicit,
  disclosed assumption, not cross-checked against a verified schedule
  source.
- **ESPN validation sample is small** (36 overlapping players across
  all positions, as few as 5 for QB/TE) -- limits confidence in the
  exact by-position numbers, though the qualitative finding (QB gap
  persists across every variant and audit) does not depend on that
  sample size alone.

## What's committed vs. what stays local

Per data-sensitivity requirements, only code, tests, this README, and
SANITIZED aggregate outputs (player-level ADP estimates, position-level
comparison statistics -- no league IDs, league names, franchise/owner
names, or raw cached API responses) are committed. The full working
cache and per-league CSVs regenerate locally by re-running the
pipeline in order; they are never committed.
