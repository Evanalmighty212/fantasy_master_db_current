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

**Methodology status for the 2025 reconstructed-MFL acquisition-source
methodology and its governed market-participation rules: APPROVED by
Evan.**

**Implementation status for those rules: NOT YET IMPLEMENTED.**

The approved 2025 acquisition source is the strict reconstructed
147-league MFL population described in the decision-history entry below.
It uses raw observed mean picks without normalization, a 35%
ordinary-market participation boundary, and a 30% principal sensitivity.
This season-specific approval does not make MFL the historical backbone
for other seasons. The live source grade and current generated artifacts
still describe the prior implementation; no grade upgrade occurs until
the approved source is preserved, implemented, regenerated, and
validated successfully.

- Primary source (to be determined)
- Secondary validation source
- Automated validation reports
- Manual review only when necessary

---

# Current Source Matrix

| Source | Coverage | Automation | Data Quality | Current Grade | Proposed Role |
|---------|----------|------------|--------------|---------------|---------------|
| nflverse / nfl_data_py | Fantasy results only | A+ | A+ | A+ | Fantasy results backbone |
| Fantasy Football Calculator | Verified: strong 2010 and 2012-2024; 2011 uses the governed pre-kickoff FFToday-hosted FFC snapshot; absent 2008/2009/2025; contaminated 2007/2008-standard | A | B (2010-2024) / F (2007-2008 standard) | B- | Secondary contributor; governed FFToday-hosted FFC snapshot is canonical for 2011 |
| FantasyPros | Historical pages confirmed | Unknown | A | A- (investigating) | Potential primary backbone |
| FFToday | Recent seasons | A | B | B- | Recent-year backup |
| Kaggle datasets | Unknown | TBD | TBD | Pending | Supplemental |
| GitHub repositories | Unknown | TBD | TBD | Pending | Supplemental |
| Internet Archive | Unknown | Low | TBD | Pending | Historical recovery |
| Sleeper | Unknown | TBD | TBD | Pending | Modern validation |
| MyFantasyLeague | Current live evidence: 254 configuration-valid leagues; approved replacement: strict 147-league reconstruction for 2025, not yet implemented | A (isolated diagnostic pipeline) | B (real QB source shift vs. FFToday validation) | B- | Canonical 2025 acquisition source only after implementation and validation; 30% sensitivity retained |
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
- **2010 and 2012-2024: genuinely clean.** Every year has a tight 1-5 day
  collection window in late Aug/early Sept (real preseason snapshots,
  not contaminated with in-season or later-year data). The former
  September 6-9, 2011 600-draft JSON overlaps the NFL kickoff window
  and is now timing sensitivity only; the governed September 4-5
  FFToday-hosted FFC snapshot is canonical for 2011. Usable skill
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
2010 and 2012-2024. The governed FFToday-hosted pre-kickoff FFC
snapshot supplies 2011 instead. Not usable at all for 2007–2009 or 2025 in its current form
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

### Status

🔴 Evaluated (2026-07) -- no usable ADP surface found

### Findings

- `api.sleeper.app` is fully reachable (confirmed live: `GET /v1/state/nfl`
  returns real season-state JSON, HTTP 200) and `robots.txt` places no
  restriction on any crawler, including AI agents.
- No aggregate ADP endpoint exists on the documented public API --
  `api.sleeper.app` exposes player/league/roster/draft-by-id data, not
  a market-wide ADP report. `sleeper.com` has no public `/adp`-style
  consumer page either (`/adp`, `/football/adp`, `/rankings/adp`,
  `/draft/adp` all return HTTP 404).
- Unlike FFC/MFL/RTSports, Sleeper's business is a draft *platform*,
  not an ADP-publishing product -- third parties (e.g. FFToday's
  blended consensus page, see below) apparently derive Sleeper-based
  ranks from Sleeper's own internal/undocumented tooling, not a source
  this project could reach directly and reproducibly.

### Verdict

Not viable as a direct-acquisition candidate -- there is no public data
surface to acquire, reachable or not. Not disqualified by policy or
robots.txt; disqualified because the data doesn't exist where a
reproducible pipeline could reach it.

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

**Superseded decision history.** This investigation originally retained
MFL only as a platform-specific sensitivity. Evan subsequently approved
the stricter 147-league reconstruction as the canonical 2025 acquisition
source. The approved rule is recorded below; its implementation remains
pending.

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

**Superseded decision history.** This pass originally left 2025 without
a canonical source. The later approved strict-reconstruction decision
below supersedes that source-policy conclusion without erasing the
cross-source evidence that motivated its safeguards.

### Next experiment

