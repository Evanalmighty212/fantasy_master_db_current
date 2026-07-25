"""
replacement_flex_allocation_sensitivity.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Final check before selecting flex_rb_wr_heavy (45% RB / 45% WR / 10%
TE) as the provisional replacement-level definition. Does NOT select
or implement anything -- tests whether the conclusions drawn from that
one specific split hold up across a reasonable NEIGHBORHOOD of nearby,
equally-plausible FLEX allocations, per the explicit instruction not
to search for a mathematically perfect split, only to check
robustness. Same population and methodology as
replacement_level_definition_comparison.py (position_finish_ppr rank,
12-rank window median, 2007-2024, games_played>=1) -- only the FLEX
allocation varies here, so every difference below is attributable to
that one assumption.

Four allocations, two axes of variation, each held independent:
  - RB/WR balance (TE fixed at 10%): 40/50/10, 45/45/10 (baseline),
    50/40/10.
  - TE share alone (RB/WR held symmetric): 47.5/47.5/5 -- isolates
    whether TE's share specifically is doing any real work, separate
    from the RB-vs-WR balance question.

Output: research/output/dataset3/flex_sensitivity_cutoffs.csv
        research/output/dataset3/flex_sensitivity_par.csv
        research/output/dataset3/flex_sensitivity_agreement.csv
        research/output/dataset3/flex_sensitivity_position_composition.csv
        research/output/dataset3/flex_sensitivity_by_season.csv
        research/output/dataset3/flex_sensitivity_named_players.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.replacement import ROSTER_PRESETS, replacement_rank_cutoff, replacement_level_from_rank

OUTPUT_DIR = Path("research/output/dataset3")
BROAD_DATASET_PATH = OUTPUT_DIR / "broad_historical_dataset.csv"
VALUE_COL = "fantasy_points_ppr"
RANK_COL = "position_finish_ppr"
WINDOW = 12  # matches config.py's LWI_REPLACEMENT_WINDOW, reused for methodology consistency
POSITIONS = ["QB", "RB", "WR", "TE"]
SEASON_MIN, SEASON_MAX = 2007, 2024
PRESET = ROSTER_PRESETS["12_team_standard"]
BASELINE = "45_45_10"

ALLOCATIONS = {
    "40_50_10": {"RB": 0.40, "WR": 0.50, "TE": 0.10},
    "45_45_10": {"RB": 0.45, "WR": 0.45, "TE": 0.10},  # flex_rb_wr_heavy, the provisional leading candidate
    "50_40_10": {"RB": 0.50, "WR": 0.40, "TE": 0.10},
    "47.5_47.5_5": {"RB": 0.475, "WR": 0.475, "TE": 0.05},
}

NAMED_PLAYERS = [
    (2024, "Ja'Marr Chase"), (2023, "CeeDee Lamb"), (2015, "Antonio Brown"),
    (2007, "Tom Brady"), (2014, "DeMarco Murray"), (2014, "Matt Forte"),
]


def load_population() -> pd.DataFrame:
    df = pd.read_csv(BROAD_DATASET_PATH)
    return df[
        (df["games_played"] >= 1)
        & (df["position"].isin(POSITIONS))
        & (df["season"].between(SEASON_MIN, SEASON_MAX))
    ].copy()


def main():
    df = load_population()
    print(f"Population: {len(df)} QB/RB/WR/TE player-seasons, {SEASON_MIN}-{SEASON_MAX}")

    cutoff_rows = []
    par_frames = {}
    for name, alloc in ALLOCATIONS.items():
        cutoff_by_position = {pos: replacement_rank_cutoff(PRESET, pos, alloc) for pos in POSITIONS}
        cutoff_rows.append({"allocation": name, **cutoff_by_position})

        replacement_points = replacement_level_from_rank(
            df, value_col=VALUE_COL, rank_col=RANK_COL,
            cutoff_by_position=cutoff_by_position, window=WINDOW,
        )
        d = df.copy()
        d["replacement_points"] = replacement_points
        d["points_above_replacement"] = d[VALUE_COL] - d["replacement_points"]
        d["allocation"] = name
        par_frames[name] = d

    cutoff_df = pd.DataFrame(cutoff_rows)
    cutoff_df.to_csv(OUTPUT_DIR / "flex_sensitivity_cutoffs.csv", index=False)
    print("\n=== 1. Replacement rank cutoffs across the neighborhood ===")
    print(cutoff_df.to_string(index=False))

    all_par = pd.concat(par_frames.values(), ignore_index=True)
    all_par.to_csv(OUTPUT_DIR / "flex_sensitivity_par.csv", index=False)

    id_cols = ["season", "player_id"]
    wide = par_frames[BASELINE][id_cols + ["position", "player_name"]].copy()
    for name in ALLOCATIONS:
        wide = wide.merge(
            par_frames[name][id_cols + ["points_above_replacement"]].rename(
                columns={"points_above_replacement": f"par_{name}"}
            ), on=id_cols,
        )

    print(f"\n=== 2a. Agreement vs. baseline ({BASELINE}) -- full population, top-25, top-100 ===")
    agreement_rows = []
    for name in ALLOCATIONS:
        if name == BASELINE:
            continue
        spearman_r = wide[f"par_{BASELINE}"].corr(wide[f"par_{name}"], method="spearman")
        top25_base = set(wide.nlargest(25, f"par_{BASELINE}")[id_cols].apply(tuple, axis=1))
        top25_alt = set(wide.nlargest(25, f"par_{name}")[id_cols].apply(tuple, axis=1))
        top100_base = set(wide.nlargest(100, f"par_{BASELINE}")[id_cols].apply(tuple, axis=1))
        top100_alt = set(wide.nlargest(100, f"par_{name}")[id_cols].apply(tuple, axis=1))
        agreement_rows.append({
            "allocation": name,
            "spearman_r_full_population": round(spearman_r, 4),
            "top_25_overlap": f"{len(top25_base & top25_alt)}/25",
            "top_100_overlap": f"{len(top100_base & top100_alt)}/100",
        })
    agreement_df = pd.DataFrame(agreement_rows)
    agreement_df.to_csv(OUTPUT_DIR / "flex_sensitivity_agreement.csv", index=False)
    print(agreement_df.to_string(index=False))

    print("\n=== 2b. Cross-position representation in top-25 / top-100, by allocation ===")
    comp_rows = []
    for name in ALLOCATIONS:
        for n in (25, 100):
            top = wide.nlargest(n, f"par_{name}")
            counts = top["position"].value_counts().reindex(POSITIONS, fill_value=0)
            comp_rows.append({"allocation": name, "top_n": n, **counts.to_dict()})
    comp_df = pd.DataFrame(comp_rows)
    comp_df.to_csv(OUTPUT_DIR / "flex_sensitivity_position_composition.csv", index=False)
    print(comp_df.to_string(index=False))

    print("\n=== 2c. Most sensitive seasons: how much does top-100 representation swing across the neighborhood? ===")
    season_rows = []
    for season in range(SEASON_MIN, SEASON_MAX + 1):
        counts = []
        for name in ALLOCATIONS:
            top100 = wide.nlargest(100, f"par_{name}")
            counts.append((top100["season"] == season).sum())
        season_rows.append({
            "season": season, "min_top100_count": min(counts), "max_top100_count": max(counts),
            "range": max(counts) - min(counts), "counts_by_allocation": dict(zip(ALLOCATIONS.keys(), counts)),
        })
    season_df = pd.DataFrame(season_rows).sort_values("range", ascending=False)
    season_df.to_csv(OUTPUT_DIR / "flex_sensitivity_by_season.csv", index=False)
    print(season_df[["season", "min_top100_count", "max_top100_count", "range"]].to_string(index=False))

    print("\n=== 3. Named players: PAR and top-25/top-100 status across the full neighborhood ===")
    named_rows = []
    for season, player_name in NAMED_PLAYERS:
        row = wide[(wide["season"] == season) & (wide["player_name"] == player_name)]
        if row.empty:
            print(f"  WARNING: {player_name} {season} not found in population -- skipping")
            continue
        row = row.iloc[0]
        out = {"season": season, "player_name": player_name, "position": row["position"]}
        for name in ALLOCATIONS:
            par_val = row[f"par_{name}"]
            rank_in_pop = (wide[f"par_{name}"] > par_val).sum() + 1
            out[f"par_{name}"] = round(par_val, 1)
            out[f"rank_{name}"] = rank_in_pop
        named_rows.append(out)
    named_df = pd.DataFrame(named_rows)
    named_df.to_csv(OUTPUT_DIR / "flex_sensitivity_named_players.csv", index=False)
    print(named_df.to_string(index=False))

    print(f"\nWrote 6 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
