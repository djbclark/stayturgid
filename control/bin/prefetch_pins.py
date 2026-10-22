#!/usr/bin/env python3
"""Fill the control-node caches a deploy already trusts.

The launchd agent and the GitHub Action both run this. Each download takes the
same lock the deploy holds, so the two do not start two transfers of one file.
A partial is kept. A finished file whose sha256 is wrong is not cached.

Pins are read from the checkout. ``git fetch`` plus a fast-forward is attempted
first so a pin pushed from another clone is the one that gets fetched. A fetch
that cannot fast-forward leaves the checkout alone and still fills what is pinned
there. Pass ``--no-update`` to skip that.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

_LIB = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import asset_fetch  # noqa: E402

# Same digest the deploy uses for ~/.cache/stayturgid/apks/partials/<token>/.
_PARTIAL_FMT = "%s\0%s\0%s"
_SHA = re.compile(r"^[0-9a-f]{64}$")
# The otelcol role builds the URL from these two lines. If they change, refuse
# rather than fetch a file the deploy will not look for.
_OTEL_NAME_TMPL = "otelcol-contrib_{{ stayturgid_otelcol_version }}_{{ stayturgid_otelcol_archive_arch }}.tar.gz"
_OTEL_URL_TMPL = (
    "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/"
    "v{{ stayturgid_otelcol_version }}/{{ stayturgid_otelcol_archive_name }}"
)


class PrefetchError(RuntimeError):
    """One pin could not be filled. Other pins still run. A partial is kept."""


class ApkPin(NamedTuple):
    ident: str
    repo: str
    tag: str
    pattern: str
    sha256: str


class OtelPin(NamedTuple):
    version: str
    arch: str
    sha256: str
    url: str

    @property
    def archive_name(self) -> str:
        return f"otelcol-contrib_{self.version}_{self.arch}.tar.gz"


def default_apk_cache() -> Path:
    return Path(os.path.expanduser("~/.cache/stayturgid/apks"))


def otel_cache_dir(version: str) -> Path:
    return Path(os.path.expanduser(f"~/.cache/stayturgid/otelcol-contrib/{version}"))


def wanted_sha256(value: str) -> str:
    text = value.strip()
    if text.startswith("sha256:"):
        text = text[len("sha256:") :]
    text = text.lower()
    if not _SHA.fullmatch(text):
        raise PrefetchError(f"checksum is not a sha256 digest: {value!r}")
    return text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def partial_token(repo: str, tag: str, pattern: str) -> str:
    raw = _PARTIAL_FMT % (repo, tag or "", pattern or "")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def apk_cache_file(cache_dir: Path, sha: str) -> Path:
    return cache_dir / f"{sha}.apk"


def apk_lock_path(cache_dir: Path, sha: str) -> Path:
    # android_apk.cached_download locks "<sha256>.apk" + ".lock".
    return Path(str(apk_cache_file(cache_dir, sha)) + ".lock")


def apk_partial_dest(cache_dir: Path, pin: ApkPin, asset_name: str) -> Path:
    token = partial_token(pin.repo, pin.tag, pin.pattern)
    return cache_dir / "partials" / token / asset_name


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _top_scalars(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0] in " \t#-" or ":" not in line:
            continue
        key, val = line.split(":", 1)
        val = val.strip()
        if not val or val in {">", ">-", "|", "|-"}:
            continue
        found[key] = _unquote(val)
    return found


def _finish_apk(item: dict[str, str], pins: list[ApkPin], skipped: list[str]) -> None:
    ident = item.get("id") or "?"
    repo = item.get("gh_repo") or ""
    tag = item.get("gh_tag") or ""
    pattern = item.get("gh_pattern") or ""
    checksum = item.get("checksum") or ""
    if not (repo and tag and pattern and checksum):
        skipped.append(ident)
        return
    pins.append(ApkPin(ident, repo, tag, pattern, wanted_sha256(checksum)))


def load_apk_pins(text: str) -> tuple[list[ApkPin], list[str]]:
    """Read the bootstrap pin list without PyYAML.

    Launchd's Homebrew python does not have PyYAML. The keys this needs are
    plain scalars, including inside the comment block on the X11 pin.
    """
    pins: list[ApkPin] = []
    skipped: list[str] = []
    current: dict[str, str] | None = None
    in_list = False
    for line in text.splitlines():
        if line.startswith("stayturgid_bootstrap_apks:"):
            in_list = True
            continue
        if not in_list:
            continue
        if line and line[0] not in " \t#":
            break
        if line.startswith("  - id:"):
            if current is not None:
                _finish_apk(current, pins, skipped)
            current = {"id": _unquote(line.split(":", 1)[1])}
            continue
        if current is None or not line.startswith("    ") or line.startswith("    #") or ":" not in line:
            continue
        key, val = line.strip().split(":", 1)
        val = val.strip()
        if key in {"gh_repo", "gh_tag", "gh_pattern", "checksum"} and val and val not in {">", ">-", "|", "|-"}:
            current[key] = _unquote(val)
    if current is not None:
        _finish_apk(current, pins, skipped)
    return pins, skipped


def load_otel_pin(text: str) -> OtelPin:
    if _OTEL_NAME_TMPL not in text or _OTEL_URL_TMPL not in text:
        raise PrefetchError("otelcol URL template changed; prefetch_pins.py must be updated with it")
    data = _top_scalars(text)
    version = data.get("stayturgid_otelcol_version", "")
    arch = data.get("stayturgid_otelcol_archive_arch", "")
    digest = data.get("stayturgid_otelcol_archive_sha256", "")
    if not version or not arch or not digest:
        raise PrefetchError("otelcol pin is missing version, arch, or sha256")
    pin = OtelPin(version, arch, wanted_sha256(digest), "")
    url = (
        "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/"
        f"v{pin.version}/{pin.archive_name}"
    )
    return OtelPin(pin.version, pin.arch, pin.sha256, url)


def _gh_asset(repo: str, tag: str, pattern: str) -> tuple[str, str]:
    proc = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo, "--json", "assets"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit {proc.returncode}"
        raise PrefetchError(f"could not read {repo}@{tag}: {tail[:300]}")
    try:
        assets = json.loads(proc.stdout)["assets"]
    except (ValueError, KeyError, TypeError) as exc:
        raise PrefetchError(f"could not read assets for {repo}@{tag}") from exc
    matches = [item for item in assets if fnmatch.fnmatch(str(item.get("name", "")), pattern)]
    if len(matches) != 1 or not matches[0].get("url") or not matches[0].get("name"):
        raise PrefetchError(f"{repo}@{tag} pattern {pattern!r} matched {len(matches)} assets")
    name = str(matches[0]["name"])
    if name != Path(name).name or name in {".", ".."}:
        raise PrefetchError(f"{repo}@{tag} asset name is not a single file")
    return name, str(matches[0]["url"])


def _cache_otelcol():
    path = Path(__file__).resolve().parent / "cache_otelcol.py"
    spec = importlib.util.spec_from_file_location("stayturgid_cache_otelcol", path)
    if spec is None or spec.loader is None:
        raise PrefetchError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apk_state(pin: ApkPin, cache_dir: Path) -> str:
    cached = apk_cache_file(cache_dir, pin.sha256)
    if cached.is_file() and sha256_file(cached) == pin.sha256:
        return "hit"
    return "miss"


def ensure_apk(pin: ApkPin, cache_dir: Path, timeout: int) -> str:
    """Download one pin under the deploy's lock. Returns ``hit`` or ``fetched``."""
    import fcntl

    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = apk_cache_file(cache_dir, pin.sha256)
    lock_path = apk_lock_path(cache_dir, pin.sha256)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if cached.is_file() and sha256_file(cached) == pin.sha256:
            return "hit"
        name, url = _gh_asset(pin.repo, pin.tag, pin.pattern)
        dest = apk_partial_dest(cache_dir, pin, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            asset_fetch.fetch(url, dest, timeout)
        except asset_fetch.FetchError as exc:
            raise PrefetchError(str(exc)) from exc
        actual = sha256_file(dest)
        if actual != pin.sha256:
            dest.unlink(missing_ok=True)
            Path(str(dest) + ".aria2").unlink(missing_ok=True)
            raise PrefetchError(f"download of {pin.ident} finished with the wrong sha256. The bad file was deleted.")
        partial = Path(str(cached) + ".part")
        shutil.copyfile(dest, partial)
        os.replace(partial, cached)
        return "fetched"


def otel_state(pin: OtelPin) -> str:
    archive = otel_cache_dir(pin.version) / pin.archive_name
    if archive.is_file() and sha256_file(archive) == pin.sha256:
        return "hit"
    return "miss"


def ensure_otel(pin: OtelPin, timeout: int) -> str:
    cache_dir = otel_cache_dir(pin.version)
    state = otel_state(pin)
    module = _cache_otelcol()
    try:
        module.ensure_cached(
            url=pin.url,
            expected_sha256=pin.sha256,
            cache_dir=cache_dir,
            architecture=pin.arch,
            timeout_seconds=timeout,
        )
    except module.ArtifactError as exc:
        raise PrefetchError(str(exc)) from exc
    return "hit" if state == "hit" else "fetched"


def update_checkout(repo: Path) -> str:
    """Fast-forward to origin/master. Never stashes and never rewrites local commits."""
    try:
        fetch = subprocess.run(
            ["git", "fetch", "origin", "master"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "checkout not updated (git fetch failed)"
    if fetch.returncode != 0:
        return "checkout not updated (git fetch failed)"
    try:
        merge = subprocess.run(
            ["git", "merge", "--ff-only", "origin/master"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "checkout not updated (git merge failed)"
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    sha = head.stdout.strip() or "unknown"
    if merge.returncode != 0:
        return f"checkout left at {sha} (origin/master is not a fast-forward)"
    return f"checkout {sha}"


def _window(explicit: int | None) -> int:
    if explicit is not None:
        if explicit <= 0:
            raise PrefetchError(f"download time window must be positive, got {explicit}")
        return explicit
    raw = os.environ.get("STAYTURGID_DOWNLOAD_TIMEOUT_SECONDS", "1800")
    try:
        window = int(raw)
    except ValueError as exc:
        raise PrefetchError(f"STAYTURGID_DOWNLOAD_TIMEOUT_SECONDS is not an integer: {raw}") from exc
    if window <= 0:
        raise PrefetchError(f"download time window must be positive, got {window}")
    return window


def _paths(repo: Path) -> tuple[Path, Path]:
    apk = repo / "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/defaults/main.yml"
    otel = repo / "ansible_collections/stayturgid/termux/roles/termux_userland/defaults/main.yml"
    return apk, otel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Report hit or miss. Do not download.")
    parser.add_argument("--no-update", action="store_true", help="Do not fetch or fast-forward the checkout.")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(line_buffering=True)
    repo = args.repo_root.expanduser().resolve()
    # Empty on purpose disables the host, same as deploy_fleet.repo_env.
    os.environ.setdefault("STAYTURGID_FETCH_SSH_HOST", "vps-primary")
    try:
        window = _window(args.timeout)
    except PrefetchError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not args.no_update and not args.dry_run:
        print(update_checkout(repo))
    apk_file, otel_file = _paths(repo)
    failures: list[str] = []
    try:
        pins, skipped = load_apk_pins(apk_file.read_text())
        otel = load_otel_pin(otel_file.read_text())
    except (OSError, PrefetchError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for ident in skipped:
        print(f"skip apk {ident}")
    cache_dir = default_apk_cache()
    for pin in pins:
        try:
            if args.dry_run:
                print(f"{apk_state(pin, cache_dir)} apk {pin.ident}")
                continue
            print(f"{ensure_apk(pin, cache_dir, window)} apk {pin.ident}")
        except PrefetchError as exc:
            failures.append(f"{pin.ident}: {exc}")
            print(f"failed apk {pin.ident}: {exc}", file=sys.stderr)
    try:
        if args.dry_run:
            print(f"{otel_state(otel)} otelcol {otel.version}")
        else:
            print(f"{ensure_otel(otel, window)} otelcol {otel.version}")
    except PrefetchError as exc:
        failures.append(f"otelcol: {exc}")
        print(f"failed otelcol {otel.version}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
