"""Run the AI Research Lab.

    python -m research.lab.run --generator random --generations 5 --pop 40
    python -m research.lab.run --generator claude --generations 3 --pop 20
    python -m research.lab.run --finalize            # judgement day (holdout)

Search span: all but the final --holdout-bars (default 365) of BTC daily
history. The holdout is touched ONLY by --finalize.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ..backtest.data import load_closes
from . import orchestrate
from .generate import ClaudeGenerator, RandomGenerator

REPORTS = Path(__file__).resolve().parent.parent / "reports"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTC")
    ap.add_argument("--multi", action="store_true", help="search BTC+ETH+SOL jointly")
    ap.add_argument("--db", default=None, help="archive.db override")
    ap.add_argument("--lab-db", default=None)
    ap.add_argument("--generator", choices=["random", "claude"], default="random")
    ap.add_argument("--generations", type=int, default=5)
    ap.add_argument("--pop", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--holdout-bars", type=int, default=365)
    ap.add_argument("--finalize", action="store_true")
    args = ap.parse_args()

    symbols = ["BTC", "ETH", "SOL"] if args.multi else [args.symbol]
    closes_map = {s: load_closes(s, db_path=args.db)[1] for s in symbols}
    closes = closes_map[symbols[0]]
    search_len = min(len(c) for c in closes_map.values()) - args.holdout_bars
    if search_len < 400:
        raise SystemExit("not enough history for search + holdout")
    conn = orchestrate.lab_db(args.lab_db)

    if args.finalize:
        if args.multi:
            report = orchestrate.finalize_multi(closes_map, search_len, conn)
            report["benchmark"] = report["benchmark_basket"]
            for f in report["finalists"]:
                f["holdout"] = f["holdout_basket"]
        else:
            report = orchestrate.finalize(closes, search_len, conn)
        stamp = time.strftime("%Y-%m-%d")
        scope = "BTC+ETH+SOL basket" if args.multi else args.symbol
        lines = [
            f"# LAB finalize — {stamp} ({scope})",
            f"\nTrials counted: {report['n_trials']} · holdout bars: {report['holdout_bars']}",
            f"\nBenchmark (B&H holdout): Sharpe/bar n/a, CAGR {report['benchmark']['cagr']*100:.1f}%, "
            f"MaxDD {report['benchmark']['max_dd']*100:.1f}%\n",
        ]
        for f in report["finalists"]:
            d = f["dsr"]
            lines += [
                f"## {f['hash']} — **{f['verdict']}**",
                f"- candidate: `{json.dumps(f['candidate'])}`",
                f"- train SR/bar {f['train_sharpe']:+.4f} (robust {f['robust_sharpe']:+.4f})",
                f"- holdout: CAGR {f['holdout']['cagr']*100:+.1f}%, Sharpe {f['holdout']['sharpe']:.2f}, "
                f"MaxDD {f['holdout']['max_dd']*100:.1f}%, trades {f['holdout'].get('trades')}",
                f"- DSR {d['dsr']:.3f} (SR0 threshold {d['sr0_threshold']:+.4f} from {d['n_trials']} trials)",
                f"- bootstrap p vs B&H: {f['holdout_vs_bh_pvalue']:.3f}",
                "",
            ]
        REPORTS.mkdir(parents=True, exist_ok=True)
        tag = "multi_" if args.multi else ""
        out = REPORTS / f"lab_finalize_{tag}{stamp}.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        print(f"Report → {out}")
        return

    search_input: dict | list = (
        {s: c[:search_len] for s, c in closes_map.items()} if args.multi else closes[:search_len]
    )
    lab = orchestrate.SearchLab(search_input, conn, args.generator)
    if args.generator == "random":
        gen = RandomGenerator(seed=args.seed)
    else:
        gen = ClaudeGenerator()
    t0 = time.time()
    lab.run_generations(gen, args.generations, args.pop)
    print(f"search done in {time.time()-t0:.1f}s — run --finalize when ready to spend the holdout")


if __name__ == "__main__":
    main()
