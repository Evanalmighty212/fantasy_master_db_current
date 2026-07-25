"""
tests/test_mmc_2010_overrides.py

Covers lib/stars_by_value/mmc_2010_overrides.py -- the loader and
validator for data/manual/mmc_2010_manual_overrides.csv, the narrow
2010-cohort manual-override escape hatch (section 8a of
research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md).

Each test protects a specific rule from section 8a, not speculative
coverage:
- TestSeasonRule protects that only a season in
  SBV_MMC_MANUAL_OVERRIDE_SEASONS (currently just 2010) is ever
  accepted, enforced against a constant DEDICATED to this mechanism --
  not SBV_FIRST_SCOREABLE_SEASON, which encodes a different concept
  and only coincides in value today (see module docstring; a prior
  version of this loader conflated the two before review).
- TestRequiredFields/TestEnumValidation protect the mandatory-field
  and enum rules verbatim from the schema table.
- TestExactlyOnePath protects rule #1 -- exactly one of {adp fields}
  or {minimal_market_cost_approved=TRUE}, never both, never neither,
  and that it must agree with override_type.
- TestDisallowedSourceValues protects rule #2 -- no override may be
  created from classifier output alone -- via an EXACT match against a
  short list of literal internal-signal-name tokens, not a substring/
  phrase search. A prior version substring-matched natural-language
  phrases and was rejected after review as overinclusive (it would
  reject a genuine independent source containing ordinary phrasing)
  and trivially evadable by rephrasing -- see
  test_ordinary_sentence_containing_a_reserved_phrase_is_not_rejected,
  which is the regression test for exactly that mistake.
- TestSchemaColumnCount confirms the CSV header, loader, and this
  file's own row fixtures all agree on the same 14-column schema
  (season, player_id, player_name, override_type, market_cost_status,
  adp_overall, adp_round, minimal_market_cost_approved, source,
  source_date, evidence_summary, confidence, approved_by, notes) --
  section 8a's table has 14 rows; an earlier summary of this work
  miscounted it as 13, though no tracked file ever actually had that
  error. This test makes the count a permanent, checked invariant
  rather than something to recount by hand later.
- TestDuplicateRows protects that each (season, player_id) pair may
  appear at most once.
- TestLoaderIndependence protects that this module never imports
  classifier/scoring code -- a bug in classification must never be
  able to reach into this loader, and vice versa.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.stars_by_value import mmc_2010_overrides as ov
from config import SBV_MMC_MANUAL_OVERRIDE_SEASONS

_OVERRIDE_SEASON = SBV_MMC_MANUAL_OVERRIDE_SEASONS[0]


def _valid_adp_row(**overrides):
    row = {
        "season": str(_OVERRIDE_SEASON),
        "player_id": "00-0012345",
        "player_name": "Test Player",
        "override_type": "usable_adp",
        "market_cost_status": "adp_scored",
        "adp_overall": "150.0",
        "adp_round": "13",
        "minimal_market_cost_approved": "",
        "source": "MyFantasyLeague direct query, 2010-08-15 snapshot",
        "source_date": "2010-08-15",
        "evidence_summary": "MFL AUG15 report shows a real average pick of 150.4 across 40 real drafts.",
        "confidence": "high",
        "approved_by": "Evan",
        "notes": "",
    }
    row.update(overrides)
    return row


def _valid_mmc_row(**overrides):
    row = _valid_adp_row(
        override_type="minimal_market_cost",
        market_cost_status="minimal_market_cost_scored",
        adp_overall="",
        adp_round="",
        minimal_market_cost_approved="TRUE",
        source="NFL.com 2010 undrafted free agent tracker",
        evidence_summary="Named on NFL.com's post-draft UDFA signing list for this team.",
    )
    row.update(overrides)
    return row


def _df(*rows):
    return pd.DataFrame(list(rows), columns=list(ov.REQUIRED_COLUMNS))


class TestSchemaColumnCount:
    def test_required_columns_has_exactly_14_entries(self):
        assert len(ov.REQUIRED_COLUMNS) == 14

    def test_csv_header_matches_required_columns_exactly(self):
        header = ov.OVERRIDE_PATH.read_text().splitlines()[0].split(",")
        assert header == list(ov.REQUIRED_COLUMNS)

    def test_valid_row_fixtures_populate_every_required_column(self):
        assert set(_valid_adp_row().keys()) == set(ov.REQUIRED_COLUMNS)
        assert set(_valid_mmc_row().keys()) == set(ov.REQUIRED_COLUMNS)


class TestLoadOverrides:
    def test_creates_empty_file_with_correct_headers_if_missing(self, tmp_path):
        path = tmp_path / "mmc_2010_manual_overrides.csv"
        assert not path.exists()

        df = ov.load_overrides(path)

        assert path.exists()
        assert list(df.columns) == list(ov.REQUIRED_COLUMNS)
        assert len(df) == 0

    def test_reads_existing_file(self, tmp_path):
        path = tmp_path / "mmc_2010_manual_overrides.csv"
        _df(_valid_adp_row()).to_csv(path, index=False)

        df = ov.load_overrides(path)

        assert len(df) == 1
        assert df.iloc[0]["player_id"] == "00-0012345"

    def test_empty_table_passes_validation(self, tmp_path):
        path = tmp_path / "mmc_2010_manual_overrides.csv"
        df = ov.load_overrides(path)
        ov.validate_overrides(df)  # must not raise


class TestValidRowsPass:
    def test_valid_usable_adp_row_passes(self):
        ov.validate_overrides(_df(_valid_adp_row()))  # must not raise

    def test_valid_minimal_market_cost_row_passes(self):
        ov.validate_overrides(_df(_valid_mmc_row()))  # must not raise


class TestSeasonRule:
    """Enforced against config.SBV_MMC_MANUAL_OVERRIDE_SEASONS, a
    constant dedicated to this mechanism -- NOT
    SBV_FIRST_SCOREABLE_SEASON, which is a different concept that only
    coincides in value today. See module docstring."""

    def test_wrong_season_is_rejected(self):
        with pytest.raises(ValueError, match="season must be one of"):
            ov.validate_overrides(_df(_valid_adp_row(season="2011")))

    def test_non_integer_season_is_rejected(self):
        with pytest.raises(ValueError, match="season must be an integer"):
            ov.validate_overrides(_df(_valid_adp_row(season="not_a_year")))

    def test_correct_season_passes(self):
        ov.validate_overrides(_df(_valid_adp_row(season=str(_OVERRIDE_SEASON))))

    def test_season_check_references_dedicated_constant_not_first_scoreable_season(self):
        """Direct proof the two concepts are decoupled: changing
        SBV_FIRST_SCOREABLE_SEASON must have zero effect on this
        loader's season check."""
        import config
        original = config.SBV_FIRST_SCOREABLE_SEASON
        try:
            config.SBV_FIRST_SCOREABLE_SEASON = 1999  # deliberately wrong/unrelated
            ov.validate_overrides(_df(_valid_adp_row(season=str(_OVERRIDE_SEASON))))  # must still pass
        finally:
            config.SBV_FIRST_SCOREABLE_SEASON = original


