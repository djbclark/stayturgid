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


@pytest.mark.parametrize(
    ("name", "reserved"),
    [
        ("site-private", True),
        ("site-private-", True),
        ("site-private-dann", True),
        ("site-public-a", False),
        ("site-a", False),
        ("site-privately", False),
    ],
)
def test_reserved_private_name_predicate(name: str, reserved: bool) -> None:
    assert sd.is_reserved_private_name(name) is reserved


@pytest.mark.parametrize("private_name", ["site-private-dann", "site-private-"])
def test_prefixed_private_companion_is_excluded(tmp_path: Path, private_name: str) -> None:
    ops = tmp_path / "ops"
    _site(ops, private_name, ansible=True)
    site = _site(ops, "site-public-a", ansible=True)

    selection = sd.resolve_site_selection({"OPS_ROOT": str(ops)}, require_ansible_config=True)

    assert selection.path == site


@pytest.mark.parametrize("private_name", ["site-private-y", "site-private-"])
def test_only_prefixed_private_companion_finds_no_overlay(tmp_path: Path, private_name: str) -> None:
    ops = tmp_path / "ops"
    _site(ops, private_name)

    with pytest.raises(sd.SiteDiscoveryError, match="No site overlay found") as error:
        sd.resolve_site_selection({"OPS_ROOT": str(ops)})

    assert "site-private* is reserved for private companions" in str(error.value)
    assert "site-public-<operator>" in str(error.value)
    assert "ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite" in str(error.value)


@pytest.mark.parametrize("via_alias", [False, True])
def test_mysite_cannot_select_prefixed_private_companion(tmp_path: Path, via_alias: bool) -> None:
    ops = tmp_path / "ops"
    private = _site(ops, "site-private-y")
    selected = private
    if via_alias:
        selected = ops / "site-foo"
        selected.symlink_to(private, target_is_directory=True)
    (ops / ".mysite").symlink_to(selected, target_is_directory=True)

    with pytest.raises(sd.SiteDiscoveryError, match="reserved for private companions"):
        sd.resolve_site_selection({"OPS_ROOT": str(ops)})


