"""
tests/test_firth_logistic.py

Validation suite for lib/dataset2/firth_logistic.py, required before
this implementation may be used for any real Star-target adjusted
result (research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md
§4). Six required checks:

1. TestEstablishedReferenceExample -- reproduces a real, analytically
   provable closed-form result, not a memorized/possibly-misremembered
   number from a specific paper's table. For an intercept-only model
   (X = column of 1s), Firth's penalized score equation reduces
   EXACTLY to p_hat = (k + 0.5) / (n + 1) for k successes in n trials
   -- the Jeffreys-prior Beta(0.5, 0.5) posterior mode for a binomial
   proportion. This is derived directly from Firth's own score
   modification (shown in the test docstring below) and is widely
   cited as the special-case solution in the Firth logistic-regression
   literature (e.g. Heinze & Schemper 2002) -- an established result
   this implementation can be checked against with mathematical
   certainty, not recalled-from-memory trivia.
2. TestCompleteSeparation -- ordinary MLE logistic regression is shown
   to diverge (real, not asserted) on a perfectly-separating predictor;
   Firth's gives a finite, sensible estimate on the identical data.
3. TestLargeNonsparseAgreement -- Firth's estimate closely matches
   ordinary MLE on a large, non-separated fixture (Firth's bias
   correction should vanish asymptotically -- Firth 1993's own
   asymptotic argument).
4. TestDeterminism -- identical results under row-order permutation and
   different starting values.
5. TestConfidenceIntervalsAndLRTest -- profile-likelihood CI coverage
   validated by simulation against a KNOWN true coefficient (not just
   "does it run"), plus real LR-test behavior on both a strongly
   predictive covariate and a null one.
6. TestIndependentImplementationCrossCheck -- DISCLOSED GAP, not
   silently skipped: no R/Rscript, conda, pyenv, or alternate Python
   interpreter compatible with any installable Firth package
   (`firthlogist` on PyPI has no wheel for this environment's Python
   version; confirmed directly that a manually-downloaded wheel
   targeting a different Python ABI fails to import) is available in
   this sandbox. Per instruction: "If the independent validation
   cannot be completed yet, build the descriptive and bust-analysis
   portions but do not treat adjusted Star results as final." This
   test is marked skip with the exact reason, so the gap is visible in
   every test run rather than silently absent.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.firth_logistic import fit_firth_logistic, firth_lr_test, firth_profile_ci


def _intercept_only_X(n):
    return np.ones((n, 1))


class TestEstablishedReferenceExample:
    """Firth's penalized score for an intercept-only model:
    U*(beta) = sum_i (y_i - p) + sum_i h_i*(0.5-p), with h_i = 1/n
    identically (X is a column of 1s, so the hat diagonal is uniform).
    U*(beta) = (k - n*p) + (0.5 - p) = k + 0.5 - p*(n+1).
    Setting to zero: p_hat = (k+0.5)/(n+1) -- exactly the Jeffreys
    Beta(0.5,0.5) posterior mode. This must hold EXACTLY (to numerical
    tolerance), for any k, n."""

    @pytest.mark.parametrize(
        "k,n",
        [
            (5, 10), (0, 10), (10, 10), (1, 3), (2, 3),
            (47, 5725),  # the real discovery-window Star rate this validation exists to protect
            (0, 50), (50, 50), (25, 100),
        ],
    )
    def test_intercept_only_matches_jeffreys_closed_form(self, k, n):
        y = np.array([1.0] * k + [0.0] * (n - k))
        X = _intercept_only_X(n)
        fit = fit_firth_logistic(X, y)
        assert fit.converged
        p_hat_firth = 1.0 / (1.0 + np.exp(-fit.beta[0]))
        p_hat_closed_form = (k + 0.5) / (n + 1)
        assert p_hat_firth == pytest.approx(p_hat_closed_form, abs=1e-6)

    def test_zero_events_gives_finite_positive_estimate(self):
        # k=0 is exactly where ordinary MLE diverges to p_hat=0 /
        # beta=-inf. Firth's closed-form answer is (0.5)/(n+1) > 0,
        # finite -- the entire point of the method for the Star target.
        n = 5725
        y = np.zeros(n)
        X = _intercept_only_X(n)
        fit = fit_firth_logistic(X, y)
        assert fit.converged
        assert np.isfinite(fit.beta[0])
        p_hat = 1.0 / (1.0 + np.exp(-fit.beta[0]))
        assert p_hat == pytest.approx(0.5 / (n + 1), abs=1e-8)


class TestCompleteSeparation:
    def _separated_fixture(self, n_per_group=40):
        rng = np.random.default_rng(0)
        x = np.concatenate([np.zeros(n_per_group), np.ones(n_per_group)])
        y = np.concatenate([np.zeros(n_per_group), np.ones(n_per_group)])  # PERFECT separation on x
        noise_cov = rng.normal(size=2 * n_per_group)  # a real, unrelated second covariate
        X = np.column_stack([np.ones(2 * n_per_group), x, noise_cov])
        return X, y

    def test_ordinary_mle_diverges_on_complete_separation(self):
        X, y = self._separated_fixture()
        # Unpenalized Newton-Raphson (ordinary MLE) -- real
        # implementation, not asserted to fail: on perfect separation,
        # the coefficient on x grows without bound each iteration.
        beta = np.zeros(X.shape[1])
        prev_norm = 0.0
        diverged = False
        for _ in range(30):
            eta = X @ beta
            pi = 1.0 / (1.0 + np.exp(-np.clip(eta, -30, 30)))
            W = pi * (1 - pi)
            W = np.clip(W, 1e-10, None)
            XtWX = (X * W[:, None]).T @ X
            try:
                delta = np.linalg.solve(XtWX, X.T @ (y - pi))
            except np.linalg.LinAlgError:
                diverged = True
                break
            beta = beta + delta
            norm = np.linalg.norm(beta)
            if norm > 1e6 or not np.isfinite(norm):
                diverged = True
                break
            prev_norm = norm
        assert diverged or prev_norm > 50, f"expected ordinary MLE to diverge under complete separation, got |beta|={prev_norm}"

    def test_firth_gives_finite_sensible_estimate_on_same_data(self):
        X, y = self._separated_fixture()
        fit = fit_firth_logistic(X, y)
        assert fit.converged
        assert np.all(np.isfinite(fit.beta))
        # The separating coefficient (index 1) must be positive (higher
        # x -> higher y, the real direction in this fixture) and finite
        # -- not blown up to an arbitrarily large magnitude.
        assert fit.beta[1] > 0
        assert abs(fit.beta[1]) < 50  # sensible, not diverged
        # The unrelated noise covariate should NOT show a large effect.
        assert abs(fit.beta[2]) < 5


class TestLargeNonsparseAgreement:
    def test_firth_close_to_ordinary_mle_when_well_powered(self):
        rng = np.random.default_rng(42)
        n = 8000
        x1 = rng.normal(size=n)
        x2 = rng.normal(size=n)
        true_beta = np.array([-0.3, 0.8, -0.5])
        X = np.column_stack([np.ones(n), x1, x2])
        eta = X @ true_beta
        p = 1.0 / (1.0 + np.exp(-eta))
        y = rng.binomial(1, p)

        firth_fit = fit_firth_logistic(X, y)
        assert firth_fit.converged

        # Ordinary MLE via unpenalized Newton-Raphson, independent of
        # the Firth code path (no shared penalty term).
        beta = np.zeros(3)
        for _ in range(50):
            eta_i = X @ beta
            pi = 1.0 / (1.0 + np.exp(-eta_i))
            W = pi * (1 - pi)
            XtWX = (X * W[:, None]).T @ X
            delta = np.linalg.solve(XtWX, X.T @ (y - pi))
            beta = beta + delta
            if np.max(np.abs(delta)) < 1e-10:
                break
        mle_beta = beta

        # With n=8000 and well-separated classes, Firth's bias
        # correction should be small -- real, checkable closeness, not
        # a vacuous "both ran" check.
        assert np.allclose(firth_fit.beta, mle_beta, atol=0.05), (
            f"Firth {firth_fit.beta} vs ordinary MLE {mle_beta} diverge more than expected at large n"
        )


class TestDeterminism:
    def _fixture(self, seed=1, n=500):
        rng = np.random.default_rng(seed)
        x1 = rng.normal(size=n)
        x2 = rng.binomial(1, 0.3, size=n).astype(float)
        true_beta = np.array([0.1, 0.6, -0.4])
        X = np.column_stack([np.ones(n), x1, x2])
        eta = X @ true_beta
        p = 1.0 / (1.0 + np.exp(-eta))
        y = rng.binomial(1, p)
        return X, y

    def test_row_order_independence(self):
        X, y = self._fixture()
        fit_a = fit_firth_logistic(X, y)
        perm = np.random.default_rng(99).permutation(len(y))
        fit_b = fit_firth_logistic(X[perm], y[perm])
        assert np.allclose(fit_a.beta, fit_b.beta, atol=1e-6)
        assert np.allclose(fit_a.cov, fit_b.cov, atol=1e-6)

    def test_starting_value_independence(self):
        X, y = self._fixture()
        fit_zero = fit_firth_logistic(X, y, beta_init=np.zeros(3))
        fit_offset = fit_firth_logistic(X, y, beta_init=np.array([1.5, -2.0, 3.0]))
        assert fit_zero.converged and fit_offset.converged
        assert np.allclose(fit_zero.beta, fit_offset.beta, atol=1e-5)

    def test_repeated_fit_is_byte_identical(self):
        X, y = self._fixture()
        fit_a = fit_firth_logistic(X, y)
        fit_b = fit_firth_logistic(X, y)
        assert np.array_equal(fit_a.beta, fit_b.beta)


class TestConfidenceIntervalsAndLRTest:
    def test_profile_ci_contains_point_estimate_and_is_ordered(self):
        rng = np.random.default_rng(7)
        n = 400
        x = rng.normal(size=n)
        true_beta = np.array([-0.2, 0.9])
        X = np.column_stack([np.ones(n), x])
        p = 1.0 / (1.0 + np.exp(-(X @ true_beta)))
        y = rng.binomial(1, p)
        lower, upper, fit = firth_profile_ci(X, y, coef_index=1)
        assert lower < fit.beta[1] < upper

    def test_profile_ci_empirical_coverage_near_nominal(self):
        """Real simulation-based coverage check -- not just 'the CI
        exists'. Fit Firth + 95% profile CI on many datasets simulated
        from a KNOWN true beta; the true value should fall inside the
        CI close to 95% of the time."""
        rng = np.random.default_rng(123)
        n_sims = 150
        n = 120
        true_beta1 = 0.7
        covered = 0
        for _ in range(n_sims):
            x = rng.normal(size=n)
            X = np.column_stack([np.ones(n), x])
            eta = X @ np.array([0.0, true_beta1])
            p = 1.0 / (1.0 + np.exp(-eta))
            y = rng.binomial(1, p)
            lower, upper, _ = firth_profile_ci(X, y, coef_index=1)
            if lower <= true_beta1 <= upper:
                covered += 1
        coverage = covered / n_sims
        # Monte Carlo tolerance band around the nominal 95% for 150 sims.
        assert 0.85 <= coverage <= 1.0, f"empirical 95% CI coverage was {coverage:.3f} over {n_sims} sims"

    def test_lr_test_rejects_strong_real_effect(self):
        rng = np.random.default_rng(11)
        n = 600
        x = rng.normal(size=n)
        X = np.column_stack([np.ones(n), x])
        true_beta = np.array([0.0, 2.0])  # strong, real effect
        p = 1.0 / (1.0 + np.exp(-(X @ true_beta)))
        y = rng.binomial(1, p)
        lr_stat, p_value, full_fit, reduced_fit = firth_lr_test(X, y, coef_index=1)
        assert lr_stat > 0
        assert p_value < 0.001
        assert full_fit.penalized_loglik > reduced_fit.penalized_loglik

    def test_lr_test_does_not_reject_null_effect(self):
        rng = np.random.default_rng(22)
        n = 600
        x = rng.normal(size=n)  # unrelated to y
        y = rng.binomial(1, 0.5, size=n)
        X = np.column_stack([np.ones(n), x])
        lr_stat, p_value, _, _ = firth_lr_test(X, y, coef_index=1)
        assert p_value > 0.05


class TestIndependentImplementationCrossCheck:
    @pytest.mark.skip(
        reason=(
            "DISCLOSED GAP, not silently absent: no independent established Firth "
            "implementation is reachable in this sandbox. Checked directly: (1) no R or "
            "Rscript on PATH (R's logistf package would be the standard cross-check); "
            "(2) `firthlogist` on PyPI has no wheel for this environment's Python 3.14 "
            "interpreter; (3) no conda/mamba/pyenv and no alternate Python 3.9-3.11 "
            "interpreter exists on this machine to run a downloaded-but-ABI-incompatible "
            "wheel (verified: importing a manually-fetched firthlogist wheel under this "
            "interpreter fails with a real numpy ABI ImportError, not a hypothetical one). "
            "Per instruction: since this specific check cannot be completed, adjusted "
            "Star results must not be treated as final until it is -- see "
            "DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md's Phase 1 status note."
        )
    )
    def test_cross_check_against_r_logistf_or_equivalent(self):
        pass
