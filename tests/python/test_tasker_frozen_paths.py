"""The recovery script paths other components call are a frozen interface.

The Tasker project is imported by hand on each phone and can never be changed
again without a human, and the native agent APK compiles in its path. Deploys
never delete, so a rename leaves deployed phones running a stale copy and new
phones failing. These tests pin the names, not just "some file exists".
"""

from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TASKER_SRC = REPO / "device" / "termux" / "tasker"
DEVICE_TASKER_DIR = "/data/data/com.termux/files/home/.termux/tasker/"
DISPATCHER = "sshd-recover-tasker.sh"
SSHD_RECOVER = "sshd-recover.sh"


def _git_mode(path: Path) -> str | None:
    r = subprocess.run(
        ["git", "ls-files", "-s", "--", str(path.relative_to(REPO))],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.split()[0] if r.stdout.strip() else None


def _assert_tracked_executable(path: Path) -> None:
    assert path.is_file(), path
    assert _git_mode(path) == "100755", "%s must be mode 100755 in git" % path


def _run_command_path() -> str:
    root = ET.parse(REPO / "device" / "tasker" / "StayTurgid_SSHD_Recover.prj.xml").getroot()
    paths = [
        s.text.split(":", 1)[1]
        for s in root.iter("Str")
        if s.text and s.text.startswith("com.termux.RUN_COMMAND_PATH:")
    ]
    assert len(paths) == 1, paths
    return paths[0]


def test_tasker_run_command_path_is_the_frozen_dispatcher():
    assert _run_command_path() == DEVICE_TASKER_DIR + DISPATCHER


def test_tasker_run_command_target_exists_and_is_executable_in_git():
    name = _run_command_path().removeprefix(DEVICE_TASKER_DIR)
    _assert_tracked_executable(TASKER_SRC / name)


def test_agent_calls_frozen_sshd_recover():
    kt = (REPO / "device/native-agent/app/src/main/kotlin/org/stayturgid/agent/SshdRecover.kt").read_text(
        encoding="utf-8"
    )
    paths = re.findall(r'"(/data/data/com\.termux/files/home/\.termux/tasker/[^"]+)"', kt)
    assert paths == [DEVICE_TASKER_DIR + SSHD_RECOVER]
    _assert_tracked_executable(TASKER_SRC / SSHD_RECOVER)


def test_firerpa_heal_calls_frozen_sshd_recover():
    src = (REPO / "control/bin/firerpa_heal.py").read_text(encoding="utf-8")
    assert re.findall(r"\.termux/tasker/([\w.-]+)", src) == [SSHD_RECOVER]


def test_recover_d_sshd_step_is_executable_and_targets_sshd_recover():
    step = TASKER_SRC / "recover.d" / "10-sshd"
    assert step.is_file()
    # Not yet tracked right after it is added; once tracked, git must agree.
    mode = _git_mode(step)
    assert mode == "100755" if mode else os.access(step, os.X_OK)
    assert SSHD_RECOVER in step.read_text(encoding="utf-8")


def test_frozen_scripts_say_so():
    for name in (DISPATCHER, SSHD_RECOVER):
        head = "\n".join((TASKER_SRC / name).read_text(encoding="utf-8").splitlines()[:3])
        assert "FROZEN INTERFACE: never rename" in head, name
