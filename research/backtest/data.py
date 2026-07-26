"""Load price series from the archive. Stdlib only."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "archive.db"


class DataError(Exception):
    pass


def load_closes(
    symbol: str, tf: str = "1d", db_path: str | Path | None = None
) -> tuple[list[int], list[float]]:
    """Daily/hourly close series for one symbol, oldest → newest."""
    path = Path(db_path or DEFAULT_DB)
    if not path.exists():
        raise DataError(
            f"No archive at {path}. Run `python -m collectors.backfill` first."
        )
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    try:
        rows = conn.execute(
            "SELECT ts, close FROM candles WHERE symbol=? AND tf=? ORDER BY ts",
            (symbol, tf),
        ).fetchall()
    finally:
        conn.close()
    if len(rows) < 250:
        raise DataError(
            f"Only {len(rows)} {tf} candles for {symbol} — need ≥250. "
            "Run the backfill."
        )
    ts = [r[0] for r in rows]
    closes = [float(r[1]) for r in rows]
    return ts, closes


def available_symbols(db_path: str | Path | None = None) -> list[str]:
    path = Path(db_path or DEFAULT_DB)
    if not path.exists():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    try:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM candles WHERE tf='1d' ORDER BY symbol"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]
