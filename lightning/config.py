"""Tip-jar service configuration — all via environment, stdlib only.

Security model in one paragraph: this service NEVER sees the wallet seed or the
admin macaroon. It authenticates to LND with an *invoice-only* macaroon
(`invoices:read invoices:write`), so a full compromise of this process could
create invoices but never move a satoshi. The seed exists only on paper; the
admin macaroon never leaves the VPS user that owns LND.
"""

from __future__ import annotations

import os
from pathlib import Path


class Config:
    def __init__(self, env: dict | None = None):
        e = env if env is not None else dict(os.environ)
        self.network = e.get("LN_NETWORK", "signet")
        self.lnd_rest_url = e.get("LND_REST_URL", "https://127.0.0.1:8080")
        self.tls_cert = e.get("LND_TLS_CERT", str(Path.home() / ".lnd" / "tls.cert"))
        self.macaroon_path = e.get(
            "LND_MACAROON",
            str(
                Path.home()
                / ".lnd" / "data" / "chain" / "bitcoin" / self.network / "invoice.macaroon"
            ),
        )
        self.username = e.get("LN_USERNAME", "tips")
        self.domain = e.get("LN_DOMAIN", "localhost")
        # Public base URL for LNURL callbacks (behind Caddy in production).
        self.public_base = e.get("TIP_PUBLIC_BASE", f"https://{self.domain}")
        self.min_sats = int(e.get("TIP_MIN_SATS", "10"))
        self.max_sats = int(e.get("TIP_MAX_SATS", "500000"))
        self.comment_len = int(e.get("TIP_COMMENT_LEN", "140"))
        self.db_path = e.get("TIP_DB", "data/tips.db")
        self.port = int(e.get("TIP_PORT", "8090"))
        self.rate_per_min = int(e.get("TIP_RATE_PER_MIN", "10"))
        self.invoice_expiry_s = int(e.get("TIP_INVOICE_EXPIRY", "3600"))
