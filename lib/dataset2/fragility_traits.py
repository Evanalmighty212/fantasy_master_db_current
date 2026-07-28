"""
lib/dataset2/fragility_traits.py

Dataset 2 families #86 (split, part) and #88 (split, part) -- the
depth-chart/competition-driven and age/frame-driven Dataset-2B
sub-signals approved 2026-07 as part of the depth-chart-cluster slice.
Both build ON TOP of already-built Tier-1 sibling modules' output, no
new acquisition.

--- #86 (split, part): volume fragility, POSITION-AWARE rank-1-tie
interpretation (REVISED 2026-07 after the real-data integration audit)
---

Input: lib.dataset2.depth_chart_traits.build_depth_chart_traits()'s
own output (or an equivalent DataFrame with the same columns).

REAL-DATA FINDING THIS REVISION IS BUILT ON (see
research/dataset2/INTEGRATION_AUDIT_2026_07.md): the original single
`committee_uncertainty` flag (real observed `starter_group_size`
exceeding the FIXED structural `position_starter_count`) was checked
against the full real 2006-2024 depth-chart history. It works
correctly for QB/RB/TE (real, occasional committees: New England
RB/James White+Sony Michel 2020, Kansas City TE/Travis Kelce+Deon
Yelder 2020) -- but WR's real `starter_group_size` was 2, not the
assumed structural 3, in 85-99% of team-seasons from 2006-2012, only
becoming majority-3 around 2023-2024. Multiple rank-1 WRs primarily
reflect real, changing BASE OFFENSIVE PERSONNEL STRUCTURE across NFL
history (the league-wide shift toward "11 personnel"/3-WR-base over
the 2010s-2020s), not role uncertainty the way an RB or TE committee
does -- a single universal "committee" interpretation was WRONG for
WR, not just imprecise.

REVISED DESIGN, approved 2026-07: WR is REMOVED from any
committee/uncertainty-style interpretation. Rank-1 ties are now
represented as:
- `multiple_rank1_players` (ALL positions): the NEUTRAL SOURCE FACT --
  real_starter_group_size > 1 for this row's (season, team, position)
  group. Carries NO interpretation by itself.
- `qb_starter_uncertainty`, `rb_committee_indicator`,
  `te_co_starter_indicator`: position-SCOPED interpretive indicators
  (populated only for their own position, null elsewhere) -- for
  QB/RB/TE, structurally single-occupant slots
  (config.DATASET2_DEPTH_CHART_STRUCTURAL_STARTER_COUNT == 1 for all
  three, unaffected by the WR finding), so these are mechanically
  identical to `multiple_rank1_players` restricted to that position --
  a real tie at a normally-single-occupant slot IS a real signal of
  competition/uncertainty for these three positions.
- WR gets NO uncertainty-style indicator. Instead, WR-specific
  PERSONNEL-STRUCTURE/OPPORTUNITY facts (never framed as uncertainty):
  `wr_starter_group_size` (pass-through of the real observed count),
  `wr_starter_group_member` (real starter-group membership),
  `wr_league_starter_group_size_norm` (the REAL, EMPIRICAL per-season
  league-wide mode of WR starter_group_size, computed fresh from data
  every season -- not a fixed constant, so it moves automatically as
  the league's real personnel usage moves), and
  `wr_starter_group_size_vs_league_norm` (this team's real deviation
  from that season's real norm -- purely descriptive, no threshold
  applied, not a flag).

`config.DATASET2_DEPTH_CHART_STRUCTURAL_STARTER_COUNT` is UNCHANGED
and still required: depth_chart_traits.py's own `position_starter_count`
output column (explicitly preserved, per the approved design, as one
of the real WR information fields) is sourced from it, and QB/RB/TE's
indicators above still rely on it being 1 for those three positions.
Only its former role as WR's committee-detection gate is removed here
-- the dict itself was never the problem, using it as a universal
committee threshold for a position with a structurally different,
historically-shifting norm was.

Every native tie is still preserved exactly as depth_chart_traits.py
reports it -- this module never infers an order within a tied group,
for any position.

- `team_qb_uncertainty`: UNCHANGED from the prior design -- True for
  EVERY skill-position player on a team whose real QB group is tied at
  the starter slot, broadcast team-wide. Not affected by the WR
  finding (QB-specific, not WR-specific).

The roadmap's full family #86 split also anticipates a "high
competition" signal from family #12 (Competition quality, Tier 3,
depends on #4+#10) -- #12 is not yet built, so this module builds ONLY
the portion that depends on #10 alone, not the full family.

--- #88 (split, part): workload/durability risk, age/frame-only
sub-signals (UNCHANGED by this revision) ---

Input: lib.dataset2.experience_age_draft.build_experience_age_draft_traits()'s
own output (needs `position`, `body_size_bmi`).

- `body_size_position_z`: BMI z-scored within position, mirroring the
  SAME within-group z-score pattern already approved for families #1/#2
  (`lib.dataset2.common.within_group_zscore()`).
- `workload_qualified`: the literal string "pending" on every row,
  same pattern as family #9's `opportunity_qualified` -- the workload
  proxy this family's original sub-bullets need is not yet retained
  (same Tier-2 dependency as #9/#16/#20). No threshold invented inline.

TEST SCOPE: tests/test_dataset2_fragility_traits.py proves
implementation correctness against synthetic fixtures only.
REAL-DATA CHECK (2026-07, this revision): the revised indicators were
run against the real 2006-2024 depth-chart population -- see
research/dataset2/DATASET2_TRAIT_ROADMAP.md's integration-audit
section for the by-position/by-season breakdown.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from lib.dataset2.common import validate_columns, within_group_zscore
from lib.dataset2.depth_chart_traits import DEPTH_CHART_STATUS_STARTER

VOLUME_FRAGILITY_REQUIRED_COLUMNS = (
    "season",
    "player_id",
    "position",
    "depth_chart_team",
    "depth_chart_status",
    "depth_rank_tied",
    "starter_group_size",
    "position_starter_count",
)

VOLUME_FRAGILITY_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "multiple_rank1_players",
    "qb_starter_uncertainty",
    "rb_committee_indicator",
    "te_co_starter_indicator",
    "wr_starter_group_size",
    "wr_starter_group_member",
    "wr_league_starter_group_size_norm",
    "wr_starter_group_size_vs_league_norm",
    "team_qb_uncertainty",
)

DURABILITY_RISK_REQUIRED_COLUMNS = ("season", "player_id", "position", "body_size_bmi")

DURABILITY_RISK_OUTPUT_COLUMNS = (
    "season",
    "player_id",
    "position",
    "body_size_position_z",
    "workload_qualified",
)

WORKLOAD_STATUS_PENDING = "pending"


def _wr_league_starter_group_size_norm(out: pd.DataFrame) -> pd.Series:
    """Real, empirical per-season league-wide mode of WR
    starter_group_size, computed fresh from the data passed in (never a
    fixed constant) -- one observation per (season, team), so a team
    with a 3-way tie doesn't get triple-counted relative to a team with
    a clean single starter. Ties in the mode itself (e.g. an exact
    50/50 season) resolve to the smaller value, a deterministic,
    disclosed tiebreak. Returns a season -> norm mapping aligned back
    onto `out`'s row index."""
    wr_starters = out[(out["position"] == "WR") & (out["depth_chart_status"] == DEPTH_CHART_STATUS_STARTER)]
    team_level = wr_starters[["season", "depth_chart_team", "starter_group_size"]].drop_duplicates()
    norm_by_season = team_level.groupby("season")["starter_group_size"].agg(lambda s: s.mode().iloc[0])
    return out["season"].map(norm_by_season)


