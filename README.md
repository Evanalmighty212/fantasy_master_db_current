# Fantasy Master Historical Database

A reproducible pipeline that builds a historical fantasy football
database (2006-2025, PPR scoring), joins preseason draft position
(ADP) against real season results, and computes the **League Winner
Index (LWI)** -- a metric scoring how much value a player's season
actually delivered relative to the draft cost it took to get them,
not just how many points they scored.

**Current status**: Dataset 1 (the historical LWI, v2.1) is complete,
deployed, and verified. See `docs/LWI_MODEL_CARD.md` for the full
validation history and `CHANGELOG.md` for what changed and why.
Next up: Dataset 2 (League Winner Traits) and Dataset 3 (a predictive
model) -- both specced but not yet built, see `docs/` below.

---

## Quick start

No local Python installation required for the automated path -- see
**"Running the pipeline"** below for the one-click GitHub Actions
option. If you do have Python locally:

```bash
pip install -r requirements.txt --break-system-packages
python3 run_pipeline.py
```

This runs every pipeline step in order and writes results to `data/`.

---

## Pipeline architecture

Each script is a numbered stage; `run_pipeline.py` chains them in
order. Every stage's output is a real file other stages (and you) can
inspect directly -- nothing is hidden inside memory between steps.

| Step | Script | What it does |
|---|---|---|
| 1 | `01_download_adp.py` | Pulls raw preseason ADP data (Fantasy Football Calculator API). **Superseded in production** by `scripts/ci_fetch_adp_phase1.py`, which is what the "Run Full Pipeline" GitHub Action actually runs for this step -- see `docs/ADP_SOURCE_MATRIX.md` |
| 2 | `02_clean_adp.py` | Cleans and standardizes ADP into one canonical schema across all sources (FFC + hand-recovered FFToday archive for 2007-2009) |
| 3 | `03_download_stats.py` | Pulls real season/weekly results from nflverse, builds season-level and weekly-level result tables, applies hand-verified position corrections |
| 4 | `04_build_master_dataset.py` | Matches ADP to real results by player identity, builds the master historical database, applies the undrafted-player proxy-ADP mechanism |
| 5 | `05_calculate_metrics.py` | Computes the League Winner Index (LWI) -- see "The metric" below |
| 6 | `06_generate_rankings.py` | Produces all-time rankings, season champions, position leaderboards, ADP value/bust lists, and Dataset 5 (no-ADP breakout research candidates) |
| 7 | `07_export_excel.py` | **Not yet built** -- final Excel packaging, deferred |

---

## The metric: League Winner Index (LWI)

**LWI is not "who scored the most points."** It measures whether a
player's season delivered real value relative to what it cost to
draft them -- a player who was the consensus #1 pick and simply met
that lofty expectation scores very differently from a late-round or
undrafted player who massively outperformed their cost, even if their
raw point totals are similar.

Six weighted components (46/18/17/12/4/3):

1. **ADP Value (46%)** -- return on overall draft capital, using a
   leave-one-season-out historical expectation curve plus a real-cost
   accountability cap
2. **Total Points Above Replacement (18%)**
3. **PPG Above Replacement (17%)**
4. **Standardized Positional Advantage (12%)**
5. **Playoff Performance (4%)**
6. **Consistency (3%)**

The exact formulas, thresholds, and every design decision behind them
(including several real bugs found and fixed along the way) are
documented in **`docs/METRIC_SPECIFICATION.md`** (the authoritative,
exact spec) and **`docs/LWI_MODEL_CARD.md`** (the full validation
history, in plain terms).

**Undrafted players are included, not excluded.** A metric literally
named "League Winner Index" that couldn't recognize a real undrafted
breakout (James Robinson 2020, Victor Cruz 2011, etc.) would measure
something narrower than its own name implies -- see the "Undrafted
player representation" section of `docs/METRIC_SPECIFICATION.md` for
the exact mechanism.

---

## Generated outputs

None of these are committed to the repo (they're reproducible from
the pipeline, not hand-edited) -- run the pipeline to generate them.

