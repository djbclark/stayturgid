"""Utility helpers for a11y detection in Ansible modules (Python 2/3 compat).

Detection-only — no automatic writes or merge-repair.
"""
from __future__ import absolute_import, division, print_function

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


def has_autojs6(raw):
    return AUTOJS6_A11Y in parse_services(raw)
