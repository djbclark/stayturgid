#!/bin/bash
# Installed as root:wheel, mode 0755, and allowed by sudoers only as _secretspec.
# This is deliberately an operation interface, not a SecretSpec CLI passthrough.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  printf '%s\n' 'denied: expected exactly one approved operation' >&2
  exit 2
fi

export HOME=/var/db/stayturgid-secrets
export SECRETSPEC_PROVIDER=dotenv
export SECRETSPEC_FILE=/var/db/stayturgid-secrets/secretspec.toml
# Do not inherit caller-controlled SecretSpec selectors or dynamic loader state.
unset SECRETSPEC_PROFILE SECRETSPEC_SCOPE SECRETSPEC_REASON DYLD_LIBRARY_PATH DYLD_INSERT_LIBRARIES

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
