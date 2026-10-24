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

# Homebrew formulae behind the control node's serverapps (ansible/roles/serverapp_*)
# and hermes (control_node/tasks/hermes.yml). None is pinned: site-djbclark's
# nightly brew-fast-upgrade upgrades them, so a lingering "1" here means that
# run is failing. The
# update monitor runs only on the control node (it pushes to localhost
# VictoriaMetrics), so hermes-agent is always part of the monitored set. We
# emit an explicit 0/1 for every formula here each run so the
# software_update_available series is resettable rather than leaving a stale
# "1" sample lingering after a package stops being outdated.
MONITORED_BREW_FORMULAE = ["caddy", "grafana", "vector", "victoriametrics", "hermes-agent"]

# Serverapps installed from GitHub/vendor release tarballs. Each role installs
# the latest release on converge (github_latest_release), so installed != latest
# means a converge has not run since the release, or failed. Binary paths are
# the roles' *_bin_path defaults; the patterns match what each binary's
# --version prints, as the roles' own version probes do.
GITHUB_APPS = [
    {
        "name": "openobserve",
        "repo": "openobserve/openobserve",
        "bin": "~/.local/bin/openobserve",
        "pattern": r"([0-9]+(?:\.[0-9]+)+)",
    },
    {
        "name": "olivetin",
        "repo": "OliveTin/OliveTin",
        "bin": "~/.local/share/olivetin/OliveTin",
        "pattern": r'version="([0-9]+(?:\.[0-9]+)+)"',
    },
    {
        "name": "blackbox_exporter",
        "repo": "prometheus/blackbox_exporter",
        "bin": "~/.local/bin/blackbox_exporter",
        "pattern": r"version ([0-9]+(?:\.[0-9]+)+)",
    },
]


def escape_label_value(value: str) -> str:
    """Escapes a Prometheus exposition-format label value (backslash, quote, newline)."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def versions_differ(current: str, latest: str) -> bool:
    """True if `current`/`latest` represent different versions.

    Compares dotted-integer segments numerically so "1.2" and "1.2.0" (or a
    CalVer tag like "2026.7.20") compare equal/ordered correctly instead of
    the raw strings just happening to differ. Avoids a hard dependency (this
    script intentionally has none) by falling back to plain string inequality
    for anything that doesn't parse as dotted integers.
    """

    def parse(v: str):
        parts = v.split(".")
        if parts and all(p.isdigit() for p in parts):
            return tuple(int(p) for p in parts)
        return None

    a, b = parse(current), parse(latest)
    if a is None or b is None:
        return current != latest
    length = max(len(a), len(b))
    return a + (0,) * (length - len(a)) != b + (0,) * (length - len(b))


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
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310  # fixed https GitHub API URL
            data = json.loads(response.read().decode("utf-8"))
            tag = data.get("tag_name", "")
            return tag.lstrip("v")
    except Exception as e:
        logging.error(f"Failed to fetch {repo} latest release: {e}")
        return None


def get_installed_version(bin_path: str, pattern: str) -> Optional[str]:
    """The version an installed binary reports via --version; None when absent or unparseable."""
    path = os.path.expanduser(bin_path)
    if not os.path.isfile(path):
        return None
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        logging.error(f"Failed to run {path} --version: {e}")
        return None
    match = re.search(pattern, result.stdout + result.stderr)
    if not match:
        logging.error(f"Could not parse a version from {path} --version")
        return None
    return match.group(1)


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
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310  # local VictoriaMetrics http URL
            if response.status not in (200, 204):
                logging.error(f"VictoriaMetrics returned {response.status}: {response.read()}")
            else:
                logging.info(f"Successfully pushed {len(metrics)} metrics to VictoriaMetrics.")
    except Exception as e:
        logging.error(f"Failed to push to VictoriaMetrics: {e}")


def main():
    argparse.ArgumentParser(description="Stayturgid Update Monitor").parse_args()

    metrics = []

    # 1. Check GitHub Releases: installed binary vs latest release.
    for app in GITHUB_APPS:
        current_version = get_installed_version(app["bin"], app["pattern"])
        if not current_version:
            continue

        latest_version = fetch_github_latest_release(app["repo"])
        if not latest_version:
            continue

        has_update = 1 if versions_differ(current_version, latest_version) else 0
        metrics.append(
            f'software_update_available{{package="{escape_label_value(app["name"])}", '
            f'type="github", current="{escape_label_value(current_version)}", '
            f'latest="{escape_label_value(latest_version)}"}} {has_update}'
        )

        if has_update:
            logging.info(f"Update available for {app['name']}: {current_version} -> {latest_version}")

    # 2. Check Homebrew Packages (MONITORED_BREW_FORMULAE).
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
