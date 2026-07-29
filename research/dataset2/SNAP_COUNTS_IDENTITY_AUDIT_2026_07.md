# Source B Identity & Aggregation Audit — 2026-07

Requested before approving Source B's traits for use. Every number
below was computed by running the real, committed
`lib/dataset2/snap_identity.py` and `lib/dataset2/snap_traits.py`
against the REAL, fully-acquired `snap_counts` data (2013-2025, fetched
and cached via `scripts/nflverse_source.py`'s asset-ID-pinned,
sha256-verified mechanism — the same one already used for
players/schedules/depth_charts) and the real master DB population —
not samples, not synthetic data.

---

## Acquisition: raw files preserved unchanged in the established
cache/provenance structure

All 13 real seasons (2013-2025) fetched and registered exactly like
every other nflverse release this project uses — asset-ID-pinned,
sha256-verified, recorded in `scripts/nflverse_source_manifest.json`
under a new `"snap_counts": {"seasons": {...}}` key (mirrors
`depth_charts`'s structure). Real row counts recorded: 23,799 (2013)
up to 26,615 (2024). Files themselves live at
`data/raw/nflverse/annual/snap_counts_{season}.csv`, gitignored like
every other raw cache file — only the manifest (small provenance
metadata) is committed.

**Season 2012 is deliberately excluded, not silently skipped**:
`register_snap_counts_manifest_entry(2012)` raises a `ValueError`
rather than caching it — the real 2012 asset is a header-only file
(154 bytes, zero data rows), not genuine coverage. Verified directly.

---

## Identity crosswalk audit — full real 2013-2025 population

| Metric | Value |
|---|---|
| Total real rows (all `game_type`, 2013-2025) | 324,611 |
| Matched (real `gsis_id` resolved) | 324,384 |
| Unmatched | 227 |
| **Match rate** | **99.93%** |
| Duplicate `pfr_id` mappings in `players.csv` (one-to-many conflict) | **0** |
| Many-to-one conflicts (2+ distinct `pfr_player_id` → same `gsis_id`) | **0** |
| `players.csv` rows with no `pfr_id` at all | 2,481 (9.9% of `players.csv`) |

**Match rate by season** — real, computed, never below 99.79%:

| Season | Rate | Season | Rate | Season | Rate |
|---|---|---|---|---|---|
| 2013 | 0.9998 | 2018 | 1.0000 | 2023 | 0.9995 |
| 2014 | 0.9997 | 2019 | 0.9987 | 2024 | 0.9984 |
| 2015 | 0.9999 | 2020 | 0.9992 | 2025 | 0.9979 |
| 2016 | 0.9997 | 2021 | 0.9987 | | |
| 2017 | 1.0000 | 2022 | 0.9997 | | |

**Match rate by position** — real, computed, worst 8 shown, never
below 99.49%: DL 0.9949, DB 0.9969, TE 0.9980, FS 0.9981, G 0.9985,
WR 0.9985, T 0.9989, S 0.9992.

**Unmatched rows are never dropped.** Both `crosswalk_snap_counts_identity()`
and `build_raw_player_game_snaps()` preserve every row; an unmatched
row keeps a null `gsis_id` and a real `identity_match_status`
explaining why (no matching `pfr_id` in `players.csv`, vs. a null
`pfr_player_id` in the source itself — two different real situations,
never collapsed into one). `build_identity_audit()`'s
`unmatched_detail` groups and counts them by real `(pfr_player_id,
player, status)` rather than silently discarding the list.

---

## Grain, duplicates, and postseason — confirmed real

- **Grain**: player-GAME (one row per player per real game — `game_id`,
  `week`, `game_type` including REG and playoffs).
- **Duplicate player-game records**: checked directly against the FULL
  real 2013-2025 REG population (310,475 rows) — **zero** duplicate
  `(pfr_player_id, game_id)` rows found. `build_raw_player_game_snaps()`
  does not just document this absence — it ACTIVELY CHECKS for a
  duplicate `(gsis_id, game_id)` pair after crosswalking and raises a
  `RuntimeError` if one is ever found, per the explicit instruction
  that duplicated/misaligned snap records are a top real risk.
- **Postseason rows**: real `WC`/`DIV`/`CON`/`SB` rows are present in
  the raw data (324,611 total rows vs. 310,475 real `REG` rows — the
  ~14,000-row gap is real postseason volume). `build_raw_player_game_snaps()`
  filters to `game_type == 'REG'` internally — the same real bug class
  already found and fixed in Source A.

---

## Aggregation semantics — offense/defense/special-teams snaps and
percentages

### `offense_snaps` — SUM
Real per-game count, summed across the real season. Unambiguous.

### `offense_pct` — RECOMPUTED, verified exactly against real data
- **Real denominator, verified**: `max(offense_snaps)` among all real
  players on that (`game_id`, `team`) — the O-line/QB group reliably
  plays every real offensive snap, so the maximum observed player IS
  the real team offensive-play total for that game. Verified against
  real 2023 data (10,078 rows): **zero** rows exceed a 0.01 real
  discrepancy against nflverse's own reported `offense_pct` when this
  denominator is used.
- **Season aggregation**: `player's season offense_snaps ÷ sum of
  that game's real team-game max, for each of the player's own real
  games, using that game's own real team` — correctly follows a
  mid-season trade (see validation table below).

### `defense_snaps` / `st_snaps` — SUM, real and unambiguous.

### `defense_pct` / `st_pct` — DEFERRED, NOT output
- **What was tried**: the same max-based recomputation that worked
  exactly for `offense_pct`.
- **Real finding, `defense_pct`**: diverges beyond rounding on
  646/10,550 real 2023 rows (6.1%), sometimes substantially (a real
  row: reported 0.73 vs. recomputed 1.00). Root cause, confirmed by
  inspecting real rows: high-rotation defensive games where NO single
  player reaches 100% of real defensive snaps — unlike the offensive
  line, there's no position that reliably anchors every defensive
  snap, so `max()` UNDERSTATES the true denominator in real
  rotation-heavy or blowout games.
- **Real finding, `st_pct`**: far worse — 16,363/18,055 real rows
  (90.6%), mean discrepancy 0.068. Special teams involves multiple
  distinct situational units (kickoff, kickoff return, punt, punt
  return, field goal/PAT) with different real play counts each, not
  one unified platoon.
- **Action taken, per the approved reconstruct-or-defer rule**: no
  season-level `defense_pct`/`st_pct` column is output.
  `defense_snaps`/`st_snaps` (real, unambiguous sums) ARE output.

### `games_active` — a real, computed COUNT
Number of real games where `offense_snaps > 0` OR `defense_snaps > 0`
OR `st_snaps > 0` — i.e., real games with ANY recorded snap activity.
A real row with all-three-zero (confirmed to occur in real data — a
player on the active roster with zero recorded snap participation) is
correctly excluded from this count, not counted as "active."

---

## Real-data validation table (2023 season)

| Player | Pos | offense_snaps | defense_snaps | st_snaps | games_active | offense_pct |
|---|---|---|---|---|---|---|
| Josh Allen | QB | 1,126 | 0 | 0 | 17 | 0.9674 |
| Christian McCaffrey | RB | 812 | 0 | 1 | 16 | 0.8080 |
| Tyreek Hill | WR | 695 | 0 | 3 | 16 | 0.6702 |
| Travis Kelce | TE | 775 | 2 | 0 | 15 | 0.7696 |
| Chase Claypool | WR | 195 | 0 | 102 | 12 | 0.2610 |

**Traded-player validation (real, Christian McCaffrey's real 2022
CAR → SF mid-season trade)**, by season:

| Season | offense_snaps | offense_pct | games_active |
|---|---|---|---|
| 2021 | 272 | 0.6004 | 7 |
| 2022 | 777 | 0.7330 | 17 |
| 2023 | 812 | 0.8080 | 16 |

**Preseason lag hand-verified**: 2023's `prior_season_offense_snaps`
(777.0) and `prior_season_offense_pct` (0.733019) match 2022's real
`offense_snaps`/`offense_pct` EXACTLY — confirming the raw/season/
preseason separation and its leakage-proof lag work correctly against
real data, not just synthetic fixtures.

---

## Real-data run summary

- Real raw player-game rows (REG only, 2013-2025): 310,475 — matches
  the identity audit's real REG-only count exactly.
- Real season-level population (master DB, skill positions,
  2013-2025): 7,512 rows in, 7,512 rows out (`build_season_snap_usage()`)
  — no row lost or duplicated.
- `offense_snaps` missingness: 0 (a real count, 0 when no real
  activity). `offense_pct` missingness: 16 rows (0.2%) — every one of
  these 16 real player-seasons has real `offense_snaps == defense_snaps
  == st_snaps == games_active == 0`, i.e. genuinely zero recorded snap
  activity that season (spot-checked, not merely asserted) — disclosed
  missingness, not a defect.

---

## Full suite

839/839 passing (804 before this slice + 13 `snap_identity` tests +
18 `snap_traits` tests + 4 from the existing
`test_no_isolated_research_dependency.py` guardrail auto-scaling with
the 2 new `lib/dataset2/*.py` files this slice added).

---

## Explicitly NOT done in this slice, per instruction

No route-participation, role, or family #9 threshold derivation from
this snap data. No `pbp_participation`/Source C work. Stopping here
for review.
