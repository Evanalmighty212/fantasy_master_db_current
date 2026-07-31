"""
research/dataset2/overlap_floor_clustering_sensitivity_2026_07.py

Read-only, one-off DESCRIPTIVE sensitivity sweep -- re-runs
research/dataset2/trait_analysis_pipeline_predictor_inventory.py's own
OUTCOME-FREE build_predictor_clusters() three times, varying only
MIN_OVERLAP_N (the minimum number of jointly-non-null real player-
season rows two predictors must share before their pairwise
similarity is even used as a clustering edge -- currently 50 in the
committed script) at 30/50/100, per instruction. Never edits the
committed script (monkeypatches the already-imported module's global
for each run instead) and never touches any outcome/target column --
same OUTCOME-FREE inputs (`real`, `inv`) the committed script itself
uses.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

import pandas as pd
import trait_analysis_pipeline_predictor_inventory as tapi


def _load_real_and_inv():
    real = tapi.load_real_rows()
    whitelist = pd.read_csv(tapi.WHITELIST_PATH)["predictor_column"].tolist()
    registry = pd.read_csv(tapi.COLUMN_REGISTRY_PATH)
    inv = tapi.build_inventory(real, whitelist, registry)
    inv = tapi.add_position_scoped_applicable_n(inv, real)
    inv = tapi.add_single_season_concentration(inv, real)
    return real, inv


def _summarize(clusters, audit_rows):
    real_clusters = {cid: v for cid, v in clusters.items() if cid != -1}
    sizes = sorted((len(v["content"]) for v in real_clusters.values()), reverse=True)
    return {
        "final_cluster_count": len(real_clusters),
        "singletons": sum(1 for s in sizes if s == 1),
        "size_2_5": sum(1 for s in sizes if 2 <= s <= 5),
        "size_6_10": sum(1 for s in sizes if 6 <= s <= 10),
        "over_10": sum(1 for s in sizes if s > 10),
        "largest_cluster": max(sizes) if sizes else 0,
    }


def _membership_signature(clusters):
    """frozenset of frozensets -- content-only, ignores cluster id
    numbering (which is an artifact of iteration order, not a real
    difference) so two runs with the SAME groupings but different ids
    compare as identical."""
    return frozenset(frozenset(v["content"]) for cid, v in clusters.items() if cid != -1 and v["content"])


def main():
    real, inv = _load_real_and_inv()
    print(f"Real population: {len(real)} rows, {len(inv)} whitelist columns in inventory.\n")

    results = {}
    memberships = {}
    for floor in (30, 50, 100):
        tapi.MIN_OVERLAP_N = floor
        clusters, audit_rows, stats = tapi.build_predictor_clusters(real, inv)
        summary = _summarize(clusters, audit_rows)
        results[floor] = summary
        memberships[floor] = _membership_signature(clusters)
        print(f"=== MIN_OVERLAP_N = {floor} ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        for k, v in summary.items():
            print(f"  {k}: {v}")
        print()

    print("=== Comparison table ===")
    df = pd.DataFrame(results).T
    df.index.name = "MIN_OVERLAP_N"
    print(df.to_string())

    print("\n=== Membership stability (baseline = 50, the committed script's real value) ===")
    baseline = memberships[50]
    for floor in (30, 100):
        same = memberships[floor] == baseline
        only_in_floor = memberships[floor] - baseline
        only_in_baseline = baseline - memberships[floor]
        print(f"\nMIN_OVERLAP_N={floor} vs. 50: identical cluster membership = {same}")
        if not same:
            print(f"  clusters present at {floor} but not at 50: {len(only_in_floor)}")
            for c in sorted(only_in_floor, key=lambda s: -len(s))[:5]:
                print(f"    {sorted(c)}")
            print(f"  clusters present at 50 but not at {floor}: {len(only_in_baseline)}")
            for c in sorted(only_in_baseline, key=lambda s: -len(s))[:5]:
                print(f"    {sorted(c)}")


if __name__ == "__main__":
    main()
