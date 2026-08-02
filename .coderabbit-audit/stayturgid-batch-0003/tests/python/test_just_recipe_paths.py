"""Regression checks for literal script paths invoked by Just recipes."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUSTFILES = (ROOT / "justfile", *sorted((ROOT / "just").glob("*.just")))
SCRIPT_COMMAND = re.compile(
    r"(?:^|\s)(?:bash|python3)\s+"
    r"(?P<quote>[\"']?)"
    r"(?:(?:\{\{\s*repo\s*\}\})/)?"
    r"(?P<path>(?:\./)?(?:ansible|control|device|just|tests)/[\w./-]+\.(?:py|sh))"
    r"(?P=quote)(?=\s|$|[;&|\\)])"
)


def literal_script_paths(command: str) -> list[str]:
    """Return normalized literal script paths invoked by a recipe command."""
    return [match.group("path").removeprefix("./") for match in SCRIPT_COMMAND.finditer(command)]


def test_literal_recipe_script_path_forms() -> None:
    cases = {
        "python3 control/bin/example.py": ["control/bin/example.py"],
        'python3 "control/bin/example.py"; next': ["control/bin/example.py"],
        "bash '{{ repo }}/just/tools/example.sh' && next": ["just/tools/example.sh"],
        "python3 tests/example.py \\": ["tests/example.py"],
        "python3 device/example.py)": ["device/example.py"],
    }

    for command, expected in cases.items():
        assert literal_script_paths(command) == expected


def test_literal_recipe_script_paths_exist() -> None:
    missing: list[str] = []

    for justfile in JUSTFILES:
        for line_number, line in enumerate(justfile.read_text(encoding="utf-8").splitlines(), start=1):
            command = line.split("#", maxsplit=1)[0]
            for relative_path in literal_script_paths(command):
                if not (ROOT / relative_path).is_file():
                    missing.append(f"{justfile.relative_to(ROOT)}:{line_number}: {relative_path}")

    assert not missing, "Just recipes reference missing scripts:\n" + "\n".join(missing)
