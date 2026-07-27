# LAB finalize — 2026-07-26 (BTC+ETH+SOL basket)

Trials counted: 166 · holdout bars: 365

Benchmark (B&H holdout): Sharpe/bar n/a, CAGR -49.6%, MaxDD -64.3%

## 0d38ed392f580f2e — **FAIL**
- candidate: `{"entry": {"a": {"op": "close"}, "b": {"n": 14, "of": {"op": "close"}, "op": "sma"}, "op": "cross_above"}, "exit": {"a": {"n": 200, "of": {"n": 100, "of": {"op": "close"}, "op": "ema"}, "op": "roll_max"}, "b": {"n": 7, "of": {"op": "close"}, "op": "sma"}, "op": "lt"}}`
- train SR/bar +0.0874 (robust +0.0616)
- holdout: CAGR -43.3%, Sharpe -0.95, MaxDD -56.3%, trades None
- DSR 0.004 (SR0 threshold +0.0909 from 166 trials)
- bootstrap p vs B&H: 0.312

## 5fad373cf3faa88e — **FAIL**
- candidate: `{"entry": {"a": {"n": 7, "of": {"op": "close"}, "op": "rsi"}, "b": {"op": "const", "v": 70}, "op": "gt"}, "exit": {"a": {"op": "close"}, "b": {"n": 40, "of": {"op": "close"}, "op": "sma"}, "op": "lt"}}`
- train SR/bar +0.0797 (robust +0.0614)
- holdout: CAGR -23.7%, Sharpe -1.07, MaxDD -27.4%, trades None
- DSR 0.003 (SR0 threshold +0.0909 from 166 trials)
- bootstrap p vs B&H: 0.269

## 349ef8158bfb14a4 — **FAIL**
- candidate: `{"entry": {"a": {"op": "close"}, "b": {"n": 14, "of": {"op": "close"}, "op": "sma"}, "op": "cross_above"}, "exit": {"a": {"n": 200, "of": {"n": 100, "of": {"op": "close"}, "op": "ema"}, "op": "roll_max"}, "b": {"n": 5, "of": {"op": "close"}, "op": "sma"}, "op": "lt"}}`
- train SR/bar +0.0880 (robust +0.0598)
- holdout: CAGR -43.2%, Sharpe -0.95, MaxDD -55.5%, trades None
- DSR 0.004 (SR0 threshold +0.0909 from 166 trials)
- bootstrap p vs B&H: 0.310

