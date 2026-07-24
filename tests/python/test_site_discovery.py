"""Shared site-discovery contract tests for issue #48."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control.landing import discover as landing_discover
from control.lib import site_discovery as sd


def _site(ops: Path, name: str, *, ansible: bool = False) -> Path:
    path = ops / name
    path.mkdir(parents=True)
    if ansible:
        (path / "ansible.cfg").write_text("[defaults]\ninventory=inventory/hosts.yml\n", encoding="utf-8")
    return path


def test_missing_private_companion_is_created_owner_only(tmp_path: Path) -> None:
    ops = tmp_path / "ops"

    path = sd.ensure_private_companion({"OPS_ROOT": str(ops)})

    assert path == ops / "site-private"
    assert path.is_dir()
    assert stat.S_IMODE(path.stat().st_mode) == 0o700


def test_private_companion_path_is_configurable_and_excluded(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    site = _site(ops, "site-example")
    private = _site(ops, "site-notes")
    env = {
        "OPS_ROOT": str(ops),
        "STAYTURGID_PRIVATE_DIR": "site-notes",
    }

    selection = sd.resolve_site_selection(env)

    assert selection.path == site
    assert private.is_dir()


def test_literal_site_private_is_excluded_even_with_ansible_config(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    _site(ops, "site-private", ansible=True)
    site = _site(ops, "site-example", ansible=True)

    selection = sd.resolve_site_selection({"OPS_ROOT": str(ops)}, require_ansible_config=True)

    assert selection.path == site
    assert selection.source == "site-* discovery"


@pytest.mark.parametrize("as_symlink", [False, True])
def test_mysite_wins_over_site_glob(tmp_path: Path, as_symlink: bool) -> None:
    ops = tmp_path / "ops"
    selected = _site(ops, "chosen", ansible=True)
    _site(ops, "site-other", ansible=True)
    mysite = ops / ".mysite"
    if as_symlink:
        mysite.symlink_to(selected, target_is_directory=True)
    else:
        mysite.mkdir()
        (mysite / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        selected = mysite

    selection = sd.resolve_site_selection({"OPS_ROOT": str(ops)}, require_ansible_config=True)

    assert selection.path == selected.resolve()
    assert selection.source == "OPS_ROOT/.mysite"


def test_mysite_cannot_select_private_companion(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    private = _site(ops, "site-private")
    (ops / ".mysite").symlink_to(private, target_is_directory=True)

    with pytest.raises(sd.SiteDiscoveryError, match="reserved for the private companion"):
        sd.resolve_site_selection({"OPS_ROOT": str(ops)})


def test_broken_mysite_fails_with_actionable_error(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / ".mysite").symlink_to(ops / "missing", target_is_directory=True)
    _site(ops, "site-example")

    with pytest.raises(sd.SiteDiscoveryError, match="Fix or remove .mysite"):
        sd.resolve_site_selection({"OPS_ROOT": str(ops)})


def test_zero_sites_still_bootstraps_private_companion(tmp_path: Path) -> None:
    ops = tmp_path / "ops"

    with pytest.raises(sd.SiteDiscoveryError, match="No site overlay found"):
        sd.resolve_site_selection({"OPS_ROOT": str(ops)})

    assert (ops / "site-private").is_dir()


def test_announcement_names_path_and_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = _site(tmp_path / "ops", "site-example")
    selection = sd.SiteSelection(path=site, source="site-* discovery")

    sd.announce_site_selection(selection, command="test-command")

    error = capsys.readouterr().err
    assert f"test-command: site directory {site}" in error
    assert "source: site-* discovery" in error


def test_landing_resolver_honors_explicit_site_before_mysite(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    explicit = _site(ops, "explicit")
    _site(ops, ".mysite")

    selection = landing_discover._resolve_site(
        {
            "OPS_ROOT": str(ops),
            "STAYTURGID_SITE_DIR": str(explicit),
        }
    )

    assert selection.path == explicit
    assert selection.source == "STAYTURGID_SITE_DIR"


def test_landing_resolver_rejects_missing_explicit_ansible_config(tmp_path: Path) -> None:
    with pytest.raises(sd.SiteDiscoveryError, match="ANSIBLE_CONFIG points to a missing file"):
        landing_discover._resolve_site(
            {
                "OPS_ROOT": str(tmp_path / "ops"),
                "ANSIBLE_CONFIG": str(tmp_path / "missing.cfg"),
            }
        )
