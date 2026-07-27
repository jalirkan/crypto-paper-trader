"""Incremental collector loop — the archive's heartbeat.

Usage:
    python -m collectors.run --once            # one collection cycle
    python -m collectors.run --loop            # run forever (15 min cycles)
    python -m collectors.run --loop --interval-min 10

Each cycle: news feeds, latest candles, funding, Fear & Greed, stablecoins.
All writes are idempotent upserts; failures are logged per-collector to the
collector_runs table and never abort the cycle.
"""

from __future__ import annotations

import argparse
import time

from . import db
from .config import COINS, FUNDING_SYMBOLS, RSS_FEEDS
from .sources import binance, misc, rss

LOOKBACK_MS = 3 * 86_400_000  # re-fetch window if collector was offline


def now_ms() -> int:
    return int(time.time() * 1000)


def collect_news(conn) -> None:
    for source, url in RSS_FEEDS:
        try:
            new = db.insert_news(conn, rss.fetch_feed(url, source))
            db.log_run(conn, f"news:{source}", True, new)
            if new:
                print(f"  news:{source}: +{new}")
        except Exception as e:  # noqa: BLE001
            db.log_run(conn, f"news:{source}", False, 0, str(e))
            print(f"  news:{source}: FAILED — {e}")


def collect_candles(conn) -> None:
    for coin in COINS:
        for tf in ("1h", "1d"):
            try:
                last = db.max_ts(conn, "candles", "symbol=? AND tf=?", (coin["sym"], tf))
                start = (last + 1) if last else now_ms() - LOOKBACK_MS
                rows = binance.fetch_klines(coin["binance"], coin["sym"], tf, start)
                if rows:
                    db.upsert_candles(conn, rows)
                db.log_run(conn, f"candles:{coin['sym']}:{tf}", True, len(rows))
            except Exception as e:  # noqa: BLE001
                db.log_run(conn, f"candles:{coin['sym']}:{tf}", False, 0, str(e))
        time.sleep(0.2)


def collect_funding(conn) -> None:
    for vsym in FUNDING_SYMBOLS:
        try:
            last = db.max_ts(conn, "funding", "symbol=?", (vsym,))
            start = (last + 1) if last else now_ms() - LOOKBACK_MS
            rows = binance.fetch_funding(vsym, start)
            if rows:
                db.upsert_funding(conn, rows)
            db.log_run(conn, f"funding:{vsym}", True, len(rows))
        except Exception as e:  # noqa: BLE001
            db.log_run(conn, f"funding:{vsym}", False, 0, str(e))


def record_signals(conn) -> None:
    """Append today's strategy weights to the forward-paper ledger."""
    try:
        from research import signals  # local import: research layer is optional here

        n = signals.record_daily(conn, ["BTC", "ETH", "SOL"])
        db.log_run(conn, "signals", True, n)
        if n:
            print(f"  signals: +{n} forward-paper rows")
    except Exception as e:  # noqa: BLE001
        db.log_run(conn, "signals", False, 0, str(e))


def collect_misc(conn) -> None:
    try:
        db.log_run(conn, "fng", True, db.upsert_fear_greed(conn, misc.fetch_fng()))
    except Exception as e:  # noqa: BLE001
        db.log_run(conn, "fng", False, 0, str(e))
    try:
        db.log_run(conn, "stables", True, db.upsert_stablecoins(conn, misc.fetch_stablecoins()))
    except Exception as e:  # noqa: BLE001
        db.log_run(conn, "stables", False, 0, str(e))


def cycle(conn) -> None:
    t0 = time.time()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] collection cycle")
    collect_news(conn)
    collect_candles(conn)
    collect_funding(conn)
    collect_misc(conn)
    record_signals(conn)
    print(f"  cycle done in {time.time() - t0:.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run data collectors.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--loop", action="store_true")
    ap.add_argument("--interval-min", type=float, default=15)
    args = ap.parse_args()

    conn = db.connect()
    if args.once:
        cycle(conn)
        return
    while True:
        try:
            cycle(conn)
        except Exception as e:  # noqa: BLE001 — the loop must survive anything
            print(f"  cycle error: {e}")
        time.sleep(args.interval_min * 60)


if __name__ == "__main__":
    main()
