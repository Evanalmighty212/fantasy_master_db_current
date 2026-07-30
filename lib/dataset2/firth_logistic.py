"""
lib/dataset2/firth_logistic.py

Firth's bias-reduced (penalized-likelihood) logistic regression --
Firth (1993), "Bias reduction of maximum likelihood estimates",
Biometrika 80(1). Built from scratch: no compatible pre-built package
is installable in this environment (`firthlogist` on PyPI has no wheel
for this interpreter's Python version; no R/Rscript, conda, pyenv, or
alternate Python interpreter is available on this machine to run an
independent implementation like R's `logistf` -- checked directly, not
assumed). See tests/test_firth_logistic.py for the full validation
suite this implementation must pass BEFORE it is trusted for any real
Star result (research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md
§4's requirement).

ALGORITHM (IRLS with Firth's score modification, matching Firth 1993
and Heinze & Schemper 2002's "A solution to the problem of separation
in logistic regression", Statistics in Medicine 21(16)):

Ordinary logistic regression solves U(beta) = X'(y - pi) = 0. Firth's
method instead solves the score of the PENALIZED log-likelihood
l*(beta) = l(beta) + 0.5*log(det(I(beta))), where I(beta) = X'WX is the
Fisher information (W = diag(pi_i*(1-pi_i))). The penalized score is

    U*(beta)_j = sum_i x_ij * (y_i - pi_i + h_i*(0.5 - pi_i))

where h_i is the i-th diagonal of the hat matrix
H = W^0.5 X (X'WX)^-1 X' W^0.5, i.e. h_i = W_i * x_i' (X'WX)^-1 x_i.
Solved by Newton-Raphson using the same X'WX as the Hessian
approximation, with step-halving whenever a step would decrease the
penalized log-likelihood (Firth's own recommended safeguard -- this is
what keeps the algorithm well-behaved under complete/quasi separation,
where ordinary MLE diverges).

CONFIDENCE INTERVALS: profile-likelihood, not Wald. Firth's own
literature (Heinze & Schemper 2002) recommends profile penalized
likelihood over Wald intervals precisely because Wald SEs from the
penalized Hessian are known to behave poorly near separation -- the
exact regime Firth's method exists to handle. `firth_profile_ci()`
finds the two beta_j values where the profile penalized deviance
crosses the chi-square(1) threshold, refitting every OTHER coefficient
at each candidate value (a real constrained re-fit, not an
approximation).

SIGNIFICANCE: penalized likelihood-ratio test (`firth_lr_test()`),
comparing the full penalized log-likelihood against a model with the
coefficient of interest fixed at 0 (again a real constrained re-fit,
not a Wald z-test), since the same non-normality that motivates
profile CIs applies to significance testing.
"""

import sys
from pathlib import Path

import numpy as np
from scipy import stats
from scipy.optimize import brentq

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

MAX_ITER_DEFAULT = 100
TOL_DEFAULT = 1e-8
MAX_STEP_HALVINGS = 20


def _sigmoid(eta: np.ndarray) -> np.ndarray:
    # Numerically stable logistic function.
    out = np.empty_like(eta, dtype=float)
    pos = eta >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-eta[pos]))
    exp_eta = np.exp(eta[~pos])
    out[~pos] = exp_eta / (1.0 + exp_eta)
    return out


def _penalized_loglik(X: np.ndarray, y: np.ndarray, beta: np.ndarray) -> float:
    eta = X @ beta
    # sum(y*eta - log(1+exp(eta))), via logaddexp for stability.
    ll = np.sum(y * eta - np.logaddexp(0.0, eta))
    pi = _sigmoid(eta)
    W = pi * (1.0 - pi)
    XtWX = (X * W[:, None]).T @ X
    sign, logdet = np.linalg.slogdet(XtWX)
    if sign <= 0:
        return -np.inf
    return ll + 0.5 * logdet


def _fisher_info(X: np.ndarray, beta: np.ndarray) -> np.ndarray:
    eta = X @ beta
    pi = _sigmoid(eta)
    W = pi * (1.0 - pi)
    return (X * W[:, None]).T @ X, pi, W


def _hat_diagonal(X: np.ndarray, XtWX_inv: np.ndarray, W: np.ndarray) -> np.ndarray:
    # h_i = W_i * x_i' (X'WX)^-1 x_i, vectorized.
    return W * np.einsum("ij,jk,ik->i", X, XtWX_inv, X)


class FirthFitResult:
    def __init__(self, beta, cov, converged, n_iter, penalized_loglik, fixed_mask=None):
        self.beta = beta
        self.cov = cov
        self.converged = converged
        self.n_iter = n_iter
        self.penalized_loglik = penalized_loglik
        self.fixed_mask = fixed_mask if fixed_mask is not None else np.zeros(len(beta), dtype=bool)

    @property
    def se(self):
        return np.sqrt(np.diag(self.cov))


