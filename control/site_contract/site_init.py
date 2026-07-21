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
from pathlib import Path, PurePosixPath
from typing import Literal, Sequence, TextIO

from control.site_contract.site_map import SiteMap, SiteMapError, is_physically_within, load_site_map

try:
    from jinja2 import Environment, StrictUndefined
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when deps missing
    raise SystemExit(
        "error: jinja2 is required for site-init (install ansible-core, or use the project test venv: just test-venv)"
    ) from exc

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
    nested = True
    try:
        dest.relative_to(product)
    except ValueError:
        nested = is_physically_within(dest, product)
    if not nested:
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
    site_map: SiteMap,
) -> dict[str, str]:
    product = str(product_root.resolve())
    return {
        "site_name": site_name,
        "product_root": product,
        "stayturgid_root": product,
        "site_dir": str(site_dir.resolve()),
        "inventory_path": site_map.relative_path("inventory"),
        "registry_ports_path": site_map.relative_path("registry_ports"),
        "registry_paths_path": site_map.relative_path("registry_paths"),
    }


def _render_template(template_path: Path, context: dict[str, str]) -> bytes:
    environment = Environment(  # nosemgrep
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
    map_path: str | None = None,
    product_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> InitPlan:
    """Compute the full init plan without writing anything."""
    name = validate_site_name(site_name)
    product = (product_root or REPO_ROOT).resolve()
    destination = resolve_destination(name, dir_path=dir_path, product_root=product, env=env)
    try:
        site_map = load_site_map(site_dir=destination, product_root=product, map_path=map_path)
    except SiteMapError as exc:
        raise SiteInitError(str(exc)) from exc
    context = _render_context(
        site_name=name,
        product_root=product,
        site_dir=destination,
        site_map=site_map,
    )

    planned: list[PlannedFile] = []
    for template_path in _template_files():
        relative = _mapped_destination_relative(template_path, site_map)
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

    relative_paths = [item.relative_path for item in planned]
    duplicate_paths = sorted({path for path in relative_paths if relative_paths.count(path) > 1})
    if duplicate_paths:
        raise SiteInitError("site map makes scaffold files collide at: " + ", ".join(duplicate_paths))

    # A site-map remap can also make one planned file's path double as an
    # ancestor directory of another planned file (e.g. `paths.inventory:
    # group_vars` collides with the derived `group_vars/.gitkeep`) — that
    # passes the exact-string dedup above but still crashes apply_plan()
    # mid-write, since one path can't be both a file and a directory.
    path_set = set(relative_paths)
    type_collisions = sorted(
        {
            path
            for path in relative_paths
            for ancestor in PurePosixPath(path).parents
            if str(ancestor) != "." and str(ancestor) in path_set
        }
    )
    if type_collisions:
        raise SiteInitError(
            "site map makes scaffold files collide (one path is used as both a file and a directory): "
            + ", ".join(type_collisions)
        )

    return InitPlan(
        site_name=name,
        destination=destination,
        product_root=product,
        files=tuple(planned),
    )


def _mapped_destination_relative(template_path: Path, site_map: SiteMap) -> str:
    """Map contract-owned scaffold templates onto an existing site layout."""
    default = _destination_relative(template_path)
    if default == "inventory/hosts.yml":
        return site_map.relative_path("inventory")
    if default == "inventory/group_vars/.gitkeep":
        inventory_parent = site_map.path("inventory").parent
        return (inventory_parent / "group_vars/.gitkeep").relative_to(site_map.site_dir).as_posix()
    if default == "registry/ports.yml":
        return site_map.relative_path("registry_ports")
    if default == "registry/paths.yml":
        return site_map.relative_path("registry_paths")
    return default


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
    """Self-contained Markdown for mode=docs (generic values only).

    Site Contract v1 §2 + §7: with the Entangled layout, mode=docs is a render
    of product-root ``SITE-CONTRACT.md``. The checked-in document already uses
    only generic/example identity (RFC 5737, ``example`` sitename). This path
    never reads the live site overlay, operator home, or production inventory,
    and writes nothing.
    """
    site_contract = REPO_ROOT / "SITE-CONTRACT.md"
    if not site_contract.is_file():
        raise SiteInitError(
            f"SITE-CONTRACT.md missing at {site_contract}; required for mode=docs "
            "(Site Contract v1 §7 Entangled layout)"
        )

    # Still validate that every scaffold template renders under the fixed
    # generic docs context (StrictUndefined) so docs mode cannot mask broken
    # Jinja templates.
    docs_site_dir = Path(_DOCS_SITE_DIR)
    docs_site_map = load_site_map(
        site_dir=docs_site_dir,
        product_root=Path(_DOCS_PRODUCT_ROOT),
    )
    context = _render_context(
        site_name=_DOCS_SITE_NAME,
        product_root=Path(_DOCS_PRODUCT_ROOT),
        site_dir=docs_site_dir,
        site_map=docs_site_map,
    )
    for template_path in _template_files():
        _load_payload(template_path, context)

    text = site_contract.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    return text


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
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Programmatic entry point used by tests and ``main``."""
    out: TextIO = stdout if stdout is not None else sys.stdout
    err: TextIO = stderr if stderr is not None else sys.stderr
    try:
        parsed_mode = _parse_mode(mode)
        if parsed_mode == "docs":
            print(_docs_markdown(), end="", file=out)
            return EXIT_OK

        plan = build_plan(
            sitename,
            dir_path=dir_path,
            map_path=map_path,
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
        help="optional explicit Site Contract v1 site-map.yml",
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
