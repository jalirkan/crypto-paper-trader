# Research Plan: From Toy Trader to Testable Edge

**Goal:** a system that beats buy-and-hold BTC on a *risk-adjusted* basis — similar returns with materially smaller drawdowns — proven net of realistic costs, out-of-sample, then live in forward paper trading. Simulated money throughout. Nothing here is financial advice.

**Constraints:** individual-level resources, ~$15/month budget, Python research backend + existing Next.js dashboard.

---

## 1. Honest odds (agreed upfront)

| Outcome | Rough odds | Notes |
|---|---|---|
| Positive paper returns in a bull market | High | Market beta, proves nothing |
| Beat B&H BTC risk-adjusted (our target) | ~40–50% | Trend-following's historical delivery |
| Beat B&H BTC on absolute returns | ~15–25% | Bull runs favor holding |
| LLM/news layer adds alpha net of costs | ~10% | Most likely: we rigorously prove it doesn't |
| Delta-neutral funding sleeve earns positive yield | ~60–75% | Yield, not directional alpha |
| Persistent, scalable alpha | <5% | Institutional territory |

Even at zero alpha, the deliverables are real: a professional-grade research pipeline (portfolio piece), quant skills, and a proprietary news/social archive that appreciates daily.

**Our three actual edges:**

1. **Evaluation discipline.** Most retail bots die from dishonest backtests, not bad ideas. Rigor is rare and free.
2. **The archive.** Live news/social/funding data is free; *historical* is paywalled. Every day the collectors run, we own something money can't easily buy retroactively. Start collecting before anything else.
3. **Cheap LLM classification.** Structured event labeling at ~$5–10/mo was impossible for individuals until ~2024. Most retail competition uses it sloppily.

---

## 2. Non-negotiable research rules

1. Every strategy is measured against **buy-and-hold BTC** and **flat cash**. Always.
2. All results **net of costs**: 10 bps taker fee + slippage model + spread. If a strategy dies from fees, it was never alive.
3. **Time-ordered validation only.** Train → validate → test in chronological walk-forward. No shuffling, no peeking.
4. **Few parameters.** Every added parameter is a chance to overfit. Prefer strategies with 1–3.
5. **Experiments ledger.** Every backtest run is logged (`research/experiments.md`): hypothesis, config, result, verdict. Failed ideas stay visible — that's how we avoid re-testing until something falsely passes.
6. **Kill criteria are written before testing** (per strategy, below). Ideas that fail get killed, not tuned until they pass.
7. **No "profitable" claim without ≥3 months of forward paper trading** on signals generated live. The forward period is the only test that can't be overfit.

---

## 3. Architecture

```
┌─────────────────────────── VPS (~$5/mo, 24/7) ───────────────────────────┐
│  collectors/ (Python, cron)                                              │
│    prices · funding · open interest · news · reddit · fear&greed · flows │
│                              ↓                                           │
│                    SQLite (data/archive.db)                              │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ↓ (rsync/litestream copy to dev machine)
   research/ (Python)                      signal service (FastAPI)
     backtest engine                         GET /signals  /sleeves  /events
     event studies                                   ↓
     strategy notebooks              Next.js dashboard (existing app)
     experiments ledger                new: Research page — sleeve P&L vs BTC,
                                       live signals, classified event feed
```

