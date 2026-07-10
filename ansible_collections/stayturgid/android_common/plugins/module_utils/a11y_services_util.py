# -*- coding: utf-8 -*-
"""Accessibility service list helpers (colon-separated settings value)."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import os


AUTOJS6_A11Y = (
    "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"
)


def normalize_value(raw):
    text = (raw or "").strip()
    if text in ("", "null", "None"):
        return ""
    return text


def parse_services(raw):
    text = normalize_value(raw)
    if not text:
        return []
    seen = set()
    out = []
    for part in text.split(":"):
        svc = part.strip()
        if not svc or svc in seen or svc == "null":
            continue
        if "/" not in svc or "." not in svc.split("/", 1)[0]:
            continue
        seen.add(svc)
        out.append(svc)
    return out


def join_services(services):
    return ":".join(parse_services(":".join(services)))


def merge_service_lists(*groups):
    merged = []
    seen = set()
    for group in groups:
        for svc in group:
            if svc and svc not in seen:
                seen.add(svc)
                merged.append(svc)
    return join_services(merged)


def load_profiles(profiles_path):
    if not profiles_path or not os.path.isfile(profiles_path):
        return {"devices": {}}
    with open(profiles_path) as f:
        return json.load(f)


def profile_services(alias, profiles_path):
    data = load_profiles(profiles_path)
    entry = (data.get("devices") or {}).get(alias) or {}
    return list(entry.get("services") or [])


def backup_file_for(alias, backups_dir):
    return os.path.join(backups_dir, "%s.txt" % alias)


def read_backup_file(path):
    if not path or not os.path.isfile(path):
        return ""
    with open(path) as f:
        return normalize_value(f.read())


def write_backup_file(path, value):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        f.write(normalize_value(value) + "\n")


def desired_services(alias, live, profiles_path, ensure_autojs6=True):
    groups = [parse_services(live), profile_services(alias, profiles_path)]
    if ensure_autojs6:
        groups.append([AUTOJS6_A11Y])
    return merge_service_lists(*groups)


def services_lost(before, after):
    before_set = set(parse_services(before))
    after_set = set(parse_services(after))
    return sorted(before_set - after_set)
