"""Fleet health probes for Mac monitors (read-only).

Scrapes Termux logs / STATUS / a11y over SSH (preferred) or adb. Thresholds
align with tests/device_tier.py. Never mutates the phone.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SHARED = _HERE.parent
_REPO = _HERE.parents[2]
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

# Align with the native-agent 20-minute heartbeat plus slack.
WATCHDOG_FRESH_SEC = 1800  # 30 min
REPAIR_FRESH_SEC = 2700  # 45 min
SSH_PORT = 8022

# Durable, Shizuku-independent native-agent heartbeat (#86). 3x the 120s
# HostService heartbeat interval (see HeartbeatWriter.HEARTBEAT_INTERVAL_MS in
# device/native-agent/.../Heartbeat.kt) + 60s jitter margin. MUST match
# FRESHNESS_SEC in device/termux/cfengine/policy/stayturgid.cf — both read the
# same /sdcard/Download/stayturgid-agent.heartbeat.txt file (the .txt is
# MediaStore's own doing — see HeartbeatWriter.FILE_NAME's comment) with the
# same threshold so the on-device and Mac-side liveness checks cannot disagree
# (unify rule, #86). This — not the old agent_age below, which stays
# Shizuku-coupled — is what drives agent_missing/agent_stale.
AGENT_HEARTBEAT_FRESH_SEC = 420  # 7 min


# Resolved at import via stayturgid_device when available; absolute path for launchd.
def _adb_bin() -> str:
    try:
        from stayturgid_device import adb_bin

        return adb_bin()
    except ImportError:
        return os.environ.get("STAYTURGID_ADB", "/opt/homebrew/bin/adb")


ADB = _adb_bin()

# Shared by SSH + adb gather scripts. Avoid GNU `date -d` (toybox → unknown ages
# → stale looked clean on Mac soft-health).
_PORTABLE_AGE_BODY = r"""
  # Portable parse — GNU date -d fails on many Android toybox builds.
  age=$(python3 -c '
import sys, time
from datetime import datetime
s = sys.argv[1].strip()
for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
    try:
        ts = datetime.strptime(s, fmt).timestamp()
        print(int(time.time() - ts))
        raise SystemExit(0)
    except ValueError:
        pass
print("unknown")
' "$last" 2>/dev/null) || age=unknown
  if [ -z "$age" ]; then age=unknown; fi
  echo "$age"
"""

HEALTH_GATHER = (
    r"""
export PATH=/data/data/com.termux/files/usr/bin:$PATH
export TMPDIR=/data/data/com.termux/files/usr/tmp
[ -f ~/.stayturgid/env ] && . ~/.stayturgid/env
SD="${STAYTURGID_SD:-/sdcard/stayturgid}"
FIRE=0
case "$SD" in *termux/files/home*) FIRE=1; echo "localhost_shell=skip" ;; esac
echo "ssh_echo=ok"
pgrep sshd >/dev/null 2>&1 && echo "sshd=ok" || echo "sshd=down"
pgrep -f 'start_adb\.py' >/dev/null 2>&1 && echo "bootloop=ok" || echo "bootloop=down"
if [ "$FIRE" = 1 ]; then
  echo "shell5555=skip"
else
  adb connect localhost:5555 >/dev/null 2>&1 </dev/null
  uid=$(adb -s localhost:5555 shell id -u 2>/dev/null </dev/null | tr -d "\r")
  [ "$uid" = "2000" ] && echo "shell5555=ok" || echo "shell5555=down"
fi
now=$(date +%s)
_age() {
  marker="$1"
  last=$(grep -h "$marker" "$SD/logs/watchdog.log" /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1 | cut -d" " -f1,2)
  if [ -z "$last" ]; then echo missing; return; fi
"""
    + _PORTABLE_AGE_BODY
    + r"""
}
echo "repair_age=$(_age '\[repair\]')"
echo "watchdog_age=$(_age '\[watchdog\]')"
# Native agent (OPTIONS K1): agent.log STATUS + age.
_agent_age() {
  last=$(grep -h '\[agent\] STATUS' "$SD/logs/agent.log" /sdcard/stayturgid/logs/agent.log 2>/dev/null | tail -1 | cut -d" " -f1,2)
  # agent lines are "[agent] STATUS ... ts=YYYY-MM-DD HH:MM:SS" — prefer ts=
  ts=$(grep -h '\[agent\] STATUS' "$SD/logs/agent.log" /sdcard/stayturgid/logs/agent.log 2>/dev/null | tail -1 | sed -n 's/.*ts=\([0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]\).*/\1/p')
  if [ -n "$ts" ]; then last="$ts"; fi
  if [ -z "$last" ]; then echo missing; return; fi
"""
    + _PORTABLE_AGE_BODY
    + r"""
}
echo "agent_age=$(_agent_age)"
# Native agent durable heartbeat (#86): Shizuku/loopback-independent, written
# by HostService.kt's dedicated heartbeat thread regardless of whether the
# Shizuku-bound co-monitor (agent_age, above) is able to run at all. This is
# the authoritative liveness signal — see AGENT_HEARTBEAT_FRESH_SEC.
_agent_heartbeat_age() {
  hb="/sdcard/Download/stayturgid-agent.heartbeat.txt"
  ts=$(grep -oE 'ts_sec=[0-9]+' "$hb" 2>/dev/null | head -1 | cut -d= -f2)
  if [ -z "$ts" ]; then echo missing; return; fi
  echo $(($(date +%s) - ts))
}
echo "agent_heartbeat_age=$(_agent_heartbeat_age)"
if [ -f ~/.stayturgid/state/agent_reboot_candidate ]; then
  echo "agent_reboot_candidate=yes"
