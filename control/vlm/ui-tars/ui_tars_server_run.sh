#!/usr/bin/env bash
# Foreground UI-TARS llama-server — used by launchd and manual debug.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Inline env helper (replaces ui_tars_env.sh)
_env() { python3 "${SCRIPT_DIR}/ui_tars_env.py" --get "$1"; }

MODEL_DIR="$(_env MODEL_DIR)"
MODEL="${MODEL_DIR}/ByteDance-Seed_UI-TARS-1.5-7B-Q4_K_M.gguf"
MMPROJ="${MODEL_DIR}/mmproj-ByteDance-Seed_UI-TARS-1.5-7B.gguf"
PORT="$(_env PORT)"
LOG_FILE="$(_env LOG_FILE)"
LLAMA="$(_env LLAMA_SERVER_BIN)" || {
  echo "llama-server not found — run: brew install llama.cpp" >&2
  exit 1
}

if [[ ! -f "$MODEL" ]] || [[ ! -f "$MMPROJ" ]]; then
  echo "Missing model weights in $MODEL_DIR — run: just vlm-install" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"

exec >>"$LOG_FILE" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') ui-tars-server-run: starting llama-server on 127.0.0.1:${PORT}"
echo "$(date '+%Y-%m-%d %H:%M:%S') model=$MODEL"
echo "$(date '+%Y-%m-%d %H:%M:%S') llama=$LLAMA ngl=$(_env NGL)"

exec caffeinate -dims "$LLAMA" \
  -m "$MODEL" \
  --mmproj "$MMPROJ" \
  -ngl "$(_env NGL)" \
  -c "${UI_TARS_CTX:-${STAYTURGID_VLM_CTX:-${QSS_VLM_CTX:-2048}}}" \
  -t "${UI_TARS_THREADS:-${STAYTURGID_VLM_THREADS:-${QSS_VLM_THREADS:-4}}}" \
  -n 256 \
  --image-min-tokens "${UI_TARS_IMAGE_MIN:-${STAYTURGID_VLM_IMAGE_MIN:-${QSS_VLM_IMAGE_MIN:-256}}}" \
  --image-max-tokens "${UI_TARS_IMAGE_MAX:-${STAYTURGID_VLM_IMAGE_MAX:-${QSS_VLM_IMAGE_MAX:-512}}}" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --parallel 1
