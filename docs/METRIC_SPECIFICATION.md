# Metric Specification: League Winner Index (LWI) v2.1

**This document is the authoritative, exact specification of the
CURRENT production formula.** It describes only what is actually
implemented in `scripts/05_calculate_metrics.py` right now -- not
rejected alternatives, not the design history. For the "why" behind
each choice and the full falsification-driven history of how this
formula was reached, see `docs/LWI_MODEL_CARD.md`. If this document
and the code ever disagree, the code has a bug -- fix the code to
match this spec, or update this spec if the formula was deliberately
changed and this doc wasn't updated yet.

Target formula, from `docs/VERSION_1_SCOPE.md` (weights fixed since
project inception, never revised):

```
LWI = 46% ADP Value
    + 18% Fantasy Finish Total Points
    + 17% Points Per Game
    + 12% Positional Advantage
    +  4% Playoff Performance
    +  3% Consistency
```

---

## Scope: which rows get an LWI score

- **Eligibility**: EITHER a real ADP match (`data_quality_flag` in
  `matched_clean`/`matched_needs_review`) OR a VERIFIED undrafted
  player (`verification_status == 'verified'` AND
  `adp_status == 'undrafted'`, per `data/manual/adp_status_verification.csv`)
  -- AND `games_played >= LWI_MIN_GAMES` (8, per `config.py`) either
  way.
- **Why undrafted players are included, not excluded**: a metric
  named "League Winner Index" that structurally cannot recognize the
  single most legendary category of league-winning story (the
  undrafted breakout -- James Robinson 2020, Victor Cruz 2011, etc.)
  measures something narrower than its own name implies. See
  "Undrafted player representation" below for the exact mechanism.
- A player who is simply UNMATCHED and not yet researched
  (`verification_status == 'unresolved'`) is explicitly NOT assumed
  undrafted -- "unknown" and "undrafted" must never be conflated. These
  rows stay ineligible, identically to how ALL unmatched rows behaved
  before this mechanism existed, until someone actually verifies their
  real status.
- Rows failing eligibility get `lwi_score = null` and a
  `lwi_eligibility_flag` explaining why (`no_adp_match` or
  `insufficient_games`), not a score computed from insufficient data.

### Approved input-governance revision

**Methodology status: APPROVED by Evan (2026-07 and 2026-08).
Implementation status: IMPLEMENTED; downstream artifact regeneration
pending.** The LWI formula and weights are unchanged. Every
position-relative LWI step uses the separately governed
`canonical_fantasy_position` defined in
[`MATCHING_ARCHITECTURE.md`](MATCHING_ARCHITECTURE.md), rather than
treating the results source's position as authoritative. The raw ADP
position, raw results position, official/team-listed position, and
actual usage roles remain separately preserved evidence.

ADP-source position governs positional ADP ranking and acquisition-cost
provenance unless that ADP-source value is itself shown erroneous.
Canonical fantasy position governs positional finish, replacement,
production, gates and thresholds, LWI position-relative components,
Stars-by-Value/bust production cells, and Dataset 2 position-normalized
traits. When ADP-source and canonical position differ, the discrepancy
must be explicitly adjudicated and documented; a mismatched positional
ADP rank and production cohort must never be used silently. Mixing a WR
ADP rank with a TE results cohort, as happened for N'Keal Harry in
2019-2020, is invalid even when the player identity itself is known
exactly.

Where stronger preseason evidence is absent, the constrained,
row-labeled `processed_results_position_fallback` described in
`MATCHING_ARCHITECTURE.md` is permitted only for otherwise clean
historical rows. It is not independently verified preseason evidence
and cannot supersede an approved override, unresolved decision, known
conflict, or contrary ADP/manual evidence.
An ADP position attached to an unresolved identity or position-matching
conflict is preserved as conflict evidence rather than treated as clean
ADP authority. Decision-bearing position-relative fields, including
positional finish, must be rebuilt from the resolved canonical cohorts.
Bare `position` is canonical-only and null for unresolved rows. LWI,
SBV, expected-production fitting, rankings, and labels must either
exclude those rows explicitly or fail loudly; source-derived position
remains available only through its named provenance fields.

