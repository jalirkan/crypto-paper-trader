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

*(no experiments yet — backtester lands in weeks 2–3)*
