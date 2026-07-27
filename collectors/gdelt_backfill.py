"""Backfill historical crypto headlines from GDELT, one day per query.

    python -m collectors.gdelt_backfill --from 2023-08-01     # resume anytime
    python -m collectors.gdelt_backfill --report              # coverage + pace stats

GDELT's real-world limiter behaves like a slow-refill token bucket and
penalizes eager retries, so this collector:

- SKIPS days already completed in any earlier run (no wasted queries),
- paces adaptively (AIMD): each success slightly speeds up, each 429 slows
  everything down — the loop converges on whatever GDELT actually allows,
- waits out 429s patiently (60s/120s/240s) instead of poking the limiter,
- appends structured JSONL to data/gdelt_backfill.log for remote monitoring.

Expect the full 3 years to be an overnight job. That's fine — it's resumable,
and the archive only has to be built once.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

from . import db
from .http import HttpError
from .sources import gdelt

LOG_PATH = db.ROOT / "data" / "gdelt_backfill.log"

# Adaptive pacing bounds (seconds between day-queries).
SLEEP_START, SLEEP_MIN, SLEEP_MAX = 20.0, 8.0, 90.0
SPEEDUP, SLOWDOWN = 0.92, 1.6
RETRY_WAITS = (60.0, 120.0, 240.0)


def log_line(payload: dict) -> None:
    payload["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def covered_days(conn) -> set[str]:
    """Days any previous run completed successfully — skip them."""
    return {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT message FROM collector_runs WHERE collector='gdelt' AND ok=1"
        )
        if r[0]
    }


def next_sleep(current: float, success: bool) -> float:
    if success:
        return max(SLEEP_MIN, current * SPEEDUP)
    return min(SLEEP_MAX, current * SLOWDOWN)


def fetch_day_patiently(day: date) -> list[tuple]:
    s = day.strftime("%Y%m%d") + "000000"
    e = day.strftime("%Y%m%d") + "235959"
    last: Exception | None = None
    for i, wait in enumerate((0.0, *RETRY_WAITS)):
        if wait:
            print(f"{day}: rate-limited, waiting {wait:.0f}s (attempt {i+1})…")
            log_line({"day": str(day), "event": "429_wait", "wait_s": wait})
            time.sleep(wait)
        try:
            return gdelt.fetch_window(s, e)
        except HttpError as err:
            last = err
            if err.status != 429:
                raise
    assert last is not None
    raise last


def run_backfill(start: date, end: date, refetch: bool) -> None:
    conn = db.connect()
    done = covered_days(conn) if not refetch else set()
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    todo = [d for d in days if str(d) not in done]
    print(
        f"{len(days)} days in range · {len(days) - len(todo)} already covered · "
        f"{len(todo)} to fetch (adaptive pace {SLEEP_START:.0f}s start, "
        f"{SLEEP_MIN:.0f}–{SLEEP_MAX:.0f}s bounds)"
    )
    log_line({"event": "start", "todo": len(todo), "skipped": len(days) - len(todo)})

    sleep_s = SLEEP_START
    total_new = fails = fetched = 0
    t0 = time.time()
    for day in todo:
        try:
            rows = fetch_day_patiently(day)
            new = db.insert_news(conn, rows)
            total_new += new
            fetched += 1
            db.log_run(conn, "gdelt", True, new, str(day))
            log_line({"day": str(day), "event": "ok", "new": new, "sleep_s": round(sleep_s, 1)})
            sleep_s = next_sleep(sleep_s, True)
            rate = fetched / max(time.time() - t0, 1) * 3600
            print(
                f"{day}: +{new:3d} new  ({fetched}/{len(todo)} fetched, {total_new} total, "
                f"pace {sleep_s:.0f}s, ~{rate:.0f} days/hr)"
            )
        except Exception as err:  # noqa: BLE001 — keep marching
            fails += 1
            db.log_run(conn, "gdelt", False, 0, f"{day}: {err}")
            log_line({"day": str(day), "event": "fail", "error": str(err)[:200]})
            sleep_s = next_sleep(sleep_s, False)
            print(f"{day}: FAILED — {str(err)[:120]}  (pace → {sleep_s:.0f}s)")
        time.sleep(sleep_s)

    log_line({"event": "done", "new": total_new, "fails": fails})
    print(f"\nDone: +{total_new} headlines, {fails} day(s) failed. Re-run to fill gaps.")


def report() -> None:
    """Coverage + pace stats from the archive and the JSONL log."""
    conn = db.connect()
    ok = covered_days(conn)
    n = conn.execute("SELECT COUNT(*) FROM news WHERE source LIKE 'gdelt:%'").fetchone()[0]
    print(f"headlines: {n} · days completed: {len(ok)}")
    if ok:
        print(f"span: {min(ok)} → {max(ok)}")
        # Gap months summary
        by_month: dict[str, int] = {}
        for d in ok:
            by_month[d[:7]] = by_month.get(d[:7], 0) + 1
        thin = {m: c for m, c in sorted(by_month.items()) if c < 25}
        if thin:
            print("months with gaps:", ", ".join(f"{m}({c}d)" for m, c in thin.items()))
    if LOG_PATH.exists():
        events = [json.loads(x) for x in LOG_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
        oks = [e for e in events if e.get("event") == "ok"]
        waits = [e for e in events if e.get("event") == "429_wait"]
        fails = [e for e in events if e.get("event") == "fail"]
        print(f"log: {len(oks)} ok · {len(waits)} rate-limit waits · {len(fails)} failures")
        if oks:
            recent = oks[-20:]
            avg_pace = sum(e.get("sleep_s", 0) for e in recent) / len(recent)
            print(f"recent settled pace: ~{avg_pace:.0f}s/query "
                  f"(~{3600/max(avg_pace,1):.0f} days/hr)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", help="YYYY-MM-DD")
    ap.add_argument("--to", dest="end", default=None)
    ap.add_argument("--refetch", action="store_true", help="ignore covered-day skip")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        report()
        return
    if not args.start:
        raise SystemExit("--from YYYY-MM-DD required (or --report)")
    run_backfill(
        date.fromisoformat(args.start),
        date.fromisoformat(args.end) if args.end else date.today(),
        args.refetch,
    )


if __name__ == "__main__":
    main()
