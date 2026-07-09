"""Light fleet health probes for Mac access_monitor (read-only).

Scrapes Termux logs / STATUS over SSH (preferred) or adb when a device is
already reachable. Thresholds match tests/device_tier.py. Never mutates the
phone — log always; callers debounce notifications.
"""
from __future__ import annotations

import re
import subprocess
from typing import Any

# Align with device_tier / AutoJs6 INTERVAL_MS (~20 min) + slack.
WATCHDOG_FRESH_SEC = 1800  # 30 min
REPAIR_FRESH_SEC = 2700  # 45 min

# Minimal gather — no md5 / VPN / overlay (those stay in make verify).
HEALTH_GATHER = r"""
export PATH=/data/data/com.termux/files/usr/bin:$PATH
export TMPDIR=/data/data/com.termux/files/usr/tmp
[ -f ~/.stayturgid/env ] && . ~/.stayturgid/env
SD="${STAYTURGID_SD:-/sdcard/stayturgid}"
echo "ssh_echo=ok"
pgrep -x sshd >/dev/null 2>&1 && echo "sshd=ok" || echo "sshd=down"
now=$(date +%s)
_age() {
  marker="$1"
  last=$(grep -h "$marker" "$SD/logs/watchdog.log" /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1 | cut -d" " -f1,2)
  if [ -z "$last" ]; then echo missing; return; fi
  ts=$(date -d "$last" +%s 2>/dev/null || echo 0)
  if [ "$ts" = 0 ]; then echo unknown; return; fi
  echo $((now - ts))
}
echo "repair_age=$(_age '\[repair\]')"
echo "watchdog_age=$(_age '\[watchdog\]')"
status=$(grep -h 'STATUS port=' "$SD/logs/watchdog.log" /sdcard/stayturgid/logs/watchdog.log ~/.stayturgid/logs/repair.log 2>/dev/null | tail -1)
if [ -n "$status" ]; then
  echo "status_line=$status"
  echo "$status" | grep -o 'a11y=[^ ]*' || echo "a11y=unknown"
else
  echo "a11y=unknown"
fi
# Merge-list presence (settings may need shell uid — best-effort via adb localhost).
a11y_list=$(adb -s localhost:5555 shell settings get secure enabled_accessibility_services 2>/dev/null </dev/null | tr -d '\r')
if [ -z "$a11y_list" ] || [ "$a11y_list" = "null" ]; then
  a11y_list=$(settings get secure enabled_accessibility_services 2>/dev/null | tr -d '\r')
fi
case "$a11y_list" in
  *org.autojs.autojs6/*) echo "autojs6_a11y=ok" ;;
  "") echo "autojs6_a11y=unknown" ;;
  *) echo "autojs6_a11y=missing" ;;
esac
"""


def parse_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _int_age(raw: str | None) -> int | None:
    if raw is None or raw in ("missing", "unknown", ""):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def evaluate_health(report: dict[str, str]) -> list[str]:
    """Return sorted issue tags (empty = healthy / inconclusive-ok)."""
    issues: list[str] = []
    if report.get("ssh_echo") == "fail":
        issues.append("ssh_echo")
    if report.get("sshd") == "down":
        issues.append("sshd_down")

    wage = _int_age(report.get("watchdog_age"))
    if report.get("watchdog_age") == "missing":
        issues.append("watchdog_missing")
    elif wage is not None and wage >= WATCHDOG_FRESH_SEC:
        issues.append("watchdog_stale")

    rage = _int_age(report.get("repair_age"))
    if report.get("repair_age") == "missing":
        issues.append("repair_missing")
    elif rage is not None and rage >= REPAIR_FRESH_SEC:
        issues.append("repair_stale")

    a11y = report.get("a11y", "")
    if a11y.startswith("FAILED") or a11y == "FAILED":
        issues.append("a11y_failed")

    if report.get("autojs6_a11y") == "missing":
        issues.append("autojs6_a11y_missing")

    return sorted(set(issues))


