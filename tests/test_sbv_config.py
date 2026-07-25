"""
tests/test_sbv_config.py

Covers the SBV_* configuration block in config.py and validate_sbv_config().
Configuration-contract tests only -- no pipeline logic exists yet
(Commit 1 of the Stars-by-Value implementation is config/enums only,
per research/dataset3/STARS_BY_VALUE_IMPLEMENTATION_PLAN.md).

Mirrors tests/test_calculate_metrics.py's TestConfigValidation pattern
exactly, including the same reason for loading config.py directly via
importlib rather than `import config`: validate_sbv_config() is
DEFINED INSIDE config.py and reads its globals from THAT module's own
namespace. Patching an aliased import elsewhere would silently test
nothing.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.py"


@pytest.fixture
def config_mod():
    """Fresh, isolated load of config.py per test -- mutations in one
    test must never leak into another."""
    spec = importlib.util.spec_from_file_location("test_sbv_config_mod", CONFIG_PATH)
    c = importlib.util.module_from_spec(spec)
    sys.modules["test_sbv_config_mod"] = c
    spec.loader.exec_module(c)
    return c


class TestValidConfigPasses:
    def test_valid_config_passes(self, config_mod):
        config_mod.validate_sbv_config()  # should not raise


class TestRequiredPositionKeys:
    """Every position-keyed SBV_* dict must have exactly {QB, RB, WR, TE}
    -- section 5/9/10 all define these per-position, never a subset or
    a superset."""

    @pytest.mark.parametrize("attr", [
        "SBV_PRODUCTION_GATE_FLOOR",
        "SBV_REPLACEMENT_RANK_CUTOFFS",
        "SBV_STAR_THRESHOLD",
        "SBV_MMC_OPPORTUNITY_PROBABILITY",
        "SBV_MMC_REPLACEMENT_PPG",
        "SBV_MMC_USAGE_DEFINITION",
    ])
    def test_missing_position_key_is_rejected(self, config_mod, attr):
        d = dict(getattr(config_mod, attr))
        del d["TE"]
        setattr(config_mod, attr, d)
        with pytest.raises(ValueError, match=attr):
            config_mod.validate_sbv_config()

    @pytest.mark.parametrize("attr", [
        "SBV_PRODUCTION_GATE_FLOOR",
        "SBV_STAR_THRESHOLD",
        "SBV_MMC_OPPORTUNITY_PROBABILITY",
    ])
    def test_extra_position_key_is_rejected(self, config_mod, attr):
        d = dict(getattr(config_mod, attr))
        d["K"] = 100.0  # not a real position
        setattr(config_mod, attr, d)
        with pytest.raises(ValueError, match=attr):
            config_mod.validate_sbv_config()

    def test_all_four_positions_present_by_default(self, config_mod):
        assert set(config_mod.SBV_POSITIONS) == {"QB", "RB", "WR", "TE"}


class TestThresholdOrderingAndTypes:
    """The production gate must be a strictly easier bar than the final
    Star threshold, for every position -- section 11's processing order
    (gate before acquisition-cost resolution before final score) is
    only meaningful if this is actually true, not just documented."""

    def test_gate_floor_below_star_threshold_for_every_position(self, config_mod):
        for pos in config_mod.SBV_POSITIONS:
            assert config_mod.SBV_PRODUCTION_GATE_FLOOR[pos] < config_mod.SBV_STAR_THRESHOLD[pos]

    def test_gate_floor_at_or_above_star_threshold_is_rejected(self, config_mod):
        config_mod.SBV_PRODUCTION_GATE_FLOOR = dict(config_mod.SBV_PRODUCTION_GATE_FLOOR)
        config_mod.SBV_PRODUCTION_GATE_FLOOR["QB"] = config_mod.SBV_STAR_THRESHOLD["QB"] + 1
        with pytest.raises(ValueError, match="must be strictly less than"):
            config_mod.validate_sbv_config()

    def test_negative_gate_floor_is_rejected(self, config_mod):
        config_mod.SBV_PRODUCTION_GATE_FLOOR = dict(config_mod.SBV_PRODUCTION_GATE_FLOOR)
        config_mod.SBV_PRODUCTION_GATE_FLOOR["RB"] = -5.0
        with pytest.raises(ValueError, match="SBV_PRODUCTION_GATE_FLOOR"):
            config_mod.validate_sbv_config()

    def test_zero_star_threshold_is_rejected(self, config_mod):
        config_mod.SBV_STAR_THRESHOLD = dict(config_mod.SBV_STAR_THRESHOLD)
        config_mod.SBV_STAR_THRESHOLD["WR"] = 0
        with pytest.raises(ValueError, match="SBV_STAR_THRESHOLD"):
            config_mod.validate_sbv_config()

    def test_first_scoreable_season_derivation_is_checked(self, config_mod):
        """2010 is derived (2007 + 3), not an independent choice --
        breaking the arithmetic must fail loudly, matching section 7's
        explicit derivation note."""
        config_mod.SBV_FIRST_SCOREABLE_SEASON = 2011
        with pytest.raises(ValueError, match="SBV_FIRST_SCOREABLE_SEASON"):
            config_mod.validate_sbv_config()

    def test_season_length_16_must_be_below_17(self, config_mod):
        config_mod.SBV_SEASON_LENGTH_16_GAME = 17
        config_mod.SBV_SEASON_LENGTH_17_GAME = 17
        with pytest.raises(ValueError, match="SBV_SEASON_LENGTH_16_GAME"):
            config_mod.validate_sbv_config()


class TestLambdaRange:
    def test_lambda_is_035(self, config_mod):
        assert config_mod.SBV_LAMBDA == 0.35

    def test_lambda_zero_is_rejected(self, config_mod):
        config_mod.SBV_LAMBDA = 0.0
        with pytest.raises(ValueError, match="SBV_LAMBDA"):
            config_mod.validate_sbv_config()

    def test_lambda_one_is_rejected(self, config_mod):
        config_mod.SBV_LAMBDA = 1.0
        with pytest.raises(ValueError, match="SBV_LAMBDA"):
            config_mod.validate_sbv_config()

    def test_lambda_above_one_is_rejected(self, config_mod):
        config_mod.SBV_LAMBDA = 1.5
        with pytest.raises(ValueError, match="SBV_LAMBDA"):
            config_mod.validate_sbv_config()

    def test_negative_lambda_is_rejected(self, config_mod):
        config_mod.SBV_LAMBDA = -0.1
        with pytest.raises(ValueError, match="SBV_LAMBDA"):
            config_mod.validate_sbv_config()


class TestShrinkageParameter:
    def test_k_is_5(self, config_mod):
        assert config_mod.SBV_SHRINKAGE_K == 5

    def test_zero_k_is_rejected(self, config_mod):
        config_mod.SBV_SHRINKAGE_K = 0
        with pytest.raises(ValueError, match="SBV_SHRINKAGE_K"):
            config_mod.validate_sbv_config()

    def test_negative_k_is_rejected(self, config_mod):
        config_mod.SBV_SHRINKAGE_K = -5
        with pytest.raises(ValueError, match="SBV_SHRINKAGE_K"):
            config_mod.validate_sbv_config()


class TestProductionWeightsAndReplacementSums:
    def test_production_weights_sum_to_one(self, config_mod):
        config_mod.SBV_PRODUCTION_WEIGHT_AATP = 0.6
        config_mod.SBV_PRODUCTION_WEIGHT_PPG_EQ = 0.6
        with pytest.raises(ValueError, match="must sum to 1.0"):
            config_mod.validate_sbv_config()

    def test_flex_allocation_sums_to_one(self, config_mod):
        config_mod.SBV_REPLACEMENT_FLEX_ALLOCATION = {"RB": 0.5, "WR": 0.5, "TE": 0.5}
        with pytest.raises(ValueError, match="SBV_REPLACEMENT_FLEX_ALLOCATION"):
            config_mod.validate_sbv_config()


class TestMmcOpportunityProbabilities:
    def test_probability_at_zero_is_rejected(self, config_mod):
        config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY = dict(config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY)
        config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY["QB"] = 0.0
        with pytest.raises(ValueError, match="SBV_MMC_OPPORTUNITY_PROBABILITY"):
            config_mod.validate_sbv_config()

    def test_probability_at_one_is_rejected(self, config_mod):
        config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY = dict(config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY)
        config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY["RB"] = 1.0
        with pytest.raises(ValueError, match="SBV_MMC_OPPORTUNITY_PROBABILITY"):
            config_mod.validate_sbv_config()

    def test_probability_above_one_is_rejected(self, config_mod):
        config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY = dict(config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY)
        config_mod.SBV_MMC_OPPORTUNITY_PROBABILITY["WR"] = 1.2
        with pytest.raises(ValueError, match="SBV_MMC_OPPORTUNITY_PROBABILITY"):
            config_mod.validate_sbv_config()

    def test_negative_replacement_ppg_is_rejected(self, config_mod):
        config_mod.SBV_MMC_REPLACEMENT_PPG = dict(config_mod.SBV_MMC_REPLACEMENT_PPG)
        config_mod.SBV_MMC_REPLACEMENT_PPG["TE"] = -1.0
        with pytest.raises(ValueError, match="SBV_MMC_REPLACEMENT_PPG"):
            config_mod.validate_sbv_config()


class TestMmcRoleConditionalDiscount:
    """Dedicated constant, deliberately separate from
    SBV_PRODUCTION_WEIGHT_AATP even though both currently equal 0.5 --
    see config.py's comment on SBV_MMC_ROLE_CONDITIONAL_DISCOUNT."""

    def test_settled_value_is_zero_point_five(self, config_mod):
        assert config_mod.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT == 0.5

    def test_zero_is_rejected(self, config_mod):
        config_mod.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT = 0.0
        with pytest.raises(ValueError, match="SBV_MMC_ROLE_CONDITIONAL_DISCOUNT"):
            config_mod.validate_sbv_config()

    def test_one_is_rejected(self, config_mod):
        config_mod.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT = 1.0
        with pytest.raises(ValueError, match="SBV_MMC_ROLE_CONDITIONAL_DISCOUNT"):
            config_mod.validate_sbv_config()

    def test_above_one_is_rejected(self, config_mod):
        config_mod.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT = 1.5
        with pytest.raises(ValueError, match="SBV_MMC_ROLE_CONDITIONAL_DISCOUNT"):
            config_mod.validate_sbv_config()

    def test_negative_is_rejected(self, config_mod):
        config_mod.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT = -0.1
        with pytest.raises(ValueError, match="SBV_MMC_ROLE_CONDITIONAL_DISCOUNT"):
            config_mod.validate_sbv_config()

    def test_is_a_distinct_constant_from_production_weight_aatp(self, config_mod):
        """Coincidentally equal in value today, but must be able to
        change independently -- proven by mutating one and confirming
        the other is untouched."""
        config_mod.SBV_PRODUCTION_WEIGHT_AATP = 0.9
        assert config_mod.SBV_MMC_ROLE_CONDITIONAL_DISCOUNT == 0.5


