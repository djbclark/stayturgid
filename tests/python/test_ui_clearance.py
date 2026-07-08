"""Unit tests for shared/mac/ui_clearance.py."""
import os
import sys
from pathlib import Path

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
  * Task{bf9d17d #1343 type=standard A=10291:com.google.android.youtube U=0 visible=true visibleRequested=true mode=pinned translucent=false sz=1}
    packageName=com.google.android.youtube
      mLastReportedMultiWindowMode=true mLastReportedPictureInPictureMode=true
  rootPinnedTask=Task=1343
"""

SAMSUNG_STACK = """
RootTask id=1343 bounds=[248,146][1038,590] displayId=0 userId=0
 configuration={... mWindowingMode=pinned ...}
  taskId=1343: com.google.android.youtube/com.google.android.youtube.app.honeycomb.Shell$HomeActivity bounds=[248,146][1038,590] userId=0 visible=true
"""


def test_samsung_youtube_pip_packages():
    pkgs = uc.pip_packages(ACTIVITY_PIP, SAMSUNG_STACK, "pip_input_consumer PipMenuView")
    assert pkgs == {"com.google.android.youtube"}


def test_pinned_stack_targets_fallback():
    targets = uc.pinned_stack_targets(ACTIVITY_PIP, "")
    assert targets == [(1343, "com.google.android.youtube")]


def test_parse_pinned_stacks():
    stacks = uc.parse_pinned_stacks(PINNED_STACK)
    assert stacks == [(42, "com.google.android.youtube")]


def test_pip_obstruction_detected_from_stack():
    assert uc.pip_obstruction_detected("", PINNED_STACK, "")


def test_pip_obstruction_detected_from_activity():
    assert uc.pip_obstruction_detected(ACTIVITY_PIP, "", "pip_input_consumer")


def test_pip_packages_excludes_protected():
    pkgs = uc.pip_packages(ACTIVITY_PIP, SAMSUNG_STACK, "")
    assert "com.google.android.youtube" in pkgs
    assert "org.lichess.mobileV2" not in pkgs
    assert "org.autojs.autojs6" not in pkgs
    assert "keyb" not in pkgs


def test_parse_services_skips_null_tokens():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
    import a11y_services as a11y
    assert a11y.parse_services("null:org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher") == [
        "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"
    ]


def test_pip_obstruction_negative():
    stack = """
RootTask id=1 bounds=[0,0][1080,2340] displayId=0
 configuration={... mWindowingMode=fullscreen ...}
  taskId=2: org.autojs.autojs6/org.autojs.autojs.ui.main.MainActivity bounds=[0,0][1080,2340]
"""
    assert not uc.pip_obstruction_detected("", stack, "")
