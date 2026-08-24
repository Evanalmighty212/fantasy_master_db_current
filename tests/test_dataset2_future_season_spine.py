"""Synthetic-only tests for the governed 2026+ future-season roster spine.

No real roster/players.csv data is loaded here -- every fixture below
is hand-built, matching this project's existing Dataset 2 test
convention (see tests/test_dataset2_phase1_runner.py, etc.).
"""

from __future__ import annotations

import pandas as pd
import pytest

from lib.dataset2.future_season_spine import (
    GOVERNED_EXCLUDE_STATUSES,
    GOVERNED_INCLUDE_STATUSES,
    build_future_season_roster_spine,
    extend_population_with_future_spine,
    roster_status_provenance_frame,
    verify_family9_superset,
)

PREDICTION_SEASON = 2026
WEEK1_KICKOFF = pd.Timestamp("2026-09-04")
VALID_SNAPSHOT_TIME = pd.Timestamp("2026-08-01")


def _snapshot_row(gsis_id, status, position="WR", latest_team="ARI", last_season=None):
    return {
        "gsis_id": gsis_id, "position": position, "latest_team": latest_team,
        "status": status, "last_season": last_season,
    }


def _snapshot(rows) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestCutoffEnforcement:
    def test_raises_when_snapshot_is_on_or_after_week1_kickoff(self):
        snapshot = _snapshot([_snapshot_row("p1", "ACT")])
        with pytest.raises(ValueError, match="Week-1 kickoff"):
            build_future_season_roster_spine(snapshot, PREDICTION_SEASON, WEEK1_KICKOFF, WEEK1_KICKOFF)

    def test_raises_when_snapshot_is_after_week1_kickoff(self):
        snapshot = _snapshot([_snapshot_row("p1", "ACT")])
        after = WEEK1_KICKOFF + pd.Timedelta(days=1)
        with pytest.raises(ValueError, match="Week-1 kickoff"):
            build_future_season_roster_spine(snapshot, PREDICTION_SEASON, after, WEEK1_KICKOFF)

    def test_accepts_a_snapshot_strictly_before_kickoff(self):
        snapshot = _snapshot([_snapshot_row("p1", "ACT")])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1


class TestGovernedIncludeExcludeStatuses:
    def test_every_governed_include_status_is_admitted(self):
        snapshot = _snapshot([_snapshot_row(f"p_{s}", s) for s in GOVERNED_INCLUDE_STATUSES])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert set(result.included["player_id"]) == {f"p_{s}" for s in GOVERNED_INCLUDE_STATUSES}
        assert result.excluded.empty

    def test_sus_is_included_with_status_preserved(self):
        snapshot = _snapshot([_snapshot_row("p1", "SUS")])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1
        assert result.included.iloc[0]["roster_status"] == "SUS"
        assert result.included.iloc[0]["inclusion_reason"] == "included_status_SUS"

    def test_every_governed_exclude_status_is_excluded_with_a_reason(self):
        snapshot = _snapshot([_snapshot_row(f"p_{s}", s) for s in GOVERNED_EXCLUDE_STATUSES])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert result.included.empty
        assert set(result.excluded["player_id"]) == {f"p_{s}" for s in GOVERNED_EXCLUDE_STATUSES}
        assert result.excluded["exclusion_reason"].notna().all()

    def test_ungoverned_status_raises_rather_than_guessing(self):
        # ZZZ is a synthetic status that will never be real -- RSN is no
        # longer usable as "the unknown example" now that it is governed
        # (see TestRsnRecencyRule).
        snapshot = _snapshot([_snapshot_row("p1", "ZZZ")])
        with pytest.raises(ValueError, match="ungoverned roster status"):
            build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)

    def test_ungoverned_status_error_names_the_status_and_player(self):
        snapshot = _snapshot([_snapshot_row("player_xyz", "ZZZ")])
        with pytest.raises(ValueError) as exc_info:
            build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        message = str(exc_info.value)
        assert "ZZZ" in message
        assert "player_xyz" in message


