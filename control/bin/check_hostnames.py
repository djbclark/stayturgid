#!/usr/bin/env python3
"""Hostname auditor and automated Android device name reconciler."""

from __future__ import annotations

import subprocess
import sys

TARGET_MAC_NAME = "mac"
ANDROID_TARGETS = {
    "100.123.218.30:5555": "s24",
    "100.65.230.108:5555": "p7a",
    "100.124.55.39:5555": "hd8",
}


def audit_mac_hostname() -> bool:
    print("=== macOS Hostname Audit ===")
    try:
        r = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=5)
        local_name = r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        local_name = "unknown"

    try:
        r = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True, timeout=5)
        comp_name = r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        comp_name = "unknown"

    print(f"Current LocalHostName: {local_name}")
    print(f"Current ComputerName:  {comp_name}")

    if local_name == TARGET_MAC_NAME and comp_name == TARGET_MAC_NAME:
        print("✓ macOS hostname is fully aligned with canonical name 'mac'.")
        return True

    print("\n⚠️ WARNING: macOS hostname differs from canonical name 'mac'!")
    print("To align your macOS system hostname with Tailscale 'mac', please run:")
    print(
        f"  sudo scutil --set ComputerName '{TARGET_MAC_NAME}' && "
        f"sudo scutil --set LocalHostName '{TARGET_MAC_NAME}' && "
        f"sudo scutil --set HostName '{TARGET_MAC_NAME}'\n"
    )
    return False


def reconcile_android_hostnames() -> None:
    print("=== Android Device Name Reconciliation ===")
    for addr, expected_name in ANDROID_TARGETS.items():
        try:
            r = subprocess.run(
                ["adb", "-s", addr, "shell", "settings", "get", "global", "device_name"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            current_name = r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            current_name = "unreachable"

        if current_name == expected_name:
            print(f"✓ Android device at {addr} is set to '{expected_name}'.")
        else:
            print(f"-> Reconciling {addr} (current: '{current_name}') -> '{expected_name}'...")
            try:
                subprocess.run(
                    ["adb", "-s", addr, "shell", "settings", "put", "global", "device_name", expected_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                print(f"✓ Reconciled {addr} to '{expected_name}'.")
            except (OSError, subprocess.TimeoutExpired) as e:
                print(f"❌ Failed to reconcile {addr}: {e}")


def main() -> int:
    mac_ok = audit_mac_hostname()
    reconcile_android_hostnames()
    return 0 if mac_ok else 1


if __name__ == "__main__":
    sys.exit(main())
