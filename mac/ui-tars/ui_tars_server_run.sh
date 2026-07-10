#!/usr/bin/env bash
# Foreground UI-TARS llama-server — used by launchd and manual debug.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ui_tars_env.sh
source "${SCRIPT_DIR}/ui_tars_env.sh"

MODEL_DIR="$(ui_tars_model_dir)"
MODEL="${MODEL_DIR}/ByteDance-Seed_UI-TARS-1.5-7B-Q4_K_M.gguf"
MMPROJ="${MODEL_DIR}/mmproj-ByteDance-Seed_UI-TARS-1.5-7B.gguf"
PORT="$(ui_tars_port)"
LOG_FILE="$(ui_tars_log_file)"
LLAMA="$(ui_tars_llama_server_bin)" || {
  echo "llama-server not found — run: brew install llama.cpp" >&2
  exit 1
}

if [[ ! -f "$MODEL" ]] || [[ ! -f "$MMPROJ" ]]; then
  echo "Missing model weights in $MODEL_DIR — run: make vlm-install" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"

exec >>"$LOG_FILE" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') ui-tars-server-run: starting llama-server on 127.0.0.1:${PORT}"
echo "$(date '+%Y-%m-%d %H:%M:%S') model=$MODEL"
echo "$(date '+%Y-%m-%d %H:%M:%S') llama=$LLAMA ngl=$(ui_tars_ngl)"

exec caffeinate -dims "$LLAMA" \
  -m "$MODEL" \
  --mmproj "$MMPROJ" \
  -ngl "$(ui_tars_ngl)" \
  -c "${UI_TARS_CTX:-${STAYTURGID_VLM_CTX:-${QSS_VLM_CTX:-2048}}}" \
  -t "${UI_TARS_THREADS:-${STAYTURGID_VLM_THREADS:-${QSS_VLM_THREADS:-4}}}" \
  -n 256 \
  --image-min-tokens "${UI_TARS_IMAGE_MIN:-${STAYTURGID_VLM_IMAGE_MIN:-${QSS_VLM_IMAGE_MIN:-256}}}" \
  --image-max-tokens "${UI_TARS_IMAGE_MAX:-${STAYTURGID_VLM_IMAGE_MAX:-${QSS_VLM_IMAGE_MAX:-512}}}" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --parallel 1
