"""Tests for the FIRERPA accessibility coexistence lifecycle controller."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LIFECYCLE_PATH = (
    REPO
    / "ansible_collections/stayturgid/firerpa/roles/firerpa/files"
    / "firerpa_lifecycle.py"
)
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


def _lifecycle(tmp_path: Path, transport=None):
    return lifecycle_module.FirerpaLifecycle(
        transport=transport or FakeTransport(),
        root=tmp_path,
        port=65000,
        certificate=tmp_path / "lamda.pem",
        timeout=0.1,
    )


def test_service_jar_pids_parses_remote_process_list(tmp_path):
    transport = FakeTransport([(0, "101\nnot-a-pid\n202\n")])
    lifecycle = _lifecycle(tmp_path, transport)

    assert lifecycle.service_jar_pids() == {101, 202}
    assert "pidof lamda" in transport.commands[0][0]
    assert lifecycle_module.SERVICE_JAR_FRAGMENT in transport.commands[0][0]


def test_remote_sha256_ignores_rish_banner(tmp_path):
    digest = lifecycle_module.SIGNED_JAR_SHA256
    transport = FakeTransport(
        [(0, f"Entering shell...\n{digest}  /remote/service.jar\n")]
    )
    lifecycle = _lifecycle(tmp_path, transport)

    assert lifecycle._remote_sha256(Path("/remote/service.jar")) == digest


def test_remote_sha256_fails_closed_without_digest(tmp_path):
    lifecycle = _lifecycle(tmp_path, FakeTransport([(0, "Entering shell...\n")]))

    with pytest.raises(lifecycle_module.LifecycleError, match="could not read"):
        lifecycle._remote_sha256(Path("/remote/service.jar"))


def test_start_is_idempotent_when_patched_driver_is_active(
    tmp_path, monkeypatch, capsys
):
    lifecycle = _lifecycle(tmp_path)
    monkeypatch.setattr(lifecycle, "validate", lambda: None)
    monkeypatch.setattr(
        lifecycle,
        "_remote_sha256",
        lambda _path: lifecycle_module.PATCHED_JAR_SHA256,
    )
    monkeypatch.setattr(lifecycle, "_port_open", lambda: True)
    monkeypatch.setattr(lifecycle, "service_jar_pids", lambda: {101})

    lifecycle.start()

    assert "already active" in capsys.readouterr().out


def test_start_launches_signed_server_then_activates_patch(tmp_path, monkeypatch):
    lifecycle = _lifecycle(tmp_path)
    calls = []
    monkeypatch.setattr(lifecycle, "validate", lambda: None)
    monkeypatch.setattr(
        lifecycle,
        "_remote_sha256",
        lambda _path: lifecycle_module.SIGNED_JAR_SHA256,
    )
    monkeypatch.setattr(lifecycle, "_port_open", lambda: False)
    monkeypatch.setattr(
        lifecycle, "_launch_signed_server", lambda: calls.append("launch")
    )
    monkeypatch.setattr(
        lifecycle,
        "_activate_coexistence_driver",
        lambda: calls.append("activate"),
    )

    lifecycle.start()

    assert calls == ["launch", "activate"]


def test_launch_accepts_adb_client_timeout_when_listener_is_open(
    tmp_path, monkeypatch
):
    lifecycle = _lifecycle(tmp_path, FakeTransport([(-1, "")]))
    monkeypatch.setattr(lifecycle, "_copy_atomic", lambda *_args: None)
    monkeypatch.setattr(lifecycle, "_port_open", lambda: True)

    lifecycle._launch_signed_server()


def test_launch_reports_adb_client_timeout_when_listener_stays_closed(
    tmp_path, monkeypatch
):
    lifecycle = _lifecycle(tmp_path, FakeTransport([(-1, "")]))
    monkeypatch.setattr(lifecycle, "_copy_atomic", lambda *_args: None)
    monkeypatch.setattr(lifecycle, "_port_open", lambda: False)

    with pytest.raises(lifecycle_module.LifecycleError, match="exit -1"):
        lifecycle._launch_signed_server()


def test_copy_atomic_uses_remote_temporary_and_replace(tmp_path):
    transport = FakeTransport()
    lifecycle = _lifecycle(tmp_path, transport)

    lifecycle._copy_atomic(Path("/signed.jar"), Path("/active.jar"))

    command = transport.commands[0][0]
    assert command.startswith("cp /signed.jar /.active.jar.stayturgid.tmp")
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
