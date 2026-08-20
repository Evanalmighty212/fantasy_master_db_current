"""
tests/test_dataset2_common.py

Protects lib/dataset2/common.py's shared helpers -- created 2026-07
specifically to regression-test the real week-boundary bug found in
lib/dataset2/partial_season_traits.py (see
research/dataset2/PARTIAL_SEASON_RELIABILITY_PROPOSAL_2026_07.md §0):
`season_length()` returns real GAMES PLAYED (16 or 17), not the real
maximum REG week NUMBER, which is one higher because every team's real
bye week consumes a week-number slot without a played game.
`real_reg_week_slots()` and `build_team_game_index()` are the shared,
canonical way every Dataset 2 module must now derive week-boundary or
team-game-sequence logic -- this file is the one place their own
correctness is proven, so every consuming module can rely on it
without re-deriving it.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from lib.dataset2.common import (
    apply_source_coverage_null_mask,
    build_team_game_index,
    classify_column_constancy,
    derive_predictor_whitelist_from_registry,
    filter_to_discovery_fit_predictor_rows,
    filter_to_historical_predictor_rows,
    predictor_registry_role,
    real_reg_week_slots,
    season_length,
    week1_kickoff_by_team,
)


class TestRealRegWeekSlots:
    def test_16_game_season_real_week_slots_is_17(self):
        # Real 2015 (pre-ERA_CUTOFF, season_length==16): real REG weeks
        # run 1-17 (verified directly against real stats_player_week_2015.csv).
        assert season_length(2015) == 16
        assert real_reg_week_slots(2015) == 17

    def test_17_game_season_real_week_slots_is_18(self):
        # Real 2021 (post-ERA_CUTOFF, season_length==17): real REG weeks
        # run 1-18 (verified directly against real stats_player_week_2021.csv).
        assert season_length(2021) == 17
        assert real_reg_week_slots(2021) == 18

    def test_postseason_exclusion_boundary_16_game_era(self):
        # Real week 17 is the final real REG week for a 16-game-era
        # season -- must NOT be classified postseason.
        assert 17 <= real_reg_week_slots(2015)
        # Real week 18 does not exist for a 16-game-era season at all;
        # if it appeared, it would correctly be beyond the real REG
        # boundary -- this is the exact rule participation_traits.py's
        # _is_postseason() applies via this same shared helper.
        assert 18 > real_reg_week_slots(2015)

    def test_postseason_exclusion_boundary_17_game_era(self):
        assert 18 <= real_reg_week_slots(2021)
        assert 19 > real_reg_week_slots(2021)


class TestBuildTeamGameIndex:
    def _weekly(self, rows):
        return pd.DataFrame(rows)

    def test_contiguous_weeks_get_sequential_index(self):
        w = self._weekly(
            [
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 2, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 3, "team": "KC", "season_type": "REG"},
            ]
        )
        out = build_team_game_index(w)
        assert out["team_game_index"].tolist() == [1, 2, 3]
        assert (out["team_total_games"] == 3).all()

    def test_bye_week_gap_is_compressed_out(self):
        # Real 2015 New England pattern: week 4 is the real bye --
        # absent from the raw data entirely, not a zero-row placeholder.
        w = self._weekly(
            [{"season": 2015, "week": wk, "team": "NE", "season_type": "REG"} for wk in [1, 2, 3, 5, 6]]
        )
        out = build_team_game_index(w)
        assert out.set_index("week")["team_game_index"].to_dict() == {1: 1, 2: 2, 3: 3, 5: 4, 6: 5}
        assert (out["team_total_games"] == 5).all()

    def test_real_16_game_season_produces_16_team_games(self):
        # A full real 16-game-era team-season: 17 real week slots minus
        # 1 real bye = 16 real games, verified directly earlier against
        # real 2015 data (every real team-season showed exactly 16 or
        # 17 distinct weeks, matching season_length exactly).
        weeks = [wk for wk in range(1, 18) if wk != 9]  # bye at week 9
        w = self._weekly([{"season": 2015, "week": wk, "team": "DAL", "season_type": "REG"} for wk in weeks])
        out = build_team_game_index(w)
        assert out["team_total_games"].iloc[0] == 16

    def test_postseason_rows_excluded(self):
        w = self._weekly(
            [
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 2, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 19, "team": "KC", "season_type": "POST"},
            ]
        )
        out = build_team_game_index(w)
        assert len(out) == 2
        assert out["team_total_games"].iloc[0] == 2

    def test_multiple_teams_independently_indexed(self):
        w = self._weekly(
            [
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 1, "team": "SF", "season_type": "REG"},
                {"season": 2023, "week": 2, "team": "KC", "season_type": "REG"},
            ]
        )
        out = build_team_game_index(w)
        kc = out[out["team"] == "KC"]
        sf = out[out["team"] == "SF"]
        assert kc["team_game_index"].tolist() == [1, 2]
        assert sf["team_game_index"].tolist() == [1]
        assert sf["team_total_games"].iloc[0] == 1

    def test_duplicate_player_rows_same_team_week_do_not_duplicate_game_index_rows(self):
        # Many real players share a (season, team, week) -- the team-game
        # index is over DISTINCT team-weeks, not one row per player.
        w = self._weekly(
            [
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
                {"season": 2023, "week": 1, "team": "KC", "season_type": "REG"},
            ]
        )
        out = build_team_game_index(w)
        assert len(out) == 1

    def test_missing_required_column_raises(self):
        w = pd.DataFrame([{"season": 2023, "week": 1, "team": "KC"}])
        with pytest.raises(ValueError, match="missing required columns"):
            build_team_game_index(w)


def _schedule(rows):
    """rows: (season, week, gameday, home_team, away_team) -- REG game_type."""
    cols = ("season", "game_type", "week", "gameday", "home_team", "away_team")
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(
        [
            {"season": s, "game_type": "REG", "week": w, "gameday": g, "home_team": h, "away_team": a}
            for s, w, g, h, a in rows
        ]
    )


class TestHistoricalTeamCodeAliases:
    """Protects week1_kickoff_by_team()'s real, verified franchise-
    relocation alias resolution (Oakland->Las Vegas Raiders, St.
    Louis->Los Angeles Rams, San Diego->Los Angeles Chargers) -- added
    2026-07 after the real age (family #2) integration audit found 624
    historical predictor-table rows with a real players.csv birth_date
    match but no real Week-1 schedule match, and every one of them
    resolved to exactly these 3 real relocations (see
    research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md
    §11.7). This project's population always uses the CURRENT/
    canonical team code (LV/LA/LAC) for every historical season; the
    real nflverse schedule file uses whichever code was actually in
    use at the time (OAK/STL/SD pre-relocation)."""

    def test_relocation_case_resolves_to_historical_schedule_date(self):
        # Real 2015 pattern: population says "LA" (this project's
        # always-current convention) but the real 2015 schedule file
        # itself says "STL" (the Rams hadn't moved yet) -- must still
        # resolve to the real 2015 Week-1 kickoff date.
        sched = _schedule([(2015, 1, "2015-09-13", "STL", "SEA")])
        kickoff = week1_kickoff_by_team(sched, 2015)
        assert kickoff["LA"] == pd.Timestamp("2015-09-13")
        # The raw historical code itself must also still resolve (additive,
        # never a replacement).
        assert kickoff["STL"] == pd.Timestamp("2015-09-13")

    def test_all_three_verified_relocations_resolve(self):
        sched = _schedule(
            [
                (2019, 1, "2019-09-09", "OAK", "DEN"),  # Raiders, pre-move (moved 2020)
                (2015, 1, "2015-09-13", "STL", "SEA"),  # Rams, pre-move (moved 2016)
                (2016, 1, "2016-09-11", "SD", "KC"),  # Chargers, pre-move (moved 2017)
            ]
        )
        assert week1_kickoff_by_team(sched, 2019)["LV"] == pd.Timestamp("2019-09-09")
        assert week1_kickoff_by_team(sched, 2015)["LA"] == pd.Timestamp("2015-09-13")
        assert week1_kickoff_by_team(sched, 2016)["LAC"] == pd.Timestamp("2016-09-11")

    def test_post_relocation_season_needs_no_alias(self):
        # From the real, verified cutoff season onward, the real
        # schedule file itself already uses the current code directly
        # -- no aliasing needed, and none must be silently applied.
        sched = _schedule([(2020, 1, "2020-09-13", "LV", "CAR")])
        kickoff = week1_kickoff_by_team(sched, 2020)
        assert kickoff["LV"] == pd.Timestamp("2020-09-13")

    def test_alias_is_season_aware_not_applied_outside_its_real_range(self):
        # Real, found boundary: OAK's real alias range is 1999-2019
        # ONLY. A synthetic "OAK" row in season 2020 (never real --
        # the real 2020 schedule never has an "OAK" row at all) must
        # NOT be silently canonicalized to "LV" -- proves the alias
        # table is keyed by season, not just by code.
        sched = _schedule([(2020, 1, "2020-09-13", "OAK", "CAR")])
        kickoff = week1_kickoff_by_team(sched, 2020)
        assert "LV" not in kickoff
        assert kickoff["OAK"] == pd.Timestamp("2020-09-13")  # raw code itself still resolves

    def test_unverified_nonmatching_team_remains_absent_never_guessed(self):
        # Real, found case: MIA and TB's real Week-1 game in the 2017
        # season was postponed league-wide (Hurricane Irma) and never
        # replayed as a real Week 1 game -- there is no real Week-1
        # kickoff for either team that season. This is genuine missing
        # data, not a team-code mismatch, and must NEVER be guessed at
        # via the alias table (neither team is in it).
        sched = _schedule([(2017, 1, "2017-09-10", "KC", "NE")])  # some other real Week-1 game
        kickoff = week1_kickoff_by_team(sched, 2017)
        assert "MIA" not in kickoff
        assert "TB" not in kickoff

    def test_no_unrelated_team_season_changed(self):
        # A normal, non-relocated team's real kickoff must be entirely
        # unaffected by the alias machinery.
        sched = _schedule(
            [
                (2015, 1, "2015-09-13", "STL", "SEA"),
                (2015, 1, "2015-09-13", "KC", "HOU"),
            ]
        )
        kickoff = week1_kickoff_by_team(sched, 2015)
        assert kickoff["KC"] == pd.Timestamp("2015-09-13")
        assert kickoff["HOU"] == pd.Timestamp("2015-09-13")
        assert "SD" not in kickoff and "LAC" not in kickoff  # no cross-alias leakage

    def test_deterministic_across_repeated_calls(self):
        sched = _schedule(
            [
                (2015, 1, "2015-09-13", "STL", "SEA"),
                (2016, 1, "2016-09-11", "SD", "KC"),
                (2019, 1, "2019-09-09", "OAK", "DEN"),
            ]
        )
        first = {s: week1_kickoff_by_team(sched, s) for s in (2015, 2016, 2019)}
        second = {s: week1_kickoff_by_team(sched, s) for s in (2015, 2016, 2019)}
        assert first == second


class TestApplySourceCoverageNullMask:
    """Protects apply_source_coverage_null_mask() -- the CENTRALIZED
    coverage-remediation mechanism added 2026-07 for the Source A
    targets/receiving_air_yards 2006-2008 gap (see
    lib/dataset2/canonical_predictor_table.py's own
    SOURCE_A_TARGETS_UNRELIABLE_SRC_COLUMNS/_fam9_targets_dependent_columns()
    and research/dataset2/SOURCE_A_TARGETS_COVERAGE_REMEDIATION_AUDIT_2026_07.md),
    but written generically since this helper is meant to be reused by
    any future source-coverage remediation, not re-derived."""

    def test_float_column_masked_to_nan_for_affected_seasons(self):
        df = pd.DataFrame({"prediction_season": [2007, 2008, 2010], "x": [1.0, 2.0, 3.0]})
        out = apply_source_coverage_null_mask(df, ["x"], (2007, 2008), "prediction_season")
        assert pd.isna(out.loc[0, "x"])
        assert pd.isna(out.loc[1, "x"])
        assert out.loc[2, "x"] == 3.0

    def test_boolean_column_masked_to_na_not_false(self):
        df = pd.DataFrame({"prediction_season": [2007, 2010]})
        df["flag"] = pd.array([True, False], dtype="boolean")
        out = apply_source_coverage_null_mask(df, ["flag"], (2007,), "prediction_season")
        assert pd.isna(out.loc[0, "flag"])
        assert out["flag"].dtype == "boolean"
        assert out.loc[1, "flag"] == False  # noqa: E712 -- real, unaffected value untouched

    def test_unaffected_seasons_untouched(self):
        df = pd.DataFrame({"prediction_season": [2006, 2009, 2010], "x": [1.0, 2.0, 3.0]})
        out = apply_source_coverage_null_mask(df, ["x"], (2007, 2008, 2009), "prediction_season")
        assert out.loc[0, "x"] == 1.0  # 2006 -- not in the affected prediction-season set
        assert pd.isna(out.loc[1, "x"])  # 2009 -- affected
        assert out.loc[2, "x"] == 3.0  # 2010 -- resumes valid

    def test_multiple_columns_masked_together(self):
        df = pd.DataFrame({"prediction_season": [2008, 2010], "a": [1.0, 2.0], "b": [10.0, 20.0]})
        out = apply_source_coverage_null_mask(df, ["a", "b"], (2008,), "prediction_season")
        assert pd.isna(out.loc[0, "a"]) and pd.isna(out.loc[0, "b"])
        assert out.loc[1, "a"] == 2.0 and out.loc[1, "b"] == 20.0

    def test_raises_on_missing_season_column(self):
        df = pd.DataFrame({"x": [1.0]})
        with pytest.raises(ValueError, match="not in df.columns"):
            apply_source_coverage_null_mask(df, ["x"], (2007,), "prediction_season")

    def test_raises_on_missing_target_column(self):
        df = pd.DataFrame({"prediction_season": [2007]})
        with pytest.raises(ValueError, match="columns not in df"):
            apply_source_coverage_null_mask(df, ["does_not_exist"], (2007,), "prediction_season")

    def test_no_row_count_or_row_order_change(self):
        df = pd.DataFrame({"prediction_season": [2010, 2007, 2009], "x": [1.0, 2.0, 3.0]})
        out = apply_source_coverage_null_mask(df, ["x"], (2007, 2009), "prediction_season")
        assert list(out["prediction_season"]) == [2010, 2007, 2009]
        assert len(out) == 3


# --- Dataset 2 predictor-clustering discovery-fit boundary (approved 2026-07,
# locked commit 648ccad -- see docs/LEAGUE_WINNER_TRAITS_SPEC.md's
# "Predictor-clustering discovery/holdout boundary" section) ---


class TestValidateDataset2PredictorClusteringConfig:
    def test_real_committed_config_passes(self):
        config.validate_dataset2_predictor_clustering_config()  # should not raise

    def test_raises_when_start_not_strictly_less_than_end(self, monkeypatch):
        monkeypatch.setattr(config, "DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_START_SEASON", 2020)
        monkeypatch.setattr(config, "DATASET2_PREDICTOR_CLUSTERING_DISCOVERY_FIT_END_SEASON", 2020)
        with pytest.raises(ValueError, match="strictly less than"):
            config.validate_dataset2_predictor_clustering_config()

    def test_raises_when_historical_range_start_not_strictly_less_than_end(self, monkeypatch):
        monkeypatch.setattr(config, "DATASET2_PREDICTOR_CLUSTERING_HISTORICAL_RANGE_START_SEASON", 2025)
        monkeypatch.setattr(config, "DATASET2_PREDICTOR_CLUSTERING_HISTORICAL_RANGE_END_SEASON", 2025)
        with pytest.raises(ValueError, match="strictly less than"):
            config.validate_dataset2_predictor_clustering_config()


class TestFilterToDiscoveryFitPredictorRows:
    """Real methodology (commit 648ccad): fit population is
    prediction_season 2006-2020 inclusive, selected SOLELY on that
    column -- never outcome_join_status or any outcome/label/target/
    eligibility field, even if such a column happens to be present."""

    @staticmethod
    def _fixture():
        return pd.DataFrame(
            {
                "prediction_season": [2005, 2006, 2010, 2020, 2021, 2025, 2026],
                "player_id": ["p2005", "p2006", "p2010", "p2020", "p2021", "p2025", "p2026"],
                "position": ["WR"] * 7,
                "some_predictor": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
            }
        )

    def test_2006_included_inclusive_start_boundary(self):
        out = self._fixture().pipe(filter_to_discovery_fit_predictor_rows)
        assert "p2006" in list(out["player_id"])

    def test_2020_included_inclusive_end_boundary(self):
        out = self._fixture().pipe(filter_to_discovery_fit_predictor_rows)
        assert "p2020" in list(out["player_id"])

    def test_excludes_2005(self):
        out = self._fixture().pipe(filter_to_discovery_fit_predictor_rows)
        assert "p2005" not in list(out["player_id"])

    def test_excludes_2021(self):
        out = self._fixture().pipe(filter_to_discovery_fit_predictor_rows)
        assert "p2021" not in list(out["player_id"])

    def test_excludes_2025(self):
        out = self._fixture().pipe(filter_to_discovery_fit_predictor_rows)
        assert "p2025" not in list(out["player_id"])

    def test_excludes_2026(self):
        out = self._fixture().pipe(filter_to_discovery_fit_predictor_rows)
        assert "p2026" not in list(out["player_id"])

    def test_exact_selected_set(self):
        out = self._fixture().pipe(filter_to_discovery_fit_predictor_rows)
        assert list(out["player_id"]) == ["p2006", "p2010", "p2020"]

    def test_raises_on_missing_prediction_season_column(self):
        df = pd.DataFrame({"x": [1.0]})
        with pytest.raises(ValueError, match="prediction_season"):
            filter_to_discovery_fit_predictor_rows(df)

    def test_raises_on_null_prediction_season(self):
        df = pd.DataFrame({"prediction_season": [2006, None], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="null"):
            filter_to_discovery_fit_predictor_rows(df)

    def test_raises_on_non_numeric_prediction_season(self):
        df = pd.DataFrame({"prediction_season": ["2006", "2010"], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="numeric"):
            filter_to_discovery_fit_predictor_rows(df)

    def test_raises_on_boolean_prediction_season(self):
        """pandas classifies bool as numeric -- a plain is_numeric_dtype
        check alone would wrongly accept this."""
        df = pd.DataFrame({"prediction_season": [True, False], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="numeric"):
            filter_to_discovery_fit_predictor_rows(df)

    def test_raises_on_fractional_prediction_season(self):
        df = pd.DataFrame({"prediction_season": [2006.5, 2010.0], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="non-integer"):
            filter_to_discovery_fit_predictor_rows(df)

    def test_raises_on_positive_infinite_prediction_season(self):
        df = pd.DataFrame({"prediction_season": [2006.0, float("inf")], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="non-finite"):
            filter_to_discovery_fit_predictor_rows(df)

    def test_raises_on_negative_infinite_prediction_season(self):
        df = pd.DataFrame({"prediction_season": [2006.0, float("-inf")], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="non-finite"):
            filter_to_discovery_fit_predictor_rows(df)

    def test_does_not_mutate_input_dataframe(self):
        df = self._fixture()
        original = df.copy()
        filter_to_discovery_fit_predictor_rows(df)
        pd.testing.assert_frame_equal(df, original)

    def test_row_order_preserved(self):
        df = pd.DataFrame(
            {"prediction_season": [2020, 2006, 2015], "player_id": ["z", "a", "m"], "x": [1.0, 2.0, 3.0]}
        )
        out = filter_to_discovery_fit_predictor_rows(df)
        assert list(out["player_id"]) == ["z", "a", "m"]

    def test_columns_preserved(self):
        df = self._fixture()
        out = filter_to_discovery_fit_predictor_rows(df)
        assert list(out.columns) == list(df.columns)

    def test_selection_unaffected_by_synthetic_forbidden_columns_added_and_mutated(self):
        """The core outcome-independence proof: add
        outcome_join_status/label/target/eligibility-shaped columns,
        mutate them arbitrarily, and confirm row identity, seasons,
        count, and order never move -- proving the selector structurally
        ignores them rather than merely happening to today."""
        df = self._fixture()
        before = filter_to_discovery_fit_predictor_rows(df)

        mutated = df.copy()
        mutated["outcome_join_status"] = "no_outcome_row_matched"
        mutated["star_by_value_label"] = None
        mutated["star_outcome_eligible"] = False
        mutated["bust_primary_label"] = 1
        mutated["bust_primary_eligible"] = True
        after = filter_to_discovery_fit_predictor_rows(mutated)

        assert list(before["player_id"]) == list(after["player_id"])
        assert list(before["prediction_season"]) == list(after["prediction_season"])
        assert len(before) == len(after)

        # Even removing the synthetic outcome columns entirely (a row
        # subset with zero outcome-side data at all) must select the
        # identical rows.
        stripped = df.copy()
        stripped_only = filter_to_discovery_fit_predictor_rows(stripped)
        assert list(stripped_only["player_id"]) == list(before["player_id"])


class TestFilterToHistoricalPredictorRows:
    """Positive, explicit historical-range selector (2006-2025) --
    used ONLY as the discovery_fit_degenerate comparator population,
    never for clustering fit itself. Same malformed-input rejection
    and outcome-independence guarantees as
    TestFilterToDiscoveryFitPredictorRows above, proven independently
    here rather than assumed from the sibling function."""

    @staticmethod
    def _fixture():
        return pd.DataFrame(
            {
                "prediction_season": [2005, 2006, 2015, 2025, 2026],
                "player_id": ["p2005", "p2006", "p2015", "p2025", "p2026"],
                "position": ["WR"] * 5,
                "some_predictor": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        )

    def test_2006_included_inclusive_start_boundary(self):
        out = self._fixture().pipe(filter_to_historical_predictor_rows)
        assert "p2006" in list(out["player_id"])

    def test_2025_included_inclusive_end_boundary(self):
        out = self._fixture().pipe(filter_to_historical_predictor_rows)
        assert "p2025" in list(out["player_id"])

    def test_excludes_2005(self):
        out = self._fixture().pipe(filter_to_historical_predictor_rows)
        assert "p2005" not in list(out["player_id"])

    def test_excludes_2026(self):
        out = self._fixture().pipe(filter_to_historical_predictor_rows)
        assert "p2026" not in list(out["player_id"])

    def test_exact_selected_set(self):
        out = self._fixture().pipe(filter_to_historical_predictor_rows)
        assert list(out["player_id"]) == ["p2006", "p2015", "p2025"]

    def test_positive_definition_excludes_any_out_of_range_row_not_only_2026(self):
        """The core distinction from the earlier '!= 2026' comparator
        this replaces: ANY out-of-range value is excluded, not only
        the literal number 2026 -- proving this is a genuine positive
        bound, not a negative exclusion of one specific value."""
        df = pd.DataFrame(
            {
                "prediction_season": [2006, 2030, 1999],
                "player_id": ["real", "future_data_error", "past_data_error"],
                "x": [1.0, 2.0, 3.0],
            }
        )
        out = filter_to_historical_predictor_rows(df)
        assert list(out["player_id"]) == ["real"]

    def test_raises_on_missing_prediction_season_column(self):
        df = pd.DataFrame({"x": [1.0]})
        with pytest.raises(ValueError, match="prediction_season"):
            filter_to_historical_predictor_rows(df)

    def test_raises_on_null_prediction_season(self):
        df = pd.DataFrame({"prediction_season": [2006, None], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="null"):
            filter_to_historical_predictor_rows(df)

    def test_raises_on_non_numeric_prediction_season(self):
        df = pd.DataFrame({"prediction_season": ["2006", "2010"], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="numeric"):
            filter_to_historical_predictor_rows(df)

    def test_raises_on_boolean_prediction_season(self):
        df = pd.DataFrame({"prediction_season": [True, False], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="numeric"):
            filter_to_historical_predictor_rows(df)

    def test_raises_on_fractional_prediction_season(self):
        df = pd.DataFrame({"prediction_season": [2006.5, 2010.0], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="non-integer"):
            filter_to_historical_predictor_rows(df)

    def test_raises_on_infinite_prediction_season(self):
        df = pd.DataFrame({"prediction_season": [2006.0, float("inf")], "x": [1.0, 2.0]})
        with pytest.raises(ValueError, match="non-finite"):
            filter_to_historical_predictor_rows(df)

    def test_does_not_mutate_input_dataframe(self):
        df = self._fixture()
        original = df.copy()
        filter_to_historical_predictor_rows(df)
        pd.testing.assert_frame_equal(df, original)

    def test_row_order_preserved(self):
        df = pd.DataFrame(
            {"prediction_season": [2015, 2006, 2025], "player_id": ["z", "a", "m"], "x": [1.0, 2.0, 3.0]}
        )
        out = filter_to_historical_predictor_rows(df)
        assert list(out["player_id"]) == ["z", "a", "m"]

    def test_columns_preserved(self):
        df = self._fixture()
        out = filter_to_historical_predictor_rows(df)
        assert list(out.columns) == list(df.columns)

    def test_selection_unaffected_by_synthetic_forbidden_columns(self):
        df = self._fixture()
        before = filter_to_historical_predictor_rows(df)
        mutated = df.copy()
        mutated["outcome_join_status"] = "no_outcome_row_matched"
        mutated["star_by_value_label"] = None
        mutated["bust_primary_eligible"] = True
        after = filter_to_historical_predictor_rows(mutated)
        assert list(before["player_id"]) == list(after["player_id"])
        assert list(before["prediction_season"]) == list(after["prediction_season"])


class TestDerivePredictorWhitelistFromRegistry:
    def test_excludes_spine_columns(self):
        registry = pd.DataFrame(
            {
                "canonical_column": ["prediction_season", "player_id", "position", "observation_season", "fam1_experience_years"],
                "family_number": ["N/A (spine)", "N/A (spine)", "N/A (spine)", "N/A (spine)", "1"],
            }
        )
        assert derive_predictor_whitelist_from_registry(registry) == ["fam1_experience_years"]

    def test_does_not_blanket_ban_legitimate_predictor_side_eligible_named_columns(self):
        """Real predictor columns legitimately contain 'eligible' in
        their name (e.g. Family #9's efficiency_volume_eligible_*
        flags) -- a naive substring ban would wrongly exclude 60 real
        predictors from the whitelist. Exclusion must use the explicit
        registry classification, never name matching."""
        registry = pd.DataFrame(
            {
                "canonical_column": [
                    "player_id",
                    "fam9_team_final_4_qb_passing_efficiency_volume_eligible_exploratory",
                ],
                "family_number": ["N/A (spine)", "9"],
            }
        )
        whitelist = derive_predictor_whitelist_from_registry(registry)
        assert "fam9_team_final_4_qb_passing_efficiency_volume_eligible_exploratory" in whitelist

    def test_excludes_all_preseason_control_and_metadata_fields(self):
        market_fields = [
            "preseason_market_status",
            "preseason_market_status_sensitivity_30",
            "preseason_market_status_authority",
            "preseason_market_status_evidence_source",
            "preseason_market_status_evidence_summary",
        ]
        registry = pd.DataFrame({
            "canonical_column": market_fields + ["fam1_experience_years"],
            "family_number": [
                "N/A (preseason control)",
                "N/A (preseason metadata)",
                "N/A (preseason metadata)",
                "N/A (preseason metadata)",
                "N/A (preseason metadata)",
                "1",
            ],
        })
        assert derive_predictor_whitelist_from_registry(registry) == ["fam1_experience_years"]
        assert predictor_registry_role("N/A (preseason control)") == "control"
        assert predictor_registry_role("N/A (preseason metadata)") == "predictor_metadata"

    def test_legitimate_na_prefixed_cross_cutting_family_remains_a_predictor(self):
        registry = pd.DataFrame({
            "canonical_column": ["srcB_prior_season_offense_pct"],
            "family_number": ["N/A (Source B base variable, cross-cutting)"],
        })
        assert derive_predictor_whitelist_from_registry(registry) == ["srcB_prior_season_offense_pct"]

    def test_sorted_deterministic(self):
        registry = pd.DataFrame({"canonical_column": ["z_col", "a_col"], "family_number": ["1", "1"]})
        assert derive_predictor_whitelist_from_registry(registry) == ["a_col", "z_col"]

    def test_raises_on_missing_required_registry_columns(self):
        registry = pd.DataFrame({"canonical_column": ["x"]})
        with pytest.raises(ValueError):
            derive_predictor_whitelist_from_registry(registry)


class TestClassifyColumnConstancy:
    def test_varies(self):
        full = pd.DataFrame({"c": [1.0, 2.0, 3.0]})
        fit = pd.DataFrame({"c": [1.0, 2.0]})
        assert classify_column_constancy(full, fit, ["c"]) == {"c": "varies"}

    def test_universally_constant(self):
        full = pd.DataFrame({"c": [5.0, 5.0, 5.0]})
        fit = pd.DataFrame({"c": [5.0, 5.0]})
        assert classify_column_constancy(full, fit, ["c"]) == {"c": "universally_constant"}

    def test_discovery_fit_degenerate(self):
        full = pd.DataFrame({"c": [5.0, 5.0, 8.0]})  # real variance across the full range
        fit = pd.DataFrame({"c": [5.0, 5.0]})  # constant only within the discovery-fit window
        assert classify_column_constancy(full, fit, ["c"]) == {"c": "discovery_fit_degenerate"}

    def test_never_conflates_degenerate_with_universally_constant(self):
        full = pd.DataFrame({"deg": [1.0, 2.0], "const": [1.0, 1.0]})
        fit = pd.DataFrame({"deg": [1.0, 1.0], "const": [1.0, 1.0]})
        result = classify_column_constancy(full, fit, ["deg", "const"])
        assert result["deg"] == "discovery_fit_degenerate"
        assert result["const"] == "universally_constant"
        assert result["deg"] != result["const"]
