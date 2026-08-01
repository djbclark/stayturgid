#!/data/data/com.termux/files/usr/bin/python
# @heals: SSHD-RUNNING PORT5555-OPEN SHIZUKU-HEADLESS A11Y-AUTOJS6 MIRROR-PINNED PATH-CLEAN ET-CONFIG OS-RELEASE PKG-UPGRADE AUTOJS6-PROFILE SHIZUKU-PROFILE DEVICE-JSON ENV-FILE TAILSCALE-VPN TAILSCALE-ALWAYSON
"""stayturgid-repair.py — Termux-side self-heal (deployed as ~/stayturgid_repair.py,
reached via the ~/stayturgid_repair.py compat shim).

Unit-tested via tests/test-unit.sh (repair_suite). The ~/stayturgid_repair.py
shim keeps AutoJs6 RUN_COMMAND / boot-loop / repair-bridge callers unchanged.

Uses Shizuku's shell-privileged adbd on localhost:5555 (uid 2000) for
privileged checks/repairs. Exit 0 = healthy after repair; 1 = a subsystem
still down (needs native-agent catastrophic repair, or physical/USB
recovery). Prints one STATUS line.
"""

import base64
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import time

# Syslog-style severity levels
EMERG, ALERT, CRIT, ERR, WARNING, NOTICE, INFO, DEBUG = range(8)
_SEV_LABEL = {
    EMERG: "EMERG",
    ALERT: "ALERT",
    CRIT: "CRIT",
    ERR: "ERR",
    WARNING: "WARNING",
    NOTICE: "NOTICE",
    INFO: "INFO",
    DEBUG: "DEBUG",
}

PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
TMPDIR = os.environ.get("TMPDIR", PREFIX + "/tmp")
os.environ["PATH"] = PREFIX + "/bin:" + PREFIX + "/sbin:" + os.environ.get("PATH", "")
os.environ["LC_ALL"] = "C"

# All stayturgid files live under one root per filesystem (self-healing: every
# writer mkdir -p's its dir, so a user-deleted dir just gets recreated).
STG = os.path.join(HOME, ".stayturgid")  # Termux-private root
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
LOG_JSONL = os.path.join(STG, "logs", "repair.jsonl")
SDLOG = os.path.join(SD, "logs", "watchdog.log")
SDLOG_JSONL = os.path.join(SD, "logs", "watchdog.jsonl")
# AutoJs6 always reads /sdcard/stayturgid/logs (cannot write Termux-private
# paths on Fire). Dual-write STATUS there so the JS co-monitor can see Termux
# freshness even when STAYTURGID_SD is ~/.stayturgid/shared.
SDCARD_WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"
SDCARD_WATCHDOG_JSONL = "/sdcard/stayturgid/logs/watchdog.jsonl"
STATE_JSON = os.path.join(STG, "run", "state.json")
A11Y_SVC = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"
TAILSCALE_PACKAGE = "com.tailscale.ipn"
TAILSCALE_CONTROL_HOST = "controlplane.tailscale.com"
TAILSCALE_RECEIVER = "com.tailscale.ipn/com.tailscale.ipn.IPNReceiver"
TAILSCALE_ACTIVITY = "com.tailscale.ipn/com.tailscale.ipn.MainActivity"


def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_iso():
    """ISO 8601 timestamp with milliseconds for JSONL/OTel schema."""
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


def _detect_hostname():
    """Return device id from device.json, falling back to 'unknown'."""
    for path in (
        os.path.join(SD, "state", "device.json"),
        os.path.join(STG, "state", "device.json"),
    ):
        try:
            with open(path) as f:
                d = json.load(f)
                return str(d.get("id", "unknown"))
        except (OSError, ValueError):
            continue
    return "unknown"


def log_json(msg, level=INFO):
    """Write a single JSON line (OTel schema) to repair.jsonl and watchdog.jsonl."""
    level_label = _SEV_LABEL.get(level, "INFO").lower()
    entry = json.dumps(
        {
            "timestamp": ts_iso(),
            "level": level_label,
            "hostname": _detect_hostname(),
            "tag": "repair",
            "pid": os.getpid(),
            "tid": 0,
            "message": str(msg),
        }
    )
    jsonl_paths = [LOG_JSONL, SDLOG_JSONL]
    if os.path.normpath(SDLOG_JSONL) != os.path.normpath(SDCARD_WATCHDOG_JSONL):
        jsonl_paths.append(SDCARD_WATCHDOG_JSONL)
    for path in jsonl_paths:
        try:
            with open(ensure_parent(path), "a") as f:
                f.write(entry + "\n")
        except OSError:
            pass


def log(msg, level=INFO):
    line = "%s [repair] %s: %s" % (ts(), _SEV_LABEL.get(level, "INFO"), msg)
    paths = [LOG, SDLOG]
    if os.path.normpath(SDLOG) != os.path.normpath(SDCARD_WATCHDOG_LOG):
        paths.append(SDCARD_WATCHDOG_LOG)
    for path in paths:
        try:
            with open(ensure_parent(path), "a") as f:
                f.write(line + "\n")
        except OSError:
            pass
    # Dual-write structured JSONL alongside the legacy text log.
    try:
        log_json(msg, level)
    except Exception:
        pass  # best effort — JSONL write failure must not break self-heal


