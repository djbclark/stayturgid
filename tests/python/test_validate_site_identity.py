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


# ---------------------------------------------------------------------------
# B6: .cf scanning + site-overlay denylist patterns (Gemini #3, H1 scanner gap)
# ---------------------------------------------------------------------------


def _prod_site() -> "_Site":
    return _Site(
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


def _fake_tracked(monkeypatch: pytest.MonkeyPatch, names: str) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_a, **_kw: type("R", (), {"returncode": 0, "stdout": names, "stderr": ""})(),
    )


def test_check_drift_scans_cf_policy_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """H1 scanner gap: a live address rendered into a tracked .cf must fail."""
    leak = tmp_path / "cf-runagent.cf"
    leak.write_text('hosts => { "198.18.0.50:5308" };\n', encoding="utf-8")
    _fake_tracked(monkeypatch, "cf-runagent.cf\n")
    violations = v.check_drift(_prod_site(), tmp_path)
    assert len(violations) == 1
    assert violations[0]["file"] == "cf-runagent.cf"


def test_check_drift_applies_overlay_denylist_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A denylisted-subnet literal not in the live inventory must still fail."""
    src = tmp_path / "tool.py"
    src.write_text('FALLBACK = "10.99.1.7"\n', encoding="utf-8")
    _fake_tracked(monkeypatch, "tool.py\n")
    extra = [(r"\b10\.99\.\d{1,3}\.\d{1,3}\b", "site denylist pattern 'lan'")]
    violations = v.check_drift(_prod_site(), tmp_path, extra)
    assert len(violations) == 1
    assert "site denylist" in violations[0]["pattern"]
    # Without the overlay the same literal passes (it is not live inventory).
    assert v.check_drift(_prod_site(), tmp_path) == []


def test_parse_identity_patterns_flat_yaml() -> None:
    text = "---\n# comment\npatterns:\n  - '\\b192\\.0\\.2\\.\\d{1,3}\\b'\n  - '\\bexample\\b'\n"
    assert v._parse_identity_patterns(text) == [
        "\\b192\\.0\\.2\\.\\d{1,3}\\b",
        "\\bexample\\b",
    ]


def test_load_overlay_patterns_from_active_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site = tmp_path / "site-overlay"
    (site / "inventory").mkdir(parents=True)
    (site / "ansible.cfg").write_text("[defaults]\ninventory = inventory/hosts.yml\n", encoding="utf-8")
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")
    (site / "registry").mkdir()
    (site / "registry" / "identity-patterns.yml").write_text(
        "patterns:\n  - '\\b10\\.99\\.\\d{1,3}\\.\\d{1,3}\\b'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANSIBLE_CONFIG", str(site / "ansible.cfg"))
    pairs = v.load_overlay_patterns(_ROOT)
    assert len(pairs) == 1
    assert pairs[0][0] == "\\b10\\.99\\.\\d{1,3}\\.\\d{1,3}\\b"


def test_load_overlay_patterns_absent_without_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    upstream = tmp_path / "product-ansible"
    upstream.mkdir()
    (upstream / "ansible.cfg").write_text("[defaults]\ninventory = hosts.yml\n", encoding="utf-8")
    (upstream / "hosts.yml").write_text("all: {}\n", encoding="utf-8")
    monkeypatch.setenv("ANSIBLE_CONFIG", str(upstream / "ansible.cfg"))
    assert v.load_overlay_patterns(_ROOT) == []


def test_load_overlay_patterns_invalid_regex_is_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site = tmp_path / "site-overlay"
    (site / "registry").mkdir(parents=True)
    (site / "ansible.cfg").write_text("[defaults]\ninventory = hosts.yml\n", encoding="utf-8")
    (site / "hosts.yml").write_text("all: {}\n", encoding="utf-8")
    (site / "registry" / "identity-patterns.yml").write_text("patterns:\n  - '(unbalanced'\n", encoding="utf-8")
    monkeypatch.setenv("ANSIBLE_CONFIG", str(site / "ansible.cfg"))
    with pytest.raises(ValueError, match="Invalid regex"):
        v.load_overlay_patterns(_ROOT)
