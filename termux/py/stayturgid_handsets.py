#!/usr/bin/env python3
"""On-device Handsets wire client (Termux → localhost daemon).

Starts ``hs.jar`` via ``adb -s localhost:5555`` (shell UID) and speaks the
length-prefixed binary protocol. No host ``hs`` binary required.

Env:
  STAYTURGID_HANDSETS=0     disable (callers fall back to uiautomator dump)
  STAYTURGID_HANDSETS_PORT  daemon port (default 9012)
  STAYTURGID_HS_JAR         path to hs.jar (default /data/local/tmp/hs.jar)

See docs/research/handsets-under-termux.md.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import time
from typing import Any

import stayturgid_shell as sh

DEFAULT_PORT = int(os.environ.get("STAYTURGID_HANDSETS_PORT", "9012"))
REMOTE_JAR = os.environ.get("STAYTURGID_HS_JAR", "/data/local/tmp/hs.jar")
# Prefer deployed copy under ~/.stayturgid/lib when present.
_STG_JAR = os.path.join(sh.STG, "lib", "hs.jar")
NICE = "hsd%d" % DEFAULT_PORT


class HandsetsError(RuntimeError):
    pass


def enabled() -> bool:
    if os.environ.get("STAYTURGID_HANDSETS", "1") == "0":
        return False
    if os.environ.get("STAYTURGID_NO_LOCAL_ADB") == "1":
        return False
    return True


def jar_path() -> str | None:
    for path in (_STG_JAR, REMOTE_JAR):
        if os.path.isfile(path):
            return path
    return None


def available() -> bool:
    return enabled() and jar_path() is not None


def _adb(*args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    sh.connect()
    return subprocess.run(
        ["adb", "-s", sh.SERIAL, "shell"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _ensure_jar_on_device() -> str:
    """Place hs.jar where shell UID can load it (Termux home is not readable)."""
    src = jar_path()
    if not src:
        raise HandsetsError("hs.jar not found (deploy ~/.stayturgid/lib/hs.jar)")
    sh.connect()
    # Always push — shell cannot read /data/data/com.termux/… even if jar is there.
    r = subprocess.run(
        ["adb", "-s", sh.SERIAL, "push", src, REMOTE_JAR],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise HandsetsError(
            "adb push hs.jar failed: %s" % ((r.stderr or r.stdout or "").strip())
        )
    return REMOTE_JAR


def _frame(cmd: str) -> bytes:
    body = cmd.encode("ascii", errors="strict")
    return struct.pack(">I", len(body)) + body


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("eof")
        buf += chunk
    return buf


def call(cmd: str, *, port: int = DEFAULT_PORT, timeout: float = 8.0) -> bytes:
    """Send one wire command; return concatenated response body frames."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        sock.sendall(_frame(cmd))
        parts: list[bytes] = []
        sock.settimeout(min(2.0, timeout))
        try:
            while True:
                hdr = _recv_exact(sock, 4)
                (n,) = struct.unpack(">I", hdr)
                if n == 0:
                    break
                if n > 50_000_000:
                    raise HandsetsError("bad frame length %d" % n)
                parts.append(_recv_exact(sock, n))
                # Single-frame replies (ping) omit EOS — stop after short idle.
                sock.settimeout(0.2)
        except socket.timeout:
            pass
        body = b"".join(parts)
        if body.startswith(b"ERR:"):
            raise HandsetsError(body.decode("utf-8", errors="replace"))
        return body
    finally:
        try:
            sock.close()
        except OSError:
            pass


def ping(port: int = DEFAULT_PORT) -> bool:
    try:
        return call("ping", port=port, timeout=3) == b"pong"
    except Exception:
        return False


