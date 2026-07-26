"""Long/flat backtest engine with honest costs and no look-ahead.

Timing model (the part that keeps us honest):

- ``weights[t]`` is the target position decided using data up to and including
  ``closes[t]`` — a strategy may only look backwards.
- That position is HELD over bar t+1: the strategy earns ``weights[t] * r[t+1]``.
- Changing position costs ``cost_rate * |weights[t] - weights[t-1]|``, charged
  when the change happens.

So a signal can never earn the bar that produced it. The unit tests prove this
with a deliberately cheating strategy.
"""

from __future__ import annotations

from . import metrics


class Result:
    def __init__(
        self,
        returns: list[float],
        weights: list[float],
        fees_paid: float,
        label: str = "",
    ):
        self.returns = returns  # per-bar net strategy returns (aligned to bars 1..n-1)
        self.weights = weights
        self.fees_paid = fees_paid  # cumulative cost drag, in return units
        self.label = label
        self.stats = metrics.summarize(returns, weights)

    def equity(self) -> list[float]:
        return metrics.equity_curve(self.returns)


def bar_returns(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]


def run(
    closes: list[float],
    weights: list[float],
    fee_bps: float = 10.0,
    slip_bps: float = 5.0,
    label: str = "",
) -> Result:
    """Backtest target-weight series against a close series.

    ``weights[t]`` ∈ [0, 1], decided at close t. len(weights) == len(closes).
    """
    if len(weights) != len(closes):
        raise ValueError("weights and closes must be the same length")
    n = len(closes)
    if n < 2:
        return Result([], [], 0.0, label)

    cost_rate = (fee_bps + slip_bps) / 10_000.0
    rets = bar_returns(closes)

    out: list[float] = []
    fees = 0.0
    prev_w = 0.0  # start flat
    for t in range(1, n):
        w_held = weights[t - 1]  # decided at close t-1, held over bar t
        trade_cost = cost_rate * abs(w_held - prev_w)
        out.append(w_held * rets[t - 1] - trade_cost)
        fees += trade_cost
        prev_w = w_held
    return Result(out, weights, fees, label)


def buy_and_hold(closes: list[float], fee_bps: float = 10.0, slip_bps: float = 5.0) -> Result:
    return run(closes, [1.0] * len(closes), fee_bps, slip_bps, label="buy&hold")
