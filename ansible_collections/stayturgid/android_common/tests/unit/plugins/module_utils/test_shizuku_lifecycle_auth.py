"""shizuku_lifecycle: the unanswered-dialog marker, and why the starter ignores it."""

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import shizuku_lifecycle as lc  # noqa: E402


def fake_run(status):
    calls = []

    def run(cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        calls.append(joined)
        if "HEADLESS_STATUS" in joined:
            return (0, status, "")
        if "pm path" in joined:
            return (0, "package:/data/app/~~x/moe.shizuku.privileged.api/base.apk\n", "")
        if "pgrep" in joined:
            return (0, "up\n", "")
        return (0, "", "")

    return run, calls


def test_marker_detection():
    assert lc.status_auth_unanswered('result=3, data="STOPPED AUTH_UNANSWERED"') is True
    assert lc.status_auth_unanswered("Broadcast completed: result=4") is False  # CRASHED
    assert lc.start_withheld("Broadcast completed: result=4") is True
    assert lc.start_withheld("Broadcast completed: result=40") is False
    assert lc.start_withheld('result=0, data="AUTH_UNANSWERED"') is True


@pytest.mark.parametrize(
    "status",
    ["Broadcast completed: result=1", 'Broadcast completed: result=1, data="RUNNING AUTH_UNANSWERED"'],
)
def test_restart_runs_the_starter_regardless_of_marker(status):
    # The starter runs from an already-authorised adb shell and offers no key.
    run, calls = fake_run(status)
    restarted, ok = lc.restart_shizuku_if_running(run, "dev")
    assert restarted is True
    assert ok is True
    assert any("libshizuku" in c for c in calls)
    assert not any("force" in c for c in calls)
