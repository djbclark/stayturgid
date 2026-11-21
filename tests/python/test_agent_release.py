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


def test_only_the_sign_job_sees_the_signing_secrets_and_only_build_runs_gradle():
    jobs = _workflow()["jobs"]
    assert set(jobs) == {"build", "check", "sign", "release"}
    for name, job in jobs.items():
        dumped = yaml.safe_dump(job)
        assert ("secrets." in dumped) == (name == "sign"), name
        assert ("gradlew" in dumped) == (name == "build"), name
    sign_job = yaml.safe_dump(jobs["sign"])
    for name in agent_release.SECRET_ENV.values():
        assert f"secrets.{name}" in sign_job
    assert sign_job.count("secrets.") == len(agent_release.SECRET_ENV) == 3
    assert jobs["sign"]["environment"] == "agent-release"
    assert "environment" not in jobs["check"] and "environment" not in jobs["release"]


def test_the_key_and_the_write_token_never_share_a_job():
    jobs = _workflow()["jobs"]
    writers = [n for n, j in jobs.items() if "write" in (j.get("permissions") or {}).values()]
    assert writers == ["release"]
    assert jobs["sign"]["permissions"] == {"contents": "read"}
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["check"]["permissions"] == {"contents": "read"}
    for name, job in jobs.items():
        assert ("github.token" in yaml.safe_dump(job)) == (name == "release"), name


def test_jobs_run_in_the_order_check_sign_release_and_only_on_master():
    jobs = _workflow()["jobs"]
    assert jobs["check"]["needs"] == "build" and "refs/heads/master" in jobs["check"]["if"]
    assert "inputs.sign" in jobs["check"]["if"]
    assert "check" in jobs["sign"]["needs"] and "sign" in jobs["release"]["needs"]  # a skipped check skips the rest
    # the one parser of the Gradle-built APK that holds a secret never runs before `check` passed
    assert "release" not in jobs["sign"]["needs"]


def test_signing_job_signs_and_parses_nothing():
    text = (ROOT / "scripts/ci/agent_release.py").read_text(encoding="utf-8")
    sign_cmd = text[text.index("def cmd_sign") : text.index("def gh_json")]
    assert "apk_badging" not in sign_cmd and "check_signer" not in sign_cmd and "check_badging" not in sign_cmd


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


def _release_args(apk, code=101):
    import argparse

    return argparse.Namespace(apk=str(apk), code=code)


def _fake_release_world(monkeypatch, tmp_path, releases, *, signer_ok=True, badging=("org.stayturgid.agent", 101)):
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ID", "9")
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"signed")
    calls = []
    monkeypatch.setattr(agent_release, "all_releases", lambda repo: releases)
    monkeypatch.setattr(agent_release, "apk_badging", lambda path: badging)
    if signer_ok:
        monkeypatch.setattr(agent_release, "check_signer", lambda path: None)
    else:
        monkeypatch.setattr(agent_release, "check_signer", lambda path: (_ for _ in ()).throw(SystemExit("bad signer")))
    monkeypatch.setattr(agent_release, "run", lambda argv, **kw: calls.append(argv))
    return apk, calls


def _rel(code, draft=False, assets=("app-release.apk",)):
    return {"tag_name": f"agent-r{code}", "draft": draft, "assets": [{"name": n} for n in assets]}


def test_release_binds_the_apk_to_its_tag_before_calling_gh(monkeypatch, tmp_path):
    apk, calls = _fake_release_world(monkeypatch, tmp_path, [], badging=("org.stayturgid.agent", 99))
    with pytest.raises(SystemExit, match="versionCode 99, expected 101"):
        agent_release.cmd_release(_release_args(apk))
    apk, calls = _fake_release_world(monkeypatch, tmp_path, [], badging=("com.evil", 101))
    with pytest.raises(SystemExit, match="package"):
        agent_release.cmd_release(_release_args(apk))
    apk, calls = _fake_release_world(monkeypatch, tmp_path, [], signer_ok=False)
    with pytest.raises(SystemExit, match="bad signer"):
        agent_release.cmd_release(_release_args(apk))
    assert calls == []


def test_release_never_deletes_or_moves_a_tag(monkeypatch, tmp_path):
    # An incomplete published release is replaced, and the oldest are pruned; neither touches git tags.
    existing = [_rel(code) for code in range(101, 90, -1)]
    apk, calls = _fake_release_world(monkeypatch, tmp_path, [_rel(101, assets=())] + existing[1:])
    agent_release.cmd_release(_release_args(apk))
    assert not any("--cleanup-tag" in c for c in calls)
    verbs = [c[2] for c in calls if c[:2] == ["gh", "release"]]
    assert verbs[0] == "delete" and verbs[1] == "create"
    assert calls[0][3] == "agent-r101"


def test_release_refuses_a_downgrade_and_skips_a_finished_release(monkeypatch, tmp_path):
    apk, calls = _fake_release_world(monkeypatch, tmp_path, [_rel(105)])
    with pytest.raises(SystemExit, match="older than"):
        agent_release.cmd_release(_release_args(apk))
    apk, calls = _fake_release_world(monkeypatch, tmp_path, [_rel(101)])
    agent_release.cmd_release(_release_args(apk))
    assert calls == []
