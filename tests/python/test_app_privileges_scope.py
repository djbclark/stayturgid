"""`just deploy-apks` must apply the fleet app privilege profiles.

deploy-apks runs site.yml with `--tags bootstrap-apks`. On 2026-10-17 the
agent was installed before a reinstalled Termux on s24 and t2e, so it never got
com.termux.permission.RUN_COMMAND, and the quiet buttons could not reach
Termux. The app_privileges role (which grants it from fleet_app_profiles.json)
only ran in the full deploy.
"""

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def test_app_privileges_runs_under_bootstrap_apks_tag():
    plays = yaml.safe_load((REPO / "ansible/playbooks/fleet/fleet.yml").read_text())
    roles = [r for play in plays for r in play.get("roles", []) if isinstance(r, dict)]
    role = next(r for r in roles if r.get("role") == "stayturgid.android_common.app_privileges")
    assert "bootstrap-apks" in role["tags"]


def test_agent_profile_grants_termux_run_command():
    profiles = json.loads((REPO / "control/lib/fleet_app_profiles.json").read_text())
    agent = next(p for p in profiles if p["package"] == "org.stayturgid.agent")
    assert "com.termux.permission.RUN_COMMAND" in agent["permissions"]