def build_volume_fragility_traits(depth_chart_traits_df: pd.DataFrame) -> pd.DataFrame:
    """#86 (split, part). Builds directly on top of
    depth_chart_traits_df -- covers the same population it does, one
    row per (season, player_id, position). See module docstring for
    the full, position-aware field design."""
    validate_columns(depth_chart_traits_df, VOLUME_FRAGILITY_REQUIRED_COLUMNS, "depth_chart_traits_df")

    out = depth_chart_traits_df.copy()
    has_data = out["depth_chart_status"].notna()

    # Neutral source fact -- no interpretation, any position.
    out["multiple_rank1_players"] = np.where(has_data, (out["starter_group_size"] > 1).astype(float), np.nan)

    # Position-scoped interpretive indicators -- QB/RB/TE only, since
    # their structural starter count is 1 (a real tie there is a real
    # signal); mechanically identical to multiple_rank1_players
    # restricted to that position.
    is_qb, is_rb, is_te, is_wr = out["position"] == "QB", out["position"] == "RB", out["position"] == "TE", out["position"] == "WR"
    out["qb_starter_uncertainty"] = np.where(is_qb, out["multiple_rank1_players"], np.nan)
    out["rb_committee_indicator"] = np.where(is_rb, out["multiple_rank1_players"], np.nan)
    out["te_co_starter_indicator"] = np.where(is_te, out["multiple_rank1_players"], np.nan)

    # WR: personnel-structure/opportunity facts, never an uncertainty label.
    out["wr_starter_group_size"] = np.where(is_wr, out["starter_group_size"], np.nan)
    out["wr_starter_group_member"] = np.where(
        is_wr & has_data, (out["depth_chart_status"] == DEPTH_CHART_STATUS_STARTER).astype(float), np.nan
    )
    wr_norm = _wr_league_starter_group_size_norm(out)
    out["wr_league_starter_group_size_norm"] = np.where(is_wr & has_data, wr_norm, np.nan)
    out["wr_starter_group_size_vs_league_norm"] = np.where(
        is_wr & has_data, out["starter_group_size"] - wr_norm, np.nan
    )

    # team_qb_uncertainty -- unchanged from the prior design.
    qb_tied_teams = out.loc[
        (out["position"] == "QB") & (out["depth_chart_status"] == DEPTH_CHART_STATUS_STARTER) & (out["depth_rank_tied"] == True),  # noqa: E712
        ["season", "depth_chart_team"],
    ].drop_duplicates()
    qb_tied_teams["_team_qb_uncertain"] = True
    out = out.merge(qb_tied_teams, on=["season", "depth_chart_team"], how="left")
    team_has_data = out["depth_chart_team"].notna()
    out["team_qb_uncertainty"] = np.where(
        team_has_data, out["_team_qb_uncertain"].fillna(False).astype(float), np.nan
    )

    return out[list(VOLUME_FRAGILITY_OUTPUT_COLUMNS)].reset_index(drop=True)


def build_durability_risk_traits(experience_age_draft_df: pd.DataFrame) -> pd.DataFrame:
    """#88 (split, part), age/frame-only portion. Builds directly on
    top of experience_age_draft_df -- covers the same population it
    does. `workload_qualified` is always "pending" -- see module
    docstring."""
    validate_columns(experience_age_draft_df, DURABILITY_RISK_REQUIRED_COLUMNS, "experience_age_draft_df")

    out = experience_age_draft_df.copy()
    out["body_size_position_z"] = within_group_zscore(out, "body_size_bmi", "position")
    out["workload_qualified"] = WORKLOAD_STATUS_PENDING

    return out[list(DURABILITY_RISK_OUTPUT_COLUMNS)].reset_index(drop=True)
