"""Unit tests for control/bin/check_termux_pkg_updates.py."""

from __future__ import annotations

import importlib.util
import json
import os
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


def _recorder(log: list[str], ok: bool):
    """A hermes_notify stand-in: records each message, reports *ok*."""

    def send(message: str) -> bool:
        log.append(message)
        return ok

    return send


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
            {},
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
    monkeypatch.setattr(ctu, "collect_updates", lambda hosts, *, refresh=True: ({}, {}, []))

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
            {},
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
        lambda hosts, *, refresh=True: ({}, {}, ["s24: down", "p7a: down"]),
    )
    monkeypatch.setattr(ctu, "hermes_notify", lambda msg: None)
    assert ctu.main([]) == 1


def test_should_notify_first_seen_and_unchanged(tmp_path: Path) -> None:
    path = str(tmp_path / "st.json")
    updates = ["s24: runit: 2.1 -> 2.3"]
    assert ctu.should_notify(path, updates) is True
    ctu.write_state(
        path,
        updates=updates,
        by_host={},
        errors=[],
        hosts_checked=["s24"],
        last_notified=updates,
    )
    assert ctu.should_notify(path, updates) is False
    assert ctu.should_notify(path, ["s24: runit: 2.1 -> 2.4"]) is True


def test_main_skips_repeat_telegram(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "termux-pkg-updates.json"
    monkeypatch.setattr(ctu, "STATE_PATH", str(state_path))
    monkeypatch.setattr(ctu, "list_hosts", lambda limit=None: ["s24"])
    monkeypatch.setattr(
        ctu,
        "collect_updates",
        lambda hosts, *, refresh=True: (
            {"s24": [{"name": "git", "current": "a", "latest": "b"}]},
            {},
            [],
        ),
    )
    called: list[str] = []
    monkeypatch.setattr(ctu, "hermes_notify", _recorder(called, True))
    assert ctu.main([]) == 0
    assert len(called) == 1
    assert ctu.main([]) == 0
    assert len(called) == 1


# --- #309: pip-only packages (not from apt, not declared) ----------------------


def test_parse_pip_only_reads_dist_info_names() -> None:
    text = (
        "termux_ai-0.5.2.dist-info\ncharset_normalizer-3.5.1.dist-info\nnoise\n-1.0.dist-info\n"
        "oldpkg-0.1-py3.13.egg-info\nevil\x1b[31m-1.0.dist-info\nsp ace-1.0.dist-info\n"
    )
    assert ctu.parse_pip_only(text) == [
        {"name": "termux_ai", "version": "0.5.2"},
        {"name": "charset_normalizer", "version": "3.5.1"},
        {"name": "oldpkg", "version": "0.1"},
        {"name": "unrecognised-metadata-entries", "version": "3"},
    ]


def test_message_caps_lines_per_host_but_dedup_sees_them_all() -> None:
    pkgs = [{"name": f"p{i:02d}", "version": "1"} for i in range(25)]
    lines = ctu.build_pip_lines({"t2e": pkgs, "s24": pkgs[:2]}, set())
    assert len(lines) == 27, "the dedup key and state keep every package"
    shown = ctu.cap_lines_per_host(lines)
    assert len(shown) == 2 + ctu._MAX_PIP_LINES_PER_HOST + 1
    assert shown[-1] == "t2e: pip-only and 5 more"
    swapped = ctu.build_pip_lines({"t2e": [*pkgs[:24], {"name": "zz", "version": "1"}], "s24": pkgs[:2]}, set())
    assert sorted(swapped) != sorted(lines), "a change past the cap is still a change"


def test_unrecognised_metadata_entries_are_counted_not_dropped() -> None:
    found = ctu.parse_pip_only("ok-1.0.dist-info\nbad name-1.dist-info\nevil\x1b-2.dist-info\n")
    assert found == [{"name": "ok", "version": "1.0"}, {"name": "unrecognised-metadata-entries", "version": "2"}]


def test_apt_lines_lose_control_characters() -> None:
    assert ctu.format_package_line({"name": "cu\x1b[31mrl", "current": "1", "latest": "2"}) == "cu?[31mrl: 1 -> 2"


def test_hermes_notify_never_raises_and_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(title, message):
        raise FileNotFoundError("hermes")

    monkeypatch.setattr(ctu._hermes, "notify", boom)
    assert ctu.hermes_notify("x") is False
    seen: dict[str, str] = {}

    def accept(title: str, message: str) -> bool:
        seen["m"] = message
        return True

    monkeypatch.setattr(ctu._hermes, "notify", accept)
    assert ctu.hermes_notify("y" * 9000) is True
    assert len(seen["m"]) == ctu._MAX_MESSAGE_CHARS and seen["m"].endswith("(truncated)")


def _pip_main(monkeypatch, tmp_path, send_ok):
    monkeypatch.setattr(ctu, "STATE_PATH", str(tmp_path / "termux-pkg-updates.json"))
    monkeypatch.setattr(ctu, "list_hosts", lambda limit=None: ["t2e"])
    monkeypatch.setattr(
        ctu,
        "collect_updates",
        lambda hosts, *, refresh=True: ({}, {"t2e": [{"name": "termux_ai", "version": "0.5.2"}]}, []),
    )
    sent: list[str] = []
    monkeypatch.setattr(ctu, "hermes_notify", _recorder(sent, send_ok))
    return sent


def test_failed_send_is_retried_on_the_next_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Adversary review H1: the state used to record a notice before the send,
    so a send that crashed (no `hermes` on launchd's PATH) was never retried."""
    sent = _pip_main(monkeypatch, tmp_path, send_ok=False)
    assert ctu.main([]) == 0 and len(sent) == 1
    assert json.loads((tmp_path / "termux-pkg-updates.json").read_text())["last_notified"] == []
    sent = _pip_main(monkeypatch, tmp_path, send_ok=True)
    assert ctu.main([]) == 0 and len(sent) == 1, "the unsent notice goes out on the next run"
    sent = _pip_main(monkeypatch, tmp_path, send_ok=True)
    assert ctu.main([]) == 0 and sent == []


def test_dry_run_does_not_use_up_the_notice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sent = _pip_main(monkeypatch, tmp_path, send_ok=True)
    assert ctu.main(["--dry-run"]) == 0 and sent == []
    assert ctu.main([]) == 0 and len(sent) == 1


def test_declared_pip_packages_normalizes_names(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("# comment\n\nCharset_Normalizer>=3  # why\nrequests[socks]==2.34\n-r other.txt\n", encoding="utf-8")
    assert ctu.declared_pip_packages(req) == {"charset-normalizer", "requests"}
    assert ctu.declared_pip_packages(tmp_path / "missing.txt") == set()


def test_repo_requirements_file_declares_nothing_today() -> None:
    """The policy (#309): device code is stdlib only, so no pip package is declared.
    Adding one is a deliberate change that this test makes visible."""
    assert ctu.DEVICE_REQUIREMENTS.is_file()
    assert ctu.declared_pip_packages() == set()


def test_build_pip_lines_skips_declared() -> None:
    pip_by_host = {"t2e": [{"name": "termux_ai", "version": "0.5.2"}, {"name": "requests", "version": "2.34.2"}]}
    assert ctu.build_pip_lines(pip_by_host, {"requests"}) == ["t2e: pip-only termux_ai 0.5.2"]


def test_remote_script_lists_only_unowned_dist_info(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run the real remote script under bash against a fake Termux prefix:
    apt's own packages (dpkg owns their dist-info) must not be reported."""
    import shutil
    import subprocess

    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    prefix = tmp_path / "usr"
    site = prefix / "lib" / "python3.13" / "site-packages"
    for d in (
        "pip-26.2.1.dist-info",
        "termux_ai-0.5.2.dist-info",
        "requests-2.34.2.dist-info",
        "oldpkg-0.1-py3.13.egg-info",
    ):
        (site / d).mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".local" / "lib" / "python3.13" / "site-packages" / "userpkg-1.0.dist-info").mkdir(parents=True)
    (prefix / "bin").mkdir()
    (prefix / "tmp").mkdir()
    (prefix / "bin" / "apt").write_text(
        "#!/bin/bash\necho 'Listing...'\necho 'curl/stable 2.0 aarch64 [upgradable from: 1.0]'\n", encoding="utf-8"
    )
    owned = site / "pip-26.2.1.dist-info"
    (prefix / "bin" / "dpkg").write_text(
        f'#!/bin/bash\nfor p in "${{@:2}}"; do [ "$p" = \'{owned}\' ] && echo "python-pip: $p" '
        '|| echo "dpkg-query: no path found matching pattern $p" >&2; done\nexit 1\n',
        encoding="utf-8",
    )
    for tool in ("apt", "dpkg"):
        (prefix / "bin" / tool).chmod(0o755)

    seen: dict[str, str] = {}
    real_run = subprocess.run  # ctu.subprocess is this module: keep the real one

    def fake_run(args, **kwargs):
        seen["remote"] = args[-1].replace(ctu.TERMUX_PREFIX, str(prefix))
        return real_run(["bash", "-c", seen["remote"]], env={**os.environ, "HOME": str(home)}, **kwargs)

    monkeypatch.setattr(ctu.subprocess, "run", fake_run)
    monkeypatch.setattr(ctu.dev, "resolve_ssh_host", lambda h, conf_path=None: h)
    apt, pip_only, err = ctu.ssh_probe("t2e", refresh=False)
    assert err is None
    assert apt == [{"name": "curl", "latest": "2.0", "current": "1.0"}]
    assert sorted(p["name"] for p in pip_only) == ["oldpkg", "requests", "termux_ai", "userpkg"]


def test_remote_script_keeps_apt_failure_as_the_exit_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import subprocess

    prefix = tmp_path / "usr"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / "apt").write_text("#!/bin/bash\necho 'E: broken' >&2\nexit 100\n", encoding="utf-8")
    (prefix / "bin" / "apt").chmod(0o755)

    real_run = subprocess.run

    def fake_run(args, **kwargs):
        remote = args[-1].replace(ctu.TERMUX_PREFIX, str(prefix))
        return real_run(["bash", "-c", remote], env={**os.environ, "HOME": str(tmp_path)}, **kwargs)

    monkeypatch.setattr(ctu.subprocess, "run", fake_run)
    monkeypatch.setattr(ctu.dev, "resolve_ssh_host", lambda h, conf_path=None: h)
    apt, pip_only, err = ctu.ssh_probe("s24", refresh=False)
    assert err is not None and "s24" in err


def test_main_reports_pip_only_packages_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_path = tmp_path / "termux-pkg-updates.json"
    monkeypatch.setattr(ctu, "STATE_PATH", str(state_path))
    monkeypatch.setattr(ctu, "list_hosts", lambda limit=None: ["t2e", "s24"])
    monkeypatch.setattr(
        ctu,
        "collect_updates",
        lambda hosts, *, refresh=True: ({}, {"t2e": [{"name": "termux_ai", "version": "0.5.2"}]}, []),
    )
    sent: list[str] = []
    monkeypatch.setattr(ctu, "hermes_notify", _recorder(sent, True))

    assert ctu.main([]) == 0
    assert len(sent) == 1 and "t2e: pip-only termux_ai 0.5.2" in sent[0] and "#309" in sent[0]
    assert json.loads(state_path.read_text())["pip_only"] == ["t2e: pip-only termux_ai 0.5.2"]
    assert ctu.main([]) == 0
    assert len(sent) == 1, "unchanged pip drift must not page again"
