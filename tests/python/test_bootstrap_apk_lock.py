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


ROLLING = {
    "org.stayturgid.agent": "djbclark/stayturgid",
    "com.termux": "termux/termux-app",
    "com.termux.boot": "termux/termux-boot",
    "com.termux.api": "termux/termux-api",
    "com.termux.tasker": "termux/termux-tasker",
    "com.termux.x11": "termux/termux-x11",
    "moe.shizuku.privileged.api": "frdminc/ShizukuTendCF",
}


def test_latest_tracking_entries_carry_no_pin():
    # Rolling releases, no pins (operator, 2026-11-21; Termux:X11 since 2026-10-24): the
    # module resolves tag and digest on each deploy. Tailscale is the one APK still locked.
    latest = [apk for apk in _catalog() if apk.get("gh_latest")]
    assert {apk["id"]: apk["gh_repo"] for apk in latest} == ROLLING
    for apk in latest:
        assert not {"gh_tag", "version_name", "checksum"} & apk.keys(), apk["id"]
    assert [apk["id"] for apk in _locked()] == ["com.tailscale.ipn"]
    install_tasks = (
        ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/tasks/install_apk.yml"
    ).read_text(encoding="utf-8")
    assert 'gh_latest: "{{ _apk.gh_latest | default(omit) }}"' in install_tasks
    assert 'gh_tag_prefix: "{{ _apk.gh_tag_prefix | default(omit) }}"' in install_tasks
    assert 'gh_skip_prereleases: "{{ _apk.gh_skip_prereleases | default(omit) }}"' in install_tasks


def test_rolling_entries_never_uninstall_to_take_a_release_signed_by_someone_else():
    install = (
        ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/tasks/install_apk.yml"
    ).read_text(encoding="utf-8")
    assert (
        'clean_on_incompatible: "{{ _apk.clean_on_incompatible | default(not (_apk.gh_latest | default(false) | bool)) }}"'
        in install
    )
    assert 'signer_sha256: "{{ _apk.signer_sha256 | default(omit) }}"' in install
    assert not [a["id"] for a in _catalog() if a.get("gh_latest") and a.get("clean_on_incompatible")]


def test_rolling_stable_upstreams_skip_prereleases():
    # Termux publishes v0.119.0-beta.N prereleases next to the stable tag; a deploy must not install them.
    by_id = {apk["id"]: apk for apk in _catalog()}
    assert by_id["com.termux"]["gh_skip_prereleases"] is True
    assert by_id["moe.shizuku.privileged.api"]["gh_skip_prereleases"] is True
    # Termux:X11 ships only a republished nightly prerelease.
    assert not by_id["com.termux.x11"].get("gh_skip_prereleases")


def test_rolling_patterns_name_one_asset_of_the_real_release_assets():
    # Asset names read from the upstream releases on 2026-11-21 (each stable release has exactly one match).
    import fnmatch

    assets = {
        "com.termux": [
            "termux-app_v0.118.3+github-debug_arm64-v8a.apk",
            "termux-app_v0.118.3+github-debug_armeabi-v7a.apk",
            "termux-app_v0.118.3+github-debug_sha256sums",
            "termux-app_v0.118.3+github-debug_universal.apk",
            "termux-app_v0.118.3+github-debug_x86.apk",
        ],
        "com.termux.boot": ["checksums-sha256.txt", "termux-boot-app_v0.8.1+github.debug.apk"],
        "com.termux.api": ["checksums-sha256.txt", "termux-api-app_v0.53.0+github.debug.apk"],
        "com.termux.tasker": ["checksums-sha256.txt", "termux-tasker-app_v0.9.0+github.debug.apk"],
        "moe.shizuku.privileged.api": [
            "SHA256SUMS",
            "ShizukuTendCF-13.7.0.r2895-universal.apk",
            "ShizukuTendCF-Compat-Hub-13.7.0.r2895.apk",
            "ShizukuTendCF-Drop-In-13.7.0.r2895.apk",
        ],
        "org.stayturgid.agent": ["app-release.apk"],
    }
    by_id = {apk["id"]: apk for apk in _catalog()}
    for ident, names in assets.items():
        matches = [n for n in names if fnmatch.fnmatch(n, by_id[ident]["gh_pattern"])]
        assert len(matches) == 1, (ident, matches)
    # A beta's apt-android asset names never match the stable-asset pattern either.
    assert not fnmatch.fnmatch(
        "termux-app_v0.119.0-beta.3+apt-android-7-github-debug_arm64-v8a.apk", by_id["com.termux"]["gh_pattern"]
    )


def test_pin_to_fleet_is_one_opt_in_role_var_off_by_default():
    role = ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks"
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text(encoding="utf-8"))
    assert defaults["stayturgid_bootstrap_apks_pin_to_fleet"] is False
    install_tasks = (role / "tasks/install_apk.yml").read_text(encoding="utf-8")
    assert 'gh_latest_pin_to_cache: "{{ stayturgid_bootstrap_apks_pin_to_fleet | default(false) }}"' in install_tasks


def test_native_agent_uses_its_release_stream_and_real_asset_name():
    agent = next(apk for apk in _catalog() if apk["id"] == "org.stayturgid.agent")
    # Rolling: CI publishes agent-r<versionCode> with one signed app-release.apk; agent-ci-* and agent-v*
    # tags are other streams, so the tag prefix is what keeps gh_latest on the signed one.
    assert agent["gh_latest"] is True
    assert agent["gh_tag_prefix"] == "agent-r"
    assert agent["gh_pattern"] == "app-release.apk"
    assert not {"gh_tag", "version_name", "checksum"} & agent.keys()
    # The signer is pinned instead of the version: whoever can create an agent-r* release cannot get
    # a foreign APK onto a phone (adversary review H1).
    assert agent["signer_sha256"] == "35bbc3d1a93c2a726df14bcc066bdc791f7f55f21b57d9455da27439c5ff9b6a"
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
    assert "_apk.gh_tag" in combined  # the pinned (Tailscale) path
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
