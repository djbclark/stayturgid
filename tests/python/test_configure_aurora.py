"""Unit tests for Aurora background-run dialog helpers."""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CFG = REPO / "control" / "tools" / "play" / "configure_aurora.py"

spec = importlib.util.spec_from_file_location("configure_aurora", CFG)
mod = importlib.util.module_from_spec(spec)
sys.modules["configure_aurora"] = mod
spec.loader.exec_module(mod)

FIRE_DIALOG = """
<hierarchy><node package="com.android.settings" text="Let app always run in background?" resource-id="android:id/alertTitle" />
<node text="Allowing Aurora Store to always run in the background" resource-id="android:id/message" />
<node resource-id="android:id/button2" text="DENY" bounds="[700,452][850,506]" clickable="true" />
<node resource-id="android:id/button1" text="ALLOW" bounds="[881,452][959,506]" clickable="true" />
</hierarchy>
"""


def test_background_dialog_markers():
    assert any(m in FIRE_DIALOG for m in mod.BACKGROUND_DIALOG_MARKERS)


def test_dismiss_background_run_dialog_denies_aurora(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "_ui_text", lambda _s: FIRE_DIALOG)
    monkeypatch.setattr(mod, "tap", lambda _s, pt: calls.append(pt))
    monkeypatch.setattr(mod, "_HS", None)
    assert mod.dismiss_background_run_dialog("serial", "Aurora") is True
    assert calls
    # Prefer DENY (button2) over ALLOW (button1).
    assert calls[0] == ((700 + 850) // 2, (452 + 506) // 2)


def test_filter_label_constants():
    assert "Filter apps from other sources" in mod.FILTER_AURORA_ONLY_LABELS
    assert "Filter F-Droid apps" in mod.FILTER_FDROID_LABELS
    assert "Do not auto-update" in mod.AUTO_UPDATE_OFF_LABELS
    assert "Check & install available updates automatically" in mod.AUTO_UPDATE_ON_LABELS


def test_configure_auto_updates_selects_off(monkeypatch):
    taps = []

    def fake_tap(serial, text, timeout=10):
        taps.append(text)
        return True

    monkeypatch.setattr(mod, "_ui_text", lambda _s: "Settings\nUpdates\nDo not auto-update")
    monkeypatch.setattr(mod, "tap_text", fake_tap)
    monkeypatch.setattr(mod, "adb", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_HS", None)
    assert mod.configure_auto_updates("serial") is True
    assert "Automatic updates" in taps
    assert "Do not auto-update" in taps
    assert "Check & install available updates automatically" not in taps
