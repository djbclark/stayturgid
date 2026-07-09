#!/usr/bin/env python3
"""Dedicated Mac fleet soft-health monitor (launchd every 5 min).

Scrapes watchdog/repair/a11y/sshd/bootloop/shell5555 when a device is
reachable. Logs to ~/.config/stayturgid/logs/fleet-health.log and notifies
after CONSECUTIVE_LIMIT consecutive soft failures (~10 min).

When ``watchdog_stale`` / ``watchdog_missing`` persists, restarts AutoJs6
``main.js`` via ``autojs6/mac/start_watchdog.py`` (rate-limited) so agents do
not need a manual heal.

Reachability-only outages stay in access_monitor.py (separate agent).
Disable with STAYTURGID_SKIP_HEALTH=1; skip restarts with
STAYTURGID_SKIP_WATCHDOG_HEAL=1.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHARED_MAC = os.path.join(_REPO, "shared", "mac")
if _SHARED_MAC not in sys.path:
    sys.path.insert(0, _SHARED_MAC)
import fleet_health as fh  # noqa: E402

ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
CONF = os.environ.get("STAYTURGID_DEVICES_CONF", os.path.join(ROOT, "devices.conf"))
STATE_DIR = os.path.join(ROOT, "state", "fleet-health")
HEAL_STATE_DIR = os.path.join(ROOT, "state", "watchdog-heal")
LOG = os.path.join(ROOT, "logs", "fleet-health.log")
CONSECUTIVE_LIMIT = 2
# After this many soft fails with watchdog_stale/missing, restart main.js once.
WATCHDOG_HEAL_AFTER = 2
WATCHDOG_HEAL_COOLDOWN_SEC = 30 * 60
SKIP_HEALTH = os.environ.get("STAYTURGID_SKIP_HEALTH") == "1"
SKIP_WATCHDOG_HEAL = os.environ.get("STAYTURGID_SKIP_WATCHDOG_HEAL") == "1"
MAX_LOG_LINES = 2000
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ts() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure(path: str) -> str:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except OSError:
        pass
    return path


def log(msg: str) -> None:
    try:
        with open(_ensure(LOG), "a") as f:
            f.write("%s  %s\n" % (ts(), msg))
    except OSError:
        pass


def trim_log(max_lines: int = MAX_LOG_LINES) -> None:
    try:
        with open(LOG) as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(LOG, "w") as f:
                f.writelines(lines[-max_lines:])
    except OSError:
        pass


def notify(title: str, message: str, sound: str | None = None) -> None:
    # Escape quotes for AppleScript.
    message = message.replace("\\", "\\\\").replace('"', '\\"')
    title = title.replace("\\", "\\\\").replace('"', '\\"')
    script = 'display notification "%s" with title "%s"' % (message, title)
    if sound:
        script += ' sound name "%s"' % sound
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def read_devices(conf_path: str):
    try:
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    name, _usb, ts_ip = parts[0], parts[1], parts[2]
                    lan = parts[3] if len(parts) > 3 else "-"
                    yield name, ts_ip, lan
    except OSError:
        return


def read_state(state_file: str) -> int:
    try:
        with open(state_file) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def write_state(state_file: str, n: int) -> None:
    try:
        with open(state_file, "w") as f:
            f.write(str(n))
    except OSError:
        pass


def _heal_stamp(name: str) -> str:
    return os.path.join(HEAL_STATE_DIR, name)


def _heal_cooldown_ok(name: str) -> bool:
    path = _heal_stamp(name)
    try:
        age = datetime.datetime.now().timestamp() - os.path.getmtime(path)
        return age >= WATCHDOG_HEAL_COOLDOWN_SEC
    except OSError:
        return True


def _touch_heal(name: str) -> None:
    try:
        os.makedirs(HEAL_STATE_DIR, exist_ok=True)
        with open(_heal_stamp(name), "w") as f:
            f.write(str(int(datetime.datetime.now().timestamp())))
    except OSError:
        pass


def maybe_heal_watchdog(name: str, issues: list[str], fails: int) -> None:
    """Restart AutoJs6 main.js when soft health shows a dead watchdog.

    Manual start_watchdog.py was required previously — that is not self-heal.
    Mac already has adb; Termux boot loop deliberately avoids RunIntentActivity
    (foreground steal). Rate-limited to once per WATCHDOG_HEAL_COOLDOWN_SEC.
    """
    if SKIP_WATCHDOG_HEAL or SKIP_HEALTH:
        return
    if fails < WATCHDOG_HEAL_AFTER:
        return
    if "watchdog_stale" not in issues and "watchdog_missing" not in issues:
        return
    if not _heal_cooldown_ok(name):
        log("%s watchdog heal skipped (cooldown)" % name)
        return
    script = os.path.join(REPO, "autojs6", "mac", "start_watchdog.py")
    if not os.path.isfile(script):
        log("%s watchdog heal skipped (missing %s)" % (name, script))
        return
    log("%s watchdog heal: starting main.js via start_watchdog.py" % name)
    try:
        r = subprocess.run(
            [sys.executable, script, name],
            capture_output=True,
            text=True,
            timeout=60,
        )
        detail = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " | ")
        log(
            "%s watchdog heal rc=%s %s"
            % (name, r.returncode, detail[:300])
        )
        _touch_heal(name)
        if r.returncode == 0:
            notify(
                "stayturgid heal",
                "%s AutoJs6 watchdog restarted" % name,
            )
    except (OSError, subprocess.TimeoutExpired) as e:
        log("%s watchdog heal error: %s" % (name, e))


def check_device(name: str, ts_ip: str, lan_ip: str) -> None:
    state_file = os.path.join(STATE_DIR, name)
    path, report = fh.probe_device(name, ts_ip, lan_ip)
    if not path:
        log("%s unreachable — skip soft health (see access-monitor)" % name)
        return

    issues = fh.evaluate_health(report, alias=name)
    summary = fh.summarize(report, issues)
    log("%s via %s: %s" % (name, path, summary))

    fails = read_state(state_file)
    if not issues:
        if fails >= CONSECUTIVE_LIMIT:
            log("%s health RECOVERED" % name)
            notify("stayturgid health", "%s soft checks OK again" % name)
        write_state(state_file, 0)
        return

    fails += 1
    write_state(state_file, fails)
    maybe_heal_watchdog(name, issues, fails)
    if fails == CONSECUTIVE_LIMIT:
        detail = ",".join(issues)
        if len(detail) > 180:
            detail = detail[:177] + "..."
        notify("stayturgid health", "%s: %s" % (name, detail), sound="Basso")


def main() -> int:
    if SKIP_HEALTH:
        return 0
    if not os.path.exists(CONF):
        return 0
    os.makedirs(STATE_DIR, exist_ok=True)
    trim_log()
    for name, ts_ip, lan_ip in read_devices(CONF):
        try:
            check_device(name, ts_ip, lan_ip)
        except Exception as e:  # noqa: BLE001
            log("%s probe error: %s" % (name, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
