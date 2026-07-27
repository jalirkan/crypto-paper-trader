"""Feed externally-generated candidates into the lab (e.g., Claude-in-session).

    python -m research.lab.feed --context                 # print elites + history
    python -m research.lab.feed --ingest gen.json --gen 7 --source claude
"""

from __future__ import annotations

import argparse
import json

from ..backtest.data import load_closes
from . import orchestrate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--lab-db", default=None)
    ap.add_argument("--symbol", default="BTC")
    ap.add_argument("--holdout-bars", type=int, default=365)
    ap.add_argument("--context", action="store_true")
    ap.add_argument("--ingest", default=None, help="JSON file with a candidate array")
    ap.add_argument("--gen", type=int, default=99)
    ap.add_argument("--source", default="claude")
    args = ap.parse_args()

    conn = orchestrate.lab_db(args.lab_db)

    if args.context:
        total = conn.execute("SELECT COUNT(*) FROM lab_candidates").fetchone()[0]
        by_src = conn.execute(
            "SELECT source, COUNT(*), MAX(robust_sharpe) FROM lab_candidates GROUP BY source"
        ).fetchall()
        print(f"total trials: {total}")
        for src, n, best in by_src:
            print(f"  {src}: {n} trials, best robust SR {best:+.4f}")
        print("\ntop by robust SR:")
        lab = orchestrate.SearchLab([1.0, 2.0], conn, "peek")  # closes unused for reads
        print(lab.history_summary(15))
        return

    if args.ingest:
        ts, closes = load_closes(args.symbol, db_path=args.db)
        search = closes[: len(closes) - args.holdout_bars]
        lab = orchestrate.SearchLab(search, conn, args.source)
        with open(args.ingest, encoding="utf-8") as f:
            candidates = json.load(f)
        results = []
        for cand in candidates:
            out = lab.evaluate(cand, args.gen)
            if out:
                results.append(out)
        results.sort(key=lambda r: -r["robust"])
        print(f"evaluated {len(results)}/{len(candidates)} (rest: dupes/invalid)")
        for r in results:
            print(
                f"  {r['hash']}  SR {r['train_sharpe']:+.4f}  robust {r['robust']:+.4f}  "
                f"trades {r['stats'].get('trades')}  expo {r['stats'].get('exposure', 0):.2f}"
            )


if __name__ == "__main__":
    main()
