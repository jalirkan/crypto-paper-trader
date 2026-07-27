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

## Risk overlays (EXP-002/003/004)

```powershell
python -m research.backtest.run_overlays     # vol target / F&G gate / stablecoin gate
```

Verdicts in `experiments.md`: vol targeting KEPT, both flow gates KILLED.

## LLM event pipeline

```powershell
python -m collectors.gdelt_backfill --from 2023-08-01   # ~25 min, free, resumable
python -m research.events.classify --limit 500          # needs ANTHROPIC_API_KEY
python -m research.events.study                         # drift analysis + report
```

GDELT backfills 3 years of crypto headlines (no key). The classifier labels
them with claude-haiku (~$0.10–0.25 per 1,000 headlines — start with a
`--limit` to gauge quality before a full run). The study engine then measures
post-event drift vs bootstrap controls; buckets flagged CANDIDATE clear the
pre-registered tradeability bar.

## AI Research Lab (`research/lab/`)

Autonomous strategy discovery with statistical honesty: a JSON strategy DSL
(no code execution), an interpreter with strict no-look-ahead timing, a
generational search loop (random baseline or Claude-guided), and a **sealed
holdout** judged by deflated Sharpe (Bailey–López de Prado, corrected for
every trial ever run) plus stationary-bootstrap p-values.

```powershell
python -m research.lab.run --generator random --generations 6 --pop 50
python -m research.lab.run --generator claude --generations 3 --pop 20   # needs ANTHROPIC_API_KEY
python -m research.lab.run --finalize        # spends the holdout — judgement day
```

LAB-001 (ledger): 274 random candidates, best train Sharpe looked strong,
sealed holdout + DSR rejected everything — the null baseline Claude-guided
search now has to beat.

## Coming next (per RESEARCH_PLAN.md)

- LAB-002: Claude-guided generation vs the random-search null
- Funding-harvest sim (needs VPS funding backfill)
- Public read-only deploy, tips widget, research page
