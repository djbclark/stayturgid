"""Unit tests for native_agent_config module."""

import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[4] / "plugins" / "modules" / "native_agent_config.py"
SPEC = importlib.util.spec_from_file_location("native_agent_config", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


def test_desired_config_is_complete_and_stable():
    assert mod.desired_config(["100.0.0.3:5555"], "moe.shizuku.privileged.api") == {
        "shizuku_pkg": "moe.shizuku.privileged.api",
        "targets": ["100.0.0.3:5555"],
    }


@pytest.mark.parametrize("text", ["", "[]", "not json", '{"targets":'])
def test_parse_config_rejects_invalid_or_non_mapping(text):
    assert mod.parse_config(text) is None


def test_parse_config_ignores_formatting():
    value = {"targets": [], "shizuku_pkg": "moe.shizuku.privileged.api"}
    assert mod.parse_config(json.dumps(value, indent=4)) == value


def test_external_config_path_is_package_scoped():
    assert (
        mod.external_config_path("org.stayturgid.agent") == "/sdcard/Android/data/org.stayturgid.agent/files/peer.json"
    )