Corrected inputs that change a previously published LWI score receive
an explicit new historical-label/reproducibility revision. This is
input-data versioning, not a formula change: the formula's version and
the corrected-input revision must remain distinguishable so two
outputs cannot appear comparable merely because their weights and
thresholds are identical.

---

## Undrafted player representation

### Approved preseason-market governance revision

**Methodology status: APPROVED by Evan.**

**Implementation status: IMPLEMENTED in clean ADP/base master;
downstream LWI/SBV regeneration pending.**

Preseason acquisition evidence and governed market status are separate
concepts. The approved three-level status field is
`ordinary_market`, `rare_minimal_market`, or `participation_unknown`.
Raw observed ADP, conditional average pick, participation counts or
percentages, source records, and provenance remain separate fields and
must never be overwritten by that classification.

A thoroughly researched source absence may support
`rare_minimal_market` only when player identity is resolved, source
coverage is adequate for that season and position, multiple reasonable
contemporaneous sources were searched, no contrary evidence indicates
ordinary drafting, and the evidence trail is documented. Otherwise the
status remains `participation_unknown`. Neither status permits an
invented numeric ADP or an inferred historical FFC selection percentage.

For Michael Vick in 2010, the approved governed classification is
`preseason_market_status = rare_minimal_market`; the downstream
acquisition/scoring treatment is categorical minimal market cost through
the general governed MMC mechanism. Observed overall ADP, positional
ADP, draft round, and draft pick remain null. The former retrospective
"14th round" rationale is superseded because it came from a draft
do-over, not contemporaneous acquisition evidence. The governing
evidence instead comprises omissions from two deep contemporaneous PPR
sources, corroboration that Vick went undrafted in approximately 90% of
Yahoo leagues, and his preseason backup status behind Kevin Kolb.
"Undrafted in the ordinary market" therefore means
`rare_minimal_market`, not `ordinary_market`, and must not be implemented
as a name-specific methodological exception. If the existing storage/
provenance value `mmc_verified_2010_manual_override` is retained, it
records this instance of the general governed rule; it does not define
or justify bespoke Vick-only methodology.

For 2025, the approved canonical acquisition source is the governed
142-league MFL reconstruction: real, completed, 12-team drafts discovered
through the PPR/redraft report; configuration-verified single-QB,
non-IDP, and non-salary; `bestLineup=Yes` and missing-status
configurations excluded as a conservative best-ball proxy; 14--18
roster spots; and a complete draft through configured roster size before
the NFL opener at September 4, 2025 8:20 p.m. Eastern / September 5
00:20 UTC. Use raw MFL mean picks without normalization. Participation
of at least 35% defines `ordinary_market`; 30% is the principal
sensitivity. Observed players below 35% remain
`rare_minimal_market`, retaining conditional picks and participation
evidence. Absence from every complete governed draft may establish zero
participation in this population but never a fabricated ADP. FFToday's
August 29 12-team PPR consensus remains independent validation only,
never a blended input. The source record must disclose that MFL QBs were
selected approximately 15 overall picks earlier than that consensus,
while RB/WR pricing and within-position ordering were much closer, and
must version the reconstruction, population rules, timing, provenance,
and preserved inputs. This source and its governed participation rules
are live in the accepted clean-ADP and base-master artifacts; downstream
LWI/SBV artifacts remain on their prior regeneration state. Normalization
toward a hypothetical FFC market requires a separate future methodology
decision.

The 142-league population corrects the superseded 147-league accounting.
Four leagues with commissioner-skipped draft slots fail genuine-player
completeness, and league 44425 is excluded separately because identity
`0801` cannot be resolved. The corrected population contains 27,840
directory-resolved selections. The old package remains preserved only as
superseded audit history.

**Downstream scoring behavior, pending coherent LWI/SBV regeneration**:
ONE unified acquisition model -- a verified-
undrafted player is NOT scored via a separate path. They receive a
MODELED overall ADP and then flow through the exact same Component
1-6 pipeline as every drafted player. These modeled proxy fields are not
observed ADP. Where the approved categorical minimal-market-cost rule
supersedes this behavior, downstream coherent regeneration remains
pending.

