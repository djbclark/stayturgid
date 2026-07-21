#!/usr/bin/env python3
"""Clear PiP and floating overlays before Mac-side UI automation.

YouTube PiP (and similar) can steal taps and hide drawer rows. This module
detects obstructions via dumpsys (no uiautomator unless needed) and dismisses
them with the cheapest reliable action first.
"""

from __future__ import annotations

import re
import time

from ui_parse import parse_content_desc_center, parse_text_center

PIP_ACTIVITY_MARKERS = (
    "mIsInPictureInPictureMode=true",
    "mLastReportedPictureInPictureMode=true",
    "mode=pinned",
    "rootPinnedTask=Task=",
)
PIP_STACK_MARKERS = (
    "mWindowingMode=pinned",
    "windowingMode=pinned",
)
PIP_WINDOW_MARKERS = (
    "PipMenu",
    "pip_menu",
    "pip_input_consumer",
    "PictureInPicture",
    "pip_expand",
    "PinnedTaskController",
)
PIP_CLOSE_LABELS = (
    "Close",
    "Dismiss",
    "Exit",
    "Exit picture-in-picture",
    "Close picture-in-picture",
)
PROTECTED_PACKAGES = frozenset(
    {
        "org.autojs.autojs6",
        "com.termux",
        "com.termux.api",
        "com.termux.boot",
        "moe.shizuku.privileged.api",
        "com.android.settings",
        "com.android.systemui",
        "com.sec.android.app.launcher",
    }
)

