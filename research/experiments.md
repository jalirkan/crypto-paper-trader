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

## LAB-002 · 2026-07-26 · Claude-guided search vs the random null

Hypothesis:  An LLM hypothesis engine searches more efficiently per trial
             than random generation. (Claude ran in-session as the generator,
             conditioned on the trial ledger; 3 generations, 43 candidates.)
Config:      Same protocol and search span as LAB-001; trials cumulative
             (N = 317 total). Candidate families: trend persistence with
             momentum confirms, low-volatility breakouts, RSI-regime
             hysteresis, smoothed momentum, vol-brake trend.
Result:      Per-trial quality — Claude decisively better: median robust SR
             +0.064 vs −0.058 (random), 77% vs 27% clearing +0.05, mean
             +0.037 vs −0.491. Best single trial — random still ahead
             (+0.097 vs +0.088), as expected: max of 274 lucky draws beats
             max of 43 disciplined ones when no true edge exists.
             Sealed holdout — ALL FAIL, both sources. But failure modes
             differ tellingly: random's finalists rode the −44.7% bear to
             −53% drawdowns (they were disguised buy-and-hold); Claude's
             finalists lost −19% to −25% at half the drawdown — they failed
             like genuine trend strategies in a bear, not like junk.
             DSR 0.000 across the board; p vs B&H 0.20–0.25 (Claude) vs
             0.11–1.00 (random). Nothing significant.
Verdict:     KEEP the two-sided finding: (1) LLM generation ≈3× more
             efficient per trial — worth using for future searches;
             (2) neither search produced an edge that survives trial-counting
             statistics — consistent with EXP-001/002: simple Donchian +
             vol targeting remains the only credible candidate, and it came
             from hypothesis-first research, not search.
Disclosures: The generator (Claude) had seen LAB-001's holdout report and
             knew the holdout year was bearish — a leak that plausibly
             biased candidates defensive. The 3 extra holdout evaluations of
             Claude's top-3 were outside the finalize protocol, are reported
             here, and selected nothing.
