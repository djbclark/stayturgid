from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import signal
import subprocess
import tarfile
import time
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


def _artifact(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "otelcol-contrib_0.156.0_linux_arm64.tar.gz"
    data = _aarch64_elf(b"collector")
    info = tarfile.TarInfo("otelcol-contrib")
    info.size = len(data)
    info.mode = 0o755
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    return archive, digest


def _render(name: str, **variables: object) -> str:
    environment = Environment(
        loader=FileSystemLoader(str(ROLE / "templates")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    return environment.get_template(name).render(**variables)


def test_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"not the pinned release")
    with pytest.raises(cache_otelcol.ArtifactError, match="SHA-256 mismatch"):
        cache_otelcol.verify_checksum(artifact, "0" * 64)


def test_corrupt_cached_archive_is_not_silently_replaced(tmp_path: Path) -> None:
    archive, digest = _artifact(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cached_archive = cache_dir / archive.name
    cached_archive.write_bytes(b"corrupt")
    with pytest.raises(cache_otelcol.ArtifactError, match="SHA-256 mismatch"):
        cache_otelcol.ensure_cached(
            url=archive.as_uri(),
            expected_sha256=digest,
            cache_dir=cache_dir,
            architecture="linux_arm64",
        )


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
    archive, digest = _artifact(tmp_path)
    cache_dir = tmp_path / "cache"
    assert cache_otelcol.ensure_cached(
        url=archive.as_uri(),
        expected_sha256=digest,
        cache_dir=cache_dir,
        architecture="linux_arm64",
    )
    assert not cache_otelcol.ensure_cached(
        url=archive.as_uri(),
        expected_sha256=digest,
        cache_dir=cache_dir,
        architecture="linux_arm64",
    )
    cached_binary = cache_dir / "otelcol-contrib"
    assert cached_binary.stat().st_mode & 0o111
    cache_otelcol.validate_linux_arm64_elf(cached_binary)


def test_corrupt_cached_binary_fails_closed(tmp_path: Path) -> None:
    archive, digest = _artifact(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_otelcol.ensure_cached(
        url=archive.as_uri(),
        expected_sha256=digest,
        cache_dir=cache_dir,
        architecture="linux_arm64",
    )
    (cache_dir / "otelcol-contrib").write_bytes(_aarch64_elf(b"tampered"))
    with pytest.raises(cache_otelcol.ArtifactError, match="does not match"):
        cache_otelcol.ensure_cached(
            url=archive.as_uri(),
            expected_sha256=digest,
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
    assert config["exporters"]["otlphttp/vector"]["endpoint"] == "http://100.64.0.1:4318"
    assert config["exporters"]["otlphttp/vector"]["sending_queue"]["storage"] == "file_storage"
    assert config["exporters"]["otlphttp/vector"]["retry_on_failure"]["max_elapsed_time"] == "0s"
    assert config["service"]["extensions"] == ["file_storage"]
    assert config["service"]["pipelines"]["logs"]["processors"] == ["memory_limiter", "batch"]

    repair = config["receivers"]["filelog/repair"]
    watchdog = config["receivers"]["filelog/watchdog"]
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
    assert tasks.index("Cache and verify pinned") < tasks.index("Detect device architecture")
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
    tasks = (REPO / "ansible/roles/serverapp_vector/tasks/main.yml").read_text()
    assert "Boot out site-namespace vector when its launchd plist changed" in tasks
    assert "--dangerously-allow-env-var-interpolation" in tasks
    assert "_vector_plist_reload_bootout.changed | default(false)" in tasks
    assert "until: _vector_bootstrap.rc == 0" in tasks
    assert "not (_vector_plist.changed | default(false))" in tasks


def test_openobserve_uses_loopback_node_addresses_and_reloads_plist() -> None:
    template = (REPO / "ansible/roles/serverapp_openobserve/templates/openobserve.plist.j2").read_text()
    tasks = (REPO / "ansible/roles/serverapp_openobserve/tasks/main.yml").read_text()
    assert "ZO_HTTP_ADDR" in template
    assert "ZO_GRPC_ADDR" in template
    assert "ZO_BIND_ADDRESS" not in template
    assert "Boot out site-namespace openobserve when its launchd plist changed" in tasks
    assert "until: _oo_bootstrap.rc == 0" in tasks
