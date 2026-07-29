"""
tests/test_dataset2_participation_identity.py

Protects lib/dataset2/participation_identity.py -- the identity audit
required for Source C Stage 1 even though pbp_participation needs no
pfr_id-style crosswalk (it natively reports gsis_id, the same ID
system the master DB population already uses). Verifies the three
real, distinct non-match situations stay distinguishable and that no
row is ever silently dropped.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.participation_identity import (
    MATCH_STATUS_MATCHED,
    MATCH_STATUS_UNMATCHED_MALFORMED_TOKEN,
    MATCH_STATUS_UNMATCHED_UNKNOWN_ID,
    MATCH_STATUS_UNMATCHED_WRONG_SEASON,
    audit_detail,
    build_identity_audit,
)


def _population():
    return pd.DataFrame(
        [
            {"season": 2023, "player_id": "00-0000001", "position": "QB"},
            {"season": 2022, "player_id": "00-0000005", "position": "RB"},
        ]
    )


def _normalized(rows):
    base_cols = {"season": None, "gsis_id": None, "has_malformed_token": False}
    return pd.DataFrame([{**base_cols, **r} for r in rows])


class TestAuditDetailClassification:
    def test_direct_match(self):
        out = audit_detail(_normalized([{"season": 2023, "gsis_id": "00-0000001"}]), _population())
        assert out.iloc[0]["match_status"] == MATCH_STATUS_MATCHED
        assert out.iloc[0]["population_position"] == "QB"

    def test_known_id_wrong_season(self):
        # 00-0000005 is known to the population, but only for 2022.
        out = audit_detail(_normalized([{"season": 2023, "gsis_id": "00-0000005"}]), _population())
        assert out.iloc[0]["match_status"] == MATCH_STATUS_UNMATCHED_WRONG_SEASON

    def test_unknown_id_never_in_population(self):
        out = audit_detail(_normalized([{"season": 2023, "gsis_id": "00-9999999"}]), _population())
        assert out.iloc[0]["match_status"] == MATCH_STATUS_UNMATCHED_UNKNOWN_ID

    def test_malformed_token_classified_before_lookup(self):
        out = audit_detail(
            _normalized([{"season": 2023, "gsis_id": "BAD-ID", "has_malformed_token": True}]), _population()
        )
        assert out.iloc[0]["match_status"] == MATCH_STATUS_UNMATCHED_MALFORMED_TOKEN

    def test_no_row_dropped(self):
        rows = [
            {"season": 2023, "gsis_id": "00-0000001"},
            {"season": 2023, "gsis_id": "00-9999999"},
            {"season": 2023, "gsis_id": "00-0000005"},
            {"season": 2023, "gsis_id": "BAD-ID", "has_malformed_token": True},
        ]
        out = audit_detail(_normalized(rows), _population())
        assert len(out) == len(rows)


class TestBuildIdentityAudit:
    def test_summary_by_season_match_rate(self):
        rows = [
            {"season": 2023, "gsis_id": "00-0000001"},  # matched
            {"season": 2023, "gsis_id": "00-9999999"},  # unmatched
        ]
        summary_by_season, _, _ = build_identity_audit(_normalized(rows), _population())
        row = summary_by_season[summary_by_season["season"] == 2023].iloc[0]
        assert row["match_rate"] == 0.5

    def test_summary_by_position_uses_unknown_bucket_for_unmatched(self):
        rows = [
            {"season": 2023, "gsis_id": "00-0000001"},  # matched, QB
            {"season": 2023, "gsis_id": "00-9999999"},  # unmatched, no known position
        ]
        _, summary_by_position, _ = build_identity_audit(_normalized(rows), _population())
        assert set(summary_by_position["audit_position"]) == {"QB", "unknown"}
        unknown_row = summary_by_position[summary_by_position["audit_position"] == "unknown"].iloc[0]
        assert unknown_row["match_rate"] == 0.0

    def test_unmatched_detail_never_empty_when_unmatched_rows_exist(self):
        rows = [{"season": 2023, "gsis_id": "00-9999999"}]
        _, _, unmatched_detail = build_identity_audit(_normalized(rows), _population())
        assert len(unmatched_detail) == 1
        assert unmatched_detail.iloc[0]["match_status"] == MATCH_STATUS_UNMATCHED_UNKNOWN_ID
        assert unmatched_detail.iloc[0]["n_plays_involved"] == 1

    def test_unmatched_detail_counts_multiple_occurrences(self):
        rows = [
            {"season": 2023, "gsis_id": "00-9999999"},
            {"season": 2023, "gsis_id": "00-9999999"},
            {"season": 2023, "gsis_id": "00-9999999"},
        ]
        _, _, unmatched_detail = build_identity_audit(_normalized(rows), _population())
        # audit is over distinct (season, gsis_id) identities, so repeat
        # occurrences collapse to one identity row here -- the *play*-
        # level occurrence count belongs to normalized data, not this
        # identity-level audit.
        assert len(unmatched_detail) == 1

    def test_fully_matched_population_has_empty_unmatched_detail(self):
        rows = [{"season": 2023, "gsis_id": "00-0000001"}]
        _, _, unmatched_detail = build_identity_audit(_normalized(rows), _population())
        assert len(unmatched_detail) == 0
