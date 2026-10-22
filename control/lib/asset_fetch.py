"""Fetch one HTTP asset, fastest robust path first.

One call uses one writer. A partial, or an aria2 sidecar, stays with aria2.
Otherwise, when STAYTURGID_FETCH_SSH_HOST is set, a 1 MiB probe may select that
host if it sustains at least 2 MiB/s. The host curls the URL (the URL is on
stdin, never in argv) and the missing tail is appended here. Anything slower,
or an SSH failure before local bytes exist, falls through to aria2 on this
machine. urllib is only the stand-in when aria2c is missing and nothing has
been written yet.

vps-primary reaches the GitHub CDN at datacenter speed, but the copy back to
this Mac was slower than a direct download (2026-10-22). The probe is what
keeps that path from becoming the default.

The caller's timeout is the deploy window. A timeout, or a transfer error
after local bytes exist, raises FetchError and does not start a second writer.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import BinaryIO

PROBE_BYTES = 1024 * 1024
PROBE_SECONDS = 3.0
PROBE_MIN_BPS = 2_000_000
REMOTE_CACHE = "/var/cache/stayturgid/fetch"

# $1 is the hex cache key. The URL arrives on stdin so it is not in argv.
REMOTE_CURL = (
    """
set -eu
umask 077
url=$(cat)
case "$1" in
  *[!0-9a-f]*|"") echo "refusing cache key" >&2; exit 2 ;;
