"""
research/diagnostics/adp_2025_investigation/audit_2025_adp_matching.py

Commit D audit (2026-07): runs the real raw MFL AUG15 2025 population
through the EXISTING, UNMODIFIED scripts/player_matching.py --
production matching rules, no new logic, no master DB writes. A
read-only, reproducible research artifact -- re-running this script
regenerates the same report against the same committed inputs; it
never writes to data/master/ and is never imported by any numbered
pipeline stage.

Also investigates the single most significant unmatched case found by
the first audit pass (Travis Hunter) directly against the RAW WEEKLY
nflverse source, to distinguish "genuinely absent from nflverse" from
"lost during 03_download_stats.py's aggregation" -- see the Travis
Hunter section below and docs/ADP_SOURCE_MATRIX.md's audit entry for
the full writeup.

Post-review resolution applied here (2026-07, explicit human review):
  - APPROVED (added to data/manual/player_name_overrides.csv, a real
    production data change, separate commit from this script):
    Chigoziem/Chig Okonkwo, Kenneth/Kenny Gainwell, Joshua/Josh Palmer
    -- all three confirmed as real nickname variants of the same
    player via nflverse's players.csv reference (unambiguous gsis_id).
  - REJECTED (Amari Cooper -> "Darius Cooper", fuzzy score 80.0, exactly
    the review floor): the real Amari Cooper has NO 2025 nflverse stats
    row at all (confirmed directly below) -- this is a spurious
    coincidental name match, not a real identity. No override exists
    for this pairing and none should be added; this script explicitly
    reclassifies the row to reflect that rejection when reporting final
    counts, WITHOUT modifying player_matching.py's own matching logic
    (the unmodified algorithm will keep proposing this same low-
    confidence match on every future run -- a real, disclosed
    limitation of not having a negative-override mechanism, not
    something this script or player_matching.py silently papers over).
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from player_matching import match_players  # noqa: E402  (existing, unmodified production module)
from mfl_2025_adp_correction import build_mfl_2025_adp_and_sensitivity, load_calibration  # noqa: E402

# Explicit, documented rejection -- see module docstring. Not a
# player_matching.py change; a reporting-level correction applied only
# by this audit script.
REJECTED_MATCHES = {
    ("Amari Cooper", "WR"): "Darius Cooper -- real Amari Cooper has zero 2025 nflverse stats rows; spurious fuzzy match at the review floor (80.0)",
}


def _mfl_name_to_first_last(name: str) -> str:
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def build_2025_adp_candidates() -> pd.DataFrame:
    mfl_raw = pd.read_csv(REPO_ROOT / "research/diagnostics/mfl_pipeline/output/adp_all_non_keeper.csv")
    mfl_raw = mfl_raw[mfl_raw["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    mfl_raw["player_name_original"] = mfl_raw["name"].apply(_mfl_name_to_first_last)
    mfl_raw["player_id"] = mfl_raw["player"].astype(str)
    mfl_raw["player_name"] = mfl_raw["player_name_original"]
    mfl_raw["mfl_mean_adp"] = mfl_raw["mean_adp"]

    calibration = load_calibration(str(REPO_ROOT / "data/manual/mfl_2025_qb_te_adp_correction_calibration.csv"))
    built = build_mfl_2025_adp_and_sensitivity(
        mfl_raw[["player_id", "player_name", "position", "mfl_mean_adp"]], calibration=calibration,
    )
    built["season"] = 2025
    built["player_name_original"] = mfl_raw["player_name_original"].values
    built["n_drafts"] = mfl_raw["n_drafts"].values
    return built.rename(columns={"overall_adp": "adp"})[
        ["season", "position", "player_name_original", "adp", "overall_adp_mfl_raw",
         "mfl_2025_sensitivity_market_rank", "adp_source", "n_drafts"]
    ]


def flag_row(r):
    """Verbatim from scripts/04_build_master_dataset.py -- not
    reimplemented, kept identical so this audit reports what the real
    pipeline would actually produce."""
    if pd.isna(r["adp"]):
        return "no_adp_match"
    if r.get("match_type") in ("fuzzy_low_confidence", "exact_name_position_mismatch"):
        return "matched_needs_review"
    return "matched_clean"


def run_audit():
    adp_df = build_2025_adp_candidates()
    results = pd.read_csv(REPO_ROOT / "data/raw/nflverse/season_results_ppr_2006_2025.csv")

    matched_df, missing_df, low_confidence_df, duplicates_df, out_of_scope_df = match_players(adp_df, results)
    matched_df["data_quality_flag"] = matched_df.apply(flag_row, axis=1)

    # Apply the explicit, documented post-review rejection (reporting
    # level only -- see REJECTED_MATCHES above).
    for (name, pos), reason in REJECTED_MATCHES.items():
        mask = (matched_df["player_name_original"] == name) & (matched_df["position"] == pos)
        if mask.any():
            matched_df.loc[mask, "data_quality_flag"] = "no_adp_match_rejected"

    return adp_df, matched_df, missing_df, low_confidence_df, duplicates_df


def verify_sensitivity_field_inert(adp_df, results):
    """Mechanical re-confirmation: matching result must be identical
    whether or not the sensitivity-rank column is present."""
    with_field = match_players(adp_df, results)[0]
    without_field = match_players(adp_df.drop(columns=["mfl_2025_sensitivity_market_rank"]), results)[0]
    return with_field.drop(columns=["mfl_2025_sensitivity_market_rank"]).reset_index(drop=True).equals(
        without_field.reset_index(drop=True)
    )


def investigate_travis_hunter():
    """Checks the RAW WEEKLY nflverse source directly (not the
    aggregated season_results table) to determine whether Travis
    Hunter's real 2025 offensive production exists upstream or is
    genuinely absent. Also checks other 2025 players tagged with a
    non-skill position who nonetheless have real offensive
    involvement, to see if the same root cause affects anyone else at
    a comparable scale."""
    players_ref = pd.read_csv(REPO_ROOT / "data/raw/nflverse/reference/players.csv", low_memory=False)
    hunter_ref = players_ref[players_ref["display_name"] == "Travis Hunter"]

    weekly = pd.read_csv(REPO_ROOT / "data/raw/nflverse/annual/stats_player_week_2025.csv", low_memory=False)
    hunter_weekly = weekly[weekly["player_id"].isin(hunter_ref["gsis_id"])] if len(hunter_ref) else weekly.iloc[0:0]

    # Systematic check: any OTHER non-skill-tagged 2025 player with
    # real offensive involvement, at a comparable or greater scale.
    skill = {"QB", "RB", "WR", "TE"}
    non_skill = weekly[~weekly["position"].isin(skill)].copy()
    non_skill["involvement"] = non_skill[["attempts", "carries", "targets"]].fillna(0).sum(axis=1)
    meaningful = non_skill[(non_skill["involvement"] > 0) | (non_skill["fantasy_points_ppr"].fillna(0) != 0)]
    other_cases = (
        meaningful.groupby(["player_id", "player_display_name", "position"])
        .agg(weeks=("week", "nunique"), total_fpts=("fantasy_points_ppr", "sum"), total_touches=("involvement", "sum"))
        .reset_index()
        .sort_values("total_fpts", ascending=False)
    )
    return hunter_ref, hunter_weekly, other_cases


if __name__ == "__main__":
    adp_df, matched_df, missing_df, low_confidence_df, duplicates_df = run_audit()
    results = pd.read_csv(REPO_ROOT / "data/raw/nflverse/season_results_ppr_2006_2025.csv")

    print("=== Final post-review counts ===")
    print(matched_df["data_quality_flag"].value_counts())
    print(f"no_adp_match (never matched at all): {len(missing_df)}")

    print("\n=== Sensitivity field inertness re-confirmed ===")
    print(verify_sensitivity_field_inert(adp_df, results))

    print("\n=== Travis Hunter investigation ===")
    hunter_ref, hunter_weekly, other_cases = investigate_travis_hunter()
    print(hunter_ref[["gsis_id", "display_name", "position", "position_group", "latest_team"]].to_string(index=False))
    print(f"real weekly rows found: {len(hunter_weekly)}")
    print(hunter_weekly[["week", "position", "receptions", "targets", "receiving_yards", "fantasy_points_ppr"]].to_string(index=False))
    print("\nother non-skill-tagged 2025 players with real offensive involvement (top 10 by fantasy points):")
    print(other_cases.head(10).to_string(index=False))
