"""Core order/fill types and the order state machine."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

# Order lifecycle:
#   PENDING_NEW → OPEN → PARTIALLY_FILLED → FILLED
#        │          │           │
#        │          └──────► CANCELED
#        ├──► REJECTED   (exchange said no — or confirmed it never saw us)
#        └──► UNKNOWN    (ack lost; only reconciliation may resolve this)
STATES = {
    "PENDING_NEW",
    "OPEN",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELED",
    "REJECTED",
    "UNKNOWN",
}
TERMINAL = {"FILLED", "CANCELED", "REJECTED"}
LIVE = {"PENDING_NEW", "OPEN", "PARTIALLY_FILLED", "UNKNOWN"}


def now_ms() -> int:
    return int(time.time() * 1000)


def make_client_id(intent_key: str) -> str:
    """Deterministic, idempotent client order id from an intent key.

    The same intent (e.g. 'rebalance:BTC:2026-07-27T00:target=0.42') always
    maps to the same id — a retried placement can never create a duplicate.
    """
    return "cpt-" + hashlib.sha256(intent_key.encode()).hexdigest()[:20]


@dataclass
class OrderIntent:
    symbol: str
    side: str  # "buy" | "sell"
    qty: float
    limit_px: float  # protective limit — worst acceptable price
    intent_key: str  # uniqueness scope for idempotency

    @property
    def client_id(self) -> str:
        return make_client_id(self.intent_key)

    @property
    def notional(self) -> float:
        return self.qty * self.limit_px


@dataclass
class Order:
    client_id: str
    symbol: str
    side: str
    qty: float
    limit_px: float
    state: str = "PENDING_NEW"
    exchange_id: str | None = None
    filled_qty: float = 0.0
    avg_px: float = 0.0
    reason: str = ""
    created_ts: int = field(default_factory=now_ms)
    updated_ts: int = field(default_factory=now_ms)

    @property
    def remaining(self) -> float:
        return max(0.0, self.qty - self.filled_qty)

    def signed_filled(self) -> float:
        return self.filled_qty if self.side == "buy" else -self.filled_qty


@dataclass
class Fill:
    trade_id: str  # exchange-assigned, globally unique → dedupe key
    client_id: str
    qty: float
    px: float
    ts: int
