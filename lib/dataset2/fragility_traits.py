"""
lib/dataset2/fragility_traits.py

Dataset 2 families #86 (split, part) and #88 (split, part) -- the
depth-chart/competition-driven and age/frame-driven Dataset-2B
sub-signals approved 2026-07 as part of the depth-chart-cluster slice.
Both build ON TOP of already-built Tier-1 sibling modules' output, no
new acquisition.

--- #86 (split, part): volume fragility, committee/competition/QB
uncertainty ---

Input: lib.dataset2.depth_chart_traits.build_depth_chart_traits()'s
own output (or an equivalent DataFrame with the same columns).

- `committee_uncertainty`: True when a row's REAL, observed
  `starter_group_size` exceeds its position's FIXED structural
  expectation (`position_starter_count`) -- i.e. a genuine,
  data-confirmed committee (an extra player sharing what is normally a
  single-occupant starter slot: real 2020 examples New England
  RB/James White+Sony Michel, Kansas City TE/Travis Kelce+Deon Yelder).
  WR's routine 3-wide starting group matches its own structural
  expectation exactly (`starter_group_size == position_starter_count
  == 3`) and is correctly NEVER flagged by this rule -- this is the
  entire point of keeping `starter_group_size` and
  `position_starter_count` as two separate fields (see
  depth_chart_traits.py's own docstring). Null wherever the underlying
  depth-chart data itself is null (no data, not "no uncertainty").
- `team_qb_uncertainty`: True for EVERY skill-position player on a
  team whose real QB group is tied at the starter slot
  (`depth_chart_status == starter` AND `depth_rank_tied == True` for
  that team's QB row(s)) -- broadcast team-wide, since QB uncertainty
  is an offense-wide environment signal, not specific to the QB
  himself. Null where the team's QB depth-chart status itself is
  unknown, never defaulted to False.

The roadmap's full family #86 split also anticipates a "high
competition" signal from family #12 (Competition quality, Tier 3,
depends on #4+#10) -- #12 is not yet built, so this module builds ONLY
the portion that depends on #10 alone, not the full family. Not a
silent scope reduction -- documented here and in the roadmap.

--- #88 (split, part): workload/durability risk, age/frame-only
sub-signals ---

Input: lib.dataset2.experience_age_draft.build_experience_age_draft_traits()'s
own output (needs `position`, `body_size_bmi`).

- `body_size_position_z`: BMI z-scored within position, mirroring the
  SAME within-group z-score pattern already approved for families #1/#2
  (`lib.dataset2.common.within_group_zscore()`).
- `workload_qualified`: the literal string "pending" on every row,
  same pattern as family #9's `opportunity_qualified`. The roadmap's
  ORIGINAL family #88 sub-bullets ("age + HIGH WORKLOAD", "small frame
  + WORKHORSE role") both require a real touch/target workload proxy,
  which is NOT yet retained -- the exact same Tier-2 weekly-column
  dependency already documented for families #9/#16/#20. Per the same
  pattern approved for family #9: build the workload-INDEPENDENT
  portion now (age_position_z from experience_age_draft.py,
  body_size_position_z here), and do NOT collapse them into a single
  binary "age+frame risk" flag -- picking a numeric threshold for
  "older" or "smaller frame" is exactly the kind of judgment call this
  project requires real-data grounding and explicit approval for
  (matching family #9's own minimum-sample-floor process), not
  something to invent inline. Do not characterize this module's output
  as the full, workload-gated family #88 finding until the retention
  work lands and thresholds are proposed from real data.

TEST SCOPE: tests/test_dataset2_fragility_traits.py proves
implementation correctness against synthetic fixtures only. Real-data
integration and coverage validation has not happened yet -- same
required checkpoint as this module's siblings, see
research/dataset2/DATASET2_TRAIT_ROADMAP.md §6.
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
    "committee_uncertainty",
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


def build_volume_fragility_traits(depth_chart_traits_df: pd.DataFrame) -> pd.DataFrame:
    """#86 (split, part). Builds directly on top of
    depth_chart_traits_df -- covers the same population it does, one
    row per (season, player_id, position)."""
    validate_columns(depth_chart_traits_df, VOLUME_FRAGILITY_REQUIRED_COLUMNS, "depth_chart_traits_df")

    out = depth_chart_traits_df.copy()

    has_data = out["depth_chart_status"].notna()
    out["committee_uncertainty"] = np.where(
        has_data, (out["starter_group_size"] > out["position_starter_count"]).astype(float), np.nan
    )

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