**Schema** (added by `04_build_master_dataset.py`):
```
overall_adp_observed      real ADP if drafted; null if undrafted (nothing was observed)
overall_adp_model         = overall_adp_observed if drafted;
                           = LWI_GLOBAL_MAX_OVERALL_ADP + 1 if verified undrafted
positional_adp_observed   same idea, per-position
positional_adp_model      = LWI_GLOBAL_MAX_POSITIONAL_ADP[position] + 1 if verified undrafted
adp_status                "drafted" | "undrafted" | null (null = unresolved)
verification_status       "verified" | "unresolved"
adp_proxy_used            boolean
adp_proxy_reason          "global_max_adp_plus_one" | null
```

**Proxy formula**: the GLOBAL maximum observed ADP across ALL 2006-2025
seasons combined, plus 1 -- NOT each season's own deepest pick + 1.
`LWI_GLOBAL_MAX_OVERALL_ADP = 193.5` (proxy = 194.5); positional max by
position: `QB: 30->31, RB: 64->65, WR: 73->74, TE: 60->61`
(`config.py`, fixed constants, not dynamically recomputed -- see that
file's extensive comment for why recomputing automatically would
break reproducibility).

**Why global, not season-relative**: a player taken with a draft's
literal last pick and one who goes undrafted are usually separated by
one manager's last-round decision, not a fundamentally different
acquisition mechanism -- the proxy should reflect that continuity.
Using each season's own source depth instead would unfairly reward
players from seasons where the ADP source happened to be shallower
(e.g. 2022's 146-player depth vs. 2010's 214).

**Verification is a manual, persistent research process**
(`data/manual/adp_status_verification.csv`, same pattern as
`player_name_overrides.csv`/`position_overrides.csv`) -- NOT automatic.
A player absent from the current ADP source is `unresolved` by
default; someone must actively confirm via additional historical
sources (MFL, RTSports, Underdog, etc.) whether they were truly
undrafted everywhere or simply outside this project's current source's
depth, before they can be marked `verified`/`undrafted` and receive
the proxy. See `docs/LWI_MODEL_CARD.md` for the current list of
research candidates (Dataset 5: "No-ADP Breakout Candidates").

Component 1 uses `overall_adp_model` (falling back to `overall_adp`
directly only for synthetic/test data lacking the full schema) -- see
that section below.

---

## Component 1: ADP Value (46% weight)

**What it measures**: return on overall draft capital -- did this
player outperform what history says you should expect from that exact
draft slot, AND did they beat the actual pick spent on them.

**Formula**:

```
expected_finish = IsotonicRegression(overall_adp -> overall_finish_ppr)
                   fit on ALL SEASONS EXCEPT the one being scored
                   (leave-one-season-out -- a player-season never
                   influences its own baseline)

eva_raw = expected_finish - overall_finish_ppr
eva_component = minmax_normalize(eva_raw, grouped by [season])

worse_than_own_adp = overall_finish_ppr > overall_adp
component_1 = min(eva_component, LWI_ADP_UNDERPERFORM_CAP)
              if worse_than_own_adp else eva_component
```

`LWI_ADP_UNDERPERFORM_CAP = 40` (config.py). Isotonic regression is
constrained monotonic-increasing so sampling noise can never let an
earlier pick have a worse expected finish than a later one.

**Why leave-one-season-out**: comparing a player only to that season's
own draft class makes the metric's meaning drift year to year. Leave-
one-season-out builds an empirical, out-of-sample expectation from the
other 18 seasons instead -- stable and reusable, not season-relative.

**Why the cap**: EVA alone can score a player positively for beating a
*historically bad* baseline (early picks bust often) even when they
lost real value versus their *own actual* draft cost. Real case: Arian
Foster, 2012, drafted 1.4 overall, finished 12th -- `eva_raw = +28.8`
(beat the rough historical average outcome for pick-1-ish slots) but
`direct_raw (overall_adp - overall_finish_ppr) = -10.6` (genuinely
worse than the pick actually spent). The cap adds direct accountability
to the real pick, not just the historical neighborhood average.

---

## Component 2: Fantasy Finish Total Points (18% weight)

**What it measures**: full-season cumulative production, credited
above a realistic replacement-level baseline, compared across ALL
positions (not within-position).

**Formula**:

```
replacement_points = median(fantasy_points_ppr) among players ranked
                      [threshold, threshold+12] at that position+season
                      (see Component 4 for the threshold table)

points_above_replacement = fantasy_points_ppr - replacement_points
component_2 = minmax_normalize(points_above_replacement, grouped by [season])
```

