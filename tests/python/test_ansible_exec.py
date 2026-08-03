"""Tests for direct just-recipe Ansible execution through the site resolver."""

import ansible_exec as ae
from ansible_context import AnsibleContext


def test_ansible_exec_delegates_env_to_resolved_env(monkeypatch, tmp_path):
    context = AnsibleContext(
        config=tmp_path / "ansible.cfg",
        inventory=tmp_path / "inventory" / "hosts.yml",
        collections_path=tmp_path / "collections",
        source="ANSIBLE_CONFIG",
    )
    # Regression (stayturgid#85): ansible_exec must build the subprocess env via
    # resolved_env(), which pins ANSIBLE_ROLES_PATH/ANSIBLE_COLLECTIONS_PATH to
    # this checkout. resolved_env()'s composition is covered in
    # test_ansible_context.py; here we only assert the delegation. Previously
    # ansible_exec set ANSIBLE_CONFIG alone, so a site overlay whose ansible.cfg
    # omits product paths failed with "role 'control_node' was not found".
    fake_env = {
        "ANSIBLE_CONFIG": str(context.config),
        "STAYTURGID_ROOT": str(ae.REPO_ROOT),
        "ANSIBLE_ROLES_PATH": f"{ae.REPO_ROOT / 'ansible' / 'roles'}",
        "ANSIBLE_COLLECTIONS_PATH": f"{ae.REPO_ROOT / '.ansible' / 'collections'}:{ae.REPO_ROOT}",
    }
    seen = {}

    monkeypatch.setattr(ae, "resolve_ansible_context", lambda repo, *a, **k: context)
    monkeypatch.setattr(ae, "require_inventory", lambda selected: None)
    monkeypatch.setattr(ae, "require_fresh_checkout", lambda repo, *a, **k: None)
    monkeypatch.setattr(ae, "resolved_env", lambda repo: dict(fake_env))

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
    assert seen["env"] == fake_env
    assert seen["cwd"] == ae.REPO_ROOT
