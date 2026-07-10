#!/usr/bin/env bash
# Start local UI-TARS-1.5-7B (GGUF) via llama.cpp for stayturgid vision gates.
set -euo pipefail

MODEL_DIR="${STAYTURGID_VLM_MODEL_DIR:-${QSS_VLM_MODEL_DIR:-${HOME}/.config/stayturgid/models/ui-tars-1.5-7b}}"
MODEL="${MODEL_DIR}/ByteDance-Seed_UI-TARS-1.5-7B-Q4_K_M.gguf"
MMPROJ="${MODEL_DIR}/mmproj-ByteDance-Seed_UI-TARS-1.5-7B.gguf"
PORT="${STAYTURGID_VLM_PORT:-${QSS_VLM_PORT:-8081}}"
PID_FILE="${STAYTURGID_VLM_PID_FILE:-${HOME}/.config/stayturgid/ui-tars-server.pid}"
LOG_FILE="${STAYTURGID_VLM_LOG:-${HOME}/.config/stayturgid/logs/ui-tars-server.log}"

if [[ ! -f "$MODEL" ]]; then
  echo "Missing model: $MODEL" >&2
  echo "Run: make vlm-install" >&2
  exit 1
fi
if [[ ! -f "$MMPROJ" ]]; then
  echo "Missing mmproj: $MMPROJ" >&2
  echo "Run: make vlm-install" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"

if [[ -z "${STAYTURGID_VLM_NGL:-${QSS_VLM_NGL:-}}" ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    QSS_VLM_NGL=99
  else
    QSS_VLM_NGL=0
  fi
fi
NGL="${STAYTURGID_VLM_NGL:-${QSS_VLM_NGL}}"

if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "UI-TARS server already running on port ${PORT}"
  exit 0
fi

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "Stopping stale UI-TARS server pid=$old_pid"
    kill "$old_pid" 2>/dev/null || true
    sleep 2
  fi
fi

echo "Starting UI-TARS-1.5-7B on 127.0.0.1:${PORT} (may take 1-3 min to load)…"
nohup caffeinate -dims llama-server \
  -m "$MODEL" \
  --mmproj "$MMPROJ" \
  -ngl "$NGL" \
  -c "${STAYTURGID_VLM_CTX:-${QSS_VLM_CTX:-2048}}" \
  -t "${STAYTURGID_VLM_THREADS:-${QSS_VLM_THREADS:-4}}" \
  -n 256 \
  --image-min-tokens "${STAYTURGID_VLM_IMAGE_MIN:-${QSS_VLM_IMAGE_MIN:-256}}" \
  --image-max-tokens "${STAYTURGID_VLM_IMAGE_MAX:-${QSS_VLM_IMAGE_MAX:-512}}" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --parallel 1 \
  >>"$LOG_FILE" 2>&1 &

echo $! >"$PID_FILE"
echo "PID $(cat "$PID_FILE") — log: $LOG_FILE"

for _ in $(seq 1 180); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "UI-TARS server ready."
    exit 0
  fi
  sleep 1
done

echo "Server did not become healthy within 180s — see $LOG_FILE" >&2
exit 1
