from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "control" / "bin"))
import verify_secretspec_sync as verifier


def _files(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    vault = tmp_path / "vault"
    source.mkdir()
    vault.mkdir()
    os.chmod(source, 0o700)
    os.chmod(vault, 0o700)
    for name in verifier.NAMES:
        (source / name).write_text(f"{name}=value\n")
        (vault / name).write_text(f"{name}=value\n")
        os.chmod(source / name, 0o600)
        os.chmod(vault / name, 0o600)
    return source, vault


def test_source_and_vault_match(tmp_path):
    source, vault = _files(tmp_path)
    assert verifier.verify(source, vault) == []


def test_mismatch_fails_closed(tmp_path):
    source, vault = _files(tmp_path)
    (source / ".env").write_text("changed=true\n")
    assert any("hash mismatch: .env" in error for error in verifier.verify(source, vault))


def test_symlink_and_permissions_fail_closed(tmp_path):
    source, vault = _files(tmp_path)
    (source / ".env").unlink()
    (source / ".env").symlink_to(vault / ".env")
    os.chmod(vault / "secretspec.toml", 0o644)
    errors = verifier.verify(source, vault)
    assert any("real 0600" in error for error in errors)
    assert any("real 0600" in error for error in errors)
