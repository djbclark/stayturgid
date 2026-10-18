"""Back up and restore Termux's device-native adb key through the secret vault.

Termux's adb identifies itself to adbd with ``~/.android/adbkey``. A reinstall wipes
it, Termux generates a new one, and adbd raises a fresh "Allow USB debugging?"
dialog (and Samsung drops it on a lock screen). Android never revokes old keys
(t2e's key store holds three stale Termux keys), so the old key is still
authorised: put it back before Termux's first adb call and nobody is asked.

``capture`` stores a phone's key in the vault once adbd's key store holds it
(``TERMUX_ADBKEY_<HOST>``, through ``sudo-secretspec``; the value goes in on stdin and
is never printed, logged or written to disk). ``restore`` writes it back, only when
the phone has no ``adbkey`` yet. The restored key is the same phone's own former
key, so ``fleet_adbkey.yml``'s rule holds: ``~/.android/adbkey`` stays the
device-native identity and the fleet key is peer-help only.
"""

from __future__ import annotations

import base64
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_COLLECTION_UTILS = REPO_ROOT / "ansible_collections" / "stayturgid" / "termux" / "plugins" / "module_utils"
if str(_COLLECTION_UTILS) not in sys.path:
    sys.path.insert(0, str(_COLLECTION_UTILS))

import secretspec_exec as se
import termux_run_as as tr

VALUE_PREFIX = "adbkey1"
VAULT_TIMEOUT_S = 60
ADB_TIMEOUT_S = 30


class VaultError(RuntimeError):
    """The vault refused or failed an adb key operation (the message never holds a value)."""


def pack(private: str, public: str) -> str:
    """One line for the vault: ``adbkey1.<b64 private>.<b64 public>`` ('.' is not base64)."""
    if "PRIVATE KEY" not in private or not tr.pubkey_blob(public):
        raise ValueError("not an adb key pair")
    return ".".join(
        [
            VALUE_PREFIX,
            base64.b64encode(private.encode()).decode(),
            base64.b64encode(public.encode()).decode(),
        ]
    )


def unpack(value: str) -> tuple[str, str]:
    parts = value.strip().split(".")
    if len(parts) != 3 or parts[0] != VALUE_PREFIX:
        raise ValueError("stored adb key has an unknown format")
    try:
        private, public = (base64.b64decode(p, validate=True).decode() for p in parts[1:])
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("stored adb key is not valid base64") from exc
    if "PRIVATE KEY" not in private or not tr.pubkey_blob(public):
        raise ValueError("stored adb key is not an adb key pair")
    return private, public


def _vault(action: str, name: str, *, value: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        se.secretspec_adbkey_command(action, name),
        input=value,
        capture_output=True,
        text=True,
        timeout=VAULT_TIMEOUT_S,
        check=False,
    )


def vault_get(name: str) -> str | None:
    """The stored value, or None when the name is undeclared or holds none."""
    done = _vault("get", name)
    value = (done.stdout or "").strip()
    return value if done.returncode == 0 and value else None


def vault_set(name: str, value: str) -> None:
    """Store *value*, declaring the name first when the vault does not know it yet."""
    if _vault("set", name, value=value).returncode == 0:
        return
    declared = _vault("add", name)
    if declared.returncode != 0:
        raise VaultError("cannot declare %s in the vault: %s" % (name, (declared.stderr or "").strip()[:200]))
    done = _vault("set", name, value=value)
    if done.returncode != 0:
        raise VaultError("cannot store %s in the vault: %s" % (name, (done.stderr or "").strip()[:200]))


def adb_run(cmd: list[str]) -> tuple[int, str, str]:
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=ADB_TIMEOUT_S, check=False)
    return done.returncode, done.stdout or "", done.stderr or ""


