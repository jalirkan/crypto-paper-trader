"""Offline tests for the collector layer — parsers, schema, upsert semantics.

Run:  python -m unittest discover -s tests -v
No network required.
"""

import sqlite3
import unittest

from collectors import db
from collectors.sources import binance, coinbase, misc, rss

RSS2_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test Feed</title>
<item>
  <title>Bitcoin ETF sees record &amp; historic inflows</title>
  <link>https://example.com/btc-etf</link>
  <description><![CDATA[<p>Spot ETFs absorbed <b>$1.2B</b> today.</p>]]></description>
  <pubDate>Sun, 26 Jul 2026 14:01:02 +0000</pubDate>
</item>
<item>
  <title>No link item is skipped</title>
</item>
</channel></rss>"""

ATOM_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Test</title>
  <entry>
    <title>Solana outage resolved</title>
    <link rel="alternate" href="https://example.com/sol-outage"/>
    <summary>Network resumed block production.</summary>
    <published>2026-07-26T10:30:00Z</published>
  </entry>
</feed>"""


class TestRss(unittest.TestCase):
    def test_rss2(self):
        rows = rss.parse_feed(RSS2_FIXTURE, "testsrc")
        self.assertEqual(len(rows), 1)  # linkless item skipped
        news_id, ts, fetched_ts, source, title, url, summary = rows[0]
        self.assertEqual(len(news_id), 32)
        self.assertEqual(source, "testsrc")
        self.assertIn("record & historic", title)
        self.assertEqual(url, "https://example.com/btc-etf")
        self.assertIn("$1.2B", summary)
        self.assertNotIn("<p>", summary)  # html stripped
        self.assertEqual(ts, 1785074462000)  # 2026-07-26T14:01:02Z

    def test_atom(self):
        rows = rss.parse_feed(ATOM_FIXTURE, "atomsrc")
        self.assertEqual(len(rows), 1)
        _, ts, _, _, title, url, summary = rows[0]
        self.assertEqual(title, "Solana outage resolved")
        self.assertEqual(url, "https://example.com/sol-outage")
        self.assertEqual(ts, 1785061800000)  # 2026-07-26T10:30:00Z

    def test_date_fallbacks(self):
        self.assertIsNone(rss.parse_date("not a date"))
        self.assertIsNone(rss.parse_date(""))
        self.assertEqual(rss.parse_date("1970-01-01T00:00:01Z"), 1000)


class TestVenueParsers(unittest.TestCase):
    def test_binance_kline_row(self):
        raw = [1753488000000, "43000.1", "43500.9", "42800.0", "43210.5", "1234.56",
               1753574399999, "0", 0, "0", "0", "0"]
        row = binance.parse_kline_row("BTC", "1d", raw)
        self.assertEqual(row, ("BTC", "1d", 1753488000000, 43000.1, 43500.9,
                               42800.0, 43210.5, 1234.56, "binance"))

    def test_coinbase_row_order_and_sort(self):
        # Coinbase: [time_s, low, high, open, close, volume], newest first
        raw_new = [1753574400, 42000.0, 44000.0, 43000.0, 43500.0, 99.9]
        raw_old = [1753488000, 41000.0, 43000.0, 42000.0, 42500.0, 88.8]
        rows = [coinbase.parse_candle_row("BTC", "1d", r) for r in (raw_new, raw_old)]
        rows.sort(key=lambda r: r[2])
        self.assertEqual(rows[0][2], 1753488000000)  # oldest first after sort
        self.assertEqual(rows[0][3], 42000.0)  # open (not low!)
        self.assertEqual(rows[0][4], 43000.0)  # high
        self.assertEqual(rows[0][5], 41000.0)  # low

    def test_fng_parser(self):
        payload = {"data": [
            {"value": "72", "value_classification": "Greed", "timestamp": "1753488000"},
            {"value": "bad"},  # malformed → skipped
        ]}
        rows = misc.parse_fng(payload)
        self.assertEqual(rows, [(1753488000000, 72, "Greed")])

    def test_stablecoin_parser(self):
        payload = [
            {"date": "1753488000", "totalCirculatingUSD": {"peggedUSD": 170_000_000_000.5}},
            {"date": "oops"},  # malformed → skipped
        ]
        rows = misc.parse_stablecoins(payload)
        self.assertEqual(rows, [(1753488000000, 170_000_000_000.5)])


class TestDb(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(db.SCHEMA)

    def test_candle_upsert_idempotent(self):
        row = ("BTC", "1d", 1000, 1.0, 2.0, 0.5, 1.5, 10.0, "binance")
        db.upsert_candles(self.conn, [row])
        db.upsert_candles(self.conn, [row])  # duplicate
        revised = ("BTC", "1d", 1000, 1.0, 2.0, 0.5, 1.6, 11.0, "coinbase")
        db.upsert_candles(self.conn, [revised])  # revision wins
        rows = self.conn.execute("SELECT close, source FROM candles").fetchall()
        self.assertEqual(rows, [(1.6, "coinbase")])

    def test_news_dedupe_counts_new_only(self):
        r1 = ("id1", 1000, 2000, "src", "title", "https://a", "sum")
        r2 = ("id2", 1001, 2000, "src", "title2", "https://b", "sum")
        self.assertEqual(db.insert_news(self.conn, [r1]), 1)
        self.assertEqual(db.insert_news(self.conn, [r1, r2]), 1)  # only r2 is new
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM news").fetchone()[0], 2
        )

    def test_max_ts(self):
        self.assertIsNone(db.max_ts(self.conn, "candles", "symbol=?", ("BTC",)))
        db.upsert_candles(self.conn, [
            ("BTC", "1d", 1000, 1, 2, 0.5, 1.5, 10, "x"),
            ("BTC", "1d", 2000, 1, 2, 0.5, 1.5, 10, "x"),
            ("ETH", "1d", 9000, 1, 2, 0.5, 1.5, 10, "x"),
        ])
        self.assertEqual(db.max_ts(self.conn, "candles", "symbol=?", ("BTC",)), 2000)

    def test_funding_upsert(self):
        db.upsert_funding(self.conn, [("BTCUSDT", 1000, 0.0001, "binance")])
        db.upsert_funding(self.conn, [("BTCUSDT", 1000, 0.0002, "binance")])
        rows = self.conn.execute("SELECT rate FROM funding").fetchall()
        self.assertEqual(rows, [(0.0002,)])

    def test_log_run(self):
        db.log_run(self.conn, "test", True, 5, "ok")
        ok, items = self.conn.execute(
            "SELECT ok, items FROM collector_runs"
        ).fetchone()
        self.assertEqual((ok, items), (1, 5))


if __name__ == "__main__":
    unittest.main()
