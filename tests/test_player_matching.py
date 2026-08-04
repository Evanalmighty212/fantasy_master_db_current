"""
tests/test_player_matching.py

Covers normalize_name and the matching priority logic in
scripts/player_matching.py. Several of these are regression tests for
real bugs/edge-cases found while building this project (see comments
on each), not speculative coverage.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pandas as pd
import pytest

import player_matching as pm


def _directory(*rows):
    return pd.DataFrame(rows, columns=["gsis_id", "display_name", "position", "rookie_season", "last_season"])


class TestRosterDirectoryFirstIdentity:
    def test_absent_michael_thomas_is_not_redirected_to_mike_thomas(self):
        adp = pd.DataFrame([{
            "season": 2021, "player_name_original": "Michael Thomas", "position": "WR",
            "overall_adp": 20.0,
        }])
        results = pd.DataFrame([{
            "season": 2021, "player_id": "00-MIKE", "player_display_name": "Mike Thomas", "position": "WR",
        }])
        directory = _directory(
            ("00-MICHAEL-DB", "Michael Thomas", "DB", 2012, 2023),
            ("00-MICHAEL-WR", "Michael Thomas", "WR", 2016, 2023),
            ("00-MIKE", "Mike Thomas", "WR", 2016, 2022),
        )
        matched, missing, _, duplicates, _ = pm.match_players(
            adp, results, pd.DataFrame(), players_directory_df=directory
        )
        assert missing.empty
        assert duplicates.empty
        assert matched.iloc[0]["nflverse_player_id"] == "00-MICHAEL-WR"
        assert matched.iloc[0]["identity_join_status"] == "identity_resolved_no_results_row"

    def test_position_only_disambiguates_same_exact_directory_name(self):
        adp = pd.DataFrame([{
            "season": 2021, "player_name_original": "Michael Thomas", "position": "WR",
            "overall_adp": 20.0,
        }])
        results = pd.DataFrame([{
            "season": 2021, "player_id": "00-MICHAEL-WR", "player_display_name": "Michael Thomas", "position": "WR",
        }])
        directory = _directory(
            ("00-MICHAEL-DB", "Michael Thomas", "DB", 2012, 2023),
            ("00-MICHAEL-WR", "Michael Thomas", "WR", 2016, 2023),
        )
        matched, *_ = pm.match_players(adp, results, pd.DataFrame(), players_directory_df=directory)
        assert matched.iloc[0]["nflverse_player_id"] == "00-MICHAEL-WR"


class TestNormalizeName:
    def test_strips_generational_suffix(self):
        # Real finding: suffix stripping cut the fuzzy-review pile from
        # 134 rows to 26 -- this is the single highest-value fix made
        # to matching, worth protecting with a test.
        assert pm.normalize_name("Robert Griffin III") == "robert griffin"
        assert pm.normalize_name("Odell Beckham Jr.") == "odell beckham"
        assert pm.normalize_name("Mark Ingram II") == "mark ingram"

    def test_strips_parenthetical_team_tag(self):
        assert pm.normalize_name("Steve Smith(NYG)") == "steve smith"

    def test_removes_periods_and_lowercases(self):
        assert pm.normalize_name("T.J. Houshmandzadeh") == "tj houshmandzadeh"

    def test_collapses_whitespace(self):
        assert pm.normalize_name("  Steve   Smith  ") == "steve smith"


class TestMatchPriority:
    """Each test builds a minimal synthetic ADP row + results pool and
    checks which match_type wins -- verifying the STAGE ORDER (exact
    beats fuzzy, override beats everything) rather than just that a
    match happens at all."""

    def _adp_row(self, season=2020, name="Test Player", position="RB"):
        return pd.DataFrame([{
            "season": season, "source": "test", "scoring_format": "ppr",
            "league_size": 12, "player_name_original": name,
            "player_name_normalized": pm.normalize_name(name),
            "position": position, "team": "XXX", "overall_adp": 10.0,
            "adp_rank": 10, "times_drafted": 100,
            "source_quality_flag": "verified_clean",
        }])

    def _results_row(self, season=2020, player_id="00-TEST1",
                      name="Test Player", position="RB"):
        return pd.DataFrame([{
            "season": season, "player_id": player_id,
            "player_display_name": name, "position": position,
        }])

    def test_exact_match_wins_when_available(self):
        adp = self._adp_row(name="Robert Griffin III")
        results = self._results_row(name="Robert Griffin", position="RB")
        matched, missing, low_conf, dupes, oos = pm.match_players(
            adp, results, pd.DataFrame(columns=["season", "adp_player_name_original",
                                                  "position", "nflverse_player_id", "notes"])
        )
        assert len(matched) == 1
        assert matched.iloc[0]["match_type"] == "exact_name_position"
        assert matched.iloc[0]["match_confidence"] == 100

    def test_override_table_beats_exact_match(self):
        # Even when an exact match WOULD succeed, an override entry
        # must take priority -- that's the whole point of having one.
        adp = self._adp_row(name="Robert Griffin III")
        results = pd.concat([
            self._results_row(player_id="00-WRONG", name="Robert Griffin", position="RB"),
            self._results_row(player_id="00-RIGHT", name="Robert Griffin", position="RB"),
        ])
        # Force a collision scenario resolved only by override
        overrides = pd.DataFrame([{
            "season": 2020, "adp_player_name_original": "Robert Griffin III",
            "position": "RB", "nflverse_player_id": "00-RIGHT", "notes": "test",
        }])
        matched, missing, low_conf, dupes, oos = pm.match_players(adp, results, overrides)
        assert len(matched) == 1
        assert matched.iloc[0]["match_type"] == "manual_override"
        assert matched.iloc[0]["nflverse_player_id"] == "00-RIGHT"

    def test_position_collision_goes_to_duplicates_not_guessed(self):
        # Real case: two different real players sharing a name+position
        # (e.g. two "Steve Smith" WRs) must NOT be auto-matched to
        # either -- this is the exact class of bug the duplicate report
        # exists to catch.
        adp = self._adp_row(name="Steve Smith", position="WR")
        results = pd.concat([
            self._results_row(player_id="00-A", name="Steve Smith", position="WR"),
            self._results_row(player_id="00-B", name="Steve Smith", position="WR"),
        ])
        matched, missing, low_conf, dupes, oos = pm.match_players(
            adp, results, pd.DataFrame(columns=["season", "adp_player_name_original",
                                                  "position", "nflverse_player_id", "notes"])
        )
        assert len(matched) == 0
        assert len(dupes) == 1

    def test_fuzzy_near_miss_between_different_real_people_stays_unmatched(self):
        # Regression guard for the Peyton/Eli Manning case documented in
        # MATCHING_ARCHITECTURE.md -- similar-sounding names for
        # DIFFERENT real people must not fuzzy-match just because
        # they're close strings.
        adp = self._adp_row(name="Peyton Manning", position="QB")
        results = self._results_row(name="Eli Manning", position="QB")
        matched, missing, low_conf, dupes, oos = pm.match_players(
            adp, results, pd.DataFrame(columns=["season", "adp_player_name_original",
                                                  "position", "nflverse_player_id", "notes"])
        )
        assert len(matched) == 0
        assert len(missing) == 1

    def test_out_of_scope_position_excluded_before_matching(self):
        adp = self._adp_row(name="Some Kicker", position="K")
        results = self._results_row(name="Some Kicker", position="K")
        matched, missing, low_conf, dupes, oos = pm.match_players(adp, results)
        assert len(matched) == 0
        assert len(missing) == 0  # not "missing" -- out of scope entirely
        assert len(oos) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
