# Crypto Paper Trader

A crypto paper-trading app **and** the quantitative research programme that
tried to find an edge for it — including the part most projects leave out:
what happened when the edges didn't survive testing.

**Six pre-registered experiments. Six honest nulls.** Every kill criterion was
written before the run; every failed idea is still in the ledger, with its
numbers. The one survivor — Donchian breakout with volatility targeting — is
recorded as a *candidate under forward paper trading*, not a strategy that
works. Simulated money throughout; nothing here is financial advice.

| | |
|---|---|
| **The experiment ledger** | [`research/experiments.md`](./research/experiments.md) — the honest core |
| **How the work was split between two AI agents** | [`AGENTS.md`](./AGENTS.md) |
| **Research method and remaining edge paths** | [`RESEARCH_PLAN.md`](./RESEARCH_PLAN.md) |

### What the six experiments found

- **EXP-001** Trend baselines: MA-cross and time-series momentum collapse out
  of sample; Donchian survives walk-forward on BTC/ETH/SOL at roughly half the
  drawdown of buy-and-hold. **The only survivor.**
- **EXP-002/3/4** Risk overlays: volatility targeting kept; Fear & Greed and
  stablecoin-flow gates killed.
- **LAB-001/2/3** An autonomous strategy-search lab with a sealed holdout and
  deflated-Sharpe statistics: 274 random candidates, then LLM-generated ones,
  then a multi-asset campaign. Every finalist rejected. Along the way it
  measured that an LLM hypothesis engine is ~3× more efficient *per trial*
  than random search — and that this still isn't enough to beat trial-counting
  statistics.
- **EXP-005** LLM event study: 93,566 news headlines classified, 10,144 events.
  No tradeable drift at any horizon; at +1h the interval is ±0.02%, which
  *rules out* an edge rather than merely failing to find one. The first run
  reported five candidates — all artifacts of comparing a signed metric to an
  unsigned control. Fixing that erased them.
- **EXP-006** Delta-neutral funding harvest: ~5% APR across three years, but
  the per-year decomposition shows +10–12% in 2024 and ~0% since. The premium
  is real and already gone.

The through-line: the machinery repeatedly caught its own mistakes — a bad
control, then a bug in the fix for that control, then a point estimate about
to be reported without its interval. That is the actual deliverable.

## Features

- **Live market data** — top 10 coins via CoinGecko (free, no key), proxied through API routes with server-side caching to stay under rate limits
- **Manual paper trading** — start with $100k, buy/sell at live prices, track holdings, average cost, realized/unrealized P&L, and an equity curve
- **Strategy bots** — attach a strategy (SMA Crossover, RSI Mean Reversion, MACD Momentum) to a coin with a budget; it evaluates 5-minute intraday data every ~90s and trades automatically while the tab is open
- **AI advisor (optional)** — sends your portfolio, live prices, and bot signals to Claude; returns an assessment, trade suggestions with rationale (one-click apply), bot tuning ideas, and risk notes
- **Persistence** — portfolio, trades, and bots survive reloads via localStorage

## Quick start

