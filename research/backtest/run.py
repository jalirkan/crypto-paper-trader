"""Baseline report: trend strategies vs buy-and-hold, in-sample AND walk-forward.

Usage:
    python -m research.backtest.run                    # BTC + ETH
    python -m research.backtest.run --symbols BTC,ETH,SOL
    python -m research.backtest.run --fee-bps 10 --slip-bps 5

Writes a dated markdown report to research/reports/ and prints the summary.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import engine
from .data import DataError, load_closes
from .strategies import STRATEGY_SPECS, compute_weights
from .walkforward import walk_forward

REPORTS = Path(__file__).resolve().parent.parent / "reports"


def fmt_stats(s: dict) -> str:
    return (
        f"CAGR {s['cagr']*100:7.1f}%  Sharpe {s['sharpe']:5.2f}  "
        f"Sortino {s['sortino']:5.2f}  MaxDD {s['max_dd']*100:6.1f}%"
        + (f"  trades {s.get('trades', '—'):>4}" if "trades" in s else "")
        + (f"  exposure {s.get('exposure', 0)*100:4.0f}%" if "exposure" in s else "")
    )


def run_symbol(
    symbol: str, fee_bps: float, slip_bps: float, lines: list[str], db: str | None = None
) -> None:
    ts, closes = load_closes(symbol, db_path=db)
    days = len(closes)
    lines.append(f"\n## {symbol} — {days} daily bars")
    print(f"\n=== {symbol} ({days} daily bars) ===")

    bh = engine.buy_and_hold(closes, fee_bps, slip_bps)
    lines.append(f"\n- **Buy & hold**: {fmt_stats(bh.stats)}")
    print(f"buy&hold            {fmt_stats(bh.stats)}")

    lines.append("\n**In-sample (full history, best grid params — optimistic by construction):**\n")
    for name, spec in STRATEGY_SPECS.items():
        best = None
        for params in spec["grid"]:
            w = compute_weights(name, closes, params)
            res = engine.run(closes, w, fee_bps, slip_bps, label=name)
            if best is None or res.stats["sharpe"] > best[0].stats["sharpe"]:
                best = (res, params)
        assert best is not None
        res, params = best
        lines.append(f"- `{name}` {params}: {fmt_stats(res.stats)}")
        print(f"{name:20}{fmt_stats(res.stats)}   {params}")

    lines.append("\n**Walk-forward out-of-sample (the number that counts):**\n")
    print("--- walk-forward OOS ---")
    for name in STRATEGY_SPECS:
        wf = walk_forward(closes, name, fee_bps=fee_bps, slip_bps=slip_bps)
        s, b = wf["oos"], wf["benchmark_oos"]
        verdict = "BEATS B&H Sharpe" if s["sharpe"] > b["sharpe"] else "loses to B&H Sharpe"
        chosen = [str(w["params"]) for w in wf["windows"][-3:]]
        lines.append(
            f"- `{name}`: {fmt_stats(s)}\n  - vs B&H same span: Sharpe {b['sharpe']:.2f}, "
            f"MaxDD {b['max_dd']*100:.1f}% → **{verdict}**\n  - recent params: {', '.join(chosen)}"
        )
        print(f"{name:20}{fmt_stats(s)}")
        print(f"{'':20}vs B&H Sharpe {b['sharpe']:5.2f}  MaxDD {b['max_dd']*100:6.1f}%  → {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Trend baselines vs buy-and-hold.")
    ap.add_argument("--symbols", default="BTC,ETH")
    ap.add_argument("--fee-bps", type=float, default=10.0)
    ap.add_argument("--slip-bps", type=float, default=5.0)
    ap.add_argument("--db", default=None, help="override archive.db path")
    args = ap.parse_args()

    stamp = time.strftime("%Y-%m-%d")
    lines = [
        f"# Trend baselines — {stamp}",
        f"\nCosts: {args.fee_bps:.0f} bps fee + {args.slip_bps:.0f} bps slippage per side. "
        "Walk-forward: 365-bar train, 90-bar test, param selection by train Sharpe.",
    ]
    for symbol in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        try:
            run_symbol(symbol, args.fee_bps, args.slip_bps, lines, db=args.db)
        except DataError as e:
            print(f"{symbol}: {e}")
            lines.append(f"\n## {symbol}\n\nSKIPPED — {e}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"baselines_{stamp}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport → {out}")


if __name__ == "__main__":
    main()
