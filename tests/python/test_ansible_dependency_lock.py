"""The normal-deploy Ansible dependencies must be immutable."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_ansible_collection_dependencies_are_exactly_versioned():
    requirements = yaml.safe_load((ROOT / "ansible/requirements.yml").read_text(encoding="utf-8"))

    versions = {item["name"]: item["version"] for item in requirements["collections"]}
    assert versions == {
        "ansible.posix": "2.2.2",
        "community.general": "13.2.0",
    }
    assert all(not any(operator in version for operator in "<>=~") for version in versions.values())
