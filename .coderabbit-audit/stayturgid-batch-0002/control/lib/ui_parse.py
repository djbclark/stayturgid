#!/usr/bin/env python3
"""Pure uiautomator XML helpers (Mac + Termux).

No adb / SSH — unit-tested. Imported by control/lib/stayturgid_device.py
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


def _label_center_y(xml, label):
    """Vertical center of a text= or content-desc= node equal to label, or None."""
    esc = re.escape(label)
    for attr in ("text", "content-desc"):
        m = re.search(
            r'%s="%s"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' % (attr, esc),
            xml,
        )
        if not m:
            m = re.search(
                r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*%s="%s"' % (attr, esc),
                xml,
            )
        if m:
            return (int(m.group(2)) + int(m.group(4))) // 2
    return None


def _nearest_switch_by_y(xml, label_y, max_dy=120):
    """Switch whose vertical center is closest to label_y (AutoJs6 drawer)."""
    best = None
    for m in re.finditer(r"<node\b[^>]*>", xml or ""):
        node = m.group(0)
        if "android.widget.Switch" not in node:
            continue
        parsed = _parse_switch_attrs(node)
        if parsed is None:
            continue
        _checked, _cx, cy = parsed
        dy = abs(cy - label_y)
        if dy > max_dy:
            continue
        if best is None or dy < best[0]:
            best = (dy, parsed)
    return best[1] if best else None


def parse_switch(xml, label):
    """From a uiautomator XML dump, find the Switch for <label>.

    Order:
      1. Switch node that itself has text=/content-desc= equal to label
      2. Switch whose Y center is nearest the label TextView (AutoJs6 drawer
         dumps Switch *before* the label text — string-order search fails)
      3. First Switch after the label string (legacy Obtainium-style layout)
      4. Last Switch before the label string within a short window
    """
    if label not in (xml or ""):
        return None
    esc = re.escape(label)
    for attr in ("text", "content-desc"):
        for m in re.finditer(
            r"<node\b(?=[^>]*\b%s=\"%s\")(?=[^>]*\bclass=\"android\.widget\.Switch\")[^>]*>" % (attr, esc),
            xml,
        ):
            parsed = _parse_switch_attrs(m.group(0))
            if parsed is not None:
                return parsed

    label_y = _label_center_y(xml, label)
    if label_y is not None:
        near = _nearest_switch_by_y(xml, label_y)
        if near is not None:
            return near

    idx = xml.index(label)
    after = _parse_switch_in_tail(xml[idx:])
    if after is not None:
        return after
    # Switch often precedes the label in the dump (end-aligned row).
    head = xml[max(0, idx - 1200) : idx]
    last = None
    for m in re.finditer(r"<node\b(?=[^>]*\bclass=\"android\.widget\.Switch\")[^>]*>", head):
        parsed = _parse_switch_attrs(m.group(0))
        if parsed is not None:
            last = parsed
    return last


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
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?content-desc="' + esc + r'"',
            xml,
        )
    if not m:
        return None
    x1, y1, x2, y2 = (int(m.group(i)) for i in range(1, 5))
    return ((x1 + x2) // 2, (y1 + y2) // 2)
