#!/usr/bin/env python3
"""REMOVED — use stayturgid.android_common.shizuku_grant instead.

This stub remains so old docs/scripts fail with a clear message.

Ansible (from repo root)::

    ANSIBLE_CONFIG=ansible/ansible.cfg ansible localhost \\
      -m stayturgid.android_common.shizuku_grant \\
      -a "device=p7a package=com.machiav3lli.fdroid" -c local

See ansible_collections/docs/modules/shizuku_grant.md
"""
import sys

sys.stderr.write(
    "grant_neo_store_shizuku.py was removed in collection v1.4.0.\n"
    "Use stayturgid.android_common.shizuku_grant (see script docstring).\n"
)
sys.exit(2)
