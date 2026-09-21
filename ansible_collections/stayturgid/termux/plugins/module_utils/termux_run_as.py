# -*- coding: utf-8 -*-
"""Termux SSH bootstrap over adb + run-as (control-node helpers)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import glob
import os
import shlex
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


def default_keys_dir():
    return os.environ.get("STAYTURGID_SSH_KEYS_DIR", os.path.expanduser("~/.ssh"))


def discover_pubkey_paths(keys_dir=None, explicit=None):
    if explicit:
        return [os.path.expanduser(p) for p in explicit]
    root = keys_dir or default_keys_dir()
    if hasattr(root, "expanduser"):
        root = os.fspath(root)
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


def start_sshd_from_app(run_command, device, termux_pkg=TERMUX_PKG, attempts=10):
    """Start sshd inside the Termux app process (untrusted_app domain).

    sshd started via run-as lives in runas_app, which has no /sdcard mount, so
    every SSH session through it fails on shared storage (#306). Type ``sshd``
    into the app's own terminal instead. Needs an unlocked screen.
    """
    adb_cmd(run_command, device, "shell", "am", "start", "-n", TERMUX_ACTIVITY)
    time.sleep(2)
    adb_cmd(run_command, device, "shell", "input", "text", "sshd")
    adb_cmd(run_command, device, "shell", "input", "keyevent", "66")
    for _ in range(attempts):
        time.sleep(1)
        if sshd_domain(run_command, device):
            return True
    return False


def ensure_sshd(run_command, device, check_mode=False):
    domain = sshd_domain(run_command, device)
    if domain and "runas_app" not in domain:
        return False
    if check_mode:
        return True
    if domain:
        # Wrong-domain sshd (adb shell cannot kill it; run-as can).
        run_as_termux(run_command, device, TERMUX_ENV + "pkill -x sshd || true\n")
        time.sleep(1)
    if not start_sshd_from_app(run_command, device):
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

    openssh_changed = install_openssh_pkg and ensure_openssh(run_command, device, check_mode=check_mode)
    keys_changed = push_authorized_keys(run_command, device, lines, check_mode=check_mode)
    sshd_changed = start_sshd_service and ensure_sshd(run_command, device, check_mode=check_mode)

    return {
        "changed": bool(openssh_changed or keys_changed or sshd_changed),
        "keys_changed": bool(keys_changed),
        "openssh_changed": bool(openssh_changed),
        "sshd_changed": bool(sshd_changed),
        "run_as_available": True,
        "public_key_count": len(lines),
    }
