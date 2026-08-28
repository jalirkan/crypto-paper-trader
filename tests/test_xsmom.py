"""Cross-sectional momentum (EXP-007) — synthetic universes, no archive needed.

The load-bearing test is `test_one_asset_universe_reproduces_the_engine`: the
portfolio layer is new code, and the cheapest way to trust its timing and cost
model is to show that on a degenerate universe it is bit-for-bit the audited
long/flat engine. Everything else here defends a specific way the sleeve could
lie — look-ahead, free trading, an unpaired bootstrap, a moved kill bar.
"""

import unittest

from research.backtest import engine, run_xsmom, xsmom
from research.lab import stats


def ramp(n: int, per_bar: float, start: float = 100.0) -> list[float]:
    """Deterministic geometric series — no randomness anywhere in these tests."""
    return [start * (1.0 + per_bar) ** i for i in range(n)]


def wobble(n: int, per_bar: float, amp: float = 0.02, start: float = 100.0) -> list[float]:
    """A trend with a repeating wiggle, so returns have nonzero variance."""
    closes = [start]
    for i in range(1, n):
        step = per_bar + (amp if i % 2 else -amp)
        closes.append(closes[-1] * (1.0 + step))
    return closes


class TestPortfolioLayer(unittest.TestCase):
    def test_one_asset_universe_reproduces_the_engine(self):
        """A universe of one, top_n=1, must equal engine.run on the same weights.

        If this passes, the portfolio layer inherits the engine's no-look-ahead
        shift and its cost timing rather than reasserting them.
        """
        closes = wobble(400, 0.002)
        out = xsmom.simulate({"A": closes}, lookback=90, top_n=1, rebalance_every=30)

        expected_w = [0.0] * 90 + [1.0] * (400 - 90)
        expected = engine.run(closes, expected_w, xsmom.FEE_BPS, xsmom.SLIP_BPS)

        self.assertEqual(len(out["returns"]), len(expected.returns))
        for got, want in zip(out["returns"], expected.returns):
            self.assertAlmostEqual(got, want, places=15)

    def test_flat_before_the_lookback_is_satisfied(self):
        closes = wobble(200, 0.002)
        w, traded = xsmom.target_weights({"A": closes}, lookback=90, top_n=1)
        self.assertEqual(sum(w["A"][:90]), 0.0)
        self.assertEqual(sum(traded[:90]), 0.0)
        self.assertEqual(w["A"][90], 1.0)

    def test_ranking_holds_the_strongest_trends(self):
        universe = {
            "UP1": ramp(300, 0.006),
            "UP2": ramp(300, 0.004),
            "DOWN1": ramp(300, -0.003),
            "DOWN2": ramp(300, -0.005),
        }
        out = xsmom.simulate(universe, lookback=90, top_n=2, rebalance_every=30)
        for held in out["holdings"][90:]:
            self.assertEqual(held, ["UP1", "UP2"])

    def test_rotation_follows_the_ranking(self):
        """When the leadership changes, the next rebalance must follow it."""
        n = 300
        # A leads for the first half, then goes sideways while B takes over.
        a = ramp(150, 0.008) + [ramp(150, 0.008)[-1]] * 150
        b = [100.0] * 150 + ramp(150, 0.010, start=100.0)
        out = xsmom.simulate({"A": a, "B": b}, lookback=90, top_n=1, rebalance_every=30)
        self.assertEqual(out["holdings"][90], ["A"])
        self.assertEqual(out["holdings"][n - 1], ["B"])
        self.assertGreaterEqual(out["rebalances"], 2)

    def test_no_lookahead_the_last_bar_cannot_change_earlier_returns(self):
        """A monster print on the final close must not move any prior return."""
        universe = {"A": wobble(200, 0.003), "B": wobble(200, 0.001)}
        base = xsmom.simulate(universe, lookback=90, top_n=1, rebalance_every=30)

        spiked = {k: list(v) for k, v in universe.items()}
        spiked["B"][-1] *= 5.0
        after = xsmom.simulate(spiked, lookback=90, top_n=1, rebalance_every=30)

        # Everything except the final bar (whose return legitimately changed).
        self.assertEqual(base["returns"][:-1], after["returns"][:-1])

    def test_costs_are_charged_only_where_a_trade_happens(self):
        universe = {"A": wobble(300, 0.004), "B": wobble(300, 0.001)}
        _, traded = xsmom.target_weights(universe, lookback=90, top_n=1, rebalance_every=30)
        rebalance_bars = {t for t in range(90, 300, 30)}
        for t, amount in enumerate(traded):
            if t not in rebalance_bars:
                self.assertEqual(amount, 0.0, f"cost charged on non-rebalance bar {t}")

    def test_drift_between_rebalances_is_free(self):
        """Holding is free; only the rebalance pays. A universe whose ranking
        never changes must be charged exactly one entry."""
        universe = {"A": ramp(400, 0.005), "B": ramp(400, -0.002)}
        out = xsmom.simulate(universe, lookback=90, top_n=1, rebalance_every=30)
        self.assertEqual(out["rebalances"], 1)  # entered once, never rotated
        self.assertAlmostEqual(sum(out["traded"]), 1.0, places=12)

    def test_higher_fees_reduce_returns_monotonically(self):
        universe = {"A": wobble(400, 0.004), "B": wobble(400, 0.003), "C": wobble(400, -0.001)}
        finals = []
        for fee in (0.0, 10.0, 50.0, 200.0):
            out = xsmom.simulate(universe, top_n=1, fee_bps=fee, slip_bps=0.0)
            finals.append(out["stats"]["total_return"])
        self.assertTrue(finals[0] > finals[1] > finals[2] > finals[3])

    def test_equal_weight_basket_is_buy_and_hold_of_the_universe(self):
        universe = {"A": wobble(300, 0.004), "B": wobble(300, -0.001), "C": wobble(300, 0.002)}
        out = xsmom.equal_weight_basket(universe, fee_bps=0.0, slip_bps=0.0)
        equity = 1.0
        for r in out["returns"]:
            equity *= 1.0 + r
        expected = sum(c[-1] / c[0] for c in universe.values()) / len(universe)
        self.assertAlmostEqual(equity, expected, places=12)
        self.assertEqual(out["rebalances"], 1)  # bought once, never touched

    def test_rejects_misaligned_and_impossible_universes(self):
        with self.assertRaises(ValueError):
            xsmom.target_weights({"A": [1.0, 2.0, 3.0], "B": [1.0, 2.0]})
        with self.assertRaises(ValueError):
            xsmom.target_weights({"A": ramp(200, 0.001)}, top_n=2)

    def test_simulate_is_deterministic(self):
        universe = {"A": wobble(300, 0.003), "B": wobble(300, 0.001), "C": wobble(300, -0.002)}
        first = xsmom.simulate(universe)
        second = xsmom.simulate(universe)
        self.assertEqual(first["returns"], second["returns"])
        self.assertEqual(first["holdings"], second["holdings"])


