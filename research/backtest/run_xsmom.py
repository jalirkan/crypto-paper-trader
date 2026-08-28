"""EXP-007 — cross-sectional momentum vs buy-and-hold BTC.

Usage:
    python -m research.backtest.run_xsmom [--db PATH]

There are deliberately no strategy options. The lookback, the basket size, the
rebalance interval, the costs, the interval, the kill bar and its four guards
are pre-registered in research/experiments.md and live in `xsmom.py` as
constants; a `--lookback` flag here would be an invitation to do the one thing
the ledger exists to prevent. `--db` points at a copy of the archive and that
is the whole surface.

The verdict is computed, not asserted: this module reads the interval, applies
the pre-registered rule, and prints whatever comes out.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from collectors.config import COINS

from ..lab import stats
from . import engine, metrics, xsmom
from .data import DataError, load_closes

REPORTS = Path(__file__).resolve().parent.parent / "reports"
HOLDOUT_BARS = 365  # the span research/lab seals — see run.py --holdout-bars
N_BOOT = 2000
MEAN_BLOCK = 20
SEED = 42


def load_universe(db: str | None = None) -> tuple[list[int], dict[str, list[float]], list[str]]:
    """Aligned daily closes for the tracked coins, anchored on BTC's calendar.

    BTC is the benchmark, so its bars define the common span. A coin that is
    missing any bar of that span is excluded and named — the pre-registered
    universe rule, which is about data coverage and cannot see a return.
    """
    ref_ts, _ = load_closes("BTC", db_path=db)
    universe: dict[str, list[float]] = {}
    excluded: list[str] = []
    for coin in COINS:
        sym = coin["sym"]
        try:
            ts, closes = load_closes(sym, db_path=db)
        except DataError as e:
            excluded.append(f"{sym}: {e}")
            continue
        by_ts = dict(zip(ts, closes))
        missing = sum(1 for t in ref_ts if t not in by_ts)
        if missing:
            excluded.append(f"{sym}: missing {missing} of {len(ref_ts)} daily bars in the span")
            continue
        universe[sym] = [by_ts[t] for t in ref_ts]
    return ref_ts, universe, excluded


def delta_sharpe(strategy: list[float], benchmark: list[float]) -> float:
    return metrics.sharpe(strategy) - metrics.sharpe(benchmark)


def decide(interval: str, guards_pass: bool) -> str:
    """The pre-registered rule, as a function so it can be tested rather than
    trusted: KILL if the interval sits below zero, KEEP if it sits above zero
    AND every guard passes, INCONCLUSIVE otherwise.

    Note what this cannot do. No guard can turn a KILL into anything else, and
    no guard can create a KEEP out of an interval that straddles zero — guards
    only ever subtract. That asymmetry is the pre-registration; a rule where a
    side condition could rescue a verdict is a rule that can be argued with
    after the numbers land.
    """
    if interval == "KILL":
        return "KILL"
    if interval == "KEEP" and guards_pass:
        return "KEEP"
    return "INCONCLUSIVE"


def year_of(ts_ms: int) -> str:
    return time.strftime("%Y", time.gmtime(ts_ms / 1000))


def per_year(
    span_ts: list[int], strategy: list[float], benchmark: list[float], min_bars: int = 100
) -> tuple[list[tuple[str, int, float, float, float]], list[str]]:
    """(year, bars, strategy Sharpe, benchmark Sharpe, ΔSharpe) per calendar year.

    EXP-006's per-year decomposition is what turned a passing headline APR into
    a kill — a multi-year average can describe a regime that has ended. Same
    check here, reported whatever it says.

    Years with fewer than `min_bars` measured bars are returned separately
    rather than dropped silently: a Sharpe over a partial quarter is noise with
    a decimal point, but a reader is entitled to know the year was there.
    """
    buckets: dict[str, list[int]] = {}
    for i, t in enumerate(span_ts):
        buckets.setdefault(year_of(t), []).append(i)
    out, skipped = [], []
    for year, idx in sorted(buckets.items()):
        if len(idx) < min_bars:
            skipped.append(f"{year} ({len(idx)} bars)")
            continue
        s = [strategy[i] for i in idx]
        b = [benchmark[i] for i in idx]
        out.append((year, len(idx), metrics.sharpe(s), metrics.sharpe(b), delta_sharpe(s, b)))
    return out, skipped


def fmt(s: dict) -> str:
    return (
        f"CAGR {s['cagr']*100:8.1f}%  Sharpe {s['sharpe']:6.2f}  "
        f"MaxDD {s['max_dd']*100:7.1f}%  exposure {s.get('exposure', 0)*100:4.0f}%"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="EXP-007 cross-sectional momentum.")
    ap.add_argument("--db", default=None, help="override archive.db path")
    args = ap.parse_args()

    ts, universe, excluded = load_universe(args.db)
    symbols = sorted(universe)
    n = len(ts)
    L = xsmom.LOOKBACK
    if n < L + HOLDOUT_BARS + 30:
        raise SystemExit(f"only {n} daily bars — need lookback + holdout + room")

    span_ts = ts[L + 1 :]  # one timestamp per measured bar
    span = {s: c[L:] for s, c in universe.items()}  # measured span, warm-up dropped

    # --- the sleeve, and the two benchmarks, over identical bars -------------
    full = xsmom.simulate(universe)
    strat = full["returns"][L:]
    bh = engine.buy_and_hold(universe["BTC"][L:], xsmom.FEE_BPS, xsmom.SLIP_BPS)
    basket = xsmom.equal_weight_basket(span)
    assert len(strat) == len(bh.returns) == len(basket["returns"]) == len(span_ts)

    strat_stats = metrics.summarize(strat, [sum(full["weights"][s][t] for s in symbols)
                                            for t in range(L, n)])
    strat_stats["trades"] = full["rebalances"]
    strat_stats["turnover_yr"] = full["stats"]["turnover_yr"]

    # --- the pre-registered statistic and its interval -----------------------
    ci = stats.sharpe_diff_ci(strat, bh.returns, N_BOOT, MEAN_BLOCK, SEED)
    interval = stats.interval_verdict(ci["lo"], ci["hi"], 0.0)
    excess = [a - b for a, b in zip(strat, bh.returns)]
    pvalue = stats.stationary_bootstrap_pvalue(excess, n_boot=N_BOOT, mean_block=MEAN_BLOCK,
                                               seed=SEED)

    # --- guards. Each can only PREVENT a KEEP -------------------------------
    boundary = n - HOLDOUT_BARS
    hold_strat = full["returns"][boundary - 1 :]
    hold_bh = engine.buy_and_hold(universe["BTC"][boundary - 1 :], xsmom.FEE_BPS,
                                  xsmom.SLIP_BPS).returns
    g2_delta = delta_sharpe(hold_strat, hold_bh)

    neighbour_rows = []
    for params in xsmom.neighbours():
        alt = xsmom.simulate(universe, **params)["returns"][L:]
        neighbour_rows.append((params, delta_sharpe(alt, bh.returns)))
    robust = min([ci["diff"], *[d for _, d in neighbour_rows]])

    g4_delta = delta_sharpe(strat, basket["returns"])

    guards = [
        ("G1 drawdown no worse than B&H BTC",
         strat_stats["max_dd"] >= bh.stats["max_dd"],
         f"{strat_stats['max_dd']*100:.1f}% vs {bh.stats['max_dd']*100:.1f}%"),
        ("G2 sealed holdout ΔSharpe > 0", g2_delta > 0,
         f"{g2_delta:+.3f} over the final {HOLDOUT_BARS} bars"),
        ("G3 robust ΔSharpe > 0 (min over ±25% neighbours)", robust > 0,
         f"{robust:+.3f}"),
        ("G4 ΔSharpe vs equal-weight basket > 0", g4_delta > 0, f"{g4_delta:+.3f}"),
    ]

    # --- the verdict, computed from the rule as written ---------------------
    verdict = decide(interval, all(ok for _, ok, _ in guards))

    years, short_years = per_year(span_ts, strat, bh.returns)

    # --- report --------------------------------------------------------------
    stamp = time.strftime("%Y-%m-%d")
    span_desc = (
        f"{time.strftime('%Y-%m-%d', time.gmtime(span_ts[0] / 1000))} → "
        f"{time.strftime('%Y-%m-%d', time.gmtime(span_ts[-1] / 1000))}"
    )
    lines = [
        f"# EXP-007 cross-sectional momentum — {stamp}",
        "",
        f"Pre-registered in `research/experiments.md` before this code existed. "
        f"Lookback {xsmom.LOOKBACK}, top {xsmom.TOP_N} of {len(symbols)}, rebalance every "
        f"{xsmom.REBALANCE} bars, {xsmom.FEE_BPS:.0f}+{xsmom.SLIP_BPS:.0f} bps per side.",
        "",
        f"- universe ({len(symbols)}): {', '.join(symbols)}",
        f"- excluded: {'; '.join(excluded) if excluded else 'none'}",
        f"- measured span: {len(strat)} bars, {span_desc} (warm-up dropped; "
        f"all three series see identical bars)",
        f"- rebalances: {full['rebalances']}, turnover {strat_stats['turnover_yr']:.2f}×/yr",
        "",
        "## Result",
        "",
        f"- **cross-sectional momentum**: {fmt(strat_stats)}",
        f"- **buy & hold BTC**: {fmt(bh.stats)}",
        f"- **equal-weight universe**: {fmt(basket['stats'])}",
        "",
        f"**ΔSharpe vs B&H BTC = {ci['diff']:+.3f}, 95% CI "
        f"[{ci['lo']:+.3f}, {ci['hi']:+.3f}]** "
        f"(paired stationary block bootstrap, {N_BOOT} resamples, mean block "
        f"{MEAN_BLOCK}, seed {SEED}) → interval reads **{interval}**",
        "",
        f"Reported, not part of the bar: stationary-bootstrap p vs B&H on mean "
        f"excess return = {pvalue:.3f}.",
        "",
        "## Guards (each can only prevent a KEEP)",
        "",
    ]
    for name, ok, detail in guards:
        lines.append(f"- {'PASS' if ok else 'FAIL'} — {name}: {detail}")
    lines += [
        "",
        "### ±25% neighbourhood (guard G3 — a probe, nothing may be selected from it)",
        "",
        "| lookback | top N | rebalance | ΔSharpe vs B&H |",
        "|---|---|---|---|",
        f"| {xsmom.LOOKBACK} | {xsmom.TOP_N} | {xsmom.REBALANCE} | {ci['diff']:+.3f} (base) |",
    ]
    for params, d in neighbour_rows:
        lines.append(
            f"| {params['lookback']} | {params['top_n']} | {params['rebalance_every']} | {d:+.3f} |"
        )
    lines += [
        "",
        "### Per-year decomposition (reported; not part of the bar)",
        "",
        "| year | bars | XSMOM Sharpe | B&H BTC Sharpe | Δ |",
        "|---|---|---|---|---|",
    ]
    for year, bars, ss, bs, d in years:
        lines.append(f"| {year} | {bars} | {ss:+.2f} | {bs:+.2f} | {d:+.3f} |")
    if short_years:
        lines += [
            "",
            f"Too few bars to report a Sharpe, and omitted above rather than "
            f"dropped quietly: {', '.join(short_years)}.",
        ]
    lines += [
        "",
        "## Verdict",
        "",
        f"**{verdict}** — computed from the pre-registered rule: KILL if the "
        "interval sits below zero, KEEP if it sits above zero and all four "
        "guards pass, INCONCLUSIVE otherwise.",
        "",
    ]

    text = "\n".join(lines) + "\n"
    print(text)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"xsmom_{stamp}.md"
    out.write_text(text, encoding="utf-8")
    print(f"Report → {out}")


if __name__ == "__main__":
    main()