Direct acquisition from Sleeper's and RTSports' own APIs/exports
(bypassing FFToday's blend entirely) would preserve real per-platform
ADP methodology and, ideally, raw mean-pick values rather than derived
ranks -- not attempted in this pass. This is the most promising
concrete next step if 2025 ADP resolution is revisited later.

---

## RTSports

### Status

🔴 Evaluated (2026-07) -- real ADP surface found, but blocked on two
independent grounds

### Findings

- `rtsports.com/adp` (allowed by `rtsports.com/robots.txt` for general
  crawlers) redirects (HTTP 302) to
  `www.freedraftguide.com/fantasy-football/average-draft-position` --
  RTSports' actual ADP product lives on its sister site
  "Free Draft Guide," not on rtsports.com itself. This is the real
  source behind the "RT" column in FFToday's modern consensus page
  (confirmed via the literal `<a href="https://rtsports.com/">RTSports</a>`
  credit link in the captured FFToday HTML).
- **`freedraftguide.com/robots.txt` explicitly disallows `ClaudeBot`
  from the entire site** (`User-agent: ClaudeBot` / `Disallow: /`),
  alongside several other named AI crawlers (GPTBot, CCBot, Bytespider,
  Google-Extended, Applebot-Extended, Amazonbot, meta-externalagent).
  One page fetch happened in the same investigative pass as the
  robots.txt check itself (both run together before the disallow was
  confirmed); no further requests were made once it was, and none
  should be -- this is a real, explicit, site-owner restriction
  targeting AI agents specifically, not a technical obstacle to route
  around with a different identity or tooling. If this source is ever
  pursued, it would need a human-run, manual acquisition process, not
  an automated fetch by this or any AI agent -- a decision for Evan to
  make, not something to build a workaround for.
- Independent of the robots.txt question, the page fetched is titled
  "2026 ADP" -- a live, continuously-updating current-season number
  (the same "not a frozen historical artifact" problem this project
  already rejected MFL's raw aggregate report for), not a preserved
  2025 preseason snapshot. Even a permitted fetch today would not
  reproduce what the market looked like before 2025's actual draft
  season.

### Verdict

Not viable as a direct-acquisition candidate for this project, on two
independent grounds: (1) the actual data lives behind an explicit
ClaudeBot/AI-crawler disallow on freedraftguide.com, which this project
respects rather than works around; (2) the page itself is a live
current-season aggregate, not an archived 2025 snapshot, so even
permitted access wouldn't solve the reproducibility problem this
project requires.

### A frozen, single-platform RTSports snapshot already exists in-repo

FFToday's already-captured 2025 page (dated 8/29/25, see the FFToday
section above) embeds RTSports' own standalone rank as one of its three
source columns (`rtsports_rank` in
`research/diagnostics/adp_2025_investigation/parsed/fftoday_2025_ppr_consensus.csv`)
-- 248/283 players covered, 28 QB and 27 TE specifically. This is a
real, dated, single-platform (not blended) RTSports data point,
legitimately obtained via FFToday (which permits automated access),
without touching freedraftguide.com at all. It's still a derived
integer rank, not raw mean-pick ADP, so it doesn't resolve the
scale-compatibility problem on its own -- but it is a genuine,
already-available independent validation point for any MFL correction
work, separate from the 3-source blended `avg_rank`.

### Manual recovery requirements, if pursued

Not attempted here (RTSports' AI-crawler restriction is respected, not
worked around; the below is a specification, not an executed fetch).
For an RTSports/Free Draft Guide 2025 snapshot to be usable:

1. **Must be dated to the 2025 preseason window** (ideally within a
   week or two of the 2025-08-15-to-kickoff convention already used
   elsewhere in this pipeline), not today's live "2026 ADP" page.
2. **Must disclose its own methodology** -- a real mean-pick ADP with a
   stated number of real drafts (like MFL's `n_drafts`), not an
   undisclosed-methodology rank, to actually resolve (not just
   relocate) the scale-compatibility problem.
3. **A Wayback Machine snapshot is the most plausible avenue** --
   `archive.org`'s own `robots.txt` places no AI-crawler restriction
   (confirmed directly), so checking `web.archive.org` for an archived
   copy of `rtsports.com/adp` or the freedraftguide.com ADP page is not
   the same restricted action as fetching freedraftguide.com live. One
   precedent snapshot was found for `rtsports.com/adp` from **2023-08-11**
   (same redirect behavior as today) via the Wayback CDX API, which is
   encouraging -- Wayback appears to have crawled this exact page
   around past preseasons. A specific 2025-dated snapshot was not
   confirmed either way this session (the CDX API returned inconsistent
   503s/timeouts under repeated querying, not a "no results" answer) --
   checking `https://web.archive.org/web/2025*/https://rtsports.com/adp`
   directly in a browser is the concrete next manual step, not
   something this pass resolved.
4. **If no 2025 snapshot exists**, a dated export or CSV Evan obtains
   directly from RTSports/Free Draft Guide (e.g. a support request, a
   paid historical-data product, or any other human-mediated channel)
   would need the same two properties above -- 2025-dated, disclosed
   methodology -- to be usable, independent of how it's obtained.

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
| 2010 | ⭐⭐⭐⭐☆ | FFC VERIFIED clean; needs a secondary source layered in to reach 250 |
| 2011 | ⭐⭐⭐⭐☆ | Canonical source is the newly preserved byte-identical copy of the audited FFToday-hosted FFC 12-team PPR snapshot: 374 drafts from Sept. 4-5, SHA-256 `dd26ad40eecab0e3882b4cb9dce3521e7da2c41431ed77db1c3e58f9158d58f0`, 61,275 bytes. The Sept. 6-9 / 600-draft JSON is timing sensitivity only. |
| 2012-2024 | ⭐⭐⭐⭐☆ | FFC VERIFIED clean -- 92-187 usable skill players/year, needs a secondary source layered in to reach 250 every year |
| 2025 | ⭐⭐☆☆☆ | FFC confirmed absent. The live grade remains unchanged while the strict reconstructed 147-league MFL population is APPROVED as future canonical acquisition evidence but NOT YET IMPLEMENTED or production-validated; FFToday's August 29 consensus remains independent validation only. See the 2026-08 decision entry. |

**2011 implementation status: ADAPTER IMPLEMENTED; PRODUCTION REGENERATION NOT YET RUN.** The production clean-ADP path now validates and parses the governed private snapshot. Existing production artifacts still reflect the prior input until an explicitly authorized regeneration.

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

### 2026-08 -- Governed pre-kickoff 2011 FFToday/FFC snapshot

**Methodology status: APPROVED by Evan.**

The canonical 2011 acquisition source is a newly preserved copy whose
bytes are exactly identical to the previously audited FFToday-hosted
Fantasy Football Calculator snapshot. It is 12-team PPR, covers 374
drafts from September 4-5, 2011, is 61,275 bytes, and has SHA-256
`dd26ad40eecab0e3882b4cb9dce3521e7da2c41431ed77db1c3e58f9158d58f0`.
This establishes byte identity with the audited snapshot; it does not
claim recovery of the earlier controlled-storage package.

The existing `data/raw/adp/ffc_adp_2011_ppr.json` covers 600 drafts
from September 6-9. Because that window overlaps the NFL kickoff, it
is retained only as a separately named timing sensitivity and must not
be substituted for the canonical pre-kickoff snapshot.

---

### 2026-08 -- Strict reconstructed MFL approved for canonical 2025 acquisition cost

**Methodology status: APPROVED by Evan.**

**Implementation status: NOT YET IMPLEMENTED.**

The approved future canonical 2025 source is the governed 147-league
reconstruction, pending implementation and production validation:
real completed drafts, 12 teams, PPR/redraft-report-discovered,
configuration-verified single-QB, non-IDP, non-salary, 14--18 roster
spots, and complete through configured roster size. Configurations with
`bestLineup=Yes` or missing status are excluded as a conservative
best-ball proxy; MFL cannot prove managed-league status perfectly. The
window ends at the actual NFL opening kickoff, September 4, 2025 at
8:20 p.m. Eastern / September 5 at 00:20 UTC, superseding the earlier
cutoff that ended about 24 hours too soon.

Raw observed MFL mean picks are used without normalization.
`ordinary_market` requires participation in at least 35% of governed
drafts; 30% is the principal sensitivity. Observed players below 35%
are `rare_minimal_market`, with conditional picks and participation
evidence preserved. Absence from all complete governed drafts supports
zero participation in this population but never a fabricated numeric
ADP. FFToday's August 29, 2025 12-team PPR consensus is independent
validation only and is never blended. The source disclosure must state
that MFL QBs were selected approximately 15 overall picks earlier than
the FFToday consensus, while RB/WR pricing and within-position ordering
were much closer. The source bytes, reconstruction version, population
rules, timing, provenance, and hashes must be preserved under the
governed reproducibility policy. Any normalization toward a hypothetical
FFC market requires a separate future methodology decision.

Current generated artifacts and the live source grade still represent
the prior implementation. Neither changes until governed preservation,
implementation, coherent regeneration, and validation succeed.

The approved general market-status architecture is
`ordinary_market`, `rare_minimal_market`, and
`participation_unknown`, with raw source observations and provenance
kept separately. Michael Vick 2010 has
`preseason_market_status = rare_minimal_market`; his downstream
acquisition/scoring treatment is categorical minimal market cost.
Observed overall ADP, positional ADP, draft round, and draft pick all
remain null. The retrospective 14th-round draft-do-over rationale is
superseded. Implementation must use the general evidence-based MMC
mechanism rather than a Vick-specific exception. Thus "undrafted in
the ordinary market" does not mean the governed status
`ordinary_market`.

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

### 2026-07 -- Stars-by-Value no-ADP-match remediation (targeted, 2010-2024)

- **Date**: 2026-07
- **Trigger**: Stars-by-Value implementation-readiness review found that
  111/823 (13.5%) of 2010-2024 elite-tier player-seasons (top-15 PPG at
  position, >=8 games) have `data_quality_flag = no_adp_match` and are
  therefore permanently ineligible for the Star label, including
  historically prominent seasons (Adrian Peterson 2012, Justin Herbert
  2020, Odell Beckham Jr. 2014, Puka Nacua 2023, Victor Cruz 2011).
  This entry documents a **targeted** remediation pass on the
  highest-impact cases -- not a full audit of all 111 rows.
- **Method**: for each targeted case, checked (1) `missing_adp_matches.csv`
  / `low_confidence_player_matches.csv` for an existing-but-unmatched ADP
  row, (2) the raw canonical `ffc_api_ppr_VERIFIED` source file directly
  for that season (player-name search across the full JSON, not just the
  matched subset), (3) where neither found the player, targeted external
  research (WebSearch/WebFetch) for a real, dated, source-quality
  historical ADP consensus -- never a single writer's subjective ranking.

**Resolved via existing-source matching fix** (override table,
`data/manual/player_name_overrides.csv`):

| Player | Season(s) | Cause | Fix |
|---|---|---|---|
| Mike Vick (nflverse `00-0020245`) | 2009, 2011, 2012, 2013 (2010-2024 scope: 2011-2013) | Category 1 -- name mismatch. ADP source spells him "Michael Vick"; nflverse stats use "Mike Vick." Fuzzy match scored 76.19, below the 80 review floor (`Michael`->`Mike` is a real nickname variant, not a typo the matcher is tuned to catch) | Added 4 rows to the override table, one per season, each citing the exact source/overall_adp/fuzzy-score evidence. Verified by rerunning `scripts/player_matching.py`: all 4 rows now resolve via `manual_override` at 100% confidence; 0 remaining Vick rows in `missing_adp_matches.csv`. |

Impact of the Vick fix: only the 2011 season (round 1, ADP 8.9) clears
the production gate (P=173.6 > QB floor 142.6); 2012 (P=124.4) and 2013
do not. Estimated against the existing round-1 QB `E_P` (~205, n=3 in
the current fit), 2011's score comes out near ~102 -- well below any
QB candidate cutoff. This is a correct, not a disappointing, result:
2011 Vick was a well-known real-world value bust relative to his
inflated post-2010-comeback ADP, and the fix correctly shows that
rather than manufacturing a new Star.

**Investigated, no existing-source fix available, external research
attempted, no qualifying source found**:

| Player-season | Canonical source checked | Found in source? | External research result | Classification | Status |
|---|---|---|---|---|---|
| Adrian Peterson 2012 | `ffc_adp_2012_ppr.json` (93 players, explicitly flagged `THIN_YEAR` in `ADP_SEASON_SOURCE_PLAN.csv`) | No | ESPN "Statuesday" column (Ken Daube, published 2012-08-08, `espn.com/fantasy/football/ffl/story?page=nfldk2k12_decisionspeterson`) gives only a single writer's subjective positional rank (RB11, recommended up to RB7) -- not an aggregated draft-position consensus. Does not meet this project's source-quality bar. | 3 (beyond reliable source depth) / 4 (no usable canonical ADP found) | Unresolved |
| Justin Herbert 2020 | `ffc_adp_2020_ppr.json` (203 players) | No | Multiple searches found only 2021 ADP data (32.42, QB4) for Herbert; no 2020 preseason figure exists in indexed sources -- consistent with him being a non-starting rookie backup (Tyrod Taylor was the starter) with no real preseason fantasy relevance that year. | 5 (genuinely no preseason draftable relevance) | Unresolved |
| Victor Cruz 2011, Odell Beckham Jr. 2014, Puka Nacua 2023 | Respective `ffc_adp_*_ppr.json` (188-202 players each) | No | Not independently re-searched externally this pass (time-boxed to the two cases above as representative) -- pattern-consistent with Herbert 2020 (real UDFA/rookie-breakout stories where a genuine lack of preseason ADP is the more likely explanation than a data gap). Flagged explicitly as un-verified, not confirmed. | 5 (probable, not confirmed) | Unresolved |
| Mike Vick 2010 | `ffc_adp_2010_ppr.json` (214 players) | No | **SUPERSEDED HISTORY:** this pass had not yet completed the later evidence review. The approved 2026-08 ruling now uses the general evidence-based rare/minimal-market mechanism. | 5 (probable, not confirmed in this pass) | Superseded by approved `preseason_market_status = rare_minimal_market`; categorical minimal-market-cost treatment; observed overall/positional ADP, draft round, and draft pick remain null |

- **Decision**: No new ADP source promoted to canonical or
  sensitivity-only status for any of these six cases -- nothing found
  cleared the bar. Per explicit instruction, no ADP was invented to
  make a famous season eligible. The wider 237-row "clears the p82.5
  gate outright" population (2010-2024, `no_adp_match`) was
  deliberately NOT audited beyond this targeted set.
- **Confidence level**: High that the Vick fix is correct (verified by
  rerun, not just reasoned about). Medium that AP 2012 and Herbert 2020
  are genuinely source-absent rather than a fixable gap -- the negative
  result is real but the search was not exhaustive. Low/unverified for
  Cruz 2011, OBJ 2014, Nacua 2023, and Vick 2010, which were reasoned
  by pattern rather than individually searched.
- **Next experiment**: if this population is revisited, prioritize a
  from-scratch search (not reasoning by analogy) for Cruz 2011, OBJ
  2014, and Nacua 2023 specifically, since rookie/UDFA breakout seasons
  are exactly the case where a real but obscure preseason ranking
  (rather than a true absence of one) is most plausible.

---

### 2026-07 -- No-ADP remediation, part 2: individual verification + drafted-vs-undrafted classification

- **Date**: 2026-07
- **Trigger**: the prior entry's "Next experiment" -- replace pattern-based
  reasoning with real, individual, per-player source research for the
  five cases still marked "probable, not confirmed," and explicitly
  separate two different questions the prior pass conflated: (1) was
  the player genuinely drafted but our evidence/matching is missing,
  vs. (2) was the player genuinely undrafted / outside reliable source
  depth. Adrian Peterson 2012 was revisited only because a promising
  new avenue (MyFantasyLeague as a second real ADP provider, surfaced
  by the Odell Beckham Jr. research below) appeared -- not re-searched
  from scratch on the original ESPN-only lead.

**Revised classification** (four categories, per instruction: confirmed
drafted with usable ADP / clearly drafted but usable ADP still missing
/ likely genuinely undrafted or outside normal draft depth / ambiguous):

| Player-season | Classification | Real-world evidence found | Primary-source verification |
|---|---|---|---|
| Mike Vick 2010 | **SUPERSEDED/CORRECTED HISTORY:** formerly classified as clearly drafted with usable ADP missing; the approved 2026-08 ruling is `preseason_market_status = rare_minimal_market` with categorical minimal-market-cost treatment | This investigation originally misread NFL.com's retrospective "2010 Fantasy draft do-over" as contemporaneous acquisition evidence. It was a post-season draft-do-over and is not valid preseason ADP evidence. The approved ruling instead rests on the governed evidence-based rare/minimal-market mechanism. | Observed overall ADP, positional ADP, draft round, and draft pick remain null. No numeric value is inherited from the article, estimated, or fabricated. |
| Adrian Peterson 2012 | Clearly drafted, usable ADP still missing (strongest of the three "missing" cases) | Bleacher Report's "Complete Fantasy Profile & Draft Strategy" cites, by name, "a 2012 average draft position of 20.69" attributed to **FFToolbox.com** -- a real named ADP aggregator, not a personal ranking (contrast with the previous pass's ESPN opinion-column finding, which this supersedes as the better lead). | Could not reach FFToolbox's own 2012 archive (site has since migrated to fulltimefantasy.com and no longer lists a 2012 page); Wayback Machine unreachable from this environment. The number is real and named but not independently re-derived from a primary table. |
| Odell Beckham Jr. 2014 | Clearly drafted, usable ADP still missing | A FoxSports "risks and rewards of rookie WRs" piece states "Beckham was a late-round flier at best" and links directly to a real (now-dead) MyFantasyLeague.com 2014 ADP query URL -- confirming a real MFL consensus existed for him that year. | The linked MFL query (`www03.myfantasyleague.com/2014/adp?...`) 404s today; no specific number recovered, only the qualitative "late-round" characterization. |
| Victor Cruz 2011 | Likely genuinely undrafted / outside normal draft depth | His famous breakout preseason game was August 2010 (his rookie year), not 2011 -- he then missed his entire 2010 season with a hamstring injury, so he entered the 2011 preseason with zero NFL production and a year-old, mostly-forgotten highlight. Real-world context supports minimal 2011 preseason relevance. | This historical audit used the repo's `ffc_adp_2011_ppr.json` (188 players, 600 drafts, Sept. 6-9) plus a live FFC page. That JSON is now timing sensitivity only; it is not the canonical 2011 source. |
| Justin Herbert 2020 | Likely genuinely undrafted / outside normal draft depth | Real backup to Tyrod Taylor entering 2020 (not his own team's starter); no 2020 ADP found anywhere searched (only 2021 data exists, ADP 32.42/QB4, confirming 2020 fantasy irrelevance rather than a data gap). | Absent from FFC's 203-player 2020 canonical file; no external source of any kind found. |
| Puka Nacua 2023 | Likely genuinely undrafted / outside normal draft depth | 5th-round NFL pick (177th overall), unremarkable college production ("barely topping 800 receiving yards in his best season"), explicitly characterized as an "unheralded rookie" in dedicated post-hoc breakout-rookie coverage. | Absent from FFC's 202-player 2023 canonical file; no external ADP source of any kind found. |

Net effect on the prior pass's classification: **Odell Beckham Jr. 2014
moves from "unresolved / pattern-reasoned category 5" to "clearly
drafted, ADP missing"** -- a real, materially different conclusion
from individual verification, which is exactly why the "Next
experiment" note called for it instead of continuing to reason by
analogy. Cruz, Herbert, and Nacua's category-5 classifications are
now backed by real (if not exhaustive) verification rather than
pattern-matching alone.

- **Decision**: No ADP was invented or backfilled into canonical or
  override data for any of these six cases. Vick's existing override
  rows and the ADP_SOURCE_MATRIX entry above remain **unstaged**,
  held pending review of the undrafted-baseline question below --
  they are not superseded by this entry, just not yet acted on further.
- **Confidence level**: High for Cruz 2011 (only case with independent
  corroboration via a live-source refetch, not just the repo snapshot).
  Medium-high for Herbert 2020 and Nacua 2023 (real-world context is
  strong, absence from source is confirmed, but no second source was
  checked). This pass recorded medium confidence for Vick 2010, AP 2012,
  and OBJ 2014 as "drafted but missing." **That Vick conclusion is
  superseded/corrected by the approved 2026-08 ruling**; the retrospective
  draft-do-over was not valid preseason acquisition evidence.
- **Next experiment**: if AP 2012's FFToolbox number is ever needed for
  real, contact FFToolbox/FullTimeFantasy directly or find a
  third-party citation that reproduces the underlying table (not just
  the summary number) -- do not treat a single restated number from a
  secondary article as canonical-quality on its own.

---

### 2026-07 -- No-ADP remediation, part 3: scalable classifier + MFL feasibility

- **Date**: 2026-07
- **Trigger**: hand-researching 6 players individually doesn't scale to
  the 237-380-row unresolved population. This entry investigates (1) a
  reproducible rule-based classifier for drafted-but-missing vs.
  genuinely-undrafted, built from existing/reachable data, and (2) MFL
  as a second historical ADP provider, superseding the "not
  independently searched" caveats on Cruz/Herbert/Nacua from part 2.

**Classifier**: built from `players.csv` (real NFL draft round/pick,
rookie season) from nflverse's `players` GitHub release -- reachable
directly from this environment (verified: `curl` to
`github.com/nflverse/nflverse-data/releases/download/players/players.csv`
succeeds; not yet wired into any pipeline script, downloaded to
scratch space only) -- joined against this project's own
`master_historical_db` for prior-season production. Rules, in order:
QB + rookie season -> likely_undrafted; UDFA or Day-3 NFL rookie at a
skill position -> likely_undrafted; Day 1-2 NFL skill-position rookie
-> likely_drafted_missing_evidence; established veteran (2+ years in,
real production in the last 3 seasons) -> likely_drafted_missing_evidence;
everything else -> ambiguous.

Validated against the 6 then-current hand-researched ground-truth cases:
**5/6 correct**. This historical validation predates the corrected
2026-08 Vick evidence ruling. The miss (Mike Vick 2010) lands in the safe "ambiguous"
bucket, not a confidently wrong one -- his last real production before
2010 was 2006, because he missed 2007-2008 entirely (incarceration),
four years outside even an extended 3-year lookback. Deliberately not
patched further: 6 examples is too small a set to keep tuning rules
against without overfitting.

Applied to the full 237-row "clears the gate outright" unresolved
population: **149 likely_drafted_missing_evidence, 64 ambiguous, 24
likely_undrafted.**

**A real, verified classifier error, found by spot-checking real
names, not the ground-truth set**: Andrew Luck 2012 and Russell Wilson
2012 both hit the "QB + rookie -> likely_undrafted" rule, but both
were real **Week-1 starters** (verified against nflverse's
`depth_charts_2012.csv`, `depth_team=1` for both), unlike Herbert 2020
and Watson 2017 (`depth_team=2`, real backups, correctly classified).
A rookie QB who wins the starting job outright is a meaningfully
different case from one who doesn't -- the current rule conflates
them. Depth-chart data (`nflverse-data` release `depth_charts`, also
directly reachable, per-season files back to 2001) is the fix, but was
only pulled for the 6 ground-truth seasons this pass, not integrated
across the full population. Separately, depth-chart status was tested
as a general drafted-vs-undrafted signal and found **weak** for that
purpose -- Vick 2010, OBJ 2014, Cruz 2011, Herbert 2020, and Nacua
2023 all showed `depth_team=2` (backup) in their target week despite
being real, different draft-cost cases; it only adds value for the
specific rookie-QB-starter sub-case above.

**MFL feasibility**: MFL's API (`api.myfantasyleague.com/{year}/export?TYPE=adp`)
is directly reachable and, critically, **the `PERIOD` parameter
matters enormously and was not obvious up front**. The unparameterized
default report is NOT a clean preseason snapshot for recent years --
it blends in-season and post-breakout draft activity. Confirmed
directly: Nacua 2023's default-report rank was 135 (46% draftSelPct);
with `PERIOD=AUG15` (a true preseason snapshot, comparable to this
project's own FFC methodology) his real rank was 209 (18%
draftSelPct) -- a materially different, more honest number. **All
results below use `PERIOD=AUG15`.**

| Season | Available? | Total AUG15 drafts | Target player's AUG15 result |
|---|---|---|---|
| 2007-2010 | No -- 0 real drafts at any PERIOD | -- | Vick 2010 NOT resolvable via MFL |
| 2011 | Yes | 7,098 | Victor Cruz: rank 268, avg pick 151.4, selected in 6% of drafts |
| 2012 | Yes | 8,913 | Adrian Peterson: rank 15, avg pick 22.81, selected in 77% of drafts |
| 2014 | Yes | 11,942 | Odell Beckham Jr.: rank 189, avg pick 126.4, selected in 61% of drafts |
| 2020 | Yes | 5,892 | Justin Herbert: rank 158, avg pick 120.0, selected in 17% of drafts |
| 2023 | Yes | 7,923 | Puka Nacua: rank 209, avg pick 123.0, selected in 18% of drafts |

MFL's real historical ADP data begins in **2011** (2007-2010 return
`totalDrafts: 0` at every PERIOD tested) -- a clean, disclosed
boundary, not a gap to work around.

**Does this resolve the 5 named gaps?** Four cleanly, one confirms the
"unresolvable" finding rather than reversing it:
- **Adrian Peterson 2012 and Odell Beckham Jr. 2014**: CONFIRMED
  drafted with a real, primary, reproducible number (not a secondary
  citation) -- AP's 22.81 corroborates the earlier FFToolbox 20.69
  finding closely. This resolves both from "clearly drafted, ADP
  missing" to "confirmed drafted with usable ADP," pending a decision
  on canonical vs. sensitivity-only status.
- **Victor Cruz 2011, Justin Herbert 2020, Puka Nacua 2023**: MFL
  reveals these are not perfectly binary "zero real relevance" cases
  -- each was selected in a small but real minority of drafts (6-18%).
  This is genuinely more precise than "likely genuinely undrafted,"
  and matches the classification wording this project already
  chose ("outside normal draft depth") better than a hard undrafted
  claim would.
- **Mike Vick 2010 -- superseded/corrected history**: MFL does not
  cover 2010, and the retrospective NFL.com "14th round" draft-do-over
  is not preseason acquisition evidence. The later approved 2026-08
  ruling uses the general evidence-based rare/minimal-market mechanism:
  `preseason_market_status = rare_minimal_market`, categorical minimal-
  market-cost treatment, and null observed overall ADP, positional ADP,
  draft round, and draft pick.

**Compatibility caveat, not yet resolved**: this project's own prior
2025 MFL investigation (see the "2025 Cross-Source Validation" entry
below) already found MFL drafts QBs measurably earlier than every
other source checked (ESPN, FFToday, FFC), for reasons that
investigation could not fully explain. Justin Herbert 2020's MFL
number should be read with that in mind -- it may still run early
relative to what FFC would have shown, even after correcting for the
PERIOD contamination above. This caveat does not apply to the
non-QB cases (Peterson, Beckham, Cruz, Nacua).

**Reproducibility**: yes, cleanly -- `mfl_client.py` (already built
for the 2025 investigation) already implements exactly the caching,
rate-limiting, and retry discipline this would need; the only change
is a year parameter and always specifying `PERIOD=AUG15` explicitly
(never relying on the default). Not yet wired into any pipeline script
-- this pass queried the raw API directly and cached responses to
scratch space, not `data/raw/`.

**Is a reliable `verified_undrafted` category realistically
achievable?** More achievable than part 2 concluded, but still not
solved: MFL's `draftSelPct` (percent of real drafts that selected a
player) is a genuinely useful **graduated** signal -- far better than
guessing at a hard binary -- and combined with (a) confirmed absence
from FFC's canonical source and (b) classifier-bucket agreement, a
defensible `verified_undrafted` definition might be: FFC-absent AND
MFL AUG15 `draftSelPct` below some low threshold (e.g. 20%) AND
classifier bucket is `likely_undrafted`. That is a real, three-way
corroboration design, not yet built or threshold-tuned. It still
cannot reach players outside MFL's 2011+ coverage (Vick-2010-style
cases) or QB-position cases without correcting for MFL's own
documented QB bias first.

