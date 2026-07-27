"""Execution loop: signal service → risk → targeter → OMS → reconcile.

    python -m execution.runner --mock            # full loop against MockExchange
    python -m execution.runner --mock --cycles 20

There is deliberately NO real-exchange mode in this file. Per the research
plan, a live adapter arrives only after a sleeve survives ≥3 months of
forward paper — and flipping it on will be a human's explicit, documented
action, not a flag that already exists waiting to be typo'd.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request

from .mock_exchange import MockExchange
from .oms import OrderManager
from .reconcile import reconcile
from .risk import RiskConfig, RiskGuard
from .store import Journal
from .target import TargetConfig, compute_intent

SIGNALS_URL = "http://127.0.0.1:8091"
SYMBOL = "BTC"


def fetch_target_weight() -> float | None:
    try:
        with urllib.request.urlopen(f"{SIGNALS_URL}/api/signals", timeout=5) as res:
            data = json.loads(res.read().decode())
        for s in data.get("signals", []):
            if s["symbol"] == SYMBOL:
                return 1.0 if s["position"] == "LONG" else 0.0
    except Exception:  # noqa: BLE001
        return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", required=True,
                    help="the only mode that exists (see module docstring)")
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--equity", type=float, default=200.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    journal = Journal(":memory:")
    exchange = MockExchange()
    risk = RiskGuard(journal, RiskConfig())
    oms = OrderManager(journal, exchange, risk)
    tcfg = TargetConfig()

    mark = 100.0
    exchange.set_mark(SYMBOL, mark)
    print(f"mock loop: {args.cycles} cycles, equity {args.equity:.0f}")

    for cycle in range(args.cycles):
        mark *= 1 + rng.gauss(0, 0.01)
        exchange.set_mark(SYMBOL, mark)

        weight = fetch_target_weight()
        if weight is None:  # signal service not running → demo square wave
            weight = 1.0 if (cycle // 3) % 2 == 0 else 0.0

        risk.check_daily_loss(args.equity)
        intent = compute_intent(
            journal, SYMBOL, weight, args.equity, mark,
            intent_key=f"mock:{SYMBOL}:c{cycle}:w{weight}", cfg=tcfg,
        )
        if intent:
            order = oms.place(intent)
            print(f"c{cycle:02d} mark {mark:7.2f} w={weight:.0f} → {order.side} "
                  f"{order.qty:.5f} [{order.state}] {order.reason}")
            if order.state == "OPEN":
                exchange.fill(order.client_id, order.qty)  # mock fills promptly
        else:
            print(f"c{cycle:02d} mark {mark:7.2f} w={weight:.0f} → hold")

        oms.poll_fills()
        oms.cancel_stale()
        rep = reconcile(journal, exchange, oms, risk, [SYMBOL])
        if rep["drift_frozen"]:
            print("!! drift frozen — halting")
            break
        time.sleep(0.05)

    pos = journal.position(SYMBOL)
    print(f"\nfinal: position {pos:.5f} ({pos*mark:.2f} notional), "
          f"kill={risk.killed() or 'off'}, events journaled")


if __name__ == "__main__":
    main()
