#!/usr/bin/env bash
# Copy DeclareRight to the server and (re)start it. Run from your Mac, in customs-agent/:
#
#   ACCESS_CODE='<code to share with reviewers>' bash deploy/vm/push.sh root@<server IP>
#
# Copies the code, the built corpus and index, .env and certs/ (over SSH, never through git),
# writes deploy/vm/.env on the server (SITE = <ip-with-dashes>.sslip.io, ACCESS_CODE), fetches the
# Linux packages on the server when uv.lock changed, then builds and starts app + Caddy.
# Re-run it after any change; the first build takes about 10 minutes.
set -euo pipefail
HOST=${1:?usage: ACCESS_CODE=... bash deploy/vm/push.sh root@<server IP>}
: "${ACCESS_CODE:?set ACCESS_CODE, e.g. ACCESS_CODE='tulip-42' bash deploy/vm/push.sh $HOST}"
IP=${HOST#*@}
SITE="${IP//./-}.sslip.io"
DIR=/opt/declareright
cd "$(dirname "$0")/../.."

for f in .env certs data/rag-corpus/corpus/chunks.jsonl data/rag-corpus/index; do
  [ -e "$f" ] || { echo "missing $f (see SETUP.md steps 3, 5 and 9)"; exit 1; }
done

echo "== copying to $HOST:$DIR"
ssh "$HOST" "mkdir -p $DIR"
rsync -az --delete \
  --exclude .venv --exclude .git --exclude '__pycache__' --exclude '.DS_Store' \
  --exclude web/node_modules --exclude web/dist --exclude logs --exclude docker/wheels \
  --exclude results --exclude eval --exclude docs --exclude tests --exclude prechecks \
  --exclude data/rag-corpus/corpus/raw --exclude data/rag-corpus/corpus/docs \
  --exclude deploy/vm/.env \
  ./ "$HOST:$DIR/"

echo "== settings and permissions on the server"
ssh "$HOST" "set -e; cd $DIR
  umask 077; printf 'SITE=%s\nACCESS_CODE=%s\n' '$SITE' '$ACCESS_CODE' > deploy/vm/.env
  mkdir -p logs; chown -R 1000:1000 logs .env; chmod 600 .env; chmod 644 certs/*.crt"

echo "== Linux packages for the image (only when uv.lock changed)"
ssh "$HOST" "set -e; cd $DIR; export PATH=\$HOME/.local/bin:\$PATH
  if [ ! -f docker/wheels/requirements.txt ] || [ uv.lock -nt docker/wheels/requirements.txt ]; then
    uv run --no-project --with packaging python docker/fetch_wheels.py --arch x86_64
  fi"

echo "== build and start (first time ~10 minutes)"
ssh "$HOST" "cd $DIR/deploy/vm && docker compose up -d --build && docker compose ps"

echo
echo "Open https://$SITE (the certificate can take a minute on first start)."
echo "Access code: the one you set. Logs: ssh $HOST 'cd $DIR/deploy/vm && docker compose logs -f app'"
