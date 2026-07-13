#!/data/data/com.termux/files/usr/bin/python
"""stayturgid-repair.py — Termux-side self-heal (deployed as ~/stayturgid_repair.py,
reached via the ~/stayturgid_repair.py compat shim).

Unit-tested via tests/test-unit.sh (repair_suite). The ~/stayturgid_repair.py
shim keeps AutoJs6 RUN_COMMAND / boot-loop / repair-bridge callers unchanged.

Uses Shizuku's shell-privileged adbd on localhost:5555 (uid 2000) for
privileged checks/repairs. Exit 0 = healthy after repair; 1 = a subsystem
still down (needs AutoJs6 UI repair or reboot). Prints one STATUS line.
"""
import datetime
import fcntl
import json
import os
import subprocess
import sys
import time

PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
TMPDIR = os.environ.get("TMPDIR", PREFIX + "/tmp")
os.environ["PATH"] = PREFIX + "/bin:" + PREFIX + "/sbin:" + os.environ.get("PATH", "")
os.environ["LC_ALL"] = "C"

# All stayturgid files live under one root per filesystem (self-healing: every
# writer mkdir -p's its dir, so a user-deleted dir just gets recreated).
STG = os.path.join(HOME, ".stayturgid")             # Termux-private root
_ENV_FILE = os.path.join(STG, "env")
if os.path.isfile(_ENV_FILE):
    try:
        with open(_ENV_FILE) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line.startswith("export STAYTURGID_SD="):
                    os.environ["STAYTURGID_SD"] = _line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")  # shared-storage root


def ensure_parent(path):
    """mkdir -p the parent dir so a deleted stayturgid dir self-heals."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except OSError:
        pass
    return path


LOCKFILE = os.path.join(TMPDIR, "stayturgid-repair.lock")
LOG = os.path.join(STG, "logs", "repair.log")
SDLOG = os.path.join(SD, "logs", "watchdog.log")
# AutoJs6 always reads /sdcard/stayturgid/logs (cannot write Termux-private
# paths on Fire). Dual-write STATUS there so the JS co-monitor can see Termux
# freshness even when STAYTURGID_SD is ~/.stayturgid/shared.
SDCARD_WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"
A11Y_SVC = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"
A11Y_BACKUP = os.path.join(SD, "state", "a11y_services_backup.txt")


def _parse_a11y_list(raw):
    text = (raw or "").strip()
    if text in ("", "null"):
        return []
    out, seen = [], set()
    for part in text.split(":"):
        svc = part.strip()
        if svc and svc not in seen:
            seen.add(svc)
            out.append(svc)
    return out


def _a11y_value_safe(value):
    """Return an adb-safe quoted value for enabled_accessibility_services.

    Avoids single-quote injection in shell commands. adb 'shell' passes the
    argument string to /system/bin/sh, so we use shlex.quote for any dynamic
    value.
    """
    import shlex
    return shlex.quote(value)


def _merge_a11y_list(current, add):
    merged = _parse_a11y_list(current)
    seen = set(merged)
    for svc in add:
        if svc and svc not in seen:
            seen.add(svc)
            merged.append(svc)
    return ":".join(merged)


def _a11y_lost(before, after):
    return [s for s in _parse_a11y_list(before) if s not in set(_parse_a11y_list(after))]


def _backup_a11y_list(value):
    ensure_parent(A11Y_BACKUP)
    try:
        with open(A11Y_BACKUP, "w") as f:
            f.write((value or "").strip() + "\n")
    except OSError:
        pass


def _read_a11y_backup():
    try:
        with open(A11Y_BACKUP) as f:
            return f.read().strip()
    except OSError:
        return ""


def _repair_a11y_shrink(before, after):
    lost = _a11y_lost(before, after)
    if not lost:
        return ""
    backup = _read_a11y_backup()
    return _merge_a11y_list(_merge_a11y_list(before, _parse_a11y_list(backup)), [A11Y_SVC])


def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    line = "%s [repair] %s" % (ts(), msg)
    paths = [LOG, SDLOG]
    if os.path.normpath(SDLOG) != os.path.normpath(SDCARD_WATCHDOG_LOG):
        paths.append(SDCARD_WATCHDOG_LOG)
    for path in paths:
        try:
            with open(ensure_parent(path), "a") as f:
                f.write(line + "\n")
        except OSError:
            pass


def trim_log(path, keep=500, over=1000):
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) > over:
        lock_path = path + ".lock"
        try:
            with open(lock_path, "a") as lock_fd:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                try:
                    with open(path, "w") as f:
                        f.writelines(lines[-keep:])
                finally:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass


def run(args, timeout=15):
    """Run a command via the sandbox/real PATH; return (rc, stdout)."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except OSError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""


