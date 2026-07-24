# ESPN championship-roster external benchmark

An external, human-expert-adjacent validation source for evaluating
Dataset 3 (and potentially, later, LWI or other models) against real
outside data -- **not** a definition of what "league winner" means for
this project, and **not** ground truth. Treat every judgment in this
directory as belonging to the source (ESPN), not to this project.
Nothing here modifies Dataset 3's target definition, LWI's weights,
`docs/PREDICTION_SPECIFICATION.md`, or any comparison formula in
`research/dataset3/`.

Stored outside `research/dataset3/` deliberately -- this is a shared
benchmark whose first use is evaluating Dataset 3, but it may later be
used against LWI or other models, and shouldn't be scoped to one
consumer.

Named for the **series**, not one author: most years are Tristan H.
Cockcroft, but 2014-2016 are credited to other ESPN staff (Tom
Carpenter, Keith Lipscomb) writing the same "won the championship"
series. Author is recorded per source and per player row
(`article_author`) -- never assumed uniform.

## Source

ESPN's annual series reporting, per player, **the percentage of ESPN
fantasy leagues in which that player was rostered on the team that
actually WON the league championship that season.** Confirmed, per
article, to be a specific series distinct from two other
similar-sounding ESPN series published in the same years:

- "playoff rosters" -- made the fantasy playoffs (much broader population)
- "finalist" / "championship-round rosters" -- made the title game, did not necessarily win it

Only the "won the championship" series is collected here. "League
winner" is this project's term, not the source's -- ESPN's own
language is "championship rosters" / "championship teams," never
"league winner." `explicitly_named_league_winner` is "No" on every row
for exactly that reason.

## Interpreting this data correctly

**Read this before writing any comparison code against this
dataset.** Five rules, each backed by what's actually in the data:

1. **Ranks (`espn_rank`) are comparable only WITHIN a season.** Rank 1
   in 2019 (a 57-row, 10%-floor year) and rank 1 in 2016 (a 10-row,
   fixed-cap year) are not measuring the same-sized population. Never
   compare `espn_rank` across seasons directly.
2. **A player's absence from this dataset is NOT a negative example.**
   Every year here is right-censored at that article's own cutoff
   (`inclusion_rule` / `coverage_type` per row -- see table below). A
   player not in the 2025 Top-50 might have been on 10.7% of
   championship rosters (just below the cutoff) or 0% -- this data
   cannot tell the two apart. Treating "not in table" as "confirmed 0%
   / not a champion" would be a real, silent error.
3. **2015 and 2016 are right-censored at the article's own Top-10
   limit** -- a much smaller published cutoff than every other
   collected year (Top 50, or a 10-15% floor that happens to produce
   31-57 rows). This is the article's own stated scope, confirmed
   directly, not a fetch limitation.
4. **Annual row counts must NOT be interpreted as a change in "how
   many league winners" existed that season.** A row count difference
   between, say, 2016 (10 rows) and 2024 (50 rows) reflects ESPN's
   publication cutoff choice that year, not a real change in how many
   players won fantasy championships (that population is roughly
   constant, set by roster construction and league count, not by how
   many rows a website chose to publish).
5. **`pct_championship_rosters` is the primary measure that's
   meaningfully comparable across seasons** -- unlike rank, which
   depends on that year's cutoff and population size, the percentage
   is a real per-player statistic computed the same way (probably)
   every year. "Probably," because **the underlying methodology and
   league denominator (how many total ESPN leagues, how ties are
   broken) are undisclosed in every single article, every year** --
   treat cross-season percentage comparisons as approximately
   comparable, not exactly comparable, given that real disclosure gap.

## Coverage structure, per season

| Season | Rows | `coverage_type` | `inclusion_rule` | `usable_for_benchmark` |
|---|---|---|---|---|
| 2025 | 50 | `fixed_rank_cap` | Top 50 | Yes |
| 2024 | 50 | `fixed_rank_cap` | Top 50 | Yes |
| 2023 | 50 | `fixed_rank_cap` | Top 50 | Yes |
| 2022 | 50 | `fixed_rank_cap` | Top 50 | Yes |
| 2021 | 0 | `inaccessible` | unknown (paywalled) | No |
| 2020 | 0 | `inaccessible` | unknown (paywalled) | No |
| 2019 | 57 | `percentage_threshold` | championship-roster % >=10% | Yes |
| 2018 | 45 | `percentage_threshold` | championship-roster % >=15% | Yes |
| 2017 | 31 | `percentage_threshold` | championship-roster % >=12.5% | Yes |
| 2016 | 10 | `fixed_rank_cap` | Top 10 | Yes |
| 2015 | 10 | `fixed_rank_cap` | Top 10 | Yes |
| 2014 | 0 | `partial_unstructured` | 4 players named in prose only, no table | No |
| 2013 | -- | -- (no article located) | -- | -- |

`coverage_type` is a controlled vocabulary
(`fixed_rank_cap` / `percentage_threshold` / `complete_published_table` /
`inaccessible` / `partial_unstructured`) -- `complete_published_table`
is defined but unused, since no collected year's article claims a
literal, threshold-free complete census. Both `inclusion_rule` and
`coverage_type` are joined onto **every row** of
`championship_roster_players.csv`, not just `sources.csv`, specifically
so comparison code reading the player-level file directly can't
accidentally ignore the censoring structure by skipping the sources
table.