class TestStatusAndProvenanceEnumUniqueness:
    def test_exactly_seven_statuses(self, config_mod):
        assert len(config_mod.SBV_STATUSES) == 7

    def test_statuses_have_no_duplicates(self, config_mod):
        config_mod.SBV_STATUSES = config_mod.SBV_STATUSES + (config_mod.SBV_STATUSES[0],)
        with pytest.raises(ValueError, match="SBV_STATUSES must not contain duplicates"):
            config_mod.validate_sbv_config()

    def test_provenance_types_have_no_duplicates(self, config_mod):
        config_mod.SBV_PROVENANCE_TYPES = config_mod.SBV_PROVENANCE_TYPES + (config_mod.SBV_PROVENANCE_TYPES[0],)
        with pytest.raises(ValueError, match="SBV_PROVENANCE_TYPES must not contain duplicates"):
            config_mod.validate_sbv_config()

    def test_expected_status_values_present(self, config_mod):
        assert set(config_mod.SBV_STATUSES) == {
            "adp_scored",
            "unscoreable_adp_needs_review",
            "minimal_market_cost_scored",
            "unscoreable_drafted_adp_missing",
            "unscoreable_ambiguous",
            "below_production_gate",
            "out_of_scope",
        }

    def test_expected_provenance_values_present(self, config_mod):
        assert set(config_mod.SBV_PROVENANCE_TYPES) == {
            "adp_matched_clean",
            "adp_matched_needs_review",
            "mmc_verified_corroborated",
            "mmc_verified_2010_manual_override",
            "evidence_drafted_unresolved",
            "evidence_ambiguous_disagreement",
            "below_production_gate",
            "out_of_scope_non_skill_position",
            "out_of_scope_temporal_window",
            "out_of_scope_insufficient_participation",
        }


