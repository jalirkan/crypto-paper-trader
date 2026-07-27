"""DSL interpreter — compiles expression trees into weight series.

Timing contract (the no-lookahead invariant):
- Every series op at index t uses data up to and including close[t] only.
- `roll_max`/`roll_min` use the window STRICTLY BEFORE t (bars t-n … t-1), so
  `cross_above(close, roll_max(close, n))` is a true breakout of a prior range.
- The engine (research.backtest.engine) then shifts execution by one bar, so a
  decision at close t earns returns from bar t+1 onward.

Booleans are False wherever an input is NaN (warm-up), so no rule can fire
before its indicators exist.
"""

from __future__ import annotations

import math

NAN = float("nan")


def _isnan(x: float) -> bool:
    return x != x


def _lead_nan_safe(fn):
    """Ops assume clean input; inputs may carry leading warm-up NaNs (nested
    ops). Strip the NaN prefix, apply, pad back — composition just works."""

    def wrapped(xs: list[float], n: int) -> list[float]:
        first = 0
        while first < len(xs) and _isnan(xs[first]):
            first += 1
        if len(xs) - first < 2:
            return [NAN] * len(xs)
        return [NAN] * first + fn(xs[first:], n)

    return wrapped


@_lead_nan_safe
def _sma(xs: list[float], n: int) -> list[float]:
    out = [NAN] * len(xs)
    s = 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


@_lead_nan_safe
def _ema(xs: list[float], n: int) -> list[float]:
    out = [NAN] * len(xs)
    if len(xs) < n:
        return out
    seed = sum(xs[:n]) / n
    out[n - 1] = seed
    k = 2 / (n + 1)
    for i in range(n, len(xs)):
        out[i] = xs[i] * k + out[i - 1] * (1 - k)
    return out


def _roll_impl(xs: list[float], n: int, fn) -> list[float]:
    """fn over xs[t-n : t] — strictly prior window."""
    out = [NAN] * len(xs)
    for i in range(n, len(xs)):
        out[i] = fn(xs[i - n : i])
    return out


def _roll_max(xs: list[float], n: int) -> list[float]:
    return _roll_impl(xs, n, max)


def _roll_min(xs: list[float], n: int) -> list[float]:
    return _roll_impl(xs, n, min)


@_lead_nan_safe
def _vol(xs: list[float], n: int) -> list[float]:
    """Std of simple returns over the prior n returns (annualization-free)."""
    out = [NAN] * len(xs)
    rets = [NAN] + [xs[i] / xs[i - 1] - 1.0 for i in range(1, len(xs))]
    for i in range(n + 1, len(xs)):
        window = rets[i - n + 1 : i + 1]
        m = sum(window) / n
        out[i] = math.sqrt(sum((r - m) ** 2 for r in window) / (n - 1))
    return out


@_lead_nan_safe
def _ret(xs: list[float], n: int) -> list[float]:
    return [
        xs[i] / xs[i - n] - 1.0 if i >= n and xs[i - n] > 0 else NAN
        for i in range(len(xs))
    ]


@_lead_nan_safe
def _rsi(xs: list[float], n: int) -> list[float]:
    out = [NAN] * len(xs)
    if len(xs) <= n:
        return out
    gain = loss = 0.0
    for i in range(1, n + 1):
        d = xs[i] - xs[i - 1]
        gain += max(d, 0)
        loss += max(-d, 0)
    gain /= n
    loss /= n
    out[n] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    for i in range(n + 1, len(xs)):
        d = xs[i] - xs[i - 1]
        gain = (gain * (n - 1) + max(d, 0)) / n
        loss = (loss * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def eval_series(node: dict, closes: list[float]) -> list[float]:
    op = node["op"]
    if op == "close":
        return list(closes)
    if op == "const":
        return [float(node["v"])] * len(closes)
    base = eval_series(node.get("of", {"op": "close"}), closes)
    n = node["n"]
    if op == "sma":
        return _sma(base, n)
    if op == "ema":
        return _ema(base, n)
    if op == "roll_max":
        return _roll_max(base, n)
    if op == "roll_min":
        return _roll_min(base, n)
    if op == "vol":
        return _vol(base, n)
    if op == "ret":
        return _ret(base, n)
    if op == "rsi":
        return _rsi(base, n)
    raise ValueError(f"unknown series op {op}")


def eval_bool(node: dict, closes: list[float]) -> list[bool]:
    op = node["op"]
    if op in ("gt", "lt"):
        a, b = eval_series(node["a"], closes), eval_series(node["b"], closes)
        if op == "gt":
            return [not _isnan(x) and not _isnan(y) and x > y for x, y in zip(a, b)]
        return [not _isnan(x) and not _isnan(y) and x < y for x, y in zip(a, b)]
    if op in ("cross_above", "cross_below"):
        a, b = eval_series(node["a"], closes), eval_series(node["b"], closes)
        out = [False] * len(a)
        for i in range(1, len(a)):
            if any(_isnan(v) for v in (a[i], b[i], a[i - 1], b[i - 1])):
                continue
            if op == "cross_above":
                out[i] = a[i - 1] <= b[i - 1] and a[i] > b[i]
            else:
                out[i] = a[i - 1] >= b[i - 1] and a[i] < b[i]
        return out
    if op == "not":
        return [not v for v in eval_bool(node["a"], closes)]
    if op in ("and", "or"):
        a, b = eval_bool(node["a"], closes), eval_bool(node["b"], closes)
        return [x and y for x, y in zip(a, b)] if op == "and" else [x or y for x, y in zip(a, b)]
    raise ValueError(f"unknown bool op {op}")


def weights(candidate: dict, closes: list[float]) -> list[float]:
    """Entry/exit state machine → long/flat weight per bar (decided at close)."""
    entry = eval_bool(candidate["entry"], closes)
    exit_ = eval_bool(candidate["exit"], closes)
    out = [0.0] * len(closes)
    state = 0.0
    for t in range(len(closes)):
        if state == 0.0 and entry[t]:
            state = 1.0
        elif state == 1.0 and exit_[t]:
            state = 0.0
        out[t] = state
    return out
