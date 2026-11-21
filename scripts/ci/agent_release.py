#!/usr/bin/env python3
"""Version, sign and publish the stayturgid-agent APK built by .github/workflows/agent-release.yml.

Subcommands (the publish job runs the last three as separate steps, so no step holds both the
release key and the write token, and the step that parses the untrusted APK first holds neither):

  version                          print the rolling version of this run as `code=..`/`name=..` lines
                                   (append them to $GITHUB_OUTPUT and export them to Gradle).
  check   --apk F --code N         no secrets: F must carry versionCode N.
  sign    --apk F --out G --code N holds the key: sign F as G, check signer and versionCode.
  release --apk G --code N         holds the token: publish G as the GitHub release agent-r<N> with
                                   one asset, app-release.apk, then prune old ones.

Versioning: versionCode = GITHUB_RUN_NUMBER + CODE_OFFSET, so every build is newer than the last
and newer than the hand-made agent-v0.9.19 (versionCode 37); versionName = 0.9.<code>+<sha8>.
The release tag is agent-r<versionCode>. Installed apps compare the digest of the release asset
(bootstrap_apks, gh_latest with gh_tag_prefix agent-r) and refuse any APK whose signer is not the
fleet's release certificate (signer_sha256), so a rolling build never needs a pin.

`sign` reads the key from the environment of the `agent-release` Actions environment (master only),
writes it to a 0600 file in a fresh temporary directory, hands apksigner the passwords through the
environment (never argv) and removes the file again. Every other subprocess runs without the key.
`sign` refuses an APK whose signer is not the fleet's release certificate or whose versionCode
differs from the one it was built with; `release` refuses one older than a release already
published. The key never reaches the Gradle build.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Run numbers restart at 1 if the workflow file is renamed (a new workflow), which would make every
# publish look like a downgrade and fail closed: raise the offset by the old run count then.
CODE_OFFSET = 100  # first rolling build (run 1) is versionCode 101, above the hand-made 37
VERSION_BASE = "0.9"
TAG_PREFIX = "agent-r"
ASSET_NAME = "app-release.apk"
KEEP_RELEASES = 10
# SHA-256 of the fleet's release certificate (keytool -list -v on agent-release.jks, alias agent).
SIGNER_SHA256 = "35bbc3d1a93c2a726df14bcc066bdc791f7f55f21b57d9455da27439c5ff9b6a"
# The alias is not secret (it is `agent`); a secret would be masked wherever the word appears in the log.
DEFAULT_ALIAS = "agent"
SECRET_ENV = {
    "keystore": "STAYTURGID_AGENT_KEYSTORE_B64",
    "store_password": "STAYTURGID_AGENT_KEYSTORE_PASSWORD",
    "key_password": "STAYTURGID_AGENT_KEY_PASSWORD",
}


def version_code(run_number: int) -> int:
    return run_number + CODE_OFFSET


def version_name(code: int, sha: str) -> str:
    return f"{VERSION_BASE}.{code}+{sha[:8]}"


def tag_for(code: int) -> str:
    return f"{TAG_PREFIX}{code}"


def code_of_tag(tag: str) -> int | None:
    match = re.fullmatch(re.escape(TAG_PREFIX) + r"(\d+)", tag)
    return int(match.group(1)) if match else None


def releases_to_prune(tags: list[str], keep: int = KEEP_RELEASES) -> list[str]:
    """Tags of the agent-r releases beyond the `keep` highest versionCodes; other tags are never listed."""
    coded = sorted(((code_of_tag(t), t) for t in tags if code_of_tag(t) is not None), reverse=True)
    return [t for _code, t in coded[keep:]]


def newest_code(tags: list[str]) -> int:
    return max((c for c in map(code_of_tag, tags) if c is not None), default=0)


def is_complete(release: dict[str, object]) -> bool:
    """A published (non-draft) release that carries the one asset the fleet installs."""
    assets = release.get("assets")
    names = [a.get("name") for a in assets if isinstance(a, dict)] if isinstance(assets, list) else []
    return not release.get("draft") and names == [ASSET_NAME]


def scrubbed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment without the signing secrets, plus what one command needs."""
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV.values()}
    env.update(extra or {})
    return env


def run(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, capture_output=True, text=True, env=env or scrubbed_env(), check=False)
    if result.returncode != 0:
        # argv never holds a secret (passwords travel in the environment), so naming it is safe.
        sys.exit(f"{' '.join(argv[:3])} failed (rc {result.returncode}): {(result.stderr or result.stdout)[:800]}")
    return result


def apksigner() -> str:
    sdk = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "")
    found = sorted(
        (sdk / "build-tools").glob("*/apksigner"),
        key=lambda p: [int(x) for x in p.parent.name.split(".") if x.isdigit()],
    )
    if not found:
        sys.exit(f"no apksigner under {sdk}/build-tools")
    return str(found[-1])


def aapt2() -> str:
    return str(Path(apksigner()).parent / "aapt2")


def apk_version_code(apk: Path) -> int:
    out = run([aapt2(), "dump", "badging", str(apk)]).stdout
    match = re.search(r"versionCode='(\d+)'", out)
    if not match:
        sys.exit("aapt2 reported no versionCode")
    return int(match.group(1))


