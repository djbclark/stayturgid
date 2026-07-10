"""Validate control/lib/autojs6_drawer_defaults.json."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PATH = REPO / "control" / "lib" / "autojs6_drawer_defaults.json"


def test_drawer_defaults_structure():
    data = json.loads(PATH.read_text())
    assert "on" in data and "off" in data
    assert "Foreground service" in data["on"]
    assert "Floating button" in data["off"]
    assert "Accessibility service" in data["on"]
    overlap = set(data["on"]) & set(data["off"])
    assert not overlap, overlap
