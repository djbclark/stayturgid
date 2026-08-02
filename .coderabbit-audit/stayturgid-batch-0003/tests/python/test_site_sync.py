"""Focused tests for site-sync (Site Contract v1 acceptance test 3 + safety)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control.site_contract import site_init as si
from control.site_contract import site_sync as ss

FIXED_VERSION = "9.9.9-test"
FIXED_COMMIT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FIXED_SYNCED = "2026-07-19T12:00:00Z"

MANAGED_PATHS = {
    "generated/stayturgid/README.md",
    "generated/stayturgid/fragments/.keep",
    "generated/stayturgid/fragments/caddy/stayturgid.caddy",
    "generated/stayturgid/fragments/vector/stayturgid_sources.yaml",
    "generated/stayturgid/fragments/vector/stayturgid_sinks.yaml",
    "generated/stayturgid/fragments/grafana/datasources/stayturgid.yaml",
    "generated/stayturgid/fragments/grafana/dashboards/provider.yaml",
    "generated/stayturgid/fragments/grafana/dashboards/json/stayturgid-fleet.json",
    "generated/stayturgid/fragments/grafana/alerting/rules.yaml",
    "generated/stayturgid/fragments/olivetin/stayturgid_actions.yaml",
    "generated/stayturgid/inventory/placeholder_inventory.yml",
    "generated/stayturgid/inventory/group_vars/all.yml",
    "generated/stayturgid/inventory/group_vars/android_11.yml",
    "generated/stayturgid/inventory/group_vars/android_16.yml",
    "generated/stayturgid/inventory/group_vars/model_galaxy_s24.yml",
    "generated/stayturgid/inventory/group_vars/model_kindle_hd8.yml",
    "generated/stayturgid/inventory/group_vars/model_pixel_7a.yml",
    "generated/stayturgid/inventory/group_vars/oneui_7.yml",
    "generated/stayturgid/inventory/group_vars/vendor_amazon.yml",
    "generated/stayturgid/inventory/group_vars/vendor_google.yml",
    "generated/stayturgid/inventory/group_vars/vendor_samsung.yml",
}
LOCKFILE = "generated/stayturgid/.lockfile.yml"


def _snapshot(path: Path) -> dict[str, bytes | None]:
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


def _init_site(tmp_path: Path, name: str = "example") -> Path:
    dest = tmp_path / f"site-{name}"
    err = io.StringIO()
    code = si.run_site_init(
        sitename=name,
        dir_path=str(dest),
        mode="apply",
        product_root=ROOT,
        env={},
        stdout=io.StringIO(),
        stderr=err,
    )
    assert code == si.EXIT_OK, err.getvalue()
    return dest


def _run_api(
    *,
    dir_path: str | None = None,
    mode: str = "apply",
    force_generated: bool | str = False,
    env: dict[str, str] | None = None,
    manifest_path: Path | None = None,
    product_version: str | None = FIXED_VERSION,
    product_commit: str | None = FIXED_COMMIT,
    synced: str | None = FIXED_SYNCED,
) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = ss.run_site_sync(
        dir_path=dir_path,
        mode=mode,
        force_generated=force_generated,
        product_root=ROOT,
        env=env if env is not None else {},
        manifest_path=manifest_path,
        product_version=product_version,
        product_commit=product_commit,
        synced=synced,
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def _run_cli(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "control.site_contract.site_sync", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=full_env,
    )


def _parse_actions(stdout: str) -> dict[str, str]:
    actions: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        assert len(parts) == 2, line
        actions[parts[1]] = parts[0]
    return actions


def _write_reduced_manifest(path: Path, *, keep: list[str]) -> None:
    """Write a manifest listing only the given managed relative paths."""
    full = yaml.safe_load((ROOT / "control/site_contract/sync_manifest.yml").read_text(encoding="utf-8"))
    files = [item for item in full["files"] if item["path"] in keep]
    assert files, "keep list must match at least one real manifest entry"
    full["files"] = files
    path.write_text(yaml.safe_dump(full, default_flow_style=False, sort_keys=False), encoding="utf-8")


# --- dry-run: actions, no writes -------------------------------------------


def test_dry_run_lists_actions_and_writes_nothing(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    before = _snapshot(dest)

    code, stdout, stderr = _run_api(dir_path=str(dest), mode="dry-run")
    assert code == ss.EXIT_OK, stderr
    assert _snapshot(dest) == before

    actions = _parse_actions(stdout)
    assert set(actions) == MANAGED_PATHS | {LOCKFILE}
    assert all(actions[p] == "create" for p in MANAGED_PATHS)
    assert actions[LOCKFILE] == "create"


def test_dry_run_via_cli_module(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    before = _snapshot(dest)
    result = _run_cli(["--dir", str(dest), "--mode", "dry-run"])
    assert result.returncode == 0, result.stderr
    assert "create" in result.stdout
    assert _snapshot(dest) == before


# --- apply: create lockfile + files; second apply no-op --------------------


def test_apply_creates_generated_and_lockfile_second_apply_noop(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    user_marker = dest / "docs" / "operator-note.md"
    user_marker.write_text("user owned\n", encoding="utf-8")
    outside_before = user_marker.read_bytes()

    code, _stdout, stderr = _run_api(dir_path=str(dest), mode="apply")
    assert code == ss.EXIT_OK, stderr

    for rel in MANAGED_PATHS:
        assert (dest / rel).is_file(), rel
    lock_path = dest / LOCKFILE
    assert lock_path.is_file()
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    assert lock["contract_version"] == 1
    assert lock["product"] == "stayturgid"
    assert lock["product_version"] == FIXED_VERSION
    assert lock["product_commit"] == FIXED_COMMIT
    assert lock["synced"] == FIXED_SYNCED
    assert {item["path"] for item in lock["files"]} == MANAGED_PATHS
    for item in lock["files"]:
        on_disk = (dest / item["path"]).read_bytes()
        assert item["sha256"] == hashlib.sha256(on_disk).hexdigest()

    # User area untouched.
    assert user_marker.read_bytes() == outside_before
    assert (dest / "README.md").is_file()
    assert (dest / "registry/ports.yml").is_file()

    after_first = _snapshot(dest)
    code2, dry_out, stderr2 = _run_api(dir_path=str(dest), mode="apply")
    assert code2 == ss.EXIT_OK, stderr2
    assert _snapshot(dest) == after_first

    code3, dry_out, dry_err = _run_api(dir_path=str(dest), mode="dry-run")
    assert code3 == ss.EXIT_OK, dry_err
    actions = _parse_actions(dry_out)
    assert all(action == "skip" for action in actions.values())


def test_apply_via_just_wrapper(tmp_path: Path) -> None:
    dest = _init_site(tmp_path, name="justsync")
    result = subprocess.run(
        [
            "just",
            "--justfile",
            str(ROOT / "justfile"),
            "--working-directory",
            str(ROOT),
            "site-sync",
            f"dir={dest}",
            "mode=apply",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / LOCKFILE).is_file()
    assert (dest / "generated/stayturgid/README.md").is_file()


# --- Acceptance test 4: site-map remap ------------------------------------


def test_site_map_remapped_inventory_used_and_default_never_written(tmp_path: Path) -> None:
    dest = tmp_path / "site-mapped"
    dest.mkdir()
    (dest / "site-map.yml").write_text(
        "contract_version: 1\npaths:\n  inventory: ansible/inventories/home/hosts.yml\n",
        encoding="utf-8",
    )
    init_code = si.run_site_init(
        sitename="mapped",
        dir_path=str(dest),
        mode="apply",
        product_root=ROOT,
        env={},
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert init_code == si.EXIT_OK
    mapped_inventory = dest / "ansible/inventories/home/hosts.yml"
    assert mapped_inventory.is_file()
    assert not (dest / "inventory").exists()

    code, _, stderr = _run_api(dir_path=str(dest), mode="apply")
    assert code == ss.EXIT_OK, stderr
    generated = (dest / "generated/stayturgid/README.md").read_text(encoding="utf-8")
    assert "ansible/inventories/home/hosts.yml" in generated
    assert not (dest / "inventory").exists()


def test_sync_invalid_auto_discovered_map_exits_1_naming_unknown_key(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    (dest / "site-map.yml").write_text(
        "contract_version: 1\npaths:\n  unknown_path: inventory/hosts.yml\n",
        encoding="utf-8",
    )
    before = _snapshot(dest)
    code, _, stderr = _run_api(dir_path=str(dest), mode="apply")
    assert code == ss.EXIT_PRECONDITION
    assert "unknown_path" in stderr
    assert _snapshot(dest) == before


# --- Acceptance test 3: hand-edit → exit 2; force-generated recovers -------


def test_hand_edit_exits_2_naming_file_force_generated_recovers(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    assert _run_api(dir_path=str(dest), mode="apply")[0] == ss.EXIT_OK

    target = dest / "generated/stayturgid/README.md"
    original = target.read_bytes()
    target.write_text("# hand edited — should trip drift\n", encoding="utf-8")
    user_marker = dest / "docs" / "keep-me.md"
    user_marker.write_text("outside\n", encoding="utf-8")
    before = _snapshot(dest)

    code, stdout, stderr = _run_api(dir_path=str(dest), mode="apply")
    assert code == ss.EXIT_WOULD_OVERWRITE
    assert "README.md" in stderr
    assert "generated/stayturgid/README.md" in stderr or "README.md" in stderr
    assert _snapshot(dest) == before
    assert target.read_text(encoding="utf-8") == "# hand edited — should trip drift\n"
    assert user_marker.read_text(encoding="utf-8") == "outside\n"

    code_dry, dry_out, dry_err = _run_api(dir_path=str(dest), mode="dry-run")
    assert code_dry == ss.EXIT_WOULD_OVERWRITE
    assert any(line.startswith("overwrite") and "README.md" in line for line in dry_out.splitlines())
    assert "README.md" in dry_err
    assert _snapshot(dest) == before

    code_force, _, err_force = _run_api(dir_path=str(dest), mode="apply", force_generated=True)
    assert code_force == ss.EXIT_OK, err_force
    # force re-renders from product (same fixed version/commit → original content)
    assert target.read_bytes() == original
    assert user_marker.read_text(encoding="utf-8") == "outside\n"
    # User area outside generated still present and unchanged.
    assert (dest / "inventory/hosts.yml").is_file()


def test_force_generated_via_cli_flag(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    assert _run_cli(["--dir", str(dest), "--mode", "apply"]).returncode == 0
    readme = dest / "generated/stayturgid/README.md"
    readme.write_text("drift\n", encoding="utf-8")
    blocked = _run_cli(["--dir", str(dest), "--mode", "apply"])
    assert blocked.returncode == 2
    forced = _run_cli(["--dir", str(dest), "--mode", "apply", "--force-generated"])
    assert forced.returncode == 0, forced.stderr
    assert readme.read_text(encoding="utf-8") != "drift\n"


# --- Manifest removal → delete ---------------------------------------------


def test_manifest_removal_lists_delete_then_apply_deletes(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    assert _run_api(dir_path=str(dest), mode="apply")[0] == ss.EXIT_OK
    keep_path = "generated/stayturgid/README.md"
    drop_path = "generated/stayturgid/fragments/.keep"
    assert (dest / drop_path).is_file()

    reduced = tmp_path / "reduced-manifest.yml"
    _write_reduced_manifest(reduced, keep=[keep_path])

    before = _snapshot(dest)
    code_dry, dry_out, dry_err = _run_api(
        dir_path=str(dest),
        mode="dry-run",
        manifest_path=reduced,
    )
    assert code_dry == ss.EXIT_OK, dry_err
    assert _snapshot(dest) == before
    actions = _parse_actions(dry_out)
    assert actions[drop_path] == "delete"
    assert actions[keep_path] == "skip"
    assert actions[LOCKFILE] in {"overwrite", "create", "skip"}

    code_apply, _, err = _run_api(dir_path=str(dest), mode="apply", manifest_path=reduced)
    assert code_apply == ss.EXIT_OK, err
    assert not (dest / drop_path).exists()
    assert (dest / keep_path).is_file()
    lock = yaml.safe_load((dest / LOCKFILE).read_text(encoding="utf-8"))
    assert {item["path"] for item in lock["files"]} == {keep_path}
    # User area untouched.
    assert (dest / "registry/ports.yml").is_file()


def test_manifest_removal_of_hand_edited_file_is_refused_without_force(tmp_path: Path) -> None:
    """The delete path must run the same drift check the overwrite path
    runs: a hand-edited generated file must not be silently destroyed just
    because its manifest entry disappeared (see FINAL-REVIEW finding)."""
    dest = _init_site(tmp_path)
    assert _run_api(dir_path=str(dest), mode="apply")[0] == ss.EXIT_OK
    keep_path = "generated/stayturgid/README.md"
    drop_path = "generated/stayturgid/fragments/.keep"
    target = dest / drop_path
    target.write_text("hand edited — should trip drift on delete too\n", encoding="utf-8")

    reduced = tmp_path / "reduced-manifest.yml"
    _write_reduced_manifest(reduced, keep=[keep_path])

    before = _snapshot(dest)
    code_dry, dry_out, dry_err = _run_api(dir_path=str(dest), mode="dry-run", manifest_path=reduced)
    assert code_dry == ss.EXIT_WOULD_OVERWRITE
    assert drop_path in dry_err
    assert _snapshot(dest) == before

    code, _, stderr = _run_api(dir_path=str(dest), mode="apply", manifest_path=reduced)
    assert code == ss.EXIT_WOULD_OVERWRITE
    assert drop_path in stderr
    assert _snapshot(dest) == before
    assert target.is_file()

    code_force, _, err_force = _run_api(dir_path=str(dest), mode="apply", manifest_path=reduced, force_generated=True)
    assert code_force == ss.EXIT_OK, err_force
    assert not target.exists()


# --- Inventory-controlled values are escaped, not spliced raw -------------


def test_crafted_inventory_names_render_safely_not_corrupted(tmp_path: Path) -> None:
    """host.name / device_label must not be able to break JSON/YAML structure
    or escape their intended shell argument when rendered into fragments
    (see FINAL-REVIEW findings on the grafana dashboard + olivetin actions
    templates)."""
    dest = _init_site(tmp_path)
    crafted_name = 'evil;touch-pwned-marker"}'
    crafted_label = 'Say "hi"\\ and go'
    inventory_doc = {
        "all": {
            "children": {
                "stayturgid": {
                    "hosts": {crafted_name: {"device_label": crafted_label}},
                }
            }
        }
    }
    # Use PyYAML's own dumper (not hand-rolled string quoting — Python str
    # repr() and YAML quoted-scalar escaping rules differ) so the file we
    # write is guaranteed to round-trip back to exactly `crafted_name` /
    # `crafted_label` when site-sync parses it.
    (dest / "inventory/hosts.yml").write_text(
        yaml.safe_dump(inventory_doc, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    code, _, stderr = _run_api(dir_path=str(dest), mode="apply")
    assert code == ss.EXIT_OK, stderr

    dashboard = json.loads(
        (dest / "generated/stayturgid/fragments/grafana/dashboards/json/stayturgid-fleet.json").read_text(
            encoding="utf-8"
        )
    )
    host_panel = next(p for p in dashboard["panels"] if p.get("id") == 100)
    assert host_panel["title"] == f"{crafted_label} ({crafted_name})"
    assert host_panel["targets"][0]["legendFormat"] == crafted_name
    assert crafted_name in host_panel["targets"][0]["expr"]

    actions_doc = yaml.safe_load(
        (dest / "generated/stayturgid/fragments/olivetin/stayturgid_actions.yaml").read_text(encoding="utf-8")
    )
    deploy_action = next(a for a in actions_doc["actions"] if a["id"].startswith("stayturgid_deploy_"))
    assert deploy_action["title"] == f"Deploy {crafted_label} ({crafted_name})"
    shell_lines = deploy_action["shell"].strip().splitlines()
    deploy_line = next(line for line in shell_lines if line.strip().startswith("just deploy"))
    assert shlex.split(deploy_line.strip()) == ["just", "deploy", crafted_name]


# --- Never writes outside generated/<product>/ -----------------------------


def test_never_writes_outside_generated_product(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    before = {rel: data for rel, data in _snapshot(dest).items() if not rel.startswith("generated/stayturgid/")}
    assert _run_api(dir_path=str(dest), mode="apply")[0] == ss.EXIT_OK
    after = {rel: data for rel, data in _snapshot(dest).items() if not rel.startswith("generated/stayturgid/")}
    assert after == before


# --- docs mode -------------------------------------------------------------


def test_docs_mode_deterministic_generic_only(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    before = _snapshot(dest)

    code1, out1, err1 = _run_api(dir_path=str(dest), mode="docs")
    code2, out2, err2 = _run_api(dir_path=str(tmp_path / "ignored"), mode="docs")
    assert code1 == ss.EXIT_OK, err1
    assert code2 == ss.EXIT_OK, err2
    assert out1 == out2
    assert _snapshot(dest) == before
    assert not (tmp_path / "ignored").exists()

    assert out1.lstrip().startswith("# ")
    assert "site-sync" in out1.lower()
    assert "lockfile" in out1.lower()
    assert "force-generated" in out1.lower() or "--force-generated" in out1
    assert "generated/stayturgid/" in out1
    assert FIXED_VERSION not in out1  # docs uses fixed generic version, not test override
    assert "0.0.0" in out1 or "example" in out1.lower()

    forbidden = [
        "djbclark",
        "site-djbclark",
        str(Path.home()),
        str(ROOT),
        "192.168.",
        "100.64.",
        "100.65.",
        FIXED_COMMIT,
        FIXED_VERSION,
    ]
    lowered = out1.lower()
    for token in forbidden:
        assert token.lower() not in lowered, f"docs leaked {token!r}"


def test_docs_mode_via_cli_no_writes(tmp_path: Path) -> None:
    before = _snapshot(tmp_path)
    result = _run_cli(["--mode", "docs"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.lstrip().startswith("#")
    assert _snapshot(tmp_path) == before


# --- Exit 1: bad dir / missing site / nested / invalid mode ----------------


def test_missing_site_dir_exits_1(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-site"
    code, _, stderr = _run_api(dir_path=str(missing), mode="dry-run")
    assert code == ss.EXIT_PRECONDITION
    assert "error:" in stderr.lower()


def test_nested_in_product_exits_1() -> None:
    nested = ROOT / ".tmp-site-sync-nested-test"
    try:
        if nested.exists():
            shutil.rmtree(nested)
        nested.mkdir()
        code, _, stderr = _run_api(dir_path=str(nested), mode="dry-run")
        assert code == ss.EXIT_PRECONDITION
        assert "nested" in stderr.lower() or "product" in stderr.lower()
    finally:
        if nested.exists():
            shutil.rmtree(nested)


def test_destination_equals_product_exits_1() -> None:
    code, _, stderr = _run_api(dir_path=str(ROOT), mode="dry-run")
    assert code == ss.EXIT_PRECONDITION
    assert "product" in stderr.lower()


def test_discovery_zero_sites_exits_1(tmp_path: Path) -> None:
    code, _, stderr = _run_api(dir_path=None, mode="dry-run", env={"OPS_ROOT": str(tmp_path)})
    assert code == ss.EXIT_PRECONDITION
    assert "no site" in stderr.lower() or "not exist" in stderr.lower() or "found" in stderr.lower()
    assert (tmp_path / "site-private").is_dir()


def test_discovery_multiple_sites_exits_1(tmp_path: Path) -> None:
    (tmp_path / "site-a").mkdir()
    (tmp_path / "site-b").mkdir()
    code, _, stderr = _run_api(dir_path=None, mode="dry-run", env={"OPS_ROOT": str(tmp_path)})
    assert code == ss.EXIT_PRECONDITION
    assert "ambiguous" in stderr.lower() or "multiple" in stderr.lower()


def test_stayturgid_site_dir_resolution(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    code, stdout, stderr = _run_api(
        dir_path=None,
        mode="dry-run",
        env={"STAYTURGID_SITE_DIR": str(dest), "OPS_ROOT": str(tmp_path / "empty-ops")},
    )
    assert code == ss.EXIT_OK, stderr
    assert "create" in stdout
    assert f"site-sync: site directory {dest}" in stderr
    assert "source: STAYTURGID_SITE_DIR" in stderr


def test_discovery_excludes_site_private_and_announces_source(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)

    code, stdout, stderr = _run_api(
        dir_path=None,
        mode="dry-run",
        env={"OPS_ROOT": str(tmp_path)},
    )

    assert code == ss.EXIT_OK, stderr
    assert "create" in stdout
    assert f"site-sync: site directory {dest}" in stderr
    assert "source: site-* discovery" in stderr
    assert (tmp_path / "site-private").is_dir()


def test_mysite_precedes_site_glob(tmp_path: Path) -> None:
    selected = _init_site(tmp_path, "selected")
    _init_site(tmp_path, "other")
    (tmp_path / ".mysite").symlink_to(selected, target_is_directory=True)

    code, _, stderr = _run_api(
        dir_path=None,
        mode="dry-run",
        env={"OPS_ROOT": str(tmp_path)},
    )

    assert code == ss.EXIT_OK, stderr
    assert f"site-sync: site directory {selected}" in stderr
    assert "source: OPS_ROOT/.mysite" in stderr


def test_explicit_private_companion_is_rejected(tmp_path: Path) -> None:
    private = tmp_path / "site-private"
    private.mkdir()

    code, _, stderr = _run_api(
        dir_path=str(private),
        mode="dry-run",
        env={"OPS_ROOT": str(tmp_path)},
    )

    assert code == ss.EXIT_PRECONDITION
    assert "reserved for the private companion" in stderr


def test_invalid_mode_exits_1(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    code, _, stderr = _run_api(dir_path=str(dest), mode="explode")
    assert code == ss.EXIT_PRECONDITION
    assert "mode" in stderr.lower()


def test_cli_exit_codes_matrix(tmp_path: Path) -> None:
    dest = _init_site(tmp_path)
    assert _run_cli(["--dir", str(dest), "--mode", "docs"]).returncode == 0
    assert _run_cli(["--dir", str(dest), "--mode", "dry-run"]).returncode == 0
    assert _run_cli(["--dir", str(dest), "--mode", "apply"]).returncode == 0
    assert _run_cli(["--dir", str(dest), "--mode", "apply"]).returncode == 0

    (dest / "generated/stayturgid/README.md").write_text("hand\n", encoding="utf-8")
    conflict = _run_cli(["--dir", str(dest), "--mode", "apply"])
    assert conflict.returncode == 2

    missing = _run_cli(["--dir", str(tmp_path / "nope"), "--mode", "dry-run"])
    assert missing.returncode == 1


def test_just_wrapper_dry_run_and_docs(tmp_path: Path) -> None:
    dest = _init_site(tmp_path, name="justmodes")
    dry = subprocess.run(
        ["just", "site-sync", f"dir={dest}", "mode=dry-run"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert dry.returncode == 0, dry.stderr
    assert "create" in dry.stdout

    docs = subprocess.run(
        ["just", "site-sync", "mode=docs"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert docs.returncode == 0, docs.stderr
    assert docs.stdout.lstrip().startswith("#")


def test_product_overwrite_when_lock_matches(tmp_path: Path) -> None:
    """Managed file changes with product content → overwrite (not drift)."""
    dest = _init_site(tmp_path)
    assert (
        _run_api(
            dir_path=str(dest),
            mode="apply",
            product_version="1.0.0",
            product_commit="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            synced="2026-01-01T00:00:00Z",
        )[0]
        == ss.EXIT_OK
    )
    first = (dest / "generated/stayturgid/README.md").read_bytes()

    code, stdout, stderr = _run_api(
        dir_path=str(dest),
        mode="dry-run",
        product_version="2.0.0",
        product_commit="cccccccccccccccccccccccccccccccccccccccc",
        synced="2026-02-02T00:00:00Z",
    )
    assert code == ss.EXIT_OK, stderr
    actions = _parse_actions(stdout)
    assert actions["generated/stayturgid/README.md"] == "overwrite"

    code2, _, err2 = _run_api(
        dir_path=str(dest),
        mode="apply",
        product_version="2.0.0",
        product_commit="cccccccccccccccccccccccccccccccccccccccc",
        synced="2026-02-02T00:00:00Z",
    )
    assert code2 == ss.EXIT_OK, err2
    second = (dest / "generated/stayturgid/README.md").read_bytes()
    assert second != first
    assert b"2.0.0" in second
    lock = yaml.safe_load((dest / LOCKFILE).read_text(encoding="utf-8"))
    assert lock["product_version"] == "2.0.0"
    assert lock["product_commit"] == "cccccccccccccccccccccccccccccccccccccccc"


def test_product_file_filter_emits_product_source_verbatim(tmp_path: Path) -> None:
    """A sync template using the product_file filter re-publishes a product
    file verbatim (single source of truth stays in the product)."""
    product = tmp_path / "product"
    (product / "sub").mkdir(parents=True)
    src = product / "sub" / "data.yml"
    src.write_text("---\nkey: value  # product-owned\n", encoding="utf-8")
    tpl = tmp_path / "t.j2"
    tpl.write_text("# header\n{{ 'sub/data.yml' | product_file }}", encoding="utf-8")

    out = ss._render_template(tpl, {"product_root": str(product)}, product_root_path=product).decode("utf-8")
    assert out == "# header\n---\nkey: value  # product-owned\n"


def test_product_file_filter_rejects_path_escape(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()
    (tmp_path / "secret.yml").write_text("nope\n", encoding="utf-8")
    tpl = tmp_path / "t.j2"
    tpl.write_text("{{ '../secret.yml' | product_file }}", encoding="utf-8")
    try:
        ss._render_template(tpl, {"product_root": str(product)}, product_root_path=product)
    except ss.SiteSyncError as exc:
        assert "escapes product root" in str(exc)
    else:
        raise AssertionError("expected SiteSyncError for path escape")


def test_product_file_filter_no_silent_fallback_when_explicit_root_given(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()
    tpl = tmp_path / "t.j2"
    tpl.write_text("{{ 'missing.yml' | product_file }}", encoding="utf-8")
    try:
        ss._render_template(tpl, {"product_root": str(product)}, product_root_path=product)
    except ss.SiteSyncError as exc:
        assert "product_file source missing" in str(exc)
        assert str(product) in str(exc)
    else:
        raise AssertionError("expected SiteSyncError for missing explicit product file")
