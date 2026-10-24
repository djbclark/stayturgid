"""Regression guards for normal-deploy APK convergence."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/defaults/main.yml"


def _catalog():
    return yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))["stayturgid_bootstrap_apks"]


def _locked():
    return [apk for apk in _catalog() if not apk.get("gh_latest")]


def test_every_pinned_github_apk_is_immutably_locked():
    required = {"id", "gh_repo", "gh_tag", "gh_pattern", "version_name", "checksum"}
    for apk in _locked():
        assert required <= apk.keys(), apk["id"]
        assert apk["gh_tag"] not in {"latest", "nightly", ""}
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", apk["checksum"])


def test_latest_tracking_entries_carry_no_pin():
    # Termux:X11 follows upstream's newest release (operator, 2026-10-24); the
    # module resolves tag and digest on each deploy.
    latest = [apk for apk in _catalog() if apk.get("gh_latest")]
    assert [apk["id"] for apk in latest] == ["com.termux.x11"]
    for apk in latest:
        assert apk["gh_repo"] == "termux/termux-x11"
        assert not {"gh_tag", "version_name", "checksum"} & apk.keys()
    install_tasks = (
        ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/tasks/install_apk.yml"
    ).read_text(encoding="utf-8")
    assert 'gh_latest: "{{ _apk.gh_latest | default(false) }}"' in install_tasks


def test_native_agent_uses_its_release_stream_and_real_asset_name():
    agent = next(apk for apk in _catalog() if apk["id"] == "org.stayturgid.agent")
    assert agent["gh_tag"] == "agent-v0.9.19"
    assert agent["gh_pattern"] == "app-release.apk"
    assert agent["version_name"] == "0.9.19"
    assert agent["remove_packages"] == ["org.stayturgid.agent.debug"]
    assert agent["service_component"] == "org.stayturgid.agent/.HostService"
    assert agent["start_broadcast_action"] == "org.stayturgid.agent.action.PEER_START_NOW"


def test_normal_deploy_ensures_before_it_verifies():
    site = (ROOT / "ansible/playbooks/site.yml").read_text(encoding="utf-8")
    assert site.index("Import bootstrap APK ensure") < site.index("Import bootstrap APK verify")


def test_monkey_launch_is_limited_to_a_real_install():
    tasks = yaml.safe_load(
        (ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/tasks/install_apk.yml").read_text(
            encoding="utf-8"
        )
    )
    reconcile = next(task for task in tasks if task["name"].startswith("Reconcile locked APK"))
    install = next(task for task in reconcile["block"] if task["name"].startswith("Install over ADB"))
    monkey = next(task for task in tasks if task["name"].startswith("Launch via monkey"))

    assert install["register"] == "_apk_install"
    assert "_apk_install.changed | default(false)" in monkey["when"]


def test_tailscale_installs_detached_because_it_carries_the_adb_transport():
    # The adb target is a tailnet address: replacing the app mid-`adb install`
    # cut the connection and left t2e off the tailnet (2026-10-17).
    tailscale = next(apk for apk in _catalog() if apk["id"] == "com.tailscale.ipn")
    assert tailscale["detached_install"] is True
    assert [apk["id"] for apk in _catalog() if apk.get("detached_install")] == ["com.tailscale.ipn"]
    tasks = (
        ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/tasks/install_apk.yml"
    ).read_text(encoding="utf-8")
    assert 'detached_install: "{{ _apk.detached_install | default(false) }}"' in tasks


def test_locked_version_check_has_no_mutable_latest_lookup():
    tasks = ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/tasks"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in tasks.glob("*.yml"))
    assert "gh release view" not in combined
    assert "_apk.gh_tag" in combined
    assert "_apk.version_name" in combined


def test_optional_github_apks_require_the_same_lock_fields():
    tasks = (ROOT / "ansible_collections/stayturgid/android_common/roles/ensure_apps/tasks/main.yml").read_text(
        encoding="utf-8"
    )
    for field in ("gh_tag", "version_name", "checksum"):
        assert f"item.{field} is defined" in tasks


def test_paseo_is_left_to_play():
    # Play updates sh.paseo. A pin here would reinstall our locked build.
    assert [apk["id"] for apk in _catalog() if apk["id"] == "sh.paseo"] == []
