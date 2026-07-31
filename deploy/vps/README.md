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

### What a VPS actually is

A Virtual Private Server is a Linux computer you rent by the hour in
someone else's data centre. There is no screen and no desktop — you reach it
only through a terminal over SSH, and it runs whether or not your own machine
is on. That last part is the whole point here: the collectors, the signal
service and the Lightning node need to be up 24/7, and this box has a
non-US IP so Binance's futures API will actually answer it.

It is also **disposable**. Everything on it is rebuilt by `install.sh` from
this repo, so if you wreck it, delete it and make a new one. That is the
normal workflow, not a failure.

### Where to get one

| Provider | Cost | Notes |
|---|---|---|
| **Hetzner Cloud CX22** (recommended) | ~€4.35/mo | 2 vCPU, 4 GB RAM, 40 GB NVMe. German company, EU regions only — which is exactly what we need. Cheapest credible option. |
| DigitalOcean Basic Droplet | ~$6/mo | Slightly pricier, but the friendliest UI and the best beginner docs on the internet. Pick Frankfurt or Amsterdam. |
| Vultr / Linode | ~$5–6/mo | Equivalent; pick a European region. |
| Oracle Cloud Always Free | $0 | Genuinely free ARM instances in non-US regions. Fussier signup, and Oracle may reclaim idle instances. Viable if you'd rather not pay. |

Prices verified 2026-07-31; check the provider before assuming.

### Ordering one (Hetzner)

1. Sign up at **hetzner.com/cloud**. New accounts are sometimes asked for ID
   verification, which can take a few hours — start this before you plan to
   build anything.
2. Create a project, then **Add Server**:
   - **Location:** Falkenstein, Nuremberg, or Helsinki. **Not a US region** —
     a US IP stays geo-blocked and the whole exercise fails.
   - **Image:** Ubuntu 24.04
   - **Type:** CX22 (shared vCPU, x86)
   - **SSH key:** paste your public key (below). Prefer this over a password.
3. Note the server's IP address. That plus your SSH key is everything the
   deploy needs.

### Oracle Cloud Always Free (the $0 path)

Genuinely free and more machine than Hetzner sells for €4 — but it has three
traps that are painful *after* the fact, so read all three before signing up.

**Trap 1 — the home region is permanent.** Oracle asks for a "home region"
during signup and **it can never be changed**; fixing it means a whole new
account. Pick a non-US region that offers Ampere A1: Frankfurt, Amsterdam,
London, or Zurich. A US home region reproduces the exact geo-block this VPS
exists to escape.

**Trap 2 — idle instances get reclaimed.** Oracle deems an instance idle if,
over 7 days, its 95th-percentile CPU, network, *and* memory use are all under
20% (A1 shapes). Our workload is deliberately light, so this box is a
candidate for reclamation. Two consequences:
  - For collectors, the archive, and the signal service: harmless. Everything
    is reproducible from this repo; rebuild and re-collect.
  - For **LND with real funds it is not harmless** — channel state is not
    reproducible from the seed alone. So: run signet here freely (worthless
    coins), and do not put mainnet funds on a reclaimable instance. Either
    upgrade the account to Pay As You Go (removes reclamation; you still pay
    nothing while inside Always Free limits) or wait for a paid box.

**Trap 3 — two firewalls.** Oracle's Ubuntu images carry restrictive iptables
rules *in addition* to the cloud-console Security List. Classic symptom: you
open a port in the console, ufw says it's allowed, and nothing connects.
`install.sh` now detects Oracle and clears the conflicting rules, but you
must **also** add ingress rules in the console:
Networking → your VCN → Security Lists → Default Security List → Add Ingress
Rules for TCP 80, 443, and 9735 from 0.0.0.0/0.

**Ordering it**

1. Sign up at **cloud.oracle.com** → Always Free. A card is required for
   identity verification; Always Free resources are not charged.
2. **Home region:** Frankfurt / Amsterdam / London / Zurich. Permanent.
3. Compute → Create Instance:
   - **Image:** Canonical Ubuntu 24.04
   - **Shape:** `VM.Standard.A1.Flex` (Ampere ARM). Free-tier accounts now get
     2 OCPU / 12 GB; Pay-As-You-Go accounts still get 4 OCPU / 24 GB. Either
     is ample — 2/12 dwarfs the €4 Hetzner box.
   - Paste your SSH public key.
4. If you hit **"Out of host capacity"** — common on A1 — try a different
   availability domain, retry later, or drop to 1 OCPU. It is capacity, not
   your account.
5. Note the public IP. Log in as **`ubuntu`**, not root:
   `ssh ubuntu@YOUR_IP`, then `sudo -i` for the install.

Architecture note: `install.sh` detects x86 vs ARM and fetches the matching
official bitcoind/LND builds, so ARM needs no special handling.

### Making an SSH key (Windows, built in)

```powershell
ssh-keygen -t ed25519 -C "cpt-vps"          # Enter through the prompts
type $env:USERPROFILE\.ssh\id_ed25519.pub   # paste THIS into Hetzner
```

The `.pub` file is public and safe to paste anywhere. The file without
`.pub` is your private key — it never leaves your machine, and losing it
means rebuilding the server.

Then connect with `ssh root@YOUR_IP` and you're in.

### What to know going in

- **It is exposed to the internet from minute one.** `install.sh` configures
  a firewall (ufw) that opens only SSH, HTTP/S, and the Lightning p2p port.
  Run it early.
- **Billing is hourly.** Deleting the server stops the charge; there is no
  contract. Snapshots and backups cost extra and are optional.
- **You are root.** You can break anything — and rebuild it in ten minutes
  from this repo, which is why that's acceptable.
- **The disk is not backed up by default.** Nothing irreplaceable should live
  only here. The archive can be re-collected; the LND seed lives on paper.

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
