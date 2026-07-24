# ADP Source Matrix

## Mission

The purpose of this document is to identify, evaluate, and document the best possible source architecture for historical preseason PPR Average Draft Position (ADP).

This is the largest remaining data acquisition challenge for the Fantasy Research Engine.

---

# Project Target

We require a dataset containing:

- Seasons: **2006–2025**
- Scoring: **PPR**
- Draft Type: **Redraft**
- Coverage: **Top 250 players minimum**
- Format: **Machine-readable**
- Automation: **Fully reproducible**
- Merge-ready with the Master Historical Database

---

# Success Criteria

An ADP source is considered "production ready" only if it satisfies all of the following:

- ✅ Historical preseason ADP
- ✅ PPR scoring
- ✅ Approximately Top 250 players
- ✅ Stable player names
- ✅ Position information
- ✅ Easily automated
- ✅ Reproducible in one pipeline run
- ✅ Compatible with player matching system

---

# Current Recommendation

**No single source has earned Primary Backbone status.**

Current expectation:

- Primary source (to be determined)
- Secondary validation source
- Automated validation reports
- Manual review only when necessary

---

# Current Source Matrix

| Source | Coverage | Automation | Data Quality | Current Grade | Proposed Role |
|---------|----------|------------|--------------|---------------|---------------|
| nflverse / nfl_data_py | Fantasy results only | A+ | A+ | A+ | Fantasy results backbone |
| Fantasy Football Calculator | Verified: strong 2010-2024, absent 2008/2009/2025, contaminated 2007/2008-standard | A | B (2010-2024) / F (2007-2008 standard) | B- | Secondary contributor, 2010-2024 only |
| FantasyPros | Historical pages confirmed | Unknown | A | A- (investigating) | Potential primary backbone |
| FFToday | Recent seasons | A | B | B- | Recent-year backup |
| Kaggle datasets | Unknown | TBD | TBD | Pending | Supplemental |
| GitHub repositories | Unknown | TBD | TBD | Pending | Supplemental |
| Internet Archive | Unknown | Low | TBD | Pending | Historical recovery |
| Sleeper | Unknown | TBD | TBD | Pending | Modern validation |
| MyFantasyLeague | 254 configuration-valid leagues (2025) | A (isolated diagnostic pipeline) | B (real QB/TE gap vs. every other 2025 source checked) | B- | Secondary sensitivity dataset only, not canonical |
| RTSports | Unknown | TBD | TBD | Pending | Candidate |
| Commercial APIs | Unknown | Varies | High | Pending | Last resort |

---

# Investigation Log

---

## Fantasy Football Calculator

### Status

🟢 Verified with real data (Phase 1 fetch complete, GitHub Actions)

### Findings

- Fetched all of 2007-2025 for real via a GitHub Actions workflow
  (my own tools are robots.txt-blocked for this site; GitHub's runners
  are not). Every response saved raw and audited -- see
  `docs/ADP_SEASON_SOURCE_PLAN.csv` and the coverage report.
- **2010-2024: genuinely clean.** Every year has a tight 1-5 day
  collection window in late Aug/early Sept (real preseason snapshots,
  not contaminated with in-season or later-year data). Usable skill
  players (QB/RB/WR/TE with valid ADP) range from 92 (2012, a notably
  thin year) to 187 (2010).
- **No single year reaches the 250-player target from FFC alone** --
  187 is the best case. This confirms the original caution in this doc:
  FFC cannot be sole primary backbone for any season, only a
  contributor. A secondary source is required everywhere, not just in
  gap years.
- **2008 and 2009 PPR: cleanly absent.** API returns
  `{"status": "Error", "errors": "No ADP data found."}` -- an honest,
  unambiguous "doesn't exist," not a technical failure.
- **2025 PPR: also cleanly absent** (same error). Reason unclear --
  worth investigating separately since the 2025 season has already been
  played by the time of this fetch (July 2026), so preseason ADP for it
  should exist somewhere even if not on FFC.
