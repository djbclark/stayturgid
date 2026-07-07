"""Unit tests for obtainium/mac/import_catalog.py deep-link import helpers."""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "obtainium", "mac"))
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


def test_app_visible_parenthetical_name():
    xml = '<node content-desc="Shizuku&#10;By thedjchi" />'
    assert ic.app_visible(xml, "Shizuku (thedjchi)") is True
    assert ic.app_visible(xml, "Tailscale") is False


def test_tracking_label_strips_parenthetical():
    assert ic.tracking_label("Shizuku (thedjchi)") == "Shizuku"


def test_canary_names_for_known_catalogs():
    apps = [{"id": "x", "name": "AutoJs6"}]
    assert ic.canary_names("all", ic.CATALOGS["all"], apps) == ic.CANARY_APPS["all"]
    assert ic.canary_names("autojs6", ic.CATALOGS["autojs6"], apps) == ["AutoJs6"]


def test_catalog_tracked_empty_names():
    assert ic.catalog_tracked("<hierarchy />", []) is True
