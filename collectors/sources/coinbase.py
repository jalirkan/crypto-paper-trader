"""Coinbase Exchange public candles — fallback source (US-friendly, no key).

API returns at most 300 candles per request, NEWEST first:
[[ time_seconds, low, high, open, close, volume ], ...]
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..http import get_json

BASE = "https://api.exchange.coinbase.com"
GRANULARITY = {"1d": 86400, "1h": 3600}
MAX_CANDLES = 300


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def parse_candle_row(symbol: str, tf: str, row: list) -> tuple:
    """Coinbase row → candles table row (note the low/high/open order!)."""
    t_s, low, high, open_, close, volume = row[:6]
    return (
        symbol,
        tf,
        int(t_s) * 1000,
        float(open_),
        float(high),
        float(low),
        float(close),
        float(volume),
        "coinbase",
    )


def fetch_candles(
    product_id: str, display_symbol: str, tf: str, start_ms: int, end_ms: int
) -> list[tuple]:
    """One window (≤300 candles), returned oldest → newest."""
    data = get_json(
        f"{BASE}/products/{product_id}/candles",
        {
            "granularity": GRANULARITY[tf],
            "start": _iso(start_ms),
            "end": _iso(end_ms),
        },
    )
    rows = [parse_candle_row(display_symbol, tf, r) for r in data]
    rows.sort(key=lambda r: r[2])
    return rows


def window_ms(tf: str) -> int:
    """Widest time window a single request can cover."""
    return GRANULARITY[tf] * 1000 * MAX_CANDLES
