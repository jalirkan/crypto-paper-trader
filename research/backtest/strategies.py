"""Long/flat baseline strategies → target weight per bar (decided at that close).

Each function returns weights the same length as closes; warm-up bars are 0
(flat). Grids are deliberately small — every extra parameter is an overfitting
opportunity (research rule #4).
"""

from __future__ import annotations


def _sma(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if period <= 0 or len(closes) < period:
        return out
    s = 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= period:
            s -= closes[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def ma_cross(closes: list[float], fast: int, slow: int) -> list[float]:
    """Long while fast SMA > slow SMA."""
    f, s = _sma(closes, fast), _sma(closes, slow)
    return [
        1.0 if f[i] is not None and s[i] is not None and f[i] > s[i] else 0.0
        for i in range(len(closes))
    ]


def tsmom(closes: list[float], lookback: int) -> list[float]:
    """Time-series momentum: long while trailing return over `lookback` is positive."""
    return [
        1.0 if i >= lookback and closes[i] > closes[i - lookback] else 0.0
        for i in range(len(closes))
    ]


def donchian(closes: list[float], entry: int, exit_: int | None = None) -> list[float]:
    """Breakout: enter long on a new `entry`-bar high, exit on a `exit_`-bar low."""
    exit_ = exit_ or max(entry // 2, 5)
    n = len(closes)
    w: list[float] = [0.0] * n
    state = 0.0
    for i in range(n):
        if i >= entry:
            hi = max(closes[i - entry : i])
            lo = min(closes[i - exit_ : i])
            if state == 0.0 and closes[i] > hi:
                state = 1.0
            elif state == 1.0 and closes[i] < lo:
                state = 0.0
        w[i] = state
    return w


# name → (fn, parameter grid). Small grids on purpose.
STRATEGY_SPECS: dict = {
    "ma_cross": {
        "fn": ma_cross,
        "grid": [
            {"fast": 5, "slow": 20},
            {"fast": 10, "slow": 30},
            {"fast": 10, "slow": 50},
            {"fast": 20, "slow": 50},
            {"fast": 20, "slow": 100},
            {"fast": 50, "slow": 200},
        ],
    },
    "tsmom": {
        "fn": tsmom,
        "grid": [
            {"lookback": 30},
            {"lookback": 60},
            {"lookback": 90},
            {"lookback": 180},
        ],
    },
    "donchian": {
        "fn": donchian,
        "grid": [
            {"entry": 20},
            {"entry": 40},
            {"entry": 55},
            {"entry": 80},
        ],
    },
}


def compute_weights(name: str, closes: list[float], params: dict) -> list[float]:
    return STRATEGY_SPECS[name]["fn"](closes, **params)
