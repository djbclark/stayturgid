#!/usr/bin/env python3
"""On-device Shizuku grant for AutoJs6 (Termux → localhost:5555).

Usage: stayturgid_grant_shizuku.py
"""
from __future__ import annotations

import json
import os
import re
import sys

import stayturgid_shell as sh

AUTOJS_PKG = "org.autojs.autojs6"
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
SHIZUKU_JSON = "/data/local/tmp/shizuku/shizuku.json"
STAGING = "/sdcard/Download/shizuku.json"


def patch_shizuku_json(current_text, uid, pkg):
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


def parse_uid(pm_output):
    m = re.search(r"uid:(\d+)", pm_output or "")
    return m.group(1) if m else None


def read_shizuku_json():
    if sh.shell("true")[0] != 0:
        return "", False
    if sh.shell("test", "-f", SHIZUKU_JSON)[0] == 0:
        text = sh.shell("cat", SHIZUKU_JSON)[1]
        if not (text or "").strip():
            return "", False
        return text, True
    return "", True


def install_shizuku_json(content):
    os.makedirs(os.path.join(sh.STG, "tmp"), exist_ok=True)
    try:
        with open(STAGING, "w") as f:
            f.write(content)
    except OSError:
        tmp = os.path.join(sh.STG, "tmp", "shizuku.json")
        with open(tmp, "w") as f:
            f.write(content)
        rc, _ = sh.shell("cp", tmp, STAGING)
        if rc != 0:
            return False
    rc, _ = sh.shell("cp", STAGING, SHIZUKU_JSON)
    if rc != 0:
        return False
    sh.shell("chmod", "644", SHIZUKU_JSON)
    return True


def main(argv=None):
    del argv
    if not sh.privileged_shell_ok():
        sys.stderr.write("ERROR: localhost:5555 shell unavailable\n")
        return 1

    _rc, out = sh.shell("pm", "list", "packages", "-U", AUTOJS_PKG)
    uid = parse_uid(out)
    if not uid:
        sys.stderr.write("ERROR: could not resolve AutoJs6 uid\n")
        return 1

    sh.shell("pm", "grant", AUTOJS_PKG, SHIZUKU_PERM)

    current, ok = read_shizuku_json()
    if not ok:
        sys.stderr.write(
            "ERROR: unreadable %s — aborting (would clobber other grants)\n" % SHIZUKU_JSON
        )
        return 1

    patched = patch_shizuku_json(current, uid, AUTOJS_PKG)
    if not install_shizuku_json(patched):
        sys.stderr.write("ERROR: failed to install patched shizuku.json\n")
        return 1

    print("Shizuku: allowed AutoJs6 (uid=%s)" % uid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