def sign(unsigned: Path, signed: Path) -> None:
    missing = [name for name in SECRET_ENV.values() if not os.environ.get(name)]
    if missing:
        sys.exit("missing signing secrets (names only): " + ", ".join(missing))
    with tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP")) as tmp:
        keystore = Path(tmp) / "agent-release.jks"
        fd = os.open(keystore, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(base64.b64decode(os.environ[SECRET_ENV["keystore"]]))
        try:
            # apksigner gets the two passwords and nothing else of the secrets; aapt2, gh and the
            # other tools never see even those.
            env = scrubbed_env(
                {
                    "AGENT_STORE_PASS": os.environ[SECRET_ENV["store_password"]],
                    "AGENT_KEY_PASS": os.environ[SECRET_ENV["key_password"]],
                }
            )
            run(
                [
                    apksigner(), "sign",
                    "--ks", str(keystore),
                    "--ks-key-alias", os.environ.get("AGENT_KEY_ALIAS") or DEFAULT_ALIAS,
                    "--ks-pass", "env:AGENT_STORE_PASS",
                    "--key-pass", "env:AGENT_KEY_PASS",
                    "--out", str(signed), str(unsigned),
                ],
                env=env,
            )  # fmt: skip
        finally:
            keystore.unlink(missing_ok=True)


def check_signer(signed: Path) -> None:
    out = run([apksigner(), "verify", "--print-certs", str(signed)]).stdout
    digests = set(re.findall(r"certificate SHA-256 digest: ([0-9a-f]{64})", out))
    if digests != {SIGNER_SHA256}:
        sys.exit("the signed APK does not carry exactly the fleet release certificate; not publishing")


def gh_json(args: list[str]) -> list[dict[str, object]]:
    data = json.loads(run(["gh", *args]).stdout or "[]")
    assert isinstance(data, list)
    return data


def all_releases(repo: str) -> list[dict[str, object]]:
    releases: list[dict[str, object]] = []
    page = 1
    while True:
        batch = gh_json(["api", f"repos/{repo}/releases?per_page=100&page={page}"])
        releases += batch
        if len(batch) < 100:
            return releases
        page += 1


def published_tags(releases: list[dict[str, object]]) -> list[str]:
    return [str(r["tag_name"]) for r in releases if not r.get("draft")]


def cmd_version(_args: argparse.Namespace) -> None:
    code = version_code(int(os.environ["GITHUB_RUN_NUMBER"]))
    print(f"code={code}")
    print(f"name={version_name(code, os.environ['GITHUB_SHA'])}")


def cmd_check(args: argparse.Namespace) -> None:
    found = apk_version_code(Path(args.apk))
    if found != args.code:
        sys.exit(f"{args.apk} carries versionCode {found}, expected {args.code}")
    print(f"versionCode {found} ok")


def cmd_sign(args: argparse.Namespace) -> None:
    out = Path(args.out)
    sign(Path(args.apk), out)
    check_signer(out)
    if apk_version_code(out) != args.code:
        sys.exit("the signed APK lost its versionCode")
    print(f"signed {out.name}: sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}")


def cmd_release(args: argparse.Namespace) -> None:
    repo, sha = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    code, tag = args.code, tag_for(args.code)
    name = version_name(code, sha)
    apk = Path(args.apk)
    if apk.name != ASSET_NAME:
        sys.exit(f"the release asset must be named {ASSET_NAME}, not {apk.name}")
    releases = all_releases(repo)
    existing = [r for r in releases if r["tag_name"] == tag]
    if any(is_complete(r) for r in existing):
        print(f"{tag} is already published; nothing to do")
        return
    if newest_code(published_tags(releases)) > code:
        sys.exit(f"{tag} is older than the published agent-r{newest_code(published_tags(releases))}; not publishing")
    if existing:  # a draft or an asset-less release left by a failed earlier attempt
        print(f"removing the incomplete {tag}")
        # A draft has no git tag yet, so --cleanup-tag would fail on it after deleting the draft.
        tagged = [] if all(r.get("draft") for r in existing) else ["--cleanup-tag"]
        run(["gh", "release", "delete", tag, "--repo", repo, *tagged, "--yes"])
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    notes = (
        f"stayturgid-agent {name} (versionCode {code}), built from {sha} and signed by CI.\n\n"
        f"Build: {server}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}\n"
        f"APK SHA-256: `{digest}`\n"
        f"Signer certificate SHA-256: `{SIGNER_SHA256}`\n"
    )
    run(
        [
            "gh", "release", "create", tag, str(apk),
            "--repo", repo,
            "--target", sha,
            "--title", f"stayturgid-agent {name}",
            "--notes", notes,
            "--latest=false",
        ]
    )  # fmt: skip
    print(f"published {tag}: sha256 {digest}")
    for stale in releases_to_prune(published_tags(all_releases(repo))):
        print(f"pruning {stale}")
        run(["gh", "release", "delete", stale, "--repo", repo, "--cleanup-tag", "--yes"])


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version").set_defaults(fn=cmd_version)
    for name, fn, needs_out in (("check", cmd_check, False), ("sign", cmd_sign, True), ("release", cmd_release, False)):
        p = sub.add_parser(name)
        p.add_argument("--apk", required=True)
        p.add_argument("--code", type=int, required=True)
        if needs_out:
            p.add_argument("--out", required=True)
        p.set_defaults(fn=fn)
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main(sys.argv[1:])
