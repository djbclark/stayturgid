"""Focused tests for site-init (Site Contract v1 acceptance tests 1, 2, 6)."""

from __future__ import annotations

import configparser
import filecmp
import io
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control.site_contract import site_init as si

TEMPLATES = ROOT / "control" / "site_contract" / "templates"

EXPECTED_RELATIVE = {
    ".gitignore",
    "README.md",
    "ansible.cfg",
    "docs/.gitkeep",
    "generated/stayturgid/.gitkeep",
    "inventory/group_vars/.gitkeep",
    "inventory/hosts.yml",
    "justfile",
    "registry/paths.yml",
    "registry/ports.yml",
    "secretspec.toml",
}


def _snapshot(path: Path) -> dict[str, bytes | None]:
    """Map relative posix paths → file bytes; directories as None."""
    if not path.exists():
        return {}
    out: dict[str, bytes | None] = {}
    for item in sorted(path.rglob("*")):
        rel = item.relative_to(path).as_posix()
        if item.is_dir():
            out[rel + "/"] = None
        else:
            out[rel] = item.read_bytes()
    return out


def _run_cli(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "control.site_contract.site_init", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=full_env,
    )


def _run_api(
    *,
    sitename: str,
    dir_path: str | None = None,
    map_path: str | None = None,
    mode: str = "apply",
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = si.run_site_init(
        sitename=sitename,
        dir_path=dir_path,
        map_path=map_path,
        mode=mode,
        product_root=ROOT,
        env=env if env is not None else {},
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


# --- Acceptance test 1: dry-run, no writes ---------------------------------


def test_dry_run_empty_destination_lists_actions_and_writes_nothing(tmp_path: Path) -> None:
    dest = tmp_path / "site-example"
    assert not dest.exists()
    before_parent = _snapshot(tmp_path)

    code, stdout, stderr = _run_api(
        sitename="example",
        dir_path=str(dest),
        mode="dry-run",
    )
    assert code == si.EXIT_OK, stderr
    assert not dest.exists()
    assert _snapshot(tmp_path) == before_parent

    lines = [line for line in stdout.splitlines() if line.strip()]
    assert lines
    actions = {line.split(maxsplit=1)[0] for line in lines}
    assert actions == {"create"}
    listed = {line.split(maxsplit=1)[1] for line in lines}
    assert listed == EXPECTED_RELATIVE


def test_dry_run_via_cli_module(tmp_path: Path) -> None:
    dest = tmp_path / "empty-site"
    before = _snapshot(tmp_path)
    result = _run_cli(["--sitename", "example", "--dir", str(dest), "--mode", "dry-run"])
    assert result.returncode == 0, result.stderr
    assert "create" in result.stdout
    assert not dest.exists()
    assert _snapshot(tmp_path) == before


# --- Acceptance test 2: apply scaffold + second apply no-op ----------------


def test_apply_creates_section3_scaffold_and_second_apply_is_noop(tmp_path: Path) -> None:
    dest = tmp_path / "site-example"
    code, _stdout, stderr = _run_api(sitename="example", dir_path=str(dest), mode="apply")
    assert code == si.EXIT_OK, stderr

    actual = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    assert actual == EXPECTED_RELATIVE

    # Structured files parse; registries are the complete derived seeds.
    ports = yaml.safe_load((dest / "registry/ports.yml").read_text(encoding="utf-8"))
    paths = yaml.safe_load((dest / "registry/paths.yml").read_text(encoding="utf-8"))
    assert ports["product"] == "stayturgid"
    claims = [claim for scope in ports["product_defaults"].values() for claim in scope]
    assert len(claims) >= 10
    assert all(claim.get("port") for claim in claims)
    assert paths["prefixes"]["stayturgid"]

    assert (dest / "registry/ports.yml").read_bytes() == (TEMPLATES / "registry/ports.yml").read_bytes()
    assert (dest / "registry/paths.yml").read_bytes() == (TEMPLATES / "registry/paths.yml").read_bytes()
    assert (dest / "inventory/hosts.yml").read_bytes() == (TEMPLATES / "inventory/hosts.yml").read_bytes()
    assert (dest / ".gitignore").read_bytes() == (TEMPLATES / ".gitignore").read_bytes()

    ansible_config = configparser.ConfigParser(interpolation=None)
    ansible_config.read_string((dest / "ansible.cfg").read_text(encoding="utf-8"))
    assert ansible_config["defaults"]["inventory"] == "inventory/hosts.yml"
    assert ansible_config["defaults"]["roles_path"] == f"{ROOT}/ansible/roles"

    secret_spec = tomllib.loads((dest / "secretspec.toml").read_text(encoding="utf-8"))
    assert secret_spec["project"]["name"] == "site-example"
    assert "OPENOBSERVE_ROOT_PASSWORD" in secret_spec["profiles"]["default"]

    readme = (dest / "README.md").read_text(encoding="utf-8")
    assert "site-example" in readme
    assert "generated/stayturgid/" in readme

    just_result = subprocess.run(
        ["just", "--summary", "--justfile", str(dest / "justfile")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert just_result.returncode == 0, just_result.stderr

    after_first = _snapshot(dest)
    code2, _stdout2, stderr2 = _run_api(sitename="example", dir_path=str(dest), mode="apply")
    assert code2 == si.EXIT_OK, stderr2
    assert _snapshot(dest) == after_first

    code3, dry_out, dry_err = _run_api(sitename="example", dir_path=str(dest), mode="dry-run")
    assert code3 == si.EXIT_OK, dry_err
    dry_actions = {line.split(maxsplit=1)[0] for line in dry_out.splitlines() if line.strip()}
    assert dry_actions == {"skip"}


def test_apply_via_just_wrapper(tmp_path: Path) -> None:
    dest = tmp_path / "from-just"
    result = subprocess.run(
        [
            "just",
            "--justfile",
            str(ROOT / "justfile"),
            "--working-directory",
            str(ROOT),
            "site-init",
            "sitename=example",
            f"dir={dest}",
            "mode=apply",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / "registry/ports.yml").is_file()
    assert (dest / "inventory/hosts.yml").is_file()


def test_explicit_map_via_just_wrapper(tmp_path: Path) -> None:
    dest = tmp_path / "mapped-from-just"
    map_file = tmp_path / "site-map.yml"
    map_file.write_text(
        "contract_version: 1\npaths:\n  inventory: custom/inventory.yml\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "just",
            "site-init",
            "sitename=example",
            f"dir={dest}",
            f"map={map_file}",
            "mode=apply",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / "custom/inventory.yml").is_file()
    assert not (dest / "inventory").exists()


def test_just_wrapper_dry_run_and_docs_exit_codes(tmp_path: Path) -> None:
    dest = tmp_path / "via-just"
    dry = subprocess.run(
        ["just", "site-init", "sitename=example", f"dir={dest}", "mode=dry-run"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert dry.returncode == 0, dry.stderr
    assert "create" in dry.stdout
    assert not dest.exists()

    docs = subprocess.run(
        ["just", "site-init", "sitename=example", "mode=docs"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert docs.returncode == 0, docs.stderr
    assert docs.stdout.lstrip().startswith("#")
    assert not dest.exists()


# --- Exit 2: conflicting user-owned file, no partial writes ----------------


def test_conflicting_user_file_exits_2_without_partial_writes(tmp_path: Path) -> None:
    dest = tmp_path / "site-conflict"
    code, _, stderr = _run_api(sitename="example", dir_path=str(dest), mode="apply")
    assert code == si.EXIT_OK, stderr

    conflict = dest / "README.md"
    conflict.write_text("# user edited this\n", encoding="utf-8")
    # Also leave a marker that must not be deleted and no new files from a half-write.
    marker = dest / "docs" / "operator-note.md"
    marker.write_text("keep me\n", encoding="utf-8")
    before = _snapshot(dest)

    code2, stdout, stderr2 = _run_api(sitename="example", dir_path=str(dest), mode="apply")
    assert code2 == si.EXIT_WOULD_OVERWRITE
    assert "README.md" in stderr2
    assert _snapshot(dest) == before
    assert marker.read_text(encoding="utf-8") == "keep me\n"
    assert conflict.read_text(encoding="utf-8") == "# user edited this\n"

    code3, dry_out, dry_err = _run_api(sitename="example", dir_path=str(dest), mode="dry-run")
    assert code3 == si.EXIT_WOULD_OVERWRITE
    assert any(line.startswith("overwrite") and "README.md" in line for line in dry_out.splitlines())
    assert "README.md" in dry_err
    assert _snapshot(dest) == before


# --- Exit 1: bad input / preconditions -------------------------------------


@pytest.mark.parametrize(
    "sitename",
    ["", "Example", "site-example", "has/slash", "has space", "-leading", "UPPER", "a_b"],
)
def test_bad_sitename_exits_1(sitename: str, tmp_path: Path) -> None:
    code, _, stderr = _run_api(sitename=sitename, dir_path=str(tmp_path / "x"), mode="dry-run")
    assert code == si.EXIT_PRECONDITION
    assert stderr.strip()
    assert "error:" in stderr.lower()


def test_empty_sitename_via_just_exits_1() -> None:
    result = subprocess.run(
        ["just", "--justfile", str(ROOT / "justfile"), "--working-directory", str(ROOT), "site-init"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 1
    assert "usage:" in result.stderr.lower() or "sitename" in result.stderr.lower()


def test_explicit_map_remaps_inventory_without_writing_default(tmp_path: Path) -> None:
    dest = tmp_path / "site-example"
    map_file = tmp_path / "custom-site-map.yml"
    map_file.write_text(
        "contract_version: 1\npaths:\n  inventory: ansible/inventories/home/hosts.yml\n",
        encoding="utf-8",
    )
    code, _, stderr = _run_api(
        sitename="example",
        dir_path=str(dest),
        map_path=str(map_file),
        mode="apply",
    )
    assert code == si.EXIT_OK, stderr
    mapped = dest / "ansible/inventories/home/hosts.yml"
    assert mapped.is_file()
    assert not (dest / "inventory/hosts.yml").exists()
    assert not (dest / "inventory").exists()
    config = configparser.ConfigParser(interpolation=None)
    config.read_string((dest / "ansible.cfg").read_text(encoding="utf-8"))
    assert config["defaults"]["inventory"] == "ansible/inventories/home/hosts.yml"


@pytest.mark.parametrize(
    ("map_text", "unknown_key"),
    [
        ("contract_version: 1\ntypo: true\n", "typo"),
        ("contract_version: 1\npaths:\n  unknown_path: elsewhere/hosts.yml\n", "unknown_path"),
        ("contract_version: 1\nserverapps:\n  unknown_app: {}\n", "unknown_app"),
        ("contract_version: 1\nserverapps:\n  caddy:\n    unknown_field: caddy.d\n", "unknown_field"),
    ],
)
def test_unknown_site_map_key_exits_1_naming_key(
    tmp_path: Path,
    map_text: str,
    unknown_key: str,
) -> None:
    map_file = tmp_path / "site-map.yml"
    map_file.write_text(map_text, encoding="utf-8")
    code, _, stderr = _run_api(
        sitename="example",
        dir_path=str(tmp_path / "site-example"),
        map_path=str(map_file),
        mode="dry-run",
    )
    assert code == si.EXIT_PRECONDITION
    assert unknown_key in stderr
    assert not (tmp_path / "site-example").exists()


def test_site_map_relative_escape_exits_1_without_writes(tmp_path: Path) -> None:
    dest = tmp_path / "site-example"
    map_file = tmp_path / "site-map.yml"
    map_file.write_text("contract_version: 1\npaths:\n  inventory: ../outside.yml\n", encoding="utf-8")
    code, _, stderr = _run_api(
        sitename="example",
        dir_path=str(dest),
        map_path=str(map_file),
        mode="apply",
    )
    assert code == si.EXIT_PRECONDITION
    assert "escapes" in stderr
    assert not dest.exists()


def test_site_map_rejects_contract_path_inside_generated_area(tmp_path: Path) -> None:
    dest = tmp_path / "site-example"
    map_file = tmp_path / "site-map.yml"
    map_file.write_text(
        "contract_version: 1\npaths:\n  inventory: generated/stayturgid/hosts.yml\n",
        encoding="utf-8",
    )
    code, _, stderr = _run_api(
        sitename="example",
        dir_path=str(dest),
        map_path=str(map_file),
        mode="apply",
    )
    assert code == si.EXIT_PRECONDITION
    assert "generated/stayturgid" in stderr
    assert not dest.exists()


def test_site_map_inventory_remap_colliding_with_group_vars_dir_exits_1(tmp_path: Path) -> None:
    """A remapped `inventory` path can collide with the *derived*
    `<inventory-parent>/group_vars/.gitkeep` scaffold path (one wants
    `group_vars` as a file, the other as a directory). The exact-string
    duplicate check misses this; build_plan() must still catch it before
    any writes happen (see FINAL-REVIEW finding)."""
    dest = tmp_path / "site-example"
    map_file = tmp_path / "site-map.yml"
    map_file.write_text("contract_version: 1\npaths:\n  inventory: group_vars\n", encoding="utf-8")
    code, _, stderr = _run_api(
        sitename="example",
        dir_path=str(dest),
        map_path=str(map_file),
        mode="dry-run",
    )
    assert code == si.EXIT_PRECONDITION
    assert "collide" in stderr.lower()
    assert not dest.exists()


def test_valid_serverapp_map_is_validation_only_in_c4(tmp_path: Path) -> None:
    dest = tmp_path / "site-example"
    map_file = tmp_path / "site-map.yml"
    map_file.write_text(
        "contract_version: 1\n"
        "serverapps:\n"
        "  caddy:\n"
        "    config: /opt/homebrew/etc/Caddyfile\n"
        "    fragment_dir: /opt/homebrew/etc/caddy.d\n"
        "    mode: inject\n",
        encoding="utf-8",
    )
    before = _snapshot(tmp_path)
    code, stdout, stderr = _run_api(
        sitename="example",
        dir_path=str(dest),
        map_path=str(map_file),
        mode="dry-run",
    )
    assert code == si.EXIT_OK, stderr
    assert "create" in stdout
    assert _snapshot(tmp_path) == before
    assert not dest.exists()


def test_invalid_serverapp_mode_exits_1(tmp_path: Path) -> None:
    map_file = tmp_path / "site-map.yml"
    map_file.write_text(
        "contract_version: 1\nserverapps:\n  caddy:\n    mode: typo\n",
        encoding="utf-8",
    )
    code, _, stderr = _run_api(
        sitename="example",
        dir_path=str(tmp_path / "site-example"),
        map_path=str(map_file),
        mode="dry-run",
    )
    assert code == si.EXIT_PRECONDITION
    assert "serverapps.caddy.mode" in stderr


def test_invalid_mode_exits_1(tmp_path: Path) -> None:
    code, _, stderr = _run_api(sitename="example", dir_path=str(tmp_path / "x"), mode="explode")
    assert code == si.EXIT_PRECONDITION
    assert "mode" in stderr.lower()


# --- Nested destination rejected before write ------------------------------


def test_destination_nested_in_product_rejected(tmp_path: Path) -> None:
    nested = ROOT / ".tmp-site-init-nested-test"
    try:
        if nested.exists():
            shutil.rmtree(nested)
        code, _, stderr = _run_api(sitename="example", dir_path=str(nested), mode="apply")
        assert code == si.EXIT_PRECONDITION
        assert "nested" in stderr.lower() or "product" in stderr.lower()
        assert not nested.exists()
    finally:
        if nested.exists():
            shutil.rmtree(nested)


def test_destination_equals_product_rejected() -> None:
    code, _, stderr = _run_api(sitename="example", dir_path=str(ROOT), mode="dry-run")
    assert code == si.EXIT_PRECONDITION


def test_destination_nested_via_case_insensitive_alias_rejected(tmp_path: Path) -> None:
    """ADR-005 nesting must not be bypassable on case-insensitive filesystems.

    Default macOS APFS resolves a differently-cased path to the exact same
    physical directory; a purely string-based relative_to() check misses
    that aliasing entirely (see FINAL-REVIEW finding). Skips itself on a
    genuinely case-sensitive filesystem where the alias doesn't apply.
    """
    aliased_root = ROOT.parent / ROOT.name.upper()
    try:
        same = aliased_root.exists() and os.path.samestat(aliased_root.stat(), ROOT.stat())
    except OSError:
        same = False
    if not same:
        pytest.skip("filesystem is case-sensitive; product-root alias does not apply here")
    nested = aliased_root / ".tmp-site-init-case-alias-test"
    try:
        code, _, stderr = _run_api(sitename="example", dir_path=str(nested), mode="dry-run")
        assert code == si.EXIT_PRECONDITION
        assert "nested" in stderr.lower() or "product" in stderr.lower()
        assert not nested.exists()
    finally:
        if nested.exists():
            shutil.rmtree(nested)
    assert "product" in stderr.lower()


def test_default_destination_under_ops_root(tmp_path: Path) -> None:
    code, stdout, stderr = _run_api(
        sitename="example",
        mode="dry-run",
        env={"OPS_ROOT": str(tmp_path)},
    )
    assert code == si.EXIT_OK, stderr
    # No dir= → plan targets OPS_ROOT/site-example; dry-run must not create it.
    assert not (tmp_path / "site-example").exists()
    plan = si.build_plan("example", env={"OPS_ROOT": str(tmp_path)}, product_root=ROOT)
    assert plan.destination == (tmp_path / "site-example").resolve()


def test_private_site_name_is_reserved() -> None:
    with pytest.raises(si.SiteInitError, match="reserved for the private companion"):
        si.validate_site_name("private")


def test_explicit_private_companion_destination_is_reserved(tmp_path: Path) -> None:
    with pytest.raises(si.SiteInitError, match="reserved for the private companion"):
        si.resolve_destination(
            "example",
            dir_path=str(tmp_path / "site-private"),
            env={"OPS_ROOT": str(tmp_path)},
            product_root=ROOT,
        )


def test_literal_private_destination_is_reserved_with_custom_companion(tmp_path: Path) -> None:
    with pytest.raises(si.SiteInitError, match="reserved for the private companion"):
        si.resolve_destination(
            "example",
            dir_path=str(tmp_path / "site-private"),
            env={
                "OPS_ROOT": str(tmp_path),
                "STAYTURGID_PRIVATE_DIR": str(tmp_path / "custom-private"),
            },
            product_root=ROOT,
        )


# --- Acceptance test 6: docs mode ------------------------------------------


def test_docs_mode_is_deterministic_markdown_without_site_identity(tmp_path: Path) -> None:
    before = _snapshot(tmp_path)
    code1, out1, err1 = _run_api(sitename="example", dir_path=str(tmp_path / "ignored"), mode="docs")
    code2, out2, err2 = _run_api(sitename="othername", dir_path=str(tmp_path / "also-ignored"), mode="docs")
    assert code1 == si.EXIT_OK, err1
    assert code2 == si.EXIT_OK, err2
    assert out1 == out2
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "ignored").exists()

    assert out1.lstrip().startswith("# ")
    assert "site-init" in out1.lower()
    assert "```" in out1
    assert "inventory/hosts.yml" in out1
    assert "registry/ports.yml" in out1
    assert "mode=docs" in out1 or "`docs`" in out1

    # Generic only — no private reference-site identity or operator home path.
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

    # Allowed generic fixtures from the contract / topology docs.
    assert "example" in lowered
    assert "192.0.2." in out1 or "RFC 5737" in out1 or "rfc 5737" in lowered


def test_docs_mode_via_cli_no_writes(tmp_path: Path) -> None:
    before = _snapshot(tmp_path)
    result = _run_cli(["--sitename", "example", "--dir", str(tmp_path / "x"), "--mode", "docs"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.lstrip().startswith("#")
    assert _snapshot(tmp_path) == before


# --- Exit codes via CLI for all three modes --------------------------------


def test_cli_exit_codes_matrix(tmp_path: Path) -> None:
    dest = tmp_path / "site-matrix"
    assert _run_cli(["--sitename", "example", "--dir", str(dest), "--mode", "dry-run"]).returncode == 0
    assert _run_cli(["--sitename", "example", "--dir", str(dest), "--mode", "docs"]).returncode == 0
    assert _run_cli(["--sitename", "example", "--dir", str(dest), "--mode", "apply"]).returncode == 0
    assert _run_cli(["--sitename", "example", "--dir", str(dest), "--mode", "apply"]).returncode == 0

    (dest / "ansible.cfg").write_text("broken\n", encoding="utf-8")
    conflict = _run_cli(["--sitename", "example", "--dir", str(dest), "--mode", "apply"])
    assert conflict.returncode == 2
    assert "ansible.cfg" in conflict.stderr

    bad = _run_cli(["--sitename", "NOT_VALID", "--dir", str(dest), "--mode", "dry-run"])
    assert bad.returncode == 1


def test_two_isolated_applies_are_byte_identical(tmp_path: Path) -> None:
    """Sanity: apply output matches a second isolated apply byte-for-byte."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert _run_api(sitename="example", dir_path=str(a), mode="apply")[0] == 0
    assert _run_api(sitename="example", dir_path=str(b), mode="apply")[0] == 0
    assert _snapshot(a) == _snapshot(b)
    comparison = filecmp.dircmp(a, b)
    assert not comparison.left_only
    assert not comparison.right_only
    assert not comparison.diff_files
