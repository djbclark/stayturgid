"""Unit tests for AutoJs6 accessibility append helper."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENABLE = REPO / "autojs6" / "mac" / "enable_autojs6_shizuku.py"

spec = importlib.util.spec_from_file_location("enable_autojs6_shizuku", ENABLE)
mod = importlib.util.module_from_spec(spec)
sys.modules["enable_autojs6_shizuku"] = mod
spec.loader.exec_module(mod)


def test_a11y_append_empty():
    assert mod.a11y_append_value("") == mod.A11Y_SVC
    assert mod.a11y_append_value("null") == mod.A11Y_SVC


def test_a11y_append_preserves_existing():
    cur = "com.other.app/.Service"
    out = mod.a11y_append_value(cur)
    assert out.startswith(cur + ":")
    assert mod.A11Y_SVC in out


def test_a11y_append_idempotent():
    cur = "com.other.app/.Service:" + mod.A11Y_SVC
    assert mod.a11y_append_value(cur) == cur
