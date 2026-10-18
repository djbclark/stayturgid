# -*- coding: utf-8 -*-
"""Termux SSH bootstrap over adb + run-as (control-node helpers)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import glob
import os
import shlex
import subprocess
import time

TERMUX_PKG = "com.termux"
TERMUX_HOME = "/data/data/com.termux/files/home"
TERMUX_PREFIX = "/data/data/com.termux/files/usr"
TERMUX_BASH = TERMUX_PREFIX + "/bin/bash"
TERMUX_SSHD = TERMUX_PREFIX + "/bin/sshd"
TERMUX_ACTIVITY = TERMUX_PKG + "/.app.TermuxActivity"

TERMUX_ENV = (
    "export PATH=%s/bin:%s/sbin:$PATH\n"
    "export HOME=%s\n"
    "export PREFIX=%s\n"
    "export TMPDIR=%s/tmp\n"
    "export LD_LIBRARY_PATH=%s/lib\n"
) % (TERMUX_PREFIX, TERMUX_PREFIX, TERMUX_HOME, TERMUX_PREFIX, TERMUX_PREFIX, TERMUX_PREFIX)


FLEET_PUBKEY_NAME = "termux_key.pub"


def default_keys_dir():
    return os.environ.get("STAYTURGID_SSH_KEYS_DIR", os.path.expanduser("~/.ssh"))


def discover_pubkey_paths(keys_dir=None, explicit=None):
    if explicit:
        return [os.path.expanduser(p) for p in explicit]
    root = keys_dir or default_keys_dir()
    if hasattr(root, "expanduser"):
        root = os.fspath(root)
    # The fleet key alone: a glob of the operator's ~/.ssh once put their personal
    # MIT, GitHub and OpenAFS keys on every phone. Without a termux_key.pub (a
    # consumer that names its key otherwise) the glob is the fallback.
    fleet_key = os.path.join(root, FLEET_PUBKEY_NAME)
    if os.path.isfile(fleet_key):
        return [fleet_key]
    return sorted(glob.glob(os.path.join(root, "*.pub")))


def read_pubkey_lines(paths):
    lines = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    lines.append(stripped)
    return lines


def normalize_pubkey_lines(lines):
    return [line.strip() for line in (lines or []) if line.strip() and not line.strip().startswith("#")]


def install_keys_shell(pubkey_lines):
    """Script that merges ``pubkey_lines`` into authorized_keys without clobbering.

    Keys are embedded (public material only) rather than staged on /sdcard:
    the run-as context cannot read /sdcard on some devices (#306).
    """
    keys = "\n".join(normalize_pubkey_lines(pubkey_lines))
    return (
        TERMUX_ENV
        + "set -e\n"
        + 'mkdir -p "$HOME/.ssh"\n'
        + 'chmod 700 "$HOME/.ssh"\n'
        + 'touch "$HOME/.ssh/authorized_keys"\n'
        + 'chmod 600 "$HOME/.ssh/authorized_keys"\n'
        + 'while IFS= read -r line || [ -n "$line" ]; do\n'
        + '  [ -z "$line" ] && continue\n'
        + '  case "$line" in \\#*) continue ;; esac\n'
        + '  if ! grep -qF "$line" "$HOME/.ssh/authorized_keys" 2>/dev/null; then\n'
        + '    printf \'%s\\n\' "$line" >> "$HOME/.ssh/authorized_keys"\n'
        + "  fi\n"
        + "done <<'STAYTURGID_KEYS_EOF'\n"
        + keys
        + "\nSTAYTURGID_KEYS_EOF\n"
    )


def install_openssh_shell(termux_sshd=TERMUX_SSHD):
    return (
        TERMUX_ENV
        + "set -e\n"
        + "if [ ! -x %s ]; then\n" % shlex.quote(termux_sshd)
        + "  pkg install -y openssh\n"
        + "fi\n"
        + "test -x %s\n" % shlex.quote(termux_sshd)
    )


def start_sshd_shell():
    return (
        TERMUX_ENV
        + "set -e\n"
        + "if ! pgrep -x sshd >/dev/null 2>&1; then\n"
        + "  sshd\n"
        + "fi\n"
        + "pgrep -x sshd >/dev/null\n"
    )


def read_authorized_keys_shell():
    return TERMUX_ENV + 'cat "$HOME/.ssh/authorized_keys" 2>/dev/null || true\n'


def sshd_running_shell():
    return TERMUX_ENV + "pgrep -x sshd >/dev/null\n"


def openssh_installed_shell(termux_sshd=TERMUX_SSHD):
    return TERMUX_ENV + "test -x %s\n" % shlex.quote(termux_sshd)


def adb_connect(run_command, device):
    if ":" not in device:
        return 0, "", ""
    return run_command(["adb", "connect", device])


def adb_cmd(run_command, device, *args):
    return run_command(["adb", "-s", device] + list(args))


def run_as_available(run_command, device, termux_pkg=TERMUX_PKG):
    rc, _out, _err = adb_cmd(run_command, device, "shell", "run-as", termux_pkg, "true")
    return rc == 0


def termux_installed(run_command, device, termux_pkg=TERMUX_PKG):
    rc, out, _err = adb_cmd(run_command, device, "shell", "pm", "path", termux_pkg)
    return rc == 0 and "package:" in (out or "")


def run_as_termux(run_command, device, script, termux_pkg=TERMUX_PKG, termux_bash=TERMUX_BASH):
    # adb joins shell args with spaces and the device shell re-parses them, so a
    # multi-line script must be quoted as a single word (#306).
    return adb_cmd(run_command, device, "shell", "run-as", termux_pkg, termux_bash, "-c", shlex.quote(script))


def read_authorized_keys(run_command, device):
    rc, out, _err = run_as_termux(run_command, device, read_authorized_keys_shell())
    existing = []
    for line in (out or "").replace("\r", "").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            existing.append(stripped)
    return existing, ""


def keys_need_install(existing, wanted):
    wanted = normalize_pubkey_lines(wanted)
    existing_set = set(existing)
    return any(line not in existing_set for line in wanted)


def push_authorized_keys(run_command, device, pubkey_lines, check_mode=False):
    lines = normalize_pubkey_lines(pubkey_lines)
    if not lines:
        raise ValueError("no SSH public keys to install")

    existing, _err = read_authorized_keys(run_command, device)
    if not keys_need_install(existing, lines):
        return False

    if check_mode:
        return True

    rc, out, err = run_as_termux(run_command, device, install_keys_shell(lines))
    if rc != 0:
        raise RuntimeError((err or out).strip() or "run-as install failed")
    return True


def ensure_openssh(run_command, device, check_mode=False, termux_sshd=TERMUX_SSHD):
    rc, _out, _err = run_as_termux(run_command, device, openssh_installed_shell(termux_sshd))
    if rc == 0:
        return False
    if check_mode:
        return True
    rc, out, err = run_as_termux(run_command, device, install_openssh_shell(termux_sshd))
    if rc != 0:
        raise RuntimeError((err or out).strip() or "openssh install failed")
    return True


INVERSION_KEY = "accessibility_display_inversion_enabled"


def inversion_state(run_command, device):
    """The secure setting as text ("1", "0", "null"), or '' if it cannot be read."""
    rc, out, _err = adb_cmd(run_command, device, "shell", "settings", "get", "secure", INVERSION_KEY)
    return (out or "").strip() if rc == 0 else ""


# adbd raises its "Allow USB debugging?" dialog when Termux's own adb first offers
# a new key, and Samsung drops that dialog silently on the lock screen
# ("startConfirmation: isLockScreenMode"), so the dialog never shows and nothing
# raises it again for ten minutes (s24, 2026-10-17). Anything that can make Termux
# connect to adb, or that types into the app, waits for an awake, unlocked screen.
SCREEN_WAIT_TIMEOUT_S = 600
SCREEN_POLL_S = 10
SCREEN_STATE_SHELL = "dumpsys window | grep isKeyguardShowing=; dumpsys power | grep mWakefulness="
HERMES_PING = os.path.expanduser("~/.local/bin/hermes-ping")


def parse_screen_state(text):
    """(awake, unlocked) from the dumpsys lines; None where the phone did not say."""
    awake = unlocked = None
    for line in (text or "").replace("\r", "").splitlines():
        key, _sep, value = line.strip().partition("=")
        value = value.strip()
        if key == "isKeyguardShowing" and value in ("true", "false"):
            unlocked = value == "false"
        elif key == "mWakefulness" and value in ("Awake", "Asleep", "Dreaming", "Dozing"):
            awake = value == "Awake"
    return awake, unlocked


def screen_state(run_command, device):
    rc, out, _err = adb_cmd(run_command, device, "shell", SCREEN_STATE_SHELL)
    if rc != 0:
        return None, None
    return parse_screen_state(out)


def screen_ready(awake, unlocked):
    """An unknown reading does not block: only a phone that says it is asleep or locked does."""
    return awake is not False and unlocked is not False


def describe_screen(awake, unlocked):
    parts = []
    if awake is False:
        parts.append("asleep")
    if unlocked is False:
        parts.append("locked")
    return " and ".join(parts) or "unreadable"


def ping_operator(message):
    """One hermes-ping line; a missing or failing ping never blocks the caller."""
    try:
        subprocess.run([HERMES_PING, message], capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def wait_for_unlocked_screen(
    run_command,
    device,
    host=None,
    purpose="bootstrap-ssh",
    timeout_s=SCREEN_WAIT_TIMEOUT_S,
    poll_s=SCREEN_POLL_S,
    notify=None,
    sleep=None,
    clock=None,
):
    """Return once the phone is awake and unlocked (True when it had to wait).

    Pings once when it is not, then polls every ``poll_s`` for ``timeout_s`` and
    raises RuntimeError. An unreadable state (adb failure, no such dumpsys line)
    proceeds: the next adb call reports the real fault.
    """
    notify = notify or ping_operator
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    awake, unlocked = screen_state(run_command, device)
    if screen_ready(awake, unlocked):
        return False
    label = host or device
    notify("stayturgid: unlock %s for %s" % (label, purpose))
    deadline = clock() + timeout_s
    while clock() < deadline:
        sleep(poll_s)
        awake, unlocked = screen_state(run_command, device)
        if screen_ready(awake, unlocked):
            return True
    raise RuntimeError(
        "%s is still %s after %d s: wake and unlock it, then re-run (%s needs an unlocked screen)"
        % (label, describe_screen(awake, unlocked), timeout_s, purpose)
    )


# Termux's adb keeps its identity in ~/.android/adbkey; adbd authorises it by the
# public key's base64 blob (the first field of adbkey.pub) in `dumpsys adb`.
ADBKEY_DIR = TERMUX_HOME + "/.android"
ADBKEY_PRIVATE = ADBKEY_DIR + "/adbkey"
ADBKEY_PUBLIC = ADBKEY_PRIVATE + ".pub"


def pubkey_blob(pub_text):
    """The base64 blob of an adb public key line (``<blob> user@host``), or ''."""
    for line in (pub_text or "").replace("\r", "").splitlines():
        parts = line.split()
        if parts:
            return parts[0]
    return ""


def read_termux_file(run_command, device, path):
    """Text of a Termux-owned file through run-as, or None when it is missing or unreadable."""
    rc, out, _err = run_as_termux(run_command, device, TERMUX_ENV + "cat %s\n" % shlex.quote(path))
    return out if rc == 0 and out else None


def adbkey_state(run_command, device):
    """Where Termux's own adb key stands: authorized, unauthorized, no-key or unknown.

    Read from the control node's adb, so it needs neither Termux's adb nor an
    unlocked screen. ``authorized`` means adbd's key store holds the public key
    (a persistent "Always allow"); ``no-key`` means Termux has not generated one
    yet, so its first adb connect will raise the dialog.
    """
    pub = read_termux_file(run_command, device, ADBKEY_PUBLIC)
    if pub is None:
        # run-as failing is not "no key": only an absent file under a working run-as is.
        if not run_as_available(run_command, device):
            return "unknown"
        return "no-key"
    blob = pubkey_blob(pub)
    rc, out, _err = adb_cmd(run_command, device, "shell", "dumpsys", "adb")
    if rc != 0 or not blob:
        return "unknown"
    return "authorized" if blob in (out or "") else "unauthorized"


def sshd_domain(run_command, device):
    """SELinux domain of the running sshd ('' if none / unknown)."""
    rc, out, _err = adb_cmd(run_command, device, "shell", "ps", "-A", "-Z")
    if rc != 0:
        return ""
    for line in (out or "").splitlines():
        parts = line.split()
        if parts and parts[-1] == "sshd" and len(parts) > 1:
            return parts[0]
    return ""


def start_sshd_from_app(run_command, device, termux_pkg=TERMUX_PKG, attempts=10, host=None):
    """Start sshd inside the Termux app process (untrusted_app domain).

    sshd started via run-as lives in runas_app, which has no /sdcard mount, so
    every SSH session through it fails on shared storage (#306). Type ``sshd``
    into the app's own terminal instead. Needs an unlocked screen.

    Typing is screen control, so the display is inverted while it happens (the
    visible "agent has the glass" signal, docs/rules/screen-control-hold.md),
    and nothing is typed unless inversion is confirmed on.
    """
    wait_for_unlocked_screen(run_command, device, host=host, purpose="bootstrap-ssh (typing sshd into Termux)")
    before = inversion_state(run_command, device)
    adb_cmd(run_command, device, "shell", "settings", "put", "secure", INVERSION_KEY, "1")
    try:
        if inversion_state(run_command, device) != "1":
            raise RuntimeError("refusing to type sshd into Termux: display inversion did not turn on")
        adb_cmd(run_command, device, "shell", "am", "start", "-n", TERMUX_ACTIVITY)
        time.sleep(2)
        adb_cmd(run_command, device, "shell", "input", "text", "sshd")
        adb_cmd(run_command, device, "shell", "input", "keyevent", "66")
    finally:
        if before != "1":
            adb_cmd(run_command, device, "shell", "settings", "put", "secure", INVERSION_KEY, before or "0")
    for _ in range(attempts):
        time.sleep(1)
        if sshd_domain(run_command, device):
            return True
    return False


def ensure_sshd(run_command, device, check_mode=False, host=None):
    domain = sshd_domain(run_command, device)
    if domain and "runas_app" not in domain:
        return False
    if check_mode:
        return True
    if domain:
        # Wrong-domain sshd (adb shell cannot kill it; run-as can).
        run_as_termux(run_command, device, TERMUX_ENV + "pkill -x sshd || true\n")
        time.sleep(1)
    if not start_sshd_from_app(run_command, device, host=host):
        raise RuntimeError("sshd did not start from the Termux app; unlock the device and retry")
    if "runas_app" in sshd_domain(run_command, device):
        raise RuntimeError("sshd is running in the run-as SELinux domain (no /sdcard access)")
    return True


def bootstrap_device(
    run_command,
    device,
    pubkey_lines,
    *,
    connect=True,
    install_openssh_pkg=True,
    start_sshd_service=True,
    check_mode=False,
    termux_pkg=TERMUX_PKG,
    host=None,
):
    if connect:
        adb_connect(run_command, device)
    if not termux_installed(run_command, device, termux_pkg):
        raise RuntimeError("%s is not installed on %s" % (termux_pkg, device))
    if not run_as_available(run_command, device, termux_pkg):
        raise RuntimeError(
            "run-as %s failed on %s — need debuggable Termux or manual ssh-copy-id" % (termux_pkg, device)
        )

    lines = normalize_pubkey_lines(pubkey_lines)
    if not lines:
        raise ValueError("no SSH public keys to install")

    if not check_mode:
        wait_for_unlocked_screen(run_command, device, host=host)

    openssh_changed = install_openssh_pkg and ensure_openssh(run_command, device, check_mode=check_mode)
    keys_changed = push_authorized_keys(run_command, device, lines, check_mode=check_mode)
    sshd_changed = start_sshd_service and ensure_sshd(run_command, device, check_mode=check_mode, host=host)

    return {
        "changed": bool(openssh_changed or keys_changed or sshd_changed),
        "keys_changed": bool(keys_changed),
        "openssh_changed": bool(openssh_changed),
        "sshd_changed": bool(sshd_changed),
        "run_as_available": True,
        "public_key_count": len(lines),
    }
