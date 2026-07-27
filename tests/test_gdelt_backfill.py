"""Offline tests for backfill pacing and covered-day skipping."""

import sqlite3
import unittest

from collectors import db as cdb
from collectors.gdelt_backfill import SLEEP_MAX, SLEEP_MIN, covered_days, next_sleep


class TestNapEscalation(unittest.TestCase):
    def test_naps_double_and_cap(self):
        from collectors.gdelt_backfill import CIRCUIT_PAUSE_MAX_S, nap_duration

        self.assertEqual(nap_duration(0), 900.0)    # 15 min
        self.assertEqual(nap_duration(1), 1800.0)   # 30 min
        self.assertEqual(nap_duration(2), 3600.0)   # 60 min
        self.assertEqual(nap_duration(3), 7200.0)   # 2 h cap
        self.assertEqual(nap_duration(10), CIRCUIT_PAUSE_MAX_S)  # stays capped


class TestPacing(unittest.TestCase):
    def test_aimd_converges_within_bounds(self):
        s = 20.0
        for _ in range(50):
            s = next_sleep(s, success=True)
        self.assertAlmostEqual(s, SLEEP_MIN)  # floor under sustained success
        for _ in range(20):
            s = next_sleep(s, success=False)
        self.assertAlmostEqual(s, SLEEP_MAX)  # ceiling under sustained 429s

    def test_slowdown_outpaces_speedup(self):
        # One failure must cost more than one success gains (stability).
        s = 30.0
        after = next_sleep(next_sleep(s, False), True)
        self.assertGreater(after, s)


class TestWindows(unittest.TestCase):
    def test_windows_skip_fully_covered_chunks(self):
        from datetime import date

        from collectors.gdelt_backfill import build_windows

        days = [date(2023, 8, d) for d in range(1, 10)]  # 9 days
        done = {"2023-08-01", "2023-08-02", "2023-08-03"}  # first chunk covered
        windows = build_windows(days, done, window_days=3)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0], (date(2023, 8, 4), date(2023, 8, 6)))
        self.assertEqual(windows[1], (date(2023, 8, 7), date(2023, 8, 9)))

    def test_partial_coverage_still_fetches_window(self):
        from datetime import date

        from collectors.gdelt_backfill import build_windows

        days = [date(2023, 8, d) for d in range(1, 4)]
        done = {"2023-08-01"}  # one of three covered → window still needed
        windows = build_windows(days, done, window_days=3)
        self.assertEqual(len(windows), 1)


class TestCoveredDays(unittest.TestCase):
    def test_only_successful_days_are_skipped(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(cdb.SCHEMA)
        cdb.log_run(conn, "gdelt", True, 250, "2023-08-01")
        cdb.log_run(conn, "gdelt", False, 0, "2023-08-02: 429")
        cdb.log_run(conn, "gdelt", True, 0, "2023-08-03")  # 0 new still counts
        cdb.log_run(conn, "news:rss", True, 10, "not-a-day")  # other collectors ignored
        done = covered_days(conn)
        self.assertIn("2023-08-01", done)
        self.assertIn("2023-08-03", done)
        self.assertNotIn("2023-08-02: 429", done)
        self.assertEqual(len([d for d in done if d.startswith("2023-08-0")]), 2)


if __name__ == "__main__":
    unittest.main()
