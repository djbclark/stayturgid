"""Tests for the hash-guarded FIRERPA v10.9 driver-archive patch."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import struct
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


# Synthetic stand-ins, the same width as the real 12-byte (six code unit) prologue
# so the fixture exercises the same same-length replacement the real patch performs.
TEST_ORIGINAL = bytes.fromhex("aa01aa02aa03aa04aa05aa06")
TEST_PATCHED = bytes.fromhex("bb01bb02bb03bb04bb05bb06")


def _fake_dex(prologue: bytes) -> bytes:
    dex = bytearray(b"dex\n035\0" + b"\0" * 120)
    dex[64 : 64 + len(prologue)] = prologue
    patcher._repair_dex_header(dex)
    return bytes(dex)


def _patch_kwargs(original: bytes, patched: bytes) -> dict[str, object]:
    return {
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "patched_sha256": hashlib.sha256(patched).hexdigest(),
        "original_prologue": TEST_ORIGINAL,
        "patched_prologue": TEST_PATCHED,
    }


def _patched_fake(original: bytes) -> bytes:
    expected = bytearray(original)
    expected[64 : 64 + len(TEST_ORIGINAL)] = TEST_PATCHED
    patcher._repair_dex_header(expected)
    return bytes(expected)


def test_patch_dex_changes_prologue_and_repairs_header():
    original = _fake_dex(TEST_ORIGINAL)
    expected = _patched_fake(original)

    result, changed = patcher.patch_dex(original, **_patch_kwargs(original, expected))

    assert changed is True
    assert result == expected
    assert result[12:32] == hashlib.sha1(result[32:]).digest()
    assert int.from_bytes(result[8:12], "little") == zlib.adler32(result[12:])


def test_patch_dex_is_idempotent_for_patched_hash():
    patched = _fake_dex(TEST_PATCHED)
    result, changed = patcher.patch_dex(
        patched,
        original_sha256="not-the-input-hash",
        patched_sha256=hashlib.sha256(patched).hexdigest(),
        original_prologue=TEST_ORIGINAL,
        patched_prologue=TEST_PATCHED,
    )

    assert result == patched
    assert changed is False


def test_patch_dex_rejects_unknown_binary():
    unknown = _fake_dex(b"\0" * len(TEST_ORIGINAL))

    with pytest.raises(patcher.PatchError, match="unsupported FIRERPA classes.dex"):
        patcher.patch_dex(unknown)


def test_patch_dex_fails_closed_when_the_prologue_is_not_unique():
    dex = bytearray(_fake_dex(TEST_ORIGINAL))
    dex[80 : 80 + len(TEST_ORIGINAL)] = TEST_ORIGINAL
    patcher._repair_dex_header(dex)
    duplicated = bytes(dex)

    with pytest.raises(patcher.PatchError, match="exactly one getUiAutomation"):
        patcher.patch_dex(
            duplicated,
            original_sha256=hashlib.sha256(duplicated).hexdigest(),
            patched_sha256="unused",
            original_prologue=TEST_ORIGINAL,
            patched_prologue=TEST_PATCHED,
        )


def test_patch_dex_fails_closed_when_the_patched_prologue_already_appears():
    dex = bytearray(_fake_dex(TEST_ORIGINAL))
    dex[80 : 80 + len(TEST_PATCHED)] = TEST_PATCHED
    patcher._repair_dex_header(dex)
    mixed = bytes(dex)

    with pytest.raises(patcher.PatchError, match="already appears"):
        patcher.patch_dex(
            mixed,
            original_sha256=hashlib.sha256(mixed).hexdigest(),
            patched_sha256="unused",
            original_prologue=TEST_ORIGINAL,
            patched_prologue=TEST_PATCHED,
        )


def test_patch_dex_rejects_a_mismatched_patched_hash():
    original = _fake_dex(TEST_ORIGINAL)

    with pytest.raises(patcher.PatchError, match="SHA-256 mismatch"):
        patcher.patch_dex(
            original,
            original_sha256=hashlib.sha256(original).hexdigest(),
            patched_sha256="0" * 64,
            original_prologue=TEST_ORIGINAL,
            patched_prologue=TEST_PATCHED,
        )


def test_patch_driver_archive_and_tar_lookup(tmp_path):
    original = _fake_dex(TEST_ORIGINAL)
    expected = _patched_fake(original)
    kwargs = _patch_kwargs(original, expected)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as driver:
        driver.writestr("classes.dex", original)

    archive_path = tmp_path / "server.tar.gz"
    zip_data = zip_buffer.getvalue()
    member = tarfile.TarInfo("server/lib/python3.12/site-packages/lamda/aab.zip")
    member.size = len(zip_data)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(zip_data))

    extracted = patcher.driver_archive_from_server_archive(archive_path)
    result, changed = patcher.patch_driver_archive(extracted, **kwargs)

    assert changed is True
    with zipfile.ZipFile(io.BytesIO(result)) as driver:
        assert driver.read("classes.dex") == expected


def test_driver_archive_lookup_rejects_a_v10_0_layout(tmp_path):
    """A pre-v10.9 tarball must fail closed, not silently patch the wrong member."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as driver:
        driver.writestr("classes.dex", _fake_dex(TEST_ORIGINAL))
    zip_data = zip_buffer.getvalue()

    archive_path = tmp_path / "old.tar.gz"
    member = tarfile.TarInfo("server/lib/python3.9/site-packages/lamda/service.jar")
    member.size = len(zip_data)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(zip_data))

    with pytest.raises(patcher.PatchError, match="exactly one lamda/aab.zip"):
        patcher.driver_archive_from_server_archive(archive_path)