esac
dir="%s/$1"
mkdir -p "$dir"
curl -fL --retry 5 --retry-delay 2 -C - --output "$dir/asset" -- "$url"
wc -c < "$dir/asset" | tr -d '[:space:]'
"""
    % REMOTE_CACHE
)

ARIA2_ARGS = [
    "--continue=true",
    "--auto-file-renaming=false",
    "--max-connection-per-server=4",
    "--split=4",
    "--min-split-size=4M",
    "--max-tries=10",
    "--retry-wait=5",
    "--timeout=60",
    "--file-allocation=none",
    "--console-log-level=warn",
    "--summary-interval=0",
]


class FetchError(RuntimeError):
    """The one transfer missed the window or failed. The partial is still there."""


def cache_key(url: str) -> str:
    """Identity of an asset. Query and fragment tokens are not part of it."""
    parts = urllib.parse.urlsplit(url)
    bare = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return hashlib.sha256(bare.encode()).hexdigest()


def _kept(destination: Path) -> str:
    if destination.exists() and destination.stat().st_size > 0:
        return f"The partial file was kept at {destination} and the next deploy continues it."
    return "No partial file was left behind."


def _window_error(destination: Path, timeout_seconds: int) -> FetchError:
    return FetchError(
        f"download of {destination.name} did not finish within {timeout_seconds}s. "
        f"The transfer was stopped. {_kept(destination)}"
    )


def _failed(destination: Path, detail: str) -> FetchError:
    text = detail.strip().replace("\n", " ")
    return FetchError(f"download of {destination.name} failed. {_kept(destination)} {text[:500]}".rstrip())


def _have(destination: Path) -> int:
    try:
        return destination.stat().st_size
    except OSError:
        return 0


def partial_started(destination: Path) -> bool:
    return _have(destination) > 0 or Path(str(destination) + ".aria2").exists()


def _host_ok(host: str) -> bool:
    if not host or len(host) > 80:
        return False
    return all(char.isalnum() or char in "._-" for char in host)


def _ssh(host: str, connect_timeout: int, remote: list[str]) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "ServerAliveInterval=30",
        host,
        *remote,
    ]


def _run(
    cmd: list[str],
    timeout: float,
    *,
    input_bytes: bytes | None = None,
    stdout: int | BinaryIO | None = subprocess.PIPE,
) -> subprocess.CompletedProcess[bytes]:
    if timeout <= 0:
        raise subprocess.TimeoutExpired(cmd, timeout)
    return subprocess.run(
        cmd,
        input=input_bytes,
        stdout=stdout,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _probe_fast(host: str, timeout: float) -> bool:
    if timeout <= 0:
        return False
    cmd = _ssh(host, 5, ["dd", "if=/dev/zero", "bs=1024", "count=1024", "status=none"])
    started = time.monotonic()
    try:
        completed = _run(cmd, min(PROBE_SECONDS, timeout))
    except (OSError, subprocess.TimeoutExpired):
        return False
    elapsed = max(time.monotonic() - started, 0.001)
    if completed.returncode != 0 or len(completed.stdout) < PROBE_BYTES:
        return False
    return len(completed.stdout) / elapsed >= PROBE_MIN_BPS


def _remote_size(host: str, url: str, timeout: float) -> int | None:
    key = cache_key(url)
    cmd = _ssh(host, 8, ["bash", "-c", REMOTE_CURL, "fetch", key])
    completed = _run(cmd, timeout, input_bytes=url.encode())
    if completed.returncode != 0:
        return None
    text = completed.stdout.decode("utf-8", "replace").strip()
    if not text.isdigit():
        return None
    return int(text)


def _pull_tail(host: str, url: str, destination: Path, timeout: float) -> bool:
    key = cache_key(url)
    remote = f"{REMOTE_CACHE}/{key}/asset"
    have = _have(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = _ssh(host, 8, ["tail", "-c", f"+{have + 1}", remote])
    with destination.open("ab") as out:
        completed = _run(cmd, timeout, stdout=out)
    return completed.returncode == 0


def try_vps(host: str, url: str, destination: Path, timeout_seconds: int) -> bool:
    """Finish destination via host. False means the caller should use aria2.

    Raises FetchError when this path used the window, or wrote local bytes and
    then failed. The caller must not start another writer after that.
    """
    if partial_started(destination) or not _host_ok(host):
        return False
    deadline = time.monotonic() + timeout_seconds
    if not _probe_fast(host, min(PROBE_SECONDS, deadline - time.monotonic())):
        return False
    try:
        left = deadline - time.monotonic()
        if left <= 0:
            raise subprocess.TimeoutExpired("ssh", timeout_seconds)
        size = _remote_size(host, url, left)
    except subprocess.TimeoutExpired as exc:
        raise _window_error(destination, timeout_seconds) from exc
    except OSError as exc:
        if _have(destination) > 0:
            raise _failed(destination, str(exc)) from exc
        return False
    if size is None or size <= 0:
        if _have(destination) > 0:
            raise _failed(destination, "remote cache did not report a size")
        return False
    if _have(destination) == size:
        return True
    before = _have(destination)
    try:
        left = deadline - time.monotonic()
        if left <= 0:
            raise subprocess.TimeoutExpired("ssh", timeout_seconds)
        pulled = _pull_tail(host, url, destination, left)
    except subprocess.TimeoutExpired as exc:
        raise _window_error(destination, timeout_seconds) from exc
    except OSError as exc:
        if _have(destination) > before:
            raise _failed(destination, str(exc)) from exc
        return False
    if not pulled:
        if _have(destination) > before:
            raise _failed(destination, "copy from the cache host stopped")
        return False
    if _have(destination) != size:
        raise _failed(destination, f"remote has {size} bytes, local has {_have(destination)}")
    return True


def _download_urllib(url: str, destination: Path, timeout_seconds: int) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "stayturgid-fetch/1"})
    try:
        # The URL is the pinned artifact. The sha256 check happens before use.
        with (
            urllib.request.urlopen(request, timeout=timeout_seconds) as response,  # nosec B310
            destination.open("wb") as out,
        ):
            shutil.copyfileobj(response, out)
    except (OSError, urllib.error.URLError) as exc:
        raise _failed(destination, str(exc)) from exc


def download_aria2(url: str, destination: Path, timeout_seconds: int) -> None:
    """One aria2 transfer into destination. A miss leaves the partial in place."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    aria2c = shutil.which("aria2c")
    if aria2c is None:
        if partial_started(destination):
            raise _failed(destination, f"aria2c is required to continue the partial file at {destination}")
        _download_urllib(url, destination, timeout_seconds)
        return
    cmd = [
        aria2c,
        *ARIA2_ARGS,
        "--dir",
        str(destination.parent),
        "--out",
        destination.name,
        url,
    ]
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise _window_error(destination, timeout_seconds) from exc
    sidecar = Path(str(destination) + ".aria2")
    if completed.returncode != 0 or not destination.is_file() or sidecar.exists():
        detail = (completed.stderr or completed.stdout or f"aria2c exit {completed.returncode}").strip()
        raise _failed(destination, detail)


def fetch(url: str, destination: Path, timeout_seconds: int, host: str | None = None) -> None:
    """Fetch url into destination. host defaults to STAYTURGID_FETCH_SSH_HOST."""
    if timeout_seconds <= 0:
        raise _window_error(destination, timeout_seconds)
    destination.parent.mkdir(parents=True, exist_ok=True)
    chosen = host if host is not None else os.environ.get("STAYTURGID_FETCH_SSH_HOST", "")
    chosen = chosen.strip()
    deadline = time.monotonic() + timeout_seconds
    if chosen and not partial_started(destination):
        if try_vps(chosen, url, destination, timeout_seconds):
            return
    remaining = int(deadline - time.monotonic())
    if remaining <= 0:
        raise _window_error(destination, timeout_seconds)
    download_aria2(url, destination, remaining)
