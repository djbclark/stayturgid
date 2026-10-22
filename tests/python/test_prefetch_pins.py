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
    "com.termux.x11",
    "moe.shizuku.privileged.api",
    "com.tailscale.ipn",
}


def test_real_pins_are_the_fleet_set() -> None:
    pins, skipped = prefetch.load_apk_pins(APK_DEFAULTS.read_text())
    assert skipped == []
    assert {pin.ident for pin in pins} == PINNED_IDS
    assert all(len(pin.sha256) == 64 for pin in pins)


def test_otel_pin_matches_the_role_template() -> None:
    pin = prefetch.load_otel_pin(OTEL_DEFAULTS.read_text())
    assert pin.version == "0.163.2"
    assert pin.arch == "linux_arm64"
    assert pin.sha256 == "d239e219cf81993213fda2fd6de7dc1f9229d32698c45d2dd7bec31b69c1c004"
    assert pin.url.endswith("/v0.163.2/otelcol-contrib_0.163.2_linux_arm64.tar.gz")


def test_otel_loader_refuses_a_changed_url_template() -> None:
    with pytest.raises(prefetch.PrefetchError, match="URL template changed"):
        prefetch.load_otel_pin("stayturgid_otelcol_version: '1'\n")


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
    otel.write_text(
        "stayturgid_otelcol_version: '0.0.1'\n"
        "stayturgid_otelcol_archive_arch: linux_arm64\n"
        "stayturgid_otelcol_archive_sha256: " + ("cd" * 32) + "\n"
        "# " + prefetch._OTEL_NAME_TMPL + "\n"
        "# " + prefetch._OTEL_URL_TMPL + "\n"
    )
    monkeypatch.setattr(prefetch, "_paths", lambda _repo: (apk, otel))
    monkeypatch.setattr(prefetch, "default_apk_cache", lambda: tmp_path / "apks")
    monkeypatch.setattr(prefetch, "update_checkout", lambda _repo: pytest.fail("updated"))
    monkeypatch.setattr(prefetch, "ensure_apk", lambda *_a, **_k: pytest.fail("downloaded"))
    monkeypatch.setattr(prefetch, "ensure_otel", lambda *_a, **_k: pytest.fail("downloaded"))
    assert prefetch.main(["--repo-root", str(tmp_path), "--dry-run", "--no-update"]) == 0
