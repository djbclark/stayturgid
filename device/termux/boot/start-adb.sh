#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot entry — delegates to the Python supervisor (start_adb.py).
# Deploy to: ~/.termux/boot/start-adb.sh on device.
# Kept as a compat shim so existing Ansible handlers and restart callers
# (fleet_health_monitor, firerpa_heal, cfengine) continue to work.

export HOME="${HOME:-/data/data/com.termux/files/home}"
export PREFIX=/data/data/com.termux/files/usr
_stg_bin="$PREFIX/bin"
[ -d "$_stg_bin" ] && PATH="$_stg_bin:$PATH"
[ -d "$PREFIX/sbin" ] && PATH="$PREFIX/sbin:$PATH"
export PATH

PYTHON3="$PREFIX/bin/python3"
BOOT_PY="$HOME/.stayturgid/bin/start_adb.py"

if [ -x "$PYTHON3" ] && [ -f "$BOOT_PY" ]; then
    exec "$PYTHON3" "$BOOT_PY"
fi

# Fallback: bare sshd start (boot script deployed before Python version)
rm -f /data/data/com.termux/files/usr/var/service/sshd/down 2>/dev/null || true
pgrep -x sshd >/dev/null 2>&1 || sshd
