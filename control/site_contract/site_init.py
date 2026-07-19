#!/usr/bin/env python3
"""Initialize a private site overlay from product site-contract templates.

Implements Site Contract v1 ``site-init`` (apply / dry-run / docs). See
``docs/architecture/site-contract.md`` §§2–3 and acceptance tests 1, 2, and 6.

Exit codes:
    0  success / no-op
    1  precondition or input failure
    2  would overwrite a user-owned file (no writes performed)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from jinja2 import Environment, StrictUndefined

PRODUCT = "stayturgid"
CONTRACT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = CONTRACT_DIR / "templates"
REPO_ROOT = CONTRACT_DIR.parents[1]

EXIT_OK = 0
EXIT_PRECONDITION = 1
EXIT_WOULD_OVERWRITE = 2

Mode = Literal["apply", "dry-run", "docs"]
ActionKind = Literal["create", "skip", "overwrite"]

# Bare site name: lowercase letter, then lowercase alphanumerics or hyphens.
_SITE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# Generic paths/names only — docs mode must never emit operator identity.
_DOCS_SITE_NAME = "example"
_DOCS_PRODUCT_ROOT = f"/srv/products/{PRODUCT}"
_DOCS_SITE_DIR = f"/srv/sites/site-{_DOCS_SITE_NAME}"


class SiteInitError(Exception):
    """Precondition or input failure for site-init."""

    def __init__(self, message: str, *, exit_code: int = EXIT_PRECONDITION) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class PlannedFile:
    """One planned file write under the destination site dir."""

    relative_path: str
    content: bytes
    action: ActionKind


@dataclass(frozen=True)
class InitPlan:
    """Fully computed site-init plan (no side effects)."""

    site_name: str
    destination: Path
    product_root: Path
    files: tuple[PlannedFile, ...]

    @property
    def conflicts(self) -> list[PlannedFile]:
        return [item for item in self.files if item.action == "overwrite"]


def _ops_root(env: dict[str, str] | None = None) -> Path:
    environ = env if env is not None else os.environ
    raw = environ.get("OPS_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / "ops").resolve()


def validate_site_name(site_name: str) -> str:
    """Return a validated bare site name or raise SiteInitError."""
    name = site_name.strip()
    if not name:
        raise SiteInitError("sitename is required (e.g. just site-init sitename=example)")
    if name.startswith("site-"):
        raise SiteInitError(
            f"sitename must be the bare name without the 'site-' prefix "
            f"(got {site_name!r}; use {name.removeprefix('site-')!r})"
        )
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise SiteInitError(f"sitename must not contain path separators: {site_name!r}")
    if not _SITE_NAME_RE.fullmatch(name):
        raise SiteInitError(
            f"sitename must match {_SITE_NAME_RE.pattern} (lowercase letter, then [a-z0-9-]*); got {site_name!r}"
        )
    if len(name) > 63:
        raise SiteInitError(f"sitename is too long ({len(name)} > 63): {site_name!r}")
    return name


def resolve_destination(
    site_name: str,
    *,
    dir_path: str | None = None,
    product_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Resolve the site directory and enforce public/private separation."""
    name = validate_site_name(site_name)
    product = (product_root or REPO_ROOT).resolve()
    if dir_path and dir_path.strip():
        destination = Path(dir_path).expanduser()
        if not destination.is_absolute():
            destination = (Path.cwd() / destination).resolve()
        else:
            destination = destination.resolve()
    else:
        destination = (_ops_root(env) / f"site-{name}").resolve()

    _reject_nested_in_product(destination, product)
    return destination


def _reject_nested_in_product(destination: Path, product_root: Path) -> None:
    product = product_root.resolve()
    dest = destination.resolve()
    if dest == product:
        raise SiteInitError(
            f"destination {dest} is the product checkout; a private site dir "
            "must not live inside (or as) the public product tree (ADR 005)"
        )
    try:
        dest.relative_to(product)
    except ValueError:
        return
    raise SiteInitError(
        f"destination {dest} is nested inside the product checkout {product}; "
        "a private site dir must never live inside a public product working tree (ADR 005)"
    )


