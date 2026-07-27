"""GDELT DOC 2.0 API — free historical news headlines, no key.

This is what makes event studies possible TODAY instead of after months of
RSS collection: GDELT indexes global news back years. We backfill crypto
headlines from 2023 onward into the same `news` table the live RSS
collectors write to.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

from ..http import get_json

BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY = '(bitcoin OR ethereum OR solana OR cryptocurrency OR "crypto exchange" OR stablecoin) sourcelang:eng'


def _parse_seendate(raw: str) -> int | None:
    """'20240101T120000Z' → epoch ms."""
    try:
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def parse_articles(payload: dict) -> list[tuple]:
    """GDELT artlist JSON → news rows (id, ts, fetched_ts, source, title, url, summary)."""
    fetched = int(time.time() * 1000)
    rows: list[tuple] = []
    for a in payload.get("articles", []):
        url = (a.get("url") or "").strip()
        title = (a.get("title") or "").strip()
        ts = _parse_seendate(a.get("seendate", ""))
        if not url or not title or ts is None:
            continue
        news_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        rows.append(
            (news_id, ts, fetched, f"gdelt:{a.get('domain', '?')}", title[:400], url, "")
        )
    return rows


def fetch_window(start: str, end: str, max_records: int = 250) -> list[tuple]:
    """One query window. start/end: 'YYYYMMDDHHMMSS'."""
    payload = get_json(
        BASE,
        {
            "query": QUERY,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records,
            "startdatetime": start,
            "enddatetime": end,
            "sort": "hybridrel",
        },
        timeout=30,
        retries=1,  # GDELT 429s need a LONG cooldown — handled per-day by the backfill
    )
    return parse_articles(payload)
