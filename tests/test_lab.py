"""AI Research Lab tests — DSL, interpreter timing, statistics, orchestration."""

import math
import unittest

from research.backtest import engine
from research.lab import dsl, interpret, orchestrate, stats
from research.lab.generate import RandomGenerator

BREAKOUT = {
    "entry": {"op": "cross_above", "a": {"op": "close"},
              "b": {"op": "roll_max", "n": 20, "of": {"op": "close"}}},
    "exit": {"op": "cross_below", "a": {"op": "close"},
             "b": {"op": "roll_min", "n": 10, "of": {"op": "close"}}},
}


def trending(n=600):
    closes = [100.0]
    for i in range(1, n):
        if n // 2 <= i < n // 2 + 60:
            closes.append(closes[-1] * 0.985)
        else:
            closes.append(closes[-1] * (1 + 0.01 * math.sin(i / 40) ** 2 + 0.002))
    return closes


class TestDsl(unittest.TestCase):
    def test_validates_good_rejects_bad(self):
        dsl.validate(BREAKOUT)  # no raise
        for bad in (
            {"entry": {"op": "exec", "a": 1}, "exit": BREAKOUT["exit"]},
            {"entry": {"op": "gt", "a": {"op": "sma", "n": 9999, "of": {"op": "close"}},
                       "b": {"op": "close"}}, "exit": BREAKOUT["exit"]},
            {"entry": BREAKOUT["entry"]},  # missing exit
        ):
            with self.assertRaises(dsl.DslError):
                dsl.validate(bad)

    def test_canonical_ignores_key_order_and_extras(self):
        a = {"exit": BREAKOUT["exit"], "entry": BREAKOUT["entry"], "name": "x"}
        self.assertEqual(dsl.cand_hash(a), dsl.cand_hash(BREAKOUT))

    def test_window_params_found(self):
        self.assertEqual(sorted(n for _, n in dsl.window_params(BREAKOUT)), [10, 20])


class TestInterpreter(unittest.TestCase):
    def test_sma_known_values(self):
        s = interpret.eval_series({"op": "sma", "n": 3, "of": {"op": "close"}}, [1, 2, 3, 4, 5])
        self.assertTrue(math.isnan(s[1]))
        self.assertEqual(s[2:], [2.0, 3.0, 4.0])

    def test_roll_max_strictly_prior(self):
        s = interpret.eval_series({"op": "roll_max", "n": 3, "of": {"op": "close"}}, [1, 2, 3, 10, 4])
        self.assertEqual(s[3], 3)   # max of bars 0-2, NOT including the 10
        self.assertEqual(s[4], 10)

    def test_nested_ops_compose_through_warmup(self):
        node = {"op": "sma", "n": 5, "of": {"op": "ema", "n": 10, "of": {"op": "close"}}}
        s = interpret.eval_series(node, trending(100))
        self.assertTrue(math.isnan(s[10]))
        self.assertFalse(math.isnan(s[-1]))

    def test_state_machine_enters_and_exits(self):
        closes = trending(400)
        w = interpret.weights(BREAKOUT, closes)
        self.assertEqual(set(w) - {0.0, 1.0}, set())
        self.assertGreater(sum(w), 10)      # actually goes long
        self.assertLess(sum(w), len(w))     # and is sometimes flat

    def test_no_lookahead_last_bar(self):
        closes = trending(300)
        w1 = interpret.weights(BREAKOUT, closes)
        closes2 = closes[:-1] + [closes[-1] * 3]  # violent change on final bar
        w2 = interpret.weights(BREAKOUT, closes2)
        self.assertEqual(w1[:-1], w2[:-1])  # history untouched

    def test_rsi_bounds(self):
        s = interpret.eval_series({"op": "rsi", "n": 14, "of": {"op": "close"}}, trending(200))
        vals = [x for x in s if not math.isnan(x)]
        self.assertTrue(all(0 <= v <= 100 for v in vals))


