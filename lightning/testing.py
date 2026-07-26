"""A fake LND for tests and the --demo mode. Same surface as LndRestClient."""

from __future__ import annotations

import hashlib
import time


class FakeLnd:
    def __init__(self):
        self.counter = 0
        self.invoices: dict[str, dict] = {}
        self.last_add_kwargs: dict = {}

    def get_info(self) -> dict:
        return {
            "alias": "fake-lnd",
            "identity_pubkey": "02" + "ab" * 32,
            "synced_to_chain": True,
            "block_height": 200000,
            "num_active_channels": 1,
        }

    def add_invoice(self, value_msat, memo="", description_hash=None, expiry_s=3600):
        self.counter += 1
        self.last_add_kwargs = {
            "value_msat": value_msat,
            "memo": memo,
            "description_hash": description_hash,
            "expiry_s": expiry_s,
        }
        r_hash = hashlib.sha256(f"fake-{self.counter}".encode()).hexdigest()
        bolt11 = f"lntbs{value_msat}n1fake{self.counter:06d}"
        self.invoices[r_hash] = {
            "settled": False,
            "value_msat": int(value_msat),
            "amt_paid_msat": 0,
            "settle_ts_ms": 0,
            "payment_request": bolt11,
        }
        return {"r_hash_hex": r_hash, "payment_request": bolt11, "add_index": self.counter}

    def lookup_invoice(self, r_hash_hex: str) -> dict:
        inv = self.invoices[r_hash_hex]
        return {
            "settled": inv["settled"],
            "state": "SETTLED" if inv["settled"] else "OPEN",
            "amt_paid_msat": inv["amt_paid_msat"],
            "settle_ts_ms": inv["settle_ts_ms"],
        }

    # --- test/demo hooks ---

    def settle(self, r_hash_hex: str, amt_msat: int | None = None) -> None:
        inv = self.invoices[r_hash_hex]
        inv["settled"] = True
        inv["amt_paid_msat"] = amt_msat or inv["value_msat"]
        inv["settle_ts_ms"] = int(time.time() * 1000)

    def settle_all(self) -> None:
        for rh in list(self.invoices):
            if not self.invoices[rh]["settled"]:
                self.settle(rh)
