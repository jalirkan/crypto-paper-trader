"""EXP-002/003/004 — risk overlays on Donchian, walk-forward OOS.

Usage:
    python -m research.backtest.run_overlays [--db PATH] [--symbols BTC,ETH,SOL]

Variants (all fixed-parameter, defined in overlays.py):
  plain        Donchian as shipped (EXP-001 baseline)
  vol_target   scale by min(1, 40% ann vol / realized 30d vol)
  fng_gate     halve exposure the day after Fear & Greed ≥ 80
  stable_gate  halve exposure while 30d stablecoin supply change < 0
  combined     all three overlays stacked

KEEP rule (pre-registered): OOS max drawdown improves while Sharpe stays
within 0.05 of plain (or better), on ≥2 of 3 symbols.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

from . import overlays
from .data import DataError, load_closes
from .walkforward import walk_forward

REPORTS = Path(__file__).resolve().parent.parent / "reports"


def day_of(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts_ms / 1000))


def load_day_map(db_path: str | None, table: str, value_col: str) -> dict[str, float]:
    from .data import DEFAULT_DB

    path = db_path or DEFAULT_DB
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    try:
        rows = conn.execute(f"SELECT ts, {value_col} FROM {table} ORDER BY ts").fetchall()
    finally:
        conn.close()
    return {day_of(r[0]): r[1] for r in rows}


def fmt(s: dict) -> str:
    return (
        f"CAGR {s['cagr']*100:7.1f}%  Sharpe {s['sharpe']:5.2f}  "
        f"MaxDD {s['max_dd']*100:6.1f}%  exposure {s.get('exposure', 0)*100:4.0f}%"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTC,ETH,SOL")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    fng = load_day_map(args.db, "fear_greed", "value")
    stables = load_day_map(args.db, "stablecoins", "total_mcap")

    stamp = time.strftime("%Y-%m-%d")
    lines = [
        f"# Overlay experiments (EXP-002/003/004) — {stamp}",
        "\nFixed-parameter risk overlays on walk-forward Donchian. KEEP rule: OOS",
        "MaxDD improves with Sharpe within 0.05 of plain, on ≥2 of 3 symbols.\n",
    ]

    for symbol in [s.strip().upper() for s in args.symbols.split(",")]:
        try:
            ts, closes = load_closes(symbol, db_path=args.db)
        except DataError as e:
            print(f"{symbol}: {e}")
            continue
        days = [day_of(t) for t in ts]

        fng_gate = overlays.fng_gate_series(fng, days)
        stb_gate = overlays.stable_gate_series(stables, days)

        variants = {
            "plain": None,
            "vol_target": lambda c, w: overlays.vol_target(c, w),
            "fng_gate": lambda c, w: overlays.series_gate(w, fng_gate),
            "stable_gate": lambda c, w: overlays.series_gate(w, stb_gate),
            "combined": lambda c, w: overlays.series_gate(
                overlays.series_gate(overlays.vol_target(c, w), fng_gate), stb_gate
            ),
        }

        print(f"\n=== {symbol} ({len(closes)} bars, {sum(1 for g in fng_gate if g is not None)} F&G-gated) ===")
        lines.append(f"\n## {symbol}\n")
        base_stats = None
        for name, tf in variants.items():
            wf = walk_forward(closes, "donchian", transform=tf)
            s = wf["oos"]
            if name == "plain":
                base_stats = s
            marker = ""
            if base_stats is not None and name != "plain":
                dd_better = s["max_dd"] > base_stats["max_dd"]
                sharpe_ok = s["sharpe"] >= base_stats["sharpe"] - 0.05
                marker = "  ← KEEP candidate" if (dd_better and sharpe_ok) else "  (fails keep rule)"
            print(f"{name:12} {fmt(s)}{marker}")
            lines.append(f"- `{name}`: {fmt(s)}{marker}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"overlays_{stamp}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport → {out}")


if __name__ == "__main__":
    main()
