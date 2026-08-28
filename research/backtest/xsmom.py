"""Cross-sectional momentum (EXP-007) — rank the universe, hold the top N.

Every strategy tested in this repo so far has been TIME-SERIES: is *this*
asset trending? Cross-sectional momentum asks a different question — which
assets are trending *most* — and the answer is a portfolio of several coins
rather than a long/flat switch on one. The single-asset engine cannot express
that, so this module adds the portfolio layer and nothing else. It does not
re-implement the backtest: the timing and cost contract is `engine`'s,
unchanged.

- ``weights[s][t]`` is decided at close t from data ≤ t, and is held over
  bar t+1. A signal can never earn the bar that produced it.
- Changing position costs ``cost_rate * |Δweight|``, charged on the bar the
  new position is first held.

`tests/test_xsmom.py` pins that to the audited engine rather than to this
docstring: a one-asset universe run through `simulate` must reproduce
``engine.run`` on the equivalent weight series, bar for bar.

Between rebalances the position is left alone — weights drift with prices and
nothing is charged, because nothing is traded. Cost is charged only at a
rebalance, on the distance from the drifted weights to the new targets. The
alternative (constant weights between rebalances) would quietly assume free
daily re-equalisation, and every unmodelled cost in this repo is one that
flatters the strategy.

Parameters are fixed a priori and there is no grid, per the overlay discipline
of EXP-002/003/004. The configuration, the kill bar and the four guards are
EXP-007 in research/experiments.md, committed before this file existed.
"""

from __future__ import annotations

from . import engine, metrics

# Pre-registered configuration (EXP-007). Not a grid, not defaults to tune.
LOOKBACK = 90
TOP_N = 3
REBALANCE = 30
FEE_BPS = 10.0
SLIP_BPS = 5.0


def momentum(closes: list[float], t: int, lookback: int) -> float:
    """Trailing `lookback`-bar return at close t. Uses data ≤ t only."""
    if lookback <= 0:
        return 0.0
    return closes[t] / closes[t - lookback] - 1.0


def _drift(weights: dict[str, float], bar_returns: dict[str, float]) -> dict[str, float]:
    """Carry weights through one bar without trading.

    The holdings grow at their own returns and the fractions re-normalise to
    the new portfolio value. A flat book stays flat.
    """
    invested = sum(weights.values())
    if invested <= 1e-12:
        return dict(weights)
    grown = {s: w * (1.0 + bar_returns[s]) for s, w in weights.items()}
    total = sum(grown.values())
    if total <= 0:
        return {s: 0.0 for s in weights}
    return {s: g * invested / total for s, g in grown.items()}


def target_weights(
    closes_map: dict[str, list[float]],
    lookback: int = LOOKBACK,
    top_n: int = TOP_N,
    rebalance_every: int = REBALANCE,
) -> tuple[dict[str, list[float]], list[float]]:
    """Weight series per symbol, plus the weight traded by each decision.

    ``traded[t]`` is the sum of |target − drifted| at close t: zero on every
    bar that is not a rebalance, and zero on a rebalance that happens to
    reselect the same names at the same weights. Returning it here — rather
    than reconstructing the pre-trade book later — keeps one drift calculation
    in the codebase, so the cost can never be charged against a position the
    weights never held.

    Rebalance bars are ``lookback, lookback + rebalance_every, …`` — a fixed
    calendar, so the schedule cannot drift toward favourable dates. Ties in the
    ranking break on symbol name: arbitrary, but deterministic.
    """
    symbols = sorted(closes_map)
    n = len(closes_map[symbols[0]])
    if any(len(closes_map[s]) != n for s in symbols):
        raise ValueError("all symbols must be aligned to one common bar count")
    if top_n < 1 or top_n > len(symbols):
        raise ValueError(f"top_n must be in 1..{len(symbols)}")

    weights: dict[str, list[float]] = {s: [0.0] * n for s in symbols}
    traded: list[float] = [0.0] * n
    current = {s: 0.0 for s in symbols}

    for t in range(n):
        if t > 0:
            current = _drift(
                current, {s: closes_map[s][t] / closes_map[s][t - 1] - 1.0 for s in symbols}
            )
        if t >= lookback and (t - lookback) % rebalance_every == 0:
            scores = {s: momentum(closes_map[s], t, lookback) for s in symbols}
            chosen = sorted(symbols, key=lambda s: (-scores[s], s))[:top_n]
            target = {s: (1.0 / top_n if s in chosen else 0.0) for s in symbols}
            traded[t] = sum(abs(target[s] - current[s]) for s in symbols)
            current = target
        for s in symbols:
            weights[s][t] = current[s]

    return weights, traded


