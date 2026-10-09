"""Operator notices from the control node go to Hermes, never to macOS notifications.

The operator reads alerts in the Hermes Telegram Inbox topic (2026-10-05: "I want only
hermes"), so every control script sends its notices through here rather than osascript.
Callers keep their own gating (cooldowns, state transitions): each call is one message.

Why ``hermes send`` and not ``hermes-ping``: the operator rule "use hermes-ping, never a
bare hermes send" (2026-10-06) is for agent sessions. hermes-ping's value is naming the
interface, workspace/tab/pane and session the ping came from; a launchd job has none of
those, and hermes-ping lives in the operator's site-djbclark checkout, which this product
repo must not depend on. The title argument says which control job sent the notice.
"""

from __future__ import annotations

import os
import shutil
import subprocess

HERMES_TARGET = "telegram:838808636:22158"


def _hermes_bin() -> str:
    # launchd jobs run with a minimal PATH that may not include ~/.local/bin.
    return shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes")


def notify(title: str, message: str) -> bool:
    """Send one notice; never raises (a dead transport must not break a monitor).

    Returns True when ``hermes send`` exited 0. Callers that remember what they
    already announced must record it only on True, or a gateway outage loses
    the alert; fire-and-forget callers can ignore the result.
    """
    try:
        result = subprocess.run(
            [_hermes_bin(), "send", "-t", HERMES_TARGET, "%s: %s" % (title, message)],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
