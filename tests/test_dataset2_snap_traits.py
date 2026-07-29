"""
tests/test_dataset2_snap_traits.py

Covers lib/dataset2/snap_traits.py -- Dataset 2 opportunity/usage
foundation, Source B. Protects:

1. Postseason rows excluded (same real bug class already found and
   fixed in Source A).
2. A real duplicate (gsis_id, game_id) row raises loudly rather than
   silently corrupting an aggregate.
3. An unmatched identity row is preserved in the raw layer but
   structurally contributes to no player's season aggregate.
4. `offense_pct` is RECOMPUTED from real summed numerator/denominator
   (max-based team-game total), never naively averaged.
5. `defense_pct`/`st_pct` are NOT output at all (deferred, per the
   real reconstruction-burden finding) -- but `defense_snaps`/
   `st_snaps` ARE output as plain sums.
6. `games_active` counts only real games with nonzero snap activity.
7. A traded player's `offense_pct` correctly follows them across teams.
8. The raw/season/preseason separation and its leakage-proof guarantee,
   mirroring Source A's tests exactly.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.dataset2 import snap_traits as st


def _snap_counts_df(*rows):
    cols = list(st.SNAP_COUNTS_REQUIRED_COLUMNS)
    return pd.DataFrame(list(rows), columns=cols)


def _snap_row(season, pfr_id, player, week, game_id, team, game_type="REG",
              offense_snaps=0, defense_snaps=0, st_snaps=0):
    return {
        "season": season, "week": week, "game_id": game_id, "game_type": game_type, "team": team,
        "pfr_player_id": pfr_id, "player": player,
        "offense_snaps": offense_snaps, "defense_snaps": defense_snaps, "st_snaps": st_snaps,
    }


def _players_df(*rows):
    cols = ["gsis_id", "pfr_id"]
    return pd.DataFrame(list(rows), columns=cols)


def _population_df(*rows):
    cols = ["season", "player_id", "position"]
    return pd.DataFrame(list(rows), columns=cols)


PLAYERS = _players_df(
    {"gsis_id": "00-a", "pfr_id": "PlayerA00"},
    {"gsis_id": "00-b", "pfr_id": "PlayerB00"},
)


class TestPostseasonExcluded:
    def test_post_row_excluded_from_raw_output(self):
        snaps = _snap_counts_df(
            _snap_row(2023, "PlayerA00", "Player A", 1, "g1", "ATL", game_type="REG", offense_snaps=50),
            _snap_row(2023, "PlayerA00", "Player A", 19, "g19", "ATL", game_type="WC", offense_snaps=999),
        )
        out = st.build_raw_player_game_snaps(snaps, PLAYERS)
        assert len(out) == 1
        assert out.iloc[0]["week"] == 1


class TestDuplicateGameRaisesLoudly:
    def test_duplicate_gsis_game_raises(self):
        snaps = _snap_counts_df(
            _snap_row(2023, "PlayerA00", "Player A", 1, "g1", "ATL", offense_snaps=50),
            _snap_row(2023, "PlayerA00", "Player A", 1, "g1", "ATL", offense_snaps=55),
        )
        with pytest.raises(RuntimeError, match="duplicate \\(gsis_id, game_id\\)"):
            st.build_raw_player_game_snaps(snaps, PLAYERS)


class TestUnmatchedRowPreservedInRawLayer:
    def test_unmatched_row_kept_with_null_gsis_id(self):
        snaps = _snap_counts_df(
            _snap_row(2023, "Unknown00", "Nobody Real", 1, "g1", "ATL", offense_snaps=10),
        )
        out = st.build_raw_player_game_snaps(snaps, PLAYERS)
        assert len(out) == 1
        assert pd.isna(out.iloc[0]["gsis_id"])


class TestOffensePctRecomputedNotAveraged:
    def test_asymmetric_volume_reveals_correct_vs_naive_average(self):
        snaps = _snap_counts_df(
            _snap_row(2023, "PlayerA00", "Player A", 1, "g1", "ATL", offense_snaps=10),
            _snap_row(2023, "PlayerB00", "Player B", 1, "g1", "ATL", offense_snaps=10),
            _snap_row(2023, "PlayerA00", "Player A", 2, "g2", "ATL", offense_snaps=1),
            _snap_row(2023, "PlayerB00", "Player B", 2, "g2", "ATL", offense_snaps=9),
        )
        raw = st.build_raw_player_game_snaps(snaps, PLAYERS)
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        out = st.build_season_snap_usage(pop, raw)
        # Real formula (verified against 2023 data): the team-game
        # denominator is MAX(offense_snaps) among that team's players
        # that game (the O-line/QB anchor plays every real snap), NOT
        # a sum across players. g1 max=10 (both players tied), g2
        # max=9 (PlayerB). Player A's correct season ratio:
        # (10+1) / (10+9) = 11/19.
        correct = 11 / 19
        naive_average = (1.0 + 1 / 9) / 2  # a naive average of weekly pct, wrong either way
        assert out.loc[0, "offense_pct"] == pytest.approx(correct)
        assert out.loc[0, "offense_pct"] != pytest.approx(naive_average, abs=1e-6)


class TestDefenseAndStPctNotOutput:
    def test_not_in_season_output_columns(self):
        assert "defense_pct" not in st.SEASON_OUTPUT_COLUMNS
        assert "st_pct" not in st.SEASON_OUTPUT_COLUMNS
        assert "defense_pct" not in st.PRESEASON_OUTPUT_COLUMNS
        assert "st_pct" not in st.PRESEASON_OUTPUT_COLUMNS

    def test_defense_and_st_snaps_still_summed(self):
        snaps = _snap_counts_df(
            _snap_row(2023, "PlayerA00", "Player A", 1, "g1", "ATL", defense_snaps=30, st_snaps=5),
            _snap_row(2023, "PlayerA00", "Player A", 2, "g2", "ATL", defense_snaps=25, st_snaps=3),
        )
        raw = st.build_raw_player_game_snaps(snaps, PLAYERS)
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "LB"})
        out = st.build_season_snap_usage(pop, raw)
        assert out.loc[0, "defense_snaps"] == 55
        assert out.loc[0, "st_snaps"] == 8


class TestGamesActive:
    def test_counts_only_real_nonzero_activity_games(self):
        snaps = _snap_counts_df(
            _snap_row(2023, "PlayerA00", "Player A", 1, "g1", "ATL", offense_snaps=50),
            _snap_row(2023, "PlayerA00", "Player A", 2, "g2", "ATL", offense_snaps=0, defense_snaps=0, st_snaps=0),
            _snap_row(2023, "PlayerA00", "Player A", 3, "g3", "ATL", st_snaps=2),
        )
        raw = st.build_raw_player_game_snaps(snaps, PLAYERS)
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        out = st.build_season_snap_usage(pop, raw)
        assert out.loc[0, "games_active"] == 2  # week 2 (all zero) excluded


class TestTradedPlayerFollowedCorrectly:
    def test_offense_pct_uses_each_games_own_real_team(self):
        snaps = _snap_counts_df(
            _snap_row(2023, "PlayerA00", "Player A", 1, "g1", "TEAM_A", offense_snaps=5),
            _snap_row(2023, "PlayerB00", "Player B", 1, "g1", "TEAM_A", offense_snaps=5),
            _snap_row(2023, "PlayerA00", "Player A", 3, "g3", "TEAM_B", offense_snaps=1),
            _snap_row(2023, "Other00", "Other Player", 3, "g3", "TEAM_B", offense_snaps=19),
        )
        players = _players_df(
            {"gsis_id": "00-a", "pfr_id": "PlayerA00"},
            {"gsis_id": "00-b", "pfr_id": "PlayerB00"},
            {"gsis_id": "00-c", "pfr_id": "Other00"},
        )
        raw = st.build_raw_player_game_snaps(snaps, players)
        pop = _population_df({"season": 2023, "player_id": "00-a", "position": "WR"})
        out = st.build_season_snap_usage(pop, raw)
        # player targets: 5+1=6. denominators: g1 TEAM_A max=5, g3 TEAM_B max=19 -> 24
        assert out.loc[0, "offense_snaps"] == 6
        assert out.loc[0, "offense_pct"] == pytest.approx(6 / 24)


class TestMissingnessAndZeroGames:
    def test_no_real_snap_rows_counts_zero_pct_null(self):
        pop = _population_df({"season": 2023, "player_id": "00-nowhere", "position": "WR"})
        raw = st.build_raw_player_game_snaps(_snap_counts_df(), PLAYERS)
        out = st.build_season_snap_usage(pop, raw)
        assert out.loc[0, "offense_snaps"] == 0
        assert pd.isna(out.loc[0, "offense_pct"])


class TestRowCountPreserved:
    def test_season_usage_one_row_per_population_row(self):
        pop = _population_df(
            {"season": 2023, "player_id": "00-a", "position": "WR"},
            {"season": 2023, "player_id": "00-b", "position": "RB"},
        )
        raw = st.build_raw_player_game_snaps(_snap_counts_df(), PLAYERS)
        out = st.build_season_snap_usage(pop, raw)
        assert len(out) == 2


def _season_usage_df(*rows):
    cols = list(st.SEASON_OUTPUT_COLUMNS)
    return pd.DataFrame(list(rows), columns=cols)


def _season_row(season, pid, position, offense_snaps=0.0, defense_snaps=0.0, st_snaps=0.0, games_active=0.0,
                 offense_pct=np.nan):
    return [season, pid, position, offense_snaps, defense_snaps, st_snaps, games_active, offense_pct]


class TestPreseasonLagCorrectness:
    def test_lags_all_fields_by_one_season(self):
        season = _season_usage_df(
            _season_row(2021, "00-a", "WR", offense_snaps=400, offense_pct=0.60),
            _season_row(2022, "00-a", "WR", offense_snaps=700, offense_pct=0.90),
        )
        out = st.build_preseason_snap_features(season)
        row_2022 = out[out["season"] == 2022].iloc[0]
        assert row_2022["prior_season_offense_snaps"] == 400
        assert row_2022["prior_season_offense_pct"] == pytest.approx(0.60)

    def test_no_plain_same_season_columns_in_output(self):
        season = _season_usage_df(_season_row(2022, "00-a", "WR", offense_snaps=700))
        out = st.build_preseason_snap_features(season)
        assert "offense_snaps" not in out.columns
        assert set(out.columns) == set(st.PRESEASON_OUTPUT_COLUMNS)

    def test_first_real_season_is_null(self):
        season = _season_usage_df(_season_row(2013, "00-a", "WR", offense_snaps=700, offense_pct=0.9))
        out = st.build_preseason_snap_features(season)
        assert pd.isna(out.loc[0, "prior_season_offense_snaps"])


class TestNoSameSeasonLeakage:
    def test_mutating_current_season_does_not_change_its_own_prior_season_feature(self):
        season_original = _season_usage_df(
            _season_row(2019, "00-a", "WR", offense_snaps=300, offense_pct=0.40),
            _season_row(2020, "00-a", "WR", offense_snaps=999, offense_pct=0.99),
        )
        out_original = st.build_preseason_snap_features(season_original)
        row_before = out_original[out_original["season"] == 2020].iloc[0]

        season_mutated = _season_usage_df(
            _season_row(2019, "00-a", "WR", offense_snaps=300, offense_pct=0.40),
            _season_row(2020, "00-a", "WR", offense_snaps=1, offense_pct=0.01),
        )
        out_mutated = st.build_preseason_snap_features(season_mutated)
        row_after = out_mutated[out_mutated["season"] == 2020].iloc[0]

        assert row_before["prior_season_offense_snaps"] == row_after["prior_season_offense_snaps"] == 300
        assert row_before["prior_season_offense_pct"] == row_after["prior_season_offense_pct"] == pytest.approx(0.40)

    def test_exhaustive_check_every_row_matches_real_prior_season_value(self):
        rows = []
        for pid in ["00-a", "00-b", "00-c"]:
            for season in range(2018, 2023):
                rows.append(_season_row(season, pid, "WR", offense_snaps=float(season * 10 + hash(pid) % 7)))
        season_df = _season_usage_df(*rows)
        out = st.build_preseason_snap_features(season_df)

        lookup = season_df.set_index(["season", "player_id"])["offense_snaps"]
        mismatches = 0
        for _, row in out.iterrows():
            prior_key = (row["season"] - 1, row["player_id"])
            if prior_key in lookup.index:
                if row["prior_season_offense_snaps"] != lookup.loc[prior_key]:
                    mismatches += 1
            else:
                if pd.notna(row["prior_season_offense_snaps"]):
                    mismatches += 1
        assert mismatches == 0


class TestRequiredColumnValidation:
    def test_raw_snaps_missing_column_raises(self):
        bad = pd.DataFrame({"season": [2023]})
        with pytest.raises(ValueError, match="snap_counts is missing required columns"):
            st.build_raw_player_game_snaps(bad, PLAYERS)

    def test_season_usage_missing_population_column_raises(self):
        bad_pop = pd.DataFrame({"season": [2023]})
        raw = st.build_raw_player_game_snaps(_snap_counts_df(), PLAYERS)
        with pytest.raises(ValueError, match="population is missing required columns"):
            st.build_season_snap_usage(bad_pop, raw)

    def test_preseason_missing_column_raises(self):
        bad = pd.DataFrame({"season": [2023]})
        with pytest.raises(ValueError, match="season_snap_usage is missing required columns"):
            st.build_preseason_snap_features(bad)
