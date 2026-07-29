# Route-Definition Investigation & Proposal — Source C Stage 1, 2026-07

**STATUS: NOT SUPPORTED.** Complete player route participation is not
recoverable from `pbp_participation`, because `route` identifies only
the targeted receiver's route. Do not implement or imply full routes
run, route participation, routes per dropback, targets per route run,
or alignment shares from this source. The two narrower ideas in §4
(targeted-route type; route-specific target outcomes) are separate,
coverage-limited hypotheses, not substitutes for complete route
participation, and are not implemented either — proposals only.

Requested before any route-participation trait is implemented:
"Before defining a 'route,' inspect the real field semantics and
compare candidate route-count definitions on actual plays. Do not
assume that appearing in a participation list automatically means a
route was run." This document reports what the real
`pbp_participation` data actually contains, and proposes (does **not**
implement) a route definition. Every number below comes from running
real code against the real, fully-acquired 2016 (20-column) and 2023
(26-column) files.

**Bottom line up front**: this file cannot support a true "routes run"
count. `route` is a single value per PLAY, describing only the
targeted receiver's route type — not a per-player field, and not
populated for the 3-4 other real receivers/backs who ran routes but
weren't thrown to. Building "targets per route run" from this source
alone would silently misrepresent what the data measures. Recommend
deferring that specific trait and building two narrower, honestly-scoped
traits instead (see §4).

---

## 1. The `route` field is play-level, not player-level

The original opportunity-foundation proposal's own §5 already flagged
this as a real risk before any code existed ("turning 'one route
string per play' into 'how many routes did player X run this week'
... is not a simple column read"). This investigation confirms it is
worse than "extra ETL work" — **the file structurally cannot answer
that question at all**, for any player except the one who was thrown
to.

A real 2023 example (`2023_01_ARI_WAS`, play 77):

| Field | Value |
|---|---|
| `offense_players` | 11 real IDs (full personnel) |
| `offense_positions` | C;G;QB;RB;T;T;T;TE;WR;WR;WR |
| `route` | `HITCH/CURL` |

`route` gives exactly ONE route type for this play, even though real
football has up to 5 real eligible receivers who could each be running
a different real route simultaneously. There is no per-player index,
ID, or position column that ties `route` to a specific one of the 11
`offense_players` — attaching it to "the receiver" requires an
external join to a real play-by-play dataset's `receiver_player_id`
(outside `pbp_participation`, and outside this stage's approved
scope).

---

## 2. Real coverage and null-pattern of `route` — a cleaner picture than
initially assumed

Real 2023 counts (46,168 real plays, all game types before REG
filtering):

| Metric | Value |
|---|---|
| `route` non-null | 19,616 (42.5%) |
| `route` null | 26,552 (57.5%) |
| `was_pressure` null | **0** (always populated — NOT a usable
  pass-play flag, contrary to what its name suggests) |
| `time_to_throw` non-null | 20,306 (44.0%) |

**`time_to_throw` non-null is a much better real proxy for "this was a
real pass dropback"** than `was_pressure` (which is populated,
True/False, on every play including runs and special teams — checked
directly, not assumed). Cross-checking the two real NGS fields against
each other:

