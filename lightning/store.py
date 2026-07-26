"""Tips ledger — SQLite, idempotent, append-only in spirit."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tips_invoices (
  r_hash      TEXT PRIMARY KEY,
  bolt11      TEXT NOT NULL,
  amount_msat INTEGER NOT NULL,
  memo        TEXT,
  comment     TEXT,
  created_ts  INTEGER NOT NULL,
  state       TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN | SETTLED | EXPIRED
  settled_ts  INTEGER,
  paid_msat   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tips_state ON tips_invoices (state);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.executescript(SCHEMA)
    return conn


def record_invoice(
    conn, r_hash: str, bolt11: str, amount_msat: int, memo: str, comment: str
) -> None:
    conn.execute(
        """INSERT INTO tips_invoices (r_hash, bolt11, amount_msat, memo, comment, created_ts)
           VALUES (?,?,?,?,?,?) ON CONFLICT(r_hash) DO NOTHING""",
        (r_hash, bolt11, amount_msat, memo, comment, int(time.time() * 1000)),
    )
    conn.commit()


def open_invoices(conn, max_age_ms: int = 48 * 3600 * 1000) -> list[str]:
    cutoff = int(time.time() * 1000) - max_age_ms
    return [
        r[0]
        for r in conn.execute(
            "SELECT r_hash FROM tips_invoices WHERE state='OPEN' AND created_ts > ?",
            (cutoff,),
        )
    ]


def mark_settled(conn, r_hash: str, settled_ts_ms: int, paid_msat: int) -> None:
    conn.execute(
        """UPDATE tips_invoices SET state='SETTLED', settled_ts=?, paid_msat=?
           WHERE r_hash=? AND state != 'SETTLED'""",
        (settled_ts_ms or int(time.time() * 1000), paid_msat, r_hash),
    )
    conn.commit()


def mark_expired(conn, max_age_ms: int = 48 * 3600 * 1000) -> None:
    cutoff = int(time.time() * 1000) - max_age_ms
    conn.execute(
        "UPDATE tips_invoices SET state='EXPIRED' WHERE state='OPEN' AND created_ts <= ?",
        (cutoff,),
    )
    conn.commit()


def totals(conn) -> dict:
    n, msat = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(paid_msat),0) FROM tips_invoices WHERE state='SETTLED'"
    ).fetchone()
    return {"count": n, "total_sats": msat // 1000}


def ledger(conn, limit: int = 25) -> list[dict]:
    rows = conn.execute(
        """SELECT settled_ts, paid_msat, comment FROM tips_invoices
           WHERE state='SETTLED' ORDER BY settled_ts DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [
        {"ts": r[0], "sats": (r[1] or 0) // 1000, "comment": (r[2] or "")[:140]}
        for r in rows
    ]
