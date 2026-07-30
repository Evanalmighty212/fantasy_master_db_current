"""
tests/test_dataset2_canonical_outcome_table.py

Protects lib/dataset2/canonical_outcome_table.py -- artifact 2 of the
three-artifact architecture (research/dataset2/CANONICAL_TABLE_PROPOSAL_2026_07.md
§1a). Proves the four separate outcome-eligibility universes (Star,
primary bust, bust historical sensitivity, underperformance
diagnostic) are genuinely distinct, that every real bug class found
during this round's review is fixed (below-gate rows get a real False
label, not null; the zero-game real-ADP row is primary-bust eligible;
MMC is bust-ineligible but diagnostic-eligible; the
expected-production-out-of-range rows are bust-eligible but
diagnostic-ineligible), and that every ineligible outcome carries
exactly one reason code while every eligible one carries none.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.canonical_outcome_table import OUTCOME_OUTPUT_COLUMNS, build_canonical_outcome_table


def _master(*rows):
    """rows: (season, player_id, position, overall_adp)."""
    return pd.DataFrame(
        [{"season": s, "player_id": p, "position": pos, "overall_adp": adp} for s, p, pos, adp in rows]
    )


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
    if not rows:
        return pd.DataFrame(columns=("season", "player_id", "P"))
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

    def test_ineligible_star_row_has_null_label_not_false(self):
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
        master = _master((2025, "P1", "RB", 158.83))
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
        master = _master((2021, "P1", "WR", None))
        sbv = _sbv()
        players = _players(("P1", 2))  # real NFL draft capital, no fantasy ADP
        ep_lookup = _ep_lookup()
        production = _production()
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_eligible"] == False  # noqa: E712
        assert row["bust_primary_ineligibility_reason"] == "zero_games_nfl_draft_capital_not_fantasy_adp"

    def test_zero_game_no_cost_signal_at_all(self):
        master = _master((2021, "P1", "TE", None))
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
        master = _master((2025, "P1", "RB", 100.0))  # adp_round = ceil(100/12) = 9
        sbv = _sbv((2025, "P1", "unscoreable_expected_production_out_of_range", None, None))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup((2025, "RB", 1, 80.0))  # round 9 not covered
        production = _production((2025, "P1", 50.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_eligible"] == True  # noqa: E712
        assert row["bust_primary_ineligibility_reason"] is None
        assert row["underperformance_diagnostic_eligible"] == False  # noqa: E712
        assert row["underperformance_diagnostic_ineligibility_reason"] == "expected_production_lookup_out_of_range"
        assert pd.isna(row["underperformance_diagnostic_value"])

    def test_below_gate_real_adp_out_of_range_also_diagnostic_ineligible(self):
        # Real, found this round: a below_production_gate real-ADP row
        # can ALSO have an out-of-range round -- must not be
        # extrapolated around, same as the ep_out_of_range status.
        master = _master((2025, "P1", "WR", 200.0))  # adp_round = ceil(200/12) = 17
        sbv = _sbv((2025, "P1", "below_production_gate", None, 0))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup((2025, "WR", 1, 90.0))  # round 17 not covered
        production = _production((2025, "P1", 5.0))
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

    def test_ineligible_bust_label_is_null_not_false(self):
        master = _master((2021, "P1", "TE", None))
        sbv = _sbv()
        players = _players(("P1", None))
        ep_lookup = _ep_lookup()
        production = _production()
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert pd.isna(row["bust_primary_label"])
        assert pd.isna(row["bust_strict_label"])
        assert pd.isna(row["bust_historical_sensitivity_label"])

    def test_bust_labels_are_always_null_this_round_even_when_eligible(self):
        # Reserved, not computed -- no approved percentile/floor value
        # exists yet, see module docstring.
        master = _master((2015, "P1", "RB", 20.0))
        sbv = _sbv((2015, "P1", "adp_scored", 10.0, 1))
        players = _players(("P1", None))
        ep_lookup = _ep_lookup((2015, "RB", 2, 5.0))
        production = _production((2015, "P1", 15.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        row = out.iloc[0]
        assert row["bust_primary_eligible"] == True  # noqa: E712
        assert pd.isna(row["bust_primary_label"])
        assert row["bust_primary_label"] is pd.NA or pd.isna(row["bust_primary_label"])


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
            (2025, "P6", "RB", 158.83),
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
            ("bust_strict_eligible", "bust_strict_ineligibility_reason"),
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


class TestNoDuplicateKeys:
    def test_no_duplicate_outcome_season_player_keys(self):
        master = _master((2015, "P1", "RB", 20.0), (2015, "P2", "WR", None))
        sbv = _sbv((2015, "P1", "adp_scored", 10.0, 1), (2015, "P2", "below_production_gate", None, 0))
        players = _players(("P1", None), ("P2", None))
        ep_lookup = _ep_lookup((2015, "RB", 2, 5.0))
        production = _production((2015, "P1", 15.0), (2015, "P2", 3.0))
        out = build_canonical_outcome_table(master, sbv, players, ep_lookup, production)
        assert out.duplicated(subset=["outcome_season", "player_id"]).sum() == 0
