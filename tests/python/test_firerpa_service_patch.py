"""Tests for the hash-guarded FIRERPA service JAR patch."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import tarfile
import zipfile
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PATCHER_PATH = REPO / "ansible_collections/stayturgid/firerpa/roles/firerpa/files" / "firerpa_service_patch.py"
SPEC = importlib.util.spec_from_file_location("firerpa_service_patch", PATCHER_PATH)
assert SPEC and SPEC.loader
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)


TEST_ORIGINAL = bytes.fromhex("6e1011110000")
TEST_PATCHED = bytes.fromhex("6e2022221000")


def _fake_dex(instruction: bytes) -> bytes:
    dex = bytearray(b"dex\n035\0" + b"\0" * 120)
    dex[64 : 64 + len(instruction)] = instruction
    patcher._repair_dex_header(dex)
    return bytes(dex)


def _patch_kwargs(original: bytes, patched: bytes) -> dict[str, object]:
    return {
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "patched_sha256": hashlib.sha256(patched).hexdigest(),
        "original_instruction": TEST_ORIGINAL,
        "patched_instruction": TEST_PATCHED,
    }


def test_patch_dex_changes_instruction_and_repairs_header():
    original = _fake_dex(TEST_ORIGINAL)
    expected = bytearray(original)
    expected[64 : 64 + len(TEST_ORIGINAL)] = TEST_PATCHED
    patcher._repair_dex_header(expected)

    result, changed = patcher.patch_dex(original, **_patch_kwargs(original, bytes(expected)))

    assert changed is True
    assert result == bytes(expected)
    assert result[12:32] == hashlib.sha1(result[32:]).digest()
    assert int.from_bytes(result[8:12], "little") == zlib.adler32(result[12:])


def test_patch_dex_is_idempotent_for_patched_hash():
    patched = _fake_dex(TEST_PATCHED)
    result, changed = patcher.patch_dex(
        patched,
        original_sha256="not-the-input-hash",
        patched_sha256=hashlib.sha256(patched).hexdigest(),
        original_instruction=TEST_ORIGINAL,
        patched_instruction=TEST_PATCHED,
    )

    assert result == patched
    assert changed is False


def test_patch_dex_rejects_unknown_binary():
    unknown = _fake_dex(b"\0" * len(TEST_ORIGINAL))

    with pytest.raises(patcher.PatchError, match="unsupported FIRERPA classes.dex"):
        patcher.patch_dex(unknown)


def test_patch_service_jar_and_archive_lookup(tmp_path):
    original = _fake_dex(TEST_ORIGINAL)
    expected = bytearray(original)
    expected[64 : 64 + len(TEST_ORIGINAL)] = TEST_PATCHED
    patcher._repair_dex_header(expected)
    kwargs = _patch_kwargs(original, bytes(expected))

    jar_buffer = io.BytesIO()
    with zipfile.ZipFile(jar_buffer, "w") as jar:
        jar.writestr("classes.dex", original)

    archive_path = tmp_path / "server.tar.gz"
    jar_data = jar_buffer.getvalue()
    member = tarfile.TarInfo("server/lib/python3.9/site-packages/lamda/service.jar")
    member.size = len(jar_data)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(jar_data))

    extracted = patcher.service_jar_from_archive(archive_path)
    result, changed = patcher.patch_service_jar(extracted, **kwargs)

    assert changed is True
    with zipfile.ZipFile(io.BytesIO(result)) as jar:
        assert jar.read("classes.dex") == bytes(expected)
