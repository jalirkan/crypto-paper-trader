"""Event study: does the market drift after classified news, net of costs?

Method (RESEARCH_PLAN §5.2):
- Events: relevant=1, novelty=1 labels, clustered so one story = one event
  (same type+direction within 6h collapses to the earliest headline).
- Signed forward return per event at +1h/+4h/+24h/+72h: direction × raw
  return from the first bar AFTER the headline (never the same bar).
- Null: bootstrap of random same-symbol windows (what drift looks like when
  nothing happened). Edge = event mean − control mean.
- Tradeable bar: |edge| > 2 × 15 bps round-trip AND the 95% CI of the event
  mean excludes the control mean AND n ≥ 20.

Usage:
    python -m research.events.study [--db PATH] [--min-conf medium]
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import time
from bisect import bisect_right
from pathlib import Path

from . import LABELS_SCHEMA

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "archive.db"
REPORTS = ROOT / "research" / "reports"

HORIZONS_H = [1, 4, 24, 72]
CLUSTER_MS = 6 * 3600 * 1000
COST = 2 * 0.0015  # tradeable bar: beat a 15 bps round trip, twice over
BOOT = 1000
CONF_RANK = {"low": 0, "medium": 1, "high": 2}
TRACKED = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK", "LTC"]


def load_hourly(conn, symbol: str) -> tuple[list[int], list[float]]:
    rows = conn.execute(
        "SELECT ts, close FROM candles WHERE symbol=? AND tf='1h' ORDER BY ts", (symbol,)
    ).fetchall()
    return [r[0] for r in rows], [float(r[1]) for r in rows]


def forward_return(ts: list[int], closes: list[float], event_ms: int, horizon_h: int) -> float | None:
    """Return from first bar strictly after the event to horizon_h bars later."""
    i = bisect_right(ts, event_ms)
    j = i + horizon_h
    if i >= len(ts) or j >= len(ts):
        return None
    # Guard against archive gaps: the entry bar must be within 2h of the event.
    if ts[i] - event_ms > 2 * 3600 * 1000:
        return None
    return closes[j] / closes[i] - 1.0


def load_events(conn, min_conf: str) -> list[dict]:
    conn.executescript(LABELS_SCHEMA)
    rows = conn.execute(
        """SELECT n.ts, l.event_type, l.direction, l.assets, l.confidence
           FROM news n JOIN news_labels l ON l.news_id = n.id
           WHERE l.relevant=1 AND l.novelty=1 AND l.direction != 0 AND n.ts IS NOT NULL
           ORDER BY n.ts"""
    ).fetchall()
    out, last_kept = [], {}
    for ts, etype, direction, assets, conf in rows:
        if CONF_RANK.get(conf, 0) < CONF_RANK[min_conf]:
            continue
        key = (etype, direction)
        if key in last_kept and ts - last_kept[key] < CLUSTER_MS:
            continue  # same story cluster
        last_kept[key] = ts
        syms = [a.strip().upper() for a in assets.split(",")]
        syms = [s for s in syms if s in TRACKED] or ["BTC"]  # MARKET → BTC proxy
        out.append({"ts": ts, "type": etype, "dir": direction, "symbols": syms})
    return out


def bootstrap_mean_ci(values: list[float], n_boot: int = BOOT) -> tuple[float, float, float]:
    means = []
    for _ in range(n_boot):
        sample = [random.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    return (
        sum(values) / len(values),
        means[int(0.025 * n_boot)],
        means[int(0.975 * n_boot)],
    )


def control_mean(
    ts: list[int],
    closes: list[float],
    horizon_h: int,
    n: int,
    dirs: list[int] | None = None,
) -> float:
    """Base rate for the SIGNED event metric: random timing, same direction mix.

    The control must be signed exactly like the statistic it benchmarks. An
    unsigned control silently imports market drift: with a 2:1 bullish:bearish
    label mix in a falling market, flipping the bearish third makes the event
    mean less negative than raw returns for purely arithmetic reasons, and the
    difference reads as 'drift'. That bug produced five false candidates at
    +72h on 2026-07-31 before the bullish-vs-bearish diagnostic caught it
    (both groups had identical forward returns). Drawing control signs from
    the observed direction mix removes it: any remaining edge is timing and
    information, not beta × imbalance.
    """
    vals = []
    hi = len(ts) - horizon_h - 1
    if hi < 2:
        return 0.0
    for _ in range(n):
        i = random.randint(1, hi)
        r = closes[i + horizon_h] / closes[i] - 1.0
        # Draw the sign, don't cycle: cycling a 300-long mix over 2000 draws
        # replays the head of the list and skews the ratio (caught by test).
        vals.append(r * (random.choice(dirs) if dirs else 1))
    return sum(vals) / len(vals)


def run_study(conn, min_conf: str) -> list[str]:
    random.seed(42)
    events = load_events(conn, min_conf)
    series = {s: load_hourly(conn, s) for s in TRACKED}
    lines = [f"Events after clustering/filters: {len(events)}\n"]

    buckets: dict[str, list[dict]] = {}
    for ev in events:
        buckets.setdefault(ev["type"], []).append(ev)
    buckets["ALL"] = events

    for name in sorted(buckets, key=lambda k: -len(buckets[k])):
        evs = buckets[name]
        lines.append(f"## {name} (n={len(evs)})\n")
        for h in HORIZONS_H:
            rets = []
            dirs: list[int] = []
            for ev in evs:
                for sym in ev["symbols"]:
                    ts, closes = series[sym]
                    if not ts:
                        continue
                    r = forward_return(ts, closes, ev["ts"], h)
                    if r is not None:
                        rets.append(ev["dir"] * r)
                        dirs.append(ev["dir"])
            if len(rets) < 5:
                lines.append(f"- +{h}h: n={len(rets)} — insufficient data")
                continue
            mean, lo, hi_ = bootstrap_mean_ci(rets)
            ts_b, closes_b = series["BTC"]
            ctrl = control_mean(ts_b, closes_b, h, 2000, dirs) if ts_b else 0.0
            edge = mean - ctrl
            tradeable = len(rets) >= 20 and abs(edge) > COST and (lo > ctrl or hi_ < ctrl)
            flag = "  ← CANDIDATE" if tradeable else ""
            lines.append(
                f"- +{h}h: n={len(rets)}  signed mean {mean*100:+.2f}%  "
                f"CI [{lo*100:+.2f}%, {hi_*100:+.2f}%]  control {ctrl*100:+.2f}%  "
                f"edge {edge*100:+.2f}%{flag}"
            )
        lines.append("")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--min-conf", default="medium", choices=["low", "medium", "high"])
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True, timeout=10)
    header = [
        f"# Event study — {time.strftime('%Y-%m-%d')}",
        f"\nFilters: relevant=1, novelty=1, direction≠0, confidence ≥ {args.min_conf}.",
        "Signed returns (bearish events flipped). Tradeable bar: n≥20, |edge| > "
        f"{COST*100:.2f}%, CI excludes control.\n",
    ]
    lines = header + run_study(conn, args.min_conf)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"event_study_{time.strftime('%Y-%m-%d')}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport → {out}")


if __name__ == "__main__":
    main()
