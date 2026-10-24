"""prefetch_pins fills the caches a deploy already checks, under the same locks."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APK_DEFAULTS = REPO / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/defaults/main.yml"
OTEL_DEFAULTS = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/defaults/main.yml"
MODULE = REPO / "ansible_collections/stayturgid/android_common/plugins/modules/android_apk.py"

_spec = importlib.util.spec_from_file_location("prefetch_pins", REPO / "control/bin/prefetch_pins.py")
assert _spec is not None and _spec.loader is not None
prefetch = importlib.util.module_from_spec(_spec)
sys.modules["prefetch_pins"] = prefetch
_spec.loader.exec_module(prefetch)

_apk_spec = importlib.util.spec_from_file_location("android_apk", MODULE)
assert _apk_spec is not None and _apk_spec.loader is not None
android_apk = importlib.util.module_from_spec(_apk_spec)
_apk_spec.loader.exec_module(android_apk)

PINNED_IDS = {
    "org.stayturgid.agent",
    "com.termux",
    "com.termux.boot",
    "com.termux.api",
    "com.termux.tasker",
    "moe.shizuku.privileged.api",
    "com.tailscale.ipn",
}


def test_real_pins_are_the_fleet_set() -> None:
    pins, skipped = prefetch.load_apk_pins(APK_DEFAULTS.read_text())
    # Termux:X11 tracks the newest upstream release, so there is nothing to prefetch.
    assert skipped == ["com.termux.x11"]
    assert {pin.ident for pin in pins} == PINNED_IDS
    assert all(len(pin.sha256) == 64 for pin in pins)


def test_otel_arch_and_cache_root_match_the_role() -> None:
    defaults = OTEL_DEFAULTS.read_text()
    assert prefetch.load_otel_arch(defaults) == "linux_arm64"
    # The deploy caches under stayturgid_otelcol_cache_root; prefetch must fill the same tree.
    assert (
        "stayturgid_otelcol_cache_root: \"{{ lookup('env', 'HOME') }}/.cache/stayturgid/otelcol-contrib\"" in defaults
    )
    assert prefetch.otel_cache_root() == Path.home() / ".cache/stayturgid/otelcol-contrib"
    assert "stayturgid_otelcol_version" not in defaults, "otelcol tracks the latest release; nothing is pinned"
    assert "sha256" not in defaults


def test_otel_loader_refuses_defaults_without_the_arch() -> None:
    with pytest.raises(prefetch.PrefetchError, match="no longer set stayturgid_otelcol_archive_arch"):
        prefetch.load_otel_arch("stayturgid_otelcol_enabled: true\n")


class _FakeCache:
    class ArtifactError(RuntimeError):
        pass

    def __init__(self, lookup_error: str = "") -> None:
        self.calls: list[dict] = []
        self.lookup_error = lookup_error

    def resolve_latest_version(self) -> str:
        if self.lookup_error:
            raise self.ArtifactError(self.lookup_error)
        return "0.170.1"

    def cache_latest(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {}


def test_ensure_otel_caches_the_latest_release_where_the_deploy_looks(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCache()
    monkeypatch.setattr(prefetch, "_cache_otelcol", lambda: fake)
    target = prefetch.latest_otel("linux_arm64")
    assert target == prefetch.OtelTarget("0.170.1", "linux_arm64")
    assert target.archive_name == "otelcol-contrib_0.170.1_linux_arm64.tar.gz"
    assert prefetch.ensure_otel(target, 30) in {"hit", "fetched"}
    assert fake.calls == [
        {
            "cache_root": prefetch.otel_cache_root(),
            "architecture": "linux_arm64",
            "timeout_seconds": 30,
            "version": "0.170.1",
        }
    ]


def test_a_failed_latest_lookup_is_a_prefetch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCache(lookup_error="rate limited")
    monkeypatch.setattr(prefetch, "_cache_otelcol", lambda: fake)
    with pytest.raises(prefetch.PrefetchError, match="rate limited"):
        prefetch.latest_otel("linux_arm64")


def test_partial_token_matches_the_deploy_downloader() -> None:
    source = MODULE.read_text()
    assert '("%s\\0%s\\0%s" % (repo, tag or "", pattern or ""))' in source
    assert prefetch.partial_token("a/b", "tag", "*.apk") == hashlib.sha256(b"a/b\0tag\0*.apk").hexdigest()[:16]


def test_lock_path_matches_cached_download() -> None:
    sha = "ab" * 32
    cached = os.path.join(android_apk.APK_CACHE_DIR, sha + ".apk")
    assert prefetch.apk_lock_path(prefetch.default_apk_cache(), sha) == Path(cached + ".lock")
    assert str(prefetch.default_apk_cache()) == android_apk.APK_CACHE_DIR


def test_ensure_apk_is_a_hit_without_downloading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"hello-apk"
    digest = hashlib.sha256(payload).hexdigest()
    pin = prefetch.ApkPin("demo", "o/r", "v1", "demo.apk", digest)
    cached = prefetch.apk_cache_file(tmp_path, digest)
    cached.write_bytes(payload)
    monkeypatch.setattr(prefetch, "_gh_asset", lambda *_a, **_k: pytest.fail("resolved a hit"))
    monkeypatch.setattr(prefetch.asset_fetch, "fetch", lambda *_a, **_k: pytest.fail("fetched a hit"))
    assert prefetch.ensure_apk(pin, tmp_path, 30) == "hit"


def test_ensure_apk_fetches_into_the_deploy_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"fresh-apk"
    digest = hashlib.sha256(payload).hexdigest()
    pin = prefetch.ApkPin("demo", "o/r", "v1", "demo.apk", digest)
    calls: list[Path] = []

    def fetch(_url: str, dest: Path, _timeout: int) -> None:
        calls.append(dest)
        dest.write_bytes(payload)

    monkeypatch.setattr(prefetch, "_gh_asset", lambda *_a, **_k: ("demo.apk", "https://example.invalid/demo.apk"))
    monkeypatch.setattr(prefetch.asset_fetch, "fetch", fetch)
    assert prefetch.ensure_apk(pin, tmp_path, 30) == "fetched"
    assert calls == [prefetch.apk_partial_dest(tmp_path, pin, "demo.apk")]
    assert prefetch.apk_cache_file(tmp_path, digest).read_bytes() == payload
    assert prefetch.ensure_apk(pin, tmp_path, 30) == "hit"
    assert len(calls) == 1


def test_wrong_sha_is_deleted_and_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    digest = "cd" * 32
    pin = prefetch.ApkPin("demo", "o/r", "v1", "demo.apk", digest)

    def fetch(_url: str, dest: Path, _timeout: int) -> None:
        dest.write_bytes(b"nope")

    monkeypatch.setattr(prefetch, "_gh_asset", lambda *_a, **_k: ("demo.apk", "https://example.invalid/demo.apk"))
    monkeypatch.setattr(prefetch.asset_fetch, "fetch", fetch)
    with pytest.raises(prefetch.PrefetchError, match="wrong sha256"):
        prefetch.ensure_apk(pin, tmp_path, 30)
    dest = prefetch.apk_partial_dest(tmp_path, pin, "demo.apk")
    assert not dest.exists()
    assert not prefetch.apk_cache_file(tmp_path, digest).exists()


def test_a_failed_transfer_keeps_the_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    digest = "ef" * 32
    pin = prefetch.ApkPin("demo", "o/r", "v1", "demo.apk", digest)

    def fetch(_url: str, dest: Path, _timeout: int) -> None:
        dest.write_bytes(b"partial")
        raise prefetch.asset_fetch.FetchError("download of demo.apk failed. The partial file was kept.")

    monkeypatch.setattr(prefetch, "_gh_asset", lambda *_a, **_k: ("demo.apk", "https://example.invalid/demo.apk"))
    monkeypatch.setattr(prefetch.asset_fetch, "fetch", fetch)
    with pytest.raises(prefetch.PrefetchError, match="partial file was kept"):
        prefetch.ensure_apk(pin, tmp_path, 30)
    assert prefetch.apk_partial_dest(tmp_path, pin, "demo.apk").read_bytes() == b"partial"


def test_callers_share_one_script() -> None:
    plist = (REPO / "ansible/roles/control_node/templates/prefetch-pins.plist.j2").read_text()
    workflow = (REPO / ".github/workflows/prefetch-pins.yml").read_text()
    ensure = (REPO / "ansible/roles/control_node/tasks/agents_ensure.yml").read_text()
    agents = (REPO / "ansible/roles/control_node/tasks/agents.yml").read_text()
    assert "control/bin/prefetch_pins.py" in plist
    assert "control/bin/prefetch_pins.py" in workflow
    assert "com.stayturgid.prefetch-pins" in plist
    assert "com.stayturgid.prefetch-pins" in ensure
    assert "com.stayturgid.prefetch-pins" in agents
    assert "runs-on: self-hosted" not in workflow
    assert "cancel-in-progress: false" in workflow
    assert "Wake secrets are unset" in workflow


def test_dry_run_does_not_download_or_update(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    apk = tmp_path / "apk.yml"
    otel = tmp_path / "otel.yml"
    apk.write_text(
        "stayturgid_bootstrap_apks:\n"
        "  - id: demo\n"
        "    gh_repo: o/r\n"
        "    gh_tag: v1\n"
        "    gh_pattern: demo.apk\n"
        '    checksum: "sha256:' + ("ab" * 32) + '"\n'
    )
    otel.write_text("stayturgid_otelcol_archive_arch: linux_arm64\n")
    monkeypatch.setattr(prefetch, "_paths", lambda _repo: (apk, otel))
    monkeypatch.setattr(prefetch, "default_apk_cache", lambda: tmp_path / "apks")
    monkeypatch.setattr(prefetch, "update_checkout", lambda _repo: pytest.fail("updated"))
    monkeypatch.setattr(prefetch, "ensure_apk", lambda *_a, **_k: pytest.fail("downloaded"))
    monkeypatch.setattr(prefetch, "ensure_otel", lambda *_a, **_k: pytest.fail("downloaded"))
    monkeypatch.setattr(prefetch, "latest_otel", lambda arch: prefetch.OtelTarget("0.0.1", arch))
    assert prefetch.main(["--repo-root", str(tmp_path), "--dry-run", "--no-update"]) == 0
