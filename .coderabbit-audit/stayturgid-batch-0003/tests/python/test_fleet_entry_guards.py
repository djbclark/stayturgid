"""B6 regression tests: fleet entry points honor the resolved site config.

Covers Codex review H1 (agents.yml must not render into the tracked tree) and
H3 (deploy_termux/verify_drift must use the shared B4 resolver and refuse
zero-host limits).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_BIN = _ROOT / "control" / "bin"
if str(_BIN) not in sys.path:
    sys.path.insert(0, str(_BIN))

import deploy_termux as dt
import verify_drift as vd
from ansible_context import AnsibleConfigError, AnsibleContext

# ---------------------------------------------------------------------------
# H1: no tracked file is a render/copy target of agents.yml
# ---------------------------------------------------------------------------

_AGENTS_YML = _ROOT / "ansible" / "roles" / "control_node" / "tasks" / "agents.yml"


def test_agents_yml_never_renders_into_the_checkout() -> None:
    """Rendering live identity to a tracked path dirties the public repo."""
    tasks = yaml.safe_load(_AGENTS_YML.read_text(encoding="utf-8"))
    offenders = []
    for task in tasks:
        for module in ("ansible.builtin.template", "ansible.builtin.copy", "template", "copy"):
            spec = task.get(module)
            if not isinstance(spec, dict):
                continue
            dest = str(spec.get("dest", ""))
            if "stayturgid_repo_root" in dest or "playbook_dir" in dest:
                offenders.append(f"{task.get('name')}: {dest}")
    assert offenders == [], f"agents.yml renders into the repo checkout: {offenders}"


# ---------------------------------------------------------------------------
# H3: shared resolver + zero-host guard in deploy_termux / verify_drift
# ---------------------------------------------------------------------------


def _write_site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "inventory").mkdir(parents=True)
    config = site / "ansible.cfg"
    config.write_text("[defaults]\ninventory = inventory/hosts.yml\n", encoding="utf-8")
    (site / "inventory" / "hosts.yml").write_text(
        "all:\n  children:\n    stayturgid:\n      hosts:\n        oneui-device:\n",
        encoding="utf-8",
    )
    return config


def _fake_context(config: Path) -> AnsibleContext:
    return AnsibleContext(
        config=config,
        inventory=config.parent / "inventory" / "hosts.yml",
        collections_path=config.parent / "collections",
        source="ANSIBLE_CONFIG",
    )


def test_verify_drift_honors_explicit_config(tmp_path, monkeypatch) -> None:
    """Review scenario: an exported site config must reach ansible-playbook."""
    config = _write_site(tmp_path)
    monkeypatch.setenv("ANSIBLE_CONFIG", str(config))
    monkeypatch.setattr(vd, "require_limit_hosts", lambda ctx, limit: ["oneui-device"])
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs.get("env", {})
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(vd.subprocess, "run", fake_run)
    assert vd.main(["--host", "oneui-device"]) == 0
    assert seen["env"]["ANSIBLE_CONFIG"] == str(config)
    assert "-l" in seen["cmd"] and "oneui-device" in seen["cmd"]


def test_verify_drift_zero_hosts_exits_nonzero(tmp_path, monkeypatch, capsys) -> None:
    config = _write_site(tmp_path)
    monkeypatch.setenv("ANSIBLE_CONFIG", str(config))

    def raise_zero(ctx, limit):
        raise AnsibleConfigError(f"Limit '{limit}' matches zero hosts in config {ctx.config}")

    monkeypatch.setattr(vd, "require_limit_hosts", raise_zero)
    monkeypatch.setattr(vd.subprocess, "run", lambda *a, **k: pytest.fail("playbook must not run"))
    assert vd.main(["--host", "no-such-host"]) == 2
    assert str(config) in capsys.readouterr().err


def test_deploy_termux_zero_hosts_raises_before_ssh(tmp_path, monkeypatch) -> None:
    config = _write_site(tmp_path)
    monkeypatch.setenv("ANSIBLE_CONFIG", str(config))

    def raise_zero(ctx, limit):
        raise AnsibleConfigError(f"Limit '{limit}' matches zero hosts in config {ctx.config}")

    monkeypatch.setattr(dt, "require_limit_hosts", raise_zero)
    monkeypatch.setattr(dt.shutil, "which", lambda _name: "/usr/bin/ansible-playbook")
    monkeypatch.setattr(dt, "verify_ssh", lambda _t: pytest.fail("guard must run before SSH"))
    with pytest.raises(AnsibleConfigError, match=str(config)):
        dt.main(["no-such-host"])


def test_deploy_termux_uses_resolved_context(tmp_path, monkeypatch) -> None:
    """H3 regression: no hardcoded upstream ANSIBLE_CONFIG override."""
    config = _write_site(tmp_path)
    monkeypatch.setenv("ANSIBLE_CONFIG", str(config))
    monkeypatch.setattr(dt, "require_limit_hosts", lambda ctx, limit: ["oneui-device"])
    monkeypatch.setattr(dt.shutil, "which", lambda _name: "/usr/bin/ansible-playbook")
    monkeypatch.setattr(dt, "ssh_target", lambda h: h)
    monkeypatch.setattr(dt, "verify_ssh", lambda _t: True)
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    assert dt.main(["oneui-device"]) == 0
    playbook_calls = [(c, k) for c, k in seen if c and c[0] == "ansible-playbook"]
    assert playbook_calls, "ansible-playbook was not invoked"
    _, kwargs = playbook_calls[0]
    assert kwargs["env"]["ANSIBLE_CONFIG"] == str(config)
