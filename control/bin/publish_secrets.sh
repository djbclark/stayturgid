#!/usr/bin/env bash
set -euo pipefail

# This script safely publishes secrets from the operator's workspace
# into the locked-down /var/db/stayturgid-secrets/ directory.

TARGET_DIR="/var/db/stayturgid-secrets"
OPS_ROOT="${OPS_ROOT:-$HOME/ops}"
PRIVATE_SITE_DIR="$OPS_ROOT/site-private"

echo "Publishing secrets to $TARGET_DIR..."

if [ ! -d "$PRIVATE_SITE_DIR" ]; then
  echo "Error: Private site directory $PRIVATE_SITE_DIR not found." >&2
  exit 1
fi

if [ ! -f "$PRIVATE_SITE_DIR/.env" ] || [ ! -f "$PRIVATE_SITE_DIR/secretspec.toml" ]; then
  echo "Error: .env or secretspec.toml missing in $PRIVATE_SITE_DIR." >&2
  exit 1
fi

sudo mkdir -p "$TARGET_DIR"
sudo cp "$PRIVATE_SITE_DIR/.env" "$TARGET_DIR/.env"
sudo cp "$PRIVATE_SITE_DIR/secretspec.toml" "$TARGET_DIR/secretspec.toml"

sudo chown -R _secretspec "$TARGET_DIR"
sudo chmod 0700 "$TARGET_DIR"
sudo chmod 0600 "$TARGET_DIR/.env" "$TARGET_DIR/secretspec.toml"

# Verify hashes match
SRC_ENV_HASH=$(shasum -a 256 "$PRIVATE_SITE_DIR/.env" | awk '{print $1}')
DST_ENV_HASH=$(sudo shasum -a 256 "$TARGET_DIR/.env" | awk '{print $1}')

if [ "$SRC_ENV_HASH" != "$DST_ENV_HASH" ]; then
  echo "Error: Hash mismatch for .env after publishing!" >&2
  exit 1
fi

SRC_TOML_HASH=$(shasum -a 256 "$PRIVATE_SITE_DIR/secretspec.toml" | awk '{print $1}')
DST_TOML_HASH=$(sudo shasum -a 256 "$TARGET_DIR/secretspec.toml" | awk '{print $1}')

if [ "$SRC_TOML_HASH" != "$DST_TOML_HASH" ]; then
  echo "Error: Hash mismatch for secretspec.toml after publishing!" >&2
  exit 1
fi

echo "Secrets published successfully. Hashes matched."
