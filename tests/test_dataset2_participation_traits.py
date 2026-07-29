"""
tests/test_dataset2_participation_traits.py

Protects lib/dataset2/participation_traits.py -- Dataset 2 Source C
Stage 1, approved (2026-07) in a NARROWED FOUNDATION ROLE (see
research/dataset2/PARTICIPATION_SOURCE_SCOPE_ASSESSMENT_2026_07.md).
This module builds raw acquisition and normalized player-play-role
participation only -- no season-level or preseason-predictor layer
exists in this module (removed 2026-07; see the module docstring's
"WHAT WAS REMOVED" section). Every edge case tested here was
explicitly required by the Stage 1 instructions; real occurrence rates
for each are documented in
research/dataset2/PARTICIPATION_SCHEMA_AUDIT_2026_07.md: malformed
tokens (0 real), cross-role ID conflicts (0 real), duplicate source IDs
within one list (470 real, mostly 2019), empty/null semicolon lists,
both real schema shapes (20-col/26-col), postseason derivation from
`nflverse_game_id` alone, and real duplicate-play detection.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.common import season_length
from lib.dataset2.participation_traits import (
    NORMALIZED_OUTPUT_COLUMNS,
    ROLE_NON_POSSESSION,
    ROLE_POSSESSION,
    build_duplicate_source_id_report,
    build_raw_play_data,
    normalize_participation,
)


def _game_id(season: int, week: int, away="AWY", home="HOM") -> str:
    return f"{season}_{week:02d}_{away}_{home}"


def _raw_row(season, week, play_id, possession="AWY", off="00-0000001;00-0000002", defn="00-0000003;00-0000004", **extra):
    row = {
        "nflverse_game_id": _game_id(season, week),
        "play_id": play_id,
        "possession_team": possession,
        "offense_players": off,
        "defense_players": defn,
    }
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# build_raw_play_data
# ---------------------------------------------------------------------------


class TestRawPlayDataDerivation:
    """Protects the season/week/postseason derivation from
    nflverse_game_id alone -- the real source has no explicit
    season/week/game_type columns, unlike snap_counts."""

    def test_parses_season_and_week_token(self):
        df = pd.DataFrame([_raw_row(2023, 5, 1)])
        out = build_raw_play_data(df)
        assert out.loc[0, "season"] == 2023
        assert out.loc[0, "week_token"] == "05"

    def test_regular_season_week_not_flagged_postseason(self):
        reg_max = season_length(2023) + 1
        df = pd.DataFrame([_raw_row(2023, reg_max, 1)])
        out = build_raw_play_data(df, include_postseason=True)
        assert out.loc[0, "is_postseason"] == False  # noqa: E712

    def test_week_beyond_reg_max_is_postseason(self):
        reg_max = season_length(2023) + 1
        df = pd.DataFrame([_raw_row(2023, reg_max + 1, 1)])
        out = build_raw_play_data(df, include_postseason=True)
        assert out.loc[0, "is_postseason"] == True  # noqa: E712

    def test_postseason_excluded_by_default(self):
        reg_max = season_length(2023) + 1
        df = pd.DataFrame([_raw_row(2023, 5, 1), _raw_row(2023, reg_max + 1, 2)])
        out = build_raw_play_data(df)
        assert len(out) == 1
        assert out.loc[0, "play_id"] == 1

    def test_postseason_retained_when_requested(self):
        reg_max = season_length(2023) + 1
        df = pd.DataFrame([_raw_row(2023, 5, 1), _raw_row(2023, reg_max + 1, 2)])
        out = build_raw_play_data(df, include_postseason=True)
        assert len(out) == 2

    def test_pre_2021_era_uses_16_game_season_length(self):
        # Real 2016 week tokens run 01-21 (17 real REG week-slots incl.
        # bye + 4 real playoff rounds) -- verified against real data.
        reg_max = season_length(2016) + 1
        assert reg_max == 17
        df = pd.DataFrame([_raw_row(2016, 17, 1), _raw_row(2016, 18, 2)])
        out = build_raw_play_data(df, include_postseason=True)
        assert out.set_index("play_id")["is_postseason"].to_dict() == {1: False, 2: True}


class TestRawPlayDataDuplicateDetection:
    def test_raises_on_duplicate_game_id_play_id(self):
        df = pd.DataFrame([_raw_row(2023, 5, 1), _raw_row(2023, 5, 1)])
        with pytest.raises(RuntimeError, match="duplicate"):
            build_raw_play_data(df)

    def test_same_play_id_different_games_is_not_a_duplicate(self):
        df = pd.DataFrame(
            [
                _raw_row(2023, 5, 1),
                {**_raw_row(2023, 6, 1), "nflverse_game_id": _game_id(2023, 6, away="XYZ")},
            ]
        )
        out = build_raw_play_data(df)
        assert len(out) == 2

    def test_missing_required_column_raises(self):
        df = pd.DataFrame([{"nflverse_game_id": _game_id(2023, 5), "play_id": 1}])
        with pytest.raises(ValueError, match="missing required columns"):
            build_raw_play_data(df)

    def test_raw_source_lists_preserved_unchanged(self):
        # Preserving the raw list verbatim (including a real duplicate
        # entry) is required so normalize_participation() can still
        # compute a correct source_occurrence_count downstream.
        df = pd.DataFrame([_raw_row(2023, 5, 1, off="00-0000001;00-0000001;00-0000002")])
        out = build_raw_play_data(df)
        assert out.loc[0, "offense_players"] == "00-0000001;00-0000001;00-0000002"


# ---------------------------------------------------------------------------
# normalize_participation
# ---------------------------------------------------------------------------


class TestNormalizeBasicSplit:
    def test_explodes_possession_and_non_possession_rows(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1)]))
        out = normalize_participation(raw)
        assert set(out["role"]) == {ROLE_POSSESSION, ROLE_NON_POSSESSION}
        assert len(out) == 4  # 2 possession-side + 2 non-possession-side ids

    def test_possession_role_team_is_possession_team(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, possession="AWY")]))
        out = normalize_participation(raw)
        poss_rows = out[out["role"] == ROLE_POSSESSION]
        assert (poss_rows["team"] == "AWY").all()

    def test_non_possession_role_team_is_the_other_real_game_team(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, possession="AWY")]))
        out = normalize_participation(raw)
        non_poss_rows = out[out["role"] == ROLE_NON_POSSESSION]
        assert (non_poss_rows["team"] == "HOM").all()

    def test_non_possession_team_flips_when_home_has_possession(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, possession="HOM")]))
        out = normalize_participation(raw)
        non_poss_rows = out[out["role"] == ROLE_NON_POSSESSION]
        assert (non_poss_rows["team"] == "AWY").all()

    def test_output_has_expected_columns(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1)]))
        out = normalize_participation(raw)
        assert list(out.columns) == list(NORMALIZED_OUTPUT_COLUMNS)


class TestNormalizeEmptyAndNullLists:
    def test_null_offense_players_produces_no_possession_rows(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, off=None)]))
        out = normalize_participation(raw)
        assert (out["role"] == ROLE_POSSESSION).sum() == 0
        assert (out["role"] == ROLE_NON_POSSESSION).sum() == 2

    def test_empty_string_list_produces_no_rows(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, off="")]))
        out = normalize_participation(raw)
        assert (out["role"] == ROLE_POSSESSION).sum() == 0

    def test_trailing_separator_does_not_create_empty_token_row(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, off="00-0000001;")]))
        out = normalize_participation(raw)
        poss_rows = out[out["role"] == ROLE_POSSESSION]
        assert len(poss_rows) == 1
        assert poss_rows.iloc[0]["gsis_id"] == "00-0000001"

    def test_all_rows_dropped_leaves_empty_frame_with_correct_columns(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, off=None, defn=None)]))
        out = normalize_participation(raw)
        assert len(out) == 0
        assert list(out.columns) == list(NORMALIZED_OUTPUT_COLUMNS)


class TestNormalizeMalformedTokens:
    """Real data showed zero malformed tokens across the full real
    2016-2025 population, but the source must still be defended against
    one -- preserved and flagged, never dropped, never a crash."""

    def test_malformed_token_flagged_not_dropped(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, off="NOT-A-REAL-ID;00-0000002")]))
        out = normalize_participation(raw)
        bad_row = out[out["gsis_id"] == "NOT-A-REAL-ID"]
        assert len(bad_row) == 1
        assert bad_row.iloc[0]["has_malformed_token"] == True  # noqa: E712

    def test_well_formed_token_not_flagged(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1)]))
        out = normalize_participation(raw)
        assert (out["has_malformed_token"] == False).all()  # noqa: E712


class TestNormalizeDuplicateSourceIds:
    """Real data showed 470 real within-list duplicates (467 in 2019
    alone) -- a genuine, nonzero anomaly, not a hypothetical. A
    duplicated id must collapse to exactly ONE normalized row (never
    one row per raw occurrence), disclosed via source_occurrence_count/
    had_duplicate_source_id, so it structurally cannot inflate a
    downstream count."""

    def test_duplicate_id_within_one_list_collapses_to_one_row(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, off="00-0000001;00-0000001;00-0000002")]))
        out = normalize_participation(raw)
        poss_rows = out[out["role"] == ROLE_POSSESSION]
        # Exactly one row per distinct id, not one row per raw occurrence.
        assert sorted(poss_rows["gsis_id"].tolist()) == ["00-0000001", "00-0000002"]
        assert len(poss_rows) == 2

    def test_duplicated_id_gets_correct_occurrence_count_and_flag(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1, off="00-0000001;00-0000001;00-0000001")]))
        out = normalize_participation(raw)
        row = out[(out["role"] == ROLE_POSSESSION) & (out["gsis_id"] == "00-0000001")].iloc[0]
        assert row["source_occurrence_count"] == 3
        assert row["had_duplicate_source_id"] == True  # noqa: E712

    def test_non_duplicated_id_has_occurrence_count_one_and_no_flag(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1)]))
        out = normalize_participation(raw)
        assert (out["source_occurrence_count"] == 1).all()
        assert (out["had_duplicate_source_id"] == False).all()  # noqa: E712

    def test_duplicated_id_extended_fields_keep_first_occurrence(self):
        raw_df = pd.DataFrame(
            [
                _raw_row(
                    2023,
                    5,
                    1,
                    off="00-0000001;00-0000001",
                    offense_names="First.Entry;Second.Entry",
                    offense_positions="WR;WR",
                    offense_numbers="10;99",
                )
            ]
        )
        raw = build_raw_play_data(raw_df)
        out = normalize_participation(raw)
        row = out[(out["role"] == ROLE_POSSESSION) & (out["gsis_id"] == "00-0000001")].iloc[0]
        assert row["player_name"] == "First.Entry"
        assert row["player_number"] == "10"


class TestNormalizeCrossRoleConflict:
    """Real data showed zero IDs appearing in both offense_players and
    defense_players on the same play -- structurally impossible in a
    real snap, but must be flagged (not silently resolved) if it ever
    occurs."""

    def test_id_in_both_lists_flagged_on_both_role_rows(self):
        raw = build_raw_play_data(
            pd.DataFrame([_raw_row(2023, 5, 1, off="00-0000001;00-0000002", defn="00-0000001;00-0000003")])
        )
        out = normalize_participation(raw)
        conflict_rows = out[out["gsis_id"] == "00-0000001"]
        assert len(conflict_rows) == 2
        assert set(conflict_rows["role"]) == {ROLE_POSSESSION, ROLE_NON_POSSESSION}
        assert (conflict_rows["cross_role_conflict"] == True).all()  # noqa: E712

    def test_non_conflicting_ids_not_flagged(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1)]))
        out = normalize_participation(raw)
        assert (out["cross_role_conflict"] == False).all()  # noqa: E712


class TestNormalizeExtendedSchema:
    """Real 26-col 2023-2025 schema exposes names/positions/numbers,
    verified list-aligned with the player-ID list on real data."""

    def test_extended_fields_populated_when_present(self):
        raw_df = pd.DataFrame(
            [
                _raw_row(
                    2023,
                    5,
                    1,
                    off="00-0000001;00-0000002",
                    offense_names="A.Player;B.Player",
                    offense_positions="QB;WR",
                    offense_numbers="1;2",
                )
            ]
        )
        raw = build_raw_play_data(raw_df)
        out = normalize_participation(raw)
        poss_rows = out[out["role"] == ROLE_POSSESSION].sort_values("gsis_id")
        assert poss_rows["player_name"].tolist() == ["A.Player", "B.Player"]
        assert poss_rows["player_position"].tolist() == ["QB", "WR"]

    def test_missing_extended_schema_leaves_optional_fields_null(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1)]))
        out = normalize_participation(raw)
        assert out["player_name"].isna().all()
        assert out["player_position"].isna().all()


# ---------------------------------------------------------------------------
# build_duplicate_source_id_report
# ---------------------------------------------------------------------------


class TestDuplicateSourceIdReport:
    def test_reports_affected_identity_and_excess_occurrences_by_season_and_role(self):
        raw = build_raw_play_data(
            pd.DataFrame(
                [
                    _raw_row(2022, 1, 1, off="00-0000001;00-0000001;00-0000001"),  # 2 excess
                    _raw_row(2023, 1, 2, defn="00-0000003;00-0000003"),  # 1 excess
                ]
            )
        )
        normalized = normalize_participation(raw)
        report = build_duplicate_source_id_report(normalized)
        row_2022 = report[(report["season"] == 2022) & (report["role"] == ROLE_POSSESSION)].iloc[0]
        assert row_2022["n_affected_identities"] == 1
        assert row_2022["total_excess_occurrences"] == 2

        row_2023 = report[(report["season"] == 2023) & (report["role"] == ROLE_NON_POSSESSION)].iloc[0]
        assert row_2023["n_affected_identities"] == 1
        assert row_2023["total_excess_occurrences"] == 1

    def test_empty_when_no_duplicates(self):
        raw = build_raw_play_data(pd.DataFrame([_raw_row(2023, 5, 1)]))
        normalized = normalize_participation(raw)
        report = build_duplicate_source_id_report(normalized)
        assert len(report) == 0