def sh_adb(cmd, timeout=15):
    """adb -s localhost:5555 shell <cmd> — cmd is one string, matching $SH "...".
    Returns (rc, stdout without CR)."""
    rc, out = run(["adb", "-s", "localhost:5555", "shell", cmd], timeout=timeout)
    return rc, out.replace("\r", "")


def sshd_listening():
    rc, out = run(["ss", "-tln"])
    if rc == 0 and ":8022 " in out:
        return True
    rc, out = run(["netstat", "-tln"])
    return rc == 0 and ":8022 " in out


def sshd_up():
    if run(["pgrep", "-x", "sshd"])[0] == 0:
        return True
    if run(["pgrep", "-f", "[s]shd"])[0] == 0:
        return True
    return sshd_listening()


def privileged_shell():
    """Return True if localhost:5555 gives a uid-2000 shell."""
    if run(["adb", "connect", "localhost:5555"])[0] != 0:
        return False
    _rc, out = sh_adb("id -u")
    return out.strip() == "2000"


def read_device_profile():
    for path in (
        os.path.join(SD, "state", "device.json"),
        os.path.join(STG, "state", "device.json"),
    ):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def privileged_shell_expected():
    """Fire OS and split-storage hosts use Mac adb, not Termux loopback 5555."""
    prof = read_device_profile()
    if prof.get("privilegedShellExpected") is False:
        return False
    if prof.get("privilegedShellExpected") is True:
        return True
    if SD.startswith(HOME) or "/com.termux/" in SD:
        return False
    return True


def ensure_wireless_debugging():
    """Proactively enable the Developer-options wireless-debugging toggle.

    Called on every boot cycle *before* the privileged-shell probe so that
    a disabled toggle is caught and repaired even when 5555 was temporarily
    down.  Returns one of: 'up', 'repaired', 'FAILED', 'NO_SHELL'.
    """
    # Try the settings check; if ADB is unreachable, attempt reconnect first.
    _rc, raw = sh_adb("settings get global adb_wifi_enabled")
    wifi = raw.strip()
    if wifi in ("null", ""):
        # ADB likely disconnected — reconnect and retry.
        run(["adb", "connect", "localhost:5555"])
        time.sleep(1)
        _rc, raw = sh_adb("settings get global adb_wifi_enabled")
        wifi = raw.strip()
    if wifi in ("1", "true"):
        return "up"
    if wifi in ("null", ""):
        log("wireless debugging: cannot reach shell (adb_wifi_enabled=%s)" % wifi)
        return "NO_SHELL"
    # Port is open and shell works — wireless debugging is functionally up.
    # On both Samsung (cosmetic toggle=0) and Pixel (settings put blocked on
    # Android 16), the toggle value is irrelevant when 5555 responds.
    if _rc == 0:
        return "up"
    # Toggle reads 0 but shell responded — cosmetic false on Samsung/
    # some OneUI where adb_wifi_enabled is disconnected from the actual
    # Shizuku-opened port.  Don't touch the toggle.
    # Toggle is off — try to enable via settings put.
    sh_adb("settings put global adb_wifi_enabled 1")
    time.sleep(2)
    wifi2 = sh_adb("settings get global adb_wifi_enabled")[1].strip()
    if wifi2 in ("1", "true"):
        log("wireless debugging was off -> re-enabled adb_wifi_enabled")
        return "repaired"
    log("wireless debugging re-enable FAILED (adb_wifi_enabled=%s)" % wifi2)
    return "FAILED"


