# -*- coding: utf-8 -*-
"""F-Droid URI helpers shared by fdroid collection modules."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re


def normalize_url(url):
    return (url or "").strip().rstrip("/")


def normalize_fingerprint(fp):
    if not fp:
        return ""
    return re.sub(r"[^0-9A-Fa-f]", "", str(fp)).upper()


def fdroidrepos_uri(address, fingerprint=None):
    hostpath = re.sub(r"^https?://", "", normalize_url(address), count=1)
    uri = "fdroidrepos://" + hostpath
    fp = normalize_fingerprint(fingerprint)
    if fp:
        uri += "?fingerprint=" + fp
    return uri
