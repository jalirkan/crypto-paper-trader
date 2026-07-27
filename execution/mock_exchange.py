"""A deterministic chaos exchange for torturing the OMS in tests.

Failure modes are scripted per-call via `behaviors` (a list consumed in
order; default 'ack'):
  'ack'       normal acknowledgment
  'drop_ack'  the order IS accepted internally, but the response is "lost"
              (raises AckTimeout) — the classic distributed-systems trap
  'reject'    exchange refuses the order
Duplicate trade reports are enabled with duplicate_reports=True.

The exchange's state is intentionally independent of any OMS instance —
"restarting" the OMS while the exchange keeps living is exactly the
crash-recovery scenario reconciliation exists for.
"""

from __future__ import annotations

import itertools

from .exchange import AckTimeout, ExchangeAdapter, ExchangeError
from .types import Fill, now_ms


class MockExchange(ExchangeAdapter):
    def __init__(self, behaviors: list[str] | None = None, duplicate_reports: bool = False):
        self.behaviors = list(behaviors or [])
        self.duplicate_reports = duplicate_reports
        self._seq = itertools.count(1)
        self.orders: dict[str, dict] = {}  # exchange_id → order
        self.by_client: dict[str, str] = {}  # client_id → exchange_id
        self.trades: list[Fill] = []
        self.marks: dict[str, float] = {}

    # ---- test controls ----

    def set_mark(self, symbol: str, px: float) -> None:
        self.marks[symbol] = px

    def fill(self, client_id: str, qty: float, px: float | None = None) -> None:
        """Fill part/all of an order (test hook)."""
        ex_id = self.by_client[client_id]
        o = self.orders[ex_id]
        qty = min(qty, o["qty"] - o["filled_qty"])
        if qty <= 0:
            return
        o["filled_qty"] += qty
        if o["filled_qty"] >= o["qty"] - 1e-12:
            o["state"] = "FILLED"
        trade = Fill(
            trade_id=f"t{next(self._seq)}",
            client_id=client_id,
            qty=qty,
            px=px if px is not None else o["limit_px"],
            ts=now_ms(),
        )
        self.trades.append(trade)

    # ---- adapter protocol ----

    def _next_behavior(self) -> str:
        return self.behaviors.pop(0) if self.behaviors else "ack"

    def place(self, client_id, symbol, side, qty, limit_px) -> str:
        if client_id in self.by_client:  # idempotency contract
            return self.by_client[client_id]
        mode = self._next_behavior()
        if mode == "reject":
            raise ExchangeError("mock: rejected")
        ex_id = f"X{next(self._seq)}"
        self.orders[ex_id] = {
            "exchange_id": ex_id, "client_id": client_id, "symbol": symbol,
            "side": side, "qty": qty, "limit_px": limit_px,
            "filled_qty": 0.0, "state": "OPEN",
        }
        self.by_client[client_id] = ex_id
        if mode == "drop_ack":
            raise AckTimeout("mock: response lost in transit")
        return ex_id

    def cancel(self, exchange_id: str) -> None:
        o = self.orders.get(exchange_id)
        if o and o["state"] in ("OPEN", "PARTIALLY_FILLED"):
            o["state"] = "CANCELED"

    def lookup_by_client_id(self, client_id: str) -> dict | None:
        ex_id = self.by_client.get(client_id)
        if ex_id is None:
            return None
        o = self.orders[ex_id]
        return {"exchange_id": ex_id, "state": o["state"], "filled_qty": o["filled_qty"]}

    def open_orders(self) -> list[dict]:
        return [dict(o) for o in self.orders.values() if o["state"] == "OPEN"]

    def trades_since(self, cursor: str | None) -> tuple[list[Fill], str]:
        start = int(cursor) if cursor else 0
        out = self.trades[start:]
        if self.duplicate_reports and out:
            out = [t for t in out for _ in (0, 1)]  # every trade reported twice
        return out, str(len(self.trades))

    def position(self, symbol: str) -> float:
        pos = 0.0
        for t in self.trades:
            o = self.orders[self.by_client[t.client_id]]
            if o["symbol"] == symbol:
                pos += t.qty if o["side"] == "buy" else -t.qty
        return pos

    def mark_price(self, symbol: str) -> float:
        return self.marks.get(symbol, 100.0)
