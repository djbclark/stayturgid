"""Unit tests for shared/mac/ui_clearance.py."""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "shared", "mac"))
import ui_clearance as uc  # noqa: E402

PINNED_STACK = """
RootTask id=42 bounds=[800,1600][1080,1900] displayId=0 userId=0
 configuration={... mWindowingMode=pinned ...}
  taskId=99: com.google.android.youtube/com.google.android.youtube.WatchActivity bounds=[800,1600][1080,1900] userId=0 visible=true
"""

ACTIVITY_PIP = """
ActivityRecord{abc u0 com.google.android.youtube/.WatchActivity t99}
  mIsInPictureInPictureMode=true
"""


def test_parse_pinned_stacks():
    stacks = uc.parse_pinned_stacks(PINNED_STACK)
    assert stacks == [(42, "com.google.android.youtube")]


def test_pip_obstruction_detected_from_stack():
    assert uc.pip_obstruction_detected("", PINNED_STACK, "")


def test_pip_obstruction_detected_from_activity():
    assert uc.pip_obstruction_detected(ACTIVITY_PIP, "", "")


def test_pip_packages_excludes_protected():
    pkgs = uc.pip_packages(ACTIVITY_PIP, PINNED_STACK, "")
    assert "com.google.android.youtube" in pkgs
    assert "org.autojs.autojs6" not in pkgs


def test_pip_obstruction_negative():
    stack = """
RootTask id=1 bounds=[0,0][1080,2340] displayId=0
 configuration={... mWindowingMode=fullscreen ...}
  taskId=2: org.autojs.autojs6/org.autojs.autojs.ui.main.MainActivity bounds=[0,0][1080,2340]
"""
    assert not uc.pip_obstruction_detected("", stack, "")
