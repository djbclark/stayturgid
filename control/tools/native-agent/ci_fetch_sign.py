#!/usr/bin/env python3
"""Fetch the unsigned CI build of stayturgid-agent and sign it on the Mac with the release key.

This is the fallback to the rolling releases. Normally .github/workflows/agent-release.yml signs
every build of master in CI and publishes it as the GitHub release agent-r<versionCode>
(device/native-agent/README.md, "Rolling releases"); nothing needs fetching. Use this script when CI
cannot sign (the signing secrets are gone, or a branch must be built without publishing): run
`just agent-ci-run BRANCH` (a workflow dispatch with sign=false), which keeps the unsigned APK as the
workflow artifact `agent-unsigned`; this script downloads it, checks its SHA-256, signs it with
device/native-agent/agent-release.jks (the gitignored local copy of the same key CI holds) and
checks the signer, writing the result where a local release build would:
device/native-agent/app/build/outputs/apk/release/app-release.apk.

Usage:
  ci_fetch_sign.py            # the CI run of HEAD (push the branch and `just agent-ci-run` first)
  ci_fetch_sign.py SHA        # the CI run of another full 40-character commit
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AGENT = REPO / "device" / "native-agent"
OUT = AGENT / "app" / "build" / "outputs" / "apk" / "release"
KEYSTORE = AGENT / "agent-release.jks"
GITHUB_REPO = "djbclark/stayturgid"
WORKFLOW = "agent-release.yml"
ARTIFACT = "agent-unsigned"
UNSIGNED = "app-release-unsigned.apk"
# Release signing certificate (keytool -list -v on agent-release.jks, alias agent).
SIGNER_SHA256 = "35bbc3d1a93c2a726df14bcc066bdc791f7f55f21b57d9455da27439c5ff9b6a"


def gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        sys.exit(f"gh {' '.join(args)} failed: {(r.stderr or r.stdout).strip()[:500]}")
    return r.stdout


def apksigner() -> Path:
    sdk = Path(os.environ.get("ANDROID_HOME") or Path.home() / "Library/Android/sdk")
    tools = sorted(
        (sdk / "build-tools").glob("*/apksigner"),
        key=lambda p: [int(x) for x in p.parent.name.split(".") if x.isdigit()],
    )
    if not tools:
        sys.exit(f"no apksigner under {sdk}/build-tools")
    return tools[-1]


def run_for(sha: str) -> int:
    """Newest successful agent-release.yml run of the exact commit; gh only matches a full SHA."""
    runs = json.loads(
        gh(
            "run",
            "list",
            "-R",
            GITHUB_REPO,
            "--workflow",
            WORKFLOW,
            "--commit",
            sha,
            "--status",
            "success",
            "--limit",
            "5",
            "--json",
            "databaseId",
        )  # fmt: skip
    )
    if not runs:
        sys.exit(f"no successful {WORKFLOW} run for {sha[:8]}: is the run finished and green?")
    return int(runs[0]["databaseId"])


def main(argv: list[str]) -> int:
    sha = argv[0] if argv else subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    if len(sha) != 40:
        sys.exit(f"{sha!r} is not a full 40-character commit")
    run_id = run_for(sha)
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        gh("run", "download", str(run_id), "-R", GITHUB_REPO, "-n", ARTIFACT, "-D", tmp)
        unsigned = OUT / UNSIGNED
        unsigned.write_bytes((Path(tmp) / UNSIGNED).read_bytes())
        want = (Path(tmp) / (UNSIGNED + ".sha256")).read_text().split()[0]
    got = hashlib.sha256(unsigned.read_bytes()).hexdigest()
    if got != want:
        sys.exit(f"SHA-256 mismatch for {UNSIGNED}: got {got}, the run says {want}")
    if not KEYSTORE.is_file():
        sys.exit(f"missing {KEYSTORE} (the gitignored local copy of the release key)")
    signed = OUT / "app-release.apk"
    signer = apksigner()
    subprocess.run(
        [str(signer), "sign", "--ks", str(KEYSTORE), "--ks-key-alias", "agent",
         "--ks-pass", "pass:stayturgid", "--key-pass", "pass:stayturgid",
         "--out", str(signed), str(unsigned)],
        check=True,
    )  # fmt: skip
    certs = subprocess.run(
        [str(signer), "verify", "--print-certs", str(signed)], capture_output=True, text=True, check=True
    ).stdout
    if f"certificate SHA-256 digest: {SIGNER_SHA256}" not in certs:
        sys.exit(f"signed APK has the wrong signer:\n{certs}")
    digest = hashlib.sha256(signed.read_bytes()).hexdigest()
    print(f"run {run_id}: signed {signed}")
    print(f"sha256:{digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
