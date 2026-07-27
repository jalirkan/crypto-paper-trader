"""Batch-classify news headlines with Claude into structured event labels.

Usage:
    python -m research.events.classify --limit 200          # newest unlabeled first
    python -m research.events.classify --limit 0            # everything unlabeled

Cost: ~10 headlines/request on claude-haiku-4-5 ≈ $0.10–0.25 per 1,000
headlines. A full 3-year GDELT backfill (~50–150k headlines) runs $10–30 —
run it once, filtered classification thereafter is pennies. Requires
ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

from . import EVENT_TYPES, LABELS_SCHEMA

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "archive.db"
BATCH = 10

SYSTEM = f"""You label crypto news headlines for a quantitative event study. For EACH headline, judge whether it is potentially market-moving crypto news and classify it.

Fields per item:
- id: echo back unchanged
- relevant: 1 if plausibly market-moving crypto news, else 0 (price recaps, listicles, opinion, ads → 0)
- event_type: one of {json.dumps(EVENT_TYPES)}
- assets: affected symbols from [BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, LINK, LTC] as CSV, or "MARKET" if crypto-wide
- direction: -1 bearish, 0 unclear, 1 bullish — for the affected assets
- magnitude: 1 minor, 2 notable, 3 major
- novelty: 1 if this reads like a first report of a new fact; 0 if follow-up, analysis, or rehash
- confidence: low | medium | high

Respond with ONLY a JSON array, one object per input item, same order, no markdown fences."""


def parse_response(text: str) -> list[dict]:
    """Tolerant parse: strip fences, find the array, validate items."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array in response")
    items = json.loads(cleaned[start : end + 1])
    out = []
    for it in items:
        out.append(
            {
                "id": str(it["id"]),
                "relevant": 1 if it.get("relevant") else 0,
                "event_type": it.get("event_type") if it.get("event_type") in EVENT_TYPES else "other",
                "assets": str(it.get("assets") or "MARKET")[:100],
                "direction": max(-1, min(1, int(it.get("direction", 0)))),
                "magnitude": max(1, min(3, int(it.get("magnitude", 1)))),
                "novelty": 1 if it.get("novelty") else 0,
                "confidence": it.get("confidence") if it.get("confidence") in ("low", "medium", "high") else "low",
            }
        )
    return out


def call_claude(api_key: str, model: str, headlines: list[dict]) -> list[dict]:
    payload = {
        "model": model,
        "max_tokens": 2000,
        "system": SYSTEM,
        "messages": [
            {
                "role": "user",
                "content": json.dumps(
                    [{"id": h["id"], "title": h["title"], "source": h["source"]} for h in headlines]
                ),
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as res:
        data = json.loads(res.read().decode())
    text = next(b.get("text", "") for b in data["content"] if b.get("type") == "text")
    return parse_response(text)


def save_labels(conn: sqlite3.Connection, labels: list[dict], model: str) -> None:
    now = int(time.time() * 1000)
    conn.executemany(
        """INSERT INTO news_labels
           (news_id, model, labeled_ts, relevant, event_type, assets, direction,
            magnitude, novelty, confidence, raw_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(news_id) DO NOTHING""",
        [
            (
                lb["id"], model, now, lb["relevant"], lb["event_type"], lb["assets"],
                lb["direction"], lb["magnitude"], lb["novelty"], lb["confidence"],
                json.dumps(lb),
            )
            for lb in labels
        ],
    )
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200, help="0 = all unlabeled")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY (see .env.example)")
    model = os.environ.get("EVENT_MODEL", "claude-haiku-4-5-20251001")

    conn = sqlite3.connect(args.db)
    conn.executescript(LABELS_SCHEMA)
    q = """SELECT n.id, n.title, n.source FROM news n
           LEFT JOIN news_labels l ON l.news_id = n.id
           WHERE l.news_id IS NULL AND n.ts IS NOT NULL ORDER BY n.ts DESC"""
    rows = conn.execute(q + (f" LIMIT {args.limit}" if args.limit else "")).fetchall()
    if not rows:
        print("Nothing unlabeled.")
        return

    print(f"Classifying {len(rows)} headlines with {model} (batches of {BATCH})…")
    done = 0
    for i in range(0, len(rows), BATCH):
        batch = [{"id": r[0], "title": r[1], "source": r[2]} for r in rows[i : i + BATCH]]
        try:
            labels = call_claude(api_key, model, batch)
            save_labels(conn, labels, model)
            done += len(labels)
            print(f"  {done}/{len(rows)}", end="\r")
        except Exception as e:  # noqa: BLE001 — skip bad batches, keep going
            print(f"\n  batch {i//BATCH} failed: {e}")
        time.sleep(0.4)

    n_rel = conn.execute("SELECT COUNT(*) FROM news_labels WHERE relevant=1").fetchone()[0]
    print(f"\nDone. Labeled {done}; {n_rel} total relevant events in archive.")


if __name__ == "__main__":
    main()
