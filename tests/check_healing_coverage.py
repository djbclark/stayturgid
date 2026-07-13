#!/usr/bin/env python3
"""Pre-flight healing coverage checker — runs as part of `make test` (tier code).

Reads `tests/healing_registry.json` (SSOT of all desired states), scans each
healing mechanism's source files for `@heals:` / `__healing_ids__` annotations,
then cross-references:

  1. Every mechanism declared in the registry has at least one source file.
  2. Every must_cover ID for a mechanism is declared in its source files.
  3. Every should_cover ID for a mechanism is declared or a TODO is emitted.
  4. Every desired state has at least one mechanism covering it.
  5. No mechanism declares an ID that is not in the registry (drift guard).

Produces TAP on stdout. Exit 0 = all must_cover checks pass.
"""
from __future__ import annotations

import json
import os
import re
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO / "tests" / "healing_registry.json"

_HEALS_LINE_RE = re.compile(r"@heals:\s*(.+?)$")
_HEALS_PY_SET_RE = re.compile(r"__healing_ids__\s*=\s*\{(.+?)\}", re.DOTALL)
_ID_RE = re.compile(r"[A-Z][A-Z0-9]+(?:-[A-Z][A-Z0-9]+)*")

TEST_NUM = 0
FAILED = 0


def tap_ok(msg: str) -> None:
    global TEST_NUM
    TEST_NUM += 1
    print(f"ok {TEST_NUM} - {msg}")


def tap_fail(msg: str, detail: str = "") -> None:
    global TEST_NUM, FAILED
    TEST_NUM += 1
    FAILED += 1
    print(f"not ok {TEST_NUM} - {msg}")
    if detail:
        for line in detail.splitlines():
            print(f"  # {line}")


def tap_todo(msg: str, detail: str = "") -> None:
    global TEST_NUM
    TEST_NUM += 1
    print(f"ok {TEST_NUM} - {msg} # TODO {detail}")


def extract_ids_from_file(filepath: Path) -> set[str]:
    if not filepath.is_file():
        return set()
    ids: set[str] = set()
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    for m in _HEALS_LINE_RE.finditer(content):
        for id_match in _ID_RE.finditer(m.group(1)):
            ids.add(id_match.group(0))

    if filepath.suffix == ".py":
        for m in _HEALS_PY_SET_RE.finditer(content):
            for id_match in _ID_RE.finditer(m.group(1)):
                ids.add(id_match.group(0))

    return ids


def resolve_files(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for pat in patterns:
        if "*" in pat or "?" in pat:
            for p in sorted(REPO.glob(pat)):
                if str(p) not in seen:
                    seen.add(str(p))
                    paths.append(p)
        else:
            p = REPO / pat
            if p.is_file() and str(p) not in seen:
                seen.add(str(p))
                paths.append(p)
    return paths


def load_registry() -> dict[str, Any]:
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"# registry load error: {e}", file=sys.stderr)
        return {}


def main() -> int:
    reg = load_registry()
    if not reg:
        tap_fail("registry: healing_registry.json loads")
        print(f"1..{TEST_NUM}")
        return 1

    tap_ok("registry: healing_registry.json loads")

    mechanisms = reg.get("mechanisms", {})
    desired_states = reg.get("desired_states", {})

    if not mechanisms:
        tap_fail("registry: mechanisms section present and non-empty")
    else:
        tap_ok("registry: mechanisms section present and non-empty")

    if not desired_states:
        tap_fail("registry: desired_states section present and non-empty")
    else:
        tap_ok(f"registry: {len(desired_states)} desired_states defined")

    all_registry_ids = set(desired_states.keys())

    mech_ids: dict[str, set[str]] = {}
    mech_files: dict[str, list[Path]] = {}

    for mech_name, mech_conf in sorted(mechanisms.items()):
        patterns = mech_conf.get("files", [])
        files = resolve_files(patterns)
        mech_files[mech_name] = files

        if not files:
            tap_fail(
                f"mechanism '{mech_name}': no source files found",
                f"patterns: {patterns}",
            )
            mech_ids[mech_name] = set()
            continue

        combined: set[str] = set()
        for fp in files:
            combined |= extract_ids_from_file(fp)
        mech_ids[mech_name] = combined

        tap_ok(
            f"mechanism '{mech_name}': {len(files)} source file(s), "
            f"{len(combined)} healing ID(s) declared"
        )

    errors = 0

    for state_id in sorted(all_registry_ids):
        state = desired_states[state_id]
        must = set(state.get("must_cover", []))
        should = set(state.get("should_cover", []))
        unknown_must = must - set(mechanisms.keys())
        unknown_should = should - set(mechanisms.keys())

        bad_refs = unknown_must | unknown_should
        if bad_refs:
            errors += 1
            tap_fail(
                f"state '{state_id}': references unknown mechanism(s): "
                f"{' '.join(sorted(bad_refs))}",
                f"description: {state.get('description', '')}",
            )
            continue

        if not must:
            errors += 1
            tap_fail(
                f"state '{state_id}': no must_cover mechanisms defined",
                f"description: {state.get('description', '')}",
            )
            continue

        any_covered = False
        for mech in sorted(must):
            if state_id in mech_ids.get(mech, set()):
                any_covered = True
            else:
                errors += 1
                tap_fail(
                    f"state '{state_id}': missing from must_cover mechanism '{mech}'",
                    f"Add @heals: {state_id} annotation to a source file of '{mech}'",
                )

        for mech in sorted(should):
            if state_id not in mech_ids.get(mech, set()):
                tap_todo(
                    f"state '{state_id}': missing from should_cover mechanism '{mech}'"
                )

        if not any_covered:
            errors += 1
            tap_fail(
                f"state '{state_id}': NOT COVERED BY ANY MECHANISM",
                f"description: {state.get('description', '')}",
            )

    known_ids: set[str] = set()
    for mech_name in sorted(mechanisms.keys()):
        known_ids |= mech_ids.get(mech_name, set())

    unknown = known_ids - all_registry_ids
    if unknown:
        for uid in sorted(unknown):
            errors += 1
            tap_fail(
                f"drift: mechanism declares unknown ID '{uid}' not in registry",
                "Either add to healing_registry.json or remove the stale annotation",
            )

    found_no_mech = all_registry_ids - known_ids
    if found_no_mech:
        tap_todo(
            f"discovery: {len(found_no_mech)} registry ID(s) not declared "
            f"by any mechanism source (no must_cover failures above = OK)"
        )

    print(f"1..{TEST_NUM}")
    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
