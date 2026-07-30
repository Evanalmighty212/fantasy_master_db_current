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

CLUSTERING (revised after review of the original 69-member cluster):
see `build_predictor_clusters()`'s own docstring for the full
methodology. Summary: (1) a semantic pre-filter based on the family #9
naming convention restricts candidate similarity pairs to columns
sharing one football concept BEFORE any statistic runs; (2)
eligibility/gating columns never enter a similarity edge; (3)
role-tier threshold flags attach to their continuous source by known
construction; (4) complete linkage (not connected components) on a
real similarity matrix, so a cluster's WORST internal pairwise
similarity is guaranteed to clear the threshold, preventing the
single-linkage chaining that produced the original 69-member cluster.

All set-based iteration is done through `sorted()` throughout --
Python's per-process hash randomization for strings makes raw `set`
iteration order non-deterministic across runs, which silently produced
different cluster numbering (and, in one caught case during this
round's own development, a different apparent cluster count: 0 vs. 3
clusters over 10 members) between two runs of otherwise-identical code.
Verified deterministic by running this script twice and diffing output
before finalizing any number in the proposal doc.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

VIEW_PATH = "data/exports/dataset2_analysis_view.parquet"
WHITELIST_PATH = "data/exports/dataset2_analysis_view_predictor_whitelist.csv"
COLUMN_REGISTRY_PATH = "data/exports/dataset2_analysis_view_column_registry.csv"

NEAR_DUPLICATE_CORR_THRESHOLD = 0.95
# Documented minimum overlapping (jointly-non-null) sample for ANY
# pairwise similarity check in this file -- a correlation/Jaccard/phi
# estimate from fewer points is unstable regardless of its value. 50 is
# 5x this project's existing DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE=10
# floor (that constant protects a single reported CELL; a pairwise
# SIMILARITY estimate deciding whether two columns measure the same
# thing needs a larger, separately-documented floor).
MIN_OVERLAP_N = 50
# Prevalence-aware boolean similarity: BOTH required, so neither
# "positives barely overlap but overall association looks strong" nor
# "association looks weak only because True is rare in both" passes
# alone. Jaccard is computed on POSITIVE cases only (ignores shared
# False) -- the exact failure mode that inflated the original
# 69-member cluster, where many unrelated eligibility-style flags
# agreed mostly by both being False for the same players.
BOOLEAN_JACCARD_THRESHOLD = 0.70
BOOLEAN_PHI_THRESHOLD = 0.85

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
    in its single most-populated real prediction_season."""
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
    traits. Adds the real, position-scoped applicable sample size."""
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
    """Unrestricted, whole-population continuous-continuous correlation
    scan -- kept ONLY as a raw §1 descriptive summary (how much
    statistical redundancy exists at all, with no semantic filter).
    NOT used to build clusters -- see build_predictor_clusters(), which
    restricts candidate pairs to a shared semantic concept before any
    statistical check runs, precisely to avoid the false-similarity
    failure mode this raw, unrestricted scan is prone to on its own."""
    cont_cols = sorted(inv[(inv["var_type"] == "continuous") & (inv["n_unique"] > 2)]["column"].tolist())
    X = real[cont_cols].astype(float)
    corr = X.corr(method="pearson", min_periods=MIN_OVERLAP_N)
    pairs = []
    for i in range(len(cont_cols)):
        for j in range(i + 1, len(cont_cols)):
            r = corr.iloc[i, j]
            if pd.notna(r) and abs(r) >= NEAR_DUPLICATE_CORR_THRESHOLD:
                pairs.append((cont_cols[i], cont_cols[j], round(float(r), 4)))
    return pd.DataFrame(pairs, columns=["col_a", "col_b", "pearson_r"]).sort_values("pearson_r", key=abs, ascending=False)


# =========================================================================
# Semantic parsing of the family #9 naming convention -- validated with
# ZERO unparsed leftovers against all 386 real fam9 whitelist columns
# before being wired into clustering below.
# =========================================================================

