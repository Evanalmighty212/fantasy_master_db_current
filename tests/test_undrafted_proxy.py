"""
tests/test_undrafted_proxy.py

Covers the undrafted-player representation mechanism added to
04_build_master_dataset.py and 05_calculate_metrics.py: verified-
undrafted players get a fixed proxy ADP and flow through the SAME
unified LWI pipeline as drafted players, per the product decision
that a "League Winner Index" must be able to recognize genuine
undrafted breakouts (James Robinson 2020, Victor Cruz 2011, etc.)
rather than structurally excluding them.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "04_build_master_dataset.py"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("build_master_dataset", SCRIPT_PATH)
    m = importlib.util.module_from_spec(spec)
    sys.modules["build_master_dataset"] = m
    spec.loader.exec_module(m)
    return m


class TestUnresolvedIsNeverAssumedUndrafted:
    """The core epistemic guard: a player absent from our current ADP
    source is 'unresolved', NOT 'undrafted', until someone explicitly
    verifies it. These must never be conflated."""

    def test_unmatched_player_not_in_verification_table_stays_unresolved(self, mod):
        master = pd.DataFrame({
            "season": [2020], "player_id": ["00-TEST"], "position": ["RB"],
            "overall_adp": [np.nan], "positional_adp": [np.nan],
            "data_quality_flag": ["no_adp_match"],
        })
        empty_verification = pd.DataFrame(columns=["player_id", "season", "adp_status", "verification_status", "notes"])
        result = mod.apply_adp_status_and_proxy(master, empty_verification)
        assert result.iloc[0]["verification_status"] == "unresolved"
        assert pd.isna(result.iloc[0]["adp_status"])
        assert pd.isna(result.iloc[0]["overall_adp_model"])


class TestDraftedPlayersUnaffected:
    def test_drafted_player_observed_equals_model(self, mod):
        master = pd.DataFrame({
            "season": [2020], "player_id": ["00-TEST"], "position": ["WR"],
            "overall_adp": [25.0], "positional_adp": [5.0],
            "data_quality_flag": ["matched_clean"],
        })
        empty_verification = pd.DataFrame(columns=["player_id", "season", "adp_status", "verification_status", "notes"])
        result = mod.apply_adp_status_and_proxy(master, empty_verification)
        row = result.iloc[0]
        assert row["adp_status"] == "drafted"
        assert row["verification_status"] == "verified"
        assert row["overall_adp_model"] == 25.0
        assert row["adp_proxy_used"] == False


class TestVerifiedUndraftedProxy:
    def test_verified_undrafted_gets_global_max_plus_one(self, mod):
        master = pd.DataFrame({
            "season": [2020], "player_id": ["00-TEST"], "position": ["RB"],
            "overall_adp": [np.nan], "positional_adp": [np.nan],
            "data_quality_flag": ["no_adp_match"],
        })
        verification = pd.DataFrame([{
            "player_id": "00-TEST", "season": "2020",
            "adp_status": "undrafted", "verification_status": "verified",
            "notes": "test",
        }])
        result = mod.apply_adp_status_and_proxy(master, verification)
        row = result.iloc[0]
        assert row["adp_status"] == "undrafted"
        assert row["verification_status"] == "verified"
        assert row["adp_proxy_used"] == True
        assert row["overall_adp_model"] == mod.LWI_GLOBAL_MAX_OVERALL_ADP + 1
        assert row["positional_adp_model"] == mod.LWI_GLOBAL_MAX_POSITIONAL_ADP["RB"] + 1
        assert row["adp_proxy_reason"] == "global_max_adp_plus_one"
        # Observed stays null -- there was no real draft to observe
        assert pd.isna(row["overall_adp_observed"])

    def test_blank_season_in_verification_table_applies_to_all_that_players_seasons(self, mod):
        # Same pattern as position_overrides.csv -- a blank season
        # column means "applies to every season for this player_id".
        master = pd.DataFrame({
            "season": [2019, 2020], "player_id": ["00-TEST", "00-TEST"],
            "position": ["RB", "RB"],
            "overall_adp": [np.nan, np.nan], "positional_adp": [np.nan, np.nan],
            "data_quality_flag": ["no_adp_match", "no_adp_match"],
        })
        verification = pd.DataFrame([{
            "player_id": "00-TEST", "season": "",
            "adp_status": "undrafted", "verification_status": "verified",
            "notes": "test",
        }])
        result = mod.apply_adp_status_and_proxy(master, verification)
        assert (result["adp_status"] == "undrafted").all()
        assert (result["verification_status"] == "verified").all()


class TestGlobalMaxIsFixedNotSeasonRelative:
    """Verifies the specific product decision that the proxy uses the
    GLOBAL max ADP across all seasons, not each season's own deepest
    pick -- so players aren't unfairly rewarded/penalized based on how
    deep that particular season's ADP source happened to go."""

    def test_proxy_identical_regardless_of_season(self, mod):
        master = pd.DataFrame({
            "season": [2010, 2022], "player_id": ["00-A", "00-B"],
            "position": ["QB", "QB"],
            "overall_adp": [np.nan, np.nan], "positional_adp": [np.nan, np.nan],
            "data_quality_flag": ["no_adp_match", "no_adp_match"],
        })
        # 2010's source went to 214 players; 2022's only went to 146 --
        # if the proxy were season-relative, these would differ.
        verification = pd.DataFrame([
            {"player_id": "00-A", "season": "2010", "adp_status": "undrafted", "verification_status": "verified", "notes": ""},
            {"player_id": "00-B", "season": "2022", "adp_status": "undrafted", "verification_status": "verified", "notes": ""},
        ])
        result = mod.apply_adp_status_and_proxy(master, verification)
        assert result.iloc[0]["overall_adp_model"] == result.iloc[1]["overall_adp_model"], (
            "Proxy ADP differed by season -- it must be a fixed global "
            "constant, not season-relative."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
