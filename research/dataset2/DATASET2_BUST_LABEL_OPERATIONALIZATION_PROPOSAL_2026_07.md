# Dataset 2B bust-label operationalization proposal (2026-07)

**Status: PROPOSAL ONLY. No bust label is implemented by this
document or by any code change alongside it.** `bust_primary_label`,
`bust_strict_label`, and `bust_historical_sensitivity_label` in
`lib/dataset2/canonical_outcome_table.py` remain reserved, always-null
columns after this round (`implementation_status =
reserved_not_computed`, `usable_as_target = False` in the data
dictionary — see the top of this document for that update). This
document proposes candidate formulas, backed by real data, for review.
It does not select one.

Every number below is computed by
`research/dataset2/bust_label_operationalization_analysis.py` against
the real, committed canonical outcome table
(`data/exports/dataset2_canonical_outcome_table.parquet`, commit
`b821118`) plus the real master population, `players.csv`, and the
fitted E_P lookup. Nothing here is estimated or extrapolated.

## 0. Why this re-does, not just reuses, `DATASET2_TRAIT_ROADMAP.md`
§3j

`research/dataset2/DATASET2_TRAIT_ROADMAP.md` §3j already did real
bust-definition analysis and reached an APPROVED decision on the
**form** of three separate outcome fields:

- `bust_label_primary` = definition **G**: position × ADP-range
  conditioned percentile.
- `bust_label_strict_hybrid` = definition **I**: G plus an absolute
  shortfall floor, stored as a stricter sensitivity analysis, never
  used to override the primary label.
- `underperformance_diagnostic` = definition **C**: raw P vs. modeled
  E_P, a secondary diagnostic, never a bust label.

