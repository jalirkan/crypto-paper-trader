# Crypto Paper Trader

Paper-trade crypto with live market data, automated strategy bots, and an optional Claude-powered AI advisor. Built with Next.js 15 + TypeScript, zero runtime dependencies beyond React. Simulated money only — educational project, not financial advice.

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

### v2 ideas (superseded by the research plan)

1. **Backtesting engine** — replay 90 days of history through strategies; report return, drawdown, win rate vs buy-and-hold
2. **AI parameter tuning loop** — Claude proposes parameter changes, backtester scores them, keep what wins
3. **AI-generated strategies** — Claude emits strategy configs (indicator combos + thresholds) evaluated in the backtester before going live
4. **Regime detection** — classify trending vs ranging markets and switch strategies accordingly
5. **Scheduled runs** — move the bot loop server-side (cron) so it trades without the tab open

## Known v1 limitations

- Bots only run while the app is open in a browser tab
- Fills are instant at spot price — no slippage or fees modeled
- CoinGecko free tier can rate-limit briefly with many bots; the app serves cached data when that happens