- **Critical finding -- 2007 and 2008 standard-scoring archives are
  contaminated, not just old:**
  - 2007 standard: API claims `status: Success` with real metadata
    (998 drafts) but returns **zero players**. The claimed collection
    window is 2007-08-29 to **2010-06-20** -- a 1,026-day span.
  - 2008 standard: returns 180 players (154 usable skill), but its
    collection window is 2008-08-30 to **2010-06-20** -- a 659-day
    span. Both end on the exact same date.
  - Compare to any clean year (e.g. 2010: a 5-day window). A real
    single-season preseason ADP snapshot does not span two-plus years.
    This strongly suggests FFC didn't cleanly separate drafts by season
    until sometime around June 2010, and everything before that got
    dumped into rolling multi-year buckets. The 2008 "154 usable
    players" figure may reflect draft behavior from as late as mid-2010,
    not genuine 2008 preseason ADP -- **it should not be used as-is**.
    The 2007 zero-players result may be a downstream bug specific to
    that same contaminated bucket.
  - **Action needed**: this isn't resolved by re-fetching -- the data
    itself is what FFC has. Would need either a different query
    parameter that isolates by date (not obviously available in this
    API), or to abandon FFC entirely for 2006-2008 and rely on
    FFToday/Wayback instead.

### Verdict

Confirmed as a strong (not sole) secondary/tertiary contributor for
2010-2024. Not usable at all for 2007–2009 or 2025 in its current form
-- 2008-2009 are cleanly absent, but 2007-2008's *standard* archives are
worse than absent: they look present but are contaminated across
multiple seasons, which is a more dangerous failure mode than a clean
404 because it's easy to mistake for real data.

---

## FantasyPros

### Status

🟡 Under Investigation (updated)

### Findings

- Historical pages exist and are reachable by automated fetch (not
  robots-blocked, unlike FFC).
- The player ADP table itself is loaded client-side by JavaScript --
  a plain HTTP fetch of `ppr-overall.php?year=YYYY` returns page shell
  (nav, footer, a "Pick Sources" modal) but not the table rows. Actual
  extraction will need a headless-browser-capable fetcher (this is a
  ChatGPT/manual task, not something the current pipeline tooling can do).
- **Important methodological finding**: the "Pick Sources" panel on the
  live page reveals FantasyPros' PPR ADP consensus is itself built by
  averaging ADP from Fantasy Football Calculator, MyFantasyLeague,
  RTSports, and Fantrax. This means FantasyPros is *not* an independent
  source relative to FFC -- for years where both are used, treating them
  as primary+secondary for cross-validation is partially circular, since
  a chunk of FantasyPros' number *is* FFC's number. Genuinely independent
  cross-validation would need MFL, RTSports, or Fantrax pulled
  separately, not just FantasyPros' blend.
- FantasyPros also has an official paid API (`fantasypros.com/api-data/`)
  -- listed as a candidate under Commercial APIs below, not yet evaluated
  for cost/access.

### Verdict

Still useful as a secondary/cross-check source, but downgraded from
"most promising primary source" given the circularity finding above.
Extraction requires a JS-capable fetcher regardless.

---

## FFToday

### Status

🟢 Verified with real data (2007-2009 successfully parsed)

### Findings

- **The data is NOT JavaScript-rendered, as originally assumed.** A
  plain markdown-converting fetch returned only a page shell, which
  led to the earlier conclusion that the table was AJAX/frame-loaded.
  That was wrong -- the real cause was that FFToday uses old-style
  nested tables (a `<table>` inside a single `<td>` of another
  `<table>`), which the markdown converter couldn't parse but a real
  HTML parser (BeautifulSoup) handles fine.
- Built `scripts/parse_fftoday_adp.py` -- a real, working parser.
  Verified against raw HTML for 2007, 2008, and 2009 (fetched via a
  dedicated GitHub Actions investigation workflow, since the site isn't
  robots.txt-blocked but the earlier tooling still needed a real
  browser-less HTTP client to see the true structure).
- **Results**: 185 (2007), 181 (2008), and 176 (2009) usable skill
  players (QB/RB/WR/TE), all clean single-snapshot extractions --
  better than several of FFC's own "clean" years (e.g. FFC's 2012 only
  had 92).
- All three snapshots are sourced from Fantasy Football Calculator
  ("Courtesy of: Fantasy Football Calculator") but captured and cached
  by FFToday at a specific point in time -- meaning FFToday effectively
  preserved a clean copy of FFC's 2007-2009 data from before FFC's own
  archive became contaminated (see the FFC section above: FFC's own
  API now returns broken/contaminated data for these exact years).
  2007's draft count (998) even matches FFC's own corrupted 2007
  archive exactly, confirming it's the same underlying draft pool,
  just captured intact.
- Minor cosmetic issue: the 2008 page's displayed date label misreads
  "8/31/07" even though it's the 08_adp.htm archive. The actual player
  rankings clearly reflect real 2008 preseason expectations (different
  player pool/ordering than 2007), so this looks like a copy-paste typo
  on FFToday's own site, not evidence of wrong-year data -- but worth
  a second look if anything about 2008 looks off later.
