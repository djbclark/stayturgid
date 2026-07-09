"""Handsets-backed UI driver for Mac fleet scripts (OPTIONS 57).

Starts a per-device Handsets daemon (app_process + adb forward) and exposes
text/CSS-like taps. Falls back to callers' raw dump+tap when Handsets is
unavailable.

Multi-device: stock ``hs use SERIAL`` rejects ``ip:5555`` / crowded
``adb devices`` lists — we push ``hs.jar``, bind a fixed port per alias, and
talk via ``hs --host 127.0.0.1 --port N``.

Do not run alongside uiautomator2 (exclusive UiAutomation slot).
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Callable

# AutoJs6 drawer: label TextView ~x=342, Switch ~x=669 → ~327px; 200 is too tight.
_SWITCH_NEAR_PX = 400
_UI_SWITCH_RE = re.compile(
    r"^\s*(?:tap\s+)?Switch\b.*?(\d+)\s*,\s*(\d+)\s*(.*)$",
    re.IGNORECASE,
)
_UI_LABEL_RE = re.compile(
    r'^\s*.*?"(?P<label>[^"]+)"\s+.*?(?P<x>\d+)\s*,\s*(?P<y>\d+)\s*',
)

# Alias → local forward port (avoid 9008 clash with uiautomator2 default).
DEFAULT_PORTS = {
    "hd8": 9008,
    "s24": 9009,
    "p7a": 9010,
}

HS_BIN = os.environ.get(
    "STAYTURGID_HANDSETS_BIN",
    os.path.expanduser("~/.handsets/hs"),
)
HS_JAR = os.environ.get(
    "STAYTURGID_HANDSETS_JAR",
    os.path.expanduser("~/.handsets/hs.jar"),
)
REMOTE_JAR = "/data/local/tmp/hs.jar"


class UiDriverError(RuntimeError):
    pass


def port_for(alias: str) -> int:
    env = os.environ.get("STAYTURGID_HANDSETS_PORT")
    if env:
        return int(env)
    return DEFAULT_PORTS.get(alias, 9011)


def handsets_available() -> bool:
    return os.path.isfile(HS_BIN) and os.path.isfile(HS_JAR)


def _run(cmd: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )


class HandsetsSession:
    """Context manager: daemon up for one serial, then tear down."""

    def __init__(
        self,
        serial: str,
        alias: str = "",
        port: int | None = None,
        *,
        keep_alive: bool = False,
    ):
        self.serial = serial
        self.alias = alias or serial
        self.port = port if port is not None else port_for(self.alias)
        self.keep_alive = keep_alive
        self.active = False
        self._nice = "hsd%d" % self.port

    def __enter__(self) -> "HandsetsSession":
        if not handsets_available():
            raise UiDriverError(
                "Handsets not installed (expected %s and %s)" % (HS_BIN, HS_JAR)
            )
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.keep_alive:
            self.stop()
        self.active = False

    def start(self) -> None:
        # Kill prior daemon on this port only.
        _run(
            [
                "adb", "-s", self.serial, "shell",
                "pkill -f '%s' 2>/dev/null; pkill -f 'dev.handsets.daemon.Main --port=%d' 2>/dev/null; true"
                % (self._nice, self.port),
            ],
            timeout=15,
        )
        push = _run(
            ["adb", "-s", self.serial, "push", HS_JAR, REMOTE_JAR],
            timeout=60,
        )
        if push.returncode != 0:
            raise UiDriverError(
                "adb push hs.jar failed: %s" % ((push.stderr or push.stdout or "").strip())
            )
        _run(
            ["adb", "-s", self.serial, "forward", "--remove", "tcp:%d" % self.port],
            timeout=10,
        )
        # Start daemon (shell UID via app_process).
        start = (
            "CLASSPATH=%s nohup app_process /system/bin --nice-name=%s "
            "dev.handsets.daemon.Main --port=%d >/data/local/tmp/%s.log 2>&1 &"
            % (REMOTE_JAR, self._nice, self.port, self._nice)
        )
        _run(["adb", "-s", self.serial, "shell", start], timeout=15)
        fwd = _run(
            ["adb", "-s", self.serial, "forward", "tcp:%d" % self.port, "tcp:%d" % self.port],
            timeout=10,
        )
        if fwd.returncode != 0:
            raise UiDriverError("adb forward failed for port %d" % self.port)
        # Wait for ping.
        deadline = time.time() + 12
        last = ""
        while time.time() < deadline:
            r = self._hs("dev", "ping", timeout=5)
            if r.returncode == 0:
                self.active = True
                return
            last = (r.stderr or r.stdout or "").strip()
            time.sleep(0.4)
        raise UiDriverError("Handsets daemon did not become ready: %s" % last)

    def stop(self) -> None:
        _run(
            [
                "adb", "-s", self.serial, "shell",
                "pkill -f '%s' 2>/dev/null; pkill -f 'dev.handsets.daemon.Main --port=%d' 2>/dev/null; true"
                % (self._nice, self.port),
            ],
            timeout=15,
        )
        _run(
            ["adb", "-s", self.serial, "forward", "--remove", "tcp:%d" % self.port],
            timeout=10,
        )
        self.active = False

    def _hs(self, *args: str, timeout: float = 20) -> subprocess.CompletedProcess:
        cmd = [
            HS_BIN,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            *args,
        ]
        return _run(cmd, timeout=timeout)

    def hs(self, *args: str, timeout: float = 20) -> subprocess.CompletedProcess:
        if not self.active:
            raise UiDriverError("HandsetsSession not active")
        return self._hs(*args, timeout=timeout)

    def tap_text(self, text: str, *, timeout_ms: int = 5000) -> bool:
        r = self.hs("tap", text, "--timeout", str(timeout_ms))
        return r.returncode == 0

    def tap_desc(self, desc: str, *, timeout_ms: int = 5000) -> bool:
        # content-desc via has-text often works; also try desc attribute.
        for sel in (
            desc,
            '*:has-text("%s")' % desc,
            '*[desc="%s"]' % desc,
            '*[content-desc="%s"]' % desc,
        ):
            r = self.hs("tap", sel, "--timeout", str(timeout_ms))
            if r.returncode == 0:
                return True
        return False

    def find_text(self, text: str, *, timeout_ms: int = 3000) -> bool:
        r = self.hs(
            "find",
            'TextView:has-text("%s")' % text,
            "--timeout",
            str(timeout_ms),
        )
        if r.returncode == 0:
            return True
        r = self.hs("find", '*:has-text("%s")' % text, "--timeout", str(timeout_ms))
        return r.returncode == 0

    def ui(self) -> str:
        r = self.hs("ui", timeout=30)
        return r.stdout or ""

    def ui_contains(self, *needles: str) -> bool:
        text = self.ui()
        return any(n in text for n in needles)

    def swipe(self, direction: str) -> bool:
        """direction: up|down|left|right (Handsets semantics)."""
        r = self.hs("swipe", direction)
        return r.returncode == 0

    def go(self, where: str) -> bool:
        r = self.hs("go", where)
        return r.returncode == 0

    def _parse_switch_from_ui(self, label: str, ui: str | None = None):
        """Return (checked, x, y) from ``hs ui`` table, or None if missing.

        Handsets ``Switch:near(..., 200)`` misses AutoJs6 drawer rows (~327px
        label→switch). Prefer the flat UI table: label line then adjacent Switch.
        """
        text = ui if ui is not None else self.ui()
        if label not in text:
            return None
        lines = text.splitlines()
        best = None  # (dy, checked, x, y)
        for i, line in enumerate(lines):
            if '"%s"' % label not in line and label not in line:
                continue
            # Prefer exact quoted title match.
            mlab = _UI_LABEL_RE.search(line)
            ly = int(mlab.group("y")) if mlab and (
                mlab.group("label") == label or label in mlab.group("label")
            ) else None
            if ly is None and '"%s"' % label not in line:
                continue
            if ly is None and mlab:
                ly = int(mlab.group("y"))
            window = lines[max(0, i - 2) : i + 5]
            for w in window:
                if "Switch" not in w:
                    continue
                m = _UI_SWITCH_RE.match(w)
                if not m:
                    continue
                x, y = int(m.group(1)), int(m.group(2))
                rest = m.group(3).lower()
                # Handsets: "[check checked]" = on; "[check]" alone = off.
                checked = "checked" in rest
                dy = abs(y - ly) if ly is not None else 0
                if best is None or dy < best[0]:
                    best = (dy, checked, x, y)
        if best is None:
            return None
        _, checked, x, y = best
        return checked, x, y

    def switch_near_label(self, label: str, *, timeout_ms: int = 4000):
        """Return (checked: bool|None, ok: bool) for Switch near label text."""
        # UI table first — reliable for AutoJs6 drawer Switch rows.
        parsed = self._parse_switch_from_ui(label)
        if parsed is not None:
            return parsed[0], True
        # Selector fallback (wider near radius than Handsets docs' 200).
        sel = 'Switch:near(TextView[text="%s"], %d)' % (label, _SWITCH_NEAR_PX)
        r = self.hs(
            "find", sel, "--timeout", str(timeout_ms), "--nth", "1",
        )
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if r.returncode == 0 and out.strip():
            checked = None
            if "checked=true" in out or "[check checked]" in out:
                checked = True
            elif "checked=false" in out or "[check]" in out:
                checked = False
            return checked, True
        return None, False

    def switch_coords(self, label: str) -> tuple[int, int] | None:
        parsed = self._parse_switch_from_ui(label)
        if parsed is None:
            return None
        return parsed[1], parsed[2]

    def tap_switch_for_label(self, label: str, *, timeout_ms: int = 5000) -> bool:
        coords = self.switch_coords(label)
        if coords is not None:
            r = self.hs(
                "tap", str(coords[0]), str(coords[1]),
                timeout=max(10.0, timeout_ms / 1000.0 + 5),
            )
            if r.returncode == 0:
                return True
        sel = 'Switch:near(TextView[text="%s"], %d)' % (label, _SWITCH_NEAR_PX)
        r = self.hs("tap", sel, "--timeout", str(timeout_ms), "--nth", "1")
        if r.returncode == 0:
            return True
        # Last resort: tap the label (does not always toggle Switch).
        return self.tap_text(label, timeout_ms=timeout_ms)


def with_handsets(
    serial: str,
    alias: str,
    body: Callable[["HandsetsSession"], int],
    *,
    required: bool = False,
) -> int:
    """Run body(session). If Handsets missing and not required, return 2."""
    if not handsets_available():
        if required:
            raise UiDriverError("Handsets required but not installed")
        return 2
    with HandsetsSession(serial, alias=alias) as session:
        return body(session)
