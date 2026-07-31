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

## EXP-006 · 2026-07-31 · Funding harvest: a real premium that has already gone

Hypothesis:  Perp funding paid by crowded longs is harvestable delta-neutral
             (long spot / short perp). Highest pre-registered odds of anything
             in the plan (~60–75%), because it is a structural risk premium
             rather than directional alpha. Kill bar written in the sim's
             docstring long before data existed: **net APR ≥ 5%**.
Config:      Fixed hysteresis, no grid: enter when trailing 7-day annualized
             funding > 8%, exit below 2%. 30 bps round trip (two legs, both
             sides). BTCUSDT/ETHUSDT/SOLUSDT, 3,195 epochs each (2023-08 →
             2026-06, 2.9 years).
Data:        Unblocked without the planned VPS — the futures API geo-blocks US
             IPs, but Binance's static mirror serves the same history and does
             not. See collectors/sources/binance_vision.py.
Result:      Headline APRs cluster on the bar: BTC +4.67%, ETH +5.13%,
             SOL +4.95%, with tiny drawdowns (−0.85% to −1.44%) exactly as a
             delta-neutral carry trade should. Taken at face value, ETH
             "passes" by 0.13pp.
             It does not. Two checks kill it:
             (1) **Intervals.** Block-bootstrap 95% CIs are [+1.4%, +7.2%],
                 [+1.1%, +8.1%], [+0.3%, +6.9%]. All three straddle 5% →
                 INCONCLUSIVE under the project's three-outcome rule. The
                 point estimates cannot distinguish these symbols from each
                 other or from the threshold.
             (2) **Per-year decomposition, which is the real finding.**
                 2023: +5.4/+5.8/+6.2%. 2024: +9.9/+11.7/+12.2%.
                 2025: +0.5/−0.1/−0.8%. 2026: 0.0% on all three — the strategy
                 never entered a position, because funding never got rich
                 enough to trigger. The entire multi-year APR is a fossil of
                 the 2023–24 bull market. The mechanism has paid nothing for
                 roughly eighteen months.
Verdict:     KILL as a live sleeve. KEEP the finding, which is more useful
             than a pass would have been: the premium is real, well understood,
             and *conditional on leveraged-long crowding* — so it pays in
             euphoria and disappears in bear and chop, which is precisely when
             a diversifying sleeve would have to earn its place. Revisit only
             if funding regimes return, and only via the live signal, never via
             the historical average.
Caveats:     Unmodelled costs are all negative — basis convergence, margin
             interest, liquidation mechanics, exchange counterparty risk — so
             true net sits BELOW these figures. Single venue. The 8%/2%
             thresholds were fixed a priori and never tuned; tuning them to
             rescue the result would be exactly the failure mode this ledger
             exists to prevent.
Code fix:    The simulator originally printed a bare APR and a two-way verdict,
             which is how "ETH passes at 5.13%" nearly became a finding. It now
             computes a stationary block-bootstrap CI (blocks preserve funding's
             regime persistence; an iid bootstrap would report an interval far
             too narrow), decides against the interval with three outcomes, and
             prints a per-year breakdown with an explicit warning when the
             recent years are dormant. Three regression tests, including one
             asserting that an episodic premium produces a WIDE interval rather
             than a confident rate.

## EXP-005 · 2026-07-31 · LLM event study: 93k headlines, 10k events, no drift

Hypothesis:  Slow-moving fundamental news produces multi-hour drift that
             survives costs, and Claude can classify events well enough to
             isolate it (PLAN §5.2, the marquee experiment).
Config:      93,566 GDELT headlines (2023-08 → 2026-07) + RSS, all classified
             by claude-haiku into {relevant, event_type, assets, direction,
             magnitude, novelty, confidence}. Filters: relevant, novel,
             direction≠0, confidence ≥ medium; 6h story clustering → 10,144
             events. Signed forward returns at +1/4/24/72h vs bootstrap
             control. Bar: n≥20, |edge| > 2× round-trip (0.30%), CI excludes
             control.
Result:      NO TRADEABLE DRIFT. Short horizons are precisely null: at +1h,
             n=4,442 with edge +0.01% and CI ±0.02% — this does not merely
             fail to find an edge, it rules out anything above a few basis
             points. The decisive diagnostic: bullish and bearish events had
             statistically identical forward returns at every horizon
             (+72h: −0.570% vs −0.599%, difference CI [−0.21%, +0.28%]).
             The direction label carries no return information.
             One residual flag (regulation +72h, edge −0.31%) is the WRONG
             SIGN — regulation events underperform their control — and with
             40 bucket×horizon tests, ~2 flags at p≈0.05 are expected by
             chance. Not pursued.
Verdict:     KILL the event-driven sleeve. The classifier works (labels are
             good: it marked the fully-anticipated 2024 halving direction=0);
             the market simply prices this news before a retail pipeline can
             act. This is the null the plan gave ~10% odds, measured rather
             than assumed.
Bug found:   The first run reported five candidates, all at +72h. They were
             artifacts of comparing a SIGNED event metric against an UNSIGNED
             control: with a 2:1 bullish:bearish label mix in a falling
             market, flipping the bearish third mechanically produces a
             less-negative mean. The control is now direction-matched (signs
             drawn from the observed mix), which is what a control for a
             signed statistic has to be. Two regression tests pin it, and
             one of them caught a second bug in the fix itself (cycling a
             300-long direction list over 2,000 draws replays its head and
             skews the ratio — now sampled). Every false candidate vanished
             under the corrected control.
Caveats:     Hourly prices cover ~1 year of the 3-year news archive after the
             candle backfill, so +72h samples are thinner than +1h. Lexical
             dedupe may leave some story clusters. A different classification
             schema, or intraday-timestamped newswire data rather than GDELT's
             indexing lag, could still surface something — but not at these
             horizons with this pipeline.

## LAB-003 · 2026-07-26 · Multi-asset search: min-across-BTC/ETH/SOL

Hypothesis:  Requiring a candidate to score robustly on ALL THREE assets
             (train = mean Sharpe, robust = min across assets of worst
             ±25% neighbor) filters luck harder; survivors judged on the
             equal-weight basket over sealed holdouts.
Config:      Fresh campaign (own trial count, N=166): random 4×40 (seed 7) +
             12 Claude-generated candidates. Same costs/protocol.
Result:      The cross-asset bar bites: random's best robust fell from
             +0.097 (single-asset) to +0.062. Claude's per-trial edge held
             (median +0.040 vs −0.065; 58% vs 17% clearing +0.03). Two of
             Claude's LAB-002 single-asset stars re-scored here and dropped
             ~50% — they had quietly specialized to BTC.
             Basket holdout (B&H −49.6% CAGR, −64.3% MaxDD): all three
             finalists (all random-source) FAIL — DSR ≤ 0.004, p ≥ 0.27.
Verdict:     Third consecutive honest null from search. Combined with
             LAB-001/002: within this DSL space and regime, discoverable
             edge that survives trial-counting statistics does not exist.
             The lab's value is proven as a *rejection machine* — and the
             per-trial LLM advantage replicated out of sample (58%/17% here
             vs 77%/27% in LAB-002).
Caveats:     Report file: reports/lab_finalize_multi_2026-07-26.md. Same
             single-bear-regime holdout caveat as before, now cubed.
