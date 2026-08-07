#!/usr/bin/env python3
"""Build safe commands for the control-node SecretSpec boundary.

The passwordless sudo rule is intentionally *not* a general SecretSpec CLI
proxy.  The root-owned wrapper exposes only two fixed operations:
``automation-env`` (JSON environment for the approved Ansible automation) and
``firerpa-mcp-token`` (one named token).  This module keeps the caller-side
interface equally narrow and executes approved automation as the invoking user.

A same-UID caller can still invoke an approved operation when the sudoers rule
is granted to that UID; UNIX credentials cannot distinguish two processes with
the same UID.  The enforceable boundary here is that malformed arguments,
caller-selected SecretSpec subcommands, environment injection, and arbitrary
commands are rejected by the wrapper and by this selector.

CI and other machines without the service account use direct ``secretspec``
with their normal provider configuration.  Set ``STAYTURGID_SECRETSPEC_DIRECT=1``
to exercise that path deliberately.
"""

from __future__ import annotations

import os
import pwd
import sys
from functools import lru_cache
from pathlib import Path

WRAPPER_PATH = "/usr/local/libexec/stayturgid-secretspec-wrapper.sh"
SERVICE_USER = "_secretspec"
VAULT_DIR = "/var/db/stayturgid-secrets"
FORCE_DIRECT_ENV = "STAYTURGID_SECRETSPEC_DIRECT"
HELPER_PATH = str(Path(__file__).with_name("secretspec_env_exec.py"))
APPROVED_EXECUTABLE = "ansible-playbook"


def _service_user_exists() -> bool:
    try:
        pwd.getpwnam(SERVICE_USER)
    except KeyError:
        return False
    return True


@lru_cache(maxsize=1)
def wrapper_available() -> bool:
    """True when the privilege-separated SecretSpec path is usable here."""
    if os.environ.get(FORCE_DIRECT_ENV) == "1":
        return False
    has_wrapper = os.path.isfile(WRAPPER_PATH) and os.access(WRAPPER_PATH, os.X_OK)
    has_user = _service_user_exists()
    if has_wrapper and has_user:
        return True
    if os.path.isdir(VAULT_DIR):
        missing = []
        if not has_wrapper:
            missing.append(f"wrapper {WRAPPER_PATH}")
        if not has_user:
            missing.append(f"user {SERVICE_USER}")
        print(
            f"WARNING: {VAULT_DIR} exists but {' and '.join(missing)} missing — "
            "falling back to direct secretspec, without privilege separation. "
            "See docs/operations/secretspec-secrets-management.md to repair.",
            file=sys.stderr,
        )
    return False


def _approved_automation(command: tuple[str, ...]) -> bool:
    """Reject shell interpreters and non- Ansible automation at this seam."""
    return bool(command) and command[0] == APPROVED_EXECUTABLE


def secretspec_token_command(name: str) -> list[str]:
    """Return the fixed FIRERPA token operation; no caller-selected ``get``."""
    if name != "firerpa_mcp_token":
        raise ValueError("only firerpa_mcp_token is available through the wrapper")
    if wrapper_available():
        return ["sudo", "-n", "-u", SERVICE_USER, WRAPPER_PATH, "firerpa-mcp-token"]
    return ["secretspec", "get", name]


def secretspec_command(*args: str) -> list[str]:
    """Return an approved SecretSpec command for this machine.

    Only ``run -- ansible-playbook ...`` is accepted on the wrapped path.  The
    helper obtains JSON from the fixed wrapper operation and overlays it onto
    the invoking user's environment before ``execvpe``-ing Ansible, so the
    target remains ``djbclark`` with a writable HOME and no shell evaluation.
    """
    if not args:
        raise ValueError("SecretSpec command cannot be empty")
    if args[:2] != ("run", "--"):
        if wrapper_available():
            raise ValueError("arbitrary SecretSpec subcommands are unavailable through the wrapper")
        return ["secretspec", *args]

    command = tuple(args[2:])
    if wrapper_available() and not _approved_automation(command):
        raise ValueError("only ansible-playbook is approved through the wrapper")
    if wrapper_available():
        return [sys.executable, HELPER_PATH, *command]
    return ["secretspec", *args]


def secretspec_run(*command: str) -> list[str]:
    """Convenience wrapper for the approved ``run -- ansible-playbook`` form."""
    return secretspec_command("run", "--", *command)