def fit_firth_logistic(
    X: np.ndarray,
    y: np.ndarray,
    beta_init: np.ndarray = None,
    fixed_index: int = None,
    fixed_value: float = None,
    max_iter: int = MAX_ITER_DEFAULT,
    tol: float = TOL_DEFAULT,
) -> FirthFitResult:
    """Fits Firth's bias-reduced logistic regression via penalized IRLS
    with step-halving. `X` must already include an intercept column if
    one is wanted (never added implicitly -- caller's explicit choice).

    `fixed_index`/`fixed_value`: if given, that coefficient is pinned
    at `fixed_value` and never updated -- used by `firth_profile_ci()`
    and `firth_lr_test()` for real constrained re-fits, not a Wald
    approximation.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = X.shape
    beta = np.zeros(p) if beta_init is None else np.array(beta_init, dtype=float)
    if fixed_index is not None:
        beta[fixed_index] = fixed_value

    free = np.ones(p, dtype=bool)
    if fixed_index is not None:
        free[fixed_index] = False

    prev_ll = _penalized_loglik(X, y, beta)
    converged = False
    n_iter = 0

    for n_iter in range(1, max_iter + 1):
        XtWX, pi, W = _fisher_info(X, beta)
        XtWX_inv = np.linalg.pinv(XtWX)
        h = _hat_diagonal(X, XtWX_inv, W)
        resid = y - pi + h * (0.5 - pi)
        U = X.T @ resid  # penalized score, all p entries

        delta_full = XtWX_inv @ U
        delta = np.zeros(p)
        delta[free] = delta_full[free]

        step = 1.0
        new_beta = beta + step * delta
        new_ll = _penalized_loglik(X, y, new_beta)
        halvings = 0
        while (not np.isfinite(new_ll) or new_ll < prev_ll - 1e-10) and halvings < MAX_STEP_HALVINGS:
            step *= 0.5
            new_beta = beta + step * delta
            new_ll = _penalized_loglik(X, y, new_beta)
            halvings += 1

        max_change = np.max(np.abs(new_beta[free] - beta[free])) if free.any() else 0.0
        beta = new_beta
        prev_ll = new_ll

        if max_change < tol:
            converged = True
            break

    XtWX, pi, W = _fisher_info(X, beta)
    cov = np.linalg.pinv(XtWX)
    fixed_mask = np.zeros(p, dtype=bool)
    if fixed_index is not None:
        fixed_mask[fixed_index] = True
    return FirthFitResult(beta, cov, converged, n_iter, prev_ll, fixed_mask)


def firth_profile_ci(X, y, coef_index: int, alpha: float = 0.05, search_width_se: float = 12.0, **fit_kwargs):
    """Profile-penalized-likelihood confidence interval for
    coefficient `coef_index` -- the recommended CI for Firth's method
    (Heinze & Schemper 2002), not a Wald interval. Finds beta values
    where 2*(l*_full - l*_profile(beta)) crosses chi2(1, 1-alpha),
    re-fitting every OTHER coefficient at each candidate value (a real
    constrained fit via `fixed_index`/`fixed_value`, not an
    approximation). Returns (lower, upper, full_fit_result).
    """
    full_fit = fit_firth_logistic(X, y, **fit_kwargs)
    target = full_fit.penalized_loglik - 0.5 * stats.chi2.ppf(1 - alpha, df=1)
    point = full_fit.beta[coef_index]
    se_guess = full_fit.se[coef_index] if np.isfinite(full_fit.se[coef_index]) else 1.0
    se_guess = se_guess if se_guess > 0 else 1.0

    def profile_ll(beta_val):
        fit = fit_firth_logistic(
            X, y, beta_init=full_fit.beta, fixed_index=coef_index, fixed_value=beta_val, **fit_kwargs
        )
        return fit.penalized_loglik

    def f(beta_val):
        return profile_ll(beta_val) - target

    # Bracket outward from the point estimate until f changes sign.
    def bracket(direction):
        lo = point
        hi = point + direction * se_guess
        step = se_guess
        tries = 0
        while f(hi) > 0 and tries < 40:
            step *= 1.5
            hi = point + direction * step
            tries += 1
        return lo, hi

    lo_lo, lo_hi = bracket(-1.0)
    hi_lo, hi_hi = bracket(1.0)
    lower = brentq(f, lo_lo - 1e-6, lo_hi, xtol=1e-6, maxiter=200) if f(lo_hi) <= 0 else -np.inf
    upper = brentq(f, hi_lo + 1e-6, hi_hi, xtol=1e-6, maxiter=200) if f(hi_hi) <= 0 else np.inf
    return lower, upper, full_fit


def firth_lr_test(X, y, coef_index: int, **fit_kwargs):
    """Penalized likelihood-ratio test for H0: beta[coef_index] = 0,
    via a real constrained re-fit (never a Wald z-test -- Firth's own
    motivation applies to significance testing exactly as it does to
    CIs). Returns (lr_statistic, p_value, full_fit_result,
    reduced_fit_result)."""
    full_fit = fit_firth_logistic(X, y, **fit_kwargs)
    reduced_fit = fit_firth_logistic(X, y, fixed_index=coef_index, fixed_value=0.0, **fit_kwargs)
    lr_stat = 2.0 * (full_fit.penalized_loglik - reduced_fit.penalized_loglik)
    lr_stat = max(lr_stat, 0.0)
    p_value = 1.0 - stats.chi2.cdf(lr_stat, df=1)
    return lr_stat, p_value, full_fit, reduced_fit
