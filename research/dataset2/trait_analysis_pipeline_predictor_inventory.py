"""
research/dataset2/trait_analysis_pipeline_predictor_inventory.py

Real-data predictor inventory backing
DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md §1. Structural
characterization of the 431-column predictor whitelist ONLY -- no
predictor is ever compared against an outcome/target column here. This
is explicitly NOT outcome testing: it touches only
lib/dataset2/analysis_view.py's already-built, already-committed
outputs (predictor whitelist + column registry) and the predictor
columns' own values, never `star_by_value_label`, `bust_primary_label`,
or any other target/eligibility column.

Restricts to `outcome_join_status == "outcome_matched"` rows (11,175 of
11,784) for sample-size/coverage purposes -- the 609 real
`prediction_season=2026` rows can never inform any outcome-adjacent
statistic and would understate real historical coverage if included.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

VIEW_PATH = "data/exports/dataset2_analysis_view.parquet"
WHITELIST_PATH = "data/exports/dataset2_analysis_view_predictor_whitelist.csv"
COLUMN_REGISTRY_PATH = "data/exports/dataset2_analysis_view_column_registry.csv"

NEAR_DUPLICATE_CORR_THRESHOLD = 0.95
MIN_PERIODS_FOR_CORR = 30

pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 300)


def load_real_rows():
    view = pd.read_parquet(VIEW_PATH)
    return view[view["outcome_join_status"] == "outcome_matched"].copy()


def build_inventory(real: pd.DataFrame, whitelist: list, registry: pd.DataFrame) -> pd.DataFrame:
    registry_idx = registry.set_index("canonical_column")
    rows = []
    for col in whitelist:
        s = real[col]
        dtype = str(s.dtype)
        n_nonnull = int(s.notna().sum())
        n_unique = int(s.dropna().nunique())
        var_type = "boolean" if dtype == "boolean" else ("continuous" if dtype in ("float64", "Float64", "int64", "Int64") else "categorical/status")
        seasons_present = sorted(real.loc[s.notna(), "prediction_season"].unique().tolist())
        pos_scope = registry_idx.loc[col, "position_scope"] if col in registry_idx.index else None
        family = registry_idx.loc[col, "family_number"] if col in registry_idx.index else None
        missingness = registry_idx.loc[col, "missingness_semantics"] if col in registry_idx.index else None
        rows.append(
            {
                "column": col,
                "family": family,
                "var_type": var_type,
                "dtype": dtype,
                "position_scope": pos_scope,
                "n_nonnull_overall": n_nonnull,
                "pct_nonnull_overall": round(n_nonnull / len(real) * 100, 1),
                "n_unique": n_unique,
                "season_min": min(seasons_present) if seasons_present else None,
                "season_max": max(seasons_present) if seasons_present else None,
                "n_seasons_present": len(seasons_present),
                "missingness_semantics": missingness,
            }
        )
    return pd.DataFrame(rows)


def add_single_season_concentration(inv: pd.DataFrame, real: pd.DataFrame) -> pd.DataFrame:
    """Outcome-free: what fraction of a trait's own non-null values sit
    in its single most-populated real prediction_season. High
    concentration flags a trait whose apparent signal could really be
    one anomalous season, independent of any outcome."""
    inv = inv.copy()
    max_season_share = []
    for col in inv["column"]:
        present = real.loc[real[col].notna(), "prediction_season"]
        if len(present) == 0:
            max_season_share.append(None)
            continue
        max_season_share.append(round(float(present.value_counts(normalize=True).max()), 3))
    inv["max_single_season_share"] = max_season_share
    return inv


def add_position_scoped_applicable_n(inv: pd.DataFrame, real: pd.DataFrame) -> pd.DataFrame:
    """pct_nonnull_overall understates coverage for position-locked
    traits (e.g. a QB-only trait is ~100% populated among QBs but looks
    like ~10% against the full cross-position population). Adds the
    real, position-scoped applicable sample size."""
    inv = inv.copy()
    applicable_n = []
    for _, row in inv.iterrows():
        col, scope = row["column"], row["position_scope"]
        pop = real if scope in (None, "ALL") else real[real["position"] == scope]
        applicable_n.append(int(real[col].notna().sum()) if len(pop) == 0 else int(pop[col].notna().sum()))
    inv["applicable_n_within_position_scope"] = applicable_n
    inv["applicable_pop_size"] = inv["position_scope"].apply(
        lambda s: len(real) if s in (None, "ALL") else int((real["position"] == s).sum())
    )
    inv["pct_nonnull_within_scope"] = (inv["applicable_n_within_position_scope"] / inv["applicable_pop_size"] * 100).round(1)
    return inv


def find_near_duplicate_pairs(real: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
    cont_cols = inv[(inv["var_type"] == "continuous") & (inv["n_unique"] > 2)]["column"].tolist()
    X = real[cont_cols].astype(float)
    corr = X.corr(method="pearson", min_periods=MIN_PERIODS_FOR_CORR)
    pairs = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if pd.notna(r) and abs(r) >= NEAR_DUPLICATE_CORR_THRESHOLD:
                pairs.append((cols[i], cols[j], round(float(r), 4)))
    return pd.DataFrame(pairs, columns=["col_a", "col_b", "pearson_r"]).sort_values("pearson_r", key=abs, ascending=False)


BOOLEAN_AGREEMENT_THRESHOLD = 0.95
BOOLEAN_AGREEMENT_MIN_JOINT_N = 30
# role_present / meaningful_role / strong_lead_role: progressively
# stricter thresholds on the SAME underlying continuous share/rate,
# per this project's own documented three-tier framework
# (partial_season_traits.py) -- a KNOWN construction relationship, not
# a statistically inferred one.
TIER_SUFFIXES = ("_role_present", "_meaningful_role", "_strong_lead_role")
# Same position+metric across trailing-window variants -- known by
# construction (family #9's own final_4/6/8 + half-split windows all
# measure the same underlying stat over overlapping game spans).
WINDOW_TOKENS = ("final_4", "final_6", "final_8", "first_half", "second_half")


def _strip_tier_suffix(col: str):
    for suf in TIER_SUFFIXES:
        if col.endswith(suf):
            return col[: -len(suf)]
    return None


def _window_stem(col: str):
    for tok in WINDOW_TOKENS:
        if f"_{tok}_" in col or col.endswith(f"_{tok}"):
            return col.replace(f"_{tok}_", "_<W>_").replace(f"_{tok}", "_<W>")
    return None


def build_predictor_clusters(real: pd.DataFrame, inv: pd.DataFrame, corr_pairs: pd.DataFrame):
    """OUTCOME-FREE clustering: never reads any target/eligibility/label
    column, only the predictor columns' own values and names. Union-find
    over four real, disclosed edge types:
      1. Continuous-continuous Pearson |r|>=0.95 (corr_pairs, §1.5).
      2. Boolean-boolean agreement rate >=95% on jointly-non-null rows
         (>=30 required for the check to run at all).
      3. Known family #9 tier vocabulary (role_present/meaningful_role/
         strong_lead_role share one continuous stem).
      4. Known family #9 trailing-window variants (same stat, different
         window length) sharing one stem.
    Returns (clusters: dict[root -> list[col]], edge_counts: dict).
    """
    const_cols = set(inv[inv["n_unique"] <= 1]["column"])
    cols = [c for c in inv["column"] if c not in const_cols]
    parent = {c: c for c in cols}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for _, row in corr_pairs.iterrows():
        if row["col_a"] in parent and row["col_b"] in parent:
            union(row["col_a"], row["col_b"])

    bool_cols = inv[(inv["column"].isin(cols)) & (inv["var_type"] == "boolean")]["column"].tolist()
    n_bool_edges = 0
    for i in range(len(bool_cols)):
        for j in range(i + 1, len(bool_cols)):
            a, b = bool_cols[i], bool_cols[j]
            both = real[[a, b]].dropna()
            if len(both) < BOOLEAN_AGREEMENT_MIN_JOINT_N:
                continue
            if (both[a] == both[b]).mean() >= BOOLEAN_AGREEMENT_THRESHOLD:
                union(a, b)
                n_bool_edges += 1

    tier_stems = {}
    for c in cols:
        stem = _strip_tier_suffix(c)
        if stem:
            tier_stems.setdefault(stem, []).append(c)
    for members in tier_stems.values():
        for m in members[1:]:
            union(members[0], m)

    window_groups = {}
    for c in cols:
        ws = _window_stem(c)
        if ws:
            window_groups.setdefault(ws, []).append(c)
    for members in window_groups.values():
        for m in members[1:]:
            union(members[0], m)

    clusters = {}
    for c in cols:
        clusters.setdefault(find(c), []).append(c)

    edge_counts = {
        "continuous_correlation_edges": len(corr_pairs),
        "boolean_agreement_edges": n_bool_edges,
        "known_tier_vocabulary_stems_merged": sum(1 for m in tier_stems.values() if len(m) > 1),
        "known_window_variant_stems_merged": sum(1 for m in window_groups.values() if len(m) > 1),
    }
    return clusters, edge_counts


def select_cluster_representative(members: list, inv: pd.DataFrame) -> str:
    """Priority order (never touches outcomes): (1) highest applicable
    coverage within its own position scope, (2) prefer a continuous
    source measure over a mechanically-derived threshold flag
    (role_present/meaningful_role/strong_lead_role suffixes), (3)
    broader historical season coverage, (4) shortest name as a crude
    proxy for fewer compounded assumptions (a raw metric name is
    shorter than a derived per-game/per-team-game/tier variant)."""
    inv_idx = inv.set_index("column")

    def sort_key(col):
        row = inv_idx.loc[col]
        is_threshold_flag = _strip_tier_suffix(col) is not None
        return (
            -row["applicable_n_within_position_scope"],
            1 if is_threshold_flag else 0,
            -row["n_seasons_present"],
            len(col),
        )

    return sorted(members, key=sort_key)[0]


if __name__ == "__main__":
    real = load_real_rows()
    whitelist = pd.read_csv(WHITELIST_PATH)["predictor_column"].tolist()
    registry = pd.read_csv(COLUMN_REGISTRY_PATH)

    print(f"Real (outcome-matched) rows: {len(real)}")
    inv = build_inventory(real, whitelist, registry)
    inv = add_position_scoped_applicable_n(inv, real)
    inv = add_single_season_concentration(inv, real)

    print("\n=== var_type counts ===")
    print(inv["var_type"].value_counts())
    print("\n=== position_scope counts ===")
    print(inv["position_scope"].value_counts())
    print("\n=== family counts (top) ===")
    print(inv["family"].value_counts())

    const_cols = inv[inv["n_unique"] <= 1]
    print(f"\n=== Constant columns (n_unique<=1): n={len(const_cols)} ===")
    print(const_cols[["column", "n_unique", "pct_nonnull_overall"]].to_string())

    low_scoped_coverage = inv[inv["pct_nonnull_within_scope"] < 50]
    print(f"\n=== Columns with real applicable coverage <50% WITHIN their own position scope: n={len(low_scoped_coverage)} ===")
    print(low_scoped_coverage[["column", "position_scope", "applicable_n_within_position_scope", "applicable_pop_size", "pct_nonnull_within_scope"]].head(20).to_string())

    pairs = find_near_duplicate_pairs(real, inv)
    print(f"\n=== Near-duplicate continuous pairs (|r|>={NEAR_DUPLICATE_CORR_THRESHOLD}): n={len(pairs)} ===")
    involved = len(set(pairs["col_a"]) | set(pairs["col_b"]))
    n_continuous_checked = len(inv[(inv["var_type"] == "continuous") & (inv["n_unique"] > 2)])
    print(f"Continuous columns checked: {n_continuous_checked}; involved in >=1 near-duplicate pair: {involved} ({involved / n_continuous_checked * 100:.1f}%)")

    high_concentration = inv[inv["max_single_season_share"] > 0.5]
    print(f"\n=== Columns with >50% of their non-null values in a single season: n={len(high_concentration)} ===")
    print(high_concentration[["column", "max_single_season_share", "n_seasons_present"]].head(15).to_string())

    print("\n=== Outcome-free predictor clustering (§ predictor clustering) ===")
    clusters, edge_counts = build_predictor_clusters(real, inv, pairs)
    for label, count in edge_counts.items():
        print(f"  {label}: {count}")
    print(f"  non-constant predictor columns: {len(inv[inv['n_unique'] > 1])}")
    print(f"  final cluster count: {len(clusters)}")
    sizes = sorted((len(v) for v in clusters.values()), reverse=True)
    print(f"  singleton clusters: {sum(1 for s in sizes if s == 1)}")
    print(f"  cluster size 2-5 / 6-10 / >10: {sum(1 for s in sizes if 2 <= s <= 5)} / {sum(1 for s in sizes if 6 <= s <= 10)} / {sum(1 for s in sizes if s > 10)}")

    cluster_rows = []
    for root, members in clusters.items():
        rep = select_cluster_representative(members, inv)
        for m in members:
            cluster_rows.append({"cluster_id": root, "cluster_size": len(members), "column": m, "is_representative": m == rep})
    cluster_df = pd.DataFrame(cluster_rows).sort_values(["cluster_size", "cluster_id"], ascending=[False, True])

    inv.to_csv("data/exports/dataset2_trait_pipeline_predictor_inventory.csv", index=False)
    pairs.to_csv("data/exports/dataset2_trait_pipeline_near_duplicate_pairs.csv", index=False)
    cluster_df.to_csv("data/exports/dataset2_trait_pipeline_predictor_clusters.csv", index=False)
    print(
        "\nWrote:\n  data/exports/dataset2_trait_pipeline_predictor_inventory.csv"
        "\n  data/exports/dataset2_trait_pipeline_near_duplicate_pairs.csv"
        "\n  data/exports/dataset2_trait_pipeline_predictor_clusters.csv"
    )
