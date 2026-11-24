"""The device_quirks role takes plain get/expect/set data; keep every model's list well formed."""

import pathlib

import yaml

GROUP_VARS = pathlib.Path(__file__).resolve().parents[2] / "ansible" / "inventory" / "group_vars"
REQUIRED = {"name", "get", "expect", "set"}


def _quirk_lists():
    for path in sorted(GROUP_VARS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if "stayturgid_device_quirks" in data:
            yield path.name, data["stayturgid_device_quirks"]


def test_every_quirk_has_name_get_expect_and_set():
    seen = 0
    for name, quirks in _quirk_lists():
        names = [q["name"] for q in quirks]
        assert len(names) == len(set(names)), "%s: duplicate quirk names" % name
        for quirk in quirks:
            assert REQUIRED <= set(quirk), "%s: %s lacks %s" % (name, quirk.get("name"), REQUIRED - set(quirk))
            assert isinstance(quirk["expect"], str), "%s: %s expect must be a string" % (name, quirk["name"])
            seen += 1
    assert seen > 0


def test_idea_tab_11_keeps_rotation_tile_working_and_zui_memory_cleaner_quirks():
    quirks = dict(_quirk_lists())["model_idea_tab_11.yml"]
    sets = " ".join(q["set"] for q in quirks)
    assert "wm fixed-to-user-rotation default" in sets
    assert "wm fixed-to-user-rotation enabled" not in sets
    assert "accelerometer_rotation" not in sets
    assert "wm user-rotation" not in sets
    assert "user_rotation" not in sets
    assert "persist.debug.zuimemory.enable false" in sets