def _write_status(status):
    """Write STATUS line to run/repair.status for Ansible/module consumers.
    Also updates run/state.json atomically with parsed status fields.
    """
    status_path = os.path.join(STG, "run", "repair.status")
    try:
        ensure_parent(status_path)
        with open(status_path, "w") as f:
            f.write(status + "\n")
    except OSError:
        pass
    # Parse status string and write atomically to state.json.
    try:
        fields = {}
        for token in status.split():
            if "=" in token:
                k, v = token.split("=", 1)
                fields[k] = v
        # Read existing state, merge repair namespace.
        current = {}
        try:
            with open(STATE_JSON) as sf:
                current = json.load(sf) or {}
        except (OSError, ValueError):
            pass
        fields["timestamp"] = ts_iso()
        current["repair"] = fields
        tmp_path = STATE_JSON + ".tmp"
        ensure_parent(tmp_path)
        with open(tmp_path, "w") as f:
            json.dump(current, f)
            f.write("\n")
        os.replace(tmp_path, STATE_JSON)
    except Exception:
        pass  # best effort — state.json write failure must not block self-heal


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


# Script path doubles as the pgrep -f marker (its argv contains the path,
# not any text inside the script body) — distinct from shizuku_server itself.
_WATCHDOG_SCRIPT_PATH = "/data/local/tmp/stayturgid_shizuku_watchdog.sh"
_WATCHDOG_LOG = "/data/local/tmp/stayturgid_shizuku_watchdog.log"
_WATCHDOG_SCRIPT_BODY = (
    "#!/system/bin/sh\n"
    "while true; do\n"
    '  pgrep -f "[s]hizuku_server" >/dev/null || /data/local/tmp/shizuku_starter >/dev/null 2>&1\n'
    "  sleep 60\n"
    "done\n"
)


def ensure_shizuku_watchdog():
    """Spawn a detached UID-2000 shell loop (setsid, ppid=1) that restarts
    shizuku_server if it dies, independent of Shizuku's own app-level
    WatchdogService (which is just a regular Android process and subject to
    the same OS battery/OOM killing as anything else). Idempotent — only
    spawns if not already running. Requires privileged_shell() to already be
    true (uses sh_adb, i.e. Shizuku's own local adbd loopback) — this cannot
    help bootstrap Shizuku from nothing, only keep it running once it's up
    once. See docs/operations/sessions/session-2026-07-25-k1-verification.md
    for why the previous am-broadcast-based restart from Termux never worked
    (INTERACT_ACROSS_USERS_FULL, which Termux can never hold) and why this
    replaces it instead of trying to fix that broadcast path.

    The loop body is pushed as a script FILE via base64 (not an inline
    `setsid sh -c '...'` string) deliberately — an earlier version used
    nested quoting through bash -> adb shell -> sh -c -> pgrep -f "...", and
    the multi-layer escaping silently mangled the `while true` loop into
    something that ran one pass and exited, which looked exactly like the OS
    killing it. base64 has no shell-special characters, so there is nothing
    left to mis-escape.
    """
    # Bracket-escape one character so this check's own `pgrep -f` invocation
    # doesn't match its own argv (classic pgrep -f self-match footgun —
    # confirmed live: the naive bare-path version always reported "already
    # running" even with nothing actually running, since the pgrep command's
    # own command line literally contains the search string). Same trick
    # already used correctly elsewhere in this file for shizuku_server.
    watchdog_pgrep_pattern = _WATCHDOG_SCRIPT_PATH.replace("/s", "/[s]", 1)
    rc, _ = sh_adb("pgrep -f " + watchdog_pgrep_pattern)
    if rc == 0:
        return "already running"
    encoded = base64.b64encode(_WATCHDOG_SCRIPT_BODY.encode("utf-8")).decode("ascii")
    rc, out = sh_adb(
        "echo {b64} | base64 -d > {path} && chmod 755 {path}".format(b64=encoded, path=_WATCHDOG_SCRIPT_PATH)
    )
    if rc != 0:
        return "spawn FAILED (write): " + out.strip()
    rc, out = sh_adb("setsid sh {path} > {log} 2>&1 &".format(path=_WATCHDOG_SCRIPT_PATH, log=_WATCHDOG_LOG))
    return "spawned" if rc == 0 else "spawn FAILED (exec): " + out.strip()


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


def _device_command(args, have_sh=False, timeout=15):
    """Run a fixed Android shell command, preferring localhost adbd."""
    if have_sh:
        return sh_adb(" ".join(args), timeout=timeout)
    return run(args, timeout=timeout)


def _tailscale_installed(have_sh=False):
    rc, out = _device_command(["pm", "path", TAILSCALE_PACKAGE], have_sh)
    return rc == 0 and "package:" in out


