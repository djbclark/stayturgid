"""Regression guards for normal-deploy APK convergence."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/defaults/main.yml"


def _catalog():
    return yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))["stayturgid_bootstrap_apks"]


def test_every_github_apk_is_immutably_locked():
    required = {"id", "gh_repo", "gh_tag", "gh_pattern", "version_name", "checksum"}
    for apk in _catalog():
        assert required <= apk.keys(), apk["id"]
        assert apk["gh_tag"] not in {"latest", ""}
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", apk["checksum"])


def test_native_agent_uses_its_release_stream_and_real_asset_name():
    agent = next(apk for apk in _catalog() if apk["id"] == "org.stayturgid.agent")
    assert agent["gh_tag"] == "agent-v0.6.0"
    assert agent["gh_pattern"] == "app-release.apk"
    assert agent["version_name"] == "0.6.0-boot-stability"
    assert agent["remove_packages"] == ["org.stayturgid.agent.debug"]
    assert agent["service_component"] == "org.stayturgid.agent/.HostService"
    assert agent["start_broadcast_action"] == "org.stayturgid.agent.action.PEER_START_NOW"


def test_normal_deploy_ensures_before_it_verifies():
    site = (ROOT / "ansible/playbooks/site.yml").read_text(encoding="utf-8")
    assert site.index("Import bootstrap APK ensure") < site.index("Import bootstrap APK verify")


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
