"""Regression tests for the fail-closed SecretSpec operation boundary."""

from __future__ import annotations

import sys

import pytest
import secretspec_exec

REAL_WRAPPER_AVAILABLE = secretspec_exec.wrapper_available


def force_wrapped(monkeypatch):
    monkeypatch.setattr(secretspec_exec, "wrapper_available", lambda: True)


@pytest.fixture
def force_direct(monkeypatch):
    monkeypatch.setattr(secretspec_exec, "wrapper_available", lambda: False)


def test_wrapper_uses_json_helper_and_keeps_target_as_invoking_user(monkeypatch):
    force_wrapped(monkeypatch)
    assert secretspec_exec.secretspec_run("ansible-playbook", "site.yml") == [
        sys.executable,
        secretspec_exec.HELPER_PATH,
        "ansible-playbook",
        "site.yml",
    ]


def test_malicious_same_user_cannot_select_get_export_or_shell(monkeypatch):
    force_wrapped(monkeypatch)
    for args in (("get", "other_secret"), ("export", "--format", "json"), ("run", "--", "/bin/sh")):
        with pytest.raises(ValueError):
            secretspec_exec.secretspec_command(*args)


def test_wrapper_script_rejects_arbitrary_secret_spec_arguments():
    import subprocess
    from pathlib import Path

    wrapper = Path(__file__).parents[2] / "control" / "bin" / "stayturgid-secretspec-wrapper.sh"
    result = subprocess.run(["bash", str(wrapper), "get", "other_secret"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "denied" in result.stderr
    assert '"$@"' not in wrapper.read_text()


def test_firerpa_operation_is_fixed_to_one_token(monkeypatch):
    force_wrapped(monkeypatch)
    assert secretspec_exec.secretspec_token_command("firerpa_mcp_token") == [
        "sudo",
        "-n",
        "-u",
        "_secretspec",
        secretspec_exec.WRAPPER_PATH,
        "firerpa-mcp-token",
    ]
    with pytest.raises(ValueError):
        secretspec_exec.secretspec_token_command("other_secret")


def test_falls_back_to_direct_secretspec_without_the_boundary(force_direct):
    assert secretspec_exec.secretspec_run("ansible-playbook", "site.yml") == [
        "secretspec",
        "run",
        "--",
        "ansible-playbook",
        "site.yml",
    ]
    assert secretspec_exec.secretspec_command("get", "firerpa_mcp_token") == ["secretspec", "get", "firerpa_mcp_token"]


def test_force_direct_env_var_overrides_a_provisioned_control_node(monkeypatch):
    real = REAL_WRAPPER_AVAILABLE
    monkeypatch.setattr(secretspec_exec, "wrapper_available", real)
    real.cache_clear()
    monkeypatch.setenv(secretspec_exec.FORCE_DIRECT_ENV, "1")
    try:
        assert real() is False
    finally:
        real.cache_clear()


def test_missing_wrapper_is_silent_when_no_vault_exists(monkeypatch, capsys, tmp_path):
    real = REAL_WRAPPER_AVAILABLE
    monkeypatch.setattr(secretspec_exec, "wrapper_available", real)
    real.cache_clear()
    monkeypatch.delenv(secretspec_exec.FORCE_DIRECT_ENV, raising=False)
    monkeypatch.setattr(secretspec_exec, "WRAPPER_PATH", str(tmp_path / "absent.sh"))
    monkeypatch.setattr(secretspec_exec, "VAULT_DIR", str(tmp_path / "absent-vault"))
    try:
        assert real() is False
        assert capsys.readouterr().err == ""
    finally:
        real.cache_clear()


def test_half_installed_boundary_warns_before_falling_back(monkeypatch, capsys, tmp_path):
    real = REAL_WRAPPER_AVAILABLE
    monkeypatch.setattr(secretspec_exec, "wrapper_available", real)
    real.cache_clear()
    monkeypatch.delenv(secretspec_exec.FORCE_DIRECT_ENV, raising=False)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(secretspec_exec, "WRAPPER_PATH", str(tmp_path / "absent.sh"))
    monkeypatch.setattr(secretspec_exec, "VAULT_DIR", str(vault))
    try:
        assert real() is False
        assert "without privilege separation" in capsys.readouterr().err
    finally:
        real.cache_clear()
