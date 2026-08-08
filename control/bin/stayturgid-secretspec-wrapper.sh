#!/bin/bash
# Installed as root:wheel, mode 0755, and allowed by sudoers only as _secretspec.
# This is deliberately an operation interface, not a SecretSpec CLI passthrough.
set -euo pipefail

export HOME=/var/db/stayturgid-secrets
export SECRETSPEC_PROVIDER=dotenv
export SECRETSPEC_FILE=/var/db/stayturgid-secrets/secretspec.toml
# Do not inherit caller-controlled SecretSpec selectors or dynamic loader state.
unset SECRETSPEC_PROFILE SECRETSPEC_SCOPE SECRETSPEC_REASON DYLD_LIBRARY_PATH DYLD_INSERT_LIBRARIES

if [ "${1:-}" = "verify-sync" ]; then
  if [ "$#" -ne 3 ] || ! [[ "$2" =~ ^[[:xdigit:]]{64}$ ]] || ! [[ "$3" =~ ^[[:xdigit:]]{64}$ ]]; then
    printf '%s\n' 'denied: verify-sync requires two SHA-256 digests' >&2
    exit 2
  fi
  for path in "$SECRETSPEC_FILE" "$HOME/.env"; do
    [ -f "$path" ] || {
      printf 'denied: missing vault file\n' >&2
      exit 1
    }
    [ "$(stat -f '%OLp' "$path")" = "600" ] || {
      printf 'denied: vault file mode\n' >&2
      exit 1
    }
  done
  [ "$(shasum -a 256 "$HOME/.env" | cut -d ' ' -f 1)" = "$2" ] || {
    printf 'denied: .env hash mismatch\n' >&2
    exit 1
  }
  [ "$(shasum -a 256 "$SECRETSPEC_FILE" | cut -d ' ' -f 1)" = "$3" ] || {
    printf 'denied: manifest hash mismatch\n' >&2
    exit 1
  }
  printf '%s\n' 'SecretSpec source/vault hashes and permissions match.'
  exit 0
fi

if [ "$#" -ne 1 ]; then
  printf '%s\n' 'denied: expected exactly one approved operation' >&2
  exit 2
fi

case "$1" in
  automation-env)
    exec /opt/homebrew/bin/secretspec -f "$SECRETSPEC_FILE" export --format json
    ;;
  firerpa-mcp-token)
    exec /opt/homebrew/bin/secretspec -f "$SECRETSPEC_FILE" get firerpa_mcp_token
    ;;
  *)
    printf '%s\n' 'denied: operation is not allowlisted' >&2
    exit 2
    ;;
esac