Cross-position (not positional-percentile) so a durable player with
more usable games is credited for availability, distinct from
Component 3's per-game rate.

---

## Component 3: Points Per Game (17% weight)

**What it measures**: weekly scoring rate above replacement, cross-
position -- the per-game counterpart to Component 2.

**Formula**:

```
replacement_ppg = median(ppg_ppr) among players ranked
                   [threshold, threshold+12] at that position+season

ppg_above_replacement = ppg_ppr - replacement_ppg
component_3 = minmax_normalize(ppg_above_replacement, grouped by [season])
```

Only computed for rows meeting the 8-game eligibility floor.

---

## Component 4: Positional Advantage (12% weight)

**What it measures**: how UNUSUAL a player's weekly production
advantage was, relative to how tightly bunched that position's
starter tier normally is -- distinct from Component 3, which measures
the raw size of the advantage, not how unusual it was.

**Replacement-level thresholds** (also used by Components 2/3):
`QB: 12, RB: 34, WR: 42, TE: 12` (`LWI_REPLACEMENT_RANK_THRESHOLDS`,
config.py). These are a conceptual choice ("freely available" under
typical 12-team PPR roster construction), not an empirical finding --
real scoring-by-rank curves show no natural cliff at any candidate
value. Sensitivity-tested and confirmed the model is robust to
reasonable alternatives (0.9996 rank correlation across the most
divergent configurations tested), which is a claim about robustness,
not about any one threshold being uniquely correct.

**Formula**:

```
starter_tier = players ranked 1..threshold at that position+season
starter_iqr = IQR(ppg_ppr) among starter_tier   # 75th - 25th percentile
              (NaN if fewer than 4 starters, or IQR == 0)

standardized_advantage = ppg_above_replacement / starter_iqr

component_4 = winsorized_minmax_normalize(
    standardized_advantage,
    grouped by [season],
    clip to [5th percentile, 95th percentile] before scaling
)
```