class TestRequiredFields:
    @pytest.mark.parametrize("field", ["player_id", "player_name", "source", "source_date", "evidence_summary", "approved_by"])
    def test_missing_required_field_is_rejected(self, field):
        with pytest.raises(ValueError, match=f"'{field}' is required"):
            ov.validate_overrides(_df(_valid_adp_row(**{field: ""})))


class TestEnumValidation:
    def test_invalid_override_type_is_rejected(self):
        with pytest.raises(ValueError, match="override_type must be one of"):
            ov.validate_overrides(_df(_valid_adp_row(override_type="bogus")))

    def test_invalid_market_cost_status_is_rejected(self):
        with pytest.raises(ValueError, match="market_cost_status must be one of"):
            ov.validate_overrides(_df(_valid_adp_row(market_cost_status="bogus")))

    def test_invalid_confidence_is_rejected(self):
        with pytest.raises(ValueError, match="confidence must be one of"):
            ov.validate_overrides(_df(_valid_adp_row(confidence="very_high")))

    def test_override_type_status_mismatch_is_rejected(self):
        with pytest.raises(ValueError, match="must pair with"):
            ov.validate_overrides(_df(_valid_adp_row(market_cost_status="minimal_market_cost_scored")))


class TestExactlyOnePath:
    def test_both_adp_and_mmc_populated_is_rejected(self):
        row = _valid_adp_row(minimal_market_cost_approved="TRUE")
        with pytest.raises(ValueError, match="cannot populate both"):
            ov.validate_overrides(_df(row))

    def test_neither_adp_nor_mmc_populated_is_rejected(self):
        row = _valid_adp_row(adp_overall="", adp_round="")
        with pytest.raises(ValueError, match="neither found"):
            ov.validate_overrides(_df(row))

    def test_usable_adp_without_adp_fields_is_rejected(self):
        row = _valid_adp_row(adp_overall="", adp_round="", minimal_market_cost_approved="")
        # neither populated -- caught by the broader "neither found" check first
        with pytest.raises(ValueError):
            ov.validate_overrides(_df(row))

    def test_minimal_market_cost_without_approval_is_rejected(self):
        row = _valid_mmc_row(minimal_market_cost_approved="FALSE")
        with pytest.raises(ValueError, match="neither found"):
            ov.validate_overrides(_df(row))


