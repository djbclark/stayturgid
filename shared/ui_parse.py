#!/usr/bin/env python3
"""Pure uiautomator XML helpers (Mac + Termux).

No adb / SSH — unit-tested. Imported by shared/mac/stayturgid_device.py
(compat re-export) and on-device screen-control scripts.
"""
from __future__ import annotations

import re


def _parse_switch_attrs(node):
    """Parse checked + bounds from a single <node …> string (any attr order)."""
    m = re.search(r'\bchecked="(true|false)"', node)
    b = re.search(r'\bbounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
    if not m or not b:
        return None
    cx = (int(b.group(1)) + int(b.group(3))) // 2
    cy = (int(b.group(2)) + int(b.group(4))) // 2
    return (m.group(1) == "true", cx, cy)


def _parse_switch_in_tail(tail):
    """First Switch in tail (adjacent TextView + Switch layout)."""
    m = re.search(
        r'android\.widget\.Switch[^>]*?checked="(true|false)"[^>]*?'
        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        tail,
    )
    if m:
        return _switch_from_match(m, bounds_first=False)
    m = re.search(
        r'android\.widget\.Switch[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        r'[^>]*?checked="(true|false)"',
        tail,
    )
    if m:
        return _switch_from_match(m, bounds_first=True)
    # checked/bounds may appear before class= on the same node
    m = re.search(
        r"<node\b(?=[^>]*\bclass=\"android\.widget\.Switch\")[^>]*>",
        tail,
    )
    if m:
        return _parse_switch_attrs(m.group(0))
    return None


def parse_switch(xml, label):
    """From a uiautomator XML dump, find the Switch for <label>.

    Prefers a Switch node that itself carries text= or content-desc= equal to
    the label; otherwise uses the first Switch after the label string (adjacent
    TextView + Switch layout).
    """
    if label not in (xml or ""):
        return None
    esc = re.escape(label)
    for attr in ("text", "content-desc"):
        for m in re.finditer(
            r"<node\b(?=[^>]*\b%s=\"%s\")(?=[^>]*\bclass=\"android\.widget\.Switch\")[^>]*>"
            % (attr, esc),
            xml,
        ):
            parsed = _parse_switch_attrs(m.group(0))
            if parsed is not None:
                return parsed
    idx = xml.index(label)
    return _parse_switch_in_tail(xml[idx:])


def _switch_from_match(m, bounds_first=False):
    if bounds_first:
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
