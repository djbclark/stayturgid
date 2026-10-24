#!/usr/bin/env python3
"""Patch FIRERPA's UIAutomation driver to preserve accessibility services.

FIRERPA bundles an ``Instrumentation`` subclass (obfuscated to ``Ld/r;``) that
overrides both ``getUiAutomation()`` and ``getUiAutomation(int)``.  The no-argument
override constructs a ``UiAutomation`` by reflection and then calls its hidden
``connect()`` with no arguments, which is equivalent to ``connect(0)``: Android
registers the test automation service with flags 0 and suppresses AutoJs6 and
every other accessibility service.  The ``getUiAutomation(int)`` override is the
flag-aware path that handles ``isDestroyed``/``getFlags`` and reconnects.

On v10.9, this patch rewrites the no-argument override's prologue so it simply delegates::

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

The role deploys whatever FIRERPA release is latest upstream, but this patch edits
exact bytes, so it is keyed by version in ``SUPPORTED_DRIVERS``.  A version with no
entry, or whose driver does not hash to its entry, fails closed with instructions,
before the deploy touches the device: an upgrade can never silently receive a
potentially invalid DEX edit.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import tarfile
import tempfile
import zipfile
import zlib
from pathlib import Path
from typing import NamedTuple


class DriverPatch(NamedTuple):
    """The exact bytes one FIRERPA release's driver is patched from and to."""

    original_dex_sha256: str
    patched_dex_sha256: str
    # lamda/aab.zip as upstream ships it, and as this script writes it.  The same
    # pair is pinned on-device in firerpa_lifecycle.py's SUPPORTED_DRIVERS.
    signed_archive_sha256: str
    patched_archive_sha256: str
    original_prologue: bytes
    patched_prologue: bytes


SUPPORTED_DRIVERS: dict[str, DriverPatch] = {
    "10.9": DriverPatch(
        original_dex_sha256="ddac4b5bfc7787b90a97b5bf7d70478d70ac8a5563334107c0bbfd8390782eb0",
        patched_dex_sha256="175454bce2efb19f147b14c860bd917794f0e3f9ff967d9b2a579a6179079a70",
        signed_archive_sha256="74d2f1493025acdb92905d8cf5b5fa75a3978508b440049f81a1dd0eab2c7465",
        patched_archive_sha256="3be26ac64d6532d1c8635737d4c186c976ea5c1c02e71c17b7207ab0cfbcb510",
        # The first six code units of Ld/r;->getUiAutomation(), which cache-check
        # ``this.b`` and return it when already connected:
        #     const/4 v0, 0; iget-object v1, v5, Ld/r;->b; if-eqz v1, +3; return-object v1
        original_prologue=bytes.fromhex("120054519505380103001101"),
        # Replaced by an unconditional delegation to the flag-aware overload
        # (method@0cf4 = Ld/r;->getUiAutomation(I)); v5 is ``this``.
        patched_prologue=bytes.fromhex("12106e20f40c05000c001100"),
    ),
}

# The embedded runtime's Python minor is upstream's choice (v10.0 shipped 3.9,
# v10.9 ships 3.12), so match any lib/python3.N rather than one release's.
DRIVER_ARCHIVE_PATTERN = re.compile(r"(?:^|/)lib/python3\.[0-9]+/site-packages/lamda/aab\.zip$")