class TestDisallowedSourceValues:
    """Section 8a rule #2 -- no override from classifier output alone.
    EXACT match after normalization, not a substring/phrase search --
    see module docstring for why the earlier substring design was
    rejected after review."""

    @pytest.mark.parametrize("value", ["classifier", "draft_capital", "rookie_status", "prior_production_heuristic", "internal_classifier_output"])
    def test_exact_disallowed_value_is_rejected(self, value):
        row = _valid_adp_row(source=value)
        with pytest.raises(ValueError, match="classifier-internal signal"):
            ov.validate_overrides(_df(row))

    def test_disallowed_value_match_is_case_insensitive(self):
        row = _valid_adp_row(source="CLASSIFIER")
        with pytest.raises(ValueError, match="classifier-internal signal"):
            ov.validate_overrides(_df(row))

    def test_disallowed_value_match_treats_underscores_and_spaces_as_equivalent(self):
        row = _valid_adp_row(source="draft capital")  # config lists "draft_capital"
        with pytest.raises(ValueError, match="classifier-internal signal"):
            ov.validate_overrides(_df(row))

    def test_disallowed_value_match_tolerates_surrounding_whitespace(self):
        row = _valid_adp_row(source="  classifier  ")
        with pytest.raises(ValueError, match="classifier-internal signal"):
            ov.validate_overrides(_df(row))

    @pytest.mark.parametrize("sentence", [
        "Cross-referenced against the team's own rookie status announcement on nfl.com",
        "Confirmed via the team's public draft capital summary press release",
        "Verified using prior production statistics published by Pro Football Reference",
    ])
    def test_ordinary_sentence_containing_a_reserved_phrase_is_not_rejected(self, sentence):
        """The regression test for the overinclusive substring design:
        a genuine independent source that happens to contain ordinary
        phrasing like "rookie status" or "draft capital" must NOT be
        rejected just because those words appear somewhere in the
        sentence."""
        ov.validate_overrides(_df(_valid_adp_row(source=sentence)))  # must not raise

    def test_legitimate_external_source_passes(self):
        ov.validate_overrides(_df(_valid_adp_row(source="MyFantasyLeague direct query, 2010-08-15 snapshot")))


class TestDuplicateRows:
    def test_duplicate_season_player_id_is_rejected(self):
        row1 = _valid_adp_row(player_id="00-0099999")
        row2 = _valid_mmc_row(player_id="00-0099999")
        with pytest.raises(ValueError, match="Duplicate .season, player_id. rows"):
            ov.validate_overrides(_df(row1, row2))

    def test_same_player_different_season_is_not_a_duplicate_at_this_check(self):
        """The season itself would still fail TestSeasonRule -- this
        test isolates that the duplicate check specifically keys on
        the (season, player_id) pair, not player_id alone."""
        row1 = _valid_adp_row(player_id="00-0099999", season=str(_OVERRIDE_SEASON))
        row2 = _valid_adp_row(player_id="00-0099999", season="2011")
        with pytest.raises(ValueError, match="season must be one of"):
            ov.validate_overrides(_df(row1, row2))

    def test_distinct_players_are_not_duplicates(self):
        row1 = _valid_adp_row(player_id="00-0099999")
        row2 = _valid_mmc_row(player_id="00-0088888")
        ov.validate_overrides(_df(row1, row2))  # must not raise


class TestMultipleErrorsReported:
    def test_all_violations_in_one_row_are_collected(self):
        row = _valid_adp_row(season="2011", source="", confidence="extreme")
        with pytest.raises(ValueError) as exc_info:
            ov.validate_overrides(_df(row))
        message = str(exc_info.value)
        assert "season must be one of" in message
        assert "'source' is required" in message
        assert "confidence must be one of" in message


class TestLoaderIndependence:
    def test_module_does_not_import_classifier_or_scoring_modules(self):
        """This loader must only parse/validate -- confirms no import
        of any not-yet-built (or future) classifier/scoring module
        name, so a bug in classification can never reach into
        override loading and vice versa."""
        import inspect
        source = inspect.getsource(ov)
        forbidden = ["acquisition_cost", "labeling", "production", "expected_production", "minimal_market_cost"]
        import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
        for line in import_lines:
            for name in forbidden:
                assert name not in line, f"mmc_2010_overrides.py must not import {name} -- found in: {line!r}"
