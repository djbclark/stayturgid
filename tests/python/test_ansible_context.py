"""Configuration precedence tests for the product/site Ansible boundary."""

from pathlib import Path

import ansible_context as ac
import pytest


def write_config(root: Path, inventory: str = "inventory/hosts.yml") -> Path:
    config = root / "ansible.cfg"
    config.write_text(
        f"[defaults]\ninventory = {inventory}\ncollections_path = collections:product-collections\n",
        encoding="utf-8",
    )
    return config


def test_explicit_ansible_config_wins_over_site_overlay(tmp_path):
    repo = tmp_path / "product"
    (repo / "ansible").mkdir(parents=True)
    write_config(repo / "ansible")
    site = tmp_path / "site"
    site.mkdir()
    write_config(site)
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    config = write_config(explicit, "inventory/live.yml")
    (explicit / "inventory").mkdir()
    (explicit / "inventory" / "live.yml").write_text("all: {}\n", encoding="utf-8")

    context = ac.resolve_ansible_context(
        repo,
        {"ANSIBLE_CONFIG": str(config), "STAYTURGID_SITE_DIR": str(site)},
    )

    assert context.source == "ANSIBLE_CONFIG"
    assert context.config == config
    assert context.inventory == explicit / "inventory" / "live.yml"
    assert context.collections_path == explicit / "collections"


def test_site_overlay_is_selected_when_no_config_is_supplied(tmp_path):
    repo = tmp_path / "product"
    (repo / "ansible").mkdir(parents=True)
    write_config(repo / "ansible")
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    context = ac.resolve_ansible_context(repo, {"STAYTURGID_SITE_DIR": str(site)})

    assert context.source == "site overlay"
    assert context.config == config
    ac.require_inventory(context)


def test_upstream_fallback_explains_missing_live_inventory(tmp_path):
    repo = tmp_path / "product"
    (repo / "ansible").mkdir(parents=True)
    config = write_config(repo / "ansible")

    context = ac.resolve_ansible_context(repo, {"STAYTURGID_SITE_DIR": str(tmp_path / "missing-site")})

    assert context.source == "upstream fallback"
    assert context.config == config
    with pytest.raises(ac.AnsibleConfigError, match="Live deploys require a site overlay"):
        ac.require_inventory(context)


def test_missing_explicit_config_has_actionable_error(tmp_path):
    with pytest.raises(ac.AnsibleConfigError, match="ANSIBLE_CONFIG points to a missing file"):
        ac.resolve_ansible_context(tmp_path, {"ANSIBLE_CONFIG": str(tmp_path / "missing.cfg")})
