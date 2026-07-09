"""Unit tests for stayturgid_rish install helpers."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "termux" / "py"))

import stayturgid_rish as rish  # noqa: E402


def test_wrapper_body_sets_termux_app_id():
    body = rish._WRAPPER_BODY.format(
        rish_dir="/tmp/rish", dex="rish_shizuku.dex", pkg="moe.shizuku.privileged.api"
    )
    assert 'RISH_APPLICATION_ID="com.termux"' in body
    assert "ShizukuShellLoader" in body


def test_install_writes_dex_and_wrapper(tmp_path, monkeypatch):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("assets/rish_shizuku.dex", b"dexdata")
    monkeypatch.setattr(rish, "HOME", str(tmp_path / "home"))
    monkeypatch.setattr(rish, "STG", str(tmp_path / "home" / ".stayturgid"))
    monkeypatch.setattr(rish, "BIN", str(tmp_path / "home" / ".stayturgid" / "bin"))
    monkeypatch.setattr(
        rish, "RISH_DIR", str(tmp_path / "home" / ".stayturgid" / "lib" / "rish")
    )
    monkeypatch.setattr(
        rish, "WRAPPER", str(tmp_path / "home" / ".stayturgid" / "bin" / "rish")
    )
    monkeypatch.setattr(rish, "shizuku_apk_path", lambda: str(apk))
    path = rish.install(force=True)
    assert Path(path).is_file()
    assert Path(rish.RISH_DIR, "rish_shizuku.dex").read_bytes() == b"dexdata"
    assert Path(path).stat().st_mode & 0o111
    assert rish.installed()
