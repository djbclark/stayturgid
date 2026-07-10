# Shared UI-TARS / llama-server paths (source from bash scripts).
# Vendor-neutral layout — not tied to stayturgid.
# shellcheck shell=bash

ui_tars_home() {
  printf '%s\n' "${UI_TARS_HOME:-${HOME}/.local/share/ui-tars}"
}

ui_tars_model_dir() {
  if [[ -n "${UI_TARS_MODEL_DIR:-}" ]]; then
    printf '%s\n' "$UI_TARS_MODEL_DIR"
    return
  fi
  if [[ -n "${STAYTURGID_VLM_MODEL_DIR:-}" ]]; then
    printf '%s\n' "$STAYTURGID_VLM_MODEL_DIR"
    return
  fi
  if [[ -n "${QSS_VLM_MODEL_DIR:-}" ]]; then
    printf '%s\n' "$QSS_VLM_MODEL_DIR"
    return
  fi
  printf '%s\n' "$(ui_tars_home)/models/1.5-7b"
}

ui_tars_port() {
  printf '%s\n' "${UI_TARS_PORT:-${STAYTURGID_VLM_PORT:-${QSS_VLM_PORT:-8081}}}"
}

ui_tars_pid_file() {
  printf '%s\n' "${UI_TARS_PID_FILE:-$(ui_tars_home)/server/server.pid}"
}

ui_tars_log_file() {
  if [[ -n "${UI_TARS_LOG:-}" ]]; then
    printf '%s\n' "$UI_TARS_LOG"
    return
  fi
  if [[ -n "${STAYTURGID_VLM_LOG:-}" ]]; then
    printf '%s\n' "$STAYTURGID_VLM_LOG"
    return
  fi
  if [[ -n "${QSS_VLM_LOG:-}" ]]; then
    printf '%s\n' "$QSS_VLM_LOG"
    return
  fi
  if [[ "$(uname -s)" == "Darwin" ]]; then
    printf '%s\n' "${HOME}/Library/Logs/ui-tars/server.log"
  else
    printf '%s\n' "$(ui_tars_home)/server/server.log"
  fi
}

ui_tars_working_dir() {
  printf '%s\n' "${UI_TARS_HOME:-$(ui_tars_home)}/server"
}

ui_tars_ngl() {
  if [[ -n "${UI_TARS_NGL:-${STAYTURGID_VLM_NGL:-${QSS_VLM_NGL:-}}}" ]]; then
    printf '%s\n' "${UI_TARS_NGL:-${STAYTURGID_VLM_NGL:-$QSS_VLM_NGL}}"
    return
  fi
  if [[ "$(uname -s)" == "Darwin" ]]; then
    printf '%s\n' "99"
  else
    printf '%s\n' "0"
  fi
}

ui_tars_llama_server_bin() {
  if [[ -n "${UI_TARS_LLAMA_SERVER:-${STAYTURGID_VLM_LLAMA_SERVER:-${QSS_VLM_LLAMA_SERVER:-}}}" ]] \
    && [[ -x "${UI_TARS_LLAMA_SERVER:-${STAYTURGID_VLM_LLAMA_SERVER:-${QSS_VLM_LLAMA_SERVER:-}}}" ]]; then
    printf '%s\n' "${UI_TARS_LLAMA_SERVER:-${STAYTURGID_VLM_LLAMA_SERVER:-$QSS_VLM_LLAMA_SERVER}}"
    return
  fi
  if command -v llama-server >/dev/null 2>&1; then
    command -v llama-server
    return
  fi
  local brew_prefix
  brew_prefix="$(brew --prefix llama.cpp 2>/dev/null || true)"
  if [[ -n "$brew_prefix" ]] && [[ -x "${brew_prefix}/bin/llama-server" ]]; then
    printf '%s\n' "${brew_prefix}/bin/llama-server"
    return
  fi
  return 1
}

ui_tars_health_url() {
  printf 'http://127.0.0.1:%s/health\n' "$(ui_tars_port)"
}

ui_tars_healthy() {
  curl -sf "$(ui_tars_health_url)" >/dev/null 2>&1
}

ui_tars_service_label() {
  printf '%s\n' "homebrew.mxcl.ui-tars"
}

ui_tars_service_plist() {
  printf '%s\n' "${HOME}/Library/LaunchAgents/$(ui_tars_service_label).plist"
}

ui_tars_legacy_service_label() {
  printf '%s\n' "homebrew.mxcl.qss-ui-tars"
}

ui_tars_legacy_service_plist() {
  printf '%s\n' "${HOME}/Library/LaunchAgents/$(ui_tars_legacy_service_label).plist"
}

ui_tars_service_installed() {
  [[ -f "$(ui_tars_service_plist)" ]]
}
