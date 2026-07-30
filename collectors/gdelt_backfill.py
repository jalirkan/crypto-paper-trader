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
import random
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

# Measured 2026-07-27 over 116 windows: each attempt succeeds with roughly
# constant probability (~25%) REGARDLESS of how many 429s preceded it —
# P(fail|prev fail) 27% vs P(fail|prev ok) 35%, and per-attempt success held
# near 22-28% at every rung of the old ladder. Observed abandonment (31%)
# matched 0.75^4 (32%) almost exactly: a memoryless lottery, not a penalty
# box that deepens. So the ladder is now MANY SHORT attempts instead of a few
# long ones — same wall-clock per window, far fewer abandoned windows
# (0.75^9 ≈ 8% vs 32%). Jitter avoids synchronizing with any bucket refill.
RETRY_WAITS = (15.0, 18.0, 22.0, 26.0, 30.0, 36.0, 43.0, 52.0)
JITTER_FRAC = 0.25


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


CIRCUIT_FAILS = 3          # consecutive window failures that trip the breaker
CIRCUIT_PAUSE_S = 900.0    # first nap: 15 min
CIRCUIT_PAUSE_MAX_S = 7200.0  # naps escalate 15→30→60→120 min while still locked out


def nap_duration(level: int) -> float:
    """Escalating nap: doubles per consecutive breaker trip, capped at 2h."""
    return min(CIRCUIT_PAUSE_S * (2**level), CIRCUIT_PAUSE_MAX_S)


def fetch_window_patiently(w_start: date, w_end: date) -> list[tuple]:
    s = w_start.strftime("%Y%m%d") + "000000"
    e = w_end.strftime("%Y%m%d") + "235959"
    label = f"{w_start}→{w_end}" if w_end != w_start else str(w_start)
    last: Exception | None = None
    for i, base_wait in enumerate((0.0, *RETRY_WAITS)):
        if base_wait:
            wait = base_wait * (1 + random.uniform(-JITTER_FRAC, JITTER_FRAC))
            print(
                f"{label}: 429 — retry {i}/{len(RETRY_WAITS)} in {wait:.0f}s "
                f"(each attempt ≈25% independent)"
            )
            log_line({"window": label, "event": "429_wait", "wait_s": round(wait, 1), "attempt": i})
            time.sleep(wait)
        try:
            return gdelt.fetch_window(s, e)
        except HttpError as err:
            last = err
            if err.status != 429:
                raise
    assert last is not None
    raise last


def build_windows(days: list[date], done: set[str], window_days: int) -> list[tuple[date, date]]:
    """Group the range into windows, keeping only those with uncovered days."""
    windows = []
    i = 0
    while i < len(days):
        chunk = days[i : i + window_days]
        if any(str(d) not in done for d in chunk):
            windows.append((chunk[0], chunk[-1]))
        i += window_days
    return windows


def run_backfill(start: date, end: date, refetch: bool, window_days: int) -> None:
    conn = db.connect()
    done = covered_days(conn) if not refetch else set()
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    windows = build_windows(days, done, window_days)
    print(
        f"{len(days)} days in range · {len(days) - sum((w[1]-w[0]).days+1 for w in windows)} "
        f"already covered · {len(windows)} queries of {window_days} day(s) each "
        f"(pace {SLEEP_START:.0f}s start, {SLEEP_MIN:.0f}–{SLEEP_MAX:.0f}s bounds, "
        f"circuit breaker: {CIRCUIT_FAILS} fails → {CIRCUIT_PAUSE_S/60:.0f} min nap)"
    )
    log_line({"event": "start", "windows": len(windows), "window_days": window_days})

    sleep_s = SLEEP_START
    total_new = fails = fetched = streak_fails = nap_level = 0
    t0 = time.time()
    for w_start, w_end in windows:
        label = f"{w_start}→{w_end}" if w_end != w_start else str(w_start)
        try:
            rows = fetch_window_patiently(w_start, w_end)
            new = db.insert_news(conn, rows)
            total_new += new
            fetched += 1
            streak_fails = 0
            nap_level = 0  # lockout over — naps reset to 15 min
            d = w_start
            while d <= w_end:  # every day in a fetched window counts as covered
                db.log_run(conn, "gdelt", True, new if d == w_start else 0, str(d))
                d += timedelta(days=1)
            log_line({"window": label, "event": "ok", "new": new, "sleep_s": round(sleep_s, 1)})
            sleep_s = next_sleep(sleep_s, True)
            rate = fetched / max(time.time() - t0, 1) * 3600
            print(
                f"{label}: +{new:3d} new  ({fetched}/{len(windows)} windows, {total_new} total, "
                f"pace {sleep_s:.0f}s, ~{rate:.0f} windows/hr)"
            )
        except Exception as err:  # noqa: BLE001 — keep marching
            fails += 1
            streak_fails += 1
            db.log_run(conn, "gdelt", False, 0, f"{label}: {err}")
            log_line({"window": label, "event": "fail", "error": str(err)[:200]})
            sleep_s = next_sleep(sleep_s, False)
            print(f"{label}: FAILED — {str(err)[:100]}  (pace → {sleep_s:.0f}s)")
            if streak_fails >= CIRCUIT_FAILS:
                pause = nap_duration(nap_level)
                print(
                    f"◔ circuit breaker: {streak_fails} consecutive failures — "
                    f"napping {pause/60:.0f} min (level {nap_level}); "
                    "escalates while the lockout holds, resets on first success"
                )
                log_line({"event": "circuit_pause", "pause_s": pause, "level": nap_level})
                time.sleep(pause)
                streak_fails = 0
                nap_level += 1
                sleep_s = SLEEP_START
        time.sleep(sleep_s)

    log_line({"event": "done", "new": total_new, "fails": fails})
    print(f"\nDone: +{total_new} headlines, {fails} window(s) failed. Re-run to fill gaps.")


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
    ap.add_argument("--window-days", type=int, default=3, choices=[1, 2, 3],
                    help="days per query (3 = fewest queries, less per-day volume)")
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
        args.window_days,
    )


if __name__ == "__main__":
    main()