# --- the real, shipped pins -------------------------------------------------


def test_pinned_driver_path_describes_the_v10_9_layout():
    assert patcher.DRIVER_ARCHIVE_SUFFIX == "/lib/python3.12/site-packages/lamda/aab.zip"


def test_real_prologues_are_the_same_length_and_distinct():
    # A same-length replacement is what keeps every branch target, try range and
    # DEX offset valid without touching the code_item header.
    assert len(patcher.ORIGINAL_PROLOGUE) == len(patcher.PATCHED_PROLOGUE) == 12
    assert patcher.ORIGINAL_PROLOGUE != patcher.PATCHED_PROLOGUE


def test_real_patched_prologue_delegates_to_the_flag_aware_overload():
    """Decode the hand-assembled bytes so they cannot drift from their intent.

    const/4 v0, 1; invoke-virtual {v5, v0}, method@0cf4; move-result-object v0;
    return-object v0
    """
    p = patcher.PATCHED_PROLOGUE

    # const/4 v0, #1  -> op 0x12, low nibble = register 0, high nibble = literal 1
    assert p[0] == 0x12
    assert p[1] & 0x0F == 0  # v0
    assert p[1] >> 4 == 1  # FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES

    # invoke-virtual {v5, v0}, method@0cf4  (format 35c)
    assert p[2] == 0x6E
    assert p[3] >> 4 == 2  # two argument registers
    assert struct.unpack_from("<H", p, 4)[0] == 0x0CF4  # Ld/r;->getUiAutomation(I)
    assert p[6] & 0x0F == 5  # first register is v5 == this
    assert p[6] >> 4 == 0  # second register is v0, the flag

    assert p[8] == 0x0C and p[9] == 0x00  # move-result-object v0
    assert p[10] == 0x11 and p[11] == 0x00  # return-object v0


def test_real_original_prologue_is_the_cache_check_it_replaces():
    """const/4 v0, 0; iget-object v1, v5, b; if-eqz v1, +3; return-object v1."""
    o = patcher.ORIGINAL_PROLOGUE

    assert o[0] == 0x12 and o[1] == 0x00  # const/4 v0, #0
    assert o[2] == 0x54  # iget-object
    assert o[3] & 0x0F == 1 and o[3] >> 4 == 5  # v1, v5
    assert o[6] == 0x38 and o[7] == 0x01  # if-eqz v1
    assert struct.unpack_from("<h", o, 8)[0] == 3  # +3 units
    assert o[10] == 0x11 and o[11] == 0x01  # return-object v1


def test_real_dex_hashes_are_pinned_and_distinct():
    for digest in (patcher.ORIGINAL_DEX_SHA256, patcher.PATCHED_DEX_SHA256):
        assert len(digest) == 64
        assert all(character in "0123456789abcdef" for character in digest)
    assert patcher.ORIGINAL_DEX_SHA256 != patcher.PATCHED_DEX_SHA256
