"""Tests for the secretspec execution-path selector (control/lib/secretspec_exec.py).

Regression coverage for the CI breakage introduced by #247: every fleet entry
point invoked `sudo -n -u _secretspec <wrapper>` unconditionally, so on a
GitHub runner -- which has neither that user nor that wrapper -- `just syntax`
died with `sudo: unknown user _secretspec` and master stayed red from
2026-08-06 through the ops-v1.3.1 release run.
"""

from __future__ import annotations

import secretspec_exec
import pytest

# Captured at import (collection time), before conftest's autouse
# _secretspec_wrapper_present fixture swaps the module attribute for a lambda --
# by the time a test body runs, secretspec_exec.wrapper_available is that lambda
# and no longer carries .cache_clear().
REAL_WRAPPER_AVAILABLE = secretspec_exec.wrapper_available

WRAPPER_ARGV = [
    "sudo",
    "-n",
    "-u",
    "_secretspec",
    "/usr/local/libexec/stayturgid-secretspec-wrapper.sh",
]


@pytest.fixture
def force_direct(monkeypatch):
    """Override conftest's autouse wrapper-present fixture for fallback tests."""
    monkeypatch.setattr(secretspec_exec, "wrapper_available", lambda: False)


def test_wrapper_argv_is_byte_identical_to_the_pre_247_hardcoded_form():
    # The control node must see no behaviour change whatsoever from the
    # refactor -- this is the exact list every call site used to inline.
    assert secretspec_exec.secretspec_run("ansible-playbook", "site.yml") == [
        *WRAPPER_ARGV,
        "run",
        "--",
        "ansible-playbook",
        "site.yml",
    ]


def test_non_run_subcommands_pass_through_unchanged():
    # firerpa_mcp.py fetches a token with `get`, not `run --`.
    assert secretspec_exec.secretspec_command("get", "firerpa_mcp_token") == [
        *WRAPPER_ARGV,
        "get",
        "firerpa_mcp_token",
    ]


def test_falls_back_to_direct_secretspec_without_the_boundary(force_direct):
    assert secretspec_exec.secretspec_run("ansible-playbook", "site.yml") == [
        "secretspec",
        "run",
        "--",
        "ansible-playbook",
        "site.yml",
    ]


def test_fallback_preserves_argv_one_to_one(force_direct):
    # The wrapper script `exec`s `secretspec ... "$@"`, so both modes must map
    # arguments identically -- only the prefix differs.
    assert secretspec_exec.secretspec_command("get", "firerpa_mcp_token") == [
        "secretspec",
        "get",
        "firerpa_mcp_token",
    ]


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
    """A machine that never had the boundary (CI) must not emit a warning."""
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
    """Vault present but wrapper gone is a broken control node, not a CI runner.

    Degrading silently there would quietly drop privilege separation on the
    machine that actually holds the secrets, so it must be noisy.
    """
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
        err = capsys.readouterr().err
        assert "without privilege separation" in err
        assert "absent.sh" in err
    finally:
        real.cache_clear()
