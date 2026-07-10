#!/usr/bin/env python3
"""Idempotent BEGIN/END marked blocks for ssh config and authorized_keys."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


def replace_marked_block(
    text: str,
    *,
    begin: str,
    end: str,
    body: str | Iterable[str],
) -> tuple[str, bool]:
    """Replace or append a marked block. Returns (new_text, changed)."""
    if isinstance(body, str):
        body_text = body.strip("\n")
    else:
        body_text = "\n".join(line.rstrip("\n") for line in body).strip("\n")

    block = begin.rstrip() + "\n"
    if body_text:
        block += body_text + "\n"
    block += end.rstrip() + "\n"

    # Match existing block (non-greedy, multiline).
    pattern = re.compile(
        re.escape(begin.rstrip()) + r"\n.*?" + re.escape(end.rstrip()) + r"\n?",
        re.DOTALL,
    )
    if pattern.search(text or ""):
        new_text = pattern.sub(block, text or "", count=1)
        # Normalize trailing newline
        if not new_text.endswith("\n") and new_text:
            new_text += "\n"
        return new_text, new_text != (text or "")

    base = text or ""
    if base and not base.endswith("\n"):
        base += "\n"
    if base and not base.endswith("\n\n"):
        # keep a blank line before a new managed block when file non-empty
        if not base.endswith("\n"):
            base += "\n"
    new_text = base + ("\n" if base and not base.endswith("\n") else "")
    if base and not base.endswith("\n"):
        new_text = base + "\n" + block
    else:
        sep = "" if (not base or base.endswith("\n")) else "\n"
        new_text = base + sep + block
    if not new_text.endswith("\n"):
        new_text += "\n"
    return new_text, new_text != (text or "")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def write_text_atomic(path: Path, text: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(mode)
    tmp.replace(path)


def ensure_marked_file(
    path: Path,
    *,
    begin: str,
    end: str,
    body: str | Iterable[str],
    mode: int = 0o600,
) -> bool:
    """Write marked block into path. Returns True if file changed."""
    old = read_text(path)
    new, changed = replace_marked_block(old, begin=begin, end=end, body=body)
    if changed:
        write_text_atomic(path, new, mode=mode)
    return changed
