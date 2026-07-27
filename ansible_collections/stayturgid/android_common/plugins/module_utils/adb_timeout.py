# -*- coding: utf-8 -*-
"""Command execution with systemic timeout support for stayturgid.android_common modules."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os

# Default timeout durations in seconds
DEFAULT_FAST_TIMEOUT = 30  # Fast queries: adb devices, adb connect, adb shell getprop, pm list, settings
DEFAULT_SLOW_TIMEOUT = 180  # Slow transfers/installs: adb push, adb install, gh release download, apksigner sign

_CACHED_TIMEOUT_BIN = None


def resolve_timeout_bin(get_bin_path_fn=None):
    """Find local coreutils `timeout` binary path or return None if missing."""
    global _CACHED_TIMEOUT_BIN
    if _CACHED_TIMEOUT_BIN is not None:
        return _CACHED_TIMEOUT_BIN

    bin_path = None
    if get_bin_path_fn is not None:
        try:
            bin_path = get_bin_path_fn("timeout")
        except Exception:
            bin_path = None

    if not bin_path:
        for candidate in ("/opt/homebrew/bin/timeout", "/usr/bin/timeout", "/bin/timeout"):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                bin_path = candidate
                break

    if bin_path:
        _CACHED_TIMEOUT_BIN = bin_path
    return bin_path


def run_command_with_timeout(run_command_fn, cmd, timeout=DEFAULT_FAST_TIMEOUT, get_bin_path_fn=None):
    """Execute cmd via run_command_fn, prefixing with `timeout <seconds>` if available.

    Handles returncode 124 (coreutils timeout command timeout) by returning
    rc=124 and appending an explicit error message to stderr.
    """
    timeout_bin = resolve_timeout_bin(get_bin_path_fn=get_bin_path_fn)

    exec_cmd = list(cmd)
    if timeout_bin and timeout and timeout > 0 and (not exec_cmd or exec_cmd[0] != timeout_bin):
        exec_cmd = [timeout_bin, str(int(timeout))] + exec_cmd

    rc, out, err = run_command_fn(exec_cmd)
    if rc == 124:
        timeout_msg = "ADB command timed out after %ds: %s" % (timeout, " ".join(cmd))
        err = (err + "\n" if err else "") + timeout_msg
    return rc, out, err
