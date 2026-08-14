"""Master-schema provenance and canonical-authority regression tests."""

import importlib.util
import zipfile
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("master_authority", ROOT / "scripts/04_build_master_dataset.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_governed_2025_participation_survives_master_join_projection():
    source = pd.DataFrame([{
        "season": 2025, "nflverse_player_id": "P1", "overall_adp": 180.0,
        "adp_rank": 180, "positional_adp": 60, "source": "mfl_strict_142_pre_kickoff_2025",
        "position": "WR", "team": "AAA", "match_type": "exact_name_position",
        "match_confidence": 100.0, "draft_selection_count": 52,
        "draft_selection_denominator": 142, "draft_selection_rate": 52 / 142,
        "mfl_reconstruction_identity": "strict-142-test",
    }])
    out = mod.build_adp_slim(source).iloc[0]
    assert out["adp_source"] == "mfl_strict_142_pre_kickoff_2025"
    assert out["draft_selection_count"] == 52
    assert out["draft_selection_denominator"] == 142
    assert out["draft_selection_rate"] == pytest.approx(52 / 142)
    assert out["mfl_reconstruction_identity"] == "strict-142-test"


@pytest.mark.parametrize(
    "match_type,expected",
    [
        ("manual_override", "matched_clean"),
        ("roster_directory_exact", "matched_clean"),
        ("exact_name_position", "matched_clean"),
        ("fuzzy_high_confidence", "matched_clean"),
        ("exact_name_position_mismatch", "matched_needs_review"),
        ("fuzzy_low_confidence", "matched_needs_review"),
    ],
)
def test_master_quality_flag_uses_shared_real_match_literals(match_type, expected):
    row = pd.Series({"overall_adp": 42.0, "match_type": match_type})
    assert mod.flag_row(row) == expected


def test_master_quality_flag_rejects_unknown_observed_match_literal():
    row = pd.Series({"overall_adp": 42.0, "match_type": "new_unreviewed_match"})
    with pytest.raises(ValueError, match="unknown match_type"):
        mod.flag_row(row)


def _xlsx_fixture():
    return pd.DataFrame({
        "season": [2024, 2025],
        "player_id": ["P1", "P2"],
        "overall_adp": [10.1234567890123, 20.0],
        "preseason_market_status": ["ordinary_market", "rare_minimal_market"],
    })


def test_validated_xlsx_atomically_replaces_target_and_matches_csv(tmp_path):
    frame = _xlsx_fixture()
    csv_path = tmp_path / "master.csv"
    xlsx_path = tmp_path / "master.xlsx"
    csv_path.write_text(frame.to_csv(index=False))
    xlsx_path.write_bytes(b"old workbook")

    mod.write_validated_xlsx(frame, csv_path, xlsx_path)

    with zipfile.ZipFile(xlsx_path) as workbook_zip:
        assert workbook_zip.testzip() is None
    mod.validate_xlsx_against_csv(xlsx_path, csv_path)
    assert not list(tmp_path.glob(".*.tmp.xlsx"))


def test_xlsx_write_timeout_preserves_target_cleans_temp_and_raises(tmp_path, monkeypatch):
    frame = _xlsx_fixture()
    csv_path = tmp_path / "master.csv"
    xlsx_path = tmp_path / "master.xlsx"
    csv_path.write_text(frame.to_csv(index=False))
    xlsx_path.write_bytes(b"previous valid artifact")

    def timeout(*args, **kwargs):
        raise TimeoutError("simulated close timeout")

    monkeypatch.setattr(pd.DataFrame, "to_excel", timeout)
    with pytest.raises(TimeoutError, match="simulated close timeout"):
        mod.write_validated_xlsx(frame, csv_path, xlsx_path)
    assert xlsx_path.read_bytes() == b"previous valid artifact"
    assert not list(tmp_path.glob(".*.tmp.xlsx"))


def test_truncated_xlsx_never_replaces_target(tmp_path, monkeypatch):
    frame = _xlsx_fixture()
    csv_path = tmp_path / "master.csv"
    xlsx_path = tmp_path / "master.xlsx"
    csv_path.write_text(frame.to_csv(index=False))
    xlsx_path.write_bytes(b"previous valid artifact")

    def write_truncated(_self, path, **kwargs):
        Path(path).write_bytes(b"not an xlsx")

    monkeypatch.setattr(pd.DataFrame, "to_excel", write_truncated)
    with pytest.raises(ValueError, match="valid readable ZIP"):
        mod.write_validated_xlsx(frame, csv_path, xlsx_path)
    assert xlsx_path.read_bytes() == b"previous valid artifact"
    assert not list(tmp_path.glob(".*.tmp.xlsx"))


def test_semantically_wrong_xlsx_never_replaces_target(tmp_path, monkeypatch):
    frame = _xlsx_fixture()
    csv_path = tmp_path / "master.csv"
    xlsx_path = tmp_path / "master.xlsx"
    csv_path.write_text(frame.to_csv(index=False))
    xlsx_path.write_bytes(b"previous valid artifact")
    original_to_excel = pd.DataFrame.to_excel

    def write_wrong(_self, path, **kwargs):
        wrong = frame.copy()
        wrong.loc[0, "player_id"] = "WRONG"
        original_to_excel(wrong, path, index=False)

    monkeypatch.setattr(pd.DataFrame, "to_excel", write_wrong)
    with pytest.raises(ValueError, match="player-season keys"):
        mod.write_validated_xlsx(frame, csv_path, xlsx_path)
    assert xlsx_path.read_bytes() == b"previous valid artifact"
    assert not list(tmp_path.glob(".*.tmp.xlsx"))


def test_raw_provider_fields_survive_canonicalization(tmp_path):
    authority_path = ROOT / "data/manual/canonical_player_season_positions.csv"
    authority = mod.load_canonical_position_authority(authority_path)
    source = pd.DataFrame([{
        "season": 2019,
        "player_id": "00-0035624",
        "processed_position": "WR",
        "results_source_position_raw": "TE",
        "adp_source_position": "WR",
        "results_source_team_raw": "LV",
        "adp_source_team_raw": "NE",
        "match_type": "exact_name_position",
        "data_quality_flag": "matched_clean",
        "fantasy_points_ppr": 100.0,
        "position_finish_ppr": 99,
    }])
    out = mod.apply_player_season_authority(source, authority)
    assert out.loc[0, "results_source_position_raw"] == "TE"
    assert out.loc[0, "processed_position"] == "WR"
    assert out.loc[0, "adp_source_position"] == "WR"
    assert out.loc[0, "canonical_fantasy_position"] == "WR"
    assert out.loc[0, "results_source_team_raw"] == "LV"
    assert out.loc[0, "adp_source_team_raw"] == "NE"
    assert out.loc[0, "canonical_team"] == "OAK"


def test_unresolved_position_is_explicit_not_silently_canonicalized():
    authority = mod.load_canonical_position_authority(
        ROOT / "data/manual/canonical_player_season_positions.csv"
    )
    source = pd.DataFrame([{
        "season": 2020,
        "player_id": "00-0030578",
        "processed_position": "RB",
        "results_source_position_raw": "RB",
        "adp_source_position": "RB",
        "results_source_team_raw": "CHI",
        "adp_source_team_raw": "CHI",
        "match_type": "exact_name_position",
        "data_quality_flag": "matched_clean",
        "fantasy_points_ppr": 100.0,
        "position_finish_ppr": 1,
    }])
    out = mod.apply_player_season_authority(source, authority)
    assert pd.isna(out.loc[0, "canonical_fantasy_position"])
    assert out.loc[0, "canonical_position_status"] == "unresolved"
    assert pd.isna(out.loc[0, "position"])
    assert out.loc[0, "processed_position"] == "RB"


@pytest.mark.parametrize(
    "season,player_id,processed,adp,match_type,expected_status",
    [
        (2020, "00-0030578", "RB", "RB", "exact_name_position", "unresolved"),
        (2023, "00-0033357", "TE", "TE", "exact_name_position", "unresolved"),
        (2024, "IDENTITY-CONFLICT", "TE", "WR", "exact_name_position_mismatch", "unresolved_identity_conflict"),
    ],
)
def test_unresolved_rows_have_null_bare_position_but_preserve_provenance(
    season, player_id, processed, adp, match_type, expected_status,
):
    authority = mod.load_canonical_position_authority(
        ROOT / "data/manual/canonical_player_season_positions.csv"
    )
    source = pd.DataFrame([{
        "season": season, "player_id": player_id,
        "processed_position": processed, "results_source_position_raw": processed,
        "adp_source_position": adp, "results_source_team_raw": "AAA",
        "adp_source_team_raw": "AAA", "match_type": match_type,
        "data_quality_flag": "matched_needs_review" if "mismatch" in match_type else "matched_clean",
        "fantasy_points_ppr": 100.0, "position_finish_ppr": 1,
    }])
    out = mod.apply_player_season_authority(source, authority)
    assert pd.isna(out.loc[0, "position"])
    assert pd.isna(out.loc[0, "canonical_fantasy_position"])
    assert out.loc[0, "canonical_position_status"] == expected_status
    assert out.loc[0, "processed_position"] == processed
    assert out.loc[0, "results_source_position_raw"] == processed
    assert out.loc[0, "adp_source_position"] == adp


def test_missing_raw_provenance_fails_loudly():
    with pytest.raises(ValueError, match="lacks authority/provenance inputs"):
        mod.apply_player_season_authority(
            pd.DataFrame([{"season": 2020, "player_id": "P"}]), pd.DataFrame()
        )


def test_cross_position_change_recomputes_entire_canonical_finish_cohort():
    authority = mod.load_canonical_position_authority(
        ROOT / "data/manual/canonical_player_season_positions.csv"
    )
    shared = {
        "season": 2019, "results_source_team_raw": "NE", "adp_source_team_raw": "NE",
        "match_type": "exact_name_position", "data_quality_flag": "matched_clean",
    }
    source = pd.DataFrame([
        {**shared, "player_id": "00-0035624", "processed_position": "TE",
         "results_source_position_raw": "TE", "adp_source_position": "WR",
         "fantasy_points_ppr": 100.0, "position_finish_ppr": 1},
        {**shared, "player_id": "WR-HIGH", "processed_position": "WR",
         "results_source_position_raw": "WR", "adp_source_position": "WR",
         "fantasy_points_ppr": 120.0, "position_finish_ppr": 1},
        {**shared, "player_id": "WR-LOW", "processed_position": "WR",
         "results_source_position_raw": "WR", "adp_source_position": "WR",
         "fantasy_points_ppr": 80.0, "position_finish_ppr": 2},
    ])
    out = mod.apply_player_season_authority(source, authority).set_index("player_id")
    assert out.loc["00-0035624", "position"] == "WR"
    assert out.loc["00-0035624", "position_finish_ppr"] == 2
    assert out.loc["WR-LOW", "position_finish_ppr"] == 3


def test_no_results_identity_remains_in_positional_adp_denominator_only():
    matched = pd.DataFrame([
        {"season": 2021, "nflverse_player_id": "NO-RESULTS", "position": "WR",
         "overall_adp": 10.0, "identity_join_status": "identity_resolved_no_results_row"},
        {"season": 2021, "nflverse_player_id": "WITH-RESULTS", "position": "WR",
         "overall_adp": 20.0, "identity_join_status": "identity_resolved_with_results"},
    ])
    ranked = mod.compute_positional_adp_ranks(matched).set_index("nflverse_player_id")
    assert ranked.loc["NO-RESULTS", "positional_adp"] == 1
    assert ranked.loc["WITH-RESULTS", "positional_adp"] == 2
    # The function ranks ADP rows only; it cannot synthesize production.
    assert "fantasy_points_ppr" not in ranked.columns
