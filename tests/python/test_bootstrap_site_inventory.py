"""#330: the fallback bootstrap playbook runs against the resolved site overlay.

``run_bootstrap_playbook`` used to default to the product's own
``ansible/ansible.cfg`` (inventory ``hosts.yml`` exists only as ``.example``),
so ``deploy_termux.py`` / ``bootstrap_ssh.py --ansible`` matched no host.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _sub in ("control/lib", "control/bin"):
    if str(_ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(_ROOT / _sub))

import bootstrap_ssh as bs
import deploy_termux as dt
import termux_ssh_bootstrap as boot
from ansible_context import AnsibleConfigError, AnsibleContext


def _site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "inventory").mkdir(parents=True)
    config = site / "ansible.cfg"
    config.write_text(
        "[defaults]\ninventory = inventory/hosts.yml\ncollections_path = site-collections\n",
        encoding="utf-8",
    )
    (site / "inventory" / "hosts.yml").write_text(
        "all:\n  hosts:\n    oneui-device:\n",
        encoding="utf-8",
    )
    return config


def _context(config: Path) -> AnsibleContext:
    return AnsibleContext(
        config=config,
        inventory=config.parent / "inventory" / "hosts.yml",
        collections_path=config.parent / "site-collections",
        source="ANSIBLE_CONFIG",
    )


@pytest.fixture
def recorded(monkeypatch):
    calls: list[tuple[list[str], dict]] = []

    def fake_run(cmd, **kwargs):
        calls.append((list(cmd), kwargs))
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(boot.subprocess, "run", fake_run)
    monkeypatch.setattr(boot, "secretspec_run", lambda *argv: list(argv))
    monkeypatch.setattr(boot, "require_limit_hosts", lambda ctx, limit: [limit])
    return calls


def _playbook_call(calls):
    found = [(c, k) for c, k in calls if c and c[0] == "ansible-playbook"]
    assert len(found) == 1
    return found[0]


def test_passed_context_pins_playbook_env_and_collections(tmp_path, recorded) -> None:
    config = _site(tmp_path)
    context = _context(config)
    assert boot.run_bootstrap_playbook(_ROOT, ["oneui-device"], context=context) == 0
    cmd, kwargs = _playbook_call(recorded)
    assert kwargs["env"]["ANSIBLE_CONFIG"] == str(config)
    assert kwargs["env"]["ANSIBLE_CONFIG"] != str(_ROOT / "ansible" / "ansible.cfg")
    assert cmd[-2:] == ["--limit", "oneui-device"]
    galaxy = next(c for c, _ in recorded if c[0] == "ansible-galaxy")
    assert galaxy[galaxy.index("-p") + 1] == str(context.collections_path)


def test_without_context_resolves_site_from_environment(tmp_path, monkeypatch, recorded) -> None:
    config = _site(tmp_path)
    monkeypatch.setenv("ANSIBLE_CONFIG", str(config))
    assert boot.run_bootstrap_playbook(_ROOT, ["oneui-device"]) == 0
    _, kwargs = _playbook_call(recorded)
    assert kwargs["env"]["ANSIBLE_CONFIG"] == str(config.resolve())
    galaxy = next(c for c, _ in recorded if c[0] == "ansible-galaxy")
    assert galaxy[galaxy.index("-p") + 1] == str((config.parent / "site-collections").resolve())


def test_unresolvable_site_raises_before_any_subprocess(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANSIBLE_CONFIG", str(tmp_path / "missing.cfg"))
    monkeypatch.setattr(boot.subprocess, "run", lambda *a, **k: pytest.fail("nothing may run blind"))
    with pytest.raises(AnsibleConfigError, match="missing"):
        boot.run_bootstrap_playbook(_ROOT, ["oneui-device"])


def test_zero_host_limit_raises_before_any_subprocess(tmp_path, monkeypatch) -> None:
    context = _context(_site(tmp_path))

    def zero(ctx, limit):
        raise AnsibleConfigError(f"Limit '{limit}' matches zero hosts")

    monkeypatch.setattr(boot, "require_limit_hosts", zero)
    monkeypatch.setattr(boot.subprocess, "run", lambda *a, **k: pytest.fail("nothing may run on zero hosts"))
    with pytest.raises(AnsibleConfigError, match="zero hosts"):
        boot.run_bootstrap_playbook(_ROOT, ["no-such-host"], context=context)


def test_bootstrap_ssh_ansible_passes_resolved_context(tmp_path, monkeypatch) -> None:
    config = _site(tmp_path)
    monkeypatch.setenv("ANSIBLE_CONFIG", str(config))
    seen = {}

    def fake_playbook(repo_root, hosts, **kwargs):
        seen["kwargs"] = kwargs
        return 0

    monkeypatch.setattr(bs.boot, "run_bootstrap_playbook", fake_playbook)
    assert bs.main(["--ansible", "--no-tailscale-verify", "oneui-device"]) == 0
    assert seen["kwargs"]["context"].config == config.resolve()


def test_bootstrap_ssh_ansible_bad_site_exits_2(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ANSIBLE_CONFIG", str(tmp_path / "missing.cfg"))
    monkeypatch.setattr(bs.boot, "run_bootstrap_playbook", lambda *a, **k: pytest.fail("must not run"))
    assert bs.main(["--ansible", "oneui-device"]) == 2
    assert "missing.cfg" in capsys.readouterr().err


def test_deploy_termux_bootstrap_fallback_passes_resolved_context(tmp_path, monkeypatch) -> None:
    config = _site(tmp_path)
    monkeypatch.setenv("ANSIBLE_CONFIG", str(config))
    monkeypatch.setattr(dt, "require_limit_hosts", lambda ctx, limit: ["oneui-device"])
    monkeypatch.setattr(dt, "require_fresh_checkout", lambda root, *a, **k: None)
    monkeypatch.setattr(dt.shutil, "which", lambda _name: "/usr/bin/x")
    monkeypatch.setattr(dt, "ssh_target", lambda h: h)
    reachable = iter([False, True])
    monkeypatch.setattr(dt, "verify_ssh", lambda _t: next(reachable))
    seen = {}

    def fake_playbook(repo_root, hosts, **kwargs):
        seen["hosts"] = hosts
        seen["context"] = kwargs.get("context")
        return 0

    monkeypatch.setattr(dt.boot, "run_bootstrap_playbook", fake_playbook)
    monkeypatch.setattr(dt.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    assert dt.main(["oneui-device"]) == 0
    assert seen["hosts"] == ["oneui-device"]
    assert seen["context"] is not None
    assert seen["context"].config == config.resolve()