def start(port: int = DEFAULT_PORT) -> None:
    jar = _ensure_jar_on_device()
    _adb(
        "pkill -f '%s' 2>/dev/null; pkill -f 'dev.handsets.daemon.Main --port=%d' 2>/dev/null; true"
        % (NICE if port == DEFAULT_PORT else "hsd%d" % port, port),
        timeout=15,
    )
    time.sleep(0.3)
    nice = "hsd%d" % port
    start_cmd = (
        "CLASSPATH=%s nohup app_process /system/bin --nice-name=%s "
        "dev.handsets.daemon.Main --port=%d >/data/local/tmp/%s.log 2>&1 &"
        % (jar, nice, port, nice)
    )
    _adb(start_cmd, timeout=15)
    deadline = time.time() + 12
    while time.time() < deadline:
        if ping(port):
            return
        time.sleep(0.35)
    log = _adb("tail", "-20", "/data/local/tmp/%s.log" % nice, timeout=10)
    raise HandsetsError(
        "Handsets daemon not ready on :%d — %s" % (port, (log.stdout or "").strip())
    )


def stop(port: int = DEFAULT_PORT) -> None:
    nice = "hsd%d" % port
    _adb(
        "pkill -f '%s' 2>/dev/null; pkill -f 'dev.handsets.daemon.Main --port=%d' 2>/dev/null; true"
        % (nice, port),
        timeout=15,
    )


class Session:
    """Context manager: daemon up for the duration of on-device UI work."""

    def __init__(self, port: int | None = None):
        self.port = port if port is not None else DEFAULT_PORT
        self.active = False

    def __enter__(self) -> "Session":
        if not available():
            raise HandsetsError("Handsets unavailable on this host")
        start(self.port)
        self.active = True
        print("UI driver: Handsets wire on port %d (Termux)" % self.port)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.active = False
        try:
            stop(self.port)
        except Exception:
            pass

    def call(self, cmd: str, timeout: float = 8.0) -> bytes:
        if not self.active:
            raise HandsetsError("session not active")
        return call(cmd, port=self.port, timeout=timeout)

    def dump(self) -> dict[str, Any]:
        raw = self.call("dump_active", timeout=10)
        return json.loads(raw.decode("utf-8"))

    def dump_text(self) -> str:
        """Flatten dump to a searchable string (labels + descs)."""
        parts: list[str] = []

        def walk(n: Any) -> None:
            if not isinstance(n, dict):
                return
            for key in ("text", "desc"):
                val = n.get(key)
                if val:
                    parts.append(str(val))
            for ch in n.get("children") or []:
                walk(ch)

        data = self.dump()
        walk(data.get("root") or data)
        return "\n".join(parts)

    def contains(self, *needles: str) -> bool:
        blob = self.dump_text()
        return any(n in blob for n in needles)

    def _walk_nodes(self, data: dict | None = None) -> list[dict]:
        nodes: list[dict] = []

        def walk(n: Any) -> None:
            if not isinstance(n, dict):
                return
            nodes.append(n)
            for ch in n.get("children") or []:
                walk(ch)

        root = (data or self.dump()).get("root") or data
        walk(root)
        return nodes

    @staticmethod
    def _center(node: dict) -> tuple[int, int] | None:
        b = node.get("bounds")
        if not b or len(b) != 4:
            return None
        x1, y1, x2, y2 = (int(v) for v in b)
        return (x1 + x2) // 2, (y1 + y2) // 2

    @staticmethod
    def _checked(node: dict) -> bool:
        # Handsets flags: capital K means checked (e.g. ckKfev vs ckfev).
        flags = str(node.get("flags") or "")
        if "K" in flags:
            return True
        return bool(node.get("checked"))

    def find_text_node(self, text: str, data: dict | None = None) -> dict | None:
        for n in self._walk_nodes(data):
            if n.get("text") == text or n.get("desc") == text:
                return n
            if text in str(n.get("text") or "") or text in str(n.get("desc") or ""):
                return n
        return None

    def find_text(self, text: str) -> bool:
        return self.find_text_node(text) is not None

    def tap_xy(self, x: int, y: int) -> None:
        self.call("tap x=%d y=%d" % (x, y))

    def tap_text(self, text: str) -> bool:
        node = self.find_text_node(text)
        if not node:
            return False
        pt = self._center(node)
        if not pt:
            return False
        self.tap_xy(*pt)
        return True

    def tap_desc(self, desc: str) -> bool:
        for n in self._walk_nodes():
            if n.get("desc") == desc or desc in str(n.get("desc") or ""):
                pt = self._center(n)
                if pt:
                    self.tap_xy(*pt)
                    return True
        return False

    def tap_any_text(self, *labels: str) -> str | None:
        data = self.dump()
        for label in labels:
            node = self.find_text_node(label, data)
            if node:
                pt = self._center(node)
                if pt:
                    self.tap_xy(*pt)
                    return label
        return None

    def switch_near_label(self, label: str) -> tuple[bool, bool]:
        """Return (checked, found) for Switch nearest to label text."""
        data = self.dump()
        label_node = None
        for n in self._walk_nodes(data):
            if n.get("text") == label:
                label_node = n
                break
        if not label_node:
            return False, False
        lb = label_node.get("bounds") or [0, 0, 0, 0]
        ly = (int(lb[1]) + int(lb[3])) // 2
        best = None  # (dy, node)
        for n in self._walk_nodes(data):
            if "Switch" not in str(n.get("cls") or ""):
                continue
            pt = self._center(n)
            if not pt:
                continue
            dy = abs(pt[1] - ly)
            if best is None or dy < best[0]:
                best = (dy, n)
        if best is None:
            return False, True  # label found, no switch
        return self._checked(best[1]), True

    def tap_switch_for_label(self, label: str) -> bool:
        data = self.dump()
        label_node = None
        for n in self._walk_nodes(data):
            if n.get("text") == label:
                label_node = n
                break
        if not label_node:
            return False
        lb = label_node.get("bounds") or [0, 0, 0, 0]
        ly = (int(lb[1]) + int(lb[3])) // 2
        best = None
        for n in self._walk_nodes(data):
            if "Switch" not in str(n.get("cls") or ""):
                continue
            pt = self._center(n)
            if not pt:
                continue
            dy = abs(pt[1] - ly)
            if best is None or dy < best[0]:
                best = (dy, pt)
        if best is None:
            return self.tap_text(label)
        self.tap_xy(*best[1])
        return True

    def swipe(self, direction: str, dur_ms: int = 400) -> None:
        self.call("swipe_dir %s dur=%d" % (direction, dur_ms))

    def key(self, name: str) -> None:
        self.call("key %s" % name)


