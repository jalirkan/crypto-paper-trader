"""Binance market data: klines (candles) and perp funding rates.

Klines use data-api.binance.vision first — Binance's public market-data mirror,
which serves in regions where api.binance.com is geo-blocked (e.g. the US).
Funding comes from fapi.binance.com (futures) and may be geo-blocked; the
runner treats funding failures as non-fatal and logs them.
"""

from __future__ import annotations

from ..http import HttpError, get_json

KLINE_BASES = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]
FAPI_BASE = "https://fapi.binance.com"

INTERVAL = {"1d": "1d", "1h": "1h"}
INTERVAL_MS = {"1d": 86_400_000, "1h": 3_600_000}


def parse_kline_row(symbol: str, tf: str, row: list) -> tuple:
    """Binance kline row → candles table row.

    Row layout: [openTime, open, high, low, close, volume, closeTime, ...]
    """
    return (
        symbol,
        tf,
        int(row[0]),
        float(row[1]),
        float(row[2]),
        float(row[3]),
        float(row[4]),
        float(row[5]),
        "binance",
    )


def fetch_klines(
    venue_symbol: str,
    display_symbol: str,
    tf: str,
    start_ms: int,
    end_ms: int | None = None,
    limit: int = 1000,
) -> list[tuple]:
    """Fetch one page of klines starting at start_ms. Returns candle rows."""
    params = {
        "symbol": venue_symbol,
        "interval": INTERVAL[tf],
        "startTime": start_ms,
        "limit": limit,
    }
    if end_ms:
        params["endTime"] = end_ms

    last_err: Exception | None = None
    for base in KLINE_BASES:
        try:
            data = get_json(f"{base}/api/v3/klines", params)
            return [parse_kline_row(display_symbol, tf, r) for r in data]
        except HttpError as e:
            last_err = e
    assert last_err is not None
    raise last_err


def parse_funding_row(item: dict) -> tuple:
    return (
        item["symbol"],
        int(item["fundingTime"]),
        float(item["fundingRate"]),
        "binance",
    )


def fetch_funding(venue_symbol: str, start_ms: int, limit: int = 1000) -> list[tuple]:
    """One page of historical funding rates (8h epochs)."""
    data = get_json(
        f"{FAPI_BASE}/fapi/v1/fundingRate",
        {"symbol": venue_symbol, "startTime": start_ms, "limit": limit},
    )
    return [parse_funding_row(item) for item in data]
