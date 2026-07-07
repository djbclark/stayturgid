# -*- coding: utf-8 -*-
"""adb install output parsing for the android_apk module."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re


def parse_install_result(output):
    """(rc-agnostic) adb install output -> (ok, reason).

    adb sometimes exits 0 while printing a Failure line, so callers must
    check the text, not just the return code.
    """
    text = (output or "").replace("\r", "")
    m = re.search(r"(INSTALL_[A-Z_]+)", text)
    if m:
        return False, m.group(1)
    if re.search(r"^Failure", text, re.M):
        return False, text.strip().splitlines()[-1]
    if re.search(r"^Success", text, re.M):
        return True, "Success"
    return False, text.strip() or "no output from adb install"