| File | What it is |
|---|---|
| `data/master/master_historical_db_with_lwi_2006_2025.csv` | The full database: every player-season, real stats, ADP, and LWI score |
| `data/exports/rankings/all_time_lwi_rankings.csv` | Every eligible player-season, ranked |
| `data/exports/rankings/season_champions.csv` | The literal #1 LWI score for each season -- the "league winner" of that year |
| `data/exports/rankings/position_leaderboards.csv` | Top 25 all-time per position |
| `data/exports/rankings/biggest_adp_values.csv` / `biggest_adp_busts.csv` | Top/bottom 10 per season by draft-value outperformance |
| `data/exports/rankings/no_adp_breakout_candidates.csv` | Dataset 5 -- players currently excluded from LWI (no ADP match) with a strong enough real season to be worth researching |
| `data/exports/validation/*.csv` | Diagnostic reports (eligibility breakdowns, match-quality dashboards, coverage reports) |

---

## Manually-maintained data (`data/manual/`)

Unlike everything else in `data/`, this folder **is** committed --
it's hand-researched correction data, not something the pipeline can
regenerate on its own:

- `player_name_overrides.csv` -- known name-matching exceptions
- `position_overrides.csv` -- corrects real position-tagging errors
  inherited from the underlying nflverse source data
- `adp_status_verification.csv` -- tracks which players have been
  researched and confirmed as genuinely undrafted (vs. simply missing
  from the current ADP source's depth) -- see Dataset 5 above

---

## Documentation (`docs/`)

`CHANGELOG.md` lives at the repo root (not in `docs/`) -- what changed
between versions, and why, including decisions that were tried and
rejected.

| File | What it's for |
|---|---|
| `METRIC_SPECIFICATION.md` | The exact, authoritative LWI formula -- if code and this doc ever disagree, the code has a bug |
| `LWI_MODEL_CARD.md` | Purpose, full validation results, design history, known limitations -- plain-language |
| `PREDICTION_SPECIFICATION.md` | Target definition, evaluation protocol, and validation plan for the future predictive model (Dataset 3) -- written before any modeling code, not yet built |
| `LEAGUE_WINNER_TRAITS_SPEC.md` | Research plan for Dataset 2 (what preseason patterns predict becoming a league winner) -- written before any research code, not yet built |
| `VERSION_1_SCOPE.md` | The original project scope |
| `MATCHING_ARCHITECTURE.md` | How player identity matching works across ADP and results sources |
| `ADP_SOURCE_MATRIX.md`, `ADP_SEASON_SOURCE_PLAN.csv` | Which ADP source covers which season, and why |

---

## Running the pipeline

**No local Python needed**: use the **Actions** tab on GitHub, select
"Run Full Pipeline," click "Run workflow." Results download as an
artifact when it finishes.

**With local Python**:
```bash
pip install -r requirements.txt --break-system-packages
python3 run_pipeline.py
```

---

## Testing

```bash
python3 -m pytest tests/ -v
```

53 automated tests as of this writing, nearly all of them written to
catch a specific real bug found during development -- not written
speculatively. See `CHANGELOG.md`'s "Fixed" sections for the
stories behind several of them (a pandas index-misalignment bug that
silently corrupted 72% of two LWI components, a mathematical
duplication between two components that went undetected until
directly tested for, a cross-position outlier-contamination bug in
Component 4's normalization, and others).

---

## Project roadmap

1. ~~**Dataset 1**: League Winner Index~~ -- complete, deployed, v2.1
2. **Dataset 2**: League Winner Traits -- research into what
   preseason-available patterns actually predict becoming a league
   winner (spec written, research not yet started)
3. **Dataset 3**: Predictive League Winner Probability -- a model
   trained on Dataset 2's findings, strictly time-validated (spec
   written, model not yet built)

The single largest open item right now isn't methodology -- it's data
completeness: verifying which of the currently-excluded, no-ADP-match
players (Dataset 5) were genuinely undrafted vs. simply missing from
this project's current ADP source depth.
