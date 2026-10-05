"""Operator notices from the control node go to Hermes, never to macOS notifications.

The operator reads alerts in the Hermes Telegram Inbox topic (2026-10-05: "I want only
hermes"), so every control script sends its notices through here rather than osascript.
Callers keep their own gating (cooldowns, state transitions): each call is one message.
"""

from __future__ import annotations

import os
import shutil
import subprocess

HERMES_TARGET = "telegram:838808636:22158"


def _hermes_bin() -> str:
    # launchd jobs run with a minimal PATH that may not include ~/.local/bin.
    return shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes")


def notify(title: str, message: str) -> None:
    """Send one notice; never raises (a dead transport must not break a monitor)."""
    try:
        subprocess.run(
            [_hermes_bin(), "send", "-t", HERMES_TARGET, "%s: %s" % (title, message)],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
