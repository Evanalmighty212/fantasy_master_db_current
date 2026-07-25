"""
tests/test_production.py

Covers lib/stars_by_value/production.py and lib/replacement.py --
promoted (Commit 5) from research/dataset3/production_weight_and_boundary_calibration.py::build_adp_aware_aatp(),
research/dataset3/normalized_shrinkage_comparison.py::ppg_eq_normalized_shrink(),
and research/dataset3/lib/replacement.py. Per the explicit promotion
directive for this commit -- treat the research script as the oracle;
any numerical difference is a bug unless explained by a proven,
tested config substitution -- these tests compare the promoted
module's output against the REAL research implementation's output on
the REAL historical population, not against hand-computed expected
values.

WHY A SUBPROCESS, NOT A DIRECT IMPORT: research/dataset3/lib/ and this
project's new top-level lib/ are both packages literally named `lib`.
Confirmed directly (not assumed) that importing both in one Python
process collides in sys.modules regardless of import order -- whichever
`lib` gets touched first "wins" the name, and the research script's
own internal `from lib.X import Y` statements then fail to find
submodules that live under the OTHER `lib` package. The oracle is
therefore computed in an isolated subprocess whose sys.path contains
ONLY research/dataset3 (this project's lib/ is never imported there),
and its output is written to a CSV that this test process (whose
sys.path contains ONLY the repo root, research/ is never imported
here) reads back and compares against. Two separate interpreter
processes, two separate `lib` resolutions, no collision either way.

SKIPPED, NOT FAILED, WHEN THE REAL RESEARCH INPUT ISN'T LOCALLY
PRESENT: research/output/dataset3/broad_historical_dataset.csv is
pipeline-regenerated and gitignored per research/dataset3/README.md's
own stated convention ("rerun the scripts... never commit it
directly") -- a fresh clone that hasn't run
build_broad_historical_dataset.py won't have it. The oracle-dependent
tests in this file skip cleanly in that case rather than failing the
whole suite; TestReplacementCutoffs, TestValidationFailsLoud,
TestSeasonLength, TestCompositeWeights, and TestNoResearchImports need
no such data and always run.
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.stars_by_value import production as prod
from lib.replacement import ROSTER_PRESETS, replacement_rank_cutoff
from config import (
    SBV_POSITIONS,
    SBV_PRODUCTION_WEIGHT_AATP,
    SBV_PRODUCTION_WEIGHT_PPG_EQ,
    SBV_REPLACEMENT_FLEX_ALLOCATION,
    SBV_REPLACEMENT_RANK_CUTOFFS,
    SBV_REPLACEMENT_ROSTER_PRESET,
    SBV_SHRINKAGE_K,
)

BROAD_DATASET_PATH = REPO_ROOT / "research" / "output" / "dataset3" / "broad_historical_dataset.csv"
WEEKLY_PATH = prod.WEEKLY_PATH

ORACLE_SUBPROCESS_SCRIPT = """
import sys
sys.path.insert(0, "research/dataset3")
from production_weight_and_boundary_calibration import build_adp_aware_aatp
from normalized_shrinkage_comparison import ppg_eq_normalized_shrink

df = build_adp_aware_aatp()
df["oracle_ppg_ar_eq_shrunk_k5"] = df.apply(
    lambda r: ppg_eq_normalized_shrink(r["PPG_AR"], r["games_played_capped"], r["G"], {shrinkage_k}), axis=1
)