FAM9_BASIS_TOKENS = ("team", "active")
FAM9_WINDOW_TOKENS = ("final_4", "final_6", "final_8", "first_half", "second_half")
FAM9_POSITIONS = ("qb", "rb", "wr", "te")
# Eligibility/gating flags -- excluded from ALL statistical similarity
# edges per instruction (shared applicability/eligibility must never
# create a content-similarity edge). Reported as associated metadata on
# their concept's cluster instead, never merged in.
FAM9_ELIGIBILITY_SUFFIXES = (
    "efficiency_volume_eligible_exploratory",
    "efficiency_volume_eligible_sensitivity",
    "has_snap_coverage",
    "sample_qualified_primary",
    "sample_qualified_sensitivity",
)
# Threshold flags derived from ONE underlying continuous share/rate --
# known by construction (this project's own three-tier framework,
# partial_season_traits.py), not a statistically inferred relationship.
# Allowed to join their continuous source as an alternate formulation
# of the SAME concept, per instruction.
FAM9_ROLE_TIER_SUFFIXES = ("role_present", "meaningful_role", "strong_lead_role")
# Real, continuous CONTENT metric types (longest-match-first so e.g.
# "opportunity_per_active_game" matches before the bare "opportunity").
FAM9_CONTENT_METRIC_TYPES = sorted(
    [
        "opportunity_per_active_game", "opportunity_per_team_game", "opportunity",
        "production", "efficiency_rate",
        "offense_snap_share", "offense_snaps", "team_offense_total",
    ],
    key=len, reverse=True,
)

# REAL FINDING, caught by verifying representative-to-member similarity
# before trusting it (not assumed): (position, metric_category) alone
# is too coarse a concept for receiving/rushing/passing -- "how much
# opportunity/role a player had" and "how efficient they were with it"
# are genuinely different football questions living under the same
# metric_category. Verified empirically: `role_present` correlates at
# r=0.82 with `opportunity` but r=-0.02 (no relationship at all) with
# `efficiency_rate`, for the identical window/basis/position/category.
# A metric_family split (volume vs. efficiency) is added below so
# role-tier flags only ever attach to the volume-type measure they are
# actually constructed from, never to the unrelated efficiency measure
# that happened to share the same (position, metric_category).
FAM9_VOLUME_METRIC_TYPES = {
    "opportunity", "opportunity_per_active_game", "opportunity_per_team_game", "production",
    "offense_snaps", "offense_snap_share", "team_offense_total",
}
FAM9_EFFICIENCY_METRIC_TYPES = {"efficiency_rate"}


def _metric_family(metric_type, kind):
    if kind == "role_tier":
        return "volume"  # role tiers are constructed FROM the volume/opportunity measure, never from efficiency
    if kind == "eligibility":
        # These gate a SPECIFIC downstream measure -- named accordingly
        # (e.g. "efficiency_volume_eligible_*" gates efficiency_rate).
        return "efficiency" if metric_type and "efficiency" in metric_type else "volume"
    if metric_type in FAM9_VOLUME_METRIC_TYPES:
        return "volume"
    if metric_type in FAM9_EFFICIENCY_METRIC_TYPES:
        return "efficiency"
    return "other"

# A small, EXPLICITLY documented set of real cross-family concept links
# -- verified via direct correlation (fam10_starter_group_size vs
# fam86_wr_starter_group_size, r=1.0000 -- literally the same real
# football fact computed by two different family modules), not a
# statistically-discovered rule; manually reviewed, not automated.
NON_FAM9_CONCEPT_OVERRIDES = {
    "fam10_starter_group_size": "starter_group_size",
    "fam86_wr_starter_group_size": "starter_group_size",
}


