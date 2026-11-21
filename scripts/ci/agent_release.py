#!/usr/bin/env python3
"""Version, sign and publish the stayturgid-agent APK built by .github/workflows/agent-release.yml.

Subcommands:

  version                       print the rolling version of this run as `code=..`/`name=..` lines
                                (append them to $GITHUB_OUTPUT and export them to Gradle).
  publish --apk F --code N      sign F, check the result and publish it as the GitHub release
                                agent-r<N> with one asset, app-release.apk, then prune old ones.

Versioning: versionCode = GITHUB_RUN_NUMBER + CODE_OFFSET, so every build is newer than the last
and newer than the hand-made agent-v0.9.19 (versionCode 37); versionName = 0.9.<code>+<sha8>.
The release tag is agent-r<versionCode>. Installed apps compare the digest of the release asset
(bootstrap_apks, gh_latest with gh_tag_prefix agent-r), so a rolling build never needs a pin.

`publish` is the only step that holds the release key. It reads it from the environment of the
`agent-release` Actions environment (master only), writes it to a 0600 file under RUNNER_TEMP,
hands apksigner the passwords through the environment (never argv) and removes the file again.
It refuses to publish an APK whose signer is not the fleet's release certificate, whose
versionCode differs from the one it was built with, or that is older than a release already
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

CODE_OFFSET = 100  # first rolling build (run 1) is versionCode 101, above the hand-made 37
VERSION_BASE = "0.9"
TAG_PREFIX = "agent-r"
ASSET_NAME = "app-release.apk"
KEEP_RELEASES = 10
# SHA-256 of the fleet's release certificate (keytool -list -v on agent-release.jks, alias agent).
SIGNER_SHA256 = "35bbc3d1a93c2a726df14bcc066bdc791f7f55f21b57d9455da27439c5ff9b6a"
SECRET_ENV = {
    "keystore": "STAYTURGID_AGENT_KEYSTORE_B64",
    "store_password": "STAYTURGID_AGENT_KEYSTORE_PASSWORD",
    "key_password": "STAYTURGID_AGENT_KEY_PASSWORD",
    "alias": "STAYTURGID_AGENT_KEY_ALIAS",
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


def run(argv: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, capture_output=True, text=True, env=env, check=False)
    if check and result.returncode != 0:
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


def sign(unsigned: Path, signed: Path, workdir: Path) -> None:
    missing = [name for name in SECRET_ENV.values() if not os.environ.get(name)]
    if missing:
        sys.exit("missing signing secrets (names only): " + ", ".join(missing))
    keystore = workdir / "agent-release.jks"
    fd = os.open(keystore, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(base64.b64decode(os.environ[SECRET_ENV["keystore"]]))
    try:
        env = dict(os.environ)
        env["AGENT_STORE_PASS"] = os.environ[SECRET_ENV["store_password"]]
        env["AGENT_KEY_PASS"] = os.environ[SECRET_ENV["key_password"]]
        run(
            [
                apksigner(), "sign",
                "--ks", str(keystore),
                "--ks-key-alias", os.environ[SECRET_ENV["alias"]],
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
    if f"certificate SHA-256 digest: {SIGNER_SHA256}" not in out:
        sys.exit("the signed APK does not carry the fleet release certificate; not publishing")


def gh_json(args: list[str]) -> object:
    return json.loads(run(["gh", *args]).stdout or "null")


def published_tags(repo: str) -> list[str]:
    tags: list[str] = []
    page = 1
    while True:
        batch = gh_json(["api", f"repos/{repo}/releases?per_page=100&page={page}"])
        assert isinstance(batch, list)
        tags += [r["tag_name"] for r in batch]
        if len(batch) < 100:
            return tags
        page += 1


def cmd_version(_args: argparse.Namespace) -> None:
    code = version_code(int(os.environ["GITHUB_RUN_NUMBER"]))
    print(f"code={code}")
    print(f"name={version_name(code, os.environ['GITHUB_SHA'])}")


def cmd_publish(args: argparse.Namespace) -> None:
    repo, sha = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    code, tag = args.code, tag_for(args.code)
    name = version_name(code, sha)
    unsigned = Path(args.apk)
    if apk_version_code(unsigned) != code:
        sys.exit(f"{unsigned.name} does not carry versionCode {code}")
    tags = published_tags(repo)
    if tag in tags:
        print(f"{tag} is already published; nothing to do")
        return
    if newest_code(tags) > code:
        sys.exit(f"{tag} is older than the published agent-r{newest_code(tags)}; not publishing")
    with tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP")) as tmp:
        out = Path(tmp) / ASSET_NAME
        sign(unsigned, out, Path(tmp))
        check_signer(out)
        if apk_version_code(out) != code:
            sys.exit("the signed APK lost its versionCode")
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        notes = (
            f"stayturgid-agent {name} (versionCode {code}), built from {sha} and signed by CI.\n\n"
            f"Build: {run_url}\n"
            f"APK SHA-256: `{digest}`\n"
            f"Signer certificate SHA-256: `{SIGNER_SHA256}`\n"
        )
        run(
            [
                "gh", "release", "create", tag, str(out),
                "--repo", repo,
                "--target", sha,
                "--title", f"stayturgid-agent {name}",
                "--notes", notes,
                "--latest=false",
            ]
        )  # fmt: skip
    print(f"published {tag}: sha256 {digest}")
    for stale in releases_to_prune(published_tags(repo)):
        print(f"pruning {stale}")
        run(["gh", "release", "delete", stale, "--repo", repo, "--cleanup-tag", "--yes"])


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version").set_defaults(fn=cmd_version)
    pub = sub.add_parser("publish")
    pub.add_argument("--apk", required=True)
    pub.add_argument("--code", type=int, required=True)
    pub.set_defaults(fn=cmd_publish)
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main(sys.argv[1:])
