#!/usr/bin/env bash
# Start local UI-TARS-1.5-7B (GGUF) via llama.cpp.
# Prefer launchd: make vlm-service-install (persists across login).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ui_tars_env.sh
source "${SCRIPT_DIR}/ui_tars_env.sh"

MODEL_DIR="$(ui_tars_model_dir)"
MODEL="${MODEL_DIR}/ByteDance-Seed_UI-TARS-1.5-7B-Q4_K_M.gguf"
MMPROJ="${MODEL_DIR}/mmproj-ByteDance-Seed_UI-TARS-1.5-7B.gguf"
PORT="$(ui_tars_port)"
PID_FILE="$(ui_tars_pid_file)"
LOG_FILE="$(ui_tars_log_file)"

if [[ ! -f "$MODEL" ]] || [[ ! -f "$MMPROJ" ]]; then
  echo "Missing model weights in $MODEL_DIR" >&2
  echo "Run: make vlm-install" >&2
  exit 1
fi

if ui_tars_healthy; then
  echo "UI-TARS server already running on port ${PORT}"
  exit 0
fi

if ui_tars_service_installed; then
  echo "LaunchAgent installed but not healthy — restarting…"
  bash "${SCRIPT_DIR}/vlm_service.sh" restart
  exit $?
fi

ui_tars_llama_server_bin >/dev/null || {
  echo "llama-server not found — run: make vlm-install" >&2
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

echo "Starting UI-TARS-1.5-7B on 127.0.0.1:${PORT} (manual; use make vlm-service-install to persist)…"
nohup bash "${SCRIPT_DIR}/ui_tars_server_run.sh" >>"$LOG_FILE" 2>&1 &

echo $! >"$PID_FILE"
echo "PID $(cat "$PID_FILE") — log: $LOG_FILE"

for _ in $(seq 1 180); do
  if ui_tars_healthy; then
    echo "UI-TARS server ready."
    exit 0
  fi
  sleep 1
done

echo "Server did not become healthy within 180s — see $LOG_FILE" >&2
echo "Tip: make vlm-service-install for launchd" >&2
exit 1