Requires Node.js ≥ 18.18 ([nodejs.org](https://nodejs.org)).

```bash
npm install
npm run dev
```

Open http://localhost:3000.

### Enable the AI advisor (optional)

```bash
copy .env.example .env.local   # then add your key from console.anthropic.com
```

Everything else works without a key.

## Architecture

```
app/
  page.tsx            → renders Dashboard
  api/prices/         → CoinGecko markets proxy, 60s cache
  api/history/        → CoinGecko market_chart proxy, 5min cache
  api/advise/         → Claude advisor endpoint (needs ANTHROPIC_API_KEY)
lib/
  indicators.ts       → SMA, EMA, RSI (Wilder), MACD — pure functions
  strategies.ts       → strategy definitions: params + evaluate() → signal
  store.tsx           → portfolio reducer + React context + localStorage
  hooks.ts            → price polling, bot runner loop
components/           → dashboard UI (tables, charts, modals — canvas charts, no chart lib)
```

Design notes:

- Strategies are **edge-triggered**: they fire on a fresh crossover/threshold event, not continuously, so bots don't re-buy every tick
- Bots own their `positionQty` but share portfolio cash; the reducer validates every trade (cash, quantity clamps) so invalid trades are no-ops
- The reducer and indicators are pure functions — unit-testable without a browser

## Research pipeline (Phase 1 live)

The quant research layer — architecture, data sources, strategy hypotheses with kill criteria, evaluation protocol, and honest odds — lives in [RESEARCH_PLAN.md](./RESEARCH_PLAN.md).

Phase 1 (data collection) is implemented: dependency-free Python collectors archive candles, funding rates, news, Fear & Greed, and stablecoin flows into SQLite. See [research/README.md](./research/README.md) to start the backfill and the collection loop.

The backtest layer (`research/backtest/`) adds a cost-modeled long/flat engine with walk-forward validation — first results in [research/experiments.md](./research/experiments.md).

## Lightning tip jar (`lightning/`)

A self-hosted donation stack on LND: custom LNURL-pay + Lightning Address implementation (LUD-06/12/16) against LND's REST API, invoice-only macaroon isolation (the web service can create invoices but never spend), SQLite settlements ledger, and a public `/api/tips` endpoint. Try it with zero infrastructure: `python -m lightning.service --demo`. Deployment (signet first, then mainnet) is scripted in [deploy/vps/README.md](./deploy/vps/README.md).

### v2 ideas (superseded by the research plan)

1. **Backtesting engine** — replay 90 days of history through strategies; report return, drawdown, win rate vs buy-and-hold
2. **AI parameter tuning loop** — Claude proposes parameter changes, backtester scores them, keep what wins
3. **AI-generated strategies** — Claude emits strategy configs (indicator combos + thresholds) evaluated in the backtester before going live
4. **Regime detection** — classify trending vs ranging markets and switch strategies accordingly
5. **Scheduled runs** — move the bot loop server-side (cron) so it trades without the tab open

## Execution engine (`execution/`)

The OMS that will eventually trade the live micro-capital — built and
chaos-tested long before it's allowed to. Write-ahead journaling (every order
hits SQLite before the wire), lost-ack semantics (timeouts become UNKNOWN,
resolved only by querying the exchange with idempotent client ids),
duplicate-fill dedupe, crash-recovery reconciliation, and a kill switch that
freezes on position drift rather than "fixing" it by trading. Tested against
a scripted chaos-mode mock exchange; there is deliberately no real-exchange
adapter until the forward-paper gate opens. Demo:
`python -m execution.runner --mock`.

## Deploying the public site (Vercel)

The app deploys to Vercel with **no configuration and no backend**. All three
environment variables below are optional; the site is designed for the case
where none of them is set, because that is how it is currently deployed.

| Variable | Effect when set | Behaviour when absent |
|---|---|---|
| `SIGNALS_URL` | Base URL of the Python signal service — Caddy routes `/api/signals` + `/api/forward` to it | Live position and forward-paper stats are replaced by an explanation of what they are and where they come from |
| `TIPS_URL` | Base URL of the Lightning tip jar (`/api/tips`) | Tip jar panel describes the stack instead of showing a payment address |
| `ANTHROPIC_API_KEY` | Enables the narrator and the AI advisor (mind the spend) | Narrator button reports the missing key; everything else is unaffected |

**Verified, not assumed** — a production build with all three unset:
`/research` returns 200 with the full ledger rendered into the server HTML,
`/api/experiments` returns 200, and `/api/signals`, `/api/tipjar` and
`/api/narrate` return 503 which the UI handles as explanatory panels rather
than error states.

Two things make this work rather than merely degrade:

- The `/research` page is **statically prerendered**, so the experiment ledger
  is baked into the HTML at build time — it renders with no backend, no
  database, and JavaScript disabled. `next.config.mjs` traces
  `research/experiments.md` into the bundle; without that the ledger 404s on
  Vercel while working perfectly in local dev.
- The trading dashboard is entirely client-side: each visitor gets their own
  $100k paper portfolio in localStorage, with live prices proxied through the
  CoinGecko routes, which need no key.

CI runs the production build on every push.

### Dependency advisories

`npm audit` reports 3 high-severity advisories in Next.js's own transitive
dependencies (`postcss`, `sharp`/libvips). There is currently no Next.js
release that resolves them — the advisory range covers every version through
16.3.0-preview, and `npm audit fix --force` "resolves" it by downgrading to
next@9.3.3, which is not a fix. Noted here rather than hidden: the postcss
issues require processing attacker-supplied CSS, and the libvips CVEs reach
this app only through `next/image`, which it does not use.

## Known v1 limitations

- Bots only run while the app is open in a browser tab
- Fills are instant at spot price — no slippage or fees modeled
- CoinGecko free tier can rate-limit briefly with many bots; the app serves cached data when that happens
