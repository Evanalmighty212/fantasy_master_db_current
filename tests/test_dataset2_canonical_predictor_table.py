"""
tests/test_dataset2_canonical_predictor_table.py

Protects lib/dataset2/canonical_predictor_table.py -- the canonical
Dataset 2 PRESEASON PREDICTOR table (artifact 1 of
research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md's three-artifact
architecture). Real-data row/column counts, missingness breakdown, and
the deferred-family inventory are produced by
scripts/build_dataset2_canonical_predictor_table.py against the real
2006-2025 population, not by this file -- these tests prove grain,
leakage, and missingness/normalization correctness against small
synthetic fixtures, same convention as every other Dataset 2 test
module.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.canonical_predictor_table import DEFERRED_FAMILIES, build_canonical_predictor_table

AAA_2015_WEEKS = [wk for wk in range(1, 18) if wk != 9]
AAA_2014_WEEKS = list(range(1, 17))


def _population(*rows):
    """rows: (season, player_id, position, team, games_played, ppg_ppr, overall_finish_ppr, position_finish_ppr)."""
    cols = ("season", "player_id", "position", "team", "games_played", "ppg_ppr", "overall_finish_ppr", "position_finish_ppr")
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


def _players(*rows):
    """rows: (gsis_id, pfr_id, birth_date, rookie_season, height, weight, draft_year, draft_round, draft_pick, draft_team)."""
    cols = ("gsis_id", "pfr_id", "birth_date", "rookie_season", "height", "weight", "draft_year", "draft_round", "draft_pick", "draft_team")
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


def _weekly(rows):
    """rows: (season, player_id, week, team, season_type, targets, carries, rushing_yards,
    receiving_yards, receiving_air_yards, passing_air_yards, passing_epa, rushing_epa,
    receiving_epa, attempts, fantasy_points_ppr)."""
    cols = (
        "season", "player_id", "week", "team", "season_type", "targets", "carries", "rushing_yards",
        "receiving_yards", "receiving_air_yards", "passing_air_yards", "passing_epa", "rushing_epa",
        "receiving_epa", "attempts", "fantasy_points_ppr",
    )
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


def _rb_weekly_rows(season, player_id, weeks, team, carries=10, ppg=10.0):
    return [
        (season, player_id, wk, team, "REG", 2, carries, carries * 4.0, 10.0, 5.0, 0.0, 0.0, 1.0, 0.5, 0, ppg)
        for wk in weeks
    ]


_SNAP_COUNTS_COLUMNS = (
    "season", "week", "game_id", "game_type", "team", "opponent", "player", "pfr_player_id",
    "position", "offense_snaps", "offense_pct", "defense_snaps", "defense_pct", "st_snaps", "st_pct",
)


_SNAP_COUNTS_DTYPES = {
    "season": "int64", "week": "int64", "game_id": "object", "game_type": "object", "team": "object",
    "opponent": "object", "player": "object", "pfr_player_id": "object", "position": "object",
    "offense_snaps": "float64", "offense_pct": "float64", "defense_snaps": "float64", "defense_pct": "float64",
    "st_snaps": "float64", "st_pct": "float64",
}


def _snap_counts(rows):
    """rows: (season, week, team, pfr_player_id, offense_snaps, offense_pct)."""
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in _SNAP_COUNTS_DTYPES.items()})
    return pd.DataFrame(
        [
            {
                "season": s, "week": w, "game_id": f"{s}_{w}", "game_type": "REG", "team": t,
                "opponent": "ZZZ", "player": "Player", "pfr_player_id": pid, "position": "RB",
                "offense_snaps": snaps, "offense_pct": pct, "defense_snaps": 0, "defense_pct": 0.0,
                "st_snaps": 0, "st_pct": 0.0,
            }
            for s, w, t, pid, snaps, pct in rows
        ]
    )


_DEPTH_CHART_COLUMNS = ("season", "club_code", "week", "game_type", "formation", "gsis_id", "position", "depth_team")


def _depth_chart(rows):
    """rows: (season, club_code, week, gsis_id, position, depth_team)."""
    if not rows:
        return pd.DataFrame(columns=_DEPTH_CHART_COLUMNS)
    return pd.DataFrame(
        [
            {"season": s, "club_code": t, "week": w, "game_type": "REG", "formation": "Offense", "gsis_id": pid, "position": pos, "depth_team": rank}
            for s, t, w, pid, pos, rank in rows
        ]
    )


def _build(pop, players, weekly, snaps=None, dc=None, window_ns=(4,)):
    if snaps is None:
        snaps = _snap_counts([])
    if dc is None:
        dc = _depth_chart([])
    return build_canonical_predictor_table(pop, players, weekly, weekly, snaps, dc, window_ns=window_ns)


class TestGrainAudits:
    def test_exactly_one_row_per_prediction_season_player(self):
        pop = _population(
            (2014, "P1", "RB", "AAA", 16, 10.0, 20, 5),
            (2015, "P1", "RB", "AAA", 15, 12.0, 15, 3),
        )
        players = _players(("P1", "PfrP1", "1995-01-01", 2013, 70, 210, 2013, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA") + _rb_weekly_rows(2014, "P1", AAA_2014_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        assert out.duplicated(subset=["prediction_season", "player_id"]).sum() == 0

    def test_no_duplicate_canonical_column_names(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2013, 70, 210, 2013, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        assert len(out.columns) == len(set(out.columns))
        assert registry["canonical_column"].duplicated().sum() == 0

    def test_no_automatic_pandas_merge_suffixes(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2013, 70, 210, 2013, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        assert not any(c.endswith("_x") or c.endswith("_y") for c in out.columns)

    def test_rookie_retained_with_prior_season_missingness(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))  # rookie_season == 2015
        players = _players(("P1", "PfrP1", "1998-01-01", 2015, 70, 210, 2015, 4, 100, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        row = out[out["prediction_season"] == 2015].iloc[0]
        assert row["fam1_experience_years"] == 0  # real, known -- rookie season itself
        assert pd.isna(row["fam7_prior_overall_finish"])  # no prior season to lag from
        assert pd.isna(row["fam39_prior_season_games_played"])
        assert pd.isna(row["fam44_prior_changed_team"])  # never False for a rookie

    def test_minimal_market_cost_style_player_retained(self):
        # A real player-season pattern matching SBV's MMC population --
        # low games/production, still a real, retained predictor row.
        pop = _population((2015, "P1", "WR", "AAA", 3, 2.0, 250, 60))
        players = _players(("P1", "PfrP1", "1994-01-01", 2010, 72, 195, 2010, 7, 220, "AAA"))
        weekly = _weekly([(2015, "P1", wk, "AAA", "REG", 1, 0, 0.0, 5.0, 2.0, 0.0, 0.0, 0.0, 0.2, 0, 2.0) for wk in AAA_2015_WEEKS[-3:]])
        out, registry, deferred = _build(pop, players, weekly)
        assert len(out[(out["prediction_season"] == 2015) & (out["player_id"] == "P1")]) == 1

    def test_traded_player_retained_with_applicable_status_semantics(self):
        pop = _population((2023, "P1", "RB", "KC", 17, 8.0, 40, 12))
        players = _players(("P1", "PfrP1", "1996-01-01", 2019, 71, 215, 2019, 5, 150, "KC"))
        weekly = _weekly(
            [(2023, "P1", wk, "KC", "REG", 1, 5, 20.0, 5.0, 2.0, 0.0, 0.0, 0.5, 0.2, 0, 8.0) for wk in range(1, 10)]
            + [(2023, "P1", wk, "SF", "REG", 1, 5, 20.0, 5.0, 2.0, 0.0, 0.0, 0.5, 0.2, 0, 8.0) for wk in range(10, 19)]
        )
        out, registry, deferred = _build(pop, players, weekly)
        # Family #9's OWN observation happened during season 2023, so
        # its lagged predictors attach to prediction_season 2024, NOT
        # to 2023 (which is where population's own season-2023 context
        # -- fam7/fam8/etc, already pre-lagged -- lives instead).
        row = out[out["prediction_season"] == 2024].iloc[0]
        from lib.dataset2.partial_season_traits import TEAM_GAME_STATUS_UNAVAILABLE_TRADED
        assert row["fam9_team_game_window_status"] == TEAM_GAME_STATUS_UNAVAILABLE_TRADED
        assert pd.isna(row["fam9_team_final_4_points_per_team_game"])
        assert not pd.isna(row["fam9_active_final_4_games_ppg"])  # active-game basis never filters by team

    def test_future_prediction_season_row_retained_when_no_outcome_exists_yet(self):
        pop = _population((2025, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1998-01-01", 2020, 70, 210, 2020, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2025, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        future = out[out["prediction_season"] == 2026]
        assert len(future) == 1
        assert future.iloc[0]["fam9_prediction_season_outcome_unavailable"] == True  # noqa: E712
        assert not pd.isna(future.iloc[0]["fam9_team_final_4_points_per_team_game"])
        # Every OTHER family correctly null -- nothing knowable about 2026 yet.
        assert pd.isna(future.iloc[0]["fam7_prior_overall_finish"])
        assert pd.isna(future.iloc[0]["fam1_experience_years"])

    def test_no_phantom_future_row_for_a_player_whose_own_last_season_predates_dataset_max(self):
        # Real bug found running against the full real 2006-2025
        # population: P1's last real season is 2015, but the DATASET's
        # overall max season (from P2) is 2016 -- P1 must NOT get a
        # phantom prediction_season=2016 row just because family #9
        # would happily lag their 2015 observation forward; that
        # "future" concept is reserved for the dataset's own real
        # max season, not every individual player's personal last one.
        pop = _population(
            (2015, "P1", "RB", "AAA", 16, 10.0, 20, 5),
            (2016, "P2", "WR", "AAA", 16, 8.0, 30, 8),
        )
        players = _players(
            ("P1", "PfrP1", "1990-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"),
            ("P2", "PfrP2", "1994-01-01", 2014, 73, 195, 2014, 4, 100, "AAA"),
        )
        weekly = _weekly(
            _rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA")
            + [(2016, "P2", wk, "AAA", "REG", 5, 0, 0.0, 30.0, 15.0, 0.0, 0.0, 0.0, 1.5, 0, 8.0) for wk in range(1, 17)]
        )
        out, registry, deferred = _build(pop, players, weekly)
        assert len(out[(out["prediction_season"] == 2016) & (out["player_id"] == "P1")]) == 0
        assert len(out[(out["prediction_season"] == 2017) & (out["player_id"] == "P2")]) == 1


class TestLeakage:
    def test_no_same_season_value_enters_a_lagged_predictor_column(self):
        # Season 2015's own overall_finish_ppr (15) must never appear as
        # 2015's OWN fam7_prior_overall_finish -- only 2014's (20) may.
        pop = _population(
            (2014, "P1", "RB", "AAA", 16, 10.0, 20, 5),
            (2015, "P1", "RB", "AAA", 15, 12.0, 15, 3),
        )
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA") + _rb_weekly_rows(2014, "P1", AAA_2014_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        row_2015 = out[out["prediction_season"] == 2015].iloc[0]
        assert row_2015["fam7_prior_overall_finish"] == 20  # 2014's real value
        assert row_2015["fam7_prior_overall_finish"] != 15  # never 2015's own value

    def test_mutating_observation_season_only_moves_the_correct_family9_row(self):
        pop = _population(
            (2014, "P1", "RB", "AAA", 16, 10.0, 20, 5),
            (2015, "P1", "RB", "AAA", 15, 12.0, 15, 3),
        )
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))

        weekly_baseline = _weekly(
            _rb_weekly_rows(2014, "P1", AAA_2014_WEEKS, "AAA", carries=5, ppg=5.0)
            + _rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA", carries=7, ppg=7.0)
        )
        weekly_mutated = _weekly(
            _rb_weekly_rows(2014, "P1", AAA_2014_WEEKS, "AAA", carries=5, ppg=5.0)
            + _rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA", carries=99, ppg=99.0)
        )
        out_baseline, _, _ = _build(pop, players, weekly_baseline)
        out_mutated, _, _ = _build(pop, players, weekly_mutated)

        rate_base = out_baseline.set_index("prediction_season")["fam9_team_final_4_points_per_team_game"]
        rate_mut = out_mutated.set_index("prediction_season")["fam9_team_final_4_points_per_team_game"]
        # prediction_season 2015's fam9 row is sourced from family #9's
        # OWN observation of season 2014 (unaffected by season 2015's
        # mutation); prediction_season 2016 is sourced from season
        # 2015's (mutated) observation.
        assert rate_base[2015] == rate_mut[2015]
        assert rate_base[2016] != rate_mut[2016]


class TestMissingnessAndNormalization:
    def test_boolean_columns_are_nullable_boolean_dtype(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        for col in ("fam44_prior_changed_team",):
            assert out[col].dtype == "boolean", col

    def test_source_not_yet_covered_is_null_not_zero(self):
        # Season 2015's prior_season (2014) has zero real Source B rows
        # for this player because snap_counts real coverage starts
        # 2013 -- but here we simulate a season BEFORE any snap
        # coverage at all was passed in (empty snap_counts).
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly, snaps=_snap_counts([]))
        row = out[out["prediction_season"] == 2015].iloc[0]
        assert pd.isna(row["srcB_prior_season_offense_snaps"])

    def test_deferred_families_inventory_has_a_real_reason_each(self):
        assert len(DEFERRED_FAMILIES) >= 3
        for entry in DEFERRED_FAMILIES:
            assert entry["reason"]
            assert len(entry["reason"]) > 20  # a real explanation, not a placeholder

    def test_no_age_columns_present(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        excluded = {"fam2_age_at_week1_years", "fam2_age_x_experience", "fam2_age_position_z"}
        assert not (excluded & set(out.columns))

    def test_no_workload_qualified_placeholder_column(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        assert "fam88_workload_qualified" not in out.columns

    def test_position_inapplicable_flag_reads_as_scoped_not_ordinary_missing(self):
        # A WR's QB-passing-role columns must be recognized as
        # position-inapplicable, not lumped in with ordinary missing
        # data, per the registry's own position_scope field.
        pop = _population((2015, "P1", "WR", "AAA", 16, 8.0, 60, 15))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 73, 195, 2010, 4, 100, "AAA"))
        weekly = _weekly([(2015, "P1", wk, "AAA", "REG", 5, 0, 0.0, 40.0, 20.0, 0.0, 0.0, 0.0, 2.0, 0, 8.0) for wk in AAA_2015_WEEKS])
        out, registry, deferred = _build(pop, players, weekly)
        qb_col = "fam9_active_final_4_qb_passing_role_present"
        assert qb_col in out.columns
        row = out[out["prediction_season"] == 2015].iloc[0]
        assert pd.isna(row[qb_col])  # real, for a WR -- but SCOPED, not ordinary missing
        scope = registry.set_index("canonical_column").loc[qb_col, "position_scope"]
        assert scope == "QB"

    def test_team_broadcast_column_scoped_all_not_qb(self):
        # Real, found exception: fam86_team_qb_uncertainty's name
        # contains "qb" but it's broadcast to every position on the
        # team, per fragility_traits.py's own docstring -- must not be
        # misclassified as QB-only.
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        scope = registry.set_index("canonical_column").loc["fam86_team_qb_uncertainty", "position_scope"]
        assert scope == "ALL"


class TestColumnRegistry:
    def test_every_output_column_except_identity_has_a_registry_row(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        registered = set(registry["canonical_column"])
        assert set(out.columns) <= registered

    def test_registry_rows_have_required_fields_populated(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        for col in ("family_number", "family_name", "source", "dtype", "missingness_semantics", "observation_type"):
            assert registry[col].notna().all(), col


class TestDeterminism:
    def test_rebuild_from_identical_inputs_produces_identical_content_and_column_order(self):
        pop = _population(
            (2014, "P1", "RB", "AAA", 16, 10.0, 20, 5),
            (2015, "P1", "RB", "AAA", 15, 12.0, 15, 3),
            (2015, "P2", "WR", "AAA", 10, 6.0, 90, 25),
        )
        players = _players(
            ("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"),
            ("P2", "PfrP2", "1997-01-01", 2013, 73, 190, 2013, 5, 150, "AAA"),
        )
        weekly = _weekly(
            _rb_weekly_rows(2014, "P1", AAA_2014_WEEKS, "AAA")
            + _rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA")
            + [(2015, "P2", wk, "AAA", "REG", 5, 0, 0.0, 40.0, 20.0, 0.0, 0.0, 0.0, 2.0, 0, 6.0) for wk in AAA_2015_WEEKS]
        )
        out1, reg1, def1 = _build(pop, players, weekly)
        out2, reg2, def2 = _build(pop, players, weekly)
        assert list(out1.columns) == list(out2.columns)
        pd.testing.assert_frame_equal(out1, out2)
        assert list(reg1["canonical_column"]) == list(reg2["canonical_column"])
