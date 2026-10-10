"""Tests for control/bin/check_secretspec_drift.py, the #287 static gate."""

from __future__ import annotations

import subprocess
from pathlib import Path

import check_secretspec_drift as drift
import pytest


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=60)
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, timeout=60)
    return tmp_path


def _rules(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, str]]:
    root = _repo(tmp_path, files)
    return sorted((f.path, f.rule) for f in drift.scan(root, drift.tracked_files(root)))


def test_this_checkout_has_no_secretspec_drift(capsys):
    """The live gate: the real repository must pass its own checker."""
    assert drift.main([]) == 0, capsys.readouterr().out


def test_clean_repo_passes(tmp_path):
    assert drift.main(["--root", str(_repo(tmp_path, {"README.md": "Use `sudo-secretspec get NAME`.\n"}))]) == 0


@pytest.mark.parametrize("name", ["secretspec.toml", ".env", "sub/.env.local", "control/secretspec.toml"])
def test_tracked_store_is_flagged(tmp_path, name):
    assert (name, "store") in _rules(tmp_path, {name: "x\n"})


@pytest.mark.parametrize("name", [".env.example", "examples/x/.env.example", "t/secretspec.toml.j2"])
def test_declarations_and_templates_are_not_stores(tmp_path, name):
    assert _rules(tmp_path, {name: "x\n"}) == []


@pytest.mark.parametrize(
    ("rel", "text"),
    [
        ("control/bin/a.sh", "secretspec --file /tmp/rogue.toml run -- true\n"),
        ("control/bin/b.sh", "secretspec -f/tmp/rogue.toml get X\n"),
        ("just/c.just", "x:\n    SECRETSPEC_FILE=/tmp/r.toml sudo-secretspec run -- y\n"),
        ("control/lib/d.py", 'import os\nos.environ["SECRETSPEC_FILE"] = "/tmp/r.toml"\n'),
        (".github/workflows/e.yml", "env:\n  SECRETSPEC_FILE: x\n"),
    ],
)
def test_alternate_manifest_selector_in_code_is_flagged(tmp_path, rel, text):
    assert (rel, "selector") in _rules(tmp_path, {rel: text})


def test_selector_named_only_in_a_comment_or_docstring_passes(tmp_path):
    files = {
        "control/bin/a.sh": "# never export SECRETSPEC_FILE here\ntrue\n",
        "control/lib/b.py": '"""SECRETSPEC_FILE is refused upstream."""\n# SECRETSPEC_FILE\nX = 1\n',
    }
    assert _rules(tmp_path, files) == []


def test_the_seam_may_name_the_selectors_it_refuses(tmp_path):
    seam = 'ALT = "SECRETSPEC_FILE"\ncmd = ["secretspec", "get", "X"]\n'
    assert _rules(tmp_path, {drift.SEAM: seam}) == []


@pytest.mark.parametrize(
    ("rel", "text"),
    [
        ("just/a.just", "x:\n    secretspec run -- ansible-playbook site.yml\n"),
        ("control/bin/b.sh", 'v="$(secretspec get TOKEN)"\n'),
        ("control/lib/c.py", 'cmd = ["secretspec", "get", "X"]\n'),
        ("AGENTS.md", "Fetch it with `secretspec get NAME`.\n"),
    ],
)
def test_plain_secretspec_cli_is_flagged(tmp_path, rel, text):
    assert (rel, "plain-cli") in _rules(tmp_path, {rel: text})


@pytest.mark.parametrize(
    "text",
    [
        "sudo-secretspec run --reason r -- ansible-playbook x\n",
        "/usr/local/bin/sudo-secretspec get --reason r X\n",
        "brew install frdminc/sudo-secretspec/sudo-secretspec\n",
    ],
)
def test_the_companion_is_not_the_plain_cli(tmp_path, text):
    assert _rules(tmp_path, {"control/bin/a.sh": text, "docs/x.md": text}) == []


@pytest.mark.parametrize(
    "text",
    [
        "Declare it in site-private/secretspec.toml.example first.\n",
        "Run `sudo-secretspec template-check` after each add.\n",
        "The vault is /var/db/stayturgid-secrets.\n",
    ],
)
def test_retired_artifact_in_a_current_doc_or_message_is_flagged(tmp_path, text):
    rules = _rules(tmp_path, {"docs/operations/x.md": text, "control/bin/m.py": f"MSG = {text.strip()!r}\n"})
    assert ("docs/operations/x.md", "retired") in rules
    assert ("control/bin/m.py", "retired") in rules


def test_historical_and_prohibitive_doc_lines_pass(tmp_path):
    doc = (
        "# Current\n\n"
        "The tracked secretspec.toml.example was retired on 2026-08-16.\n"
        "An earlier design permitted plain `secretspec run --` here.\n"
        "The seam refuses `SECRETSPEC_FILE` on the direct path.\n\n"
        "## Retired: the wrapper\n\n"
        "It used /var/db/stayturgid-secrets.\n\n"
        "## Gotchas\n\n"
        "> Historical. Kept for context.\n\n"
        "- Export HOME=/var/db/stayturgid-secrets for the wrapper.\n\n"
        "## Now\n\n"
        "Run `sudo-secretspec template-check` daily.\n"
    )
    assert _rules(tmp_path, {"docs/x.md": doc}) == [("docs/x.md", "retired")]


def test_records_under_docs_are_not_scanned(tmp_path):
    text = "Use `secretspec run --` with secretspec.toml.example.\n"
    files = {f"{prefix}x.md": text for prefix in drift.DOC_RECORD_PREFIXES}
    assert _rules(tmp_path, files) == []


def test_not_a_git_checkout_exits_2(tmp_path, capsys):
    assert drift.main(["--root", str(tmp_path / "nowhere")]) == 2
    assert "not a git checkout" in capsys.readouterr().err
