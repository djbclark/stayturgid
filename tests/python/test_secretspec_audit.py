"""Tests for the protected, transactional SecretSpec audit ledger."""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

import pytest
import secretspec_audit as audit


def protected(tmp_path: Path) -> Path:
    path = tmp_path / "protected"
    path.mkdir(mode=0o700)
    return path


def append(path: Path, phase: str, **kwargs):
    values = {
        "operation": "source-set",
        "phase": phase,
        "transaction": kwargs.pop("transaction", str(uuid.uuid4())),
        "actor": "djbclark",
        "client": "hermes",
        "reason": "rotate integration credential",
        "names": ["EXAMPLE_KEY"],
        "expected_uid": os.getuid(),
    }
    values.update(kwargs)
    return audit.append_event(path, **values)


def rows(path: Path) -> list[tuple]:
    db = sqlite3.connect(path / audit.DB_NAME)
    try:
        return db.execute(
            "SELECT phase,client,reason_sha256,command_basename,names_json,event_hash FROM events ORDER BY sequence"
        ).fetchall()
    finally:
        db.close()


def test_attempt_and_success_are_transactional_and_value_free(tmp_path: Path):
    path = protected(tmp_path)
    tx = str(uuid.uuid4())
    first = append(path, "attempt", transaction=tx, command_basename="curl")
    second = append(path, "success", transaction=tx, command_basename="curl", result_code=0)
    data = rows(path)
    assert [item[0] for item in data] == ["attempt", "success"]
    assert first["client"] == "hermes"
    assert second["previous_hash"] == first["event_hash"]
    raw = (path / audit.DB_NAME).read_bytes()
    assert b"rotate integration credential" not in raw
    assert b"hermes:topic" not in raw
    assert b"Authorization: Bearer" not in raw
    assert b"EXAMPLE_KEY" in raw
    assert (path / audit.DB_NAME).stat().st_mode & 0o777 == 0o600
    assert audit.verify(path, expected_uid=os.getuid()) == {"count": 2, "hash": second["event_hash"]}


def test_unknown_outcome_is_a_distinct_terminal_phase(tmp_path: Path):
    path = protected(tmp_path)
    tx = str(uuid.uuid4())
    append(path, "attempt", transaction=tx)
    append(path, "unknown", transaction=tx, result_code=125)
    with sqlite3.connect(path / audit.DB_NAME) as conn:
        assert [row[0] for row in conn.execute("SELECT phase FROM events ORDER BY sequence")] == [
            "attempt",
            "unknown",
        ]


def test_free_form_reason_and_command_arguments_never_persist(tmp_path: Path):
    path = protected(tmp_path)
    secretish = "Authorization: Bearer credential-value"
    append(path, "attempt", reason=secretish, command_basename="curl")
    raw = (path / audit.DB_NAME).read_bytes()
    assert secretish.encode() not in raw
    assert b"credential-value" not in raw
    assert b"curl" in raw


def test_interrupted_attempt_remains_visible(tmp_path: Path):
    path = protected(tmp_path)
    append(path, "attempt")
    assert [item[0] for item in rows(path)] == ["attempt"]


def test_bad_metadata_fails_before_creating_ledger(tmp_path: Path):
    path = protected(tmp_path)
    with pytest.raises(SystemExit):
        append(path, "attempt", names=["BAD-NAME"])
    assert not (path / audit.DB_NAME).exists()
    with pytest.raises(SystemExit):
        append(path, "attempt", command_basename="bad\ncommand")
    with pytest.raises(SystemExit):
        append(path, "attempt", client="invented-client")


def test_symlink_ledger_is_rejected_without_touching_target(tmp_path: Path):
    path = protected(tmp_path)
    target = tmp_path / "target"
    target.write_text("unchanged")
    (path / audit.DB_NAME).symlink_to(target)
    with pytest.raises(SystemExit):
        append(path, "attempt")
    assert target.read_text() == "unchanged"


def test_wrong_directory_or_ledger_mode_is_rejected(tmp_path: Path):
    path = protected(tmp_path)
    path.chmod(0o755)
    with pytest.raises(SystemExit):
        append(path, "attempt")
    path.chmod(0o700)
    ledger = path / audit.DB_NAME
    sqlite3.connect(ledger).close()
    ledger.chmod(0o644)
    with pytest.raises(SystemExit):
        append(path, "attempt")


def test_terminal_event_requires_result_code(tmp_path: Path):
    path = protected(tmp_path)
    with pytest.raises(SystemExit):
        append(path, "failure")
    with pytest.raises(SystemExit):
        append(path, "attempt", result_code=1)


def test_chain_verification_detects_database_tampering(tmp_path: Path):
    path = protected(tmp_path)
    append(path, "attempt")
    db = sqlite3.connect(path / audit.DB_NAME)
    db.execute("UPDATE events SET operation='source-get' WHERE sequence=1")
    db.commit()
    db.close()
    with pytest.raises(SystemExit):
        audit.verify(path, expected_uid=os.getuid())


def test_event_and_head_rollback_together_on_head_failure(tmp_path: Path):
    path = protected(tmp_path)
    append(path, "attempt")
    db = sqlite3.connect(path / audit.DB_NAME)
    db.execute("CREATE TRIGGER reject_head BEFORE UPDATE ON head BEGIN SELECT RAISE(ABORT, 'fault injection'); END")
    db.commit()
    db.close()
    with pytest.raises(SystemExit):
        append(path, "success", result_code=0)
    assert [item[0] for item in rows(path)] == ["attempt"]
    db = sqlite3.connect(path / audit.DB_NAME)
    assert db.execute("SELECT sequence FROM head").fetchone() == (1,)
    db.close()