cols = [
    "season", "player_id", "position", "games_played", "fantasy_points_ppr",
    "ppg_ppr", "position_finish_ppr", "adp_matched",
    "G", "games_played_capped", "eligible_games", "games_missed_eligible",
    "replacement_ppg", "AATP", "PPG_AR", "PPG_AR_eq", "oracle_ppg_ar_eq_shrunk_k5",
]
df[cols].to_csv(r"{out_path}", index=False)
print(f"oracle rows: {{len(df)}}")
"""


def _oracle_available() -> bool:
    return BROAD_DATASET_PATH.exists() and WEEKLY_PATH.exists()


@pytest.fixture(scope="module")
def oracle_df(tmp_path_factory):
    if not _oracle_available():
        pytest.skip(
            f"Oracle regression requires {BROAD_DATASET_PATH} (pipeline-regenerated, "
            f"gitignored) -- rerun research/dataset3/build_broad_historical_dataset.py "
            f"first, per research/dataset3/README.md's Run order."
        )
    out_path = tmp_path_factory.mktemp("oracle") / "oracle_aatp.csv"
    script = ORACLE_SUBPROCESS_SCRIPT.format(shrinkage_k=SBV_SHRINKAGE_K, out_path=out_path)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Oracle subprocess failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return pd.read_csv(out_path)


@pytest.fixture(scope="module")
def promoted_df(oracle_df):
    """Feeds the ORACLE's exact (already population-scoped) input rows
    through the PROMOTED compute_production() -- apples-to-apples per
    the agreed design: production.py doesn't scope population itself,
    so the test pre-filters to the oracle's population before comparing."""
    input_cols = list(prod.REQUIRED_COLUMNS)
    input_df = oracle_df[input_cols].copy()
    input_df["adp_matched"] = input_df["adp_matched"].astype(bool)
    return prod.compute_production(input_df, weekly_path=WEEKLY_PATH)


class TestOracleComparisonAATP:
    """Row-by-row comparison against the real research build_adp_aware_aatp()
    output -- every row of the real 2007-2024 historical population,
    not a handful of named examples."""

    def test_row_count_matches(self, oracle_df, promoted_df):
        assert len(promoted_df) == len(oracle_df)

    @pytest.mark.parametrize("column", ["G", "games_played_capped", "eligible_games", "games_missed_eligible"])
    def test_intermediate_columns_match_exactly(self, oracle_df, promoted_df, column):
        pd.testing.assert_series_equal(
            promoted_df[column].reset_index(drop=True),
            oracle_df[column].reset_index(drop=True),
            check_names=False,
        )

    @pytest.mark.parametrize("column", ["replacement_ppg", "AATP", "PPG_AR", "PPG_AR_eq"])
    def test_computed_columns_match_within_float_tolerance(self, oracle_df, promoted_df, column):
        pd.testing.assert_series_equal(
            promoted_df[column].reset_index(drop=True),
            oracle_df[column].reset_index(drop=True),
            check_names=False,
            rtol=1e-9,
            atol=1e-9,
        )

    def test_zero_rows_differ_by_more_than_floating_point_noise(self, oracle_df, promoted_df):
        """Belt-and-suspenders on top of the per-column asserts above --
        an explicit count of materially differing AATP values, which
        must be exactly zero."""
        diff = (promoted_df["AATP"].reset_index(drop=True) - oracle_df["AATP"].reset_index(drop=True)).abs()
        n_diff = (diff > 1e-6).sum()
        assert n_diff == 0, f"{n_diff} of {len(diff)} rows have AATP differing from the oracle by more than 1e-6"


class TestOracleComparisonShrinkageAndComposite:
    def test_shrunk_ppg_eq_matches_oracle_formula(self, oracle_df, promoted_df):
        pd.testing.assert_series_equal(
            promoted_df["PPG_AR_eq_shrunk"].reset_index(drop=True),
            oracle_df["oracle_ppg_ar_eq_shrunk_k5"].reset_index(drop=True),
            check_names=False,
            rtol=1e-9,
            atol=1e-9,
        )

    def test_composite_equals_weighted_sum_of_oracle_pieces(self, oracle_df, promoted_df):
        expected_p = (
            SBV_PRODUCTION_WEIGHT_AATP * oracle_df["AATP"]
            + SBV_PRODUCTION_WEIGHT_PPG_EQ * oracle_df["oracle_ppg_ar_eq_shrunk_k5"]
        )
        pd.testing.assert_series_equal(
            promoted_df["P"].reset_index(drop=True),
            expected_p.reset_index(drop=True),
            check_names=False,
            rtol=1e-9,
            atol=1e-9,
        )


class TestCompositeWeights:
    def test_weights_are_the_settled_50_50_baseline(self):
        """Matches production_weight_and_boundary_calibration.py's own
        "50_50" weight set exactly -- the settled choice per section 10."""
        assert SBV_PRODUCTION_WEIGHT_AATP == 0.5
        assert SBV_PRODUCTION_WEIGHT_PPG_EQ == 0.5


