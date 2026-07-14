"""Unit tests for control/lib/ui_driver.py (Handsets helper)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import ui_driver as ud  # noqa: E402


def test_port_for_defaults():
    assert ud.port_for("s24") == 9013
    assert ud.port_for("hd8") == 9012
    assert ud.port_for("p7a") == 9014
    assert ud.port_for("unknown") == 9011


def test_port_for_env_override(monkeypatch):
    monkeypatch.setenv("STAYTURGID_HANDSETS_PORT", "9123")
    assert ud.port_for("s24") == 9123


def test_handsets_available_false_when_missing(monkeypatch):
    monkeypatch.setattr(ud, "HS_BIN", "/no/such/hs")
    monkeypatch.setattr(ud, "HS_JAR", "/no/such/hs.jar")
    assert ud.handsets_available() is False


def test_session_start_pushes_and_forwards(monkeypatch, tmp_path):
    hs = tmp_path / "hs"
    jar = tmp_path / "hs.jar"
    hs.write_text("#!/bin/sh\n")
    jar.write_text("jar")
    monkeypatch.setattr(ud, "HS_BIN", str(hs))
    monkeypatch.setattr(ud, "HS_JAR", str(jar))

    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):
        calls.append(list(cmd))
        # Pretend ping succeeds once hs is invoked with ping
        if "ping" in cmd:
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ud, "_run", fake_run)
    session = ud.HandsetsSession("SERIAL", alias="s24", port=9013)
    session.start()
    assert session.active
    joined = [" ".join(c) for c in calls]
    assert any("push" in j and "hs.jar" in j for j in joined)
    assert any("forward" in j and "9013" in j for j in joined)
    assert any("app_process" in j for j in joined)
    session.stop()
    assert session.active is False


_SAMPLE_DRAWER_UI = """\
-    TextView              "Accessibility service"  #title  342,250
tap  Switch                #sw  669,250  [check]
-    TextView              "Foreground service"  #title  342,363
tap  Switch                #sw  669,363  [check]
-    TextView              "Shizuku access"  #title  342,2194
tap  Switch                #sw  669,2189  [check checked]
"""


def test_parse_switch_from_ui_checked_and_coords():
    session = ud.HandsetsSession("SERIAL", alias="s24", port=9013)
    session.active = True
    got = session._parse_switch_from_ui("Shizuku access", _SAMPLE_DRAWER_UI)
    assert got == (True, 669, 2189)
    got_off = session._parse_switch_from_ui("Accessibility service", _SAMPLE_DRAWER_UI)
    assert got_off == (False, 669, 250)


def test_parse_switch_missing_label():
    session = ud.HandsetsSession("SERIAL", alias="s24", port=9013)
    session.active = True
    assert session._parse_switch_from_ui("No such row", _SAMPLE_DRAWER_UI) is None


_SAMPLE_AURORA_UPDATES_UI = """\
-    TextView     "Filter F-Droid apps"  #title  219,705
-    Switch       #switchWidget  969,735  [check checked]
-    TextView     "Filter apps from other sources"  #title  333,928
-    Switch       #switchWidget  969,980  [check checked]
-    Switch       #switchWidget  969,1360  [check]
"""


def test_parse_switch_aurora_preference_rows():
    session = ud.HandsetsSession("SERIAL", alias="p7a", port=9014)
    session.active = True
    assert session._parse_switch_from_ui("Filter F-Droid apps", _SAMPLE_AURORA_UPDATES_UI) == (True, 969, 735)
    assert session._parse_switch_from_ui("Filter apps from other sources", _SAMPLE_AURORA_UPDATES_UI) == (
        True,
        969,
        980,
    )


def test_try_handsets_yields_none_when_missing(monkeypatch):
    monkeypatch.setattr(ud, "handsets_available", lambda: False)
    with ud.try_handsets("SERIAL", "s24") as hs:
        assert hs is None