from contextlib import contextmanager
from typing import Iterator


@contextmanager
def try_session(port: int | None = None) -> Iterator["Session | None"]:
    """Yield an active Session, or None if Handsets cannot start."""
    if not available():
        yield None
        return
    session = Session(port=port)
    try:
        session.__enter__()
        yield session
    except HandsetsError as e:
        sys.stderr.write("WARN: Handsets unavailable (%s) — raw dump fallback\n" % e)
        yield None
    finally:
        if session.active:
            session.__exit__(None, None, None)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        sys.stderr.write(
            "usage: stayturgid_handsets.py ping|start|stop|dump|bench\n"
        )
        return 2
    cmd = argv[0]
    if cmd == "ping":
        if not available():
            print("unavailable")
            return 1
        start()
        ok = ping()
        stop()
        print("pong" if ok else "fail")
        return 0 if ok else 1
    if cmd == "start":
        start()
        print("started port=%d" % DEFAULT_PORT)
        return 0
    if cmd == "stop":
        stop()
        print("stopped")
        return 0
    if cmd == "dump":
        with Session() as hs:
            print(hs.dump_text()[:2000])
        return 0
    if cmd == "bench":
        n = int(argv[1]) if len(argv) > 1 else 8
        with Session() as hs:
            times = []
            for _ in range(n):
                t0 = time.perf_counter()
                hs.dump()
                times.append((time.perf_counter() - t0) * 1000)
            times.sort()
            print(
                "dump_active n=%d p50=%.0f avg=%.0f max=%.0f"
                % (n, times[len(times) // 2], sum(times) / len(times), max(times))
            )
        # raw dump compare
        times = []
        for _ in range(n):
            t0 = time.perf_counter()
            sh.shell("uiautomator", "dump", "/sdcard/hs_bench.xml")
            sh.shell("cat", "/sdcard/hs_bench.xml")
            times.append((time.perf_counter() - t0) * 1000)
        times.sort()
        print(
            "uiautomator dump n=%d p50=%.0f avg=%.0f max=%.0f"
            % (n, times[len(times) // 2], sum(times) / len(times), max(times))
        )
        return 0
    sys.stderr.write("unknown command %r\n" % cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
