"""
research/dataset3/tests/test_lib.py

Tests for the REUSABLE Dataset 3 research code in
research/dataset3/lib/ -- eras.py, replacement.py, comparison.py.
Deliberately does NOT test the one-off table-generation scripts
(build_broad_historical_dataset.py etc.) since those are thin CLI
wrappers around this lib; testing the lib functions directly is what
actually protects the reusable logic. Kept isolated from the
production test suite in tests/ at the repo root -- these protect
exploratory research code, not the production LWI pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from lib import eras, replacement, comparison


class TestEras:
    def test_boundary_seasons(self):
        # Exact boundary years, since off-by-one errors here would
        # silently misclassify entire seasons.
        assert eras.assign_era(2010) == "pre_2011"
        assert eras.assign_era(2011) == "2011_2020"
        assert eras.assign_era(2020) == "2011_2020"
        assert eras.assign_era(2021) == "2021_plus"

    def test_add_era_column(self):
        df = pd.DataFrame({"season": [2009, 2015, 2023]})
        out = eras.add_era_column(df)
        assert list(out["era"]) == ["pre_2011", "2011_2020", "2021_plus"]
        # original df untouched (add_era_column copies)
        assert "era" not in df.columns


class TestReplacementRankCutoff:
    def test_no_flex(self):
        preset = replacement.ROSTER_PRESETS["12_team_standard"]
        assert replacement.replacement_rank_cutoff(preset, "RB", replacement.FLEX_ALLOCATION_NONE) == 24
        assert replacement.replacement_rank_cutoff(preset, "QB", replacement.FLEX_ALLOCATION_NONE) == 12

    def test_even_flex_adds_expected_slots(self):
        preset = replacement.ROSTER_PRESETS["12_team_standard"]
        # 2*12 starters + (1/3 * 1 * 12) flex share = 24 + 4 = 28
        assert replacement.replacement_rank_cutoff(preset, "RB", replacement.FLEX_ALLOCATION_EVEN) == 28

    def test_qb_unaffected_by_flex_allocation(self):
        # QB isn't in any flex_allocation dict tested here -- .get()
        # should default to 0, not raise or silently misallocate.
        preset = replacement.ROSTER_PRESETS["10_team_standard"]
        no_flex = replacement.replacement_rank_cutoff(preset, "QB", replacement.FLEX_ALLOCATION_NONE)
        even_flex = replacement.replacement_rank_cutoff(preset, "QB", replacement.FLEX_ALLOCATION_EVEN)
        assert no_flex == even_flex == 10


class TestReplacementLevelFromRank:
    def test_median_within_window(self):
        df = pd.DataFrame({
            "season": [2020] * 6,
            "position": ["RB"] * 6,
            "position_finish_ppr": [1, 2, 3, 4, 5, 6],
            "ppg_ppr": [20.0, 18.0, 16.0, 14.0, 12.0, 10.0],
        })
        result = replacement.replacement_level_from_rank(
            df, value_col="ppg_ppr", rank_col="position_finish_ppr",
            cutoff_by_position={"RB": 3}, window=2,
        )
        # ranks 3,4,5 -> ppg values 16,14,12 -> median 14, for every row
        # in this (season, position) group (function returns one value
        # per input row via lookup, not per group)
        assert (result == 14.0).all()

    def test_missing_position_returns_nan(self):
        df = pd.DataFrame({
            "season": [2020], "position": ["TE"], "position_finish_ppr": [1], "ppg_ppr": [10.0],
        })
        result = replacement.replacement_level_from_rank(
            df, value_col="ppg_ppr", rank_col="position_finish_ppr",
            cutoff_by_position={"RB": 3}, window=2,  # no TE entry
        )
        assert result.isna().all()


class TestComparisonQualifiers:
    def _synthetic_df(self):
        # 2 seasons x 1 position x 10 players each, scores 100..91 (season A) / 50..41 (season B)
        rows = []
        for season, base in [(2020, 100), (2021, 50)]:
            for i in range(10):
                rows.append({
                    "season": season, "position": "WR", "player_id": f"{season}_{i}",
                    "player_name": f"Player {i}", "score": base - i,
                })
        return pd.DataFrame(rows)

    def test_top_pct_by_position_season_is_season_relative(self):
        df = self._synthetic_df()
        qualify_fn = comparison.top_pct_by_position_season_qualifier(pct=0.30)
        qualifies = qualify_fn(df, df["score"])
        # top 30% of 10 = top 3 in EACH season, regardless of the raw
        # score scale differing wildly between seasons (100s vs 50s)
        assert qualifies[df["season"] == 2020].sum() == 3
        assert qualifies[df["season"] == 2021].sum() == 3
        # season B's qualifiers are its own top scorers (50, 49, 48), not season A's scale
        season_b_qualifiers = df[(df["season"] == 2021) & qualifies]["score"]
        assert set(season_b_qualifiers) == {50, 49, 48}

    def test_absolute_threshold_is_not_season_relative(self):
        df = self._synthetic_df()
        qualify_fn = comparison.absolute_threshold_qualifier(threshold=95)
        qualifies = qualify_fn(df, df["score"])
        # only season A (scores 91-100) can clear an absolute 95 --
        # season B (41-50) gets ZERO qualifiers, unlike the relative
        # rule which always gives every season the same count. This is
        # the exact behavioral contrast the harness exists to surface.
        assert qualifies[df["season"] == 2020].sum() == 6  # scores 95-100
        assert qualifies[df["season"] == 2021].sum() == 0


class TestEvaluateDefinitionAndCounts:
    def _df(self):
        return pd.DataFrame({
            "season": [2020, 2020, 2021, 2021],
            "position": ["WR", "RB", "WR", "RB"],
            "player_id": ["a", "b", "c", "d"],
            "raw": [10.0, 20.0, 30.0, 5.0],
        })

    def test_evaluate_definition_adds_named_columns(self):
        df = self._df()
        definition = comparison.ScoringDefinition(
            name="demo",
            score_fn=lambda d: d["raw"],
            qualify_fn=comparison.absolute_threshold_qualifier(15.0),
        )
        out = comparison.evaluate_definition(df, definition)
        assert list(out["demo_score"]) == [10.0, 20.0, 30.0, 5.0]
        assert list(out["demo_qualifies"]) == [False, True, True, False]
        # original df untouched
        assert "demo_score" not in df.columns

    def test_annual_and_positional_counts(self):
        df = self._df()
        df["q"] = [False, True, True, False]
        annual = comparison.annual_qualifying_counts(df, "q")
        assert dict(zip(annual["season"], annual["n_qualifying"])) == {2020: 1, 2021: 1}
        positional = comparison.positional_qualifying_counts(df, "q")
        assert len(positional) == 2  # (2020, RB) and (2021, WR)


class TestRankChangeAndOverlap:
    def test_rank_change_positive_means_candidate_ranks_higher(self):
        df = pd.DataFrame({
            "season": [2020, 2020, 2020],
            "player_id": ["a", "b", "c"],
            "player_name": ["A", "B", "C"],
            "position": ["WR", "WR", "WR"],
            "baseline": [10.0, 20.0, 30.0],   # baseline rank: C=1, B=2, A=3
            "candidate": [30.0, 20.0, 10.0],  # candidate rank: A=1, B=2, C=3
        })
        result = comparison.rank_change_vs_baseline(df, "candidate", "baseline")
        row_a = result[result["player_id"] == "a"].iloc[0]
        # A: baseline_rank=3, candidate_rank=1 -> rank_change = 3-1 = +2 (moved up)
        assert row_a["rank_change"] == 2
        row_c = result[result["player_id"] == "c"].iloc[0]
        # C: baseline_rank=1, candidate_rank=3 -> rank_change = 1-3 = -2 (moved down)
        assert row_c["rank_change"] == -2

    def test_qualifying_set_overlap(self):
        df = pd.DataFrame({"a": [True, True, False, False], "b": [True, False, True, False]})
        result = comparison.qualifying_set_overlap(df, "a", "b")
        assert result["n_a"] == 2
        assert result["n_b"] == 2
        assert result["n_both"] == 1
        assert result["n_only_a"] == 1
        assert result["n_only_b"] == 1
        assert result["jaccard"] == pytest.approx(1 / 3)
