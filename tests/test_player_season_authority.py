"""Regression coverage for approved canonical player-season authority."""

from pathlib import Path

import pandas as pd
import pytest

from lib.player_season_authority import (
    add_canonical_fantasy_position,
    add_canonical_team,
    canonical_team,
    load_canonical_position_authority,
    resolved_canonical_position_population,
)


AUTHORITY_PATH = Path(__file__).resolve().parent.parent / "data/manual/canonical_player_season_positions.csv"


def _row(season, player_id, processed="TE", adp=None):
    return {
        "season": season,
        "player_id": player_id,
        "processed_position": processed,
        "adp_source_position": adp,
    }


def test_approved_position_treatments_and_unresolved_cases():
    authority = load_canonical_position_authority(AUTHORITY_PATH)
    rows = [
        _row(2019, "00-0035624"), _row(2022, "00-0035624"), _row(2023, "00-0035624"),
        _row(2013, "00-0030578", "RB"), _row(2020, "00-0030578", "RB", "RB"),
        _row(2021, "00-0030578", "WR"), _row(2012, "00-0027651", "WR"),
        _row(2013, "00-0027651", "RB"), _row(2016, "00-0032200", "RB"),
        _row(2017, "00-0032200", "WR"), _row(2012, "00-0028825", "WR"),
        _row(2016, "00-0028825", "QB"), _row(2021, "00-0035719", "WR"),
        _row(2011, "00-0026998", "WR"), _row(2023, "00-0033357", "TE", "TE"),
    ]
    out = add_canonical_fantasy_position(pd.DataFrame(rows), authority).set_index(["player_id", "season"])
    expected = {
        ("00-0035624", 2019): "WR", ("00-0035624", 2022): "WR",
        ("00-0035624", 2023): "TE", ("00-0030578", 2013): "WR",
        ("00-0030578", 2021): "RB", ("00-0027651", 2012): "RB",
        ("00-0027651", 2013): "WR", ("00-0032200", 2016): "WR",
        ("00-0032200", 2017): "RB", ("00-0028825", 2012): "QB",
        ("00-0028825", 2016): "WR", ("00-0035719", 2021): "WR",
        ("00-0026998", 2011): "WR",
    }
    for key, position in expected.items():
        assert out.loc[key, "canonical_fantasy_position"] == position
        assert out.loc[key, "canonical_position_status"] != "unresolved"
    for key in [("00-0030578", 2020), ("00-0033357", 2023)]:
        assert pd.isna(out.loc[key, "canonical_fantasy_position"])
        assert out.loc[key, "canonical_position_status"] == "unresolved"


def test_adp_source_precedes_processed_fallback_without_overwriting_provenance():
    authority = load_canonical_position_authority(AUTHORITY_PATH)
    source = pd.DataFrame([_row(2024, "00-X", processed="TE", adp="WR")])
    out = add_canonical_fantasy_position(source, authority)
    assert out.loc[0, "canonical_fantasy_position"] == "WR"
    assert out.loc[0, "canonical_position_authority"] == "adp_source_position"
    assert out.loc[0, "processed_position"] == "TE"
    assert out.loc[0, "adp_source_position"] == "WR"


@pytest.mark.parametrize("match_type", ["exact_name_position_mismatch", "fuzzy_low_confidence"])
def test_identity_conflict_blocks_adp_and_processed_authority(match_type):
    authority = load_canonical_position_authority(AUTHORITY_PATH)
    source = pd.DataFrame([{**_row(2024, "00-CONFLICT", processed="TE", adp="WR"),
                            "match_type": match_type}])
    out = add_canonical_fantasy_position(source, authority)
    assert pd.isna(out.loc[0, "canonical_fantasy_position"])
    assert out.loc[0, "canonical_position_status"] == "unresolved_identity_conflict"
    assert out.loc[0, "canonical_position_authority"] == "adp_source_position_with_identity_conflict"


def test_approved_override_supersedes_identity_conflict():
    authority = load_canonical_position_authority(AUTHORITY_PATH)
    source = pd.DataFrame([{**_row(2019, "00-0035624", processed="TE", adp="WR"),
                            "match_type": "exact_name_position_mismatch"}])
    out = add_canonical_fantasy_position(source, authority)
    assert out.loc[0, "canonical_fantasy_position"] == "WR"
    assert out.loc[0, "canonical_position_status"] == "approved_override"


def test_constrained_fallback_is_named_and_never_claimed_as_verified():
    authority = load_canonical_position_authority(AUTHORITY_PATH)
    source = pd.DataFrame([_row(2024, "00-CLEAN", processed="TE", adp=None)])
    out = add_canonical_fantasy_position(source, authority)
    assert out.loc[0, "canonical_fantasy_position"] == "TE"
    assert out.loc[0, "canonical_position_status"] == "constrained_fallback"
    assert out.loc[0, "canonical_position_authority"] == "processed_results_position_fallback"


def test_manual_and_unresolved_rules_supersede_adp_and_fallback():
    authority = load_canonical_position_authority(AUTHORITY_PATH)
    source = pd.DataFrame([
        _row(2017, "00-0032200", processed="WR", adp="WR"),
        _row(2020, "00-0030578", processed="RB", adp="RB"),
    ])
    out = add_canonical_fantasy_position(source, authority).set_index("player_id")
    assert out.loc["00-0032200", "canonical_fantasy_position"] == "RB"
    assert out.loc["00-0032200", "canonical_position_status"] == "approved_override"
    assert pd.isna(out.loc["00-0030578", "canonical_fantasy_position"])
    assert out.loc["00-0030578", "canonical_position_status"] == "unresolved"


def test_resolved_population_never_falls_back_to_bare_processed_position():
    source = pd.DataFrame([
        {"canonical_fantasy_position": "WR", "canonical_position_status": "adp_source",
         "position": "TE", "processed_position": "TE"},
        {"canonical_fantasy_position": pd.NA, "canonical_position_status": "unresolved",
         "position": "RB", "processed_position": "RB"},
    ])
    out = resolved_canonical_position_population(source)
    assert len(out) == 1
    assert out.iloc[0]["position"] == "WR"
    assert out.iloc[0]["processed_position"] == "TE"


def test_authority_validation_rejects_overlap(tmp_path):
    bad = pd.DataFrame([
        {"player_id": "P", "start_season": 2020, "end_season": 2021, "canonical_fantasy_position": "WR", "decision_status": "approved", "authority": "x", "notes": "x"},
        {"player_id": "P", "start_season": 2021, "end_season": 2022, "canonical_fantasy_position": "RB", "decision_status": "approved", "authority": "x", "notes": "x"},
    ])
    path = tmp_path / "bad.csv"
    bad.to_csv(path, index=False)
    with pytest.raises(ValueError, match="overlapping"):
        load_canonical_position_authority(path)


@pytest.mark.parametrize(
    "team,season,expected",
        [("LV", 2019, "OAK"), ("OAK", 2019, "OAK"), ("LV", 2020, "LV"),
         ("STL", 2015, "STL"), ("SD", 2016, "SD"), ("LAC", 2017, "LAC")],
)
def test_canonical_team_is_season_accurate(team, season, expected):
    assert canonical_team(team, season) == expected


def test_add_canonical_team_preserves_raw_provider_value():
    source = pd.DataFrame([{"season": 2019, "results_source_team_raw": "OAK"}])
    out = add_canonical_team(source, "results_source_team_raw")
    assert out.loc[0, "results_source_team_raw"] == "OAK"
    assert out.loc[0, "canonical_team"] == "OAK"
