#!/usr/bin/env python3
"""Build the argv that runs a command with fleet secrets in its environment.

On the control node, secrets live in a ``0700`` vault owned by a dedicated
``_secretspec`` service account and are reachable only through one narrowly
scoped sudoers rule — see ``docs/operations/secretspec-secrets-management.md``
for the full design and why the wrapper script exists at all.

Anywhere that boundary does not exist — CI runners above all — there is no
``_secretspec`` user and no wrapper, so ``sudo -n -u _secretspec ...`` fails
with ``sudo: unknown user _secretspec``. That is what turned stayturgid's
``test`` workflow red on master from #247 onward. Callers therefore go through
:func:`secretspec_command`, which uses the privilege-separated path when it is
actually present and otherwise invokes ``secretspec`` directly, letting
``SECRETSPEC_FILE`` / ``SECRETSPEC_PROVIDER`` from the environment point it at
the right spec (exactly what ``.github/workflows`` already exports).

The fallback is deliberately *not* silent when it looks like a broken control
node: if the vault directory exists but the wrapper or the service account does
not, that is a half-installed boundary rather than a machine that never had one,
and :func:`secretspec_command` warns on stderr before falling back.

Note for test authors: callers reach this module by *both* spellings --
``import secretspec_exec`` (control/lib on sys.path) and
``from control.lib.secretspec_exec import ...`` -- matching how
``ansible_context`` is already imported repo-wide. Those are two distinct module
objects with independent :func:`wrapper_available` caches, so anything
monkeypatching the selector must patch both; see the
``_secretspec_wrapper_present`` fixture in tests/python/conftest.py.
"""

from __future__ import annotations

import os
import pwd
import sys
from functools import lru_cache

WRAPPER_PATH = "/usr/local/libexec/stayturgid-secretspec-wrapper.sh"
SERVICE_USER = "_secretspec"
VAULT_DIR = "/var/db/stayturgid-secrets"

#: Set to "1" to force the direct path even on a fully provisioned control node.
#: Intended for local debugging, not for automation.
FORCE_DIRECT_ENV = "STAYTURGID_SECRETSPEC_DIRECT"


def _service_user_exists() -> bool:
    try:
        pwd.getpwnam(SERVICE_USER)
    except KeyError:
        return False
    return True


@lru_cache(maxsize=1)
def wrapper_available() -> bool:
    """True when the privilege-separated secretspec path is usable here.

    Cached: every input is machine-level state that cannot change within a
    single process run, and some callers build commands in a loop.
    """
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


def secretspec_command(*args: str) -> list[str]:
    """Return the argv that runs ``secretspec <args>`` for this machine.

    Arguments map 1:1 onto ``secretspec``'s own CLI in both modes — the wrapper
    script ``exec``s ``secretspec ... "$@"`` — so callers pass e.g.
    ``("run", "--", "ansible-playbook", ...)`` or ``("get", "some_token")``
    and get identical semantics either way.
    """
    if wrapper_available():
        return ["sudo", "-n", "-u", SERVICE_USER, WRAPPER_PATH, *args]
    return ["secretspec", *args]


def secretspec_run(*command: str) -> list[str]:
    """Convenience wrapper for the overwhelmingly common ``run --`` form."""
    return secretspec_command("run", "--", *command)
