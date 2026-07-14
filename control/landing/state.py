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
