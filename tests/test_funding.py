"""Funding-harvest simulator tests — synthetic rate series."""

import unittest

from research.funding.sim import EPOCHS_PER_DAY, annualized, simulate

RICH = 0.0002  # 0.02%/epoch ≈ 21.9% annualized — juicy regime
POOR = -0.0001


class TestFundingSim(unittest.TestCase):
    def test_constant_rich_regime_harvests(self):
        rates = [RICH] * (EPOCHS_PER_DAY * 365 * 2)  # two years
        res = simulate(rates)
        self.assertEqual(res["entries"], 1)  # enters once, never exits
        self.assertGreater(res["time_in_position"], 0.95)
        # APR is geometric (per-epoch compounding), so compare against the
        # compounded rate, minus the negligible one-off entry cost.
        compounded = (1 + RICH) ** (EPOCHS_PER_DAY * 365) - 1
        self.assertAlmostEqual(res["apr"], compounded, delta=0.01)
        self.assertGreater(res["apr"], annualized(RICH) * 0.95)  # sanity vs simple rate
        self.assertGreater(res["apr"], 0.05)  # would pass the KEEP bar

    def test_negative_regime_stays_out(self):
        rates = [POOR] * (EPOCHS_PER_DAY * 365)
        res = simulate(rates)
        self.assertEqual(res["entries"], 0)
        self.assertEqual(res["final_equity"], 1.0)  # flat, unscathed

    def test_hysteresis_no_churn_in_gray_zone(self):
        # Trailing annualized oscillating between 3% and 7% — inside the
        # enter-8%/exit-2% band → whichever state it's in, it stays.
        gray = [0.00005, 0.00006] * (EPOCHS_PER_DAY * 180)
        res = simulate(gray)
        self.assertEqual(res["entries"], 0)  # never crosses 8% to enter

    def test_regime_flip_exits_and_costs_bite(self):
        rich_year = [RICH] * (EPOCHS_PER_DAY * 200)
        dead_year = [0.0] * (EPOCHS_PER_DAY * 200)
        res = simulate(rich_year + dead_year)
        self.assertEqual(res["entries"], 1)
        self.assertLess(res["time_in_position"], 0.6)  # exited for the dead half
        free = simulate(rich_year + dead_year, leg_cost=0.0)
        self.assertLess(res["final_equity"], free["final_equity"])  # costs matter

    def test_no_lookahead_at_decision_epoch(self):
        # A monster rate at the FINAL epoch can't affect entry decisions
        # (decisions use rates strictly before the current epoch).
        base = [0.0] * (EPOCHS_PER_DAY * 100)
        spiked = base[:-1] + [0.01]
        self.assertEqual(simulate(base)["entries"], simulate(spiked)["entries"])
