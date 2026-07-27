"""Backfill historical crypto headlines from GDELT, one day per query.

Usage:
    python -m collectors.gdelt_backfill --from 2023-08-01 [--to 2026-07-26]

~1,100 queries for 3 years at ~1.3s each ≈ 25 minutes. Idempotent (URL-hash
dedupe), resumable (re-run anytime), polite (rate-limited).
"""

from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

from . import db
from .sources import gdelt

SLEEP_S = 1.3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="end", default=None, help="YYYY-MM-DD (default today)")
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today()

    conn = db.connect()
    total_new = 0
    day = start
    while day <= end:
        s = day.strftime("%Y%m%d") + "000000"
        e = day.strftime("%Y%m%d") + "235959"
        try:
            rows = gdelt.fetch_window(s, e)
            new = db.insert_news(conn, rows)
            total_new += new
            db.log_run(conn, "gdelt", True, new, str(day))
            print(f"{day}: +{new:3d} new ({len(rows)} fetched, {total_new} total)", end="\r")
        except Exception as err:  # noqa: BLE001 — keep marching through outages
            db.log_run(conn, "gdelt", False, 0, f"{day}: {err}")
            print(f"\n{day}: FAILED — {err}")
        day += timedelta(days=1)
        time.sleep(SLEEP_S)

    print(f"\nDone: {total_new} new headlines → news table")


if __name__ == "__main__":
    main()
