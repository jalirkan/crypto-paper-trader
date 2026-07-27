"""Reconciliation — the crash-recovery core.

Runs at startup and periodically. Three duties:

1. **Resolve UNKNOWN / stuck PENDING_NEW orders** by asking the exchange about
   our client_id: adopt what exists (the ack was lost, the order wasn't);
   mark REJECTED only when the exchange confirms it never saw the id.
2. **Ingest any fills we missed** while down (delegated to poll_fills).
3. **Compare journal position vs exchange position.** Beyond tolerance, the
   correct move is to STOP — freeze via kill switch and demand human eyes.
   An OMS that "fixes" drift by trading is an OMS that doubles a bug.
"""

from __future__ import annotations

from .exchange import ExchangeAdapter
from .oms import OrderManager
from .risk import RiskGuard
from .store import Journal
from .types import now_ms

POSITION_TOLERANCE = 1e-6


def reconcile(
    journal: Journal,
    exchange: ExchangeAdapter,
    oms: OrderManager,
    risk: RiskGuard,
    symbols: list[str],
) -> dict:
    report = {"resolved": 0, "adopted_fills": 0, "drift_frozen": False}

    # 1. Resolve limbo orders by asking the source of truth.
    for o in journal.live_orders():
        if o.state not in ("UNKNOWN", "PENDING_NEW"):
            continue
        info = exchange.lookup_by_client_id(o.client_id)
        if info is None:
            o.state = "REJECTED"
            o.reason = "reconcile: exchange never saw this client_id"
        else:
            o.exchange_id = info["exchange_id"]
            o.state = info["state"] if info["state"] in ("FILLED", "CANCELED") else "OPEN"
            o.reason = "reconcile: adopted"
        o.updated_ts = now_ms()
        journal.write_order(o)
        journal.event("RECONCILE_RESOLVE", f"{o.client_id} → {o.state}")
        report["resolved"] += 1

    # 2. Catch up on fills (idempotent; adjusts adopted orders' filled state).
    report["adopted_fills"] = oms.poll_fills()

    # 3. Position truth check — freeze on drift, never trade to fix.
    for symbol in symbols:
        local = journal.position(symbol)
        remote = exchange.position(symbol)
        if abs(local - remote) > POSITION_TOLERANCE:
            risk.kill(
                f"position drift {symbol}: journal {local:.8f} vs exchange {remote:.8f}"
            )
            report["drift_frozen"] = True

    return report
