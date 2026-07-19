#!/usr/bin/env python3
"""Fail closed when SITE-CONTRACT.md and literate C1 templates drift.

Entangled 2.x has no ``tangle --check`` exit code that compares disk to the
document (``entangled tangle`` exits 0 even on conflicts). This module is the
project's equivalent: load ``SITE-CONTRACT.md`` via the Entangled API, compute
expected naked-annotation content for every ``file=`` target, and compare
byte-for-byte with the checked-in templates.

Registry seeds under ``templates/registry/`` are intentionally *not* literate
(single authority: ``generate_registry_seeds``). They must still exist on disk
and are listed as known non-literate scaffold members.

Exit codes:
    0  document and literate templates match; scaffold inventory complete
    1  drift, missing files, unexpected files, or Entangled unavailable
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = CONTRACT_DIR / "templates"
SITE_CONTRACT_MD = REPO_ROOT / "SITE-CONTRACT.md"
ENTANGLED_TOML = REPO_ROOT / "entangled.toml"

# Generator-owned; must exist but are not Entangled targets.
REGISTRY_SEED_RELATIVE = frozenset(
    {
        "registry/ports.yml",
        "registry/paths.yml",
    }
)

TEMPLATE_PREFIX = "control/site_contract/templates/"


class EntangledCheckError(Exception):
    """Parity or inventory failure."""


def _require_entangled():
    try:
        from entangled.config import AnnotationMethod  # noqa: F401
        from entangled.interface import Context, Document  # noqa: F401
        from entangled.io import TransactionMode, transaction  # noqa: F401
        from entangled.io.virtual import FileCache  # noqa: F401
    except ModuleNotFoundError as exc:  # pragma: no cover - env-dependent
        raise EntangledCheckError(
            "entangled-cli is required for site-contract parity "
            "(install via tests/python/requirements.txt / just test-venv)"
        ) from exc


def _all_template_files() -> dict[str, Path]:
    if not TEMPLATE_DIR.is_dir():
        raise EntangledCheckError(f"template directory missing: {TEMPLATE_DIR}")
    files = {path.relative_to(TEMPLATE_DIR).as_posix(): path for path in TEMPLATE_DIR.rglob("*") if path.is_file()}
    if not files:
        raise EntangledCheckError(f"no template files under {TEMPLATE_DIR}")
    return files


def expected_literate_contents(*, repo_root: Path | None = None) -> dict[str, str]:
    """Return relative template path → expected text from SITE-CONTRACT.md."""
    _require_entangled()
    from entangled.config import AnnotationMethod
    from entangled.interface import Context, Document
    from entangled.io import TransactionMode, transaction
    from entangled.io.virtual import FileCache

    root = (repo_root or REPO_ROOT).resolve()
    site_contract = root / "SITE-CONTRACT.md"
    if not site_contract.is_file():
        raise EntangledCheckError(f"missing literate source: {site_contract}")
    if not (root / "entangled.toml").is_file():
        raise EntangledCheckError(f"missing Entangled config: {root / 'entangled.toml'}")

    # Entangled resolves config and paths relative to the process cwd.
    # Callers must chdir to repo root (main and tests do).
    fs = FileCache()
    doc = Document(context=Context(fs=fs))
    with transaction(TransactionMode.SHOW, fs=fs) as txn:
        doc.load(txn)
        targets = list(doc.reference_map.targets())
        if not targets:
            raise EntangledCheckError(f"{site_contract.name} defines no Entangled file= targets")
        expected: dict[str, str] = {}
        for target in targets:
            path = Path(target)
            text, _deps = doc.target_text(path)
            # Match Entangled's on-disk write normalization (final newline).
            if text and not text.endswith("\n"):
                text = text + "\n"
            elif text == "":
                # Empty fence bodies crash Entangled on write; treat as invalid.
                raise EntangledCheckError(f"Entangled target {path} has empty content")
            rel = _to_template_relative(path)
            if rel in expected:
                raise EntangledCheckError(f"duplicate Entangled target for {rel}")
            expected[rel] = text
        # AnnotationMethod imported to document naked requirement in config.
        _ = AnnotationMethod.NAKED
        return expected


def _to_template_relative(path: Path) -> str:
    posix = path.as_posix()
    if posix.startswith(TEMPLATE_PREFIX):
        return posix[len(TEMPLATE_PREFIX) :]
    # Allow targets written relative to templates/ only if misconfigured.
    if posix.startswith("templates/"):
        return posix[len("templates/") :]
    raise EntangledCheckError(
        f"Entangled target {posix!r} is outside {TEMPLATE_PREFIX} (site-contract literate scope is templates only)"
    )


def check_parity(*, repo_root: Path | None = None) -> list[str]:
    """Return a list of human-readable problems (empty means OK)."""
    root = (repo_root or REPO_ROOT).resolve()
    problems: list[str] = []

    if not (root / "SITE-CONTRACT.md").is_file():
        return [f"missing {root / 'SITE-CONTRACT.md'}"]
    if not (root / "entangled.toml").is_file():
        return [f"missing {root / 'entangled.toml'}"]

    try:
        expected = expected_literate_contents(repo_root=root)
    except EntangledCheckError as exc:
        return [str(exc)]

    template_root = root / "control" / "site_contract" / "templates"
    on_disk = {path.relative_to(template_root).as_posix(): path for path in template_root.rglob("*") if path.is_file()}

    # Every literate target must match on disk exactly.
    for rel, text in sorted(expected.items()):
        path = template_root / rel
        if rel not in on_disk:
            problems.append(f"missing tangled template: {rel}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != text:
            problems.append(f"drift: {rel} (SITE-CONTRACT.md vs templates/)")

    # Scaffold inventory: every on-disk template is literate or a registry seed.
    for rel in sorted(on_disk):
        if rel in expected:
            continue
        if rel in REGISTRY_SEED_RELATIVE:
            continue
        problems.append(f"unexpected non-literate template (not in SITE-CONTRACT.md and not a registry seed): {rel}")

    # Registry seeds must still be present (site-init depends on them).
    for rel in sorted(REGISTRY_SEED_RELATIVE):
        if rel not in on_disk:
            problems.append(f"missing generator-owned registry seed: {rel}")

    # No Entangled target may claim a registry seed path (would dual-own).
    for rel in sorted(expected):
        if rel in REGISTRY_SEED_RELATIVE:
            problems.append(
                f"registry seed {rel} must not be an Entangled target (single authority: generate_registry_seeds)"
            )

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    # Entangled loads entangled.toml from cwd.
    import os

    os.chdir(REPO_ROOT)
    try:
        problems = check_parity(repo_root=REPO_ROOT)
    except EntangledCheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if problems:
        print("error: site-contract Entangled parity failed:", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        print(
            "hint: edit SITE-CONTRACT.md then `entangled tangle --force`, "
            "or restore templates from the document; registry seeds use "
            "`python -m control.site_contract.generate_registry_seeds`",
            file=sys.stderr,
        )
        return 1

    literate = len(expected_literate_contents(repo_root=REPO_ROOT))
    print(
        f"site-contract Entangled parity OK "
        f"({literate} literate templates; {len(REGISTRY_SEED_RELATIVE)} registry seeds generator-owned)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