- Not yet tested: whether the same `NN_adp.htm` pattern and table
  structure holds for years between 2010-2020 (FFC's API already
  covers those cleanly, so lower priority), or whether 2006 exists at
  all under this pattern (untested -- the confirmed-dead `06_adp.htm`
  guess used earlier was for a different naming convention we haven't
  verified against the real site).

### Verdict

**Promoted to verified primary source for 2007-2009**, replacing FFC
(which is broken/contaminated for these exact years). This closes 3 of
the historical gap years with real, clean, better-than-FFC data.

### 2025 update -- a different page template, not the same source (2026-07)

**The 2007-2009 archive pages and the current-era page are not the
same kind of source and must not be assumed to share a methodology.**
The 2007-2009 pages (Findings above) are a single-source snapshot
credited "Courtesy of: Fantasy Football Calculator." The current page
(confirmed for 2025, URL pattern `NN_adp_ppr.html`) uses a completely
different template: a three-source RANK consensus, not FFToday's own
collected draft data.

- **`https://www.fftoday.com/rankings/25_adp_ppr.html`** -- HTTP 200,
  not robots.txt-blocked (`fftoday.com/robots.txt` itself 404s -- no
  disallow rules exist for this site at all). A real, dated,
  single-snapshot page: **"PPR Scoring - 8/29/25"** appears directly
  in the page text -- a clean, disclosed collection date, 6 days
  before the 2025 kickoff assumption already used elsewhere in this
  project (`WINDOW_END` in `research/diagnostics/mfl_pipeline/`).
- The table header discloses its own sourcing directly: **"Sources:
  Sleeper, RTSports, ESPN"** -- three columns (`S`, `RT`, `ESPN`) give
  each platform's own rank, plus an `Avg` column FFToday computes
  itself. This is the same kind of opacity problem already flagged
  for FantasyPros above (an undisclosed blend, not an independent
  primary source) -- just a different set of three platforms
  (Sleeper/RTSports/ESPN here, vs. FFC/MFL/RTSports/Fantrax for
  FantasyPros). RTSports appears in both blends.
- **283 total ranked players, 238 of them QB/RB/WR/TE** -- the best
  skill-position coverage found for any source, any year, in this
  entire project (FFC's best year, 2010, was 187).
- **Critical structural difference from every other season's ADP
  field (2007-2024): these are integer RANKS (1-283) per source, not
  fractional mean-pick ADP.** FFC's `adp` field is a real decimal --
  mean pick across many real drafts, e.g. `4.2`; this page's `S`,
  `RT`, `ESPN`, and `Avg` columns are derived whole-number rank
  positions with no visibility into pick spread, sample size, or raw
  underlying ADP per platform. Treating a rank column as
  interchangeable with historical mean-pick ADP would silently change
  what the "ADP" field means for 2025 relative to every other season.
- **Cross-validated against this project's own, independently
  collected ESPN championship-roster benchmark data**
  (`research/benchmarks/espn_championship_rosters/`): FFToday's
  embedded `ESPN` column vs. that benchmark's `adp_overall`, 37
  overlapping 2025 players -- Pearson r = 0.973, median absolute
  difference = 2.7 ranks. Strong agreement between two independently
  collected datasets is good evidence FFToday's extraction here is
  genuine, not corrupted or mislabeled.

### Verdict (2025 page)

Not promoted to any canonical or secondary-blend role. Real,
reproducible data with the best skill-position coverage found in this
project, but disqualified from canonical status today by (a)
undisclosed per-platform methodology behind the blend, and (b) being
an integer-rank product rather than the mean-pick-ADP quantity used
for every other season. See "2025 Cross-Source Validation" below for
how it was used as corroborating evidence instead.

---

## Kaggle

Status:

🟡 Partially Evaluated

### Findings

- Dataset pages (e.g. robertcurrie/nfl-adp-and-fantasy-pts-fantasy-pros-2020-2022)
  are reachable and confirmed to exist, but the page itself is a JS
  single-page app -- fetching it returns only metadata (title,
  description), not the actual CSV contents or even a preview table.
- Actual CSV download requires either the Kaggle API (needs an account +
  API token) or a browser session -- neither of which the current
  pipeline tooling has. This needs a human with a Kaggle account (or
  ChatGPT if it can authenticate) to actually pull the files down.

### Verdict

Datasets likely exist as described in the original handoff, but
"evaluated" still means someone with Kaggle access needs to actually
download and inspect the CSVs -- can't be done by URL fetch alone.

---

## GitHub Repositories

Status:

🟡 Evaluated (ffverse specifically) -- important caveat found

### Findings

- Cloned `ffverse/ffsimulator` directly and inspected its bundled data
  (not just the README claims).
- `fp_rankings_history` covers 2012-2020 (QB/RB/WR/TE/PK) and 2015-2020
  (DL/LB/DB), 11,336 rows -- confirmed to exist as a real, loadable
  dataset (R `.rda` format).
- **Critical finding**: this data is FantasyPros *Expert Consensus
  Rankings* (ECR) -- analyst-produced positional rankings scraped via
  the `ffpros` package's cheatsheet pages -- NOT observed draft-market
  ADP. The package's own `ffs_adp_outcomes()` function is documented as
  "Connects ff_scoringhistory to past ADP rankings" and internally uses
  `fp_rankings_history` as its input, effectively treating expert
  rankings as an ADP stand-in for simulation purposes.
- This is legitimate for ffsimulator's own purpose (simulating season
  outcomes by preseason rank, not doing ADP market research), but it
  means **this dataset must not be imported into our pipeline and
  labeled as ADP**. Per the addendum's rules on scoring-format labeling,
  the same principle applies: rankings are not ADP, regardless of how
  convenient the substitution would be.
