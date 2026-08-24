"""Executable tests for protected mutation backup/rollback helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
WRAPPER = (ROOT / "control/bin/sudo-secretspec-broker").read_text()
FUNCTIONS = WRAPPER.split("\noperation=${1:-}", 1)[0]


def run_helper(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    vault = tmp_path / "vault"
    vault.mkdir()
    manifest = vault / "secretspec.toml"
    env = vault / ".env"
    manifest.write_text("manifest-before\n")
    env.write_text("env-before\n")
    script = tmp_path / "test.sh"
    script.write_text(
        FUNCTIONS
        + "\nSERVICE_USER=$(id -un)\n"
        + f"VAULT_DIR={vault!s}\nVAULT_MANIFEST={manifest!s}\nVAULT_ENV={env!s}\n"
        + "transaction=test-transaction\nmutation_open=0\nmanifest_backup=''\nenv_backup=''\n"
        + body
    )
    return subprocess.run(["bash", script], capture_output=True, text=True, check=False)


def test_failed_mutation_restores_manifest_and_env(tmp_path: Path):
    result = run_helper(
        tmp_path,
        """
mutation_backup || exit 10
printf 'manifest-after\n' > "$VAULT_MANIFEST"
printf 'env-after\n' > "$VAULT_ENV"
mutation_restore || exit 11
[[ $(cat "$VAULT_MANIFEST") == manifest-before ]] || exit 12
[[ $(cat "$VAULT_ENV") == env-before ]] || exit 13
[[ $mutation_open -eq 0 ]] || exit 14
""",
    )
    assert result.returncode == 0, result.stderr


def test_successful_mutation_removes_rollback_copies(tmp_path: Path):
    result = run_helper(
        tmp_path,
        """
mutation_backup || exit 20
manifest_backup_copy=$manifest_backup
env_backup_copy=$env_backup
mutation_commit || exit 21
[[ ! -e "$manifest_backup_copy" && ! -L "$manifest_backup_copy" ]] || exit 22
[[ ! -e "$env_backup_copy" && ! -L "$env_backup_copy" ]] || exit 23
[[ $mutation_open -eq 0 ]] || exit 24
""",
    )
    assert result.returncode == 0, result.stderr


def test_collision_stops_before_overwriting_existing_backup(tmp_path: Path):
    result = run_helper(
        tmp_path,
        """
manifest_backup="$VAULT_DIR/.secretspec.toml.rollback.$transaction"
printf 'sentinel\n' > "$manifest_backup"
mutation_backup
""",
    )
    assert result.returncode != 0
    collision = tmp_path / "vault" / ".secretspec.toml.rollback.test-transaction"
    assert collision.read_text() == "sentinel\n"


def test_terminal_audit_precedes_successful_backup_cleanup():
    finish = WRAPPER.rindex('finish "$rc"')
    cleanup = WRAPPER.rindex("mutation_commit || printf")
    assert finish < cleanup
    assert "audit_event unknown" in WRAPPER
    assert "unknown_outcome=1" in WRAPPER