def duplicate_branch():
    """Another invocation holds the lock: read-only advisory probe, exit 0."""
    sshd = "up" if (sshd_up() or sshd_listening()) else "unknown"
    # Match main() STATUS schema (a11y=, et_cfg=) so parsers stay consistent.
    if not privileged_shell_expected():
        port, sh, shizuku, a11y, wifi = "skip", False, "skip", "skip", "skip"
    elif privileged_shell():
        port, sh = "open", True
        _, shizuku_out = sh_adb("am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS 2>/dev/null")
        if "result=1" in shizuku_out:
            shizuku = "up"
        else:
            rc, _ = sh_adb("pgrep -f shizuku_server")
            shizuku = "up" if rc == 0 else "down"
        wifi = (
            "up"
            if sh_adb("settings get global adb_wifi_enabled")[1].strip()
            in ("1", "true")
            else "down"
        )
        before = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
        a11y = "up" if A11Y_SVC in before else "down"
    else:
        port, sh, shizuku, a11y, wifi = (
            "CLOSED_NO_SHELL",
            False,
            "unknown",
            "unknown",
            "unknown",
        )
    # Contention path never mutates SSH config; report presence only.
    share = os.path.join(STG, "share", "ssh-config-control-et")
    if not os.path.isfile(share):
        et_cfg = "skip"
    else:
        conf = os.path.join(HOME, ".ssh", "config")
        existing = ""
        try:
            if os.path.isfile(conf):
                with open(conf) as f:
                    existing = f.read()
        except OSError:
            existing = ""
        et_cfg = (
            "up"
            if "STAYTURGID-CONTROL-ET" in existing and "IdentityFile" in existing
            else "down"
        )
    status = (
        "STATUS port=%s shizuku=%s sshd=%s a11y=%s shell=%s wifi=%s et_cfg=%s os_release=skip auto_profile=skip shizuku_profile=skip device_profile=skip env=skip"
        % (port, shizuku, sshd, a11y, "yes" if sh else "no", wifi, et_cfg)
    )
    log(status + " rc=0 (skipped-duplicate)")
    print(status)
    return 0


