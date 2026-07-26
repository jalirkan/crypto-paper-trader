# VPS Setup — Lightning Tip Jar + 24/7 Collectors

Your side of the deployment. Everything here touches keys or money, which is
why it's manual. Budget ~30–45 min active time (signet sync runs unattended).

**Key rules, non-negotiable:**

- The 24-word seed shown at wallet creation goes on paper. Never into a file,
  a chat (including with Claude), a password manager screenshot, or an email.
- `admin.macaroon` never leaves the VPS. The tip-jar service runs on a baked
  **invoice-only** macaroon — it can create/read invoices, nothing else.
- On signet, coins are worthless — mistakes are free. That's the point.

## 1. Get the VPS (~$5/mo)

Hetzner (or any provider): Ubuntu 24.04, 2+ GB RAM, 40 GB disk, x86.
Add your SSH key. Note the IP.

## 2. Bootstrap

```bash
ssh root@YOUR_IP
git clone https://github.com/jalirkan/crypto-paper-trader.git /opt/crypto-paper-trader
cd /opt/crypto-paper-trader/deploy/vps
less install.sh        # READ IT — never run scripts blind, even mine
bash install.sh
```

This installs bitcoind (signet, pruned, checksum-verified), LND
(checksum-verified), Caddy, firewall rules, and starts **bitcoind** and the
**collectors** (your archive is now 24/7 — and the funding-rate backfill works
from here: `sudo -u cpt python3 -m collectors.backfill --funding`).

Signet sync takes roughly 30–90 min. Check:

```bash
sudo -u bitcoin bitcoin-cli -signet getblockchaininfo   # "blocks" ≈ "headers" = done
```

## 3. Create the LND wallet (the seed moment)

```bash
systemctl start lnd
sudo -u lnd lncli --network=signet create
```

Pick a wallet password, say **n** to existing seed, write the 24 words on
paper. Then confirm LND is happy:

```bash
sudo -u lnd lncli --network=signet getinfo    # synced_to_chain: true
```

## 4. Bake the invoice-only macaroon and start the tip jar

```bash
sudo -u lnd lncli --network=signet bakemacaroon invoices:read invoices:write \
  --save_to /tmp/invoice.macaroon
install -o cpt -g cpt -m 600 /tmp/invoice.macaroon /etc/cpt/invoice.macaroon && rm /tmp/invoice.macaroon
# lnd's TLS cert must be readable by the service:
install -o cpt -g cpt -m 644 /home/lnd/.lnd/tls.cert /etc/cpt/lnd-tls.cert

nano /etc/cpt/tipjar.env   # set LN_DOMAIN, TIP_PUBLIC_BASE, LND_TLS_CERT=/etc/cpt/lnd-tls.cert
systemctl enable --now cpt-tipjar
curl -s http://127.0.0.1:8090/healthz          # {"ok": true, ...}
curl -s http://127.0.0.1:8090/.well-known/lnurlp/tips
```

## 5. Domain + HTTPS (for the Lightning Address)

Point an A record (e.g. `tips.yourdomain.com` or the apex) at the VPS IP,
put that domain in `/etc/caddy/Caddyfile` (replace `example.com`), then:

```bash
systemctl reload caddy
curl -s https://YOURDOMAIN/.well-known/lnurlp/tips
```

Your Lightning Address is now `tips@YOURDOMAIN`. (No domain yet? Everything
still works via direct invoice creation; the pretty address just waits.)

## 6. Fund and test on signet

1. Get free signet coins: `sudo -u lnd lncli --network=signet newaddress p2wkh`
   then use a signet faucet (search "bitcoin signet faucet" — e.g. signetfaucet.com).
2. Open a small channel to any reachable signet Lightning node
   (`lncli --network=signet openchannel <pubkey> --local_amt 100000`) — or run a
   second throwaway signet wallet on your PC and channel between the two.
3. Pay yourself through the whole stack: wallet → `tips@YOURDOMAIN` → watch it
   appear in `curl https://YOURDOMAIN/api/tips`.

To receive from *others* the channel needs inbound liquidity — spend some sats
out first, or have the peer open the channel toward you.

## 7. Mainnet flip (later, only after signet works end-to-end)

Follow the commented blocks in `bitcoin.conf` and `lnd.conf`, create the new
mainnet wallet (new paper seed), re-bake the macaroon from the mainnet path,
flip `LN_NETWORK=mainnet` in tipjar.env. Keep amounts tiny; this jar is a demo.

## Troubleshooting

```bash
journalctl -u bitcoind -n 50    # or: lnd / cpt-tipjar / cpt-collectors
systemctl status cpt-tipjar
```
