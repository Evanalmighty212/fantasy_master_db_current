# Stars-by-Value Methodology (Settled and Implemented)

**Status: SETTLED AND IMPLEMENTED (2026-07).** The methodology below
is wired into `config.py` (`SBV_STATUSES`, `SBV_PROVENANCE_TYPES`,
`SBV_STAR_THRESHOLD`, `SBV_PRODUCTION_GATE_FLOOR`, etc.) and released
as the canonical Stars-by-Value label pipeline
(`scripts/11_calculate_stars_by_value.py --mode canonical`, backed by
`lib/stars_by_value/`). Canonical outputs:
`data/processed/stars_by_value_player_seasons.parquet`,
`data/exports/stars_by_value_player_seasons.csv` (schema documented in
the generated `data/exports/stars_by_value_player_seasons_SCHEMA.md`),
and the evidence-audit artifact
`data/exports/stars_by_value_evidence_audit.csv`.

**Relationship to Dataset 3, stated explicitly so it's never
conflated**: this pipeline is the canonical ground-truth
LABEL-GENERATION SYSTEM Dataset 3's eventual predictive model will be
trained and evaluated against -- see `docs/PREDICTION_SPECIFICATION.md`'s
2026-07 update. **Stars-by-Value is NOT Dataset 3.** It computes a
HISTORICAL fact (`star_by_value_label`) for player-seasons that have
already happened; it never predicts anything about a future or
held-out season. Dataset 3 is the separate, not-yet-built model that
will eventually predict, in advance, the probability that a
not-yet-observed player-season will go on to receive
`star_by_value_label == 1` once Stars-by-Value is run against its real
results.

This document exists to keep the settled construction in one durable
place -- the research/output CSVs behind these decisions are
gitignored and regenerate on demand, but the decisions themselves
shouldn't only live in conversation history.

**Superseded status line, preserved as history**: this document was
originally titled "(Provisional)" and marked "provisional decision
record, not implemented -- nothing here is wired into `config.py` or
any canonical pipeline." That was accurate throughout the methodology
investigation and design phase; it stopped being accurate once the
pipeline above was built and canonically released.

This is the "absolute-impact, stars-by-value" methodology first
scoped in `research/dataset3/README.md` and `LWI_COMPONENT_AUDIT.md`.
Every number below was arrived at empirically (real historical data,
real edge cases, honest out-of-sample testing) -- see the referenced
scripts in `research/dataset3/` for the evidence behind each line.

## 1. Expected-contribution window (governs AATP's active-window rule)

- A player with a **trustworthy ADP match** is a legitimate
  preseason fantasy asset from **Week 1**, regardless of round depth.
  "Trustworthy" means the real, matched ADP record already in this
  project's pipeline (`adp_matched`) -- capping this at a fixed depth
  like top-200 was tested and rejected: real per-season ADP depth
  (92-211 players) never approaches `config.py`'s TOP_N_ADP=250 cap,
  and a top-200 cut demonstrably misclassifies real, productive
  late-drafted players (David Garrard 2010, Bo Nix 2024) as
  "undrafted."
- **Undrafted players** begin their expected-contribution window at
  their **first verified active appearance** (from real weekly
  participation data, `data/raw/nflverse/weekly_results_ppr_2006_2025.csv`
  -- not approximated).
- Replacement credit applies only to games missed **within** that
  window. Games before a window opens are neither credited nor
  debited -- they're outside the window entirely, not treated as
  zero-value missed games.
- Games actually played always use actual fantasy points, never
  replacement points on top of real production.

Source: `production_weight_and_boundary_calibration.py::build_adp_aware_aatp()`.

## 2. AATP (Availability-Adjusted Total Points)

```
AATP = actual_fantasy_points + replacement_PPG(position, season) x games_missed_within_window
```

`games_missed_within_window = G(season) - games_played`, where
`G(season)` is the **verified** historical regular-season length (16
games 2006-2020, 17 from 2021 on) -- not derived from
`max(games_played)` in the data, which contains two known single-row
anomalies (Emmanuel Sanders 2019, Rashid Shaheed 2025) traced to
mid-season team changes, not real 17/18-game seasons.

Purpose: credit a player's roster spot with what a realistic
replacement would have produced during games actually missed, rather
than treating a missed game as zero. Not a weekly-lineup-optimization
model -- a season-long fairness adjustment.

## 3. PPG reliability -- normalized shrinkage, k=5

```
PPG_AR = ppg_ppr - replacement_PPG(position, season)
reliability_multiplier(games, k) = (G+k) x games / (G x (games+k))
PPG_AR_eq_shrunk = PPG_AR x (G+k) x games / (games+k)
```

**k=5 is a continuous confidence parameter, not a minimum-games
cutoff.** It reaches exactly 1.0 (full trust) only at a complete
season and is strictly increasing everywhere in between -- verified
numerically, not asserted. Selected over hard minimum-games rules
(4/6/8 games), which were rejected after demonstrating a real,
damaging artifact: they treated Deshaun Watson's real 7-game 2017
season nearly as harshly as a 1-game sample, purely because of which
side of an arbitrary threshold he fell on. k=5 was chosen over k=2
(too permissive -- failed to separate CMC 2020 from Watson/Henry) and
is empirically nearly indistinguishable from k=4 through k=8 on actual
rankings (0.997+ correlation) -- a conceptual calibration choice
(matches a stated confidence progression: ~begin believing at 4 games,
~generally believe at 8, ~substantially trust at 12, ~99% by 16, exact
100% at 17), not an accuracy-driven one.

Source: `normalized_shrinkage_comparison.py`.

## 4. Production composite

```
production_composite = 0.5 x AATP + 0.5 x PPG_AR_eq_shrunk
```

Provisional 50/50 weighting -- not yet finalized (60/40, 40/60, and
the LWI-precedent-derived 51.4/48.6 split were all tested and found
statistically indistinguishable on real rankings; the weight choice
remains open pending further calibration).

**Continuous, not a dual hard gate.** A geometric-mean version
(clipping negative terms to zero) was tested and explicitly rejected:
it recreated a harsher cliff than the hard-gate approach it was meant
to replace, provably collapsing every below-replacement PPG value to
an identical zero regardless of how negative it actually was (shown
both synthetically and on three real below-replacement QB seasons).

## 5. Meaningful-production gate -- p82.5, position-specific

Fixed, position-specific `production_composite` floors, calibrated
once from the full historical reference population (not re-derived
per season) and held constant thereafter -- preserves the Absolute
Impact property that different seasons can produce different numbers
of qualifiers.

**p82.5 selected over p85 and p80**, via a face-validity audit using
position-appropriate meaningful-usage ranges derived from the
already-approved `flex_rb_wr_heavy` replacement definition
(QB<=12 / RB<=29 / WR<=29 / TE<=13 -- itself the empirically-derived
"last plausible starter" boundary, not a new assumption):

- **p85 excluded real, plausible Stars-by-Value candidates** before
  the value stage could evaluate them -- Dion Lewis 2017 (round 13,
  RB13 finish, full season, +75 raw surplus) and Nyheim Hines 2020
  (round 12, RB15, full season, +53 raw surplus) both fail p85 by a
  razor-thin margin despite real, substantial positive surplus.
- **p82.5 preserves both**, along with the broader pattern of
  real late-round, full-season, meaningfully-positive-surplus players
  p85 was removing (Dak Prescott 2018, Darrel Williams 2021, among
  others).
- **The weakest p82.5 survivors were audited directly**, not assumed
  safe -- the bottom ~15 gate-passers are either (a) early/mid-round
  picks whose modest composite doesn't matter, since the value stage
  will reject them on cost anyway, or (b) genuinely late-round/
  undrafted players with modest-but-real, fairly-computed production
  (Rishard Matthews 2015, Malcolm Floyd 2012 -- real cases where a
  low raw positional finish is explained by fair replacement credit
  for missed games, not a construction error). Nothing in the bottom
  of the surviving set read as an error or obvious noise.
- **p80 was found more permissive than necessary** -- it admits
  additional cases (Austin Ekeler 2018, Gus Edwards 2023) beyond what
  p82.5 already rescues, at the cost of also admitting noisier,
  harder-to-verify cases. p82.5 is the smallest relaxation from p85
  that fixes the demonstrated false-negative problem.

Source: `production_weight_and_boundary_calibration.py`,
`aatp_round_refit_and_short_season_calibration.py`, and the
position-appropriate re-audit (this conversation).

## 6. Value -- raw absolute surplus

```
surplus = actual_AATP - expected_AATP(draft_round, position)
```

Preferred over percentile-rank, z-score, and ratio-based alternatives
specifically because it preserves real magnitude -- central to the
Absolute Impact philosophy, which exists to let genuinely extreme
seasons read as extreme rather than being normalized away. Ratio
surplus was rejected outright (mathematically undefined/unstable when
expected AATP is near zero, exactly the range where late-round value
stories live). Winsorizing legitimate extremes was explicitly
rejected: it would have clipped Mahomes 2018, Lamar Jackson 2019, Cam
Newton 2011/2015, and Cooper Kupp 2021 -- the exact seasons this
methodology exists to find, not noise to suppress. Winsorization
remains appropriate only for genuine data-quality errors, handled
separately (see verified season-length fix above), never for real
extreme performances.

## 7. Expected AATP by round

Fit via **honest expanding windows only** (prior seasons predicting
future seasons, minimum 3 prior seasons before any prediction) --
never leave-one-season-out, which would leak future seasons backward.
Uses **all trustworthy ADP observations** for fitting (capping at a
fixed depth like 200 was tested and found to hurt, not help: no
accuracy benefit, and it starves the already-thin round-15 sample
down to as few as 3 training rows in some folds).