- **Python owns**: data collection, backtesting, signal generation, the canonical paper ledger for automated sleeves.
- **Next.js owns**: visualization + the existing manual/interactive paper trader (kept as-is — it becomes the human sandbox).
- SQLite until it hurts (it won't for years at this volume). One file = trivial backup.

Repo layout: existing app stays at root; new `research/` (Python, own venv + requirements.txt), `collectors/`, `data/` (gitignored).

---

## 4. Data sources (Phase 1 — build first, run forever)

| Source | Data | Cadence | Cost |
|---|---|---|---|
| Binance/Coinbase public APIs | OHLCV candles, full history backfill | 1m/1h/1d | Free |
| Binance + Bybit public APIs | Funding rates, open interest, basis | 5–15 min | Free |
| CryptoPanic API | Aggregated crypto news + community votes | 15 min | Free tier |
| RSS: CoinDesk, CoinTelegraph, The Block, Decrypt | News headlines + timestamps | 15 min | Free |
| Alpaca news API (free account) | Real-time Benzinga news websocket | Streaming | Free |
| Reddit API | r/CryptoCurrency, r/Bitcoin — posts, scores, comment velocity | 30 min | Free tier |
| alternative.me | Fear & Greed index | Daily | Free |
| DefiLlama API | Stablecoin issuance, TVL, chain flows | Hourly | Free |
| Etherscan free tier | Whale/exchange wallet movements | Hourly | Free |

**Deliberately excluded for now:** X/Twitter. Scraping violates ToS and breaks constantly; the official API is $200/mo. Revisit only if the event pipeline shows promise on free sources (decision gate in §8). Farcaster (open protocol, free) is the interim social alternative.

Priority order matters: **news/social collectors ship in week 1** even though they're used in week 4+ — candles can be backfilled anytime; social/news cannot.

---

## 5. Strategy families: hypotheses & kill criteria

### 5.1 Trend / momentum (the core)

- **Hypothesis:** crypto exhibits medium-term autocorrelation; systematic trend capture retains most upside while sidestepping deep drawdowns.
- **Implementations:** MA cross (e.g., 20/100), Donchian channel breakout, time-series momentum (sign of trailing N-day return), each with volatility targeting. BTC + ETH first, top-10 alts later. Daily bars — low turnover keeps fees negligible.
- **Kill criteria:** fails to beat B&H Sharpe across walk-forward windows, or edge exists only in one narrow parameter island.
- This family also sets **the bar**: nothing fancier graduates unless it beats the best boring trend baseline.

### 5.2 LLM news/event trading (the experiment)

- **Hypothesis:** slow-moving *fundamental* news (regulation, ETF flows, hacks, listings) produces multi-hour drift that survives costs, and Claude can classify relevance/direction/magnitude/novelty reliably enough to isolate those events.
- **Pipeline:** ingest → dedupe (embedding or fuzzy-hash) → Claude Haiku structured classification `{event_type, assets, direction, magnitude, novelty, confidence}` → **event study**: cumulative abnormal returns at +1h/+4h/+24h/+72h vs matched control windows, bucketed by event class.
- **Graduation rule:** a class becomes a signal only when drift CI excludes zero, n ≥ ~100 events, and drift > 2× round-trip cost.
- **Kill criteria:** after 3 months of archive, no event class clears the bar → layer is demoted to a dashboard feature (still a great portfolio artifact), not a trading input.
- **Cost:** ~200–400 deduped items/day × ~700 tokens ≈ $5–10/mo on Haiku (halve with the batch API).

### 5.3 Funding-rate / delta-neutral (the probable profit)

- **Hypothesis:** perp funding paid by crowded longs is harvestable: long spot + short perp, collect funding while price-neutral.
- **Implementation:** simulate both legs with realistic funding accrual (8h epochs), entry when annualized funding > threshold (e.g., >10%), exit on flip/decay. Requires adding perp mechanics to the paper engine (engineering item, week 4–5).
- **Kill criteria:** simulated net APR < 5% sustained, or returns exist only during brief euphoria spikes too rare to matter.
- Also doubles as a **crowding sensor**: extreme funding is itself a contrarian input to §5.1's regime filter.

### 5.4 On-chain / flow signals (the filter, not the trigger)

- **Hypothesis:** stablecoin net issuance and exchange netflows lead medium-term risk appetite — useful as *regime filters* (size up/down) rather than entry signals.
- **Kill criteria:** no measurable improvement when layered onto the trend sleeve's walk-forward results.

---

## 6. Portfolio & risk layer

- Each sleeve is volatility-targeted, then combined with caps (no sleeve > 40% of risk budget).
- Global kill-switch: system drawdown > 15% → new entries paused, review triggered.
- Regime filter: trend sleeve's state (+ funding extremes) gates how aggressive other sleeves may be.
- Metrics reported everywhere: CAGR, max drawdown, Sharpe, Sortino, hit rate, turnover, fees paid — always side-by-side with B&H BTC.

---

## 7. Evaluation protocol

1. **Backtest** (2+ years, costs on) → experiments ledger entry.
2. **Walk-forward:** rolling train/test windows; parameters chosen only on past data; report the *stitched out-of-sample* equity curve, nothing else.
3. **Robustness:** parameter-neighborhood check (edge must survive ±25% parameter wiggle), bootstrap CIs on Sharpe, sanity check on sub-periods (bull/bear/chop).
4. **Forward paper:** ≥3 months live signals into the paper ledger. Track realized-vs-backtest slippage and signal latency.
5. **Graduation:** only forward-paper survivors count as "working." That's the claim we stand behind — no earlier.

---

## 8. Roadmap

| Weeks | Milestone |
|---|---|
| 1 | Repo restructure (`research/`, `collectors/`), Python env, SQLite schemas. **All collectors live** (news/social first — the archive clock starts now). Candle backfill: 3+ years daily, 1+ year hourly. VPS deployed. |
| 2–3 | Backtest engine with cost model + walk-forward harness. Baselines: B&H, MA cross, Donchian, TSMOM, vol targeting. First experiments-ledger entries. First honest answer: *does trend beat holding, net of fees?* |
| 4–5 | LLM classifier + event-study harness running over the growing archive. Perp/funding mechanics in paper engine; funding-harvest simulation. |
| 6–8 | Risk layer + sleeve combination. FastAPI signal service. Dashboard Research page: sleeve equity curves vs BTC, live signals, classified event feed. Forward paper period officially starts. |
| Ongoing (monthly) | Review ritual: ledger review, sleeve report vs benchmarks, kill/keep decisions. **Decision gates:** X API ($200/mo) only if free-source event studies show near-significant drift. Real-money micro-pilot (~$100, purely to calibrate true slippage) only after a sleeve survives 3 months of forward paper — optional, your call entirely. |

## 9. Budget

| Item | $/mo |
|---|---|
| VPS (Hetzner/equivalent, runs collectors 24/7) | ~$5 |
| Claude API (Haiku classification, batched) | ~$5–10 |
| Everything else (all data sources above) | $0 |
| **Total** | **~$10–15** |

$0 fallback: run collectors on your PC via Task Scheduler — workable, but archive gaps whenever it sleeps.

---

## 10. What success looks like in 6 months

Realistic good outcome: a trend sleeve with a stitched out-of-sample record showing B&H-comparable returns at roughly half the drawdown, a funding sleeve accruing modest simulated yield, an event-study writeup with real statistical hygiene (whatever its verdict), months of forward paper track record, and an archive nobody else has. If the LLM layer finds tradeable drift — bonus, and a genuinely novel individual-scale result. If not, we'll know *why*, with confidence intervals.
