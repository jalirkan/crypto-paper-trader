"""Position targeting: turn a desired weight into the minimal safe order.

Accounts for what's already working (live orders) so repeated cycles never
stack duplicate exposure — the delta is measured against position PLUS the
signed remainder of live orders.
"""

from __future__ import annotations

from .store import Journal
from .types import OrderIntent


class TargetConfig:
    def __init__(
        self,
        min_notional: float = 5.0,
        lot_step: float = 1e-5,
        tolerance_pct: float = 0.02,
        slippage_cap_pct: float = 0.01,
    ):
        self.min_notional = min_notional
        self.lot_step = lot_step
        self.tolerance_pct = tolerance_pct  # ignore drifts smaller than this × equity
        self.slippage_cap_pct = slippage_cap_pct  # protective limit distance


def round_lot(qty: float, step: float) -> float:
    return int(qty / step + 1e-9) * step


def compute_intent(
    journal: Journal,
    symbol: str,
    target_weight: float,
    equity: float,
    mark: float,
    intent_key: str,
    cfg: TargetConfig | None = None,
) -> OrderIntent | None:
    """One minimal order toward target, or None if already close enough."""
    cfg = cfg or TargetConfig()
    if mark <= 0 or equity <= 0:
        return None

    position = journal.position(symbol)
    working = sum(
        (o.remaining if o.side == "buy" else -o.remaining)
        for o in journal.live_orders(symbol)
        if o.state != "UNKNOWN"  # unknowns are frozen exposure until reconciled
    )
    effective = position + working

    target_qty = (equity * max(0.0, min(1.0, target_weight))) / mark
    delta = target_qty - effective

    if abs(delta * mark) < max(cfg.min_notional, cfg.tolerance_pct * equity):
        return None

    side = "buy" if delta > 0 else "sell"
    qty = round_lot(abs(delta), cfg.lot_step)
    if qty * mark < cfg.min_notional:
        return None
    if side == "sell":
        qty = min(qty, max(0.0, position))  # long-only book: never sell short
        if qty * mark < cfg.min_notional:
            return None

    cap = cfg.slippage_cap_pct
    limit_px = mark * (1 + cap) if side == "buy" else mark * (1 - cap)
    return OrderIntent(
        symbol=symbol, side=side, qty=qty, limit_px=round(limit_px, 2),
        intent_key=intent_key,
    )
