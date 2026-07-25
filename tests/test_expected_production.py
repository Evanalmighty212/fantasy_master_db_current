"""
tests/test_expected_production.py

Covers lib/stars_by_value/expected_production.py and
scripts/09_fit_sbv_expected_production.py -- promoted (Commit 6) from
the expected-production research chain. See expected_production.py's
own module docstring for the full oracle-chain identification (six
scripts read in full, chronological) and for the one synthesis this
commit had to build fresh: no single research script runs a combined
fit where QB's baseline+offset are recency-weighted while RB/WR/TE's
are simultaneously equal-weighted -- that combination is a direct,
documented reading of aatp_round_refit_and_short_season_calibration.py's
own per-position equal-vs-recency comparison, not an independent
invention.

WHY A SUBPROCESS FOR THE ORACLE COMPARISON: same reason as
tests/test_production.py -- research/dataset3/lib/ and this project's
top-level lib/ are both packages named `lib` and collide in
sys.modules regardless of import order (confirmed in Commit 5). The
oracle subprocess re-derives fit_round_means()/fit_offsets()/
season_weight() VERBATIM from aatp_round_refit_and_short_season_calibration.py
(copy-pasted, not reimplemented differently) against the real
build_adp_aware_aatp() population, then applies the SAME documented
per-position pipeline-selection this module uses -- so this test
verifies the promoted module's fitting MECHANICS are byte-identical to
the oracle's own functions, not that some research script printed this
exact combined table (none did, see above).

SKIPPED, NOT FAILED, when real research inputs aren't locally present
-- same convention as test_production.py.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.stars_by_value import expected_production as ep
from lib.stars_by_value import production as prod
from config import SBV_MIN_PRIOR_SEASONS, SBV_POSITIONS, SBV_RECENCY_HALF_LIFE_YEARS, SBV_RECENCY_POSITIONS, SBV_ROUND_OFFSET_POSITIONS, SBV_VERSION

BROAD_DATASET_PATH = REPO_ROOT / "research" / "output" / "dataset3" / "broad_historical_dataset.csv"
WEEKLY_PATH = prod.WEEKLY_PATH


def _oracle_available() -> bool:
    return BROAD_DATASET_PATH.exists() and WEEKLY_PATH.exists()


ORACLE_SUBPROCESS_SCRIPT = """
import sys
sys.path.insert(0, "research/dataset3")
import numpy as np
import pandas as pd
from production_weight_and_boundary_calibration import build_adp_aware_aatp
from expected_production_by_round_investigation import POSITIONS, adp_round

MIN_PRIOR_SEASONS = {min_prior_seasons}
HALF_LIFE_YEARS = {half_life_years}
OFFSET_POSITIONS = {offset_positions!r}
RECENCY_POSITIONS = {recency_positions!r}

# Verbatim from aatp_round_refit_and_short_season_calibration.py
def season_weight(season, asof_year, scheme):
    if scheme == "equal":
        return 1.0
    age = (asof_year - 1) - season
    return 0.5 ** (age / HALF_LIFE_YEARS)

def fit_round_means(train, asof_year, scheme):
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    return {{r: np.average(g["AATP"], weights=g["w"]) for r, g in t.groupby("adp_round")}}

def fit_offsets(train, round_means, asof_year, scheme):
    t = train.copy()
    t["w"] = t["season"].apply(lambda s: season_weight(s, asof_year, scheme))
    t["pooled_pred"] = t["adp_round"].map(round_means)
    t["residual"] = t["AATP"] - t["pooled_pred"]
    return {{pos: np.average(t[t["position"] == pos].dropna(subset=["residual"])["residual"],
                             weights=t.loc[(t["position"] == pos) & t["residual"].notna(), "w"])
            for pos in POSITIONS}}

df = build_adp_aware_aatp()
matched = df[df["adp_matched"]].copy()
matched["adp_round"] = matched["overall_adp_observed"].apply(adp_round)

