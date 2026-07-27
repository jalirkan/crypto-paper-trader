"""The OMS journal — SQLite, write-ahead of every exchange interaction."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .types import LIVE, Fill, Order, now_ms

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  client_id  TEXT PRIMARY KEY,
  symbol     TEXT NOT NULL,
  side       TEXT NOT NULL,
  qty        REAL NOT NULL,
  limit_px   REAL NOT NULL,
  state      TEXT NOT NULL,
  exchange_id TEXT,
  filled_qty REAL NOT NULL DEFAULT 0,
  avg_px     REAL NOT NULL DEFAULT 0,
  reason     TEXT DEFAULT '',
  created_ts INTEGER NOT NULL,
  updated_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
  trade_id  TEXT PRIMARY KEY,      -- idempotency: a fill applies exactly once
  client_id TEXT NOT NULL,
  qty       REAL NOT NULL,
  px        REAL NOT NULL,
  ts        INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  ts     INTEGER NOT NULL,
  kind   TEXT NOT NULL,
  detail TEXT
);
"""


class Journal:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    # ---- orders ----

    def write_order(self, o: Order) -> None:
        self.conn.execute(
            """INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(client_id) DO UPDATE SET
                 state=excluded.state, exchange_id=excluded.exchange_id,
                 filled_qty=excluded.filled_qty, avg_px=excluded.avg_px,
                 reason=excluded.reason, updated_ts=excluded.updated_ts""",
            (
                o.client_id, o.symbol, o.side, o.qty, o.limit_px, o.state,
                o.exchange_id, o.filled_qty, o.avg_px, o.reason,
                o.created_ts, o.updated_ts,
            ),
        )
        self.conn.commit()

    def get_order(self, client_id: str) -> Order | None:
        row = self.conn.execute(
            "SELECT * FROM orders WHERE client_id=?", (client_id,)
        ).fetchone()
        return self._to_order(row) if row else None

    def live_orders(self, symbol: str | None = None) -> list[Order]:
        q = f"SELECT * FROM orders WHERE state IN ({','.join('?' * len(LIVE))})"
        params: list = list(LIVE)
        if symbol:
            q += " AND symbol=?"
            params.append(symbol)
        return [self._to_order(r) for r in self.conn.execute(q, params)]

    @staticmethod
    def _to_order(r) -> Order:
        return Order(
            client_id=r[0], symbol=r[1], side=r[2], qty=r[3], limit_px=r[4],
            state=r[5], exchange_id=r[6], filled_qty=r[7], avg_px=r[8],
            reason=r[9], created_ts=r[10], updated_ts=r[11],
        )

    # ---- fills (idempotent by trade_id) ----

    def apply_fill(self, f: Fill) -> bool:
        """Returns True if this fill was NEW (not a duplicate report)."""
        cur = self.conn.execute(
            "INSERT INTO fills VALUES (?,?,?,?,?) ON CONFLICT(trade_id) DO NOTHING",
            (f.trade_id, f.client_id, f.qty, f.px, f.ts),
        )
        if cur.rowcount == 0:
            return False
        o = self.get_order(f.client_id)
        if o is not None:
            new_filled = o.filled_qty + f.qty
            o.avg_px = (o.avg_px * o.filled_qty + f.px * f.qty) / new_filled
            o.filled_qty = new_filled
            o.state = "FILLED" if o.filled_qty >= o.qty - 1e-12 else "PARTIALLY_FILLED"
            o.updated_ts = now_ms()
            self.write_order(o)
        self.conn.commit()
        return True

    def position(self, symbol: str) -> float:
        row = self.conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN o.side='buy' THEN f.qty ELSE -f.qty END), 0)
               FROM fills f JOIN orders o ON o.client_id = f.client_id
               WHERE o.symbol=?""",
            (symbol,),
        ).fetchone()
        return float(row[0])

    # ---- meta / events ----

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def event(self, kind: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO events (ts, kind, detail) VALUES (?,?,?)",
            (now_ms(), kind, detail[:500]),
        )
        self.conn.commit()
