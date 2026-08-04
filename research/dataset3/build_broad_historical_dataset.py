"""
build_broad_historical_dataset.py  (Dataset 3 research foundation, Deliverable 2)

Research script -- NOT part of the production pipeline. Reads the
production master database (already includes all current LWI
components) and re-exposes it as a BROADER research population than
`lwi_score notna()` -- every QB/RB/WR/TE player-season with meaningful
fantasy activity, including rows the current LWI has to exclude
(no ADP match, insufficient games), with clear flags rather than
silent exclusion. No filtering to LWI-eligible-only happens here.

"Meaningful fantasy activity" = games_played >= 1. This is a low,
explicit bar chosen specifically to be broader than LWI's own 8-game
floor -- the whole point of this dataset is to let future methodology
work see the players current LWI can't, not to pre-filter them again
for a different reason.

This is the ONLY filter applied on top of the master database, and it
excludes EXACTLY 2 rows (10,070 -> 10,068, verified directly, not
estimated): both are real, zero-activity player-seasons with
games_played == 0 and fantasy_points_ppr == 0.0 --
David Fales (2019, QB, NYJ, player_id 00-0031076) and
Malik Cunningham (2023, WR, NE, player_id 00-0038911). Both are also
no_adp_match. Neither represents real fantasy activity to analyze, so
excluding them is the filter working as intended, not an
unaccounted-for discrepancy.

Draft status is represented as a real THREE-state flag, not a binary,
because the underlying data genuinely only supports three states
today:
  - "drafted"           -- real ADP match (data_quality_flag in
                            matched_clean/matched_needs_review)
  - "verified_undrafted" -- adp_status == 'undrafted' AND
                            verification_status == 'verified', per
                            data/manual/adp_status_verification.csv
  - "unresolved"         -- no ADP match AND not verified-undrafted.
                            This is NOT the same claim as "drafted
                            elsewhere" or "confirmed undrafted" -- it
                            means genuinely unknown. As of this
                            writing, data/manual/adp_status_verification.csv
                            has zero verified rows, so in practice
                            almost every no_adp_match row lands here.
                            Collapsing this to a binary would silently
                            manufacture certainty that doesn't exist.

Input:  data/master/master_historical_db_with_lwi_2006_2025.csv
Output: research/output/dataset3/broad_historical_dataset.csv
"""

from pathlib import Path

import pandas as pd
from lib.player_season_authority import resolved_canonical_position_population

MASTER_DB_PATH = Path("data/master/master_historical_db_with_lwi_2006_2025.csv")
OUTPUT_PATH = Path("research/output/dataset3/broad_historical_dataset.csv")

MEANINGFUL_ACTIVITY_MIN_GAMES = 1
POSITIONS = ["QB", "RB", "WR", "TE"]

DRAFTED_QUALITY_FLAGS = {"matched_clean", "matched_needs_review"}

# Columns carried through unchanged from the master DB, grouped by what
# they're for -- see module docstring for why nothing is silently
# dropped for lacking an LWI score.
IDENTITY_COLS = ["season", "player_id", "player_name", "position", "team"]
PERFORMANCE_COLS = [
    "games_played", "fantasy_points_ppr", "ppg_ppr",
    "overall_finish_ppr", "position_finish_ppr",
]
ADP_COLS = [
    "overall_adp", "positional_adp", "adp_source", "adp_rank",
    "overall_adp_observed", "positional_adp_observed",
    "overall_adp_model", "positional_adp_model",
    "adp_status", "verification_status", "adp_proxy_used", "adp_proxy_reason",
]
DATA_QUALITY_COLS = ["data_quality_flag"]
LWI_COLS = [
    "lwi_eligibility_flag", "lwi_score", "lwi_score_diagnostic",
    "lwi_component_coverage", "lwi_version", "lwi_config_fingerprint",
    "adp_value_component", "fantasy_finish_component", "ppg_component",
    "positional_advantage_component", "playoff_performance_component",
    "consistency_component",
    "expected_finish_loso", "eva_raw", "adp_value_raw",
    "replacement_points", "points_above_replacement",
    "replacement_ppg", "ppg_above_replacement", "starter_ppg_iqr",
    "positional_advantage_raw", "positional_advantage_winsorized",
    "playoff_games_played", "playoff_availability",
]


def classify_draft_status(df: pd.DataFrame) -> pd.Series:
    drafted = df["data_quality_flag"].isin(DRAFTED_QUALITY_FLAGS)
    verified_undrafted = (df.get("verification_status") == "verified") & (
        df.get("adp_status") == "undrafted"
    )
    status = pd.Series("unresolved", index=df.index)
    status[drafted] = "drafted"
    status[verified_undrafted & ~drafted] = "verified_undrafted"
    return status


def build_broad_historical_dataset(master_path: Path = MASTER_DB_PATH) -> pd.DataFrame:
    df = pd.read_csv(master_path)

    df = resolved_canonical_position_population(df)
    df = df[df["position"].isin(POSITIONS) & (df["games_played"] >= MEANINGFUL_ACTIVITY_MIN_GAMES)].copy()

    df["adp_matched"] = df["data_quality_flag"].isin(DRAFTED_QUALITY_FLAGS)
    df["draft_status"] = classify_draft_status(df)
    df["lwi_eligible"] = df["lwi_score"].notna()

    keep_cols = (
        IDENTITY_COLS
        + ["adp_matched", "draft_status", "lwi_eligible"]
        + PERFORMANCE_COLS
        + ADP_COLS
        + DATA_QUALITY_COLS
        + LWI_COLS
    )
    keep_cols = [c for c in keep_cols if c in df.columns]
    return df[keep_cols].sort_values(["season", "position", "overall_finish_ppr"]).reset_index(drop=True)


def main():
    broad = build_broad_historical_dataset()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    broad.to_csv(OUTPUT_PATH, index=False)

    print(f"Broad historical dataset: {len(broad)} player-seasons "
          f"(games_played >= {MEANINGFUL_ACTIVITY_MIN_GAMES})")
    print(f"\nBy draft_status:\n{broad['draft_status'].value_counts().to_string()}")
    print(f"\nBy lwi_eligible:\n{broad['lwi_eligible'].value_counts().to_string()}")
    print(f"\nBy position:\n{broad['position'].value_counts().to_string()}")
    print(f"\nCross-tab, draft_status x lwi_eligible:")
    print(pd.crosstab(broad["draft_status"], broad["lwi_eligible"]).to_string())
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