§3j explicitly left the **numeric** percentile and floor unset
("implementation details to fix when Dataset 2B's outcome-labeling
module is actually built, not re-decided here"). This proposal takes
that as still true and does not assume any number from that section
carries forward as decided.

What changed since §3j and must be re-run, not reused: §3j's real
counts were computed against the **1,293-row `adp_matched` scored-only
population** — the population as it existed before this project's own
later correction (commit `b46d6b4`) that below-production-gate rows
with real ADP are legitimate bust candidates SBV's Star methodology
structurally cannot see. The approved primary bust-eligible population
is now **2,677 rows** (2010+, real ADP, gate not required), more than
double §3j's analysis population and structurally different in
composition (it now includes 1,381 rows SBV itself never scored at
all). Every percentile/cell/overlap number in §3j is therefore stale
for this population and is not reused directly below — only the
**definitional forms** (G, I, C) carry forward.

## 1. Two distinct "ADP conditioning" mechanisms — kept separate

This proposal's own construction surfaced a distinction that matters
for what follows and was not fully separated in §3j:

- **Fine-grained, per-round E_P lookup** (`draft_round` exact value,
  `data/processed/sbv_expected_production_lookup.parquet`) — used to
  compute `expected_production` and therefore `score_like` (below).
  This is the SAME lookup the underperformance diagnostic uses, and
  carries the SAME real coverage gap already disclosed for that
  diagnostic: of the 2,677 primary-eligible rows, **20 have no
  computable `score_like`** — 19 because their real ADP round has no
  fitted (season, position, round) cell (17 below-gate + 2
  `unscoreable_expected_production_out_of_range`), 1 because the row
  has zero games and no computable `P` (Isaac Guerendo, see §12).
- **Coarse position × ADP-round-BUCKET peer cells**
  (`config.DATASET2_ADP_ROUND_BUCKETS`: R1-2/R3-5/R6-10/R11+) — used to
  group players for the percentile RANKING itself (definition G).

These are independent: a row can have a valid coarse bucket
(R1-2..R11+) but no fine-grained E_P cell. Below, "G-score" means
percentile computed on `score_like` (needs the fine lookup); "G-raw"
is an alternative computed directly on raw `P` (needs only the coarse
bucket, sidestepping the lookup-gap problem entirely) — see §4.

`score_like = P - SBV_LAMBDA * expected_production`, reusing
`SBV_LAMBDA` (0.35) directly from config. Verified against the real
`star_by_value_score` for all 1,293 `adp_scored` rows: **max abs
difference = 0.000000** — confirms this is the identical formula SBV
itself uses, extended to below-gate rows only for peer-ranking
purposes here (never written back to any SBV export or Star label).

## 2. Candidate realized-production measures

Three candidates, in order of how much they already account for
missed time:

| Measure | What it is | Missed-games handling |
|---|---|---|
| **P** (SBV's own composite, `lib/stars_by_value/production.py`) | `0.5·AATP + 0.5·PPG_AR_eq_shrunk` | AATP credits REPLACEMENT-LEVEL production for each eligible game missed (not zero, not "season never happened"); PPG_AR_eq_shrunk additionally shrinks a small-sample per-game rate toward the replacement baseline as `games_played_capped` shrinks, via `SBV_SHRINKAGE_K=5` |
| Raw season total (`fantasy_points_ppr`) | Sum of actual points scored | None — a player who played 3 elite games and then got hurt scores identically low to a player who played 3 mediocre games all season, with no distinction |
| Raw per-game rate (`ppg_ppr`) | Points ÷ games played | Opposite failure mode — a 2-game hot streak before a season-ending injury looks identical to a full healthy season at the same rate |

**Recommendation: use `P`**, for two reasons — it is the SAME measure
whose expectation the E_P lookup is fit against (using a different
raw measure for the bust label than the one Star/diagnostic scoring
already uses would make the three outcome fields internally
inconsistent), and it already has explicit, calibrated machinery for
the missed-games question (§3) rather than requiring a new ad hoc rule
invented here.

**Real finding that complicates a clean "P already solved this"
story**: even with AATP's replacement-level crediting, partial-season
rows in the primary population are flagged as G-score-bottom-20% bust
at a MEATERIALLY higher rate than full-season rows:

| `games_played` bucket | n | G20-flagged | rate |
|---|---|---|---|
| 1-4 | 109 | 27 | 24.8% |
| 5-8 | 223 | 66 | 29.6% |
| 9-12 | 450 | 131 | 29.1% |
| 13+ | 1,875 | 303 | 16.2% |

This has two honest readings, and this document does not resolve
which is correct:

- **Reading A (real signal)**: a player who lost his role or got hurt
  mid-season IS legitimately a bust relative to what his draft cost
  promised — availability risk is part of what "bust" means to a
  fantasy manager who paid a real acquisition cost for a full season
  of production.
- **Reading B (measurement artifact)**: AATP's replacement-level
  credit may not be fully neutralizing the missed-games penalty, so
  partial seasons are still being mechanically disadvantaged in a way
  that isn't really about the player's own skill/opportunity.

This is presented as an open question for the user's judgment, not
resolved here.

## 3. Missed-games effect on the label — options

1. **No separate rule (recommended default)**: rely entirely on P's
   built-in AATP/shrinkage machinery, accept the games-bucket
   asymmetry in §2 as-is.
2. **Minimum-games floor for label eligibility** (mirrors the
   Family #9 "meaningful role" pattern already used elsewhere in
   Dataset 2): require e.g. `games_played >= 4` for
   `bust_primary_eligible`, moving very-short seasons to a separate
   diagnostic. Real cost: would remove 109 of 2,677 primary-eligible
   rows (4.1%).
3. **Separate "availability bust" flag**, orthogonal to the
   production-based label: flag `games_played < 50% of eligible
   games` as its own field, never merged into `bust_primary_label`.

No option is selected here; option 1 is the default only because it
requires no new rule, not because it has been shown superior.

## 4. ADP conditioning method — G-score vs. G-raw

| | Needs fine E_P lookup? | Rankable n (of 2,677) | Bottom-20% n |
|---|---|---|---|
| **G-score** (`score_like` percentile within position×bucket) | Yes | 2,657 | 527 |
| **G-raw** (raw `P` percentile within position×bucket) | No | 2,676 | 531 |

**Overlap at bottom-20%: 497 of 527/531 flagged rows (89.2%)** — the
two are close but not identical. G-raw's advantage is that it
sidesteps the 19-row E_P-lookup-coverage gap entirely (only the 1
zero-game row is unrankable, vs. 20 for G-score) and needs one fewer
moving part (no fitted lookup table dependency at label-build time).
G-score's advantage is that it nets out the position's Star threshold
and each round's specific expected production, which G-raw's coarse
4-bucket grouping doesn't fully capture (e.g., G-raw cannot distinguish
a round-6 pick from a round-10 pick, both in "R6-10").

**Recommendation: G-score**, since it stays consistent with the
existing SBV score formula and the diagnostic, but this is a real
tradeoff, not a clear-cut call — G-raw is a legitimate, simpler
fallback if the E_P-lookup dependency is judged too fragile for a
production label.

## 5. Position stratification

Already decided (definition G computes within position). Confirmed
real cell sizes below (§7) support this — no position×bucket cell in
the primary population falls below `DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE`
(10).

## 6. Era handling

Reusing `config.DATASET2_ERA_BOUNDARIES = (2011, 2021)` (already
established, flagged as still-open in that constant's own comment).

**Real finding — MORE era-sensitive than §3j's old finding F**: pooled
vs. era-stratified bottom-20% (G-score) overlap is **81.2%** (466 of
574 rows in either set), noticeably lower than §3j's 92.6% overlap on
the old, narrower population. This is a genuine difference, not a
recomputation of the same fact — the broader population (now dominated
by below-gate rows spanning a wider range of scoring eras) is more
era-sensitive than the narrow scored-only population was. **This
means §3j's basis for dismissing era stratification ("pooling doesn't
meaningfully distort the tail") no longer clearly holds for the new,
approved population** — flagged for explicit reconsideration, not
carried forward as settled.

Countervailing real finding (§8): stratifying peer cells by era
directly creates several real sparse cells (e.g., `TE R1-2 pre-2011` =
0 rows, `QB R1-2 pre-2011` = 3 rows) — a genuine tension between
era-sensitivity and cell-size adequacy that this document surfaces but
does not resolve.

## 7. Peer-cell construction and minimum sample size

Position × `DATASET2_ADP_ROUND_BUCKETS` (4 positions × 4 buckets = 16
cells), primary population (n=2,677):

| position | R1-2 | R3-5 | R6-10 | R11+ |
|---|---|---|---|---|
| QB | 26 | 60 | 165 | 135 |
| RB | 197 | 203 | 316 | 223 |
| TE | 13 | 57 | 122 | 120 |
| WR | 145 | 250 | 369 | 276 |

**All 16 cells clear `DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE=10`** —
no sparse-cell problem at this granularity. The smallest real cell is
QB/TE R1-2 (13-26 rows), reflecting the real fact that few QBs/TEs are
drafted in the first two rounds.

## 8. Sparse late-round cell treatment

Not currently needed at the position×bucket granularity (§7). It
WOULD become needed if era stratification is added on top (§6) — real
example cells at position×bucket×era: `QB/R1-2/pre-2011=3`,
`TE/R1-2/pre-2011=0`, `TE/R1-2/2021+=4`. If era stratification is
adopted despite §6's finding, a fallback rule (e.g., pool to the
position×bucket cell, ignoring era, whenever the era-specific cell has
n < 10) would be required — proposed but not built.

## 9. Candidate primary percentiles: 20% / 25% / 30%

G-score, position × ADP-bucket peer cells, primary population
(n=2,657 rankable):

| Cutoff | n flagged | Position composition | ADP-bucket composition |
|---|---|---|---|
| Bottom 20% | 527 | WR 205, RB 185, QB 77, TE 60 | R6-10 193, R11+ 146, R3-5 113, R1-2 75 |
| Bottom 25% | 658 | WR 256, RB 231, QB 95, TE 76 | R6-10 242, R11+ 181, R3-5 141, R1-2 94 |
| Bottom 30% | 789 | WR 307, RB 277, QB 114, TE 91 | R6-10 289, R11+ 218, R3-5 170, R1-2 112 |

By construction (within-cell percentile), the flagged RATE is ~20/25/30%
in every position and every ADP bucket at each respective cutoff — this
table mainly confirms internal consistency, not a substantive finding.
No cutoff is recommended over another here; all three are legitimate,
defensible choices and the tradeoff is purely how large a "bust" tail
the research question needs.

## 10. Candidate absolute floors for the strict hybrid (definition I)

**Floor candidate A — percent below own position threshold**
(`pct_below_threshold`, same construction as §3j's definition H,
reusing `SBV_STAR_THRESHOLD` directly):

| Floor | n (of 2,657 rankable) | % of rankable |
|---|---|---|
| ≥50% | 2,094 | 78.8% |
| ≥60% | 1,870 | 70.4% |
| ≥65% | 1,725 | 64.9% |
| ≥70% | 1,591 | 59.9% |
| ≥80% | 1,313 | 49.4% |

**Floor candidate B — `P < 0` (below replacement level, zero free
parameters)**: since `P` is already defined relative to replacement-level
production (`AATP`/`PPG_AR` both net out `replacement_ppg`), `P < 0` is
a parameter-free, principled floor requiring no arbitrary percentage
choice: **n = 101 (3.8% of rankable)**.

**Hybrid (G bottom-20% AND floor)** — real finding: in this broader
population, floor candidate A barely narrows G20 at any floor commonly
considered reasonable:

| Floor added to G20 (n=527 alone) | n |
|---|---|
| ≥50-75% | 526-527 (no material effect) |
| ≥80% | 520 |
| ≥85% | 505 |
| ≥90% | 482 |
| ≥95% | 455 |
| ≥100% | 419 |
| ≥110% | 334 |

This is a stronger version of §3j's own finding (there, the hybrid
only started mattering above ~65%; here it barely moves before ~85%) —
because this broader population's tail (dominated by below-gate rows)
already sits extremely far below threshold, a percentage-of-threshold
floor needs to go well past 100% (i.e., the shortfall exceeds the
entire threshold value) before it meaningfully narrows the primary
set.

