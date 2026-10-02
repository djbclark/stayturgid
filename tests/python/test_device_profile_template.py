"""device.json must render valid JSON for every host in the live taxonomy.

read_device_profile() in stayturgid_repair.py / stayturgid_shell.py had been
reading this file with nothing writing it, so t2e — onboarded after the AutoJs6
flow that used to template the older /sdcard/stayturgid_device.json path was
retired — reported device_profile=MISSING on every repair cycle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from ansible.plugins.filter.core import FilterModule
from jinja2 import Environment, FileSystemLoader, StrictUndefined

REPO = Path(__file__).resolve().parents[2]
GROUP_VARS = REPO / "ansible/inventory/group_vars"
TEMPLATES = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/templates"

# The example taxonomy, not the private site overlay: these tests must pass on a
# clean checkout with no site-* sibling present.
TAXONOMY = {
    "oneui-device": ["vendor_samsung.yml", "oneui_7.yml", "model_galaxy_s24.yml", "android_16.yml"],
    "stock-android-device": ["vendor_google.yml", "model_pixel_7a.yml", "android_16.yml"],
    "fireos-device": ["vendor_amazon.yml", "model_kindle_hd8.yml", "android_11.yml"],
    "bare-device": [],  # a host with nothing but all.yml, like t2e before a model file exists
}


def _render(host: str, group_files: list[str], **overrides: object) -> dict:
    variables: dict = yaml.safe_load((GROUP_VARS / "all.yml").read_text(encoding="utf-8"))
    for name in group_files:
        path = GROUP_VARS / name
        if path.exists():
            variables.update(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    variables["inventory_hostname"] = host
    # all.yml stores these as Ansible-only expressions over ansible_host
    # ("{{ ansible_host is match('^100\\.') }}"), which a plain Jinja harness
    # cannot evaluate — replace, do not setdefault, or the raw string lands in
    # the rendered JSON.
    variables["stayturgid_tailscale_enabled"] = True
    variables["stayturgid_tailscale_ip"] = "100.0.0.11"
    variables.update(overrides)

    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    # Only `bool`, by name: Ansible ships its own `default` filter that does not
    # tolerate StrictUndefined outside a real templar, so bulk-updating the
    # filter set would clobber Jinja's and break `| default(...)` in the
    # template.
    environment.filters["bool"] = FilterModule().filters()["bool"]
    return json.loads(environment.get_template("device.json.j2").render(**variables))


@pytest.mark.parametrize("host,group_files", sorted(TAXONOMY.items()))
def test_device_profile_renders_valid_json(host: str, group_files: list[str]) -> None:
    profile = _render(host, group_files)
    # `id` is what stayturgid_repair.py checks to decide device_profile=MISSING.
    assert profile["id"] == host
    assert profile["label"]
    assert profile["sdRoot"]
    # These two are read as `is True` / `is False`, so a string would silently
    # take neither branch.
    assert isinstance(profile["tailscaleEnabled"], bool)
    assert isinstance(profile["privilegedShellExpected"], bool)


def test_no_local_adb_host_does_not_expect_a_privileged_shell() -> None:
    """Fire OS gets its uid-2000 shell from the Mac, not Termux loopback."""
    fireos = _render("fireos-device", TAXONOMY["fireos-device"])
    assert fireos["privilegedShellExpected"] is False
    # Only that the override is in play — this harness does not do Ansible's
    # recursive templating, so the value still carries a literal {{ termux_home }}.
    assert fireos["sdRoot"] != "/sdcard/stayturgid", "vendor_amazon overrides the SD root"

    normal = _render("oneui-device", TAXONOMY["oneui-device"])
    assert normal["privilegedShellExpected"] is True


def test_bool_coercion_survives_the_string_false() -> None:
    """A bool arriving as the string "False" is truthy in Jinja without `| bool`."""
    profile = _render(
        "bare-device",
        [],
        stayturgid_no_local_adb="False",
        stayturgid_tailscale_enabled="False",
        stayturgid_wireless_debug_ui_fallback="False",
    )
    assert profile["privilegedShellExpected"] is True
    assert profile["tailscaleEnabled"] is False
    assert profile["wirelessDebugUiFallback"] is False


def test_unset_shizuku_coords_omit_the_key_rather_than_emit_null() -> None:
    bare = _render("bare-device", [])
    assert "shizukuStartCoords" not in bare

    with_coords = _render("bare-device", [], stayturgid_shizuku_start_coords={"x": 227, "y": 1977})
    assert with_coords["shizukuStartCoords"] == {"x": 227, "y": 1977}


def test_tailscale_ip_is_null_not_the_string_none_when_absent() -> None:
    profile = _render("bare-device", [], stayturgid_tailscale_enabled=False, stayturgid_tailscale_ip=None)
    assert profile["tailscaleIp"] is None
