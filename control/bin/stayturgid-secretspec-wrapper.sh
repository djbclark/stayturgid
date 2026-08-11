#!/bin/bash
# Root-owned, fail-closed SecretSpec operation interface.
#
# The AI/operator invokes this wrapper through sudo. It is deliberately an
# allowlisted lifecycle API, not a general SecretSpec CLI passthrough.
set -euo pipefail

SECRETSPEC_BIN=/opt/homebrew/bin/secretspec
VAULT_DIR=/var/db/stayturgid-secrets
VAULT_HOME="$VAULT_DIR"
VAULT_MANIFEST="$VAULT_DIR/secretspec.toml"
SOURCE_DIR="$VAULT_DIR"
SOURCE_MANIFEST="$VAULT_MANIFEST"
SOURCE_ENV="$VAULT_DIR/.env"
SOURCE_EXAMPLE=/Users/djbclark/ops/site-private/secretspec.toml.example

fail() {
  printf 'denied: %s\n' "$1" >&2
  exit 2
}

valid_name() {
  [[ "${1:-}" =~ ^[A-Z][A-Z0-9_]*$ ]] || fail 'secret name must be uppercase ASCII'
}

declared_name() {
  local name=$1
  valid_name "$name"
  grep -Eq "^${name}[[:space:]]*=" "$SOURCE_MANIFEST" || fail 'secret is not declared; add it through source-add'
}