- Of the 20,306 real dropback plays (`time_to_throw` present), only
  **770 (3.8%)** have a null `route` — a small, real residual
  (consistent with real sacks, scrambles, spikes, or plays NGS
  couldn't classify a route for).
- Of the 19,616 real plays with `route` present, only 80 (0.4%) have a
  null `time_to_throw` — i.e. `route` and `time_to_throw` agree with
  each other on ~99.6% of real rows.

So `route`'s real null pattern is NOT noise — it is close to exactly
"non-dropback plays" (runs, special teams, the earlier finding that
`offense_players` on a real special-teams play can be entirely
defensive-position personnel, e.g. a real punt-team/return-team
snapshot). This is good: it means `route`, when present, is a reliable
real signal about the real targeted receiver's route on a real
dropback — the limitation is entirely about WHICH player it describes
(one, not all), not about data quality within that one player.

`ngs_air_yards` was checked as a possible secondary signal and found
**100% null across the full real 2023 season (46,168/46,168)** — an
unpopulated real field in this release, not usable for anything.

---

## 3. Why "offense_players membership on a pass play" is not a safe
proxy for "ran a route" either

The natural fallback — count a player as having run a route whenever
they appear in `offense_players` on a real dropback play
(`time_to_throw` non-null) and hold a receiving-eligible position
(WR/TE/RB) — was evaluated and rejected as a *route count*, though it
remains usable as a *personnel-opportunity* signal (§4B):

- Real personnel data confirms up to 2 real RBs and 2-3 real TEs can
  be on the field together on a real dropback (`n_offense` real values
  up to 13 observed), and pass-blocking is a real, common assignment
  for exactly these positions — a real RB or TE who stays in to
  pass-block appears in `offense_players` on a real dropback without
  running a route. There is no field in this source that distinguishes
  "stayed in to block" from "ran a route" for a non-targeted player.
- This would systematically OVERCOUNT true route participation for
  every position group that sometimes pass-blocks (RB, TE, and in
  rarer real packages, WR on jet-sweep/stay-blocking looks) while
  UNDERCOUNTING nothing (a real route-runner who wasn't targeted still
  correctly appears in the list) — an asymmetric, one-directional bias
  that would misstate route participation specifically for the
  positions (RB/TE) where the false "route" signal matters most for
  family #16.

---

## 4. Proposal — two narrower, honestly-scoped traits instead of a
routes-run count

### A. Target route-type profile (uses `route` correctly, for its real
scope: the targeted receiver only)

For plays where a player is the real receiver-of-record (joinable via
Source A's existing weekly `stats_player` `receiver_player_id`, a
target that already has confirmed real identity — no new join risk),
attach that play's real `route` value. This produces a legitimate
trait: **which route types a player runs when he IS targeted** (e.g.
real route-tree tendency — mostly `GO`/`POST` vs. mostly
`SCREEN`/`SWING`), not a route-running volume metric. Scope is
explicitly "conditional on being targeted," stated as such in any
future trait name/docstring (e.g. `targeted_route_type_mix`, not
`routes_run`).

**Limitation to disclose**: this only characterizes a player's routes
on the ~40-45% of real dropbacks where a target is recorded and NGS
classified a route — it says nothing about a player's non-targeted
route-running.

### B. Eligible-receiver dropback personnel share (uses `offense_players`
+ `time_to_throw`, explicitly NOT called a route count)

For real dropback plays (`time_to_throw` non-null, the verified real
proxy from §2), the share of a team's real dropback plays where a
given WR/TE/RB appears in `offense_players` — a real, disclosed
**personnel-opportunity** signal (closer to "was on the field for
passing situations" than Source B's game-level `offense_pct`), NOT a
verified route count. Must be named and documented accordingly (e.g.
`dropback_personnel_share`, not `route_participation_rate`) so it is
never confused with an actual route-running measurement, and its
known RB/TE pass-blocking overcount bias (§3) must be stated in the
same docstring, not left implicit.

### What this proposal explicitly does NOT recommend

Building any field literally named "route count," "routes run," or
"targets per route run" from `pbp_participation` alone. If that trait
is still wanted, the real prerequisite is investigating whether
nflverse (or another real source) publishes a dedicated
routes-run-per-player dataset (Next Gen Stats has one publicly, e.g.
via nfl.com's advanced stats — not yet checked against nflverse's
release catalog for this project). That investigation is out of scope
for this stage and is flagged here as a real open question for a
future Source C Stage 2 (or Source D) discussion, not started or
assumed.

---

## Stop point

This is a proposal only. No route, personnel-share, or target-route
trait has been implemented in `lib/dataset2/participation_traits.py`
in this stage — that module currently outputs only the non-route
`offense_plays_participated`/`defense_plays_participated` counts
already approved in scope. Per instruction, implementation of either
candidate above (§4A/§4B) waits for explicit approval, together with
family #9 threshold selection and any Source C Stage 2 work.
