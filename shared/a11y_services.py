"""Pure helpers for enabled_accessibility_services (colon-separated list).

settings put REPLACES the entire list — never write a single service without
merging the prior value and any device profile backup.
"""
from __future__ import annotations

import json
from pathlib import Path

AUTOJS6_A11Y = (
    "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"
)

_HERE = Path(__file__).resolve()
# Repo: shared/a11y_services.py → parents[1] = repo root.
# On-device: ~/.stayturgid/lib/a11y_services.py → parents[1] = ~/.stayturgid.
_ROOT = _HERE.parents[1]
_ON_DEVICE_PROFILES = Path.home() / ".stayturgid" / "a11y_profiles.json"
_LIB_SIBLING_PROFILES = _ROOT / "a11y_profiles.json"
_REPO_PROFILES = _ROOT / "shared" / "a11y_profiles.json"
if _ON_DEVICE_PROFILES.is_file():
    PROFILES_PATH = _ON_DEVICE_PROFILES
elif _LIB_SIBLING_PROFILES.is_file():
    PROFILES_PATH = _LIB_SIBLING_PROFILES
else:
    PROFILES_PATH = _REPO_PROFILES
BACKUPS_DIR = _ROOT / "shared" / "a11y_backups"
if not BACKUPS_DIR.is_dir():
    BACKUPS_DIR = _ROOT / "a11y_backups"
DEVICE_BACKUP_REL = "state/a11y_services_backup.txt"


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


def join_services(services: list[str]) -> str:
    return ":".join(parse_services(":".join(services)))


def append_service(current: str | None, svc: str) -> str:
    services = parse_services(current)
    if svc not in services:
        services.append(svc)
    return join_services(services)


def merge_service_lists(*groups: list[str]) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for svc in group:
            if svc and svc not in seen:
                seen.add(svc)
                merged.append(svc)
    return join_services(merged)


def services_lost(before: str | None, after: str | None) -> list[str]:
    """Services present before but missing after (shrink detection)."""
    before_set = set(parse_services(before))
    after_set = set(parse_services(after))
    return sorted(before_set - after_set)


def load_profiles() -> dict:
    if not PROFILES_PATH.is_file():
        return {"devices": {}}
    return json.loads(PROFILES_PATH.read_text())


def profile_services(alias: str) -> list[str]:
    data = load_profiles()
    entry = (data.get("devices") or {}).get(alias) or {}
    return list(entry.get("services") or [])


def backup_file_for(alias: str) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUPS_DIR / ("%s.txt" % alias)


def read_backup_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return normalize_value(path.read_text())


def write_backup_file(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_value(value) + "\n")


def desired_services(alias: str, live: str | None, *, ensure_autojs6: bool = True) -> str:
    """Union of live snapshot, profile, and optional AutoJs6."""
    groups = [parse_services(live), profile_services(alias)]
    if ensure_autojs6:
        groups.append([AUTOJS6_A11Y])
    return merge_service_lists(*groups)


def repair_after_shrink(
    before: str | None,
    after: str | None,
    alias: str,
    *,
    ensure_autojs6: bool = True,
) -> str | None:
    """If after dropped services from before, return merged restore value."""
    lost = services_lost(before, after)
    if not lost:
        return None
    return desired_services(alias, before, ensure_autojs6=ensure_autojs6)
