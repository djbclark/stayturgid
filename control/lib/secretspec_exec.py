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
exercise that path deliberately on such a machine.

A *provisioned* control node (one where the canonical vault directory exists)
never falls back (#287): if the companion is missing there, or the direct path
is forced, building a command raises :class:`BoundaryUnavailable` and the
dependent work stops.  A broken broker is a repair job, not a licence to read
secrets from some other manifest or provider.  For the same reason this seam
refuses the SecretSpec selectors that point at an alternate manifest
(``--file``/``-f`` and ``SECRETSPEC_FILE``) on every path.  The
``SECRETSPEC_FILE`` check reads this process's inherited environment
(``os.environ``); a caller that passes its own ``env=`` to the child must
derive it from ``os.environ`` (every caller does today) or the guard does not
see what the child gets.  On the brokered path this is moot: the companion
purges ``SECRETSPEC_*`` before it execs.

Replaced the ``stayturgid-secretspec-wrapper.sh`` boundary, retired 2026-08-15
when the vault moved to ``/var/db/sudo-secretspec``.  The wrapper ran as the
separate ``_secretspec`` service account, which cannot read the canonical
vault, and its ``sync_source`` would have chowned that vault away from
``_sudo_secretspec``.
"""

from __future__ import annotations

import os
import shutil
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


# SecretSpec's own ways of pointing at a manifest other than the one the
# broker resolves. Neither has a legitimate use from automation in this repo.
ALTERNATE_MANIFEST_ENV = "SECRETSPEC_FILE"
ALTERNATE_MANIFEST_FLAGS = ("--file", "-f")

REPAIR_HINT = "See docs/operations/secretspec-boundary-lifecycle.md to repair."


class BoundaryUnavailable(RuntimeError):
    """The managed SecretSpec boundary is provisioned here but not usable.

    Raised instead of falling back to direct ``secretspec``: on a provisioned
    control node a broker failure stops dependent work (#287).
    """


def _provisioned() -> bool:
    """True when this machine carries the canonical vault."""
    return os.path.isdir(VAULT_DIR)


@lru_cache(maxsize=1)
def boundary_available() -> bool:
    """True when the privilege-separated SecretSpec path is usable here.

    False only on a machine that was never provisioned with the vault (CI, a
    fresh checkout elsewhere). On a provisioned control node this either
    returns True or raises :class:`BoundaryUnavailable`; it never selects the
    direct path there.
    """
    if os.environ.get(FORCE_DIRECT_ENV) == "1":
        if _provisioned():
            raise BoundaryUnavailable(
                f"{FORCE_DIRECT_ENV}=1 is refused on a provisioned control node: "
                f"{VAULT_DIR} is the only secret store here. Unset it to use {BOUNDARY_BIN}."
            )
        return False
    if shutil.which(BOUNDARY_BIN) is not None:
        return True
    if _provisioned():
        raise BoundaryUnavailable(
            f"{VAULT_DIR} exists but {BOUNDARY_BIN} is not on PATH. Refusing to fall "
            f"back to direct secretspec or any other manifest. {REPAIR_HINT}"
        )
    return False


def _reject_alternate_manifest(args: tuple[str, ...]) -> None:
    """Refuse SecretSpec-level selectors for a different manifest.

    Only the arguments before ``--`` belong to SecretSpec; anything after it is
    the target command's own argv (``ansible-playbook -f 5`` is a fork count).
    """
    own = args[: args.index("--")] if "--" in args else args
    for arg in own:
        # `-fPATH` is clap's attached short form of `-f PATH`.
        if arg in ALTERNATE_MANIFEST_FLAGS or arg.startswith(("--file=", "-f")):
            raise ValueError(f"alternate SecretSpec manifest selector {arg!r} is not allowed")


def _approved_automation(command: tuple[str, ...]) -> bool:
    """Reject shell interpreters and non-Ansible automation at this seam."""
    return bool(command) and command[0] == APPROVED_EXECUTABLE


def secretspec_command(*args: str) -> list[str]:
    """Return an approved SecretSpec command for this machine.

    Only ``run -- ansible-playbook ...`` is accepted on the brokered path.
    """
    if not args:
        raise ValueError("SecretSpec command cannot be empty")
    _reject_alternate_manifest(args)
    brokered = boundary_available()
    if not brokered and os.environ.get(ALTERNATE_MANIFEST_ENV):
        # The companion purges SECRETSPEC_* before exec, so this only matters on
        # the direct path, where secretspec would honour it.
        raise ValueError(f"{ALTERNATE_MANIFEST_ENV} selects an alternate SecretSpec manifest; unset it")
    if args[:2] != ("run", "--"):
        if brokered:
            raise ValueError("arbitrary SecretSpec subcommands are unavailable through the boundary")
        return ["secretspec", *args]

    command = tuple(args[2:])
    if brokered:
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
    if os.environ.get(ALTERNATE_MANIFEST_ENV):
        raise ValueError(f"{ALTERNATE_MANIFEST_ENV} selects an alternate SecretSpec manifest; unset it")
    return ["secretspec", "get", name]
