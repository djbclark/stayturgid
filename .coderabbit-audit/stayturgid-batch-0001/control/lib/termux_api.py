"""Safe Termux:API invocation — avoid ResultReturner error toasts.

Termux:API talks to the CLI over a local socket. If we SIGKILL the CLI
(``termux-notification``, ``termux-torch``, …) before the app writes back,
the app posts a loud "Error in ResultReturner / Connection refused" toast.
That is usually harmless but noisy (especially on Samsung).

Rules used here:

1. Always ``start_new_session=True`` so an SSH/parent timeout does not
   tear down the API client mid-flight.
2. On soft timeout: **do not kill** the process group — orphan it and
   return. The socket can still complete; we just stop waiting.
3. Serialize calls with a tiny gap so bursts (torch on/off) do not race.
4. Fire-and-forget helpers (notify / toast / vibrate / torch) wait briefly
   then orphan — never SIGKILL.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Sequence

_FIRE_AND_FORGET = frozenset(
    {
        "termux-notification",
        "termux-notification-remove",
        "termux-toast",
        "termux-vibrate",
        "termux-torch",
        "termux-wallpaper",
        "termux-brightness",
        "termux-wake-lock",
        "termux-wake-unlock",
    }
)

_LAST_CALL_MONO = 0.0
_MIN_GAP_SEC = 0.08


def _basename(args: Sequence[str]) -> str:
    if not args:
        return ""
    return os.path.basename(str(args[0]))


def is_termux_api(args: Sequence[str]) -> bool:
    return _basename(args).startswith("termux-")


def is_fire_and_forget(args: Sequence[str]) -> bool:
    return _basename(args) in _FIRE_AND_FORGET


def _gap() -> None:
    global _LAST_CALL_MONO
    now = time.monotonic()
    wait = _MIN_GAP_SEC - (now - _LAST_CALL_MONO)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL_MONO = time.monotonic()


def run(
    args: Sequence[str],
    *,
    timeout: float | None = 15,
    input_text: str | None = None,
):
    """Run a command; never SIGKILL Termux:API clients on timeout.

    Returns ``subprocess.CompletedProcess`` or ``None`` on failure/timeout.
    Timed-out Termux:API processes are left running (orphaned in their own
    session) so ResultReturner can still finish the socket.
    """
    args = list(args)
    if is_termux_api(args):
        _gap()

    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired:
        # Orphan — do NOT killpg. Killing the CLI causes ResultReturner toasts.
        return None
    except OSError:
        return None


def run_ff(args: Sequence[str], *, timeout: float = 3.0):
    """Fire-and-forget Termux:API: wait briefly, then orphan (never kill)."""
    args = list(args)
    if is_termux_api(args):
        _gap()
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
    except OSError:
        return None
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        # Leave the process alone — socket may still complete.
        return subprocess.CompletedProcess(args, 0, "", "")


def notify(args: Sequence[str], *, timeout: float = 4.0):
    return run_ff(list(args), timeout=timeout)


def toast(message: str, *, timeout: float = 2.0):
    return run_ff(["termux-toast", message], timeout=timeout)


def vibrate(ms: int = 200, *, timeout: float = 2.0):
    return run_ff(["termux-vibrate", "-d", str(ms)], timeout=timeout)


def torch(state: str, *, timeout: float = 2.0):
    """state: 'on' | 'off'."""
    return run_ff(["termux-torch", state], timeout=timeout)


def pulse_torch(
    n: int = 1,
    *,
    on_s: float = 0.22,
    off_s: float = 0.18,
    torch_timeout: float = 2.0,
) -> None:
    for _ in range(max(0, n)):
        torch("on", timeout=torch_timeout)
        time.sleep(on_s)
        torch("off", timeout=torch_timeout)
        time.sleep(off_s)