class TestArtifactPaths:
    def test_all_five_paths_are_defined_strings(self, config_mod):
        for attr in [
            "SBV_OUTPUT_PARQUET_PATH",
            "SBV_OUTPUT_CSV_EXPORT_PATH",
            "SBV_OUTPUT_CSV_SCHEMA_PATH",
            "SBV_EXPECTED_PRODUCTION_LOOKUP_PATH",
            "SBV_MMC_2010_OVERRIDE_PATH",
        ]:
            val = getattr(config_mod, attr)
            assert isinstance(val, str) and val.strip()

    def test_empty_path_is_rejected(self, config_mod):
        config_mod.SBV_OUTPUT_PARQUET_PATH = ""
        with pytest.raises(ValueError, match="SBV_OUTPUT_PARQUET_PATH"):
            config_mod.validate_sbv_config()

    def test_wrong_extension_is_rejected(self, config_mod):
        config_mod.SBV_OUTPUT_PARQUET_PATH = "data/processed/stars_by_value_player_seasons.csv"
        with pytest.raises(ValueError, match="must end with"):
            config_mod.validate_sbv_config()

    def test_paths_point_at_distinct_files(self, config_mod):
        paths = [
            config_mod.SBV_OUTPUT_PARQUET_PATH,
            config_mod.SBV_OUTPUT_CSV_EXPORT_PATH,
            config_mod.SBV_OUTPUT_CSV_SCHEMA_PATH,
            config_mod.SBV_EXPECTED_PRODUCTION_LOOKUP_PATH,
            config_mod.SBV_MMC_2010_OVERRIDE_PATH,
        ]
        assert len(paths) == len(set(paths))