valid_description() {
  local description=$1
  [[ -n "$description" && ${#description} -le 240 && "$description" != *$'\n'* && "$description" != *$'\r'* ]] || fail 'description must be 1-240 characters without newlines'
}

sync_source() {
  [[ -d "$VAULT_DIR" && ! -L "$VAULT_DIR" ]] || fail 'vault directory missing or symlinked'
  [[ -f "$SOURCE_MANIFEST" && ! -L "$SOURCE_MANIFEST" ]] || fail 'manifest missing or symlinked'
  [[ -f "$SOURCE_ENV" && ! -L "$SOURCE_ENV" ]] || fail 'dotenv file missing or symlinked'
  chown _secretspec:staff "$VAULT_DIR" "$SOURCE_MANIFEST" "$SOURCE_ENV"
  chmod 0700 "$VAULT_DIR"
  chmod 0600 "$SOURCE_MANIFEST" "$SOURCE_ENV"
}

run_source() {
  local reason=$1
  shift
  export HOME="$SOURCE_DIR"
  export SECRETSPEC_PROVIDER=dotenv
  export SECRETSPEC_FILE="$SOURCE_MANIFEST"
  export SECRETSPEC_REASON="$reason"
  unset SECRETSPEC_PROFILE SECRETSPEC_SCOPE DYLD_LIBRARY_PATH DYLD_INSERT_LIBRARIES
  "$SECRETSPEC_BIN" -f "$SOURCE_MANIFEST" "$@"
}

[[ "$(id -u)" -eq 0 || "$(id -un)" == "_secretspec" ]] || fail 'unexpected execution user'

operation=${1:-}
case "$operation" in
  verify-sync)
    [[ "$(id -un)" == "_secretspec" && $# -eq 3 ]] || fail 'verify-sync requires _secretspec and two digests'
    [[ "$2" =~ ^[[:xdigit:]]{64}$ && "$3" =~ ^[[:xdigit:]]{64}$ ]] || fail 'verify-sync requires two SHA-256 digests'
    for path in "$VAULT_MANIFEST" "$VAULT_DIR/.env"; do
      [[ -f "$path" && ! -L "$path" ]] || {
        printf 'denied: missing vault file\n' >&2
        exit 1
      }
      [[ "$(stat -f '%OLp' "$path")" == 600 ]] || {
        printf 'denied: vault file mode\n' >&2
        exit 1
      }
    done
    [[ "$(shasum -a 256 "$VAULT_DIR/.env" | cut -d ' ' -f 1)" == "$2" ]] || {
      printf 'denied: .env hash mismatch\n' >&2
      exit 1
    }
    [[ "$(shasum -a 256 "$VAULT_MANIFEST" | cut -d ' ' -f 1)" == "$3" ]] || {
      printf 'denied: manifest hash mismatch\n' >&2
      exit 1
    }
    printf '%s\n' 'SecretSpec source/vault hashes and permissions match.'
    ;;
  automation-env)
    [[ "$(id -un)" == "_secretspec" && $# -eq 1 ]] || fail 'automation-env requires _secretspec'
    export HOME="$VAULT_HOME" SECRETSPEC_PROVIDER=dotenv SECRETSPEC_FILE="$VAULT_MANIFEST"
    unset SECRETSPEC_PROFILE SECRETSPEC_SCOPE SECRETSPEC_REASON DYLD_LIBRARY_PATH DYLD_INSERT_LIBRARIES
    exec "$SECRETSPEC_BIN" -f "$VAULT_MANIFEST" export --format json
    ;;
  firerpa-mcp-token)
    [[ "$(id -un)" == "_secretspec" && $# -eq 1 ]] || fail 'firerpa-mcp-token requires _secretspec'
    export HOME="$VAULT_HOME" SECRETSPEC_PROVIDER=dotenv SECRETSPEC_FILE="$VAULT_MANIFEST"
    unset SECRETSPEC_PROFILE SECRETSPEC_SCOPE SECRETSPEC_REASON DYLD_LIBRARY_PATH DYLD_INSERT_LIBRARIES
    exec "$SECRETSPEC_BIN" -f "$VAULT_MANIFEST" get firerpa_mcp_token --reason 'approved firerpa consumer'
    ;;
  source-add)
    [[ "$(id -u)" -eq 0 && $# -eq 3 ]] || fail 'source-add requires root, a name, and a description'
    valid_name "$2"
    valid_description "$3"
    grep -Eq "^${2}[[:space:]]*=" "$SOURCE_MANIFEST" && fail 'secret is already declared'
    run_source 'wrapper source-add' add "$2" --description "$3"
    sync_source
    printf 'declaration added to runtime; mirror %s in %s through a worktree PR\n' "$2" "$SOURCE_EXAMPLE"
    ;;
  source-set)
    [[ "$(id -u)" -eq 0 && $# -eq 2 ]] || fail 'source-set requires root and one declared secret name'
    declared_name "$2"
    run_source 'wrapper source-set' set "$2"
    sync_source
    ;;
  source-delete)
    [[ "$(id -u)" -eq 0 && $# -eq 2 ]] || fail 'source-delete requires root and one declared secret name'
    declared_name "$2"
    run_source 'wrapper source-delete' delete "$2"
    sync_source
    ;;
  source-get)
    [[ "$(id -u)" -eq 0 && $# -eq 2 ]] || fail 'source-get requires root and one declared secret name'
    declared_name "$2"
    run_source 'wrapper source-get' get "$2"
    ;;
  source-check)
    [[ "$(id -u)" -eq 0 && $# -eq 1 ]] || fail 'source-check requires root'
    run_source 'wrapper source-check' check --no-prompt
    ;;
  source-export)
    [[ "$(id -u)" -eq 0 && $# -eq 1 ]] || fail 'source-export requires root'
    run_source 'wrapper source-export' export --format json
    ;;
  source-template-check)
    [[ "$(id -u)" -eq 0 && $# -eq 1 ]] || fail 'source-template-check requires root'
    [[ -f "$SOURCE_EXAMPLE" && ! -L "$SOURCE_EXAMPLE" ]] || fail 'tracked declaration example missing or symlinked'
    cmp -s "$SOURCE_MANIFEST" "$SOURCE_EXAMPLE" || fail 'runtime manifest differs from tracked declaration example'
    printf 'runtime manifest matches tracked declaration example\n'
    ;;
  source-publish)
    [[ "$(id -u)" -eq 0 && $# -eq 1 ]] || fail 'source-publish requires root'
    sync_source
    ;;
  *)
    fail 'operation is not allowlisted'
    ;;
esac
