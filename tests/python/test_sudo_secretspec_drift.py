"""Fail-closed SecretSpec drift guard tests."""

from __future__ import annotations

import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

CHECKER = Path(__file__).parents[2] / "control/bin/sudo-secretspec-drift-check"
LOADER = SourceFileLoader("sudo_secretspec_drift_check", str(CHECKER))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
DRIFT = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(DRIFT)
drift = DRIFT


def layout(tmp_path: Path):
    home = tmp_path / "home"
    ops = home / "ops"
    share = tmp_path / "share"
    home.mkdir()
    (home / ".config").mkdir()
    (ops / "site-private").mkdir(parents=True)
    (ops / "stayturgid" / "control" / "bin").mkdir(parents=True)
    (ops / "site-djbclark").mkdir(parents=True)
    share.mkdir()
    sentinel = share / "sudo-secretspec-retired.toml"
    sentinel.write_text(drift.RETIRED_SENTINEL)
    (home / ".config" / "secretspec.toml").symlink_to(sentinel)
    (ops / "site-private" / "secretspec.toml.example").write_text("[profiles.default]\n")
    (ops / "stayturgid" / "secretspec.toml").symlink_to("../site-private/secretspec.toml.example")
    (ops / "site-djbclark" / "secretspec.toml").symlink_to("../site-private/secretspec.toml.example")
    (home / ".bashrc").write_text("# clean\n")
    wrapper = ops / "stayturgid" / "control" / "bin" / "sudo-secretspec-broker"
    wrapper.write_text("#!/bin/bash\n")
    wrapper.chmod(0o755)
    client = ops / "stayturgid" / "control" / "bin" / "sudo-secretspec"
    client.write_text("#!/usr/bin/env python3\n")
    client.chmod(0o755)
    installed = tmp_path / "installed"
    installed.mkdir()
    installed_wrapper = installed / "wrapper"
    installed_client = installed / "client"
    installed_wrapper.write_bytes(wrapper.read_bytes())
    installed_client.write_bytes(client.read_bytes())
    canonical = tmp_path / "canonical"
    canonical.mkdir(mode=0o700)
    return drift.Layout(
        home=home,
        ops_root=ops,
        retired_target=sentinel,
        canonical_dir=canonical,
        installed_wrapper=installed_wrapper,
        installed_client=installed_client,
        verify_audit=False,
        verify_artifacts=False,
        verify_store=False,
    )


def codes(report: dict) -> set[str]:
    return {finding["code"] for finding in report["findings"]}


def test_clean_layout_passes_without_repair(tmp_path: Path):
    cfg = layout(tmp_path)
    before = {p: p.lstat() for p in (cfg.retired_path, cfg.retired_target, cfg.bashrc)}
    report = drift.inspect(cfg, environ={})
    assert report["ok"] is True
    assert report["findings"] == []
    for path, stat_before in before.items():
        stat_after = path.lstat()
        assert (stat_after.st_dev, stat_after.st_ino, stat_after.st_mtime_ns) == (
            stat_before.st_dev,
            stat_before.st_ino,
            stat_before.st_mtime_ns,
        )


def test_0600_file_in_operator_writable_parent_is_still_removable(tmp_path: Path):
    writable_parent = tmp_path / "operator-controlled"
    writable_parent.mkdir(mode=0o700)
    canonical = writable_parent / "vault"
    canonical.mkdir(mode=0o700)
    protected_file = canonical / ".env"
    protected_file.write_text("not-inspected")
    protected_file.chmod(0o600)
    assert drift._store_is_removable(
        canonical,
        required_realpath=canonical.resolve(),
        ancestors=(writable_parent,),
    )


def test_forbidden_global_regular_manifest_fails(tmp_path: Path):
    cfg = layout(tmp_path)
    cfg.retired_path.unlink()
    cfg.retired_path.write_text("[profiles.default]\n")
    assert "GLOBAL_MANIFEST_NOT_SENTINEL" in codes(drift.inspect(cfg, environ={}))


