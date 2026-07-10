#!/usr/bin/env bash
# One-time migration from ~/.config/stayturgid/ UI-TARS paths to vendor-neutral layout.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ui_tars_env.sh
source "${SCRIPT_DIR}/ui_tars_env.sh"

OLD_STAY="${HOME}/.config/stayturgid"
NEW_MODEL="$(ui_tars_model_dir)"
NEW_LOG="$(ui_tars_log_file)"
NEW_PID="$(ui_tars_pid_file)"
DOMAIN="gui/$(id -u)"

move_path() {
  local src="$1" dst="$2"
  if [[ ! -e "$src" ]]; then
    return 0
  fi
  if [[ -e "$dst" ]]; then
    echo "  skip $src (destination exists: $dst)"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  mv "$src" "$dst"
  echo "  moved $src -> $dst"
}

move_tree() {
  local src="$1" dst="$2"
  if [[ ! -d "$src" ]] || [[ -z "$(ls -A "$src" 2>/dev/null || true)" ]]; then
    return 0
  fi
  mkdir -p "$dst"
  if [[ -z "$(ls -A "$dst" 2>/dev/null || true)" ]]; then
    mv "$src"/* "$dst"/ 2>/dev/null || true
    echo "  moved $src/* -> $dst/"
  else
    echo "  merge $src -> $dst (destination not empty)"
    shopt -s dotglob nullglob
    for item in "$src"/*; do
      [[ -e "$item" ]] || continue
      base="$(basename "$item")"
      if [[ ! -e "$dst/$base" ]]; then
        mv "$item" "$dst/$base"
        echo "    moved $base"
      fi
    done
    shopt -u dotglob nullglob
  fi
}

unload_legacy_agent() {
  local legacy
  legacy="$(ui_tars_legacy_service_plist)"
  if [[ -f "$legacy" ]]; then
    launchctl bootout "$DOMAIN" "$legacy" 2>/dev/null || true
    rm -f "$legacy"
    echo "  removed legacy LaunchAgent $(basename "$legacy")"
  fi
}

prune_empty() {
  local dir="$1"
  while [[ "$dir" == "${HOME}/.config/stayturgid"* ]] && [[ -d "$dir" ]]; do
    if [[ -n "$(ls -A "$dir" 2>/dev/null || true)" ]]; then
      return 0
    fi
    rmdir "$dir" 2>/dev/null && echo "  removed empty $dir" || return 0
    dir="$(dirname "$dir")"
  done
}

main() {
  echo "==> UI-TARS path migration (stayturgid -> vendor-neutral)"
  unload_legacy_agent

  move_tree "${OLD_STAY}/models/ui-tars-1.5-7b" "$NEW_MODEL"
  move_path "${OLD_STAY}/logs/ui-tars-server.log" "$NEW_LOG"
  move_path "${OLD_STAY}/ui-tars-server.pid" "$NEW_PID"

  prune_empty "${OLD_STAY}/models/ui-tars-1.5-7b"
  prune_empty "${OLD_STAY}/models"

  echo "==> Done. UI-TARS home: $(ui_tars_home)"
  echo "    stayturgid fleet data unchanged under ${OLD_STAY}/"
}

main "$@"
