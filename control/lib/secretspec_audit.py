#!/usr/bin/env python3
"""Transactional, value-free SecretSpec broker audit ledger.

SQLite provides one atomic transaction for the chained event and current head,
so a crash cannot leave a separately updated checkpoint out of sync. The ledger
stores no reason text, session identifier, command arguments, or secret values.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
import time
import uuid
from pathlib import Path
from typing import Optional, Sequence

DB_NAME = "broker-audit.sqlite3"
ZERO_HASH = "0" * 64
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
OP_RE = re.compile(r"^[a-z][a-z0-9-]*$")
CLIENT_RE = re.compile(r"^(?:hermes|claude|codex|opencode|cursor|agy|fixed-consumer|unknown)$")
COMMAND_RE = re.compile(r"^[A-Za-z0-9_.+-]{1,128}$")
PHASES = {"attempt", "success", "failure", "unknown"}


def fail(message: str) -> None:
    raise SystemExit(f"audit denied: {message}")


def _validate_text(label: str, value: str, limit: int) -> str:
    if not value or len(value) > limit or any(c in value for c in "\r\n\0"):
        fail(f"invalid {label}")
    return value


def _open_dir(path: Path, expected_uid: Optional[int]) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot open protected directory: {exc.strerror}")
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o700:
        os.close(fd)
        fail("protected directory must be mode 0700")
    if expected_uid is not None and st.st_uid != expected_uid:
        os.close(fd)
        fail("protected directory owner mismatch")
    return fd


def _connect(directory: Path, expected_uid: Optional[int]) -> tuple[int, sqlite3.Connection]:
    dir_fd = _open_dir(directory, expected_uid)
    existing: Optional[os.stat_result] = None
    try:
        existing = os.stat(DB_NAME, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        os.close(dir_fd)
        fail(f"cannot inspect protected ledger: {exc.strerror}")
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        os.close(dir_fd)
        fail("ledger path must be a regular file")
    if existing is not None and stat.S_IMODE(existing.st_mode) != 0o600:
        os.close(dir_fd)
        fail("ledger must be mode 0600")
    connection: Optional[sqlite3.Connection] = None
    previous_umask = os.umask(0o077)
    try:
        # SQLite cannot lock a database through macOS /dev/fd. Reopen the fixed
        # basename only after validating the non-symlink protected directory and
        # any existing inode. The directory is mode 0700 under a protected /var
        # parent chain, so untrusted operator processes cannot race this reopen.
        connection = sqlite3.connect(str(directory / DB_NAME), timeout=10, isolation_level=None)
    except sqlite3.Error as exc:
        os.close(dir_fd)
        fail(f"cannot open protected ledger: {exc}")
    finally:
        os.umask(previous_umask)
    assert connection is not None
    if existing is None:
        os.chmod(DB_NAME, 0o600, dir_fd=dir_fd, follow_symlinks=False)
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
          sequence INTEGER PRIMARY KEY AUTOINCREMENT,
          timestamp_ns INTEGER NOT NULL,
          transaction_id TEXT NOT NULL,
          phase TEXT NOT NULL CHECK (phase IN ('attempt','success','failure','unknown')),
          operation TEXT NOT NULL,
          actor TEXT NOT NULL,
          client TEXT NOT NULL,
          reason_sha256 TEXT NOT NULL,
          command_basename TEXT,
          names_json TEXT NOT NULL,
          result_code INTEGER,
          previous_hash TEXT NOT NULL,
          event_hash TEXT NOT NULL UNIQUE
        ) STRICT
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS head (
          singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
          sequence INTEGER NOT NULL,
          event_hash TEXT NOT NULL
        ) STRICT
        """
    )
    st: Optional[os.stat_result] = None
    try:
        st = os.stat(DB_NAME, dir_fd=dir_fd, follow_symlinks=False)
    except OSError as exc:
        connection.close()
        os.close(dir_fd)
        fail(f"cannot stat protected ledger: {exc.strerror}")
    assert st is not None
    if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600:
        connection.close()
        os.close(dir_fd)
        fail("ledger must be a regular file with mode 0600")
    if expected_uid is not None and st.st_uid != expected_uid:
        connection.close()
        os.close(dir_fd)
        fail("ledger owner mismatch")
    return dir_fd, connection


def _canonical(fields: dict) -> bytes:
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()


def _verify_rows(connection: sqlite3.Connection) -> tuple[str, int]:
    previous = ZERO_HASH
    count = 0
    for row in connection.execute(
        "SELECT sequence,timestamp_ns,transaction_id,phase,operation,actor,client,reason_sha256,"
        "command_basename,names_json,result_code,previous_hash,event_hash FROM events ORDER BY sequence"
    ):
        (
            sequence,
            timestamp_ns,
            transaction_id,
            phase,
            operation,
            actor,
            client,
            reason_sha256,
            command_basename,
            names_json,
            result_code,
            stored_previous,
            event_hash,
        ) = row
        fields = {
            "sequence": sequence,
            "timestamp_ns": timestamp_ns,
            "transaction": transaction_id,
            "phase": phase,
            "operation": operation,
            "actor": actor,
            "client": client,
            "reason_sha256": reason_sha256,
            "command_basename": command_basename,
            "names": json.loads(names_json),
            "result_code": result_code,
            "previous_hash": stored_previous,
        }
        expected = hashlib.sha256(previous.encode() + b"\n" + _canonical(fields)).hexdigest()
        if stored_previous != previous or not hmac.compare_digest(event_hash, expected):
            fail("ledger chain is invalid")
        previous = event_hash
        count = sequence
    head = connection.execute("SELECT sequence,event_hash FROM head WHERE singleton=1").fetchone()
    expected_head = None if count == 0 else (count, previous)
    if head != expected_head:
        fail("ledger head is invalid")
    return previous, count


