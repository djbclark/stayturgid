"""Static landing catalog plus user-local discovery state."""

from __future__ import annotations

import json
import os
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


def filter_example_devices(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out example Android device entries if any actual Android devices are present."""
    device_services = [s for s in services if s.get("group") in ("devices", "android")]
    actual_devices = {_extract_device_name(s) for s in device_services} - EXAMPLE_DEVICE_NAMES

    if actual_devices:
        return [
            s
            for s in services
            if s.get("group") not in ("devices", "android") or _extract_device_name(s) not in EXAMPLE_DEVICE_NAMES
        ]
    return services


OS_ORDER: list[str] = ["MacOS", "Linux", "Android", "Other"]


def get_os_category(s: dict[str, Any]) -> str:
    group = str(s.get("group", ""))
    if group == "mac":
        return "MacOS"
    elif group in ("linux", "computer", "computers"):
        return "Linux"
    elif group in ("devices", "android"):
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