rows = []
for asof_year in sorted(matched["season"].unique()):
    train = matched[matched["season"] < asof_year]
    if train["season"].nunique() < MIN_PRIOR_SEASONS:
        continue
    equal_rm = fit_round_means(train, asof_year, "equal")
    equal_off = fit_offsets(train, equal_rm, asof_year, "equal")
    recency_rm = fit_round_means(train, asof_year, "recency")
    recency_off = fit_offsets(train, recency_rm, asof_year, "recency")

    for pos in ["QB", "RB", "WR", "TE"]:
        use_recency = pos in RECENCY_POSITIONS
        rm = recency_rm if use_recency else equal_rm
        off = recency_off if use_recency else equal_off
        raw_offset = off.get(pos) if pos in OFFSET_POSITIONS else None
        offset = None if raw_offset is None or (isinstance(raw_offset, float) and np.isnan(raw_offset)) else raw_offset
        for rnd in sorted(train["adp_round"].dropna().unique()):
            baseline = rm.get(rnd)
            if baseline is None or (isinstance(baseline, float) and np.isnan(baseline)):
                continue
            rows.append({{
                "prediction_season": asof_year, "position": pos, "draft_round": int(rnd),
                "expected_production": baseline + (offset if offset is not None else 0.0),
                "positional_offset_applied": offset,
            }})