def portfolio_returns(
    closes_map: dict[str, list[float]],
    weights: dict[str, list[float]],
    traded: list[float],
    fee_bps: float = FEE_BPS,
    slip_bps: float = SLIP_BPS,
) -> list[float]:
    """Net per-bar portfolio returns, aligned to bars 1..n-1 like `engine.run`.

    The decision made at close t-1 is held over bar t and pays for itself on
    that same bar — the engine's rule, applied to a basket instead of one
    switch.
    """
    symbols = sorted(closes_map)
    n = len(closes_map[symbols[0]])
    cost_rate = (fee_bps + slip_bps) / 10_000.0
    rets = {s: engine.bar_returns(closes_map[s]) for s in symbols}

    out: list[float] = []
    for t in range(1, n):
        d = t - 1  # the decision held over bar t was made at close t-1
        gross = sum(weights[s][d] * rets[s][d] for s in symbols)
        out.append(gross - cost_rate * traded[d])
    return out


def simulate(
    closes_map: dict[str, list[float]],
    lookback: int = LOOKBACK,
    top_n: int = TOP_N,
    rebalance_every: int = REBALANCE,
    fee_bps: float = FEE_BPS,
    slip_bps: float = SLIP_BPS,
) -> dict:
    """Run the sleeve. Returns net per-bar returns, weights and summary stats.

    `stats` carries the usual summary plus honest turnover: `metrics.summarize`
    counts a "trade" as a change in total exposure, which for a basket that is
    always fully invested would report one trade for the whole history. The
    rebalance count and traded weight are the real figures and they replace it.
    """
    weights, traded = target_weights(closes_map, lookback, top_n, rebalance_every)
    returns = portfolio_returns(closes_map, weights, traded, fee_bps, slip_bps)
    symbols = sorted(closes_map)
    invested = [sum(weights[s][t] for s in symbols) for t in range(len(traded))]
    stats = metrics.summarize(returns, invested)
    rebalances = sum(1 for x in traded if x > 1e-12)
    stats["trades"] = rebalances
    stats["turnover_yr"] = (
        sum(traded) * metrics.PERIODS_PER_YEAR / max(len(traded), 1)
    )
    return {
        "returns": returns,
        "weights": weights,
        "traded": traded,
        "rebalances": rebalances,
        "stats": stats,
        "holdings": [
            [s for s in symbols if weights[s][t] > 0.0] for t in range(len(traded))
        ],
    }


def equal_weight_basket(
    closes_map: dict[str, list[float]],
    fee_bps: float = FEE_BPS,
    slip_bps: float = SLIP_BPS,
) -> dict:
    """Buy and hold the whole universe, equal-weight, never rebalanced.

    Guard G4's benchmark: cross-sectional momentum claims that *ranking* adds
    value, so the thing it has to beat is holding everything. Expressed through
    `simulate` with no lookback and a single rebalance, rather than as a second
    portfolio implementation that could drift out of step with this one.
    """
    n = len(next(iter(closes_map.values())))
    return simulate(
        closes_map,
        lookback=0,
        top_n=len(closes_map),
        rebalance_every=n + 1,
        fee_bps=fee_bps,
        slip_bps=slip_bps,
    )


def neighbours(
    lookback: int = LOOKBACK, top_n: int = TOP_N, rebalance_every: int = REBALANCE
) -> list[dict]:
    """The six one-at-a-time ±25% parameter neighbours (guard G3).

    Same wiggle the lab applies to its DSL candidates. A robustness probe, not
    a grid: the pre-registration forbids selecting from it.
    """
    base = {"lookback": lookback, "top_n": top_n, "rebalance_every": rebalance_every}
    out: list[dict] = []
    for key in ("lookback", "top_n", "rebalance_every"):
        for factor in (0.75, 1.25):
            # Half-up, not banker's: round(112.5) is 112 in Python, and the
            # pre-registration names 113. The neighbours are part of the bar.
            n = max(1, int(base[key] * factor + 0.5))
            if n == base[key]:
                continue
            out.append({**base, key: n})
    return out
