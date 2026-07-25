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
