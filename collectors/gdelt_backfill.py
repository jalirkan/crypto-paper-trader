"""Backfill historical crypto headlines from GDELT, one day per query.

Usage:
    python -m collectors.gdelt_backfill --from 2023-08-01 [--to 2026-07-26]
    python -m collectors.gdelt_backfill --from 2023-08-01 --sleep 8   # gentler

GDELT rate-limits to roughly one query per ~5s per IP, so the full 3 years
takes ~2 hours. Idempotent (URL-hash dedupe) and resumable — re-running
fetches only what's missing, and 429s retry the SAME day after a cooldown
instead of skipping it.
"""

from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

from . import db
from .http import HttpError
from .sources import gdelt

DAY_RETRIES = 4
COOLDOWN_S = 25.0


def fetch_day_patiently(day: date, sleep_s: float) -> list[tuple]:
    """Fetch one day, waiting out GDELT's rate limiter as needed."""
    s = day.strftime("%Y%m%d") + "000000"
    e = day.strftime("%Y%m%d") + "235959"
    for attempt in range(DAY_RETRIES):
        try:
            return gdelt.fetch_window(s, e)
        except HttpError as err:
            if err.status == 429 and attempt < DAY_RETRIES - 1:
                wait = COOLDOWN_S * (attempt + 1)
                print(f"{day}: rate-limited, cooling down {wait:.0f}s…")
                time.sleep(wait)
                continue
            raise
    raise HttpError("gdelt", 429, "retries exhausted")  # pragma: no cover


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="end", default=None, help="YYYY-MM-DD (default today)")
    ap.add_argument("--sleep", type=float, default=6.0, help="seconds between days")
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today()
    n_days = (end - start).days + 1
    print(f"{n_days} days to cover at ~{args.sleep:.0f}s each ≈ {n_days*args.sleep/60:.0f} min (plus cooldowns)")

    conn = db.connect()
    total_new = 0
    failed_days = 0
    done = 0
    day = start
    while day <= end:
        try:
            rows = fetch_day_patiently(day, args.sleep)
            new = db.insert_news(conn, rows)
            total_new += new
            db.log_run(conn, "gdelt", True, new, str(day))
            done += 1
            if new == 0 and len(rows) > 0:
                pass  # fully deduped day (already fetched in a previous run)
            print(f"{day}: +{new:3d} new  ({done}/{n_days} days, {total_new} total this run)")
        except Exception as err:  # noqa: BLE001 — keep marching through outages
            failed_days += 1
            db.log_run(conn, "gdelt", False, 0, f"{day}: {err}")
            print(f"{day}: FAILED — {err}")
        day += timedelta(days=1)
        time.sleep(args.sleep)

    print(f"\nDone: {total_new} new headlines this run; {failed_days} day(s) failed.")
    if failed_days:
        print("Re-run the same command to fill the gaps — already-fetched days dedupe instantly.")


if __name__ == "__main__":
    main()
