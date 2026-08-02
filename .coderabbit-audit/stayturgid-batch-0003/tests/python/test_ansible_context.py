"""Configuration precedence tests for the product/site Ansible boundary.

Resolution rule (multi-site-topology.md §4.8): explicit ``ANSIBLE_CONFIG``
wins; else explicit ``STAYTURGID_SITE_DIR``; else ``OPS_ROOT/.mysite``; else
exactly one discovered ``site-*`` checkout excluding ``site-private``.
"""

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


def make_site(root: Path, name: str = "site-example") -> Path:
    site = root / name
    site.mkdir(parents=True)
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")
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


def test_multiple_inventory_sources_preserve_precedence_and_validate(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site, "generated/inventory,inventory/hosts.yml")
    (site / "generated" / "inventory").mkdir(parents=True)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    context = ac.resolve_ansible_context(tmp_path, {"ANSIBLE_CONFIG": str(config)})

    assert context.inventories == (
        site / "generated" / "inventory",
        site / "inventory" / "hosts.yml",
    )
    assert context.inventory == site / "inventory" / "hosts.yml"
    assert context.inventory_args() == [
        "-i",
        str(site / "generated" / "inventory"),
        "-i",
        str(site / "inventory" / "hosts.yml"),
    ]
    ac.require_inventory(context)


def test_multiple_inventory_sources_fail_when_any_source_is_missing(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site, "generated/inventory,inventory/hosts.yml")
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    context = ac.resolve_ansible_context(tmp_path, {"ANSIBLE_CONFIG": str(config)})

    with pytest.raises(ac.AnsibleConfigError, match="generated/inventory"):
        ac.require_inventory(context)


def test_site_dir_is_selected_when_no_config_is_supplied(tmp_path):
    repo = tmp_path / "product"
    (repo / "ansible").mkdir(parents=True)
    write_config(repo / "ansible")
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    context = ac.resolve_ansible_context(repo, {"STAYTURGID_SITE_DIR": str(site)})

    assert context.source == "STAYTURGID_SITE_DIR"
    assert context.config == config
    ac.require_inventory(context)


def test_explicit_site_dir_without_config_fails(tmp_path):
    """An explicitly selected site dir must not silently fall back anywhere."""
    repo = tmp_path / "product"
    (repo / "ansible").mkdir(parents=True)
    write_config(repo / "ansible")

    with pytest.raises(ac.AnsibleConfigError, match="STAYTURGID_SITE_DIR"):
        ac.resolve_ansible_context(repo, {"STAYTURGID_SITE_DIR": str(tmp_path / "missing-site")})


def test_single_site_checkout_is_discovered_under_ops_root(tmp_path):
    repo = tmp_path / "ops" / "product"
    (repo / "ansible").mkdir(parents=True)
    write_config(repo / "ansible")
    config = make_site(tmp_path / "ops", "site-example")

    context = ac.resolve_ansible_context(repo, {"OPS_ROOT": str(tmp_path / "ops")})

    assert context.source == "site-* discovery"
    assert context.config == config
    ac.require_inventory(context)


def test_zero_discovered_sites_fails_with_instructions(tmp_path):
    """No silent default: an empty OPS_ROOT names the knobs to set."""
    repo = tmp_path / "ops" / "product"
    (repo / "ansible").mkdir(parents=True)
    write_config(repo / "ansible")

    with pytest.raises(ac.AnsibleConfigError, match="ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite"):
        ac.resolve_ansible_context(repo, {"OPS_ROOT": str(tmp_path / "ops")})
    assert (tmp_path / "ops" / "site-private").is_dir()


def test_multiple_discovered_sites_fail_with_instructions(tmp_path):
    repo = tmp_path / "ops" / "product"
    (repo / "ansible").mkdir(parents=True)
    write_config(repo / "ansible")
    make_site(tmp_path / "ops", "site-alpha")
    make_site(tmp_path / "ops", "site-beta")

    with pytest.raises(ac.AnsibleConfigError, match="Ambiguous site overlay"):
        ac.resolve_ansible_context(repo, {"OPS_ROOT": str(tmp_path / "ops")})


def test_explicit_private_companion_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    site = tmp_path / "ops" / "site-private"
    site.mkdir(parents=True)
    write_config(site)

    with pytest.raises(ac.AnsibleConfigError, match="reserved for the private companion"):
        ac.resolve_ansible_context(
            repo,
            {
                "OPS_ROOT": str(tmp_path / "ops"),
                "STAYTURGID_SITE_DIR": str(site),
            },
        )


def test_no_operator_specific_default_in_module_source():
    """Gemini #2 regression: the public product hardcodes no site checkout name."""
    source = Path(ac.__file__).read_text(encoding="utf-8")
    assert "site-djbclark" not in source


