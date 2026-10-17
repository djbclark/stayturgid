#!/usr/bin/env python3
"""Publish CI's unsigned stayturgid-agent release APK as a Forgejo release, then prune old ones.

    agent_release.py

Run inside the agent-build job on forgejo.mit.edu, from the repository root. Reads
FORGEJO_TOKEN (the job's automatic token), GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_SHA,
GITHUB_RUN_NUMBER and optionally AGENT_KEEP_RELEASES (default 10). The tag is
agent-ci-<versionName>-<sha8>; the asset is
stayturgid-agent-<versionName>-<sha8>-release-unsigned.apk with a .sha256 beside it.

The APK is unsigned on purpose: the release key never leaves the Mac, which signs it with
apksigner before the GitHub release that bootstrap_apks pins. Adapted from Plektra's
djb_release.py (djbclark/plektra-djbclark, plk/base).
"""

import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

SERVER = os.environ["GITHUB_SERVER_URL"].rstrip("/")
REPO = os.environ["GITHUB_REPOSITORY"]
SHA = os.environ["GITHUB_SHA"]
TOKEN = os.environ["FORGEJO_TOKEN"]
API = f"{SERVER}/api/v1/repos/{REPO}"
OUT = pathlib.Path("device/native-agent/app/build/outputs/apk/release")
PREFIX = "agent-ci-"


def call(method, path, body=None, data=None, content_type=None):
    headers = {"Authorization": f"token {TOKEN}", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # nosec B310 - https API URL from the runner env
            payload = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"agent_release: {method} {path}: HTTP {e.code}: {e.read().decode()[:500]}")
    return json.loads(payload) if payload.strip() else None


def upload(release_id, name, content):
    boundary = uuid.uuid4().hex
    data = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="attachment"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    query = urllib.parse.urlencode({"name": name})
    call(
        "POST",
        f"/releases/{release_id}/assets?{query}",
        data=data,
        content_type=f"multipart/form-data; boundary={boundary}",
    )


def prune(keep):
    releases, page = [], 1
    while True:
        batch = call("GET", f"/releases?limit=50&page={page}") or []
        releases += batch
        if len(batch) < 50:
            break
        page += 1
    ours = sorted(
        (r for r in releases if r["tag_name"].startswith(PREFIX)), key=lambda r: r["created_at"], reverse=True
    )
    for r in ours[keep:]:
        print(f"pruning {r['tag_name']}")
        call("DELETE", f"/releases/{r['id']}")
        call("DELETE", f"/tags/{urllib.parse.quote(r['tag_name'], safe='')}")


def main():
    meta = json.loads((OUT / "output-metadata.json").read_text())
    element = meta["elements"][0]
    version, code = element["versionName"], element["versionCode"]
    apk_path = OUT / element["outputFile"]
    if "unsigned" not in apk_path.name:
        sys.exit(f"agent_release: {apk_path.name} is signed; CI must not hold the release key")
    sha8 = SHA[:8]
    tag = f"{PREFIX}{version}-{sha8}"
    name = f"stayturgid-agent-{version}-{sha8}-release-unsigned.apk"
    apk = apk_path.read_bytes()
    digest = hashlib.sha256(apk).hexdigest()
    run_url = f"{SERVER}/{REPO}/actions/runs/{os.environ['GITHUB_RUN_NUMBER']}"
    body = "\n".join(
        [
            f"stayturgid-agent {version} (versionCode {code}), unsigned release build of {SHA}.",
            "",
            f"Build: {run_url}",
            f"Unsigned APK SHA-256: `{digest}`",
            "",
            "Sign on the Mac with the release key (apksigner), then publish the signed APK as the",
            "GitHub release agent-v<version> that bootstrap_apks pins.",
        ]
    )
    release = call(
        "POST",
        "/releases",
        body={
            "tag_name": tag,
            "target_commitish": SHA,
            "name": f"stayturgid-agent {version} ({sha8}, unsigned)",
            "body": body,
            "draft": False,
            "prerelease": True,
        },
    )
    upload(release["id"], name, apk)
    upload(release["id"], name + ".sha256", f"{digest}  {name}\n".encode())
    print(f"released {tag}: {release['html_url']}")
    prune(int(os.environ.get("AGENT_KEEP_RELEASES", "10")))


if __name__ == "__main__":
    main()