class TestMmcManualOverrideSeasons:
    """Deliberately a constant SEPARATE from SBV_FIRST_SCOREABLE_SEASON
    -- the two encode different concepts that only coincide in value
    today. See config.py's comment on SBV_MMC_MANUAL_OVERRIDE_SEASONS."""

    def test_not_empty(self, config_mod):
        assert len(config_mod.SBV_MMC_MANUAL_OVERRIDE_SEASONS) > 0

    def test_empty_tuple_is_rejected(self, config_mod):
        config_mod.SBV_MMC_MANUAL_OVERRIDE_SEASONS = ()
        with pytest.raises(ValueError, match="SBV_MMC_MANUAL_OVERRIDE_SEASONS"):
            config_mod.validate_sbv_config()

    def test_duplicate_seasons_are_rejected(self, config_mod):
        config_mod.SBV_MMC_MANUAL_OVERRIDE_SEASONS = (2010, 2010)
        with pytest.raises(ValueError, match="must not contain duplicates"):
            config_mod.validate_sbv_config()

    def test_non_integer_season_is_rejected(self, config_mod):
        config_mod.SBV_MMC_MANUAL_OVERRIDE_SEASONS = (2010.5,)
        with pytest.raises(ValueError, match="must be integers"):
            config_mod.validate_sbv_config()

    def test_currently_equals_2010_only(self, config_mod):
        assert config_mod.SBV_MMC_MANUAL_OVERRIDE_SEASONS == (2010,)

    def test_is_a_distinct_constant_from_first_scoreable_season(self, config_mod):
        """Coincidentally equal in value today, but must be able to
        change independently -- proven by mutating one and confirming
        the other is untouched."""
        config_mod.SBV_FIRST_SCOREABLE_SEASON = 2099
        assert config_mod.SBV_MMC_MANUAL_OVERRIDE_SEASONS == (2010,)


