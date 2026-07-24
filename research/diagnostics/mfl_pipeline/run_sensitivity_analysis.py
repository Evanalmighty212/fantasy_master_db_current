"""
run_sensitivity_analysis.py  (ISOLATED DIAGNOSTIC)

Builds the MFL clean-1QB ADP estimate under several named, explicit
variants and compares each against the real ESPN 2025 ADP benchmark
already collected in research/benchmarks/espn_championship_rosters/.
Replaces the earlier reconstruct_adp.py / compare_to_espn.py, which
picked a single "winning" provenance filter -- on review, that
overstated confidence about which picks are and aren't real market
data (a commissioner-entered pick can be a genuine offline draft; an
imported pick can be real human selections from another platform).
This script reports several defensible variants side by side instead
of choosing one as ground truth.

PRIMARY estimate: all configuration-VALID clean-1QB leagues (all 254
that passed classify_leagues.py), all non-keeper picks. Leagues are
NOT excluded here for how they drafted (e.g. early-QB behavior) --
their verified starting-lineup configuration is genuinely 1-QB, and
excluding them because their behavior "looks wrong" would circularly
force MFL to resemble ESPN rather than measure MFL's actual market.

PROVENANCE variants (see fetch_drafts.py for the category
definitions), all still drawn from the full 254-league set:
  - all_non_keeper: every picked player except keeper-tagged picks
    (the PRIMARY estimate)
  - native_live_only: only picks with no annotation at all (the
    strongest single signal of a real-time human pick, but not
    proof every unannotated pick is human, and not proof every
    annotated one isn't)
  - native_live_plus_commissioner_imported: native-live picks plus
    commissioner-entered and externally-imported picks (both
    genuinely ambiguous, not excluded by default per the corrected
    interpretation)
  - auto_default_rank_only: ONLY MFL's own automated default-rank
    picks -- reported on its own specifically because this is known
    NOT to reflect a human market decision at all; useful as a
    reference for "what does the algorithm alone produce," not
    blended into any other variant.

SENSITIVITY-ONLY variant (reported separately, never as the primary
estimate): all_non_keeper_excluding_early_qb_leagues -- the 43
leagues flagged for 2+ QBs drafted in the first 12 overall picks,
removed entirely. Their configuration is genuinely 1-QB; this variant
exists only to show how much the estimate moves if that specific
behavioral pattern is excluded, not because those leagues are known
to be misconfigured.

Output (per variant): research/diagnostics/mfl_pipeline/output/adp_<variant>.csv
                       research/diagnostics/mfl_pipeline/output/espn_comparison_<variant>.csv
Output (combined):     research/diagnostics/mfl_pipeline/output/sensitivity_summary.csv
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
ESPN_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "research" / "benchmarks" / "espn_championship_rosters" / "championship_roster_players.csv"
)

EARLY_QB_LEAGUE_THRESHOLD = 2  # leagues with >= this many QBs in the first 12 picks, flagged for the sensitivity variant only


def normalize_name(s: str) -> str:
    return re.sub(r"[.']", "", str(s)).lower().strip()


def mfl_name_to_normalized(s: str) -> str:
    if isinstance(s, str) and "," in s:
        s = " ".join(reversed([p.strip() for p in s.split(",", 1)]))
    return normalize_name(s)


def load_picks_with_positions() -> pd.DataFrame:
    picks = pd.read_csv(OUTPUT_DIR / "draft_picks_in_window.csv", dtype={"player": str})
    players = pd.read_csv(OUTPUT_DIR / "all_players.csv", dtype={"id": str})
    merged = picks.merge(players[["id", "name", "position", "team"]], left_on="player", right_on="id", how="left")
    return merged.dropna(subset=["name"])


def find_early_qb_leagues(picks: pd.DataFrame) -> set:
    qb_picks = picks[picks["position"] == "QB"]
    counts = qb_picks[qb_picks["overall_pick"] <= 12].groupby("league_id").size()
    return set(counts[counts >= EARLY_QB_LEAGUE_THRESHOLD].index)


def build_variant(picks: pd.DataFrame, provenance_filter, exclude_leagues=None) -> pd.DataFrame:
    df = picks[picks["provenance"] != "keeper"].copy()  # keeper always excluded, every variant
    if provenance_filter is not None:
        df = df[df["provenance"].isin(provenance_filter)]
    if exclude_leagues:
        df = df[~df["league_id"].isin(exclude_leagues)]
    return df


def reconstruct_adp(picks: pd.DataFrame) -> pd.DataFrame:
    return (
        picks.groupby(["player", "name", "position", "team"])["overall_pick"]
        .agg(mean_adp="mean", median_adp="median", n_drafts="count")
        .reset_index()
        .sort_values("mean_adp")
    )


def compare_to_espn(adp: pd.DataFrame, espn: pd.DataFrame) -> pd.DataFrame:
    adp = adp.copy()
    adp["player_norm"] = adp["name"].apply(mfl_name_to_normalized)
    merged = espn.merge(adp, on="player_norm", how="inner")
    merged["abs_diff"] = (merged["adp_overall"] - merged["mean_adp"]).abs()
    merged["signed_diff"] = merged["mean_adp"] - merged["adp_overall"]
    return merged


def summarize_comparison(merged: pd.DataFrame, variant_name: str) -> list:
    rows = []
    pos_col = "position_x" if "position_x" in merged.columns else "position"
    for pos in ["QB", "RB", "WR", "TE", None]:
        sub = merged if pos is None else merged[merged[pos_col] == pos]
        if len(sub) < 2:
            continue
        rows.append({
            "variant": variant_name, "position": pos or "ALL",
            "n": len(sub),
            "pearson_r": sub["adp_overall"].corr(sub["mean_adp"]),
            "median_abs_diff": sub["abs_diff"].median(),
            "mean_signed_diff_mfl_minus_espn": sub["signed_diff"].mean(),
            "max_abs_diff": sub["abs_diff"].max(),
        })
    return rows


def main():
    picks = load_picks_with_positions()
    espn = pd.read_csv(ESPN_PATH)
    espn = espn[(espn["season"] == 2025) & (espn["position"].isin(["QB", "RB", "WR", "TE"]))].copy()
    espn = espn[espn["adp_overall"].notna()]
    espn["player_norm"] = espn["player_name"].apply(normalize_name)

    early_qb_leagues = find_early_qb_leagues(picks)
    print(f"Leagues flagged for early-QB behavior (>={EARLY_QB_LEAGUE_THRESHOLD} QBs in first 12 picks, "
          f"SENSITIVITY-ONLY exclusion, not applied to the primary estimate): {len(early_qb_leagues)}")

    variants = {
        "all_non_keeper": (None, None),
        "native_live_only": ({"native_live_selection"}, None),
        "native_live_plus_commissioner_imported": (
            {"native_live_selection", "commissioner_entered", "externally_imported"}, None
        ),
        "auto_default_rank_only": ({"automated_default_rank"}, None),
        "SENSITIVITY_all_non_keeper_excluding_early_qb_leagues": (None, early_qb_leagues),
    }

    all_summary_rows = []
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for variant_name, (prov_filter, exclude_leagues) in variants.items():
        df = build_variant(picks, prov_filter, exclude_leagues)
        adp = reconstruct_adp(df)
        adp.to_csv(OUTPUT_DIR / f"adp_{variant_name}.csv", index=False)

        merged = compare_to_espn(adp, espn)
        merged.to_csv(OUTPUT_DIR / f"espn_comparison_{variant_name}.csv", index=False)

        rows = summarize_comparison(merged, variant_name)
        all_summary_rows.extend(rows)

        print(f"\n=== {variant_name} ===")
        print(f"  picks={len(df)}, leagues={df['league_id'].nunique()}, unique_players={len(adp)}")
        for r in rows:
            print(f"  {r['position']:>3s}: n={r['n']:3d}  r={r['pearson_r']:.3f}  "
                  f"median_abs_diff={r['median_abs_diff']:6.2f}  "
                  f"mean_signed_diff={r['mean_signed_diff_mfl_minus_espn']:+7.2f}  "
                  f"max_abs_diff={r['max_abs_diff']:6.2f}")

    summary_df = pd.DataFrame(all_summary_rows)
    summary_df.to_csv(OUTPUT_DIR / "sensitivity_summary.csv", index=False)
    print(f"\nWrote {OUTPUT_DIR / 'sensitivity_summary.csv'}")


if __name__ == "__main__":
    main()
