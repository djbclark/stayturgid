"""Offline-target behavior for the CFEngine SSH entry point."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "control" / "bin" / "cf_run.py"
SPEC = importlib.util.spec_from_file_location("cf_run", MODULE_PATH)
cf_run = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(cf_run)


def test_dry_run_uses_shared_eligible_targets(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cf_run, "resolve_hosts", lambda hosts, **_kwargs: ["s24", "hd8"])

    assert cf_run.main(["--dry-run"]) == 0
    assert capsys.readouterr().out.strip() == "cf-run targets: s24, hd8"


def test_explicit_host_is_passed_as_override(monkeypatch, capsys) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(cf_run, "resolve_hosts", lambda hosts, **_kwargs: calls.append(hosts) or hosts)

    assert cf_run.main(["p7a", "--dry-run"]) == 0
    assert calls == [["p7a"]]
    assert capsys.readouterr().out.strip() == "cf-run targets: p7a"