- Other GitHub repos beyond ffverse: not yet searched.

### Verdict

Not usable as an ADP source under any label other than
`estimated_adp_from_expert_rankings`, and even then only with explicit
approval -- same standard as the standard-to-PPR proxy rule. Do not use
as primary or secondary ADP source in the season plan above.

---

## Internet Archive

Status:

Not yet evaluated.

---

## Sleeper

Status:

Not yet evaluated.

---

## MyFantasyLeague

### Status

🟢 Evaluated via a dedicated, isolated diagnostic pipeline (2026-07)

### Findings

Full investigation, methodology, and a 26-test suite live in
`research/diagnostics/mfl_pipeline/` -- never wired into the canonical
ADP pipeline; see that directory's README for the complete audit.
Summary:

- Built a serial, rate-limited, resumable per-league fetcher, since
  MFL's own aggregate ADP report has no way to filter out
  superflex/2-QB leagues -- per-league reconstruction from real draft
  results was required instead.
- 586 candidate 2025 leagues discovered; 254 classified as
  configuration-valid clean-1QB PPR redraft (the superflex check
  parses the real MAX of the QB slot's `limit` field, not
  string-equality to `"1"`, per this document's own principle of never
  guessing from an incomplete signal).
- Found a real, substantial, unexplained gap: MFL's reconstructed
  market drafts quarterbacks and tight ends meaningfully earlier than
  every other 2025 source checked (see "2025 Cross-Source Validation"
  below). This persists across every pick-provenance variant tested,
  and after excluding the 43 leagues with the most unusual QB-heavy
  early-round behavior.

### Verdict

Preserved as a secondary, platform-specific sensitivity dataset, not
canonical history. See `research/diagnostics/mfl_pipeline/README.md`
for the full final-decision writeup.

---

## 2025 Cross-Source Validation: MFL vs. FFToday's 3-source consensus

### Status

🟢 Complete (2026-07) -- a one-time targeted investigation, not an
ongoing pipeline stage.

### Purpose

MFL's reconstructed 2025 QB ADP (see MyFantasyLeague findings above)
looked implausible on its own (Josh Allen at mean ADP 6.3). The only
outside comparison available at the time was this project's own
50-player ESPN championship-roster benchmark -- a real but
survivorship-biased sample (only players who ended up on a winning
roster), not general-market ADP. Discovering FFToday's 2025 page (see
FFToday's "2025 update" findings above) added three more independent
2025 rank sources -- Sleeper, RTSports, ESPN -- to compare against,
without requiring any new data collection.

### Method

