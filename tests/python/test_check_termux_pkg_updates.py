"""Unit tests for control/bin/check_termux_pkg_updates.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_MOD = REPO / "control" / "bin" / "check_termux_pkg_updates.py"
_spec = importlib.util.spec_from_file_location("check_termux_pkg_updates", _MOD)
assert _spec is not None
ctu = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ctu)


# --- parse_apt_upgradable -----------------------------------------------------


def test_parse_apt_upgradable_extracts_name_and_versions() -> None:
    text = """\
Listing...
curl/stable 8.12.1 aarch64 [upgradable from: 8.11.0]
libandroid-support/stable 29-1 aarch64 [upgradable from: 28-3]
"""
    pkgs = ctu.parse_apt_upgradable(text)
    assert pkgs == [
        {"name": "curl", "latest": "8.12.1", "current": "8.11.0"},
        {"name": "libandroid-support", "latest": "29-1", "current": "28-3"},
    ]


def test_parse_apt_upgradable_empty_listing() -> None:
    assert ctu.parse_apt_upgradable("Listing...\n") == []
    assert ctu.parse_apt_upgradable("") == []


def test_parse_apt_upgradable_ignores_noise() -> None:
    text = """\
WARNING: apt does not have a stable CLI interface
Listing... Done
something-weird without brackets
openssh/stable 10.4p1 aarch64 [upgradable from: 9.9p1]
"""
    pkgs = ctu.parse_apt_upgradable(text)
    assert len(pkgs) == 1
    assert pkgs[0]["name"] == "openssh"
    assert pkgs[0]["current"] == "9.9p1"
    assert pkgs[0]["latest"] == "10.4p1"


def test_build_update_lines_sorted_by_host() -> None:
    by_host = {
        "p7a": [{"name": "curl", "current": "1", "latest": "2"}],
        "s24": [
            {"name": "git", "current": "2.40", "latest": "2.50"},
            {"name": "wget", "current": "1.0", "latest": "1.1"},
        ],
    }
    lines = ctu.build_update_lines(by_host)
    assert lines == [
        "p7a: curl: 1 -> 2",
        "s24: git: 2.40 -> 2.50",
        "s24: wget: 1.0 -> 1.1",
    ]


# --- list_hosts ---------------------------------------------------------------


def test_list_hosts_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ctu.dev,
        "iter_devices_conf",
        lambda conf_path=None: [
            ("s24", "usb1", "1.1.1.1", "-", "-"),
            ("p7a", "usb2", "1.1.1.2", "-", "-"),
            ("hd8", "usb3", "1.1.1.3", "-", "-"),
        ],
    )
    assert ctu.list_hosts(None) == ["s24", "p7a", "hd8"]
    assert ctu.list_hosts("p7a,hd8") == ["p7a", "hd8"]
    assert ctu.list_hosts("missing") == []


# --- ssh_upgradable / main ----------------------------------------------------


class _Result:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_ssh_upgradable_parses_remote_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(args, **kwargs):
        assert args[0] == "ssh"
        assert "s24" in args
        remote = args[-1]
        assert "apt list --upgradable" in remote
        assert "pkg update" in remote
        return _Result(
            0,
            stdout="Listing...\ncurl/stable 2.0 aarch64 [upgradable from: 1.0]\n",
        )

    monkeypatch.setattr(ctu.subprocess, "run", fake_run)
    monkeypatch.setattr(ctu.dev, "resolve_ssh_host", lambda h, conf_path=None: h)
    pkgs, err = ctu.ssh_upgradable("s24")
    assert err is None
    assert pkgs == [{"name": "curl", "latest": "2.0", "current": "1.0"}]


def test_ssh_upgradable_no_refresh_skips_pkg_update(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def fake_run(args, **kwargs):
        seen["remote"] = args[-1]
        return _Result(0, stdout="Listing...\n")

    monkeypatch.setattr(ctu.subprocess, "run", fake_run)
    monkeypatch.setattr(ctu.dev, "resolve_ssh_host", lambda h, conf_path=None: h)
    pkgs, err = ctu.ssh_upgradable("s24", refresh=False)
    assert err is None
    assert pkgs == []
    assert "pkg update" not in seen["remote"]


def test_ssh_upgradable_returns_error_on_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ctu.subprocess,
        "run",
        lambda *a, **k: _Result(255, stderr="Connection refused"),
    )
    monkeypatch.setattr(ctu.dev, "resolve_ssh_host", lambda h, conf_path=None: h)
    pkgs, err = ctu.ssh_upgradable("s24")
    assert pkgs == []
    assert err is not None
    assert "s24" in err


def test_ssh_upgradable_returns_error_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*a, **k):
        raise ctu.subprocess.TimeoutExpired(cmd=a[0] if a else "ssh", timeout=180)

    monkeypatch.setattr(ctu.subprocess, "run", fake_run)
    monkeypatch.setattr(ctu.dev, "resolve_ssh_host", lambda h, conf_path=None: h)
    pkgs, err = ctu.ssh_upgradable("s24")
    assert pkgs == []
    assert err is not None
    assert "timed out" in err
    assert "s24" in err


def test_main_notifies_on_updates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "termux-pkg-updates.json"
    monkeypatch.setattr(ctu, "STATE_PATH", str(state_path))
    monkeypatch.setattr(ctu, "list_hosts", lambda limit=None: ["s24", "p7a"])

    def fake_collect(hosts, *, refresh=True):
        return (
            {
                "s24": [{"name": "curl", "current": "1", "latest": "2"}],
            },
            [],
        )

    monkeypatch.setattr(ctu, "collect_updates", fake_collect)

    sent: dict[str, list[str]] = {}
    monkeypatch.setattr(ctu, "hermes_notify", lambda msg: sent.setdefault("msg", msg))

    assert ctu.main([]) == 0
    assert "Stayturgid Termux package updates available" in sent["msg"]
    assert "s24: curl: 1 -> 2" in sent["msg"]
    state = json.loads(state_path.read_text())
    assert state["updates"]
    assert state["hosts_checked"] == ["s24", "p7a"]


def test_main_does_not_notify_when_current(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "termux-pkg-updates.json"
    monkeypatch.setattr(ctu, "STATE_PATH", str(state_path))
    monkeypatch.setattr(ctu, "list_hosts", lambda limit=None: ["s24"])
    monkeypatch.setattr(ctu, "collect_updates", lambda hosts, *, refresh=True: ({}, []))

    called: list[str] = []
    monkeypatch.setattr(ctu, "hermes_notify", lambda msg: called.append(msg))

    assert ctu.main([]) == 0
    assert called == []
    state = json.loads(state_path.read_text())
    assert state["updates"] == []


def test_main_dry_run_skips_hermes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "termux-pkg-updates.json"
    monkeypatch.setattr(ctu, "STATE_PATH", str(state_path))
    monkeypatch.setattr(ctu, "list_hosts", lambda limit=None: ["s24"])
    monkeypatch.setattr(
        ctu,
        "collect_updates",
        lambda hosts, *, refresh=True: (
            {"s24": [{"name": "git", "current": "a", "latest": "b"}]},
            [],
        ),
    )
    called: list[str] = []
    monkeypatch.setattr(ctu, "hermes_notify", lambda msg: called.append(msg))

    assert ctu.main(["--dry-run"]) == 0
    assert called == []
    assert json.loads(state_path.read_text())["updates"]


def test_main_all_hosts_failed_exits_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "termux-pkg-updates.json"
    monkeypatch.setattr(ctu, "STATE_PATH", str(state_path))
    monkeypatch.setattr(ctu, "list_hosts", lambda limit=None: ["s24", "p7a"])
    monkeypatch.setattr(
        ctu,
        "collect_updates",
        lambda hosts, *, refresh=True: ({}, ["s24: down", "p7a: down"]),
    )
    monkeypatch.setattr(ctu, "hermes_notify", lambda msg: None)
    assert ctu.main([]) == 1
