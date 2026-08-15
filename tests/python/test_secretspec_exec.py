"""Regression tests for the fail-closed SecretSpec operation boundary."""

from __future__ import annotations

import pytest
import secretspec_exec

REAL_BOUNDARY_AVAILABLE = secretspec_exec.boundary_available


def _executable_source(path) -> str:
    """Return a file's source with comments and string literals removed.

    Used by the retirement checks below so they assert on what the code *does*
    rather than on what its prose mentions.
    """
    import io
    import tokenize

    if path.suffix == ".sh":
        return "\n".join(line.split("#", 1)[0] for line in path.read_text().splitlines())
    kept = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(path.read_text()).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                kept.append(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return path.read_text()  # unparseable: fall back to the blunt check
    return "\n".join(kept)


def force_brokered(monkeypatch):
    monkeypatch.setattr(secretspec_exec, "boundary_available", lambda: True)


@pytest.fixture
def force_direct(monkeypatch):
    monkeypatch.setattr(secretspec_exec, "boundary_available", lambda: False)


def test_brokered_run_targets_the_companion_and_carries_a_reason(monkeypatch):
    force_brokered(monkeypatch)
    assert secretspec_exec.secretspec_run("ansible-playbook", "site.yml") == [
        "sudo-secretspec",
        "run",
        "--reason",
        secretspec_exec.RUN_REASON,
        "--",
        "ansible-playbook",
        "site.yml",
    ]


def test_companion_is_never_wrapped_in_sudo(monkeypatch):
    """The companion elevates itself through the NOPASSWD broker path.

    Wrapping it in `sudo` would run the *client* as root, so the target would
    inherit root's environment and HOME instead of the invoking user's -- the
    exact failure the retired wrapper needed an explicit `HOME` export to
    work around.
    """
    force_brokered(monkeypatch)
    argv = secretspec_exec.secretspec_run("ansible-playbook", "site.yml")
    assert "sudo" not in argv
    assert argv[0] == secretspec_exec.BOUNDARY_BIN


def test_malicious_same_user_cannot_select_get_export_or_shell(monkeypatch):
    force_brokered(monkeypatch)
    for args in (("get", "other_secret"), ("export", "--format", "json"), ("run", "--", "/bin/sh")):
        with pytest.raises(ValueError):
            secretspec_exec.secretspec_command(*args)


def test_approved_executable_must_be_a_bare_name(monkeypatch):
    """The broker audits the target by basename and refuses path separators.

    Rejecting it here turns an opaque `audit denied: invalid command basename`
    from the broker into a message that names the actual problem.
    """
    force_brokered(monkeypatch)
    with pytest.raises(ValueError):
        secretspec_exec.secretspec_run("/usr/local/bin/ansible-playbook", "site.yml")


def test_retired_wrapper_leaves_no_callers_behind():
    """The `_secretspec` wrapper boundary was retired on 2026-08-15.

    It ran as a service account that cannot read the canonical vault, and its
    `sync_source` would have chowned that vault away from `_sudo_secretspec`.
    Any surviving reference is a path that fails closed at runtime.
    """
    from pathlib import Path

    root = Path(__file__).parents[2]
    stale = [
        "stayturgid-secretspec-wrapper.sh",
        "/var/db/stayturgid-secrets",
        "secretspec_env_exec",
        "automation-env",
        "firerpa-mcp-token",
    ]
    offenders = []
    for path in list(root.glob("control/**/*.py")) + list(root.glob("control/**/*.sh")):
        # Only executable code counts. Comments and docstrings legitimately
        # name the retired wrapper to explain why it is gone; a match there is
        # documentation, not a call path that fails closed at runtime.
        code = _executable_source(path)
        offenders += [f"{path.relative_to(root)}: {token}" for token in stale if token in code]
    assert offenders == [], f"stale references to the retired wrapper: {offenders}"


def test_publisher_verifies_boundary_values_and_schema():
    from pathlib import Path

    root = Path(__file__).parents[2]
    publisher = (root / "control/bin/publish_secrets.sh").read_text()
    assert (root / "secretspec.toml").readlink() == Path("../site-private/secretspec.toml.example")
    # doctor covers the boundary, check covers the values, template-check covers
    # drift between the runtime manifest and the tracked declarations. Dropping
    # any one of the three loses a verification the retired wrapper performed.
    assert "sudo-secretspec doctor" in publisher
    assert "sudo-secretspec check --reason" in publisher
    assert "sudo-secretspec template-check --reason" in publisher
    # `check` falls into the engine's interactive prompt when a secret is
    # missing, which blocks invisibly when this script runs unattended.
    assert "</dev/null" in publisher
    # The companion elevates itself; wrapping it in sudo would run the client
    # as root. Check the commands, not the prose explaining this.
    commands = _executable_source(root / "control/bin/publish_secrets.sh")
    assert "sudo " not in commands


def test_token_fetch_is_fixed_to_one_secret(monkeypatch):
    force_brokered(monkeypatch)
    assert secretspec_exec.secretspec_token_command(secretspec_exec.APPROVED_SECRET) == [
        "sudo-secretspec",
        "get",
        "FIRERPA_MCP_TOKEN",
        "--reason",
        secretspec_exec.TOKEN_REASON,
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
    assert secretspec_exec.secretspec_command("get", "some_secret") == ["secretspec", "get", "some_secret"]


def test_force_direct_env_var_overrides_a_provisioned_control_node(monkeypatch):
    real = REAL_BOUNDARY_AVAILABLE
    monkeypatch.setattr(secretspec_exec, "boundary_available", real)
    real.cache_clear()
    monkeypatch.setenv(secretspec_exec.FORCE_DIRECT_ENV, "1")
    try:
        assert real() is False
    finally:
        real.cache_clear()


def test_missing_companion_is_silent_when_no_vault_exists(monkeypatch, capsys, tmp_path):
    real = REAL_BOUNDARY_AVAILABLE
    monkeypatch.setattr(secretspec_exec, "boundary_available", real)
    real.cache_clear()
    monkeypatch.delenv(secretspec_exec.FORCE_DIRECT_ENV, raising=False)
    monkeypatch.setattr(secretspec_exec.shutil, "which", lambda _: None)
    monkeypatch.setattr(secretspec_exec, "VAULT_DIR", str(tmp_path / "absent-vault"))
    try:
        assert real() is False
        assert capsys.readouterr().err == ""
    finally:
        real.cache_clear()


def test_half_installed_boundary_warns_before_falling_back(monkeypatch, capsys, tmp_path):
    real = REAL_BOUNDARY_AVAILABLE
    monkeypatch.setattr(secretspec_exec, "boundary_available", real)
    real.cache_clear()
    monkeypatch.delenv(secretspec_exec.FORCE_DIRECT_ENV, raising=False)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(secretspec_exec.shutil, "which", lambda _: None)
    monkeypatch.setattr(secretspec_exec, "VAULT_DIR", str(vault))
    try:
        assert real() is False
        assert "without privilege separation" in capsys.readouterr().err
    finally:
        real.cache_clear()
