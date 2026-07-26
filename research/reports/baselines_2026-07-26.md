# Trend baselines — 2026-07-26

Costs: 10 bps fee + 5 bps slippage per side. Walk-forward: 365-bar train, 90-bar test, param selection by train Sharpe.

## BTC — 1095 daily bars

- **Buy & hold**: CAGR    30.6%  Sharpe  0.81  Sortino  1.22  MaxDD  -53.0%  trades    1  exposure  100%

**In-sample (full history, best grid params — optimistic by construction):**

- `ma_cross` {'fast': 10, 'slow': 50}: CAGR    27.7%  Sharpe  0.91  Sortino  1.44  MaxDD  -40.0%  trades   27  exposure   53%
- `tsmom` {'lookback': 90}: CAGR    32.3%  Sharpe  1.01  Sortino  1.58  MaxDD  -25.1%  trades   28  exposure   54%
- `donchian` {'entry': 20}: CAGR    38.3%  Sharpe  1.28  Sortino  2.12  MaxDD  -27.5%  trades   39  exposure   41%

**Walk-forward out-of-sample (the number that counts):**

- `ma_cross`: CAGR   -23.7%  Sharpe -0.77  Sortino -1.06  MaxDD  -51.0%  trades   33  exposure   50%
  - vs B&H same span: Sharpe 0.19, MaxDD -53.0% → **loses to B&H Sharpe**
  - recent params: {'fast': 20, 'slow': 50}, {'fast': 20, 'slow': 100}, {'fast': 20, 'slow': 50}
- `tsmom`: CAGR   -17.6%  Sharpe -0.50  Sortino -0.71  MaxDD  -45.9%  trades   54  exposure   53%
  - vs B&H same span: Sharpe 0.19, MaxDD -53.0% → **loses to B&H Sharpe**
  - recent params: {'lookback': 30}, {'lookback': 90}, {'lookback': 180}
- `donchian`: CAGR     8.1%  Sharpe  0.44  Sortino  0.67  MaxDD  -25.4%  trades   27  exposure   40%
  - vs B&H same span: Sharpe 0.19, MaxDD -53.0% → **BEATS B&H Sharpe**
  - recent params: {'entry': 20}, {'entry': 20}, {'entry': 20}

## ETH — 1095 daily bars

- **Buy & hold**: CAGR     1.4%  Sharpe  0.35  Sortino  0.52  MaxDD  -67.6%  trades    1  exposure  100%

**In-sample (full history, best grid params — optimistic by construction):**

- `ma_cross` {'fast': 20, 'slow': 50}: CAGR    22.3%  Sharpe  0.69  Sortino  1.08  MaxDD  -47.2%  trades   19  exposure   46%
- `tsmom` {'lookback': 60}: CAGR    38.4%  Sharpe  0.96  Sortino  1.51  MaxDD  -39.2%  trades   40  exposure   50%
- `donchian` {'entry': 55}: CAGR    30.5%  Sharpe  0.88  Sortino  1.42  MaxDD  -42.1%  trades   14  exposure   39%

**Walk-forward out-of-sample (the number that counts):**

- `ma_cross`: CAGR     2.9%  Sharpe  0.28  Sortino  0.43  MaxDD  -45.7%  trades   16  exposure   44%
  - vs B&H same span: Sharpe -0.02, MaxDD -67.6% → **BEATS B&H Sharpe**
  - recent params: {'fast': 20, 'slow': 50}, {'fast': 20, 'slow': 100}, {'fast': 20, 'slow': 100}
- `tsmom`: CAGR     9.2%  Sharpe  0.42  Sortino  0.64  MaxDD  -42.8%  trades   26  exposure   44%
  - vs B&H same span: Sharpe -0.02, MaxDD -67.6% → **BEATS B&H Sharpe**
  - recent params: {'lookback': 30}, {'lookback': 30}, {'lookback': 180}
- `donchian`: CAGR     5.2%  Sharpe  0.32  Sortino  0.49  MaxDD  -31.6%  trades   10  exposure   28%
  - vs B&H same span: Sharpe -0.02, MaxDD -67.6% → **BEATS B&H Sharpe**
  - recent params: {'entry': 55}, {'entry': 55}, {'entry': 80}

## SOL — 1095 daily bars

- **Buy & hold**: CAGR    45.6%  Sharpe  0.86  Sortino  1.35  MaxDD  -76.3%  trades    1  exposure  100%

**In-sample (full history, best grid params — optimistic by construction):**

- `ma_cross` {'fast': 10, 'slow': 30}: CAGR    87.6%  Sharpe  1.36  Sortino  2.35  MaxDD  -48.6%  trades   36  exposure   51%
- `tsmom` {'lookback': 30}: CAGR    56.9%  Sharpe  1.04  Sortino  1.73  MaxDD  -58.2%  trades   67  exposure   52%
- `donchian` {'entry': 20}: CAGR   112.1%  Sharpe  1.70  Sortino  3.18  MaxDD  -34.9%  trades   40  exposure   38%

**Walk-forward out-of-sample (the number that counts):**

- `ma_cross`: CAGR   -23.2%  Sharpe -0.30  Sortino -0.44  MaxDD  -52.4%  trades   30  exposure   46%
  - vs B&H same span: Sharpe -0.17, MaxDD -76.3% → **loses to B&H Sharpe**
  - recent params: {'fast': 10, 'slow': 50}, {'fast': 10, 'slow': 30}, {'fast': 20, 'slow': 100}
- `tsmom`: CAGR   -43.6%  Sharpe -0.70  Sortino -1.00  MaxDD  -72.5%  trades   48  exposure   48%
  - vs B&H same span: Sharpe -0.17, MaxDD -76.3% → **loses to B&H Sharpe**
  - recent params: {'lookback': 30}, {'lookback': 180}, {'lookback': 180}
- `donchian`: CAGR    10.1%  Sharpe  0.44  Sortino  0.72  MaxDD  -35.1%  trades   30  exposure   32%
  - vs B&H same span: Sharpe -0.17, MaxDD -76.3% → **BEATS B&H Sharpe**
  - recent params: {'entry': 20}, {'entry': 20}, {'entry': 20}
