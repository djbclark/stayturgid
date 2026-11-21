"""Every collection module must stop Ansible expanding the commands it sends through module.run_command.

``AnsibleModule.run_command`` expands ``$VAR`` and ``~`` in argv by default, on the control node. A device
script (``mkdir -p "$HOME/.ssh"``) then reaches the phone with the Mac's home in it (s24, 2026-11-21).
``plain_run_command(module)`` as the statement right after ``AnsibleModule(...)`` turns that off for the
whole module. Selection is every module that builds an AnsibleModule, not only those whose text says
``run_command``, so a module that hands ``module`` to a helper is covered too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COLLECTIONS = REPO / "ansible_collections" / "stayturgid"
MODULES = sorted(COLLECTIONS.glob("*/plugins/modules/*.py"))
# stayturgid_verify runs its commands with subprocess, never module.run_command.
SUBPROCESS_ONLY = {"stayturgid_verify.py"}


def modules_with_an_ansible_module() -> list[Path]:
    return [p for p in MODULES if "module = AnsibleModule(" in p.read_text(encoding="utf-8")]


def statement_after_constructor(text: str) -> str:
    """The first line after the closing paren of ``module = AnsibleModule(...)``."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith("module = AnsibleModule("))
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    end = next(i for i in range(start, len(lines)) if lines[i] == indent + ")" or lines[i].endswith("AnsibleModule()"))
    return lines[end + 1].strip()


def test_the_scan_finds_the_modules_that_matter():
    names = {p.name for p in modules_with_an_ansible_module()}
    assert {"termux_ssh_bootstrap.py", "termux_pkg.py", "android_apk.py", "shizuku_start.py", "play_apps.py"} <= names


@pytest.mark.parametrize(
    "path", [p for p in modules_with_an_ansible_module() if p.name not in SUBPROCESS_ONLY], ids=lambda p: p.name
)
def test_module_turns_off_run_command_expansion_right_after_building_the_module(path: Path):
    text = path.read_text(encoding="utf-8")
    assert statement_after_constructor(text) == "plain_run_command(module)", (
        "%s: put plain_run_command(module) right after AnsibleModule(...)" % path.name
    )
    assert "import plain_run_command" in text


def test_no_module_or_module_util_asks_for_the_expansion_back():
    offenders = [
        str(p.relative_to(REPO))
        for p in sorted(COLLECTIONS.glob("*/plugins/**/*.py"))
        if p.name != "plain_run.py" and "expand_user_and_vars=True" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
