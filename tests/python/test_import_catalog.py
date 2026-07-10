"""Unit tests for control/tools/obtainium/import_catalog.py deep-link import helpers."""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "control", "tools", "obtainium"))
import import_catalog as ic  # noqa: E402


SAMPLE_APPS = [
    {"id": "org.autojs.autojs6", "name": "AutoJs6", "url": "https://github.com/x/y"},
    {"id": "com.aurora.store", "name": "Aurora Store", "url": "https://gitlab.com/x/y"},
]


def test_build_import_uri_prefix_and_roundtrip():
    uri = ic.build_import_uri(SAMPLE_APPS)
    assert uri.startswith("obtainium://apps/")
    payload = uri[len("obtainium://apps/"):]
    assert json.loads(urllib.parse.unquote(payload)) == SAMPLE_APPS


def test_import_dialog_detection():
    xml = '<node content-desc="Import apps" /><node content-desc="Continue" bounds="[1,2][3,4]" />'
    assert ic.import_dialog_visible(xml)
    assert ic.continue_button(xml) == (2, 3)


def test_continue_button_missing():
    assert ic.continue_button('<node content-desc="Cancel" />') is None


def test_catalog_tracked_requires_all_names():
    xml = '<node content-desc="AutoJs6&#10;By x" />'
    assert ic.catalog_tracked(xml, ["AutoJs6"]) is True
    assert ic.catalog_tracked(xml, ["AutoJs6", "Aurora Store"]) is False


def test_app_visible_handles_handsets_newlines():
    # Handsets dump uses real newlines; uiautomator uses &#10;
    hs = 'ImageView  "AutoJs6\nBy SuperMonster003\n6.7.0 → Unknown"'
    assert ic.app_visible(hs, "AutoJs6") is True
    assert ic.app_visible(hs, "Shizuku (thedjchi)") is False


def test_app_visible_parenthetical_name():
    xml = '<node content-desc="Shizuku&#10;By thedjchi" />'
    assert ic.app_visible(xml, "Shizuku (thedjchi)") is True
    assert ic.app_visible(xml, "Tailscale") is False


def test_tracking_label_strips_parenthetical():
    assert ic.tracking_label("Shizuku (thedjchi)") == "Shizuku"


def test_canary_names_for_known_catalogs():
    # Canaries are filtered to apps actually present in the catalog payload.
    apps = [
        {"id": "x", "name": "AutoJs6"},
        {"id": "com.termux", "name": "Termux"},
        {"id": "moe.shizuku.privileged.api", "name": "Shizuku (thedjchi)"},
        {"id": "com.tailscale.ipn", "name": "Tailscale"},
    ]
    assert ic.canary_names("all", ic.CATALOGS["all"], apps) == ic.CANARY_APPS["all"]
    assert ic.canary_names("autojs6", ic.CATALOGS["autojs6"], apps) == ["AutoJs6"]


def test_canary_names_drops_missing_from_payload():
    apps = [{"id": "x", "name": "AutoJs6"}, {"id": "com.termux", "name": "Termux"}]
    assert ic.canary_names("all", ic.CATALOGS["all"], apps) == ["AutoJs6", "Termux"]


def test_catalog_tracked_empty_names():
    assert ic.catalog_tracked("<hierarchy />", []) is True
