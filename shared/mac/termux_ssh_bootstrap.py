"""Bootstrap Termux SSH authorized_keys over adb (no ssh-copy-id).

Uses ``run-as com.termux`` on debuggable Termux builds (fleet default). Stages
public keys and a shell script under ``/sdcard/stayturgid/tmp/`` when needed.
Never reads or writes private keys except for optional local SSH verification.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

TERMUX_PKG = "com.termux"
TERMUX_HOME = "/data/data/com.termux/files/home"
TERMUX_PREFIX = "/data/data/com.termux/files/usr"
TERMUX_BASH = f"{TERMUX_PREFIX}/bin/bash"
TERMUX_SSHD = f"{TERMUX_PREFIX}/bin/sshd"
SD_TMP = "/sdcard/stayturgid/tmp"
STAGING_KEYS = f"{SD_TMP}/bootstrap_keys.pub"
STAGING_SCRIPT = f"{SD_TMP}/bootstrap_ssh.sh"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR"]

TERMUX_ENV = f"""\
export PATH={TERMUX_PREFIX}/bin:{TERMUX_PREFIX}/sbin:$PATH
export HOME={TERMUX_HOME}
export PREFIX={TERMUX_PREFIX}
export TMPDIR={TERMUX_PREFIX}/tmp
export LD_LIBRARY_PATH={TERMUX_PREFIX}/lib"""


def default_keys_dir() -> Path:
    return Path(os.environ.get("STAYTURGID_SSH_KEYS_DIR", Path.home() / ".ssh"))


def discover_pubkey_paths(
    keys_dir: Path | None = None,
    explicit: list[str | Path] | None = None,
) -> list[Path]:
    if explicit:
        return [Path(p) for p in explicit]
    root = keys_dir or default_keys_dir()
    return sorted(root.glob("*.pub"))


def read_pubkey_lines(paths: list[Path]) -> list[str]:
    lines: list[str] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
    return lines


def install_keys_shell(keys_file: str) -> str:
    quoted = shlex.quote(keys_file)
    return f"""\
{TERMUX_ENV}
set -e
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
while IFS= read -r line || [ -n "$line" ]; do
  [ -z "$line" ] && continue
  case "$line" in \\#*) continue ;; esac
  if ! grep -qF "$line" "$HOME/.ssh/authorized_keys" 2>/dev/null; then
    printf '%s\\n' "$line" >> "$HOME/.ssh/authorized_keys"
  fi
done < {quoted}
"""


def install_openssh_shell() -> str:
    return f"""\
{TERMUX_ENV}
set -e
if [ ! -x {shlex.quote(TERMUX_SSHD)} ]; then
  pkg install -y openssh
fi
test -x {shlex.quote(TERMUX_SSHD)}
"""


def start_sshd_shell() -> str:
    return f"""\
{TERMUX_ENV}
set -e
if ! pgrep -x sshd >/dev/null 2>&1; then
  sshd