def parse_fam9_column(col: str) -> dict:
    """Real semantic parser. Returns basis, window, position,
    metric_category, metric_type, kind
    ("content"/"role_tier"/"eligibility"), and concept_key -- the ONLY
    basis on which candidate similarity pairs are formed."""
    assert col.startswith("fam9_")
    rest = col[len("fam9_") :]

    basis = None
    for b in FAM9_BASIS_TOKENS:
        if rest == b or rest.startswith(b + "_"):
            basis = b
            rest = rest[len(b) :].lstrip("_")
            break

    window = None
    for w in FAM9_WINDOW_TOKENS:
        if rest == w or rest.startswith(w + "_"):
            window = w
            rest = rest[len(w) :].lstrip("_")
            break

    position = None
    for p in FAM9_POSITIONS:
        if rest == p or rest.startswith(p + "_"):
            position = p
            rest = rest[len(p) :].lstrip("_")
            break

    kind, metric_category, metric_type = None, None, None
    for suf in FAM9_ELIGIBILITY_SUFFIXES:
        if rest == suf or rest.endswith("_" + suf):
            kind, metric_type = "eligibility", suf
            metric_category = rest[: -(len(suf) + 1)] if rest != suf else None
            rest = ""
            break
    if kind is None:
        for suf in FAM9_ROLE_TIER_SUFFIXES:
            if rest == suf or rest.endswith("_" + suf):
                kind, metric_type = "role_tier", suf
                metric_category = rest[: -(len(suf) + 1)] if rest != suf else None
                rest = ""
                break
    if kind is None:
        for suf in FAM9_CONTENT_METRIC_TYPES:
            if rest == suf or rest.endswith("_" + suf):
                kind, metric_type = "content", suf
                metric_category = rest[: -(len(suf) + 1)] if rest != suf else None
                rest = ""
                break
    if kind is None:
        # Team-level/ungrouped remainder (games, active_games,
        # games_ppg, points_per_*, team_games) -- still real content,
        # just not position/metric_category-structured.
        kind, metric_type, metric_category, rest = "content", rest, None, ""

    metric_family = _metric_family(metric_type, kind)
    return {
        "column": col, "basis": basis, "window": window, "position": position,
        "metric_category": metric_category, "metric_type": metric_type, "kind": kind,
        "metric_family": metric_family,
        "concept_key": (position or "ALL", metric_category or metric_type, metric_family),
        "_unparsed_leftover": rest,
    }


def semantic_concept_key(col: str, family) -> str:
    if col.startswith("fam9_"):
        return "fam9::" + str(parse_fam9_column(col)["concept_key"])
    if col in NON_FAM9_CONCEPT_OVERRIDES:
        return "xfam::" + NON_FAM9_CONCEPT_OVERRIDES[col]
    return "family::" + str(family)


def boolean_pair_similarity(real: pd.DataFrame, a: str, b: str):
    """Returns (jaccard_on_positives, phi, joint_n), or None if
    MIN_OVERLAP_N isn't met on the jointly-non-null rows."""
    both = real[[a, b]].dropna()
    joint_n = len(both)
    if joint_n < MIN_OVERLAP_N:
        return None
    A, B = both[a].astype(bool), both[b].astype(bool)
    union_n = int((A | B).sum())
    jaccard = float((A & B).sum() / union_n) if union_n > 0 else 0.0
    phi = pd.Series(A.astype(int)).corr(pd.Series(B.astype(int)))
    return jaccard, (float(phi) if pd.notna(phi) else 0.0), joint_n


