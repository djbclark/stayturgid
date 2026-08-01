"""Unit tests for the adb_timeout module_util (systemic command timeout wrapper)."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import adb_timeout as at


def test_resolve_timeout_bin():
    bin_path = at.resolve_timeout_bin()
    assert bin_path is not None
    assert os.path.isfile(bin_path)


def test_run_command_with_timeout_prefixes_command(monkeypatch):
    monkeypatch.setattr(at, "resolve_timeout_bin", lambda get_bin_path_fn=None: "/usr/bin/timeout")
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return 0, "ok", ""

    rc, out, err = at.run_command_with_timeout(fake_run, ["adb", "devices"], timeout=30)
    assert rc == 0
    assert out == "ok"
    assert calls == [["/usr/bin/timeout", "30", "adb", "devices"]]


def test_run_command_with_timeout_handles_rc_124(monkeypatch):
    monkeypatch.setattr(at, "resolve_timeout_bin", lambda get_bin_path_fn=None: "/usr/bin/timeout")

    def fake_run(cmd):
        return 124, "", "initial stderr"

    rc, out, err = at.run_command_with_timeout(fake_run, ["adb", "install", "app.apk"], timeout=180)
    assert rc == 124
    assert "ADB command timed out after 180s: adb install app.apk" in err
    assert "initial stderr" in err


def test_run_command_with_timeout_prevents_double_wrapping(monkeypatch):
    monkeypatch.setattr(at, "resolve_timeout_bin", lambda get_bin_path_fn=None: "/usr/bin/timeout")
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return 0, "", ""

    already_wrapped = ["/usr/bin/timeout", "60", "adb", "shell", "getprop"]
    rc, out, err = at.run_command_with_timeout(fake_run, already_wrapped, timeout=30)
    assert rc == 0
    assert calls == [already_wrapped]


def test_resolve_timeout_bin_prefers_fresh_get_bin_path_fn_over_cache(monkeypatch):
    """A provided get_bin_path_fn must win even if a prior call (with no
    get_bin_path_fn, or a different one) already populated the process-wide
    fallback cache — regression test for a real cross-call staleness bug
    where android_apk.py's install path got a stale /opt/homebrew/bin/timeout
    instead of the test's own mocked /usr/bin/timeout."""
    monkeypatch.setattr(at, "_CACHED_TIMEOUT_BIN", "/some/other/cached/timeout")
    assert at.resolve_timeout_bin(get_bin_path_fn=lambda name: "/usr/bin/" + name) == "/usr/bin/timeout"


def test_run_command_with_timeout_when_no_timeout_bin(monkeypatch):
    monkeypatch.setattr(at, "resolve_timeout_bin", lambda get_bin_path_fn=None: None)
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return 0, "output", ""

    rc, out, err = at.run_command_with_timeout(fake_run, ["adb", "devices"], timeout=30)
    assert rc == 0
    assert out == "output"
    assert calls == [["adb", "devices"]]
