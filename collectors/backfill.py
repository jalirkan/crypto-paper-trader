"""Historical backfill: candles, funding, Fear & Greed, stablecoin supply.

Usage:
    python -m collectors.backfill              # everything
    python -m collectors.backfill --candles    # candles only

Idempotent — safe to re-run; it resumes from the latest stored timestamp.
News/social cannot be backfilled (no free history) — that archive starts the
day `collectors.run` first executes, which is why it ships in week 1.
"""

from __future__ import annotations

import argparse
import time

from . import db
from .config import COINS, DAILY_BACKFILL_DAYS, FUNDING_SYMBOLS, HOURLY_BACKFILL_DAYS
from .http import HttpError
from .sources import binance, coinbase, misc

SLEEP_BINANCE = 0.25
SLEEP_COINBASE = 0.4


def now_ms() -> int:
    return int(time.time() * 1000)


def backfill_candles_symbol(conn, coin: dict, tf: str, since_days: int) -> int:
    sym = coin["sym"]
    target_start = now_ms() - since_days * 86_400_000
    last = db.max_ts(conn, "candles", "symbol=? AND tf=?", (sym, tf))
    start = max(target_start, (last + 1) if last else target_start)
    total = 0

    # Primary: Binance klines (paginated, 1000/req)
    try:
        while start < now_ms():
            rows = binance.fetch_klines(coin["binance"], sym, tf, start)
            if not rows:
                break
            total += db.upsert_candles(conn, rows)
            start = rows[-1][2] + binance.INTERVAL_MS[tf]
            print(f"  {sym} {tf}: {total} candles (binance)", end="\r")
            time.sleep(SLEEP_BINANCE)
        return total
    except HttpError as e:
        print(f"\n  {sym} {tf}: binance unavailable ({e}), trying coinbase…")

    # Fallback: Coinbase (300/req windows)
    if not coin.get("coinbase"):
        print(f"  {sym} {tf}: no coinbase listing — skipped")
        return total
    win = coinbase.window_ms(tf)
    while start < now_ms():
        end = min(start + win, now_ms())
        rows = coinbase.fetch_candles(coin["coinbase"], sym, tf, start, end)
        if rows:
            total += db.upsert_candles(conn, rows)
        start = end + 1
        print(f"  {sym} {tf}: {total} candles (coinbase)", end="\r")
        time.sleep(SLEEP_COINBASE)
    return total


def backfill_candles(conn) -> None:
    print("== Candles ==")
    for coin in COINS:
        for tf, days in (("1d", DAILY_BACKFILL_DAYS), ("1h", HOURLY_BACKFILL_DAYS)):
            try:
                n = backfill_candles_symbol(conn, coin, tf, days)
                print(f"  {coin['sym']} {tf}: +{n} candles          ")
                db.log_run(conn, f"backfill:candles:{coin['sym']}:{tf}", True, n)
            except Exception as e:  # noqa: BLE001 — one symbol must not kill the run
                print(f"  {coin['sym']} {tf}: FAILED — {e}")
                db.log_run(conn, f"backfill:candles:{coin['sym']}:{tf}", False, 0, str(e))


def backfill_funding(conn) -> None:
    print("== Funding rates ==")
    for vsym in FUNDING_SYMBOLS:
        try:
            last = db.max_ts(conn, "funding", "symbol=?", (vsym,))
            start = (last + 1) if last else now_ms() - 3 * 365 * 86_400_000
            total = 0
            while start < now_ms():
                rows = binance.fetch_funding(vsym, start)
                if not rows:
                    break
                total += db.upsert_funding(conn, rows)
                start = rows[-1][1] + 1
                time.sleep(SLEEP_BINANCE)
            print(f"  {vsym}: +{total} funding points")
            db.log_run(conn, f"backfill:funding:{vsym}", True, total)
        except Exception as e:  # noqa: BLE001
            print(f"  {vsym}: FAILED — {e} (geo-blocked? runs fine from a VPS)")
            db.log_run(conn, f"backfill:funding:{vsym}", False, 0, str(e))


def backfill_misc(conn) -> None:
    print("== Fear & Greed ==")
    try:
        n = db.upsert_fear_greed(conn, misc.fetch_fng())
        print(f"  +{n} days")
        db.log_run(conn, "backfill:fng", True, n)
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED — {e}")
        db.log_run(conn, "backfill:fng", False, 0, str(e))

    print("== Stablecoin supply ==")
    try:
        n = db.upsert_stablecoins(conn, misc.fetch_stablecoins())
        print(f"  +{n} days")
        db.log_run(conn, "backfill:stables", True, n)
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED — {e}")
        db.log_run(conn, "backfill:stables", False, 0, str(e))


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill the historical archive.")
    ap.add_argument("--candles", action="store_true", help="candles only")
    ap.add_argument("--funding", action="store_true", help="funding only")
    ap.add_argument("--misc", action="store_true", help="fear&greed + stables only")
    args = ap.parse_args()
    run_all = not (args.candles or args.funding or args.misc)

    conn = db.connect()
    t0 = time.time()
    if run_all or args.candles:
        backfill_candles(conn)
    if run_all or args.funding:
        backfill_funding(conn)
    if run_all or args.misc:
        backfill_misc(conn)
    print(f"Done in {time.time() - t0:.0f}s → {db.DEFAULT_DB}")


if __name__ == "__main__":
    main()
