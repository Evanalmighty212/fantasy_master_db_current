"""
tests/test_dataset2_canonical_outcome_table.py

Protects lib/dataset2/canonical_outcome_table.py -- artifact 2 of the
three-artifact architecture (research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md
§1a). Proves the four separate outcome-eligibility universes (Star,
primary bust, bust historical sensitivity, underperformance
diagnostic) are genuinely distinct, that every real bug class found
during review is fixed (below-gate rows get a real False label, not
null; the zero-game real-ADP row is primary-bust eligible; MMC is
bust-ineligible but diagnostic-eligible; the
expected-production-out-of-range rows are bust-eligible but
diagnostic-ineligible), that every ineligible outcome carries exactly
one reason code while every eligible one carries none, AND -- per the
2026-07 label-implementation round -- that the approved bust-label
formula (research/dataset2/DATASET2_BUST_LABEL_OPERATIONALIZATION_PROPOSAL_2026_07.md
§23) is computed correctly: era-specific vs. pooled-era-fallback cell
selection at the exact minimum-sample boundary, the G-raw
lookup-gap fallback, the automatic zero-game rule, tie handling, input-
order independence, and that bust_historical_sensitivity_label stays
reserved (not computed this round).
"""

import sys
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE
from lib.dataset2.canonical_outcome_table import (
    ASSIGNMENT_METHOD_AUTOMATIC_ZERO_GAME,
    ASSIGNMENT_METHOD_ERA_SPECIFIC,
    ASSIGNMENT_METHOD_G_RAW_LOOKUP_GAP_FALLBACK,
    ASSIGNMENT_METHOD_POOLED_ERA_FALLBACK,
    OUTCOME_OUTPUT_COLUMNS,
    build_canonical_outcome_table,
)

DRIVER_SPEC = importlib.util.spec_from_file_location(
    "dataset2_outcome_driver",
    Path(__file__).resolve().parent.parent / "scripts/build_dataset2_canonical_outcome_table.py",
)
outcome_driver = importlib.util.module_from_spec(DRIVER_SPEC)
DRIVER_SPEC.loader.exec_module(outcome_driver)


def _master(*rows):
    """rows: (season, player_id, position, overall_adp, games_played).
    games_played defaults to 10 (a normal, non-zero season) if a
    4-tuple is passed, for brevity in tests that don't care about it."""
    cols = ("season", "player_id", "position", "overall_adp", "games_played")
    out_rows = []
    for r in rows:
        if len(r) == 4:
            s, p, pos, adp = r
            gp = 10
        else:
            s, p, pos, adp, gp = r
        out_rows.append({
            "season": s, "player_id": p, "position": pos,
            "canonical_position_status": "adp_source",
            "canonical_position_authority": "adp_source_position",
            "overall_adp": adp, "games_played": gp, "lwi_score": 0.0,
        })
    if not out_rows:
        return pd.DataFrame(columns=cols + ("canonical_position_status", "canonical_position_authority"))
    return pd.DataFrame(out_rows)


def _sbv(*rows):
    """rows: (season, player_id, status, score, label)."""
    cols = ("season", "player_id", "star_by_value_status", "star_by_value_score", "star_by_value_label")
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(
        [{"season": s, "player_id": p, "star_by_value_status": st, "star_by_value_score": sc, "star_by_value_label": lb} for s, p, st, sc, lb in rows]
    )


def _players(*rows):
    """rows: (gsis_id, draft_round)."""
    cols = ("gsis_id", "draft_round")
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([{"gsis_id": g, "draft_round": dr} for g, dr in rows])


def _ep_lookup(*rows):
    """rows: (season, position, draft_round, expected_production)."""
    cols = ("prediction_season", "position", "draft_round", "expected_production")
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(
        [{"prediction_season": s, "position": pos, "draft_round": dr, "expected_production": ep} for s, pos, dr, ep in rows]
    )


