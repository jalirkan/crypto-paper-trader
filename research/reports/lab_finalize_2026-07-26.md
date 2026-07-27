# LAB finalize — 2026-07-26 (BTC)

Trials counted: 274 · holdout bars: 365

Benchmark (B&H holdout): Sharpe/bar n/a, CAGR -44.7%, MaxDD -53.0%

## 8844fafea110477e — **FAIL**
- candidate: `{"entry": {"a": {"op": "close"}, "b": {"n": 40, "of": {"op": "close"}, "op": "roll_max"}, "op": "cross_below"}, "exit": {"a": {"n": 37, "of": {"op": "close"}, "op": "rsi"}, "b": {"op": "const", "v": 75}, "op": "gt"}}`
- train SR/bar +0.0983 (robust +0.0968)
- holdout: CAGR -44.7%, Sharpe -1.16, MaxDD -53.0%, trades 1
- DSR 0.000 (SR0 threshold +0.1218 from 274 trials)
- bootstrap p vs B&H: 1.000

## 732571a34a9fd238 — **FAIL**
- candidate: `{"entry": {"a": {"n": 45, "of": {"op": "close"}, "op": "rsi"}, "b": {"op": "const", "v": 40}, "op": "gt"}, "exit": {"a": {"n": 14, "of": {"op": "close"}, "op": "roll_max"}, "b": {"n": 150, "of": {"op": "close"}, "op": "sma"}, "op": "cross_below"}}`
- train SR/bar +0.0932 (robust +0.0931)
- holdout: CAGR -43.5%, Sharpe -1.11, MaxDD -52.0%, trades 7
- DSR 0.000 (SR0 threshold +0.1218 from 274 trials)
- bootstrap p vs B&H: 0.108

## bc9ddf2d1e534603 — **FAIL**
- candidate: `{"entry": {"a": {"n": 45, "of": {"op": "close"}, "op": "rsi"}, "b": {"op": "const", "v": 40}, "op": "gt"}, "exit": {"a": {"n": 30, "of": {"op": "close"}, "op": "rsi"}, "b": {"op": "const", "v": 75}, "op": "gt"}}`
- train SR/bar +0.0933 (robust +0.0925)
- holdout: CAGR -44.7%, Sharpe -1.16, MaxDD -53.0%, trades 1
- DSR 0.000 (SR0 threshold +0.1218 from 274 trials)
- bootstrap p vs B&H: 1.000

