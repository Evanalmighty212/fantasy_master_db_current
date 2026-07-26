"""
tests/test_labeling.py

Covers lib/stars_by_value/labeling.py -- the wiring layer implementing
the settled four-step processing order (methodology section 11). This
is the first place all of Commits 5-8 are exercised together, so these
tests protect the ORDER and the INVARIANTS, not the formulas inside
each already-tested module (production.py, expected_production.py,
acquisition_cost.py, minimal_market_cost.py each have their own
dedicated, already-passing test suites).

Named-case regression fixtures reproduce the REAL settled scores from
STARS_BY_VALUE_METHODOLOGY.md's reinforcement-check table exactly
(Herbert 2020 202.0, Cruz 2011 187.6, Nacua 2023 184.4, Kyren Williams
2023 232.6, Barnidge 2015 160.9) -- P values were solved backward from
score = P - SBV_LAMBDA * E_P using the real, already-verified
minimal_market_cost_expected_production() output for each
(position, season), not invented numbers.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from lib.stars_by_value import acquisition_cost as ac
from lib.stars_by_value import labeling
from lib.stars_by_value import minimal_market_cost as mmc


def _ep_lookup(*rows):
    cols = list((
        "prediction_season", "position", "draft_round", "expected_production",
        "positional_offset_applied", "recency_weighted", "half_life_years",
        "sample_size", "sbv_version", "fit_timestamp",
    ))
    defaults = {
        "positional_offset_applied": None, "recency_weighted": False,
        "half_life_years": None, "sample_size": 100,
        "sbv_version": config.SBV_VERSION, "fit_timestamp": pd.Timestamp.now(tz="UTC"),
    }
    full_rows = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        full_rows.append(row)
    return pd.DataFrame(full_rows, columns=cols)


def _row(**overrides):
    base = {
        "season": 2020, "player_id": "00-1", "player_name": "Test Player", "position": "WR",
        "games_played": 12, "P": 300.0, "data_quality_flag": "matched_clean", "adp_round": 3,
    }
    base.update(overrides)
    return base


class TestTemporalScopeStrictlyBeforeGate:
    """A pre-2010 row must return at step 1, never reach step 2's
    gate check or step 3's acquisition-cost logic -- even with a P
    value that would obviously fail (or pass) the gate."""

    def test_pre_2010_with_extremely_high_p_is_out_of_scope_not_scored(self):
        lookup = _ep_lookup()
        row = _row(season=2009, P=99999.0)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] == labeling.STATUS_OUT_OF_SCOPE
        assert result["star_by_value_provenance_type"] == labeling.PROVENANCE_OUT_OF_SCOPE_TEMPORAL_WINDOW
        assert result["star_by_value_label"] is None
        assert result["star_by_value_score"] is None

    def test_pre_2010_gate_threshold_is_null_not_populated(self):
        lookup = _ep_lookup()
        row = _row(season=2005, P=1000.0)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_production_gate_threshold"] is None
        assert result["star_by_value_threshold"] is None

    def test_pre_2010_never_becomes_below_production_gate(self):
        """A pre-2010 row with a P far below the gate must still be
        out_of_scope, not below_production_gate -- the two-description
        collision this ordering exists to eliminate."""
        lookup = _ep_lookup()
        row = _row(season=2000, P=0.0)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] != labeling.STATUS_BELOW_PRODUCTION_GATE
        assert result["star_by_value_status"] == labeling.STATUS_OUT_OF_SCOPE

    def test_2010_itself_is_in_scope(self):
        lookup = _ep_lookup({"prediction_season": 2010, "position": "WR", "draft_round": 3, "expected_production": 100.0})
        row = _row(season=2010, P=300.0)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] != labeling.STATUS_OUT_OF_SCOPE

    def test_acquisition_cost_never_invoked_for_pre_2010_row(self, monkeypatch):
        def _fail_if_called(*args, **kwargs):
            raise AssertionError("acquisition_cost.classify_row must never be called for a pre-2010 out-of-scope row")
        monkeypatch.setattr(ac, "classify_row", _fail_if_called)
        lookup = _ep_lookup()
        row = _row(season=2008, data_quality_flag="no_adp_match", P=500.0)
        labeling.assign_sbv_status(row, lookup)  # must not raise


class TestOutOfScopeVariants:
    def test_non_skill_position_is_out_of_scope(self):
        lookup = _ep_lookup()
        row = _row(position="K", season=2020)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] == labeling.STATUS_OUT_OF_SCOPE
        assert result["star_by_value_provenance_type"] == labeling.PROVENANCE_OUT_OF_SCOPE_NON_SKILL_POSITION

    def test_zero_games_played_is_out_of_scope(self):
        lookup = _ep_lookup()
        row = _row(games_played=0, season=2020)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] == labeling.STATUS_OUT_OF_SCOPE
        assert result["star_by_value_provenance_type"] == labeling.PROVENANCE_OUT_OF_SCOPE_INSUFFICIENT_PARTICIPATION


class TestGateBeforeAcquisitionCost:
    def test_below_gate_row_never_invokes_acquisition_cost(self, monkeypatch):
        def _fail_if_called(*args, **kwargs):
            raise AssertionError("acquisition_cost.classify_row must never be called for a below-gate row")
        monkeypatch.setattr(ac, "classify_row", _fail_if_called)
        lookup = _ep_lookup()
        row = _row(season=2020, position="WR", data_quality_flag="no_adp_match", P=0.0)
        labeling.assign_sbv_status(row, lookup)  # must not raise

    def test_below_gate_status_and_population_rules(self):
        lookup = _ep_lookup()
        floor = config.SBV_PRODUCTION_GATE_FLOOR["WR"]
        row = _row(season=2020, position="WR", P=floor - 1.0)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] == labeling.STATUS_BELOW_PRODUCTION_GATE
        assert result["star_by_value_provenance_type"] == labeling.PROVENANCE_BELOW_PRODUCTION_GATE
        assert result["star_by_value_score"] is None
        assert result["star_by_value_label"] == 0  # NOT None -- gate failure is a real label
        assert result["star_by_value_production_gate_threshold"] == floor
        assert result["star_by_value_threshold"] is None  # never reached the final cutoff question

    def test_p_exactly_at_floor_clears_the_gate(self):
        """The gate check is strictly '<', not '<='."""
        lookup = _ep_lookup({"prediction_season": 2020, "position": "WR", "draft_round": 1, "expected_production": 50.0})
        floor = config.SBV_PRODUCTION_GATE_FLOOR["WR"]
        row = _row(season=2020, position="WR", P=floor, adp_round=1)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] != labeling.STATUS_BELOW_PRODUCTION_GATE


class TestMatchedClean:
    def test_adp_scored_computes_score_and_label(self):
        lookup = _ep_lookup({"prediction_season": 2020, "position": "WR", "draft_round": 3, "expected_production": 100.0})
        row = _row(season=2020, position="WR", data_quality_flag="matched_clean", adp_round=3, P=300.0)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] == labeling.STATUS_ADP_SCORED
        assert result["star_by_value_provenance_type"] == labeling.PROVENANCE_ADP_MATCHED_CLEAN
        expected_score = 300.0 - config.SBV_LAMBDA * 100.0
        assert result["star_by_value_score"] == pytest.approx(expected_score)
        assert result["star_by_value_label"] == (1 if expected_score >= config.SBV_STAR_THRESHOLD["WR"] else 0)
        assert result["star_by_value_production_gate_threshold"] == config.SBV_PRODUCTION_GATE_FLOOR["WR"]
        assert result["star_by_value_threshold"] == config.SBV_STAR_THRESHOLD["WR"]

    def test_missing_lookup_cell_raises(self):
        lookup = _ep_lookup({"prediction_season": 1999, "position": "WR", "draft_round": 3, "expected_production": 1.0})
        row = _row(season=2020, position="WR", data_quality_flag="matched_clean", adp_round=3, P=300.0)
        with pytest.raises(ValueError, match="No E_P lookup entry"):
            labeling.assign_sbv_status(row, lookup)


class TestMatchedNeedsReview:
    def test_both_thresholds_populated_score_and_label_null(self):
        lookup = _ep_lookup()
        row = _row(season=2020, position="RB", data_quality_flag="matched_needs_review", P=300.0)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] == labeling.STATUS_UNSCOREABLE_ADP_NEEDS_REVIEW
        assert result["star_by_value_provenance_type"] == labeling.PROVENANCE_ADP_MATCHED_NEEDS_REVIEW
        assert result["star_by_value_score"] is None
        assert result["star_by_value_label"] is None
        assert result["star_by_value_production_gate_threshold"] == config.SBV_PRODUCTION_GATE_FLOOR["RB"]
        assert result["star_by_value_threshold"] == config.SBV_STAR_THRESHOLD["RB"]

    def test_below_gate_needs_review_row_is_ordinary_below_gate(self):
        """Production failure is dispositive at step 2 regardless of
        ADP quality."""
        lookup = _ep_lookup()
        floor = config.SBV_PRODUCTION_GATE_FLOOR["RB"]
        row = _row(season=2020, position="RB", data_quality_flag="matched_needs_review", P=floor - 1.0)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_status"] == labeling.STATUS_BELOW_PRODUCTION_GATE


class TestNoAdpMatchDelegation:
    def _players(self, gsis_id, position, draft_year=2020, draft_round=6, rookie_season=2020):
        cols = ["gsis_id", "position", "draft_year", "draft_round", "draft_pick", "rookie_season"]
        return pd.DataFrame([{
            "gsis_id": gsis_id, "position": position, "draft_year": draft_year,
            "draft_round": draft_round, "draft_pick": 180, "rookie_season": rookie_season,
        }], columns=cols)

    def _history(self):
        return pd.DataFrame(columns=["season", "player_id", "games_played", "fantasy_points_ppr"])

    def test_mmc_path_computes_score_via_minimal_market_cost_module(self):
        players = self._players("00-mmc", "WR", draft_year=2023, draft_round=5, rookie_season=2023)
        history = self._history()
        mfl_players = {"players": {"player": [{"id": "1", "name": "Player, Test", "position": "WR", "team": "FA"}]}}
        mfl_adp = {"adp": {"totalDrafts": "5000", "player": [{"id": "1", "draftSelPct": "10", "rank": "300", "averagePick": "180.0"}]}}
        lookup = _ep_lookup()
        row = _row(season=2023, position="WR", player_id="00-mmc", data_quality_flag="no_adp_match", P=300.0)

        result = labeling.assign_sbv_status(
            row, lookup, players_df=players, history_df=history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["star_by_value_status"] == labeling.STATUS_MMC_SCORED
        assert result["star_by_value_provenance_type"] == ac.PROVENANCE_MMC_CORROBORATED
        expected_e_p = mmc.minimal_market_cost_expected_production("WR", 2023)
        expected_score = 300.0 - config.SBV_LAMBDA * expected_e_p
        assert result["star_by_value_score"] == pytest.approx(expected_score)
        assert result["star_by_value_label"] is not None

    def test_drafted_missing_path_has_null_score_and_label(self):
        players = self._players("00-dm", "RB", draft_year=2019, draft_round=2, rookie_season=2019)
        history = self._history()
        mfl_players = {"players": {"player": [{"id": "2", "name": "Player, Test", "position": "RB", "team": "FA"}]}}
        mfl_adp = {"adp": {"totalDrafts": "5000", "player": [{"id": "2", "draftSelPct": "50", "rank": "50", "averagePick": "50.0"}]}}
        lookup = _ep_lookup()
        row = _row(season=2019, position="RB", player_id="00-dm", data_quality_flag="no_adp_match", P=300.0)

        result = labeling.assign_sbv_status(
            row, lookup, players_df=players, history_df=history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["star_by_value_status"] == labeling.STATUS_DRAFTED_MISSING
        assert result["star_by_value_score"] is None
        assert result["star_by_value_label"] is None
        assert result["star_by_value_threshold"] == config.SBV_STAR_THRESHOLD["RB"]  # populated informationally

    def test_ambiguous_path_has_null_score_and_label(self):
        players = self._players("00-amb", "TE", draft_year=2015, draft_round=6, rookie_season=2015)
        history = self._history()
        mfl_players = {"players": {"player": []}}  # unmatched
        mfl_adp = {"adp": {"totalDrafts": "5000", "player": []}}
        lookup = _ep_lookup()
        row = _row(season=2019, position="TE", player_id="00-amb", data_quality_flag="no_adp_match", P=300.0)

        result = labeling.assign_sbv_status(
            row, lookup, players_df=players, history_df=history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["star_by_value_status"] == labeling.STATUS_AMBIGUOUS
        assert result["star_by_value_score"] is None
        assert result["star_by_value_label"] is None


class TestUsableAdpOverride2010:
    def _overrides(self, *rows):
        cols = ["season", "player_id", "override_type", "adp_overall", "adp_round"]
        return pd.DataFrame(list(rows), columns=cols)

    def test_usable_adp_override_routes_to_adp_scored(self):
        players = pd.DataFrame(columns=["gsis_id", "position", "draft_year", "draft_round", "draft_pick", "rookie_season"])
        history = pd.DataFrame(columns=["season", "player_id", "games_played", "fantasy_points_ppr"])
        overrides = self._overrides({"season": "2010", "player_id": "00-override", "override_type": "usable_adp", "adp_overall": 55.2, "adp_round": 5})
        lookup = _ep_lookup({"prediction_season": 2010, "position": "WR", "draft_round": 5, "expected_production": 80.0})
        row = _row(season=2010, position="WR", player_id="00-override", data_quality_flag="no_adp_match", P=300.0)

        result = labeling.assign_sbv_status(
            row, lookup, players_df=players, history_df=history, overrides_2010_df=overrides,
        )
        assert result["star_by_value_status"] == labeling.STATUS_ADP_SCORED
        expected_score = 300.0 - config.SBV_LAMBDA * 80.0
        assert result["star_by_value_score"] == pytest.approx(expected_score)


class TestExactCutoffEquality:
    def test_score_exactly_equal_to_threshold_is_label_1(self):
        position = "WR"
        threshold = config.SBV_STAR_THRESHOLD[position]
        e_p = 100.0
        # solve P so that score lands EXACTLY on the threshold
        P = threshold + config.SBV_LAMBDA * e_p
        lookup = _ep_lookup({"prediction_season": 2020, "position": position, "draft_round": 2, "expected_production": e_p})
        row = _row(season=2020, position=position, data_quality_flag="matched_clean", adp_round=2, P=P)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_score"] == pytest.approx(threshold)
        assert result["star_by_value_label"] == 1

    def test_score_just_below_threshold_is_label_0(self):
        position = "WR"
        threshold = config.SBV_STAR_THRESHOLD[position]
        e_p = 100.0
        P = threshold + config.SBV_LAMBDA * e_p - 0.01
        lookup = _ep_lookup({"prediction_season": 2020, "position": position, "draft_round": 2, "expected_production": e_p})
        row = _row(season=2020, position=position, data_quality_flag="matched_clean", adp_round=2, P=P)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_label"] == 0


class TestExpectedProductionOutOfRange:
    """Covers STATUS_UNSCOREABLE_EP_OUT_OF_RANGE (added 2026-07 -- see
    docs/ADP_SOURCE_MATRIX.md's Blocker B entry). A real ADP-matched,
    gate-clearing row whose draft_round exceeds the E_P lookup's fitted
    depth: NOT capped at the deepest fitted round, NOT MMC-substituted
    -- score=NULL, label=NULL, both thresholds populated, provenance
    explicitly states acquisition cost is known but E_P is unavailable.

    Named-case values for the 8 real 2025 rows that clear the
    production gate at adp_round > 15 (P, gate_floor, adp_round all
    verified directly against the real master DB during the Blocker B
    audit -- not invented). All 8 also happen to fail the Star
    threshold even at the theoretical best case of E_P=0 -- but the
    system must NEVER shortcut to label=0 on that basis. See
    test_hypothetical_high_production_round16_player_still_gets_null_label
    below for the proof that a DIFFERENT, much-higher-P player at the
    same out-of-range round also gets label=NULL, not label=1 -- the
    resolution is genuinely unresolved, not a disguised "always 0."
    """

    LOOKUP_1_TO_15 = _ep_lookup(*[
        {"prediction_season": 2025, "position": pos, "draft_round": rnd, "expected_production": 200.0}
        for pos in ("QB", "RB", "WR", "TE") for rnd in range(1, 16)
    ])

    @pytest.mark.parametrize("player_name,position,P,gate_floor,adp_round", [
        ("Daniel Jones", "QB", 158.403333, 142.599891, 16),
        ("Jaxson Dart", "QB", 157.116316, 142.599891, 16),
        ("Kenny Gainwell", "RB", 148.645000, 113.712500, 17),
        ("Michael Wilson", "WR", 129.255000, 98.105667, 17),
        ("Alec Pierce", "WR", 114.527500, 98.105667, 16),
        ("AJ Barner", "TE", 72.800000, 66.679583, 17),
        ("Oronde Gadsden II", "TE", 74.460000, 66.679583, 16),
        ("Theo Johnson", "TE", 70.680000, 66.679583, 16),
    ])
    def test_real_2025_named_case(self, player_name, position, P, gate_floor, adp_round):
        row = _row(
            season=2025, player_name=player_name, position=position,
            P=P, data_quality_flag="matched_clean", adp_round=adp_round,
        )
        result = labeling.assign_sbv_status(row, self.LOOKUP_1_TO_15)
        assert result["star_by_value_status"] == labeling.STATUS_UNSCOREABLE_EP_OUT_OF_RANGE
        assert result["star_by_value_provenance_type"] == labeling.PROVENANCE_KNOWN_COST_EP_OUT_OF_RANGE
        assert result["star_by_value_score"] is None
        assert result["star_by_value_label"] is None
        assert result["star_by_value_production_gate_threshold"] == pytest.approx(config.SBV_PRODUCTION_GATE_FLOOR[position])
        assert result["star_by_value_threshold"] == config.SBV_STAR_THRESHOLD[position]

    def test_hypothetical_high_production_round16_player_still_gets_null_label(self):
        """The critical proof: a DIFFERENT, hypothetical player at the
        same out-of-range round, with P so high it would obviously be
        a Star under ANY plausible E_P (even a very large one), STILL
        gets label=NULL -- the system does not shortcut to label=0
        merely because the 8 real 2025 cases all happen to fail. The
        resolution is genuinely "unknown," not a disguised default."""
        row = _row(
            season=2025, position="WR", P=1000.0,  # absurdly high, would clear any real threshold
            data_quality_flag="matched_clean", adp_round=20,
        )
        result = labeling.assign_sbv_status(row, self.LOOKUP_1_TO_15)
        assert result["star_by_value_status"] == labeling.STATUS_UNSCOREABLE_EP_OUT_OF_RANGE
        assert result["star_by_value_score"] is None
        assert result["star_by_value_label"] is None, (
            "A high-production out-of-range player must not be silently "
            "auto-labeled 1 (or 0) -- the label is genuinely unresolved."
        )

    def test_round_exactly_at_fitted_max_is_unaffected(self):
        """Regression guard: round 15 (the real fitted maximum) must
        still resolve to the normal adp_scored path, not the new
        out-of-range status -- '>' not '>='."""
        row = _row(season=2025, position="WR", P=300.0, data_quality_flag="matched_clean", adp_round=15)
        result = labeling.assign_sbv_status(row, self.LOOKUP_1_TO_15)
        assert result["star_by_value_status"] == labeling.STATUS_ADP_SCORED
        assert result["star_by_value_score"] is not None

    def test_below_gate_row_still_resolves_to_below_production_gate_not_ep_out_of_range(self):
        """Step 2 (production gate) still runs BEFORE step 3 -- a
        gate-failing row at a deep round must stay
        below_production_gate, never reach the new status at all."""
        row = _row(season=2025, position="TE", P=1.0, data_quality_flag="matched_clean", adp_round=20)
        result = labeling.assign_sbv_status(row, self.LOOKUP_1_TO_15)
        assert result["star_by_value_status"] == labeling.STATUS_BELOW_PRODUCTION_GATE

    def test_status_and_provenance_are_valid_config_members(self):
        assert labeling.STATUS_UNSCOREABLE_EP_OUT_OF_RANGE in config.SBV_STATUSES
        assert labeling.PROVENANCE_KNOWN_COST_EP_OUT_OF_RANGE in config.SBV_PROVENANCE_TYPES


class TestAllStatusesExhaustiveAndExclusive:
    def test_all_statuses_reachable_and_valid(self):
        players = pd.DataFrame(columns=["gsis_id", "position", "draft_year", "draft_round", "draft_pick", "rookie_season"])
        history = pd.DataFrame(columns=["season", "player_id", "games_played", "fantasy_points_ppr"])
        lookup = _ep_lookup(
            {"prediction_season": 2020, "position": "WR", "draft_round": 1, "expected_production": 50.0},
            {"prediction_season": 2010, "position": "WR", "draft_round": 5, "expected_production": 80.0},
        )
        overrides = pd.DataFrame(columns=["season", "player_id", "override_type", "adp_overall", "adp_round"])

        rows_and_kwargs = [
            (_row(season=2005, position="WR"), {}),  # out_of_scope
            (_row(season=2020, position="WR", P=0.0), {}),  # below_production_gate
            (_row(season=2020, position="WR", data_quality_flag="matched_clean", adp_round=1, P=300.0), {}),  # adp_scored
            (_row(season=2020, position="WR", data_quality_flag="matched_needs_review", P=300.0), {}),  # unscoreable_adp_needs_review
            (_row(season=2020, position="WR", player_id="00-oor", data_quality_flag="matched_clean", adp_round=2, P=300.0), {}),  # unscoreable_expected_production_out_of_range -- round 2 exceeds the lookup's only fitted WR/2020 round (1)
            (
                _row(season=2020, position="WR", player_id="00-mmc2", data_quality_flag="no_adp_match", P=300.0),
                {"players_df": players, "history_df": history,
                 "mfl_players_response": {"players": {"player": [{"id": "9", "name": "X, Y", "position": "WR", "team": "FA"}]}},
                 "mfl_adp_response": {"adp": {"totalDrafts": "1000", "player": [{"id": "9", "draftSelPct": "5", "rank": "300", "averagePick": "200.0"}]}}},
            ),  # minimal_market_cost_scored
            (
                _row(season=2020, position="WR", player_id="00-dm2", data_quality_flag="no_adp_match", P=300.0),
                {"players_df": players, "history_df": history,
                 "mfl_players_response": {"players": {"player": [{"id": "8", "name": "A, B", "position": "WR", "team": "FA"}]}},
                 "mfl_adp_response": {"adp": {"totalDrafts": "1000", "player": [{"id": "8", "draftSelPct": "80", "rank": "5", "averagePick": "5.0"}]}}},
            ),
        ]

        # Force the drafted-missing case's classifier bucket via a Day-1-2 rookie
        players_dm = pd.DataFrame([{
            "gsis_id": "00-dm2", "position": "WR", "draft_year": 2020, "draft_round": 2,
            "draft_pick": 40, "rookie_season": 2020,
        }], columns=players.columns)
        rows_and_kwargs[6] = (rows_and_kwargs[6][0], {**rows_and_kwargs[6][1], "players_df": players_dm})

        seen_statuses = set()
        for row, kwargs in rows_and_kwargs:
            result = labeling.assign_sbv_status(row, lookup, **kwargs)
            seen_statuses.add(result["star_by_value_status"])
            assert result["star_by_value_status"] in config.SBV_STATUSES
            assert result["star_by_value_provenance_type"] in config.SBV_PROVENANCE_TYPES

        # ambiguous and unscoreable_ambiguous covered by TestNoAdpMatchDelegation directly;
        # confirms every status produced here is a real, valid member
        assert seen_statuses <= set(config.SBV_STATUSES)
        assert labeling.STATUS_UNSCOREABLE_EP_OUT_OF_RANGE in seen_statuses
        assert len(seen_statuses) >= 6


class TestLookupValidatedOnce:
    def test_validate_lookup_called_exactly_once_for_multi_row_batch(self, monkeypatch):
        from lib.stars_by_value import expected_production as ep
        call_count = {"n": 0}
        original = ep.validate_lookup

        def _counting_validate(*args, **kwargs):
            call_count["n"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(labeling.ep, "validate_lookup", _counting_validate)

        lookup = _ep_lookup(
            {"prediction_season": 2020, "position": "WR", "draft_round": 1, "expected_production": 50.0},
        )
        rows = pd.DataFrame([
            _row(season=2005, position="WR"),
            _row(season=2020, position="WR", P=0.0),
            _row(season=2020, position="WR", data_quality_flag="matched_clean", adp_round=1, P=300.0),
        ])
        labeling.label_rows(rows, lookup)
        assert call_count["n"] == 1

    def test_stale_lookup_version_raises_before_any_row_is_processed(self):
        lookup = _ep_lookup({"prediction_season": 2020, "position": "WR", "draft_round": 1, "expected_production": 50.0})
        lookup["sbv_version"] = "0.0-stale"
        rows = pd.DataFrame([_row(season=2020, position="WR")])
        with pytest.raises(ValueError, match="STALE E_P LOOKUP TABLE"):
            labeling.label_rows(rows, lookup)


class TestNoSilentNullToZeroCoercion:
    def test_out_of_scope_label_is_none_not_zero(self):
        lookup = _ep_lookup()
        row = _row(season=2005)
        result = labeling.assign_sbv_status(row, lookup)
        assert result["star_by_value_label"] is None

    def test_ambiguous_label_is_none_not_zero(self):
        players = pd.DataFrame(columns=["gsis_id", "position", "draft_year", "draft_round", "draft_pick", "rookie_season"])
        history = pd.DataFrame(columns=["season", "player_id", "games_played", "fantasy_points_ppr"])
        lookup = _ep_lookup()
        row = _row(season=2019, position="TE", data_quality_flag="no_adp_match", P=300.0)
        result = labeling.assign_sbv_status(
            row, lookup, players_df=players, history_df=history,
            mfl_players_response={"players": {"player": []}}, mfl_adp_response={"adp": {"totalDrafts": "1", "player": []}},
        )
        assert result["star_by_value_label"] is None

    def test_batch_output_preserves_pandas_na_not_coerced_to_zero(self):
        # label_rows() validates the whole lookup table up front regardless
        # of which rows need it -- an empty table is itself invalid per
        # expected_production.validate_lookup() (Commit 6), so a real,
        # non-empty (if irrelevant to this out-of-scope row) table is used.
        lookup = _ep_lookup({"prediction_season": 2020, "position": "WR", "draft_round": 1, "expected_production": 50.0})
        rows = pd.DataFrame([_row(season=2005)])
        out = labeling.label_rows(rows, lookup)
        assert pd.isna(out.loc[0, "star_by_value_label"])
        assert out["star_by_value_label"].dtype == "Int8"


class TestNullableInt8Label:
    def test_label_column_dtype_is_int8(self):
        lookup = _ep_lookup({"prediction_season": 2020, "position": "WR", "draft_round": 1, "expected_production": 50.0})
        rows = pd.DataFrame([_row(season=2020, position="WR", data_quality_flag="matched_clean", adp_round=1, P=300.0)])
        out = labeling.label_rows(rows, lookup)
        assert out["star_by_value_label"].dtype == "Int8"

    def test_int8_column_holds_real_zero_and_one_and_na(self):
        lookup = _ep_lookup({"prediction_season": 2020, "position": "WR", "draft_round": 1, "expected_production": 500.0})
        floor = config.SBV_PRODUCTION_GATE_FLOOR["WR"]
        rows = pd.DataFrame([
            _row(season=2005, position="WR"),  # NA
            _row(season=2020, position="WR", P=floor - 1),  # 0 (below gate)
            _row(season=2020, position="WR", data_quality_flag="matched_clean", adp_round=1, P=10000.0),  # 1 (huge P)
        ])
        out = labeling.label_rows(rows, lookup)
        values = list(out["star_by_value_label"])
        assert pd.isna(values[0])
        assert values[1] == 0
        assert values[2] == 1


class TestNamedCaseRegression:
    """Real settled scores from STARS_BY_VALUE_METHODOLOGY.md's
    reinforcement-check table -- see module docstring for how P was
    solved backward to reproduce them exactly."""

    def _players(self, gsis_id, position, draft_year, draft_round, rookie_season):
        cols = ["gsis_id", "position", "draft_year", "draft_round", "draft_pick", "rookie_season"]
        return pd.DataFrame([{
            "gsis_id": gsis_id, "position": position, "draft_year": draft_year,
            "draft_round": draft_round, "draft_pick": (draft_round or 0) * 30, "rookie_season": rookie_season,
        }], columns=cols)

    def _history(self, *rows):
        cols = ["season", "player_id", "games_played", "fantasy_points_ppr"]
        return pd.DataFrame(list(rows), columns=cols)

    def _empty_lookup(self):
        return _ep_lookup()

    def test_herbert_2020(self):
        players = self._players("00-herbert", "QB", 2020, 6, 2020)
        history = self._history()
        depth = pd.DataFrame([{"season": 2020, "week": 1, "game_type": "REG", "position": "QB", "gsis_id": "00-herbert", "depth_team": 2}])
        mfl_players = {"players": {"player": [{"id": "h1", "name": "Herbert, Justin", "position": "QB", "team": "LAC"}]}}
        mfl_adp = {"adp": {"totalDrafts": "5892", "player": [{"id": "h1", "draftSelPct": "17.9", "rank": "158", "averagePick": "120.0"}]}}
        row = _row(season=2020, position="QB", player_id="00-herbert", player_name="Justin Herbert", data_quality_flag="no_adp_match", P=212.198334)

        result = labeling.assign_sbv_status(
            row, self._empty_lookup(), players_df=players, history_df=history,
            depth_chart_df=depth, mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["star_by_value_status"] == labeling.STATUS_MMC_SCORED
        assert result["star_by_value_score"] == pytest.approx(202.0, abs=0.01)
        assert result["star_by_value_label"] == 1

    def test_cruz_2011(self):
        players = self._players("00-cruz", "WR", None, None, 2010)
        history = self._history({"season": 2010, "player_id": "00-cruz", "games_played": 0, "fantasy_points_ppr": 0.0})
        mfl_players = {"players": {"player": [{"id": "c1", "name": "Cruz, Victor", "position": "WR", "team": "NYG"}]}}
        mfl_adp = {"adp": {"totalDrafts": "7098", "player": [{"id": "c1", "draftSelPct": "6.7", "rank": "268", "averagePick": "151.4"}]}}
        row = _row(season=2011, position="WR", player_id="00-cruz", player_name="Victor Cruz", data_quality_flag="no_adp_match", P=199.370259)

        result = labeling.assign_sbv_status(
            row, self._empty_lookup(), players_df=players, history_df=history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["star_by_value_status"] == labeling.STATUS_MMC_SCORED
        assert result["star_by_value_score"] == pytest.approx(187.6, abs=0.01)
        assert result["star_by_value_label"] == 1

    def test_nacua_2023(self):
        players = self._players("00-nacua", "WR", 2023, 5, 2023)
        history = self._history()
        mfl_players = {"players": {"player": [{"id": "n1", "name": "Nacua, Puka", "position": "WR", "team": "LAR"}]}}
        mfl_adp = {"adp": {"totalDrafts": "7923", "player": [{"id": "n1", "draftSelPct": "18.5", "rank": "209", "averagePick": "123.0"}]}}
        row = _row(season=2023, position="WR", player_id="00-nacua", player_name="Puka Nacua", data_quality_flag="no_adp_match", P=196.905900)

        result = labeling.assign_sbv_status(
            row, self._empty_lookup(), players_df=players, history_df=history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["star_by_value_status"] == labeling.STATUS_MMC_SCORED
        assert result["star_by_value_score"] == pytest.approx(184.4, abs=0.01)
        assert result["star_by_value_label"] == 1

    def test_kyren_williams_2023(self):
        players = self._players("00-kyren", "RB", 2022, 5, 2022)
        history = self._history({"season": 2022, "player_id": "00-kyren", "games_played": 3, "fantasy_points_ppr": 15.0})
        mfl_players = {"players": {"player": [{"id": "15710", "name": "Williams, Kyren", "position": "RB", "team": "LAR"}]}}
        mfl_adp = {"adp": {"totalDrafts": "9970", "player": [{"id": "15710", "draftSelPct": "12", "rank": "358", "averagePick": "170.71"}]}}
        row = _row(season=2023, position="RB", player_id="00-kyren", player_name="Kyren Williams", data_quality_flag="no_adp_match", P=240.676203)

        result = labeling.assign_sbv_status(
            row, self._empty_lookup(), players_df=players, history_df=history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["star_by_value_status"] == labeling.STATUS_MMC_SCORED
        assert result["star_by_value_score"] == pytest.approx(232.6, abs=0.01)
        assert result["star_by_value_label"] == 1

    def test_barnidge_2015(self):
        players = self._players("00-barnidge", "TE", 2008, 5, 2008)
        history = self._history(
            {"season": 2012, "player_id": "00-barnidge", "games_played": 2, "fantasy_points_ppr": 5.0},
            {"season": 2013, "player_id": "00-barnidge", "games_played": 1, "fantasy_points_ppr": 0.0},
            {"season": 2014, "player_id": "00-barnidge", "games_played": 3, "fantasy_points_ppr": 10.0},
        )
        mfl_players = {"players": {"player": [{"id": "9189", "name": "Barnidge, Gary", "position": "TE", "team": "CLE"}]}}
        mfl_adp = {"adp": {"totalDrafts": "4628", "player": []}}  # real: matched, zero selection
        row = _row(season=2015, position="TE", player_id="00-barnidge", player_name="Gary Barnidge", data_quality_flag="no_adp_match", P=167.260060)

        result = labeling.assign_sbv_status(
            row, self._empty_lookup(), players_df=players, history_df=history,
            mfl_adp_response=mfl_adp, mfl_players_response=mfl_players,
        )
        assert result["star_by_value_status"] == labeling.STATUS_MMC_SCORED
        assert result["star_by_value_score"] == pytest.approx(160.9, abs=0.01)
        assert result["star_by_value_label"] == 1

    def test_vick_2010(self):
        """Must resolve to unscoreable_drafted_adp_missing with
        label=NULL -- explicitly NOT label=0, and NOT scored via MMC,
        regardless of how high P is set."""
        players = self._players(ac.VICK_2010_GSIS_ID, "QB", 2001, 1, 2001)
        history = self._history(
            {"season": 2007, "player_id": ac.VICK_2010_GSIS_ID, "games_played": 0, "fantasy_points_ppr": 0.0},
            {"season": 2008, "player_id": ac.VICK_2010_GSIS_ID, "games_played": 0, "fantasy_points_ppr": 0.0},
            {"season": 2009, "player_id": ac.VICK_2010_GSIS_ID, "games_played": 0, "fantasy_points_ppr": 0.0},
        )
        overrides = pd.DataFrame(columns=["season", "player_id", "override_type", "adp_overall", "adp_round"])
        row = _row(season=2010, position="QB", player_id=ac.VICK_2010_GSIS_ID, data_quality_flag="no_adp_match", P=400.0)

        result = labeling.assign_sbv_status(
            row, self._empty_lookup(), players_df=players, history_df=history, overrides_2010_df=overrides,
        )
        assert result["star_by_value_status"] == labeling.STATUS_DRAFTED_MISSING
        assert result["star_by_value_provenance_type"] == ac.PROVENANCE_DRAFTED_UNRESOLVED
        assert result["star_by_value_score"] is None
        assert result["star_by_value_label"] is None
        assert result["star_by_value_label"] != 0


class TestNoResearchImports:
    def test_module_does_not_import_research(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(labeling))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "research" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "research" not in module
