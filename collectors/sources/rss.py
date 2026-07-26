"""RSS 2.0 / Atom feed parser using stdlib xml.etree — no feedparser dependency.

Namespace-agnostic: matches elements by local name so it handles both formats
and the many slightly-broken feeds in the wild.
"""

from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from ..http import get_text

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(el) -> str:
    return WS_RE.sub(" ", TAG_RE.sub(" ", "".join(el.itertext()))).strip()


def parse_date(raw: str) -> int | None:
    """RFC 822 or ISO 8601 → epoch ms UTC. None if unparseable."""
    raw = raw.strip()
    if not raw:
        return None
    try:  # RFC 822: 'Sun, 26 Jul 2026 14:01:02 +0000'
        return int(parsedate_to_datetime(raw).timestamp() * 1000)
    except (ValueError, TypeError):
        pass
    try:  # ISO 8601: '2026-07-26T14:01:02Z'
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def parse_feed(xml_text: str, source: str) -> list[tuple]:
    """Feed XML → news rows: (id, ts, fetched_ts, source, title, url, summary)."""
    root = ET.fromstring(xml_text)
    fetched_ts = int(time.time() * 1000)

    items = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]
    rows: list[tuple] = []
    for item in items:
        title, url, summary, ts = "", "", "", None
        for child in item:
            name = _local(child.tag)
            if name == "title":
                title = _text(child)
            elif name == "link":
                # RSS: text content. Atom: href attribute (prefer rel=alternate).
                href = child.get("href")
                if href:
                    if not url or child.get("rel") in (None, "alternate"):
                        url = href.strip()
                elif _text(child):
                    url = _text(child)
            elif name in ("description", "summary", "content"):
                if not summary:
                    summary = _text(child)[:500]
            elif name in ("pubdate", "published", "updated", "date") and ts is None:
                ts = parse_date(child.text or "")

        if not title or not url:
            continue
        news_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        rows.append((news_id, ts, fetched_ts, source, title[:400], url, summary))
    return rows


def fetch_feed(url: str, source: str) -> list[tuple]:
    return parse_feed(get_text(url), source)
