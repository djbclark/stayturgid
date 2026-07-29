import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from control.lib.ansible_context import resolve_ansible_context, resolved_env
from control.lib.site_logging import WARNING, log

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_NAME = "firerpa-fleet.log"


def _log(level: int, msg: str) -> None:
    log(LOG_NAME, level, msg, also_print=True)


@dataclass(frozen=True)
class FirerpaTarget:
    """Inventory-derived FIRERPA policy for one Android host."""

    alias: str
    ip: str
    usb_serial: str = ""
    enabled: bool = True
    runtime_status: str = "supported"
    recovery_mode: str = "none"
    port: int = 65000
    certificate_device_path: str = "/data/local/tmp/firerpa/server/lamda.pem"


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_fleet() -> list[FirerpaTarget]:
    context = resolve_ansible_context(REPO_ROOT)
    env = resolved_env(REPO_ROOT)

    try:
        result = subprocess.run(
            ["ansible-inventory", "--list", *context.inventory_args()],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        _log(WARNING, "Failed to resolve inventory: ansible-inventory timed out after 30s")
        return []
    except OSError as e:
        _log(WARNING, f"Failed to resolve inventory: {e}")
        return []

    if result.returncode != 0:
        _log(WARNING, "Failed to resolve inventory: " + result.stderr)
        return []

    try:
        inv = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        _log(WARNING, f"Failed to decode inventory JSON: {e}")
        return []
    hosts = inv.get("stayturgid", {}).get("hosts", [])
    if not hosts:
        # Fallback to children of stayturgid if it's a group of groups
        for child_group in inv.get("stayturgid", {}).get("children", []):
            hosts.extend(inv.get(child_group, {}).get("hosts", []))

    hostvars = inv.get("_meta", {}).get("hostvars", {})

    fleet = []
    for host in hosts:
        variables = hostvars.get(host, {})
        ip = variables.get("ansible_host")
        if ip:
            fleet.append(
                FirerpaTarget(
                    alias=host,
                    ip=str(ip),
                    usb_serial=str(variables.get("device_usb_serial", "")),
                    enabled=_as_bool(variables.get("firerpa_enabled"), True),
                    runtime_status=str(variables.get("firerpa_runtime_status", "supported")),
                    recovery_mode=str(variables.get("firerpa_recovery_mode", "none")),
                    port=int(variables.get("firerpa_port", 65000)),
                    certificate_device_path=str(
                        variables.get(
                            "firerpa_certificate_device_path",
                            "/data/local/tmp/firerpa/server/lamda.pem",
                        )
                    ),
                )
            )

    return fleet