def summarize(report: dict[str, str], issues: list[str]) -> str:
    bits = [
        "sshd=%s" % report.get("sshd", "?"),
        "watchdog_age=%s" % report.get("watchdog_age", "?"),
        "repair_age=%s" % report.get("repair_age", "?"),
        "a11y=%s" % report.get("a11y", "?"),
        "autojs6_a11y=%s" % report.get("autojs6_a11y", "?"),
    ]
    if issues:
        bits.append("issues=%s" % ",".join(issues))
    else:
        bits.append("issues=none")
    return " ".join(bits)


def ssh_health(host: str, *, timeout: int = 25) -> dict[str, str]:
    """Run HEALTH_GATHER over SSH. On failure return ssh_echo=fail."""
    try:
        r = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "LogLevel=ERROR",
                host,
                "bash",
                "-s",
            ],
            input=HEALTH_GATHER,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ssh_echo": "fail"}
    if r.returncode != 0:
        return {"ssh_echo": "fail"}
    report = parse_kv(r.stdout or "")
    if "ssh_echo" not in report:
        report["ssh_echo"] = "ok"
    # Normalize a11y from STATUS fragment if present as a11y=...
    if "a11y" not in report and "status_line" in report:
        m = re.search(r"a11y=([^\s]+)", report["status_line"])
        if m:
            report["a11y"] = m.group(1)
    return report


def adb_health(serial: str, *, timeout: int = 25) -> dict[str, str]:
    """Best-effort Mac-side scrape when SSH is down but adb works (e.g. Fire)."""
    report: dict[str, str] = {"ssh_echo": "skip", "sshd": "unknown"}
    script = r"""
now=$(date +%s)
LOGS="/sdcard/stayturgid/logs/watchdog.log /data/data/com.termux/files/home/.stayturgid/shared/logs/watchdog.log"
age_of() {
  m="$1"
  last=$(grep -hF "$m" $LOGS 2>/dev/null | tail -1 | cut -d" " -f1,2)
  if [ -z "$last" ]; then echo missing; return; fi
  ts=$(date -d "$last" +%s 2>/dev/null || echo 0)
  if [ "$ts" = 0 ]; then echo unknown; return; fi
  echo $((now - ts))
}
echo "repair_age=$(age_of '[repair]')"
echo "watchdog_age=$(age_of '[watchdog]')"
list=$(settings get secure enabled_accessibility_services 2>/dev/null | tr -d '\r')
case "$list" in
  *org.autojs.autojs6/*) echo "autojs6_a11y=ok" ;;
  ""|null) echo "autojs6_a11y=unknown" ;;
  *) echo "autojs6_a11y=missing" ;;
esac
st=$(grep -h 'STATUS port=' $LOGS 2>/dev/null | tail -1)
echo "$st" | grep -o 'a11y=[^ ]*' || echo "a11y=unknown"
"""
    try:
        r = subprocess.run(
            ["adb", "-s", serial, "shell", "sh", "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        report.update(parse_kv(r.stdout or ""))
    except (OSError, subprocess.TimeoutExpired):
        report["probe"] = "adb_timeout"
    return report


def probe_via_path(ok_path: str, name: str) -> dict[str, Any]:
    """ok_path is 'adb:<serial_or_addr>' or 'ssh:<host_or_ip>' from access_monitor."""
    if ok_path.startswith("ssh:"):
        # Prefer SSH config alias (name) over raw Tailscale IP for keys/HostName.
        host = name
        report = ssh_health(host)
        if report.get("ssh_echo") == "fail":
            # TCP was open but auth/session failed — frozen or misconfigured sshd.
            report = {"ssh_echo": "fail", "sshd": report.get("sshd", "unknown")}
        return report
    if ok_path.startswith("adb:"):
        serial = ok_path.split(":", 1)[1]
        # Prefer SSH alias when adb works — richer Termux view.
        report = ssh_health(name)
        if report.get("ssh_echo") != "fail":
            return report
        return adb_health(serial)
    return {"ssh_echo": "skip", "probe": "unknown_path"}