class TestUdfUnconditionalInclusion:
    def test_udf_is_included_regardless_of_last_season(self):
        # UDF (undrafted free agent) has no recency gate -- see
        # GOVERNED_INCLUDE_STATUSES' own comment: every real UDF row is
        # inherently current by construction, unlike NWT/RSN/RSR.
        snapshot = _snapshot([_snapshot_row("p1", "UDF", last_season=PREDICTION_SEASON)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1
        assert result.included.iloc[0]["inclusion_reason"] == "included_status_UDF"

    def test_udf_is_included_even_with_no_last_season(self):
        snapshot = _snapshot([_snapshot_row("p1", "UDF", last_season=None)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1
        assert result.excluded.empty


class TestRsnRecencyRule:
    def test_recent_rsn_is_included_with_status_specific_reason(self):
        snapshot = _snapshot([_snapshot_row("p1", "RSN", last_season=PREDICTION_SEASON - 1)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1
        assert result.included.iloc[0]["inclusion_reason"] == "included_rsn_recent"

    def test_stale_rsn_is_excluded_with_status_specific_reason(self):
        # Real, verified case this rule protects: Joe Mixon (RB), a
        # genuinely current, fantasy-relevant veteran, is real RSN status
        # -- but this fixture uses a synthetic stale case to prove the
        # OTHER side of the rule (149 of 154 real RSN rows are stale).
        snapshot = _snapshot([_snapshot_row("p1", "RSN", last_season=PREDICTION_SEASON - 5)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert result.included.empty
        assert result.excluded.iloc[0]["exclusion_reason"] == "rsn_stale_last_season_excluded"

    def test_rsn_with_no_last_season_is_excluded_not_guessed(self):
        snapshot = _snapshot([_snapshot_row("p1", "RSN", last_season=None)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert result.included.empty
        assert result.excluded.iloc[0]["exclusion_reason"] == "rsn_no_last_season_excluded"

    def test_rsn_exactly_at_the_recency_boundary_is_included(self):
        snapshot = _snapshot([_snapshot_row("p1", "RSN", last_season=PREDICTION_SEASON - 1)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1


class TestRsrRecencyRule:
    def test_recent_rsr_is_included_with_status_specific_reason(self):
        snapshot = _snapshot([_snapshot_row("p1", "RSR", last_season=PREDICTION_SEASON - 1)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1
        assert result.included.iloc[0]["inclusion_reason"] == "included_rsr_recent"

    def test_stale_rsr_is_excluded_with_status_specific_reason(self):
        snapshot = _snapshot([_snapshot_row("p1", "RSR", last_season=PREDICTION_SEASON - 5)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert result.included.empty
        assert result.excluded.iloc[0]["exclusion_reason"] == "rsr_stale_last_season_excluded"

    def test_rsr_with_no_last_season_is_excluded_not_guessed(self):
        snapshot = _snapshot([_snapshot_row("p1", "RSR", last_season=None)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert result.included.empty
        assert result.excluded.iloc[0]["exclusion_reason"] == "rsr_no_last_season_excluded"


class TestRecencyGatedReasonsAreDistinctPerStatus:
    """Protects the auditability requirement: NWT/RSN/RSR share one
    recency mechanism internally, but must never collapse into one
    ambiguous 'stale' bucket in the excluded ledger."""

    def test_nwt_rsn_rsr_stale_reasons_are_all_distinct(self):
        snapshot = _snapshot([
            _snapshot_row("p_nwt", "NWT", last_season=PREDICTION_SEASON - 5),
            _snapshot_row("p_rsn", "RSN", last_season=PREDICTION_SEASON - 5),
            _snapshot_row("p_rsr", "RSR", last_season=PREDICTION_SEASON - 5),
        ])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        reasons = dict(zip(result.excluded["player_id"], result.excluded["exclusion_reason"]))
        assert reasons == {
            "p_nwt": "nwt_stale_last_season_excluded",
            "p_rsn": "rsn_stale_last_season_excluded",
            "p_rsr": "rsr_stale_last_season_excluded",
        }
        assert len(set(reasons.values())) == 3

    def test_nwt_rsn_rsr_included_reasons_are_all_distinct(self):
        snapshot = _snapshot([
            _snapshot_row("p_nwt", "NWT", last_season=PREDICTION_SEASON - 1),
            _snapshot_row("p_rsn", "RSN", last_season=PREDICTION_SEASON - 1),
            _snapshot_row("p_rsr", "RSR", last_season=PREDICTION_SEASON - 1),
        ])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        reasons = dict(zip(result.included["player_id"], result.included["inclusion_reason"]))
        assert reasons == {
            "p_nwt": "included_nwt_recent",
            "p_rsn": "included_rsn_recent",
            "p_rsr": "included_rsr_recent",
        }


class TestNwtRecencyRule:
    def test_recent_nwt_is_included(self):
        snapshot = _snapshot([_snapshot_row("p1", "NWT", last_season=PREDICTION_SEASON - 1)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1
        assert result.included.iloc[0]["inclusion_reason"] == "included_nwt_recent"

    def test_stale_nwt_is_excluded_with_governed_reason(self):
        snapshot = _snapshot([_snapshot_row("p1", "NWT", last_season=PREDICTION_SEASON - 5)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert result.included.empty
        assert result.excluded.iloc[0]["exclusion_reason"] == "nwt_stale_last_season_excluded"

    def test_nwt_with_no_last_season_is_excluded_not_guessed(self):
        snapshot = _snapshot([_snapshot_row("p1", "NWT", last_season=None)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert result.included.empty
        assert result.excluded.iloc[0]["exclusion_reason"] == "nwt_no_last_season_excluded"

    def test_nwt_exactly_at_the_recency_boundary_is_included(self):
        # last_season == prediction_season - 1 is the boundary itself.
        snapshot = _snapshot([_snapshot_row("p1", "NWT", last_season=PREDICTION_SEASON - 1)])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert len(result.included) == 1


class TestDuplicateIdentity:
    def test_duplicate_gsis_id_is_excluded_not_guessed(self):
        snapshot = _snapshot([
            _snapshot_row("dup1", "ACT", latest_team="ARI"),
            _snapshot_row("dup1", "ACT", latest_team="SEA"),
            _snapshot_row("clean1", "ACT"),
        ])
        result = build_future_season_roster_spine(snapshot, PREDICTION_SEASON, VALID_SNAPSHOT_TIME, WEEK1_KICKOFF)
        assert list(result.included["player_id"]) == ["clean1"]
        assert set(result.excluded["player_id"]) == {"dup1"}
        assert (result.excluded["exclusion_reason"] == "duplicate_gsis_id").all()


class TestFamily9SupersetVerification:
    def test_passes_when_spine_covers_every_family9_key(self):
        spine = pd.DataFrame({"prediction_season": [2026, 2026], "player_id": ["p1", "p2"]})
        fam9 = pd.DataFrame({"prediction_season": [2026], "player_id": ["p1"]})
        verify_family9_superset(spine, fam9)  # must not raise

    def test_raises_when_a_family9_key_is_missing_from_the_spine(self):
        spine = pd.DataFrame({"prediction_season": [2026], "player_id": ["p1"]})
        fam9 = pd.DataFrame({"prediction_season": [2026, 2026], "player_id": ["p1", "p2"]})
        with pytest.raises(ValueError, match="missing 1"):
            verify_family9_superset(spine, fam9)


class TestExtendPopulationWithFutureSpine:
    _COLUMNS = ("season", "player_id", "position", "team", "ppg_ppr")

    def test_adds_identity_only_rows_with_other_columns_null(self):
        population = pd.DataFrame({
            "season": [2025], "player_id": ["p1"], "position": ["WR"], "team": ["ARI"], "ppg_ppr": [12.5],
        })
        spine = pd.DataFrame({
            "prediction_season": [2026], "player_id": ["p2"], "position": ["RB"], "team": ["SEA"],
            "roster_status": ["ACT"], "inclusion_reason": ["included_status_ACT"],
        })
        extended = extend_population_with_future_spine(population, spine, self._COLUMNS)
        assert len(extended) == 2
        new_row = extended[extended["season"] == 2026].iloc[0]
        assert new_row["player_id"] == "p2"
        assert new_row["position"] == "RB"
        assert new_row["team"] == "SEA"
        assert pd.isna(new_row["ppg_ppr"])

    def test_existing_historical_rows_are_unchanged(self):
        population = pd.DataFrame({
            "season": [2025], "player_id": ["p1"], "position": ["WR"], "team": ["ARI"], "ppg_ppr": [12.5],
        })
        spine = pd.DataFrame({
            "prediction_season": [2026], "player_id": ["p2"], "position": ["RB"], "team": ["SEA"],
            "roster_status": ["ACT"], "inclusion_reason": ["included_status_ACT"],
        })
        extended = extend_population_with_future_spine(population, spine, self._COLUMNS)
        original_row = extended[extended["season"] == 2025].iloc[0]
        pd.testing.assert_series_equal(
            original_row[list(self._COLUMNS)], population.iloc[0][list(self._COLUMNS)], check_names=False,
        )

    def test_raises_on_key_collision_with_existing_population(self):
        population = pd.DataFrame({
            "season": [2026], "player_id": ["p1"], "position": ["WR"], "team": ["ARI"], "ppg_ppr": [12.5],
        })
        spine = pd.DataFrame({
            "prediction_season": [2026], "player_id": ["p1"], "position": ["WR"], "team": ["ARI"],
            "roster_status": ["ACT"], "inclusion_reason": ["included_status_ACT"],
        })
        with pytest.raises(ValueError, match="collides"):
            extend_population_with_future_spine(population, spine, self._COLUMNS)


class TestRosterStatusProvenanceFrame:
    def test_returns_a_metadata_only_frame_named_distinctly_from_any_predictor(self):
        spine = pd.DataFrame({
            "prediction_season": [2026], "player_id": ["p1"], "position": ["WR"], "team": ["ARI"],
            "roster_status": ["SUS"], "inclusion_reason": ["included_status_SUS"],
        })
        frame = roster_status_provenance_frame(spine)
        assert list(frame.columns) == ["prediction_season", "player_id", "future_season_roster_status"]
        assert frame.iloc[0]["future_season_roster_status"] == "SUS"


class TestNoHistoricalContamination:
    """Guards the explicit requirement that this mechanism never touches
    (or could be mistaken for touching) any historical prediction_season
    row -- see the module docstring's SCOPE section."""

    def test_provenance_frame_only_ever_carries_spine_rows(self):
        spine = pd.DataFrame({
            "prediction_season": [2026], "player_id": ["p1"], "position": ["WR"], "team": ["ARI"],
            "roster_status": ["ACT"], "inclusion_reason": ["included_status_ACT"],
        })
        frame = roster_status_provenance_frame(spine)
        assert set(frame["prediction_season"].unique()) == {2026}

    def test_a_historical_season_population_row_is_never_reclassified_by_extension(self):
        population = pd.DataFrame({
            "season": [2025, 2024], "player_id": ["p1", "p2"], "position": ["WR", "RB"],
            "team": ["ARI", "SEA"], "ppg_ppr": [12.5, 9.0],
        })
        spine = pd.DataFrame({
            "prediction_season": [2026], "player_id": ["p3"], "position": ["TE"], "team": ["KC"],
            "roster_status": ["ACT"], "inclusion_reason": ["included_status_ACT"],
        })
        extended = extend_population_with_future_spine(population, spine, ("season", "player_id", "position", "team", "ppg_ppr"))
        historical = extended[extended["season"].isin([2024, 2025])].sort_values("season").reset_index(drop=True)
        expected = population.sort_values("season").reset_index(drop=True)
        pd.testing.assert_frame_equal(historical[list(population.columns)], expected[list(population.columns)])
