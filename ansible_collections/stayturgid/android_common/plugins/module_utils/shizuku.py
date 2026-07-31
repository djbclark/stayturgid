# -*- coding: utf-8 -*-
"""Pure Shizuku grant helpers (mirrors control/lib/stayturgid_device.py)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

SHIZUKU_PERMISSION = "moe.shizuku.manager.permission.API_V23"


def parse_uid(pm_output):
    """`pm list packages -U <pkg>` -> uid string, or None."""
    m = re.search(r"uid:(\d+)", pm_output or "")
    return m.group(1) if m else None