def _tailscale_runtime_up(have_sh=False):
    """Require both a tunnel interface and Tailscale control-plane reachability.

    The tunnel-interface check must run under the device shell (uid 2000 via
    localhost adbd), not this Termux process: the Termux app uid cannot read
    ``/proc/net/dev`` on modern Android (SELinux restricts ``/proc/net``
    per-uid), so the old direct read always failed with EACCES -> tunnel read as
    absent -> runtime reported "down" every cycle -> the foreground activity
    fallback fired ~every 15 min even with a perfectly healthy tunnel. The
    native agent reads the same file fine precisely because it runs as uid 2000.

    Without a privileged shell (``have_sh=False`` — Fire OS/split-storage
    hosts where ``STAYTURGID_NO_LOCAL_ADB=1`` and localhost:5555 is not the
    privileged-shell mechanism at all, or any host that has momentarily lost
    port 5555), ``sh_adb`` has no uid-2000 shell to reach and would always
    fail — the exact same false-"down" failure mode described above, just via
    an unreachable path instead of an EACCES read. Returns ``None`` ("cannot
    verify") instead of ``False`` in that case, so callers don't mistake
    "couldn't check" for "confirmed down" and fire disruptive repairs
    (foregrounding Tailscale's UI) against a tunnel that is actually healthy.
    Confirmed live on hd8 (2026-07-31): the Shizuku-privileged on-device
    comonitor probe reported tailscale up at the same moment this check, run
    without a shell, could only ever read "down" — a guaranteed false
    negative, not a real outage.
    """
    if not have_sh:
        return None
    rc, out = sh_adb("grep -oE '(tun0|tailscale0)' /proc/net/dev 2>/dev/null | sort -u")
    tunnel = rc == 0 and ("tun0" in out or "tailscale0" in out)
    return tunnel and run(["ping", "-c", "2", "-W", "3", TAILSCALE_CONTROL_HOST], timeout=8)[0] == 0


def _tailscale_policy_up(have_sh=False):
    """Returns ``None`` ("cannot verify") instead of ``False`` when
    ``have_sh`` is false: Android's ``settings get/put secure ...`` requires
    shell-level privilege to resolve the current user
    (``INTERACT_ACROSS_USERS``); an unprivileged Termux process always throws
    a SecurityException there, which would otherwise look indistinguishable
    from a genuinely misconfigured policy. See ``_tailscale_runtime_up``.
    """
    if not have_sh:
        return None
    app = _device_command(["settings", "get", "secure", "always_on_vpn_app"], have_sh)[1].strip()
    lockdown = _device_command(["settings", "get", "secure", "always_on_vpn_lockdown"], have_sh)[1].strip()
    return app == TAILSCALE_PACKAGE and lockdown == "0"


def _tailscale_status(have_sh=False):
    """Return normalized runtime and always-on policy states.

    Reports "unknown" (not "down") when ``have_sh`` is false — neither check
    can be verified from an unprivileged Termux process, so treating that as
    "down" would be a false negative, not a real finding.
    """
    if read_device_profile().get("tailscaleEnabled") is False:
        return "skip", "skip"
    if not _tailscale_installed(have_sh):
        return "skip", "skip"
    runtime_up = _tailscale_runtime_up(have_sh)
    policy_up = _tailscale_policy_up(have_sh)
    runtime = "unknown" if runtime_up is None else ("up" if runtime_up else "down")
    policy = "unknown" if policy_up is None else ("up" if policy_up else "down")
    return runtime, policy


def _wait_for_tailscale(attempts=3, have_sh=False):
    for _ in range(attempts):
        time.sleep(2)
        if _tailscale_runtime_up(have_sh):
            return True
    return False


def _previous_repair_field(key):
    """Read a field from the previous cycle's repair status in state.json."""
    try:
        with open(STATE_JSON) as f:
            data = json.load(f) or {}
        return data.get("repair", {}).get(key)
    except (OSError, ValueError):
        return None