def test_alias_to_prefixed_private_companion_is_excluded(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    private = _site(ops, "site-private-y")
    (ops / "site-foo").symlink_to(private, target_is_directory=True)
    site = _site(ops, "site-public-a")

    selection = sd.resolve_site_selection({"OPS_ROOT": str(ops)})

    assert selection.path == site


def test_reserved_alias_to_public_overlay_is_excluded(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    site = _site(ops, "site-public-a")
    (ops / "site-private-alias").symlink_to(site, target_is_directory=True)

    selection = sd.resolve_site_selection({"OPS_ROOT": str(ops)})

    assert selection.path == site


def test_public_and_legacy_overlays_remain_ambiguous(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    public = _site(ops, "site-public-a")
    legacy = _site(ops, "site-a")

    with pytest.raises(sd.SiteDiscoveryError, match="Ambiguous site overlay") as error:
        sd.resolve_site_selection({"OPS_ROOT": str(ops)})

    assert str(public) in str(error.value)
    assert str(legacy) in str(error.value)
    assert "site-private* is reserved for private companions" in str(error.value)
    assert "site-public-<operator>" in str(error.value)
    assert "ANSIBLE_CONFIG, STAYTURGID_SITE_DIR, or OPS_ROOT/.mysite" in str(error.value)


@pytest.mark.parametrize("configured_name", ["site-z", "site-private-a", "site-private-b"])
def test_two_private_companions_and_configured_path_are_excluded(tmp_path: Path, configured_name: str) -> None:
    ops = tmp_path / "ops"
    _site(ops, "site-private-a")
    _site(ops, "site-private-b")
    if configured_name == "site-z":
        _site(ops, configured_name)
    site = _site(ops, "site-public-a")

    selection = sd.resolve_site_selection({"OPS_ROOT": str(ops), "STAYTURGID_PRIVATE_DIR": configured_name})

    assert selection.path == site


def test_explicit_alias_to_prefixed_private_companion_is_rejected(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    private = _site(ops, "site-private-y")
    alias = ops / "site-foo"
    alias.symlink_to(private, target_is_directory=True)

    with pytest.raises(sd.SiteDiscoveryError, match="reserved for private companions"):
        sd.reject_private_companion_overlay(alias, {"OPS_ROOT": str(ops)})


def test_explicit_configured_private_companion_is_rejected(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    private = _site(ops, "site-z")

    with pytest.raises(sd.SiteDiscoveryError, match="reserved for the private companion"):
        sd.reject_private_companion_overlay(private, {"OPS_ROOT": str(ops), "STAYTURGID_PRIVATE_DIR": "site-z"})


# ---------------------------------------------------------------------------
# Stage 0 dual-read (frdminc/tendcf#98): ~/tendcf-ops + deterministic pairing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "reserved"),
    [
        ("tendcf-private", True),
        ("tendcf-private-", True),
        ("tendcf-private-alice", True),
        ("tendcf-public-alice", False),
        ("tendcf-privately", False),
    ],
)
def test_tendcf_reserved_private_names(name: str, reserved: bool) -> None:
    assert sd.is_reserved_private_name(name) is reserved


@pytest.mark.parametrize(
    "bad_slug",
    [
        "",
        "Alice",
        "alice_lab",
        "-alice",
        "alice-",
        "alice--lab",
        "alice-wt",
        "../alice",
        "alice\n",
        "a" * 65,
    ],
)
def test_validate_site_slug_rejects_invalid_values(bad_slug: str) -> None:
    with pytest.raises(sd.SiteDiscoveryError):
        sd.validate_site_slug(bad_slug)


def test_tendcf_ops_root_with_tendcf_site_resolves_deterministic_pair(tmp_path: Path) -> None:
    tendcf_ops = tmp_path / "tendcf-ops"
    pub = _site(tendcf_ops, "tendcf-public-alice", ansible=True)
    _site(tendcf_ops, "tendcf-public-bob", ansible=True)
    priv = _site(tendcf_ops, "tendcf-private-alice")

    selection = sd.resolve_site_selection(
        {"TENDCF_OPS_ROOT": str(tendcf_ops), "TENDCF_SITE": "alice"},
        require_ansible_config=True,
    )

    assert selection.path == pub.resolve()
    assert selection.source == "TENDCF_SITE"
    assert selection.slug == "alice"
    assert selection.private_dir == priv.resolve()
    assert not (tendcf_ops / "site-private").exists()


def test_tendcf_ops_root_creates_paired_private_never_legacy_site_private(tmp_path: Path) -> None:
    tendcf_ops = tmp_path / "tendcf-ops"
    pub = _site(tendcf_ops, "tendcf-public-alice-lab", ansible=True)

    selection = sd.resolve_site_selection(
        {"TENDCF_OPS_ROOT": str(tendcf_ops), "TENDCF_SITE": "alice-lab"},
        require_ansible_config=True,
    )

    expected_priv = (tendcf_ops / "tendcf-private-alice-lab").resolve()
    assert selection.path == pub.resolve()
    assert selection.private_dir == expected_priv
    assert expected_priv.is_dir()
    assert stat.S_IMODE(expected_priv.stat().st_mode) == 0o700
    assert not (tendcf_ops / "site-private").exists()


def test_tendcf_active_site_file_via_xdg_and_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    tendcf_ops = home / "tendcf-ops"
    pub = _site(tendcf_ops, "tendcf-public-alice", ansible=True)
    priv = _site(tendcf_ops, "tendcf-private-alice")
    xdg = tmp_path / "xdg"
    cfg = xdg / "tendcf" / "active-site"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("# comment\n\n  alice  \n", encoding="utf-8")

    selection = sd.resolve_site_selection(
        {"HOME": str(home), "XDG_CONFIG_HOME": str(xdg)},
        require_ansible_config=True,
    )

    assert selection.path == pub.resolve()
    assert selection.slug == "alice"
    assert selection.private_dir == priv.resolve()
    assert "active-site" in selection.source


def test_relative_xdg_config_home_falls_back_to_home_dot_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    tendcf_ops = home / "tendcf-ops"
    pub = _site(tendcf_ops, "tendcf-public-alice", ansible=True)
    cfg = home / ".config" / "tendcf" / "active-site"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("alice\n", encoding="utf-8")

    selection = sd.resolve_site_selection(
        {"HOME": str(home), "XDG_CONFIG_HOME": "relative/config"},
        require_ansible_config=True,
    )

    assert selection.path == pub.resolve()
    assert selection.slug == "alice"


def test_tendcf_ops_never_globs_sole_directory_without_selector(tmp_path: Path) -> None:
    tendcf_ops = tmp_path / "tendcf-ops"
    _site(tendcf_ops, "tendcf-public-alice", ansible=True)

    with pytest.raises(sd.SiteDiscoveryError, match="never globs a sole directory"):
        sd.resolve_site_selection({"TENDCF_OPS_ROOT": str(tendcf_ops)}, require_ansible_config=True)

    assert not (tendcf_ops / "site-private").exists()


def test_default_tendcf_ops_without_selector_fails_closed_even_if_legacy_ops_exists(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _site(home / "tendcf-ops", "tendcf-public-alice", ansible=True)
    _site(home / "ops", "site-public-alice", ansible=True)

    with pytest.raises(sd.SiteDiscoveryError, match="never globs a sole directory"):
        sd.resolve_site_selection({"HOME": str(home)}, require_ansible_config=True)


def test_explicit_legacy_ops_root_is_isolated_from_host_active_site(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cfg = home / ".config" / "tendcf" / "active-site"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("corrupt invalid slug!!!\n", encoding="utf-8")
    legacy_ops = tmp_path / "legacy-ops"
    site = _site(legacy_ops, "site-public-example", ansible=True)

    selection = sd.resolve_site_selection(
        {"HOME": str(home), "OPS_ROOT": str(legacy_ops)},
        require_ansible_config=True,
    )

    assert selection.path == site.resolve()
    assert selection.source == "site-* discovery"


def test_active_site_file_rejects_symlink_multiline_and_bare_cr(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _site(home / "tendcf-ops", "tendcf-public-alice", ansible=True)
    cfg = home / ".config" / "tendcf" / "active-site"
    cfg.parent.mkdir(parents=True)

    target = tmp_path / "real-active-site"
    target.write_text("alice\n", encoding="utf-8")
    cfg.symlink_to(target)
    with pytest.raises(sd.SiteDiscoveryError, match="must not be a symlink"):
        sd.resolve_site_selection({"HOME": str(home)})

    cfg.unlink()
    cfg.write_text("alice\nbob\n", encoding="utf-8")
    with pytest.raises(sd.SiteDiscoveryError, match="ambiguous"):
        sd.resolve_site_selection({"HOME": str(home)})

    cfg.write_bytes(b"alice\rbob")
    with pytest.raises(sd.SiteDiscoveryError, match="bare CR"):
        sd.resolve_site_selection({"HOME": str(home)})


def test_tendcf_ops_rejects_symlinked_public_or_private_repo(tmp_path: Path) -> None:
    tendcf_ops = tmp_path / "tendcf-ops"
    tendcf_ops.mkdir()
    real_pub = _site(tmp_path / "elsewhere", "real-pub", ansible=True)
    (tendcf_ops / "tendcf-public-alice").symlink_to(real_pub, target_is_directory=True)

    with pytest.raises(sd.SiteDiscoveryError, match="must not be a symlink"):
        sd.resolve_site_selection({"TENDCF_OPS_ROOT": str(tendcf_ops), "TENDCF_SITE": "alice"})

    (tendcf_ops / "tendcf-public-alice").unlink()
    _site(tendcf_ops, "tendcf-public-alice", ansible=True)
    real_priv = _site(tmp_path / "elsewhere", "real-priv")
    (tendcf_ops / "tendcf-private-alice").symlink_to(real_priv, target_is_directory=True)

    with pytest.raises(sd.SiteDiscoveryError, match="must not be a symlink"):
        sd.resolve_site_selection({"TENDCF_OPS_ROOT": str(tendcf_ops), "TENDCF_SITE": "alice"})


def test_tendcf_ops_rejects_cross_site_private_dir_drift(tmp_path: Path) -> None:
    tendcf_ops = tmp_path / "tendcf-ops"
    _site(tendcf_ops, "tendcf-public-alice", ansible=True)
    _site(tendcf_ops, "tendcf-private-alice")
    bob_priv = _site(tendcf_ops, "tendcf-private-bob")

    with pytest.raises(sd.SiteDiscoveryError, match="Cross-site pairing mismatch"):
        sd.resolve_site_selection(
            {
                "TENDCF_OPS_ROOT": str(tendcf_ops),
                "TENDCF_SITE": "alice",
                "STAYTURGID_PRIVATE_DIR": str(bob_priv),
            }
        )


def test_tendcf_private_rejected_as_explicit_overlay(tmp_path: Path) -> None:
    tendcf_ops = tmp_path / "tendcf-ops"
    priv = _site(tendcf_ops, "tendcf-private-alice", ansible=True)

    with pytest.raises(sd.SiteDiscoveryError, match="reserved for the private companion"):
        sd.reject_private_companion_overlay(priv, {"TENDCF_OPS_ROOT": str(tendcf_ops)})


def test_stage0_tendcf_site_under_legacy_ops_pairs_site_public_and_private(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ops = home / "ops"
    pub = _site(ops, "site-public-alice", ansible=True)
    priv = _site(ops, "site-private-alice")
    _site(ops, "site-public-bob", ansible=True)

    selection = sd.resolve_site_selection(
        {"HOME": str(home), "TENDCF_SITE": "alice"},
        require_ansible_config=True,
    )

    assert selection.path == pub.resolve()
    assert selection.slug == "alice"
    assert selection.private_dir == priv.resolve()


def test_stage2_bridge_symlink_in_legacy_ops_deduplicates_without_ambiguity(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    real = _site(ops, "tendcf-public-alice", ansible=True)
    _site(ops, "tendcf-private-alice")
    (ops / "site-public-alice").symlink_to(real, target_is_directory=True)
    (ops / "tendcf-public-alice-wt").mkdir()

    selection = sd.resolve_site_selection({"OPS_ROOT": str(ops)}, require_ansible_config=True)

    assert selection.path == real.resolve()
    assert selection.slug == "alice"
    assert selection.private_dir == (ops / "tendcf-private-alice").resolve()


def test_tendcf_ops_root_empty_or_relative_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(sd.SiteDiscoveryError, match="TENDCF_OPS_ROOT"):
        sd.resolve_site_selection({"TENDCF_OPS_ROOT": ""})
    with pytest.raises(sd.SiteDiscoveryError, match="TENDCF_OPS_ROOT"):
        sd.resolve_site_selection({"TENDCF_OPS_ROOT": "relative/tendcf-ops"})
    with pytest.raises(sd.SiteDiscoveryError, match="TENDCF_OPS_ROOT"):
        sd.resolve_site_selection({"TENDCF_OPS_ROOT": str(tmp_path / ".." / "escape")})
    with pytest.raises(sd.SiteDiscoveryError, match="whitespace"):
        sd.resolve_site_selection({"TENDCF_OPS_ROOT": f"{tmp_path / 'tendcf-ops'}\n"})


# --- Adversary R1 regression tests (HIGH-1..5, MEDIUM-1..2, LOW-1) ----------


def test_high1_partial_rename_in_legacy_ops_does_not_self_brick(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    pub = _site(ops, "tendcf-public-alice", ansible=True)
    priv = _site(ops, "site-private-alice")
    env = {"OPS_ROOT": str(ops), "TENDCF_SITE": "alice"}

    first = sd.resolve_site_selection(env, require_ansible_config=True)
    second = sd.resolve_site_selection(env, require_ansible_config=True)

    assert first.path == pub.resolve()
    assert first.private_dir == priv.resolve()
    assert second == first
    assert not (ops / "tendcf-private-alice").exists()


def test_high1_stage2_bridge_symlink_on_private_companion_works_in_legacy_ops(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    pub = _site(ops, "tendcf-public-alice", ansible=True)
    real_priv = _site(ops, "site-private-alice")
    (ops / "tendcf-private-alice").symlink_to(real_priv, target_is_directory=True)
    env = {"OPS_ROOT": str(ops), "TENDCF_SITE": "alice"}

    selection = sd.resolve_site_selection(env, require_ansible_config=True)

    assert selection.path == pub.resolve()
    assert selection.private_dir == real_priv.resolve()


def test_high2_legacy_ops_tendcf_site_rejects_symlinked_private_overlay(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    priv = _site(ops, "site-private-alice", ansible=True)
    (ops / "site-public-alice").symlink_to(priv, target_is_directory=True)

    with pytest.raises(sd.SiteDiscoveryError, match="reserved for the private companion"):
        sd.resolve_site_selection({"OPS_ROOT": str(ops), "TENDCF_SITE": "alice"}, require_ansible_config=True)


@pytest.mark.parametrize("name", ["Site-Private", "SITE-PRIVATE-ALICE", "Tendcf-Private", "TENDCF-PRIVATE-ALICE"])
def test_high3_reserved_private_names_are_case_insensitive(name: str) -> None:
    assert sd.is_reserved_private_name(name) is True


def test_high3_reserved_private_symlink_name_rejected_before_resolve(tmp_path: Path) -> None:
    ops = tmp_path / "ops"
    real_site = _site(tmp_path / "elsewhere", "real-site", ansible=True)
    ops.mkdir()
    reserved_link = ops / "tendcf-private-alice"
    reserved_link.symlink_to(real_site, target_is_directory=True)

    with pytest.raises(sd.SiteDiscoveryError, match="reserved for the private companion"):
        sd.reject_private_companion_overlay(reserved_link, {"OPS_ROOT": str(ops)})


def test_high5_cross_slug_and_cross_root_pairing_rejected(tmp_path: Path) -> None:
    root_a = tmp_path / "root-a" / "tendcf-ops"
    root_b = tmp_path / "root-b" / "tendcf-ops"
    _site(root_a, "tendcf-public-alice", ansible=True)
    bob_legacy = _site(tmp_path / "ops", "site-public-bob", ansible=True)
    alice_other_root = _site(root_b, "tendcf-public-alice", ansible=True)

    with pytest.raises(sd.SiteDiscoveryError, match="Cross-site pairing mismatch"):
        sd.private_companion_path(
            {"TENDCF_OPS_ROOT": str(root_a), "TENDCF_SITE": "alice"},
            site_dir=bob_legacy,
        )
    with pytest.raises(sd.SiteDiscoveryError, match="Cross-root pairing mismatch"):
        sd.private_companion_path(
            {"TENDCF_OPS_ROOT": str(root_a), "TENDCF_SITE": "alice"},
            site_dir=alice_other_root,
        )


def test_high5_explicit_override_works_when_tendcf_ops_root_set_without_selector(tmp_path: Path) -> None:
    home = tmp_path / "home"
    tendcf_ops = home / "tendcf-ops"
    tendcf_ops.mkdir(parents=True)
    custom_site = _site(tmp_path / "custom", "my-site", ansible=True)

    selection = landing_discover._resolve_site(
        {
            "HOME": str(home),
            "TENDCF_OPS_ROOT": str(tendcf_ops),
            "STAYTURGID_SITE_DIR": str(custom_site),
        }
    )

    assert selection.path == custom_site.resolve()
    assert not (tendcf_ops / "site-private").exists()


def test_medium2_cross_root_bridge_and_mysite_pair_sibling_tendcf_private_without_ops_site_private(
    tmp_path: Path,
) -> None:
    ops = tmp_path / "ops"
    ops.mkdir()
    tendcf_ops = tmp_path / "tendcf-ops"
    real_pub = _site(tendcf_ops, "tendcf-public-alice", ansible=True)
    real_priv = _site(tendcf_ops, "tendcf-private-alice")
    (ops / "site-public-alice").symlink_to(real_pub, target_is_directory=True)

    sel_glob = sd.resolve_site_selection({"OPS_ROOT": str(ops)}, require_ansible_config=True)
    assert sel_glob.path == real_pub.resolve()
    assert sel_glob.slug == "alice"
    assert sel_glob.private_dir == real_priv.resolve()
    assert not (ops / "site-private").exists()

    (ops / ".mysite").symlink_to(real_pub, target_is_directory=True)
    sel_mysite = sd.resolve_site_selection({"OPS_ROOT": str(ops)}, require_ansible_config=True)
    assert sel_mysite.path == real_pub.resolve()
    assert sel_mysite.slug == "alice"
    assert sel_mysite.private_dir == real_priv.resolve()
    assert not (ops / "site-private").exists()
