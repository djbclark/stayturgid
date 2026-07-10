#!/usr/bin/env bash
# Install UI-TARS-1.5-7B GGUF + mmproj (vendor-neutral; Homebrew llama.cpp).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ui_tars_env.sh
source "${SCRIPT_DIR}/ui_tars_env.sh"

MODEL_DIR="$(ui_tars_model_dir)"
BASE_URL="https://huggingface.co/adriabama06/UI-TARS-1.5-7B-GGUF/resolve/main"

echo "==> brew install llama.cpp (if needed)"
brew list llama.cpp >/dev/null 2>&1 || brew install llama.cpp

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

download() {
  local name="$1"
  if [[ -f "$name" ]]; then
    echo "  ok  $name"
    return 0
  fi
  echo "  get $name …"
  curl -L --fail --continue-at - -o "$name" "${BASE_URL}/${name}"
}

echo "==> Download UI-TARS weights to $MODEL_DIR (~5.9 GB total)"
download "ByteDance-Seed_UI-TARS-1.5-7B-Q4_K_M.gguf"
download "mmproj-ByteDance-Seed_UI-TARS-1.5-7B.gguf"

echo "==> Done."
echo "    Models:  ${MODEL_DIR}"
echo "    Service: make vlm-service-install"
echo "    Test:    make vlm-check"
