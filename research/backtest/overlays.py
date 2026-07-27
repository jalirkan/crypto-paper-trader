"""Risk overlays — fixed-parameter weight transforms layered on a base strategy.

Design rules (overfitting defense):
- Overlays have NO tunable grid. Parameters are fixed a priori and documented.
  If it only works after tuning, it doesn't work.
- An overlay may only shrink or keep exposure (never leverage up), so any OOS
  improvement must come from risk timing, not added risk.
- Transforms see data up to and including bar t when setting weight t —
  same no-look-ahead contract as strategies (engine shifts execution anyway).

Kill criteria (written before running, see experiments.md):
KEEP an overlay only if, walk-forward OOS on ≥2 of 3 symbols, it improves
max drawdown while keeping Sharpe within 0.05 of plain Donchian (or better).
"""

from __future__ import annotations

import math

ANNUALIZE = math.sqrt(365)


def vol_target(
    closes: list[float],
    weights: list[float],
    target_ann_vol: float = 0.40,
    lookback: int = 30,
) -> list[float]:
    """Scale weight down when trailing realized vol exceeds the target.

    scale_t = min(1, target / realized_vol_t), realized over `lookback` bars
    of returns ending at t. Fixed: 40% annual target, 30-bar window.
    """
    n = len(closes)
    out = list(weights)
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, n)]
    for t in range(n):
        if t < lookback + 1 or out[t] == 0.0:
            continue
        window = rets[t - lookback : t]  # returns up to and including bar t
        mean = sum(window) / len(window)
        var = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
        ann = math.sqrt(var) * ANNUALIZE
        if ann > 1e-9:
            out[t] = out[t] * min(1.0, target_ann_vol / ann)
    return out


def series_gate(
    weights: list[float],
    gate: list[float | None],
    scale_when_off: float = 0.5,
) -> list[float]:
    """Generic gate: multiply weight by `scale_when_off` where gate[t] is 0.
    gate[t]: 1.0 = risk-on, 0.0 = risk-off, None = no data → leave unchanged.
    """
    return [
        w if g is None or g >= 1.0 else w * scale_when_off
        for w, g in zip(weights, gate)
    ]


def fng_gate_series(fng_by_day: dict[str, int], days: list[str]) -> list[float | None]:
    """Risk-off when Fear & Greed shows extreme greed (≥ 80) — crowding proxy.

    Fixed threshold 80 ('Extreme Greed' band). Uses the PREVIOUS day's print
    to be safe about publication timing.
    """
    out: list[float | None] = []
    prev: int | None = None
    for day in days:
        val = prev  # yesterday's reading gates today's weight
        prev = fng_by_day.get(day, prev)
        out.append(None if val is None else (0.0 if val >= 80 else 1.0))
    return out


def stable_gate_series(
    mcap_by_day: dict[str, float], days: list[str], lookback_days: int = 30
) -> list[float | None]:
    """Risk-off when total stablecoin supply is shrinking over 30d — liquidity
    draining out of the crypto system. Fixed 30-day lookback, previous-day data.
    """
    out: list[float | None] = []
    history: list[float | None] = []
    prev: float | None = None
    for day in days:
        history.append(prev)  # value known as of yesterday
        prev = mcap_by_day.get(day, prev)
        idx = len(history) - 1
        past = history[idx - lookback_days] if idx >= lookback_days else None
        now = history[idx]
        if now is None or past is None or past <= 0:
            out.append(None)
        else:
            out.append(1.0 if now >= past else 0.0)
    return out
