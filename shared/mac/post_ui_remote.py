#!/usr/bin/env python3
"""Mac → Termux SSH invoke for on-device post-UI scripts.

s24/p7a: run ~/.stayturgid/bin/<script>.py over SSH (localhost:5555 on device).
hd8 / no privileged shell: caller keeps Mac USB ScreenControlSession path.
"""
from __future__ import annotations

import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "shared", "mac"))
import stayturgid_device as dev  # noqa: E402

SSH_OPTS = list(dev.SSH_OPTS)
ON_DEVICE_BIN = "~/.stayturgid/bin"


def host_uses_on_device_ui(alias: str) -> bool:
    """True when Termux localhost:5555 is the expected privileged channel."""
    # Fire OS / hd8: inventory marks privilegedShellExpected false via device.json
    # on device; Mac-side we treat known Fire alias as USB-only.
    if alias in ("hd8",):
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


def _shell_quote(text: str) -> str:
    return "'" + str(text).replace("'", "'\"'\"'") + "'"
