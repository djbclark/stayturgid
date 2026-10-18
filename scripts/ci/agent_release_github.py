#!/usr/bin/env python3
"""Publish CI's unsigned stayturgid-agent APK as a GitHub prerelease.

Same naming as the Forgejo script: tag agent-ci-<version>-<sha8>, asset
stayturgid-agent-<version>-<sha8>-release-unsigned.apk (+ .sha256).
Uses GITHUB_TOKEN (Actions automatic token). APK remains unsigned; the Mac
signs with apksigner before the GitHub release that bootstrap_apks pins.
"""
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import base64

REPO = os.environ["GITHUB_REPOSITORY"]
SHA = os.environ["GITHUB_SHA"]
TOKEN = os.environ["GITHUB_TOKEN"]
API = f"https://api.github.com/repos/{REPO}"
UPLOAD = f"https://uploads.github.com/repos/{REPO}"
OUT = pathlib.Path("device/native-agent/app/build/outputs/apk/release")
PREFIX = "agent-ci-"


def call(method, url, body=None, data=None, content_type=None, missing_ok=False):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if body is not None:
        data = json.dumps(body).encode()
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # nosec B310
            payload = r.read()
    except urllib.error.HTTPError as e:
        if missing_ok and e.code == 404:
            return None
        sys.exit(f"agent_release_github: {method} {url}: HTTP {e.code}: {e.read().decode()[:500]}")
    return json.loads(payload) if payload.strip() else None


def upload(release_id, name, content):
    query = urllib.parse.urlencode({"name": name})
    call(
        "POST",
        f"{UPLOAD}/releases/{release_id}/assets?{query}",
        data=content,
        content_type="application/octet-stream",
    )


def prune(keep):
    releases, page = [], 1
    while True:
        batch = call("GET", f"{API}/releases?per_page=50&page={page}") or []
        releases += batch
        if len(batch) < 50:
            break
        page += 1
    ours = sorted(
        (r for r in releases if r["tag_name"].startswith(PREFIX)),
        key=lambda r: r["created_at"],
        reverse=True,
    )
    for r in ours[keep:]:
        print(f"pruning {r['tag_name']}")
        call("DELETE", f"{API}/releases/{r['id']}")
        # delete tag ref
        call("DELETE", f"{API}/git/refs/tags/{urllib.parse.quote(r['tag_name'], safe='')}", missing_ok=True)


def main():
    meta = json.loads((OUT / "output-metadata.json").read_text())
    element = meta["elements"][0]
    version, code = element["versionName"], element["versionCode"]
    apk_path = OUT / element["outputFile"]
    if "unsigned" not in apk_path.name:
        sys.exit(f"agent_release_github: {apk_path.name} is signed; CI must not hold the release key")
    sha8 = SHA[:8]
    tag = f"{PREFIX}{version}-{sha8}"
    name = f"stayturgid-agent-{version}-{sha8}-release-unsigned.apk"
    existing = call("GET", f"{API}/releases/tags/{urllib.parse.quote(tag, safe='')}", missing_ok=True)
    if existing:
        print(f"{tag} already released: {existing['html_url']}")
        return
    apk = apk_path.read_bytes()
    digest = hashlib.sha256(apk).hexdigest()
    run_url = f"https://github.com/{REPO}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
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
        f"{API}/releases",
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