_ROOT_TASK_RE = re.compile(r"RootTask id=(\d+)\b", re.IGNORECASE)
_TASK_PKG_RE = re.compile(r"taskId=\d+:\s*([a-zA-Z0-9_.]+)/")
_PKG_FROM_ACTIVITY_RE = re.compile(r"\b([a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)/[a-zA-Z0-9_.$]+")
_WINDOW_PKG_RE = re.compile(r"package=([a-zA-Z0-9_.]+)")
_FRAME_RE = re.compile(r"frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_ROOT_PINNED_TASK_RE = re.compile(r"rootPinnedTask=Task=(\d+)")
_PINNED_ACTIVITY_TASK_RE = re.compile(r"A=\d+:([a-zA-Z0-9_.]+)\b[^\n]*mode=pinned")


def parse_pinned_stacks(stack_dump: str) -> list[tuple[int, str]]:
    """Return (stack_id, package) for pinned / PiP stacks."""
    text = (stack_dump or "").replace("\r", "")
    found: list[tuple[int, str]] = []
    for match in _ROOT_TASK_RE.finditer(text):
        stack_id = int(match.group(1))
        chunk = text[match.start() : match.start() + 900]
        if not any(marker in chunk for marker in PIP_STACK_MARKERS):
            continue
        pkg_match = _TASK_PKG_RE.search(chunk)
        if pkg_match:
            found.append((stack_id, pkg_match.group(1)))
    return found


def _packages_from_pinned_activity_tasks(activity_dump: str) -> set[str]:
    packages: set[str] = set()
    text = (activity_dump or "").replace("\r", "")
    for match in _PINNED_ACTIVITY_TASK_RE.finditer(text):
        packages.add(match.group(1))
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if "packageName=" not in line:
            continue
        nearby = "\n".join(lines[max(0, idx - 3) : idx + 4])
        if "mode=pinned" not in nearby and "mWindowingMode=pinned" not in nearby:
            continue
        pkg_match = re.search(r"packageName=([a-zA-Z0-9_.]+)", line)
        if pkg_match:
            packages.add(pkg_match.group(1))
    return packages


def _packages_from_pip_windows(window_dump: str) -> set[str]:
    packages: set[str] = set()
    text = window_dump or ""
    if not any(marker in text for marker in PIP_WINDOW_MARKERS):
        return packages
    for line in text.splitlines():
        if not any(marker in line for marker in PIP_WINDOW_MARKERS + ("mWindowingMode=pinned",)):
            continue
        match = re.search(
            r"\b([a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)/[a-zA-Z0-9_.$]+",
            line,
        )
        if match:
            packages.add(match.group(1))
        match = _WINDOW_PKG_RE.search(line)
        if match:
            packages.add(match.group(1))
    return packages


def pinned_stack_targets(activity_dump: str, stack_dump: str) -> list[tuple[int, str]]:
    """Pinned stack ids to remove, with best-effort package label for logging."""
    found = parse_pinned_stacks(stack_dump)
    if found:
        return found
    text = (activity_dump or "").replace("\r", "")
    match = _ROOT_PINNED_TASK_RE.search(text)
    if not match:
        return []
    stack_id = int(match.group(1))
    pkgs = _packages_from_pinned_activity_tasks(text)
    if pkgs:
        return [(stack_id, sorted(pkgs)[0])]
    return [(stack_id, "unknown")]


def _packages_in_pip_activity(activity_dump: str) -> set[str]:
    packages: set[str] = set()
    lines = (activity_dump or "").splitlines()
    for idx, line in enumerate(lines):
        if not any(marker in line for marker in PIP_ACTIVITY_MARKERS):
            continue
        for j in range(max(0, idx - 4), min(len(lines), idx + 5)):
            match = _PKG_FROM_ACTIVITY_RE.search(lines[j])
            if match:
                packages.add(match.group(1))
    return packages


def pip_packages(activity_dump: str, stack_dump: str, window_dump: str = "") -> set[str]:
    """Packages that appear to be in PiP or a pinned overlay."""
    packages: set[str] = set()
    packages.update(_packages_in_pip_activity(activity_dump))
    packages.update(_packages_from_pinned_activity_tasks(activity_dump))
    for _stack_id, pkg in parse_pinned_stacks(stack_dump):
        packages.add(pkg)
    packages.update(_packages_from_pip_windows(window_dump))
    return {p for p in packages if p and p not in PROTECTED_PACKAGES}


def pip_obstruction_detected(
    activity_dump: str,
    stack_dump: str,
    window_dump: str = "",
    *,
    screen_size: tuple[int, int] | None = None,
) -> bool:
    combined = "\n".join((activity_dump or "", stack_dump or "", window_dump or ""))
    if any(marker in combined for marker in PIP_ACTIVITY_MARKERS + PIP_STACK_MARKERS):
        return True
    if parse_pinned_stacks(stack_dump):
        return True
    if any(marker in (window_dump or "") for marker in PIP_WINDOW_MARKERS):
        return True
    if screen_size and _has_small_floating_window(window_dump or "", screen_size):
        return True
    return False


def _has_small_floating_window(window_dump: str, screen_size: tuple[int, int]) -> bool:
    """Heuristic: visible app window much smaller than the display (typical PiP)."""
    sw, sh = screen_size
    if sw <= 0 or sh <= 0:
        return False
    screen_area = sw * sh
    for match in _FRAME_RE.finditer(window_dump):
        x1, y1, x2, y2 = (int(match.group(i)) for i in range(1, 5))
        w, h = max(0, x2 - x1), max(0, y2 - y1)
        if w < 80 or h < 80:
            continue
        area = w * h
        if area < screen_area * 0.22 and area > screen_area * 0.01:
            # Ignore nav/status slivers; PiP is usually 5–20% of screen.
            chunk_start = max(0, match.start() - 400)
            chunk = window_dump[chunk_start : match.end() + 200]
            if "isReadyForDisplay()=true" not in chunk and "mViewVisibility=0x0" not in chunk:
                continue
            if _WINDOW_PKG_RE.search(chunk):
                return True
    return False


def _try_ui_close_pip(serial: str, shell) -> bool:
    """Tap PiP close controls if visible in the current hierarchy."""
    rc, _ = shell(serial, "uiautomator", "dump", "/sdcard/stayturgid_ui_clearance.xml")
    if rc != 0:
        return False
    rc, out = shell(serial, "cat", "/sdcard/stayturgid_ui_clearance.xml")
    if rc != 0:
        return False
    xml = (out or "").replace("\r", "")
    for label in PIP_CLOSE_LABELS:
        point = parse_text_center(xml, label)
        if not point:
            point = parse_content_desc_center(xml, label)
        if point:
            shell(serial, "input", "tap", str(point[0]), str(point[1]))
            time.sleep(0.5)
            return True
    return False


def clear_ui_obstructions(serial: str, shell) -> list[str]:
    """Dismiss PiP / floating overlays. Returns human-readable actions taken."""
    actions: list[str] = []
    rc, size_out = shell(serial, "wm", "size")
    screen_size = (1080, 2400)
    if rc == 0:
        for line in (size_out or "").splitlines():
            if "Physical size:" in line:
                parts = line.split(":")[-1].strip().split("x")
                if len(parts) == 2:
                    screen_size = (int(parts[0]), int(parts[1]))

    for _attempt in range(3):
        rc_a, activity = shell(serial, "dumpsys", "activity", "activities")
        rc_s, stack = shell(serial, "cmd", "activity", "stack", "list")
        rc_w, window = shell(serial, "dumpsys", "window", "windows")
        if rc_a != 0 and rc_s != 0:
            break
        if not pip_obstruction_detected(activity or "", stack or "", window or "", screen_size=screen_size):
            break

        for stack_id, pkg in pinned_stack_targets(activity or "", stack or ""):
            rc, _ = shell(serial, "cmd", "activity", "stack", "remove", str(stack_id))
            if rc == 0:
                actions.append("pinned-stack-remove:%s#%s" % (pkg, stack_id))

        shell(serial, "am", "broadcast", "-a", "android.intent.action.CLOSE_SYSTEM_DIALOGS")
        shell(serial, "input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.35)
        shell(serial, "input", "keyevent", "KEYCODE_ESCAPE")
        time.sleep(0.35)

        if _try_ui_close_pip(serial, shell):
            actions.append("ui-tap-pip-close")

        time.sleep(0.35)
        rc_a2, activity2 = shell(serial, "dumpsys", "activity", "activities")
        rc_s2, stack2 = shell(serial, "cmd", "activity", "stack", "list")
        rc_w2, window2 = shell(serial, "dumpsys", "window", "windows")
        still_pip = pip_obstruction_detected(activity2 or "", stack2 or "", window2 or "", screen_size=screen_size)
        if still_pip:
            for pkg in sorted(_packages_from_pinned_activity_tasks(activity2 or "")):
                if pkg in PROTECTED_PACKAGES:
                    continue
                rc, _ = shell(serial, "am", "kill", pkg)
                if rc == 0:
                    actions.append("am-kill-pip:%s" % pkg)

        time.sleep(0.5)

    return actions
