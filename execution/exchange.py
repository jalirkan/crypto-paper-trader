"""Exchange adapter protocol. The OMS speaks only this interface.

A real adapter (Kraken: client ids map to `cl_ord_id`/userref) gets written
only when the live gate opens. Everything here is exercised by MockExchange.
"""

from __future__ import annotations

from .types import Fill


class ExchangeError(Exception):
    """Exchange said no (reject, validation, insufficient funds…)."""


class AckTimeout(Exception):
    """We don't know what happened. The order may or may not exist.
    Callers must treat this as UNKNOWN — never as a failure."""


class ExchangeAdapter:
    """Duck-typed protocol; MockExchange and future real adapters implement it."""

    def place(self, client_id: str, symbol: str, side: str, qty: float, limit_px: float) -> str:
        """Place an order. Returns exchange_id. MUST be idempotent on client_id:
        re-placing a known client_id returns the existing exchange_id."""
        raise NotImplementedError

    def cancel(self, exchange_id: str) -> None:
        raise NotImplementedError

    def lookup_by_client_id(self, client_id: str) -> dict | None:
        """{exchange_id, state, filled_qty} or None if truly never seen."""
        raise NotImplementedError

    def open_orders(self) -> list[dict]:
        raise NotImplementedError

    def trades_since(self, cursor: str | None) -> tuple[list[Fill], str]:
        """(fills, new_cursor). May deliver duplicates; consumers must dedupe."""
        raise NotImplementedError

    def position(self, symbol: str) -> float:
        """Exchange-side signed position/balance for reconciliation."""
        raise NotImplementedError

    def mark_price(self, symbol: str) -> float:
        raise NotImplementedError
