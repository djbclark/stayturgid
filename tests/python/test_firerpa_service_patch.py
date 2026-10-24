"""Tests for the version-keyed, hash-guarded FIRERPA driver-archive patch."""

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


def _spec(original_dex: bytes, patched_dex: bytes, **overrides: str) -> object:
    fields = {
        "original_dex_sha256": hashlib.sha256(original_dex).hexdigest(),
        "patched_dex_sha256": hashlib.sha256(patched_dex).hexdigest(),
        "signed_archive_sha256": "unused",
        "patched_archive_sha256": "unused",
        "original_prologue": TEST_ORIGINAL,
        "patched_prologue": TEST_PATCHED,
    }
    fields.update(overrides)
    return patcher.DriverPatch(**fields)


def _patched_fake(original: bytes) -> bytes:
    expected = bytearray(original)
    expected[64 : 64 + len(TEST_ORIGINAL)] = TEST_PATCHED
    patcher._repair_dex_header(expected)
    return bytes(expected)


def _driver_zip(dex: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as driver:
        driver.writestr("classes.dex", dex)
    return buffer.getvalue()


def _rezip(driver: bytes, dex: bytes) -> bytes:
    """``driver`` with classes.dex replaced, keeping its ZipInfo as the patcher does."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(driver)) as zin, zipfile.ZipFile(buffer, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info, dex)
    return buffer.getvalue()


def _server_tarball(path: Path, member_name: str, data: bytes) -> Path:
    member = tarfile.TarInfo(member_name)
    member.size = len(data)
    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(data))
    return path


def test_patch_dex_changes_prologue_and_repairs_header():
    original = _fake_dex(TEST_ORIGINAL)
    expected = _patched_fake(original)

    result, changed = patcher.patch_dex(original, _spec(original, expected))

    assert changed is True
    assert result == expected
    assert result[12:32] == hashlib.sha1(result[32:]).digest()
    assert int.from_bytes(result[8:12], "little") == zlib.adler32(result[12:])


def test_patch_dex_is_idempotent_for_patched_hash():
    patched = _fake_dex(TEST_PATCHED)
    spec = _spec(patched, patched, original_dex_sha256="not-the-input-hash")

    result, changed = patcher.patch_dex(patched, spec)

    assert result == patched
    assert changed is False


def test_patch_dex_rejects_unknown_binary():
    unknown = _fake_dex(b"\0" * len(TEST_ORIGINAL))
    spec = _spec(_fake_dex(TEST_ORIGINAL), _fake_dex(TEST_PATCHED))

    with pytest.raises(patcher.PatchError, match="unsupported FIRERPA classes.dex"):
        patcher.patch_dex(unknown, spec)


def test_patch_dex_fails_closed_when_the_prologue_is_not_unique():
    dex = bytearray(_fake_dex(TEST_ORIGINAL))
    dex[80 : 80 + len(TEST_ORIGINAL)] = TEST_ORIGINAL
    patcher._repair_dex_header(dex)
    duplicated = bytes(dex)

    with pytest.raises(patcher.PatchError, match="exactly one getUiAutomation"):
        patcher.patch_dex(duplicated, _spec(duplicated, duplicated, patched_dex_sha256="unused"))


def test_patch_dex_fails_closed_when_the_patched_prologue_already_appears():
    dex = bytearray(_fake_dex(TEST_ORIGINAL))
    dex[80 : 80 + len(TEST_PATCHED)] = TEST_PATCHED
    patcher._repair_dex_header(dex)
    mixed = bytes(dex)

    with pytest.raises(patcher.PatchError, match="already appears"):
        patcher.patch_dex(mixed, _spec(mixed, mixed, patched_dex_sha256="unused"))


def test_patch_dex_rejects_a_mismatched_patched_hash():
    original = _fake_dex(TEST_ORIGINAL)

    with pytest.raises(patcher.PatchError, match="SHA-256 mismatch"):
        patcher.patch_dex(original, _spec(original, original, patched_dex_sha256="0" * 64))


def test_patch_driver_archive_and_tar_lookup(tmp_path):
    original = _fake_dex(TEST_ORIGINAL)
    expected = _patched_fake(original)
    archive_path = _server_tarball(
        tmp_path / "server.tar.gz", "server/lib/python3.12/site-packages/lamda/aab.zip", _driver_zip(original)
    )

    extracted = patcher.driver_archive_from_server_archive(archive_path)
    expected_archive = _rezip(extracted, expected)
    spec = _spec(original, expected, patched_archive_sha256=hashlib.sha256(expected_archive).hexdigest())
    result, changed = patcher.patch_driver_archive(extracted, spec)

    assert changed is True
    assert result == expected_archive
    with zipfile.ZipFile(io.BytesIO(result)) as driver:
        assert driver.read("classes.dex") == expected
    assert patcher.patch_driver_archive(result, spec) == (result, False), "already-patched input is a no-op"


def test_patch_driver_archive_rejects_output_the_device_would_refuse():
    """The lifecycle pins the patched aab.zip bytes; a mismatch must fail here, off-device."""
    original = _fake_dex(TEST_ORIGINAL)
    spec = _spec(original, _patched_fake(original), patched_archive_sha256="0" * 64)

    with pytest.raises(patcher.PatchError, match="aab.zip SHA-256 mismatch"):
        patcher.patch_driver_archive(_driver_zip(original), spec)


@pytest.mark.parametrize("minor", ["3.12", "3.13", "3.15"])
def test_driver_lookup_follows_the_embedded_python_minor(tmp_path, minor):
    """Upstream picks the embedded runtime's minor; no single minor is hard-coded."""
    data = _driver_zip(_fake_dex(TEST_ORIGINAL))
    archive_path = _server_tarball(
        tmp_path / "server.tar.gz", f"server/lib/python{minor}/site-packages/lamda/aab.zip", data
    )

    assert patcher.driver_archive_from_server_archive(archive_path) == data


def test_driver_archive_lookup_rejects_a_v10_0_layout(tmp_path):
    """A pre-v10.9 tarball must fail closed, not silently patch the wrong member."""
    archive_path = _server_tarball(
        tmp_path / "old.tar.gz",
        "server/lib/python3.9/site-packages/lamda/service.jar",
        _driver_zip(_fake_dex(TEST_ORIGINAL)),
    )

    with pytest.raises(patcher.PatchError, match="exactly one lib/python3.N/site-packages/lamda/aab.zip"):
        patcher.driver_archive_from_server_archive(archive_path)


# --- keyed by version: an unvetted release fails closed ----------------------


def test_an_unknown_version_is_refused_with_the_entry_to_add():
    driver = _driver_zip(_fake_dex(TEST_ORIGINAL))

    with pytest.raises(patcher.PatchError) as error:
        patcher.driver_patch_for("99.0", driver)

    message = str(error.value)
    assert "FIRERPA 99.0 has no entry in SUPPORTED_DRIVERS" in message
    assert "SUPPORTED_DRIVERS['99.0']" in message
    assert "check that the getUiAutomation() patch still applies" in message
    assert hashlib.sha256(driver).hexdigest() in message, "the error must hand over the new driver's hash"
    assert "firerpa_lifecycle.py" in message


def test_a_known_version_with_different_driver_bytes_is_refused():
    """A re-published release must not reuse a stale entry."""
    with pytest.raises(patcher.PatchError, match="does not match SUPPORTED_DRIVERS\\['10.9'\\]"):
        patcher.driver_patch_for("10.9", _driver_zip(_fake_dex(TEST_ORIGINAL)))


def test_main_fails_closed_on_an_unknown_version_without_writing_output(tmp_path, capsys):
    archive_path = _server_tarball(
        tmp_path / "server.tar.gz",
        "server/lib/python3.12/site-packages/lamda/aab.zip",
        _driver_zip(_fake_dex(TEST_ORIGINAL)),
    )
    output = tmp_path / "patched.zip"

    with pytest.raises(SystemExit) as exit_info:
        patcher.main(["--archive", str(archive_path), "--version", "99.0", "--output", str(output)])

    assert exit_info.value.code == 1
    assert "FIRERPA 99.0 has no entry" in capsys.readouterr().err
    assert not output.exists()


# --- the vetted entries ------------------------------------------------------

V10_9 = patcher.SUPPORTED_DRIVERS["10.9"]


def test_real_prologues_are_the_same_length_and_distinct():
    # A same-length replacement is what keeps every branch target, try range and
    # DEX offset valid without touching the code_item header.
    for spec in patcher.SUPPORTED_DRIVERS.values():
        assert len(spec.original_prologue) == len(spec.patched_prologue) == 12
        assert spec.original_prologue != spec.patched_prologue


def test_real_patched_prologue_delegates_to_the_flag_aware_overload():
    """Decode the hand-assembled bytes so they cannot drift from their intent.

    const/4 v0, 1; invoke-virtual {v5, v0}, method@0cf4; move-result-object v0;
    return-object v0
    """
    p = V10_9.patched_prologue

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
    o = V10_9.original_prologue

    assert o[0] == 0x12 and o[1] == 0x00  # const/4 v0, #0
    assert o[2] == 0x54  # iget-object
    assert o[3] & 0x0F == 1 and o[3] >> 4 == 5  # v1, v5
    assert o[6] == 0x38 and o[7] == 0x01  # if-eqz v1
    assert struct.unpack_from("<h", o, 8)[0] == 3  # +3 units
    assert o[10] == 0x11 and o[11] == 0x01  # return-object v1
