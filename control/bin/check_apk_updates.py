#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pyyaml>=6.0.1",
# ]
# ///

"""Notify when pinned bootstrap APKs fall behind their latest GitHub releases.

Reads ``stayturgid_bootstrap_apks`` pins from the bootstrap_apks role
defaults, compares each pinned ``gh_tag`` against the repo's latest
release/tag, and records the pending set in STATE_PATH on every run.

Telegram (hermes) fires only when that set CHANGES since the previous run
(new package, new latest tag, or pending updates cleared) — Jobber runs
this repeatedly and an unchanged set must not re-nag the operator; it is
still printed to stdout for the Jobber log. This checker never installs
anything; bumping pins is an operator/ansible change.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import yaml

HERMES_TARGET = "telegram:838808636:22158"
STATE_PATH = os.path.expanduser("~/.local/state/stayturgid/apk-updates.json")

# This project's own release is tracked separately (native-agent release
# process), not by this upstream-third-party checker.
SKIP_IDS = {"org.stayturgid.agent"}

NO_UPDATES_MESSAGE = "No pinned APK updates available."
CLEARED_MESSAGE = "Stayturgid pinned APK updates cleared: all pinned APKs match their latest GitHub tags."


def latest_tag_for(gh_repo):
    url = f"https://api.github.com/repos/{gh_repo}/releases/latest"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "stayturgid-updater")

    try:
        with urllib.request.urlopen(req) as response:  # nosec B310 — fixed-scheme https URL, ansible-pinned repos
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
            with urllib.request.urlopen(req) as response:  # nosec B310 — same fixed-scheme GitHub API URL
                tags_data = json.loads(response.read().decode())
                return tags_data[0].get("name") if tags_data else None
        except Exception as ex:
            print(f"Error checking tags for {gh_repo}: {ex}")
            return None
    except Exception as e:
        print(f"Error checking {gh_repo}: {e}")
        return None


def normalize_updates(updates):
    """Sorted unique update lines — the comparison/persistence form."""
    return sorted(set(updates))


def format_updates_message(updates):
    return "Stayturgid pinned APK updates available:\n" + "\n".join(updates)


def load_last_updates(path):
    """Pending-update lines recorded by the previous run; [] if none.

    A missing or corrupt state file reads as empty, which fails toward one
    extra notification rather than silencing a real change.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    updates = data.get("updates") if isinstance(data, dict) else None
    if not isinstance(updates, list):
        return []
    return normalize_updates([u for u in updates if isinstance(u, str)])


def write_state(path, updates):
    """Write state atomically; failures are non-fatal so notify can still run."""
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "updates": updates,
    }
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"WARN: could not write state {path}: {exc}", file=sys.stderr)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def hermes_notify(message):
    subprocess.run(["hermes", "send", "-t", HERMES_TARGET, message], check=False)


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

    updates = normalize_updates(updates)
    last_updates = load_last_updates(STATE_PATH)
    write_state(STATE_PATH, updates)

    if updates != last_updates:
        if updates:
            message = format_updates_message(updates)
        else:
            # Pending set went non-empty -> empty (pins bumped / tags rolled
            # back): tell the operator the nag is resolved.
            message = CLEARED_MESSAGE
        print(message)
        hermes_notify(message)
    else:
        # Same pending set as the previous run: Jobber log only, no re-nag.
        print(format_updates_message(updates) if updates else NO_UPDATES_MESSAGE)

    return 0


if __name__ == "__main__":
    sys.exit(main())
