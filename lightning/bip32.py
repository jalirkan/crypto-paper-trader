"""Watch-only BIP32 public derivation and P2WPKH address encoding (stdlib).

This module handles **public keys only**. There is deliberately no function
here that accepts a seed, a mnemonic, a private key, or an xprv, and no code
path that can produce a signature. An extended *public* key can derive receive
addresses and nothing else — that is the whole security argument for pointing
a sweep script at an xpub instead of a wallet.

Non-hardened derivation only, which is the other half of that argument:
hardened derivation is mathematically impossible from a public key, so an
index ≥ 2^31 is rejected rather than silently mishandled.

Implements: base58check decode, secp256k1 point arithmetic, CKDpub (BIP32),
hash160, and bech32 encoding (BIP173). Dependency-free, matching the rest of
the Python in this repo.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

# --- secp256k1 -------------------------------------------------------------

P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)

Point = tuple[int, int] | None  # None is the point at infinity


def _inv(a: int, m: int = P) -> int:
    return pow(a, m - 2, m)


def point_add(p1: Point, p2: Point) -> Point:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1) * _inv(2 * y1) % P
    else:
        lam = (y2 - y1) * _inv(x2 - x1) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def point_mul(k: int, p: Point = G) -> Point:
    r: Point = None
    addend = p
    while k:
        if k & 1:
            r = point_add(r, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return r


def ser_p(p: Point) -> bytes:
    """Compressed SEC encoding."""
    if p is None:
        raise ValueError("cannot serialize the point at infinity")
    x, y = p
    return bytes([2 + (y & 1)]) + x.to_bytes(32, "big")


def parse_p(data: bytes) -> Point:
    """Decompress a 33-byte SEC public key."""
    if len(data) != 33 or data[0] not in (2, 3):
        raise ValueError("not a compressed secp256k1 public key")
    x = int.from_bytes(data[1:], "big")
    if x >= P:
        raise ValueError("public key x coordinate out of range")
    y = pow((x * x * x + 7) % P, (P + 1) // 4, P)
    if (y * y - x * x * x - 7) % P != 0:
        raise ValueError("public key is not on the curve")
    if y & 1 != data[0] & 1:
        y = P - y
    return (x, y)


# --- hashes ----------------------------------------------------------------


def _ripemd160(data: bytes) -> bytes:
    """RIPEMD-160, preferring hashlib but falling back to pure Python.

    OpenSSL 3 ships with the legacy provider disabled on most current distros
    (Ubuntu 24.04 included), so hashlib.new("ripemd160") raises there. Bitcoin
    addresses need it either way, so the fallback is not optional.
    """
    try:
        return hashlib.new("ripemd160", data).digest()
    except (ValueError, TypeError):
        return _ripemd160_py(data)


_RL = [
    *range(16),
    7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
    3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12,
    1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
    4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13,
]
_RR = [
    5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12,
    6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
    15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13,
    8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
    12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11,
]
_SL = [
    11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8,
    7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
    11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5,
    11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12,
    9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6,
]
_SR = [
    8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6,
    9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
    9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5,
    15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8,
    8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11,
]
_KL = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
_KR = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]
_M32 = 0xFFFFFFFF


def _rol(x: int, n: int) -> int:
    x &= _M32
    return ((x << n) | (x >> (32 - n))) & _M32


def _f(j: int, x: int, y: int, z: int) -> int:
    if j < 16:
        return x ^ y ^ z
    if j < 32:
        return (x & y) | (~x & z)
    if j < 48:
        return (x | ~y) ^ z
    if j < 64:
        return (x & z) | (y & ~z)
    return x ^ (y | ~z)


def _ripemd160_py(data: bytes) -> bytes:
    ml = len(data)
    data += b"\x80"
    data += b"\x00" * ((56 - len(data) % 64) % 64)
    data += (ml * 8 & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")

    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    for off in range(0, len(data), 64):
        x = [int.from_bytes(data[off + 4 * i : off + 4 * i + 4], "little") for i in range(16)]
        al, bl, cl, dl, el = h
        ar, br, cr, dr, er = h
        for j in range(80):
            rnd = j // 16
            t = _rol((al + _f(j, bl, cl, dl) + x[_RL[j]] + _KL[rnd]) & _M32, _SL[j])
            t = (t + el) & _M32
            al, bl, cl, dl, el = el, t, bl, _rol(cl, 10), dl
            t = _rol((ar + _f(79 - j, br, cr, dr) + x[_RR[j]] + _KR[rnd]) & _M32, _SR[j])
            t = (t + er) & _M32
            ar, br, cr, dr, er = er, t, br, _rol(cr, 10), dr
        h = [
            (h[1] + cl + dr) & _M32,
            (h[2] + dl + er) & _M32,
            (h[3] + el + ar) & _M32,
            (h[4] + al + br) & _M32,
            (h[0] + bl + cr) & _M32,
        ]
    return b"".join(v.to_bytes(4, "little") for v in h)


def hash160(data: bytes) -> bytes:
    return _ripemd160(hashlib.sha256(data).digest())


# --- base58check -----------------------------------------------------------

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58check_decode(s: str) -> bytes:
    num = 0
    for ch in s:
        idx = _B58.find(ch)
        if idx < 0:
            raise ValueError(f"invalid base58 character {ch!r}")
        num = num * 58 + idx
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    pad = len(s) - len(s.lstrip("1"))
    raw = b"\x00" * pad + raw
    if len(raw) < 5:
        raise ValueError("base58 string too short")
    body, checksum = raw[:-4], raw[-4:]
    if hashlib.sha256(hashlib.sha256(body).digest()).digest()[:4] != checksum:
        raise ValueError("bad base58 checksum — the key was mistyped or truncated")
    return body


# --- bech32 (BIP173) -------------------------------------------------------

_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values: list[int]) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            chk ^= gen[i] if (top >> i) & 1 else 0
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convertbits(data: bytes, frm: int, to: int) -> list[int]:
    acc, bits, out = 0, 0, []
    maxv = (1 << to) - 1
    for b in data:
        acc = (acc << frm) | b
        bits += frm
        while bits >= to:
            bits -= to
            out.append((acc >> bits) & maxv)
    if bits:
        out.append((acc << (to - bits)) & maxv)
    return out


def bech32_p2wpkh(pubkey: bytes, hrp: str = "bc") -> str:
    """Native segwit v0 address for a compressed public key."""
    data = [0] + _convertbits(hash160(pubkey), 8, 5)
    chk = _polymod(_hrp_expand(hrp) + data + [0] * 6) ^ 1
    checksum = [(chk >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_BECH32[d] for d in data + checksum)


# --- extended public keys --------------------------------------------------

# Version bytes for extended PUBLIC keys only. xprv/yprv/zprv are absent by
# design: a private key must not be loadable by this module at all.
XPUB_VERSIONS = {
    0x0488B21E: ("xpub", "bc"),
    0x049D7CB2: ("ypub", "bc"),  # BIP49 wrapped segwit
    0x04B24746: ("zpub", "bc"),  # BIP84 native segwit
    0x043587CF: ("tpub", "tb"),
    0x045F1CF6: ("vpub", "tb"),
}


@dataclass(frozen=True)
class ExtendedPubKey:
    key: bytes  # 33-byte compressed point
    chain_code: bytes
    depth: int
    flavour: str
    hrp: str

    @property
    def point(self) -> Point:
        return parse_p(self.key)

    def child(self, index: int) -> "ExtendedPubKey":
        """CKDpub. Hardened indices are impossible from a public key."""
        if not 0 <= index < 2**31:
            raise ValueError(
                f"index {index} is hardened or out of range; hardened derivation "
                "requires a private key, which this module cannot hold"
            )
        data = self.key + index.to_bytes(4, "big")
        digest = hmac.new(self.chain_code, data, hashlib.sha512).digest()
        il = int.from_bytes(digest[:32], "big")
        if il >= N:
            raise ValueError("derived key invalid (IL >= n) — use the next index")
        child_point = point_add(point_mul(il), self.point)
        if child_point is None:
            raise ValueError("derived key is the point at infinity — use the next index")
        return ExtendedPubKey(
            key=ser_p(child_point),
            chain_code=digest[32:],
            depth=self.depth + 1,
            flavour=self.flavour,
            hrp=self.hrp,
        )

    def derive_path(self, path: str) -> "ExtendedPubKey":
        """Relative non-hardened path, e.g. "0/7"."""
        node = self
        for part in path.strip().strip("/").split("/"):
            if not part or part in ("m", "M"):
                continue
            if part.endswith(("'", "h", "H")):
                raise ValueError(
                    f"path element {part!r} is hardened; derive the account xpub "
                    "in your own wallet and give this tool that instead"
                )
            node = node.child(int(part))
        return node

    def address(self, path: str) -> str:
        return bech32_p2wpkh(self.derive_path(path).key, self.hrp)


def parse_xpub(text: str) -> ExtendedPubKey:
    raw = b58check_decode(text.strip())
    if len(raw) != 78:
        raise ValueError(f"extended key payload is {len(raw)} bytes, expected 78")
    version = int.from_bytes(raw[:4], "big")
    if version not in XPUB_VERSIONS:
        raise ValueError(
            "not a recognised extended PUBLIC key. This tool accepts xpub/ypub/"
            "zpub/tpub/vpub only — never an xprv or a seed phrase."
        )
    flavour, hrp = XPUB_VERSIONS[version]
    key = raw[45:78]
    if key[0] not in (2, 3):
        raise ValueError("extended key does not contain a compressed public key")
    return ExtendedPubKey(
        key=key,
        chain_code=raw[13:45],
        depth=raw[4],
        flavour=flavour,
        hrp=hrp,
    )
