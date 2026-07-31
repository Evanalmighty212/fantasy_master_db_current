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
    receiving_epa, attempts, fantasy_points_ppr, receptions=0, receiving_yards_after_catch=0)."""
    cols = (
        "season", "player_id", "week", "team", "season_type", "targets", "carries", "rushing_yards",
        "receiving_yards", "receiving_air_yards", "passing_air_yards", "passing_epa", "rushing_epa",
        "receiving_epa", "attempts", "fantasy_points_ppr", "receptions", "receiving_yards_after_catch",
    )
    if not rows:
        return pd.DataFrame(columns=cols)
    # `receptions`/`receiving_yards_after_catch` are optional trailing
    # fields (default 0) so existing shorter fixtures throughout this
    # file don't all need updating just to add a new required input.
    padded = [tuple(r) + (0,) * (len(cols) - len(r)) for r in rows]
    return pd.DataFrame([dict(zip(cols, r)) for r in padded])


def _rb_weekly_rows(season, player_id, weeks, team, carries=10, ppg=10.0, receptions=2, receiving_yards_after_catch=3):
    return [
        (season, player_id, wk, team, "REG", 2, carries, carries * 4.0, 10.0, 5.0, 0.0, 0.0, 1.0, 0.5, 0, ppg, receptions, receiving_yards_after_catch)
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


_SCHEDULE_COLUMNS = ("season", "game_type", "week", "gameday", "home_team", "away_team")


def _schedule(rows):
    """rows: (season, week, gameday, home_team, away_team) -- REG game_type,
    matching build_experience_age_draft_traits()'s only real filter
    (kickoff_lookup_table() in lib/dataset2/common.py)."""
    if not rows:
        return pd.DataFrame(columns=_SCHEDULE_COLUMNS)
    return pd.DataFrame(
        [
            {"season": s, "game_type": "REG", "week": w, "gameday": g, "home_team": h, "away_team": a}
            for s, w, g, h, a in rows
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


def _build(pop, players, weekly, snaps=None, dc=None, schedule=None, window_ns=(4,)):
    if snaps is None:
        snaps = _snap_counts([])
    if dc is None:
        dc = _depth_chart([])
    if schedule is None:
        schedule = _schedule([])  # empty by default -> real, disclosed all-null age columns
    return build_canonical_predictor_table(pop, players, weekly, weekly, snaps, dc, schedule, window_ns=window_ns)


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
        # Family #2 (age) was removed from this tuple 2026-07 -- see
        # test_family_2_no_longer_in_deferred_families -- leaving
        # Source C and family #88's workload sub-signal.
        assert len(DEFERRED_FAMILIES) >= 2
        for entry in DEFERRED_FAMILIES:
            assert entry["reason"]
            assert len(entry["reason"]) > 20  # a real explanation, not a placeholder

    def test_age_columns_computed_from_real_schedule(self):
        # Family #2 (age) was moved from deferred to included 2026-07
        # once schedules.csv was fetched/pinned -- see
        # canonical_predictor_table.py's module docstring's AGE
        # INCLUSION section. A real schedule_df with a real Week-1
        # game for this player's team/season must produce a real,
        # non-null age value, computed the same way
        # experience_age_draft.py's own tests already prove.
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        schedule = _schedule([(2015, 1, "2015-09-13", "AAA", "ZZZ")])
        out, registry, deferred = _build(pop, players, weekly, schedule=schedule)
        row = out[out["prediction_season"] == 2015].iloc[0]
        expected_age = (pd.Timestamp("2015-09-13") - pd.Timestamp("1995-01-01")).days / 365.25
        assert row["fam2_age_at_week1_years"] == pytest.approx(expected_age)
        assert row["fam2_age_x_experience"] == pytest.approx(expected_age * row["fam1_experience_years"])
        assert {"fam2_age_at_week1_years", "fam2_age_x_experience", "fam2_age_position_z"} <= set(out.columns)

    def test_age_null_when_team_has_no_week1_game_in_schedule(self):
        # Real, disclosed missingness (never guessed): a team absent
        # from schedule_df's real Week-1 rows for that season leaves
        # age null, same MISSINGNESS POLICY as every other family here.
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)  # default empty schedule
        row = out[out["prediction_season"] == 2015].iloc[0]
        assert pd.isna(row["fam2_age_at_week1_years"])
        assert pd.isna(row["fam2_age_x_experience"])
        assert pd.isna(row["fam2_age_position_z"])

    def test_family_2_no_longer_in_deferred_families(self):
        assert not any(entry["family_number"] == "2" for entry in DEFERRED_FAMILIES)

    def test_no_workload_qualified_placeholder_column(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        assert "fam88_workload_qualified" not in out.columns
        assert "workload_qualified" not in out.columns

    def test_fam88_workload_core_present_and_computed(self):
        # Real 2014 season: P1 gets 10 carries/week + 2 receptions/week
        # x 16 real weeks -- prior_season_touches for the 2015
        # prediction_season row must equal the real 2014 total.
        pop = _population(
            (2014, "P1", "RB", "AAA", 16, 10.0, 20, 5),
            (2015, "P1", "RB", "AAA", 15, 12.0, 15, 3),
        )
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(
            _rb_weekly_rows(2014, "P1", AAA_2014_WEEKS, "AAA", carries=10, receptions=2)
            + _rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA")
        )
        out, registry, deferred = _build(pop, players, weekly)
        row_2015 = out[out["prediction_season"] == 2015].iloc[0]
        expected_carries = 10 * len(AAA_2014_WEEKS)
        expected_receptions = 2 * len(AAA_2014_WEEKS)
        assert row_2015["fam88_prior_season_touches"] == expected_carries + expected_receptions
        assert row_2015["fam88_prior_season_heavy_touch_workload"] == (
            (expected_carries + expected_receptions) >= 350
        )

    def test_fam88_workload_core_null_for_rookie_not_zero(self):
        # rookie_season == prediction_season -> no real season N-1 row
        # to lag from -- must be null, never a guessed zero.
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1998-01-01", 2015, 70, 210, 2015, 4, 100, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        row = out[out["prediction_season"] == 2015].iloc[0]
        assert pd.isna(row["fam88_prior_season_touches"])
        assert pd.isna(row["fam88_prior_season_heavy_touch_workload"])

    def test_fam88_workload_core_traded_player_aggregates_across_teams(self):
        # Real pattern: P1 traded mid-2014, real touches sum across
        # BOTH teams into one real prior-season total, no duplicate
        # (prediction_season, player_id) row created by the trade.
        pop = _population(
            (2014, "P1", "RB", "KC", 16, 8.0, 30, 8),
            (2015, "P1", "RB", "SF", 15, 9.0, 25, 6),
        )
        players = _players(("P1", "PfrP1", "1992-01-01", 2010, 70, 210, 2010, 4, 100, "KC"))
        weekly = _weekly(
            _rb_weekly_rows(2014, "P1", AAA_2014_WEEKS[:8], "KC", carries=10, receptions=1)
            + _rb_weekly_rows(2014, "P1", AAA_2014_WEEKS[8:], "SF", carries=8, receptions=1)
            + _rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "SF")
        )
        out, registry, deferred = _build(pop, players, weekly)
        assert out.duplicated(subset=["prediction_season", "player_id"]).sum() == 0
        row_2015 = out[out["prediction_season"] == 2015].iloc[0]
        n_kc, n_sf = len(AAA_2014_WEEKS[:8]), len(AAA_2014_WEEKS[8:])
        expected = (10 * n_kc + 1 * n_kc) + (8 * n_sf + 1 * n_sf)
        assert row_2015["fam88_prior_season_touches"] == expected

    def test_srca_prior_season_receptions_present(self):
        pop = _population(
            (2014, "P1", "RB", "AAA", 16, 10.0, 20, 5),
            (2015, "P1", "RB", "AAA", 16, 10.0, 20, 5),
        )
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2014, "P1", AAA_2014_WEEKS, "AAA", receptions=3) + _rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        row_2015 = out[out["prediction_season"] == 2015].iloc[0]
        assert row_2015["srcA_prior_season_receptions"] == 3 * len(AAA_2014_WEEKS)
        assert "srcA_prior_season_receptions" in set(registry["canonical_column"])

    def test_fam88_columns_registered(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        reg_idx = registry.set_index("canonical_column")
        for col in ("fam88_prior_season_touches", "fam88_prior_season_heavy_touch_workload"):
            assert col in reg_idx.index
            row = reg_idx.loc[col]
            assert row["family_number"] == "88 (split, part)"
            assert row["missingness_semantics"]
            assert row["dtype"]

    def test_fam88_heavy_touch_workload_is_nullable_boolean(self):
        pop = _population((2015, "P1", "RB", "AAA", 16, 10.0, 20, 5))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 70, 210, 2010, 3, 80, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2014, "P1", AAA_2014_WEEKS, "AAA") + _rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        assert out["fam88_prior_season_heavy_touch_workload"].dtype == "boolean"

    def test_fam18_receiving_efficiency_computed_from_real_season_totals(self):
        # Real 2014 season for P1: 5 targets/week, 3 receptions/week,
        # 10 receiving_yards/week, 3 receiving_yards_after_catch/week
        # x 16 real weeks. Season-total ratios must reflect the REAL
        # SUMMED totals, not a per-week average.
        pop = _population(
            (2014, "P1", "WR", "AAA", 16, 8.0, 40, 12),
            (2015, "P1", "WR", "AAA", 15, 9.0, 35, 10),
        )
        players = _players(("P1", "PfrP1", "1994-01-01", 2012, 72, 195, 2012, 4, 100, "AAA"))
        weekly = _weekly(
            [(2014, "P1", wk, "AAA", "REG", 5, 0, 0.0, 10.0, 6.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 3, 3) for wk in AAA_2014_WEEKS]
            + [(2015, "P1", wk, "AAA", "REG", 5, 0, 0.0, 10.0, 6.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 3, 3) for wk in AAA_2015_WEEKS]
        )
        out, registry, deferred = _build(pop, players, weekly)
        row_2015 = out[out["prediction_season"] == 2015].iloc[0]
        n_weeks = len(AAA_2014_WEEKS)
        expected_targets, expected_receptions = 5 * n_weeks, 3 * n_weeks
        expected_rec_yards, expected_yac = 10 * n_weeks, 3 * n_weeks
        assert row_2015["fam18_prior_season_catch_rate"] == pytest.approx(expected_receptions / expected_targets)
        assert row_2015["fam18_prior_season_receiving_yards_per_target"] == pytest.approx(expected_rec_yards / expected_targets)
        assert row_2015["fam18_prior_season_yac_per_reception"] == pytest.approx(expected_yac / expected_receptions)

    def test_fam18_null_for_rookie_not_zero(self):
        pop = _population((2015, "P1", "WR", "AAA", 16, 8.0, 40, 12))
        players = _players(("P1", "PfrP1", "1998-01-01", 2015, 72, 195, 2015, 4, 100, "AAA"))
        weekly = _weekly(
            [(2015, "P1", wk, "AAA", "REG", 5, 0, 0.0, 10.0, 6.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 3, 3) for wk in AAA_2015_WEEKS]
        )
        out, registry, deferred = _build(pop, players, weekly)
        row = out[out["prediction_season"] == 2015].iloc[0]
        assert pd.isna(row["fam18_prior_season_catch_rate"])
        assert pd.isna(row["fam18_prior_season_receiving_yards_per_target"])
        assert pd.isna(row["fam18_prior_season_yac_per_reception"])

    def test_fam18_null_for_zero_targets_source_coverage_gap(self):
        # A real prior-season row exists (population has 2014), but no
        # real weekly rows at all that season -- zero targets -> null
        # ratios, never a guessed 0.0.
        pop = _population(
            (2014, "P1", "WR", "AAA", 16, 8.0, 40, 12),
            (2015, "P1", "WR", "AAA", 15, 9.0, 35, 10),
        )
        players = _players(("P1", "PfrP1", "1994-01-01", 2012, 72, 195, 2012, 4, 100, "AAA"))
        weekly = _weekly([(2015, "P1", wk, "AAA", "REG", 5, 0, 0.0, 10.0, 6.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 3, 3) for wk in AAA_2015_WEEKS])
        out, registry, deferred = _build(pop, players, weekly)
        row_2015 = out[out["prediction_season"] == 2015].iloc[0]
        assert pd.isna(row_2015["fam18_prior_season_catch_rate"])
        assert pd.isna(row_2015["fam18_prior_season_receiving_yards_per_target"])
        assert pd.isna(row_2015["fam18_prior_season_yac_per_reception"])

    def test_fam18_traded_player_aggregates_across_teams_no_duplicate_rows(self):
        pop = _population(
            (2014, "P1", "WR", "KC", 16, 8.0, 30, 8),
            (2015, "P1", "WR", "SF", 15, 9.0, 25, 6),
        )
        players = _players(("P1", "PfrP1", "1993-01-01", 2011, 72, 195, 2011, 4, 100, "KC"))
        weekly = _weekly(
            [(2014, "P1", wk, "KC", "REG", 5, 0, 0.0, 10.0, 6.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 3, 3) for wk in AAA_2014_WEEKS[:8]]
            + [(2014, "P1", wk, "SF", "REG", 4, 0, 0.0, 8.0, 5.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 2, 2) for wk in AAA_2014_WEEKS[8:]]
            + [(2015, "P1", wk, "SF", "REG", 5, 0, 0.0, 10.0, 6.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 3, 3) for wk in AAA_2015_WEEKS]
        )
        out, registry, deferred = _build(pop, players, weekly)
        assert out.duplicated(subset=["prediction_season", "player_id"]).sum() == 0
        row_2015 = out[out["prediction_season"] == 2015].iloc[0]
        n_kc, n_sf = len(AAA_2014_WEEKS[:8]), len(AAA_2014_WEEKS[8:])
        expected_targets = 5 * n_kc + 4 * n_sf
        expected_receptions = 3 * n_kc + 2 * n_sf
        assert row_2015["fam18_prior_season_catch_rate"] == pytest.approx(expected_receptions / expected_targets)

    def test_fam18_columns_registered_and_denominators_preserved(self):
        pop = _population((2015, "P1", "WR", "AAA", 16, 8.0, 40, 12))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 72, 195, 2010, 4, 100, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        reg_idx = registry.set_index("canonical_column")
        for col in (
            "fam18_prior_season_catch_rate",
            "fam18_prior_season_receiving_yards_per_target",
            "fam18_prior_season_yac_per_reception",
        ):
            assert col in reg_idx.index
            assert reg_idx.loc[col, "family_number"] == "18"
            assert reg_idx.loc[col, "missingness_semantics"]
        # Denominator columns must remain separately present/auditable.
        assert "srcA_prior_season_targets" in out.columns
        assert "srcA_prior_season_receptions" in out.columns

    def test_fam18_no_threshold_or_classification_column(self):
        pop = _population((2015, "P1", "WR", "AAA", 16, 8.0, 40, 12))
        players = _players(("P1", "PfrP1", "1995-01-01", 2010, 72, 195, 2010, 4, 100, "AAA"))
        weekly = _weekly(_rb_weekly_rows(2015, "P1", AAA_2015_WEEKS, "AAA"))
        out, registry, deferred = _build(pop, players, weekly)
        fam18_cols = [c for c in out.columns if c.startswith("fam18_")]
        assert set(fam18_cols) == {
            "fam18_prior_season_catch_rate",
            "fam18_prior_season_receiving_yards_per_target",
            "fam18_prior_season_yac_per_reception",
        }

    def test_fam18_targets_unreliable_coverage_floor_applied_end_to_end(self):
        # Real, audited finding: observation season 2007 has an
        # unreliable real `targets` count -- prediction_season 2008
        # must be forced null for catch_rate/yards_per_target even
        # though real (garbage) counts would otherwise compute a
        # value, while yac_per_reception stays real and computed.
        pop = _population(
            (2007, "P1", "WR", "AAA", 16, 8.0, 40, 12),
            (2008, "P1", "WR", "AAA", 15, 9.0, 35, 10),
        )
        players = _players(("P1", "PfrP1", "1990-01-01", 2005, 72, 195, 2005, 4, 100, "AAA"))
        weekly = _weekly(
            [(2007, "P1", wk, "AAA", "REG", 1, 0, 0.0, 10.0, 6.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 3, 3) for wk in range(1, 17)]
            + [(2008, "P1", wk, "AAA", "REG", 5, 0, 0.0, 10.0, 6.0, 0.0, 0.0, 0.0, 1.0, 0, 8.0, 3, 3) for wk in range(1, 17)]
        )
        out, registry, deferred = _build(pop, players, weekly)
        row_2008 = out[out["prediction_season"] == 2008].iloc[0]
        assert pd.isna(row_2008["fam18_prior_season_catch_rate"])
        assert pd.isna(row_2008["fam18_prior_season_receiving_yards_per_target"])
        assert not pd.isna(row_2008["fam18_prior_season_yac_per_reception"])

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
