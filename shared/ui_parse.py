#!/usr/bin/env python3
"""Pure uiautomator XML helpers (Mac + Termux).

No adb / SSH — unit-tested. Imported by shared/mac/stayturgid_device.py
(compat re-export) and on-device screen-control scripts.
"""
from __future__ import annotations

import re


def parse_switch(xml, label):
    """From a uiautomator XML dump, find the Switch adjacent to <label> and
    return (checked_bool, cx, cy) center, or None."""
    if label not in (xml or ""):
        return None
    idx = xml.index(label)
    tail = xml[idx:]
    m = re.search(
        r'android\.widget\.Switch[^>]*?checked="(true|false)"[^>]*?'
        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        tail,
    )
    if not m:
        m = re.search(
            r'android\.widget\.Switch[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            r'[^>]*?checked="(true|false)"',
            tail,
        )
        if not m:
            return None
        x1, y1, x2, y2, checked = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
            m.group(5),
        )
    else:
        checked, x1, y1, x2, y2 = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
            m.group(5),
        )
    cx = (int(x1) + int(x2)) // 2
    cy = (int(y1) + int(y2)) // 2
    return (checked == "true", cx, cy)


def parse_button_center(xml, resource_id):
    """Center (cx, cy) of the node with the given resource-id, or None."""
    m = re.search(
        re.escape(resource_id) + r'"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml or "",
    )
    if not m:
        return None
    x1, y1, x2, y2 = (int(m.group(i)) for i in range(1, 5))
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def parse_text_center(xml, text):
    """Center of a node whose text= attribute equals text (exact match)."""
    if not xml or not text:
        return None
    esc = re.escape(text)
    m = re.search(
        r'text="' + esc + r'"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml,
    )
    if not m:
        m = re.search(
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?text="' + esc + r'"',
            xml,
        )
    if not m:
        return None
    x1, y1, x2, y2 = (int(m.group(i)) for i in range(1, 5))
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def parse_content_desc_center(xml, desc):
    """Center of a node whose content-desc equals desc (exact match)."""
    if not xml or not desc:
        return None
    esc = re.escape(desc)
    m = re.search(
        r'content-desc="' + esc + r'"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml,
    )
    if not m:
        m = re.search(
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?content-desc="'
            + esc
            + r'"',
            xml,
        )
    if not m:
        return None
    x1, y1, x2, y2 = (int(m.group(i)) for i in range(1, 5))
    return ((x1 + x2) // 2, (y1 + y2) // 2)
