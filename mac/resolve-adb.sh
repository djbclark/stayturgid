#!/usr/bin/env bash
# Resolve ADB target: USB serial when plugged in, else Tailscale wireless.
# Usage: source mac/resolve-adb.sh && resolve_adb p7a
#
# Aliases: p7a, s24. Pass a raw serial or host:port to use as-is.

resolve_adb() {
  local alias="${1:?usage: resolve_adb <p7a|s24|serial>}"
  case "$alias" in
    p7a)
      if adb devices 2>/dev/null | grep -qF $'35261JEHN12374\tdevice'; then
        echo "35261JEHN12374"
      else
        echo "100.65.230.108:5555"
      fi
      ;;
    s24)
      if adb devices 2>/dev/null | grep -qF $'RFCX219CHKA\tdevice'; then
        echo "RFCX219CHKA"
      else
        echo "100.123.218.30:5555"
      fi
      ;;
    *)
      echo "$alias"
      ;;
  esac
}
