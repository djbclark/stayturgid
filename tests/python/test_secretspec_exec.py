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


def test_publisher_verifies_boundary_and_values():
    from pathlib import Path

    root = Path(__file__).parents[2]
    publisher = (root / "control/bin/publish_secrets.sh").read_text()
    assert not (root / "secretspec.toml").exists()
    # doctor covers the boundary, check covers the values. There is no
    # tracked declarations file anymore, so there is nothing for
    # template-check to diff against.
    assert "sudo-secretspec doctor" in publisher
    assert "sudo-secretspec check --reason" in publisher
    assert "sudo-secretspec template-check" not in publisher
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


def _real_boundary(monkeypatch, *, vault, companion):
    """Swap the conftest stub for the real check, with a fake vault and PATH."""
    real = REAL_BOUNDARY_AVAILABLE
    monkeypatch.setattr(secretspec_exec, "boundary_available", real)
    real.cache_clear()
    monkeypatch.setattr(
        secretspec_exec.shutil, "which", lambda _: "/opt/homebrew/bin/sudo-secretspec" if companion else None
    )
    monkeypatch.setattr(secretspec_exec, "VAULT_DIR", str(vault))
    return real


def test_force_direct_env_var_is_refused_on_a_provisioned_control_node(monkeypatch, tmp_path):
    """#287: an operator-UID process must not opt out of the broker by env var."""
    vault = tmp_path / "vault"
    vault.mkdir()
    real = _real_boundary(monkeypatch, vault=vault, companion=True)
    monkeypatch.setenv(secretspec_exec.FORCE_DIRECT_ENV, "1")
    try:
        with pytest.raises(secretspec_exec.BoundaryUnavailable, match="refused on a provisioned"):
            real()
        with pytest.raises(secretspec_exec.BoundaryUnavailable):
            secretspec_exec.secretspec_run("ansible-playbook", "site.yml")
    finally:
        real.cache_clear()


def test_force_direct_env_var_selects_direct_where_no_vault_exists(monkeypatch, tmp_path):
    real = _real_boundary(monkeypatch, vault=tmp_path / "absent-vault", companion=True)
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


def test_half_installed_boundary_stops_instead_of_falling_back(monkeypatch, capsys, tmp_path):
    """#287: a broker failure stops dependent work; it never authorizes another provider."""
    vault = tmp_path / "vault"
    vault.mkdir()
    real = _real_boundary(monkeypatch, vault=vault, companion=False)
    monkeypatch.delenv(secretspec_exec.FORCE_DIRECT_ENV, raising=False)
    try:
        with pytest.raises(secretspec_exec.BoundaryUnavailable, match="Refusing to fall back"):
            real()
        for build in (
            lambda: secretspec_exec.secretspec_run("ansible-playbook", "site.yml"),
            lambda: secretspec_exec.secretspec_command("get", "SOME_SECRET"),
            lambda: secretspec_exec.secretspec_token_command(secretspec_exec.APPROVED_SECRET),
        ):
            with pytest.raises(secretspec_exec.BoundaryUnavailable):
                build()
    finally:
        real.cache_clear()