def verify(directory: Path, expected_uid: Optional[int] = None) -> dict:
    dir_fd, connection = _connect(directory, expected_uid)
    try:
        connection.execute("BEGIN IMMEDIATE")
        digest, count = _verify_rows(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            fail("ledger integrity check failed")
        connection.execute("COMMIT")
        return {"count": count, "hash": digest}
    except sqlite3.Error as exc:
        connection.execute("ROLLBACK")
        fail(f"ledger verification failed: {exc}")
    finally:
        connection.close()
        os.close(dir_fd)
    return {}


def append_event(
    directory: Path,
    *,
    operation: str,
    phase: str,
    transaction: str,
    actor: str,
    client: str,
    reason: str = "",
    reason_sha256: str = "",
    command_basename: str = "",
    names: Sequence[str] = (),
    result_code: Optional[int] = None,
    expected_uid: Optional[int] = None,
) -> dict:
    if not OP_RE.fullmatch(operation) or phase not in PHASES:
        fail("invalid operation or phase")
    try:
        uuid.UUID(transaction)
    except ValueError:
        fail("invalid transaction")
    actor = _validate_text("actor", actor, 128)
    if not CLIENT_RE.fullmatch(client):
        fail("invalid client")
    if reason:
        _validate_text("reason", reason, 512)
        reason_sha256 = hashlib.sha256(reason.encode()).hexdigest()
    elif not re.fullmatch(r"[0-9a-f]{64}", reason_sha256):
        fail("invalid reason hash")
    if command_basename and not COMMAND_RE.fullmatch(command_basename):
        fail("invalid command basename")
    clean_names = sorted(set(names))
    if any(not NAME_RE.fullmatch(name) for name in clean_names):
        fail("invalid secret name")
    if phase == "attempt" and result_code is not None:
        fail("attempt cannot have a result code")
    if phase != "attempt" and (result_code is None or not 0 <= result_code <= 255):
        fail("terminal event requires a result code")

    dir_fd, connection = _connect(directory, expected_uid)
    try:
        connection.execute("BEGIN IMMEDIATE")
        previous, count = _verify_rows(connection)
        sequence = count + 1
        fields = {
            "sequence": sequence,
            "timestamp_ns": time.time_ns(),
            "transaction": transaction,
            "phase": phase,
            "operation": operation,
            "actor": actor,
            "client": client,
            "reason_sha256": reason_sha256,
            "command_basename": command_basename or None,
            "names": clean_names,
            "result_code": result_code,
            "previous_hash": previous,
        }
        event_hash = hashlib.sha256(previous.encode() + b"\n" + _canonical(fields)).hexdigest()
        connection.execute(
            "INSERT INTO events(sequence,timestamp_ns,transaction_id,phase,operation,actor,client,"
            "reason_sha256,command_basename,names_json,result_code,previous_hash,event_hash) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sequence,
                fields["timestamp_ns"],
                transaction,
                phase,
                operation,
                actor,
                client,
                reason_sha256,
                fields["command_basename"],
                json.dumps(clean_names, separators=(",", ":")),
                result_code,
                previous,
                event_hash,
            ),
        )
        connection.execute(
            "INSERT INTO head(singleton,sequence,event_hash) VALUES(1,?,?) "
            "ON CONFLICT(singleton) DO UPDATE SET sequence=excluded.sequence,event_hash=excluded.event_hash",
            (sequence, event_hash),
        )
        connection.execute("COMMIT")
        return {**fields, "event_hash": event_hash}
    except sqlite3.Error as exc:
        connection.execute("ROLLBACK")
        fail(f"cannot append audit event: {exc}")
    finally:
        connection.close()
        os.close(dir_fd)
    return {}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=[*sorted(PHASES), "verify"])
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--operation")
    p.add_argument("--transaction")
    p.add_argument("--actor")
    p.add_argument("--client")
    p.add_argument("--reason")
    p.add_argument("--reason-sha256")
    p.add_argument("--command-basename", default="")
    p.add_argument("--name", action="append", default=[])
    p.add_argument("--result-code", type=int)
    p.add_argument("--expected-uid", type=int)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.phase == "verify":
        print(json.dumps(verify(args.directory, args.expected_uid), sort_keys=True))
        return 0
    for label in ("operation", "transaction", "actor", "client"):
        if getattr(args, label) is None:
            fail(f"{label} is required")
    if not args.reason and not args.reason_sha256:
        fail("reason or reason-sha256 is required")
    event = append_event(
        args.directory,
        operation=args.operation,
        phase=args.phase,
        transaction=args.transaction,
        actor=args.actor,
        client=args.client,
        reason=args.reason or "",
        reason_sha256=args.reason_sha256 or "",
        command_basename=args.command_basename,
        names=args.name,
        result_code=args.result_code,
        expected_uid=args.expected_uid,
    )
    print(event["event_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
