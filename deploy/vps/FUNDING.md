# Funding the Node: Venmo → LND (mainnet)

Do this **after** the signet end-to-end test passes and you've flipped to
mainnet (step 7 of README.md, or the neutrino fast path below). Venmo sends
BTC **on-chain only** (no Lightning), which is exactly what LND's built-in
on-chain wallet expects — nothing custom to build, just careful steps.

Keep amounts small. This node is a public demo, not a treasury.

## 0. Mainnet flip, fast path (neutrino — no multi-day bitcoind sync)

The $5 VPS would take days to sync a pruned mainnet bitcoind. Neutrino syncs
in minutes to hours:

```bash
systemctl stop lnd
cp /opt/crypto-paper-trader/deploy/vps/lnd.mainnet.conf /home/lnd/.lnd/lnd.conf
chown lnd:lnd /home/lnd/.lnd/lnd.conf && chmod 600 /home/lnd/.lnd/lnd.conf
systemctl disable --now bitcoind        # not needed under neutrino
systemctl start lnd
sudo -u lnd lncli create                # NEW mainnet wallet → NEW seed ON PAPER
# wait for: sudo -u lnd lncli getinfo → "synced_to_chain": true
```

Then re-bake the invoice macaroon from the **mainnet** path (README step 4,
`--network` flag no longer needed) and set `LN_NETWORK=mainnet` in
`/etc/cpt/tipjar.env`, restart `cpt-tipjar`.

## 1. Generate the deposit address — on the node, over SSH

```bash
sudo -u lnd lncli newaddress p2wkh
```

Use the `bc1q…` address it prints. **Copy it from your SSH terminal directly**
— never from a web page or chat, so a compromised anything can't swap it.
(p2wkh is the safe choice; some senders still reject taproot `bc1p…`.)

## 2. Send from Venmo — test amount first

In Venmo: Crypto → Bitcoin → transfer/send → external wallet → paste address.
(Exact menus move around; if "send to external wallet" is missing, Venmo may
require extra identity verification first.)

1. **First send: ~$10.** Venmo shows its network fee before you confirm.
2. Watch it arrive (1–3 confirmations, ~10–30 min):

   ```bash
   sudo -u lnd lncli walletbalance     # unconfirmed → confirmed
   ```

3. Address verified end-to-end → send the rest. Suggested total: **$30–75**
   (50k–100k sats). Note: moving BTC out of Venmo isn't a sale for tax
   purposes; buying/selling inside Venmo is its own story. Not tax advice.

## 3. Open a channel (makes the node real)

```bash
sudo -u lnd lncli connect <pubkey>@<host>:9735
sudo -u lnd lncli openchannel --node_key=<pubkey> --local_amt=80000 --sat_per_vbyte=<check mempool>
```

Pick a large, well-connected peer (browse amboss.space — ACINQ, Kraken,
Voltage hubs, etc.). Leave ~10–15k sats on-chain for future fees. After ~3
confirmations the channel is active: you now have **outbound** liquidity.

## 4. Inbound liquidity (so strangers can actually tip you)

A fresh channel is all outbound. Three ways to get the receiving side:

1. **Spend out**: pay for something over Lightning; whatever leaves becomes
   inbound capacity. Simplest.
2. **Swap out**: Boltz (boltz.exchange) — pay yourself over Lightning, receive
   on-chain back to your own LND wallet (~0.5% + network fees). Turns outbound
   into inbound without buying anything.
3. Later, if the jar earns attention: someone opens a channel toward you.

Sanity check: `sudo -u lnd lncli channelbalance` → `remote_balance` is what
the world can pay you. Then pay yourself a real tip through
`tips@YOURDOMAIN` from any Lightning wallet and watch `/api/tips`.

## 5. Sweeping out — moving accumulated sats off the node

A VPS is a hot wallet on a machine you rent. Whatever sits on it is exposed to
the host, to your SSH hygiene, and to your own mistakes. Tips accumulate slowly,
so the balance creeps up quietly and there is never an obvious moment to act —
which is what `lightning/sweep.py` is for: it watches the balance and tells you
when it's time, with the transaction details already worked out.

