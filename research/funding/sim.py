"""Delta-neutral funding harvest simulator (RESEARCH_PLAN §5.3).

Position: long 1 unit spot + short 1 unit perp. Price exposure ≈ 0; the short
perp leg RECEIVES funding when the rate is positive (crowded longs pay).

Strategy (fixed hysteresis — no grid, per overlay discipline):
  enter when trailing 7-day mean funding, annualized, > enter_thr (default 8%)
  exit  when it decays below exit_thr (default 2%)

Costs: each transition trades two legs (spot + perp) at fee+slip per leg —
30 bps per entry, 30 bps per exit at defaults.

Modeled honestly as yield, not magic: when flat, capital earns nothing; when
the rate flips negative while in position, the short PAYS. Not modeled (noted
limitations): basis convergence P&L, margin interest, liquidation mechanics,
exchange counterparty risk — which is why the pre-registered kill bar is a
net APR ≥ 5%, well above zero.

Usage:
    python -m research.funding.sim                    # BTCUSDT from archive
    python -m research.funding.sim --symbol ETHUSDT --enter 0.10
(Needs funding rows — run the VPS backfill first; geo-blocked on US IPs.)
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "archive.db"

EPOCHS_PER_DAY = 3  # 8h funding epochs
LOOKBACK_EPOCHS = 21  # 7 days
LEG_COST = 0.0015  # 10 bps fee + 5 bps slip per leg


def annualized(mean_epoch_rate: float) -> float:
    return mean_epoch_rate * EPOCHS_PER_DAY * 365


def simulate(
    rates: list[float],
    enter_thr: float = 0.08,
    exit_thr: float = 0.02,
    leg_cost: float = LEG_COST,
) -> dict:
    """rates: chronological per-epoch funding rates (fraction, e.g. 0.0001)."""
    n = len(rates)
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    in_pos = False
    entries = 0
    epochs_in_pos = 0
    curve = [1.0]

    for i in range(n):
        # Decide at epoch i using rates up to and including i-1 (no look-ahead).
        if i >= LOOKBACK_EPOCHS:
            trailing = annualized(sum(rates[i - LOOKBACK_EPOCHS : i]) / LOOKBACK_EPOCHS)
            if not in_pos and trailing > enter_thr:
                in_pos = True
                entries += 1
                equity *= 1 - 2 * leg_cost  # open both legs
            elif in_pos and trailing < exit_thr:
                in_pos = False
                equity *= 1 - 2 * leg_cost  # close both legs

        if in_pos:
            equity *= 1 + rates[i]  # short perp receives (or pays) this epoch
            epochs_in_pos += 1

        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1)
        curve.append(equity)

    years = n / (EPOCHS_PER_DAY * 365)
    apr = (equity ** (1 / years) - 1) if years > 0 and equity > 0 else -1.0
    return {
        "epochs": n,
        "years": round(years, 2),
        "final_equity": equity,
        "apr": apr,
        "max_dd": max_dd,
        "entries": entries,
        "time_in_position": epochs_in_pos / n if n else 0.0,
        "curve": curve,
    }


def bootstrap_apr_ci(
    rates: list[float],
    enter_thr: float = 0.08,
    exit_thr: float = 0.02,
    n_boot: int = 400,
    block: int = 90,
    seed: int = 11,
) -> tuple[float, float]:
    """95% CI on APR via stationary block bootstrap.

    Blocks (~1 month of 8h epochs) preserve the regime persistence that makes
    funding autocorrelated; an iid bootstrap would shatter it and report an
    interval far too narrow. Required by the project's uncertainty rule — a
    bare APR is a bug, and a point estimate near the decision threshold is
    exactly where that bug does damage.
    """
    rng = random.Random(seed)
    n = len(rates)
    if n < block * 3:
        return (float("nan"), float("nan"))
    out = []
    for _ in range(n_boot):
        s: list[float] = []
        while len(s) < n:
            i = rng.randrange(0, n - block)
            s.extend(rates[i : i + block])
        out.append(simulate(s[:n], enter_thr, exit_thr)["apr"])
    out.sort()
    k = max(1, int(0.025 * n_boot))
    return (out[k], out[-k])


def yearly_apr(rows: list[tuple[int, float]], **kw) -> dict[str, float]:
    """APR per calendar year — the check that separates a live premium from a
    historical average dominated by one regime."""
    by_year: dict[str, list[float]] = {}
    for ts, rate in rows:
        by_year.setdefault(time.strftime("%Y", time.gmtime(ts / 1000)), []).append(rate)
    return {
        y: simulate(rr, **kw)["apr"]
        for y, rr in sorted(by_year.items())
        if len(rr) >= 200
    }


def load_rates(symbol: str, db_path: str | Path | None = None) -> list[float]:
    conn = sqlite3.connect(f"file:{db_path or DEFAULT_DB}?mode=ro", uri=True, timeout=10)
    try:
        rows = conn.execute(
            "SELECT rate FROM funding WHERE symbol=? ORDER BY ts", (symbol,)
        ).fetchall()
    finally:
        conn.close()
    return [float(r[0]) for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--db", default=None)
    ap.add_argument("--enter", type=float, default=0.08)
    ap.add_argument("--exit", dest="exit_thr", type=float, default=0.02)
    args = ap.parse_args()

    rates = load_rates(args.symbol, args.db)
    if len(rates) < 100:
        raise SystemExit(
            f"Only {len(rates)} funding epochs for {args.symbol}. Funding history "
            "is geo-blocked on US IPs — run `python -m collectors.backfill "
            "--funding` from the VPS first (deploy/vps/README.md)."
        )

    res = simulate(rates, args.enter, args.exit_thr)
    lo, hi = bootstrap_apr_ci(rates, args.enter, args.exit_thr)
    print(f"{args.symbol}: {res['epochs']} epochs ({res['years']}y)")
    print(
        f"  APR {res['apr']*100:+.2f}%  95% CI [{lo*100:+.2f}%, {hi*100:+.2f}%]  "
        f"MaxDD {res['max_dd']*100:.2f}%  entries {res['entries']}  "
        f"in-position {res['time_in_position']*100:.0f}%"
    )

    # Three outcomes decided against the INTERVAL, not the point estimate.
    if lo > 0.05:
        verdict = "KEEP (interval clears the 5% bar)"
    elif hi < 0.05:
        verdict = "KILL (interval below the 5% bar)"
    else:
        verdict = "INCONCLUSIVE (interval straddles the 5% bar)"
    print(f"  Pre-registered verdict: {verdict}")

    conn = sqlite3.connect(f"file:{args.db or DEFAULT_DB}?mode=ro", uri=True, timeout=10)
    try:
        rows = conn.execute(
            "SELECT ts, rate FROM funding WHERE symbol=? ORDER BY ts", (args.symbol,)
        ).fetchall()
    finally:
        conn.close()
    per_year = yearly_apr(rows, enter_thr=args.enter, exit_thr=args.exit_thr)
    if per_year:
        print("  per-year: " + "  ".join(f"{y} {a*100:+.1f}%" for y, a in per_year.items()))
        recent = list(per_year.values())[-2:]
        if recent and max(recent) < 0.02:
            print("  ⚠ the premium is dormant in the most recent years — a multi-year")
            print("    average here describes a regime that has ended, not a live edge.")

    stamp = time.strftime("%Y-%m-%d")
    out = ROOT / "research" / "reports" / f"funding_{args.symbol}_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"# Funding harvest — {args.symbol} — {stamp}\n\n"
        f"- thresholds: enter {args.enter:.0%} / exit {args.exit_thr:.0%} annualized (fixed)\n"
        f"- {res['epochs']} epochs ({res['years']}y), APR {res['apr']*100:+.2f}%, "
        f"MaxDD {res['max_dd']*100:.2f}%, entries {res['entries']}, "
        f"in-position {res['time_in_position']*100:.0f}%\n- verdict: {verdict}\n",
        encoding="utf-8",
    )
    print(f"Report → {out}")


if __name__ == "__main__":
    main()
