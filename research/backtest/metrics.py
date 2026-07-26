"""Performance metrics. Daily bars, 365-day crypto year. Stdlib only."""

from __future__ import annotations

import math

PERIODS_PER_YEAR = 365


def equity_curve(returns: list[float]) -> list[float]:
    eq = [1.0]
    for r in returns:
        eq.append(eq[-1] * (1.0 + r))
    return eq


def cagr(returns: list[float]) -> float:
    if not returns:
        return 0.0
    total = 1.0
    for r in returns:
        total *= 1.0 + r
    if total <= 0:
        return -1.0
    years = len(returns) / PERIODS_PER_YEAR
    return total ** (1 / years) - 1 if years > 0 else 0.0


def max_drawdown(returns: list[float]) -> float:
    """Most negative peak-to-trough move, as a negative fraction."""
    peak = 1.0
    equity = 1.0
    worst = 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def sharpe(returns: list[float]) -> float:
    s = _std(returns)
    if s == 0:
        return 0.0
    return _mean(returns) / s * math.sqrt(PERIODS_PER_YEAR)


def sortino(returns: list[float]) -> float:
    if not returns:
        return 0.0
    downside = math.sqrt(_mean([min(r, 0.0) ** 2 for r in returns]))
    if downside == 0:
        return 0.0
    return _mean(returns) / downside * math.sqrt(PERIODS_PER_YEAR)


def summarize(returns: list[float], weights: list[float] | None = None) -> dict:
    out = {
        "days": len(returns),
        "total_return": math.prod(1 + r for r in returns) - 1 if returns else 0.0,
        "cagr": cagr(returns),
        "sharpe": sharpe(returns),
        "sortino": sortino(returns),
        "max_dd": max_drawdown(returns),
    }
    if weights is not None and weights:
        deltas = [abs(weights[i] - (weights[i - 1] if i else 0.0)) for i in range(len(weights))]
        out["exposure"] = _mean(weights)
        out["trades"] = sum(1 for d in deltas if d > 1e-12)
        out["turnover_yr"] = sum(deltas) * PERIODS_PER_YEAR / max(len(weights), 1)
    return out
