"""Sync guard: the obtainium_apps role defaults (authoritative) must stay
aligned with obtainium/stayturgid-apps.json (the adb-fallback rendering used
by obtainium/mac/sync_to_device.py when SSH is unavailable)."""
import json
import os

import yaml

from conftest import REPO


def load_role_specs():
    path = os.path.join(REPO, "ansible", "roles", "obtainium_apps", "defaults", "main.yml")
    return yaml.safe_load(open(path))["stayturgid_obtainium_apps"]


def load_fallback_apps():
    path = os.path.join(REPO, "obtainium", "stayturgid-apps.json")
    return json.load(open(path))["apps"]


def test_same_app_ids_and_urls():
    role = {(a["id"], a["url"]) for a in load_role_specs()}
    fallback = {(a["id"], a["url"]) for a in load_fallback_apps()}
    assert role == fallback, (
        "role defaults and obtainium/stayturgid-apps.json diverged — "
        "update both (role defaults are authoritative)"
    )


def test_same_apk_filters():
    role = {
        a["id"]: (a.get("settings") or {}).get("apkFilterRegEx", "")
        for a in load_role_specs()
    }
    fallback = {
        a["id"]: json.loads(a["additionalSettings"]).get("apkFilterRegEx", "")
        for a in load_fallback_apps()
    }
    assert role == fallback
