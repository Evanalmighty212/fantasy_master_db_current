"""
Shared comparison harness for evaluating candidate Dataset 3 target
definitions against current LWI and the existing relative
top-10%-by-position benchmark. Deliberately configuration-driven --
no absolute-impact methodology is hardcoded here, since none has been
finalized (see task scope). Every candidate is supplied by the CALLER
as a ScoringDefinition; this module only knows how to score and
compare whatever it's given.
"""

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass
class ScoringDefinition:
    """
    A candidate way of scoring AND qualifying player-seasons as
    "league winners" -- fully caller-supplied, nothing about
    absolute-impact vs. relative is assumed here.

    score_fn(df) -> pd.Series: a numeric score, higher = better. Does
        not need to be 0-100 or normalized in any particular way.
    qualify_fn(df, score) -> pd.Series[bool]: which rows count as
        "league winners" under this definition. Deliberately decoupled
        from score_fn -- e.g. a RELATIVE definition might qualify the
        top 10% by position by season of its own score; an ABSOLUTE
        definition might qualify score >= some fixed threshold
        regardless of how many players that produces in a given
        season/position, which is the whole point of comparing the
        two philosophies side by side.
    """
    name: str
    score_fn: Callable[[pd.DataFrame], pd.Series]
    qualify_fn: Callable[[pd.DataFrame, pd.Series], pd.Series]


def top_pct_by_position_season_qualifier(pct: float = 0.10):
    """Factory for the EXISTING relative benchmark, generalized to any
    score column -- preserved as the fallback/benchmark method per the
    task's explicit instruction not to delete it. Matches
    docs/PREDICTION_SPECIFICATION.md Section 2's proposed rule: score
    >= that (season, position) group's (1-pct) quantile."""
    def qualify(df, score):
        thresh = score.groupby([df["season"], df["position"]]).transform(lambda s: s.quantile(1 - pct))
        return score >= thresh
    return qualify


def absolute_threshold_qualifier(threshold: float):
    """Factory for a simple fixed-threshold qualifier -- ONE example
    shape an absolute-impact rule could take, supplied as a
    CONFIGURABLE option for harness demonstration/testing, not
    hardcoded as THE methodology. A real absolute-impact definition
    would need real design work (see LWI_COMPONENT_AUDIT.md and the
    expected-production/replacement-level tables) before being used
    for anything beyond exercising this harness."""
    def qualify(df, score):
        return score >= threshold
    return qualify


def evaluate_definition(df: pd.DataFrame, definition: ScoringDefinition) -> pd.DataFrame:
    """Apply one ScoringDefinition to df, returning a COPY of df with
    two new columns: f"{name}_score" and f"{name}_qualifies"."""
    out = df.copy()
    score = definition.score_fn(out)
    out[f"{definition.name}_score"] = score
    out[f"{definition.name}_qualifies"] = definition.qualify_fn(out, score)
    return out


def annual_qualifying_counts(df: pd.DataFrame, qualifies_col: str) -> pd.DataFrame:
    return (
        df[df[qualifies_col]]
        .groupby("season").size()
        .rename("n_qualifying").reset_index()
    )


def positional_qualifying_counts(df: pd.DataFrame, qualifies_col: str) -> pd.DataFrame:
    return (
        df[df[qualifies_col]]
        .groupby(["season", "position"]).size()
        .rename("n_qualifying").reset_index()
    )


def top_historical_seasons(df: pd.DataFrame, score_col: str, n: int = 25) -> pd.DataFrame:
    cols = [c for c in [
        "season", "player_name", "position", "team",
        "fantasy_points_ppr", "ppg_ppr", "overall_finish_ppr", score_col,
    ] if c in df.columns]
    return df.dropna(subset=[score_col]).sort_values(score_col, ascending=False).head(n)[cols]


def rank_change_vs_baseline(
    df: pd.DataFrame, candidate_score_col: str, baseline_score_col: str,
) -> pd.DataFrame:
    """Rank movement between a candidate definition's score and a
    baseline (e.g. lwi_score), computed WITHIN each season. Positive
    rank_change means the candidate ranks the player HIGHER than the
    baseline did (baseline_rank - candidate_rank)."""
    work = df.dropna(subset=[candidate_score_col, baseline_score_col]).copy()
    work["candidate_rank"] = work.groupby("season")[candidate_score_col].rank(ascending=False, method="min")
    work["baseline_rank"] = work.groupby("season")[baseline_score_col].rank(ascending=False, method="min")
    work["rank_change"] = work["baseline_rank"] - work["candidate_rank"]
    cols = ["season", "player_id", "player_name", "position",
            "candidate_rank", "baseline_rank", "rank_change"]
    return work[[c for c in cols if c in work.columns]].sort_values(
        "rank_change", ascending=False
    )


def qualifying_set_overlap(df: pd.DataFrame, qualifies_col_a: str, qualifies_col_b: str) -> dict:
    """How much two definitions' qualifying sets agree -- overlap
    count, Jaccard, and how many rows only one side flags."""
    a = set(df.index[df[qualifies_col_a].fillna(False)])
    b = set(df.index[df[qualifies_col_b].fillna(False)])
    both = a & b
    union = a | b
    return {
        "n_a": len(a), "n_b": len(b), "n_both": len(both),
        "n_only_a": len(a - b), "n_only_b": len(b - a),
        "jaccard": (len(both) / len(union)) if union else float("nan"),
    }
