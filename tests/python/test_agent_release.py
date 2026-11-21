"""scripts/ci/agent_release.py: rolling version, tag and prune rules of the agent release workflow."""

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("agent_release", ROOT / "scripts/ci/agent_release.py")
assert SPEC and SPEC.loader
agent_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_release)
WORKFLOW = ROOT / ".github/workflows/agent-release.yml"


def test_first_rolling_build_is_newer_than_the_hand_made_release():
    # agent-v0.9.19 is versionCode 37; run 1 of the new workflow must already beat it.
    assert agent_release.version_code(1) > 37


def test_version_code_rises_with_every_run_and_name_carries_code_and_sha():
    assert agent_release.version_code(8) == agent_release.version_code(7) + 1
    assert agent_release.version_name(108, "0123456789abcdef") == "0.9.108+01234567"


def test_tag_round_trips_and_ignores_other_streams():
    assert agent_release.tag_for(108) == "agent-r108"
    assert agent_release.code_of_tag("agent-r108") == 108
    for other in ("agent-v0.9.19", "agent-ci-0.9.19-cdd76c47", "agent-r", "agent-r1x", "ops-v1.0"):
        assert agent_release.code_of_tag(other) is None


def test_prune_keeps_the_newest_ten_by_version_code_not_by_text_order():
    tags = [f"agent-r{n}" for n in range(99, 111)]
    tags += ["agent-v0.9.19", "agent-ci-0.9.19-cdd76c47", "stayturgid.fleet-1.0.0"]
    # As text 99 sorts after 110; by code it is the oldest of twelve.
    assert agent_release.releases_to_prune(tags) == ["agent-r100", "agent-r99"]
    assert agent_release.releases_to_prune(tags[:10]) == []
    assert agent_release.releases_to_prune(["agent-v0.9.19"] * 30) == []


def test_newest_code_ignores_other_streams():
    assert agent_release.newest_code(["agent-v0.9.19", "agent-r120", "agent-r7"]) == 120
    assert agent_release.newest_code(["agent-v0.9.19"]) == 0


def test_signer_constant_matches_the_local_fallback_signer():
    fetch = (ROOT / "control/tools/native-agent/ci_fetch_sign.py").read_text(encoding="utf-8")
    assert f'SIGNER_SHA256 = "{agent_release.SIGNER_SHA256}"' in fetch


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_never_runs_on_pull_requests_or_other_branches():
    workflow = _workflow()
    triggers = workflow[True]  # PyYAML reads the bare key `on` as the boolean True
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["master"]
    assert "device/native-agent/**" in triggers["push"]["paths"]
    assert workflow["permissions"] == {}


def test_only_the_publish_job_sees_the_signing_secrets_and_it_runs_no_gradle():
    text = WORKFLOW.read_text(encoding="utf-8")
    jobs = _workflow()["jobs"]
    assert "secrets." not in yaml.safe_dump(jobs["build"])
    assert "gradlew" not in yaml.safe_dump(jobs["publish"])
    assert jobs["publish"]["environment"] == "agent-release"
    assert "refs/heads/master" in jobs["publish"]["if"]
    assert jobs["build"]["permissions"] == {"contents": "read"}
    for name in agent_release.SECRET_ENV.values():
        assert f"secrets.{name}" in text
    assert text.count("secrets.") == len(agent_release.SECRET_ENV) == 3


def test_no_publish_step_holds_both_the_key_and_the_token_or_parses_the_apk_with_either():
    steps = _workflow()["jobs"]["publish"]["steps"]
    holders = {}
    for step in steps:
        env = " ".join(f"{k}={v}" for k, v in (step.get("env") or {}).items())
        holders[step["name"]] = ("secrets." in env, "github.token" in env)
    key_steps = [n for n, (key, _tok) in holders.items() if key]
    token_steps = [n for n, (_key, tok) in holders.items() if tok]
    assert len(key_steps) == 1 and len(token_steps) == 1 and key_steps != token_steps
    names = [step["name"] for step in steps]
    # the step that first parses the Gradle-built APK (check) comes before and holds neither
    first_check = next(i for i, n in enumerate(names) if n.startswith("Check the unsigned APK"))
    assert first_check < names.index(key_steps[0]) < names.index(token_steps[0])
    assert holders[names[first_check]] == (False, False)


def test_branch_dispatches_cannot_replace_a_pending_master_release():
    group = _workflow()["concurrency"]["group"]
    assert "refs/heads/master" in group and "format(" in group
    # a master dispatch that does not publish (sign=false) must not share the publishing group either
    assert "inputs.sign" in group and "github.run_id" in group


def test_scrubbed_env_hides_every_signing_secret(monkeypatch):
    for name in agent_release.SECRET_ENV.values():
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("GH_TOKEN", "t")
    env = agent_release.scrubbed_env({"AGENT_STORE_PASS": "p"})
    assert not set(agent_release.SECRET_ENV.values()) & env.keys()
    assert env["GH_TOKEN"] == "t" and env["AGENT_STORE_PASS"] == "p"


def test_a_draft_or_asset_less_release_is_not_complete():
    ok = {"tag_name": "agent-r101", "draft": False, "assets": [{"name": "app-release.apk"}]}
    assert agent_release.is_complete(ok)
    assert not agent_release.is_complete({**ok, "draft": True})
    assert not agent_release.is_complete({**ok, "assets": []})
    assert not agent_release.is_complete({**ok, "assets": [{"name": "other.apk"}]})
    assert not agent_release.is_complete({**ok, "assets": [{"name": "app-release.apk"}, {"name": "x"}]})


def test_actions_in_the_workflow_are_pinned_by_commit():
    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW.read_text(encoding="utf-8"))
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref


def test_workflow_hands_gradle_the_rolling_version():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "AGENT_VERSION_CODE" in text and "AGENT_VERSION_NAME" in text
    gradle = (ROOT / "device/native-agent/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'System.getenv("AGENT_VERSION_CODE")' in gradle
    assert 'System.getenv("AGENT_VERSION_NAME")' in gradle


def test_release_asset_name_is_the_one_bootstrap_apks_matches():
    defaults = yaml.safe_load(
        (ROOT / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/defaults/main.yml").read_text(
            encoding="utf-8"
        )
    )
    agent = next(a for a in defaults["stayturgid_bootstrap_apks"] if a["id"] == "org.stayturgid.agent")
    assert agent["gh_pattern"] == agent_release.ASSET_NAME
    assert agent["gh_tag_prefix"] == agent_release.TAG_PREFIX
    assert agent["signer_sha256"] == agent_release.SIGNER_SHA256


def test_sign_refuses_to_run_without_the_secrets(monkeypatch, tmp_path):
    for name in agent_release.SECRET_ENV.values():
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as exc:
        agent_release.sign(tmp_path / "in.apk", tmp_path / "out.apk")
    assert "STAYTURGID_AGENT_KEYSTORE_B64" in str(exc.value)
    assert not list(tmp_path.glob("*.jks"))