class TestPreRegisteredNeighbourhood(unittest.TestCase):
    def test_neighbours_match_the_pre_registration(self):
        """EXP-007 names these six by number. Rounding half-up matters: Python's
        round(112.5) is 112, and the ledger says 113."""
        got = xsmom.neighbours()
        self.assertEqual(len(got), 6)
        self.assertIn({"lookback": 68, "top_n": 3, "rebalance_every": 30}, got)
        self.assertIn({"lookback": 113, "top_n": 3, "rebalance_every": 30}, got)
        self.assertIn({"lookback": 90, "top_n": 2, "rebalance_every": 30}, got)
        self.assertIn({"lookback": 90, "top_n": 4, "rebalance_every": 30}, got)
        self.assertIn({"lookback": 90, "top_n": 3, "rebalance_every": 23}, got)
        self.assertIn({"lookback": 90, "top_n": 3, "rebalance_every": 38}, got)

    def test_pre_registered_defaults_are_what_the_ledger_says(self):
        """The module's constants ARE the pre-registration. If someone tunes
        them to rescue a result, this test is the tripwire."""
        self.assertEqual(xsmom.LOOKBACK, 90)
        self.assertEqual(xsmom.TOP_N, 3)
        self.assertEqual(xsmom.REBALANCE, 30)
        self.assertEqual((xsmom.FEE_BPS, xsmom.SLIP_BPS), (10.0, 5.0))