fi
pgrep -x sshd >/dev/null
"""


def _adb(serial: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", serial, *args],
        capture_output=True,
        text=True,
        **kwargs,
    )


def run_as_available(serial: str) -> bool:
    result = _adb(serial, "shell", "run-as", TERMUX_PKG, "true")
    return result.returncode == 0


def termux_installed(serial: str) -> bool:
    result = _adb(serial, "shell", "pm", "path", TERMUX_PKG)
    return result.returncode == 0 and "package:" in (result.stdout or "")


def run_as_termux(serial: str, script: str, *, timeout: int = 120) -> tuple[int, str, str]:
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "run-as", TERMUX_PKG, TERMUX_BASH, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def _ensure_sd_tmp(serial: str) -> None:
    _adb(serial, "shell", "mkdir", "-p", SD_TMP)


def _push_text(serial: str, local_path: Path, remote_path: str) -> None:
    result = _adb(serial, "push", str(local_path), remote_path)
    if result.returncode != 0:
        raise RuntimeError(
            "adb push %s failed: %s" % (remote_path, (result.stderr or result.stdout).strip())
        )


def push_authorized_keys(serial: str, pubkey_lines: list[str]) -> None:
    if not pubkey_lines:
        raise ValueError("no SSH public keys to install")
    _ensure_sd_tmp(serial)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as keys_tmp:
        keys_tmp.write("\n".join(pubkey_lines) + "\n")
        keys_path = Path(keys_tmp.name)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as script_tmp:
        script_tmp.write(install_keys_shell(STAGING_KEYS) + "\n")
        script_path = Path(script_tmp.name)
    try:
        _push_text(serial, keys_path, STAGING_KEYS)
        _push_text(serial, script_path, STAGING_SCRIPT)
        rc, out, err = run_as_termux(serial, f"bash {shlex.quote(STAGING_SCRIPT)}")
        if rc != 0:
            detail = (err or out).strip() or "run-as install failed"
            raise RuntimeError(detail)
    finally:
        keys_path.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)


def ensure_openssh(serial: str) -> None:
    rc, out, err = run_as_termux(serial, install_openssh_shell(), timeout=300)
    if rc != 0:
        raise RuntimeError((err or out).strip() or "openssh install failed")


def ensure_sshd(serial: str) -> None:
    rc, out, err = run_as_termux(serial, start_sshd_shell())
    if rc != 0:
        raise RuntimeError((err or out).strip() or "sshd start failed")


def forward_local_ssh(serial: str) -> None:
    _adb(serial, "forward", "tcp:8022", "tcp:8022")


def verify_ssh_local(private_key: Path) -> bool:
    result = subprocess.run(
        [
            "ssh",
            *SSH_OPTS,
            "-o",
            "StrictHostKeyChecking=no",
            "-i",
            str(private_key),
            "-p",
            "8022",
            "localhost",
            "echo",
            "termux_ssh_ok",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "termux_ssh_ok" in (result.stdout or "")


def verify_ssh_alias(host: str) -> bool:
    result = subprocess.run(
        ["ssh", *SSH_OPTS, host, "echo", "termux_ssh_ok"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "termux_ssh_ok" in (result.stdout or "")


def pick_private_key(keys_dir: Path | None = None) -> Path | None:
    root = keys_dir or default_keys_dir()
    for candidate in (root / "termux_key", *sorted(root.glob("id_*"))):
        if candidate.is_file() and not str(candidate).endswith(".pub"):
            return candidate
    return None


def bootstrap_serial(
    serial: str,
    *,
    pubkey_paths: list[Path] | None = None,
    keys_dir: Path | None = None,
    install_openssh: bool = True,
    forward: bool = True,
    verify_alias: str = "",
) -> None:
    if not termux_installed(serial):
        raise RuntimeError("%s is not installed on %s" % (TERMUX_PKG, serial))
    if not run_as_available(serial):
        raise RuntimeError(
            "run-as %s failed on %s — need a debuggable Termux build "
            "(see HACKING.md §5b) or bootstrap manually with ssh-copy-id"
            % (TERMUX_PKG, serial)
        )

    paths = pubkey_paths if pubkey_paths is not None else discover_pubkey_paths(keys_dir)
    lines = read_pubkey_lines(paths)
    if not lines:
        raise RuntimeError("no *.pub keys found under %s" % (keys_dir or default_keys_dir()))

    if install_openssh:
        ensure_openssh(serial)
    push_authorized_keys(serial, lines)
    ensure_sshd(serial)

    local_ok = False
    if forward:
        forward_local_ssh(serial)
        key = pick_private_key(keys_dir)
        if key:
            local_ok = verify_ssh_local(key)

    if verify_alias:
        if not verify_ssh_alias(verify_alias) and not local_ok:
            raise RuntimeError("SSH to %s failed after bootstrap" % verify_alias)
    elif forward and not local_ok:
        raise RuntimeError("SSH via adb forward tcp:8022 failed after bootstrap")


def bootstrap_alias(
    alias: str,
    resolve_adb,
    *,
    verify_alias: str | None = None,
    **kwargs,
) -> None:
    serial = resolve_adb(alias)
    bootstrap_serial(
        serial,
        verify_alias=verify_alias if verify_alias is not None else alias,
        **kwargs,
    )