def adb_run_with_input(cmd: list[str], data: str) -> tuple[int, str, str]:
    """Run an adb command with *data* on its stdin, so a private key never appears in argv."""
    done = subprocess.run(cmd, input=data, capture_output=True, text=True, timeout=ADB_TIMEOUT_S, check=False)
    return done.returncode, done.stdout or "", done.stderr or ""


def read_device_key(serial: str, run=adb_run) -> tuple[str, str] | None:
    """(private, public) text of Termux's adb key over run-as, or None when it has none."""
    private = tr.read_termux_file(run, serial, tr.ADBKEY_PRIVATE)
    public = tr.read_termux_file(run, serial, tr.ADBKEY_PUBLIC)
    if not private or not public:
        return None
    return private, public


def capture(host: str, serial: str, *, run=adb_run) -> str:
    """Store the phone's adb key in the vault once adbd authorises it; one status line."""
    name = se.adbkey_secret_name(host)
    state = tr.adbkey_state(run, serial)
    if state != "authorized":
        return "capture: skipped for %s (Termux's adb key is %s, not yet in adbd's key store)" % (host, state)
    pair = read_device_key(serial, run)
    if pair is None:
        return "capture: skipped for %s (Termux's adb key could not be read over run-as)" % host
    value = pack(*pair)
    if vault_get(name) == value:
        return "capture: unchanged, %s already holds this key" % name
    vault_set(name, value)
    if vault_get(name) != value:
        raise VaultError("%s did not read back after it was stored" % name)
    return "capture: stored %s" % name


def _write_script(path: str, mode: str) -> str:
    """Termux shell that writes its stdin to *path* atomically with *mode* (key text never in argv)."""
    quoted = shlex.quote(path)
    return (
        tr.TERMUX_ENV
        + "set -e\n"
        + "umask 077\n"
        + 'mkdir -p "$HOME/.android"\n'
        + 'chmod 700 "$HOME/.android"\n'
        + "cat > %s.stg-new\n" % quoted
        + "chmod %s %s.stg-new\n" % (mode, quoted)
        + "mv -f %s.stg-new %s\n" % (quoted, quoted)
    )


def _write_through_run_as(serial: str, path: str, mode: str, text: str, run_with_input) -> None:
    cmd = [
        "adb",
        "-s",
        serial,
        "shell",
        "run-as",
        tr.TERMUX_PKG,
        tr.TERMUX_BASH,
        "-c",
        shlex.quote(_write_script(path, mode)),
    ]
    rc, _out, err = run_with_input(cmd, text)
    if rc != 0:
        raise RuntimeError("writing %s on %s over run-as failed: %s" % (path, serial, err.strip()[:200]))


def restore(host: str, serial: str, *, run=adb_run, run_with_input=adb_run_with_input) -> str:
    """Put the phone's own stored key back before its Termux first calls adb; one status line.

    Only when the phone has no ``adbkey`` yet: a live key is never replaced. The public
    half is written first and the private half last, atomically, so a private key on the
    phone always comes with its public key.
    """
    name = se.adbkey_secret_name(host)
    stored = vault_get(name)
    if stored is None:
        return "restore: nothing stored for %s (%s)" % (host, name)
    private, public = unpack(stored)
    if not tr.run_as_available(run, serial):
        return "restore: skipped for %s (run-as com.termux is not available yet)" % host
    if tr.read_termux_file(run, serial, tr.ADBKEY_PRIVATE):
        return "restore: skipped for %s (it already has an adb key; left alone)" % host
    _write_through_run_as(serial, tr.ADBKEY_PUBLIC, "0644", public, run_with_input)
    _write_through_run_as(serial, tr.ADBKEY_PRIVATE, "0600", private, run_with_input)
    written = tr.read_termux_file(run, serial, tr.ADBKEY_PUBLIC)
    if tr.pubkey_blob(written) != tr.pubkey_blob(public):
        raise RuntimeError("the restored adb key on %s did not read back" % serial)
    return "restore: restored %s's own adb key from %s" % (host, name)