**Floor candidate B (`P<0`) is a clean nested nested subset**: all 101
`P<0` rows are already within G20 (hybrid = 101, unchanged from B
alone) — a strict, well-defined, parameter-free strict-hybrid
candidate. **Recommendation: consider `P<0` as the strict-hybrid floor**
instead of an arbitrary percentage, given it requires no threshold
choice and is already fully nested inside G. Percentage floors at
90-100% are the next most defensible alternative if a less extreme
strict set is wanted.

## 11. Tie handling

Checked every position × ADP-bucket cell in the real primary
population for duplicate `score_like` values at the 20% boundary:
**zero duplicate values found in any cell.** Percentile ties are
therefore not a live problem in this data today, but as a forward-looking
rule (in case future seasons introduce them): recommend pandas'
`method="average"` rank (ties share the mean percentile rank) with an
inclusive `<=` cutoff comparison, so a boundary tie is never arbitrarily
broken by row order.

## 12. The one zero-game real-ADP row

**Isaac Guerendo, 2025 RB, `overall_adp`=158.83 (round 14, bucket
R11+), `games_played`=0.** No `P` is computable — `production.py`'s
`compute_production()` structurally requires non-null `ppg_ppr`
(§ Errors and fixes, prior round), and this row has none by
definition. This row therefore cannot participate in a percentile
computation in its peer cell at all — a genuinely different kind of
"missing" than the 19 E_P-lookup-gap rows (which have real production,
just no expectation to compare against).

