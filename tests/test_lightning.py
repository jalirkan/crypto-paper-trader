"""Lightning tip-jar tests — fake LND, in-memory DB, loopback HTTP. No network."""

import hashlib
import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from lightning import lnurl, store
from lightning.config import Config
from lightning.service import TipJarService, make_handler
from lightning.testing import FakeLnd

TEST_ENV = {
    "LN_NETWORK": "signet",
    "LN_USERNAME": "tips",
    "LN_DOMAIN": "example.org",
    "TIP_PUBLIC_BASE": "https://example.org",
    "TIP_MIN_SATS": "10",
    "TIP_MAX_SATS": "1000",
    "TIP_RATE_PER_MIN": "5",
    "TIP_DB": ":memory:",
}


def make_cfg():
    return Config(env=dict(TEST_ENV))


class TestLnurlParams(unittest.TestCase):
    def test_pay_params_spec_fields(self):
        cfg = make_cfg()
        p = lnurl.pay_params(cfg)
        self.assertEqual(p["tag"], "payRequest")
        self.assertEqual(p["minSendable"], 10_000)      # msat
        self.assertEqual(p["maxSendable"], 1_000_000)   # msat
        self.assertEqual(p["callback"], "https://example.org/lnurlp/callback")
        meta = json.loads(p["metadata"])
        self.assertIn(["text/identifier", "tips@example.org"], meta)


class TestCallback(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()
        self.client = FakeLnd()
        self.conn = store.connect(":memory:")

    def test_happy_path_returns_invoice_and_records_it(self):
        out = lnurl.handle_callback(self.cfg, self.client, self.conn, "21000", "gm")
        self.assertIn("pr", out)
        self.assertEqual(out["routes"], [])
        # invoice recorded as OPEN
        self.assertEqual(len(store.open_invoices(self.conn)), 1)
        # spec: description_hash must commit to sha256(metadata)
        expected = hashlib.sha256(lnurl.metadata_json(self.cfg).encode()).digest()
        self.assertEqual(self.client.last_add_kwargs["description_hash"], expected)
        self.assertEqual(self.client.last_add_kwargs["value_msat"], 21000)

    def test_rejects_bad_amounts_and_long_comments(self):
        for bad in (None, "abc", "9999", str(1001 * 1000 + 1)):  # <min, >max, junk
            out = lnurl.handle_callback(self.cfg, self.client, self.conn, bad, "")
            self.assertEqual(out.get("status"), "ERROR", bad)
        out = lnurl.handle_callback(self.cfg, self.client, self.conn, "21000", "x" * 999)
        self.assertEqual(out.get("status"), "ERROR")
        self.assertEqual(len(store.open_invoices(self.conn)), 0)  # nothing recorded

    def test_reconcile_settles_and_ledger_reports(self):
        lnurl.handle_callback(self.cfg, self.client, self.conn, "50000", "nice bot")
        self.assertEqual(lnurl.reconcile_once(self.client, self.conn), 0)  # unpaid
        self.client.settle_all()
        self.assertEqual(lnurl.reconcile_once(self.client, self.conn), 1)
        self.assertEqual(lnurl.reconcile_once(self.client, self.conn), 0)  # idempotent
        t = store.totals(self.conn)
        self.assertEqual(t["count"], 1)
        led = store.ledger(self.conn)
        self.assertEqual(led[0]["comment"], "nice bot")
        self.assertEqual(len(store.open_invoices(self.conn)), 0)


class TestServiceHTTP(unittest.TestCase):
    """Spin the real HTTP server on a loopback ephemeral port."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = make_cfg()
        cls.client = FakeLnd()
        cls.conn = store.connect(":memory:")
        svc = TipJarService(cls.cfg, cls.client, cls.conn)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_discovery_endpoint(self):
        status, body = self._get("/.well-known/lnurlp/tips")
        self.assertEqual(status, 200)
        self.assertEqual(body["tag"], "payRequest")

    def test_unknown_user_404(self):
        status, body = self._get("/.well-known/lnurlp/satoshi")
        self.assertEqual(status, 404)
        self.assertEqual(body["status"], "ERROR")

    def test_callback_and_public_ledger(self):
        status, body = self._get("/lnurlp/callback?amount=25000&comment=hello")
        self.assertEqual(status, 200)
        self.assertTrue(body["pr"].startswith("lntbs"))
        self.client.settle_all()
        lnurl.reconcile_once(self.client, self.conn)
        status, tips = self._get("/api/tips")
        self.assertEqual(status, 200)
        self.assertEqual(tips["address"], "tips@example.org")
        self.assertEqual(tips["totals"]["count"], 1)
        self.assertEqual(tips["recent"][0]["comment"], "hello")

    def test_rate_limit_429(self):
        codes = [self._get("/lnurlp/callback?amount=25000")[0] for _ in range(8)]
        self.assertIn(429, codes)

    def test_healthz(self):
        status, body = self._get("/healthz")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["lnd"]["alias"], "fake-lnd")


if __name__ == "__main__":
    unittest.main()
