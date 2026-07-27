"""Live strategy signals + the forward-paper ledger.

This is where the forward-paper clock ticks (RESEARCH_PLAN §7): every day the
current Donchian state per symbol is recorded to `forward_paper`. Those rows
are immutable history — the strategy's public track record — and the stats we
quote are computed from them, never from a backtest.

Live parameter rule (mirrors EXP-001's walk-forward): params are re-selected
every 90 bars using the trailing 365 bars, scored by net Sharpe. Between
boundaries, params stay fixed.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .backtest import engine
from .backtest.strategies import STRATEGY_SPECS, donchian

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "archive.db"

STRATEGY = "donchian"  # EXP-001 survivor; ma_cross/tsmom were killed
TRAIN_BARS = 365
RESELECT_EVERY = 90
FEE_BPS, SLIP_BPS = 10.0, 5.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS forward_paper (
  day     TEXT NOT NULL,      -- YYYY-MM-DD (UTC) of the bar's open time
  symbol  TEXT NOT NULL,
  weight  REAL NOT NULL,      -- position decided at that day's close
  close   REAL NOT NULL,
  params  TEXT NOT NULL,
  recorded_ts INTEGER NOT NULL,
  PRIMARY KEY (day, symbol)
);
"""


def _day(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts_ms / 1000))


def _load(conn: sqlite3.Connection, symbol: str) -> tuple[list[int], list[float]]:
    rows = conn.execute(
        "SELECT ts, close FROM candles WHERE symbol=? AND tf='1d' ORDER BY ts",
        (symbol,),
    ).fetchall()
    return [r[0] for r in rows], [float(r[1]) for r in rows]


def select_params(closes: list[float]) -> dict:
    """Params chosen on the trailing TRAIN_BARS as of the last reselection boundary."""
    n = len(closes)
    boundary = (n // RESELECT_EVERY) * RESELECT_EVERY
    boundary = max(boundary, TRAIN_BARS)
    train = closes[max(0, boundary - TRAIN_BARS) : boundary]

    best_params, best_score = STRATEGY_SPECS[STRATEGY]["grid"][0], float("-inf")
    for params in STRATEGY_SPECS[STRATEGY]["grid"]:
        w = STRATEGY_SPECS[STRATEGY]["fn"](train, **params)
        score = engine.run(train, w, FEE_BPS, SLIP_BPS).stats["sharpe"]
        if score > best_score:
            best_params, best_score = params, score
    return best_params


def current_state(conn: sqlite3.Connection, symbol: str) -> dict | None:
    """Full live state for one symbol — everything the narrator needs."""
    ts, closes = _load(conn, symbol)
    if len(closes) < TRAIN_BARS + 5:
        return None

    params = select_params(closes)
    entry, exit_ = params["entry"], max(params["entry"] // 2, 5)
    weights = donchian(closes, **params)

    w_now = weights[-1]
    # Days since the position last flipped.
    flip_idx = len(weights) - 1
    while flip_idx > 0 and weights[flip_idx - 1] == w_now:
        flip_idx -= 1

    return {
        "symbol": symbol,
        "strategy": "Donchian breakout",
        "params": params,
        "position": "LONG" if w_now == 1.0 else "FLAT",
        "since": _day(ts[flip_idx]),
        "days_in_state": len(weights) - flip_idx,
        "close": closes[-1],
        "bar_day": _day(ts[-1]),
        "entry_level": max(closes[-entry:]),   # breakout price that triggers/holds long
        "exit_level": min(closes[-exit_:]),    # breakdown price that exits
        "change_30d_pct": round((closes[-1] / closes[-31] - 1) * 100, 2)
        if len(closes) > 31
        else None,
    }


def record_daily(conn: sqlite3.Connection, symbols: list[str]) -> int:
    """Append today's decided weight per symbol. Idempotent per (day, symbol)."""
    conn.executescript(SCHEMA)
    written = 0
    for symbol in symbols:
        state = current_state(conn, symbol)
        if state is None:
            continue
        cur = conn.execute(
            """INSERT INTO forward_paper (day, symbol, weight, close, params, recorded_ts)
               VALUES (?,?,?,?,?,?) ON CONFLICT(day, symbol) DO NOTHING""",
            (
                state["bar_day"],
                symbol,
                1.0 if state["position"] == "LONG" else 0.0,
                state["close"],
                str(state["params"]),
                int(time.time() * 1000),
            ),
        )
        written += cur.rowcount if cur.rowcount > 0 else 0
    conn.commit()
    return written


def forward_stats(conn: sqlite3.Connection, symbol: str) -> dict | None:
    """Track-record stats from the immutable forward ledger (not backtest!)."""
    from .backtest import metrics

    rows = conn.execute(
        "SELECT weight, close FROM forward_paper WHERE symbol=? ORDER BY day",
        (symbol,),
    ).fetchall()
    if len(rows) < 3:
        return {"symbol": symbol, "days": len(rows), "note": "forward ledger warming up"}

    weights = [r[0] for r in rows]
    closes = [r[1] for r in rows]
    res = engine.run(closes, weights, FEE_BPS, SLIP_BPS)
    bh = engine.buy_and_hold(closes, FEE_BPS, SLIP_BPS)
    return {
        "symbol": symbol,
        "start": conn.execute(
            "SELECT MIN(day) FROM forward_paper WHERE symbol=?", (symbol,)
        ).fetchone()[0],
        "days": len(rows),
        "strategy": res.stats,
        "buy_hold": bh.stats,
    }
