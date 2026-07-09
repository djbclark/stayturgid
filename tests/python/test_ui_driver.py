"""Unit tests for shared/mac/ui_driver.py (Handsets helper)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared" / "mac"))

import ui_driver as ud  # noqa: E402


def test_port_for_defaults():
    assert ud.port_for("s24") == 9009
    assert ud.port_for("hd8") == 9008
    assert ud.port_for("p7a") == 9010
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
    session = ud.HandsetsSession("SERIAL", alias="s24", port=9009)
    session.start()
    assert session.active
    joined = [" ".join(c) for c in calls]
    assert any("push" in j and "hs.jar" in j for j in joined)
    assert any("forward" in j and "9009" in j for j in joined)
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
    session = ud.HandsetsSession("SERIAL", alias="s24", port=9009)
    session.active = True
    got = session._parse_switch_from_ui("Shizuku access", _SAMPLE_DRAWER_UI)
    assert got == (True, 669, 2189)
    got_off = session._parse_switch_from_ui("Accessibility service", _SAMPLE_DRAWER_UI)
    assert got_off == (False, 669, 250)


def test_parse_switch_missing_label():
    session = ud.HandsetsSession("SERIAL", alias="s24", port=9009)
    session.active = True
    assert session._parse_switch_from_ui("No such row", _SAMPLE_DRAWER_UI) is None
