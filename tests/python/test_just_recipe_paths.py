"""Regression checks for literal script paths invoked by Just recipes."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUSTFILES = (ROOT / "justfile", *sorted((ROOT / "just").glob("*.just")))
SCRIPT_COMMAND = re.compile(
    r"(?:^|\s)(?:bash|python3)\s+"
    r"(?P<path>(?:\./)?(?:ansible|control|device|just|tests)/[\w./-]+\.(?:py|sh))"
    r"(?=\s|$)"
)


def test_literal_recipe_script_paths_exist() -> None:
    missing: list[str] = []

    for justfile in JUSTFILES:
        for line_number, line in enumerate(justfile.read_text(encoding="utf-8").splitlines(), start=1):
            command = line.split("#", maxsplit=1)[0]
            for match in SCRIPT_COMMAND.finditer(command):
                relative_path = match.group("path").removeprefix("./")
                if not (ROOT / relative_path).is_file():
                    missing.append(f"{justfile.relative_to(ROOT)}:{line_number}: {relative_path}")

    assert not missing, "Just recipes reference missing scripts:\n" + "\n".join(missing)
