# Dataset 3 research foundation

Implementation-neutral scaffolding for evaluating an "absolute-impact,
stars-by-value" alternative to Dataset 3's current relative
top-10%-by-position target.

**The methodology is now settled** -- see
`STARS_BY_VALUE_METHODOLOGY.md` for the full, current decision record
(production composite, minimal-market-cost baseline, position
thresholds, label schema) and `STARS_BY_VALUE_IMPLEMENTATION_PLAN.md`
for how it turns into pipeline code. Everything in this directory,
including the calibration scripts indexed below, is the exploratory
work that *led* to those settled decisions -- a research log, not an
independent source of truth. Where this README or a script's own
comments disagree with `STARS_BY_VALUE_METHODOLOGY.md`, the
methodology document wins.

Not part of the production pipeline. Nothing under `scripts/`,
`config.py`, or the `docs/*_SPECIFICATION.md` files is touched by
anything here.

## Run order

```bash
python research/dataset3/build_broad_historical_dataset.py   # run first -- everything else reads its output
python research/dataset3/expected_production_tables.py
python research/dataset3/replacement_level_tables.py
python research/dataset3/comparison_harness.py
python research/dataset3/human_review_export.py
python -m pytest research/dataset3/tests/                    # tests for lib/ only
```

## Files

| File | What it is |
|---|---|
| `LWI_COMPONENT_AUDIT.md` | Where total points, PPG, games played/availability, VORP, ADP value, and playoff production already enter current LWI, and where real overlap exists. Read this before designing any new formula on top of LWI -- it's the map of what's already spoken for. |
| `build_broad_historical_dataset.py` | The population every other file reads: all QB/RB/WR/TE player-seasons with `games_played >= 1`, including players with no ADP match -- current LWI eligibility is a FLAG here, not a filter. |
| `expected_production_tables.py` | Descriptive-only: production by ADP slot, ADP round, position, season, era bucket. Does not fit or choose an expected-production model. |
| `replacement_level_tables.py` | Descriptive-only: plausible replacement production under stated 10-team/12-team roster assumptions, season grain plus TWO weekly grains -- "active-week" (real production in weeks replacement-tier players actually played; reads HIGH, conditioned on activity) and "calendar-week" (explicit zeroes for weeks genuinely missed, using an inferred, verified bye-week schedule). Does not select a final replacement definition, and neither weekly table claims to model real waiver-wire availability -- see the script's docstring. |
| `lib/eras.py`, `lib/replacement.py`, `lib/comparison.py` | Reusable logic behind the above -- the only code in this directory with tests, since these are the parts meant to be imported and reused rather than run once. |
| `comparison_harness.py` | Scores the broad dataset under multiple `ScoringDefinition`s (current LWI, the preserved relative top-10%-by-position benchmark, and any future candidate) and reports annual/positional qualifying counts, top seasons, and rank changes. The one non-LWI definition included is explicitly labeled DEMO-ONLY -- a placeholder to prove the harness works, not a proposal. |
| `human_review_export.py` | Full CSV plus TWO shortlists -- a rank-based one with POSITION-SPECIFIC cutoffs (2x each position's own LWI replacement threshold, imported from `config.py`; a flat cutoff across positions was tried and rejected during review since it under-covers deep positions like RB/WR relative to QB), and a value-based one (beat own overall ADP, no rank cutoff at all, so it catches real value stories the rank-based list structurally can't). Includes undrafted/unresolved players throughout, not just current LWI-eligible ones. |
| `tests/test_lib.py` | Tests for `lib/` only, per the task's "test reusable code" scope -- the one-off table scripts are thin wrappers around `lib/` and aren't separately tested. Isolated from the production `tests/` suite at the repo root on purpose. |

## Calibration scripts (later investigation -- production formula, replacement level, expected production, thresholds)

