"""Event pipeline tests — planted drift detection, classifier parsing, GDELT parsing."""

import math
import random
import sqlite3
import unittest

from collectors import db as cdb
from collectors.sources import gdelt
from research.events import LABELS_SCHEMA
from research.events.classify import parse_response
from research.events.study import forward_return, load_events, run_study

HOUR = 3_600_000
T0 = 1_700_000_000_000


def synth_conn(n_hours=4000, drift_events=None, drift_pct=0.02, drift_hours=24):
    """In-memory archive: hourly BTC noise, with optional planted post-event drift."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(cdb.SCHEMA)
    conn.executescript(LABELS_SCHEMA)
    rng = random.Random(7)
    drift_events = drift_events or []

    # Per-bar drift injection windows
    boost = [0.0] * n_hours
    for ev_idx in drift_events:
        per_bar = drift_pct / drift_hours
        for k in range(ev_idx + 1, min(ev_idx + 1 + drift_hours, n_hours)):
            boost[k] += per_bar

    price = 50_000.0
    rows = []
    for i in range(n_hours):
        price *= 1 + rng.gauss(0, 0.002) + boost[i]
        rows.append(("BTC", "1h", T0 + i * HOUR, price, price, price, price, 1.0, "t"))
    cdb.upsert_candles(conn, rows)
    return conn


def add_event(conn, idx, news_id, etype="hack_exploit", direction=1, novelty=1):
    conn.execute(
        "INSERT INTO news (id, ts, fetched_ts, source, title, url) VALUES (?,?,?,?,?,?)",
        (news_id, T0 + idx * HOUR + 60_000, 0, "test", f"event {news_id}", f"https://x/{news_id}"),
    )
    conn.execute(
        """INSERT INTO news_labels (news_id, model, labeled_ts, relevant, event_type,
           assets, direction, magnitude, novelty, confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (news_id, "test", 0, 1, etype, "BTC", direction, 2, novelty, "high"),
    )
    conn.commit()


class TestForwardReturn(unittest.TestCase):
    def test_uses_first_bar_after_event_never_same_bar(self):
        ts = [T0 + i * HOUR for i in range(10)]
        closes = [100.0] * 5 + [110.0] * 5  # jump at bar 5
        # Event exactly at bar 4's timestamp → entry is bar 5 (post-jump): no free lunch.
        r = forward_return(ts, closes, ts[4], 1)
        self.assertAlmostEqual(r, 0.0, places=9)

    def test_gap_guard(self):
        ts = [T0, T0 + 50 * HOUR]
        self.assertIsNone(forward_return(ts, [1.0, 2.0], T0 + HOUR, 1))


class TestPlantedDrift(unittest.TestCase):
    def test_detects_planted_drift_and_not_noise(self):
        rng = random.Random(3)
        drift_idx = sorted(rng.sample(range(200, 3600, 100), 30))
        conn = synth_conn(drift_events=drift_idx)
        for i, idx in enumerate(drift_idx):
            add_event(conn, idx, f"hack{i}", etype="hack_exploit", direction=1)
        # Control bucket with no planted drift, spaced away from hack events:
        for i, idx in enumerate(range(250, 3300, 150)):
            add_event(conn, idx, f"other{i}", etype="other", direction=1)

        lines = "\n".join(run_study(conn, "medium"))
        hack_block = lines.split("## hack_exploit")[1].split("##")[0]
        self.assertIn("CANDIDATE", hack_block)  # +24h planted 2% must clear the bar

    def test_clustering_collapses_duplicates(self):
        conn = synth_conn()
        add_event(conn, 100, "a1")
        add_event(conn, 101, "a2")  # 1h later, same type+direction → clustered away
        add_event(conn, 200, "b1")  # 100h later → separate
        events = load_events(conn, "medium")
        self.assertEqual(len(events), 2)


class TestClassifierParse(unittest.TestCase):
    def test_parses_fenced_and_validates(self):
        text = """```json
        [{"id": "x1", "relevant": 1, "event_type": "regulation", "assets": "BTC,ETH",
          "direction": 1, "magnitude": 5, "novelty": 1, "confidence": "high"},
         {"id": "x2", "relevant": 0, "event_type": "bogus_type", "assets": null,
          "direction": -9, "magnitude": 0, "novelty": 0, "confidence": "??"}]
        ```"""
        out = parse_response(text)
        self.assertEqual(out[0]["magnitude"], 3)          # clamped 5 → 3
        self.assertEqual(out[1]["event_type"], "other")   # unknown type coerced
        self.assertEqual(out[1]["direction"], -1)         # clamped
        self.assertEqual(out[1]["assets"], "MARKET")      # null coerced
        self.assertEqual(out[1]["confidence"], "low")     # invalid coerced

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_response("no json here at all")


class TestGdeltParse(unittest.TestCase):
    def test_articles_to_news_rows(self):
        payload = {
            "articles": [
                {"url": "https://a.example/1", "title": "Bitcoin ETF approved",
                 "seendate": "20240110T210000Z", "domain": "a.example"},
                {"url": "", "title": "skip me", "seendate": "20240110T210000Z"},
                {"url": "https://a.example/2", "title": "bad date", "seendate": "nope"},
            ]
        }
        rows = gdelt.parse_articles(payload)
        self.assertEqual(len(rows), 1)
        news_id, ts, _, source, title, url, _ = rows[0]
        self.assertEqual(source, "gdelt:a.example")
        self.assertEqual(ts, 1704920400000)  # 2024-01-10T21:00:00Z
        self.assertEqual(len(news_id), 32)


if __name__ == "__main__":
    unittest.main()
