"""The tip-jar HTTP service — stdlib ThreadingHTTPServer, GET-only surface.

Routes (all JSON, CORS-open, read/create-invoice only — nothing can spend):
  GET /.well-known/lnurlp/<user>   LNURL-pay discovery (Lightning Address)
  GET /lnurlp/callback?amount=&comment=   → BOLT11 invoice
  GET /api/tips                    public ledger: totals + recent settled tips
  GET /healthz                     service + LND sync status

Usage:
  python -m lightning.service            # real LND via env config
  python -m lightning.service --demo     # FakeLnd, auto-settles after ~4s
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import lnurl, store
from .config import Config


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


class TipJarService:
    def __init__(self, cfg: Config, client, conn):
        self.cfg = cfg
        self.client = client
        self.conn = conn
        self.limiter = RateLimiter(cfg.rate_per_min)
        self._info_cache: tuple[float, dict] = (0.0, {})

    def lnd_info(self) -> dict:
        ts, info = self._info_cache
        if time.time() - ts > 60:
            try:
                raw = self.client.get_info()
                info = {
                    "alias": raw.get("alias"),
                    "synced": bool(raw.get("synced_to_chain")),
                    "block_height": raw.get("block_height"),
                    "channels": raw.get("num_active_channels"),
                }
            except Exception as e:  # noqa: BLE001
                info = {"error": str(e)[:200]}
            self._info_cache = (time.time(), info)
        return info

    def handle(self, path: str, query: dict, client_ip: str) -> tuple[int, dict]:
        if path == f"/.well-known/lnurlp/{self.cfg.username}":
            return 200, lnurl.pay_params(self.cfg)

        if path.startswith("/.well-known/lnurlp/"):
            return 404, lnurl.error("unknown user")

        if path == "/lnurlp/callback":
            if not self.limiter.allow(client_ip):
                return 429, lnurl.error("rate limited — try again in a minute")
            body = lnurl.handle_callback(
                self.cfg,
                self.client,
                self.conn,
                (query.get("amount") or [None])[0],
                (query.get("comment") or [""])[0],
            )
            return (200 if "pr" in body else 400), body

        if path == "/api/tips":
            return 200, {
                "network": self.cfg.network,
                "address": f"{self.cfg.username}@{self.cfg.domain}",
                "totals": store.totals(self.conn),
                "recent": store.ledger(self.conn),
            }

        if path == "/healthz":
            return 200, {"ok": True, "network": self.cfg.network, "lnd": self.lnd_info()}

        return 404, {"error": "not found"}


def make_handler(svc: TipJarService):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — http.server API
            parsed = urlparse(self.path)
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0]
            try:
                status, body = svc.handle(parsed.path, parse_qs(parsed.query), ip)
            except Exception as e:  # noqa: BLE001 — never crash the server thread
                status, body = 500, {"status": "ERROR", "reason": str(e)[:200]}
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):  # quieter logs
            print(f"[http] {self.client_address[0]} {fmt % args}")

    return Handler


def start_reconciler(svc: TipJarService, interval_s: float = 30.0) -> threading.Thread:
    def loop():
        while True:
            try:
                n = lnurl.reconcile_once(svc.client, svc.conn)
                if n:
                    print(f"[reconcile] {n} invoice(s) settled")
            except Exception as e:  # noqa: BLE001
                print(f"[reconcile] error: {e}")
            time.sleep(interval_s)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def main() -> None:
    ap = argparse.ArgumentParser(description="LNURL tip-jar service for LND.")
    ap.add_argument("--demo", action="store_true", help="run with a fake LND that auto-settles")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    cfg = Config()
    if args.port:
        cfg.port = args.port

    if args.demo:
        from .testing import FakeLnd

        client = FakeLnd()
        cfg.db_path = ":memory:"
        cfg.public_base = f"http://127.0.0.1:{cfg.port}"

        def auto_settle():
            while True:
                time.sleep(4)
                client.settle_all()

        threading.Thread(target=auto_settle, daemon=True).start()
        print("DEMO MODE — fake LND, invoices auto-settle ~4s after creation")
    else:
        from .lnd import LndRestClient

        client = LndRestClient(cfg.lnd_rest_url, cfg.tls_cert, cfg.macaroon_path)

    conn = store.connect(cfg.db_path)
    svc = TipJarService(cfg, client, conn)
    start_reconciler(svc, interval_s=3.0 if args.demo else 30.0)

    server = ThreadingHTTPServer(("0.0.0.0", cfg.port), make_handler(svc))
    print(f"tip jar on :{cfg.port} — {cfg.username}@{cfg.domain} ({cfg.network})")
    print(f"try:  curl 'http://127.0.0.1:{cfg.port}/.well-known/lnurlp/{cfg.username}'")
    server.serve_forever()


if __name__ == "__main__":
    main()