def ensure_tailscale(have_sh=False):
    """Restore always-on policy and request runtime reconnect when possible.

    Tailscale's exported CONNECT_VPN receiver is the supported headless path.
    Some Fire OS / WorkManager combinations reject its expedited worker; the
    activity fallback may then require an unlocked operator action. Never
    report repair unless both policy and runtime verify healthy.

    The activity fallback launches Tailscale's MainActivity into the
    foreground, interrupting whatever the user is doing on-screen — only
    worth that disruption for a sustained outage, not a single transient
    ping/DNS blip. It only fires when the previous repair cycle *also* saw
    the runtime down (~one extra cycle's delay, ~15 min), tracked via
    state.json rather than in-process state since each cycle is a fresh
    process invocation.

    Every check and repair action below requires a privileged (uid 2000)
    shell — the settings get/put calls throw SecurityException without one,
    and the tunnel-interface read needs uid 2000 to see ``/proc/net/dev``.
    Without one (``have_sh=False``: Fire OS/split-storage hosts with
    ``STAYTURGID_NO_LOCAL_ADB=1``, or a host that's momentarily lost
    localhost:5555), every one of those calls is guaranteed to fail — not
    because Tailscale is down, but because this process cannot see it.
    Returns "unknown" and does nothing in that case, rather than reporting a
    false "FAILED" and forcing Tailscale's MainActivity into the foreground
    against a tunnel that may be perfectly healthy (confirmed live on hd8,
    2026-07-31: see ``_tailscale_runtime_up``).
    """
    if read_device_profile().get("tailscaleEnabled") is False:
        return "skip"
    if not _tailscale_installed(have_sh):
        return "skip"
    if not have_sh:
        return "unknown"

    _device_command(
        ["settings", "put", "secure", "always_on_vpn_app", TAILSCALE_PACKAGE],
        have_sh,
    )
    _device_command(
        ["settings", "put", "secure", "always_on_vpn_lockdown", "0"],
        have_sh,
    )
    policy_ok = _tailscale_policy_up(have_sh)
    if _tailscale_runtime_up(have_sh):
        if policy_ok:
            return "up"
        log("Tailscale runtime up but always-on policy repair FAILED", ERR)
        return "FAILED"

    _device_command(
        [
            "am",
            "broadcast",
            "--include-stopped-packages",
            "-a",
            "com.tailscale.ipn.CONNECT_VPN",
            "-n",
            TAILSCALE_RECEIVER,
        ],
        have_sh,
    )
    restored = _wait_for_tailscale(have_sh=have_sh)
    if not restored:
        if _previous_repair_field("tailscale") == "down":
            _device_command(["am", "start", "-n", TAILSCALE_ACTIVITY], have_sh)
            restored = _wait_for_tailscale(attempts=2, have_sh=have_sh)
        else:
            log(
                "Tailscale still down after CONNECT_VPN broadcast; deferring "
                "foreground activity fallback to next cycle",
                NOTICE,
            )

    if restored and policy_ok:
        log("Tailscale runtime/policy restored", NOTICE)
        return "repaired"
    log(
        "Tailscale repair FAILED (runtime=%s policy=%s); unlocked operator action may be required"
        % ("up" if restored else "down", "up" if policy_ok else "down"),
        ERR,
    )
    return "FAILED"


