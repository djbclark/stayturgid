#!/usr/bin/env python3
"""Fetch the CI-built stayturgid-agent APK from Forgejo and sign it with the release key.

stayturgid-agent is built only on Forgejo CI (forgejo.mit.edu/djbclark/stayturgid,
.forgejo/workflows/agent-build.yml), never on this Mac (djbclark, 2026-10-17). CI publishes an
unsigned release APK as the prerelease agent-ci-<versionName>-<sha8>; this script downloads it,
checks its SHA-256, signs it with device/native-agent/agent-release.jks (which never leaves the
Mac) and checks the signer, writing the result where a local release build would:
device/native-agent/app/build/outputs/apk/release/app-release.apk.

Usage:
  ci_fetch_sign.py            # the build of HEAD (push it to the forgejo remote first)
  ci_fetch_sign.py SHA        # the build of another commit
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AGENT = REPO / "device" / "native-agent"
OUT = AGENT / "app" / "build" / "outputs" / "apk" / "release"
KEYSTORE = AGENT / "agent-release.jks"
FORGEJO_REPO = "djbclark/stayturgid"
FORGEJO_API = (
    Path(os.environ.get("FORGEJO_SCRIPTS", Path.home() / "src/djbclark-ade/skills/forgejo/scripts")) / "forgejo-api"
)
# Release signing certificate (keytool -list -v on agent-release.jks, alias agent).
SIGNER_SHA256 = "35bbc3d1a93c2a726df14bcc066bdc791f7f55f21b57d9455da27439c5ff9b6a"


def api(*args: str) -> str:
    r = subprocess.run([str(FORGEJO_API), *args], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        sys.exit(f"forgejo-api {' '.join(args)} failed: {(r.stderr or r.stdout).strip()[:500]}")
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


def main(argv: list[str]) -> int:
    sha = argv[0] if argv else subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    releases = json.loads(api("GET", f"/repos/{FORGEJO_REPO}/releases?limit=50"))
    rel = next((r for r in releases if r["tag_name"].startswith("agent-ci-") and r["tag_name"].endswith(sha[:8])), None)
    if rel is None:
        sys.exit(f"no agent-ci-*-{sha[:8]} release yet: is the CI run for {sha[:8]} finished and green?")
    assets = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
    name = next(n for n in assets if n.endswith("-release-unsigned.apk"))
    OUT.mkdir(parents=True, exist_ok=True)
    unsigned = OUT / name
    api("--output", str(unsigned), "GET", assets[name])
    want = api("GET", assets[name + ".sha256"]).split()[0]
    got = hashlib.sha256(unsigned.read_bytes()).hexdigest()
    if got != want:
        sys.exit(f"SHA-256 mismatch for {name}: got {got}, release says {want}")
    if not KEYSTORE.is_file():
        sys.exit(f"missing {KEYSTORE} (the release key lives only on djbclark's Mac)")
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
    print(f"{rel['tag_name']}: signed {signed}")
    print(f"sha256:{digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
