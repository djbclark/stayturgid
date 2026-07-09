#!/usr/bin/env python3
"""Localhost:5555 privileged shell for Termux on-device scripts.

Matches stayturgid_repair.py channel (uid 2000). Fire OS hosts with
privilegedShellExpected=false must not use this — Mac USB adb instead.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
STG = os.path.join(HOME, ".stayturgid")
SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")
SERIAL = "localhost:5555"


def _ensure_env():
    os.environ.setdefault("PATH", "%s/bin:/system/bin" % PREFIX)
    os.environ.setdefault("TMPDIR", "%s/tmp" % PREFIX)
    os.environ.setdefault("PREFIX", PREFIX)
    os.environ.setdefault("HOME", HOME)
    env_path = os.path.join(STG, "env")
    if os.path.isfile(env_path):
        # Lightweight: only STAYTURGID_SD is required for profile paths.
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export STAYTURGID_SD="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            os.environ["STAYTURGID_SD"] = val
                            global SD
                            SD = val
        except OSError:
            pass


def run(args, timeout=60, input_text=None):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def connect(timeout=15):
    _ensure_env()
    r = run(["adb", "connect", SERIAL], timeout=timeout)
    return r is not None and r.returncode == 0


def shell(*args, timeout=30):
    """adb -s localhost:5555 shell … → (rc, stdout)."""
    connect()
    r = run(["adb", "-s", SERIAL, "shell"] + list(args), timeout=timeout)
    if r is None:
        return 127, ""
    return r.returncode, (r.stdout or "").replace("\r", "")


def shell_fn(serial, *args, timeout=30):
    """Adapter matching ui_clearance / ScreenControlSession shell(serial, *args)."""
    del serial  # always localhost:5555 on-device
    return shell(*args, timeout=timeout)


def read_device_profile():
    _ensure_env()
    for path in (
        os.path.join(SD, "state", "device.json"),
        os.path.join(STG, "state", "device.json"),
        os.path.join(STG, "shared", "state", "device.json"),
    ):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def privileged_shell_expected():
    """False on Fire OS / split-storage hosts (Mac USB adb only)."""
    prof = read_device_profile()
    if prof.get("privilegedShellExpected") is False:
        return False
    if prof.get("privilegedShellExpected") is True:
        return True
    sd = os.environ.get("STAYTURGID_SD", SD)
    if sd.startswith(HOME) or "/com.termux/" in sd:
        return False
    return True


def privileged_shell_ok():
    if not privileged_shell_expected():
        return False
    if not connect():
        return False
    rc, out = shell("id", "-u")
    return rc == 0 and out.strip() == "2000"


def device_label():
    prof = read_device_profile()
    return prof.get("label") or prof.get("alias") or "this phone"


def lib_paths():
    """sys.path entries for ~/.stayturgid/lib and repo shared/ when developing."""
    paths = [
        os.path.join(STG, "lib"),
        os.path.join(HOME, ".stayturgid", "lib"),
    ]
    # Repo checkout (Mac unit tests / ad-hoc): termux/py → repo root
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    paths.append(os.path.join(repo, "shared"))
    paths.append(repo)
    return paths


def ensure_lib_path():
    for p in lib_paths():
        if p and p not in sys.path and os.path.isdir(p):
            sys.path.insert(0, p)
        elif p and p not in sys.path:
            # Allow importing from repo shared/ even if only parent exists
            parent = os.path.dirname(p)
            if parent and os.path.isdir(parent) and parent not in sys.path:
                sys.path.insert(0, parent)