def _template_files() -> list[Path]:
    if not TEMPLATE_DIR.is_dir():
        raise SiteInitError(f"template directory missing: {TEMPLATE_DIR}")
    files = sorted(path for path in TEMPLATE_DIR.rglob("*") if path.is_file())
    if not files:
        raise SiteInitError(f"no template files under {TEMPLATE_DIR}")
    return files


def _destination_relative(template_path: Path) -> str:
    relative = template_path.relative_to(TEMPLATE_DIR).as_posix()
    if relative.endswith(".j2"):
        return relative[: -len(".j2")]
    return relative


def _render_context(
    *,
    site_name: str,
    product_root: Path,
    site_dir: Path,
) -> dict[str, str]:
    product = str(product_root.resolve())
    return {
        "site_name": site_name,
        "product_root": product,
        "stayturgid_root": product,
        "site_dir": str(site_dir.resolve()),
    }


def _render_template(template_path: Path, context: dict[str, str]) -> bytes:
    environment = Environment(
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    text = template_path.read_text(encoding="utf-8")
    rendered = environment.from_string(text).render(**context)
    return rendered.encode("utf-8")


def _load_payload(template_path: Path, context: dict[str, str]) -> bytes:
    if template_path.suffix == ".j2" or template_path.name.endswith(".j2"):
        return _render_template(template_path, context)
    return template_path.read_bytes()


def build_plan(
    site_name: str,
    *,
    dir_path: str | None = None,
    product_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> InitPlan:
    """Compute the full init plan without writing anything."""
    name = validate_site_name(site_name)
    product = (product_root or REPO_ROOT).resolve()
    destination = resolve_destination(name, dir_path=dir_path, product_root=product, env=env)
    context = _render_context(site_name=name, product_root=product, site_dir=destination)

    planned: list[PlannedFile] = []
    for template_path in _template_files():
        relative = _destination_relative(template_path)
        content = _load_payload(template_path, context)
        target = destination / relative
        if target.exists():
            if target.is_dir():
                raise SiteInitError(f"destination path {target} exists as a directory; expected a file")
            existing = target.read_bytes()
            action: ActionKind = "skip" if existing == content else "overwrite"
        else:
            action = "create"
        planned.append(PlannedFile(relative_path=relative, content=content, action=action))

    return InitPlan(
        site_name=name,
        destination=destination,
        product_root=product,
        files=tuple(planned),
    )


def format_action_list(plan: InitPlan) -> str:
    """Exact per-file action list for dry-run (and conflict reporting)."""
    lines = [f"{item.action:9} {item.relative_path}" for item in plan.files]
    return "\n".join(lines) + ("\n" if lines else "")


def apply_plan(plan: InitPlan) -> None:
    """Write planned creates. Refuses if any overwrite would occur."""
    if plan.conflicts:
        paths = ", ".join(item.relative_path for item in plan.conflicts)
        raise SiteInitError(
            f"refusing to overwrite user-owned file(s): {paths}",
            exit_code=EXIT_WOULD_OVERWRITE,
        )
    plan.destination.mkdir(parents=True, exist_ok=True)
    for item in plan.files:
        if item.action == "skip":
            continue
        target = plan.destination / item.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)


def _docs_markdown() -> str:
    """Self-contained Markdown for mode=docs (generic values only)."""
    context = _render_context(
        site_name=_DOCS_SITE_NAME,
        product_root=Path(_DOCS_PRODUCT_ROOT),
        site_dir=Path(_DOCS_SITE_DIR),
    )
    rows: list[tuple[str, str, str]] = []
    for template_path in _template_files():
        relative = _destination_relative(template_path)
        if template_path.name.endswith(".j2"):
            kind = "Jinja2 render"
            note = (
                f"Render `{template_path.relative_to(CONTRACT_DIR).as_posix()}` with "
                f"`site_name={_DOCS_SITE_NAME!r}`, `product_root={_DOCS_PRODUCT_ROOT!r}`, "
                f"`stayturgid_root={_DOCS_PRODUCT_ROOT!r}`, `site_dir={_DOCS_SITE_DIR!r}`."
            )
            # Ensure templates still render under docs context (StrictUndefined).
            _load_payload(template_path, context)
        else:
            kind = "byte-for-byte copy"
            note = f"Copy `{template_path.relative_to(CONTRACT_DIR).as_posix()}` unchanged to `{relative}`."
        rows.append((relative, kind, note))

    lines = [
        "# site-init — manual equivalent (Site Contract v1)",
        "",
        "This document is produced by `just site-init mode=docs`. It describes every",
        "filesystem step `site-init` performs so an operator can reproduce the scaffold",
        "by hand. Values below are **generic only** (RFC 5737 / example inventory names);",
        "they are not taken from any private site overlay.",
        "",
        "## Preconditions",
        "",
        f"1. Public product checkout available (example path: `{_DOCS_PRODUCT_ROOT}`).",
        "2. Destination site directory does not nest inside the product tree (ADR 005).",
        f"3. Default destination is `$OPS_ROOT/site-<name>` (example: `{_DOCS_SITE_DIR}`).",
        "4. Bare sitename matches `^[a-z][a-z0-9-]*$` (no `site-` prefix).",
        "5. Existing destination files with **different** content block initialization",
        "   (exit code 2); identical content is skipped (idempotent no-op).",
        "",
        "## CLI",
        "",
        "```text",
        "just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]",
        "```",
        "",
        "- `mode=apply` (default): create missing files; never overwrite user content.",
        "- `mode=dry-run`: print per-file `create` / `skip` / `overwrite` actions; no writes.",
        "- `mode=docs`: emit this document; no writes.",
        "- Exit codes: `0` success/no-op; `1` bad input/precondition; `2` would overwrite.",
        "- `map=` is reserved for Phase C4 (`site-map.yml`); providing it fails closed today.",
        "",
        "## Scaffold layout",
        "",
        "```text",
        f"site-{_DOCS_SITE_NAME}/",
        "  README.md",
        "  ansible.cfg",
        "  justfile",
        "  .gitignore",
        "  inventory/",
        "    hosts.yml          # product example inventory (RFC 5737 / §4.1 names)",
        "    group_vars/",
        "  registry/",
        "    ports.yml          # product port defaults (derived seeds)",
        "    paths.yml          # product path defaults (derived seeds)",
        "  secretspec.toml",
        f"  generated/{PRODUCT}/",
        "  docs/",
        "```",
        "",
        "## Per-file steps",
        "",
        "| Destination | Action | Manual equivalent |",
        "| --- | --- | --- |",
    ]
    for relative, kind, note in rows:
        safe_note = note.replace("|", "\\|")
        lines.append(f"| `{relative}` | {kind} | {safe_note} |")

    lines.extend(
        [
            "",
            "## After initialization",
            "",
            "1. Edit `inventory/hosts.yml`: replace example aliases, RFC 5737 addresses,",
            "   and placeholder serials with this site's values.",
            "2. Reconcile `registry/ports.yml` and `registry/paths.yml` with local allocations.",
            "3. Provide secret *values* via a secretspec provider (never commit them).",
            "4. Point product tooling at the site via `STAYTURGID_SITE_DIR` or `ANSIBLE_CONFIG`,",
            "   or place the site as the sole `site-*` checkout under `$OPS_ROOT`.",
            "5. Later product upgrades use `site-sync` (Phase C3) for `generated/<product>/` only.",
            "",
            "## Invariants",
            "",
            f"- Everything outside `generated/{PRODUCT}/` is user-owned after creation.",
            "- `site-init` never overwrites a differing user file.",
            "- A second identical `apply` is a no-op (all files `skip`).",
            "- Private site data must never nest inside the public product working tree.",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_mode(value: str) -> Mode:
    mode = value.strip().lower()
    if mode not in {"apply", "dry-run", "docs"}:
        raise SiteInitError(f"mode must be apply, dry-run, or docs; got {value!r}")
    return mode  # type: ignore[return-value]


def run_site_init(
    *,
    sitename: str,
    dir_path: str | None = None,
    map_path: str | None = None,
    mode: str = "apply",
    product_root: Path | None = None,
    env: dict[str, str] | None = None,
    stdout: object | None = None,
    stderr: object | None = None,
) -> int:
    """Programmatic entry point used by tests and ``main``."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    try:
        if map_path and str(map_path).strip():
            raise SiteInitError(
                "site-map.yml support is not implemented in this phase (Phase C4); omit map= until then"
            )
        parsed_mode = _parse_mode(mode)
        if parsed_mode == "docs":
            print(_docs_markdown(), end="", file=out)
            return EXIT_OK

        plan = build_plan(
            sitename,
            dir_path=dir_path,
            product_root=product_root,
            env=env,
        )
        action_list = format_action_list(plan)
        if parsed_mode == "dry-run":
            print(action_list, end="", file=out)
            if plan.conflicts:
                conflict_paths = ", ".join(item.relative_path for item in plan.conflicts)
                print(
                    f"error: would overwrite user-owned file(s): {conflict_paths}",
                    file=err,
                )
                return EXIT_WOULD_OVERWRITE
            return EXIT_OK

        # apply
        if plan.conflicts:
            conflict_paths = ", ".join(item.relative_path for item in plan.conflicts)
            print(action_list, end="", file=out)
            print(
                f"error: refusing to overwrite user-owned file(s): {conflict_paths}",
                file=err,
            )
            return EXIT_WOULD_OVERWRITE
        apply_plan(plan)
        # Quiet success: optional summary on stderr for operators.
        created = sum(1 for item in plan.files if item.action == "create")
        skipped = sum(1 for item in plan.files if item.action == "skip")
        print(
            f"site-init: {plan.destination} (created={created}, skipped={skipped}, site_name={plan.site_name})",
            file=err,
        )
        return EXIT_OK
    except SiteInitError as exc:
        print(f"error: {exc}", file=err)
        return exc.exit_code
    except OSError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_PRECONDITION


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize a private stayturgid site overlay (Site Contract v1).",
    )
    parser.add_argument("--sitename", default="", help="bare site name (e.g. example → site-example)")
    parser.add_argument("--dir", dest="dir_path", default="", help="explicit destination directory")
    parser.add_argument(
        "--map",
        dest="map_path",
        default="",
        help="optional site-map.yml (Phase C4; rejected until then)",
    )
    parser.add_argument(
        "--mode",
        default="apply",
        help="apply (default), dry-run, or docs",
    )
    parser.add_argument(
        "assignments",
        nargs="*",
        help="optional KEY=VALUE assignments: sitename=, dir=, map=, mode=",
    )
    return parser


def _merge_assignments(
    *,
    sitename: str,
    dir_path: str,
    map_path: str,
    mode: str,
    assignments: Sequence[str],
) -> tuple[str, str, str, str]:
    """Merge KEY=VALUE tokens (from the just wrapper) into flag values."""
    allowed = {"sitename", "dir", "map", "mode"}
    values = {
        "sitename": sitename,
        "dir": dir_path,
        "map": map_path,
        "mode": mode,
    }
    for token in assignments:
        if "=" not in token:
            raise SiteInitError(
                f"unknown argument {token!r}; expected sitename= / dir= / map= / mode= or the matching --flag forms"
            )
        key, value = token.split("=", 1)
        if key not in allowed:
            raise SiteInitError(f"unknown assignment {key!r}; expected one of: {', '.join(sorted(allowed))}")
        values[key] = value
    return values["sitename"], values["dir"], values["map"], values["mode"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        sitename, dir_path, map_path, mode = _merge_assignments(
            sitename=args.sitename,
            dir_path=args.dir_path,
            map_path=args.map_path,
            mode=args.mode,
            assignments=args.assignments,
        )
    except SiteInitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    if not sitename.strip():
        print(
            "error: sitename is required (e.g. just site-init sitename=example  or  --sitename example)",
            file=sys.stderr,
        )
        return EXIT_PRECONDITION
    return run_site_init(
        sitename=sitename,
        dir_path=dir_path or None,
        map_path=map_path or None,
        mode=mode,
    )


if __name__ == "__main__":
    raise SystemExit(main())
