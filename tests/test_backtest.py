"""Backtest engine tests — synthetic data, no archive needed.

The look-ahead test is the one that matters most: it proves a signal cannot
earn the bar that produced it.
"""

import math
import unittest

from research.backtest import engine, metrics
from research.backtest.strategies import donchian, ma_cross, tsmom
from research.backtest.walkforward import walk_forward


def trend_series(n=500, start=100.0, drift=0.01):
    """Deterministic regimes: long uptrend, gradual 60-bar bear (~-60%), recovery.

    The bear is gradual on purpose — a trend follower can react to a multi-bar
    decline (unlike a one-bar gap, which nothing long-only can dodge).
    """
    closes = [start]
    bear_start, bear_len = n // 2, 60
    for i in range(1, n):
        if bear_start <= i < bear_start + bear_len:
            closes.append(closes[-1] * 0.985)  # -1.5%/bar, ≈ -60% cumulative
        else:
            closes.append(closes[-1] * (1 + drift * math.sin(i / 40) ** 2 + 0.002))
    return closes


class TestEngine(unittest.TestCase):
    def test_buy_and_hold_matches_price_ratio_when_free(self):
        closes = [100.0, 110.0, 99.0, 120.0]
        res = engine.run(closes, [1.0] * 4, fee_bps=0, slip_bps=0)
        self.assertAlmostEqual(res.equity()[-1], 120.0 / 100.0, places=12)

    def test_costs_reduce_returns_monotonically(self):
        closes = trend_series(300)
        w = ma_cross(closes, 5, 20)
        eq = [
            engine.run(closes, w, fee_bps=f, slip_bps=0).equity()[-1]
            for f in (0, 10, 50, 200)
        ]
        self.assertTrue(eq[0] > eq[1] > eq[2] > eq[3])

    def test_flat_strategy_earns_nothing_and_pays_nothing(self):
        closes = trend_series(100)
        res = engine.run(closes, [0.0] * len(closes))
        self.assertEqual(res.equity()[-1], 1.0)
        self.assertEqual(res.fees_paid, 0.0)

    def test_no_lookahead_cheater_gains_nothing(self):
        """A 'strategy' that goes long exactly on big up-bars (same-bar knowledge)
        must NOT capture those bars — the engine shifts execution to the next bar.
        """
        # Alternating: big up bar, big down bar. Cheater is long only on up bars.
        closes = [100.0]
        for i in range(60):
            closes.append(closes[-1] * (1.10 if i % 2 == 0 else 0.92))
        rets = engine.bar_returns(closes)
        cheat_w = [0.0] + [1.0 if r > 0 else 0.0 for r in rets]  # decided same-bar

        res = engine.run(closes, cheat_w, fee_bps=0, slip_bps=0)
        # If the engine leaked, the cheater would earn every +10% bar: 1.1^30 ≈ 17.4x.
        # Correctly shifted one bar, it instead holds through every -8% bar:
        # exactly 0.92^30. Pinning the exact value proves the one-bar shift.
        self.assertAlmostEqual(res.equity()[-1], 0.92**30, places=10)
        self.assertLess(res.equity()[-1], 1.0)

    def test_weight_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            engine.run([1.0, 2.0], [1.0])


class TestMetrics(unittest.TestCase):
    def test_max_drawdown_known_sequence(self):
        # 100 → 120 → 60 → 90: worst peak-to-trough is 60/120 - 1 = -50%
        rets = [0.20, -0.50, 0.50]
        self.assertAlmostEqual(metrics.max_drawdown(rets), -0.50, places=12)

    def test_sharpe_signs(self):
        up = [0.01, 0.012, 0.008, 0.011] * 20
        down = [-0.01, -0.012, -0.008, -0.011] * 20
        self.assertGreater(metrics.sharpe(up), 0)
        self.assertLess(metrics.sharpe(down), 0)
        self.assertEqual(metrics.sharpe([0.01]), 0.0)  # too short → 0

    def test_cagr_doubling(self):
        rets = [2.0 ** (1 / 365) - 1] * 365  # doubles in exactly one year
        self.assertAlmostEqual(metrics.cagr(rets), 1.0, places=6)

    def test_summarize_turnover_counts(self):
        w = [0.0, 1.0, 1.0, 0.0, 1.0]
        s = metrics.summarize([0.0] * 5, w)
        self.assertEqual(s["trades"], 3)  # 0→1, 1→0, 0→1


class TestStrategies(unittest.TestCase):
    def test_ma_cross_long_in_uptrend_flat_in_downtrend(self):
        up = [100 * 1.01**i for i in range(120)]
        down = [100 * 0.99**i for i in range(120)]
        self.assertEqual(ma_cross(up, 5, 20)[-1], 1.0)
        self.assertEqual(ma_cross(down, 5, 20)[-1], 0.0)

    def test_tsmom_warmup_flat(self):
        closes = [100.0] * 50
        self.assertEqual(sum(tsmom(closes, 60)), 0.0)  # lookback > data → all flat

    def test_donchian_enters_on_breakout_exits_on_breakdown(self):
        flat = [100.0] * 60
        breakout = flat + [110.0, 112.0, 114.0]
        w = donchian(breakout, entry=20)
        self.assertEqual(w[-1], 1.0)
        breakdown = breakout + [90.0]
        self.assertEqual(donchian(breakdown, entry=20)[-1], 0.0)

    def test_trend_strategy_cuts_crash_drawdown(self):
        closes = trend_series(500)
        bh = engine.buy_and_hold(closes, 0, 0)
        w = ma_cross(closes, 10, 30)
        strat = engine.run(closes, w, 10, 5)
        self.assertGreater(strat.stats["max_dd"], bh.stats["max_dd"])  # less negative


class TestWalkForward(unittest.TestCase):
    def test_runs_and_is_out_of_sample_sized(self):
        closes = trend_series(700)
        wf = walk_forward(closes, "tsmom", train_bars=200, test_bars=50)
        self.assertGreater(len(wf["windows"]), 5)
        self.assertEqual(wf["oos"]["days"], len(wf["oos_returns"]))
        # OOS covers everything after the first train window
        self.assertEqual(wf["oos"]["days"], 700 - 200)
        # benchmark measured over the same span
        self.assertEqual(wf["benchmark_oos"]["days"], wf["oos"]["days"])


if __name__ == "__main__":
    unittest.main()
