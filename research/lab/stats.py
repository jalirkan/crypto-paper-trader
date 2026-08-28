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

3. Paired stationary bootstrap on a Sharpe DIFFERENCE: the same block indices
   are applied to a strategy and its benchmark, so the pairing that defines
   the difference survives resampling. Reports an interval rather than a
   p-value, because EXP-006 is what happens when a point estimate near a
   decision threshold is quoted without one.

Stdlib only; the normal inverse CDF is done by bisection on erf.
"""

from __future__ import annotations

import math
import random

from ..backtest import metrics

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


def block_indices(t: int, mean_block: int, rng: random.Random) -> list[int]:
    """One stationary-bootstrap resample of the positions 0..t-1.

    Geometric block lengths (expected `mean_block`), wrapping at the end.
    Returning INDICES rather than values is what makes a paired resample
    possible: two series resampled with the same indices stay aligned.
    """
    idx: list[int] = []
    p_new = 1.0 / mean_block
    i = rng.randrange(t)
    while len(idx) < t:
        idx.append(i)
        i = rng.randrange(t) if rng.random() < p_new else (i + 1) % t
    return idx


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
    count = 0
    for _ in range(n_boot):
        sample = [centered[i] for i in block_indices(t, mean_block, rng)]
        if sum(sample) / t >= observed:
            count += 1
    return count / n_boot


def sharpe_diff_ci(
    strategy: list[float],
    benchmark: list[float],
    n_boot: int = 2000,
    mean_block: int = 20,
    seed: int = 42,
) -> dict:
    """95% CI on the ANNUALIZED Sharpe difference, paired block bootstrap.

    `strategy` and `benchmark` must be per-bar net returns over the SAME bars.
    Each resample draws one set of block indices and applies it to both series,
    so every draw compares the two over the same (resampled) history — which is
    the only way the interval is about the difference rather than about two
    independently jittered curves.

    Returns the observed difference and the 2.5/97.5 percentiles of its
    bootstrap distribution. Deciding against this interval instead of against
    `diff` alone is the rule EXP-006 paid for.
    """
    if len(strategy) != len(benchmark):
        raise ValueError("paired bootstrap needs series over the same bars")
    t = len(strategy)
    observed = metrics.sharpe(strategy) - metrics.sharpe(benchmark)
    if t < 30:
        return {"diff": observed, "lo": float("nan"), "hi": float("nan"), "n_boot": 0}
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(n_boot):
        idx = block_indices(t, mean_block, rng)
        draws.append(
            metrics.sharpe([strategy[i] for i in idx])
            - metrics.sharpe([benchmark[i] for i in idx])
        )
    draws.sort()
    k = max(1, int(0.025 * n_boot))
    return {"diff": observed, "lo": draws[k], "hi": draws[-k], "n_boot": n_boot}


def interval_verdict(lo: float, hi: float, bar: float = 0.0) -> str:
    """Three outcomes, read off the interval rather than the point estimate.

    The project's uncertainty rule in one function: an interval that straddles
    the bar is INCONCLUSIVE, and INCONCLUSIVE is not a soft pass.
    """
    if lo != lo or hi != hi:  # NaN — not enough data to form an interval
        return "INCONCLUSIVE"
    if lo > bar:
        return "KEEP"
    if hi < bar:
        return "KILL"
    return "INCONCLUSIVE"
