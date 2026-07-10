#!/usr/bin/env python3
"""Dedicated Mac fleet soft-health monitor (launchd every 5 min).

Scrapes watchdog/repair/a11y/sshd/bootloop/shell5555 when a device is
reachable. Logs to ~/.config/stayturgid/logs/fleet-health.log and notifies
after CONSECUTIVE_LIMIT consecutive soft failures (~10 min).

When ``watchdog_stale`` / ``watchdog_missing`` persists, restarts AutoJs6
``main.js`` via ``control/tools/autojs6/start_watchdog.py`` (rate-limited) so agents do
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

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LIB = os.path.join(_REPO, "control", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import fleet_health as fh  # noqa: E402
import hd8_google_stack as hgs  # noqa: E402
import stayturgid_device as dev  # noqa: E402
import vlm_helpers as vh  # noqa: E402

ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
CONF = os.environ.get("STAYTURGID_DEVICES_CONF", os.path.join(ROOT, "devices.conf"))
STATE_DIR = os.path.join(ROOT, "state", "fleet-health")
HEAL_STATE_DIR = os.path.join(ROOT, "state", "watchdog-heal")
GOOGLE_HEAL_STATE_DIR = os.path.join(ROOT, "state", "google-stack-heal")
GOOGLE_VERIFY_STATE_DIR = os.path.join(ROOT, "state", "google-stack-verify")
LOG = os.path.join(ROOT, "logs", "fleet-health.log")
CONSECUTIVE_LIMIT = 2
# After this many soft fails with watchdog_stale/missing, restart main.js once.
WATCHDOG_HEAL_AFTER = 2
WATCHDOG_HEAL_COOLDOWN_SEC = 30 * 60
GOOGLE_STACK_HEAL_COOLDOWN_SEC = 24 * 60 * 60
GOOGLE_VERIFY_COOLDOWN_SEC = 6 * 60 * 60
SKIP_HEALTH = os.environ.get("STAYTURGID_SKIP_HEALTH") == "1"
SKIP_WATCHDOG_HEAL = os.environ.get("STAYTURGID_SKIP_WATCHDOG_HEAL") == "1"
SKIP_GOOGLE_STACK_HEAL = os.environ.get("STAYTURGID_SKIP_GOOGLE_STACK_HEAL") == "1"
MAX_LOG_LINES = 2000
REPO = _REPO


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


def _heal_cooldown_ok_dir(name: str, state_dir: str, cooldown_sec: int) -> bool:
    path = os.path.join(state_dir, name)
    try:
        age = datetime.datetime.now().timestamp() - os.path.getmtime(path)
        return age >= cooldown_sec
    except OSError:
        return True


def _touch_heal_dir(name: str, state_dir: str) -> None:
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, name), "w") as f:
            f.write(str(int(datetime.datetime.now().timestamp())))
    except OSError:
        pass


def _heal_cooldown_ok(name: str) -> bool:
    return _heal_cooldown_ok_dir(name, HEAL_STATE_DIR, WATCHDOG_HEAL_COOLDOWN_SEC)


def _touch_heal(name: str) -> None:
    _touch_heal_dir(name, HEAL_STATE_DIR)


def maybe_heal_watchdog(
    name: str, issues: list[str], fails: int, adb_serial: str | None = None
) -> None:
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
    script = os.path.join(REPO, "control", "tools", "autojs6", "start_watchdog.py")
    if not os.path.isfile(script):
        log("%s watchdog heal skipped (missing %s)" % (name, script))
        return
    log("%s watchdog heal: starting main.js via start_watchdog.py" % name)
    cmd = [sys.executable, script, name]
    if adb_serial:
        cmd.append(adb_serial)
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        detail = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " | ")
        log(
            "%s watchdog heal rc=%s %s"
            % (name, r.returncode, detail[:300])
        )
        if r.returncode == 0:
            _touch_heal(name)
            notify(
                "stayturgid heal",
                "%s AutoJs6 watchdog restarted" % name,
            )
    except (OSError, subprocess.TimeoutExpired) as e:
        log("%s watchdog heal error: %s" % (name, e))


def maybe_heal_hd8_google_stack(name: str) -> None:
    """Pin sideloaded GMS when Play Store auto-updated past Fire-compatible builds."""
    if SKIP_HEALTH or SKIP_GOOGLE_STACK_HEAL or name != "hd8":
        return
    if not _heal_cooldown_ok_dir(
        name, GOOGLE_HEAL_STATE_DIR, GOOGLE_STACK_HEAL_COOLDOWN_SEC
    ):
        return

    def _run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode, r.stdout or "", r.stderr or ""

    # Entire heal path must never abort soft-health scrape (adb/PATH issues).
    try:
        serial = dev.resolve_adb(name)
        gms_ver = hgs.package_version_code(_run, serial, hgs.GMS_PKG)
        gsf_ver = hgs.package_version_name(_run, serial, hgs.GSF_PKG)
        if not hgs.needs_gms_downgrade(gms_ver) and not hgs.needs_gsf_reinstall(gsf_ver):
            hgs.ensure_doze_whitelist(_run, serial)
            return
        if hgs.needs_gsf_reinstall(gsf_ver) and not hgs.needs_gms_downgrade(gms_ver):
            log(
                "%s google-stack heal: GSF %s — reinstalling pinned 10-6494331"
                % (name, gsf_ver)
            )
        else:
            log(
                "%s google-stack heal: GMS versionCode=%s > %s — pinning Fire-Tools stack"
                % (name, gms_ver, hgs.MAX_GMS_VERSION_CODE)
            )
        result = hgs.repair_if_needed(_run, serial)
        _touch_heal_dir(name, GOOGLE_HEAL_STATE_DIR)
        new_ver = result.get("gms_version")
        log("%s google-stack heal done gms versionCode=%s" % (name, new_ver))
        if hgs.needs_gms_downgrade(new_ver):
            notify(
                "stayturgid heal",
                "%s GMS still too new (%s) — run make fix-hd8-google"
                % (name, new_ver),
                sound="Basso",
            )
        else:
            notify(
                "stayturgid heal",
                "%s Google Play Services pinned (%s)" % (name, new_ver),
            )
            maybe_verify_hd8_google_closeout(name)
    except Exception as e:  # noqa: BLE001
        log("%s google-stack heal skipped: %s" % (name, e))


def maybe_verify_hd8_google_closeout(name: str) -> None:
    """Rate-limited VLM verify after stack heal (auto-update + crash dialog)."""
    if SKIP_HEALTH or name != "hd8" or not vh.auto_verify_enabled():
        return
    if not _heal_cooldown_ok_dir(name, GOOGLE_VERIFY_STATE_DIR, GOOGLE_VERIFY_COOLDOWN_SEC):
        return
    script = os.path.join(REPO, "control", "bin", "verify_hd8_google.py")
    if not os.path.isfile(script):
        return
    log("%s google-stack VLM close-out (verify_hd8_google)" % name)
    env = os.environ.copy()
    env.setdefault("STAYTURGID_VLM", "1")
    try:
        r = subprocess.run(
            [sys.executable, script, name],
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        detail = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " | ")
        log("%s google-stack VLM verify rc=%s %s" % (name, r.returncode, detail[:400]))
        _touch_heal_dir(name, GOOGLE_VERIFY_STATE_DIR)
        if r.returncode != 0:
            notify(
                "stayturgid heal",
                "%s Google stack VLM check failed — see fleet-health.log" % name,
                sound="Basso",
            )
    except (OSError, subprocess.TimeoutExpired) as e:
        log("%s google-stack VLM verify error: %s" % (name, e))


def check_device(name: str, ts_ip: str, lan_ip: str) -> None:
    state_file = os.path.join(STATE_DIR, name)
    path, report = fh.probe_device(name, ts_ip, lan_ip)
    if not path:
        log("%s unreachable — skip soft health (see access-monitor)" % name)
        return

    maybe_heal_hd8_google_stack(name)

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
    adb_serial = path.split(":", 1)[1] if path and path.startswith("adb:") else None
    maybe_heal_watchdog(name, issues, fails, adb_serial=adb_serial)
    if fails == CONSECUTIVE_LIMIT:
        detail = ",".join(issues)
        if len(detail) > 180:
            detail = detail[:177] + "..."
        notify("stayturgid health", "%s: %s" % (name, detail), sound="Basso")


ET_MAC_HEAL_STATE = os.path.join(ROOT, "state", "et-mac-ensure")
ET_MAC_HEAL_COOLDOWN_SEC = 30 * 60  # re-sync fleet keys on Mac at most 2×/hour


def maybe_ensure_et_mac() -> None:
    """Idempotent phone→Mac ET authorized_keys reconcile (marked block).

    Collects fleet pubs when hosts are up and rewrites STAYTURGID-ET-MAC.
    Does not touch peer-help ForceCommand lines. Rate-limited.
    """
    if SKIP_HEALTH or os.environ.get("STAYTURGID_SKIP_ET_MAC") == "1":
        return
    stamp = os.path.join(ET_MAC_HEAL_STATE, "last")
    try:
        age = datetime.datetime.now().timestamp() - os.path.getmtime(stamp)
        if age < ET_MAC_HEAL_COOLDOWN_SEC:
            return
    except OSError:
        pass
    script = os.path.join(REPO, "control", "bin", "ensure_et_mac.py")
    if not os.path.isfile(script):
        return
    try:
        r = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                "PATH": "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", ""),
            },
        )
        detail = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " | ")
        log("et-mac ensure rc=%s %s" % (r.returncode, detail[:400]))
        try:
            os.makedirs(ET_MAC_HEAL_STATE, exist_ok=True)
            with open(stamp, "w") as f:
                f.write(str(int(datetime.datetime.now().timestamp())))
        except OSError:
            pass
    except (OSError, subprocess.TimeoutExpired) as e:
        log("et-mac ensure error: %s" % e)


def main() -> int:
    if SKIP_HEALTH:
        return 0
    if not os.path.exists(CONF):
        return 0
    os.makedirs(STATE_DIR, exist_ok=True)
    trim_log()
    maybe_ensure_et_mac()
    for name, ts_ip, lan_ip in read_devices(CONF):
        try:
            check_device(name, ts_ip, lan_ip)
        except Exception as e:  # noqa: BLE001
            # Structured line so check_fleet_health can triage (not only SCRAPE_STALE).
            log(
                "%s via none: sshd=unknown issues=probe_error probe_error=%s"
                % (name, str(e).replace(" ", "_")[:120])
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
