"""Binance's public data mirror — historical funding rates as monthly CSV dumps.

Why this exists: `fapi.binance.com` (the futures API) geo-blocks US IPs, which
is what kept EXP-006 blocked and drove the whole VPS plan. But Binance also
publishes the same history as static files on data.binance.vision, and static
file hosting is NOT geo-restricted — verified 2026-07-31 from a US residential
connection, HTTP 200.

So the entire multi-year funding history is downloadable locally, in bulk,
with no rate limits and no dependency on where a server sits. This is strictly
better than the API path it replaces: one request per symbol-month instead of
paginated 1000-row pages.

URL shape:
  .../data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip

Each zip holds one CSV: calc_time, funding_interval_hours, last_funding_rate.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date

from ..http import HttpError, get_bytes

BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"


def month_url(symbol: str, year: int, month: int) -> str:
    return f"{BASE}/{symbol}/{symbol}-fundingRate-{year:04d}-{month:02d}.zip"


def parse_funding_csv(raw: bytes, symbol: str) -> list[tuple]:
    """Zip bytes → funding rows (symbol, ts_ms, rate, source).

    Tolerates a header row or its absence, and skips malformed lines rather
    than aborting a month for one bad record.
    """
    rows: list[tuple] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = zf.namelist()[0]
        text = zf.read(name).decode("utf-8", errors="replace")

    for parts in csv.reader(io.StringIO(text)):
        if len(parts) < 3:
            continue
        try:
            ts = int(float(parts[0]))
            rate = float(parts[2])
        except (ValueError, TypeError):
            continue  # header row, or junk
        # Binance switched to microseconds in some dumps; normalise to ms.
        if ts > 10**14:
            ts //= 1000
        rows.append((symbol, ts, rate, "binance-vision"))
    return rows


def fetch_funding_month(symbol: str, year: int, month: int) -> list[tuple]:
    """One symbol-month. Returns [] for months Binance hasn't published."""
    try:
        raw = get_bytes(month_url(symbol, year, month), timeout=30, retries=2)
    except HttpError as e:
        if e.status == 404:
            return []  # month predates the contract, or isn't published yet
        raise
    return parse_funding_csv(raw, symbol)


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out
