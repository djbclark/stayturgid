"""Unit tests for stayturgid_rish install helpers."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import stayturgid_rish as rish


def test_wrapper_body_sets_termux_app_id():
    body = rish._WRAPPER_BODY.format(rish_dir="/tmp/rish", dex="rish_shizuku.dex", pkg="moe.shizuku.privileged.api")
    assert 'RISH_APPLICATION_ID="com.termux"' in body
    assert "ShizukuShellLoader" in body


def test_install_writes_dex_and_wrapper(tmp_path, monkeypatch):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("assets/rish_shizuku.dex", b"dexdata")
    monkeypatch.setattr(rish, "HOME", str(tmp_path / "home"))
    monkeypatch.setattr(rish, "STG", str(tmp_path / "home" / ".stayturgid"))
    monkeypatch.setattr(rish, "BIN", str(tmp_path / "home" / ".stayturgid" / "bin"))
    monkeypatch.setattr(rish, "RISH_DIR", str(tmp_path / "home" / ".stayturgid" / "lib" / "rish"))
    monkeypatch.setattr(rish, "WRAPPER", str(tmp_path / "home" / ".stayturgid" / "bin" / "rish"))
    monkeypatch.setattr(rish, "shizuku_apk_path", lambda: str(apk))
    path = rish.install(force=True)
    assert Path(path).is_file()
    assert Path(rish.RISH_DIR, "rish_shizuku.dex").read_bytes() == b"dexdata"
    assert Path(path).stat().st_mode & 0o111
    assert rish.installed()


def _point_at(tmp_path, monkeypatch, apk):
    monkeypatch.setattr(rish, "HOME", str(tmp_path / "home"))
    monkeypatch.setattr(rish, "STG", str(tmp_path / "home" / ".stayturgid"))
    monkeypatch.setattr(rish, "BIN", str(tmp_path / "home" / ".stayturgid" / "bin"))
    monkeypatch.setattr(rish, "RISH_DIR", str(tmp_path / "home" / ".stayturgid" / "lib" / "rish"))
    monkeypatch.setattr(rish, "WRAPPER", str(tmp_path / "home" / ".stayturgid" / "bin" / "rish"))
    monkeypatch.setattr(rish, "shizuku_apk_path", lambda: str(apk))


def test_install_replaces_a_stale_dex_after_an_app_update(tmp_path, monkeypatch):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("assets/rish_shizuku.dex", b"old")
    _point_at(tmp_path, monkeypatch, apk)
    rish.install(force=True)
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("assets/rish_shizuku.dex", b"new")
    rish.install()
    assert Path(rish.RISH_DIR, "rish_shizuku.dex").read_bytes() == b"new"


def test_install_leaves_a_current_dex_alone(tmp_path, monkeypatch):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("assets/rish_shizuku.dex", b"same")
    _point_at(tmp_path, monkeypatch, apk)
    rish.install(force=True)
    dex = Path(rish.RISH_DIR, "rish_shizuku.dex")
    before = dex.stat().st_mtime_ns
    rish.install()
    assert dex.stat().st_mtime_ns == before


def test_install_command_reports_a_change_only_when_it_writes(tmp_path, monkeypatch, capsys):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("assets/rish_shizuku.dex", b"same")
    _point_at(tmp_path, monkeypatch, apk)
    assert rish.main(["install"]) == 0
    assert capsys.readouterr().out.startswith("rish installed: ")
    assert rish.main(["install"]) == 0
    assert capsys.readouterr().out.startswith("rish up to date: ")
    # The role's changed_when keys on the first form only (rish.yml).
    role = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"
    task = yaml.safe_load((role / "tasks/rish.yml").read_text())[0]
    assert task["changed_when"] == "'rish installed:' in (_rish_install.stdout | default(''))"
