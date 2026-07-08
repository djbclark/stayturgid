#!/usr/bin/env bash
# Resolve ADB target: USB serial when plugged in, else Tailscale wireless.
# Prefer stayturgid_device.resolve_adb (Python) for new code.
# This file remains for optional bash sourcing.
#
# Device facts come from ~/.config/stayturgid/devices.conf, generated from the
# Ansible inventory by ansible/playbooks/mac.yml — no device names live in
# code. Unknown aliases pass through unchanged (raw serial or host:port).
#
# Usage:
#   source /path/to/stayturgid/shared/mac/resolve-adb.sh
#   SERIAL="$(resolve_adb s24)"

STAYTURGID_DEVICES_CONF="${STAYTURGID_DEVICES_CONF:-$HOME/.config/stayturgid/devices.conf}"

# alias -> "usb_serial tailscale_ip lan_ip" (fields may be '-')
_device_row() {
  [ -f "$STAYTURGID_DEVICES_CONF" ] || return 1
  awk -v a="$1" '$1 == a && $1 !~ /^#/ { print $2, $3, $4; exit }' \
      "$STAYTURGID_DEVICES_CONF" | grep .
}

resolve_adb() {
  local alias="${1:?usage: resolve_adb <alias|serial|host:port>}" row usb ts lan
  if row="$(_device_row "$alias")"; then
    read -r usb ts lan <<< "$row"
    : "$lan"
    if [ "$usb" != "-" ] && adb devices 2>/dev/null | grep -qF "$usb"$'\t'"device"; then
      echo "$usb"
    elif [ -n "$ts" ] && [ "$ts" != "-" ]; then
      echo "${ts}:5555"
    elif [ -n "$lan" ] && [ "$lan" != "-" ]; then
      echo "${lan}:5555"
    else
      echo "$alias"
    fi
  else
    echo "$alias"
  fi
}

# SSH alias for a known device (assumes a matching ~/.ssh/config Host entry);
# empty when the argument isn't in the conf (raw ADB serial etc.).
resolve_ssh_host() {
  if _device_row "${1:-}" >/dev/null 2>&1; then
    echo "$1"
  else
    echo ""
  fi
}
