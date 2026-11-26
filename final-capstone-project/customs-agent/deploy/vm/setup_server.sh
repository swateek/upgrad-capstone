#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 server for DeclareRight (SETUP.md step 16).
#   scp deploy/vm/setup_server.sh root@<ip>:   then on the server:   bash setup_server.sh
# Safe to run twice. Prints a connectivity check of the course endpoints at the end.
set -euo pipefail

echo "== 2 GB swap (building the image needs more than 4 GB at peak)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== firewall: SSH, HTTP, HTTPS only"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ufw status | sed 's/^/   /'

echo "== security updates installed automatically"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades rsync netcat-openbsd >/dev/null

echo "== Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
docker --version

echo "== uv (to fetch the Python packages for the image)"
if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
fi
"$HOME/.local/bin/uv" --version 2>/dev/null || uv --version

echo "== can this server reach the course endpoints?"
for port in 1033 1035; do
  if nc -z -w 8 103.42.50.41 "$port"; then echo "   103.42.50.41:$port reachable"; else echo "   103.42.50.41:$port NOT reachable"; fi
done
echo "done"
