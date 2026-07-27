"""Overlay tests — no-look-ahead, gating semantics, exposure-only-shrinks."""

import math
import unittest

from research.backtest import overlays


def wavy(n=200, vol=0.01):
    closes = [100.0]
    for i in range(1, n):
        closes.append(closes[-1] * (1 + vol * math.sin(i * 1.7)))
    return closes


class TestVolTarget(unittest.TestCase):
    def test_never_increases_exposure(self):
        closes = wavy(300, vol=0.06)  # very volatile → heavy scaling
        w = [1.0] * 300
        out = overlays.vol_target(closes, w)
        self.assertTrue(all(o <= i + 1e-12 for o, i in zip(out, w)))
        self.assertTrue(any(o < 1.0 for o in out[40:]))  # actually scales down

    def test_calm_market_unchanged(self):
        closes = [100 * 1.0005**i for i in range(300)]  # ~1% ann vol
        out = overlays.vol_target(closes, [1.0] * 300)
        self.assertTrue(all(abs(o - 1.0) < 1e-9 for o in out[40:]))

    def test_no_lookahead_on_vol_spike(self):
        """A crash at bar T must not affect weights before T."""
        calm = [100.0 * 1.001**i for i in range(100)]
        crashed = calm + [calm[-1] * 0.7]
        w_calm = overlays.vol_target(calm, [1.0] * len(calm))
        w_crash = overlays.vol_target(crashed, [1.0] * len(crashed))
        self.assertEqual(w_calm, w_crash[:-1])  # history identical pre-crash


class TestGates(unittest.TestCase):
    def test_series_gate_semantics(self):
        w = [1.0, 1.0, 1.0, 0.0]
        gate = [1.0, 0.0, None, 0.0]
        out = overlays.series_gate(w, gate, scale_when_off=0.5)
        self.assertEqual(out, [1.0, 0.5, 1.0, 0.0])  # None → unchanged; 0-weight stays 0

    def test_fng_gate_uses_previous_day(self):
        days = ["d1", "d2", "d3", "d4"]
        fng = {"d1": 50, "d2": 85, "d3": 85, "d4": 20}
        gate = overlays.fng_gate_series(fng, days)
        # d1 gates on nothing (None), d2 gates on d1 (50→on), d3 on d2 (85→off), d4 on d3 (85→off)
        self.assertEqual(gate, [None, 1.0, 0.0, 0.0])

    def test_stable_gate_30d_change(self):
        days = [f"d{i}" for i in range(40)]
        rising = {d: 100.0 + i for i, d in enumerate(days)}
        gate = overlays.stable_gate_series(rising, days, lookback_days=30)
        self.assertTrue(all(g is None for g in gate[:31]))  # warmup: prev-day + 30d change
        self.assertTrue(all(g == 1.0 for g in gate[31:]))   # supply rising → risk-on

        falling = {d: 100.0 - i for i, d in enumerate(days)}
        gate2 = overlays.stable_gate_series(falling, days, lookback_days=30)
        self.assertTrue(all(g == 0.0 for g in gate2[31:]))  # draining → risk-off


class TestWalkForwardTransform(unittest.TestCase):
    def test_transform_is_applied(self):
        from research.backtest.walkforward import walk_forward

        closes = [100.0]
        for i in range(1, 700):
            closes.append(closes[-1] * (1 + 0.01 * math.sin(i / 40) ** 2 + 0.002))

        plain = walk_forward(closes, "donchian", train_bars=200, test_bars=50)
        halved = walk_forward(
            closes, "donchian", train_bars=200, test_bars=50,
            transform=lambda c, w: [x * 0.5 for x in w],
        )
        self.assertLess(halved["oos"]["exposure"], plain["oos"]["exposure"])
        self.assertLessEqual(halved["oos"]["exposure"], 0.5 + 1e-9)


if __name__ == "__main__":
    unittest.main()
