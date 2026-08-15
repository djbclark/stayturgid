#!/usr/bin/env python3
"""Build safe commands for the control-node SecretSpec boundary.

Secrets live in the canonical vault at ``/var/db/sudo-secretspec`` and are
reached through the ``sudo-secretspec`` companion, which brokers every
operation through a root-owned, allowlisted binary and records it in a
hash-chained audit ledger.  This module keeps the caller-side interface narrow:
only ``run -- ansible-playbook ...`` is approved here.

The companion elevates itself -- it invokes the NOPASSWD broker path
internally -- so call sites must NOT wrap it in ``sudo``.  It fetches the
environment from the broker and then ``exec``s the target as the *invoking*
user, so Ansible still runs as ``djbclark`` with a writable HOME and no shell
evaluation.  It also purges every ``SECRETSPEC_*`` variable from the inherited
environment before the exec.

A same-UID caller can still invoke an approved operation when the sudoers rule
is granted to that UID; UNIX credentials cannot distinguish two processes with
the same UID.  The enforceable boundary here is that malformed arguments,
caller-selected SecretSpec subcommands, environment injection, and arbitrary
commands are rejected by the broker and by this selector.

CI and other machines without the boundary use direct ``secretspec`` with their
normal provider configuration.  Set ``STAYTURGID_SECRETSPEC_DIRECT=1`` to
exercise that path deliberately.

Replaced the ``stayturgid-secretspec-wrapper.sh`` boundary, retired 2026-08-15
when the vault moved to ``/var/db/sudo-secretspec``.  The wrapper ran as the
separate ``_secretspec`` service account, which cannot read the canonical
vault, and its ``sync_source`` would have chowned that vault away from
``_sudo_secretspec``.
"""

from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache

BOUNDARY_BIN = "sudo-secretspec"
VAULT_DIR = "/var/db/sudo-secretspec"
FORCE_DIRECT_ENV = "STAYTURGID_SECRETSPEC_DIRECT"
APPROVED_EXECUTABLE = "ansible-playbook"

# The single secret this module will fetch by name. The boundary itself accepts
# any declared name; keeping the caller-side list to one keeps a compromised
# call site from turning this seam into a general `get`.
APPROVED_SECRET = "FIRERPA_MCP_TOKEN"

# Recorded verbatim in the broker's audit ledger for every approved operation.
RUN_REASON = "stayturgid approved ansible automation"
TOKEN_REASON = "stayturgid firerpa mcp bearer token"


@lru_cache(maxsize=1)
def boundary_available() -> bool:
    """True when the privilege-separated SecretSpec path is usable here."""
    if os.environ.get(FORCE_DIRECT_ENV) == "1":
        return False
    if shutil.which(BOUNDARY_BIN) is not None:
        return True
    if os.path.isdir(VAULT_DIR):
        print(
            f"WARNING: {VAULT_DIR} exists but {BOUNDARY_BIN} is not on PATH — "
            "falling back to direct secretspec, without privilege separation. "
            "See docs/operations/secretspec-secrets-management.md to repair.",
            file=sys.stderr,
        )
    return False


def _approved_automation(command: tuple[str, ...]) -> bool:
    """Reject shell interpreters and non-Ansible automation at this seam."""
    return bool(command) and command[0] == APPROVED_EXECUTABLE


def secretspec_command(*args: str) -> list[str]:
    """Return an approved SecretSpec command for this machine.

    Only ``run -- ansible-playbook ...`` is accepted on the brokered path.
    """
    if not args:
        raise ValueError("SecretSpec command cannot be empty")
    if args[:2] != ("run", "--"):
        if boundary_available():
            raise ValueError("arbitrary SecretSpec subcommands are unavailable through the boundary")
        return ["secretspec", *args]

    command = tuple(args[2:])
    if boundary_available():
        if not _approved_automation(command):
            raise ValueError("only ansible-playbook is approved through the boundary")
        # The broker audits the target by basename and refuses anything
        # containing a path separator, so a caller must not pass an absolute
        # path. Fail here with a clear message rather than at the broker.
        if os.sep in command[0]:
            raise ValueError("the approved executable must be a bare name, not a path")
        return [BOUNDARY_BIN, "run", "--reason", RUN_REASON, "--", *command]
    return ["secretspec", *args]


def secretspec_run(*command: str) -> list[str]:
    """Convenience wrapper for the approved ``run -- ansible-playbook`` form."""
    return secretspec_command("run", "--", *command)


def secretspec_token_command(name: str) -> list[str]:
    """Return the fixed FIRERPA token fetch; no caller-selected ``get``.

    NOTE: ``FIRERPA_MCP_TOKEN`` is not declared in the tracked manifest, so this
    resolves to nothing on the control node today and
    ``control/bin/firerpa_mcp.py`` falls back to starting its HTTP transport
    unauthenticated. That predates this module's rewrite -- the retired wrapper
    asked for a lowercase ``firerpa_mcp_token`` that was equally undeclared --
    and declaring the secret is what fixes it, not a change here.
    """
    if name != APPROVED_SECRET:
        raise ValueError(f"only {APPROVED_SECRET} is available through the boundary")
    if boundary_available():
        return [BOUNDARY_BIN, "get", APPROVED_SECRET, "--reason", TOKEN_REASON]
    return ["secretspec", "get", name]