**353 total player rows across 9 usable seasons.** Every article --
including the 3 confirmed-but-unusable ones -- is recorded in
`sources.csv` with `accessible` and `censoring_notes`; none are
silently omitted.

## What's in `championship_roster_players.csv`

One row per (season, player) table appearance -- **ranked
championship-table rows only.** No narrative-only mentions are
included (see "Known limitations"). Schema:

| Field | Meaning |
|---|---|
| `season` | NFL season |
| `player_name`, `position`, `team` | As ESPN reported (position includes K/D-ST) |
| `espn_rank` | Rank within THAT year's table only -- see rule 1 above |
| `pct_championship_rosters` | % of ESPN leagues where this player was on the title-winning roster -- see rule 5 above |
| `adp_overall` | Numeric ADP; blank if `draft_status == undrafted` |
| `draft_status` | `drafted` / `undrafted` / `not_reported_this_year` (2015-2016 published no ADP column at all -- distinct from "undrafted," never conflated) |
| `season_ppr_points` | As reported; blank for 2015-2016 |
| `espn_category` | Uniformly `on_champion_roster_ranked_table` |
| `narrative_label` | The source's own prose label for that player, where given (most rows: blank) |
| `explicitly_named_league_winner` | Always "No" |
| `reasoning_paraphrase` | Short paraphrase where the source gave one |
| `inclusion_rule`, `coverage_type` | This row's season-level censoring structure, joined down from `sources.csv` -- see "Coverage structure" above |
| `article_title`, `article_author`, `article_publication_date`, `article_url` | Full provenance, every row |
| `extraction_confidence` | `high` for all rows here -- every included year was cross-verified and/or spot-checked (log below) |
| `ambiguity_notes` | Flags K/D-ST rows as outside this project's QB/RB/WR/TE scope |

`sources.csv`: one row per **confirmed** article (12 total, including
the 3 inaccessible/unusable ones) with the full coverage-structure
fields plus `censoring_notes` (season-specific detail) and `note`
(extraction/spot-check detail). 2013 is not a row (no article found to
cite) -- reported in this README and in the build script's
`YEARS_SEARCHED_NOT_LOCATED` instead.

## Spot-check log

Every accessible year was checked at least once against the live
article before being trusted:

- **2025**: full 50-row table independently re-fetched a second time (separate tool call, not a cache hit) -- identical results.
- **2024, 2023, 2022, 2019**: one mid-table row each re-fetched and compared -- **Travis Etienne Jr. (2022, rank 25), Jake Elliott (2023, rank 30), Terry McLaurin (2024, rank 35), Kenyan Drake (2019)** -- all four matched exactly.
- **2018**: cross-validated via its own retrospective aside ("Todd Gurley II (34.4 percent, 2017), Tim Hightower (33.6 percent, 2015), Odell Beckham Jr. (31.0 percent, 2014), David Johnson (23.6 percent, 2016)"), which exactly matches all four of those years' OWN independently-fetched dedicated articles' rank-1 figures -- five-source agreement.
- **2017, 2016, 2015**: one row each re-fetched and compared -- rank-31 endpoint (2017, confirmed the article's real complete list, not a truncation), Matt Bryant (2016, rank 5), Chiefs D/ST (2015, rank 7) -- all matched exactly.
- **No discrepancies found in any spot-check performed.** This is a sample, not an exhaustive per-row audit -- 353 rows were not all individually re-verified.

## Known limitations

- **2020 and 2021 exist as the same series but are ESPN+ paywalled.**
  Alternate retrieval exhausted: web.archive.org unreachable by this
  tool (hard error, not a paywall response); a syndicated-copy
  candidate (FantasyPros' 2021 roster-frequency piece) checked and
  rejected -- it discloses no ESPN citation and uses an undisclosed,
  different methodology, so using it would misattribute a different
  source's numbers as ESPN's; search-indexed excerpts surfaced nothing
  beyond the paywall intro; no authenticated ESPN+ access available.
- **2014: right article confirmed, no usable table** -- only 4 named
  players with inconsistent partial stats in prose; not transcribed to
  avoid fabricating column values the source didn't provide in
  extractable form.
- **2013 and earlier: searched, not located.**
- **No stated methodology** in any article, any year -- league sample
  size and tie-breaking are never disclosed.
- **K/D-ST rows are outside this project's QB/RB/WR/TE scope** -- kept
  for provenance, not silently dropped.
- **Narrative-only mentions are deliberately excluded entirely**, not
  partially collected -- an earlier draft included one incidental such
  row, removed on review since one non-systematic row would have
  misrepresented the dataset's structure. A future systematic pass
  belongs in a separate `narrative_mentions.csv`, not mixed in here.
- **Extraction used a web-fetch summarization tool, not a raw HTML
  parse** -- mitigated by the spot-check log above, not equivalent to
  re-parsing raw HTML for all 353 rows.

## On "reproducibility"

Running `build_dataset.py` **deterministically regenerates** the CSV
outputs from the constants in that file, and its sanity checks fail
loudly on structural breaks (gapped ranks, `usable_for_benchmark`
disagreeing with actual data presence). That is auditability, not
independent verification: the script has no network access and does
not re-fetch the live source articles -- it writes out what was
manually transcribed and spot-checked at collection time. If ESPN
edits a source article later, this script would not detect the drift.

## Rebuilding

```bash
python research/benchmarks/espn_championship_rosters/build_dataset.py
```
