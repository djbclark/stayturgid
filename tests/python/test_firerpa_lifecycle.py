"""Tests for the FIRERPA accessibility coexistence lifecycle controller."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LIFECYCLE_PATH = REPO / "ansible_collections/stayturgid/firerpa/roles/firerpa/files" / "firerpa_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("firerpa_lifecycle", LIFECYCLE_PATH)
assert SPEC and SPEC.loader
lifecycle_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lifecycle_module)


class FakeTransport:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.commands = []

    def run(self, command, timeout=15):
        self.commands.append((command, timeout))
        if self.responses:
            return self.responses.pop(0)
        return 0, ""


SIGNED, PATCHED = lifecycle_module.SUPPORTED_DRIVERS["10.9"]


def _lifecycle(tmp_path: Path, transport=None, *, active_driver: Path | None = None):
    lifecycle = lifecycle_module.FirerpaLifecycle(
        transport=transport or FakeTransport(),
        root=tmp_path,
        port=65000,
        certificate=tmp_path / "lamda.pem",
        timeout=0.1,
    )
    if active_driver is not None:
        lifecycle._active_driver = active_driver
    return lifecycle


def test_driver_pids_parses_remote_process_list(tmp_path):
    transport = FakeTransport([(0, "101\nnot-a-pid\n202\n")])
    lifecycle = _lifecycle(tmp_path, transport)

    assert lifecycle.driver_pids() == {101, 202}
    assert "pidof lamda" in transport.commands[0][0]
    assert lifecycle_module.DRIVER_ARCHIVE_FRAGMENT in transport.commands[0][0]


def test_remote_sha256_ignores_rish_banner(tmp_path):
    digest = SIGNED
    transport = FakeTransport([(0, f"Entering shell...\n{digest}  /remote/aab.zip\n")])
    lifecycle = _lifecycle(tmp_path, transport)

    assert lifecycle._remote_sha256(Path("/remote/aab.zip")) == digest


def test_remote_sha256_fails_closed_without_digest(tmp_path):
    lifecycle = _lifecycle(tmp_path, FakeTransport([(0, "Entering shell...\n")]))

    with pytest.raises(lifecycle_module.LifecycleError, match="could not read"):
        lifecycle._remote_sha256(Path("/remote/aab.zip"))


def test_start_is_idempotent_when_patched_driver_is_active(tmp_path, monkeypatch, capsys):
    lifecycle = _lifecycle(tmp_path, active_driver=tmp_path / "active.zip")
    monkeypatch.setattr(lifecycle, "validate", lambda: None)
    monkeypatch.setattr(
        lifecycle,
        "_remote_sha256",
        lambda _path: PATCHED,
    )
    monkeypatch.setattr(lifecycle, "_port_open", lambda: True)
    monkeypatch.setattr(lifecycle, "driver_pids", lambda: {101})

    lifecycle.start()

    assert "already active" in capsys.readouterr().out


def test_start_launches_signed_server_then_activates_patch(tmp_path, monkeypatch):
    lifecycle = _lifecycle(tmp_path, active_driver=tmp_path / "active.zip")
    calls = []
    monkeypatch.setattr(lifecycle, "validate", lambda: None)
    monkeypatch.setattr(
        lifecycle,
        "_remote_sha256",
        lambda _path: SIGNED,
    )
    monkeypatch.setattr(lifecycle, "_port_open", lambda: False)
    monkeypatch.setattr(lifecycle, "_launch_signed_server", lambda: calls.append("launch"))
    monkeypatch.setattr(
        lifecycle,
        "_activate_coexistence_driver",
        lambda: calls.append("activate"),
    )

    lifecycle.start()

    assert calls == ["launch", "activate"]


def test_launch_accepts_adb_client_timeout_when_listener_is_open(tmp_path, monkeypatch):
    lifecycle = _lifecycle(tmp_path, FakeTransport([(-1, "")]), active_driver=tmp_path / "active.zip")
    monkeypatch.setattr(lifecycle, "_copy_atomic", lambda *_args: None)
    monkeypatch.setattr(lifecycle, "_port_open", lambda: True)

    lifecycle._launch_signed_server()


def test_launch_reports_adb_client_timeout_when_listener_stays_closed(tmp_path, monkeypatch):
    lifecycle = _lifecycle(tmp_path, FakeTransport([(-1, "")]), active_driver=tmp_path / "active.zip")
    monkeypatch.setattr(lifecycle, "_copy_atomic", lambda *_args: None)
    monkeypatch.setattr(lifecycle, "_port_open", lambda: False)

    with pytest.raises(lifecycle_module.LifecycleError, match="exit -1"):
        lifecycle._launch_signed_server()


def test_copy_atomic_uses_remote_temporary_and_replace(tmp_path):
    transport = FakeTransport()
    lifecycle = _lifecycle(tmp_path, transport)

    lifecycle._copy_atomic(Path("/signed.zip"), Path("/active.zip"))

    command = transport.commands[0][0]
    assert command.startswith("cp /signed.zip /.active.zip.stayturgid.tmp")
    assert "chmod 0644" in command
    assert "mv -f" in command


def test_transport_from_adb_arguments():
    parser_args = type(
        "Args",
        (),
        {"adb_target": "phone:5555", "adb": "adb", "rish": None},
    )()

    transport = lifecycle_module._transport_from_args(parser_args)

    assert transport.prefix == ["adb", "-s", "phone:5555", "shell"]


def test_active_driver_is_found_under_whichever_python_minor_exists(tmp_path):
    found = f"{tmp_path}/server/lib/python3.13/site-packages/lamda/aab.zip"
    transport = FakeTransport([(0, f"Entering shell...\n{found}\n")])
    lifecycle = _lifecycle(tmp_path, transport)

    assert lifecycle.active_driver == Path(found)
    assert "lib/python3.*/site-packages/lamda/aab.zip" in transport.commands[0][0]
    assert lifecycle.active_driver == Path(found)
    assert len(transport.commands) == 1, "the location is looked up once"


@pytest.mark.parametrize(
    "listing",
    ["", "/a/lib/python3.12/site-packages/lamda/aab.zip\n/a/lib/python3.13/site-packages/lamda/aab.zip\n"],
)
def test_active_driver_fails_closed_unless_exactly_one_exists(tmp_path, listing):
    lifecycle = _lifecycle(tmp_path, FakeTransport([(0, listing)]))

    with pytest.raises(lifecycle_module.LifecycleError, match="expected exactly one"):
        lifecycle.active_driver


def _validating(tmp_path, monkeypatch, signed: str, patched: str):
    lifecycle = _lifecycle(tmp_path, active_driver=tmp_path / "active.zip")
    digests = {lifecycle.signed_driver: signed, lifecycle.patched_driver: patched}
    monkeypatch.setattr(lifecycle, "_remote_sha256", lambda path: digests[path])
    return lifecycle


def test_validate_accepts_a_supported_signed_and_patched_pair(tmp_path, monkeypatch):
    _validating(tmp_path, monkeypatch, SIGNED, PATCHED).validate()


@pytest.mark.parametrize(
    ("signed", "patched"),
    [("0" * 64, PATCHED), (SIGNED, "0" * 64), (PATCHED, SIGNED)],
)
def test_validate_refuses_drivers_outside_the_version_table(tmp_path, monkeypatch, signed, patched):
    lifecycle = _validating(tmp_path, monkeypatch, signed, patched)

    with pytest.raises(lifecycle_module.LifecycleError, match="not a pair in SUPPORTED_DRIVERS"):
        lifecycle.validate()