class TestMmc2010OverrideDisallowedSourceValues:
    def test_not_empty(self, config_mod):
        assert len(config_mod.SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES) > 0

    def test_empty_tuple_is_rejected(self, config_mod):
        config_mod.SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES = ()
        with pytest.raises(ValueError, match="SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES"):
            config_mod.validate_sbv_config()

    def test_duplicate_values_are_rejected(self, config_mod):
        config_mod.SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES = ("classifier", "classifier")
        with pytest.raises(ValueError, match="must not contain duplicates"):
            config_mod.validate_sbv_config()

    def test_uppercase_value_is_rejected(self, config_mod):
        config_mod.SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES = ("Classifier",)
        with pytest.raises(ValueError, match="lowercase"):
            config_mod.validate_sbv_config()

    def test_expected_values_present(self, config_mod):
        assert set(config_mod.SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES) == {
            "classifier",
            "internal_classifier_output",
            "acquisition_cost_classifier",
            "draft_capital",
            "rookie_status",
            "prior_production_heuristic",
        }

    def test_values_are_short_tokens_not_full_sentences(self, config_mod):
        """Guards against accidentally reintroducing phrase-length
        entries that would make exact-match behave like a substring
        search in practice -- see mmc_2010_overrides.py's docstring
        for why substring matching was rejected after review."""
        for value in config_mod.SBV_MMC_2010_OVERRIDE_DISALLOWED_SOURCE_VALUES:
            assert " " not in value, (
                f"{value!r} contains a space -- disallowed values should be single "
                f"underscore_or_lowercase tokens, not multi-word phrases"
            )


class TestMflSettings:
    def test_period_must_be_aug15(self, config_mod):
        config_mod.SBV_MFL_PERIOD = "RECENT"
        with pytest.raises(ValueError, match="SBV_MFL_PERIOD"):
            config_mod.validate_sbv_config()

    def test_available_from_2011(self, config_mod):
        assert config_mod.SBV_MFL_AVAILABLE_FROM_SEASON == 2011

    def test_zero_min_request_delay_is_rejected(self, config_mod):
        config_mod.SBV_MFL_MIN_REQUEST_DELAY_SECONDS = 0
        with pytest.raises(ValueError, match="SBV_MFL_MIN_REQUEST_DELAY_SECONDS"):
            config_mod.validate_sbv_config()

    def test_negative_min_request_delay_is_rejected(self, config_mod):
        config_mod.SBV_MFL_MIN_REQUEST_DELAY_SECONDS = -1.5
        with pytest.raises(ValueError, match="SBV_MFL_MIN_REQUEST_DELAY_SECONDS"):
            config_mod.validate_sbv_config()

    def test_zero_max_retries_is_rejected(self, config_mod):
        config_mod.SBV_MFL_MAX_RETRIES = 0
        with pytest.raises(ValueError, match="SBV_MFL_MAX_RETRIES"):
            config_mod.validate_sbv_config()

    def test_non_integer_max_retries_is_rejected(self, config_mod):
        config_mod.SBV_MFL_MAX_RETRIES = 3.5
        with pytest.raises(ValueError, match="SBV_MFL_MAX_RETRIES"):
            config_mod.validate_sbv_config()

    def test_zero_backoff_base_is_rejected(self, config_mod):
        config_mod.SBV_MFL_BACKOFF_BASE_SECONDS = 0
        with pytest.raises(ValueError, match="SBV_MFL_BACKOFF_BASE_SECONDS"):
            config_mod.validate_sbv_config()

    def test_zero_request_timeout_is_rejected(self, config_mod):
        config_mod.SBV_MFL_REQUEST_TIMEOUT_SECONDS = 0
        with pytest.raises(ValueError, match="SBV_MFL_REQUEST_TIMEOUT_SECONDS"):
            config_mod.validate_sbv_config()

    def test_default_rate_limit_values_match_proven_research_client(self, config_mod):
        """Not arbitrary defaults -- these match the values already
        proven safe in research/diagnostics/mfl_pipeline/mfl_client.py
        (built after an earlier ad hoc parallel-batch attempt triggered
        apparent rate-limiting)."""
        assert config_mod.SBV_MFL_MIN_REQUEST_DELAY_SECONDS == 1.5
        assert config_mod.SBV_MFL_MAX_RETRIES == 3
        assert config_mod.SBV_MFL_BACKOFF_BASE_SECONDS == 3


