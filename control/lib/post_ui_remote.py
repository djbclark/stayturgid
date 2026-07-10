#!/usr/bin/env python3
"""Mac → Termux SSH invoke for on-device post-UI scripts.

s24/p7a: prefer SSH → ~/.stayturgid/bin/<script>.py (Termux localhost:5555).
On SSH failure (connect error or non-zero), fall back to the caller's Mac adb
path (USB or wireless via resolve_adb).

hd8 / raw serial / no privileged shell: Mac adb only — Fire OS has no
Termux→localhost:5555 loopback, so SSH-invoking on-device UI cannot work.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "control", "lib"))
import stayturgid_device as dev  # noqa: E402

SSH_OPTS = list(dev.SSH_OPTS)
ON_DEVICE_BIN = "~/.stayturgid/bin"

# Fire OS aliases: no Termux privileged localhost:5555 — never SSH-invoke UI.
MAC_ADB_ONLY_ALIASES = frozenset({"hd8"})


def host_uses_on_device_ui(alias: str) -> bool:
    """True when Termux localhost:5555 is the expected privileged channel."""
    if alias in MAC_ADB_ONLY_ALIASES:
        return False
    row = dev.device_row(alias)
    if not row:
        return False  # raw serial → Mac adb
    return bool(dev.resolve_ssh_host(alias))


def ssh_run_on_device(alias: str, script_name: str, args: list[str] | None = None) -> int:
    """SSH to alias and run python3 ~/.stayturgid/bin/<script_name> [args]."""
    host = dev.resolve_ssh_host(alias) or alias
    args = args or []
    remote = (
        "export PATH=/data/data/com.termux/files/usr/bin:$PATH; "
        "export TMPDIR=/data/data/com.termux/files/usr/tmp; "
        "[ -f ~/.stayturgid/env ] && . ~/.stayturgid/env; "
        "exec python3 %s/%s %s"
        % (
            ON_DEVICE_BIN,
            script_name,
            " ".join(_shell_quote(a) for a in args),
        )
    )
    print("On-device UI: ssh %s → %s %s" % (host, script_name, " ".join(args)))
    r = subprocess.run(
        ["ssh"] + SSH_OPTS + [host, remote],
        cwd=REPO,
    )
    return r.returncode


def run_with_mac_fallback(
    alias: str,
    script_name: str,
    args: list[str] | None,
    mac_fn: Callable[[], int],
) -> int:
    """Prefer on-device SSH when expected; on any failure, run mac_fn (Mac adb).

    hd8 / raw serial skip SSH and call mac_fn immediately.
    """
    if not host_uses_on_device_ui(alias):
        return mac_fn()

    rc = ssh_run_on_device(alias, script_name, args)
    if rc == 0:
        return 0

    sys.stderr.write(
        "WARN: on-device UI via SSH failed (rc=%s) — falling back to Mac adb\n" % rc
    )
    return mac_fn()


def _shell_quote(text: str) -> str:
    return "'" + str(text).replace("'", "'\"'\"'") + "'"
