"""Pure helpers for reading/parsing enabled_accessibility_services.

Detection-only — no automatic writes, no merge-repair, no backup/restore.
Accessibility is a user-managed setting; all mechanisms detect and notify.
"""

from __future__ import annotations

import json
from pathlib import Path

AUTOJS6_A11Y = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"

_LIB = Path(__file__).resolve().parent
_ON_DEVICE_PROFILES = Path.home() / ".stayturgid" / "a11y_profiles.json"
_REPO_PROFILES = _LIB / "a11y_profiles.json"
if _ON_DEVICE_PROFILES.is_file():
    PROFILES_PATH = _ON_DEVICE_PROFILES
else:
    PROFILES_PATH = _REPO_PROFILES


def normalize_value(raw: str | None) -> str:
    text = (raw or "").strip()
    if text in ("", "null", "None"):
        return ""
    return text


def parse_services(raw: str | None) -> list[str]:
    text = normalize_value(raw)
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for part in text.split(":"):
        svc = part.strip()
        if not svc or svc in seen or svc == "null":
            continue
        if "/" not in svc or "." not in svc.split("/", 1)[0]:
            continue
        seen.add(svc)
        out.append(svc)
    return out


def has_autojs6(raw: str | None) -> bool:
    return AUTOJS6_A11Y in parse_services(raw)


def load_profiles() -> dict:
    if not PROFILES_PATH.is_file():
        return {"devices": {}}
    return json.loads(PROFILES_PATH.read_text())


def profile_services(alias: str) -> list[str]:
    data = load_profiles()
    entry = (data.get("devices") or {}).get(alias) or {}
    return list(entry.get("services") or [])