**Recommendation**: treat this row (and any future row like it) as an
**automatic/definitional bust** under both `bust_primary_label` and
`bust_strict_label` — a real, non-trivial fantasy acquisition cost
(round 14, not undrafted) that returned literally zero production is
trivially the worst possible outcome in any peer cell, and does not
need a percentile computation to establish that. This is a proposed
special-case RULE requiring explicit approval, not something inferred
automatically by the percentile machinery (which would otherwise leave
this single row's label permanently null, silently excluding a real,
relevant case from the bust label it is already eligible for).

## 13. Partial seasons and lost-role players

Recap of §2/§3's real finding: games-bucket 5-12 (partial season, still
rostered/played some) shows the HIGHEST bust rate (~29%) of any bucket,
higher even than the shortest (1-4 games, 24.8%) or full-season (13+,
16.2%) buckets. This is a real, slightly counter-intuitive pattern
worth the user's attention: it is NOT a smooth monotonic relationship
between games played and bust rate. A player who played roughly half a
season is, in this data, more likely to be flagged than one who played
almost none or nearly all of it. No rule is proposed to correct or
explain this pattern here — it is reported as a finding requiring
review before any label is finalized.

## 14. Representative players under the candidate definition (G-score,
bottom-20%)

**R1-2 bucket (obvious high-cost failures — sanity check)**: Randy
Moss (2010), Adrian Peterson (2016), Jamaal Charles (2016), Montee Ball
(2014), JuJu Smith-Schuster (2019), Doug Martin (2014), Brandon
Marshall (2016), Jordy Nelson (2017), Dez Bryant (2015), Saquon
Barkley (2020), Eddie Lacy (2015), C.J. Anderson (2015), Isiah Pacheco
(2024), Travis Etienne (2024), Trent Richardson (2013) — a real,
recognizable list of early/mid-first- and second-round picks who fell
hard, confirming the definition captures genuine high-cost failures at
the top of the draft, not noise.

**R11+ bucket, closest to the cutoff (mediocre-vs-major-bust check)**:
Zach Wilson (2021), Justin Fields (2024), Jimmy Garoppolo (2020),
Derek Carr (2018), Case Keenum (2018), Kyle Orton (2011), Daniel Jones
(2020), Matt Hasselbeck (2010), Trevor Lawrence (2021), Matt Schaub
(2013), Vince Young (2010), Jay Cutler (2017), Chad Henne (2010),
Spencer Rattler (2025), Marcus Mariota (2018) — every one of these is a
`below_production_gate` real-ADP QB, each 100-108% below their own
position threshold. These are backup-caliber or clearly disappointing
starting QBs having genuinely bad statistical seasons, not merely
"slightly below average" players swept in by a noisy sparse cell — a
real, reassuring finding that even at the percentile boundary in a
QB-heavy late-round bucket, the definition is not mislabeling mediocre
players as major busts.

## 15. Prevalence tables (G-score, bottom-20% baseline)

**By ADP bucket** (near-uniform ~20% by construction — confirms the
percentile mechanism is working, not a substantive finding):

| bucket | n | flagged | rate |
|---|---|---|---|
| R1-2 | 381 | 75 | 19.7% |
| R3-5 | 570 | 113 | 19.8% |
| R6-10 | 972 | 193 | 19.9% |
| R11+ | 734 | 146 | 19.9% |

**By era** (pooled cells, not era-stratified — see §6 for why these
numbers differ from a hypothetical era-conditioned version):

| era | n | flagged | rate |
|---|---|---|---|
| pre-2011 | 179 | 40 | 22.3% |
| 2011-2020 | 1,571 | 305 | 19.4% |
| 2021+ | 907 | 182 | 20.1% |

**By games played**: see §2's table (16.2% for 13+ games vs. 24.8-29.6%
for partial seasons).

**Rookie vs. veteran**:

| | n | flagged | rate |
|---|---|---|---|
| Veteran | 2,375 | 442 | 18.6% |
| Rookie | 282 | 85 | **30.1%** |

Real, substantial finding: rookies are flagged at ~1.6x the rate of
veterans — consistent with the well-known real phenomenon of rookie
bust risk, and a real signal this label would need to be interpreted
alongside (a "rookie-adjusted" reading of bust rate may be warranted
in downstream analysis, though not built here).

**Season-by-season** (selected — full table in the analysis script's
output): rates are broadly stable in the 10-26% range for most seasons,
notably lower in 2020-2022 (9.7-12.9%) and notably higher in 2025
(30.8%, n=234). The 2025 elevation is plausibly explained by this
season now containing many more real below-gate-real-ADP rows than
prior seasons in this population (251 primary-eligible rows in 2025 vs.
176 in 2024) rather than a data-completeness problem — real
`games_played` distributions for 2025 (mean 13.2, median 15, max 18)
look comparable to 2024's — but this is flagged for the user's own
judgment, not asserted with confidence here.

