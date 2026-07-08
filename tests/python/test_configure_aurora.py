"""Unit tests for Aurora background-run dialog helpers."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CFG = REPO / "play" / "mac" / "configure_aurora.py"

spec = importlib.util.spec_from_file_location("configure_aurora", CFG)
mod = importlib.util.module_from_spec(spec)
sys.modules["configure_aurora"] = mod
spec.loader.exec_module(mod)

FIRE_DIALOG = """
<hierarchy><node package="com.android.settings" text="Let app always run in background?" resource-id="android:id/alertTitle" />
<node text="Allowing Aurora Store to always run in the background" resource-id="android:id/message" />
<node resource-id="android:id/button1" text="ALLOW" bounds="[881,452][959,506]" clickable="true" />
</hierarchy>
"""


def test_background_dialog_markers():
    assert any(m in FIRE_DIALOG for m in mod.BACKGROUND_DIALOG_MARKERS)


def test_dismiss_background_run_dialog_detects_aurora(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "dump_xml", lambda _s: FIRE_DIALOG)
    monkeypatch.setattr(mod, "tap", lambda _s, pt: calls.append(pt))
    assert mod.dismiss_background_run_dialog("serial", "Aurora") is True
    assert calls
