#!/usr/bin/env bash
set -euo pipefail

# Publish the two SecretSpec inputs, then fail closed unless the source and
# root-owned vault are byte-identical private regular files. No secret values
# are printed or logged.
TARGET_DIR="/var/db/stayturgid-secrets"
OPS_ROOT="${OPS_ROOT:-$HOME/ops}"
PRIVATE_SITE_DIR="$OPS_ROOT/site-private"
VERIFY_SCRIPT="$(cd "$(dirname "$0")" && pwd)/verify_secretspec_sync.py"

if [ ! -d "$PRIVATE_SITE_DIR" ] || [ -L "$PRIVATE_SITE_DIR" ]; then
  echo "Error: private site directory is missing or a symlink." >&2
  exit 1
fi
for name in .env secretspec.toml; do
  path="$PRIVATE_SITE_DIR/$name"
  if [ ! -f "$path" ] || [ -L "$path" ]; then
    echo "Error: $path must be a regular file (not a symlink)." >&2
    exit 1
  fi
done
# The source copy is itself private operator state; repair overly broad modes
# before publishing so the verifier and the source remain owner-only.
chmod 0600 "$PRIVATE_SITE_DIR/.env" "$PRIVATE_SITE_DIR/secretspec.toml"

sudo mkdir -p "$TARGET_DIR"
sudo chown _secretspec "$TARGET_DIR"
sudo chmod 0700 "$TARGET_DIR"
# install writes the named destination with the requested mode and does not
# copy source metadata or follow a source symlink (which was rejected above).
sudo install -o _secretspec -g staff -m 0600 "$PRIVATE_SITE_DIR/.env" "$TARGET_DIR/.env"
sudo install -o _secretspec -g staff -m 0600 "$PRIVATE_SITE_DIR/secretspec.toml" "$TARGET_DIR/secretspec.toml"

python3 "$VERIFY_SCRIPT" "$PRIVATE_SITE_DIR" "$TARGET_DIR"
