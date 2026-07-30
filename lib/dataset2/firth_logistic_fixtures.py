"""
lib/dataset2/firth_logistic_fixtures.py

Shared, deterministic fixture generators for validating
lib/dataset2/firth_logistic.py -- used by BOTH
tests/test_firth_logistic.py (the internal Python validation suite)
and scripts/ci_export_firth_fixtures.py (the external R `logistf`
cross-check run on GitHub Actions), so both checks run against
IDENTICAL data. Factored out into one shared module specifically so
"the Python suite and the R cross-check used the same fixtures" is a
structural guarantee, not a claim that has to be manually kept in
sync across two files.

Three fixtures, matching the three regimes
DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md's Firth validation
requirement names explicitly:
- `ordinary_fixture()`: large, well-powered, no separation -- Firth
  and ordinary MLE should closely agree.
- `sparse_fixture()`: event rate close to the real discovery-window
  Star rate (47/5725 ~ 0.82%), WITH real covariate structure (not just
  an intercept) -- the regime Firth's method exists for.
- `complete_separation_fixture()`: one predictor perfectly separates
  the outcome -- ordinary MLE diverges, Firth must not.

Every function returns (X, y, columns) -- `columns` names each column
of X (including the intercept) for CSV export / R model formulas.
"""

import numpy as np


def ordinary_fixture():
    rng = np.random.default_rng(42)
    n = 8000
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    true_beta = np.array([-0.3, 0.8, -0.5])
    X = np.column_stack([np.ones(n), x1, x2])
    eta = X @ true_beta
    p = 1.0 / (1.0 + np.exp(-eta))
    y = rng.binomial(1, p)
    return X, y, ["intercept", "x1", "x2"]


def sparse_fixture():
    """n and event rate chosen to land close to the real discovery-
    window star_by_value_label rate (47/5725 ~ 0.0082), with two real
    covariates (not just an intercept) -- TestEstablishedReferenceExample
    already covers the pure intercept-only closed-form case separately."""
    rng = np.random.default_rng(2026)
    n = 5725
    x1 = rng.normal(size=n)
    x2 = rng.binomial(1, 0.3, size=n).astype(float)
    # Intercept tuned so the baseline rate lands near the real 0.82%
    # target before the covariates shift individual rows up/down.
    true_beta = np.array([-4.85, 0.35, 0.25])
    X = np.column_stack([np.ones(n), x1, x2])
    eta = X @ true_beta
    p = 1.0 / (1.0 + np.exp(-eta))
    y = rng.binomial(1, p)
    return X, y, ["intercept", "x1_continuous", "x2_boolean"]


def complete_separation_fixture(n_per_group=40):
    rng = np.random.default_rng(0)
    x = np.concatenate([np.zeros(n_per_group), np.ones(n_per_group)])
    y = np.concatenate([np.zeros(n_per_group), np.ones(n_per_group)])  # PERFECT separation on x
    noise_cov = rng.normal(size=2 * n_per_group)
    X = np.column_stack([np.ones(2 * n_per_group), x, noise_cov])
    return X, y, ["intercept", "x_separating", "x_noise"]


FIXTURES = {
    "ordinary": ordinary_fixture,
    "sparse": sparse_fixture,
    "complete_separation": complete_separation_fixture,
}
