"""Sweep-tooling tests — fixture xpub, known-answer vectors, no network.

The security-relevant tests are the ones at the bottom: they assert that the
sweep module cannot spend, sign, or broadcast, by inspecting what it actually
exposes rather than trusting the docstring.
"""

import hashlib
import inspect
import unittest

from lightning import bip32, sweep

# BIP84 test vectors — account 0 of the standard "abandon … about" mnemonic.
# Matching all three at once exercises base58check, secp256k1 point addition,
# CKDpub, hash160 and bech32 together; a fault in any one of them changes the
# output completely.
BIP84_ZPUB = (
    "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtf"
    "SdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs"
)
BIP84_ADDRESSES = {
    "0/0": "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu",
    "0/1": "bc1qnjg0jd8228aq7egyzacy8cys3knf9xvrerkf9g",
    "1/0": "bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el",
}

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58check_encode(payload: bytes) -> str:
    """Test-only helper, so we can build a deliberately invalid extended key."""
    raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    num = int.from_bytes(raw, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = B58[rem] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


class TestPrimitives(unittest.TestCase):
    def test_pure_python_ripemd160_matches_hashlib(self):
        # The fallback exists because OpenSSL 3 disables ripemd160 on the
        # target VPS; it has to agree with the reference exactly.
        for data in (b"", b"abc", b"a" * 200, bytes(range(256))):
            self.assertEqual(
                bip32._ripemd160_py(data),
                hashlib.new("ripemd160", data).digest(),
            )

    def test_base58_checksum_is_enforced(self):
        mangled = BIP84_ZPUB[:-1] + ("q" if BIP84_ZPUB[-1] != "q" else "p")
        with self.assertRaises(ValueError):
            bip32.parse_xpub(mangled)

    def test_point_on_curve_is_validated(self):
        with self.assertRaises(ValueError):
            bip32.parse_p(b"\x02" + b"\xff" * 32)


class TestDerivation(unittest.TestCase):
    def setUp(self):
        self.xpub = bip32.parse_xpub(BIP84_ZPUB)

    def test_known_answer_addresses(self):
        for path, expected in BIP84_ADDRESSES.items():
            self.assertEqual(self.xpub.address(path), expected, path)

    def test_indices_do_not_collide(self):
        addrs = {self.xpub.address(f"0/{i}") for i in range(8)}
        self.assertEqual(len(addrs), 8)

    def test_hardened_index_is_rejected(self):
        with self.assertRaises(ValueError):
            self.xpub.child(2**31)
        for path in ("0'", "0/1h", "44'/0'/0'"):
            with self.assertRaises(ValueError):
                self.xpub.derive_path(path)


class TestKeyTypeRefusal(unittest.TestCase):
    """A private key must not be loadable, not merely unused."""

    def test_xprv_version_is_refused(self):
        xprv_version = (0x0488ADE4).to_bytes(4, "big")
        body = bip32.b58check_decode(BIP84_ZPUB)
        forged = b58check_encode(xprv_version + body[4:])
        with self.assertRaises(ValueError) as ctx:
            bip32.parse_xpub(forged)
        self.assertIn("PUBLIC", str(ctx.exception))

    def test_module_has_no_private_key_entry_points(self):
        banned = ("xprv", "seed", "mnemonic", "privkey", "private_key", "sign")
        for name in dir(bip32):
            if name.startswith("_"):
                continue
            self.assertFalse(
                any(b in name.lower() for b in banned),
                f"bip32 exposes {name!r}, which suggests a private-key path",
            )


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.xpub = bip32.parse_xpub(BIP84_ZPUB)

    def plan(self, confirmed, **kw):
        return sweep.plan_sweep(self.xpub, confirmed_sats=confirmed, index=0, **kw)

    def test_below_threshold_does_not_sweep(self):
        p = self.plan(199_999, threshold_sats=200_000)
        self.assertFalse(p.should_sweep)
        self.assertIn("below", p.reason)

    def test_above_threshold_sweeps_balance_less_reserve(self):
        p = self.plan(500_000, threshold_sats=200_000, reserve_sats=15_000)
        self.assertTrue(p.should_sweep)
        self.assertEqual(p.amount_sats, 485_000)

    def test_reserve_can_block_a_sweep(self):
        p = self.plan(200_000, threshold_sats=200_000, reserve_sats=200_000)
        self.assertFalse(p.should_sweep)
        self.assertIn("reserve", p.reason)

    def test_destination_matches_the_derivation_it_reports(self):
        p = self.plan(500_000)
        self.assertEqual(p.address, self.xpub.address(p.path))
        self.assertEqual(p.address, BIP84_ADDRESSES["0/0"])

    def test_summary_states_nothing_was_signed(self):
        out = sweep.render_plan(self.plan(500_000))
        self.assertIn("nothing has been signed or sent", out)
        for token in (BIP84_ADDRESSES["0/0"], "485,000", "psbt fund"):
            self.assertIn(token, out)

    def test_no_sweep_summary_offers_no_commands(self):
        out = sweep.render_plan(self.plan(1_000))
        self.assertIn("NO SWEEP", out)
        self.assertNotIn("psbt fund", out)
        self.assertNotIn("publishtx", out)


class TestStructurallyCannotSpend(unittest.TestCase):
    """These are the tests the design claim rests on."""

    def test_client_is_get_only(self):
        src = inspect.getsource(sweep.ReadOnlyLnd)
        for verb in ('"POST"', '"PUT"', '"DELETE"', '"PATCH"'):
            self.assertNotIn(verb, src)
        methods = [m for m in dir(sweep.ReadOnlyLnd) if not m.startswith("__")]
        self.assertEqual(sorted(methods), ["_get", "confirmed_balance_sats", "fee_rate_sat_vb"])

    def test_module_exposes_no_send_path(self):
        banned = ("broadcast", "publish", "sign", "finalize", "sendcoins", "sendmany")
        for name, obj in vars(sweep).items():
            if name.startswith("_") or not callable(obj):
                continue
            self.assertFalse(
                any(b in name.lower() for b in banned),
                f"sweep exposes {name!r}, which reads like a send path",
            )

    def test_no_cli_flag_can_broadcast(self):
        src = inspect.getsource(sweep.main)
        for token in ("publishtx", "publish_transaction", "--send", "--broadcast", "--yes"):
            self.assertNotIn(token, src)

    def test_cli_refuses_a_non_public_key(self):
        rc = sweep.main(["--xpub", "not-a-key", "--balance-sats", "500000"])
        self.assertEqual(rc, 2)

    def test_cli_dry_run_needs_no_node(self):
        # --balance-sats bypasses the node entirely, so this touches no socket.
        rc = sweep.main(
            ["--xpub", BIP84_ZPUB, "--balance-sats", "500000", "--index", "0", "--dry-run"]
        )
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
