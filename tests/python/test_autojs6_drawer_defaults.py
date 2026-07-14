"""Validate device/autojs6/fleet_profile.json structure."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET_PROFILE = REPO / "device" / "autojs6" / "fleet_profile.json"


def test_fleet_profile_exists():
    assert FLEET_PROFILE.is_file(), f"Missing fleet profile: {FLEET_PROFILE}"


def test_fleet_profile_structure():
    data = json.loads(FLEET_PROFILE.read_text())
    assert "_meta" in data, "Missing _meta section"
    assert "name" in data["_meta"]
    assert "version" in data["_meta"]
    assert isinstance(data["_meta"].get("clear_existing", True), bool)


def test_fleet_profile_has_critical_keys():
    data = json.loads(FLEET_PROFILE.read_text())
    critical = {"foreground_service", "enable_a11y_service_with_secure_settings", "stable_mode"}
    present = critical & set(data.keys())
    assert present == critical, f"Missing critical keys: {critical - present}"


def test_fleet_profile_booleans_are_booleans():
    data = json.loads(FLEET_PROFILE.read_text())
    for key in (
        "foreground_service",
        "floating_menu_shown",
        "stable_mode",
        "guard_mode",
        "auto_check_for_updates",
        "display_over_other_apps",
    ):
        if key in data:
            assert isinstance(data[key], bool), f"{key} should be bool, got {type(data[key])}"