def test_missing_explicit_config_has_actionable_error(tmp_path):
    with pytest.raises(ac.AnsibleConfigError, match="ANSIBLE_CONFIG points to a missing file"):
        ac.resolve_ansible_context(tmp_path, {"ANSIBLE_CONFIG": str(tmp_path / "missing.cfg")})


def test_inventory_containing_only_separators_has_actionable_error(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site, " , , ")

    with pytest.raises(ac.AnsibleConfigError, match=r"no \[defaults\] inventory"):
        ac.resolve_ansible_context(tmp_path, {"ANSIBLE_CONFIG": str(config)})


# ---------------------------------------------------------------------------
# Zero-host guard (H3)
# ---------------------------------------------------------------------------


def _context_for(tmp_path: Path) -> ac.AnsibleContext:
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text(
        "all:\n  children:\n    stayturgid:\n      hosts:\n        oneui-device:\n",
        encoding="utf-8",
    )
    return ac.resolve_ansible_context(tmp_path, {"ANSIBLE_CONFIG": str(config)})


def test_require_limit_hosts_returns_matches(tmp_path, monkeypatch):
    context = _context_for(tmp_path)

    class R:
        returncode = 0
        stdout = "  hosts (1):\n    oneui-device\n"
        stderr = ""

    monkeypatch.setattr(ac.subprocess, "run", lambda *a, **k: R())
    assert ac.require_limit_hosts(context, "oneui-device") == ["oneui-device"]


def test_require_limit_hosts_zero_matches_names_config(tmp_path, monkeypatch):
    """A limit matching no hosts must fail and name the config that was used."""
    context = _context_for(tmp_path)

    class R:
        returncode = 0
        stdout = "  hosts (0):\n"
        stderr = ""

    monkeypatch.setattr(ac.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(ac.AnsibleConfigError, match=str(context.config)):
        ac.require_limit_hosts(context, "no-such-host")


def test_resolved_env_pins_selected_config(tmp_path):
    """H3 regression: entry points must honor the caller's explicit config."""
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    env = ac.resolved_env(tmp_path, {"ANSIBLE_CONFIG": str(config)})

    assert env["ANSIBLE_CONFIG"] == str(config)
    assert env["STAYTURGID_ROOT"] == str(tmp_path)
    assert env["ANSIBLE_ROLES_PATH"] == str(tmp_path / "ansible" / "roles")
    assert env["ANSIBLE_COLLECTIONS_PATH"] == (f"{tmp_path / '.ansible' / 'collections'}:{tmp_path}")


def test_resolved_env_preserves_additional_ansible_search_paths(tmp_path):
    """Product paths are authoritative without hiding caller-owned extensions."""
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    env = ac.resolved_env(
        tmp_path,
        {
            "ANSIBLE_CONFIG": str(config),
            "ANSIBLE_ROLES_PATH": "/site/roles",
            "ANSIBLE_COLLECTIONS_PATH": "/site/collections",
        },
    )

    assert env["ANSIBLE_ROLES_PATH"] == f"{tmp_path / 'ansible' / 'roles'}:/site/roles"
    assert env["ANSIBLE_COLLECTIONS_PATH"] == (f"{tmp_path / '.ansible' / 'collections'}:{tmp_path}:/site/collections")


def test_resolved_env_enables_profile_tasks_callback(tmp_path):
    """#57: real per-task timing must be on regardless of the selected site config."""
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    env = ac.resolved_env(tmp_path, {"ANSIBLE_CONFIG": str(config)})

    assert env["ANSIBLE_CALLBACKS_ENABLED"] == "ansible.posix.profile_tasks"


def test_resolved_env_preserves_additional_callbacks(tmp_path):
    """A caller-configured callback list keeps its entries alongside profile_tasks."""
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    env = ac.resolved_env(
        tmp_path,
        {"ANSIBLE_CONFIG": str(config), "ANSIBLE_CALLBACKS_ENABLED": "community.general.diy"},
    )

    assert env["ANSIBLE_CALLBACKS_ENABLED"] == "ansible.posix.profile_tasks,community.general.diy"


def test_resolved_env_does_not_duplicate_profile_tasks(tmp_path):
    """If a site already enables profile_tasks explicitly, don't list it twice."""
    site = tmp_path / "site"
    site.mkdir()
    config = write_config(site)
    (site / "inventory").mkdir()
    (site / "inventory" / "hosts.yml").write_text("all: {}\n", encoding="utf-8")

    env = ac.resolved_env(
        tmp_path,
        {"ANSIBLE_CONFIG": str(config), "ANSIBLE_CALLBACKS_ENABLED": "ansible.posix.profile_tasks"},
    )

    assert env["ANSIBLE_CALLBACKS_ENABLED"] == "ansible.posix.profile_tasks"
