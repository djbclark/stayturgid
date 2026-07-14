"""Centralized guard for stayturgid UI automation.

Blocks UI automation unless STAYTURGID_ALLOW_UI_AUTOMATION=1 is set.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

try:
    from control.lib.logging import ERR, log
except ImportError:
    log = None
    ERR = 3


def is_android() -> bool:
    return os.path.exists("/system/bin/app_process") or "com.termux" in os.environ.get("PREFIX", "")


def get_state_file() -> Path:
    if is_android():
        return Path("/sdcard/stayturgid/state/pending_ui.json")
    return Path(os.path.expanduser("~/.config/stayturgid/state/pending_ui.json"))


def check_ui_guard(
    host: str,
    action_type: str,
    message: str,
    detect_fn: Callable[[], bool] | None = None,
) -> bool:
    """Blocks UI automation if STAYTURGID_ALLOW_UI_AUTOMATION is not '1'.

    Logs the block, sets pending UI request on the dashboard, and polls
    until the user clicks 'Done' on the dashboard or `detect_fn` returns True.
    """
    if os.environ.get("STAYTURGID_ALLOW_UI_AUTOMATION") == "1":
        return True

    # Centralized warning format
    full_warning = f"\n🚨📱🚨 MANUAL ACTION REQUIRED on {host} ({action_type}):\n{message}\n"
    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.write(full_warning)
    sys.stderr.write("=" * 80 + "\n\n")

    # Log the blocked action to errors.log
    log_msg = f"UI_AUTOMATION_GATED: {host} blocked on {action_type}. {message}"
    if log is not None:
        log("errors.log", ERR, log_msg)
    else:
        # Fallback logging if run on-device or without logging library
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"{timestamp}  ERR {log_msg}\n"
        err_log = (
            Path("/sdcard/stayturgid/logs/errors.log")
            if is_android()
            else Path(os.path.expanduser("~/.config/stayturgid/logs/errors.log"))
        )
        try:
            err_log.parent.mkdir(parents=True, exist_ok=True)
            with open(err_log, "a") as f:
                f.write(log_line)
        except Exception:
            pass

    # Write state JSON file
    started_at = time.time()
    started_at_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at))
    state_data = {
        "host": host,
        "action_type": action_type,
        "message": message,
        "started_at": started_at,
        "started_at_str": started_at_str,
        "status": "pending",
    }

    state_file = get_state_file()
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state_data, indent=2))
    except Exception as e:
        sys.stderr.write(f"WARN: failed to write state file {state_file}: {e}\n")

    sys.stderr.write("Entering wait loop. Perform the action manually and click 'Done' on the dashboard.\n")
    try:
        while True:
            # Check state file status
            status = "pending"
            if state_file.is_file():
                try:
                    data = json.loads(state_file.read_text())
                    status = data.get("status", "pending")
                except Exception:
                    pass

            if status == "done":
                sys.stderr.write("\nUser clicked Done/Resume on dashboard. Proceeding...\n")
                break

            # Check if auto-detected
            if detect_fn:
                try:
                    if detect_fn():
                        sys.stderr.write("\nAuto-detected manual action completed! Proceeding...\n")
                        break
                except Exception:
                    pass

            elapsed = int(time.time() - started_at)
            sys.stderr.write(f"\rWaiting for human UI action on {host} ({action_type})... {elapsed}s elapsed")
            sys.stderr.flush()
            time.sleep(2)
    finally:
        # Cleanup state file on exit
        if state_file.is_file():
            try:
                state_file.unlink()
            except Exception:
                pass

    return True
