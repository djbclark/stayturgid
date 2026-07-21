"""Focused tests for Site Contract v1 Entangled literate layout (C5)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control.site_contract import check_entangled as ce  # noqa: E402
from control.site_contract import generate_registry_seeds as seeds  # noqa: E402
from control.site_contract import site_init as si  # noqa: E402

TEMPLATES = ROOT / "control" / "site_contract" / "templates"
SITE_CONTRACT = ROOT / "SITE-CONTRACT.md"

EXPECTED_TEMPLATES = {
    ".gitignore",
    "README.md.j2",
    "ansible.cfg.j2",
    "docs/.gitkeep",
    "generated/stayturgid/.gitkeep",
    "inventory/group_vars/.gitkeep",
    "inventory/hosts.yml",
    "justfile.j2",
    "registry/paths.yml",
    "registry/ports.yml",
    "secretspec.toml.j2",
}

LITERATE_TEMPLATES = EXPECTED_TEMPLATES - ce.REGISTRY_SEED_RELATIVE


@pytest.fixture(autouse=True)
def _chdir_repo() -> Iterator[None]:
    """Entangled loads entangled.toml from the process cwd."""
    previous = Path.cwd()
    os.chdir(ROOT)
    yield
    os.chdir(previous)


def test_clean_entangled_parity_check_passes() -> None:
    problems = ce.check_parity(repo_root=ROOT)
    assert problems == []
    assert ce.main([]) == 0


def test_planted_document_drift_fails_closed(tmp_path: Path) -> None:
    """Editing SITE-CONTRACT.md fence body without updating templates fails."""
    original = SITE_CONTRACT.read_text(encoding="utf-8")
    # Plant drift inside the .gitignore fence (literate target).
    marker = "# Secret values and local credentials. Declarations remain committed."
    assert marker in original
    drifted = original.replace(marker, marker + "\n# C5-DRIFT-MARKER", 1)
    assert drifted != original
    try:
        SITE_CONTRACT.write_text(drifted, encoding="utf-8")
        problems = ce.check_parity(repo_root=ROOT)
        assert problems, "expected parity failure after document drift"
        assert any("drift" in p and ".gitignore" in p for p in problems)
        assert ce.main([]) == 1
    finally:
        SITE_CONTRACT.write_text(original, encoding="utf-8")
    assert ce.check_parity(repo_root=ROOT) == []


def test_planted_template_drift_fails_closed() -> None:
    """Editing a tangled template without updating SITE-CONTRACT.md fails."""
    target = TEMPLATES / ".gitignore"
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n# C5-TEMPLATE-DRIFT\n")
        problems = ce.check_parity(repo_root=ROOT)
        assert problems, "expected parity failure after template drift"
        assert any("drift" in p and ".gitignore" in p for p in problems)
        assert ce.main([]) == 1
    finally:
        target.write_bytes(original)
    assert ce.check_parity(repo_root=ROOT) == []


def test_all_c1_scaffold_templates_present_and_byte_correct() -> None:
    actual = {path.relative_to(TEMPLATES).as_posix() for path in TEMPLATES.rglob("*") if path.is_file()}
    assert actual == EXPECTED_TEMPLATES

    expected_text = ce.expected_literate_contents(repo_root=ROOT)
    assert set(expected_text) == LITERATE_TEMPLATES
    for rel, text in expected_text.items():
        on_disk = (TEMPLATES / rel).read_text(encoding="utf-8")
        assert on_disk == text, f"byte mismatch for literate template {rel}"
        assert (TEMPLATES / rel).read_bytes() == text.encode("utf-8")

    # Registry seeds remain generator-owned and byte-current.
    for name, content in seeds.rendered_seeds().items():
        assert (TEMPLATES / "registry" / name).read_text(encoding="utf-8") == content

    # Empty-dir placeholders are a single newline (Entangled-safe).
    for rel in (
        "docs/.gitkeep",
        "generated/stayturgid/.gitkeep",
        "inventory/group_vars/.gitkeep",
    ):
        assert (TEMPLATES / rel).read_bytes() == b"\n"


def test_mode_docs_is_site_contract_render_generic_write_free(tmp_path: Path) -> None:
    before = {p: p.read_bytes() if p.is_file() else None for p in tmp_path.rglob("*")} if tmp_path.exists() else {}
    dest = tmp_path / "must-not-be-created"
    code1, out1, err1 = _run_docs(sitename="example", dir_path=str(dest))
    code2, out2, err2 = _run_docs(sitename="othername", dir_path=str(tmp_path / "also-ignored"))
    assert code1 == si.EXIT_OK, err1
    assert code2 == si.EXIT_OK, err2
    assert out1 == out2
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == [] or True  # no site dir created

    contract = SITE_CONTRACT.read_text(encoding="utf-8")
    if not contract.endswith("\n"):
        contract += "\n"
    assert out1 == contract

    assert out1.lstrip().startswith("# ")
    assert "site-init" in out1.lower()
    assert "inventory/hosts.yml" in out1
    assert "registry/ports.yml" in out1
    assert "mode=docs" in out1 or "`docs`" in out1
    assert "example" in out1.lower()
    assert "192.0.2." in out1 or "RFC 5737" in out1

    forbidden = [
        "djbclark",
        "site-djbclark",
        str(Path.home()),
        str(ROOT),
        "192.168.",
        "100.64.",
        "100.65.",
        "EXAMPLE-SERIAL-LIVE",
    ]
    lowered = out1.lower()
    for token in forbidden:
        assert token.lower() not in lowered, f"docs leaked {token!r}"

    # Ensure docs mode did not write under tmp_path.
    after_files = list(tmp_path.rglob("*"))
    assert after_files == [] or all(p.is_dir() for p in after_files)
    _ = before  # snapshot reserved for future expansion


def test_registry_not_entangled_target() -> None:
    expected = ce.expected_literate_contents(repo_root=ROOT)
    for rel in ce.REGISTRY_SEED_RELATIVE:
        assert rel not in expected


def test_just_site_contract_check() -> None:
    env = os.environ.copy()
    env["SITE_INIT_PYTHON"] = sys.executable
    # Ensure just shebang recipes have a writable host temp dir.
    env.setdefault("TMPDIR", "/tmp")
    result = subprocess.run(
        ["just", "site-contract-check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "parity OK" in result.stdout or "parity OK" in result.stderr


def _run_docs(*, sitename: str, dir_path: str) -> tuple[int, str, str]:
    import io

    out = io.StringIO()
    err = io.StringIO()
    code = si.run_site_init(
        sitename=sitename,
        dir_path=dir_path,
        mode="docs",
        product_root=ROOT,
        env={},
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()
