"""Tests for the sole public managed SecretSpec client."""

from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

PATH = Path(__file__).parents[2] / "control/bin/sudo-secretspec"
LOADER = SourceFileLoader("sudo_secretspec_client", str(PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
client = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(client)


def test_parser_has_no_manifest_provider_profile_or_direct_options():
    help_text = client.parser().format_help()
    for forbidden in ("--file", "--provider", "--profile", "SUDO_SECRETSPEC_DIRECT"):
        assert forbidden not in help_text


def test_get_builds_fixed_broker_command(monkeypatch):
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setattr(client, "client_family", lambda: "hermes")
    monkeypatch.setattr(client.subprocess, "run", lambda command: calls.append(command) or Result())
    rc = client.main(["--reason", "test read", "get", "EXAMPLE_KEY"])
    assert rc == 0
    assert calls == [
        [
            "sudo",
            "-n",
            client.WRAPPER,
            "source-get",
            "--client",
            "hermes",
            "--reason",
            "test read",
            "--name",
            "EXAMPLE_KEY",
        ]
    ]


def test_reason_is_freeform_before_or_after_operation(monkeypatch):
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setattr(client, "client_family", lambda: "hermes")
    monkeypatch.setattr(client.subprocess, "run", lambda command: calls.append(command) or Result())
    assert client.main(["get", "EXAMPLE_KEY", "--reason", "after form"]) == 0
    assert calls[0][calls[0].index("--reason") + 1] == "after form"


def test_invalid_name_and_missing_reason_fail_before_subprocess(monkeypatch):
    monkeypatch.setattr(client.subprocess, "run", lambda *_: pytest.fail("must not execute"))
    with pytest.raises(SystemExit):
        client.main(["get", "EXAMPLE_KEY"])
    with pytest.raises(SystemExit):
        client.main(["--reason", "test", "get", "bad-name"])


def test_run_rejects_missing_command(monkeypatch):
    monkeypatch.setattr(client.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("must not execute"))
    with pytest.raises(SystemExit, match="run requires"):
        client.main(["--reason", "test", "run"])


def test_run_rejects_invalid_json_and_never_uses_shell(monkeypatch):
    class Result:
        returncode = 0
        stdout = "not-json"
        stderr = ""

    seen = []
    monkeypatch.setattr(client.subprocess, "run", lambda command, **kwargs: seen.append((command, kwargs)) or Result())
    with pytest.raises(SystemExit, match="invalid JSON"):
        client.main(["--reason", "test", "run", "--", "/usr/bin/true"])
    assert seen[0][1] == {"capture_output": True, "text": True}
    assert "--command-basename" in seen[0][0]
    assert seen[0][0][seen[0][0].index("--command-basename") + 1] == "true"


def test_client_family_never_persists_session_metadata(monkeypatch):
    monkeypatch.setenv("HERMES_SESSION_ID", "x" * 200)
    assert client.client_family() == "hermes"
    monkeypatch.delenv("HERMES_SESSION_ID")
    assert client.client_family() == "unknown"
