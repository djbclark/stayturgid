"""Keep shared/fleet_app_profiles.json aligned with role defaults mirror."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JSON_PATH = REPO / "shared" / "fleet_app_profiles.json"


def test_fleet_app_profiles_json_is_valid():
    data = json.loads(JSON_PATH.read_text())
    assert isinstance(data, list)
    assert len(data) >= 10
    packages = {entry["package"] for entry in data}
    assert "org.autojs.autojs6" in packages
    assert "com.termux" in packages
    assert "dev.imranr.obtainium" in packages
    for entry in data:
        assert entry.get("battery_unrestricted") is True
        assert entry.get("disable_unused_restrictions") is True
