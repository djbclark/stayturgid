# -*- coding: utf-8 -*-
"""Pure Shizuku grant helpers (mirrors control/lib/stayturgid_device.py)."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import re

SHIZUKU_PERMISSION = "moe.shizuku.manager.permission.API_V23"
DEFAULT_SHIZUKU_JSON = "/data/local/tmp/shizuku/shizuku.json"
DEFAULT_STAGING = "/sdcard/Download/shizuku-grant.json"


def parse_uid(pm_output):
    """`pm list packages -U <pkg>` -> uid string, or None."""
    m = re.search(r"uid:(\d+)", pm_output or "")
    return m.group(1) if m else None


def patch_shizuku_json(current_text, uid, pkg):
    """Add/replace a uid->pkg authorization, preserving all other entries."""
    uid = int(uid)
    raw = (current_text or "").strip()
    try:
        data = json.loads(raw) if raw else {"version": 2, "packages": []}
    except ValueError:
        data = {"version": 2, "packages": []}
    pkgs = [e for e in data.get("packages", []) if e.get("uid") != uid]
    pkgs.append({"uid": uid, "flags": 2, "packages": [pkg]})
    data["packages"] = pkgs
    return json.dumps(data, separators=(",", ":"))
