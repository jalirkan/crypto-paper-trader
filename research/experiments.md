# Experiments Ledger

Every backtest/study gets an entry — including (especially) the failures.
Format per entry:

```
## EXP-NNN · YYYY-MM-DD · short name
Hypothesis:  what we expect and why
Config:      strategy, params, universe, timeframe, costs
Data:        range used, train/validation/test split
Result:      key metrics vs B&H BTC benchmark (net of costs)
Verdict:     KEEP / KILL / REVISE — and the reasoning
```

Rules (from RESEARCH_PLAN.md): kill criteria are written before running;
killed ideas don't get quietly retried with tweaked parameters.

---

## EXP-001 · 2026-07-26 · Trend baselines, daily bars, BTC/ETH/SOL

Hypothesis:  Medium-term trend capture beats buy-and-hold risk-adjusted (PLAN §5.1).
Config:      ma_cross / tsmom / donchian, small grids, long/flat, 10bps fee + 5bps
             slippage per side. Walk-forward: 365-bar train, 90-bar test, selection
             by train Sharpe.
Data:        1,095 daily bars per symbol (2023-07 → 2026-07), archive.db snapshot.
Result:      In-sample, every strategy "beats" B&H (donchian BTC Sharpe 1.28 vs
             0.81) — expected optimism. Walk-forward OOS: ma_cross and tsmom
             collapse (negative Sharpe on BTC and SOL). donchian survives on all
             three: Sharpe 0.44/0.32/0.44 vs B&H 0.19/−0.02/−0.17, with max
             drawdown roughly halved (−25%/−32%/−35% vs −53%/−68%/−76%).
             Full tables: reports/baselines_2026-07-26.md
Verdict:     KEEP donchian as the candidate trend sleeve → forward paper next.
             KILL ma_cross and tsmom as standalone sleeves (parked; revisit only
             as regime-filter inputs).
Caveats:     (1) OOS span ≈2y of mostly bear/chop — a long/flat structure is
             flattered by this regime; (2) picking donchian after seeing all
             three OOS results carries residual selection bias — it is a
             candidate, not a conclusion; (3) no live claim before ≥3 months of
             forward paper per PLAN §7.
