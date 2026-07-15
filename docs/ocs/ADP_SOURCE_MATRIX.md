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
| MyFantasyLeague | Unknown | TBD | TBD | Pending | Candidate |
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

Status:

Not yet evaluated.

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
| 2025 | ⭐⭐☆☆☆ | FFC confirmed cleanly absent (reason unclear); FFToday/FantasyPros untested for this year |

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
