"""Unit tests for obtainium/mac/apply_updates.py installer-dialog decision logic."""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "obtainium", "mac"))
import apply_updates as au  # noqa: E402


def test_installer_dialog_returns_button2_center():
    xml = (
        '<node package="com.google.android.packageinstaller">'
        '<node resource-id="android:id/button2" bounds="[600,1400][900,1500]" />'
        '</node>'
    )
    kind, center = au.installer_action(xml)
    assert kind == "installer"
    assert center == (750, 1450)


def test_installer_present_but_no_button():
    xml = '<node package="com.google.android.packageinstaller" />'
    kind, center = au.installer_action(xml)
    assert kind == "installer" and center is None


def test_play_protect_detected():
    xml = '<node package="com.android.vending" text="Play Protect" />'
    assert au.installer_action(xml) == ("playprotect", None)


def test_nothing_to_do():
    assert au.installer_action('<node package="dev.imranr.obtainium" />') == (None, None)
    assert au.installer_action("") == (None, None)
    assert au.installer_action(None) == (None, None)
