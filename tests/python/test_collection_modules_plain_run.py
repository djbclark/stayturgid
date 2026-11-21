"""Every collection module that sends commands through module.run_command must stop Ansible expanding them.

``AnsibleModule.run_command`` expands ``$VAR`` and ``~`` in argv by default, on the control node. A device
script (``mkdir -p "$HOME/.ssh"``) then reaches the phone with the Mac's home in it (s24, 2026-11-21).
``plain_run_command(module)`` right after ``AnsibleModule(...)`` turns that off for the whole module.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULES = sorted((REPO / "ansible_collections" / "stayturgid").glob("*/plugins/modules/*.py"))
USES_RUN_COMMAND = re.compile(r"\brun_command\b")


def modules_that_run_commands() -> list[Path]:
    return [p for p in MODULES if USES_RUN_COMMAND.search(p.read_text(encoding="utf-8"))]


def test_the_scan_finds_the_modules_that_matter():
    names = {p.name for p in modules_that_run_commands()}
    assert {"termux_ssh_bootstrap.py", "termux_pkg.py", "android_apk.py", "shizuku_start.py"} <= names


@pytest.mark.parametrize("path", modules_that_run_commands(), ids=lambda p: p.name)
def test_module_turns_off_run_command_expansion(path: Path):
    text = path.read_text(encoding="utf-8")
    built = text.index("module = AnsibleModule(")
    assert "plain_run_command(module)" in text[built:], (
        "%s: add plain_run_command(module) after AnsibleModule(...)" % path.name
    )
    assert "import plain_run_command" in text
    # Nothing may ask for the expansion back for a device script.
    assert "expand_user_and_vars=True" not in text
