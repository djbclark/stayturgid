"""Regression test for ansible_collections/stayturgid/fleet's stayturgid_verify module.

CHECK_MAP is a module-level dict literal built from function references; a
forward reference to a function defined later in the same file raises
NameError at *import* time (dict literals evaluate their values eagerly,
unlike type annotations). This previously broke the whole module — every
check, not just the misordered one — and was invisible to py_compile-based
syntax checks (which don't execute module-level code) and to ruff's F821
lint (silenced by a stale `# noqa` comment based on a misreading of Python's
forward-reference rules).
"""

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_MOD = _REPO / "ansible_collections/stayturgid/fleet/plugins/modules/stayturgid_verify.py"
_spec = importlib.util.spec_from_file_location("stayturgid_verify", _MOD)
assert _spec is not None
sv = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(sv)


def test_check_map_fully_populated_with_callables() -> None:
    expected_keys = {
        "sshd",
        "bootloop",
        "shell5555",
        "shizuku",
        "a11y",
        "repair_log",
        "watchdog",
        "termux_api",
        "mirror",
        "sshd_config",
        "overlay_perms",
        "write_settings",
        "tailscale_vpn",
        "scripts_match",
        "wireless_debugging",
    }
    assert set(sv.CHECK_MAP) == expected_keys
    for key, fn in sv.CHECK_MAP.items():
        assert callable(fn), f"CHECK_MAP[{key!r}] is not callable: {fn!r}"
