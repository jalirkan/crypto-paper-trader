"""Prepare an on-chain sweep from the node to a watch-only xpub. Never signs.

What this does: reads the node's confirmed on-chain balance, and if it exceeds
a threshold, derives a destination address from an extended PUBLIC key and
prints a summary plus the exact `lncli` command to build the PSBT.

What this cannot do, structurally rather than by policy:

  * **Spend.** It holds no private key and no seed; lightning.bip32 has no
    function that accepts one. The destination comes from an xpub, which can
    derive addresses and nothing else.
  * **Sign.** No signing code exists in this module or anything it imports.
  * **Broadcast.** The LND client below is GET-only — it has no POST method at
    all, so there is no publishtransaction call to make and no flag that could
    enable one. This is why it does not reuse LndRestClient (which can POST to
    create invoices): keeping the write verb out of the call graph entirely is
    a stronger guarantee than not calling it.

The macaroon this needs is read-only (`onchain:read`). Do not point it at
admin.macaroon; nothing here requires those rights, and granting them would
trade the guarantee above for convenience.

Signing and broadcasting are steps you perform yourself, in your own SSH
session, after reading the summary. See "Sweeping out" in
deploy/vps/FUNDING.md.

Usage:
    python -m lightning.sweep                      # read config from env
    python -m lightning.sweep --index 3            # explicit address index
    python -m lightning.sweep --xpub zpub... --balance-sats 250000 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .bip32 import ExtendedPubKey, hash160, parse_xpub

DEFAULT_THRESHOLD_SATS = 200_000
DEFAULT_RESERVE_SATS = 15_000
STATE_PATH = Path(os.environ.get("SWEEP_STATE", "/etc/cpt/sweep.state"))


class SweepError(Exception):
    pass


# --- read-only LND client --------------------------------------------------


class ReadOnlyLnd:
    """LND REST client with GET and nothing else. See module docstring."""

    def __init__(
        self,
        base_url: str,
        tls_cert_path: str | None = None,
        macaroon_path: str | None = None,
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._macaroon_hex = (
            Path(macaroon_path).read_bytes().hex() if macaroon_path else ""
        )
        if tls_cert_path and Path(tls_cert_path).exists():
            self._ctx = ssl.create_default_context(cafile=tls_cert_path)
        else:
            self._ctx = ssl.create_default_context()

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            method="GET",
            headers={"Grpc-Metadata-macaroon": self._macaroon_hex},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as res:
                return json.loads(res.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            raise SweepError(f"LND GET {path} → {e.code}: {body}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SweepError(f"LND unreachable at {self.base_url}: {e}") from e

    def confirmed_balance_sats(self) -> int:
        raw = self._get("/v1/balance/blockchain")
        return int(raw.get("confirmed_balance", 0) or 0)

    def fee_rate_sat_vb(self, conf_target: int = 6) -> float | None:
        """Current fee estimate, or None when the node won't answer."""
        try:
            raw = self._get(f"/v2/wallet/estimatefee/{conf_target}")
        except SweepError:
            return None
        sat_per_kw = int(raw.get("sat_per_kw", 0) or 0)
        return round(sat_per_kw / 250, 2) if sat_per_kw else None


# --- planning --------------------------------------------------------------


@dataclass(frozen=True)
class SweepPlan:
    should_sweep: bool
    reason: str
    confirmed_sats: int
    threshold_sats: int
    reserve_sats: int
    amount_sats: int
    address: str
    path: str
    index: int
    xpub_flavour: str
    xpub_fingerprint: str
    fee_rate_sat_vb: float | None


def fingerprint(xpub: ExtendedPubKey) -> str:
    """First 4 bytes of hash160(pubkey) — lets you match this key in a wallet."""
    return hash160(xpub.key)[:4].hex()


def plan_sweep(
    xpub: ExtendedPubKey,
    confirmed_sats: int,
    index: int,
    threshold_sats: int = DEFAULT_THRESHOLD_SATS,
    reserve_sats: int = DEFAULT_RESERVE_SATS,
    branch: int = 0,
    fee_rate_sat_vb: float | None = None,
) -> SweepPlan:
    """Pure decision function — no I/O, so the rules are testable offline."""
    path = f"{branch}/{index}"
    address = xpub.address(path)
    amount = confirmed_sats - reserve_sats

    if confirmed_sats < threshold_sats:
        should, reason = False, (
            f"confirmed balance {confirmed_sats:,} sats is below the "
            f"{threshold_sats:,} sat threshold"
        )
    elif amount <= 0:
        should, reason = False, (
            f"nothing to sweep after holding back the {reserve_sats:,} sat reserve"
        )
    else:
        should, reason = True, (
            f"confirmed balance {confirmed_sats:,} sats exceeds the "
            f"{threshold_sats:,} sat threshold"
        )

    return SweepPlan(
        should_sweep=should,
        reason=reason,
        confirmed_sats=confirmed_sats,
        threshold_sats=threshold_sats,
        reserve_sats=reserve_sats,
        amount_sats=max(0, amount),
        address=address,
        path=path,
        index=index,
        xpub_flavour=xpub.flavour,
        xpub_fingerprint=fingerprint(xpub),
        fee_rate_sat_vb=fee_rate_sat_vb,
    )