class TestPreRegisteredDecisionRule(unittest.TestCase):
    """The verdict is computed from the rule, so the rule itself gets tested."""

    def test_interval_below_zero_kills_regardless_of_guards(self):
        self.assertEqual(run_xsmom.decide("KILL", True), "KILL")
        self.assertEqual(run_xsmom.decide("KILL", False), "KILL")

    def test_keep_requires_the_interval_and_every_guard(self):
        self.assertEqual(run_xsmom.decide("KEEP", True), "KEEP")
        self.assertEqual(run_xsmom.decide("KEEP", False), "INCONCLUSIVE")

    def test_guards_cannot_manufacture_a_keep(self):
        """Passing guards on a straddling interval is not a pass. This is the
        EXP-006 failure mode — a point estimate over the bar, an interval that
        does not clear it — expressed as a decision table."""
        self.assertEqual(run_xsmom.decide("INCONCLUSIVE", True), "INCONCLUSIVE")

    def test_per_year_reports_short_years_instead_of_dropping_them(self):
        day = 86_400_000
        # 2024 is a leap year: 400 bars from 2024-01-01 is 366 + 34.
        ts = [1_704_067_200_000 + i * day for i in range(400)]
        s = [0.001] * 400
        b = [0.0005] * 400
        rows, skipped = run_xsmom.per_year(ts, s, b, min_bars=100)
        self.assertEqual([r[0] for r in rows], ["2024"])
        self.assertEqual(len(skipped), 1)
        self.assertIn("2025", skipped[0])


class TestPairedBootstrap(unittest.TestCase):
    def test_identical_series_give_a_zero_width_interval(self):
        """The pairing test. Resampled with the SAME block indices, a series
        against itself has a Sharpe difference of exactly zero in every draw.
        An unpaired bootstrap would scatter both ends away from zero, so this
        fails loudly if the indices are ever drawn twice."""
        series = [0.01, -0.004, 0.007, -0.002] * 40
        ci = stats.sharpe_diff_ci(series, list(series), n_boot=200)
        self.assertEqual(ci["diff"], 0.0)
        self.assertAlmostEqual(ci["lo"], 0.0, places=12)
        self.assertAlmostEqual(ci["hi"], 0.0, places=12)

    def test_interval_brackets_the_observed_difference(self):
        a = [0.006, -0.001, 0.004, 0.002] * 60
        b = [0.001, -0.003, 0.002, -0.001] * 60
        ci = stats.sharpe_diff_ci(a, b, n_boot=300)
        self.assertLessEqual(ci["lo"], ci["diff"])
        self.assertGreaterEqual(ci["hi"], ci["diff"])

    def test_a_clear_gap_produces_an_interval_above_zero(self):
        better = [0.010, 0.009, 0.011, 0.010] * 60   # steady and smooth
        worse = [-0.010, -0.009, -0.011, -0.010] * 60
        ci = stats.sharpe_diff_ci(better, worse, n_boot=300)
        self.assertGreater(ci["lo"], 0.0)
        self.assertEqual(stats.interval_verdict(ci["lo"], ci["hi"]), "KEEP")

    def test_noise_against_itself_straddles_zero(self):
        """Two different-but-equivalent series must not read as an edge."""
        a = [0.01, -0.01, 0.008, -0.008] * 60
        b = [-0.01, 0.01, -0.008, 0.008] * 60
        ci = stats.sharpe_diff_ci(a, b, n_boot=300)
        self.assertEqual(stats.interval_verdict(ci["lo"], ci["hi"]), "INCONCLUSIVE")

    def test_same_seed_reproduces_the_interval(self):
        a = [0.006, -0.001, 0.004, 0.002] * 60
        b = [0.001, -0.003, 0.002, -0.001] * 60
        first = stats.sharpe_diff_ci(a, b, n_boot=200, seed=42)
        second = stats.sharpe_diff_ci(a, b, n_boot=200, seed=42)
        other = stats.sharpe_diff_ci(a, b, n_boot=200, seed=7)
        self.assertEqual(first, second)
        self.assertNotEqual(first["lo"], other["lo"])  # the seed is doing work

    def test_mismatched_lengths_raise_rather_than_truncate(self):
        with self.assertRaises(ValueError):
            stats.sharpe_diff_ci([0.01] * 50, [0.01] * 40)

    def test_interval_verdict_is_three_outcomes_not_two(self):
        self.assertEqual(stats.interval_verdict(0.1, 0.4), "KEEP")
        self.assertEqual(stats.interval_verdict(-0.4, -0.1), "KILL")
        self.assertEqual(stats.interval_verdict(-0.2, 0.3), "INCONCLUSIVE")
        self.assertEqual(stats.interval_verdict(float("nan"), float("nan")), "INCONCLUSIVE")
        # Straddling the bar is not a soft pass, even when the point estimate
        # is comfortably above it — the EXP-006 lesson, pinned.
        self.assertEqual(stats.interval_verdict(-0.01, 2.0), "INCONCLUSIVE")

    def test_block_indices_are_in_range_and_full_length(self):
        import random

        idx = stats.block_indices(50, 10, random.Random(1))
        self.assertEqual(len(idx), 50)
        self.assertTrue(all(0 <= i < 50 for i in idx))


if __name__ == "__main__":
    unittest.main()
