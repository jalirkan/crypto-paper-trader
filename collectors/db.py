"""SQLite archive — schema and idempotent upserts. Stdlib only.

Every writer is an INSERT ... ON CONFLICT upsert, so collectors can re-fetch
overlapping ranges freely; duplicates are impossible by construction.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "archive.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
  symbol TEXT NOT NULL,            -- BTC, ETH, ...
  tf     TEXT NOT NULL,            -- '1d' | '1h'
  ts     INTEGER NOT NULL,         -- open time, epoch ms UTC
  open REAL, high REAL, low REAL, close REAL, volume REAL,
  source TEXT,
  PRIMARY KEY (symbol, tf, ts)
);
CREATE TABLE IF NOT EXISTS funding (
  symbol TEXT NOT NULL,            -- venue symbol, e.g. BTCUSDT
  ts     INTEGER NOT NULL,         -- funding time, epoch ms UTC
  rate   REAL NOT NULL,
  source TEXT,
  PRIMARY KEY (symbol, ts)
);
CREATE TABLE IF NOT EXISTS news (
  id         TEXT PRIMARY KEY,     -- sha256(url)[:32]
  ts         INTEGER,              -- published, epoch ms UTC
  fetched_ts INTEGER NOT NULL,
  source     TEXT,
  title      TEXT,
  url        TEXT,
  summary    TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_ts ON news (ts);
CREATE TABLE IF NOT EXISTS fear_greed (
  ts    INTEGER PRIMARY KEY,       -- epoch ms UTC (daily)
  value INTEGER,
  label TEXT
);
CREATE TABLE IF NOT EXISTS stablecoins (
  ts         INTEGER PRIMARY KEY,  -- epoch ms UTC (daily)
  total_mcap REAL                  -- total USD-pegged circulating, USD
);
CREATE TABLE IF NOT EXISTS collector_runs (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        INTEGER NOT NULL,
  collector TEXT NOT NULL,
  ok        INTEGER NOT NULL,
  items     INTEGER NOT NULL,
  message   TEXT
);
"""


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or os.environ.get("CPT_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_candles(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """rows: (symbol, tf, ts, open, high, low, close, volume, source)"""
    conn.executemany(
        """INSERT INTO candles (symbol, tf, ts, open, high, low, close, volume, source)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(symbol, tf, ts) DO UPDATE SET
             open=excluded.open, high=excluded.high, low=excluded.low,
             close=excluded.close, volume=excluded.volume, source=excluded.source""",
        rows,
    )
    conn.commit()
    return len(rows)


def upsert_funding(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """rows: (symbol, ts, rate, source)"""
    conn.executemany(
        """INSERT INTO funding (symbol, ts, rate, source) VALUES (?,?,?,?)
           ON CONFLICT(symbol, ts) DO UPDATE SET rate=excluded.rate, source=excluded.source""",
        rows,
    )
    conn.commit()
    return len(rows)


def insert_news(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """rows: (id, ts, fetched_ts, source, title, url, summary). Returns NEW rows only."""
    before = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    conn.executemany(
        """INSERT INTO news (id, ts, fetched_ts, source, title, url, summary)
           VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
        rows,
    )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    return after - before


def upsert_fear_greed(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """rows: (ts, value, label)"""
    conn.executemany(
        """INSERT INTO fear_greed (ts, value, label) VALUES (?,?,?)
           ON CONFLICT(ts) DO UPDATE SET value=excluded.value, label=excluded.label""",
        rows,
    )
    conn.commit()
    return len(rows)


def upsert_stablecoins(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """rows: (ts, total_mcap)"""
    conn.executemany(
        """INSERT INTO stablecoins (ts, total_mcap) VALUES (?,?)
           ON CONFLICT(ts) DO UPDATE SET total_mcap=excluded.total_mcap""",
        rows,
    )
    conn.commit()
    return len(rows)


def max_ts(
    conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()
) -> int | None:
    sql = f"SELECT MAX(ts) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    row = conn.execute(sql, params).fetchone()
    return row[0] if row and row[0] is not None else None


def log_run(
    conn: sqlite3.Connection, collector: str, ok: bool, items: int, message: str = ""
) -> None:
    conn.execute(
        "INSERT INTO collector_runs (ts, collector, ok, items, message) VALUES (?,?,?,?,?)",
        (int(time.time() * 1000), collector, 1 if ok else 0, items, message[:500]),
    )
    conn.commit()