class TestNoAccidentalLwiReuse:
    """SBV and LWI are two different specs with independently
    calibrated replacement-level definitions -- a copy-paste bug that
    accidentally points an SBV_* dict at the actual LWI_* object (or
    silently reproduces its values) would quietly corrupt Dataset 3
    with Dataset 1's assumptions. Checked both ways: object identity
    (catches `SBV_X = LWI_Y`) and value equality (catches
    `SBV_X = dict(LWI_Y)`, which identity alone would miss)."""

    def test_replacement_definitions_are_not_the_same_object(self, config_mod):
        assert config_mod.SBV_REPLACEMENT_RANK_CUTOFFS is not config_mod.LWI_REPLACEMENT_RANK_THRESHOLDS

    def test_replacement_definitions_have_different_values(self, config_mod):
        # Real, independently-calibrated difference: SBV uses
        # flex_rb_wr_heavy (QB12/RB29/WR29/TE13); LWI uses its own
        # QB12/RB34/WR42/TE12. If these ever become byte-for-byte
        # identical, that's worth a hard look, not a silent pass.
        assert config_mod.SBV_REPLACEMENT_RANK_CUTOFFS != config_mod.LWI_REPLACEMENT_RANK_THRESHOLDS

    def test_star_threshold_is_not_lwi_replacement_threshold(self, config_mod):
        assert config_mod.SBV_STAR_THRESHOLD is not config_mod.LWI_REPLACEMENT_RANK_THRESHOLDS

    def test_sbv_version_is_independent_of_lwi_version(self, config_mod):
        assert config_mod.SBV_VERSION is not config_mod.LWI_VERSION

    def test_no_sbv_constant_is_literally_an_lwi_constant(self, config_mod):
        """Broad sweep: no module-level SBV_* name may be the same
        object as any module-level LWI_* name -- restricted to mutable
        containers (dict/list/set/frozenset), where accidental aliasing
        (`SBV_X = LWI_Y`) is a real, meaningful bug. Deliberately
        EXCLUDES scalars (int/float/str/tuple-of-scalars): CPython
        caches small ints, so `12 is 12` is True for any two unrelated
        constants that happen to equal 12 -- confirmed directly
        (SBV_REPLACEMENT_WINDOW and LWI_REPLACEMENT_WINDOW both
        legitimately, independently equal 12; `is` flagged that as a
        false positive before this test was narrowed to containers)."""
        container_types = (dict, list, set, frozenset)
        sbv_values = {
            name: getattr(config_mod, name)
            for name in dir(config_mod)
            if name.startswith("SBV_") and isinstance(getattr(config_mod, name), container_types)
        }
        lwi_values = {
            name: getattr(config_mod, name)
            for name in dir(config_mod)
            if name.startswith("LWI_") and isinstance(getattr(config_mod, name), container_types)
        }
        assert sbv_values and lwi_values  # sanity: the sweep actually found dict-typed constants on both sides
        for sbv_name, sbv_val in sbv_values.items():
            for lwi_name, lwi_val in lwi_values.items():
                assert sbv_val is not lwi_val, (
                    f"{sbv_name} and {lwi_name} are the same object -- "
                    "SBV and LWI config must never share a reference"
                )

    def test_validate_sbv_config_does_not_touch_lwi_globals(self, config_mod):
        """Calling validate_sbv_config() must never mutate or depend on
        LWI_* state -- corrupting LWI_WEIGHTS here and confirming SBV
        validation is unaffected proves the two are truly independent."""
        original_lwi_weights = dict(config_mod.LWI_WEIGHTS)
        config_mod.LWI_WEIGHTS = {"adp_value": -999}  # deliberately invalid LWI config
        config_mod.validate_sbv_config()  # must not raise -- SBV validation ignores LWI entirely
        assert config_mod.LWI_WEIGHTS == {"adp_value": -999}  # confirms validate_sbv_config didn't touch/reset it either
        config_mod.LWI_WEIGHTS = original_lwi_weights  # restore, though fixture is fresh per test anyway
