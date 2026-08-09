#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pyyaml>=6.0.1",
# ]
# ///

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone

import yaml

HERMES_TARGET = "telegram:838808636:22158"
STATE_PATH = os.path.expanduser("~/.local/state/stayturgid/apk-updates.json")

# This project's own release is tracked separately (native-agent release
# process), not by this upstream-third-party checker.
SKIP_IDS = {"org.stayturgid.agent"}


def latest_tag_for(gh_repo):
    url = f"https://api.github.com/repos/{gh_repo}/releases/latest"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "stayturgid-updater")

    try:
        with urllib.request.urlopen(req) as response:
            release_data = json.loads(response.read().decode())
            return release_data.get("tag_name")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"Error checking {gh_repo}: {e}")
            return None
        # Some repos might not use releases, check tags instead.
        url = f"https://api.github.com/repos/{gh_repo}/tags"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "stayturgid-updater")
        try:
            with urllib.request.urlopen(req) as response:
                tags_data = json.loads(response.read().decode())
                return tags_data[0].get("name") if tags_data else None
        except Exception as ex:
            print(f"Error checking tags for {gh_repo}: {ex}")
            return None
    except Exception as e:
        print(f"Error checking {gh_repo}: {e}")
        return None


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    yaml_path = os.path.join(
        repo_root, "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/defaults/main.yml"
    )

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    apks = data.get("stayturgid_bootstrap_apks", [])
    updates = []

    for apk in apks:
        if apk.get("id") in SKIP_IDS:
            continue

        gh_repo = apk.get("gh_repo")
        gh_tag = apk.get("gh_tag")
        if not gh_repo or not gh_tag:
            continue

        latest_tag = latest_tag_for(gh_repo)
        if latest_tag and latest_tag != gh_tag:
            updates.append(f"{gh_repo}: {gh_tag} -> {latest_tag}")

    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(
            {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "updates": updates,
            },
            f,
            indent=2,
        )

    if updates:
        message = "Stayturgid pinned APK updates available:\n" + "\n".join(updates)
        print(message)
        subprocess.run(["hermes", "send", "-t", HERMES_TARGET, message], check=False)


if __name__ == "__main__":
    main()
