#!/usr/bin/env bash
# Resolve ADB target: USB serial when plugged in, else Tailscale wireless.
# Shared by mac/, autojs6/mac/, obtainium/mac/, and other modules.
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
    else
      echo "${ts}:5555"
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
