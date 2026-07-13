# @heals: HD8-DOZE-WHITELIST HD8-GSF-PINNED HD8-GMS-PINNED
"""Fire HD 8 sideloaded Google Play stack — version pin + Doze whitelist.

Play Services auto-updates (via Play Store) to builds that require
``/system/etc/sysconfig/google.xml`` and ``CHANGE_DEVICE_IDLE_TEMP_WHITELIST``,
which Fire OS lacks. Symptom: repeated ``Google Services Framework has stopped``
dialogs (root crash is ``com.google.android.gms.persistent``).

Pinned APKs ship in the Fire-Tools release (APKMirror bundles). See
``docs/research/fire-os-google-play.md``.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

FIRE_TOOLS_ZIP_URL = (
    "https://github.com/mrhaydendp/Fire-Tools/releases/latest/download/Fire-Tools.zip"
)
FIRE_TOOLS_CACHE = Path.home() / ".cache" / "stayturgid" / "fire-tools"
GMS_APKM = "Fire-Tools/Gapps/Google Play Services 24.35.30.apkm"
PLAY_APKM = "Fire-Tools/Gapps/Google Play Store 42.6.23-23.apkm"
GSF_APK = "Fire-Tools/Gapps/Google Services Framework 10-6494331.apk"
PINNED_GSF_VERSION_PREFIX = "10-"
# Fire-Tools pin (legacy / emergency only via --force or STAYTURGID_HD8_PIN_GMS=1).
# 2026-07-10: operator prefers newer GMS/Play over the 24.35.30 pin — auto-heal
# no longer force-downgrades GMS/Play. Keep GSF 10-x + Doze whitelist.
MAX_GMS_VERSION_CODE = 250_000_000
PINNED_GMS_VERSION_CODE = 243_530_013
PINNED_PLAY_VERSION_CODE = 84_262_300
MAX_PLAY_VERSION_CODE = 85_000_000
GMS_PKG = "com.google.android.gms"
GSF_PKG = "com.google.android.gsf"
PLAY_PKG = "com.android.vending"
WHITELIST_PKGS = (GMS_PKG, GSF_PKG)


def pin_gms_enabled() -> bool:
    """True when fleet heal / repair_if_needed may reinstall Fire-Tools GMS+Play.

    Default **off** (2026-07-10): newer Play Store + device-matched GMS worked
    better for the operator than the 24.35.30 pin. Opt-in with
    ``STAYTURGID_HD8_PIN_GMS=1`` or ``fix_hd8_google_stack.py --force``.
    """
    return os.environ.get("STAYTURGID_HD8_PIN_GMS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

_VERSION_CODE_RE = re.compile(r"versionCode=(\d+)")


def parse_version_code(dumpsys_package: str) -> int | None:
    for line in dumpsys_package.splitlines():
        line = line.strip()
        if line.startswith("versionCode="):
            m = _VERSION_CODE_RE.match(line)
            if m:
                return int(m.group(1))
    return None


def _adb() -> str:
    try:
        from stayturgid_device import adb_bin  # type: ignore

        return adb_bin()
    except Exception:  # noqa: BLE001
        return os.environ.get("STAYTURGID_ADB", "adb")


def adb_shell(run_command, device: str, *args: str) -> tuple[int, str, str]:
    cmd = [_adb(), "-s", device, "shell", *args]
    rc, out, err = run_command(cmd)
    return rc, out, err


def package_version_code(run_command, device: str, package: str) -> int | None:
    rc, out, _err = adb_shell(run_command, device, "dumpsys", "package", package)
    if rc != 0:
        return None
    return parse_version_code(out)


def deviceidle_whitelist_add(run_command, device: str, package: str) -> bool:
    rc, out, err = adb_shell(
        run_command, device, "cmd", "deviceidle", "whitelist", "+%s" % package
    )
    text = (out + err).lower()
    return rc == 0 or "added" in text or "already" in text


def ensure_doze_whitelist(run_command, device: str) -> list[str]:
    applied: list[str] = []
    for pkg in WHITELIST_PKGS:
        if deviceidle_whitelist_add(run_command, device, pkg):
            applied.append(pkg)
    return applied


def needs_gms_downgrade(gms_version_code: int | None) -> bool:
    """True when GMS is newer than Fire-Tools pin *and* pin policy is enabled."""
    if not pin_gms_enabled():
        return False
    if gms_version_code is None:
        return False
    return gms_version_code > MAX_GMS_VERSION_CODE


def needs_play_downgrade(play_version_code: int | None) -> bool:
    if not pin_gms_enabled():
        return False
    if play_version_code is None:
        return False
    return play_version_code > MAX_PLAY_VERSION_CODE


def _ensure_fire_tools_zip(zip_path: Path) -> None:
    """Download Fire-Tools.zip once; flock + unique temp avoid concurrent races (L4)."""
    import fcntl
    import os
    import uuid

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.is_file() and zip_path.stat().st_size > 1_000_000:
        return
    lock_path = zip_path.with_suffix(".lock")
    lock_fd = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        # Re-check under lock — another process may have finished the download.
        if zip_path.is_file() and zip_path.stat().st_size > 1_000_000:
            return
        tmp = zip_path.with_name(
            "%s.%s.part" % (zip_path.name, uuid.uuid4().hex[:10])
        )
        try:
            subprocess.run(
                ["curl", "-fsSL", "-o", str(tmp), FIRE_TOOLS_ZIP_URL],
                check=True,
                timeout=300,
            )
            os.replace(tmp, zip_path)
        finally:
            if tmp.is_file():
                tmp.unlink(missing_ok=True)
    finally:
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        lock_fd.close()


def _extract_apkm_splits(apkm_zip: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apkm_zip) as zf:
        names = [n for n in zf.namelist() if n.endswith(".apk")]
        for name in names:
            target = dest / Path(name).name
            if not target.is_file():
                zf.extract(name, dest)
                extracted = dest / name
                if extracted != target and extracted.is_file():
                    extracted.replace(target)
    return sorted(dest.glob("*.apk"))


def _apkm_from_fire_tools(zip_path: Path, member: str, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / Path(member).name
    if not out.is_file():
        with zipfile.ZipFile(zip_path) as zf:
            zf.extract(member, work_dir)
            extracted = work_dir / member
            if extracted != out:
                extracted.replace(out)
    return out


def package_version_name(run_command, device: str, package: str) -> str | None:
    rc, out, _err = adb_shell(run_command, device, "dumpsys", "package", package)
    if rc != 0:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("versionName="):
            return line.split("=", 1)[1].split()[0]
    return None


def needs_gsf_reinstall(gsf_version_name: str | None) -> bool:
    if not gsf_version_name:
        return True
    return not gsf_version_name.startswith(PINNED_GSF_VERSION_PREFIX)


def _install_apk(run_command, device: str, apk: Path) -> tuple[int, str]:
    cmd = [_adb(), "-s", device, "install", "-r", "-g", "--user", "0", str(apk)]
    rc, out, err = run_command(cmd)
    return rc, (out + err).strip()


def reinstall_gsf(run_command, device: str, zip_path: Path, work_dir: Path) -> dict:
    gsf_apk = _apkm_from_fire_tools(zip_path, GSF_APK, work_dir / "apkm")
    _uninstall_user_package(run_command, device, GSF_PKG)
    rc, msg = _install_apk(run_command, device, gsf_apk)
    return {
        "rc": rc,
        "message": msg,
        "version": package_version_name(run_command, device, GSF_PKG),
    }


def stop_aurora_churn(run_command, device: str) -> None:
    """Aurora Store (parked) triggers GMS BadAuthentication on uncertified Fire."""
    adb_shell(run_command, device, "am", "force-stop", "com.aurora.store")


def _install_splits(run_command, device: str, apks: list[Path]) -> tuple[int, str]:
    if not apks:
        return 1, "no APK splits"
    cmd = [_adb(), "-s", device, "install-multiple", "-r", "-g", "--user", "0", *[str(p) for p in apks]]
    rc, out, err = run_command(cmd)
    return rc, (out + err).strip()


def _uninstall_user_package(run_command, device: str, package: str) -> None:
    adb_shell(run_command, device, "pm", "uninstall", "--user", "0", package)


def reinstall_pinned_stack(
    run_command,
    device: str,
    *,
    cache_dir: Path | None = None,
    work_dir: Path | None = None,
) -> dict:
    """Download Fire-Tools GApps (if needed) and install pinned GMS + Play Store."""
    cache = cache_dir or FIRE_TOOLS_CACHE
    work = work_dir or (cache / "work")
    zip_path = cache / "Fire-Tools.zip"
    _ensure_fire_tools_zip(zip_path)

    gms_apkm = _apkm_from_fire_tools(zip_path, GMS_APKM, work / "apkm")
    play_apkm = _apkm_from_fire_tools(zip_path, PLAY_APKM, work / "apkm")

    gms_splits = _extract_apkm_splits(gms_apkm, work / "gms-splits")
    play_splits = _extract_apkm_splits(play_apkm, work / "play-splits")

    results: dict = {"gsf": {}, "gms": {}, "play": {}}

    results["gsf"] = reinstall_gsf(run_command, device, zip_path, work)

    _uninstall_user_package(run_command, device, GMS_PKG)
    gms_rc, gms_msg = _install_splits(run_command, device, gms_splits)
    results["gms"] = {"rc": gms_rc, "message": gms_msg, "splits": len(gms_splits)}

    _uninstall_user_package(run_command, device, PLAY_PKG)
    play_rc, play_msg = _install_splits(run_command, device, play_splits)
    results["play"] = {"rc": play_rc, "message": play_msg, "splits": len(play_splits)}

    results["whitelist"] = ensure_doze_whitelist(run_command, device)
    results["gms_version"] = package_version_code(run_command, device, GMS_PKG)
    results["play_version"] = package_version_code(run_command, device, PLAY_PKG)
    results["gsf_version"] = package_version_name(run_command, device, GSF_PKG)
    return results


def repair_if_needed(
    run_command,
    device: str,
    *,
    force: bool = False,
    cache_dir: Path | None = None,
    stop_aurora: bool = True,
) -> dict:
    """Whitelist always; reinstall GSF 10 if missing; pin GMS/Play only if force/opt-in.

    ``force=True`` or ``STAYTURGID_HD8_PIN_GMS=1`` reinstalls Fire-Tools GMS+Play.
    Default path only keeps Doze whitelist + GSF 10-x (does not roll back new Play).
    """
    gms_ver = package_version_code(run_command, device, GMS_PKG)
    play_ver = package_version_code(run_command, device, PLAY_PKG)
    gsf_ver = package_version_name(run_command, device, GSF_PKG)
    whitelist = ensure_doze_whitelist(run_command, device)
    if stop_aurora:
        stop_aurora_churn(run_command, device)
    # Full stack pin only when explicitly forced or pin policy enabled + drift.
    pin_stack = force or (
        pin_gms_enabled()
        and (
            needs_gms_downgrade(gms_ver)
            or needs_play_downgrade(play_ver)
        )
    )
    out = {
        "gms_version": gms_ver,
        "play_version": play_ver,
        "gsf_version": gsf_ver,
        "whitelist": whitelist,
        "downgraded": False,
        "pin_policy": pin_gms_enabled(),
    }
    cache = cache_dir or FIRE_TOOLS_CACHE
    zip_path = cache / "Fire-Tools.zip"
    if needs_gsf_reinstall(gsf_ver) and not pin_stack:
        _ensure_fire_tools_zip(zip_path)
        out["gsf"] = reinstall_gsf(
            run_command, device, zip_path, (cache / "work")
        )
        out["gsf_version"] = package_version_name(run_command, device, GSF_PKG)
    if pin_stack:
        out["install"] = reinstall_pinned_stack(
            run_command, device, cache_dir=cache_dir
        )
        out["downgraded"] = True
        out["gms_version"] = package_version_code(run_command, device, GMS_PKG)
        out["play_version"] = package_version_code(run_command, device, PLAY_PKG)
        out["gsf_version"] = package_version_name(run_command, device, GSF_PKG)
    return out
