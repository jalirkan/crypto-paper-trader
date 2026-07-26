"""LNURL-pay (LUD-06) + Lightning Address (LUD-16) + comments (LUD-12),
implemented from spec against LND's REST API.

Flow: a wallet resolving `tips@domain` GETs
  https://domain/.well-known/lnurlp/tips        → pay parameters (this module)
  <callback>?amount=<msat>&comment=...          → BOLT11 invoice (this module)

Spec compliance detail worth noticing: the invoice commits to
sha256(metadata) as its description_hash, which is how the payer's wallet
cryptographically ties the invoice to what was displayed.
"""

from __future__ import annotations

import hashlib
import json

from . import store
from .config import Config


def metadata_json(cfg: Config) -> str:
    return json.dumps(
        [
            ["text/plain", "Tip the crypto-paper-trader live experiment"],
            ["text/identifier", f"{cfg.username}@{cfg.domain}"],
        ],
        separators=(",", ":"),
    )


def pay_params(cfg: Config) -> dict:
    return {
        "callback": f"{cfg.public_base}/lnurlp/callback",
        "minSendable": cfg.min_sats * 1000,
        "maxSendable": cfg.max_sats * 1000,
        "metadata": metadata_json(cfg),
        "commentAllowed": cfg.comment_len,
        "tag": "payRequest",
    }


def error(reason: str) -> dict:
    return {"status": "ERROR", "reason": reason}


def handle_callback(cfg: Config, client, conn, amount_raw, comment: str = "") -> dict:
    """Validate a wallet's callback and return {"pr": bolt11, "routes": []}."""
    try:
        amount_msat = int(amount_raw)
    except (TypeError, ValueError):
        return error("amount must be an integer number of millisatoshis")

    if amount_msat < cfg.min_sats * 1000 or amount_msat > cfg.max_sats * 1000:
        return error(
            f"amount out of range ({cfg.min_sats}–{cfg.max_sats} sats)"
        )
    comment = (comment or "").strip()
    if len(comment) > cfg.comment_len:
        return error(f"comment too long (max {cfg.comment_len} chars)")

    meta = metadata_json(cfg)
    try:
        inv = client.add_invoice(
            value_msat=amount_msat,
            memo=f"tip → {cfg.username}@{cfg.domain}",
            description_hash=hashlib.sha256(meta.encode()).digest(),
            expiry_s=cfg.invoice_expiry_s,
        )
    except Exception as e:  # noqa: BLE001 — wallet-facing error must be JSON
        return error(f"could not create invoice: {e}")

    store.record_invoice(
        conn, inv["r_hash_hex"], inv["payment_request"], amount_msat,
        memo=f"tip:{cfg.username}", comment=comment,
    )
    return {"pr": inv["payment_request"], "routes": []}


def reconcile_once(client, conn) -> int:
    """Poll LND for settlement of open invoices. Returns newly settled count."""
    settled = 0
    for r_hash in store.open_invoices(conn):
        try:
            info = client.lookup_invoice(r_hash)
        except Exception:  # noqa: BLE001 — one bad lookup shouldn't stop the rest
            continue
        if info["settled"]:
            store.mark_settled(conn, r_hash, info["settle_ts_ms"], info["amt_paid_msat"])
            settled += 1
    store.mark_expired(conn)
    return settled