These aren't a pipeline to re-run in order -- they're a chronological
research log, the equivalent of dated lab notebook entries. Several
scripts on the same question supersede an earlier one on that same
question (e.g. `expected_production_by_round_investigation.py` ->
`..._position_adjustment_investigation.py` -> `..._residual_diagnostics.py`
-> `..._temporal_validation.py` is the actual order the offset/recency
questions were resolved in, each building on the last, not four
independent takes). **`STARS_BY_VALUE_METHODOLOGY.md` is the
authoritative record of what was concluded and why -- these scripts
are the evidence and reproducibility trail behind it, cited there by
name (`Source: ...`) at the relevant decision, not an independent
narrative.** Deliberately not added to "Run order" above for the same
reason -- there is no single reproducible output to regenerate by
running them in sequence.

**Production formula / AATP / shrinkage**:
- `production_weight_and_boundary_calibration.py` -- the AATP
  construction (`build_adp_aware_aatp()`), the most-reused function
  across every later script in this group.
- `production_formula_and_active_window_comparison.py` -- production
  weight and meaningful-ADP boundary comparisons ahead of the AATP
  build above.
- `normalized_shrinkage_comparison.py` -- the normalized-vs-ordinary
  shrinkage math that led to k=5.
- `short_season_ppg_adjustment_comparison.py` -- short-season
  treatment alternatives compared before settling on normalized
  shrinkage.

**Replacement level**:
- `replacement_level_definition_comparison.py`
- `replacement_flex_allocation_sensitivity.py`
- `replacement_par_position_adjustment_selection.py`
- `replacement_cross_position_calibration_check.py` -- the first
  appearance of the RB/TE cross-position scale asymmetry, later
  resolved via position-specific thresholds (section 10).

**Expected production by round** (chronological -- each supersedes/extends the last):
- `expected_production_by_round_investigation.py`
- `expected_production_position_adjustment_investigation.py`
- `expected_production_position_adjustment_residual_diagnostics.py`
- `expected_production_replacement_adjusted_retest.py`
- `expected_production_temporal_validation.py`
- `aatp_round_refit_and_short_season_calibration.py`

**League-winner label / threshold calibration**:
- `league_winner_label_framework_comparison.py`
- `league_winner_value_signal_and_floor_calibration.py`

## Known data limitations carried through from the audit

- **Draft status is a real three-state fact, not two.** `drafted` /
  `verified_undrafted` / `unresolved` -- `verified_undrafted` is
  currently ~0 rows because `data/manual/adp_status_verification.csv`
  has no verified entries yet (same backlog flagged earlier as the
  single largest open item in the project). Don't read `unresolved`
  as "undrafted."
- **Weekly data has no rows for missed weeks.** `weekly_results_ppr_*.csv`
  only contains weeks a player had real involvement. The active-week
  replacement table describes REAL production replacement-tier
  players posted in weeks they played (reads high). The calendar-week
  table fills in explicit zeroes for genuinely missed weeks, using an
  inferred bye-week schedule (verified against 608 real team-seasons;
  the 2 exceptions are a real canceled game, not an inference error --
  see `replacement_level_tables.py`'s docstring). Neither version
  models real waiver-wire availability -- that would need per-league
  roster data this pipeline doesn't have.
- **Population counts, verified fresh against the actual files**
  (not carried forward from memory): the production master database
  is exactly 10,070 rows (`data/master/master_historical_db_with_lwi_2006_2025.csv`);
  ADP-matched rows are exactly 2,939 (2,921 `matched_clean` + 18
  `matched_needs_review`; split 2,420 FFC / 519 FFToday by source).
  The broad historical dataset here is 10,068 -- exactly 2 rows
  dropped for `games_played == 0`, both real, zero-activity
  player-seasons (David Fales 2019, Malik Cunningham 2023 -- see
  `build_broad_historical_dataset.py`'s docstring for the exact
  identification). If a different count has been cited elsewhere,
  treat these as the current, directly-verified numbers for this
  pipeline run.
- **`human_review_shortlist_by_value.csv` necessarily excludes every
  `unresolved` (no-ADP-match) player-season** -- outperformance vs.
  ADP is undefined without an ADP. Those seasons remain fully present
  in `human_review_full.csv` and in the rank-based
  `human_review_shortlist.csv` (which uses finish rank, not ADP, so
  isn't affected by this limitation) -- see
  `human_review_export.py`'s docstring.
