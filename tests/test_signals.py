"""Signals + forward-paper ledger tests — synthetic archive, no network."""

import math
import sqlite3
import unittest

from collectors import db as cdb
from research import signals
from research.backtest.strategies import STRATEGY_SPECS


def synth_archive(n_days: int = 500) -> sqlite3.Connection:
    """In-memory archive with a deterministic BTC daily series."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(cdb.SCHEMA)
    conn.executescript(signals.SCHEMA)
    price = 100.0
    rows = []
    day_ms = 86_400_000
    t0 = 1_600_000_000_000
    for i in range(n_days):
        # trend up, gradual mid-bear, trend up (same shape the backtests use)
        if n_days // 2 <= i < n_days // 2 + 60:
            price *= 0.985
        else:
            price *= 1 + 0.01 * math.sin(i / 40) ** 2 + 0.002
        rows.append(("BTC", "1d", t0 + i * day_ms, price, price, price, price, 1.0, "test"))
    cdb.upsert_candles(conn, rows)
    return conn


class TestCurrentState(unittest.TestCase):
    def setUp(self):
        self.conn = synth_archive()

    def test_state_shape_and_sanity(self):
        s = signals.current_state(self.conn, "BTC")
        self.assertIsNotNone(s)
        self.assertIn(s["position"], ("LONG", "FLAT"))
        self.assertIn("entry", s["params"])
        self.assertGreater(s["days_in_state"], 0)
        self.assertGreater(s["entry_level"], s["exit_level"])  # max > min of trailing window
        self.assertEqual(len(s["since"]), 10)  # YYYY-MM-DD

    def test_uptrend_tail_is_long(self):
        # The synthetic series ends in a sustained uptrend → breakout state.
        s = signals.current_state(self.conn, "BTC")
        self.assertEqual(s["position"], "LONG")

    def test_unknown_symbol_none(self):
        self.assertIsNone(signals.current_state(self.conn, "DOGE"))


class TestForwardLedger(unittest.TestCase):
    def setUp(self):
        self.conn = synth_archive()

    def test_record_daily_idempotent(self):
        n1 = signals.record_daily(self.conn, ["BTC"])
        n2 = signals.record_daily(self.conn, ["BTC"])
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 0)  # same day, same symbol → no duplicate
        rows = self.conn.execute("SELECT COUNT(*) FROM forward_paper").fetchone()[0]
        self.assertEqual(rows, 1)

    def test_forward_stats_warming_up_then_real(self):
        signals.record_daily(self.conn, ["BTC"])
        s = signals.forward_stats(self.conn, "BTC")
        self.assertIn("note", s)  # < 3 rows → warming up

        # Simulate three more recorded days by inserting directly.
        for i, (day, px, w) in enumerate(
            [("2099-01-01", 110.0, 1.0), ("2099-01-02", 112.0, 1.0), ("2099-01-03", 111.0, 0.0)]
        ):
            self.conn.execute(
                "INSERT INTO forward_paper VALUES (?,?,?,?,?,?)",
                (day, "BTC", w, px, "{}", i),
            )
        s = signals.forward_stats(self.conn, "BTC")
        self.assertIn("strategy", s)
        self.assertIn("buy_hold", s)
        self.assertEqual(s["days"], 4)


class TestParamSelection(unittest.TestCase):
    def test_params_come_from_grid_and_are_stable(self):
        conn = synth_archive()
        ts, closes = signals._load(conn, "BTC")
        p1 = signals.select_params(closes)
        p2 = signals.select_params(closes)
        self.assertEqual(p1, p2)  # deterministic
        self.assertIn(p1, STRATEGY_SPECS["donchian"]["grid"])


if __name__ == "__main__":
    unittest.main()
