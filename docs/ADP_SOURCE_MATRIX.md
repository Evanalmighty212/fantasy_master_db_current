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
| Fantasy Football Calculator | Partial historical ADP | A | B | B | Backup / validation |
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

🟡 Partial Success

### Findings

- Historical API exists.
- PPR supported.
- Missing 2006.
- Missing 2025.
- Several seasons returned significantly fewer than 250 players.

### Verdict

Useful as a validation source but not reliable enough to serve as the primary backbone.

---

## FantasyPros

### Status

🟡 Under Investigation

### Findings

- Historical pages exist.
- PPR supported.
- Structured `window.FP.reportConfig` discovered.
- Embedded sample player rows located.
- Full player table not yet extracted.
- Export filename discovered.
- Possible JavaScript/API-backed architecture.

### Verdict

Currently the most promising primary source.

Next objective:

Locate the true export/API endpoint.

---

## FFToday

### Status

🟡 Partial Success

### Findings

- Automation successful for 2021–2025.
- Earlier seasons did not expose usable tables using current URL patterns.

### Verdict

Excellent recent-year fallback.

Needs further investigation for 2011–2020.

---

## Kaggle

Status:

Not yet evaluated.

---

## GitHub Repositories

Status:

Not yet evaluated.

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
| 2006 | ⭐☆☆☆☆ | Largest gap |
| 2007–2010 | ⭐⭐☆☆☆ | FFC + Archive candidates |
| 2011–2020 | ⭐⭐☆☆☆ | Primary unresolved range |
| 2021–2024 | ⭐⭐⭐⭐☆ | Multiple candidate sources |
| 2025 | ⭐⭐⭐☆☆ | FantasyPros appears strongest |

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

The goal is to preserve engineering reasoning so future work never repeats previous investigations.