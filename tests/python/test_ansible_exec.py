"""Tests for direct just-recipe Ansible execution through the site resolver."""

import ansible_exec as ae
from ansible_context import AnsibleContext


def test_ansible_exec_preserves_resolved_config_and_product_root(monkeypatch, tmp_path):
    context = AnsibleContext(
        config=tmp_path / "ansible.cfg",
        inventory=tmp_path / "inventory" / "hosts.yml",
        collections_path=tmp_path / "collections",
        source="ANSIBLE_CONFIG",
    )
    seen = {}

    monkeypatch.setattr(ae, "resolve_ansible_context", lambda repo: context)
    monkeypatch.setattr(ae, "require_inventory", lambda selected: None)

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        seen["cwd"] = kwargs["cwd"]

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(ae.subprocess, "run", fake_run)

    assert ae.main(["ansible-playbook", "ansible/playbooks/site.yml", "--syntax-check"]) == 0
    assert seen["command"] == [
        "ansible-playbook",
        "-e",
        f"stayturgid_repo_root={ae.REPO_ROOT}",
        "ansible/playbooks/site.yml",
        "--syntax-check",
    ]
    assert seen["env"]["ANSIBLE_CONFIG"] == str(context.config)
    assert seen["env"]["STAYTURGID_ROOT"] == str(ae.REPO_ROOT)
    assert seen["cwd"] == ae.REPO_ROOT