class TestStats(unittest.TestCase):
    def test_norm_ppf_inverts_cdf(self):
        for p in (0.025, 0.5, 0.95, 0.999):
            self.assertAlmostEqual(stats.norm_cdf(stats.norm_ppf(p)), p, places=6)

    def test_expected_max_grows_with_trials(self):
        v = 0.01
        e10 = stats.expected_max_sharpe(10, v)
        e1000 = stats.expected_max_sharpe(1000, v)
        self.assertGreater(e1000, e10)
        self.assertGreater(e10, 0)

    def test_dsr_punishes_many_trials(self):
        rng = __import__("random").Random(5)
        rets = [0.003 + rng.gauss(0, 0.01) for _ in range(500)]
        few = stats.deflated_sharpe(rets, 5, [0.01, 0.02, -0.01, 0.0, 0.03])
        many_sharpes = [rng.gauss(0, 0.05) for _ in range(2000)]
        many = stats.deflated_sharpe(rets, 2000, many_sharpes)
        self.assertGreater(few["dsr"], many["dsr"])

    def test_bootstrap_pvalue_direction(self):
        rng = __import__("random").Random(9)
        edge = [0.002 + rng.gauss(0, 0.004) for _ in range(400)]
        noise = [rng.gauss(0, 0.004) for _ in range(400)]
        self.assertLess(stats.stationary_bootstrap_pvalue(edge, n_boot=300), 0.05)
        self.assertGreater(stats.stationary_bootstrap_pvalue(noise, n_boot=300), 0.05)


class TestOrchestration(unittest.TestCase):
    def test_search_and_finalize_roundtrip(self):
        closes = trending(700)
        conn = orchestrate.lab_db(":memory:")
        lab = orchestrate.SearchLab(closes[:500], conn, "random")
        self.assertEqual(len(lab.closes), 500)  # holdout never enters the lab

        lab.run_generations(RandomGenerator(seed=3), generations=2, pop=15, log=lambda *_: None)
        trials = conn.execute("SELECT COUNT(*) FROM lab_candidates").fetchone()[0]
        self.assertGreater(trials, 10)

        report = orchestrate.finalize(closes, 500, conn, top_m=2)
        self.assertEqual(report["n_trials"], trials)
        self.assertEqual(report["holdout_bars"], 200)
        self.assertEqual(len(report["finalists"]), 2)
        for f in report["finalists"]:
            self.assertIn(f["verdict"], ("PASS", "FAIL"))
            self.assertLessEqual(f["dsr"]["dsr"], 1.0)
            # holdout uses exactly the sealed segment
            self.assertEqual(f["holdout"]["days"], 200)

    def test_dedupe_across_evaluations(self):
        conn = orchestrate.lab_db(":memory:")
        lab = orchestrate.SearchLab(trending(500), conn, "random")
        first = lab.evaluate(BREAKOUT, 0)
        second = lab.evaluate(BREAKOUT, 1)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_multi_asset_scoring_and_basket_finalize(self):
        a = trending(700)
        b = [c * 0.5 for c in trending(700)]  # second asset, same shape
        conn = orchestrate.lab_db(":memory:")
        lab = orchestrate.SearchLab({"A": a[:500], "B": b[:500]}, conn, "random")
        out = lab.evaluate(BREAKOUT, 0)
        self.assertIsNotNone(out)
        self.assertIn("per_asset", out["stats"])
        self.assertEqual(set(out["stats"]["per_asset"]), {"A", "B"})

        report = orchestrate.finalize_multi({"A": a, "B": b}, 500, conn, top_m=1)
        f = report["finalists"][0]
        self.assertEqual(report["holdout_bars"], 200)
        self.assertIn(f["verdict"], ("PASS", "FAIL"))
        self.assertEqual(set(f["per_asset"]), {"A", "B"})
        self.assertIn("sharpe", f["holdout_basket"])

    def test_known_breakout_scores_sanely(self):
        closes = trending(600)
        conn = orchestrate.lab_db(":memory:")
        lab = orchestrate.SearchLab(closes, conn, "random")
        out = lab.evaluate(BREAKOUT, 0)
        self.assertIsNotNone(out)
        w = interpret.weights(BREAKOUT, closes)
        res = engine.run(closes, w, 10, 5)
        self.assertAlmostEqual(out["train_sharpe"], stats.sharpe_per_bar(res.returns), places=12)


if __name__ == "__main__":
    unittest.main()
