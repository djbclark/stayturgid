#!/usr/bin/env python3
"""Patch FIRERPA v10's UIAutomation driver to preserve accessibility services.

FIRERPA's bundled driver initializes ``UiAutomation`` with the no-argument
``Instrumentation.getUiAutomation()`` overload.  Android therefore registers
the test automation service with flags 0 and suppresses AutoJs6 and every other
accessibility service.  The driver already prepares flag 1 in the adjacent
register; this patch changes the single invoke instruction to call
``getUiAutomation(1)`` instead.

The patch is deliberately pinned to the known v10 DEX hashes and byte pattern.
It fails closed on any upstream binary change so an upgrade cannot silently
receive a potentially invalid DEX edit.
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

ORIGINAL_DEX_SHA256 = (
    "69b52ebca5a0751b78f22c2f5a964b673e433be2e76e5b37f491813e472ec7c8"
)
PATCHED_DEX_SHA256 = (
    "7801c9e77f675f25c2fbc2fe2d254ed3750f00f82fa7d925d0904690b0ca70c5"
)

# Dalvik invoke-virtual, changed from {v0}, method@056a to
# {v0, v1}, method@056b.  v1 is flag 1 on the supported Android versions.
ORIGINAL_INSTRUCTION = bytes.fromhex("6e106a050000")
PATCHED_INSTRUCTION = bytes.fromhex("6e206b051000")
SERVICE_JAR_SUFFIX = "/lib/python3.9/site-packages/lamda/service.jar"


class PatchError(RuntimeError):
    """Raised when the input is not the exact supported FIRERPA driver."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _repair_dex_header(dex: bytearray) -> None:
    """Recalculate the DEX SHA-1 signature and Adler-32 checksum in place."""
    if len(dex) < 32 or not dex.startswith(b"dex\n"):
        raise PatchError("classes.dex has an invalid DEX header")
    dex[12:32] = hashlib.sha1(dex[32:]).digest()
    checksum = zlib.adler32(dex[12:]) & 0xFFFFFFFF
    dex[8:12] = checksum.to_bytes(4, "little")


def patch_dex(
    data: bytes,
    *,
    original_sha256: str = ORIGINAL_DEX_SHA256,
    patched_sha256: str = PATCHED_DEX_SHA256,
    original_instruction: bytes = ORIGINAL_INSTRUCTION,
    patched_instruction: bytes = PATCHED_INSTRUCTION,
) -> tuple[bytes, bool]:
    """Return a coexistence-patched DEX and whether it changed."""
    digest = _sha256(data)
    if digest == patched_sha256:
        return data, False
    if digest != original_sha256:
        raise PatchError(
            "unsupported FIRERPA classes.dex SHA-256 "
            f"{digest}; expected {original_sha256}"
        )
    if data.count(original_instruction) != 1:
        raise PatchError("expected exactly one UIAutomation invoke instruction")
    if patched_instruction in data:
        raise PatchError("patched UIAutomation instruction already appears unexpectedly")

    dex = bytearray(data)
    offset = dex.index(original_instruction)
    dex[offset : offset + len(original_instruction)] = patched_instruction
    _repair_dex_header(dex)
    result = bytes(dex)
    result_digest = _sha256(result)
    if result_digest != patched_sha256:
        raise PatchError(
            "patched FIRERPA classes.dex SHA-256 mismatch: "
            f"{result_digest}; expected {patched_sha256}"
        )
    return result, True


def patch_service_jar(data: bytes, **patch_kwargs: object) -> tuple[bytes, bool]:
    """Patch ``classes.dex`` inside a FIRERPA service JAR."""
    source = io.BytesIO(data)
    output = io.BytesIO()
    changed = False
    try:
        with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(output, "w") as zout:
            names = zin.namelist()
            if names.count("classes.dex") != 1:
                raise PatchError("service.jar must contain exactly one classes.dex")
            for info in zin.infolist():
                member = zin.read(info.filename)
                if info.filename == "classes.dex":
                    member, changed = patch_dex(member, **patch_kwargs)
                zout.writestr(info, member)
    except zipfile.BadZipFile as exc:
        raise PatchError("service.jar is not a valid ZIP archive") from exc
    return output.getvalue(), changed


def service_jar_from_archive(archive: Path) -> bytes:
    """Read the single FIRERPA service JAR from a server tar archive."""
    try:
        with tarfile.open(archive, "r:gz") as tar:
            matches = [
                member
                for member in tar.getmembers()
                if member.isfile() and member.name.endswith(SERVICE_JAR_SUFFIX)
            ]
            if len(matches) != 1:
                raise PatchError(
                    "FIRERPA archive must contain exactly one lamda/service.jar"
                )
            extracted = tar.extractfile(matches[0])
            if extracted is None:
                raise PatchError("could not read lamda/service.jar from archive")
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
    parser = argparse.ArgumentParser(
        description="Patch FIRERPA v10 service.jar for accessibility coexistence."
    )
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    jar = service_jar_from_archive(args.archive)
    patched, changed = patch_service_jar(jar)
    write_atomic(args.output, patched)
    state = "patched" if changed else "already-patched"
    print(f"{state} FIRERPA service.jar -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
