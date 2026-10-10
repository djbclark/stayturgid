"""Device-side Python stays stdlib only (#309).

The pip policy in docs/hacking.md (no on-device pip packages, none declared in
device/termux/requirements.txt) rests on one fact: nothing the roles ship to
a phone imports a third-party package. This keeps that fact true. A change
that needs one fails here and has to go through the policy: the Termux apt
package first, a declared pip package only if apt lacks it.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
TERMUX_DEFAULTS = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/defaults/main.yml"
FIRERPA_FILES = REPO / "ansible_collections/stayturgid/firerpa/roles/firerpa/files"
# Repo-local packages a device script may try first and fall back from; they
# exist only on the control node, so the import must be guarded.
_GUARDED_LOCAL = {"shared", "control"}
_IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError", "Exception"}


def shipped_python_files() -> list[Path]:
    defaults = yaml.safe_load(TERMUX_DEFAULTS.read_text(encoding="utf-8"))
    files = [REPO / "device/termux/py" / name for name in defaults["stayturgid_py_scripts"]]
    files += [REPO / entry["src"] for entry in defaults["stayturgid_lib_files"] if entry["src"].endswith(".py")]
    files += sorted(FIRERPA_FILES.glob("*.py"))
    return files


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id in _IMPORT_ERRORS for n in names)


def _guarded(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """True when *node* is a try body import that an import-error handler
    catches, or the fallback import inside such a handler."""
    child, parent = node, parents.get(node)
    while parent is not None:
        if isinstance(parent, ast.Try) and child in parent.body:
            if any(_catches_import_error(h) for h in parent.handlers):
                return True
        if isinstance(parent, ast.ExceptHandler) and _catches_import_error(parent):
            return True
        child, parent = parent, parents.get(parent)
    return False


def third_party_imports(path: Path, local: set[str]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
        else:
            continue
        for module in modules:
            top = module.split(".")[0]
            if top in sys.stdlib_module_names or top in local:
                continue
            if top in _GUARDED_LOCAL and _guarded(node, parents):
                continue
            where = path.relative_to(REPO) if path.is_relative_to(REPO) else path.name
            bad.append(f"{where}:{node.lineno} imports {module}")
    return bad


def test_the_shipped_file_list_is_real():
    files = shipped_python_files()
    assert len(files) >= 20, "the role lists changed shape; update shipped_python_files()"
    missing = [str(f.relative_to(REPO)) for f in files if not f.is_file()]
    assert missing == []


def test_device_python_imports_only_stdlib_and_shipped_siblings():
    files = shipped_python_files()
    local = {f.stem for f in files}
    bad = [line for f in files for line in third_party_imports(f, local)]
    assert bad == [], (
        "device-side Python must stay stdlib only (#309, docs/hacking.md). "
        "Prefer the Termux apt package; declare a pip one in device/termux/requirements.txt "
        "only if apt lacks it:\n" + "\n".join(bad)
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import requests\n", ["imports requests"]),
        ("try:\n    import requests\nexcept ImportError:\n    requests = None\n", ["imports requests"]),
        ("from control.lib import x\n", ["imports control.lib"]),
        ("try:\n    from shared.ui_clearance import y\nexcept ImportError:\n    y = None\n", []),
        ("try:\n    import ui_clearance as uc\nexcept ImportError:\n    from shared import ui_clearance as uc\n", []),
        ("try:\n    import x\nexcept OSError:\n    from shared import y\n", ["imports x", "imports shared"]),
        ("import json, os.path\nfrom __future__ import annotations\n", []),
    ],
)
def test_the_checker_itself(tmp_path, source, expected):
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    found = third_party_imports(probe, {"ui_clearance"})  # a shipped sibling
    assert [line.split(" ", 1)[1] for line in found] == expected
