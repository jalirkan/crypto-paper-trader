"""Walk-forward validation: choose params on a trailing train window, apply
them to the next unseen test window, roll forward, stitch the test segments.

The stitched out-of-sample curve is the only number we quote (research rule #3).
"""

from __future__ import annotations

from . import engine, metrics
from .strategies import STRATEGY_SPECS, compute_weights


def walk_forward(
    closes: list[float],
    strategy: str,
    train_bars: int = 365,
    test_bars: int = 90,
    fee_bps: float = 10.0,
    slip_bps: float = 5.0,
) -> dict:
    """Returns stitched OOS stats plus the per-window parameter choices."""
    n = len(closes)
    grid = STRATEGY_SPECS[strategy]["grid"]

    # Precompute full weight series per param set — weights at t only use data
    # ≤ t, so slicing windows out of the full series is both correct and fast.
    all_weights = {i: compute_weights(strategy, closes, p) for i, p in enumerate(grid)}

    oos_returns: list[float] = []
    oos_weights: list[float] = []
    windows: list[dict] = []

    start = train_bars
    while start + 1 < n:
        end = min(start + test_bars, n)

        # Select params on the train window [start-train_bars, start).
        best_i, best_score = 0, float("-inf")
        for i in range(len(grid)):
            w = all_weights[i][start - train_bars : start]
            c = closes[start - train_bars : start]
            res = engine.run(c, w, fee_bps, slip_bps)
            score = res.stats["sharpe"]
            if score > best_score:
                best_i, best_score = i, score

        # Apply to the test window. Include one leading bar so the position
        # decided at the last train close is held over the first test bar.
        w_test = all_weights[best_i][start - 1 : end]
        c_test = closes[start - 1 : end]
        res = engine.run(c_test, w_test, fee_bps, slip_bps)
        oos_returns.extend(res.returns)
        oos_weights.extend(w_test[1:])
        windows.append(
            {"train_end_idx": start, "params": grid[best_i], "train_sharpe": best_score}
        )
        start = end

    bh_returns = engine.bar_returns(closes[train_bars - 1 :])[: len(oos_returns)]
    return {
        "strategy": strategy,
        "oos": metrics.summarize(oos_returns, oos_weights),
        "benchmark_oos": metrics.summarize(bh_returns),
        "windows": windows,
        "oos_returns": oos_returns,
    }