- **Decision**: No baseline assigned, no override or canonical data
  changed. Vick's override rows and prior `ADP_SOURCE_MATRIX.md`
  entries remain unstaged. This entry documents feasibility findings
  only.
- **Confidence level**: High that MFL AUG15 data is usable and
  meaningfully more precise than what part 2 had (verified via a
  worked example -- the PERIOD contamination check -- not just
  asserted). Medium on the specific numbers reported above pending a
  second independent check (only one MFL query per player was run;
  not cross-validated against a third source). Low on QB compatibility
  specifically, pending the documented MFL QB-early-bias question
  being resolved.
- **Next experiment**: (1) integrate `depth_charts` into the
  classifier for the full population, not just the 6 ground-truth
  seasons, to fix the rookie-QB-starter gap; (2) if MFL is pursued
  further, resolve the QB-early-bias compatibility question before
  trusting any QB-position MFL number at face value; (3) formalize and
  threshold-tune the three-way `verified_undrafted` corroboration
  design above on a larger labeled sample before treating it as
  reliable.

---

### 2026-07 -- No-ADP remediation, part 4: corroborated framework built and tested

- **Date**: 2026-07
- **Trigger**: build and test the three-way corroboration design part 3
  proposed but didn't implement; fix the rookie-QB classifier gap;
  narrowly test the MFL QB bias on prevalence specifically (not exact
  cost); compare -- without assigning -- minimal-market-cost treatment
  options.

