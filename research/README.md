# Research Layer — Phase 1: Data Collection

The collectors build the historical archive everything else depends on. They are
**dependency-free Python** (stdlib only) — no venv or pip needed for this phase.

## Setup (Windows)

Install Python 3.10+ if you don't have it:

```powershell
winget install Python.Python.3.12
```

(Re-open the terminal afterwards so `python` is on PATH.)

## One-time backfill (~10–20 min)

From the repo root:

```powershell
python -m collectors.backfill
```

Pulls into `data/archive.db` (SQLite, gitignored):

- 3 years of daily + 1 year of hourly candles, 10 coins (Binance public data mirror, Coinbase fallback)
- 3 years of perp funding rates for BTC/ETH/SOL (may fail on US residential IPs — geo-blocked; fine from a VPS, and non-fatal)
- Full Fear & Greed index history (2018→)
- Full stablecoin supply history (DefiLlama)

Safe to re-run anytime; it resumes from where it stopped.

## Ongoing collection (the archive clock)

```powershell
python -m collectors.run --loop
```

Every 15 min: news from CoinDesk/CoinTelegraph/The Block/Decrypt RSS, fresh
candles, funding, Fear & Greed, stablecoin supply. **News cannot be backfilled**
— the social/news archive only exists from the day this starts running, which
is why it ships before any strategy code.

Run it whenever your PC is on (or via Task Scheduler at logon). The week-6
plan moves this to a ~$5/mo VPS for 24/7 coverage — until then, gaps are
recorded honestly in the `collector_runs` table.

## Tests (no network needed)

```powershell
python -m unittest
```

## Archive health check

```powershell
python -c "import sqlite3; c=sqlite3.connect('data/archive.db'); [print(f'{t}: {c.execute(f\"SELECT COUNT(*) FROM {t}\").fetchone()[0]} rows') for t in ('candles','funding','news','fear_greed','stablecoins')]"
```

## Backtesting + live signals

```powershell
python -m research.backtest.run              # trend baselines vs buy-and-hold
python -m research.signal_service            # live strategy state on :8091
```

The signal service powers the dashboard's narrator panel (run it alongside
`npm run dev`). The collector loop records the strategy's daily weights into
the `forward_paper` table — that immutable ledger is the live track record,
started 2026-07-26. First backtest findings: `experiments.md` (EXP-001).

## Coming next (per RESEARCH_PLAN.md)

- Weeks 4–5: LLM news classifier + event studies, funding-harvest sim
- Weeks 6–8: public read-only deploy, tips widget, VPS signal service
