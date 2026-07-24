"""
expected_production_tables.py  (Dataset 3 research foundation, Deliverable 3)

EXPLORATORY ONLY. Descriptive tables of historical fantasy production
cut by ADP slot, ADP round, position, season, and era bucket. Does not
choose, fit, or recommend an expected-production model -- that
decision is explicitly out of scope here (see task instructions).

Restricted to adp_matched == True rows from the broad historical
dataset -- ADP slot/round are undefined for unresolved (no real ADP)
player-seasons, and it would be misleading to bucket a verified-
undrafted player's fixed 194.5 proxy alongside real observed ADP
values as if they were the same kind of measurement.

ADP round uses TEAMS = 12 (config.py's existing convention) --
ceil(overall_adp / 12). ADP slot uses fixed-width-10 bins on overall
ADP for finer granularity than round. Both are just binning choices
for descriptive display, not modeling decisions.

Input:  research/output/dataset3/broad_historical_dataset.csv
Output: research/output/dataset3/expected_production_by_adp_slot.csv
        research/output/dataset3/expected_production_by_adp_round.csv
        research/output/dataset3/expected_production_by_position.csv
        research/output/dataset3/expected_production_by_season.csv
        research/output/dataset3/expected_production_by_era.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.eras import add_era_column

BROAD_DATASET_PATH = Path("research/output/dataset3/broad_historical_dataset.csv")
OUTPUT_DIR = Path("research/output/dataset3")

TEAMS_FOR_ROUND = 12
ADP_SLOT_BIN_WIDTH = 10
PERCENTILES = [0.10, 0.25, 0.50, 0.75, 0.90]


def adp_slot_bin(adp: float, width: int = ADP_SLOT_BIN_WIDTH) -> str:
    if pd.isna(adp):
        return None
    lo = int((adp - 1) // width) * width + 1
    hi = lo + width - 1
    return f"{lo:03d}-{hi:03d}"


def adp_round(adp: float, teams: int = TEAMS_FOR_ROUND) -> int:
    if pd.isna(adp):
        return None
    return int(np.ceil(adp / teams))


def summarize(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    agg_spec = {
        "fantasy_points_ppr": ["count", "mean", "median"] + [
            (f"p{int(p*100)}", lambda s, p=p: s.quantile(p)) for p in PERCENTILES
        ],
        "ppg_ppr": ["mean", "median"] + [
            (f"p{int(p*100)}", lambda s, p=p: s.quantile(p)) for p in PERCENTILES
        ],
    }
    grouped = df.groupby(group_cols)
    out = grouped.agg(agg_spec)
    out.columns = [f"{col}_{stat}" for col, stat in out.columns]
    out = out.rename(columns={"fantasy_points_ppr_count": "n"})
    return out.reset_index()


def load_matched() -> pd.DataFrame:
    df = pd.read_csv(BROAD_DATASET_PATH)
    matched = df[df["adp_matched"]].copy()
    matched["adp_slot"] = matched["overall_adp_observed"].apply(adp_slot_bin)
    matched["adp_round"] = matched["overall_adp_observed"].apply(adp_round)
    matched = add_era_column(matched)
    return matched


def main():
    matched = load_matched()
    print(f"ADP-matched player-seasons available for expected-production tables: {len(matched)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tables = {
        "expected_production_by_adp_slot.csv": summarize(matched, ["position", "adp_slot"]),
        "expected_production_by_adp_round.csv": summarize(matched, ["position", "adp_round"]),
        "expected_production_by_position.csv": summarize(matched, ["position"]),
        "expected_production_by_season.csv": summarize(matched, ["season", "position"]),
        "expected_production_by_era.csv": summarize(matched, ["era", "position"]),
    }

    for filename, table in tables.items():
        path = OUTPUT_DIR / filename
        table.to_csv(path, index=False)
        print(f"\n{filename}: {len(table)} rows -> {path}")

    print("\nSample -- production by ADP round, position=WR:")
    wr_by_round = tables["expected_production_by_adp_round.csv"]
    print(wr_by_round[wr_by_round["position"] == "WR"].to_string(index=False))


if __name__ == "__main__":
    main()