**Why IQR-standardized, not raw**: an earlier version used the raw,
unstandardized `ppg_above_replacement` value directly for Component 4.
Once Component 3 was ALSO made replacement-adjusted, this made
Components 3 and 4 mathematically IDENTICAL (Spearman correlation
~0.9999999, R-squared of 1.000 when Component 4 was regressed on
Components 2+3 -- literally the same formula, weighted twice).
Dividing by the position's own starter-tier spread gives Component 4 a
genuinely distinct job. IQR was chosen over standard deviation (weaker
result: 15.8% unique variance vs IQR's) and tested head-to-head
against MAD (close; IQR gave meaningfully better false-positive
separation, which was judged the more important property -- see the
Model Card's "precision over recall" reasoning).

**Why WINSORIZED min-max, not plain min-max**: plain min-max is highly
sensitive to its own extremes. Verified directly that a single wild
outlier in ONE position's data could shift an UNRELATED player's score
in a DIFFERENT position by 60+ points, because the final normalization
is cross-position (one shared 0-100 range across all 4 positions
within a season, needed for cross-position comparability). Winsorizing
at the 5th/95th percentile before scaling reduced that shift to 0.0 in
the same test, while retaining more discriminative power than
percentile-rank normalization or a tighter 2.5/97.5 winsorization
(both tested head-to-head; 5/95 won on known-winner and false-positive
separation among the outlier-robust alternatives).

---

## Component 5: Playoff Performance (4% weight)

**What it measures**: performance specifically in fantasy playoff
weeks, rewarding players who performed when it mattered for actually
winning a league.

**Playoff week definition**, verified against actual max-week-per-
season in the real data (`config.py`):

```
Seasons <= LWI_PLAYOFF_ERA_CUTOFF_SEASON (2020, 16-game NFL seasons):
    playoff_weeks = [14, 15, 16]
Seasons > 2020 (17-game NFL seasons):
    playoff_weeks = [15, 16, 17]
```

**Formula** -- production and availability scored separately, not
blended into one raw average:

```
playoff_games_played = count of playoff_weeks with a row in
                        weekly_results_ppr (i.e. genuinely played)
playoff_availability = playoff_games_played / len(playoff_weeks)

if playoff_games_played > 0:
    playoff_ppg = mean(fantasy_points_ppr across weeks actually played)
    playoff_ppg_percentile = percentile rank of playoff_ppg within
                              [season, position], among players with
                              playoff_games_played > 0
else:
    playoff_ppg_percentile = 0   # floor, not an undefined average

component_5 = 0.75 * playoff_ppg_percentile + 0.25 * (playoff_availability * 100)
```

Percentile rank (not min-max) for the production term specifically,
since a 3-week sample is small enough that one monster game could
distort a min-max range badly.

**Known limitation**: byes landing inside the playoff window (rare,
but possible for the first playoff week specifically) can't currently
be distinguished from a genuine missed/injured week -- both simply
produce no row for that week. Low-impact given rarity; would need team
schedule data (`nfl_data_py.import_schedules()`, not yet integrated)
to fix properly.

---

## Component 6: Consistency (3% weight)

**What it measures**: week-to-week scoring reliability.

**Formula**:

```
consistency_raw = mean(weekly fantasy_points_ppr) / stdev(weekly fantasy_points_ppr)
component_6 = minmax_normalize(consistency_raw, grouped by [season, position])
```

Bye/inactive weeks are excluded by construction (not present in
`weekly_results_ppr_*.csv` at all -- see `03_download_stats.py`).

---

## Component availability policy

- **Never silently redistribute a missing component's weight.** A
  score computed from 5 of 6 components is a different measurement
  than one computed from all 6.
- **Incomplete scores are never shown in `lwi_score`.** A row missing
  any component gets `lwi_score = null` and `lwi_component_coverage`
  set to `incomplete_N_of_6`, not a number that looks like a normal
  score. A separate `lwi_score_diagnostic` column retains a labeled
  partial score for anyone who explicitly wants it.
- Currently moot in practice -- every eligible row has all 6
  components computed -- but enforced as a real, tested invariant
  (`TestComponentAvailabilityPolicy`), not an assumption.

---

## Output schema

Per (season, player_id) row, in addition to everything already in
`master_historical_db_*.csv`:

```
lwi_score                        (0-100, or null if ineligible/incomplete)
lwi_score_diagnostic             (partial score, always computed, for reference)
lwi_eligibility_flag             (eligible / insufficient_games / no_adp_match)
lwi_component_coverage           (complete_6_of_6 / incomplete_N_of_6)
lwi_version                      (e.g. "2.1")
lwi_config_fingerprint           (hash of every LWI_* config value used)
adp_value_component
fantasy_finish_component
ppg_component
positional_advantage_component
positional_advantage_raw         (pre-normalization: ppg_above_replacement / starter_ppg_iqr)
positional_advantage_winsorized  (raw value after 5th/95th percentile clipping, pre-scale -- kept visible so the clipping itself is auditable, not hidden inside one opaque step)
playoff_performance_component
playoff_games_played             (0-3, diagnostic)
playoff_availability              (0, 0.33, 0.67, or 1 -- diagnostic)
consistency_component
```

---

## Open items (not blocking current use, tracked for follow-up)

1. **Verification research for the remaining known real "league winner"
   candidates** (Cruz 2011, Forsett 2014, James Robinson
   2020, Nacua 2023, Kyren Williams 2023, Geno Smith 2022) -- the
   MECHANISM to include them once verified now exists (see "Undrafted
   player representation" above), but none are yet confirmed
   `verified`/`undrafted` vs. simply `unresolved`/outside our current
   source's depth. Confirmed all 7 are genuinely absent from our
   current ADP source (not a matching failure), but "absent from our
   source" and "undrafted everywhere" are different claims -- checking
   additional historical sources (MFL, RTSports, Underdog, etc.) for
   each is the remaining work. Michael Vick 2010 is no longer open;
   the approved market-governance revision above supersedes his prior
   unresolved treatment. This remains a material weakness
   in the whole system -- larger than any open formula question. See
   `docs/LWI_MODEL_CARD.md` and Dataset 5
   (`no_adp_breakout_candidates.csv`) for the broader research
   candidate list.
2. Playoff bye-week disambiguation (Component 5) -- documented above,
   low priority given rarity.
3. Replacement-level thresholds are a documented conceptual choice
   (see Component 4), reasonable to revisit if evidence emerges, but
   not something the data alone can resolve.