def build_predictor_clusters(real: pd.DataFrame, inv: pd.DataFrame):
    """OUTCOME-FREE clustering -- reads only predictor column VALUES and
    NAMES, never a target/eligibility/label column.

    1. SEMANTIC PRE-FILTER FIRST: candidate similarity pairs are
       restricted to columns sharing one concept_key (fam9: (position,
       metric_category) parsed from the family #9 naming convention;
       non-fam9: family number, plus 2 manually-reviewed real
       cross-family links) -- computed BEFORE any statistic runs, so
       two columns can never merge merely because they are
       statistically associated across unrelated football concepts.
    2. Eligibility/gating columns NEVER enter a statistical similarity
       edge -- reported as associated metadata on their concept's
       cluster, never merged in as content.
    3. Role-tier threshold flags attach to their own continuous source
       by KNOWN construction (matched on identical basis+window within
       the same concept where possible) -- not a statistical inference.
    4. Remaining CONTENT columns within a concept are clustered by
       COMPLETE LINKAGE (never connected components/single linkage) on
       a real similarity matrix -- continuous: 1-|Pearson r|; boolean:
       binary edge from the dual Jaccard+phi test. Complete linkage
       guarantees every resulting cluster's WORST internal pairwise
       similarity still clears the threshold -- the direct fix for the
       original 69-member cluster, which was a single-linkage chain
       (A~B~C~D) whose distant members were never actually similar to
       each other.

    All iteration is via sorted() -- see module docstring on the real
    determinism bug this caught during development.

    Returns (clusters: dict[cluster_id -> {"content": [...],
    "eligibility_metadata": [...]}], audit_rows: list of per-cluster
    audit records, stats: dict of real edge/pair counts).
    """
    inv_idx = inv.set_index("column")
    family_map = inv_idx["family"].to_dict()
    const_cols = sorted(inv[inv["n_unique"] <= 1]["column"].tolist())
    cols = sorted([c for c in inv["column"] if c not in const_cols])

    parsed = {c: (parse_fam9_column(c) if c.startswith("fam9_") else {"kind": "content"}) for c in cols}
    kind_of = {c: parsed[c]["kind"] for c in cols}
    concept_map = {c: semantic_concept_key(c, family_map.get(c)) for c in cols}

    eligibility_cols = sorted([c for c in cols if kind_of[c] == "eligibility"])
    role_tier_cols = sorted([c for c in cols if kind_of[c] == "role_tier"])
    content_cols = sorted([c for c in cols if kind_of[c] == "content"])
    content_set, role_tier_set = set(content_cols), set(role_tier_cols)

    groups = {}
    for c in content_cols:
        groups.setdefault(concept_map[c], []).append(c)

    member_to_cluster = {}
    cluster_counter = 0
    audit_rows = []
    n_pairs_checked = 0

    for concept in sorted(groups.keys()):
        members = sorted(groups[concept])
        vtypes = sorted(set(inv_idx.loc[m, "var_type"] for m in members))
        if len(members) == 1 or len(vtypes) > 1:
            # Singleton, or a concept mixing continuous/boolean/status
            # types with no defined cross-type similarity measure this
            # round -- each member stays its own cluster rather than
            # guessing a cross-type merge.
            for m in members:
                cluster_counter += 1
                member_to_cluster[m] = cluster_counter
            continue

        vt = vtypes[0]
        n = len(members)
        if vt == "continuous":
            X = real[members].astype(float)
            corr = X.corr(method="pearson", min_periods=MIN_OVERLAP_N).fillna(0.0)
            sim = corr.abs().values
            n_pairs_checked += n * (n - 1) // 2
            threshold_dist = 1.0 - NEAR_DUPLICATE_CORR_THRESHOLD
        elif vt == "boolean":
            sim = np.eye(n)
            for i in range(n):
                for j in range(i + 1, n):
                    n_pairs_checked += 1
                    res = boolean_pair_similarity(real, members[i], members[j])
                    edge = 0.0
                    if res is not None:
                        jaccard, phi, _ = res
                        if jaccard >= BOOLEAN_JACCARD_THRESHOLD and phi >= BOOLEAN_PHI_THRESHOLD:
                            edge = 1.0
                    sim[i, j] = sim[j, i] = edge
            threshold_dist = 0.5
        else:
            for m in members:
                cluster_counter += 1
                member_to_cluster[m] = cluster_counter
            continue

        dist = np.clip(1.0 - sim, 0.0, None)
        np.fill_diagonal(dist, 0.0)
        Z = linkage(squareform(dist, checks=False), method="complete")
        labels = fcluster(Z, t=threshold_dist, criterion="distance")

        local = {}
        for m, lab in zip(members, labels):
            local.setdefault(int(lab), []).append(m)
        for lab in sorted(local.keys()):
            mem = sorted(local[lab])
            cluster_counter += 1
            for m in mem:
                member_to_cluster[m] = cluster_counter
            min_sim, med_sim = 1.0, 1.0
            if len(mem) > 1:
                idxs = [members.index(m) for m in mem]
                pairwise = [sim[i][j] for i in idxs for j in idxs if i != j]
                min_sim, med_sim = float(min(pairwise)), float(np.median(pairwise))
            audit_rows.append(
                {
                    "concept": concept, "cluster_id": cluster_counter, "size": len(mem),
                    "members": mem, "min_pairwise_sim": round(min_sim, 4), "median_pairwise_sim": round(med_sim, 4),
                }
            )

    for c in role_tier_cols:
        p = parsed[c]
        stem_concept = concept_map[c]
        candidates = sorted([m for m in content_cols if concept_map[m] == stem_concept])
        target_col = None
        for cand in candidates:
            cand_p = parsed[cand]
            if cand_p.get("basis") == p.get("basis") and cand_p.get("window") == p.get("window"):
                target_col = cand
                break
        target_col = target_col or (candidates[0] if candidates else None)
        target = member_to_cluster.get(target_col) if target_col else None
        if target is not None:
            member_to_cluster[c] = target
        else:
            cluster_counter += 1
            member_to_cluster[c] = cluster_counter

    eligibility_metadata = {}
    for c in eligibility_cols:
        concept = concept_map[c]
        candidates = sorted(
            [member_to_cluster[m] for m in sorted(content_set | role_tier_set) if concept_map.get(m) == concept and m in member_to_cluster]
        )
        target = max(sorted(set(candidates)), key=candidates.count) if candidates else None
        eligibility_metadata.setdefault(target, []).append(c)

    clusters = {}
    for m in sorted(member_to_cluster.keys()):
        cid = member_to_cluster[m]
        clusters.setdefault(cid, {"content": [], "eligibility_metadata": []})
        clusters[cid]["content"].append(m)
    for cid in sorted(eligibility_metadata.keys(), key=lambda x: (x is None, x)):
        elig = sorted(eligibility_metadata[cid])
        if cid in clusters:
            clusters[cid]["eligibility_metadata"].extend(elig)
        else:
            clusters.setdefault(-1, {"content": [], "eligibility_metadata": []})["eligibility_metadata"].extend(elig)

    stats = {
        "n_content_columns": len(content_cols),
        "n_role_tier_columns": len(role_tier_cols),
        "n_eligibility_columns": len(eligibility_cols),
        "n_pairs_statistically_checked": n_pairs_checked,
        "n_concepts": len(groups),
    }
    return clusters, audit_rows, stats