def _production(*rows):
    """rows: (season, player_id, P)."""
    cols = ("season", "player_id", "P")
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([{"season": s, "player_id": p, "P": prod} for s, p, prod in rows])


class TestStarOutcome:
    def test_below_production_gate_gets_real_false_label_not_missing(self):
        master = _master((2015, "P1", "RB", 20.0))
        sbv = _sbv((2015, "P1", "below_production_gate", None, 0))
        players = _players(("P1", 3))
        ep_lookup = _ep_lookup((2015, "RB", 2, 50.0))
        production = _production((2015, "P1", 10.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["star_outcome_eligible"] == True  # noqa: E712
        assert row["star_by_value_label"] == False  # noqa: E712
        assert not pd.isna(row["star_by_value_label"])
        assert row["sbv_score_available"] == False  # noqa: E712
        assert pd.isna(row["star_by_value_score"])

    def test_scored_row_has_real_score_and_label(self):
        master = _master((2015, "P1", "WR", 5.0))
        sbv = _sbv((2015, "P1", "adp_scored", 42.0, 1))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup((2015, "WR", 1, 30.0))
        production = _production((2015, "P1", 60.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["star_outcome_eligible"] == True  # noqa: E712
        assert row["star_by_value_label"] == True  # noqa: E712
        assert row["sbv_score_available"] == True  # noqa: E712
        assert row["star_by_value_score"] == 42.0


def test_primary_bust_production_receives_canonical_position_and_reranked_finish(monkeypatch):
    captured = {}

    def fake_compute(frame):
        captured["frame"] = frame.copy()
        return frame[["season", "player_id"]].assign(P=1.0)

    monkeypatch.setattr(outcome_driver.prod, "compute_production", fake_compute)
    master = pd.DataFrame([{
        "season": 2019, "player_id": "00-0035624", "position": "WR",
        "canonical_fantasy_position": "WR", "canonical_position_status": "approved_override",
        "canonical_position_authority": "Evan-approved season-specific treatment",
        "games_played": 7, "fantasy_points_ppr": 100.0, "ppg_ppr": 100 / 7,
        "position_finish_ppr": 123, "data_quality_flag": "matched_clean",
    }])
    outcome_driver._compute_production(master)
    supplied = captured["frame"].iloc[0]
    assert supplied["position"] == "WR"
    assert supplied["position_finish_ppr"] == 123

def test_ineligible_star_row_has_null_label_not_false():
    master = _master((2008, "P1", "QB", 10.0))
    sbv = _sbv((2008, "P1", "out_of_scope", None, None))
    players = _players(("P1", 1))
    ep_lookup = _ep_lookup()
    production = _production((2008, "P1", 40.0))
    out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
    row = out.iloc[0]
    assert row["star_outcome_eligible"] == False  # noqa: E712
    assert pd.isna(row["star_by_value_label"])
    assert row["star_outcome_ineligibility_reason"] == "out_of_scope_temporal_window"


class TestBustPrimaryAndHistoricalSensitivity:
    def test_zero_game_real_adp_row_is_primary_bust_eligible(self):
        # No matching SBV row at all -- real_status becomes
        # no_sbv_row_found -- but real market ADP makes it eligible.
        master = _master((2025, "P1", "RB", 158.83, 0))
        sbv = _sbv()
        players = _players(("P1", None))
        ep_lookup = _ep_lookup()
        production = _production()
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["real_status"] == "no_sbv_row_found"
        assert row["bust_primary_eligible"] == True  # noqa: E712
        assert row["bust_primary_ineligibility_reason"] is None

    def test_zero_game_drafted_no_adp_is_not_primary_bust_eligible(self):
        master = _master((2021, "P1", "WR", None, 0))
        sbv = _sbv()
        players = _players(("P1", 2))  # real NFL draft capital, no fantasy ADP
        ep_lookup = _ep_lookup()
        production = _production()
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_eligible"] == False  # noqa: E712
        assert row["bust_primary_ineligibility_reason"] == "zero_games_nfl_draft_capital_not_fantasy_adp"

    def test_zero_game_no_cost_signal_at_all(self):
        master = _master((2021, "P1", "TE", None, 0))
        sbv = _sbv()
        players = _players(("P1", None))
        ep_lookup = _ep_lookup()
        production = _production()
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_ineligibility_reason"] == "zero_games_no_valid_cost_signal"

    def test_mmc_excluded_from_bust_but_diagnostic_eligible(self):
        master = _master((2015, "P1", "RB", None))
        sbv = _sbv((2015, "P1", "minimal_market_cost_scored", 5.0, 0))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup()
        production = _production((2015, "P1", 8.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_eligible"] == False  # noqa: E712
        assert row["bust_primary_ineligibility_reason"] == "mmc_no_real_adp_round_peer_group"
        assert row["bust_historical_sensitivity_eligible"] == False  # noqa: E712
        assert row["underperformance_diagnostic_eligible"] == True  # noqa: E712
        assert not pd.isna(row["underperformance_diagnostic_value"])

    def test_ep_out_of_range_bust_eligible_but_diagnostic_ineligible(self):
        # Real ADP resolves to round 9, but the fitted lookup has no
        # cell for (2025, RB, 9) -- real cost known, E_P unavailable.
        master = _master((2020, "P1", "RB", 100.0))  # adp_round = ceil(100/12) = 9
        sbv = _sbv((2020, "P1", "unscoreable_expected_production_out_of_range", None, None))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup((2020, "RB", 1, 80.0))  # round 9 not covered
        production = _production((2020, "P1", 50.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_eligible"] == True  # noqa: E712
        assert row["bust_primary_ineligibility_reason"] is None
        assert row["underperformance_diagnostic_eligible"] == False  # noqa: E712
        assert row["underperformance_diagnostic_ineligibility_reason"] == "expected_production_lookup_out_of_range"
        assert pd.isna(row["underperformance_diagnostic_value"])

    def test_below_gate_real_adp_out_of_range_also_diagnostic_ineligible(self):
        # Real, found in the operationalization round: a
        # below_production_gate real-ADP row can ALSO have an
        # out-of-range round -- must not be extrapolated around, same
        # as the ep_out_of_range status.
        master = _master((2020, "P1", "WR", 200.0))  # adp_round = ceil(200/12) = 17
        sbv = _sbv((2020, "P1", "below_production_gate", None, 0))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup((2020, "WR", 1, 90.0))  # round 17 not covered
        production = _production((2020, "P1", 5.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_eligible"] == True  # noqa: E712 -- real ADP still grants bust eligibility
        assert row["underperformance_diagnostic_eligible"] == False  # noqa: E712
        assert row["underperformance_diagnostic_ineligibility_reason"] == "expected_production_lookup_out_of_range"

    def test_pre_2010_real_adp_excluded_from_primary_but_included_in_historical_sensitivity(self):
        master = _master((2008, "P1", "RB", 15.0))
        sbv = _sbv((2008, "P1", "out_of_scope", None, None))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup()
        production = _production((2008, "P1", 30.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_eligible"] == False  # noqa: E712
        assert row["bust_primary_ineligibility_reason"] == "pre_2010_temporal_window_real_adp"
        assert row["bust_historical_sensitivity_eligible"] == True  # noqa: E712
        assert row["bust_historical_sensitivity_ineligibility_reason"] is None
        # Historical-sensitivity label VALUES were not in scope this
        # round -- stays reserved/null even for an eligible row.
        assert pd.isna(row["bust_historical_sensitivity_label"])

    def test_ineligible_bust_label_is_null_not_false(self):
        master = _master((2021, "P1", "TE", None, 0))
        sbv = _sbv()
        players = _players(("P1", None))
        ep_lookup = _ep_lookup()
        production = _production()
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert pd.isna(row["bust_primary_label"])
        assert pd.isna(row["bust_primary_sensitivity_pct25_label"])
        assert pd.isna(row["bust_primary_sensitivity_pct30_label"])
        assert pd.isna(row["bust_strict_below_replacement_label"])
        assert pd.isna(row["bust_historical_sensitivity_label"])
        assert row["bust_primary_assignment_method"] is None or pd.isna(row["bust_primary_assignment_method"])


class TestZeroGameAutomaticRule:
    """The generalized zero-game rule (proposal §22): any
    bust_primary_eligible row with games_played == 0 is an automatic
    bust at every threshold, including strict-below-replacement, via
    the real replacement-level argument -- never a player-specific
    override, keyed purely on games_played == 0."""

    def _build(self):
        master = _master((2025, "ZG", "RB", 158.83, 0))
        sbv = _sbv()
        players = _players(("ZG", None))
        ep_lookup = _ep_lookup()
        production = _production()
        return build_canonical_outcome_table(master, sbv, players, ep_lookup, production).iloc[0]

    def test_automatic_true_at_every_primary_threshold(self):
        row = self._build()
        assert row["bust_primary_label"] == True  # noqa: E712
        assert row["bust_primary_sensitivity_pct25_label"] == True  # noqa: E712
        assert row["bust_primary_sensitivity_pct30_label"] == True  # noqa: E712

    def test_automatic_true_for_strict_below_replacement_too(self):
        row = self._build()
        assert row["bust_strict_below_replacement_label"] == True  # noqa: E712

    def test_assignment_method_is_automatic_zero_game(self):
        row = self._build()
        assert row["bust_primary_assignment_method"] == ASSIGNMENT_METHOD_AUTOMATIC_ZERO_GAME

    def test_rule_is_general_not_player_specific(self):
        # A second, differently-named zero-game real-ADP row must get
        # identical treatment -- proves this is a mechanical rule keyed
        # on games_played == 0, not a hardcoded player check.
        master = _master((2024, "SOMEONE_ELSE", "WR", 190.0, 0))
        sbv = _sbv()
        players = _players(("SOMEONE_ELSE", None))
        out = build_canonical_outcome_table(master, sbv, players, _ep_lookup(), _production())
        row = out.iloc[0]
        assert row["bust_primary_label"] == True  # noqa: E712
        assert row["bust_strict_below_replacement_label"] == True  # noqa: E712
        assert row["bust_primary_assignment_method"] == ASSIGNMENT_METHOD_AUTOMATIC_ZERO_GAME


class TestEraFallbackAtExactBoundary:
    """Proposal §20 Method 4: a real (position, ADP bucket, era) cell
    below DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE falls back to the
    pooled (position, ADP bucket) ranking, era ignored. Tested at the
    EXACT boundary: one cell with n == MIN_N (era-specific), one with
    n == MIN_N - 1 (falls back)."""

    def test_exact_boundary_era_specific_vs_fallback(self):
        min_n = DATASET2_ANALYSIS_MIN_CELL_SAMPLE_SIZE
        rows_master = []
        rows_sbv = []
        rows_players = []
        rows_ep = [(2015, "RB", 7, 50.0), (2010, "RB", 7, 50.0)]  # E_P cells for both real seasons used below
        rows_production = []

        # era "2011-2020" cell: exactly min_n rows -- era_specific_g_score
        for i in range(min_n):
            pid = f"ERA_OK_{i}"
            rows_master.append((2015, pid, "RB", 80.0))  # adp_round = ceil(80/12) = 7 -> bucket R6-10
            rows_sbv.append((2015, pid, "adp_scored", 10.0, 1))
            rows_players.append((pid, None))
            rows_production.append((2015, pid, 50.0 + i))  # distinct P values, no ties

        # era "pre-2011" cell (season 2010, only season < 2011 that's
        # still >= SBV_FIRST_SCOREABLE_SEASON so bust_primary_eligible
        # holds): exactly min_n - 1 rows -- pooled_era_g_score_fallback
        for i in range(min_n - 1):
            pid = f"ERA_SPARSE_{i}"
            rows_master.append((2010, pid, "RB", 80.0))
            rows_sbv.append((2010, pid, "adp_scored", 10.0, 1))
            rows_players.append((pid, None))
            rows_production.append((2010, pid, 50.0 + i))

        master = _master(*rows_master)
        sbv = _sbv(*rows_sbv)
        players = _players(*rows_players)
        ep_lookup = _ep_lookup(*rows_ep)
        production = _production(*rows_production)
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)

        ok_rows = out[out["player_id"].str.startswith("ERA_OK_")]
        sparse_rows = out[out["player_id"].str.startswith("ERA_SPARSE_")]

        assert (ok_rows["bust_primary_assignment_method"] == ASSIGNMENT_METHOD_ERA_SPECIFIC).all()
        assert (sparse_rows["bust_primary_assignment_method"] == ASSIGNMENT_METHOD_POOLED_ERA_FALLBACK).all()
        # No label is left null for either group -- both get a real
        # percentile-derived label since score_like is available for all.
        assert ok_rows["bust_primary_label"].notna().all()
        assert sparse_rows["bust_primary_label"].notna().all()


class TestLookupGapFallback:
    """Proposal §19/§23: a row with real ADP and real P but no fitted
    E_P cell falls back to a raw-P percentile within the pooled
    (position, ADP bucket) reference population (all eligible rows
    with real P), not just among the gap rows themselves."""

    def test_gap_row_gets_g_raw_fallback_and_a_real_label(self):
        # GAP has adp_round=9 (bucket R6-10) with no fitted E_P cell.
        # Two ordinary rows in the SAME bucket provide real E_P
        # coverage AND a real reference population to rank the gap
        # row's raw P against.
        # OK1/OK2 use round 7 (bucket R6-10), which DOES have a fitted
        # E_P cell; GAP uses round 9 (same bucket) which does NOT --
        # isolates the lookup gap while keeping all three in one real
        # pooled reference population for the G-raw fallback.
        master = _master(
            (2020, "GAP", "RB", 100.0, 12),   # round 9, no E_P cell
            (2020, "OK1", "RB", 73.0, 12),    # round 7, has E_P cell
            (2020, "OK2", "RB", 84.0, 5),     # round 7, has E_P cell, low P -> worst in pool
        )
        sbv = _sbv(
            (2020, "GAP", "below_production_gate", None, 0),
            (2020, "OK1", "adp_scored", 20.0, 1),
            (2020, "OK2", "below_production_gate", None, 0),
        )
        players = _players(("GAP", None), ("OK1", None), ("OK2", None))
        ep_lookup = _ep_lookup((2020, "RB", 7, 60.0))  # round 9 (GAP's round) NOT covered
        production = _production((2020, "GAP", 40.0), (2020, "OK1", 90.0), (2020, "OK2", 5.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)

        gap_row = out[out["player_id"] == "GAP"].iloc[0]
        assert gap_row["bust_primary_eligible"] == True  # noqa: E712
        assert gap_row["bust_primary_assignment_method"] == ASSIGNMENT_METHOD_G_RAW_LOOKUP_GAP_FALLBACK
        assert not pd.isna(gap_row["bust_primary_label"])
        # GAP's raw P (40.0) sits between OK2 (5.0, worst) and OK1
        # (90.0, best) in the pooled R6-10 RB pool -- not the bottom of
        # the pool, so NOT flagged at the 20% cutoff (1 of 3 rows).
        assert gap_row["bust_primary_label"] == False  # noqa: E712


class TestTieHandling:
    """Two rows tied for the worst score_like straddling a percentile
    boundary must be labeled TOGETHER -- never arbitrarily split by
    row order. method='average' rank + inclusive <= cutoff."""

    def test_tied_rows_move_together_across_a_boundary(self):
        # 5 rows, same (position, adp_bucket); E_P fixed at 0.0 for all
        # so score_like == P exactly, avoiding any rounding subtlety.
        # TIE_A and TIE_B share P=10.0 (worst, tied) -> average rank
        # 1.5 of 5 -> pct = 0.30. This is > the 20% cutoff (excluded
        # together) but <= the 30% cutoff (included together).
        master = _master(
            (2015, "TIE_A", "RB", 80.0),
            (2015, "TIE_B", "RB", 80.0),
            (2015, "P3", "RB", 80.0),
            (2015, "P4", "RB", 80.0),
            (2015, "P5", "RB", 80.0),
        )
        sbv = _sbv(
            (2015, "TIE_A", "adp_scored", None, 1),
            (2015, "TIE_B", "adp_scored", None, 1),
            (2015, "P3", "adp_scored", None, 1),
            (2015, "P4", "adp_scored", None, 1),
            (2015, "P5", "adp_scored", None, 1),
        )
        players = _players(("TIE_A", None), ("TIE_B", None), ("P3", None), ("P4", None), ("P5", None))
        ep_lookup = _ep_lookup((2015, "RB", 7, 0.0))
        production = _production(
            (2015, "TIE_A", 10.0), (2015, "TIE_B", 10.0), (2015, "P3", 20.0), (2015, "P4", 30.0), (2015, "P5", 40.0)
        )
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        a = out[out["player_id"] == "TIE_A"].iloc[0]
        b = out[out["player_id"] == "TIE_B"].iloc[0]

        assert a["bust_primary_label"] == b["bust_primary_label"]
        assert a["bust_primary_label"] == False  # noqa: E712 -- tie pushes pct to 0.30, excludes both from 20%
        assert a["bust_primary_sensitivity_pct30_label"] == b["bust_primary_sensitivity_pct30_label"]
        assert a["bust_primary_sensitivity_pct30_label"] == True  # noqa: E712 -- both included together at 30%


class TestInputOrderIndependence:
    def test_reversed_row_order_produces_identical_labels(self):
        rows_master = [(2015, f"P{i}", "RB", 60.0 + i) for i in range(12)]
        rows_sbv = [(2015, f"P{i}", "adp_scored", None, 1) for i in range(12)]
        rows_players = [(f"P{i}", None) for i in range(12)]
        rows_production = [(2015, f"P{i}", 20.0 + i * 3.0) for i in range(12)]
        ep_lookup = _ep_lookup((2015, "RB", 5, 10.0), (2015, "RB", 6, 10.0))

        forward = build_canonical_outcome_table(
            _master(*rows_master), _sbv(*rows_sbv), _players(*rows_players), ep_lookup, _production(*rows_production)
        ).sort_values("player_id").reset_index(drop=True)

        reversed_out = build_canonical_outcome_table(
            _master(*reversed(rows_master)),
            _sbv(*reversed(rows_sbv)),
            _players(*reversed(rows_players)),
            ep_lookup,
            _production(*reversed(rows_production)),
        ).sort_values("player_id").reset_index(drop=True)

        pd.testing.assert_series_equal(forward["bust_primary_label"], reversed_out["bust_primary_label"])
        pd.testing.assert_series_equal(forward["bust_primary_assignment_method"], reversed_out["bust_primary_assignment_method"])
        pd.testing.assert_series_equal(
            forward["bust_strict_below_replacement_label"], reversed_out["bust_strict_below_replacement_label"]
        )


class TestUniverseCounts:
    def test_primary_and_historical_sensitivity_universe_sizes(self):
        rows = [
            (2015, "P1", "RB", 20.0),  # real ADP, 2010+ -- primary + historical eligible
            (2008, "P2", "WR", 15.0),  # real ADP, pre-2010 -- historical only
            (2015, "P3", "TE", None),  # no ADP -- neither
        ]
        master = _master(*rows)
        sbv = _sbv(
            (2015, "P1", "adp_scored", 10.0, 1),
            (2008, "P2", "out_of_scope", None, None),
            (2015, "P3", "below_production_gate", None, 0),
        )
        players = _players(("P1", None), ("P2", None), ("P3", None))
        ep_lookup = _ep_lookup((2015, "RB", 2, 5.0))
        production = _production((2015, "P1", 15.0), (2008, "P2", 20.0), (2015, "P3", 3.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        assert out["bust_primary_eligible"].sum() == 1
        assert out["bust_historical_sensitivity_eligible"].sum() == 2


class TestReasonCodeCompleteness:
    def test_every_ineligible_has_exactly_one_reason_every_eligible_has_none(self):
        rows = [
            (2015, "P1", "RB", 20.0),
            (2008, "P2", "WR", 15.0),
            (2015, "P3", "TE", None),
            (2015, "P4", "QB", None),
            (2021, "P5", "WR", None),
            (2025, "P6", "RB", 158.83, 0),
        ]
        master = _master(*rows)
        sbv = _sbv(
            (2015, "P1", "adp_scored", 10.0, 1),
            (2008, "P2", "out_of_scope", None, None),
            (2015, "P3", "below_production_gate", None, 0),
            (2015, "P4", "minimal_market_cost_scored", 4.0, 0),
            (2021, "P5", "unscoreable_drafted_adp_missing", None, None),
        )
        players = _players(("P1", None), ("P2", None), ("P3", None), ("P4", None), ("P5", 3), ("P6", None))
        ep_lookup = _ep_lookup((2015, "RB", 2, 5.0))
        production = _production((2015, "P1", 15.0), (2008, "P2", 20.0), (2015, "P3", 3.0), (2015, "P4", 6.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)

        for eligible_col, reason_col in (
            ("star_outcome_eligible", "star_outcome_ineligibility_reason"),
            ("bust_primary_eligible", "bust_primary_ineligibility_reason"),
            ("bust_strict_below_replacement_eligible", "bust_strict_below_replacement_ineligibility_reason"),
            ("bust_historical_sensitivity_eligible", "bust_historical_sensitivity_ineligibility_reason"),
            ("underperformance_diagnostic_eligible", "underperformance_diagnostic_ineligibility_reason"),
        ):
            eligible_with_reason = out[eligible_col] & out[reason_col].notna()
            ineligible_without_reason = (~out[eligible_col].astype(bool)) & out[reason_col].isna()
            assert eligible_with_reason.sum() == 0, f"{eligible_col}: eligible row(s) with a reason"
            assert ineligible_without_reason.sum() == 0, f"{eligible_col}: ineligible row(s) without a reason"

    def test_output_columns_are_exactly_declared(self):
        master = _master((2015, "P1", "RB", 20.0))
        sbv = _sbv((2015, "P1", "adp_scored", 10.0, 1))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup((2015, "RB", 2, 5.0))
        production = _production((2015, "P1", 15.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        assert list(out.columns) == list(OUTCOME_OUTPUT_COLUMNS)
        assert out.loc[0, "canonical_position_status"] == "adp_source"
        assert out.loc[0, "canonical_position_authority"] == "adp_source_position"


class TestNoDuplicateKeys:
    def test_no_duplicate_outcome_season_player_keys(self):
        master = _master((2015, "P1", "RB", 20.0), (2015, "P2", "WR", None))
        sbv = _sbv((2015, "P1", "adp_scored", 10.0, 1), (2015, "P2", "below_production_gate", None, 0))
        players = _players(("P1", None), ("P2", None))
        ep_lookup = _ep_lookup((2015, "RB", 2, 5.0))
        production = _production((2015, "P1", 15.0), (2015, "P2", 3.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        assert out.duplicated(subset=["outcome_season", "player_id"]).sum() == 0
