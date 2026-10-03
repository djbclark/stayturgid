#!/usr/bin/env python3
"""Patch FIRERPA v10.9's UIAutomation driver to preserve accessibility services.

FIRERPA bundles an ``Instrumentation`` subclass (obfuscated to ``Ld/r;``) that
overrides both ``getUiAutomation()`` and ``getUiAutomation(int)``.  The no-argument
override constructs a ``UiAutomation`` by reflection and then calls its hidden
``connect()`` with no arguments, which is equivalent to ``connect(0)``: Android
registers the test automation service with flags 0 and suppresses AutoJs6 and
every other accessibility service.  The ``getUiAutomation(int)`` override is the
flag-aware path that handles ``isDestroyed``/``getFlags`` and reconnects.

This patch rewrites the no-argument override's prologue so it simply delegates::

    const/4             v0, 1              # FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES
    invoke-virtual      {v5, v0}, Ld/r;->getUiAutomation(I)Landroid/app/UiAutomation;
    move-result-object  v0
    return-object       v0

That is 12 bytes replacing the override's first 12 bytes (six 16-bit code units),
landing exactly on an instruction boundary, so the method's remaining units become
unreachable and no branch target, ``try`` range or offset shifts.  The method has
``tries_size`` 0 and ``outs_size`` 3, so the two-argument invoke needs no header
change and the DEX keeps its original length.

Patching this single override is deliberate: v10.9 calls the no-argument overload
from four separate sites, and this is the one chokepoint all four pass through.  It
also agrees with upstream's own intent — FIRERPA's driver already sets
``Configurator.uiAutomationFlags = 1`` before it starts, and ``UiDevice``'s helper
honours that on API 24+; only this private override ignored it.

The patch is pinned to the known v10.9 DEX hashes and byte sequence.  It fails
closed on any upstream binary change so an upgrade cannot silently receive a
potentially invalid DEX edit.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import tarfile
import tempfile
import zipfile
import zlib
from pathlib import Path

ORIGINAL_DEX_SHA256 = "ddac4b5bfc7787b90a97b5bf7d70478d70ac8a5563334107c0bbfd8390782eb0"
PATCHED_DEX_SHA256 = "175454bce2efb19f147b14c860bd917794f0e3f9ff967d9b2a579a6179079a70"

# The first six code units of Ld/r;->getUiAutomation(), which cache-check
# ``this.b`` and return it when already connected:
#     const/4 v0, 0; iget-object v1, v5, Ld/r;->b; if-eqz v1, +3; return-object v1
ORIGINAL_PROLOGUE = bytes.fromhex("120054519505380103001101")
# Replaced by an unconditional delegation to the flag-aware overload
# (method@0cf4 = Ld/r;->getUiAutomation(I)); v5 is ``this``.
PATCHED_PROLOGUE = bytes.fromhex("12106e20f40c05000c001100")
DRIVER_ARCHIVE_SUFFIX = "/lib/python3.12/site-packages/lamda/aab.zip"


class PatchError(RuntimeError):
    """Raised when the input is not the exact supported FIRERPA driver."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _repair_dex_header(dex: bytearray) -> None:
    """Recalculate the DEX SHA-1 signature and Adler-32 checksum in place."""
    if len(dex) < 32 or not dex.startswith(b"dex\n"):
        raise PatchError("classes.dex has an invalid DEX header")
    # SHA-1 here is the DEX header signature field mandated by the file format, not a security
    # control; usedforsecurity=False (Python 3.9+) says so and yields the identical digest.
    dex[12:32] = hashlib.sha1(dex[32:], usedforsecurity=False).digest()  # nosemgrep
    checksum = zlib.adler32(dex[12:]) & 0xFFFFFFFF
    dex[8:12] = checksum.to_bytes(4, "little")


def patch_dex(
    data: bytes,
    *,
    original_sha256: str = ORIGINAL_DEX_SHA256,
    patched_sha256: str = PATCHED_DEX_SHA256,
    original_prologue: bytes = ORIGINAL_PROLOGUE,
    patched_prologue: bytes = PATCHED_PROLOGUE,
) -> tuple[bytes, bool]:
    """Return a coexistence-patched DEX and whether it changed."""
    digest = _sha256(data)
    if digest == patched_sha256:
        return data, False
    if digest != original_sha256:
        raise PatchError(f"unsupported FIRERPA classes.dex SHA-256 {digest}; expected {original_sha256}")
    if data.count(original_prologue) != 1:
        raise PatchError("expected exactly one getUiAutomation() override prologue")
    if patched_prologue in data:
        raise PatchError("patched getUiAutomation() prologue already appears unexpectedly")

    dex = bytearray(data)
    offset = dex.index(original_prologue)
    dex[offset : offset + len(original_prologue)] = patched_prologue
    _repair_dex_header(dex)
    result = bytes(dex)
    result_digest = _sha256(result)
    if result_digest != patched_sha256:
        raise PatchError(f"patched FIRERPA classes.dex SHA-256 mismatch: {result_digest}; expected {patched_sha256}")
    return result, True


def patch_driver_archive(
    data: bytes,
    *,
    original_sha256: str = ORIGINAL_DEX_SHA256,
    patched_sha256: str = PATCHED_DEX_SHA256,
    original_prologue: bytes = ORIGINAL_PROLOGUE,
    patched_prologue: bytes = PATCHED_PROLOGUE,
) -> tuple[bytes, bool]:
    """Patch ``classes.dex`` inside FIRERPA's driver archive (``aab.zip``)."""
    source = io.BytesIO(data)
    output = io.BytesIO()
    changed = False
    try:
        with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(output, "w") as zout:
            names = zin.namelist()
            if names.count("classes.dex") != 1:
                raise PatchError("aab.zip must contain exactly one classes.dex")
            for info in zin.infolist():
                member = zin.read(info.filename)
                if info.filename == "classes.dex":
                    member, changed = patch_dex(
                        member,
                        original_sha256=original_sha256,
                        patched_sha256=patched_sha256,
                        original_prologue=original_prologue,
                        patched_prologue=patched_prologue,
                    )
                zout.writestr(info, member)
    except zipfile.BadZipFile as exc:
        raise PatchError("aab.zip is not a valid ZIP archive") from exc
    return output.getvalue(), changed


def driver_archive_from_server_archive(archive: Path) -> bytes:
    """Read the single FIRERPA driver archive from a server tar archive."""
    try:
        with tarfile.open(archive, "r:gz") as tar:
            matches = [
                member for member in tar.getmembers() if member.isfile() and member.name.endswith(DRIVER_ARCHIVE_SUFFIX)
            ]
            if len(matches) != 1:
                raise PatchError("FIRERPA archive must contain exactly one lamda/aab.zip")
            extracted = tar.extractfile(matches[0])
            if extracted is None:
                raise PatchError("could not read lamda/aab.zip from archive")
            return extracted.read()
    except (tarfile.TarError, OSError) as exc:
        raise PatchError(f"could not read FIRERPA archive {archive}: {exc}") from exc


def write_atomic(path: Path, data: bytes) -> None:
    """Write output beside its destination, then atomically replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Patch FIRERPA v10.9 aab.zip for accessibility coexistence.")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    driver = driver_archive_from_server_archive(args.archive)
    patched, changed = patch_driver_archive(driver)
    write_atomic(args.output, patched)
    state = "patched" if changed else "already-patched"
    print(f"{state} FIRERPA aab.zip -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
