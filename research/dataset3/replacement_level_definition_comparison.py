"""
replacement_level_definition_comparison.py
(Dataset 3 research foundation -- EXPLORATORY ONLY)

Compares reasonable roster-based, flex-aware replacement-level
definitions -- per the decision to drop waiver-wire approaches
entirely and focus on this family, in service of the "last plausible
starter in a typical 12-team league" philosophy. Does NOT select or
implement a final definition, and does NOT touch config.py or any
production file -- LWI's own QB12/RB34/WR42/TE12 thresholds are read
here only as a comparison point, never modified.

Four candidate definitions, same population and methodology
(position_finish_ppr rank within season, median over a 12-rank window
-- matching config.py's LWI_REPLACEMENT_WINDOW exactly, so every
comparison below isolates the cutoff choice itself, not a methodology
difference):

  A. current_lwi        -- QB12/RB34/WR42/TE12, config.py's real,
                            confirmed production thresholds.
  B. literal_starters    -- 12-team roster, 1 QB/2 RB/2 WR/1 TE, ZERO
                            flex credit. The strictest "last mandatory
                            starter" reading -- a floor, not a proposal.
  C. flex_even           -- same roster, flex slot split evenly across
                            RB/WR/TE (1/3 each). lib/replacement.py's
                            FLEX_ALLOCATION_EVEN preset.
  D. flex_rb_wr_heavy    -- same roster, flex split 45% RB / 45% WR /
                            10% TE (real flex usage skews toward
                            RB/WR). lib/replacement.py's
                            FLEX_ALLOCATION_RB_WR_HEAVY preset.

Population: QB/RB/WR/TE player-seasons with games_played >= 1,
2007-2024 (18 seasons) -- matching the scope already established for
the expected-production-by-round work, even though replacement level
itself doesn't strictly require excluding 2006/2025 (it's rank-based
within season, not ADP-dependent). Kept in sync deliberately so this
and the round-based work describe the same population when eventually
combined.

Output: research/output/dataset3/replacement_cutoffs_by_definition.csv
        research/output/dataset3/replacement_level_by_definition.csv
        research/output/dataset3/points_above_replacement_by_definition.csv
        research/output/dataset3/replacement_definition_agreement.csv
        research/output/dataset3/replacement_definition_top25_movers.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.replacement import (
    ROSTER_PRESETS, FLEX_ALLOCATION_NONE, FLEX_ALLOCATION_EVEN, FLEX_ALLOCATION_RB_WR_HEAVY,
    replacement_rank_cutoff, replacement_level_from_rank,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config

OUTPUT_DIR = Path("research/output/dataset3")
BROAD_DATASET_PATH = OUTPUT_DIR / "broad_historical_dataset.csv"
VALUE_COL = "fantasy_points_ppr"
RANK_COL = "position_finish_ppr"
WINDOW = config.LWI_REPLACEMENT_WINDOW  # 12 -- reused, not redefined
POSITIONS = ["QB", "RB", "WR", "TE"]
SEASON_MIN, SEASON_MAX = 2007, 2024
TOP_N = 25
PRESET = ROSTER_PRESETS["12_team_standard"]


def build_cutoffs() -> dict:
    flex_derived = {
        "literal_starters": FLEX_ALLOCATION_NONE,
        "flex_even": FLEX_ALLOCATION_EVEN,
        "flex_rb_wr_heavy": FLEX_ALLOCATION_RB_WR_HEAVY,
    }
    cutoffs = {"current_lwi": dict(config.LWI_REPLACEMENT_RANK_THRESHOLDS)}
    for name, alloc in flex_derived.items():
        cutoffs[name] = {pos: replacement_rank_cutoff(PRESET, pos, alloc) for pos in POSITIONS}
    return cutoffs


def load_population() -> pd.DataFrame:
    df = pd.read_csv(BROAD_DATASET_PATH)
    df = df[
        (df["games_played"] >= 1)
        & (df["position"].isin(POSITIONS))
        & (df["season"].between(SEASON_MIN, SEASON_MAX))
    ].copy()
    return df


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_population()
    print(f"Population: {len(df)} QB/RB/WR/TE player-seasons, {SEASON_MIN}-{SEASON_MAX}, games_played>=1")

    cutoffs = build_cutoffs()
    cutoff_rows = [{"definition": name, **vals} for name, vals in cutoffs.items()]
    cutoff_df = pd.DataFrame(cutoff_rows)
    cutoff_df.to_csv(OUTPUT_DIR / "replacement_cutoffs_by_definition.csv", index=False)
    print("\n=== 1. Replacement rank cutoffs by definition ===")
    print(cutoff_df.to_string(index=False))

    level_rows = []
    par_frames = {}
    for name, cutoff_by_position in cutoffs.items():
        replacement_points = replacement_level_from_rank(
            df, value_col=VALUE_COL, rank_col=RANK_COL,
            cutoff_by_position=cutoff_by_position, window=WINDOW,
        )
        d = df.copy()
        d["replacement_points"] = replacement_points
        d["points_above_replacement"] = d[VALUE_COL] - d["replacement_points"]
        d["definition"] = name
        par_frames[name] = d

        avg_level = d.groupby("position")["replacement_points"].mean()
        for pos in POSITIONS:
            level_rows.append({"definition": name, "position": pos,
                                "avg_replacement_points_ppr": avg_level.get(pos, np.nan)})

    level_df = pd.DataFrame(level_rows)
    level_df.to_csv(OUTPUT_DIR / "replacement_level_by_definition.csv", index=False)
    print("\n=== 2. Average replacement-level fantasy_points_ppr by position (across 18 seasons) ===")
    print(level_df.pivot(index="position", columns="definition", values="avg_replacement_points_ppr").round(1).to_string())

    all_par = pd.concat(par_frames.values(), ignore_index=True)
    all_par.to_csv(OUTPUT_DIR / "points_above_replacement_by_definition.csv", index=False)

    print("\n=== 3. Agreement between definitions (rank correlation + top-N overlap) ===")
    names = list(cutoffs.keys())
    id_cols = ["season", "player_id"]
    wide = par_frames[names[0]][id_cols + ["position"]].copy()
    for name in names:
        wide = wide.merge(
            par_frames[name][id_cols + ["points_above_replacement"]].rename(
                columns={"points_above_replacement": f"par_{name}"}
            ), on=id_cols,
        )

    agreement_rows = []
    baseline = "current_lwi"
    for name in names:
        if name == baseline:
            continue
        spearman_r = wide[f"par_{baseline}"].corr(wide[f"par_{name}"], method="spearman")
        top_baseline = set(wide.nlargest(TOP_N, f"par_{baseline}")[id_cols].apply(tuple, axis=1))
        top_other = set(wide.nlargest(TOP_N, f"par_{name}")[id_cols].apply(tuple, axis=1))
        overlap = len(top_baseline & top_other)
        agreement_rows.append({
            "compared_to": baseline, "definition": name,
            "spearman_r_full_population": spearman_r,
            f"top_{TOP_N}_overlap": f"{overlap}/{TOP_N}",
        })
    agreement_df = pd.DataFrame(agreement_rows)
    agreement_df.to_csv(OUTPUT_DIR / "replacement_definition_agreement.csv", index=False)
    print(agreement_df.to_string(index=False))

    print(f"\n=== 4. Concrete movers: in current_lwi's top {TOP_N} but NOT in flex_rb_wr_heavy's (or vice versa) ===")
    top_current = wide.nlargest(TOP_N, "par_current_lwi").copy()
    top_heavy = wide.nlargest(TOP_N, "par_flex_rb_wr_heavy").copy()
    dropped_out = top_current[~top_current[id_cols].apply(tuple, axis=1).isin(
        set(top_heavy[id_cols].apply(tuple, axis=1)))]
    newly_in = top_heavy[~top_heavy[id_cols].apply(tuple, axis=1).isin(
        set(top_current[id_cols].apply(tuple, axis=1)))]
    names_df = df[["season", "player_id", "player_name", "position"]].drop_duplicates()
    dropped_out = dropped_out.drop(columns=["position"]).merge(names_df, on=id_cols)
    newly_in = newly_in.drop(columns=["position"]).merge(names_df, on=id_cols)
    movers = pd.concat([
        dropped_out.assign(status="in current_lwi top25, drops out under flex_rb_wr_heavy"),
        newly_in.assign(status="not in current_lwi top25, enters under flex_rb_wr_heavy"),
    ], ignore_index=True)
    movers.to_csv(OUTPUT_DIR / "replacement_definition_top25_movers.csv", index=False)
    print(movers[["season", "player_name", "position", "status", "par_current_lwi", "par_flex_rb_wr_heavy"]]
          .round(1).to_string(index=False))

    print(f"\nWrote 5 CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
