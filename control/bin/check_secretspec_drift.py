#!/usr/bin/env python3
"""Static gate against SecretSpec source-of-truth drift (#287).

The canonical secret store is the ``sudo-secretspec`` vault at
``/var/db/sudo-secretspec``. Nothing in this repository may become a second
source of truth or tell a reader to use one. This checker fails when:

``store``
    a SecretSpec manifest or ``.env`` store is tracked (templates ending in
    ``.j2`` and ``.example`` files are declarations, not stores);
``selector``
    executable code points SecretSpec at an alternate manifest
    (``SECRETSPEC_FILE``, ``secretspec --file``/``-f``);
``plain-cli``
    executable code, or a current instruction, calls the plain ``secretspec``
    CLI instead of the ``sudo-secretspec`` companion;
``retired``
    executable code, or a current instruction, names a retired SecretSpec
    artifact (the tracked ``secretspec.toml.example`` declarations file and
    its ``template-check``, the ``/var/db/stayturgid-secrets`` vault, the
    ``_secretspec`` wrapper, the PR-gating CI manifest) as if it were live.

``control/lib/secretspec_exec.py`` is exempt from ``selector`` and
``plain-cli``: it names the selectors in order to refuse them, and its direct
path is the one CI uses on machines without the vault.

A documentation line passes when it, the two lines before it, or its nearest
Markdown heading says the thing is historical (``retired``, ``historical``,
``earlier``, ``formerly``, ``no longer``, ``superseded``, ``was``/``were``)
or forbids it (``refuse``, ``reject``, ``never``, ``forbidden``, ``not
allowed``, ``do not``), and when its section opens with a ``> Historical``
callout. Archived plans, research, session handoffs and correspondence under
``docs/`` are records, not instructions, and are not scanned.

Stdlib only. Run from anywhere inside the checkout::

    python3 control/bin/check_secretspec_drift.py

Exit status: 0 clean, 1 drift found, 2 not a git checkout.
Runtime drift (wrapper hashes, vault ownership/mode) is ``sudo-secretspec
doctor``'s job, not this file's: it needs the installed boundary.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

SEAM = "control/lib/secretspec_exec.py"
SELF = "control/bin/check_secretspec_drift.py"

# Where executable code lives, and which suffixes count as code.
CODE_PREFIXES = ("control/", "just/", "device/", "ansible/", "ansible_collections/", "examples/", ".github/")
CODE_FILES = ("justfile", ".mcp.json")
CODE_SUFFIXES = (".py", ".sh", ".just", ".j2", ".yml", ".yaml", ".json", ".toml")

# Current instructions: agent rules, top-level docs, and docs/ minus records.
DOC_FILES = ("AGENTS.md", "README.md", "SITE-CONTRACT.md")
DOC_RECORD_PREFIXES = (
    "docs/archive/",
    "docs/research/",
    "docs/operations/sessions/",
    "docs/operations/plans/",
    "docs/correspondence/",
)

SELECTOR = re.compile(r"SECRETSPEC_FILE|(?<![\w/.-])secretspec\b[^\n]*\s(?:--file\b|-f)")
PLAIN_CLI_TEXT = re.compile(
    r"(?<![\w/.-])secretspec\s+(?:run|get|set|check|add|delete|export|import|config|init|schema)\b"
)
PLAIN_CLI_PY = re.compile(r"""[\[(,]\s*["']secretspec["']\s*,""")
RETIRED = re.compile(
    r"secretspec\.toml\.example|template-check|/var/db/stayturgid-secrets"
    r"|stayturgid-secretspec-wrapper|ci-secretspec\.toml|verify_secretspec_sync"
)
HISTORICAL = re.compile(
    r"\b(?:retired|retire|historical|history|earlier|formerly|no longer|superseded|replaced|was|were)\b",
    re.IGNORECASE,
)
PROHIBITIVE = re.compile(
    r"\b(?:refuse[sd]?|reject(?:s|ed)?|never|forbid(?:s|den)?|not allowed|do not|don't)\b", re.IGNORECASE
)
CALLOUT_HISTORICAL = re.compile(r"^>\s*(?:\[!\w+\]\s*)?\**historical\b", re.IGNORECASE)
HEADING = re.compile(r"^#{1,6}\s")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.text.strip()[:160]}"


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True, check=True, timeout=60
    ).stdout
    return [p for p in out.split("\0") if p]


def is_store(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if name.endswith((".j2", ".example")):
        return False
    return name in ("secretspec.toml", ".env") or re.fullmatch(r"\.env\.[^.]+", name) is not None


def is_code(rel: str) -> bool:
    if rel in CODE_FILES:
        return True
    return rel.startswith(CODE_PREFIXES) and rel.endswith(CODE_SUFFIXES)


def is_doc(rel: str) -> bool:
    if rel in DOC_FILES:
        return True
    return rel.startswith("docs/") and rel.endswith(".md") and not rel.startswith(DOC_RECORD_PREFIXES)


def code_lines(path: Path) -> list[tuple[int, str]]:
    """Lines of a code file with comments and Python docstrings blanked.

    String literals that are *not* docstrings stay: an error message or an
    ``os.environ["SECRETSPEC_FILE"]`` is exactly what this gate is for.
    """
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    if path.suffix == ".py":
        blank: set[tuple[int, int, int, int]] = set()
        prev = tokenize.NEWLINE
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.COMMENT:
                    blank.add((tok.start[0], tok.start[1], tok.end[0], tok.end[1]))
                elif tok.type == tokenize.STRING and prev in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                    blank.add((tok.start[0], tok.start[1], tok.end[0], tok.end[1]))
                if tok.type not in (tokenize.NL, tokenize.COMMENT):
                    prev = tok.type
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return list(enumerate(lines, 1))
        for sl, sc, el, ec in blank:
            for ln in range(sl, el + 1):
                s = sc if ln == sl else 0
                e = ec if ln == el else len(lines[ln - 1])
                lines[ln - 1] = lines[ln - 1][:s] + " " * (e - s) + lines[ln - 1][e:]
        return list(enumerate(lines, 1))
    if path.suffix in (".sh", ".just", ".yml", ".yaml", ".toml") or path.name == "justfile":
        return [(n, re.sub(r"(^|\s)#.*$", "", line)) for n, line in enumerate(lines, 1)]
    return list(enumerate(lines, 1))


def _excused(lines: list[str], idx: int, heading: str) -> bool:
    window = " ".join(lines[max(0, idx - 2) : idx + 1])
    return bool(HISTORICAL.search(window) or PROHIBITIVE.search(window) or HISTORICAL.search(heading))


def scan(root: Path, files: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for rel in files:
        path = root / rel
        if is_store(rel):
            findings.append(Finding(rel, 0, "store", "tracked SecretSpec manifest or .env store"))
        if rel == SELF or path.is_symlink() or not path.is_file():
            continue
        if is_code(rel):
            for n, line in code_lines(path):
                if rel != SEAM and SELECTOR.search(line):
                    findings.append(Finding(rel, n, "selector", line))
                plain = PLAIN_CLI_PY.search(line) if rel.endswith(".py") else PLAIN_CLI_TEXT.search(line)
                if rel != SEAM and plain:
                    findings.append(Finding(rel, n, "plain-cli", line))
                if RETIRED.search(line):
                    findings.append(Finding(rel, n, "retired", line))
        elif is_doc(rel):
            lines = path.read_text(errors="replace").splitlines()
            heading = ""
            fenced = False
            historical_section = False
            for i, line in enumerate(lines):
                if line.lstrip().startswith(("```", "~~~")):
                    fenced = not fenced
                if not fenced and HEADING.match(line):
                    heading = line
                    historical_section = False
                    continue
                if not fenced and CALLOUT_HISTORICAL.match(line):
                    historical_section = True
                if historical_section:
                    continue
                for rule, rx in (("retired", RETIRED), ("plain-cli", PLAIN_CLI_TEXT), ("selector", SELECTOR)):
                    if rx.search(line) and not _excused(lines, i, heading):
                        findings.append(Finding(rel, i + 1, rule, line))
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--root", type=Path, help="checkout root (default: the git toplevel of this file)")
    args = ap.parse_args(argv)
    root = args.root or Path(__file__).resolve().parents[2]
    try:
        files = tracked_files(root)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"check_secretspec_drift: not a git checkout: {exc}", file=sys.stderr)
        return 2
    findings = scan(root, files)
    for f in findings:
        print(f)
    if findings:
        print(
            f"check_secretspec_drift: {len(findings)} finding(s). The vault behind sudo-secretspec is the "
            "only secret store; see docs/operations/secretspec-boundary-lifecycle.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