class PatchError(RuntimeError):
    """Raised when the input is not the exact supported FIRERPA driver."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _add_entry_instructions(version: str, driver: bytes) -> str:
    dex_sha256 = "<unreadable>"
    try:
        with zipfile.ZipFile(io.BytesIO(driver)) as archive:
            dex_sha256 = _sha256(archive.read("classes.dex"))
    except (zipfile.BadZipFile, KeyError):
        pass
    return (
        f"To deploy FIRERPA {version}, first check that the getUiAutomation() patch still applies to "
        f"its driver: find the no-argument Ld/r;->getUiAutomation() override's prologue in classes.dex "
        f"(SHA-256 {dex_sha256}) and the method index of the flag-aware getUiAutomation(I), and "
        f"confirm the patched driver keeps accessibility services running on a device. Then add "
        f"SUPPORTED_DRIVERS[{version!r}] to {Path(__file__).name} with those prologues, "
        f"signed_archive_sha256={_sha256(driver)!r} and original_dex_sha256={dex_sha256!r}, plus the "
        f"patched hashes this script reports, and add the matching (signed, patched) aab.zip pair to "
        f"SUPPORTED_DRIVERS in firerpa_lifecycle.py."
    )


def driver_patch_for(version: str, driver: bytes) -> DriverPatch:
    """Return the vetted patch for ``version``, refusing anything not vetted."""
    spec = SUPPORTED_DRIVERS.get(version)
    if spec is None:
        raise PatchError(
            f"FIRERPA {version} has no entry in SUPPORTED_DRIVERS (vetted: {', '.join(sorted(SUPPORTED_DRIVERS))}); "
            f"refusing to patch an unvetted driver. {_add_entry_instructions(version, driver)}"
        )
    digest = _sha256(driver)
    if digest not in (spec.signed_archive_sha256, spec.patched_archive_sha256):
        raise PatchError(
            f"FIRERPA {version} aab.zip SHA-256 {digest} does not match SUPPORTED_DRIVERS[{version!r}] "
            f"(expected {spec.signed_archive_sha256}): upstream changed the driver bytes. "
            f"{_add_entry_instructions(version, driver)} Replace the existing entry rather than adding one."
        )
    return spec


def _repair_dex_header(dex: bytearray) -> None:
    """Recalculate the DEX SHA-1 signature and Adler-32 checksum in place."""
    if len(dex) < 32 or not dex.startswith(b"dex\n"):
        raise PatchError("classes.dex has an invalid DEX header")
    # SHA-1 here is the DEX header signature field mandated by the file format, not a security
    # control; usedforsecurity=False (Python 3.9+) says so and yields the identical digest.
    dex[12:32] = hashlib.sha1(dex[32:], usedforsecurity=False).digest()  # nosemgrep
    checksum = zlib.adler32(dex[12:]) & 0xFFFFFFFF
    dex[8:12] = checksum.to_bytes(4, "little")


def patch_dex(data: bytes, spec: DriverPatch) -> tuple[bytes, bool]:
    """Return a coexistence-patched DEX and whether it changed."""
    digest = _sha256(data)
    if digest == spec.patched_dex_sha256:
        return data, False
    if digest != spec.original_dex_sha256:
        raise PatchError(f"unsupported FIRERPA classes.dex SHA-256 {digest}; expected {spec.original_dex_sha256}")
    if data.count(spec.original_prologue) != 1:
        raise PatchError("expected exactly one getUiAutomation() override prologue")
    if spec.patched_prologue in data:
        raise PatchError("patched getUiAutomation() prologue already appears unexpectedly")

    dex = bytearray(data)
    offset = dex.index(spec.original_prologue)
    dex[offset : offset + len(spec.original_prologue)] = spec.patched_prologue
    _repair_dex_header(dex)
    result = bytes(dex)
    result_digest = _sha256(result)
    if result_digest != spec.patched_dex_sha256:
        raise PatchError(
            f"patched FIRERPA classes.dex SHA-256 mismatch: {result_digest}; expected {spec.patched_dex_sha256}"
        )
    return result, True


def patch_driver_archive(data: bytes, spec: DriverPatch) -> tuple[bytes, bool]:
    """Patch ``classes.dex`` inside FIRERPA's driver archive (``aab.zip``)."""
    if _sha256(data) == spec.patched_archive_sha256:
        return data, False
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
                    member, changed = patch_dex(member, spec)
                zout.writestr(info, member)
    except zipfile.BadZipFile as exc:
        raise PatchError("aab.zip is not a valid ZIP archive") from exc
    result = output.getvalue()
    # The on-device lifecycle refuses any other bytes, so catch a mismatch (for
    # example a zlib that compresses differently) here, before the device is touched.
    result_digest = _sha256(result)
    if changed and result_digest != spec.patched_archive_sha256:
        raise PatchError(
            f"patched FIRERPA aab.zip SHA-256 mismatch: {result_digest}; expected {spec.patched_archive_sha256}"
        )
    return result, changed


def driver_archive_from_server_archive(archive: Path) -> bytes:
    """Read the single FIRERPA driver archive from a server tar archive."""
    try:
        with tarfile.open(archive, "r:gz") as tar:
            matches = [
                member for member in tar.getmembers() if member.isfile() and DRIVER_ARCHIVE_PATTERN.search(member.name)
            ]
            if len(matches) != 1:
                raise PatchError("FIRERPA archive must contain exactly one lib/python3.N/site-packages/lamda/aab.zip")
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
    parser = argparse.ArgumentParser(description="Patch FIRERPA's aab.zip for accessibility coexistence.")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--version", required=True, help="FIRERPA release the archive belongs to, e.g. 10.9")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        driver = driver_archive_from_server_archive(args.archive)
        spec = driver_patch_for(args.version, driver)
        patched, changed = patch_driver_archive(driver, spec)
    except PatchError as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    write_atomic(args.output, patched)
    state = "patched" if changed else "already-patched"
    print(f"{state} FIRERPA {args.version} aab.zip -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
