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
import sys
import urllib.request
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def fetch_github_latest_release(repo: str) -> Optional[str]:
    """Fetches the latest stable release tag from GitHub."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "stayturgid-update-monitor"})
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
                match_unquoted = re.match(rf'^{var_name}:\s*([^\s#]+)', line.strip())
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
            installed = item.get("installed_versions", [""])[0]
            latest = item.get("current_version", "")
            outdated.append({"name": name, "current": installed, "latest": latest})
        return outdated
    except Exception as e:
        logging.error(f"Failed to run brew outdated: {e}")
        return []


def push_to_victoriametrics(metrics: List[str], vm_url: str = "http://127.0.0.1:8428/api/v1/import/prometheus"):
    """POSTs Prometheus metrics to VictoriaMetrics."""
    payload = "\n".join(metrics) + "\n"
    req = urllib.request.Request(vm_url, data=payload.encode("utf-8"), headers={"Content-Type": "text/plain"}, method="POST")
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
        {"name": "openobserve", "repo": "openobserve/openobserve", "role": "serverapp_openobserve", "var": "serverapp_openobserve_version"},
        {"name": "olivetin", "repo": "OliveTin/OliveTin", "role": "serverapp_olivetin", "var": "serverapp_olivetin_version"}
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
        metrics.append(f'software_update_available{{package="{app["name"]}", type="github", current="{clean_current}", latest="{clean_latest}"}} {has_update}')
        
        if has_update:
            logging.info(f"Update available for {app['name']}: {clean_current} -> {clean_latest}")

    # 2. Check Homebrew Packages
    brew_outdated = get_brew_outdated()
    # For every package that is outdated, it has an update available
    for pkg in brew_outdated:
        metrics.append(f'software_update_available{{package="{pkg["name"]}", type="homebrew", current="{pkg["current"]}", latest="{pkg["latest"]}"}} 1')
        logging.info(f"Update available for {pkg['name']}: {pkg['current']} -> {pkg['latest']}")

    if not metrics:
        # Push a heartbeat metric so we know it ran
        metrics.append("software_update_monitor_last_run_seconds_total 1")

    push_to_victoriametrics(metrics)


if __name__ == "__main__":
    main()