pd.DataFrame(rows).to_csv(r"{out_path}", index=False)
print(f"oracle rows: {{len(rows)}}")
"""


@pytest.fixture(scope="module")
def oracle_ep_df(tmp_path_factory):
    if not _oracle_available():
        pytest.skip(f"Oracle regression requires {BROAD_DATASET_PATH} and {WEEKLY_PATH}")
    out_path = tmp_path_factory.mktemp("oracle_ep") / "oracle_ep.csv"
    script = ORACLE_SUBPROCESS_SCRIPT.format(
        min_prior_seasons=SBV_MIN_PRIOR_SEASONS,
        half_life_years=SBV_RECENCY_HALF_LIFE_YEARS,
        offset_positions=set(SBV_ROUND_OFFSET_POSITIONS),
        recency_positions=set(SBV_RECENCY_POSITIONS),
        out_path=out_path,
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"Oracle subprocess failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return pd.read_csv(out_path)


@pytest.fixture(scope="module")
def real_matched_population():
    """compute_aatp() must run on the FULL population BEFORE filtering
    to adp_matched -- replacement_level_from_rank() needs undrafted
    players present in the rank pool to compute correct replacement_ppg.
    Filtering to adp_matched first (an earlier version of this fixture
    did exactly this) silently produces wrong AATP values -- caught by
    TestOracleParity failing with small, non-noise, systematic
    per-row diffs, not floating-point tolerance."""
    if not _oracle_available():
        pytest.skip(f"Requires {BROAD_DATASET_PATH} and {WEEKLY_PATH}")
    df = pd.read_csv(BROAD_DATASET_PATH)
    input_cols = list(prod.REQUIRED_COLUMNS) + ["overall_adp_observed"]
    df = df[input_cols].copy()
    df["adp_matched"] = df["adp_matched"].astype(bool)
    with_aatp = prod.compute_aatp(df, weekly_path=WEEKLY_PATH)
    with_aatp["adp_round"] = with_aatp["overall_adp_observed"].apply(ep.adp_round)
    matched = with_aatp[with_aatp["adp_matched"]].copy()
    return matched.dropna(subset=["adp_round"])


@pytest.fixture(scope="module")
def promoted_ep_df(real_matched_population):
    return ep.fit_expected_production(real_matched_population)


class TestAdpRound:
    def test_ceil_division_by_12(self):
        assert ep.adp_round(1) == 1
        assert ep.adp_round(12) == 1
        assert ep.adp_round(13) == 2
        assert ep.adp_round(24) == 2
        assert ep.adp_round(25) == 3

    def test_nan_returns_none(self):
        assert ep.adp_round(float("nan")) is None

    def test_uses_config_teams_by_default(self):
        import config
        assert ep.adp_round(12) == int(np.ceil(12 / config.TEAMS))


class TestOracleParity:
    def test_row_count_matches(self, oracle_ep_df, promoted_ep_df):
        assert len(promoted_ep_df) == len(oracle_ep_df)

    def test_expected_production_matches_within_tolerance(self, oracle_ep_df, promoted_ep_df):
        key_cols = ["prediction_season", "position", "draft_round"]
        merged = promoted_ep_df.merge(oracle_ep_df, on=key_cols, suffixes=("_mine", "_oracle"))
        assert len(merged) == len(oracle_ep_df), "join key mismatch -- some (season, position, round) cells differ"
        diff = (merged["expected_production_mine"] - merged["expected_production_oracle"]).abs()
        assert (diff < 1e-9).all(), f"max diff = {diff.max()}"

    def test_offsets_match_within_tolerance(self, oracle_ep_df, promoted_ep_df):
        key_cols = ["prediction_season", "position", "draft_round"]
        merged = promoted_ep_df.merge(oracle_ep_df, on=key_cols, suffixes=("_mine", "_oracle"))
        both_null = merged["positional_offset_applied_mine"].isna() & merged["positional_offset_applied_oracle"].isna()
        both_present = merged["positional_offset_applied_mine"].notna() & merged["positional_offset_applied_oracle"].notna()
        assert (both_null | both_present).all(), "offset null-ness disagrees between promoted and oracle"
        diff = (merged.loc[both_present, "positional_offset_applied_mine"] - merged.loc[both_present, "positional_offset_applied_oracle"]).abs()
        assert (diff < 1e-9).all()

    def test_first_fitted_season_is_2010(self, promoted_ep_df):
        """2010 = 2007 (trustworthy ADP start) + 3 (SBV_MIN_PRIOR_SEASONS)
        -- derived from the real population's earliest season, not
        hardcoded anywhere in expected_production.py."""
        assert promoted_ep_df["prediction_season"].min() == 2010


class TestNoLeakage:
    """Mechanical, not just documented: perturbing season Y or any
    later season must not move season Y's fitted values; perturbing an
    earlier season must be ABLE to move them (proving training data is
    actually used, not just ignored)."""

    def _synthetic_population(self, n_seasons=6, start_season=2007):
        rows = []
        rng = np.random.default_rng(42)
        for i, season in enumerate(range(start_season, start_season + n_seasons)):
            for position in SBV_POSITIONS:
                for rnd in range(1, 5):
                    for _ in range(6):
                        rows.append({
                            "season": season, "position": position, "adp_round": rnd,
                            "AATP": 100 + rnd * 10 + rng.normal(0, 3),
                        })
        return pd.DataFrame(rows)

    def test_perturbing_season_y_itself_does_not_move_its_own_fit(self):
        df = self._synthetic_population()
        target_year = df["season"].max()  # the last season present -- perturb it directly
        baseline = ep.fit_expected_production(df)
        baseline_y = baseline[baseline["prediction_season"] == target_year].sort_values(
            ["position", "draft_round"]
        ).reset_index(drop=True)

        perturbed = df.copy()
        perturbed.loc[perturbed["season"] == target_year, "AATP"] += 10_000
        refit = ep.fit_expected_production(perturbed)
        refit_y = refit[refit["prediction_season"] == target_year].sort_values(
            ["position", "draft_round"]
        ).reset_index(drop=True)

        pd.testing.assert_series_equal(
            baseline_y["expected_production"], refit_y["expected_production"], check_names=False,
        )

    def test_perturbing_a_future_season_does_not_move_earlier_fit(self):
        df = self._synthetic_population()
        seasons = sorted(df["season"].unique())
        target_year = seasons[3]  # an interior prediction season with future data available
        future_year = seasons[-1]
        assert future_year > target_year

        baseline = ep.fit_expected_production(df)
        baseline_y = baseline[baseline["prediction_season"] == target_year].sort_values(
            ["position", "draft_round"]
        ).reset_index(drop=True)

        perturbed = df.copy()
        perturbed.loc[perturbed["season"] == future_year, "AATP"] += 10_000
        refit = ep.fit_expected_production(perturbed)
        refit_y = refit[refit["prediction_season"] == target_year].sort_values(
            ["position", "draft_round"]
        ).reset_index(drop=True)

        pd.testing.assert_series_equal(
            baseline_y["expected_production"], refit_y["expected_production"], check_names=False,
        )

    def test_perturbing_a_prior_season_can_move_the_fit(self):
        df = self._synthetic_population()
        seasons = sorted(df["season"].unique())
        target_year = seasons[3]
        prior_year = seasons[1]
        assert prior_year < target_year

        baseline = ep.fit_expected_production(df)
        baseline_y = baseline[baseline["prediction_season"] == target_year].sort_values(
            ["position", "draft_round"]
        ).reset_index(drop=True)

        perturbed = df.copy()
        perturbed.loc[perturbed["season"] == prior_year, "AATP"] += 10_000
        refit = ep.fit_expected_production(perturbed)
        refit_y = refit[refit["prediction_season"] == target_year].sort_values(
            ["position", "draft_round"]
        ).reset_index(drop=True)

        assert not baseline_y["expected_production"].equals(refit_y["expected_production"]), (
            "perturbing a prior season had NO effect -- training data isn't actually being used"
        )


class TestMinimumHistoryEnforcement:
    def _synthetic_population(self, n_seasons, start_season=2007):
        rows = []
        for season in range(start_season, start_season + n_seasons):
            for position in SBV_POSITIONS:
                for rnd in range(1, 4):
                    for _ in range(5):
                        rows.append({"season": season, "position": position, "adp_round": rnd, "AATP": 100.0 + rnd})
        return pd.DataFrame(rows)

    def test_no_fit_with_fewer_than_min_prior_seasons(self):
        df = self._synthetic_population(n_seasons=SBV_MIN_PRIOR_SEASONS)  # exactly min, zero seasons qualify to be predicted
        out = ep.fit_expected_production(df)
        assert out.empty

    def test_fit_appears_once_enough_prior_seasons_exist(self):
        df = self._synthetic_population(n_seasons=SBV_MIN_PRIOR_SEASONS + 1)
        out = ep.fit_expected_production(df)
        assert not out.empty
        assert out["prediction_season"].min() == 2007 + SBV_MIN_PRIOR_SEASONS

    def test_custom_min_prior_seasons_parameter_is_honored(self):
        df = self._synthetic_population(n_seasons=5)
        out = ep.fit_expected_production(df, min_prior_seasons=4)
        assert out["prediction_season"].min() == 2007 + 4


class TestOffsetAndRecencyByPosition:
    def test_recency_weighted_flag_matches_settled_positions(self, promoted_ep_df):
        for position in SBV_POSITIONS:
            values = set(promoted_ep_df.loc[promoted_ep_df["position"] == position, "recency_weighted"].unique())
            expected = {position in SBV_RECENCY_POSITIONS}
            assert values == expected, f"{position}: expected recency_weighted={expected}, got {values}"

    def test_offset_applied_only_for_settled_offset_positions(self, promoted_ep_df):
        for position in SBV_POSITIONS:
            sub = promoted_ep_df[promoted_ep_df["position"] == position]
            if position in SBV_ROUND_OFFSET_POSITIONS:
                assert sub["positional_offset_applied"].notna().any(), f"{position} should have a non-null offset somewhere"
            else:
                assert sub["positional_offset_applied"].isna().all(), f"{position} should never have an offset applied"

    def test_half_life_years_populated_only_when_recency_weighted(self, promoted_ep_df):
        recency_rows = promoted_ep_df[promoted_ep_df["recency_weighted"]]
        non_recency_rows = promoted_ep_df[~promoted_ep_df["recency_weighted"]]
        assert (recency_rows["half_life_years"] == SBV_RECENCY_HALF_LIFE_YEARS).all()
        assert non_recency_rows["half_life_years"].isna().all()


class TestAllTrustworthyAdpRowsUsed:
    def test_no_draft_depth_cap_all_rounds_present_in_training_are_fittable(self):
        """Synthetic population with a deep round (16) that would be
        excluded by a fixed-depth cap like 200 -- must still appear."""
        rows = []
        for season in range(2007, 2013):
            for rnd in [1, 16]:
                for _ in range(5):
                    rows.append({"season": season, "position": "WR", "adp_round": rnd, "AATP": 50.0})
        df = pd.DataFrame(rows)
        out = ep.fit_expected_production(df)
        assert 16 in set(out["draft_round"].unique()), "round 16 was dropped -- a draft-depth cap must have been applied"

    def test_sample_size_reflects_full_uncapped_training_count(self):
        rows = []
        for season in [2007, 2008, 2009, 2010]:  # 2010 row needed so the walk-forward loop visits it as an asof_year
            for _ in range(37):
                rows.append({"season": season, "position": "RB", "adp_round": 5, "AATP": 60.0})
        df = pd.DataFrame(rows)
        out = ep.fit_expected_production(df, min_prior_seasons=3)
        row = out[(out["prediction_season"] == 2010) & (out["position"] == "RB") & (out["draft_round"] == 5)]
        assert len(row) == 1
        assert row.iloc[0]["sample_size"] == 37 * 3  # only the 3 PRIOR seasons count, not 2010 itself


class TestValidateLookup:
    def _minimal_valid_lookup(self):
        return pd.DataFrame([{
            "prediction_season": 2010, "position": "QB", "draft_round": 1,
            "expected_production": 200.0, "positional_offset_applied": 5.0,
            "recency_weighted": True, "half_life_years": 5.0, "sample_size": 10,
            "sbv_version": SBV_VERSION, "fit_timestamp": pd.Timestamp.now(tz="UTC"),
        }])

    def test_valid_lookup_passes(self):
        ep.validate_lookup(self._minimal_valid_lookup())  # must not raise

    def test_stale_version_raises(self):
        df = self._minimal_valid_lookup()
        df["sbv_version"] = "0.1-stale"
        with pytest.raises(ValueError, match="STALE E_P LOOKUP TABLE"):
            ep.validate_lookup(df)

    def test_missing_column_raises(self):
        df = self._minimal_valid_lookup().drop(columns=["sample_size"])
        with pytest.raises(ValueError, match="missing required columns"):
            ep.validate_lookup(df)

    def test_empty_lookup_raises(self):
        df = self._minimal_valid_lookup().iloc[0:0]
        with pytest.raises(ValueError, match="empty"):
            ep.validate_lookup(df)

    def test_duplicate_key_raises(self):
        df = pd.concat([self._minimal_valid_lookup(), self._minimal_valid_lookup()], ignore_index=True)
        with pytest.raises(ValueError, match="duplicate"):
            ep.validate_lookup(df)


class TestSchemaAndUniqueness:
    def test_all_schema_columns_present(self, promoted_ep_df):
        assert set(ep.LOOKUP_SCHEMA_COLUMNS) <= set(promoted_ep_df.columns)

    def test_no_duplicate_keys(self, promoted_ep_df):
        dupes = promoted_ep_df.duplicated(subset=list(ep.LOOKUP_KEY_COLUMNS))
        assert not dupes.any()


class TestDeterministicOutput:
    def test_two_runs_produce_identical_output_except_timestamp(self, real_matched_population):
        run1 = ep.fit_expected_production(real_matched_population)
        run2 = ep.fit_expected_production(real_matched_population)
        cols_to_compare = [c for c in ep.LOOKUP_SCHEMA_COLUMNS if c != "fit_timestamp"]
        pd.testing.assert_frame_equal(
            run1[cols_to_compare].reset_index(drop=True),
            run2[cols_to_compare].reset_index(drop=True),
        )


class TestNoResearchImports:
    def test_module_does_not_import_research(self):
        """Uses ast, not string-matching on source lines -- a naive
        `"research" not in line` check false-positives on this very
        module's own docstring prose (which discusses the research
        oracle chain by path). Parsing real import statements avoids
        that entirely."""
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(ep))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "research" not in alias.name, f"expected_production.py must not import {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "research" not in module, f"expected_production.py must not import from {module}"
