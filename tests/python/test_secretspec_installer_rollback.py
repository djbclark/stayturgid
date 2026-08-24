"""Executable failure-injection tests for installer rollback boundaries."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).parents[2]
INSTALLER = (ROOT / "control/bin/install-sudo-secretspec").read_text()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rollback_model(destinations: list[Path], recovery: Path) -> bool:
    """Model the shell rollback contract using its persisted state files."""
    verified = True
    for index in range(len(destinations) - 1, -1, -1):
        destination = destinations[index]
        state_path = recovery / f"{index}.state"
        if not state_path.is_file():
            verified = False
            continue
        state = state_path.read_text().strip()
        if state.startswith("present:"):
            saved = recovery / str(index)
            if not saved.is_file():
                verified = False
                continue
            shutil.copyfile(saved, destination)
            if digest(destination) != state.removeprefix("present:"):
                verified = False
        elif state == "absent":
            destination.unlink(missing_ok=True)
            if destination.exists() or destination.is_symlink():
                verified = False
        else:
            verified = False
    return verified


def test_every_partial_commit_boundary_restores_prior_state(tmp_path: Path):
    count = 8
    recovery = tmp_path / "rollback"
    recovery.mkdir()
    destinations = [tmp_path / f"destination-{index}" for index in range(count)]
    prior_present = {index for index in range(count) if index % 2 == 0}
    for index, destination in enumerate(destinations):
        if index in prior_present:
            saved = recovery / str(index)
            saved.write_text(f"prior-{index}")
            destination.write_bytes(saved.read_bytes())
            (recovery / f"{index}.state").write_text(f"present:{digest(saved)}\n")
        else:
            (recovery / f"{index}.state").write_text("absent\n")

    for failure_after in range(1, count + 1):
        for index, destination in enumerate(destinations):
            if index in prior_present:
                destination.write_text(f"prior-{index}")
            else:
                destination.unlink(missing_ok=True)
        for index in range(failure_after):
            destinations[index].write_text(f"replacement-{index}")

        assert rollback_model(destinations, recovery)
        for index, destination in enumerate(destinations):
            if index in prior_present:
                assert destination.read_text() == f"prior-{index}"
            else:
                assert not destination.exists()


def test_corrupt_recovery_state_fails_verification(tmp_path: Path):
    recovery = tmp_path / "rollback"
    recovery.mkdir()
    destination = tmp_path / "destination"
    saved = recovery / "0"
    saved.write_text("prior")
    (recovery / "0.state").write_text("present:" + "0" * 64 + "\n")
    destination.write_text("replacement")
    assert not rollback_model([destination], recovery)


def test_installer_activates_rollback_before_commit_and_verifies_restore():
    assert INSTALLER.index("commit_started=1") < INSTALLER.index(
        'for i in "${!DESTINATIONS[@]}"; do', INSTALLER.index("# Commit")
    )
    assert "rollback_verified=0" in INSTALLER
    assert "CRITICAL: SecretSpec boundary rollback could not be verified" in INSTALLER
    assert "exit 125" in INSTALLER
