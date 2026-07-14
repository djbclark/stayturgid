#!/usr/bin/env python3
"""Pre-flight healing coverage checker — runs as part of `just test` (tier code).

Reads `tests/healing_registry.json` (SSOT of all desired states), scans each
healing mechanism's source files for `@heals:` annotations, cross-references:

  1. Every mechanism declared in the registry has at least one source file.
  2. Every must_cover ID for a mechanism is declared in its source files.
  3. Every should_cover ID for a mechanism is declared or a TODO is emitted.
  4. Every desired state has at least one mechanism covering it.
  5. No mechanism declares an ID that is not in the registry (drift guard).

Modes:
  default  — full TAP output on stdout
  --summary — one-line pass/fail message; exit 0/1 only (no TAP)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO / "tests" / "healing_registry.json"

_HEALS_LINE_RE = re.compile(r"@heals:\s*(.+?)$", re.MULTILINE)
_HEALS_PY_SET_RE = re.compile(r"__healing_ids__\s*=\s*\{(.+?)\}", re.DOTALL)
_ID_RE = re.compile(r"[A-Z][A-Z0-9]+(?:-[A-Z][A-Z0-9]+)*")


@dataclass
class CheckResult:
    registry_loaded: bool = False
    num_states: int = 0
    mech_counts: dict[str, int] = field(default_factory=dict)
    missing_must: list[tuple[str, str]] = field(default_factory=list)
    missing_should: list[tuple[str, str]] = field(default_factory=list)
    uncovered_states: list[str] = field(default_factory=list)
    drift_ids: set[str] = field(default_factory=set)
    unknown_mechs: set[str] = field(default_factory=set)
    no_must_defined: list[str] = field(default_factory=list)
    errors: int = 0


def extract_ids_from_file(filepath: Path) -> set[str]:
    """Extract healing IDs from a source file via @heals: annotations."""
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


def run_check() -> CheckResult:
    """Run the full cross-reference check. Returns result without printing TAP."""
    r = CheckResult()
    reg = load_registry()
    r.registry_loaded = bool(reg)
    if not reg:
        r.errors += 1
        return r

    mechanisms = reg.get("mechanisms", {})
    desired_states = reg.get("desired_states", {})
    r.num_states = len(desired_states)

    if not mechanisms or not desired_states:
        r.errors += 1
        return r

    all_registry_ids = set(desired_states.keys())
    all_mech_names = set(mechanisms.keys())
    mech_ids: dict[str, set[str]] = {}

    for mech_name, mech_conf in sorted(mechanisms.items()):
        files = resolve_files(mech_conf.get("files", []))
        if not files:
            r.errors += 1
            mech_ids[mech_name] = set()
            continue
        combined: set[str] = set()
        for fp in files:
            combined |= extract_ids_from_file(fp)
        mech_ids[mech_name] = combined
        r.mech_counts[mech_name] = len(combined)

    for state_id in sorted(all_registry_ids):
        state = desired_states[state_id]
        must = set(state.get("must_cover", []))
        should = set(state.get("should_cover", []))

        bad_refs = (must | should) - all_mech_names
        if bad_refs:
            r.errors += 1
            r.unknown_mechs |= bad_refs
            continue

        if not must:
            r.errors += 1
            r.no_must_defined.append(state_id)
            continue

        any_covered = False
        for mech in sorted(must):
            if state_id in mech_ids.get(mech, set()):
                any_covered = True
            else:
                r.errors += 1
                r.missing_must.append((state_id, mech))

        for mech in sorted(should):
            if state_id not in mech_ids.get(mech, set()):
                r.missing_should.append((state_id, mech))

        if not any_covered:
            r.uncovered_states.append(state_id)

    known_ids: set[str] = set()
    for mech_name in sorted(all_mech_names):
        known_ids |= mech_ids.get(mech_name, set())

    r.drift_ids = known_ids - all_registry_ids
    if r.drift_ids:
        r.errors += len(r.drift_ids)

    return r


def emit_tap(r: CheckResult) -> int:
    """Produce TAP output from a CheckResult. Returns exit code."""
    n = 0
    failed = 0

    def ok(msg):
        nonlocal n
        n += 1
        print(f"ok {n} - {msg}")

    def fail(msg, detail=""):
        nonlocal n, failed
        n += 1
        failed += 1
        print(f"not ok {n} - {msg}")
        if detail:
            for line in detail.splitlines():
                print(f"  # {line}")

    def todo(msg):
        nonlocal n
        n += 1
        print(f"ok {n} - {msg} # TODO")

    if not r.registry_loaded:
        fail("registry: healing_registry.json loads")
        print(f"1..{n}")
        return 1

    ok("registry: healing_registry.json loads")
    ok(f"registry: {r.num_states} desired_states defined")

    for mech_name, count in sorted(r.mech_counts.items()):
        ok(f"mechanism '{mech_name}': {count} healing ID(s) declared")

    for state_id, mech in sorted(r.missing_must):
        fail(
            f"state '{state_id}': missing from must_cover mechanism '{mech}'",
            f"Add @heals: {state_id} annotation to a source file of '{mech}'",
        )

    for state_id, mech in sorted(r.missing_should):
        todo(f"state '{state_id}': missing from should_cover mechanism '{mech}'")

    for state_id in sorted(r.uncovered_states):
        fail(f"state '{state_id}': NOT COVERED BY ANY MECHANISM")

    for uid in sorted(r.drift_ids):
        fail(
            f"drift: mechanism declares unknown ID '{uid}' not in registry",
            "Either add to healing_registry.json or remove the stale annotation",
        )

    print(f"1..{n}")
    return 1 if failed > 0 else 0


def emit_summary(r: CheckResult) -> int:
    """Produce a one-line summary message. Returns exit code."""
    if not r.registry_loaded:
        print("FAIL: healing_registry.json could not be loaded")
        return 1

    mech_info = ", ".join(
        f"{m}={c}" for m, c in sorted(r.mech_counts.items())
    )

    if r.errors == 0:
        print(
            f"PASS: healing coverage — {r.num_states} states, "
            f"{len(r.mech_counts)} mechanisms ({mech_info})"
        )
        return 0

    parts = []
    if r.missing_must:
        parts.append(f"{len(r.missing_must)} must_cover gap(s)")
    if r.uncovered_states:
        parts.append(f"{len(r.uncovered_states)} uncovered state(s)")
    if r.drift_ids:
        parts.append(f"{len(r.drift_ids)} drift ID(s)")
    if not parts:
        parts.append("unknown error")

    print(
        f"FAIL: healing coverage — {', '.join(parts)}. "
        f"Run without --summary for details."
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Healing coverage checker")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="One-line pass/fail message (no TAP output)",
    )
    parser.add_argument(
        "--tap",
        dest="tap",
        action="store_true",
        default=True,
        help="Full TAP output (default)",
    )
    args = parser.parse_args()

    r = run_check()
    if args.summary:
        return emit_summary(r)
    return emit_tap(r)


if __name__ == "__main__":
    sys.exit(main())
