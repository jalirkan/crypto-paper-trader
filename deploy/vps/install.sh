#!/usr/bin/env bash
# VPS bootstrap: bitcoind (signet, pruned) + LND + tip-jar service + collectors.
#
# REVIEW THIS SCRIPT BEFORE RUNNING. Run as root on a fresh Ubuntu 24.04 VPS:
#   git clone https://github.com/jalirkan/crypto-paper-trader.git /opt/crypto-paper-trader
#   cd /opt/crypto-paper-trader/deploy/vps && bash install.sh
#
# What it does NOT do, by design: create the LND wallet (your seed, your eyes),
# bake macaroons, or open channels. Those are manual steps in README.md.

set -euo pipefail

BITCOIN_VERSION="${BITCOIN_VERSION:-28.1}"     # check bitcoincore.org for latest
LND_VERSION="${LND_VERSION:-v0.18.5-beta}"     # check github.com/lightningnetwork/lnd/releases
ARCH="x86_64-linux-gnu"
LND_ARCH="linux-amd64"
REPO_DIR="/opt/crypto-paper-trader"

echo "== users and directories =="
id -u bitcoin &>/dev/null || useradd -r -m -s /usr/sbin/nologin bitcoin
id -u lnd     &>/dev/null || useradd -r -m -s /usr/sbin/nologin lnd
id -u cpt     &>/dev/null || useradd -r -m -s /usr/sbin/nologin cpt
mkdir -p /etc/cpt "$REPO_DIR/data"
chown -R cpt:cpt "$REPO_DIR/data"

echo "== base packages =="
apt-get update -qq
apt-get install -y -qq python3 git curl ufw debian-keyring debian-archive-keyring apt-transport-https

echo "== firewall (SSH, HTTP/S for Caddy, 9735 for LND p2p) =="
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 9735/tcp
ufw --force enable

echo "== bitcoin core ${BITCOIN_VERSION} (signet, pruned) =="
cd /tmp
curl -fsSLO "https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VERSION}/bitcoin-${BITCOIN_VERSION}-${ARCH}.tar.gz"
curl -fsSLO "https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VERSION}/SHA256SUMS"
grep " bitcoin-${BITCOIN_VERSION}-${ARCH}.tar.gz\$" SHA256SUMS | sha256sum --check -
# (Optional extra rigor: verify SHA256SUMS.asc signatures with gpg — see README.)
tar -xzf "bitcoin-${BITCOIN_VERSION}-${ARCH}.tar.gz"
install -m 0755 "bitcoin-${BITCOIN_VERSION}/bin/bitcoind" "bitcoin-${BITCOIN_VERSION}/bin/bitcoin-cli" /usr/local/bin/

echo "== lnd ${LND_VERSION} =="
curl -fsSLO "https://github.com/lightningnetwork/lnd/releases/download/${LND_VERSION}/lnd-${LND_ARCH}-${LND_VERSION}.tar.gz"
curl -fsSLO "https://github.com/lightningnetwork/lnd/releases/download/${LND_VERSION}/manifest-${LND_VERSION}.txt"
grep " lnd-${LND_ARCH}-${LND_VERSION}.tar.gz\$" "manifest-${LND_VERSION}.txt" | sha256sum --check -
tar -xzf "lnd-${LND_ARCH}-${LND_VERSION}.tar.gz"
install -m 0755 "lnd-${LND_ARCH}-${LND_VERSION}/lnd" "lnd-${LND_ARCH}-${LND_VERSION}/lncli" /usr/local/bin/

echo "== configs (bitcoind rpc password generated once) =="
RPC_PASS_FILE=/etc/cpt/.rpcpass
if [[ ! -f "$RPC_PASS_FILE" ]]; then
  head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40 > "$RPC_PASS_FILE"
  chmod 600 "$RPC_PASS_FILE"
fi
RPC_PASS="$(cat "$RPC_PASS_FILE")"

install -d -o bitcoin -g bitcoin /home/bitcoin/.bitcoin
sed "s/__RPC_PASS__/${RPC_PASS}/" "$REPO_DIR/deploy/vps/bitcoin.conf" > /home/bitcoin/.bitcoin/bitcoin.conf
chown bitcoin:bitcoin /home/bitcoin/.bitcoin/bitcoin.conf && chmod 600 /home/bitcoin/.bitcoin/bitcoin.conf

install -d -o lnd -g lnd /home/lnd/.lnd
sed "s/__RPC_PASS__/${RPC_PASS}/" "$REPO_DIR/deploy/vps/lnd.conf" > /home/lnd/.lnd/lnd.conf
chown lnd:lnd /home/lnd/.lnd/lnd.conf && chmod 600 /home/lnd/.lnd/lnd.conf

[[ -f /etc/cpt/tipjar.env ]] || cp "$REPO_DIR/deploy/vps/tipjar.env.example" /etc/cpt/tipjar.env

echo "== caddy (reverse proxy + auto-TLS) =="
if ! command -v caddy &>/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy
fi
cp "$REPO_DIR/deploy/vps/Caddyfile" /etc/caddy/Caddyfile

echo "== systemd units =="
cp "$REPO_DIR"/deploy/vps/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable bitcoind lnd cpt-collectors
systemctl start bitcoind
systemctl start cpt-collectors

echo
echo "DONE. Next (manual, from README.md):"
echo "  1. wait for signet sync:  sudo -u bitcoin bitcoin-cli -signet getblockchaininfo"
echo "  2. start lnd:             systemctl start lnd"
echo "  3. create wallet:         sudo -u lnd lncli --network=signet create   (WRITE THE SEED ON PAPER)"
echo "  4. bake invoice macaroon + fill /etc/cpt/tipjar.env, then: systemctl enable --now cpt-tipjar"
echo "  5. point your domain at this box and set it in /etc/caddy/Caddyfile, then: systemctl reload caddy"