def test_checkout_manifest_and_dotenv_fail(tmp_path: Path):
    cfg = layout(tmp_path)
    cfg.checkout_manifest.write_text("[profiles.default]\n")
    cfg.checkout_env.write_text("VALUE=redacted\n")
    result = codes(drift.inspect(cfg, environ={}))
    assert {"CHECKOUT_MANIFEST_PRESENT", "CHECKOUT_ENV_PRESENT"} <= result


def test_stale_environment_and_shell_exports_fail(tmp_path: Path):
    cfg = layout(tmp_path)
    cfg.bashrc.write_text('export SECRETSPEC_FILE="$HOME/ops/site-private/secretspec.toml"\n')
    result = codes(drift.inspect(cfg, environ={"SECRETSPEC_FILE": "/tmp/alternate.toml"}))
    assert {"SECRETSPEC_FILE_SET", "SHELL_OVERRIDE_PRESENT"} <= result


def test_legacy_shell_client_fails(tmp_path: Path):
    cfg = layout(tmp_path)
    cfg.bashrc.write_text("secretspec() { sudo wrapper; }\n")
    assert "SHELL_LEGACY_CLIENT_PRESENT" in codes(drift.inspect(cfg, environ={}))


def test_live_hermes_script_direct_cli_fails(tmp_path: Path):
    cfg = layout(tmp_path)
    script = cfg.home / ".hermes" / "scripts" / "bad.sh"
    script.parent.mkdir(parents=True)
    script.write_text("value=$(secretspec get EXAMPLE_KEY)\n")
    assert "DIRECT_CLI_BYPASS" in codes(drift.inspect(cfg, environ={}))


def test_direct_file_bypass_in_active_script_fails(tmp_path: Path):
    cfg = layout(tmp_path)
    script = cfg.ops_root / "site-private" / "bin" / "consumer.sh"
    script.parent.mkdir()
    script.write_text("secretspec --file ~/.config/secretspec.toml run -- true\n")
    assert "DIRECT_FILE_BYPASS" in codes(drift.inspect(cfg, environ={}))


def test_retired_direct_mode_reference_is_detected(tmp_path: Path):
    cfg = layout(tmp_path)
    client = cfg.ops_root / "stayturgid" / "control" / "bad.py"
    client.write_text('mode = os.environ.get("SUDO_SECRETSPEC_DIRECT")\n')
    assert "DIRECT_MODE_REFERENCE" in codes(drift.inspect(cfg, environ={}, runtime=False))


def test_project_manifest_agent_instruction_fails(tmp_path: Path):
    cfg = layout(tmp_path)
    agents = cfg.ops_root / "stayturgid" / "AGENTS.md"
    agents.parent.mkdir(parents=True, exist_ok=True)
    agents.write_text("Secrets managed via `secretspec`. Spec at `secretspec.toml`.\n")
    assert "PROJECT_MANIFEST_INSTRUCTION" in codes(drift.inspect(cfg, environ={}, runtime=False))


def test_bad_sentinel_target_fails(tmp_path: Path):
    cfg = layout(tmp_path)
    cfg.retired_path.unlink()
    cfg.retired_path.symlink_to(tmp_path / "other.toml")
    assert "GLOBAL_SENTINEL_TARGET_MISMATCH" in codes(drift.inspect(cfg, environ={}))


def test_cli_json_is_value_free(tmp_path: Path, capsys):
    cfg = layout(tmp_path)
    cfg.checkout_env.write_text("SECRET_VALUE=must-not-appear\n")
    rc = drift.main(
        [
            "--home",
            str(cfg.home),
            "--ops-root",
            str(cfg.ops_root),
            "--retired-target",
            str(cfg.retired_target),
            "--json",
        ]
    )
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert rc == 1
    assert parsed["ok"] is False
    assert "must-not-appear" not in output
    assert "SECRET_VALUE" not in output


def test_agent_authorization_failure_message_forbids_alternate_manifest():
    message = drift.AUTHORIZATION_FAILURE
    assert "Touch ID" in message
    assert "Do not create" in message
    assert "alternate manifest" in message
    assert "provider" in message