**2010 is the first leakage-free scoreable season -- derived once,
here, not treated as an unexplained constant elsewhere.** Trustworthy
ADP fitting data begins in 2007. The expanding-window rule above
requires a minimum of 3 prior seasons before any prediction is made.
2007 + 3 = 2010: the first season with enough honest prior history to
fit `E_P` without leaking future seasons backward. Every other
reference to "2010-2024" or "the study scope" elsewhere in this
document (sections 9, 11) means exactly this -- the first season this
rule allows, not an independently chosen cutoff.

**Positional offsets (QB+RB) remain the simplest supported choice**,
reconfirmed under the fully settled construction: `QB_RB` (MAE 40.98)
is statistically indistinguishable from the full four-position ceiling
(`all_four`, MAE 40.58), while `TE_only` and `WR_only` alone barely
beat doing nothing at all. This is provisional, not final -- it has
already been shown to shift once (raw points -> PAR -> AATP each
changed which positions needed correcting), so it should be
re-verified again if the production composite's weighting or the gate
changes materially.

**Recency weighting (5-year half-life) kept, QB-specific**: reconfirmed
significant for QB (MAE 44.60 -> 40.51, p<0.0001) under the fully
settled construction, not significant for RB (p=0.11) or WR (p=0.98).
Worth noting honestly: under recency weighting, TE's *pooled*-curve
prediction (TE isn't part of the QB_RB offset) gets measurably worse
(38.13 -> 38.79, p=0.0002) -- out of scope for the current offset
choice, but worth remembering if TE offsets are revisited later.

## 8. Weekly consistency -- deliberately not added

Median weekly points and proportion-of-usable-weeks (position-specific
threshold = that season's own `replacement_PPG`) were both tested as
candidate additions and **rejected**. Neither showed a robust
out-of-sample improvement over the production composite alone against
the championship-roster benchmark (median: not significant, p=0.41,
no out-of-sample gain; usable-weeks: significant in-sample, p=0.0038,
but the out-of-sample picture was mixed -- AUC improved trivially,
Brier score got worse). Both candidates, tested illustratively, would
have meaningfully downgraded Derrick Henry's real, historically
celebrated 2018 season (a full 16-game season carried by one legendary
game) -- exactly the kind of boom-driven-but-legitimate performance
this methodology should not penalize. Trimmed-mean (dropping the
single highest week) was evaluated as a third candidate and found
*less* diagnostic than either of the above on the real Penny/Martin
test case, despite sounding more sophisticated. **The real gap this
testing surfaced (Rashaad Penny 2022 vs. Doug Martin 2013, similar
season averages, very different weekly repeatability) is genuine and
unaddressed -- but no lightweight fix tested here earns its added
complexity without a real cost elsewhere.**

## 9. Minimal-market-cost expectation -- opportunity-based, position-specific

**Problem this solves**: `E_P` (section 7) and the final score both require
a real ADP round, so any player with `data_quality_flag = no_adp_match`
was previously unscoreable no matter how good the season -- including,
by direct count, 111 of 823 (13.5%) 2010-2024 elite-tier seasons
(top-15 PPG at position, >=8 games), among them Adrian Peterson 2012,
Justin Herbert 2020, Odell Beckham Jr. 2014, Puka Nacua 2023, and
Victor Cruz 2011. Investigated and settled across
`docs/ADP_SOURCE_MATRIX.md`'s "No-ADP remediation" decision-history
entries (parts 1-6); this section records only the final settled
construction.

**Three status groups, kept explicitly separate**:
- **Normal ADP-scored**: a real, matched `adp_round` exists. Uses the
  real round-based `E_P` from section 7, unchanged.
- **Verified minimal-market-cost**: no real ADP match, but corroborating
  evidence (below) indicates the player was genuinely outside normal
  draft depth, not just missing evidence. Gets the position-specific
  expectation calibrated in this section.
- **Unresolved / ambiguous (unscoreable)**: everything else with no
  ADP match -- including cases with real evidence a market cost
  existed but no recoverable number (e.g. Adrian Peterson 2012 --
  MFL confirms real, substantial 2012 draft relevance, rank 15, 77%
  of drafts selected him, but that is not usable as a canonical round),
  and cases where the evidence genuinely conflicts. **These never
  receive the minimal-market-cost baseline** -- assigning it to a
  player who likely had real, non-trivial cost would manufacture
  exactly the inflated-surplus risk this whole investigation exists to
  avoid.

**Classifying "verified minimal-market-cost"**: three-way corroboration
of (a) absence from the canonical FFC ADP source, (b) a rule-based
classifier built from real NFL draft capital, rookie status, and prior-season
production (all pre-outcome signals, includes a narrow rookie-QB
Week-1-starter-vs-backup correction from real depth-chart data), and
(c) MyFantasyLeague's `PERIOD=AUG15` preseason `draftSelPct` (2011+
only -- MFL has no usable historical data before 2011) as a second,
independent ADP provider. A player lands in `minimal_market_cost` only
when the classifier and MFL corroborate each other; disagreement is
left `ambiguous`, not resolved by guessing.

**What the expectation represents, and why the obvious first answer was
wrong**: the first candidate baseline was `0.5 x replacement_ppg x G`
-- algebraically, the production composite of a hypothetical player
performing at exactly replacement rate for a full season. Tested
against the verified minimal-market-cost population, it produced real
false negatives: Herbert 2020 (a top-10 real QB finish), Cruz 2011,
and Nacua 2023 all missed their position's Star cutoff, while
Kyren Williams 2023 and Gary Barnidge 2015 cleared. Examined closely,
that baseline was answering the wrong question. `replacement_ppg` is a
**role-conditional** rate -- the average output of the readily-available
pool *given they get real playing time* (that's how it's used
elsewhere: fairly backfilling an *established* player's missed games).
A genuinely minimal-cost player's real preseason expectation is not
"replacement rate, guaranteed a role" -- it has to also price in the
real chance of getting **no meaningful role at all**, which is exactly
why nobody drafted them. Treating the conditional rate as unconditional
structurally overstated the baseline. (No literal double-subtraction
was found in any individual player's score -- Kyren Williams, the one
case with real missed-game replacement credit in his own AATP, was
checked directly -- but the *conceptual* mismatch was real and was
confirmed by both a mechanistic argument and an empirical test that
agreed independently.)

Two simple alternatives were considered and rejected in favor of the
approach below:
- **Mapping MFL's `draftSelPct` to an implied late round**, then
  reusing the section-7 round curve: rejected for false precision --
  it would manufacture a specific implied round from a noisy,
  **position-biased** percentage (MFL drafts QBs measurably earlier
  than other positions at the same real round -- confirmed directly,
  not assumed, comparing MFL selection rates for real FFC-matched
  players at the same round across positions, n=747) with no
  correction built in.
- **Treating all minimal-market-cost players as the deepest reliably
  modeled round**: rejected for the opposite reason -- it actively
  *overstates* cost. Real round-15 MFL prevalence (28-58% depending on
  position) is still well above what verified minimal-cost players
  actually showed (their real MFL selection rates ran 0-18%), and the
  deepest modeled round is itself a thin, unstable anchor (n=1 in the
  current fit).

**The settled approach -- opportunity probability x replacement-implied
rate, season-varying**:

```
minimal_market_cost_E_P(position, season) = opportunity_probability(position) x 0.5 x replacement_ppg(position) x G(season)
```

**`G(season)` here is the same verified, season-varying schedule
length defined in section 2 (16 games through 2020, 17 from 2021 on)
-- not a flat constant.** This was a real inconsistency in an earlier
draft of this section, caught during an implementation-readiness
review: `replacement_ppg(position)` is the already-settled
equal-weighted full-history rate (unchanged, not being recalibrated
here), but `G` must vary by the row's own season, exactly as it does
everywhere else in this document. `opportunity_probability` is the
fraction of a **broad, pre-outcome**
population -- every 2011-2024 `no_adp_match` QB/RB/WR/TE player-season
classified `minimal_market_cost` by the corroboration above, n=3,418,
*not* the smaller population that happened to also clear the p82.5
gate (using the gate-cleared population here would have reintroduced
survivorship bias into the very thing being estimated) -- that went on
to earn **meaningful usage**, defined without reference to fantasy
points or the p82.5 gate: QB pass attempts >= 100, RB touches
(carries + targets) >= 40, WR/TE targets >= 20 (roughly a month of
real, sustained usage -- the level at which a real manager would
actually consider rostering them). Equal-weighted across full history
(2011-2024, the full window MFL coverage allows) -- checked for era
drift (four eras, 2011-14 through 2021-24) and found none large or
monotonic enough to justify recency weighting.

**Estimated opportunity probabilities**: QB 24.7% (n=413), RB 29.0%
(n=775), TE 28.5% (n=965), WR 36.8% (n=1,265).

**Final settled constants -- QB 31.0 / RB 23.1 / WR 35.7 / TE 19.3 are
17-game-era reference values (`G=17`, seasons 2021+), not timeless
constants**:

| Position | Opportunity probability | Replacement PPG (equal-wtd, settled) | **MMC E_P, G=16 (2007-2020)** | **MMC E_P, G=17 (2021+)** |
|---|---|---|---|---|
| QB | 24.7% | 14.746 | 29.14 | **31.0** |
| RB | 29.0% | 9.361 | 21.72 | **23.1** |
| WR | 36.8% | 11.423 | 33.63 | **35.7** |
| TE | 28.5% | 7.970 | 18.17 | **19.3** |

**Recomputed under season-varying `G` and checked against the full
54-row verified minimal-market-cost population: no label changes.**
Every pre-2021 row's `E_P` is 1.1-2.1 points lower under the correct
`G=16`, which (since a lower `E_P` only ever *raises* a score) can
only turn a non-Star into a Star, never the reverse -- and no case in
the verified population was close enough to the cutoff for that small
a shift to matter. The three pre-2021 named cases specifically:
Herbert 2020 (score 202.68 vs. 202.03 under flat `G=17`), Cruz 2011
(188.34 vs. 187.61), Barnidge 2015 (161.25 vs. 160.85) -- all still
clear by wide margins. Williams 2023 and Nacua 2023 are both real
17-game seasons and are unaffected by this correction entirely.

**Sensitivity**: the 100-attempts/40-touches/20-targets thresholds are
a convention, not a uniquely correct cutoff -- but re-derived under three
alternative usage definitions (a looser bar: QB att>=35/RB touches>=15/WR-TE
targets>=8; a stricter bar: QB att>=200/RB touches>=75/WR-TE targets>=40;
and games-played>=8 as a fully different signal), **the resulting
classification of every named case was identical**. Only the weakest,
least defensible definition tested (raw games-played >= 4, which
doesn't require real usage at all) produced a different result -- Puka
Nacua missing by 0.52 points -- which is evidence against that
definition, not against the settled one.

**Face validity, verified minimal-market-cost population only**:
Justin Herbert 2020, Victor Cruz 2011, Puka Nacua 2023, Kyren Williams
2023, and Gary Barnidge 2015 all clear their position's Star cutoff
under these constants. No obvious false positive appears anywhere in
the verified population (the only case that clears under any tested
variant, Nick Foles 2013, appears solely at the literal
zero-expectation extreme -- not under the settled constants or any of
the tested alternatives -- and even then only by a 4-point margin).

Source: `docs/ADP_SOURCE_MATRIX.md`, "No-ADP remediation" parts 1-6.
Computed directly this pass; not yet captured in a permanent, reusable
script -- population and usage data cached to scratch space, not
`data/raw/`.

## STILL OPEN: post-gate continuous score

Everything above (sections 1-8) is settled, provisional construction,
confirmed by repeated empirical testing. **Everything below is
actively unresolved** -- do not treat it as settled, and do not build
against it until it converges.

### A real structural problem was found, not yet fixed

The first four candidate combination forms proposed (equal / 70-30
production / 70-30 value / signed-log, each combining
`production_composite` with `surplus`) were tested and found to
**double-count AATP**, algebraically proven and verified numerically:

```
production_composite = 0.5 x AATP + 0.5 x PPG_eq_shrunk
surplus               = AATP - expected_AATP
0.5 x composite + 0.5 x surplus = 0.75 x AATP + 0.25 x PPG_eq_shrunk - 0.5 x expected_AATP
```

"50/50 production and value" does not give those two concepts equal
influence -- it gives AATP three times the effective weight of
PPG_eq_shrunk. Shifting nominal weight toward "value" makes this
*worse*, not better (70/30-value pushes AATP's effective weight to
0.85), since `surplus` is itself mostly AATP. Confirmed via influence
decomposition (effective weight x term std) on the real gated
population: AATP alone contributes more to the equal-weighted score's
spread than PPG_eq_shrunk and expected_AATP combined.

Floor-relative production (`composite - floor`) and fixed
historical-unit rescaling were both evaluated as remedies and found to
address a *different* problem (cross-position comparability / raw
scale) without fixing the double-counting itself -- subtracting or
rescaling by a constant doesn't remove a shared underlying term.

### Two candidate remedies compared -- neither selected

**A. Three true primitives, independently weighted:**
```
final_score = wA x AATP + wP x PPG_eq_shrunk - wC x expected_AATP
```
Each ingredient appears exactly once, by construction. Three free
parameters -- maximally flexible (AATP and PPG_eq can be given
independent cost-sensitivity), but discards the already-settled 50/50
production composite entirely and requires anchoring three numbers
with no obvious reference point.

**B. Production minus a scaled acquisition-cost penalty (current leading candidate):**
```
P    = 0.5 x AATP + 0.5 x PPG_eq_shrunk               (the settled production composite, unchanged)
E_P  = expected value of P by (round, position)        (refit directly on P, NOT assumed to inherit AATP's offsets)
Stars-by-Value score = P - lambda x E_P
                      = (1-lambda) x Production + lambda x (Production - Expected Production)
```
Algebraically confirmed to avoid double-counting (each of AATP and
PPG_eq_shrunk appears with a single clean coefficient: 0.5 and
0.5-lambda respectively once E_P is expanded) -- verified symbolically
and numerically. **One free parameter (lambda) instead of three**,
and it directly extends the already-agreed production composite
rather than replacing it. The real trade-off against remedy A: lambda
applies the *same* cost-sensitivity to both AATP and PPG_eq_shrunk by
construction -- it cannot independently discount one more than the
other the way three separately-weighted primitives could. This is a
deliberate simplification, not a hidden flaw.

**E_P must be fit on the full composite P, not on expected_AATP
alone** -- using AATP-only expectation would leave PPG_eq_shrunk's
half of production completely unpenalized by draft cost at any
lambda, an internal inconsistency once the penalty is meant to apply
to the same quantity production is built from.

**Refitting E_P against P (expanding window, not assumed to inherit
AATP's offsets) reconfirmed QB_RB as the leading positional-offset
variant** (MAE 41.55, edging out the four-position ceiling at 41.60)
and reconfirmed recency weighting's QB-specific benefit (p<0.0001) --
though recency now shows a small, real *cost* for RB and WR under
this target (p=0.024, p=0.023) that wasn't significant when the
target was AATP alone. QB's gain is large enough that applying
recency globally still nets positive, but this is a real, disclosed
nuance, not a clean "recency only helps."

**Lambda sweep (0.25 / 0.50 / 0.75 / 1.00), tested on the full gated
population and real historical cases, not just headline rankings**:
lambda is a genuinely consequential choice -- Spearman correlation
between lambda=0.25 and lambda=1.0 is only 0.785 across the full
gated population (n=1193), and top-25 overlap between the extremes is
just 12/25. Legendary full-value seasons (CMC 2019) stay at #1
regardless of lambda. Late-round efficiency stories (Dion Lewis 2017,
Nyheim Hines 2020) climb by 350-450 rank positions as lambda rises
from 0.25 to 1.0. Expensive underperformers (Tyreek Hill 2024, Cooper
Kupp 2023, Keenan Allen 2016 -- all real, verified round-1/2 picks
with real negative P-minus-E_P gaps) fall toward the bottom of the
gated population as lambda increases, confirming the penalty works in
both directions as intended.

**A real, disclosed scope limitation surfaced by the boundary-case
check**: players without a trustworthy ADP match (e.g., Rishard
Matthews 2015, Malcolm Floyd 2012 -- both flagged as marginal p82.5
survivors in the earlier audit) cannot be scored under this framework
at all, since E_P requires a real draft round. This isn't new --
`surplus` always had this limitation -- but it means the eventual
implementation needs an explicit answer for undrafted gate-passers
(production-only scoring, or exclusion from the final ranking), not a
silent gap.

**Remedy B confirmed as the structure.** Remedy A (three independently
weighted primitives) was not pursued further -- remedy B's single
parameter, direct extension of the already-settled production
composite, and provable absence of double-counting made it the
clearly better-supported candidate once both were compared on real
data.

### lambda = 0.35, selected provisionally

Chosen philosophically, from real historical pairwise data, not by
optimizing a predictive benchmark. Reference points from ~711,000
pairwise comparisons among p82.5 gate-passers: a *typical* production
gap is ~45 points, a *substantial* one (90th percentile) is ~120; a
*typical* surplus gap is ~42 points, a *truly exceptional* one (95th
percentile) is ~128. Using the exact crossover formula
`lambda* = |dP| / (|dP| + |dS|)`:

- At lambda=0.35, on real crossed pairs (higher production, lower
  surplus), the higher-production player still wins **88.4%** of the
  time when the value edge is merely ordinary (below median), and the
  higher-surplus player wins **88.8%** of the time when the value edge
  is genuinely exceptional (top decile). The middle band (large-but-
  not-exceptional value edges, 50th-90th percentile) sits close to a
  genuine coin flip (53.6%) -- the philosophically appropriate
  behavior for a case that's neither clearly modest nor clearly
  exceptional.
- lambda=0.45-0.50 were rejected specifically because they let
  *merely large* (not exceptional) value edges already dominate
  production in that same middle band (63-72% value wins, not a coin
  flip) -- a looser match to "production remains primary in ordinary
  comparisons, exceptional value earns the right to override it."

Face validity on real cases confirmed the intended behavior: CMC 2019
stays at #1 regardless of lambda in the tested range; Aaron Rodgers
2012 (much higher production, small surplus) stays comfortably ranked
above Sam LaPorta 2023 (lower production, 267% of expectation) at
lambda=0.35; Travis Kelce's 2014 (178% "return" but modest absolute
production, near the gate floor) stays near the bottom of the gated
population at every candidate lambda -- confirming raw absolute
surplus (not a percentage) is doing its job here too.

### Full ranking, lambda=0.35 -- computed and audited

Top 25 is uniformly composed of real, well-known, celebrated fantasy
seasons (CMC 2019/2023, Cooper Kupp 2021, Arian Foster 2010, David
Johnson 2016, Todd Gurley 2017/2018, Rob Gronkowski 2011 [round 10],
Cam Newton 2011, Lamar Jackson 2019/2024, Mahomes 2018) -- strong face
validity. Era composition of the top tiers tracks the underlying
season-count weighting closely, with no dramatic skew toward recent
or older seasons.

**A real, unresolved cross-position problem was found, and must be
flagged rather than smoothed over**: RB holds 64% of the top-25 and
56% of the top-50 despite being only 28% of the gated population; TE
holds 4% of the top-25 and 2% of the top-50 despite being 16% of the
gated population, and **the entire bottom 15 of the full 1,193-player
ranking are TEs** (all with negative surplus). Position-specific score
percentiles confirm the scale gap directly: a 90th-percentile RB
season (206.5) already exceeds a 95th-percentile TE season (172.9).
This is the same structural asymmetry first identified in the
original cross-position calibration check many turns before AATP,
shrinkage, the gate, or lambda existed -- `flex_rb_wr_heavy` fixed
cross-position comparability for the *production gate* specifically,
but nothing since has touched the *continuous score's* raw-magnitude
scale, which is exactly where this asymmetry still lives. **This will
need to be resolved (most likely via position-specific label
thresholds, mirroring how `p82.5` itself was built) before the final
league-winner label can be considered fair across positions.**

### Converting the continuous score into a binary label -- position-specific fixed thresholds evaluated

**SETTLED -- see Section 10 below for the final values and decision record.** The evaluation, candidate ranges, and calibration process below are kept as the historical record of how those values were reached.

Given the position-scale problem above, a single universal score
threshold was ruled out explicitly (would reproduce an "almost all
RB, no TE" winner list). Also explicitly ruled out: forcing equal
positional representation, and using the same percentile for every
position -- either would just recreate the relative-philosophy label
this project already rejected, one level removed. The chosen
framework instead: **one fixed absolute score cutoff per position,
held constant across seasons, with annual and positional winner
counts allowed to vary naturally** -- the Absolute Impact philosophy
applied to the label itself, not just to the score that feeds it.

**Method**: for each position, computed a percentile grid (p85, 88,
90, 92, 95, 97) over that position's own gated-population score
distribution, then for each candidate: total qualifiers, qualifiers
per season (including zero-winner seasons), championship-roster rate
(reported as corroboration only, never optimized against), the named
players entering/leaving across adjacent candidates, and a
contrasting "good but not winning" zone one tier down (p75-p85) to
check the label draws its line in a face-valid place. Fragility was
tested by moving each leading candidate +/-5 and +/-10 score points
and counting how many player-seasons would flip.

**Per-position candidate grids** (gated population, n and
seasons-covered from lambda=0.35 score, 2010-2024):

| Position | Gated n | p85 | p88 | p90 | p92 | p95 | p97 |
|---|---|---|---|---|---|---|---|
| QB | 187 (15 seasons) | cutoff 179.4, n=28 | cutoff 191.8, n=23 | cutoff 196.3, n=19 | cutoff 200.9, n=15 | cutoff 215.6, n=10 | cutoff 231.5, n=6 |
| RB | 334 (15 seasons) | cutoff 187.4, n=50 | cutoff 198.6, n=40 | cutoff 206.5, n=34 | cutoff 215.2, n=27 | cutoff 233.7, n=17 | cutoff 254.2, n=10 |
| WR | 476 (15 seasons) | cutoff 152.2, n=72 | cutoff 159.6, n=58 | cutoff 166.8, n=48 | cutoff 179.0, n=39 | cutoff 188.3, n=24 | cutoff 201.9, n=15 |
| TE | 196 (15 seasons) | cutoff 134.4, n=30 | cutoff 139.1, n=24 | cutoff 146.5, n=20 | cutoff 149.6, n=16 | cutoff 172.9, n=10 | cutoff 184.8, n=6 |

Championship-roster rate at these cutoffs is uniformly high (QB
100% at every candidate on a small n; RB 67-82%, falling as the
cutoff rises -- elite RB seasons don't always land on the eventual
champion's own roster; WR 75-88%, rising with the cutoff; TE 82-100%,
rising with the cutoff) -- consistent with corroboration, not used to
pick a cutoff.

**Face validity, by position** (named players from the actual gated
ranking, not invented examples):

- **QB**: the entire p85-p92 boundary band (Matthew Stafford 2011,
  Tom Brady 2021, Josh Allen 2024/2023, Justin Herbert 2021, Baker
  Mayfield 2024, Aaron Rodgers 2016, Kyler Murray 2020, Mahomes 2020,
  Joe Burrow 2024, Matt Ryan 2016, Deshaun Watson 2020, Andrew Luck
  2014) reads as legitimately elite, winner-caliber -- no clear miss
  either direction. The p75-p85 contrast zone directly below it
  (Carson Wentz 2017, Russell Wilson 2017/2020, Jayden Daniels 2024,
  RG3 2012) is real "very good starting QB, not the league-defining
  year" territory. A focused range of **p87-90** (roughly cutoff
  188-196, n=19-24) looks best supported: p92 and above thins to
  n=15 and turns fragile (see below) without gaining any clearer
  face-validity separation.
- **RB**: p85-p90 boundary band includes several single-year
  breakouts alongside the expected stars (Matt Forte 2013, Arian
  Foster 2011, Zeke 2016/2018, Darren McFadden 2010, Knowshon Moreno
  2013, Peyton Hillis 2010, Derrick Henry 2024/2020, Bijan Robinson
  2024, Raheem Mostert 2023, Leonard Fournette 2021) -- all real,
  notable, "that back won someone's league that year" seasons, not
  compilers. The p75-p85 contrast zone (LeSean McCoy 2016, Marshawn
  Lynch 2014, DeMarco Murray 2016) is good-RB1-not-transcendent
  territory -- a real, visible break. A focused range of **p85-88**
  (cutoff 187-199, n=40-50) is best supported by RB's own face
  validity. (This is evaluated independently of the RB/TE scale
  problem above -- the position label is not being tightened to
  compensate for that, per instruction.)
- **WR**: the wide p85-p95 band mixes clear stars (Calvin Johnson
  2012, Justin Jefferson 2021, Ja'Marr Chase 2021, DeAndre Hopkins
  multiple) with softer inclusions lower in the band (Randall Cobb
  2014, Diontae Johnson 2021) that read more as "good WR2/low-end
  WR1" than league-winning. The p75-p85 contrast zone confirms this
  --  Tee Higgins 2024, Doug Baldwin 2015, Calvin Ridley 2020 sit
  just below and look like the same tier as the softer p85-90
  inclusions, not a clean break. A focused range of **p90-92** (cutoff
  167-179, n=39-48) is best supported -- it's where the softer
  inclusions drop out.
- **TE**: p85-p90 boundary band (Sam LaPorta 2023, Aaron Hernandez
  2011, Trey McBride 2024, Jason Witten 2010, Eric Ebron 2018, Gronk
  2017, Kelce 2017/2019/2021, Darren Waller 2019, Tony Gonzalez 2012,
  Kittle 2019, Antonio Gates 2014) all read as real, TE1-defining
  seasons given how shallow the position's usable universe is. The
  p75-p85 contrast zone (Jordan Cameron 2013, Austin Hooper 2019,
  Gronk's own down year in 2012) is a clean, visible step down. A
  focused range of **p85-88** (cutoff 134-139, n=24-30) is best
  supported.

**Fragility** (players who'd flip membership under a +/-5 or +/-10
score-point nudge, as a fraction of that cutoff's qualifiers):

| Position | Cutoff | +/-5pt turnover | +/-10pt turnover |
|---|---|---|---|
| QB | 188.0 (~p87) | 4-8% | 25% both directions |
| QB | 201.0 (~p92) | 13-27% | 20-53% |
| RB | 198.6 (~p88) | 8-15% | 18-28% |
| RB | 215.2 (~p92) | 7-15% | 30% both directions |
| WR | 166.8 (~p90) | 10-12% | 17-29% |
| WR | 179.0 (~p92) | 8-21% | 18-50% |
| TE | 139.1 (~p88) | 12-25% | 29-46% |
| TE | 146.5 (~p90) | 10-30% | 30-35% |

No candidate showed pathological fragility (e.g. most of the
population flipping at +/-5pts); the lower end of each focused range
(QB ~188, RB ~199, WR ~167, TE ~139) is consistently less fragile
than the upper end, reinforcing those as the better-supported side of
each range.

**Sample size for Dataset 2/3**: no numeric minimum is specified
anywhere in `LEAGUE_WINNER_TRAITS_SPEC.md` or
`PREDICTION_SPECIFICATION.md` -- the traits spec explicitly
anticipates "a few dozen player-seasons per era" as a normal, workable
sample size for a stratified trait test. Every focused-range candidate
above clears that bar (QB: 19-28 across 15 seasons; RB: 40-50; WR:
39-48; TE: 24-30), though QB and TE stay the thinnest at the tighter
end of their ranges -- worth remembering if a later Dataset 2/3 test
needs to stratify a QB or TE trait further (e.g. by era).

**Result**: this evaluation narrows each position to a focused
range, using each position's own distribution and face validity --
not a shared percentile:

- QB: p87-90 (cutoff ~188-196)
- RB: p85-88 (cutoff ~187-199)
- WR: p90-92 (cutoff ~167-179)
- TE: p85-88 (cutoff ~134-139)

**No cutoff has been selected.** This is still STILL OPEN -- these
are candidate ranges for review, not a final threshold, and nothing
here has been implemented in `config.py` or turned into a label
column.

*(Superseded by the named-case calibration and narrative-blind
validation below, which narrows these ranges to specific provisional
values.)*

### Gap analysis -- is there a natural break, or is this a calibration decision?

Before anchoring on any of the focused ranges above, checked directly
whether a natural separation exists in the score distribution itself,
rather than only reasoning from percentiles and face validity.
Method: sort each position's gated population by score descending,
compute every consecutive gap, and compare the gap size at each
candidate rank (p85-p95) against that position's own median
consecutive gap -- a genuine natural break should look like one gap
standing out sharply from its neighbors, not just "somewhat bigger
than typical."

**Finding: no position has a single dominant natural break sitting
inside its previously-identified focused range.** Local gaps through
roughly p85-93 fluctuate between 0.1x and 8x the median gap at every
position -- consistent with ordinary sampling variation in a
40-90-point neighborhood, not a step change. QB's largest nearby gap
(8.1x median, between Aaron Rodgers 2020 at 205.8 and Tom Brady 2011
at 201.5) sits at p93, no more distinct than three or four other
bumps around it (p86, p90, p91, p94 all land between 2.4x-5.5x). WR
is similar (largest in-zone gap 8.8x median at p95, between Tyreek
Hill 2020 at 188.3 and Calvin Johnson 2012 at 186.5), with several
comparable bumps nearby.

**A genuinely dominant gap does exist for two positions, but well
above the focused ranges evaluated above, not inside them:**

- **RB**: a 28.1x-median gap at p95 (cutoff ~233) -- Alvin Kamara
  2018 / Dalvin Cook 2020 (score 234.5 / 233.3) sit clearly apart from
  James Conner 2018 / Saquon Barkley 2024 (225.4 / 225.2) just below.
  Nothing else in the RB distribution comes close to this size (next
  largest in-zone gap is 6.2x median, at p89).
- **TE**: a 17.4x-median gap at p94 (cutoff ~156-160) -- Rob
  Gronkowski 2014 (160.1) sits clearly apart from Delanie Walker 2015
  (151.7) just below. Nothing else in the TE distribution below that
  point comes close (next largest is 5.4x median, at p87).

Both of these real breaks separate a much smaller, more exclusive
tier (RB: n=17, 1.1-1.4 winners/season; TE: n~12) of unambiguously
historic seasons -- David Johnson 2016, Todd Gurley 2017/2018,
peak-Gronkowski, prime Kelce -- from the merely-great seasons this
conversation has otherwise been treating as plausible winners
(Bijan Robinson 2024, Sam LaPorta 2023, etc.). That is a materially
different, narrower philosophy ("all-time great year" vs. "the season
that won someone's league") than what the focused-range face-validity
review above assumed. QB and WR show no comparable single dominant
break anywhere in the p85-99 zone -- their largest gaps (25-32x
median) are truly isolated one-or-two-player outliers at p98-99
(Aaron Rodgers 2011; Josh Gordon 2013/Antonio Brown 2014), too
exclusive to use as a general cutoff.

**Conclusion**: for all four positions, choosing a cutoff anywhere in
the previously-identified focused ranges (QB p87-90, RB p85-88, WR
p90-92, TE p85-88) is a **philosophical calibration decision**, not
the discovery of a natural boundary -- the data does not hand us a
clean break there. RB and TE do have a real, sharp natural break, but
it sits well above those ranges and encodes a stricter "historic
season" standard rather than the more inclusive "league winner"
standard this conversation has used so far; adopting it would be a
deliberate scope change, not a refinement of the same target.

**Approach going forward**: having run this search and found no
dominant break inside the plausible cutoff region, further undirected
searches for a hidden natural boundary are not planned. A new search
is warranted only if a specific mechanism is proposed that could
plausibly produce one (a clustering phenomenon, a sudden change in
championship correlation, etc.) -- not as a routine re-check. Absent
that, cutoff selection proceeds as calibration: named historical
boundary cases, sensitivity analysis, and face-validity review, aimed
at the question "which cutoff best captures a Star-by-Value season
while minimizing obvious false positives/negatives" rather than
"where is the mathematical cliff."

### Named-case calibration and narrative-blind validation -- provisional thresholds (superseded)

**These thresholds are now SETTLED -- see Section 10.** "Provisional" below reflects the status at the time this subsection was written, before the minimal-market-cost reinforcement check and final sign-off.

With no natural break to anchor on, threshold selection proceeded as
calibration rather than discovery, per the "approach going forward"
note above: named historical boundary cases, sensitivity to small
cutoff movements, and face-validity review, aimed at minimizing
obvious false positives/negatives rather than finding a cliff.

**Method**: for each position, reviewed every player-season in the
boundary band around its focused range (roughly 10-20 seasons above
and below each candidate cutoff), judged individually against
football knowledge of that season, and picked the point that best
separated seasons that plausibly changed a fantasy league from
seasons that were merely good.

**Provisional cutoffs from that review**:

| Position | Provisional cutoff | vs. original focused range |
|---|---|---|
| QB | ~176.5 | Lower than the original p87-90 (188-196) -- Matt Ryan's 2016 MVP season (183.0) and two rookie-breakout seasons (Jayden Daniels 2024, RG3 2012, both ~177) sit below that floor |
| RB | ~188 | Confirms the original p85 floor (187.4) |
| WR | ~171 | Within the original p90-92 range (167-179), no clean sub-break found |
| TE | ~134 | Confirms the original p85 floor (134.4) |

**Narrative-blind validation**: re-ran the boundary judgments for
every debatable case using only three numbers -- production
percentile (within position), surplus percentile (within position),
and draft round -- with all team/season narrative (records, injuries,
"breakout"/"comeback" framing) deliberately stripped out. This was a
bias check, not a re-optimization: does the earlier judgment survive
contact with the same production/value numbers the score itself is
built from, or was it actually driven by name recognition?

Result: **the numeric cutoffs above did not change** -- they were
computed from the score, which was never narrative-based to begin
with, so there was nothing for narrative to have biased in the
cutoff itself. What the check *did* find: several individual
boundary judgments underneath the QB and WR cutoffs did not survive
stripping the narrative. Examples: Tannehill 2020 (R14, 90th-pctile
surplus) and RG3 2012 (R9, 89th-pctile surplus) are statistically
indistinguishable, yet the earlier review called one a clear star and
the other not; Thielen 2018 (90th-pctile production, 89th-pctile
surplus) scores as strong or stronger on the numbers than Alshon
Jeffery 2013 (83rd/99th), which the earlier review favored on
"breakout story" grounds; Gonzalez 2012 and Hooper 2019 (TE) are
nearly numerically identical (83rd-pctile production both) yet were
judged differently. RB and TE mostly held up, with narrower
exceptions (Sproles 2011's "non-bellcow archetype" hesitation wasn't
supported by his surplus percentile, which matched players judged
more favorably).

**What this means, stated explicitly**:

- The recommended numeric cutoffs are unchanged, because they were
  derived from the score (production + value, weighted 65/35 per
  lambda=0.35), never from narrative.
- The narrative-blind review reduced confidence in several
  *individual* boundary calls -- it did not produce evidence that any
  of the four thresholds themselves should move. No new structural
  hypothesis came out of it either (see the "approach going forward"
  policy above -- this was a bias check, not a structure search, and
  it isn't one).
- **QB and WR in particular should be read as calibration ranges, not
  precise discovered boundaries.** Both zones showed boundary cases
  that are genuinely indistinguishable on the numbers the score itself
  uses -- not just close in score, but close on production percentile,
  surplus percentile, and round simultaneously. RB and TE are on
  firmer ground; their boundary reviews mostly survived the
  narrative-blind check.
- **The final thresholds are therefore calibration choices, supported
  by face validity and sensitivity analysis -- not objectively
  "correct" breakpoints.** That is the intended, honest epistemic
  status of a label built on the Absolute Impact philosophy: a
  defensible line drawn through a genuinely continuous distribution,
  not a fact discovered in the data.

**Status**: this closes the position-specific-threshold calibration
work. QB ~176.5, RB ~188, WR ~171, TE ~134 are the provisional
thresholds carried forward. Nothing has been written to `config.py`
and no label column exists yet -- that remains a separate, explicit
implementation step.

### Two distinct future outputs -- not to be conflated

- **Historical label** (what this section evaluates): a binary,
  backward-looking fact -- did this player-season clear his
  position's fixed absolute Stars-by-Value threshold. Used to build
  the historical Dataset 2/3 training population.
- **Future cross-position ranking** (not started, a later design
  question): once Dataset 3's predictive model exists, players would
  be ranked by their *predicted probability* of clearing that same
  threshold going forward. Probability is naturally on a common 0-1
  scale, which is what will make cross-position ranking possible
  without needing the raw score itself to be cross-position
  comparable -- the raw-score scale problem documented above does not
  need to be solved for this to work, because the label it trains
  against is already position-specific by construction.

Source: this conversation's lambda analysis (crossover-formula
derivation, ~711,000-pair distribution, candidate comparison, full
ranking and position/era audit), plus this turn's position-specific
threshold evaluation -- computed directly, not yet captured in a
permanent, reusable script. Full ranking saved to
`research/output/dataset3/stars_by_value_score_lambda035.csv`
(gitignored, regenerable).

## 10. Position-specific Stars-by-Value thresholds -- SETTLED

**Final values**:

| Position | Threshold |
|---|---|
| QB | 176.5 |
| RB | 188 |
| WR | 171 |
| TE | 134 |

**These are settled calibration choices, not discovered natural
breakpoints.** Section "Gap analysis" above already established this
explicitly: no position showed a single dominant natural break inside
the plausible cutoff region. Choosing a value anywhere in that region
was always going to be a calibration decision grounded in face
validity and philosophy, not a fact waiting to be found in the data --
and that is how these four values were reached: named-case boundary
review, sensitivity to small movements, a narrative-blind validation
pass, and, most recently, a direct reinforcement check against the
minimal-market-cost population.

**The minimal-market-cost resolution (section 9) reinforced these
thresholds rather than requiring any of them to move.** When Herbert
2020, Cruz 2011, and Nacua 2023 first became scoreable, they missed
their cutoffs under the initial (100% replacement-implied)
minimal-cost baseline -- but the diagnosis was that the *baseline* was
answering the wrong question (see section 9), not that the
*thresholds* were miscalibrated. Once section 9's opportunity-based
constants were settled, all five relevant minimal-cost cases clear
their position's threshold by wide, non-borderline margins:

| Player | Score | Cutoff | Margin |
|---|---|---|---|
| Justin Herbert 2020 (QB) | 202.0 | 176.5 | +25.5 |
| Victor Cruz 2011 (WR) | 187.6 | 171 | +16.6 |
| Puka Nacua 2023 (WR) | 184.4 | 171 | +13.4 |
| Kyren Williams 2023 (RB) | 232.6 | 188 | +44.6 |
| Gary Barnidge 2015 (TE) | 160.9 | 134 | +26.9 |

No other player in the 54-row verified minimal-market-cost population
clears any threshold beyond these five. This also closes the loop on
the cross-position raw-score problem first flagged early in the STILL
OPEN section above ("a real structural problem was found") --
position-specific thresholds were always the intended resolution, and
that resolution now demonstrably works correctly across both the
ADP-matched and minimal-market-cost populations, not just the
population it was originally calibrated against.

**QB and WR retain more genuine boundary ambiguity than RB and TE.**
This was true when the thresholds were first calibrated and remains
true now -- nothing in the minimal-market-cost work changed it either
direction. QB's debatable zone (Ryan 2016, Daniels 2024, RG3 2012,
Burrow 2022, Tannehill 2020) and WR's (Jeffery 2013, White 2010,
Thomas 2018, Thielen 2018) both showed real players within a few
points of the cutoff whose inclusion or exclusion survived
narrative-blind scrutiny but never resolved to full confidence. RB and
TE's boundary reviews were comparatively cleaner throughout. This
asymmetry is disclosed, not hidden, and is not a reason to move any
threshold absent new evidence -- it is a description of how much
residual judgment each position's cutoff carries.

**Evidentiary basis, summarized**: face validity (named historical
boundary cases reviewed position by position), sensitivity analysis
(+/-5 and +/-10 point movement tested, no pathological fragility
found), a full narrative-blind re-review (several individual boundary
judgments changed under scrutiny; the cutoffs themselves did not need
to), a gap analysis that confirmed no natural breakpoint exists
anywhere near the plausible region for any position, and, this pass,
the minimal-market-cost reinforcement check above. No genuinely new
evidence surfaced that argues for moving any of the four values.

**Decision: SETTLED.** QB 176.5, RB 188, WR 171, TE 134. Not yet
implemented in `config.py` or wired into any canonical label column --
that remains a distinct, separate step.

## 11. Historical label schema -- SETTLED

**Status: SETTLED.** Everything settled through section 10 answers
what score a player gets and what cutoff it faces; this section
settles the output schema -- what the label column(s) actually
contain. Revised three times before approval: the first draft routed
production-gate failures to `out_of_scope`/`NULL` (corrected -- see
"Why gate failure is a label, not a NULL" below); the second draft
used a single `star_by_value_threshold` field for both the production
gate and the final score cutoff (corrected -- see "Two thresholds,
not one" below); a subsequent independent-implementer consistency
review found five further specification gaps (an undefined status for
`matched_needs_review` rows, a flat vs. season-varying `G` ambiguity
in the section-9 formula, an unresolved ordering conflict between the
production gate and the temporal fit-window boundary, an unstated
derivation for the 2010 start year, and no general rule for the 2010
cohort specifically), all resolved below. Every correction is kept in
the record rather than silently smoothed over, consistent with this
project's standing convention of not deleting decision history.

**Design principle**: separate three logically independent questions
into separate columns rather than one categorical enum -- substantive
outcome (`star_by_value_label`), whether the player could be scored at
all (implied by `label`/`score` being `NULL` vs. not), and acquisition-cost
provenance (`star_by_value_status` plus the structured/free-text
provenance fields below). A single compound column would require
downstream consumers to parse a string to find a valid 0/1 target --
fragile, and exactly the kind of silent-failure risk this whole
investigation exists to avoid. It would also make "give me every
scoreable row regardless of outcome" or "how many labels rest on the
minimal-market-cost provenance" require string parsing instead of a
`WHERE` clause, and would force a combinatorial redefinition of the
enum every time a new provenance type is added.

### Why gate failure is a label, not a NULL

The first draft of this schema routed any player who failed the p82.5
gate to `out_of_scope` with `label=NULL`, on the reasoning that the
gate is an entry requirement to the whole system. **That was wrong**,
caught before approval: failing the gate is a substantive, *known*
fact -- the player did not produce enough meaningful output to
qualify, full stop, independent of what their acquisition cost was or
whether that cost is even known. Routing it to `NULL` would mean any
supervised model trained on `WHERE label IS NOT NULL` implicitly
conditions on "given the player already cleared the production bar" --
a different, narrower question than the one this label is meant to
answer ("who becomes a Star among the full eligible preseason
population"). This is exactly the kind of scope-narrowing the
minimal-market-cost investigation (section 9) exists to prevent, just
showing up on the production axis instead of the cost axis.

**Operational consequence**: the production-gate check runs
*before*, and independently of, any ADP/classifier/MFL logic. A
player's `below_production_gate` status never depends on whether they
have real ADP, verified minimal-cost status, or unresolved cost
evidence -- production failure alone is dispositive. This does not
reopen or invalidate the classifier + MFL corroboration work in
section 9/`ADP_SOURCE_MATRIX.md` -- that apparatus only ever needs to
run on gate-*clearing*, ADP-unresolved players, which is precisely the
population it was built and tested against throughout. (This ordering
claim needed one more precision pass -- see the next subsection: the
production gate runs before ADP/cost logic, but *after* the temporal
scope check, which was a real, separate ordering question this
document previously left unresolved.)

### Processing order: temporal scope, then production gate, then acquisition-cost resolution

A consistency review surfaced a genuine edge case the ordering above
didn't resolve: a pre-2010 player-season that also fails the
production gate satisfies two different status descriptions at once
(`out_of_scope`, temporal, and `below_production_gate`) with no stated
tie-break. Assigning it `below_production_gate` would make it a real
`label=0` negative in the supervised population -- but doing that
*only* for pre-2010 failures, while pre-2010 gate-*passers* remain
unscoreable (`out_of_scope`, since `E_P` can't be fit that far back),
would build a one-sided, biased training population: real pre-2010
non-Stars included as negatives, real pre-2010 Star-caliber seasons
silently excluded. That asymmetry is worse than the ambiguity it would
resolve, so it isn't the answer. The correct resolution is a strict
four-step order, applied to every player-season without exception:

1. **Temporal/study-scope eligibility.** Season must be 2010 or later
   (section 7's derivation: 2007 + 3 prior-season minimum = 2010,
   the first leakage-free fittable season), position must be
   QB/RB/WR/TE, and `games_played >= 1`. Fail any of these ->
   `out_of_scope`, `label = NULL`, regardless of what the player's
   production or cost situation looks like. **No pre-2010 row is ever
   evaluated against the production gate at all** -- eliminating the
   two-description collision by construction, and keeping the
   pre-2010 population out of the supervised set symmetrically
   (neither its failures nor its successes are labeled), not
   one-sidedly.
2. **Production gate** (section 5, p82.5). Only reached by rows that
   passed step 1. Below the position's floor -> `below_production_gate`,
   `label = 0`. This is where the "Why gate failure is a label, not a
   NULL" reasoning above applies -- and now applies cleanly, since
   step 1 already removed the only case that made it ambiguous.
3. **Acquisition-cost resolution.** Only reached by rows that cleared
   the gate in step 2. Real ADP match, MFL/classifier corroboration,
   or the 2010-cohort fallback (below) determine `adp_scored` /
   `unscoreable_adp_needs_review` / `minimal_market_cost_scored` /
   `unscoreable_drafted_adp_missing` / `unscoreable_ambiguous`.
4. **Score and label.** Only for the two scoreable statuses from step
   3 (`adp_scored`, `minimal_market_cost_scored`): compute
   `score = P - lambda x E_P`, `label = 1` if `score >= star_by_value_threshold`
   else `0`.

This also means the `below_production_gate` negative population
(6,724 rows, reported below) was already correctly scoped to
2010-2024 throughout this document's prior drafts -- no pre-2010 row
was ever counted in that figure. What was missing was the *stated
rule* that makes that scoping non-arbitrary, not the number itself.

### Two thresholds, not one

A single `star_by_value_threshold` field, populated for
`below_production_gate` rows with the position's *final* Star cutoff,
would silently imply those rows were evaluated against that cutoff --
they weren't; they never reached the final scoring stage at all. The
production gate (section 5, p82.5) and the final Stars-by-Value cutoff
(section 10) are genuinely different bars answering different
questions ("did this player produce enough to be in the conversation"
vs. "did this player, once in the conversation, clear the value bar
for their position"), so they get separate columns:

- `star_by_value_production_gate_threshold` -- the position's p82.5
  production-composite floor. Relevant to every row where production
  alone is a meaningful question.
- `star_by_value_threshold` -- the position's final score cutoff
  (section 10). Relevant only to rows that cleared the production gate
  and therefore reached, or would have reached, final score
  evaluation.

| Status | Production-gate threshold | Star threshold |
|---|---|---|
| `adp_scored` | populated | populated |
| `minimal_market_cost_scored` | populated | populated |
| `unscoreable_drafted_adp_missing` | populated | populated (informational) |
| `unscoreable_ambiguous` | populated | populated (informational) |
| `below_production_gate` | populated | `NULL` -- never reached final evaluation |
| `out_of_scope` | usually `NULL` | `NULL` |

The two unscoreable-but-gate-passing statuses populate *both*
thresholds: those rows cleared production and would have faced the
final positional cutoff -- their acquisition-cost evidence, not their
production, is what's missing. `below_production_gate` populates only
the gate threshold, because the final threshold was never a live
question for that row. `out_of_scope`'s gate threshold is "usually"
rather than always `NULL`: it's meaningless for non-skill positions
(no gate is defined) and zero-participation rows, but could in
principle be populated for the temporal-window subtype (a real QB/RB/WR/TE
position does have a real gate value even for a pre-2010 season) if a
future extension of the fittable window ever makes that worth
recording -- not required now.

**Seven mutually exclusive statuses**, checked against the populations
already built in section 9 / `docs/ADP_SOURCE_MATRIX.md`:

| Status | Definition | Approx. n (2010-2024 study scope) |
|---|---|---|
| `adp_scored` | Real ADP match (`matched_clean`), clears the p82.5 gate | 1,193 |
| `unscoreable_adp_needs_review` | Real ADP match, but lower-confidence (`matched_needs_review`), clears the p82.5 gate | 0 currently (see below) |
| `minimal_market_cost_scored` | Verified minimal-market-cost (3-way corroboration agreement, or a documented 2010-cohort manual override), clears the p82.5 gate | 54 |
| `unscoreable_drafted_adp_missing` | Clears the gate; real evidence a draft cost existed (classifier says likely-drafted and/or MFL corroborates real market presence), no usable canonical number | ~107-114 |
| `unscoreable_ambiguous` | Clears the gate; classifier and MFL disagree, or neither signal alone is strong enough to corroborate either direction | ~50-57 |
| `below_production_gate` | Fails the p82.5 gate -- regardless of ADP status. **Only ever assigned to 2010+ rows** (step 1 of the processing order routes anything earlier to `out_of_scope` first) | ~6,724 (5,494 no ADP match + 1,230 ADP-matched) |
| `out_of_scope` | Never reaches the gate at all: pre-2010 season, non-skill position, or `games_played=0` | remainder |

### `matched_needs_review` -- a distinct status, not a silent gap

A `matched_needs_review` row has a real ADP record, just a
lower-confidence match than `matched_clean`. Section 1 already treats
it as "trustworthy" for the AATP active-window rule (`adp_matched`
covers both quality flags) -- a needs-review match is real evidence
the player was a genuine preseason asset, which is enough to place
them in the Week-1-eligible window. It is *not* enough to trust the
specific round number as an `E_P(round, position)` lookup key with
the same confidence as a clean match, so no score is computed. For a
gate-passing `matched_needs_review` row: `score = NULL`, `label = NULL`,
both thresholds populated (same treatment as the other two
gate-passing unscoreable statuses -- the bar is known, the score to
compare against it isn't). A below-gate `matched_needs_review` row is
unaffected by any of this -- production failure is dispositive at
step 2 regardless of ADP quality, so it becomes an ordinary
`below_production_gate` row.

This status currently has zero real rows (the gated population is
100% `matched_clean` today, confirmed earlier in this investigation),
but the rule is now defined rather than silently absent -- a future
data refresh that produces one has a specified outcome to follow.

### The 2010 cohort -- explicit fallback, since MFL cannot corroborate that year

MFL's usable historical ADP data begins in 2011 (confirmed directly --
2007-2010 all return zero real drafts at any query period). For a
2010, gate-clearing, `no_adp_match` player, the three-way
corroboration in section 9 is structurally short one of its three
legs for the entire season, not just for that player -- it cannot run
to completion the way it does for 2011+. The fallback, in priority
order:

1. **Strong evidence a real draft cost existed, but no usable
   canonical number** -> `unscoreable_drafted_adp_missing`.
2. **Strong, independent evidence of genuine minimal market cost**
   (independent specifically meaning *not* the classifier's output
   alone -- a second, real, citable source corroborating minimal
   preseason relevance, of the same evidentiary character as the
   named-source citations already used elsewhere in this
   investigation, e.g. a real contemporaneous ranking/roster report,
   not a restated summary of one) -> a **documented manual MMC
   override** may be applied: `minimal_market_cost_scored`, logged in
   `docs/ADP_SOURCE_MATRIX.md` with the source, the specific evidence,
   and the reasoning, the same way every other override in this
   project is recorded. This is expected to be **rare** -- a narrow
   exception mechanism for the one year MFL structurally cannot help
   with, not a general bypass of the corroboration requirement.
3. **Otherwise** -> `unscoreable_ambiguous`. This is the default,
   safe outcome for the 2010 cohort absent case (1) or (2) -- **the
   classifier's output alone is never sufficient, on its own, to
   produce `minimal_market_cost_scored`** for a 2010 row, exactly as
   it's insufficient (without MFL agreement) for any other season.

**`usable_adp` override provenance -- an IMPLEMENTATION decision, not
a settled specification.** The override schema (section 8a of the
implementation plan) already specifies that a `usable_adp` override
produces `star_by_value_status = adp_scored` -- that mapping was
settled when the schema was designed. What was never specified,
because it wasn't considered at the time, is which
`star_by_value_provenance_type` such a row should carry: the 10-value
provenance enum (settled separately, in the initial `SBV_*` config
commit) has no dedicated value distinguishing "adp_scored via a
reviewed manual override" from "adp_scored via a real, direct
canonical-source match." When `labeling.py` was implemented, this gap
was resolved by using `adp_matched_clean` -- the override supplies a
human-verified, clean-quality number, so it was treated as the closest
existing fit -- but this was an implementation-time interpretation,
not a rule derived from anything settled here. It has never been
exercised against a real row (the 2010 override file is still empty
at the time of this note). If the override mechanism is ever actually
used, this provenance choice should be revisited for face validity
before being treated as final -- and if a real need for the
distinction emerges, the cleaner fix is a dedicated eleventh
provenance value, not continuing to overload `adp_matched_clean`.

**Vick 2010 specifically remains `unscoreable_drafted_adp_missing`.**
The existing lead (NFL.com's "2010 ADP: 14th round" citation) is a
real, named source, but it is a single restated number from one
article with no snapshot date, scoring format, or underlying table --
it does not currently meet this project's source-quality bar for a
canonical number (the same bar applied throughout `ADP_SOURCE_MATRIX.md`),
and it is not independent evidence of *minimal* cost in the sense
case (2) requires -- if anything it's evidence a real, if very late,
cost existed, which is exactly the `unscoreable_drafted_adp_missing`
definition. It stays there unless a future source is judged
sufficient to supply an actual canonical round under the project's
existing standards -- not automatically promoted either direction by
this schema revision.

**Population rules -- when score/label/thresholds are populated vs. `NULL`**:

| Status | `score` | `label` | production-gate threshold | Star threshold |
|---|---|---|---|---|
| `adp_scored` | Computed (round-based `E_P`) | `1`/`0` vs. cutoff | populated | populated |
| `unscoreable_adp_needs_review` | `NULL` | `NULL` | populated | populated (informational) |
| `minimal_market_cost_scored` | Computed (opportunity-based `E_P`) | `1`/`0` vs. cutoff | populated | populated |
| `unscoreable_drafted_adp_missing` | `NULL` | `NULL` | populated | populated (informational) |
| `unscoreable_ambiguous` | `NULL` | `NULL` | populated | populated (informational) |
| `below_production_gate` | `NULL` (documented choice) | **`0`** | populated | `NULL` |
| `out_of_scope` | `NULL` | `NULL` | usually `NULL` | `NULL` |

`score = NULL` for `below_production_gate` is a documented choice, not
an oversight: the raw production composite (`P`) that determined gate
failure is already recorded elsewhere in the pipeline (`P`, `floor`,
`passes_gate`), so nothing is lost for audit purposes -- computing a
full cost-adjusted `P - lambda x E_P` adds no information once `P`
alone is already below the position floor, and for the no-ADP-match
subset of these rows there may not even be a clean cost basis to
adjust against.

### Formalized invariants

- `label = 1` only for a scoreable row (`adp_scored` or
  `minimal_market_cost_scored`) with `score >= star_by_value_threshold`.
- `label = 0` for a scoreable non-Star, or for `below_production_gate`.
- `label = NULL` only when the outcome is genuinely unknowable
  (`unscoreable_adp_needs_review`, `unscoreable_drafted_adp_missing`,
  `unscoreable_ambiguous`) or outside scope (`out_of_scope`).
- `score` may be `NULL` while `label = 0` **only** for
  `below_production_gate` -- any other `label = 0` row must have a
  real, non-`NULL` score.
- No player-season is ever evaluated against the production gate
  before passing the temporal/study-scope check (step 1 before step 2,
  always) -- `below_production_gate` is therefore only ever assigned
  to 2010+ rows, never earlier ones.
- `minimal_market_cost_scored` requires classifier-and-MFL agreement
  for 2011+ rows, or a documented manual override for the 2010 cohort
  specifically -- classifier output alone is never sufficient on its
  own, for any season.
- Pipeline logic may branch on `star_by_value_status` and
  `star_by_value_provenance_type`, but must never read the separate
  evidence-audit artifact (`data/exports/stars_by_value_evidence_audit.csv`
  -- see "Structured provenance, not unconstrained free text" below for
  why this replaced the originally-proposed `star_by_value_evidence_notes`
  column, and the "REJECTED" note there for the preserved original
  proposal).

**Downstream modeling rules**: `WHERE star_by_value_label IS NOT NULL`
is unchanged in its literal form, but its effect is now substantially
different and needs to be understood correctly -- it includes every
`below_production_gate` row (`label=0`, not `NULL`) as a real negative
example, and excludes only the genuinely non-evaluable statuses
(`unscoreable_adp_needs_review`, `unscoreable_drafted_adp_missing`,
`unscoreable_ambiguous`, `out_of_scope`). Checked directly against the
study population (2010-2024, `games_played>=1`, QB/RB/WR/TE): **6,724
rows are real `label=0` negatives** against 1,193 `adp_scored` and 54
`minimal_market_cost_scored` rows -- the actual shape of the corrected
supervised population, not a rounding change. NULL labels remain
retained in every audit/reporting output (dropping them would hide
the exact gap this investigation exists to disclose) and never
silently coerced to `0` anywhere in the pipeline -- when implemented,
this needs an enforced regression test (e.g.
`TestNoSilentNullToZeroCoercion`), the same way
`TestNoDuplicateComponentFormulas` already protects a different
invariant in this project.

**Minimal-market-cost labels carry the same binary meaning as
ADP-scored labels** -- same formula, same lambda, same cutoff; section
10's reinforcement check specifically validated this equivalence. What
differs is the rigor behind the `E_P` feeding it (a large real-market
curve vs. an estimated opportunity probability), which is exactly why
that distinction lives in provenance, not in a different meaning for
the label itself.

**Structured provenance, not unconstrained free text**: a single
free-text provenance field would mean core downstream logic could end
up depending on parsing prose -- the same risk the separated-column
design exists to avoid at the status/label level. Split into two
fields instead:

- `star_by_value_provenance_type` (structured enum, safe for
  downstream code to branch on): `adp_matched_clean`,
  `adp_matched_needs_review`, `mmc_verified_corroborated`,
  `mmc_verified_2010_manual_override`, `evidence_drafted_unresolved`,
  `evidence_ambiguous_disagreement`, `below_production_gate`,
  `out_of_scope_non_skill_position`, `out_of_scope_temporal_window`,
  `out_of_scope_insufficient_participation`. The 2010-manual-override
  value is split out from the ordinary corroborated value deliberately
  -- it's a real, if rare, lower-volume-of-evidence path (section
  above), and an auditor or future re-reviewer should be able to find
  every row that took it without parsing free text.
- ~~`star_by_value_evidence_notes` (free text, human-audit only --
  documented explicitly as never to be parsed by pipeline logic): the
  specific round, specific MFL selection percentage, specific
  classifier reasoning, etc.~~ **REJECTED 2026-07, never implemented.**
  This free-text column on the MAIN SBV dataset was the original
  proposal. It was never built -- `lib/stars_by_value/labeling.py`'s
  `OUTPUT_COLUMNS` never included it. When the gap was found (during a
  canonical-build schema/data-dictionary audit), the design was
  reconsidered and formally rejected in favor of keeping the main SBV
  Parquet/CSV strictly structured and machine-readable, with
  case-specific evidence living in a **separate, strictly one-way
  artifact** instead: `data/exports/stars_by_value_evidence_audit.csv`,
  joined by `(season, player_id)`. Generated during the SAME
  evaluation that determines the canonical row (Option 3A -- see
  `lib/stars_by_value/evidence_audit.py` and `labeling.py`'s
  `assign_sbv_status()`), not a second reconstruction pass, so the
  audit explanation can never drift from the canonical result. An
  audit row exists only for the six provenance types that reflect a
  real evidentiary/classifier judgment call
  (`adp_matched_needs_review`, `mmc_verified_corroborated`,
  `mmc_verified_2010_manual_override`, `evidence_drafted_unresolved`,
  `evidence_ambiguous_disagreement`,
  `known_acquisition_cost_ep_out_of_fitted_range`) -- every other
  provenance type is already fully explained by the canonical row's
  own structured columns and must have zero audit rows. No scoring,
  matching, labeling, or modeling code may ever read this artifact
  (mechanically enforced -- see
  `tests/test_evidence_audit.py::TestNeverConsumedDownstream`).

`provenance_type` is mostly a 1:1 refinement of `status`, with one
deliberate exception: `out_of_scope` gets three real subtypes here
rather than being split into three separate top-level statuses -- that
keeps `status` itself small and stable for anything that touches
`label`/`score` logic, while still letting an auditor distinguish "this
row will never be evaluable" (non-skill position) from "this row could
become evaluable if the fittable window were extended" (temporal). It
also leaves room to add finer-grained provenance later (e.g. a second
canonical ADP source) without ever touching the `status` enum.

**Schema**:

| Column | Type | Allowed values | Definition |
|---|---|---|---|
| `star_by_value_label` | Int8, nullable | `1`, `0`, `NULL` | Qualifies / scoreable-but-doesn't-qualify (incl. gate failure) / cannot be scored honestly |
| `star_by_value_score` | Float64, nullable | real number, or `NULL` | `P - lambda x E_P`; `NULL` for all non-computed statuses (including `below_production_gate`, by documented choice) |
| `star_by_value_status` | String (enum) | `adp_scored`, `unscoreable_adp_needs_review`, `minimal_market_cost_scored`, `unscoreable_drafted_adp_missing`, `unscoreable_ambiguous`, `below_production_gate`, `out_of_scope`, `unscoreable_expected_production_out_of_range` | Always populated, never `NULL` |
| `star_by_value_production_gate_threshold` | Float64, nullable | position's p82.5 constant, or `NULL` | The production bar this row faced (or would face); `NULL` usually only for `out_of_scope` |
| `star_by_value_threshold` | Float64, nullable | position's final cutoff constant, or `NULL` | The final Star cutoff; populated only for rows that cleared, or would have cleared, the production gate. `NULL` for `below_production_gate` and `out_of_scope` |
| `star_by_value_provenance_type` | String (enum) | `adp_matched_clean`, `adp_matched_needs_review`, `mmc_verified_corroborated`, `mmc_verified_2010_manual_override`, `evidence_drafted_unresolved`, `evidence_ambiguous_disagreement`, `below_production_gate`, `out_of_scope_non_skill_position`, `out_of_scope_temporal_window`, `out_of_scope_insufficient_participation`, `known_acquisition_cost_ep_out_of_fitted_range` | Structured provenance; safe for downstream logic to branch on |

~~`star_by_value_evidence_notes` | String, nullable | free text | Human-audit detail only -- never parsed by pipeline logic`~~ **REJECTED 2026-07** -- see "Structured provenance, not unconstrained free text" above. Replaced by the separate `stars_by_value_evidence_audit.csv` artifact (schema below), not a column on this table.

**Evidence-audit artifact schema** (`data/exports/stars_by_value_evidence_audit.csv`, separate file, join keys `season`+`player_id`):

| Column | Type | Definition |
|---|---|---|
| `season` | Int64 | Join key |
| `player_id` | String | Join key |
| `player_name` | String | Denormalized, human-scanning only |
| `star_by_value_status` | String (enum) | Denormalized copy of the canonical row's status -- validated to match, never independently derived |
| `star_by_value_provenance_type` | String (enum) | Denormalized copy, same validation |
| `evidence_type` | String (enum, 6 values) | Structured, NOT free text -- `adp_match_needs_review`, `mmc_corroborated_by_mfl`, `mmc_2010_manual_override`, `drafted_but_adp_unresolved`, `classifier_mfl_disagreement`, `round_beyond_fitted_ep_range` |
| `evidence_summary` | String, free text | Human-audit only, never parsed by pipeline logic |
| `source_reference` | String | Pointer to the specific grounding fact (classifier bucket/MFL result, an override table, a fitted-round comparison) |

**Terminology note**: this supersedes the single catch-all term
`unscoreable_no_adp` used as an interim policy label earlier in this
project's working history (chat only, never written into this doc) --
that population is now split into `unscoreable_drafted_adp_missing`
and `unscoreable_ambiguous`; `out_of_scope` no longer includes
production-gate failures; the single `threshold` field from an earlier
revision is now two fields, so a `below_production_gate` row can never
appear to have been evaluated against a cutoff it never reached; and
`unscoreable_adp_needs_review` is a new status, not folded into either
`adp_scored` or the ambiguous/unresolved categories.

### Whether any ambiguity remains

Checked directly against all five findings from the independent-implementer
review: `matched_needs_review` now has a defined status and population
rule; the minimal-market-cost formula now uses season-varying `G` and
was recomputed against the full verified population with no label
changes; the temporal-scope-vs-production-gate ordering is now a
strict, stated four-step sequence with no case satisfying two status
descriptions at once; the 2010 start year is derived once, in section
7, and referenced rather than restated elsewhere; and the 2010 cohort
has a general fallback rule, not just one worked precedent. No new
ambiguity was introduced resolving them -- the six-status table became
seven cleanly, without touching the meaning of any of the original
six. **No open internal inconsistency remains in this document as of
this revision.**

**Status: SETTLED, not yet implemented.** No column has been added to
any canonical file, `config.py` is untouched. The schema itself is
approved; wiring it into the pipeline remains a distinct, separate
step.
