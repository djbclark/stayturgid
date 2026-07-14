#!/usr/bin/env bash
# Start local UI-TARS-1.5-7B (GGUF) via llama.cpp.
# Prefer launchd: just vlm-service-install (persists across login).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Inline env helper (replaces ui_tars_env.sh)
_env() { python3 "${SCRIPT_DIR}/ui_tars_env.py" --get "$1"; }

MODEL_DIR="$(_env MODEL_DIR)"
MODEL="${MODEL_DIR}/ByteDance-Seed_UI-TARS-1.5-7B-Q4_K_M.gguf"
MMPROJ="${MODEL_DIR}/mmproj-ByteDance-Seed_UI-TARS-1.5-7B.gguf"
PORT="$(_env PORT)"
PID_FILE="$(_env PID_FILE)"
LOG_FILE="$(_env LOG_FILE)"

if [[ ! -f "$MODEL" ]] || [[ ! -f "$MMPROJ" ]]; then
  echo "Missing model weights in $MODEL_DIR" >&2
  echo "Run: just vlm-install" >&2
  exit 1
fi

if curl -sf -o /dev/null http://127.0.0.1:${PORT}/health; then
  echo "UI-TARS server already running on port ${PORT}"
  exit 0
fi

if [[ -f "${PLIST}" ]]; then
  echo "LaunchAgent installed but not healthy — restarting…"
  bash "${SCRIPT_DIR}/vlm_service.sh" restart
  exit $?
fi

test -x "$(_env LLAMA_SERVER_BIN)" >/dev/null || {
  echo "llama-server not found — run: just vlm-install" >&2
  exit 1
}

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "Stopping stale UI-TARS server pid=$old_pid"
    kill "$old_pid" 2>/dev/null || true
    sleep 2
  fi
fi

echo "Starting UI-TARS-1.5-7B on 127.0.0.1:${PORT} (manual; use just vlm-service-install to persist)…"
nohup bash "${SCRIPT_DIR}/ui_tars_server_run.sh" >>"$LOG_FILE" 2>&1 &

echo $! >"$PID_FILE"
echo "PID $(cat "$PID_FILE") — log: $LOG_FILE"

for _ in $(seq 1 180); do
  if curl -sf -o /dev/null http://127.0.0.1:${PORT}/health; then
    echo "UI-TARS server ready."
    exit 0
  fi
  sleep 1
done

echo "Server did not become healthy within 180s — see $LOG_FILE" >&2
echo "Tip: just vlm-service-install for launchd" >&2
exit 1