def ensure_wireless_debugging():
    """Assess the localhost shell bridge and repair the toggle when possible.

    A responsive UID-2000 shell is functionally healthy even when Android 16
    reports the cosmetic ``adb_wifi_enabled=0`` value; Samsung and Pixel both
    exhibit that state. Returns: 'up', 'repaired', 'FAILED', or 'NO_SHELL'.
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
        log("wireless debugging: cannot reach shell (adb_wifi_enabled=%s)" % wifi, ERR)
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
    log("wireless debugging re-enable FAILED (adb_wifi_enabled=%s)" % wifi2, ERR)
    return "FAILED"


def duplicate_branch():
    """Another invocation holds the lock: read-only advisory probe, exit 0.
    Output goes only to log — never stdout, even when quiet mode is off."""
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
            shizuku_rc, _ = sh_adb("pgrep -f '[s]hizuku_server'")
            shizuku = "up" if shizuku_rc == 0 else "down"
        wifi = "up" if sh_adb("settings get global adb_wifi_enabled")[1].strip() in ("1", "true") else "down"
        before = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
        a11y = "up" if A11Y_SVC in before else "down"
    else:
        # Port 5555 down — fall back to Termux-native pgrep for Shizuku.
        port, sh = "CLOSED_NO_SHELL", False
        rc, _ = run(["pgrep", "-f", "[s]hizuku_server"])
        shizuku = "up" if rc == 0 else "down"
        wifi, a11y = "unknown", "unknown"
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
        et_cfg = "up" if "STAYTURGID-CONTROL-ET" in existing and "IdentityFile" in existing else "down"
    tailscale, tailscale_policy = _tailscale_status(have_sh=sh)
    status = (
        "STATUS port=%s shizuku=%s sshd=%s a11y=%s shell=%s wifi=%s tailscale=%s tailscale_policy=%s et_cfg=%s os_release=skip pkg_upgrade=skip auto_profile=skip shizuku_profile=skip device_profile=skip env=skip"
        % (
            port,
            shizuku,
            sshd,
            a11y,
            "yes" if sh else "no",
            wifi,
            tailscale,
            tailscale_policy,
            et_cfg,
        )
    )
    log(status + " rc=0 (skipped-duplicate)")
    _write_status(status)


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


MAC_PATH_KEYWORDS = ("/Users/", "/opt/homebrew/", "/Library/Apple/", "/System/Cryptexes/")

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
            if (stripped.startswith("export PATH=") or stripped.startswith("PATH=")) and any(
                kw in stripped for kw in MAC_PATH_KEYWORDS
            ):
                new.append('export PATH="$HOME/bin:%s/bin:%s/sbin:$PATH"\n' % (PREFIX, PREFIX))
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
        log(
            "Termux mirror re-pinned from %s -> %s"
            % (current.strip().split()[1] if len(current.split()) > 1 else "absent", CANONICAL_MIRROR)
        )
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
    # Older deployments wrote an unmarked Mac block before the managed block.
    # OpenSSH keeps the first value for each option, so that stale block wins
    # and silently routes ET to the old hostname/key. Remove only that known
    # legacy block; preserve all unrelated SSH configuration.
    legacy = re.compile(r"(?ms)^# MacBook Air via Tailscale.*?^    IdentitiesOnly yes[ \t]*\n?")
    cleaned = legacy.sub("", existing)
    has_managed = "STAYTURGID-CONTROL-ET" in cleaned and "IdentityFile" in cleaned
    if has_managed:
        if cleaned == existing:
            return "up"
        try:
            with open(conf, "w") as f:
                f.write(cleaned)
            os.chmod(conf, 0o600)
            log("stale legacy control-ET ssh config removed")
            return "repaired"
        except OSError as e:
            log("control-ET legacy ssh config cleanup FAILED: %s" % e)
            return "FAILED"
    block = "%s\n%s\n%s\n" % (alt_begin, fragment, alt_end)
    try:
        os.makedirs(os.path.dirname(conf), exist_ok=True)
        existing = cleaned
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
    "ID=termux\n"
    "ID_LIKE=android\n"
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


PKG_UPGRADE_STAMP = os.path.join(STG, "state", "pkg-upgrade.stamp")
PKG_UPGRADE_LOW_HOURS = range(3, 6)  # 3am-5am local device time


def ensure_pkg_upgrade_daily():
    """Run pkg upgrade at most once per day, during low-activity hours.

    Checks a timestamp file: if >24h since last successful upgrade AND the
    current hour is in a low-activity window (3-5am) OR the stamp is very old
    (>48h), runs pkg update + upgrade. Records success/failure so the next
    cycle retries if needed.
    """
    now_ts = time.time()
    now_hour = time.localtime(now_ts).tm_hour
    try:
        with open(PKG_UPGRADE_STAMP) as f:
            last_line = f.read().strip()
            if last_line.startswith("ok "):
                last_ts = float(last_line.split(" ", 1)[1])
                age_hours = (now_ts - last_ts) / 3600.0
                if age_hours < 24:
                    return "up"
    except (OSError, ValueError, IndexError):
        pass

    # Only run during low-activity hours (3-5am), or if very stale (>48h).
    if now_hour not in PKG_UPGRADE_LOW_HOURS:
        try:
            with open(PKG_UPGRADE_STAMP) as f:
                first_line = f.read().strip().split("\n")[0]
            if first_line.startswith("ok "):
                try:
                    last_ts = float(first_line.split(" ", 1)[1])
                    if (now_ts - last_ts) / 3600.0 < 48:
                        return "waiting"
                except (ValueError, IndexError):
                    pass
        except OSError:
            return "waiting"

    log("daily pkg upgrade: running update + full-upgrade")
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    try:
        # pkg update (non-fatal — indexes may already be fresh)
        subprocess.run(
            ["pkg", "update", "-y"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=120,
            env=env,
        )
        p = subprocess.run(
            [
                "apt-get",
                "-y",
                "-o",
                "Dpkg::Options::=--force-confdef",
                "-o",
                "Dpkg::Options::=--force-confold",
                "full-upgrade",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
            env=env,
        )
        rc = p.returncode
    except subprocess.TimeoutExpired:
        log("daily pkg upgrade TIMEOUT")
        return "FAILED"
    except Exception as e:
        log("daily pkg upgrade ERROR: %s" % e)
        return "FAILED"

    if rc == 0:
        try:
            with open(PKG_UPGRADE_STAMP, "w") as f:
                f.write("ok %s\n" % now_ts)
        except OSError:
            pass
        log("daily pkg upgrade succeeded")
        return "repaired"
    else:
        log("daily pkg upgrade FAILED rc=%d" % rc)
        return "FAILED"


# --- On-device fallback anomaly detection (issue: central-logging gap, 2026-07-31) ---
#
# fleet_health_monitor.py now ships new ERR/WARNING watchdog.log lines to
# stats/OpenObserve every SSH probe cycle — but that whole path (Mac reachable
# over SSH/Tailscale, OpenObserve up) can be down at exactly the moment a
# device is unhealthy. This is the fallback that doesn't depend on any of it:
# count our own recent ERR lines and, past a threshold, poke the operator
# directly via termux-notification. Deliberately simple — a counter + a
# threshold, not a general anomaly detector.
ERROR_RATE_WINDOW_SEC = 3600  # rolling window: last hour
# ensure_tailscale (and other checks) log a fresh ERR every repair cycle
# (~STAYTURGID_INTERVAL_SEC=300s in start_adb.py) they still see the same
# failure, so a *sustained* problem produces ~12 ERR lines/hour. Threshold=3
# (~15 min of consecutive failing cycles) is high enough that one or two
# transient blips don't page a human, low enough to catch a real outage well
# before the old "nobody happened to SSH in today" discovery path.
ERROR_RATE_THRESHOLD = 3
ERROR_RATE_NOTIFY_COOLDOWN_SEC = 3600  # re-notify at most once/hour while still bad
ERROR_RATE_NOTIFY_STAMP = os.path.join(STG, "state", "watchdog-error-rate-notify")


def _parse_watchdog_line_epoch(line):
    """Return epoch seconds for a 'YYYY-MM-DD HH:MM:SS [repair] ...' line, or None."""
    try:
        return datetime.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def count_recent_watchdog_errors(path=None, now=None, window_sec=ERROR_RATE_WINDOW_SEC):
    """Count '[repair] ERR:' lines within window_sec of now in watchdog.log.

    path/now are injectable for tests; production calls use SDLOG/real time.
    """
    path = path or SDLOG
    now = now if now is not None else time.time()
    count = 0
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return 0
    for line in lines:
        if "[repair] ERR:" not in line:
            continue
        epoch = _parse_watchdog_line_epoch(line)
        if epoch is None:
            continue
        if 0 <= now - epoch <= window_sec:
            count += 1
    return count


def maybe_notify_error_rate(tapi_module=None):
    """termux-notification fallback for when the Mac pipe might be unreachable too.

    Uses ONLY the safe termux_api wrapper (control/lib/termux_api.py, deployed
    to ~/.stayturgid/lib) — never a bare subprocess call to termux-notification.
    A bare timeout+kill on a termux-api client causes a loud "Error in
    ResultReturner" toast (the exact bug already fixed once this session, in
    start_adb.py) — termux_api.notify()/run_ff() orphan instead of killing so
    the socket can still complete.

    Returns "ok" (below threshold), "cooldown" (already notified recently),
    or "notified".
    """
    count = count_recent_watchdog_errors()
    if count < ERROR_RATE_THRESHOLD:
        return "ok"
    last = 0.0
    try:
        with open(ERROR_RATE_NOTIFY_STAMP) as f:
            last = float(f.read().strip() or 0)
    except (OSError, ValueError):
        last = 0.0
    now = time.time()
    if now - last < ERROR_RATE_NOTIFY_COOLDOWN_SEC:
        return "cooldown"

    tapi = tapi_module
    if tapi is None:
        try:
            import stayturgid_shell as _sh

            _sh.ensure_lib_path()
            import termux_api as tapi
        except ImportError:
            tapi = None
    if tapi is not None:
        tapi.notify(
            [
                "termux-notification",
                "--id",
                "stayturgid-error-rate",
                "--title",
                "stayturgid: repeated errors",
                "--content",
                "%d repair ERR lines in the last hour - check watchdog.log" % count,
            ]
        )
    log(
        "watchdog error-rate fallback: %d ERR lines in last %ds — notified operator (Mac pipe may be down too)"
        % (count, ERROR_RATE_WINDOW_SEC),
        WARNING,
    )
    try:
        with open(ensure_parent(ERROR_RATE_NOTIFY_STAMP), "w") as f:
            f.write(str(int(now)))
    except OSError:
        pass
    return "notified"


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
    ensure_sshd_down_file()
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
        log("5555 CLOSED / no privileged shell — escalate to native-agent catastrophic repair or reboot", ERR)

    # --- 3. shizuku (via privileged shell; watchdog handles restart) ---
    if expect_shell and have_sh:
        _, shizuku_out = sh_adb("am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS 2>/dev/null")
        if "result=1" in shizuku_out:
            shizuku = "up"
        else:
            # NOTE: was previously `rc, _ = sh_adb(...)`, silently clobbering
            # the overall health rc (e.g. erasing an earlier sshd-failure
            # rc=1 if this check happened to pass) — fixed to a properly
            # namespaced variable, matching the convention used everywhere
            # else in this file (_rc / shizuku_rc).
            shizuku_rc, _ = sh_adb("pgrep -f '[s]hizuku_server'")
            shizuku = "up" if shizuku_rc == 0 else "down"
        if shizuku == "down":
            rc = 1
            log("shizuku_server not running (adb shell still reachable)", WARNING)
        # Ensure the detached UID-2000 watchdog is running while we have
        # privileged shell — this is what actually restarts shizuku_server
        # if it dies later, independent of Shizuku's own app-level
        # WatchdogService (which is just a regular Android process, subject
        # to the same OS battery/OOM killing as anything else). Idempotent.
        watchdog_status = ensure_shizuku_watchdog()
        if watchdog_status != "already running":
            log("shizuku watchdog: " + watchdog_status, INFO if watchdog_status == "spawned" else WARNING)
        if watchdog_status.startswith("spawn FAILED"):
            # The watchdog is a safeguard, not just a nice-to-have — if it
            # can't even be spawned, that's a real problem worth surfacing
            # as an unhealthy exit code, not just a log line nobody reads.
            rc = 1
    elif expect_shell:
        # Port 5555 is down — can't use adb shell, so we're on Termux's own
        # unprivileged UID. Only pgrep-based liveness detection is possible;
        # this used to also try `am broadcast HEADLESS_START`, but that
        # receiver requires INTERACT_ACROSS_USERS_FULL (a signature/
        # privileged permission Termux can never hold — confirmed via a live
        # Permission Denial in logcat, meaning this call has been silently
        # failing since the feature was added). Removed rather than fixed:
        # confirmed via two independent reviews that no securely-pinned
        # version of that broadcast recovers anything the native agent's own
        # privileged Shizuku-UserService path, or an adb-shell-based Mac
        # trigger (when a transport is reachable), don't already cover. See
        # docs/operations/sessions/session-2026-07-25-k1-verification.md.
        shizuku_rc, _ = run(["pgrep", "-f", "[s]hizuku_server"])
        if shizuku_rc == 0:
            shizuku = "up"
            # Shizuku daemon is running but port 5555 is closed — likely TCP
            # mode wasn't enabled (fleet profile not applied). Re-applying
            # the fleet profile is a plain `am start` on an unprotected
            # activity, unlike HEADLESS_START — this part still works from
            # Termux without any privilege.
            log("shizuku_server running but port 5555 closed — re-applying fleet profile", WARNING)
            shizuku_fp = "/data/local/tmp/shizuku-fleet.json"
            if not os.path.isfile(shizuku_fp):
                shizuku_fp = "/sdcard/Download/shizuku-fleet.json"
            if os.path.isfile(shizuku_fp):
                run(
                    [
                        "am",
                        "start",
                        "--user",
                        "0",
                        "-a",
                        "moe.shizuku.privileged.api.APPLY_FLEET_PROFILE",
                        "-e",
                        "profile_path",
                        shizuku_fp,
                        "-e",
                        "silent",
                        "true",
                        "-n",
                        "moe.shizuku.privileged.api/moe.shizuku.manager.fleet.FleetProfileActivity",
                    ]
                )
                time.sleep(1)
            # Re-check if the profile re-apply alone was enough.
            if privileged_shell():
                have_sh = True
                port = "open"
                log("port 5555 restored via fleet profile re-apply from Termux", NOTICE)
        else:
            shizuku = "down"
            log(
                "shizuku_server NOT running and no privileged shell available — "
                "cannot restart from Termux (needs adb shell or the on-device "
                "watchdog, which needs shizuku_server to have been up at least "
                "once already); escalate to native-agent/USB/physical recovery",
                ERR,
            )

    # AutoJs6 was fully uninstalled fleet-wide during the K1 native-agent
    # cutover verification (2026-07-25, issue #43) and is not expected to
    # return. Gate the two legacy AutoJs6-specific self-heal checks below on
    # live install state so its absence reads as the retired, healthy state
    # instead of perpetual ACTION_REQUIRED noise (was: always "missing").
    autojs6_present = False
    if expect_shell and have_sh:
        _rc, _autojs6_out = sh_adb("pm path org.autojs.autojs6 2>/dev/null")
        autojs6_present = _rc == 0 and "package:" in _autojs6_out

    # --- 4. AutoJs6 accessibility (detection only; user must enable manually) ---
    a11y = "unknown"
    if expect_shell:
        if have_sh:
            if not autojs6_present:
                a11y = "retired"
            else:
                raw = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
                if A11Y_SVC in raw:
                    a11y = "up"
                    # Settings-list alone cannot detect sticky ON (enabled but not bound).
                    # If the AutoJs6 watchdog has gone quiet while we remain listed, nudge
                    # the operator — OFF→ON rebind is the human fix (policy G3: no settings put).
                    try:
                        wd = os.path.join(SD, "logs", "watchdog.log")
                        if os.path.isfile(wd):
                            age = time.time() - os.path.getmtime(wd)
                            if age >= 1800:  # 30 min — matches fleet WATCHDOG_FRESH_SEC band
                                log(
                                    "AutoJs6 a11y listed ON but watchdog quiet %.0fs — "
                                    "if Task is empty, toggle Accessibility OFF then ON "
                                    "and re-run main.js" % age,
                                    WARNING,
                                )
                                log(
                                    "ACTION_REQUIRED: AutoJs6 accessibility may be sticky "
                                    "(Settings ON, service not bound) on %s — toggle OFF then ON"
                                    % (os.uname().nodename if hasattr(os, "uname") else "device"),
                                    NOTICE,
                                )
                    except OSError:
                        pass
                else:
                    a11y = "down"
                    log(
                        "AutoJs6 accessibility is OFF — re-enable in Settings > Accessibility > "
                        "AutoJs6 (if already ON, turn OFF then ON again)",
                        WARNING,
                    )
                    log(
                        "ACTION_REQUIRED: AutoJs6 accessibility disabled on %s"
                        % (os.uname().nodename if hasattr(os, "uname") else "device"),
                        NOTICE,
                    )

    # --- 5. Shell profile PATH (remove leaked Mac PATH that breaks pkg/apt) ---
    ensure_shell_profile_path()

    # --- 6. Termux mirror pin (re-pin after random mirror selection by pkg) ---
    ensure_termux_mirror()

    # --- 7. phone→Mac Eternal Terminal SSH config (share-backed self-heal) ---
    et_cfg = ensure_control_et_ssh_config()

    # --- 7b. os-release (CFEngine platform detection needs it) ---
    os_release = ensure_os_release()

    # --- 7c. Daily pkg upgrade (once/24h, 3-5am; retries if phone was off) ---
    pkg_upgrade = ensure_pkg_upgrade_daily()

    # --- 8. Re-apply fleet profiles (AutoJs6 + Shizuku) in case app data was cleared.
    # Gate each independently: AutoJs6 only re-applies when its process is dead
    # (likely after data clear); Shizuku only when HEADLESS_STATUS/pgrep says down.
    # Avoids waking healthy apps and suppresses toasts every cycle.
    shizuku_profile = "skip"
    auto_profile = "skip"
    device_profile = "present"
    if expect_shell and have_sh:
        if not autojs6_present:
            auto_profile = "retired"
        else:
            # AutoJs6: only re-apply if the process is dead (cleared data or crash).
            auto_running = False
            rc_auto, _ = sh_adb("pgrep -f org.autojs.autojs6 2>/dev/null")
            if rc_auto == 0:
                auto_running = True
            _, afp_out = sh_adb("[ -f /sdcard/Download/autojs6-fleet.json ] && echo ok || echo missing")
            if "ok" in afp_out:
                if not auto_running:
                    profile = "/sdcard/Download/autojs6-fleet.json"
                    sh_adb(
                        "if [ -f %s ]; then am start --user 0 "
                        "-a org.autojs.autojs6.action.APPLY_FLEET_PROFILE "
                        "-e profile_path %s -e silent true "
                        "-n org.autojs.autojs6/org.autojs.autojs.core.pref.fleet.FleetProfileActivity; fi"
                        % (profile, profile)
                    )
                    time.sleep(0.5)
                    auto_profile = "applied"
                else:
                    auto_profile = "up"
            else:
                auto_profile = "MISSING"
                log("autojs6-fleet.json is MISSING from /sdcard/Download/ — re-deploy required")
        # Shizuku: only re-apply when Shizuku is down.
        _, sf_out = sh_adb("[ -f /data/local/tmp/shizuku-fleet.json ] && echo ok || echo missing")
        profile = "/data/local/tmp/shizuku-fleet.json"
        if "missing" in sf_out:
            _, sf_out2 = sh_adb("[ -f /sdcard/Download/shizuku-fleet.json ] && echo ok || echo missing")
            if "ok" in sf_out2:
                sf_out = sf_out2
                profile = "/sdcard/Download/shizuku-fleet.json"

        if "ok" in sf_out:
            shizuku_profile = "present"
            if shizuku != "up":
                sh_adb(
                    "if [ -f %s ]; then am start "
                    "-a moe.shizuku.privileged.api.APPLY_FLEET_PROFILE "
                    "-e profile_path %s -e silent true "
                    "-n moe.shizuku.privileged.api/moe.shizuku.manager.fleet.FleetProfileActivity; fi"
                    % (profile, profile)
                )
                time.sleep(0.5)
                shizuku_profile = "applied"
                sh_adb("dumpsys deviceidle whitelist +moe.shizuku.privileged.api")
        else:
            shizuku_profile = "MISSING"
            log("shizuku-fleet.json is MISSING from /data/local/tmp/ and /sdcard/Download/ — re-deploy required")
        # device.json: using generic fallback loses tap coordinates.
        prof = read_device_profile()
        if not prof.get("id") and not prof.get("_comment"):
            device_profile = "MISSING"
    # --- 9. Env file presence (STAYTURGID_SD, NO_LOCAL_ADB, etc.) ---
    env_file = "present" if os.path.isfile(_ENV_FILE) else "MISSING"

    # --- 10. Tailscale runtime and non-lockdown always-on policy ---
    tailscale_repair = ensure_tailscale(have_sh=have_sh)
    tailscale, tailscale_policy = _tailscale_status(have_sh=have_sh)
    if tailscale_repair == "FAILED" or tailscale == "down" or tailscale_policy == "down":
        rc = 1

    # --- 11. Fallback anomaly detection: notify a human directly if this
    # cycle (or a recent one) is part of a sustained error spike, independent
    # of whether the Mac control node / OpenObserve is reachable at all.
    maybe_notify_error_rate()

    status = (
        "STATUS port=%s shizuku=%s sshd=%s a11y=%s shell=%s wifi=%s tailscale=%s tailscale_policy=%s et_cfg=%s os_release=%s pkg_upgrade=%s auto_profile=%s shizuku_profile=%s device_profile=%s env=%s"
        % (
            port,
            shizuku,
            sshd,
            a11y,
            "yes" if have_sh else "no",
            wifi,
            tailscale,
            tailscale_policy,
            et_cfg,
            os_release,
            pkg_upgrade,
            auto_profile,
            shizuku_profile,
            device_profile,
            env_file,
        )
    )
    log(status + " rc=%d" % rc)
    _write_status(status)
    return rc


if __name__ == "__main__":
    sys.exit(main())
