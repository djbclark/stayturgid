"""Every adb `input` event (tap, text, keyevent, swipe, ...) must run behind the inversion gate.

Display inversion is the visible "agent has the glass" signal
(docs/rules/screen-control-hold.md), and ScreenControlSession refuses input while
it is off. Code that calls `adb shell input` directly skips both: on 2026-10-17
the Termux bootstrap typed "sshd" into s24 and t2e with the colors normal, and
fleet_health_monitor pressed Enter on the 16 KB dialog the same way.

A new raw input call fails this test. Route it through ScreenControlSession, or
invert around it as termux_run_as.start_sshd_from_app does, then add it to
ALLOWED with the reason.
"""

import re
import subprocess
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The session implementations themselves, which own the gate.
GATE_MODULES = {
    "control/lib/screen_control.py",
    "device/termux/py/stayturgid_screen_control.py",
}

# path -> number of raw input calls expected there, and why each is allowed.
ALLOWED = {
    # Inverts the display around the keystrokes and refuses if it stays off.
    "ansible_collections/stayturgid/termux/plugins/module_utils/termux_run_as.py": 2,
    "control/lib/adb_cli.py": 1,
    # Called only from inside a held ScreenControlSession.
    "control/lib/ui_clearance.py": 3,
    "control/bin/h2_confirm_ui.py": 1,
    # Power keys (screen on/off), not UI driving.
    "device/termux/py/stayturgid_screen_awake_guard.py": 2,
    "device/termux/py/stayturgid_battery_alarm.py": 1,
}

EVENTS = r"(?:tap|text|keyevent|swipe|draganddrop|roll|motionevent|press)"
PATTERNS = (
    re.compile(r"""["']input["']\s*,\s*["']%s["']""" % EVENTS),  # argv lists
    re.compile(r"""\binput\s+%s\b""" % EVENTS),  # shell strings
)


def raw_input_calls() -> Counter[str]:
    files = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "*.py", "*.sh", "*.bash", "*.yml", "*.yaml", "*.j2"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    found: Counter[str] = Counter()
    for rel in files:
        if rel in GATE_MODULES or rel.startswith("tests/") or "/tests/" in rel or rel.startswith("docs/"):
            continue
        path = REPO / rel
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if any(p.search(line) for p in PATTERNS):
                found[rel] += 1
    return found


def test_no_ungated_screen_input():
    found = raw_input_calls()
    unexpected = {rel: n for rel, n in found.items() if n != ALLOWED.get(rel, 0)}
    stale = {rel: n for rel, n in ALLOWED.items() if rel not in found}
    assert not unexpected, (
        "raw adb input outside the inversion gate (path: calls found); route it through "
        "ScreenControlSession or invert around it, then update ALLOWED: %s" % unexpected
    )
    assert not stale, "ALLOWED lists files with no raw input calls left: %s" % stale
