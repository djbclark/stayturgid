#!/usr/bin/env python3
"""Cross-platform hostname auditor and automated reconciler for macOS, Linux, and Android devices."""

from __future__ import annotations

import os
import subprocess
import sys

TARGET_MAC_NAME = "mac"
ANDROID_TARGETS = {
    "100.123.218.30:5555": "s24",
    "100.65.230.108:5555": "p7a",
    "100.124.55.39:5555": "hd8",
}
KNOWN_LINUX_HOSTS = {
    "100.72.30.90": "p7a-kvm",
    "vps-primary": "vps-primary",
}


def is_darwin() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def audit_mac_hostname() -> bool:
    if is_darwin():
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
    return True


def audit_local_linux_hostname(expected_name: str) -> bool:
    if is_linux():
        print("=== Linux Local Hostname Audit ===")
        try:
            r = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5)
            current_name = r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            current_name = "unknown"

        print(f"Current Linux Hostname: {current_name}")

        if current_name == expected_name:
            print(f"✓ Linux hostname is fully aligned with canonical name '{expected_name}'.")
            return True

        print(f"\n-> Reconciling local Linux hostname (current: '{current_name}') -> '{expected_name}'...")
        try:
            r = subprocess.run(
                ["sudo", "-n", "hostnamectl", "set-hostname", expected_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                print(f"✓ Successfully reconciled Linux hostname to '{expected_name}'.")
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass

        print(f"⚠️ WARNING: Linux hostname differs from canonical name '{expected_name}'!")
        print(f"To align your Linux hostname, please run:\n  sudo hostnamectl set-hostname '{expected_name}'\n")
        return False
    return True


def audit_remote_linux_hosts() -> None:
    print("=== Remote Linux Nodes Audit ===")
    for addr, expected_name in KNOWN_LINUX_HOSTS.items():
        try:
            r = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", f"djbclark@{addr}", "hostname"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                current_name = r.stdout.strip()
                if current_name == expected_name:
                    print(f"✓ Remote Linux node {addr} ({expected_name}) hostname is aligned.")
                else:
                    print(f"⚠️ Remote Linux node {addr} hostname is '{current_name}' (expected: '{expected_name}')!")
                    print(f"  Run on {addr}: sudo hostnamectl set-hostname '{expected_name}'")
            else:
                print(f"ℹ️ Remote Linux node {addr} ({expected_name}) unreachable or offline.")
        except (OSError, subprocess.TimeoutExpired):
            print(f"ℹ️ Remote Linux node {addr} ({expected_name}) offline.")


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
    linux_ok = audit_local_linux_hostname(os.environ.get("STAYTURGID_EXPECTED_HOST", "vps-primary"))
    audit_remote_linux_hosts()
    reconcile_android_hostnames()
    return 0 if (mac_ok and linux_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
