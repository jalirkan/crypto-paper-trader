"""Fear & Greed index (alternative.me) and stablecoin supply (DefiLlama).

Both endpoints return full history in one call, so backfill and incremental
updates are the same operation — upserts make it idempotent.
"""

from __future__ import annotations

from ..http import get_json

FNG_URL = "https://api.alternative.me/fng/"
STABLES_URL = "https://stablecoins.llama.fi/stablecoincharts/all"


def parse_fng(payload: dict) -> list[tuple]:
    """→ (ts_ms, value, label) rows."""
    rows = []
    for item in payload.get("data", []):
        try:
            rows.append(
                (
                    int(item["timestamp"]) * 1000,
                    int(item["value"]),
                    str(item.get("value_classification", "")),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return rows


def fetch_fng() -> list[tuple]:
    return parse_fng(get_json(FNG_URL, {"limit": 0}))  # limit=0 → full history


def parse_stablecoins(payload: list) -> list[tuple]:
    """→ (ts_ms, total_usd_pegged_mcap) rows."""
    rows = []
    for item in payload:
        try:
            ts = int(item["date"]) * 1000
            mcap = float(item["totalCirculatingUSD"]["peggedUSD"])
            rows.append((ts, mcap))
        except (KeyError, ValueError, TypeError):
            continue
    return rows


def fetch_stablecoins() -> list[tuple]:
    return parse_stablecoins(get_json(STABLES_URL))