else
  echo "agent_reboot_candidate=no"
fi
# Prefer freshest STATUS among watchdog, repair, and native agent.
status=$( {
  grep -h 'STATUS port=' "$SD/logs/watchdog.log" /sdcard/stayturgid/logs/watchdog.log ~/.stayturgid/logs/repair.log 2>/dev/null
  grep -h 'STATUS port=' "$SD/logs/agent.log" /sdcard/stayturgid/logs/agent.log 2>/dev/null
} | tail -1 )
if [ -n "$status" ]; then
  echo "status_line=$status"
  echo "$status" | grep -oE 'port=[^ ]+' || true
  echo "$status" | grep -oE 'shizuku=[^ ]+' || true
  echo "$status" | grep -oE 'a11y=[^ ]+' || echo "a11y=unknown"
else
  echo "a11y=unknown"
  echo "port=unknown"
  echo "shizuku=unknown"
fi
a11y_list=$(adb -s localhost:5555 shell settings get secure enabled_accessibility_services 2>/dev/null </dev/null | tr -d '\r')
if [ -z "$a11y_list" ] || [ "$a11y_list" = "null" ]; then
  a11y_list=$(settings get secure enabled_accessibility_services 2>/dev/null | tr -d '\r')
fi
echo "a11y_list=$a11y_list"
case "$a11y_list" in
  *org.autojs.autojs6/*) echo "autojs6_a11y=ok" ;;
  ""|null) echo "autojs6_a11y=unknown" ;;
  *) echo "autojs6_a11y=missing" ;;
esac
# CFEngine self-heal: scrape last line of its repair log for visibility.
cf_line=$(tail -1 "$HOME/.stayturgid/logs/repair-cfengine.log" 2>/dev/null)
if [ -n "$cf_line" ]; then
  echo "cfengine=ok"  # log exists and has content
  echo "cfengine_last=${cf_line:0:200}"
else
  echo "cfengine=down"
fi
"""
)


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


def _normalize_status_fields(report: dict[str, str]) -> None:
    if "status_line" not in report:
        return
    for field in ("a11y", "port", "shizuku", "tailscale", "tailscale_policy"):
        if field in report:
            continue
        match = re.search(rf"{field}=([^\s]+)", report["status_line"])
        if match:
            report[field] = match.group(1)


def a11y_profile_missing(alias: str, a11y_list: str | None) -> list[str]:
    """Return profile services absent from the live list (empty if unknown)."""
    if not a11y_list or a11y_list in ("null", "unknown", ""):
        return []
    try:
        import a11y_services as a11y
    except ImportError:
        return []
    expected = a11y.profile_services(alias)
    if not expected:
        return []
    live = set(a11y.parse_services(a11y_list))
    return [s for s in expected if s not in live]


def evaluate_health(report: dict[str, str], *, alias: str | None = None) -> list[str]:
    """Return sorted issue tags (empty = healthy / inconclusive-ok)."""
    issues: list[str] = []
    # Structured probe failures (Mac adb missing/timeout) — not device soft state.
    if report.get("probe") in ("adb_missing", "adb_timeout") or report.get("issues") == "probe_error":
        issues.append("probe_error")
    if report.get("ssh_echo") == "fail":
        issues.append("ssh_echo")
    if report.get("sshd") == "down":
        issues.append("sshd_down")
    if report.get("bootloop") == "down":
        issues.append("bootloop_down")
    if report.get("shell5555") == "down":
        issues.append("shell5555_down")

    # agent_missing/agent_stale gate on the durable heartbeat (#86,
    # Shizuku/loopback-independent), not the older agent_age (still reported
    # above for its own diagnostic value — it reflects the Shizuku-bound
    # co-monitor specifically, and stays coupled to Shizuku on purpose).
    hbage = _int_age(report.get("agent_heartbeat_age"))
    if hbage is None:
        issues.append("agent_missing")
    elif hbage >= AGENT_HEARTBEAT_FRESH_SEC:
        issues.append("agent_stale")

    if report.get("agent_reboot_candidate") == "yes":
        issues.append("agent_reboot_candidate")

    rage = _int_age(report.get("repair_age"))
    if report.get("repair_age") == "missing":
        issues.append("repair_missing")
    elif rage is not None and rage >= REPAIR_FRESH_SEC:
        issues.append("repair_stale")

    a11y = report.get("a11y", "")
    if a11y.startswith("FAILED") or a11y == "FAILED":
        issues.append("a11y_failed")

    port = report.get("port", "")
    if port in ("closed", "CLOSED", "CLOSED_NO_SHELL"):
        issues.append("port_closed")

    shizuku = (report.get("shizuku") or "").lower()
    if shizuku in ("down", "dead", "failed", "false", "0"):
        issues.append("shizuku_down")

    if (report.get("tailscale") or "").lower() in ("down", "failed"):
        issues.append("tailscale_down")
    if (report.get("tailscale_policy") or "").lower() in ("down", "failed"):
        issues.append("tailscale_policy_down")

    if alias:
        missing = a11y_profile_missing(alias, report.get("a11y_list"))
        if missing:
            issues.append("a11y_profile_drift")
            report["a11y_missing_n"] = str(len(missing))

    # CFEngine is complementary (not critical). Report down but don't alert.
    if report.get("cfengine") == "down":
        issues.append("cfengine_down")

    return sorted(set(issues))


def summarize(report: dict[str, str], issues: list[str]) -> str:
    bits = [
        "sshd=%s" % report.get("sshd", "?"),
        "bootloop=%s" % report.get("bootloop", "?"),
        "shell5555=%s" % report.get("shell5555", "?"),
        "watchdog_age=%s" % report.get("watchdog_age", "?"),
        "agent_age=%s" % report.get("agent_age", "?"),
        "agent_heartbeat_age=%s" % report.get("agent_heartbeat_age", "?"),
        "repair_age=%s" % report.get("repair_age", "?"),
        "port=%s" % report.get("port", "?"),
        "shizuku=%s" % report.get("shizuku", "?"),
        "tailscale=%s" % report.get("tailscale", "?"),
        "tailscale_policy=%s" % report.get("tailscale_policy", "?"),
        "a11y=%s" % report.get("a11y", "?"),
        "autojs6_a11y=%s" % report.get("autojs6_a11y", "?"),
        "cfengine=%s" % report.get("cfengine", "?"),
    ]
    if report.get("a11y_missing_n"):
        bits.append("a11y_missing_n=%s" % report["a11y_missing_n"])
    if issues:
        bits.append("issues=%s" % ",".join(issues))
    else:
        bits.append("issues=none")
    return " ".join(bits)


def ssh_health(host: str, *, timeout: int = 30) -> dict[str, str]:
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
                "-o",
                "ServerAliveInterval=5",
                "-o",
                "ServerAliveCountMax=3",
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
    _normalize_status_fields(report)
    return report


def adb_health(serial: str, *, timeout: int = 30) -> dict[str, str]:
    """Best-effort Mac-side scrape when SSH is down but adb works (e.g. Fire)."""
    report: dict[str, str] = {"ssh_echo": "skip", "sshd": "unknown", "bootloop": "unknown"}
    script = (
        r"""
now=$(date +%s)
LOGS="/sdcard/stayturgid/logs/watchdog.log /data/data/com.termux/files/home/.stayturgid/shared/logs/watchdog.log /sdcard/stayturgid/logs/agent.log"
age_of() {
  m="$1"
  last=$(grep -hF "$m" $LOGS 2>/dev/null | tail -1 | cut -d" " -f1,2)
  if [ -z "$last" ]; then echo missing; return; fi
"""
        + _PORTABLE_AGE_BODY
        + r"""
}
echo "repair_age=$(age_of '[repair]')"
echo "watchdog_age=$(age_of '[watchdog]')"
# agent.ts= prefer explicit ts= field on [agent] STATUS lines
agent_last=$(grep -h '\[agent\] STATUS' /sdcard/stayturgid/logs/agent.log 2>/dev/null | tail -1)
agent_ts=$(echo "$agent_last" | sed -n 's/.*ts=\([0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]\).*/\1/p')
if [ -n "$agent_ts" ]; then
  last="$agent_ts"