**1. Classifier correction (narrow, as scoped)**: identified all 9
rookie-QB candidates in the 380-row unresolved population, pulled
`depth_charts` for their specific seasons (2012, 2015, 2017-2020,
2023), and checked real Week-1 `depth_team` status. 4 were verified
Week-1 **starters** (Andrew Luck 2012, Russell Wilson 2012, Jameis
Winston 2015, C.J. Stroud 2023) and moved from `likely_undrafted` to
`ambiguous` -- the other 5 (Herbert 2020, Watson 2017, Allen 2018,
Jones 2019, Minshew 2019) were verified real backups and correctly
stay `likely_undrafted`. Not expanded to any other position or rule.
Full-population bucket counts (380 rows): `likely_drafted_missing_evidence`
243 (unchanged), `ambiguous` 106 (+4), `likely_undrafted` 31 (-4).

**2. Three-way corroboration, built and threshold-swept**: combined
(a) absence from FFC canonical, (b) MFL `PERIOD=AUG15` `draftSelPct`,
(c) the corrected classifier, for all 222 gate-clearing 2011-2024
unresolved candidates (2010 excluded -- no MFL data exists for it).
Matched 216/222 to a real MFL player record by normalized name
(4 players excluded as unresolvable name collisions -- e.g. two real
"Steve Smith"s at WR in the same era -- same category of ambiguity
already documented for FFC matching, not guessed at).

Threshold sweep on the 7 named cases (draftSelPct shown, ABOVE/below
a candidate boundary):

| Player | draftSelPct | 5% | 10% | 15% | 20% | 25% | 30% |
|---|---|---|---|---|---|---|---|
| Adrian Peterson 2012 | 77.2% | ABOVE | ABOVE | ABOVE | ABOVE | ABOVE | ABOVE |
| Odell Beckham Jr. 2014 | 61.3% | ABOVE | ABOVE | ABOVE | ABOVE | ABOVE | ABOVE |
| Andrew Luck 2012 | 94.0% | ABOVE | ABOVE | ABOVE | ABOVE | ABOVE | ABOVE |
| Russell Wilson 2012 | 58.3% | ABOVE | ABOVE | ABOVE | ABOVE | ABOVE | ABOVE |
| Justin Herbert 2020 | 17.9% | ABOVE | ABOVE | ABOVE | below | below | below |
| Puka Nacua 2023 | 18.5% | ABOVE | ABOVE | ABOVE | below | below | below |
| Victor Cruz 2011 | 6.7% | ABOVE | below | below | below | below | below |

Four of seven are robust to threshold choice across the whole tested
range (Peterson, Beckham, Luck, Wilson all sit far above any
reasonable boundary -- Luck and Wilson's real MFL presence also
retroactively validates the classifier correction in part 1 well
beyond just "not backups"). The real decision is in a narrow band:
Cruz separates from the other two around 10%, Herbert/Nacua separate
around 20% -- **20% is the first threshold that groups all three
low-signal cases together**, which is the basis for using it as the
primary value below.

**Final 3-category bucket counts** (threshold=20%, 222 candidates):
**107 confirmed_or_likely_drafted, 54 minimal_market_cost, 47
ambiguous_disagreement** (classifier and MFL genuinely conflict -- not
resolved by design, flagged rather than guessed), plus 10
MFL-unmatched (fall back to classifier alone, lower confidence) and 2
classifier-ambiguous-with-no-MFL-signal. At threshold=15%:
118/50/40 unmatched-adjusted; at 25%: 99/55/54. **The
ambiguous-disagreement count grows with the threshold** (40 at 15% ->
54 at 25%) -- raising the bar to call something "confirmed drafted"
mechanically produces more disagreement with a classifier that was
tuned independently, not more resolution. This is real friction
between the two signals, disclosed rather than smoothed over.

