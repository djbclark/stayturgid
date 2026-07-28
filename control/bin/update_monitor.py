#!/usr/bin/env python3
"""
Update monitor: checks for Homebrew updates and new GitHub releases for non-brew software.
Emits Prometheus metrics via HTTP POST to VictoriaMetrics.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Homebrew formulae pinned to Tier-1 on the control node (see the brew-pin
# tasks in ansible/roles/serverapp_* and control_node/tasks/hermes.yml). The
# update monitor runs only on the control node (it pushes to localhost
# VictoriaMetrics), so hermes-agent is always part of the monitored set. We
# emit an explicit 0/1 for every formula here each run so the
# software_update_available series is resettable rather than leaving a stale
# "1" sample lingering after a package stops being outdated.
MONITORED_BREW_FORMULAE = ["caddy", "grafana", "vector", "victoriametrics", "hermes-agent"]


def escape_label_value(value: str) -> str:
    """Escapes a Prometheus exposition-format label value (backslash, quote, newline)."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def fetch_github_latest_release(repo: str) -> Optional[str]:
    """Fetches the latest stable release tag from GitHub."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"User-Agent": "stayturgid-update-monitor"}
    # Best-effort auth to lift the 60/hr unauthenticated shared-IP rate limit.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            tag = data.get("tag_name", "")
            return tag.lstrip("v")
    except Exception as e:
        logging.error(f"Failed to fetch {repo} latest release: {e}")
        return None


def get_ansible_version(role_path: str, var_name: str) -> Optional[str]:
    """Reads a version string from an Ansible defaults/main.yml file using regex to avoid yaml dependency."""
    try:
        with open(os.path.join(role_path, "defaults", "main.yml"), "r") as f:
            for line in f:
                match = re.match(rf'^{var_name}:\s*"(.*?)"', line.strip())
                if match:
                    return match.group(1)
                # handle unquoted values just in case
                match_unquoted = re.match(rf"^{var_name}:\s*([^\s#]+)", line.strip())
                if match_unquoted:
                    return match_unquoted.group(1)
        return None
    except Exception as e:
        logging.error(f"Failed to read {var_name} from {role_path}: {e}")
        return None


def get_brew_outdated() -> List[Dict[str, str]]:
    """Runs brew outdated --json and returns a list of dicts with name, current_version, and latest_version."""
    try:
        result = subprocess.run(["brew", "outdated", "--json"], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        formulae = data.get("formulae", [])

        outdated = []
        for item in formulae:
            name = item.get("name")
            # `installed_versions` can be an empty list ([]), not just absent;
            # the dict default only covers absence, so `or [""]` guards the [0].
            installed = (item.get("installed_versions") or [""])[0]
            latest = item.get("current_version", "")
            outdated.append({"name": name, "current": installed, "latest": latest})
        return outdated
    except Exception as e:
        logging.error(f"Failed to run brew outdated: {e}")
        return []


def get_brew_installed_versions(formulae: List[str]) -> Dict[str, str]:
    """Returns {name: installed_version} for whichever of `formulae` are installed."""
    versions: Dict[str, str] = {}
    try:
        result = subprocess.run(
            ["brew", "list", "--versions", *formulae],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                versions[parts[0]] = parts[1]
    except Exception as e:
        logging.error(f"Failed to run brew list --versions: {e}")
    return versions


def push_to_victoriametrics(metrics: List[str], vm_url: str = "http://127.0.0.1:8428/api/v1/import/prometheus"):
    """POSTs Prometheus metrics to VictoriaMetrics."""
    payload = "\n".join(metrics) + "\n"
    req = urllib.request.Request(
        vm_url, data=payload.encode("utf-8"), headers={"Content-Type": "text/plain"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status not in (200, 204):
                logging.error(f"VictoriaMetrics returned {response.status}: {response.read()}")
            else:
                logging.info(f"Successfully pushed {len(metrics)} metrics to VictoriaMetrics.")
    except Exception as e:
        logging.error(f"Failed to push to VictoriaMetrics: {e}")


def main():
    parser = argparse.ArgumentParser(description="Stayturgid Update Monitor")
    parser.add_argument("--repo-root", required=True, help="Path to stayturgid repo root")
    args = parser.parse_args()

    metrics = []

    # 1. Check GitHub Releases
    github_apps = [
        {
            "name": "openobserve",
            "repo": "openobserve/openobserve",
            "role": "serverapp_openobserve",
            "var": "serverapp_openobserve_version",
        },
        {
            "name": "olivetin",
            "repo": "OliveTin/OliveTin",
            "role": "serverapp_olivetin",
            "var": "serverapp_olivetin_version",
        },
    ]

    for app in github_apps:
        role_path = os.path.join(args.repo_root, "ansible", "roles", app["role"])
        current_version = get_ansible_version(role_path, app["var"])
        if not current_version:
            continue

        latest_version = fetch_github_latest_release(app["repo"])
        if not latest_version:
            continue

        # Clean versions for comparison
        clean_current = current_version.lstrip("v")
        clean_latest = latest_version.lstrip("v")

        has_update = 1 if clean_current != clean_latest else 0
        metrics.append(
            f'software_update_available{{package="{escape_label_value(app["name"])}", '
            f'type="github", current="{escape_label_value(clean_current)}", '
            f'latest="{escape_label_value(clean_latest)}"}} {has_update}'
        )

        if has_update:
            logging.info(f"Update available for {app['name']}: {clean_current} -> {clean_latest}")

    # 2. Check Homebrew Packages (Tier-1 pinned set).
    # Emit an explicit 0/1 for every monitored formula each run so the series
    # is resettable: once a formula stops being outdated, its 0 sample clears
    # the alert instead of a stale 1 lingering until retention.
    outdated_map = {pkg["name"]: pkg for pkg in get_brew_outdated()}
    installed_versions = get_brew_installed_versions(MONITORED_BREW_FORMULAE)
    for name in MONITORED_BREW_FORMULAE:
        if name in outdated_map:
            current = outdated_map[name]["current"]
            latest = outdated_map[name]["latest"]
            has_update = 1
            logging.info(f"Update available for {name}: {current} -> {latest}")
        else:
            # Up to date (or not installed on this node): current == latest, value 0.
            current = latest = installed_versions.get(name, "")
            has_update = 0
        metrics.append(
            f'software_update_available{{package="{escape_label_value(name)}", '
            f'type="homebrew", current="{escape_label_value(current)}", '
            f'latest="{escape_label_value(latest)}"}} {has_update}'
        )

    # Unconditional liveness gauge: the monitor's last successful run as an
    # epoch timestamp. Emitted every run (not only when there are no updates)
    # so the Grafana alert can detect a stalled monitor via staleness.
    metrics.append(f"software_update_monitor_last_success_timestamp {int(time.time())}")

    push_to_victoriametrics(metrics)


if __name__ == "__main__":
    main()