"""
        + r"""
  age=$(python3 -c '
import sys, time
from datetime import datetime
s = sys.argv[1].strip()
for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
    try:
        ts = datetime.strptime(s, fmt).timestamp()
        print(int(time.time() - ts))
        raise SystemExit(0)
    except ValueError:
        pass
print("unknown")
' "$last" 2>/dev/null) || age=unknown
  if [ -z "$age" ]; then age=unknown; fi
  echo "agent_age=$age"
else
  echo "agent_age=missing"
fi
hb_ts=$(grep -oE 'ts_sec=[0-9]+' /sdcard/Download/stayturgid-agent.heartbeat.txt 2>/dev/null | head -1 | cut -d= -f2)
if [ -n "$hb_ts" ]; then
  echo "agent_heartbeat_age=$(($(date +%s) - hb_ts))"
else
  echo "agent_heartbeat_age=missing"
fi
if [ -f /data/data/com.termux/files/home/.stayturgid/state/agent_reboot_candidate ]; then
  echo "agent_reboot_candidate=yes"
else
  echo "agent_reboot_candidate=no"
fi
list=$(settings get secure enabled_accessibility_services 2>/dev/null | tr -d '\r')
echo "a11y_list=$list"
case "$list" in
  *org.autojs.autojs6/*) echo "autojs6_a11y=ok" ;;
  ""|null) echo "autojs6_a11y=unknown" ;;
  *) echo "autojs6_a11y=missing" ;;
esac
st=$(grep -h 'STATUS port=' $LOGS 2>/dev/null | tail -1)
echo "status_line=$st"
echo "$st" | grep -oE 'port=[^ ]+' || echo "port=unknown"
echo "$st" | grep -oE 'shizuku=[^ ]+' || echo "shizuku=unknown"
echo "$st" | grep -oE 'a11y=[^ ]+' || echo "a11y=unknown"
echo "shell5555=skip"
echo "bootloop=unknown"
"""
    )
    try:
        r = subprocess.run(
            [ADB, "-s", serial, "shell", "sh", "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        report.update(parse_kv(r.stdout or ""))
        _normalize_status_fields(report)
    except FileNotFoundError:
        report["probe"] = "adb_missing"
        report["issues"] = "probe_error"
    except (OSError, subprocess.TimeoutExpired):
        report["probe"] = "adb_timeout"
        report["issues"] = "probe_error"
    return report


def tcp_open(host: str, port: int, timeout: float = 5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def adb_reachable(addrs: list[str]) -> str | None:
    try:
        listed = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        listed = ""
    for addr in addrs:
        if "%s\tdevice" % addr in listed:
            return "adb:%s" % addr
        try:
            out = subprocess.run([ADB, "connect", addr], capture_output=True, text=True, timeout=15).stdout
            if "connected to" in out:
                return "adb:%s" % addr
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def resolve_path(name: str, ts_ip: str, lan_ip: str) -> str | None:
    addrs: list[str] = []
    if lan_ip and lan_ip != "-":
        addrs.append("%s:5555" % lan_ip)
    if ts_ip and ts_ip != "-":
        addrs.append("%s:5555" % ts_ip)
    ok = adb_reachable(addrs)
    if ok:
        return ok
    if ts_ip and ts_ip != "-" and tcp_open(ts_ip, SSH_PORT):
        return "ssh:%s" % ts_ip
    return None


def probe_via_path(ok_path: str, name: str) -> dict[str, Any]:
    """ok_path is 'adb:<serial_or_addr>' or 'ssh:<host_or_ip>'."""
    if ok_path.startswith("ssh:"):
        report = ssh_health(name)
        if report.get("ssh_echo") == "fail":
            return {"ssh_echo": "fail", "sshd": report.get("sshd", "unknown")}
        return report
    if ok_path.startswith("adb:"):
        serial = ok_path.split(":", 1)[1]
        report = ssh_health(name)
        if report.get("ssh_echo") != "fail":
            return report
        return adb_health(serial)
    return {"ssh_echo": "skip", "probe": "unknown_path"}


def probe_device(name: str, ts_ip: str, lan_ip: str) -> tuple[str | None, dict[str, Any]]:
    """Resolve path + scrape. Returns (path_or_None, report)."""
    path = resolve_path(name, ts_ip, lan_ip)
    if not path:
        return None, {"reachable": "no"}
    report = probe_via_path(path, name)
    report["reachable"] = "yes"
    report["via"] = path
    return path, report
