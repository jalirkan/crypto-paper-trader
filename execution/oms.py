"""The order manager — write-ahead placement, fill ingestion, stale cleanup."""

from __future__ import annotations

from .exchange import AckTimeout, ExchangeAdapter, ExchangeError
from .risk import RiskGuard
from .store import Journal
from .types import Order, OrderIntent, now_ms


class OrderManager:
    def __init__(self, journal: Journal, exchange: ExchangeAdapter, risk: RiskGuard):
        self.j = journal
        self.x = exchange
        self.risk = risk

    def place(self, intent: OrderIntent) -> Order:
        """Risk-check → journal (write-ahead) → exchange → record outcome.

        Idempotent: if this intent's client_id already exists in the journal,
        the existing order is returned untouched — a retried cycle can never
        double-place."""
        existing = self.j.get_order(intent.client_id)
        if existing is not None:
            return existing

        mark = self.x.mark_price(intent.symbol)
        reason = self.risk.check(intent, mark, self.j.position(intent.symbol))
        order = Order(
            client_id=intent.client_id, symbol=intent.symbol, side=intent.side,
            qty=intent.qty, limit_px=intent.limit_px,
        )
        if reason is not None:
            order.state = "REJECTED"
            order.reason = f"risk: {reason}"
            self.j.write_order(order)
            self.j.event("RISK_REJECT", f"{intent.client_id} {reason}")
            return order

        self.j.write_order(order)  # PENDING_NEW hits disk before the wire

        try:
            exchange_id = self.x.place(
                intent.client_id, intent.symbol, intent.side, intent.qty, intent.limit_px
            )
            order.exchange_id = exchange_id
            order.state = "OPEN"
        except AckTimeout as e:
            order.state = "UNKNOWN"  # NOT rejected — reconciliation will resolve
            order.reason = str(e)
            self.j.event("ACK_LOST", intent.client_id)
        except ExchangeError as e:
            order.state = "REJECTED"
            order.reason = str(e)
        order.updated_ts = now_ms()
        self.j.write_order(order)
        return order

    def poll_fills(self) -> int:
        """Ingest new trades from the exchange; duplicates no-op. Returns new count."""
        cursor = self.j.get_meta("trade_cursor")
        fills, new_cursor = self.x.trades_since(cursor)
        applied = 0
        for f in fills:
            if self.j.apply_fill(f):
                applied += 1
        self.j.set_meta("trade_cursor", new_cursor)
        return applied

    def cancel_stale(self, ttl_ms: int = 15 * 60_000, now: int | None = None) -> int:
        """Cancel resting orders older than ttl (limit never hit → give up)."""
        now = now or now_ms()
        n = 0
        for o in self.j.live_orders():
            if o.state in ("OPEN", "PARTIALLY_FILLED") and now - o.created_ts > ttl_ms:
                try:
                    if o.exchange_id:
                        self.x.cancel(o.exchange_id)
                    o.state = "CANCELED"
                    o.reason = "stale ttl"
                    o.updated_ts = now
                    self.j.write_order(o)
                    self.j.event("STALE_CANCEL", o.client_id)
                    n += 1
                except ExchangeError:
                    pass  # reconcile will sort it out next pass
        return n
