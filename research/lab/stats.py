"""Honest statistics for automated search.

Two guards against "we tried 500 things and one worked":

1. Deflated Sharpe Ratio (Bailey & López de Prado, 2014): the probability
   that the observed Sharpe exceeds the Sharpe you'd expect from the BEST of
   N junk strategies. Uses the expected-maximum-of-N-normals threshold and a
   non-normality-adjusted PSR. Want DSR ≥ 0.95.

2. Stationary bootstrap (Politis & Romano, 1994): block-resamples the
   holdout excess-return series under the null of no edge; p-value = how
   often noise looks this good. Blocks preserve autocorrelation that plain
   bootstrap would destroy.

Stdlib only; the normal inverse CDF is done by bisection on erf.
"""

from __future__ import annotations

import math
import random

EULER_GAMMA = 0.5772156649015329


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse normal CDF via bisection — slow, exact enough, no magic constants."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0,1)")
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _moments(returns: list[float]) -> tuple[float, float, float, float]:
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(var)
    if std < 1e-12:
        return mean, std, 0.0, 3.0
    skew = sum((r - mean) ** 3 for r in returns) / (n * std**3)
    kurt = sum((r - mean) ** 4 for r in returns) / (n * std**4)
    return mean, std, skew, kurt


def sharpe_per_bar(returns: list[float]) -> float:
    mean, std, _, _ = _moments(returns)
    return 0.0 if std < 1e-12 else mean / std


def expected_max_sharpe(n_trials: int, sr_var: float) -> float:
    """E[max SR] across n_trials junk strategies whose SR estimates have
    variance sr_var. The bar the winner must clear."""
    if n_trials <= 1 or sr_var <= 0:
        return 0.0
    return math.sqrt(sr_var) * (
        (1 - EULER_GAMMA) * norm_ppf(1 - 1 / n_trials)
        + EULER_GAMMA * norm_ppf(1 - 1 / (n_trials * math.e))
    )


def probabilistic_sharpe(returns: list[float], sr_benchmark: float) -> float:
    """PSR: P(true SR > sr_benchmark), adjusted for skew/kurtosis."""
    t = len(returns)
    if t < 10:
        return 0.0
    _, _, skew, kurt = _moments(returns)
    sr = sharpe_per_bar(returns)
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr**2
    if denom <= 0:
        return 0.0
    z = (sr - sr_benchmark) * math.sqrt(t - 1) / math.sqrt(denom)
    return norm_cdf(z)


def deflated_sharpe(
    returns: list[float], n_trials: int, trial_sharpes: list[float]
) -> dict:
    """DSR = PSR against the expected-best-of-N-junk threshold.

    `trial_sharpes`: per-bar Sharpe of every candidate ever evaluated —
    their cross-sectional variance calibrates how lucky the luckiest junk
    strategy should be.
    """
    if len(trial_sharpes) >= 2:
        m = sum(trial_sharpes) / len(trial_sharpes)
        sr_var = sum((s - m) ** 2 for s in trial_sharpes) / (len(trial_sharpes) - 1)
    else:
        sr_var = 0.0
    sr0 = expected_max_sharpe(max(n_trials, len(trial_sharpes)), sr_var)
    return {
        "sharpe_per_bar": sharpe_per_bar(returns),
        "sr0_threshold": sr0,
        "n_trials": n_trials,
        "dsr": probabilistic_sharpe(returns, sr0),
    }


def stationary_bootstrap_pvalue(
    excess_returns: list[float],
    n_boot: int = 1000,
    mean_block: int = 20,
    seed: int = 42,
) -> float:
    """P(mean excess ≥ observed | no true edge), stationary block bootstrap.

    Demeans the series (imposing H0), then resamples with geometric block
    lengths (expected `mean_block`) preserving short-range dependence.
    """
    t = len(excess_returns)
    if t < 30:
        return 1.0
    observed = sum(excess_returns) / t
    centered = [r - observed for r in excess_returns]
    rng = random.Random(seed)
    p_new = 1.0 / mean_block
    count = 0
    for _ in range(n_boot):
        sample = []
        i = rng.randrange(t)
        while len(sample) < t:
            sample.append(centered[i])
            i = rng.randrange(t) if rng.random() < p_new else (i + 1) % t
        if sum(sample) / t >= observed:
            count += 1
    return count / n_boot
