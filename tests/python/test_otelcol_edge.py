from __future__ import annotations

import importlib.util
import io
import json
import os
import signal
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"


def _load_cache_module():
    path = REPO / "control/bin/cache_otelcol.py"
    spec = importlib.util.spec_from_file_location("cache_otelcol", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cache_otelcol = _load_cache_module()


def _aarch64_elf(payload: bytes = b"") -> bytes:
    header = bytearray(20)
    header[:4] = b"\x7fELF"
    header[4] = 2  # ELFCLASS64
    header[5] = 1  # little endian
    header[18:20] = (183).to_bytes(2, "little")  # EM_AARCH64
    return bytes(header) + payload


def _artifact(tmp_path: Path) -> Path:
    archive = tmp_path / "otelcol-contrib_0.156.0_linux_arm64.tar.gz"
    data = _aarch64_elf(b"collector")
    info = tarfile.TarInfo("otelcol-contrib")
    info.size = len(data)
    info.mode = 0o755
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.addfile(info, io.BytesIO(data))
    return archive


def _render(name: str, **variables: object) -> str:
    environment = Environment(
        loader=FileSystemLoader(str(ROLE / "templates")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    return environment.get_template(name).render(**variables)


class _Release(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _mock_latest(monkeypatch: pytest.MonkeyPatch, tag: str) -> list[urllib.request.Request]:
    """Answer the GitHub releases/latest lookup locally; anything else (file:// fixtures) is real."""
    seen: list[urllib.request.Request] = []
    real_urlopen = urllib.request.urlopen

    def urlopen(request, timeout=None):
        if not request.full_url.startswith("https://api.github.com/"):
            return real_urlopen(request, timeout=timeout)
        seen.append(request)
        return _Release(json.dumps({"tag_name": tag}).encode())

    monkeypatch.setattr(cache_otelcol.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    return seen


def test_latest_version_is_resolved_from_the_releases_api(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _mock_latest(monkeypatch, "v0.170.1")
    assert cache_otelcol.resolve_latest_version() == "0.170.1"
    assert seen[0].full_url.endswith("/repos/open-telemetry/opentelemetry-collector-releases/releases/latest")
    assert seen[0].get_header("Authorization") == "Bearer tok"
    assert cache_otelcol.archive_url("0.170.1", "linux_arm64") == (
        "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/"
        "v0.170.1/otelcol-contrib_0.170.1_linux_arm64.tar.gz"
    )


@pytest.mark.parametrize("tag", ["", "nightly", "v1", "v0.170.1-rc1"])
def test_a_latest_tag_that_is_not_a_dotted_version_fails(monkeypatch: pytest.MonkeyPatch, tag: str) -> None:
    _mock_latest(monkeypatch, tag)
    with pytest.raises(cache_otelcol.ArtifactError, match="not a dotted version"):
        cache_otelcol.resolve_latest_version()


def test_cache_latest_caches_the_resolved_version_and_prunes_older_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _artifact(tmp_path)
    _mock_latest(monkeypatch, "v0.156.0")
    monkeypatch.setattr(cache_otelcol, "archive_url", lambda version, arch: archive.as_uri())
    root = tmp_path / "root"
    old = root / "0.155.0"
    old.mkdir(parents=True)
    (root / "notes").mkdir()
    result = cache_otelcol.cache_latest(cache_root=root, architecture="linux_arm64")
    assert result == {
        "version": "0.156.0",
        "archive": str(root / "0.156.0" / "otelcol-contrib_0.156.0_linux_arm64.tar.gz"),
        "binary": str(root / "0.156.0" / "otelcol-contrib"),
        "changed": True,
    }
    assert Path(str(result["archive"])).is_file()
    assert not old.exists()
    assert (root / "notes").is_dir()
    assert cache_otelcol.cache_latest(cache_root=root, architecture="linux_arm64")["changed"] is False


def test_http_download_timeout_keeps_the_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    partial = tmp_path / "otelcol-contrib_0.163.2_linux_arm64.tar.gz.partial"
    partial.write_bytes(b"already")

    def expire(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(cache_otelcol.shutil, "which", lambda name: "/usr/bin/aria2c")
    monkeypatch.setattr(cache_otelcol.subprocess, "run", expire)
    with pytest.raises(cache_otelcol.ArtifactError, match="did not finish within 30s"):
        cache_otelcol.download_to("https://example.invalid/otel.tar.gz", partial, 30)
    assert partial.read_bytes() == b"already"


def test_http_download_failure_keeps_the_partial_and_names_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    partial = tmp_path / "otel.partial"
    partial.write_bytes(b"some")

    class Done:
        returncode = 1
        stderr = "connection reset"
        stdout = ""

    monkeypatch.setattr(cache_otelcol.shutil, "which", lambda name: "/usr/bin/aria2c")
    monkeypatch.setattr(cache_otelcol.subprocess, "run", lambda *args, **kwargs: Done())
    with pytest.raises(cache_otelcol.ArtifactError, match="download of otel.partial failed") as raised:
        cache_otelcol.download_to("https://example.invalid/otel.tar.gz", partial, 30)
    assert "partial file was kept" in str(raised.value)
    assert "connection reset" in str(raised.value)
    assert partial.read_bytes() == b"some"


def test_download_to_skips_aria2_when_the_host_finishes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asset_fetch

    partial = tmp_path / "otel.tar.gz.partial"
    monkeypatch.setenv("STAYTURGID_FETCH_SSH_HOST", "vps-primary")
    monkeypatch.setattr(asset_fetch, "try_vps", lambda *_args, **_kwargs: True)

    def boom(*_args, **_kwargs):
        raise AssertionError("aria2 should not run")

    monkeypatch.setattr(cache_otelcol.subprocess, "run", boom)
    cache_otelcol.download_to("https://example.invalid/otel.tar.gz", partial, 30)


def test_download_to_does_not_aria2_when_the_host_transfer_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asset_fetch

    partial = tmp_path / "otel.tar.gz.partial"
    monkeypatch.setenv("STAYTURGID_FETCH_SSH_HOST", "vps-primary")

    def fail(*_args, **_kwargs):
        raise asset_fetch.FetchError(
            "download of otel.tar.gz.partial did not finish within 30s. The transfer was stopped."
        )

    monkeypatch.setattr(asset_fetch, "try_vps", fail)
    monkeypatch.setattr(cache_otelcol.subprocess, "run", lambda *_a, **_k: pytest.fail("aria2 started"))
    with pytest.raises(cache_otelcol.ArtifactError, match="did not finish within 30s"):
        cache_otelcol.download_to("https://example.invalid/otel.tar.gz", partial, 30)


def test_download_to_keeps_a_partial_on_aria2_when_a_host_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asset_fetch

    partial = tmp_path / "otel.partial"
    partial.write_bytes(b"already")
    monkeypatch.setenv("STAYTURGID_FETCH_SSH_HOST", "vps-primary")
    monkeypatch.setattr(asset_fetch, "try_vps", lambda *_a, **_k: pytest.fail("probed a partial"))

    def expire(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(cache_otelcol.shutil, "which", lambda name: "/usr/bin/aria2c")
    monkeypatch.setattr(cache_otelcol.subprocess, "run", expire)
    with pytest.raises(cache_otelcol.ArtifactError, match="did not finish within 30s"):
        cache_otelcol.download_to("https://example.invalid/otel.tar.gz", partial, 30)
    assert partial.read_bytes() == b"already"


def test_a_truncated_download_is_not_cached(tmp_path: Path) -> None:
    archive = _artifact(tmp_path)
    truncated = tmp_path / "otelcol-contrib_0.156.0_linux_arm64.tar.gz.src"
    truncated.write_bytes(archive.read_bytes()[:-20])
    cache_dir = tmp_path / "cache"
    with pytest.raises(cache_otelcol.ArtifactError, match="invalid collector archive"):
        cache_otelcol.ensure_cached(url=truncated.as_uri(), cache_dir=cache_dir, architecture="linux_arm64")
    assert list(cache_dir.glob("*.tar.gz*")) == []


def test_corrupt_cached_archive_is_not_silently_replaced(tmp_path: Path) -> None:
    archive = _artifact(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cached_archive = cache_dir / archive.name
    cached_archive.write_bytes(b"corrupt")
    with pytest.raises(cache_otelcol.ArtifactError, match="invalid collector archive"):
        cache_otelcol.ensure_cached(
            url=archive.as_uri(),
            cache_dir=cache_dir,
            architecture="linux_arm64",
        )
    assert cached_archive.read_bytes() == b"corrupt"


def test_abi_selection_and_elf_validation_fail_closed(tmp_path: Path) -> None:
    assert cache_otelcol.normalize_device_arch("aarch64") == "linux_arm64"
    assert cache_otelcol.normalize_device_arch("ARM64") == "linux_arm64"
    with pytest.raises(cache_otelcol.ArtifactError, match="unsupported"):
        cache_otelcol.normalize_device_arch("armv7l")

    wrong_arch = tmp_path / "otelcol-contrib"
    wrong = bytearray(_aarch64_elf())
    wrong[18:20] = (62).to_bytes(2, "little")  # EM_X86_64
    wrong_arch.write_bytes(wrong)
    with pytest.raises(cache_otelcol.ArtifactError, match="expected AArch64"):
        cache_otelcol.validate_linux_arm64_elf(wrong_arch)


def test_mac_cache_is_idempotent(tmp_path: Path) -> None:
    archive = _artifact(tmp_path)
    cache_dir = tmp_path / "cache"
    assert cache_otelcol.ensure_cached(
        url=archive.as_uri(),
        cache_dir=cache_dir,
        architecture="linux_arm64",
    )
    assert not cache_otelcol.ensure_cached(
        url=archive.as_uri(),
        cache_dir=cache_dir,
        architecture="linux_arm64",
    )
    cached_binary = cache_dir / "otelcol-contrib"
    assert cached_binary.stat().st_mode & 0o111
    cache_otelcol.validate_linux_arm64_elf(cached_binary)


def test_corrupt_cached_binary_fails_closed(tmp_path: Path) -> None:
    archive = _artifact(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_otelcol.ensure_cached(
        url=archive.as_uri(),
        cache_dir=cache_dir,
        architecture="linux_arm64",
    )
    (cache_dir / "otelcol-contrib").write_bytes(_aarch64_elf(b"tampered"))
    with pytest.raises(cache_otelcol.ArtifactError, match="does not match"):
        cache_otelcol.ensure_cached(
            url=archive.as_uri(),
            cache_dir=cache_dir,
            architecture="linux_arm64",
        )


def test_config_has_required_pipeline_and_persistent_storage() -> None:
    rendered = _render(
        "otel-config.yaml.j2",
        stayturgid_otelcol_state_dir="/data/data/com.termux/files/home/.stayturgid/state/otelcol",
        termux_home="/data/data/com.termux/files/home",
        stayturgid_sd_root="/sdcard/stayturgid",
        inventory_hostname="pilot",
        stayturgid_otelcol_endpoint="http://100.64.0.1:4318",
    )
    config = yaml.safe_load(rendered)

    storage = config["extensions"]["file_storage"]
    assert storage["directory"].endswith("/.stayturgid/state/otelcol")
    assert storage["compaction"]["directory"].endswith("/.stayturgid/state/otelcol/compaction")
    assert config["processors"]["memory_limiter"]["limit_mib"] == 100
    assert config["processors"]["batch"]["timeout"] == "30s"
    assert config["exporters"]["otlp_http/vector"]["endpoint"] == "http://100.64.0.1:4318"
    assert config["exporters"]["otlp_http/vector"]["sending_queue"]["storage"] == "file_storage"
    assert config["exporters"]["otlp_http/vector"]["retry_on_failure"]["max_elapsed_time"] == "0s"
    assert config["service"]["extensions"] == ["file_storage"]
    assert config["service"]["pipelines"]["logs"]["processors"] == ["memory_limiter", "batch"]

    repair = config["receivers"]["file_log/repair"]
    watchdog = config["receivers"]["file_log/watchdog"]
    assert repair["include"] == ["/data/data/com.termux/files/home/.stayturgid/logs/repair.jsonl"]
    assert watchdog["include"] == ["/sdcard/stayturgid/logs/watchdog.jsonl"]
    assert repair["storage"] == watchdog["storage"] == "file_storage"
    assert repair["start_at"] == watchdog["start_at"] == "end"
    # drop (not drop_quiet, M1-Q S-10): malformed lines are still dropped,
    # but the collector now logs the failure instead of discarding silently.
    assert repair["operators"][0]["on_error"] == "drop"
    assert watchdog["operators"][0]["on_error"] == "drop"


def test_boot_entrypoint_is_idempotent_and_supports_rollback(tmp_path: Path) -> None:
    stg = tmp_path / "stg"
    binary = stg / "bin/otelcol-contrib"
    config = stg / "otel-config.yaml"
    state_dir = stg / "state/otelcol"
    pidfile = stg / "run/otelcol.pid"
    binary.parent.mkdir(parents=True)
    config.write_text("service: {}\n")
    binary.write_text("#!/bin/bash\nwhile :; do sleep 1; done\n")
    binary.chmod(0o755)

    script = tmp_path / "start-otelcol.sh"
    script.write_text(
        _render(
            "start-otelcol.sh.j2",
            termux_home=str(tmp_path),
            termux_prefix="/usr",
            stayturgid_otelcol_binary=str(binary),
            stayturgid_otelcol_config=str(config),
            stayturgid_otelcol_pid_file=str(pidfile),
            stayturgid_otelcol_state_dir=str(state_dir),
        )
    )
    script.chmod(0o755)
    env = os.environ | {"STAYTURGID_HOME": str(stg), "PREFIX": "/usr"}

    command = ["/bin/bash", str(script)]
    subprocess.run(command, check=True, env=env, timeout=5)
    first_pid = int(pidfile.read_text())
    try:
        subprocess.run(command, check=True, env=env, timeout=5)
        assert int(pidfile.read_text()) == first_pid
        subprocess.run(command + ["stop"], check=True, env=env, timeout=5)
        assert not pidfile.exists()
        for _ in range(20):
            try:
                os.kill(first_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("rollback stop left the collector process alive")
    finally:
        try:
            os.kill(first_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_role_orders_mac_prerequisites_before_device_and_integrates_supervision() -> None:
    tasks = (ROLE / "tasks/otelcol.yml").read_text()
    assert tasks.index("Verify Vector API") < tasks.index("Detect device architecture")
    assert tasks.index("Cache the latest otelcol-contrib release archive") < tasks.index("Detect device architecture")
    assert "Deploy otelcol-contrib Termux supervisor integration" in tasks
    assert tasks.index("Probe installed otelcol-contrib runtime compatibility") < tasks.index(
        "Install otelcol-contrib Termux boot integration"
    )
    assert "Remove otelcol-contrib boot integration after runtime incompatibility" in tasks
    assert tasks.index("Remove otelcol-contrib boot integration") < tasks.index("Stop otelcol-contrib when disabled")
    defaults = (ROLE / "defaults/main.yml").read_text()
    assert ".termux/boot/start-otelcol.sh" in defaults
    assert "default(role_path" in defaults
    assert "ansible_config_file" not in defaults
    supervisor = (REPO / "device/termux/py/start_adb.py").read_text()
    assert "@heals: OTELCOL-RUNNING" in supervisor
    assert "_monitor_otelcol()" in supervisor


def test_otelcol_verify_self_heals_once_before_hard_failing() -> None:
    """#103: a self-heal retry must run between the first verify and any hard
    failure, using the same start/stop path as the "restart otelcol" handler,
    and the retry itself must be skippable when the first verify already
    passed (never fires on the happy path)."""
    tasks = (ROLE / "tasks/otelcol.yml").read_text()
    assert tasks.index("Apply pending otelcol-contrib restart") < tasks.index(
        "Probe the running otelcol-contrib version"
    )
    assert tasks.index("Probe the running otelcol-contrib version") < tasks.index(
        "Restart otelcol-contrib when the running version is older than the deployed one"
    )
    assert tasks.index("Restart otelcol-contrib when the running version is older than the deployed one") < tasks.index(
        "Verify otelcol-contrib is running"
    )
    assert "is version(_otelcol_version | string, '<')" in tasks
    assert "/proc/${pid}/exe" in tasks
    assert tasks.index("Verify otelcol-contrib is running") < tasks.index(
        "Restart otelcol-contrib when not found running"
    )
    assert tasks.index("Restart otelcol-contrib when not found running") < tasks.index(
        "Re-verify otelcol-contrib is running after self-heal restart"
    )
    assert "failed_when: false" in tasks
    assert "_otelcol_verify.rc | default(0) != 0" in tasks
    assert "stayturgid_otelcol_boot_script | quote }} stop" in tasks


def test_vector_reloads_launchd_job_when_credential_plist_changes() -> None:
    """vector's launchd lifecycle moved into the shared serverapp_launchd role.

    The reload semantics themselves are asserted in
    test_launchd_reload_semantics.py; what matters here is that vector still
    feeds its own plist-change signal into that shared lifecycle rather than
    quietly dropping it (the plist is where the credential interpolation flag
    lives, so a stale definition keeps the old credentials).
    """
    tasks = (REPO / "ansible/roles/serverapp_vector/tasks/main.yml").read_text()
    assert "--dangerously-allow-env-var-interpolation" in tasks
    assert "name: serverapp_launchd" in tasks
    assert 'sl_plist_changed: "{{ _vector_plist.changed | default(false) }}"' in tasks


def test_openobserve_uses_loopback_node_addresses_and_reloads_plist() -> None:
    template = (REPO / "ansible/roles/serverapp_openobserve/templates/openobserve.plist.j2").read_text()
    tasks = (REPO / "ansible/roles/serverapp_openobserve/tasks/main.yml").read_text()
    assert "ZO_HTTP_ADDR" in template
    assert "ZO_GRPC_ADDR" in template
    assert "ZO_BIND_ADDRESS" not in template
    assert "Boot out site-namespace openobserve when its launchd plist changed" in tasks
    assert "until: _oo_bootstrap.rc == 0" in tasks
