"""Checks for the core-versus-site ownership manifest (issue #50, ADR 007).

The schema checks always run. The checks that compare the manifest with the
tracked files (every glob matches something, every in-scope file belongs to
exactly one concern) only warn by default, so adding a playbook or script does
not break `just test` before the operator has adopted the manifest. Set
STAYTURGID_OWNERSHIP_STRICT=1 to make them fail instead.
"""

import os
import subprocess
import warnings
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/architecture/ownership-manifest.yml"
DISPOSITIONS = {
    "core",
    "site",
    "private",
    "shared-contract",
    "retire",
    "core+site-data",
    "split",
    "decision-needed",
}
DECISIONS = {f"D{i}" for i in range(1, 8)}
SCOPE_DIRS = ("ansible/", "ansible_collections/", "control/", "device/", "examples/", "just/")
SCOPE_FILES = {"justfile"}
STRICT = os.environ.get("STAYTURGID_OWNERSHIP_STRICT") == "1"


def _manifest():
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _git_ls(*pathspec):
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", *pathspec],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {line for line in out.splitlines() if line}


def _report(problems, what):
    if not problems:
        return
    message = f"ownership manifest: {what}: " + ", ".join(sorted(problems)[:40])
    if STRICT:
        pytest.fail(message)
    warnings.warn(message, stacklevel=2)


def test_manifest_schema():
    concerns = _manifest()
    assert isinstance(concerns, list) and concerns
    seen = set()
    for entry in concerns:
        assert {"concern", "title", "paths", "disposition"} <= entry.keys(), entry
        assert entry["concern"] not in seen, entry["concern"]
        seen.add(entry["concern"])
        assert entry["disposition"] in DISPOSITIONS, entry["concern"]
        assert entry.get("decision", "D1") in DECISIONS, entry["concern"]
        if entry["disposition"] == "decision-needed":
            assert "decision" in entry, entry["concern"]
        assert entry["paths"] and all(isinstance(p, str) and p for p in entry["paths"]), entry["concern"]


def test_every_glob_matches_a_tracked_file():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    empty = [
        f"{entry['concern']}:{glob}"
        for entry in _manifest()
        for glob in entry["paths"]
        if not _git_ls(f":(glob){glob}")
    ]
    _report(empty, "globs that match no tracked file")


def test_in_scope_files_belong_to_exactly_one_concern():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    owners = defaultdict(set)
    for entry in _manifest():
        for path in _git_ls(*(f":(glob){glob}" for glob in entry["paths"])):
            owners[path].add(entry["concern"])
    in_scope = {path for path in _git_ls() if path.startswith(SCOPE_DIRS) or path in SCOPE_FILES}
    _report({p for p in in_scope if p not in owners}, "unclassified tracked files")
    _report({f"{p} ({'/'.join(sorted(c))})" for p, c in owners.items() if len(c) > 1}, "files in two concerns")