**Risks**:
- **False positive** (calling minimal-cost players "confirmed
  drafted"): mainly a QB-position risk, per the bias test below.
- **False negative** (calling real draft-cost players "minimal
  market cost"): mainly a threshold-too-low risk (setting the bar
  under ~15% would have called Herbert and Nacua minimal-cost despite
  real, if modest, market presence) and an early-year MFL-thinness
  risk (2011's 7,098 total drafts is MFL's thinnest year with usable
  data -- prevalence estimates from it carry more sampling noise than
  2020+'s 15,000-17,000-draft years).
- **Unresolved risk**: the 47 ambiguous_disagreement rows (21% of the
  222) are not a small residual -- a real chunk of the population
  still has no reliable answer from this framework.

**3. MFL QB bias, tested narrowly on prevalence (not reopening the
2025 investigation)**: compared MFL `draftSelPct` for REAL,
FFC-confirmed players at the same real ADP round (10-15), by position,
2011-2024, n=747 matched. **Result: the bias is not confined to exact
rank/cost -- it measurably affects prevalence too.** At round 15
specifically: QB median draftSelPct 58.1% vs. RB 28.3% vs. WR 32.8% --
roughly double. The gap is present at every round tested (10 through
15), narrower at shallower rounds, widest at the deepest ones.

**This means the clean distinction proposed going in
("unsuitable for exact cost, but reliable for whether drafted at
all") does not fully hold** -- it needed testing, and testing changed
the answer. The practically important part, though: the bias runs in
one direction only (inflating apparent QB presence), and for the
specific cases in this population, it doesn't flip anything. Herbert's
raw 17.9% is already below the 20% threshold; correcting for a ~1.5-2x
QB inflation would only push his true estimate lower, reinforcing
`minimal_market_cost`, not undermining it. The real practical risk is
for QB rows sitting **close to whatever threshold is chosen** -- those
need either a QB-specific (higher) threshold or a lower-confidence
flag, not the same cutoff used for RB/WR/TE. Not built this pass --
a disclosed follow-up, not a blocker for the framework's non-QB
conclusions.

**4. Minimal-market-cost treatment comparison (no baseline assigned)**:

| Option | Reproducibility | False-precision risk |
|---|---|---|
| A. Dedicated fixed minimal-market-cost expectation (position-specific constant) | High -- one number per position, fully deterministic | Low -- explicitly declines to claim a precise implied round |
| B. Map MFL `draftSelPct` to an implied late round via a continuous function | Medium -- the mapping function itself becomes a new, uncalibrated design question | High -- manufactures false precision from a noisy, now confirmed **position-biased** percentage; directly exposed to the QB-inflation finding above with no correction |
| C. Treat all below-threshold players as the final reliable modeled round | High -- reuses existing infrastructure exactly | Medium-high -- actively **overstates** cost: round-15 QB/RB/WR MFL prevalence (28-58%) is still well above Cruz's actual 6.7%, so this would hand these players more expected credit than the evidence supports, and the deepest modeled round is itself thin (n=1 in the current fit) |

**Assessment**: Option A is both the most reproducible and the least
falsely precise, independent of anyone's preference -- Option B's
weakness is compounded directly by the part-3 finding (a mapping
function would silently bake in the QB bias unless explicitly
corrected, which is extra unbuilt machinery), and Option C
contradicts the graduated MFL evidence gathered this pass by assigning
*more* implied cost than the most marginal cases (6-18% draftSelPct)
actually show. **A dedicated minimal-market-cost category is the
right kind of answer** -- this agrees with the philosophical
preference stated going in, arrived at independently from the
reproducibility/precision comparison, not by deference. What it does
not yet resolve: whether the constant should be position-specific
(very likely, given how differently QB/RB/WR/TE market behavior
showed up in every test this pass) and where to calibrate it -- both
open, undecided design questions, not defaults.

- **Decision**: No baseline assigned, no canonical data changed,
  `config.py` untouched. Vick's override rows and all prior entries
  remain unstaged.
- **Confidence level**: High on the classifier correction (verified
  directly, not reasoned). Medium-high on the corroboration bucket
  counts at threshold=20% (real data, real matching, but 21% of the
  population is honestly unresolved). Medium on the QB-bias-on-prevalence
  finding (n=747, real signal, single test design -- not
  independently replicated a second way).
- **Next experiment**: (1) build the QB-specific threshold or
  confidence-downgrade for the corroboration framework; (2) resolve
  the 47 ambiguous_disagreement rows with a second signal (e.g. a
  third ADP provider, or manual review of the highest-production
  ones) rather than leaving them all as one undifferentiated bucket;
  (3) calibrate the Option-A minimal-market-cost constant(s) if this
  path is chosen -- likely via the same named-case/sensitivity
  process already used for lambda and k.

---

### 2026-07 -- No-ADP remediation, part 5: Option A calibrated (universal vs. position-specific tested, not implemented)

- **Date**: 2026-07
- **Trigger**: calibrate candidate values for the minimal-market-cost
  baseline (Option A, chosen over B/C in part 4) and determine whether
  a universal or position-specific constant is justified -- empirically,
  not by precedent from the rest of this project's position-specific
  defaults.

**Derivation population and a real circularity caveat, disclosed up
front**: the 54-row `minimal_market_cost` bucket (threshold=20%, part
4) is not a clean, unbiased sample -- it only contains players who
already cleared the p82.5 production gate, i.e. **successful**
minimal-cost breakouts. A baseline derived directly from this
population's production would be upward-biased (survivorship), the
same circularity flagged and rejected for "Option 3" two passes ago.
Two anchors were computed instead, and compared:

1. **Empirical bucket percentiles** (survivorship-biased, used only as
   a face-validity cross-check, not a derivation source): QB n=3
   (P10-P75: 176.9-196.7), RB n=8 (132.7-165.9), WR n=12 (100.1-135.1),
   TE n=31 (70.2-107.8).
2. **Replacement-implied P** -- a principled, non-circular anchor:
   for a hypothetical exactly-replacement-level player (rate exactly
   at `replacement_ppg` all season), the production composite reduces
   algebraically to `P = 0.5 x replacement_ppg x G` (the PPG-above-replacement
   term is exactly 0 by construction at replacement rate). Computed
   from `replacement_ppg` averaged over 2015-2024 (the same,
   already-approved, much larger replacement-level population used
   throughout AATP -- NOT the thin 54-row bucket): **QB 133.3, RB
   80.7, TE 67.6, WR 98.6.** Sanity check: this anchor lands almost
   exactly at the TE (66.7) and WR (98.1) p82.5 gate floors, and
   meaningfully below the QB (142.6) and RB (113.7) floors -- consistent
   with TE/WR's gate representing "replacement plus a little" and
   QB/RB's representing a bigger real jump above replacement, a real
   and previously undocumented positional difference, not asserted.

**Universal vs. position-specific, tested by simulating actual scores**
on the 54-row bucket (`Score = P - 0.35 x E_P`, existing settled
lambda) and checking how many would cross their position's own
already-calibrated Star cutoff (QB ~176.5, RB ~188, WR ~171, TE ~134):

| E_P treatment | False positives created | False negatives created |
|---|---|---|
| Position-specific (replacement-implied) | 0 beyond 2 defensible cases (Kyren Williams 2023 RB, Gary Barnidge 2015 TE -- both real, extreme, legitimate outlier breakouts) | None found |
| Universal, set at the pooled average (95.0, pulled toward WR/TE's scale) | **Justin Herbert 2020 incorrectly clears the QB cutoff** (score 179.6 vs. 176.5) -- a player this entire investigation independently found to be a marginal, 17.9%-MFL-selected case, not a Star | -- |
| Universal, set at the pooled bucket median (107.8, pulled toward QB/RB's scale) | -- | **Gary Barnidge's real TE breakout incorrectly fails to clear** (score 129.9 vs. 134) -- a legitimate outlier wrongly excluded |

**No single universal value avoids both failure modes** -- the
position scale gap is too large (TE median raw P ~85 vs. QB ~180,
more than 2x) for one constant to be simultaneously strict enough for
QB and lenient enough for TE. This is concrete, not asserted from the
rest of the project's position-specific precedent.

**Stability**: the thin per-position sample sizes (QB n=3, RB n=8)
that would make a *position-specific empirical percentile* unstable do
**not** apply to the replacement-implied anchor actually recommended --
it's derived from `replacement_ppg`, which comes from the full,
much larger, already-approved replacement-level population, not from
the 54-row bucket. Sensitivity-tested by perturbing all four anchors
+/-30%: completely stable from 0% to +30% (same 2 players clear
throughout); only breaks down on the downward side, first at -20%
(Cruz 2011 starts clearing) and further at -30% (Herbert 2020 and
Nacua 2023 also start clearing) -- i.e. the current calibration point
sits with real margin on the safe side, and the failure direction
(setting the anchor too low) matches exactly the universal-95.0
failure mode found above.

**Conclusion**: position-specific constants are empirically justified,
not merely consistent with precedent -- a universal constant was
shown, concretely, to either falsely promote a real marginal QB
season or falsely suppress a real legitimate TE breakout, and no
single value avoids both. The additional complexity is worth it here.
**Candidate position-specific values (not selected, not implemented):
QB 133.3, RB 80.7, TE 67.6, WR 98.6** (replacement-implied,
2015-2024 basis). Open, undecided: whether to use full-history
(2007-2024) `replacement_ppg` instead of the recent-era window (checked:
QB 14.75 vs 15.68, RB/TE/WR nearly identical -- a minor, not decisive,
choice) and whether the empirical bucket percentiles should inform a
face-validity adjustment on top of the algebraic anchor.

- **Decision**: No baseline assigned, no canonical/config change.
  Everything from this and all prior remediation entries remains
  unstaged.
- **Confidence level**: High that position-specific beats universal
  (concrete, simulated false-positive/negative evidence, not just
  reasoning). Medium on the exact candidate values -- they're
  principled and stability-tested, but not yet run through the same
  named-case face-validity review lambda and k received before being
  treated as settled.
- **Next experiment**: named-case face-validity review of the
  candidate values (the same process used for lambda/k) before
  selecting a final constant; decide the full-history-vs-recent-era
  question; decide whether the two real face-validity clears (Williams,
  Barnidge) should be treated as confirmation the calibration is
  reasonable, or as boundary cases needing their own review.

---

### 2026-07 -- No-ADP remediation, part 6: minimal-market-cost expectation SETTLED

- **Date**: 2026-07
- **Trigger**: part 5's replacement-implied baseline (100% of
  `0.5 x replacement_ppg x G`) was tested against the verified
  minimal-market-cost population and produced real false negatives --
  Herbert 2020, Cruz 2011, and Nacua 2023 all missed their Star cutoff
  despite Herbert finishing top-10 at QB. This entry resolves that by
  re-deriving the baseline from first principles rather than tuning
  the existing one to fit three names.

**Step 1 -- decomposed the false negatives mechanically.** Herbert,
Cruz, and Nacua all have **zero missed-game replacement credit in
their own AATP** (production is 100% real, on-field output) and real
positional finishes (QB9, WR3, WR4) better than either of the two
players the 100% baseline did correctly clear (Williams RB7, Barnidge
TE4). The exclusion was not a marginal statistical fact -- it was the
baseline erasing a real top-10 finish.

**Step 2 -- re-examined the concept.** The question the baseline
should answer is "what preseason production expectation should be
assigned to an effectively free acquisition" -- not "how much does a
replacement-level player produce if rostered and given a role."
`replacement_ppg` is a role-conditional rate (average output *given*
real playing time); a true minimal-cost player's real expectation must
also price in the substantial chance of getting **no meaningful role
at all**. Checked directly for literal double-counting (Kyren
Williams, the one case with real missed-game replacement credit in his
own AATP) and found none -- no arithmetic double-subtraction in any
individual score -- but the conceptual mismatch (conditional rate
treated as unconditional) was real and explains the false negatives
mechanistically, independent of the empirical test.

**Step 3 -- tested a 100/75/50/25/0% scalar sweep on the same
replacement-implied family across all 54 verified minimal-market-cost
players.** 25%, 50%, and 75% produced **identical classifications** --
all five real cases (Williams, Herbert, Cruz, Nacua, Barnidge) qualify,
no false positives anywhere in that range. Only the 0% extreme
introduced a new, marginal case (Nick Foles 2013, by a 4-point
margin) -- evidence that literal zero-expectation goes a step too far,
not evidence for a specific number in between.

**Step 4 -- estimated the scalar as an actual probability, non-circularly**,
rather than picking a point in the stable range by preference. Built
the reference population from **every 2011-2024 `no_adp_match`
QB/RB/WR/TE player-season classified `minimal_market_cost` before
outcome** (n=3,418 -- not the 54 that happened to also clear the
p82.5 gate, which would have reintroduced survivorship bias into the
very estimate being built). Defined "earned meaningful opportunity"
via real usage data (nflverse `stats_player` release, pulled fresh --
attempts/carries/targets, not present anywhere else in this repo),
never fantasy points or the gate: QB attempts >= 100, RB touches
(carries+targets) >= 40, WR/TE targets >= 20. Checked for era drift
(four eras, 2011-14 to 2021-24) -- found none large or monotonic
enough to justify recency weighting, so equal-weighted full history
was used, consistent with this project's standing default.

**Result -- opportunity probabilities**: QB 24.7% (n=413), RB 29.0%
(n=775), TE 28.5% (n=965), WR 36.8% (n=1,265). These land in the
lower part of the already-safe 25-75% range, not at the midpoint --
a uniform "50%" convention would have been a real, avoidable
overstatement given what the data actually shows.

**Final settled constants** (`opportunity_probability x replacement-implied
rate`): **QB 31.0, RB 23.1, WR 35.7, TE 19.3.**

**Sensitivity**: re-derived under three alternative usage definitions
(a looser bar, a stricter bar, and games-played>=8 as a different
signal entirely) -- **identical classification of every named case in
all three**. Only the weakest tested definition (raw games-played>=4,
which doesn't require real usage) gave a different result -- Nacua
missing by 0.52 points -- which argues against that definition, not
against the settled one.

**Decision: SETTLED.** QB 31.0, RB 23.1, WR 35.7, TE 19.3, applied
only to the verified `minimal_market_cost` status group -- never to
`confirmed_or_likely_drafted` (real cost existed, just no recoverable
number) or `ambiguous_disagreement`. Recorded in
`STARS_BY_VALUE_METHODOLOGY.md` section 9. Not yet implemented in
`config.py` or any canonical pipeline -- that remains a distinct,
separate step.
- **Confidence level**: High. Two independent lines of evidence
  (mechanistic/conceptual, and an empirical non-circular estimate)
  converged on the same correction, sensitivity-tested across five
  different opportunity-threshold definitions and a temporal check,
  with no obvious false positive surviving anywhere in the safe range.
- **Next experiment**: none planned for this specific calibration
  absent a new, specific mechanism. Known, disclosed, out-of-scope
  items: the 47 `ambiguous_disagreement` rows (2011-2024) remain
  genuinely unresolved; `confirmed_or_likely_drafted` players (real
  cost, no usable number -- e.g. Adrian Peterson 2012) remain
  permanently unscoreable absent new source-quality ADP evidence;
  Vick 2010 remains outside MFL's coverage entirely.

---

### 2026-07 -- No-ADP remediation, part 7: position-specific Star thresholds SETTLED

- **Date**: 2026-07
- **Trigger**: with the minimal-market-cost expectation settled (part
  6), review whether the provisional position-specific Stars-by-Value
  thresholds (QB ~176.5, RB ~188, WR ~171, TE ~134 --
  `STARS_BY_VALUE_METHODOLOGY.md`, "Named-case calibration and
  narrative-blind validation") still hold given everything learned
  since, without re-opening the already-settled finding that no
  natural breakpoint exists near the plausible region for any
  position.
- **Method**: not a new statistical search -- explicitly a calibration
  review. Checked for (1) obvious false positives/negatives, (2)
  internal consistency with the now-finalized methodology (in
  particular, whether the minimal-market-cost `E_P` values sit in a
  sensible position relative to the round-based `E_P` curve they now
  coexist with), and (3) whether each position's label would be
  defensible to another researcher.
- **Findings**: Herbert 2020, Cruz 2011, Nacua 2023, Kyren Williams
  2023, and Gary Barnidge 2015 -- the five real cases that motivated
  the minimal-market-cost recalibration in part 6 -- all clear their
  position's *existing, unchanged* threshold by wide margins (+13.4 to
  +44.6 points) once scored under the settled section-9 constants. No
  other verified minimal-market-cost player clears any threshold.
  The minimal-market-cost `E_P` values (19.3-35.7) sit below even the
  deepest real round's `E_P` (~84 for QB round 15, thin sample) --
  the correct direction, confirming no overlap/inconsistency between
  the two `E_P` sources that now share the same score formula and
  cutoffs. QB and WR retain more genuine boundary ambiguity than RB
  and TE (unchanged from prior calibration passes -- not worsened,
  not resolved, by this check). No obvious false positive or false
  negative found anywhere.
- **Decision: SETTLED.** QB 176.5, RB 188, WR 171, TE 134, unchanged
  from the provisional values. Treated as calibration choices
  supported by face validity, sensitivity analysis, narrative-blind
  review, a confirmed absence of any natural breakpoint, and this
  pass's reinforcement check -- not as discovered natural breakpoints.
  This also formally closes the cross-position raw-score problem
  flagged early in the Stars-by-Value methodology work: position-specific
  thresholds were always the intended fix, and this pass confirms they
  work correctly across both populations that now feed the same score
  formula, not just the one they were originally calibrated against.
  Recorded in `STARS_BY_VALUE_METHODOLOGY.md` section 10.
- **Confidence level**: High. No genuinely new evidence surfaced that
  argues for moving any of the four values; the reinforcement check
  was a real test (the five named cases could have landed close to
  their cutoffs and didn't) rather than a formality.
- **Next experiment**: none planned for the thresholds themselves
  absent a new, specific mechanism. The label schema question below
  (how the three status groups map into an actual label column) is
  the next real design decision, not a reason to revisit these values.

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

---

### 2026-07 -- Direct Sleeper/RTSports acquisition attempted, both blocked

- **Date**: 2026-07 (immediate follow-up to the entry above; 2025
  integration is now a blocking prerequisite for the SBV orchestration
  commit, not deferred work -- see
  `research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md` section 2a/13)
- **Evidence**: live probing against `api.sleeper.app`, `sleeper.com`,
  `rtsports.com`, and `freedraftguide.com` this session -- see the
  Sleeper and RTSports sections above for full findings.
- **Findings**: Sleeper has no public ADP data surface at all (not a
  policy restriction -- the data simply isn't published anywhere
  reachable). RTSports' real ADP product lives on `freedraftguide.com`,
  which explicitly disallows `ClaudeBot` and other AI crawlers in
  `robots.txt` -- respected, not routed around -- and even a permitted
  fetch would return a live 2026 aggregate, not an archived 2025
  snapshot.
- **Decision**: Neither direct-acquisition candidate is usable. No
  source promoted. This reopens (does not resolve) the question of an
  explicit, reviewed MFL QB/TE bias-correction methodology as the
  remaining realistic path to a canonical whole-master-DB 2025 source
  -- a genuine methodology decision, pending explicit approval, not
  decided by this entry.
- **Confidence level**: High that neither Sleeper nor RTSports is
  reachable for this project's purposes today, for two independent and
  unrelated reasons (no data surface; explicit AI-crawler policy +
  wrong data shape).
- **Next experiment**: none automated remaining on this branch. A
  manual, human-run RTSports/Free Draft Guide acquisition is
  conceivable but out of scope for this project's stated preference
  for reproducible pipelines over manual downloads, and wasn't pursued
  here.

---

### 2026-07 -- MFL QB/TE correction study (three candidate methods, not yet selected)

- **Date**: 2026-07
- **Evidence**: `research/diagnostics/mfl_pipeline/output/adp_all_non_keeper.csv`
  (576-row MFL reconstruction), `research/diagnostics/adp_2025_investigation/parsed/mfl_vs_fftoday_comparison.csv`
  (228-player overlap, the fit/training basis), `research/diagnostics/mfl/espn_vs_mfl_2025_comparison.csv`
  (23-player independent ESPN benchmark, 4 of them QB/TE -- the true
  held-out test set, never used to fit anything). RB/WR excluded from
  this study by design (raw MFL already agrees closely with consensus
  for those positions, ~7 rank median diff -- no evidence justifies
  changing them).
- **Three candidates fit on the 35 QB / 36 TE training rows**, each
  producing a corrected value from MFL's raw `mean_adp`:
  - **A -- additive shift**: `mean_adp + median(consensus - mfl)`
    (QB +25.5, TE +19.8). Simplest, fully transparent.
  - **B -- quantile mapping**: replace each MFL QB/TE's percentile
    (within the MFL QB/TE training distribution) with the value at the
    matching percentile of the consensus training distribution. Cannot
    produce a value outside the real observed target range, by
    construction.
  - **C -- affine (OLS) recalibration**: `avg_rank = a + b * mean_adp`
    per position (QB: `-9.96 + 1.324x`, r2=0.948; TE: `-33.45 + 1.416x`,
    r2=0.900). Justified over a pure shift because slope != 1 for both
    positions -- MFL doesn't just start QB/TE early, it compresses the
    round spread, worsening with pick depth.
- **Findings (the decisive evidence is the 4-case independent ESPN
  benchmark, never used to fit any method)**:
  - Method B wins 3 of 4 held-out cases decisively (Trey McBride:
    raw err 6.7 -> 0.3; Josh Allen: 16.1 -> 0.7; Joe Burrow: 17.8 ->
    4.2) and is competitive on the fourth (Dak Prescott).
  - **Method C is worse than doing nothing on 2 of 4 held-out cases**
    (Josh Allen 16.1 -> 24.6; Joe Burrow 17.8 -> 22.5) despite the best
    in-sample r2 -- a real overfitting/generalization failure, not a
    close call.
  - **Method C also produces an implausible negative corrected ADP**
    for the earliest-drafted QB (Josh Allen: -1.7 in-sample, -4.0 on
    the held-out check) -- a hard, structural flaw of an unclamped
    linear extrapolation, not a rounding artifact.
  - Method A is a solid, unspectacular middle: improves on raw for 3 of
    4 held-out cases, never catastrophically wrong, but well behind
    Method B where B does well. Its uniform shift also visibly distorts
    which QBs land in rounds 1-3 (raw and B both keep 5 QBs there,
    matching real-world expectation of only elite arms going that
    early; A drops it to 1).
  - Dak Prescott remains a large residual error under every method
    (raw 49.1 -> best correction, C, still 38.2) -- flagged as a
    genuine named-case risk, not smoothed over.
  - No method was selected on the basis of median positional gap alone
    -- the deciding evidence is the independent held-out comparison and
    the implausible-value check, per explicit instruction.
- **Decision**: **Not yet decided.** Method B (quantile mapping) is the
  strongest candidate on every held-out and structural-safety measure
  checked; Method C is disqualified by its own held-out failures and
  implausible extremes; Method A remains a fallback if simplicity is
  weighted above accuracy. No correction has been selected or
  implemented -- pending explicit approval.
- **Confidence level**: Medium -- the held-out benchmark is real and
  independent but only 4 QB/TE cases; a larger validation set (e.g. the
  28 QB / 27 TE standalone RTSports ranks embedded in the FFToday
  capture, see the RTSports section above) would strengthen this before
  final selection.
- **Next experiment**: re-run this same comparison against the
  standalone RTSports rank column (28 QB / 27 TE) as a second,
  independent check before final selection.

---

### 2026-07 -- MFL correction study, round 2: full-population stats, RTSports cross-check, downstream SBV impact

- **Date**: 2026-07 (Method C dropped per its round-1 held-out
  failures and implausible negative values -- this round compares only
  A and B, at the full 54-QB/58-TE population, per explicit request)
- **Full-population error stats** (median / p90 / max absolute error;
  the 71-row overlap vs. `avg_rank` -- **Method B's numbers here are
  partly circular**, since B was fit to reproduce this exact
  distribution's order statistics; A's are not):
  - QB: raw 25.5/66.3/91.0 -> A 17.4/40.9/65.5 -> B 4.5/28.4/41.5
  - TE: raw 19.8/76.6/94.4 -> A 23.4/56.9/74.7 -> B 12.2/38.0/84.5
- **Standalone RTSports cross-check** (28 QB / 27 TE, genuinely more
  independent -- contributed only 1/3 to the `avg_rank` fitting target,
  not identical to it):
  - QB: raw 19.4/44.9/80.6 -> A 14.2/31.9/55.1 -> **B 12.4/25.6/48.7
    (still best)**
  - TE: raw 10.3/42.5/61.4 -> A 20.7/30.2/41.6 -> B 17.3/35.6/54.1 --
    **neither correction beats raw MFL on median error here**, though B
    is still clearly better than A. Flagged honestly, not smoothed
    over: this complicates TE specifically -- the `avg_rank`-based TE
    bias may be driven more by the Sleeper/ESPN components of the blend
    than by an RTSports-specific pattern.
- **Order preservation**: Spearman rho vs. raw `mean_adp`, full
  population -- A = 1.000000 (exact, by construction), B = 0.994 (QB)
  / 0.996 (TE). Effectively fully order-preserving for both.
- **Round-boundary crossings**, full population: QB -- A 54/54 change
  round (max jump 3), B 45/54 (max jump 7). TE -- A 58/58 (max jump 2),
  B 47/58 (max jump 6). A's uniform shift touches every player by a
  small, predictable amount; B reorders more within-position, with a
  few larger jumps.
- **Implausible-value check**, full population: no negatives, no
  out-of-range values for either A or B (QB: A 31.7-376.5, B
  21.3-280.0; TE: A 47.1-347.3, B 19.7-269.0).
- **Downstream Stars-by-Value impact** (real, not simulated): matched
  101/112 MFL QB/TE by name to real 2025 master-DB rows with
  `games_played >= 1` (90% match rate). Computed real `P` via
  `lib/stars_by_value/production.py` (existing, tested code, real 2025
  stats -- the season is already complete). `E_P` uses the **2024
  fitted lookup as an explicit stand-in proxy** (2025 itself has no
  real fitted `E_P` yet -- that's Phase 3, still blocked on this
  decision). Result: **0 of 101 players' final Star/non-Star label
  differs between Method A's round assignment and Method B's**, despite
  individual round differences of up to 6-7 rounds for some players.
  Both methods produce exactly 1 real 2025 Star QB/TE from this
  population, same player either way.
- **Acquisition-cost classification**: structurally moot for this
  comparison, not a discriminating factor -- once any MFL-based source
  is promoted, corrected QB/TE rows become `adp_scored` and never reach
  `acquisition_cost.py` at all (that step only runs for `no_adp_match`
  rows, per the settled 4-step order). Both methods bypass it
  identically.
- **Decision**: Not yet made. Given equal downstream label impact (0
  flips either way), the choice reduces to accuracy and structural
  safety, where B still leads on 3 of 4 comparisons (avg_rank QB/TE,
  RTSports QB) and ties/loses only on RTSports TE median error --
  still not a clean sweep, disclosed rather than rounded up to one.
- **Confidence level**: Medium-high for QB (multiple independent checks
  agree B is best). Medium for TE (RTSports check complicates the
  picture; avg_rank check still favors B but with the known circularity
  caveat).
- **Next experiment**: none required before a decision -- this was the
  requested final validation round.

---

### 2026-07 -- 2025 depth-chart Week 1 mapping validated against the real nflverse schedule

- **Date**: 2026-07
- **Evidence**: `nflverse/nflverse-data` release tag `schedules`, asset
  `games.csv` -- confirmed to exist via the public GitHub API (not yet
  fetched into the production pipeline; this was a one-time research
  verification, mirroring how `players`/`depth_charts` were confirmed
  before being wired into `nflverse_source.py`). Real per-team 2025
  Week 1 REG kickoff dates range 2025-09-04 (Thursday opener,
  DAL@PHI) through 2025-09-08 (MIN@CHI, Monday).
- **Findings**: replacing the earlier shared-date approximation
  (single project-wide 2025-09-04 for every team) with each team's real
  Week 1 date and taking the latest `depth_charts_2025.csv` snapshot
  (`dt`) on or before it reproduces the identical, correct result for
  every 2025 rookie QB already checked: Cam Ward (`pos_rank=1`, the
  only true Week 1 starter in the class), Jaxson Dart/Dillon
  Gabriel/Shedeur Sanders/Tyler Shough correctly behind their real
  Week 1 starters, remaining Day-3/UDFA rookies correctly absent from
  the active-roster depth chart or clearly buried at `pos_rank` 3-4.
- **Decision**: the per-team-schedule definition is validated and ready
  for production use. `nflverse-data`'s `schedules` release
  (`games.csv`) is the identified canonical source -- a single,
  all-seasons file, same "no season grain" fetch shape already used for
  `players.csv`.
- **Confidence level**: High -- every real 2025 rookie QB with an
  active-roster presence resolves to a real-world-correct starter/
  backup split under the schedule-precise definition, matching the
  approximation's results exactly (the earlier shared-date proxy turned
  out not to have introduced any error for this specific check, but the
  schedule-based version is the one that should ship).
- **Next experiment**: none remaining for this definition -- ready for
  `acquisition_cost.py`'s Phase 2 implementation once Phase 1's source
  decision lands.

---

### 2026-07 -- Final 2025 ADP decision: raw MFL AUG15 canonical, Method B rejected as a numeric input

**Superseded population definition.** The no-normalization conclusion
remains approved, but the later 2026-08 decision replaces this
heterogeneous aggregate with the strict governed 147-league
reconstruction and its 35%/30% participation policy. Implementation of
that replacement is pending.

- **Date**: 2026-07
- **Decision**: **Canonical `overall_adp` for 2025, all four positions
  (QB/RB/WR/TE alike), is raw MFL AUG15 `mean_adp`**, source-labeled
  `mfl_aug15_2025`. Method B's quantile-mapped output survives only as
  a disclosed, NEVER-CONSUMED QB/TE sensitivity field
  (`mfl_2025_sensitivity_market_rank`, named as a rank deliberately --
  see `scripts/mfl_2025_adp_correction.py`'s module docstring). RB/WR
  were never corrected in any version of this study.
- **Why raw MFL, given its own documented QB/TE bias**: this decision
  does **not** establish raw MFL is unbiased for QB/TE -- the bias is
  real and stays on the record (two-round validation study above: QB
  high-confidence bias, TE moderate-confidence, genuine market-source
  disagreement, Mark Andrews the clearest disclosed counterexample).
  What was established, across two full studies, is that **no tested
  method can convert the corrected ordering onto a more defensible
  mean-pick ADP scale than simply leaving the units alone**:
  1. Method B's output is mathematically rank-scale (inherited from
     FFToday `avg_rank`, an average of platform RANKS), not genuine
     mean-pick ADP -- writing it into `overall_adp` would silently
     recreate the exact rank-vs-ADP incompatibility that already
     disqualified FFToday from canonical status elsewhere in this
     document.
  2. A follow-up historical FFC rank-to-ADP reconstruction study
     walk-forward validated four candidate conversion curves
     (prior-season, pooled-recent-5, recency-weighted, simple
     monotonic interpolation) against real FFC ADP, 2014-2024. **The
     naive "rank IS the ADP" baseline beat every one of them on every
     metric** (median error 1.28 vs. the best fitted method's 2.83;
     correct-round-rate 89.4% vs. 76.4%). Per the pre-committed
     fallback rule, this result means no historically-validated
     conversion clears the bar -- not that one was found and adopted.
  Raw MFL mean_adp preserves genuine mean-pick units and historical
  comparability, for both LWI and SBV, at the cost of leaving the
  known QB/TE bias uncorrected in the number actually consumed
  downstream. That tradeoff was judged safer than introducing a
  units error into the canonical pipeline.
- **Provenance retained**: `overall_adp_mfl_raw` (defensive copy of
  the raw value), `mfl_2025_sensitivity_market_rank` (QB/TE only, NULL
  for RB/WR), `adp_source="mfl_aug15_2025"`. Snapshot retrieval
  date/hash is not duplicated per-row -- already recorded once per
  season/endpoint in `scripts/mfl_source_manifest.json`, looked up via
  `(season=2025, source="mfl_aug15_2025")`. Matching confidence
  (`data_quality_flag`, from the unmodified `player_matching.py`
  pipeline) and source-level confidence (the QB/TE bias documented
  here) are deliberately kept as two separate, never-blended concepts
  -- a well-matched QB with a known-biased source stays
  `matched_clean`, not downgraded because of a position-level source
  fact that has nothing to do with match quality.
- **Mechanically enforced, not just documented**: no scoring or
  eligibility path (`05_calculate_metrics.py`, `adp_round()`, E_P
  fitting, SBV labeling/acquisition-cost/production) may ever read
  `mfl_2025_sensitivity_market_rank` --
  `tests/test_mfl_2025_adp_correction.py`'s
  `TestSensitivityFieldNeverConsumedDownstream` scans every real
  consumer's source for the field name and fails if any reference
  exists.
- **Confidence level**: High that this is the safest available
  canonical choice given what's been tested. Not a claim that the
  QB/TE bias is resolved -- it remains a known, disclosed, uncorrected
  limitation of 2025's canonical ADP for those two positions
  specifically.
- **Next steps**: run the real 2025 MFL population through
  `player_matching.py` (real `matched_clean`/`matched_needs_review`/
  `no_adp_match` counts, duplicate/collision audit) before any
  canonical value is written to the master DB -- not yet done as of
  this entry.

---

### 2026-07 -- 2025 ADP matching audit (Commit D), Travis Hunter investigation, and needs-review resolution

- **Date**: 2026-07
- **Evidence**: `research/diagnostics/adp_2025_investigation/audit_2025_adp_matching.py`
  -- a committed, read-only, reproducible research artifact. Runs the
  real raw MFL AUG15 2025 population through the existing, unmodified
  `player_matching.py` -- no new matching logic, no master DB writes.
- **Initial pass** (371 real skill-position candidates): 342
  `matched_clean`, 4 `matched_needs_review`, 25 `no_adp_match`, 0
  duplicates/collisions. 58% of `matched_clean` fall within ADP <=170
  (the 2020-2024 typical historical depth) -- real, comparable
  coverage where it matters most for E_P fitting and scoring.
- **The 25 unmatched, verified not assumed**: checked each notable
  name directly against `season_results_ppr_2006_2025.csv` rather than
  trusting the "no match" reason string. Almost all (Joe Mixon 164 real
  MFL drafts, Brandon Aiyuk 106, Tank Dell, Alexander Mattison, Logan
  Woodside, Sam Hartman, etc.) have **zero 2025 nflverse stats rows at
  all** -- not a matching failure. Real players drafted heavily
  pre-season who then recorded no real per-week production (consistent
  with real 2025 injury/absence situations). Since the master DB's base
  population is anchored to nflverse's real stats table, not the ADP
  source, these would never become master DB rows regardless of match
  outcome -- not a Commit D defect.

#### Travis Hunter -- investigated as a blocking data-quality case

- **Real root cause identified, not assumed**: Travis Hunter (185 real
  MFL drafts, ADP 79.4 -- a real, notable early pick, consistent with
  his real profile as the 2024 Heisman winner and #2 overall 2025
  pick) has genuine, substantial real offensive production **in the
  raw weekly nflverse source** -- confirmed directly against
  `data/raw/nflverse/annual/stats_player_week_2025.csv` by his real
  `gsis_id` (`00-0040718`): 7 weeks, 46 total touches, up to 24.1 PPR
  points in week 7. He is NOT absent from nflverse's data.
- **He is lost during aggregation, not fetch.** nflverse's own
  `players.csv` reference and the raw weekly file both tag him
  `position="CB"` (his real, listed primary position -- he plays both
  ways). `scripts/03_download_stats.py`'s Step 2
  (`weekly = weekly[weekly["position"].isin(SKILL_POSITIONS)]`)
  unconditionally drops every non-QB/RB/WR/TE-tagged row **before**
  Step 5b's `position_overrides.csv` mechanism ever runs -- so by the
  time the existing tweener-correction mechanism (built for Jordan
  Matthews/Devin Funchess/N'Keal Harry, all TE-vs-WR cases that
  survive the Step 2 filter either way) could apply, his rows are
  already gone. This is a materially different, harder case than the
  ones `position_overrides.csv` was designed for: CB-vs-WR (skill vs.
  non-skill), not TE-vs-WR (skill vs. skill). The existing override
  mechanism cannot rescue him as currently wired -- fixing this would
  require applying overrides before, not after, the skill-position
  filter, a real change to `03_download_stats.py`, not something this
  audit does unilaterally.
- **Systematic check for other cases**: scanned every 2025 player
  tagged with a non-skill position in the raw weekly source for real
  offensive involvement (43 found). Kyle Juszczyk (FB, 67.7 total
  points) is numerically larger but a different, already-implicit
  scope boundary -- fullbacks are excluded by the same `SKILL_POSITIONS`
  definition as K/DST, not a data bug. Bo Melton (CB, 24.2 points) is a
  smaller, mixed case (mostly kickoff-return yardage, a handful of real
  WR-style targets). Everyone else drops off sharply or is clearly a
  single defensive/special-teams scoring play (0-1 touches). **Travis
  Hunter is the one real, consequential, disclosed exception** -- a
  genuine skill-position-caliber player excluded from the fantasy
  results aggregate by a scope-boundary side effect, not a scope
  decision made about him specifically.
- **Decision**: not fixed in this pass. Flagged as a real, open
  data-quality gap for a future, separately-scoped
  `03_download_stats.py` change (apply `position_overrides.csv` before
  the `SKILL_POSITIONS` filter, or add a dedicated allow-list for
  confirmed two-way skill contributors) -- out of scope for Commit D,
  which only runs existing matching rules unchanged.

#### `matched_needs_review` resolution (explicit human review, all four resolved)

| Case | Fuzzy score | Resolution | Basis |
|---|---|---|---|
| Chigoziem Okonkwo -> "Chig Okonkwo" | 82.76 | **Approved** -- override added | Confirmed same player (TE, gsis_id `00-0037809`) via nflverse's `players.csv` |
| Kenneth Gainwell -> "Kenny Gainwell" | 86.67 | **Approved** -- override added | Confirmed same player (RB, gsis_id `00-0036919`) |
| Joshua Palmer -> "Josh Palmer" | 91.67 | **Approved** -- override added | Confirmed same player (WR, gsis_id `00-0036988`) |
| Amari Cooper -> "Darius Cooper" | 80.00 (review floor) | **Rejected** | Real Amari Cooper has zero 2025 nflverse stats rows -- same "drafted, no real production" pattern as Mixon/Aiyuk above, not this specific pairing being a real identity |

Three approved rows added to `data/manual/player_name_overrides.csv`
(the existing, unmodified override mechanism -- checked first, 100%
confidence, exactly how Vick 2011-2013 was already handled). The
rejected pairing has no override and gets none -- `player_matching.py`
itself is unmodified, so its unchanged fuzzy logic will keep proposing
this same low-confidence match on every future run; the audit script
explicitly reclassifies it for reporting, a real, disclosed limitation
of not having a negative-override mechanism, not silently patched over.

#### Final post-review counts

| Status | Count |
|---|---|
| `matched_clean` | 345 (342 + 3 approved) |
| `matched_needs_review` | 0 (all four resolved) |
| `no_adp_match` (rejected pairing) | 1 (Amari Cooper) |
| `no_adp_match` (never matched) | 25 |
| **Total candidates** | **371** |

- **Sensitivity field re-confirmed inert** after the override changes:
  identical matching result with `mfl_2025_sensitivity_market_rank`
  present or dropped.
- **Confidence level**: High in the matching audit's own counts and
  the three approved identities. Medium-high on Travis Hunter's root
  cause (verified directly against real source data, not inferred) but
  the FIX itself is undecided and out of scope here.
- **Next steps**: Commit E (master DB rebuild) still not proposed.
  Travis Hunter's resolution (a `03_download_stats.py` change) is a
  separate, real decision to make before or independently of Commit E
  -- his exclusion is a pre-existing condition of the whole master DB
  build, not created by this audit, but now disclosed rather than
  silently absorbed into "no_adp_match."

---

### 2026-07 -- Travis Hunter fixed: position override now applied before the skill-position filter

- **Date**: 2026-07
- **Decision**: treated as a real pipeline bug, not an acceptable
  missing-data case, and fixed -- resolved before Commit E rather than
  deferred alongside it.
- **The narrowest fix**: `scripts/03_download_stats.py`'s existing
  `apply_position_overrides()` (unchanged function, unchanged strict
  player_id-keyed matching) is now ALSO called on the raw weekly data
  at a new Step 1b, before Step 2's `SKILL_POSITIONS` filter -- not
  only at the existing Step 5b (season level, after the filter). This
  is a narrow rescue path, not a broadened population: only player_ids
  with a real, explicit `data/manual/position_overrides.csv` entry are
  ever affected. Every other non-skill-tagged row (every other CB,
  every FB, every defensive score) is filtered exactly as before --
  confirmed both by 6 new regression tests
  (`tests/test_download_stats.py::TestPositionOverrideRescuesNonSkillTaggedPlayer`)
  and directly against the real, full 2025 production data (below).
- **Travis Hunter added to `data/manual/position_overrides.csv`**:
  `player_id=00-0040718`, blank season (applies to all his seasons,
  same convention as Matthews/Funchess), `correct_position=WR`.
- **Verified on real, full production data**, not just synthetic
  tests: re-ran `scripts/03_download_stats.py` end-to-end against the
  real, already-cached 2006-2025 raw weekly data (no new network
  fetch -- cache-hit on every season). Travis Hunter now appears in
  the regenerated `season_results_ppr_2006_2025.csv` with
  `position=WR`, `games_played=7`, `fantasy_points_ppr=63.8`,
  `position_finish_ppr=97` -- his real numbers. Matthews/Funchess
  (13 total player-seasons across both) remained correctly `WR`,
  confirming the pre-existing override path is untouched by this
  change.
- **Narrow-rescue-path re-confirmed on the full real population**: of
  the same 43 non-skill-tagged 2025 players with real offensive
  involvement identified in the prior audit entry, **exactly one**
  (Travis Hunter) now appears in the regenerated season results.
  Every other one -- Kyle Juszczyk (FB, 67.7 points, numerically
  larger than Hunter), Bo Melton (CB), Connor Heyward (FB), and the
  rest -- remains correctly excluded. The fix rescues only the
  explicitly approved exception, nothing else.
- **Re-ran the 2025 ADP matching audit** (`audit_2025_adp_matching.py`,
  unchanged) against the regenerated season results:

| Status | Before fix | After fix |
|---|---|---|
| `matched_clean` | 345 | **346** |
| `matched_needs_review` | 0 | 0 |
| `no_adp_match` (Amari Cooper, rejected) | 1 | 1 |
| `no_adp_match` (never matched) | 25 | **24** |
| **Total candidates** | 371 | 371 |

  Sensitivity field re-confirmed inert after the fix.
- **Confidence level**: High -- verified against real source data at
  every step (raw weekly stats, regenerated season results, the real
  matching audit), not inferred from the synthetic tests alone.
- **Next steps**: Commit E (master DB rebuild) can now proceed with
  Travis Hunter genuinely included, not silently missing.

---

### 2026-07 -- Blocker B settled: unscoreable_expected_production_out_of_range (8th status)

- **Date**: 2026-07
- **Decision**: NOT capped at round 15, NOT MMC-substituted -- there is
  no real historical population past round 15 to fit an honest E_P
  from (confirmed: zero rows in any 2006-2024 season ever exceed round
  15), and doing either would be artificial precision. Instead, a real,
  8th settled status: `unscoreable_expected_production_out_of_range`
  (provenance `known_acquisition_cost_ep_out_of_fitted_range`) --
  `score=NULL`, `label=NULL`, both thresholds populated. Acquisition
  cost (the real ADP round) is known and trustworthy; what's
  unavailable is an E_P value for that round. Not described as
  permanent -- the honest current treatment until deeper historically-
  compatible ADP data exists.
- **Real stakes, precisely quantified before deciding**: of the 118
  rows with `adp_round > 15` (2025 only), 110 already fail the
  production gate regardless (status unaffected by this decision) and
  only 8 clear the gate and genuinely need this status. Of those 8,
  **none can reach their Star threshold even at the theoretical best
  case (E_P=0)** -- this decision changes zero Star labels. Verified on
  real, full-population data after implementation: `below_production_gate`
  2377->2487 (+110), new status = 8 (exact match), `Stars unchanged at 74`.
- **Mechanically guaranteed not to silently default to label=0**:
  `tests/test_labeling.py::TestExpectedProductionOutOfRange::test_hypothetical_high_production_round16_player_still_gets_null_label`
  pins a synthetic, absurdly-high-P player at an out-of-range round and
  asserts `label=NULL`, not `label=1` or `label=0` -- the resolution is
  genuinely unresolved, not a disguised default, regardless of how the
  8 real 2025 cases happen to turn out.
- **Confidence level**: High -- verified against real data at every
  step, and the "zero Stars affected" finding was established BEFORE
  the status was implemented, not asserted after the fact.
- **Next steps**: none required to proceed to a canonical build on this
  specific blocker. Revisit only if a genuine historically-compatible
  ADP source with real round-16+ coverage is ever established.

---

### 2026-07 -- Blocker A: historical MFL backfill CI workflow built, not yet run

- **Date**: 2026-07
- **Built**: `scripts/mfl_historical_backfill.py` (driver, seasons
  2011-2024, calls `mfl_client.fetch_adp()`/`fetch_players()`
  unmodified -- existing caching/rate-limiting/integrity-check
  behavior reused as-is, never `force_refresh=True` implicitly) +
  `.github/workflows/fetch_mfl_historical.yml` (manual
  `workflow_dispatch` only, mirrors `fetch_adp.yml`'s structure,
  uploads `data/raw/mfl/` + the committed manifest as an artifact,
  does NOT rebuild the master DB automatically). 9 mocked tests
  (`tests/test_mfl_historical_backfill.py`) -- no real network calls
  in normal test execution.
- **Not yet run**: this workflow needs to actually be triggered (via
  the GitHub Actions tab) and its resulting artifact downloaded into
  `data/raw/mfl/` before the 4,893 deferred historical rows can be
  re-attempted. Not something this session can trigger directly.
- **Next steps**: run the workflow, place the resulting files under
  `data/raw/mfl/`, re-run `scripts/11_calculate_stars_by_value.py
  --mode diagnostic`, and report how many of the 4,893 deferred rows
  become scoreable.