def test_operator_uid_cannot_bypass_a_broken_broker_with_another_manifest(monkeypatch, tmp_path):
    """#287 adversarial case: broker unavailable, caller writes its own manifest.

    Whatever the caller does in its own directory or environment, the seam
    still refuses to build a direct command on a provisioned node.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    rogue = tmp_path / "rogue"
    rogue.mkdir()
    (rogue / "secretspec.toml").write_text('[project]\nname = "rogue"\n')
    monkeypatch.chdir(rogue)
    monkeypatch.setenv(secretspec_exec.ALTERNATE_MANIFEST_ENV, str(rogue / "secretspec.toml"))
    real = _real_boundary(monkeypatch, vault=vault, companion=False)
    try:
        for force in (None, "1"):
            if force:
                monkeypatch.setenv(secretspec_exec.FORCE_DIRECT_ENV, force)
            real.cache_clear()
            with pytest.raises(secretspec_exec.BoundaryUnavailable):
                secretspec_exec.secretspec_run("ansible-playbook", "site.yml")
            with pytest.raises((ValueError, secretspec_exec.BoundaryUnavailable)):
                secretspec_exec.secretspec_command("--file", str(rogue / "secretspec.toml"), "get", "X")
    finally:
        real.cache_clear()


@pytest.mark.parametrize(
    "args",
    [
        ("--file", "other.toml", "get", "X"),
        ("-f", "other.toml", "check"),
        ("--file=other.toml", "run", "--", "ansible-playbook", "site.yml"),
        ("run", "--file", "other.toml", "--", "ansible-playbook", "site.yml"),
    ],
)
def test_alternate_manifest_flags_are_refused_on_every_path(monkeypatch, args, force_direct):
    with pytest.raises(ValueError, match="alternate SecretSpec manifest"):
        secretspec_exec.secretspec_command(*args)
    force_brokered(monkeypatch)
    with pytest.raises(ValueError, match="alternate SecretSpec manifest"):
        secretspec_exec.secretspec_command(*args)


def test_target_command_flags_after_the_separator_are_not_selectors(force_direct):
    # `-f` after `--` is ansible-playbook's fork count, not a SecretSpec flag.
    assert secretspec_exec.secretspec_run("ansible-playbook", "-f", "5", "site.yml")[-3:] == ["-f", "5", "site.yml"]


def test_secretspec_file_env_is_refused_on_the_direct_path(monkeypatch, force_direct):
    monkeypatch.setenv(secretspec_exec.ALTERNATE_MANIFEST_ENV, "/tmp/other.toml")
    with pytest.raises(ValueError, match="SECRETSPEC_FILE"):
        secretspec_exec.secretspec_run("ansible-playbook", "site.yml")
    with pytest.raises(ValueError, match="SECRETSPEC_FILE"):
        secretspec_exec.secretspec_token_command(secretspec_exec.APPROVED_SECRET)


def test_secretspec_file_env_is_harmless_on_the_brokered_path(monkeypatch):
    # The companion purges every SECRETSPEC_* variable before it execs.
    force_brokered(monkeypatch)
    monkeypatch.setenv(secretspec_exec.ALTERNATE_MANIFEST_ENV, "/tmp/other.toml")
    assert secretspec_exec.secretspec_run("ansible-playbook", "site.yml")[0] == "sudo-secretspec"


def test_no_alternate_manifest_or_env_store_is_tracked_or_selected():
    """#287 static gate: nothing in this repo is a second source of secret truth.

    Fails on a tracked SecretSpec manifest or `.env` store (templates and
    `.example` files are declarations, not stores), and on executable code that
    selects an alternate manifest via SECRETSPEC_FILE or `secretspec --file`.
    """
    import re
    import subprocess
    from pathlib import Path

    root = Path(__file__).parents[2]
    try:
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True, timeout=60
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("not a git checkout")

    stores = []
    for rel in tracked:
        name = rel.rsplit("/", 1)[-1]
        if name.endswith((".j2", ".example")):
            continue
        if name == "secretspec.toml" or name == ".env" or re.fullmatch(r"\.env\.[^.]+", name):
            stores.append(rel)
    assert stores == [], f"tracked secret manifests/stores: {stores}"

    selector = re.compile(r"SECRETSPEC_FILE|\bsecretspec\b[^\n]*\s(--file|-f)\b")
    offenders = []
    for rel in tracked:
        if not rel.startswith(("control/", "just/", "device/", "ansible/", "ansible_collections/")):
            continue
        if not rel.endswith((".py", ".sh", ".just", ".j2", ".yml", ".yaml")) and rel != "justfile":
            continue
        path = root / rel
        if path.is_symlink() or not path.is_file():
            continue
        code = _executable_source(path) if rel.endswith((".py", ".sh")) else path.read_text(errors="replace")
        if rel == "control/lib/secretspec_exec.py":
            continue  # the module that names the selectors in order to refuse them
        if selector.search(code):
            offenders.append(rel)
    assert offenders == [], f"code selecting an alternate SecretSpec manifest: {offenders}"


def test_conftest_alone_makes_both_module_spellings_importable():
    """Regression for #312: a single test file must run on its own.

    The autouse `_secretspec_boundary_present` fixture imports both
    `secretspec_exec` and `control.lib.secretspec_exec`. The second spelling
    needs the repo root on sys.path. It used to arrive only because some other
    collected test file happened to add it, so `pytest <one file>` errored at
    fixture setup while the full suite stayed green. Load conftest in a fresh
    interpreter with nothing else on the path and import both spellings.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    tests_dir = Path(__file__).resolve().parent
    probe = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('conftest', {str(tests_dir / 'conftest.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "import secretspec_exec\n"
        "import control.lib.secretspec_exec\n"
        "print('ok')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        cwd="/",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
