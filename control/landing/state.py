"""Static landing catalog plus user-local discovery state."""

from __future__ import annotations

import functools
import json
import os
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CATALOG_FILE = HERE / "services.json"
STATE_FILE = Path(
    os.environ.get(
        "STAYTURGID_LANDING_STATE",
        str(Path.home() / ".config" / "stayturgid" / "landing" / "services.json"),
    )
)


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_catalog() -> dict[str, Any]:
    """Read the committed static service definitions."""
    return _read(CATALOG_FILE) or {"services": [], "hidden": []}


def write_state(data: dict[str, Any]) -> None:
    """Atomically write generated state below the user config directory."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(STATE_FILE)


def load_state() -> dict[str, Any]:
    """Load runtime state, migrating the old tracked catalog on first use."""
    state = _read(STATE_FILE)
    if state is not None:
        return state
    legacy = _read(CATALOG_FILE)
    if legacy is not None:
        try:
            write_state(legacy)
        except OSError:
            pass
        return legacy
    return load_catalog()


import re


def natural_sort_key(s: str) -> list[int | str]:
    """Return a sort key for natural (case-insensitive, numeric-aware) ordering."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", str(s))]


def _extract_device_name(service: dict[str, Any]) -> str:
    # If the group is itself a known device name (e.g. group="p7a"), use it directly.
    group = str(service.get("group", ""))
    if group not in ("mac", "devices", "android", "computers", "computer", "linux", "other", ""):
        return group
    label = str(service.get("label", ""))
    device = str(service.get("device", ""))
    if device:
        return device
    parts = label.split()
    return parts[0] if parts else label


def service_sort_key(s: dict[str, Any]) -> tuple:
    """Sort key:
    1. Dashboard host (Mac) first (rank 0)
    2. Computers by name (rank 1)
    3. Android devices by name (rank 2)
    4. Other (rank 3)
    Within each name, sort services by label (case-insensitive, natural numbers).
    """
    group = str(s.get("group", ""))
    label = str(s.get("label", ""))

    if group == "mac":
        cat_rank = 0
        dev_name = "mac"
    elif group in ("computers", "computer"):
        cat_rank = 1
        dev_name = _extract_device_name(s)
    elif group in ("devices", "android"):
        cat_rank = 2
        dev_name = _extract_device_name(s)
    else:
        cat_rank = 3
        dev_name = _extract_device_name(s)

    return (cat_rank, natural_sort_key(dev_name), natural_sort_key(label))


EXAMPLE_DEVICE_NAMES: set[str] = {"fireos-device", "oneui-device", "stock-android-device"}

# Last-resort fallback only -- used when the live Ansible inventory can't be
# resolved (tests, no site configured). _known_android_devices() below is the
# real source of truth; this operator's own fleet aliases are not portable to
# a different site/operator, which is exactly why they shouldn't be the
# primary source in shared dashboard code.
_KNOWN_ANDROID_DEVICES_FALLBACK: frozenset[str] = frozenset({"hd8", "p7a", "s24"})


@functools.lru_cache(maxsize=1)
def _known_android_devices() -> frozenset[str]:
    """Real fleet device aliases from the active Ansible inventory.

    A service whose ``group`` is set directly to a device alias (rather than
    the generic ``"devices"``/``"android"`` group) is classified Android by
    matching against this set -- e.g. a per-device dashboard entry. Cached
    for the process lifetime: landing.py calls this per dashboard request,
    and an inventory shell-out per request would be a real cost.
    """
    from control.lib.ansible_context import AnsibleConfigError
    from control.lib.fleet_targets import inventory_list, parse_inventory_hosts

    repo_root = Path(__file__).resolve().parents[2]
    try:
        data = inventory_list(repo_root)
        hosts = parse_inventory_hosts(data)
    except (AnsibleConfigError, subprocess.CalledProcessError, OSError, ValueError):
        return _KNOWN_ANDROID_DEVICES_FALLBACK
    return frozenset(hosts) if hosts else _KNOWN_ANDROID_DEVICES_FALLBACK


def filter_example_devices(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out example Android device entries if any actual Android devices are present."""
    device_services = [s for s in services if get_os_category(s) == "Android"]
    actual_devices = {_extract_device_name(s) for s in device_services} - EXAMPLE_DEVICE_NAMES

    if actual_devices:
        return [
            s
            for s in services
            if get_os_category(s) != "Android" or _extract_device_name(s) not in EXAMPLE_DEVICE_NAMES
        ]
    return services


OS_ORDER: list[str] = ["MacOS", "Linux", "Android", "Other"]


def get_os_category(s: dict[str, Any]) -> str:
    group = str(s.get("group", ""))
    if group == "mac":
        return "MacOS"
    elif group in ("linux", "computer", "computers"):
        return "Linux"
    elif group in ("devices", "android") or group in _known_android_devices():
        return "Android"
    return "Other"


def get_clean_display_label(s: dict[str, Any], dev_name: str) -> str:
    lbl = str(s.get("label", ""))
    if dev_name.lower() != "mac" and lbl.lower().startswith(dev_name.lower()):
        cleaned = lbl[len(dev_name) :].strip()
        return cleaned if cleaned else lbl
    return lbl


def build_os_hierarchy(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group services into a 3-level hierarchy: OS -> Device -> Services list."""
    filtered = filter_example_devices(services)
    os_map: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for s in filtered:
        os_cat = get_os_category(s)
        dev_name = "mac" if os_cat == "MacOS" else _extract_device_name(s)

        if os_cat not in os_map:
            os_map[os_cat] = {}
        if dev_name not in os_map[os_cat]:
            os_map[os_cat][dev_name] = []

        item = dict(s)
        item["display_label"] = get_clean_display_label(s, dev_name)
        os_map[os_cat][dev_name].append(item)

    hierarchy: list[dict[str, Any]] = []
    for os_cat in OS_ORDER:
        if os_cat in os_map:
            dev_list: list[dict[str, Any]] = []
            for dev_name in sorted(os_map[os_cat].keys(), key=natural_sort_key):
                svcs = sorted(
                    os_map[os_cat][dev_name],
                    key=lambda item: natural_sort_key(str(item.get("display_label", ""))),
                )
                dev_list.append({"name": dev_name, "services": svcs})
            hierarchy.append({"os": os_cat, "devices": dev_list})

    return hierarchy
