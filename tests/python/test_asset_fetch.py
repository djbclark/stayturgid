"""The shared fetcher: a fast host when a probe says so, otherwise one aria2 transfer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import asset_fetch
import pytest

URL = "https://example.invalid/releases/app.bin?token=secret"


class Result:
    def __init__(
        self,
        returncode: int = 0,
        stdout: bytes | str = b"",
        stderr: bytes | str = b"",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch: pytest.MonkeyPatch, run) -> None:
    monkeypatch.setattr(asset_fetch.subprocess, "run", run)
    monkeypatch.setattr(asset_fetch.shutil, "which", lambda name: "/usr/bin/aria2c" if name == "aria2c" else None)


def _fast_body(body: bytes):
    """Probe passes, the remote cache reports len(body), and tail writes body."""

    def run(cmd, **kwargs):
        if "if=/dev/zero" in cmd:
            assert "secret" not in " ".join(cmd)
            return Result(stdout=b"x" * asset_fetch.PROBE_BYTES)
        if "bash" in cmd and "-c" in cmd:
            assert "secret" not in " ".join(str(part) for part in cmd)
            assert kwargs["input"] == URL.encode()
            assert cmd[-1] == asset_fetch.cache_key(URL)
            return Result(stdout=str(len(body)).encode() + b"\n")
        if "tail" in cmd:
            assert cmd[cmd.index("-c") + 1] == "+1"
            kwargs["stdout"].write(body)
            return Result()
        raise AssertionError(cmd)

    return run


def test_cache_key_ignores_the_query_token() -> None:
    bare = "https://example.invalid/releases/app.bin"
    assert asset_fetch.cache_key(URL) == asset_fetch.cache_key(bare + "?token=other")
    assert asset_fetch.cache_key(URL) == asset_fetch.cache_key(bare)
    assert asset_fetch.cache_key(URL) != asset_fetch.cache_key(bare + ".2")


def test_partial_or_sidecar_never_switches_to_the_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin"

    def boom(*_args, **_kwargs):
        raise AssertionError("ssh")

    _patch_run(monkeypatch, boom)
    dest.write_bytes(b"some")
    assert asset_fetch.try_vps("vps-primary", URL, dest, 30) is False
    dest.unlink()
    Path(str(dest) + ".aria2").write_bytes(b"sidecar")
    assert asset_fetch.try_vps("vps-primary", URL, dest, 30) is False


def test_bad_host_and_a_slow_probe_fall_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin"

    def boom(*_args, **_kwargs):
        raise AssertionError("ssh")

    _patch_run(monkeypatch, boom)
    assert asset_fetch.try_vps("-oProxyCommand=evil", URL, dest, 30) is False

    def slow(cmd, **_kwargs):
        assert "if=/dev/zero" in cmd
        return Result(stdout=b"x" * 100)

    _patch_run(monkeypatch, slow)
    assert asset_fetch.try_vps("vps-primary", URL, dest, 30) is False

    def stalled(cmd, **_kwargs):
        raise subprocess.TimeoutExpired(cmd, 3)

    _patch_run(monkeypatch, stalled)
    assert asset_fetch.try_vps("vps-primary", URL, dest, 30) is False

    def refused(cmd, **_kwargs):
        if "if=/dev/zero" in cmd:
            return Result(stdout=b"x" * asset_fetch.PROBE_BYTES)
        return Result(returncode=1, stderr=b"connection refused")

    _patch_run(monkeypatch, refused)
    assert asset_fetch.try_vps("vps-primary", URL, dest, 30) is False
    assert not dest.exists() or dest.stat().st_size == 0


def test_fast_host_streams_the_missing_tail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin"
    _patch_run(monkeypatch, _fast_body(b"hello"))
    assert asset_fetch.try_vps("vps-primary", URL, dest, 30) is True
    assert dest.read_bytes() == b"hello"


def test_host_timeout_keeps_the_partial_and_does_not_ask_aria2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin"

    def run(cmd, **kwargs):
        if "if=/dev/zero" in cmd:
            return Result(stdout=b"x" * asset_fetch.PROBE_BYTES)
        if "tail" in cmd:
            kwargs["stdout"].write(b"ab")
            raise subprocess.TimeoutExpired(cmd, 30)
        if "bash" in cmd:
            return Result(stdout=b"5\n")
        raise AssertionError("second writer")

    _patch_run(monkeypatch, run)
    with pytest.raises(asset_fetch.FetchError, match="did not finish within 30s") as raised:
        asset_fetch.fetch(URL, dest, 30, host="vps-primary")
    assert "The transfer was stopped" in str(raised.value)
    assert "partial file was kept" in str(raised.value)
    assert dest.read_bytes() == b"ab"


def test_short_copy_is_a_failed_transfer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin"

    def run(cmd, **kwargs):
        if "if=/dev/zero" in cmd:
            return Result(stdout=b"x" * asset_fetch.PROBE_BYTES)
        if "bash" in cmd and "-c" in cmd:
            return Result(stdout=b"5\n")
        if "tail" in cmd:
            kwargs["stdout"].write(b"ab")
            return Result()
        raise AssertionError(cmd)

    _patch_run(monkeypatch, run)
    with pytest.raises(asset_fetch.FetchError, match="download of app.bin failed") as raised:
        asset_fetch.try_vps("vps-primary", URL, dest, 30)
    assert "remote has 5 bytes, local has 2" in str(raised.value)
    assert dest.read_bytes() == b"ab"


def test_fetch_continues_a_partial_with_aria2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin.partial"
    dest.write_bytes(b"some")

    def run(cmd, **_kwargs):
        assert "if=/dev/zero" not in cmd
        assert "--continue=true" in cmd
        assert "--quiet" not in cmd
        assert not any(str(part).startswith("--lowest-speed-limit") for part in cmd)
        return Result()

    _patch_run(monkeypatch, run)
    asset_fetch.fetch(URL, dest, 30, host="vps-primary")
    assert dest.read_bytes() == b"some"


def test_slow_probe_falls_through_to_one_aria2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin"
    seen: list[list[str]] = []

    def run(cmd, **_kwargs):
        seen.append(list(cmd))
        if "if=/dev/zero" in cmd:
            return Result(stdout=b"x" * 10)
        target = Path(cmd[cmd.index("--dir") + 1]) / cmd[cmd.index("--out") + 1]
        target.write_bytes(b"PK")
        return Result()

    _patch_run(monkeypatch, run)
    asset_fetch.fetch(URL, dest, 30, host="vps-primary")
    assert dest.read_bytes() == b"PK"
    assert sum(1 for cmd in seen if "if=/dev/zero" in cmd) == 1
    assert sum(1 for cmd in seen if any(part.endswith("aria2c") for part in cmd)) == 1


def test_aria2_timeout_names_the_window_and_keeps_the_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin.partial"
    dest.write_bytes(b"some")

    def expire(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    _patch_run(monkeypatch, expire)
    with pytest.raises(asset_fetch.FetchError, match="did not finish within 30s") as raised:
        asset_fetch.download_aria2(URL, dest, 30)
    assert "partial file was kept" in str(raised.value)
    assert dest.read_bytes() == b"some"


def test_aria2_failure_does_not_hide_the_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "app.bin.partial"
    dest.write_bytes(b"some")

    def fail(_cmd, **_kwargs):
        return Result(returncode=1, stdout="", stderr="connection reset")

    _patch_run(monkeypatch, fail)
    with pytest.raises(asset_fetch.FetchError, match="download of app.bin.partial failed") as raised:
        asset_fetch.download_aria2(URL, dest, 30)
    assert "connection reset" in str(raised.value)
    assert dest.read_bytes() == b"some"
