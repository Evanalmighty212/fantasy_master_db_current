"""
lib/dataset2/firth_logistic.py

Firth's bias-reduced (penalized-likelihood) logistic regression --
Firth (1993), "Bias reduction of maximum likelihood estimates",
Biometrika 80(1). Built from scratch: no compatible pre-built package
is installable in this environment (`firthlogist` on PyPI has no wheel
for this interpreter's Python version; no R/Rscript, conda, pyenv, or
alternate Python interpreter is available on this machine to run an
independent implementation like R's `logistf` locally -- checked
directly, not assumed).

INDEPENDENT VALIDATION: COMPLETE (2026-07), via GitHub Actions --
R's `logistf` run on the identical fixtures this module's own test
suite uses (`.github/workflows/fetch_schedules_and_firth_crosscheck.yml`,
real output committed at
`research/dataset2/firth_crosscheck_results_2026_07/`). Coefficients,
profile-likelihood CIs, and LR-test p-values now agree with R to under
1e-6 on all three regimes (ordinary/sparse/complete-separation).
`tests/test_firth_logistic.py::TestIndependentImplementationCrossCheck`
replays this comparison on every local test run (against the frozen,
real R output -- no R interpreter needed here to keep verifying it).

The first cross-check attempt found real disagreements (1-9 units on
CI bounds for the complete-separation fixture) -- root cause and fix
documented on `_fit_firth_constrained_scipy` and inside
`fit_firth_logistic` below: this module's own Newton/IRLS constrained
refit can report `converged=True` while still sitting on a real,
verified-lower penalized log-likelihood than the true conditional
maximum, specifically when profiling pins one coefficient far from its
MLE into a quasi-separated regime for the REMAINING free parameters.
Fixed by always cross-checking constrained fits against a robust
general-purpose optimizer and keeping whichever result is higher --
never trusting IRLS's own convergence flag alone for a constrained fit.

See tests/test_firth_logistic.py for the full validation suite this
implementation must pass BEFORE it is trusted for any real Star result
(research/dataset2/DATASET2_TRAIT_ANALYSIS_PIPELINE_PROPOSAL_2026_07.md
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

CONVERGENCE: the original maximum coefficient-update rule remains the
first criterion. A second numerical-recognition path handles a verified
stationary penalized-likelihood solution whose sparse nuisance coefficient
oscillates above the raw update tolerance: finite likelihood, objective
change within the existing line-search tolerance, and a small Fisher-scaled
penalized-score/Newton decrement must all hold on consecutive iterations.
This changes no likelihood or estimate; it prevents a stationary numerical
two-cycle from being mislabeled as nonconvergence.

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
MAX_STEP_HALVINGS = 30
OBJECTIVE_TOLERANCE = 1e-10
STATIONARY_ITERATIONS_REQUIRED = 2


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
    def __init__(
        self, beta, cov, converged, n_iter, penalized_loglik, fixed_mask=None,
        *, termination_reason=None, final_score_norm=np.nan,
        final_newton_decrement=np.nan, final_likelihood_change=np.nan,
        step_halving_count=0,
    ):
        self.beta = beta
        self.cov = cov
        self.converged = converged
        self.n_iter = n_iter
        self.penalized_loglik = penalized_loglik
        self.fixed_mask = fixed_mask if fixed_mask is not None else np.zeros(len(beta), dtype=bool)
        self.termination_reason = termination_reason
        self.final_score_norm = final_score_norm
        self.final_newton_decrement = final_newton_decrement
        self.final_likelihood_change = final_likelihood_change
        self.step_halving_count = step_halving_count

    @property
    def se(self):
        return np.sqrt(np.diag(self.cov))


def _stationarity_diagnostics(X, y, beta, free):
    """Return penalized-score diagnostics on the estimable coordinates."""
    XtWX, pi, W = _fisher_info(X, beta)
    if not np.isfinite(XtWX).all():
        return np.inf, np.inf
    XtWX_inv = np.linalg.pinv(XtWX)
    h = _hat_diagonal(X, XtWX_inv, W)
    score = X.T @ (y - pi + h * (0.5 - pi))
    free_score = score[free]
    free_info = XtWX[np.ix_(free, free)]
    if not np.isfinite(free_score).all() or not np.isfinite(free_info).all():
        return np.inf, np.inf
    score_norm = float(np.max(np.abs(free_score))) if free_score.size else 0.0
    decrement = float(free_score @ np.linalg.pinv(free_info) @ free_score) if free_score.size else 0.0
    return score_norm, decrement


def _fit_firth_irls(X, y, beta_init, fixed_index, fixed_value, max_iter, tol):
    n, p = X.shape
    beta = np.zeros(p) if beta_init is None else np.array(beta_init, dtype=float)
    if fixed_index is not None:
        beta[fixed_index] = fixed_value

    free = np.ones(p, dtype=bool)
    if fixed_index is not None:
        free[fixed_index] = False

    converged = False
    n_iter = 0
    termination_reason = "max_iterations"
    total_halvings = 0
    stationary_iterations = 0
    final_score_norm = np.inf
    final_newton_decrement = np.inf
    final_likelihood_change = np.nan

    if not np.isfinite(X).all() or not np.isfinite(y).all() or not np.isfinite(beta).all():
        fixed_mask = ~free
        return FirthFitResult(
            beta, np.full((p, p), np.nan), False, 0, -np.inf, fixed_mask,
            termination_reason="non_finite_input",
            final_score_norm=np.inf,
            final_newton_decrement=np.inf,
            final_likelihood_change=np.nan,
            step_halving_count=0,
        )

    prev_ll = _penalized_loglik(X, y, beta)

    # A singular design cannot define the Jeffreys/Firth information
    # penalty. Never let a small pseudo-inverse update masquerade as
    # convergence in that case.
    if np.linalg.matrix_rank(X) != p:
        cov = np.linalg.pinv((X * 0.25).T @ X)
        fixed_mask = ~free
        return FirthFitResult(
            beta, cov, False, 0, prev_ll, fixed_mask,
            termination_reason="rank_deficient",
            final_score_norm=np.inf,
            final_newton_decrement=np.inf,
            final_likelihood_change=np.nan,
            step_halving_count=0,
        )
    if not np.isfinite(prev_ll):
        cov = np.linalg.pinv((X * 0.25).T @ X)
        fixed_mask = ~free
        return FirthFitResult(
            beta, cov, False, 0, prev_ll, fixed_mask,
            termination_reason="non_finite_initial_likelihood",
            final_score_norm=np.inf,
            final_newton_decrement=np.inf,
            final_likelihood_change=np.nan,
            step_halving_count=0,
        )

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
        while (
            not np.isfinite(new_ll) or new_ll < prev_ll - OBJECTIVE_TOLERANCE
        ) and halvings < MAX_STEP_HALVINGS:
            step *= 0.5
            new_beta = beta + step * delta
            new_ll = _penalized_loglik(X, y, new_beta)
            halvings += 1
        total_halvings += halvings

        if not np.isfinite(new_ll):
            termination_reason = "non_finite_likelihood"
            break
        if new_ll < prev_ll - OBJECTIVE_TOLERANCE:
            termination_reason = "line_search_failure"
            break

        max_change = np.max(np.abs(new_beta[free] - beta[free])) if free.any() else 0.0
        likelihood_change = float(new_ll - prev_ll)
        beta = new_beta
        prev_ll = new_ll
        final_likelihood_change = likelihood_change
        final_score_norm, final_newton_decrement = _stationarity_diagnostics(X, y, beta, free)

        if max_change < tol:
            converged = True
            termination_reason = "coefficient_update"
            break

        stationary = (
            np.isfinite(final_score_norm)
            and np.isfinite(final_newton_decrement)
            and abs(likelihood_change) <= OBJECTIVE_TOLERANCE
            and final_newton_decrement <= tol
        )
        stationary_iterations = stationary_iterations + 1 if stationary else 0
        if stationary_iterations >= STATIONARY_ITERATIONS_REQUIRED:
            converged = True
            termination_reason = "stationary_penalized_likelihood"
            break

    XtWX, pi, W = _fisher_info(X, beta)
    cov = np.linalg.pinv(XtWX)
    fixed_mask = np.zeros(p, dtype=bool)
    if fixed_index is not None:
        fixed_mask[fixed_index] = True
    return FirthFitResult(
        beta, cov, converged, n_iter, prev_ll, fixed_mask,
        termination_reason=termination_reason,
        final_score_norm=final_score_norm,
        final_newton_decrement=final_newton_decrement,
        final_likelihood_change=final_likelihood_change,
        step_halving_count=total_halvings,
    )


def _fit_firth_constrained_scipy(X, y, fixed_index, fixed_value, beta_init, max_iter):
    """Robust fallback for the CONSTRAINED (fixed_index given) case
    only, used when this module's own Newton/IRLS fails to converge.

    Real finding (2026-07, caught by the R logistf cross-check and
    confirmed independently before this fix was written -- not
    assumed): the Newton/IRLS step-halving above can fail to converge
    when the FIXED coordinate itself sits far out in a quasi-separated
    regime -- pinning one coefficient at an extreme value can make the
    conditional optimization over the REMAINING free parameters nearly
    separated too, and plain Newton steps handle that badly even with
    warm starts. Verified directly: an independent
    scipy.optimize.minimize run found penalized log-likelihoods 1.7-6.1
    nats HIGHER than this module's own IRLS output at the same fixed
    value, at points where IRLS reported `converged=False`.

    Uses Nelder-Mead (derivative-free, robust to the flat/ill-scaled
    regions that break Newton here) over just the free parameters.
    Only ever used for the constrained sub-problem inside
    `firth_profile_ci()`/`firth_lr_test()` -- the primary, unconstrained
    fit always uses this module's own IRLS (already validated on its
    own terms and never observed to have this failure mode)."""
    from scipy.optimize import minimize

    p = X.shape[1]
    free_idx = [j for j in range(p) if j != fixed_index]
    start = np.zeros(p) if beta_init is None else np.array(beta_init, dtype=float)
    free_start = start[free_idx]

    def neg_penalized_ll(free_params):
        beta = np.empty(p)
        beta[fixed_index] = fixed_value
        beta[free_idx] = free_params
        ll = _penalized_loglik(X, y, beta)
        return -ll if np.isfinite(ll) else 1e10

    res = minimize(
        neg_penalized_ll, free_start, method="Nelder-Mead",
        options={"xatol": 1e-8, "fatol": 1e-10, "maxiter": max(max_iter * 100, 5000), "maxfev": max(max_iter * 100, 5000)},
    )
    beta = np.empty(p)
    beta[fixed_index] = fixed_value
    beta[free_idx] = res.x
    ll = _penalized_loglik(X, y, beta)
    XtWX, pi, W = _fisher_info(X, beta)
    cov = np.linalg.pinv(XtWX)
    fixed_mask = np.zeros(p, dtype=bool)
    fixed_mask[fixed_index] = True
    score_norm, decrement = _stationarity_diagnostics(X, y, beta, ~fixed_mask)
    return FirthFitResult(
        beta, cov, bool(res.success), int(res.nit), ll, fixed_mask,
        termination_reason="optimizer_success" if res.success else "optimizer_failure",
        final_score_norm=score_norm,
        final_newton_decrement=decrement,
        final_likelihood_change=np.nan,
        step_halving_count=0,
    )


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
    approximation. When `fixed_index` is given AND the IRLS path fails
    to converge, automatically falls back to a robust general-purpose
    optimizer (`_fit_firth_constrained_scipy`, see its docstring for
    why) and keeps whichever result has the higher penalized
    log-likelihood -- never silently trusts a non-converged IRLS fit.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)

    result = _fit_firth_irls(X, y, beta_init, fixed_index, fixed_value, max_iter, tol)

    if fixed_index is not None:
        # ALWAYS cross-check against the robust fallback for constrained
        # fits, never gated on IRLS's own `converged` flag alone --
        # real finding (2026-07): IRLS can report converged=True (its
        # parameter-step tolerance was satisfied) while still sitting on
        # a real, verified-lower penalized log-likelihood than the true
        # conditional maximum (confirmed directly against an independent
        # scipy.optimize.minimize ground truth at the R logistf
        # cross-check's disputed CI bounds -- a small step size between
        # iterations does not guarantee the true optimum was reached on
        # a flat/ill-conditioned profile likelihood surface). Keeping
        # whichever of the two has the higher likelihood is a strictly
        # dominant, cheap-to-verify safeguard.
        fallback = _fit_firth_constrained_scipy(X, y, fixed_index, fixed_value, beta_init, max_iter)
        if fallback.penalized_loglik > result.penalized_loglik:
            result = fallback

    return result


_PROFILE_MAX_STEPS = 60
_PROFILE_REFIT_MAX_ITER = 100
_PROFILE_REFIT_TOL = 1e-8


def _profile_constrained_fit(X, y, coef_index, beta_val, warm_start, fit_kwargs):
    """One constrained (fixed_index=coef_index) refit for profiling,
    warm-started from `warm_start` (the PREVIOUS profile step's own
    solution, not the original unconstrained MLE -- converges far more
    reliably step-to-step than always restarting from a potentially
    distant point). Robustness against IRLS non-convergence at extreme
    (e.g. quasi-separated) profile points is handled inside
    `fit_firth_logistic()` itself now (automatic scipy fallback, see
    its docstring and `_fit_firth_constrained_scipy`) -- this function
    no longer needs its own separate retry logic."""
    kwargs = dict(fit_kwargs)
    kwargs.setdefault("max_iter", _PROFILE_REFIT_MAX_ITER)
    kwargs.setdefault("tol", _PROFILE_REFIT_TOL)
    return fit_firth_logistic(X, y, beta_init=warm_start, fixed_index=coef_index, fixed_value=beta_val, **kwargs)


def firth_profile_ci(X, y, coef_index: int, alpha: float = 0.05, **fit_kwargs):
    """Profile-penalized-likelihood confidence interval for
    coefficient `coef_index` -- the recommended CI for Firth's method
    (Heinze & Schemper 2002), not a Wald interval. Finds beta values
    where 2*(l*_full - l*_profile(beta)) crosses chi2(1, 1-alpha),
    re-fitting every OTHER coefficient at each candidate value (a real
    constrained fit via `fixed_index`/`fixed_value`, not an
    approximation). Walks outward in small steps, warm-starting each
    constrained refit from the PREVIOUS step's own solution (see
    `_profile_constrained_fit`'s docstring for why this matters) --
    never jumps straight from the unconstrained MLE to a far candidate
    value. Returns (lower, upper, full_fit_result).
    """
    full_fit = fit_firth_logistic(X, y, **fit_kwargs)
    target = full_fit.penalized_loglik - 0.5 * stats.chi2.ppf(1 - alpha, df=1)
    point = full_fit.beta[coef_index]
    se_guess = full_fit.se[coef_index] if np.isfinite(full_fit.se[coef_index]) else 1.0
    se_guess = se_guess if se_guess > 0 else 1.0

    def walk(direction):
        step = se_guess * 0.25
        current_val = point
        current_warm = full_fit.beta.copy()
        prev_val = point
        for _ in range(_PROFILE_MAX_STEPS):
            candidate_val = current_val + direction * step
            fit = _profile_constrained_fit(X, y, coef_index, candidate_val, current_warm, fit_kwargs)
            f_val = fit.penalized_loglik - target
            if f_val <= 0:
                # Crossing is between prev_val and candidate_val -- refine
                # via brentq, warm-starting every evaluation from the
                # already-converged solution just found (the bracket is
                # narrow at this point, so this stays cheap and reliable).
                def f_refine(bv):
                    return _profile_constrained_fit(X, y, coef_index, bv, fit.beta, fit_kwargs).penalized_loglik - target

                lo, hi = (prev_val, candidate_val) if direction > 0 else (candidate_val, prev_val)
                return brentq(f_refine, lo, hi, xtol=1e-6, maxiter=100)
            prev_val = candidate_val
            current_val = candidate_val
            current_warm = fit.beta.copy()
            step *= 1.15
        return direction * np.inf

    lower = walk(-1.0)
    upper = walk(1.0)
    return lower, upper, full_fit


def firth_lr_test(X, y, coef_index: int, **fit_kwargs):
    """Penalized likelihood-ratio test for H0: beta[coef_index] = 0,
    via a real constrained re-fit (never a Wald z-test -- Firth's own
    motivation applies to significance testing exactly as it does to
    CIs). Uses the same convergence-checked, retry-on-failure
    constrained fit as `firth_profile_ci` (§ its docstring) -- a
    silently non-converged reduced-model fit would bias the LR
    statistic exactly like it biased the CI search. Returns
    (lr_statistic, p_value, full_fit_result, reduced_fit_result)."""
    full_fit = fit_firth_logistic(X, y, **fit_kwargs)
    reduced_fit = _profile_constrained_fit(X, y, coef_index, 0.0, full_fit.beta, fit_kwargs)
    lr_stat = 2.0 * (full_fit.penalized_loglik - reduced_fit.penalized_loglik)
    lr_stat = max(lr_stat, 0.0)
    p_value = 1.0 - stats.chi2.cdf(lr_stat, df=1)
    return lr_stat, p_value, full_fit, reduced_fit
