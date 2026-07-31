"""Unit tests for just/tools/add_generated_header.py."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_MOD = REPO / "just" / "tools" / "add_generated_header.py"
_spec = importlib.util.spec_from_file_location("add_generated_header", _MOD)
assert _spec is not None
agh = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(agh)


# --- pure header logic ------------------------------------------------------


def test_header_line_index_no_shebang() -> None:
    assert agh.header_line_index('"use strict";\nconsole.log(1);\n') == 0


def test_header_line_index_with_shebang() -> None:
    assert agh.header_line_index("#!/usr/bin/env node\nconsole.log(1);\n") == 1


def test_header_line_index_empty_file() -> None:
    assert agh.header_line_index("") == 0


def test_has_header_true_no_shebang() -> None:
    assert agh.has_header('// @generated\n"use strict";\n') is True


def test_has_header_true_after_shebang() -> None:
    assert agh.has_header("#!/usr/bin/env node\n// @generated\nconsole.log(1);\n") is True


def test_has_header_false_missing() -> None:
    assert agh.has_header('"use strict";\nconsole.log(1);\n') is False


def test_has_header_false_shebang_file_missing_header() -> None:
    """A shebang file with no header at all — the old shell check would have
    looked at line 1 (the shebang) and never noticed either way; this must
    still correctly report "missing" rather than false-passing."""
    assert agh.has_header("#!/usr/bin/env node\nconsole.log(1);\n") is False


def test_inject_header_no_shebang() -> None:
    result = agh.inject_header('"use strict";\nconsole.log(1);\n')
    assert result == '// @generated\n"use strict";\nconsole.log(1);\n'


def test_inject_header_with_shebang() -> None:
    result = agh.inject_header("#!/usr/bin/env node\nconsole.log(1);\n")
    assert result == "#!/usr/bin/env node\n// @generated\nconsole.log(1);\n"


def test_inject_header_idempotent() -> None:
    once = agh.inject_header('"use strict";\nconsole.log(1);\n')
    twice = agh.inject_header(once)
    assert once == twice


def test_inject_header_idempotent_with_shebang() -> None:
    once = agh.inject_header("#!/usr/bin/env node\nconsole.log(1);\n")
    twice = agh.inject_header(once)
    assert once == twice


def test_inject_header_preserves_no_trailing_newline() -> None:
    result = agh.inject_header('"use strict";')
    assert result == '// @generated\n"use strict";'


def test_inject_header_empty_file() -> None:
    result = agh.inject_header("")
    assert result == "// @generated\n"


# --- find_js_files -----------------------------------------------------------


def test_find_js_files_scopes_to_known_dirs_and_excludes_node_modules(tmp_path: Path) -> None:
    (tmp_path / "just" / "tools").mkdir(parents=True)
    (tmp_path / "just" / "tools" / "a.js").write_text("a")
    (tmp_path / "just" / "tools" / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "just" / "tools" / "node_modules" / "pkg" / "b.js").write_text("b")
    (tmp_path / "docs" / "research").mkdir(parents=True)
    (tmp_path / "docs" / "research" / "c.js").write_text("c")
    (tmp_path / "control" / "bin").mkdir(parents=True)
    (tmp_path / "control" / "bin" / "unrelated.js").write_text("d")

    found = agh.find_js_files(tmp_path)
    rel = sorted(str(p.relative_to(tmp_path)) for p in found)
    assert rel == ["docs/research/c.js", "just/tools/a.js"]


# --- main() end-to-end (inject + --check) ------------------------------------


def _write_fixture_tree(root: Path) -> None:
    research = root / "docs" / "research"
    research.mkdir(parents=True)
    (research / "plain.js").write_text('"use strict";\nconsole.log(1);\n')
    tools = root / "just" / "tools"
    tools.mkdir(parents=True)
    (tools / "with_shebang.js").write_text("#!/usr/bin/env node\nconsole.log(1);\n")


def test_main_inject_mode_adds_headers(tmp_path: Path, monkeypatch) -> None:
    _write_fixture_tree(tmp_path)
    monkeypatch.setattr(agh, "__file__", str(tmp_path / "just" / "tools" / "add_generated_header.py"))

    code = agh.main([])
    assert code == 0

    plain = (tmp_path / "docs" / "research" / "plain.js").read_text()
    assert plain.startswith("// @generated\n")
    shebang_file = (tmp_path / "just" / "tools" / "with_shebang.js").read_text()
    lines = shebang_file.splitlines()
    assert lines[0] == "#!/usr/bin/env node"
    assert lines[1] == "// @generated"


def test_main_inject_mode_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    _write_fixture_tree(tmp_path)
    monkeypatch.setattr(agh, "__file__", str(tmp_path / "just" / "tools" / "add_generated_header.py"))

    agh.main([])
    first_pass = (tmp_path / "docs" / "research" / "plain.js").read_text()
    agh.main([])
    second_pass = (tmp_path / "docs" / "research" / "plain.js").read_text()
    assert first_pass == second_pass


def test_main_check_mode_fails_before_inject_and_passes_after(tmp_path: Path, monkeypatch) -> None:
    _write_fixture_tree(tmp_path)
    monkeypatch.setattr(agh, "__file__", str(tmp_path / "just" / "tools" / "add_generated_header.py"))

    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    assert agh.main(["--check"]) == 1
    assert "with_shebang.js" in stderr.getvalue() or "plain.js" in stderr.getvalue()

    agh.main([])
    assert agh.main(["--check"]) == 0


def test_main_check_mode_reports_shebang_file_correctly(tmp_path: Path, monkeypatch) -> None:
    """Regression: a file with the header correctly on line 2 (after a shebang)
    must not be reported as missing just because line 1 isn't the header."""
    root = tmp_path
    tools = root / "just" / "tools"
    tools.mkdir(parents=True)
    (tools / "with_shebang.js").write_text("#!/usr/bin/env node\n// @generated\nconsole.log(1);\n")
    monkeypatch.setattr(agh, "__file__", str(tools / "add_generated_header.py"))

    assert agh.main(["--check"]) == 0