## 16. Historical sensitivity population (pre-2010 extension)

The 521 rows unique to `bust_historical_sensitivity_eligible` (3,198
total) vs. the primary population (2,677) are exactly the real 2007-2009
rows with real ADP: WR 198, RB 181, QB 85, TE 57. Never mixed into the
primary label per the approved decision — reported here only for
completeness of this proposal's population accounting.

## 17. Summary — open decisions requiring approval before any label is
built

| Decision | Candidates presented | Recommendation (not a decision) |
|---|---|---|
| Realized-production measure | P (composite) / raw season total / raw ppg | P — but §2's partial-season finding is unresolved |
| Missed-games rule | none / min-games floor / separate availability flag | none (rely on P's existing machinery) |
| ADP conditioning for ranking | G-score (needs E_P) / G-raw (raw P percentile) | G-score, but G-raw is a real, simpler fallback |
| Era stratification of peer cells | pooled / era-stratified | Neither clearly settled — §6's overlap dropped from §3j's 92.6% to 81.2% on this population, undermining the old dismissal, but era-stratified cells are real-data sparse (§8) |
| Primary percentile | 20% / 25% / 30% | No preference — pick per research need |
| Strict-hybrid floor | %-below-threshold (50-110%) / `P<0` | `P<0` — parameter-free, cleanly nested |
| Zero-game real-ADP row | null label / automatic bust | Automatic bust (proposed rule, needs approval) |
| Partial-season/lost-role treatment | accept P's handling as-is / add rule | Accept as-is, but §13's non-monotonic finding needs review |

**Nothing above is implemented.** This document stops before building
any bust label, per instruction — the next step, once these choices
are made, is a small, focused change to
`lib/dataset2/canonical_outcome_table.py` to compute the three label
columns using whichever combination is approved.

---

## Round 2 (2026-07) — approved decisions, and closing the remaining
open items

**Status: still a proposal. No label is implemented by this section.**
This round's real-data analysis is produced by
`research/dataset2/bust_label_round2_analysis.py`, run against the
same real, committed canonical outcome table plus `AATP`/`PPG_AR`
(production.py's own intermediate columns, not new formulas).

### 18. Decisions approved this round

- **Primary percentile: bottom 20%.** Bottom 25%/30% are preserved as
  named sensitivities (§9 above), not alternates under consideration
  for the primary label.
- **Strict hybrid: bottom 20% AND `P < 0`** (below replacement level,
  zero free parameters — §10's floor candidate B). Percentage-of-
  threshold floors are preserved only as sensitivities.
- **Zero-game real-ADP rule, generalized** (§21 below) — a mechanical
  rule, not a player-specific override.

### 19. G-raw vs. E_P-dependent (G-score) — disagreement audit

The 60 real disagreement rows (30 flagged only by `score_like`, 30
flagged only by raw `P` — together the 10.8% already reported in §4)
were audited directly, not assumed:

**A structural fact worth stating plainly**: because G-score and G-raw
rank the SAME group sizes (same position×bucket cells) and this data
has zero ties (§11), **the two methods always flag the identical COUNT
per cell** — 527 total either way. Disagreement is entirely about
*which* players fill those slots, never about how many.

| | score_only (n=30) | raw_only (n=30) |
|---|---|---|
| Position | WR 9, QB 9, RB 8, TE 4 | WR 9, QB 9, RB 8, TE 4 (identical — a mathematical necessity given equal per-cell counts, §above) |
| ADP bucket | Same identical-count property as position | Same |
| Era | 2011-2020: 14, 2021+: 14, pre-2011: 2 | 2011-2020: 16, 2021+: 9, pre-2011: 5 |
| Games bucket | 13+: 13, 9-12: 11, 5-8: 6 | 13+: 18, 9-12: 7, 5-8: 4, 1-4: 1 |
| Rookie | 4 of 30 | 3 of 30 |
| `adp_round` (mean / median) | 7.23 / 7 | 8.73 / 10 |
| Rounds from E_P lookup's coverage boundary (mean) | 7.2 | 5.6 |

**Real finding: disagreement is NOT concentrated near the E_P lookup's
coverage edge.** Both groups sit, on average, 5-7 rounds away from
where the fitted lookup actually runs out — this rules out "G-score
disagrees with G-raw mainly because the lookup model gets unreliable
near its boundary" as the explanation.

**What the disagreement actually is**: `raw_only` rows skew to LATER
rounds within their bucket (median round 10) than `score_only` rows
(median round 7). Real examples make this concrete — Sam Bradford
(2010, round 14 QB, `P`=74.6) is flagged bust by raw-P-within-`R11+`
(his absolute output is low among the whole R11+ QB pool, which
includes some strong round-11 performers), but NOT by G-score, because
his round's own expectation (`E_P`=182.4) was already appropriately
low for a round-14 QB — relative to what a round-14 QB is supposed to
produce, he was not a standout underperformer. This is exactly the
scenario position×ADP-**round** conditioning exists to correct, and
G-raw's coarse 4-bucket grouping cannot see it (it cannot distinguish
a round-11 pick from a round-14 pick, both inside "R11+").

**Conclusion: the four ADP buckets DO make G-raw meaningfully coarser
within-bucket** — this is not primarily an artifact of the E_P lookup.
**G-score is the more defensible ranking method on this evidence**,
not merely because it "was already being used" — the disagreement
cases are concentrated exactly where fine-round conditioning should
matter, and away from the lookup's own coverage edge. The 19-row
coverage gap is handled separately (§22).

### 20. Era handling — four methods compared

| Method | Description | n flagged (of 2,657 rankable) | Real cell-size issue |
|---|---|---|---|
| **1. Fully pooled** | Current approach — rank within position×bucket, era ignored | 527 | None |
| **2. Broad-era stratification** | Rank within position×bucket×era | 513 | **10 of 47 real cells (21%) fall below `DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE=10`** — e.g. `TE/R1-2/2011-2020`=9, `QB/R1-2/pre-2011`=3, `WR/R1-2/pre-2011`=9 |
| **3. Era-normalized production, pooled ranking** | z-score `score_like` within era×position, then rank the z-score within pooled position×bucket | 527 | None — normalization never fragments cells |
| **4. Era-stratified with minimum-sample fallback** | Rank within position×bucket×era; for the 10 real sparse cells, fall back to the pooled position×bucket ranking (mechanical rule, pre-specified: any cell with n < 10 uses method 1 for its members) | 517 (65 rows used the fallback) | Resolved by construction |

**Pairwise label-stability (Jaccard overlap)**:

| | M1 | M2 | M3 | M4 |
|---|---|---|---|---|
| M1 | 100% | 81.2% | 88.6% | 82.2% |
| M2 | 81.2% | 100% | 84.7% | 98.8% |
| M3 | 88.6% | 84.7% | 100% | 85.4% |
| M4 | 82.2% | 98.8% | 85.4% | 100% |

**Real, convergent finding across all three era-aware methods (2, 3,
4)**: pooling (M1) measurably OVER-flags the pre-2011 era relative to
every era-aware alternative:

| Era | M1 (pooled) | M2 (era-stratified) | M3 (era-normalized) | M4 (fallback) |
|---|---|---|---|---|
| pre-2011 | **22.3%** | 15.6% | 15.1% | 16.2% |
| 2011-2020 | 19.4% | 19.7% | 20.8% | 19.7% |
| 2021+ | 20.1% | 19.4% | 19.1% | 19.6% |

All three era-aware methods agree pre-2011's flag rate should be
~15-16%, not 22.3% — this is no longer a minor sensitivity difference,
per instruction, and pooling (M1) is not recommended.

**Recommendation: Method 4 (era-stratified with a pre-specified
minimum-sample fallback to pooled)** — it delivers the same
era-correction as pure stratification (98.8% overlap with M2) while
mechanically resolving every real sparse cell, and it ranks the actual
real production value directly rather than a normalized proxy (easier
to audit/explain than M3's z-score transform). The fallback rule is
fully specified and requires no judgment at build time: **for a given
(position, adp_bucket, era) cell, if n < `DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE`
(10), rank that cell's members within the pooled (position, adp_bucket)
group instead** — applied mechanically, identically, to all 10 real
sparse cells.

### 21. Availability / partial seasons — season-total vs. rate vs.
current blend

Per instruction, season-total (`P`, already the leading concept) is
kept as the primary measure. Compared directly against its own two
component concepts already computed by `production.py` — no new
formula:

- **Availability-adjusted season production = `AATP`** (season-total
  scale; credits REPLACEMENT-level production for each eligible game
  missed, so a hurt player isn't penalized as if the season simply
  didn't happen, but also isn't credited their OWN rate for time
  missed).
- **Active-game production rate = `PPG_AR`** (rate only, entirely
  ignores games played — measures only what happened while active).

| | vs. `P` (current) overlap | Rankable n |
|---|---|---|
| `AATP` alone | 80.4% | 2,676 |
| `PPG_AR` alone | 70.9% | 2,676 |
| `AATP` vs. `PPG_AR` directly | 58.0% | 2,676 |

**Real finding — the two component measures cleanly separate injury
busts from performance busts, exactly per instruction**:

- **Flagged by `AATP` but NOT by `PPG_AR`** (n=141): a recognizable
  real list of established, good-rate players who got hurt early —
  **Antonio Brown (2019, 1 game, `PPG_AR`=+4.41 — a GOOD per-game
  rate)**, David Johnson (2017, 1 game), Delanie Walker (2018, 1
  game), Odell Beckham Jr. (2017, 4 games, `PPG_AR`=+7.34), Jermichael
  Finley (2010, 4 games). These are the real injury-bust pattern —
  `AATP`'s replacement-level-for-missed-games credit still can't offset
  losing most of a season, even though the player was clearly
  productive when active.
- **Flagged by `PPG_AR` but NOT by `AATP`** (n=141): players with a
  genuinely POOR rate even in the limited action they got — Tyrell
  Williams (2021, 1 game, `PPG_AR`=**-7.24**), Kevin White (2017, 1
  game, -8.56), Damien Harris (2019, 1 game, -8.47). `AATP` is more
  forgiving of these because most of the season defaults to a neutral
  replacement assumption regardless of how badly their brief action
  went — `PPG_AR` correctly isolates that the actual performance, not
  just the absence, was bad.

**This resolves round 1's open question (§2/§13) rather than leaving
it unresolved**: instruction explicitly says injury-shortened players
must NOT be exempted from the bust label merely because their
per-game rate was adequate ("do not remove injury-shortened players
merely because their per-game production was adequate"). `P`'s 50/50
blend of `AATP` and shrunk `PPG_AR_eq` does exactly this — it still
lets a value-destroying absence (Antonio Brown 2019) register as a
real acquisition-cost failure, while the shrinkage component keeps a
tiny, clearly-lucky sample from dominating the other direction. Round
1's elevated partial-season flag rate (§2, ~29% vs 16.2% for full
seasons) is **confirmed as intended behavior under this instruction,
not an artifact requiring correction.**

### 22. Zero-game real-ADP rule — formalized, generalized

**Rule (not a player-specific override)**: any row with
`bust_primary_eligible = True` and `games_played = 0` receives
`bust_primary_label = True` automatically, bypassing the percentile
mechanism it cannot mathematically participate in (`compute_production()`
structurally requires non-null `ppg_ppr`, undefined at 0 games).

**Grounding, not assertion**: replacement level is a real, positive
number for every position/season in this data (e.g. real 2025 RB
`replacement_ppg` = 8.55, computed directly by
`lib.replacement.replacement_level_from_rank()` — the same function
`production.py` itself calls). Zero real points recorded across a full
season (`fantasy_points_ppr` = 0.00, a real, disclosed value, not a
placeholder — verified directly for Isaac Guerendo, 2025 RB) is below
ANY positive replacement baseline by construction — no percentile
computation is needed to establish that this is the worst possible
outcome in any peer cell.

**Strict-hybrid status — stated separately, per instruction**: strict
requires `P < 0` in addition to the primary flag. `P` cannot be
literally computed (undefined at 0 games), but the same replacement-
level argument extends directly: 0 recorded points is below the real,
positive `replacement_ppg` for every position in this dataset, which
is the exact condition `P < 0` tests for on rows where `P` IS
computable. **This row therefore also qualifies for
`bust_strict_label = True`, by logical extension of the same
replacement-level argument the literal `P<0` floor is built on — not
because `P` was computed and found negative, but because the
underlying condition the floor exists to detect (below-replacement
production) unambiguously holds.**

**Today's real count under this generalized rule: 1** (Isaac Guerendo,
2025 RB, `overall_adp`=158.83, round 14, R11+). The rule is written to
generalize to any future row meeting the same condition, not to this
player specifically.

### 23. Final proposed formula (recommendation, not yet implemented)

1. **Ranking measure**: `score_like = P - SBV_LAMBDA * expected_production`
   (G-score, §19), because the disagreement evidence favors it on
   substance, not just historical use.
2. **Peer cells**: position × `DATASET2_ADP_ROUND_BUCKETS`, era-
   stratified with the mechanical minimum-sample fallback to pooled
   (Method 4, §20).
3. **E_P-lookup-coverage gap (19 rows)**: fall back to a G-raw
   percentile (raw `P` ranked within the same peer cell) for exactly
   these rows — the same "pre-specified mechanical fallback" pattern
   as the era rule, applied to a different real gap. Real effect: 4 of
   19 flagged bust under this fallback (see §22's table in the
   analysis script output).
4. **Zero-game real-ADP row(s)**: automatic `bust_primary_label = True`
   and `bust_strict_label = True` per §22's rule — never subject to
   the percentile mechanism.
5. **Primary threshold**: bottom 20% within each (era-aware) peer cell.
6. **Strict hybrid**: bottom 20% AND `P < 0`.
7. **Tie rule** (§11, unchanged — no ties found in real data, kept as
   a forward-looking rule): `method="average"` percentile rank,
   inclusive `<=` cutoff comparison.
8. **Sensitivities preserved, not primary**: bottom 25%/30% (§9),
   percentage-of-threshold floors (§10), fully-pooled era treatment
   (Method 1), `AATP`-alone and `PPG_AR`-alone availability measures
   (§21), G-raw as the full ranking method (§19).

### 24. Exact final counts — CORRECTED (2026-07, implementation round)

**Disclosure: the counts originally reported here (532 primary / 104
strict) were wrong, caught during implementation, not before.**
`section_22_23_final_formula()` in `bust_label_round2_analysis.py`
computed its "final formula" ranking using the plain POOLED
`["position", "adp_bucket"]` percentile — it never actually applied
era-stratification (Method 4), despite §20 recommending Method 4 and
§23's own item 2 claiming to use it. This was a real bug in that
function, not a rounding or tie-rule difference. It was caught exactly
where it was supposed to be caught: `lib/dataset2/canonical_outcome_table.py`'s
real implementation of the approved formula (which correctly applies
era-stratification with the mechanical fallback) produced **522**, not
532, and re-deriving the count independently after fixing the
analysis script's bug reproduces **522** exactly — two independently
written computations of the same formula now agree. The verified,
correct counts are:

| | n | % of 2,677 primary-eligible |
|---|---|---|
| **Primary bust** (`bust_primary_label` — era-specific/pooled-fallback G-score + G-raw fallback for the 19-row lookup gap + automatic zero-game rule) | **522** | 19.5% |
| **Strict below-replacement** (`bust_strict_below_replacement_label` — primary AND `P<0`, plus the zero-game logical extension) | **103** | 3.8% |
| Sensitivity: bottom 25% (`bust_primary_sensitivity_pct25_label`, same ranking pipeline as primary) | 659 | 24.6% |
| Sensitivity: bottom 30% (`bust_primary_sensitivity_pct30_label`, same ranking pipeline as primary) | 790 | 29.5% |

Real assignment-method totals (`bust_primary_assignment_method`, population = 2,677 `bust_primary_eligible` rows):

| Method | n |
|---|---|
| `era_specific_g_score` | 2,592 |
| `pooled_era_g_score_fallback` | 65 |
| `g_raw_lookup_gap_fallback` | 19 (4 flagged primary bust, 2 also strict) |
| `automatic_zero_game` | 1 (flagged bust at every threshold, including strict) |
| **Total** | **2,677** |

### 25. Prevalence under the CORRECTED final formula (primary / strict)

| Position | n | primary | rate | strict | rate |
|---|---|---|---|---|---|
| QB | 386 | 77 | 19.9% | 0 | **0.0%** |
| RB | 939 | 183 | 19.5% | 45 | 4.8% |
| TE | 312 | 58 | 18.6% | 3 | 1.0% |
| WR | 1,040 | 204 | 19.6% | 55 | 5.3% |

**Real finding worth flagging plainly**: the `P<0` strict floor is
NOT position-symmetric — zero QBs in this entire dataset ever record
`P<0` among the flagged primary busts (QB replacement level is low
enough, and even bad QB seasons rarely post literally negative
value-add). The strict-hybrid label, as currently formulated, is
effectively a RB/WR/TE phenomenon. This is disclosed here, not hidden
— if a position-balanced strict definition is wanted, this floor
choice needs revisiting.

| ADP bucket | n | primary | rate | strict | rate |
|---|---|---|---|---|---|
| R1-2 | 381 | 75 | 19.7% | 0 | 0.0% |
| R3-5 | 570 | 110 | 19.3% | 1 | 0.2% |
| R6-10 | 972 | 190 | 19.5% | 43 | 4.4% |
| R11+ | 754 | 147 | 19.5% | 59 | 7.8% |

| Era | n | primary | rate | strict | rate |
|---|---|---|---|---|---|
| pre-2011 | 179 | 29 | 16.2% | 10 | 5.6% |
| 2011-2020 | 1,571 | 310 | 19.7% | 44 | 2.8% |
| 2021+ | 927 | 183 | 19.7% | 49 | 5.3% |

Note the era rates are now much closer to each other (16.2/19.7/19.7)
than the earlier, wrong 532-based table showed (22.3/19.4/20.2) — the
era-stratification bug being fixed is EXACTLY what corrects this,
consistent with §20's own finding that era-aware methods bring
pre-2011 down from a pooled-only 22.3% to ~15-16%.

| Games bucket | n | primary | rate | strict | rate |
|---|---|---|---|---|---|
| 0 | 1 | 1 | 100.0% | 1 | 100.0% |
| 1-4 | 110 | 28 | 25.5% | 0 | 0.0% |
| 5-8 | 225 | 69 | 30.7% | 4 | 1.8% |
| 9-12 | 455 | 130 | 28.6% | 31 | 6.8% |
| 13+ | 1,886 | 294 | 15.6% | 67 | 3.6% |

| Rookie status | n | primary | rate | strict | rate |
|---|---|---|---|---|---|
| Veteran | 2,395 | 444 | 18.5% | 72 | 3.0% |
| Rookie | 282 | 78 | 27.7% | 31 | **11.0%** |

Rookie strict-hybrid rate (11.0%) remains roughly 3.7x the veteran
rate (3.0%) — this finding survives the correction essentially intact.

### 26. What remains for the next round

**Superseded — labels are now implemented.** §23's formula was
approved and `lib/dataset2/canonical_outcome_table.py` now computes
`bust_primary_label`, `bust_primary_sensitivity_pct25_label`,
`bust_primary_sensitivity_pct30_label`, and
`bust_strict_below_replacement_label` for real (commit history —
`bust_historical_sensitivity_label` remains reserved/null, its label
values were not in scope for this implementation round). The corrected
522/103 counts in §24-25 are the real, verified values under the
approved formula; the 532/104 figures earlier in this document are
preserved as a disclosed historical error, not silently deleted, per
this project's own decision-history conventions.