def select_cluster_representative(members: list, inv: pd.DataFrame) -> str:
    """Priority order (never touches outcomes, per instruction):
    (1) highest applicable coverage within its own position scope,
    (2) prefer a continuous source measure over a mechanically-derived
        threshold flag (role_present/meaningful_role/strong_lead_role),
    (3) broader historical season coverage,
    (4) fewer compounded assumptions -- proxied by shorter column name
        (a raw metric name is reliably shorter than its per-game/
        per-team-game-normalized or tier-derived variant in this
        project's established naming convention)."""
    inv_idx = inv.set_index("column")

    def is_threshold_flag(col):
        return any(col.endswith("_" + s) for s in FAM9_ROLE_TIER_SUFFIXES)

    def sort_key(col):
        row = inv_idx.loc[col]
        return (-row["applicable_n_within_position_scope"], 1 if is_threshold_flag(col) else 0, -row["n_seasons_present"], len(col))

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
    print(f"\n=== Unrestricted continuous correlation scan (|r|>={NEAR_DUPLICATE_CORR_THRESHOLD}, descriptive only, NOT used to build clusters): n={len(pairs)} ===")

    high_concentration = inv[inv["max_single_season_share"] > 0.5]
    print(f"\n=== Columns with >50% of their non-null values in a single season: n={len(high_concentration)} ===")

    print("\n=== Outcome-free semantic predictor clustering (revised) ===")
    clusters, audit_rows, stats = build_predictor_clusters(real, inv)
    for label, count in stats.items():
        print(f"  {label}: {count}")
    real_clusters = {cid: v for cid, v in clusters.items() if cid != -1}
    print(f"  final cluster count: {len(real_clusters)}")
    sizes = sorted((len(v["content"]) for v in real_clusters.values()), reverse=True)
    print(f"  singleton clusters: {sum(1 for s in sizes if s == 1)}")
    print(f"  cluster size 2-5 / 6-10 / >10: {sum(1 for s in sizes if 2 <= s <= 5)} / {sum(1 for s in sizes if 6 <= s <= 10)} / {sum(1 for s in sizes if s > 10)}")
    print(f"  largest cluster size: {max(sizes)}")

    print("\n=== Audit: every cluster with more than 10 members ===")
    large_clusters = sorted([cid for cid, v in real_clusters.items() if len(v["content"]) > 10], key=lambda cid: -len(real_clusters[cid]["content"]))
    print(f"  n clusters >10 members: {len(large_clusters)} (down from the original review's 1 cluster of 69 members)")
    inv_idx_print = inv.set_index("column")
    for cid in large_clusters:
        v = real_clusters[cid]
        ar = [r for r in audit_rows if r["cluster_id"] == cid][0]
        rep = select_cluster_representative(v["content"], inv)
        is_flag = any(rep.endswith("_" + s) for s in FAM9_ROLE_TIER_SUFFIXES)
        print(f"\n  --- Cluster {cid}: concept={ar['concept']} ---")
        print(f"  size={ar['size']}, min_pairwise_sim={ar['min_pairwise_sim']}, median_pairwise_sim={ar['median_pairwise_sim']}")
        print(f"  eligibility metadata excluded from edges, attached for reporting: {len(v['eligibility_metadata'])} -> {v['eligibility_metadata']}")
        print(f"  recommended representative: {rep}")
        if is_flag:
            cont_candidates = [m for m in v["content"] if not any(m.endswith("_" + s) for s in FAM9_ROLE_TIER_SUFFIXES)]
            if cont_candidates:
                best_cont = sorted(cont_candidates, key=lambda m: -inv_idx_print.loc[m, "applicable_n_within_position_scope"])[0]
                print(
                    f"  FLAGGED FOR REVIEW: representative is a threshold flag, not the continuous measure -- "
                    f"real coverage {inv_idx_print.loc[rep, 'applicable_n_within_position_scope']} vs. "
                    f"{inv_idx_print.loc[best_cont, 'applicable_n_within_position_scope']} for the best continuous "
                    f"candidate ({best_cont}). Priority 1 (coverage) legitimately outranked priority 5 (prefer "
                    f"continuous) per the specified order -- not overridden unilaterally, but disclosed for review."
                )
        print(f"  members: {v['content']}")

    cluster_rows = []
    for cid, v in clusters.items():
        rep = select_cluster_representative(v["content"], inv) if v["content"] else None
        for m in v["content"]:
            cluster_rows.append({"cluster_id": cid, "cluster_size": len(v["content"]), "column": m, "role": "content", "is_representative": m == rep})
        for m in v["eligibility_metadata"]:
            cluster_rows.append({"cluster_id": cid, "cluster_size": len(v["content"]), "column": m, "role": "eligibility_metadata", "is_representative": False})
    cluster_df = pd.DataFrame(cluster_rows).sort_values(["cluster_size", "cluster_id"], ascending=[False, True])

    inv.to_csv("data/exports/dataset2_trait_pipeline_predictor_inventory.csv", index=False)
    pairs.to_csv("data/exports/dataset2_trait_pipeline_near_duplicate_pairs.csv", index=False)
    cluster_df.to_csv("data/exports/dataset2_trait_pipeline_predictor_clusters.csv", index=False)
    print(
        "\nWrote:\n  data/exports/dataset2_trait_pipeline_predictor_inventory.csv"
        "\n  data/exports/dataset2_trait_pipeline_near_duplicate_pairs.csv"
        "\n  data/exports/dataset2_trait_pipeline_predictor_clusters.csv"
    )
