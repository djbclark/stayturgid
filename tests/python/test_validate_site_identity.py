"""Unit tests for control/bin/validate_site_identity.py drift helpers."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LIB = _ROOT / "control" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


def _load_validator():
    path = _ROOT / "control" / "bin" / "validate_site_identity.py"
    spec = importlib.util.spec_from_file_location("validate_site_identity", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(path)
    spec.loader.exec_module(mod)
    return mod


v = _load_validator()


@dataclass(frozen=True)
class _Dev:
    alias: str
    ansible_host: str
    device_usb_serial: str
    device_lan_ip: str
    device_label: str = "label"
    ansible_port: int = 8022
    ansible_user: str = "termux"
    stayturgid_automation_mode: str = "autojs6"


@dataclass(frozen=True)
class _Ctrl:
    ssh_user: str = "operator"
    lan_ip: str = "192.0.2.1"
    tailscale_ip: str = "100.0.0.1"


@dataclass(frozen=True)
class _Site:
    telegram_allowed_users: tuple[str, ...]
    telegram_home_channel: str
    devices: dict
    control_node: _Ctrl


def test_is_generic_fixture_aliases_and_rfc5737() -> None:
    assert v.is_generic_fixture("oneui-device")
    assert v.is_generic_fixture("stock-android-device")
    assert v.is_generic_fixture("fireos-device")
    assert v.is_generic_fixture("192.0.2.11")
    assert v.is_generic_fixture("100.0.0.11")
    assert v.is_generic_fixture("EXAMPLE-SERIAL-ONEUI")
    assert not v.is_generic_fixture("prod-phone")
    assert not v.is_generic_fixture("198.18.0.1")  # not TEST-NET


def test_build_drift_patterns_skips_generic_identity() -> None:
    site = _Site(
        telegram_allowed_users=(),
        telegram_home_channel="",
        devices={
            "oneui-device": _Dev(
                "oneui-device",
                "100.0.0.11",
                "EXAMPLE-SERIAL-ONEUI",
                "192.0.2.11",
            )
        },
        control_node=_Ctrl(),
    )
    patterns = v._build_drift_patterns(site)
    assert patterns == []


def test_build_drift_patterns_includes_production_identity() -> None:
    site = _Site(
        telegram_allowed_users=(),
        telegram_home_channel="",
        devices={
            "prod-phone": _Dev(
                "prod-phone",
                "198.18.0.50",
                "REALSERIAL001",
                "10.0.0.50",
            )
        },
        control_node=_Ctrl(lan_ip="10.0.0.1", tailscale_ip="198.18.0.1"),
    )
    patterns = v._build_drift_patterns(site)
    descs = [d for _, d in patterns]
    assert any("device alias 'prod-phone'" in d for d in descs)
    assert any("ansible_host IP" in d for d in descs)
    assert any("USB serial" in d for d in descs)
    assert any("LAN IP" in d for d in descs)
    assert any("control node LAN IP" in d for d in descs)
    assert any("control node Tailscale IP" in d for d in descs)


def test_check_drift_finds_hardcoded_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site = _Site(
        telegram_allowed_users=(),
        telegram_home_channel="",
        devices={
            "prod-phone": _Dev(
                "prod-phone",
                "198.18.0.50",
                "REALSERIAL001",
                "10.0.0.50",
            )
        },
        control_node=_Ctrl(lan_ip="10.0.0.1", tailscale_ip="198.18.0.1"),
    )
    src = tmp_path / "tool.py"
    src.write_text('HOST = "prod-phone"\n', encoding="utf-8")
    # Pretend tmp_path is a git repo root with one tracked file
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_a, **_kw: type(
            "R",
            (),
            {"returncode": 0, "stdout": "tool.py\n", "stderr": ""},
        )(),
    )
    # Make Path.suffix check work: root is tmp_path
    violations = v.check_drift(site, tmp_path)
    assert len(violations) == 1
    assert violations[0]["file"] == "tool.py"
    assert "prod-phone" in violations[0]["pattern"]


def test_check_drift_clean_when_no_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site = _Site(
        telegram_allowed_users=(),
        telegram_home_channel="",
        devices={
            "prod-phone": _Dev(
                "prod-phone",
                "198.18.0.50",
                "REALSERIAL001",
                "10.0.0.50",
            )
        },
        control_node=_Ctrl(lan_ip="10.0.0.1", tailscale_ip="198.18.0.1"),
    )
    src = tmp_path / "tool.py"
    src.write_text('HOST = "oneui-device"\n', encoding="utf-8")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_a, **_kw: type(
            "R",
            (),
            {"returncode": 0, "stdout": "tool.py\n", "stderr": ""},
        )(),
    )
    assert v.check_drift(site, tmp_path) == []
