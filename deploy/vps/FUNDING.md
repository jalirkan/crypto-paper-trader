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

## Rules that don't change

- Seed on paper only. Admin macaroon never leaves the VPS. I (Claude) never
  see keys, seeds, or macaroons — addresses only.
- Every command that moves value runs in **your** SSH session, typed by you.