**Sweep when** the confirmed on-chain balance crosses your threshold (default
200,000 sats), or before any maintenance that touches the node, or any time
you're unsure whether the box is still trustworthy. There is no penalty for
sweeping early beyond the miner fee.

### One-time setup

Export the **account xpub** from your personal wallet — the watch-only public
key, *not* the seed phrase and *not* an xprv. In most wallets this is under
"Account details", "Export public key", or similar; BIP84 wallets show a
`zpub`. The tool accepts `xpub`, `ypub`, `zpub`, `tpub` and `vpub`, and rejects
anything else at parse time.

```bash
# On the VPS. This file holds a PUBLIC key — it cannot spend anything.
cat > /etc/cpt/sweep.env << 'EOF'
SWEEP_XPUB=zpub6r...your-account-xpub
SWEEP_THRESHOLD_SATS=200000
SWEEP_RESERVE_SATS=15000
LND_REST_URL=https://127.0.0.1:8080
LND_TLS_CERT=/etc/cpt/lnd-tls.cert
SWEEP_MACAROON=/etc/cpt/sweep.macaroon
EOF
chmod 600 /etc/cpt/sweep.env

# A READ-ONLY macaroon. Not admin.macaroon — the script needs nothing more.
sudo -u lnd lncli bakemacaroon onchain:read --save_to /tmp/sweep.macaroon
install -o cpt -g cpt -m 600 /tmp/sweep.macaroon /etc/cpt/sweep.macaroon && rm /tmp/sweep.macaroon
```

### Checking whether it's time

```bash
set -a && . /etc/cpt/sweep.env && set +a
python3 -m lightning.sweep
```

It prints a plan and stops:

```
  SWEEP PLAN - nothing has been signed or sent
  ------------------------------------------------------------------
  confirmed on-chain            480,000 sats
  threshold                     200,000 sats
  reserve (kept on node)         15,000 sats
  amount to sweep               465,000 sats

  destination            bc1qp59yckz4ae5c4efgw2s5wfyvrz0ala7rgvuz8z
  derivation             zpub [fd13aac9] / 0/2
  fee rate               12.5 sat/vB (estimate for 6 blocks)
  ------------------------------------------------------------------
  decision: SWEEP - confirmed balance 480,000 sats exceeds the 200,000 sat threshold
```

**Verify the destination before going further.** Open your own wallet and
confirm that address appears at index 2 of key `fd13aac9`. Read it from your
SSH terminal — never copy an address out of a web page, a chat window, or this
file. The fingerprint is there so you can tell at a glance that the tool is
deriving from the key you think it is.

### Signing — your step, always

The script never signs and never broadcasts. It has no `--send` flag, no
`--broadcast` flag, and no `--yes`; the LND client inside it implements `GET`
and nothing else, so there is no write call available to it even in principle.
Three tests assert exactly that, and they'd fail if someone added one.

You run these, in your own session:

```bash
# 1. Build the unsigned PSBT (lncli picks the inputs and change)
sudo -u lnd lncli wallet psbt fund \
  --outputs='{"bc1q...destination-from-the-plan":465000}' \
  --sat_per_vbyte=<rate you chose, see mempool.space>

# 2. Sign it with the node's wallet and get the raw transaction
sudo -u lnd lncli wallet psbt finalize <psbt-from-step-1>

# 3. Read the decoded output ONE more time, then broadcast
sudo -u lnd lncli wallet publishtx <final-tx-hex>
```

Between steps 2 and 3 is the last point at which a mistake is free. Check the
destination and the amount there.

### Rotating the address

Each sweep should use a fresh index — reusing one links your payments together
on a public ledger. The tool remembers the last index it prepared in
`/etc/cpt/sweep.state` and defaults to the next one; pass `--index N` to
override. A skipped index is harmless (wallets scan a gap of ~20 ahead).

### Testing it without a node

```bash
python3 -m lightning.sweep --xpub <your-xpub> --balance-sats 480000 --dry-run
```

`--balance-sats` bypasses the node entirely, so you can check that the derived
addresses match your wallet before any real sats exist.

## Rules that don't change

- Seed on paper only. Admin macaroon never leaves the VPS. I (Claude) never
  see keys, seeds, or macaroons — addresses only.
- Every command that moves value runs in **your** SSH session, typed by you.