def render_plan(plan: SweepPlan, network_flag: str = "") -> str:
    """The human-readable summary. Everything you need to check before signing."""
    net = f" {network_flag}" if network_flag else ""
    fee = (
        f"{plan.fee_rate_sat_vb} sat/vB (estimate for 6 blocks)"
        if plan.fee_rate_sat_vb is not None
        else "unavailable - check mempool.space before you sign"
    )

    lines = [
        "",
        "  SWEEP PLAN - nothing has been signed or sent",
        "  " + "-" * 66,
        f"  confirmed on-chain     {plan.confirmed_sats:>14,} sats",
        f"  threshold              {plan.threshold_sats:>14,} sats",
        f"  reserve (kept on node) {plan.reserve_sats:>14,} sats",
        f"  amount to sweep        {plan.amount_sats:>14,} sats",
        "",
        f"  destination            {plan.address}",
        f"  derivation             {plan.xpub_flavour} [{plan.xpub_fingerprint}] / {plan.path}",
        f"  fee rate               {fee}",
        "  " + "-" * 66,
        f"  decision: {'SWEEP' if plan.should_sweep else 'NO SWEEP'} - {plan.reason}",
        "",
    ]

    if not plan.should_sweep:
        return "\n".join(lines)

    lines += [
        "  Before you sign, verify in your OWN wallet that the address above",
        f"  appears at index {plan.index} of key [{plan.xpub_fingerprint}]. Read it from this",
        "  terminal, not from a web page or a chat window.",
        "",
        "  Then run these yourself. This script does not run them, and has no",
        "  flag that would:",
        "",
        f"    lncli{net} wallet psbt fund \\",
        f"      --outputs='{{\"{plan.address}\":{plan.amount_sats}}}' \\",
        "      --sat_per_vbyte=<rate you chose>",
        "",
        f"    lncli{net} wallet psbt finalize <psbt-from-previous-step>",
        f"    lncli{net} wallet publishtx <final-tx-hex>",
        "",
    ]
    return "\n".join(lines)


# --- state (advisory only) -------------------------------------------------


def read_last_index(path: Path = STATE_PATH) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_last_index(index: int, path: Path = STATE_PATH) -> bool:
    """Record the index just prepared. Advisory: a skipped index is harmless."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(index), encoding="utf-8")
        return True
    except OSError:
        return False


# --- cli -------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Prepare (never send) an on-chain sweep to a watch-only xpub."
    )
    ap.add_argument("--xpub", default=os.environ.get("SWEEP_XPUB"))
    ap.add_argument("--index", type=int, default=None, help="address index (default: last+1)")
    ap.add_argument("--branch", type=int, default=0, help="0 receive, 1 change")
    ap.add_argument(
        "--threshold-sats",
        type=int,
        default=int(os.environ.get("SWEEP_THRESHOLD_SATS", DEFAULT_THRESHOLD_SATS)),
    )
    ap.add_argument(
        "--reserve-sats",
        type=int,
        default=int(os.environ.get("SWEEP_RESERVE_SATS", DEFAULT_RESERVE_SATS)),
    )
    ap.add_argument("--lnd-url", default=os.environ.get("LND_REST_URL", "https://127.0.0.1:8080"))
    ap.add_argument("--macaroon", default=os.environ.get("SWEEP_MACAROON"))
    ap.add_argument("--tls-cert", default=os.environ.get("LND_TLS_CERT"))
    ap.add_argument("--network-flag", default=os.environ.get("SWEEP_NETWORK_FLAG", ""))
    ap.add_argument(
        "--balance-sats",
        type=int,
        default=None,
        help="skip the node and plan against this balance (offline dry run)",
    )
    ap.add_argument("--dry-run", action="store_true", help="do not record the index")
    args = ap.parse_args(argv)

    if not args.xpub:
        print("No xpub. Set SWEEP_XPUB or pass --xpub. It must be an extended")
        print("PUBLIC key (xpub/ypub/zpub) - never a seed phrase or an xprv.")
        return 2

    try:
        xpub = parse_xpub(args.xpub)
    except ValueError as e:
        print(f"Could not read the extended key: {e}")
        return 2

    index = args.index
    if index is None:
        last = read_last_index()
        index = 0 if last is None else last + 1

    fee_rate = None
    if args.balance_sats is not None:
        confirmed = args.balance_sats
    else:
        try:
            lnd = ReadOnlyLnd(args.lnd_url, args.tls_cert, args.macaroon)
            confirmed = lnd.confirmed_balance_sats()
            fee_rate = lnd.fee_rate_sat_vb()
        except SweepError as e:
            print(f"Could not read the node's balance: {e}")
            return 1

    plan = plan_sweep(
        xpub,
        confirmed_sats=confirmed,
        index=index,
        threshold_sats=args.threshold_sats,
        reserve_sats=args.reserve_sats,
        branch=args.branch,
        fee_rate_sat_vb=fee_rate,
    )
    print(render_plan(plan, args.network_flag))

    if plan.should_sweep and not args.dry_run and args.index is None:
        if not write_last_index(index):
            print(f"  (could not record index {index} to {STATE_PATH}; pass --index next time)\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
