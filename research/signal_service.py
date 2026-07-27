"""Signal service — read-only HTTP API over the archive + forward ledger.

Routes (JSON, CORS-open):
  GET /api/signals   current strategy state for all tracked symbols
  GET /api/forward   forward-paper track record vs buy-and-hold
  GET /healthz

Usage:  python -m research.signal_service   (port 8091, CPT_DB to override db)
The dashboard's narrator reads /api/signals via the Next.js proxy route.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import signals

SYMBOLS = ["BTC", "ETH", "SOL"]
CACHE_S = 300  # recompute at most every 5 min


class SignalAPI:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, object]] = {}

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)

    def _cached(self, key: str, fn):
        with self._lock:
            ts, val = self._cache.get(key, (0.0, None))
            if time.time() - ts < CACHE_S and val is not None:
                return val
        val = fn()
        with self._lock:
            self._cache[key] = (time.time(), val)
        return val

    def get_signals(self) -> dict:
        def compute():
            conn = self._conn()
            try:
                states = [
                    s
                    for s in (signals.current_state(conn, sym) for sym in SYMBOLS)
                    if s is not None
                ]
            finally:
                conn.close()
            return {
                "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "note": "Simulated paper strategy — not financial advice.",
                "signals": states,
            }

        return self._cached("signals", compute)

    def get_forward(self) -> dict:
        def compute():
            conn = self._conn()
            try:
                return {
                    "note": "Forward-paper ledger: recorded live, never backfilled.",
                    "symbols": [signals.forward_stats(conn, s) for s in SYMBOLS],
                }
            finally:
                conn.close()

        return self._cached("forward", compute)


def make_handler(api: SignalAPI):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            try:
                if path == "/api/signals":
                    status, body = 200, api.get_signals()
                elif path == "/api/forward":
                    status, body = 200, api.get_forward()
                elif path == "/healthz":
                    status, body = 200, {"ok": True}
                else:
                    status, body = 404, {"error": "not found"}
            except Exception as e:  # noqa: BLE001
                status, body = 500, {"error": str(e)[:200]}
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            pass  # quiet

    return Handler


def main() -> None:
    db = os.environ.get("CPT_DB") or (Path(__file__).resolve().parent.parent / "data" / "archive.db")
    port = int(os.environ.get("SIGNAL_PORT", "8091"))
    api = SignalAPI(db)
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(api))
    print(f"signal service on :{port} (db: {db})")
    server.serve_forever()


if __name__ == "__main__":
    main()
