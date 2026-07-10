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
# Reject 26.x auto-updates (262434022 observed crashing on hd8 2026-07-09).
MAX_GMS_VERSION_CODE = 250_000_000
PINNED_GMS_VERSION_CODE = 243_530_013
PINNED_PLAY_VERSION_CODE = 84_262_300
MAX_PLAY_VERSION_CODE = 85_000_000
GMS_PKG = "com.google.android.gms"
GSF_PKG = "com.google.android.gsf"
PLAY_PKG = "com.android.vending"
WHITELIST_PKGS = (GMS_PKG, GSF_PKG)

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
    if gms_version_code is None:
        return False
    return gms_version_code > MAX_GMS_VERSION_CODE


def needs_play_downgrade(play_version_code: int | None) -> bool:
    if play_version_code is None:
        return False
    return play_version_code > MAX_PLAY_VERSION_CODE


def _ensure_fire_tools_zip(zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.is_file() and zip_path.stat().st_size > 1_000_000:
        return
    tmp = zip_path.with_suffix(".part")
    try:
        subprocess.run(
            ["curl", "-fsSL", "-o", str(tmp), FIRE_TOOLS_ZIP_URL],
            check=True,
            timeout=300,
        )
        tmp.replace(zip_path)
    finally:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)


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
    cmd = [_adb(), "-s", device, "install", "-r", "-g", str(apk)]
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
    cmd = [_adb(), "-s", device, "install-multiple", "-r", "-g", *[str(p) for p in apks]]
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
    """Whitelist always; reinstall pinned APKs when GMS/Play/GSF drift."""
    gms_ver = package_version_code(run_command, device, GMS_PKG)
    play_ver = package_version_code(run_command, device, PLAY_PKG)
    gsf_ver = package_version_name(run_command, device, GSF_PKG)
    whitelist = ensure_doze_whitelist(run_command, device)
    if stop_aurora:
        stop_aurora_churn(run_command, device)
    downgrade = (
        force
        or needs_gms_downgrade(gms_ver)
        or needs_play_downgrade(play_ver)
        or needs_gsf_reinstall(gsf_ver)
    )
    out = {
        "gms_version": gms_ver,
        "play_version": play_ver,
        "gsf_version": gsf_ver,
        "whitelist": whitelist,
        "downgraded": False,
    }
    cache = cache_dir or FIRE_TOOLS_CACHE
    zip_path = cache / "Fire-Tools.zip"
    if needs_gsf_reinstall(gsf_ver) and not downgrade:
        _ensure_fire_tools_zip(zip_path)
        out["gsf"] = reinstall_gsf(
            run_command, device, zip_path, (cache / "work")
        )
        out["gsf_version"] = package_version_name(run_command, device, GSF_PKG)
    if downgrade:
        out["install"] = reinstall_pinned_stack(
            run_command, device, cache_dir=cache_dir
        )
        out["downgraded"] = True
        out["gms_version"] = package_version_code(run_command, device, GMS_PKG)
        out["play_version"] = package_version_code(run_command, device, PLAY_PKG)
        out["gsf_version"] = package_version_name(run_command, device, GSF_PKG)
    return out
