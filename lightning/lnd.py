"""Minimal LND REST client (stdlib only).

Auth: `Grpc-Metadata-macaroon` header, hex-encoded macaroon bytes.
TLS: LND's self-signed cert is pinned by loading it as the CA. Its SANs include
127.0.0.1/localhost, so verification passes for a same-host service.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path


class LndError(Exception):
    pass


def _b64_to_hex(s: str) -> str:
    return base64.b64decode(s).hex()


class LndRestClient:
    def __init__(
        self,
        base_url: str,
        tls_cert_path: str | None = None,
        macaroon_path: str | None = None,
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self._macaroon_hex = ""
        if macaroon_path:
            self._macaroon_hex = Path(macaroon_path).read_bytes().hex()

        if os.environ.get("LND_TLS_SKIP_VERIFY") == "1":
            self._ctx = ssl._create_unverified_context()  # dev escape hatch only
        elif tls_cert_path and Path(tls_cert_path).exists():
            self._ctx = ssl.create_default_context(cafile=tls_cert_path)
        else:
            self._ctx = ssl.create_default_context()

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Grpc-Metadata-macaroon": self._macaroon_hex,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as res:
                return json.loads(res.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            raise LndError(f"LND {method} {path} → {e.code}: {body}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LndError(f"LND unreachable at {url}: {e}") from e

    # --- API surface the tip jar needs (invoice-only macaroon suffices) ---

    def get_info(self) -> dict:
        return self._call("GET", "/v1/getinfo")

    def add_invoice(
        self,
        value_msat: int,
        memo: str = "",
        description_hash: bytes | None = None,
        expiry_s: int = 3600,
    ) -> dict:
        """Create an invoice. Returns {r_hash_hex, payment_request, add_index}."""
        payload: dict = {
            "value_msat": str(value_msat),
            "memo": memo,
            "expiry": str(expiry_s),
            "private": True,  # include route hints for our unannounced channels
        }
        if description_hash is not None:
            payload["description_hash"] = base64.b64encode(description_hash).decode()
        raw = self._call("POST", "/v1/invoices", payload)
        return {
            "r_hash_hex": _b64_to_hex(raw["r_hash"]),
            "payment_request": raw["payment_request"],
            "add_index": int(raw.get("add_index", 0)),
        }

    def lookup_invoice(self, r_hash_hex: str) -> dict:
        """Returns {settled, state, amt_paid_msat, settle_ts_ms}."""
        raw = self._call("GET", f"/v1/invoice/{r_hash_hex}")
        settled = raw.get("state") == "SETTLED" or bool(raw.get("settled"))
        return {
            "settled": settled,
            "state": raw.get("state", "OPEN"),
            "amt_paid_msat": int(raw.get("amt_paid_msat", 0) or 0),
            "settle_ts_ms": int(raw.get("settle_date", 0) or 0) * 1000,
        }