def acquire_lock():
    """Non-blocking exclusive lock. FLOCK_RC=1 is a test seam for the
    contention path (macOS test host has no flock(1)); real runs use fcntl."""
    if os.environ.get("FLOCK_RC") == "1":
        return None
    fd = None
    try:
        os.makedirs(os.path.dirname(LOCKFILE), exist_ok=True)
        fd = open(LOCKFILE, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except (OSError, IOError):
        if fd is not None:
            fd.close()
        return None


MAC_PATH_KEYWORDS = ("/Users/", "/opt/homebrew/", "/Library/Apple/",
                     "/System/Cryptexes/")

PROFILES = [".profile", ".bashrc", ".bash_profile"]


CANONICAL_MIRROR = "https://packages-cf.termux.dev/apt/termux-main"
SSHD_SERVICE_DIR = PREFIX + "/var/service/sshd"


def ensure_sshd_down_file():
    """Remove a stale runsv ``down`` file that silently blocks sshd.

    The file is set by ``sv down sshd`` or manual troubleshooting.  When
    present, runsv refuses to start sshd even after a reboot.  Returns
    ``repaired`` when removed, ``up`` when clean.
    """
    down = os.path.join(SSHD_SERVICE_DIR, "down")
    if not os.path.isfile(down):
        return "up"
    try:
        os.unlink(down)
        log("removed stale sshd down file -> runsv can start sshd")
        return "repaired"
    except OSError:
        return "FAILED"


def ensure_shell_profile_path():
    """Remove Mac-style PATH lines from Termux shell profiles.

    A leaked Mac PATH replaces the Termux prefix, breaking pkg/apt and
    every Termux binary.  Returns 'repaired' when a line was fixed,
    'up' when clean, 'skip' when nothing to check.
    """
    fixed = 0
    for rel in PROFILES:
        path = os.path.join(HOME, rel)
        try:
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            continue
        new = []
        changed = False
        for line in lines:
            stripped = line.strip()
            if (stripped.startswith("export PATH=") or stripped.startswith("PATH=")) \
                    and any(kw in stripped for kw in MAC_PATH_KEYWORDS):
                new.append('export PATH="$HOME/bin:%s/bin:%s/sbin:$PATH"\n'
                           % (PREFIX, PREFIX))
                changed = True
            else:
                new.append(line)
        if changed:
            try:
                with open(path, "w") as f:
                    f.writelines(new)
                os.chmod(path, 0o644)
                fixed += 1
                log("shell profile %s PATH was broken (Mac paths) -> repaired" % path)
            except OSError:
                pass
    if fixed:
        return "repaired"
    if any(os.path.isfile(os.path.join(HOME, r)) for r in PROFILES):
        return "up"
    return "skip"


def ensure_termux_mirror():
    """Re-pin the Termux mirror after a random mirror change by pkg update.

    pkg update selects a random mirror and rewrites sources.list.  The
    canonical CDN (packages-cf.termux.dev) is the most reliable.
    Returns 'repaired' when the mirror was changed, 'up' when already
    correct, 'FAILED' when unwritable.
    """
    sources = os.path.join(PREFIX, "etc", "apt", "sources.list")
    expected = "deb %s stable main\n" % CANONICAL_MIRROR
    try:
        if os.path.isfile(sources):
            with open(sources) as f:
                current = f.read()
            if current == expected:
                return "up"
        else:
            current = ""
    except OSError:
        return "FAILED"
    try:
        os.makedirs(os.path.dirname(sources), exist_ok=True)
        with open(sources, "w") as f:
            f.write(expected)
        run(["apt-get", "update", "-y"], timeout=30)
        log("Termux mirror re-pinned from %s -> %s" % (
            current.strip().split()[1] if len(current.split()) > 1 else "absent",
            CANONICAL_MIRROR))
        return "repaired"
    except OSError:
        return "FAILED"


def ensure_control_et_ssh_config():
    """Restore phone→Mac ET Host block from deploy share if markers missing.

    Deploy plants ~/.stayturgid/share/ssh-config-control-et. Cheap no-op when
    inventory never shipped the fragment.
    """
    share = os.path.join(STG, "share", "ssh-config-control-et")
    conf = os.path.join(HOME, ".ssh", "config")
    if not os.path.isfile(share):
        return "skip"
    try:
        with open(share) as f:
            fragment = f.read().strip()
    except OSError:
        return "skip"
    if not fragment or "Host " not in fragment:
        return "skip"
    # Ansible blockinfile marker "# {mark} STAYTURGID-CONTROL-ET"
    alt_begin = "# BEGIN STAYTURGID-CONTROL-ET"
    alt_end = "# END STAYTURGID-CONTROL-ET"
    try:
        existing = ""
        if os.path.isfile(conf):
            with open(conf) as f:
                existing = f.read()
    except OSError:
        existing = ""
    if "STAYTURGID-CONTROL-ET" in existing and "IdentityFile" in existing:
        return "up"
    block = "%s\n%s\n%s\n" % (alt_begin, fragment, alt_end)
    try:
        os.makedirs(os.path.dirname(conf), exist_ok=True)
        if existing and not existing.endswith("\n"):
            existing += "\n"
        # Drop a stale partial Host mac without our markers
        with open(conf, "w") as f:
            f.write(existing)
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(block)
        os.chmod(conf, 0o600)
        log("control-ET ssh config restored from share")
        return "repaired"
    except OSError as e:
        log("control-ET ssh config restore FAILED: %s" % e)
        return "FAILED"


OS_RELEASE_PATH = os.path.join(PREFIX, "etc", "os-release")
OS_RELEASE_CONTENT = (
    'NAME="Termux"\n'
    'ID=termux\n'
    'ID_LIKE=android\n'
    'PRETTY_NAME="Termux (Android)"\n'
    'VERSION_ID="1"\n'
    'HOME_URL="https://termux.dev/"\n'
)


def ensure_os_release():
    """Re-create /etc/os-release if missing (needed by CFEngine platform detection)."""
    try:
        with open(OS_RELEASE_PATH) as f:
            if f.read().strip():
                return "present"
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(OS_RELEASE_PATH), exist_ok=True)
        with open(OS_RELEASE_PATH, "w") as f:
            f.write(OS_RELEASE_CONTENT)
        os.chmod(OS_RELEASE_PATH, 0o644)
        log("os-release was missing — re-created")
        return "repaired"
    except OSError as e:
        log("os-release re-create FAILED: %s" % e)
        return "FAILED"