`research/diagnostics/mfl_pipeline/output/adp_all_non_keeper.csv`
(MFL's primary-variant reconstructed ADP) merged against
`research/diagnostics/adp_2025_investigation/parsed/fftoday_2025_ppr_consensus.csv`
on normalized player name, **restricted to real QB/RB/WR/TE rows on
both sides before merging.**

An earlier pass merged before filtering out MFL's non-player,
franchise-level rows -- MFL's player table contains up to 6 duplicate
rows per NFL team under labels like `Def`, `TMPK`, `ST`, `Off`,
`Coach`, `PN`, alongside real players. FFToday's 27 team-defense rows
collided with those duplicates and inflated the naive merge to 348
"overlapping" rows -- inconsistent with the by-position counts (which
summed to 228 and were never actually affected, since none of those
team-level MFL rows carry a QB/RB/WR/TE label). **Corrected,
skill-position-only total: 228 overlapping players**, which now
matches the position breakdown exactly (35 QB + 72 RB + 85 WR + 36 TE
= 228).

**This is now enforced, not just fixed once.**
`research/diagnostics/adp_2025_investigation/compare_mfl_fftoday.py`
requires both sides to be passed through `filter_to_skill_positions()`
before merging, and its `summarize()` step asserts the per-position
counts sum to the total overlap -- the same consistency check that
caught this bug in the first place -- so a future contaminated merge
fails loudly instead of printing a plausible-looking wrong number.
`tests/test_compare_mfl_fftoday.py` locks this in with a synthetic
fixture that reproduces the exact collision (one real player plus
MFL's 6 team-level duplicate rows for one franchise, matched against
one FFToday DEF row) and asserts the unfiltered merge reproduces the
inflation (7 rows instead of 1) while the filtered merge does not.
**Any future player-level cross-source comparison involving MFL's
player table must filter to real skill positions before merging** --
that table carries non-player, franchise-level rows under labels like
`Def`/`TMPK`/`ST`/`Off`/`Coach`/`PN`, several per team, all sharing one
normalized team name.

### Findings

Overall (228 players, corrected):

| Comparison | n | Pearson r | median abs diff (ranks) |
|---|---|---|---|
| MFL vs. Sleeper rank | 228 | 0.955 | 14.6 |
| MFL vs. RTSports rank | 201 | 0.948 | 10.6 |
| MFL vs. FFToday's embedded ESPN rank | 182 | 0.965 | 8.6 |
| MFL vs. 3-source Avg rank | 228 | 0.962 | 9.4 |

By position (MFL vs. the 3-source Avg rank):

| Position | n | Pearson r | median abs diff | mean signed (MFL minus consensus) |
|---|---|---|---|---|
| QB | 35 | 0.973 | 25.5 | -28.2 |
| RB | 72 | 0.974 | 7.3 | -7.2 |
| WR | 85 | 0.970 | 7.8 | -7.0 |
| TE | 36 | 0.949 | 19.8 | -23.0 |

RB and WR agree closely across all sources (roughly a 7-8 rank median
difference). **QB and TE do not** -- both show MFL pricing the
position roughly 20-28 ranks earlier than the Sleeper/RTSports/ESPN
consensus, consistently in the same direction (MFL always earlier,
never later).

For the specific case that originally triggered this investigation:

| Player | MFL mean ADP | Sleeper rank | RTSports rank | ESPN rank (via FFToday) | This project's own ESPN benchmark |
|---|---|---|---|---|---|
| Josh Allen | 6.3 | 20 | 25 | 19 | 20.6 |
| Lamar Jackson | 16.0 | 21 | 24 | 23 | -- |
| Joe Burrow | 24.0 | 36 | 37 | 33 | 34.1 |

Four independent sources -- Sleeper, RTSports, ESPN (via FFToday), and
this project's own separately-collected ESPN championship-roster data
-- now agree Josh Allen's real 2025 ADP was approximately 19-25. Only
MFL puts him at 6.3.

### Verdict

**Strengthens, rather than resolves, the existing MFL finding.** The
QB/TE gap no longer rests on a single 50-player, survivorship-biased
comparison -- three more independent platforms corroborate the same
direction and rough magnitude of disagreement. This is good evidence
the gap is a real MFL-platform-specific (or MFL-diagnostic-pipeline-
specific) characteristic rather than a fluke of the ESPN benchmark's
small, biased sample. It does not, by itself, prove *why* -- MFL's own
per-league audit already ruled out configuration error and
pick-provenance contamination as the sole explanation (see
`research/diagnostics/mfl_pipeline/README.md`).

### Decision

2025 remains excluded from primary ADP-dependent fitting and is not
promoted to canonical or secondary-blend status from any source
checked in this pass (MFL, FFToday's consensus, or ESPN's partial data
individually). **2007-2024 (18 seasons) is used for the Absolute
Impact expected-production work**, per the existing decision in
`research/diagnostics/mfl_pipeline/README.md`, now with stronger
supporting evidence.

### Next experiment

Direct acquisition from Sleeper's and RTSports' own APIs/exports
(bypassing FFToday's blend entirely) would preserve real per-platform
ADP methodology and, ideally, raw mean-pick values rather than derived
ranks -- not attempted in this pass. This is the most promising
concrete next step if 2025 ADP resolution is revisited later.

---

## RTSports

Status:

Not yet evaluated.

---

## Commercial APIs

Status:

Not yet evaluated.

---

# Coverage Assessment

| Years | Confidence | Notes |
|---------|-----------|-------|
| 2006 | ⭐☆☆☆☆ | Largest remaining gap, no source verified yet |
| 2007 | ⭐⭐⭐⭐☆ | FFToday VERIFIED: 185 usable skill players, clean single snapshot (FFC's own archive for this year is broken) |
| 2008 | ⭐⭐⭐⭐☆ | FFToday VERIFIED: 181 usable skill players, clean single snapshot (FFC's own archive for this year is contaminated) |
| 2009 | ⭐⭐⭐⭐☆ | FFToday VERIFIED: 176 usable skill players, clean single snapshot; FFC PPR confirmed absent |
| 2010-2024 | ⭐⭐⭐⭐☆ | FFC VERIFIED clean -- 92-187 usable skill players/year, needs a secondary source layered in to reach 250 every year |
| 2025 | ⭐⭐☆☆☆ | FFC confirmed cleanly absent. FFToday's modern page (Sleeper/RTSports/ESPN rank consensus) and MFL's diagnostic pipeline both evaluated -- neither qualifies as canonical (see FFToday, MyFantasyLeague, and "2025 Cross-Source Validation" sections). 2025 remains sensitivity-only; 2007-2024 used for ADP-dependent fitting. |

---

# Engineering Principles

When evaluating an ADP source:

1. Never assume completeness.
2. Automate validation before importing.
3. Record evidence for every decision.
4. Prefer reproducible pipelines over manual downloads.
5. A hybrid architecture is acceptable if it improves data quality.

---

# Next Investigations

## High Priority

- [ ] Locate FantasyPros export/API endpoint.
- [ ] Test alternative FFToday historical URL structures.
- [ ] Search Kaggle for historical ADP datasets.
- [ ] Search GitHub for historical CSV repositories.
- [ ] Investigate Internet Archive snapshots.

## Medium Priority

- [ ] Evaluate Sleeper historical ADP.
- [ ] Evaluate RTSports historical ADP.
- [ ] Evaluate MyFantasyLeague historical ADP.

---

# Definition of Success

The ADP problem is solved when:

- Every season (2006–2025) contains Top 250 preseason PPR ADP.
- Every player matches the Master Player Table.
- Validation reports pass.
- The complete ADP database rebuilds with a single command:

```bash
python run_pipeline.py
```

---

# Decision History

This document is intended to remain a living engineering notebook.

Every major source evaluation should be documented with:

- Date
- Evidence
- Findings
- Decision
- Confidence level
- Next experiment
- The goal is to preserve engineering reasoning so future work never repeats previous investigations.

---

### 2026-07 -- 2025 canonical ADP investigation (MFL + FFToday cross-validation)

- **Date**: 2026-07
- **Evidence**: `research/diagnostics/mfl_pipeline/` (254-league MFL
  diagnostic, 26-test suite) and
  `research/diagnostics/adp_2025_investigation/` (FFToday 2025 page
  capture and MFL comparison).
- **Findings**: FFC confirmed absent for 2025. FantasyPros still not
  automatable (JS-rendered table). FFToday's modern page is a real,
  dated (8/29/25), 238-skill-player consensus of Sleeper/RTSports/ESPN
  ranks -- the best coverage found to date, but an opaque blend of
  integer ranks, not raw mean-pick ADP. Cross-validated against this
  project's own ESPN benchmark (r=0.973, n=37). Compared against MFL:
  RB/WR agree closely (~7-8 rank median diff) across all sources; QB
  and TE do not (~20-28 rank median diff, MFL consistently earlier).
- **Decision**: No source promoted to canonical or blended-consensus
  status. 2025 remains sensitivity-only. 2007-2024 (18 seasons) used
  for Absolute Impact expected-production fitting.
- **Confidence level**: Medium-high that MFL's QB/TE gap is a real
  MFL-specific characteristic (now corroborated by 3 additional
  independent sources, not just 1). Low that any single 2025 source is
  ready for canonical promotion.
- **Next experiment**: Direct Sleeper and RTSports acquisition
  (bypassing FFToday's blend), preserving raw ADP rather than derived
  ranks.