class TestReplacementCutoffsMatchSettledConfig:
    """Confirms the promoted lib/replacement.py, applied to the settled
    roster preset and flex allocation, reproduces config.py's
    already-committed SBV_REPLACEMENT_RANK_CUTOFFS exactly -- if this
    ever failed, it would mean Commit 1's config and the actual
    replacement-construction formula had drifted apart."""

    def test_cutoffs_are_qb12_rb29_wr29_te13(self):
        preset = ROSTER_PRESETS[SBV_REPLACEMENT_ROSTER_PRESET]
        computed = {
            pos: replacement_rank_cutoff(preset, pos, SBV_REPLACEMENT_FLEX_ALLOCATION)
            for pos in SBV_POSITIONS
        }
        assert computed == {"QB": 12, "RB": 29, "WR": 29, "TE": 13}

    def test_computed_cutoffs_equal_config_cutoffs_exactly(self):
        preset = ROSTER_PRESETS[SBV_REPLACEMENT_ROSTER_PRESET]
        computed = {
            pos: replacement_rank_cutoff(preset, pos, SBV_REPLACEMENT_FLEX_ALLOCATION)
            for pos in SBV_POSITIONS
        }
        assert computed == SBV_REPLACEMENT_RANK_CUTOFFS


class TestSeasonLength:
    def test_2020_is_16_games(self):
        assert prod.season_length(2020) == 16

    def test_2021_is_17_games(self):
        assert prod.season_length(2021) == 17

    def test_2024_is_17_games(self):
        assert prod.season_length(2024) == 17

    def test_2006_is_16_games(self):
        assert prod.season_length(2006) == 16


class TestValidationFailsLoud:
    """No silent row-dropping -- a structurally invalid row must raise,
    never be quietly filtered out. Population scoping (season range,
    games_played >= 1) is deliberately NOT enforced here -- see module
    docstring."""

    def _valid_df(self, **overrides):
        row = {
            "season": 2020, "player_id": "00-001", "position": "WR",
            "games_played": 10, "fantasy_points_ppr": 150.0, "ppg_ppr": 15.0,
            "position_finish_ppr": 20, "adp_matched": True,
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_missing_column_raises(self):
        df = self._valid_df().drop(columns=["ppg_ppr"])
        with pytest.raises(ValueError, match="missing required columns"):
            prod.compute_aatp(df)

    def test_null_required_numeric_column_raises(self):
        df = self._valid_df(fantasy_points_ppr=float("nan"))
        with pytest.raises(ValueError, match="null value"):
            prod.compute_aatp(df)

    def test_position_outside_sbv_positions_raises(self):
        df = self._valid_df(position="K")
        with pytest.raises(ValueError, match="outside SBV_POSITIONS"):
            prod.compute_aatp(df)

    def test_non_boolean_adp_matched_raises(self):
        df = self._valid_df(adp_matched="True")  # string, not bool
        with pytest.raises(ValueError, match="boolean dtype"):
            prod.compute_aatp(df)

    def test_games_played_zero_is_accepted_not_filtered(self):
        """Population scoping is the caller's job -- games_played=0
        must NOT be rejected or silently dropped by this module."""
        if not WEEKLY_PATH.exists():
            pytest.skip(f"Requires {WEEKLY_PATH} (pipeline-generated, not guaranteed present)")
        df = self._valid_df(games_played=0)
        out = prod.compute_aatp(df, weekly_path=WEEKLY_PATH)
        assert len(out) == 1  # present, not dropped

    def test_error_never_silently_drops_the_bad_row(self):
        """A DataFrame with one good row and one bad row must raise for
        the WHOLE call, not silently return just the good row."""
        good = self._valid_df()
        bad = self._valid_df(position="K")
        df = pd.concat([good, bad], ignore_index=True)
        with pytest.raises(ValueError):
            prod.compute_aatp(df)


class TestNoResearchImports:
    def test_production_module_does_not_import_research(self):
        import inspect
        source = inspect.getsource(prod)
        import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "research" not in line, f"production.py must not import from research/ -- found: {line!r}"

    def test_replacement_module_does_not_import_research(self):
        import inspect
        from lib import replacement
        source = inspect.getsource(replacement)
        import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "research" not in line, f"lib/replacement.py must not import from research/ -- found: {line!r}"