def main():
    try:
        os.makedirs(TMPDIR, exist_ok=True)
    except OSError:
        pass

    lock = acquire_lock()
    if lock is None:
        return duplicate_branch()

    trim_log(LOG)
    trim_log(SDLOG)
    if os.path.normpath(SDLOG) != os.path.normpath(SDCARD_WATCHDOG_LOG):
        trim_log(SDCARD_WATCHDOG_LOG)
    rc = 0

    # --- 1. sshd ---
    sshd_down = ensure_sshd_down_file()
    if sshd_up():
        sshd = "up"
    else:
        if not sshd_listening():
            run(["sshd"])
        time.sleep(2)
        if sshd_up():
            sshd = "restarted"
            log("sshd was down -> restarted")
        else:
            sshd = "FAILED"
            rc = 1
            log("sshd restart FAILED")

    # --- 2. privileged shell via Shizuku's adbd on localhost:5555 ---
    expect_shell = privileged_shell_expected()
    # Proactively enable wireless debugging *before* the privileged-shell
    # probe so a disabled toggle is caught and repaired even when 5555 was
    # temporarily down.  On Fire OS this will return NO_SHELL (Mac must
    # re-enable), but on Samsung/Pixel it self-heals immediately.
    if expect_shell:
        wifi = ensure_wireless_debugging()
    else:
        wifi = "skip"
    if not expect_shell:
        have_sh = False
        port = "skip"
        shizuku = "skip"
        a11y = "skip"
        wifi = "skip"
    elif privileged_shell():
        have_sh = True
        port = "open"
        _rc, cur = sh_adb("getprop service.adb.tcp.port")
        if cur.strip() != "5555":
            sh_adb("setprop service.adb.tcp.port 5555")  # keep 5555 sticky
        # wifi already set by proactive ensure_wireless_debugging() above
    else:
        have_sh = False
        port = "CLOSED_NO_SHELL"
        wifi = "unknown"
        rc = 1
        log("5555 CLOSED / no privileged shell — escalate to AutoJs6 UI repair or reboot")

    # --- 3. shizuku (via privileged shell) ---
    if expect_shell and have_sh:
        _, shizuku_out = sh_adb("am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS 2>/dev/null")
        if "result=1" in shizuku_out:
            shizuku = "up"
        else:
            rc, _ = sh_adb("pgrep -f shizuku_server")
            shizuku = "up" if rc == 0 else "down"
    elif expect_shell:
        shizuku = "unknown"

    # --- 4. AutoJs6 accessibility (Samsung disables it) — merge, never replace ---
    if expect_shell:
        a11y = "unknown"
        if have_sh:
            before = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
            _backup_a11y_list(before)
            if A11Y_SVC in before:
                a11y = "up"
            else:
                # Only merge if AutoJs6 is actually missing from the list.
                # accessibility_enabled 1 is skipped when already set (avoids
                # the Android 13+ confirmation dialog on redundant writes).
                new = _merge_a11y_list(before, [A11Y_SVC])
                sh_adb("settings put secure enabled_accessibility_services %s" % _a11y_value_safe(new))
                en = sh_adb("settings get secure accessibility_enabled")[1].strip()
                if en != "1":
                    sh_adb("settings put secure accessibility_enabled 1")
                recheck = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
                repaired = _repair_a11y_shrink(before, recheck)
                if repaired:
                    sh_adb("settings put secure enabled_accessibility_services %s" % _a11y_value_safe(repaired))
                    en2 = sh_adb("settings get secure accessibility_enabled")[1].strip()
                    if en2 != "1":
                        sh_adb("settings put secure accessibility_enabled 1")
                    recheck = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
                if A11Y_SVC in recheck:
                    a11y = "repaired"
                    lost = _a11y_lost(before, recheck)
                    if lost:
                        log("AutoJs6 a11y re-enabled but still missing: %s" % ",".join(lost))
                    else:
                        log("AutoJs6 accessibility was off -> re-enabled (merged)")
                else:
                    a11y = "FAILED"
                    log("AutoJs6 accessibility re-enable FAILED")

    # --- 5. Shell profile PATH (remove leaked Mac PATH that breaks pkg/apt) ---
    profile_path = ensure_shell_profile_path()

    # --- 6. Termux mirror pin (re-pin after random mirror selection by pkg) ---
    mirror = ensure_termux_mirror()

    # --- 7. phone→Mac Eternal Terminal SSH config (share-backed self-heal) ---
    et_cfg = ensure_control_et_ssh_config()

    # --- 7b. os-release (CFEngine platform detection needs it) ---
    os_release = ensure_os_release()

    # --- 8. Re-apply fleet profiles (AutoJs6 + Shizuku) in case app data was cleared.
    # Gate each independently: AutoJs6 only re-applies when its process is dead
    # (likely after data clear); Shizuku only when HEADLESS_STATUS/pgrep says down.
    # Avoids waking healthy apps and suppresses toasts every cycle.
    shizuku_profile = "skip"
    auto_profile = "skip"
    device_profile = "present"
    if expect_shell and have_sh:
        # AutoJs6: only re-apply if the process is dead (cleared data or crash).
        auto_running = False
        rc_auto, _ = sh_adb("pgrep -f org.autojs.autojs6 2>/dev/null")
        if rc_auto == 0:
            auto_running = True
        _, afp_out = sh_adb("[ -f /sdcard/Download/autojs6-fleet.json ] && echo ok || echo missing")
        if "ok" in afp_out:
            if not auto_running:
                profile = "/sdcard/Download/autojs6-fleet.json"
                sh_adb("if [ -f %s ]; then am start --user 0 "
                       "-a org.autojs.autojs6.action.APPLY_FLEET_PROFILE "
                       "-e profile_path %s -e silent true "
                       "-n org.autojs.autojs6/org.autojs.autojs.core.pref.fleet.FleetProfileActivity; fi"
                       % (profile, profile))
                time.sleep(0.5)
                auto_profile = "applied"
            else:
                auto_profile = "up"
        else:
            auto_profile = "MISSING"
            log("autojs6-fleet.json is MISSING from /sdcard/Download/ — re-deploy required")
        # Shizuku: only re-apply when Shizuku is down.
        _, sf_out = sh_adb("[ -f /data/local/tmp/shizuku-fleet.json ] && echo ok || echo missing")
        if "ok" in sf_out:
            shizuku_profile = "present"
            if shizuku != "up":
                profile = "/data/local/tmp/shizuku-fleet.json"
                sh_adb("if [ -f %s ]; then am start "
                       "-a moe.shizuku.privileged.api.APPLY_FLEET_PROFILE "
                       "-e profile_path %s -e silent true "
                       "-n moe.shizuku.privileged.api/moe.shizuku.manager.fleet.FleetProfileActivity; fi"
                       % (profile, profile))
                time.sleep(0.5)
                shizuku_profile = "applied"
                sh_adb("dumpsys deviceidle whitelist +moe.shizuku.privileged.api")
        else:
            shizuku_profile = "MISSING"
            log("shizuku-fleet.json is MISSING from /data/local/tmp/ — re-deploy required")
        # device.json: using generic fallback loses tap coordinates.
        prof = read_device_profile()
        if not prof.get("_comment") and not prof.get("device"):
            device_profile = "MISSING"
    # --- 9. Env file presence (STAYTURGID_SD, NO_LOCAL_ADB, etc.) ---
    env_file = "present" if os.path.isfile(_ENV_FILE) else "MISSING"

    status = "STATUS port=%s shizuku=%s sshd=%s a11y=%s shell=%s wifi=%s et_cfg=%s os_release=%s auto_profile=%s shizuku_profile=%s device_profile=%s env=%s" % (
        port, shizuku, sshd, a11y, "yes" if have_sh else "no", wifi, et_cfg, os_release,
        auto_profile, shizuku_profile, device_profile, env_file)
    log(status + " rc=%d" % rc)
    print(status)
    return rc


if __name__ == "__main__":
    sys.exit(main())
