#!/usr/bin/env bash
# Install and manage UI-TARS llama-server as a macOS LaunchAgent (launchctl).
#
# Prefer standard launchctl commands — see PATHS.md and docs/vlm.md.
# This script is used once at install time and for status helpers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Inline env helper (replaces ui_tars_env.sh)
_env() { python3 "${SCRIPT_DIR}/ui_tars_env.py" --get "$1"; }

RUN_SCRIPT="${SCRIPT_DIR}/ui_tars_server_run.sh"
LABEL="$(_env SERVICE_LABEL)"
PLIST="$(_env SERVICE_PLIST)"
PORT="$(_env PORT)"
LOG_FILE="$(_env LOG_FILE)"

launchctl_domain() {
  printf 'gui/%s' "$(id -u)"
}

service_loaded() {
  launchctl print "$(launchctl_domain)/$(_env SERVICE_LABEL)" >/dev/null 2>&1
}

service_bootstrap() {
  local domain
  domain="$(launchctl_domain)"
  if service_loaded; then
    launchctl bootout "$domain" "$PLIST" 2>/dev/null || true
  fi
  launchctl bootstrap "$domain" "$PLIST"
}

service_bootout() {
  local domain
  domain="$(launchctl_domain)"
  if service_loaded; then
    launchctl bootout "$domain" "$PLIST"
  fi
}

service_kickstart() {
  launchctl kickstart -k "$(launchctl_domain)/$(_env SERVICE_LABEL)" 2>/dev/null || true
}

die() {
  echo "vlm-service: $*" >&2
  exit 1
}

need_macos() {
  [[ "$(uname -s)" == "Darwin" ]] || die "UI-TARS LaunchAgent is macOS-only"
}

need_brew() {
  command -v brew >/dev/null 2>&1 || die "Homebrew required — https://brew.sh"
}

write_plist() {
  need_macos
  need_brew
  chmod +x "$RUN_SCRIPT"
  mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG_FILE")" "$(_env WORKING_DIR)"

  local llama_bin work_dir
  llama_bin="$(_env LLAMA_SERVER_BIN)" || die "llama-server missing — brew install llama.cpp"
  # model dir validated by run script; ensure parent tree exists
  mkdir -p "$(_env MODEL_DIR)"
  work_dir="$(_env WORKING_DIR)"

  cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>Comment</key>
  <string>UI-TARS-1.5-7B llama-server (local vision model sidecar)</string>
  <key>ProgramArguments</key>
  <array>
    <string>${RUN_SCRIPT}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${work_dir}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>$(brew --prefix)/bin:$(brew --prefix llama.cpp 2>/dev/null)/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_FILE}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_FILE}</string>
  <key>ThrottleInterval</key>
  <integer>30</integer>
</dict>
</plist>
EOF
  echo "Wrote ${PLIST}"
  echo "  run script: ${RUN_SCRIPT}"
  echo "  llama-server: ${llama_bin}"
}

stop_manual_server() {
  local pid_file
  pid_file="$(_env PID_FILE)"
  if [[ -f "$pid_file" ]]; then
    local old_pid
    old_pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      echo "Stopping manual UI-TARS server pid=${old_pid}"
      kill "$old_pid" 2>/dev/null || true
      sleep 2
    fi
    rm -f "$pid_file"
  fi
}

cmd_install() {
  need_macos
  need_brew
  local repo_root
  repo_root="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  export ANSIBLE_CONFIG="${repo_root}/ansible/ansible.cfg"
  exec ansible-playbook "${repo_root}/ansible/playbooks/control_node/site.yml" \
    --tags vlm-service \
    -e stayturgid_vlm_enabled=true
}

cmd_uninstall() {
  need_macos
  need_brew
  if [[ -f "${PLIST}" ]]; then
    service_bootout
    rm -f "$PLIST"
    echo "Removed ${PLIST}"
  else
    echo "Service not installed"
  fi
  stop_manual_server
}

cmd_start() {
  need_macos
  need_brew
  [[ -f "${PLIST}" ]] || die "not installed — run: just vlm-service-install"
  service_bootstrap
  service_kickstart
  wait_healthy 240
}

cmd_stop() {
  need_macos
  need_brew
  if [[ -f "${PLIST}" ]]; then
    service_bootout
  fi
  stop_manual_server
  echo "stopped"
}

cmd_restart() {
  need_macos
  need_brew
  [[ -f "${PLIST}" ]] || die "not installed — run: just vlm-service-install"
  stop_manual_server
  service_bootout
  service_bootstrap
  service_kickstart
  wait_healthy 240
}

wait_healthy() {
  local timeout="${1:-120}"
  local i
  for ((i = 1; i <= timeout; i++)); do
    if curl -sf -o /dev/null http://127.0.0.1:${PORT}/health; then
      echo "healthy: $(_env HEALTH_URL)"
      return 0
    fi
    sleep 1
  done
  return 1
}

cmd_status() {
  local healthy="no"
  curl -sf -o /dev/null http://127.0.0.1:${PORT}/health && healthy="yes"

  echo "UI-TARS VLM service"
  echo "  health:     ${healthy} ($(_env HEALTH_URL))"
  echo "  port:       ${PORT}"
  echo "  log:        ${LOG_FILE}"
  echo "  plist:      ${PLIST}"
  echo "  models:     $(_env MODEL_DIR)"
  echo "  installed:  $([[ -f "${PLIST}" ]] && echo yes || echo no)"

  echo "  launchd:    $(service_loaded && echo loaded || echo not_loaded) ($(_env SERVICE_LABEL))"

  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo ""
    echo "launchctl:"
    launchctl print "$(launchctl_domain)/$(_env SERVICE_LABEL)" 2>/dev/null | head -12 || echo "  (not loaded)"
  fi

  if [[ "$healthy" == "no" ]] && [[ -f "$LOG_FILE" ]]; then
    echo ""
    echo "last log lines:"
    tail -8 "$LOG_FILE" 2>/dev/null || true
  fi

  curl -sf -o /dev/null http://127.0.0.1:${PORT}/health
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <install|uninstall|start|stop|restart|status>

Install once, then use launchctl (see docs/vlm.md):
  launchctl kickstart -k gui/\$(id -u)/$(_env SERVICE_LABEL)
  launchctl bootout gui/\$(id -u) $(_env SERVICE_PLIST)

  install    migrate paths, write plist, launchctl bootstrap
  uninstall  launchctl bootout + remove plist
  start|stop|restart|status — wrappers around launchctl
EOF
}

main() {
  local cmd="${1:-status}"
  case "$cmd" in
    install) cmd_install ;;
    uninstall) cmd_uninstall ;;
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_restart ;;
    status) cmd_status ;;
    -h|--help|help) usage ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
