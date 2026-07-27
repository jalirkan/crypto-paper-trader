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

## EXP-002/003/004 · 2026-07-26 · Risk overlays on Donchian (pre-registered)

Hypothesis:  Fixed-parameter, shrink-only risk overlays improve OOS drawdown
             without hurting Sharpe. KEEP rule written before running: MaxDD
             improves with Sharpe within 0.05 of plain, on ≥2 of 3 symbols.
Config:      vol_target (40% ann / 30d window), fng_gate (halve day after
             F&G ≥ 80), stable_gate (halve while 30d stablecoin supply Δ < 0).
             No grids — parameters fixed a priori. Walk-forward as EXP-001.
Data:        Same candles as EXP-001 + 3,094 days of F&G + 3,162 days of
             stablecoin supply. Full tables: reports/overlays_2026-07-26.md
Result:      vol_target: KEEP (BTC Sharpe 0.44→0.67, MaxDD −25.4→−19.4;
             ETH MaxDD −31.6→−22.8 with Sharpe within band; SOL fails).
             fng_gate: 1/3 → KILL. stable_gate: 1/3 → KILL.
             combined: 1/3 → KILL (over-stacking shrinks returns too far).
Verdict:     KEEP vol targeting as part of the candidate sleeve
             (donchian + vol_target). KILL both flow gates — archived here so
             they don't get quietly retried.
Caveats:     Overlays tested on the same OOS span as EXP-001 — regime caveat
             carries over. Vol targeting's edge concentrated in high-vol
             months; that's consistent with its mechanism, but forward paper
             remains the judge.

## LAB-001 · 2026-07-26 · Research Lab first run: random search, BTC

Hypothesis:  Infrastructure test + null calibration: does random search over
             the strategy DSL find anything that survives a sealed holdout
             with trial-counting statistics? (Expected answer: no.)
Config:      Random generator, 6 generations × 50 pop, seed 42. Search span =
             first 730 daily bars; final 365 bars SEALED. Costs 10+5 bps.
             Judgement: DSR ≥ 0.95 (N = all 274 trials) AND stationary-
             bootstrap p ≤ 0.05 vs B&H on holdout.
Data:        BTC daily, archive snapshot. Report: reports/lab_finalize_2026-07-26.md
Result:      274 unique candidates evaluated. Best train SR/bar +0.098
             (≈1.9 annualized — looks great, means nothing). Expected-max-of-
             274-junk threshold SR0 = +0.122 — no finalist cleared it even
             in-sample. Holdout (a −44.7% B&H year): all three finalists
             FAILED — DSR 0.000, bootstrap p 0.11–1.00. One "elite" was a
             nonsense inverted breakout that train data happened to reward.
Verdict:     Lab works as designed: it correctly identified 274 strategies'
             worth of apparent edge as pure selection luck. This run is the
             null baseline for LAB-002 (Claude-guided generation): the
             question becomes whether an LLM hypothesis engine beats random
             search per trial — measurable, falsifiable.
Caveats:     Holdout is a single bear-market year; a strategy family could
             fail here and still have merit elsewhere. The lab's verdicts are
             about THIS search, not the universe.
