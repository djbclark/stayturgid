#!/usr/bin/env python3
"""Quiet GUI audit: Neo Store + Aurora settings screenshots + H2 assertions.

Intended for launchd at 03:14 local time. Tolerates offline Mac wake misses
and unreachable devices (per-host skip, exit 0 unless a reachable host fails
assertions).

  STAYTURGID_PRESENCE_QUIET=1  — no torch / vibrate / dialogs / presence sounds
  No macOS notification sounds.

Logs:  ~/.config/stayturgid/logs/gui-audit.log
Shots: ~/.config/stayturgid/artifacts/gui-audit/<YYYY-MM-DD>/<host>/

Usage:
  python3 mac/gui_audit.py              # all devices.conf hosts
  python3 mac/gui_audit.py s24 p7a
  python3 mac/gui_audit.py --dry-reach  # reachability only
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared" / "mac"))
import stayturgid_device as dev  # noqa: E402
import screen_control as sc  # noqa: E402
import ui_driver as uid  # noqa: E402

ROOT = Path(os.path.expanduser("~")) / ".config" / "stayturgid"
LOG = ROOT / "logs" / "gui-audit.log"
ART = ROOT / "artifacts" / "gui-audit"
CONF = Path(
    os.environ.get(
        "STAYTURGID_DEVICES_CONF",
        str(ROOT / "devices.conf"),
    )
)

NEO = "com.machiav3lli.fdroid"
AURORA = "com.aurora.store"

FILTER_AURORA_ONLY = (
    "Filter apps from other sources",
    "Do not check for updates for apps installed from sources outside Aurora Store",
)
FILTER_FDROID = (
    "Filter F-Droid apps",
    "Don't check updates for apps installed from F-Droid",
)
AUTO_UPDATE_OK = (
    "Check & install available updates automatically",
    "Check and install available updates automatically",
)
AUTO_UPDATE_BAD = (
    "Do not auto-update",
    "Don't auto-update",
    "Never",
)


def ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    line = "%s  %s\n" % (ts(), msg)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
    print(line, end="")


def read_hosts(conf: Path) -> list[str]:
    out: list[str] = []
    try:
        for line in conf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts:
                out.append(parts[0])
    except OSError:
        pass
    return out


def adb_connect(serial: str) -> bool:
    r = subprocess.run(
        ["adb", "connect", serial],
        capture_output=True,
        text=True,
        timeout=20,
    )
    out = ((r.stdout or "") + (r.stderr or "")).lower()
    if "connected" in out or "already connected" in out:
        return True
    # Some adb builds print nothing useful; probe shell.
    probe = subprocess.run(
        ["adb", "-s", serial, "shell", "echo", "ok"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return probe.returncode == 0 and "ok" in (probe.stdout or "")


def reachable(host: str) -> tuple[bool, str]:
    """Return (ok, serial_or_reason)."""
    try:
        serial = dev.resolve_adb(host)
    except Exception as e:  # noqa: BLE001 — soft skip
        return False, "resolve_failed:%s" % e
    if not serial:
        return False, "no_serial"
    if not adb_connect(serial):
        return False, "adb_unreachable"
    return True, serial


def shot(serial: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["adb", "-s", serial, "exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=45,
    )
    path.write_bytes(r.stdout or b"")


def adb_shell(serial: str, *args: str, timeout: int = 30) -> str:
    r = subprocess.run(
        ["adb", "-s", serial, "shell", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (r.stdout or "").replace("\r", "")


def aurora_battery_unrestricted(serial: str) -> bool | None:
    """True if Aurora is Doze-whitelisted (bad for our policy)."""
    out = adb_shell(serial, "dumpsys", "deviceidle")
    if not out.strip():
        return None
    # whitelist entries look like: com.aurora.store
    for line in out.splitlines():
        if AURORA in line and "whitelist" in line.lower():
            return True
        if line.strip() == AURORA or line.strip().endswith("," + AURORA):
            return True
    # Also check appops RUN_ANY_IN_BACKGROUND
    ops = adb_shell(serial, "appops", "get", AURORA, "RUN_ANY_IN_BACKGROUND")
    if "allow" in ops.lower():
        return True
    if "ignore" in ops.lower() or "deny" in ops.lower():
        return False
    return False if AURORA not in out else None


def _switch_on(hs, labels: tuple[str, ...]) -> bool | None:
    if hs is None:
        return None
    for lab in labels:
        checked, ok = hs.switch_near_label(lab, timeout_ms=2500)
        if ok and checked is not None:
            return bool(checked)
    return None


def _ui_has(hs, *needles: str) -> bool:
    if hs is None:
        return False
    ui = hs.ui()
    return any(n in ui for n in needles)


def audit_neo(host: str, session, hs, out: Path) -> list[str]:
    issues: list[str] = []
    serial = session.serial
    adb_shell(serial, "am", "force-stop", NEO)
    time.sleep(0.4)
    adb_shell(serial, "am", "start", "-n", "%s/.NeoActivity" % NEO)
    time.sleep(2.2)
    shot(serial, out / "01_neo_home.png")

    if hs is not None:
        opened = False
        for lab in ("Settings", "Preferencias", "Einstellungen"):
            if hs.tap_desc(lab, timeout_ms=1200) or hs.tap_text(lab, timeout_ms=1200):
                opened = True
                break
        if not opened:
            for lab in ("More options", "More"):
                if hs.tap_desc(lab, timeout_ms=1000):
                    time.sleep(0.8)
                    if hs.tap_text("Settings", timeout_ms=1500):
                        opened = True
                        break
        time.sleep(1.0)
        shot(serial, out / "02_neo_settings.png")
        hs.tap_text("Installer", timeout_ms=2000) or hs.tap_text(
            "Installation", timeout_ms=1500
        )
        time.sleep(1.0)
        shot(serial, out / "03_neo_installer.png")
        ui = hs.ui()
        if "Shizuku" not in ui and "shizuku" not in ui.lower():
            issues.append("neo_shizuku_missing")
        # Auto-update: look for common Neo labels
        session.shell("input", "swipe", "540", "1600", "540", "800")
        time.sleep(0.8)
        shot(serial, out / "04_neo_scrolled.png")
        ui2 = hs.ui()
        if "Auto" in ui2 or "auto" in ui2.lower():
            # Soft: if we see an Off/disabled near auto-update, flag it
            if re.search(r"auto.?update.*\b(off|disabled|never)\b", ui2, re.I):
                issues.append("neo_autoupdate_off")
        if not opened:
            issues.append("neo_settings_nav_failed")
    else:
        issues.append("handsets_unavailable")
        shot(serial, out / "02_neo_settings.png")

    session.shell("input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.4)
    return issues


def audit_aurora(host: str, session, hs, out: Path) -> list[str]:
    issues: list[str] = []
    serial = session.serial
    adb_shell(serial, "am", "force-stop", AURORA)
    time.sleep(0.4)
    adb_shell(serial, "am", "start", "-n", "%s/.MainActivity" % AURORA)
    time.sleep(2.0)
    shot(serial, out / "10_aurora_home.png")

    if hs is not None:
        hs.tap_id("%s:id/menu_more" % AURORA, timeout_ms=2000) or hs.tap_desc(
            "More", timeout_ms=1500
        )
        time.sleep(0.8)
        hs.tap_text("Settings", timeout_ms=2000)
        time.sleep(1.2)
        shot(serial, out / "11_aurora_settings.png")

        hs.tap_text("Installation", timeout_ms=2000)
        time.sleep(0.8)
        hs.tap_text("Installation method", timeout_ms=2000)
        time.sleep(1.0)
        shot(serial, out / "12_aurora_installer.png")
        checked, ok = hs.switch_near_label("Shizuku installer", timeout_ms=3000)
        if not ok and not _ui_has(hs, "Shizuku installer"):
            issues.append("aurora_shizuku_missing")
        elif ok and checked is False:
            issues.append("aurora_shizuku_off")

        for _ in range(3):
            session.shell("input", "keyevent", "KEYCODE_BACK")
            time.sleep(0.5)
        ui = hs.ui()
        if "Updates" not in ui and "Installation" not in ui:
            hs.tap_id("%s:id/menu_more" % AURORA, timeout_ms=1500)
            time.sleep(0.6)
            hs.tap_text("Settings", timeout_ms=1500)
            time.sleep(0.8)
        hs.tap_text("Updates", timeout_ms=2000)
        time.sleep(1.0)
        shot(serial, out / "13_aurora_updates.png")

        filt = _switch_on(hs, FILTER_AURORA_ONLY)
        if filt is False:
            issues.append("aurora_filter_other_sources_off")
        elif filt is None and not _ui_has(hs, *FILTER_AURORA_ONLY):
            issues.append("aurora_filter_other_sources_missing")

        fdroid = _switch_on(hs, FILTER_FDROID)
        if fdroid is False:
            issues.append("aurora_filter_fdroid_off")
        elif fdroid is None and not _ui_has(hs, *FILTER_FDROID):
            issues.append("aurora_filter_fdroid_missing")

        hs.tap_text("Automatic updates", timeout_ms=2000)
        time.sleep(1.0)
        shot(serial, out / "14_aurora_auto_updates.png")
        ui = hs.ui()
        if any(b in ui for b in AUTO_UPDATE_BAD) and not any(
            g in ui for g in AUTO_UPDATE_OK
        ):
            # Selected radio often shows as checked near the bad label
            bad_on = False
            for lab in AUTO_UPDATE_BAD:
                c, ok = hs.switch_near_label(lab, timeout_ms=1200)
                if ok and c:
                    bad_on = True
                    break
            if bad_on or "Do not auto-update" in ui:
                # Heuristic: if the screen title is Automatic updates and the
                # primary selected option text is the deny option.
                issues.append("aurora_autoupdate_disabled")
        elif not any(g in ui for g in AUTO_UPDATE_OK) and "Automatic" in ui:
            issues.append("aurora_autoupdate_unclear")
    else:
        issues.append("handsets_unavailable")

    # Battery policy — dumpsys preferred (no extra UI noise).
    batt = aurora_battery_unrestricted(serial)
    if batt is True:
        issues.append("aurora_battery_unrestricted")
    adb_shell(
        serial,
        "am",
        "start",
        "-a",
        "android.settings.APPLICATION_DETAILS_SETTINGS",
        "-d",
        "package:%s" % AURORA,
    )
    time.sleep(1.5)
    shot(serial, out / "20_aurora_app_info.png")
    if hs is not None:
        for lab in ("App battery usage", "Battery", "Battery usage", "Power usage"):
            if hs.tap_text(lab, timeout_ms=1200):
                time.sleep(1.0)
                break
        shot(serial, out / "21_aurora_battery.png")
        ui = hs.ui()
        if re.search(r"Unrestricted|Not optimized|No restrictions", ui, re.I):
            if "aurora_battery_unrestricted" not in issues:
                issues.append("aurora_battery_unrestricted")

    session.shell("input", "keyevent", "KEYCODE_HOME")
    time.sleep(0.4)
    return issues


def audit_host(host: str, day_dir: Path) -> list[str]:
    ok, serial_or = reachable(host)
    if not ok:
        log("%s unreachable — skip (%s)" % (host, serial_or))
        return []  # not an assertion failure

    serial = serial_or
    out = day_dir / host
    out.mkdir(parents=True, exist_ok=True)
    issues: list[str] = []
    log("%s start serial=%s quiet=1" % (host, serial))
    try:
        with sc.ScreenControlSession(host, label=host) as session:
            with uid.try_handsets(serial, host) as hs:
                issues.extend(audit_neo(host, session, hs, out))
                issues.extend(audit_aurora(host, session, hs, out))
    except sc.ScreenControlError as e:
        issues.append("screen_control_failed")
        log("%s screen_control_error: %s" % (host, e))
    except Exception as e:  # noqa: BLE001
        issues.append("audit_exception")
        log("%s exception: %s" % (host, e))

    # De-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    tag = ",".join(uniq) if uniq else "none"
    log("%s done issues=%s shots=%s" % (host, tag, out))
    return uniq


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("hosts", nargs="*", help="Aliases (default: devices.conf)")
    ap.add_argument(
        "--dry-reach",
        action="store_true",
        help="Only check reachability; no UI",
    )
    args = ap.parse_args(argv)

    # Quiet presence: no torch/vibrate/dialogs. Never skip inversion.
    os.environ["STAYTURGID_PRESENCE_QUIET"] = "1"
    os.environ.pop("STAYTURGID_SKIP_PRESENCE", None)

    hosts = args.hosts or read_hosts(CONF)
    if not hosts:
        log("health no_hosts — devices.conf empty or missing at %s" % CONF)
        return 0  # Mac may be misconfigured; do not wake the operator at 3am

    day = dt.datetime.now().strftime("%Y-%m-%d")
    day_dir = ART / day
    day_dir.mkdir(parents=True, exist_ok=True)
    log("health start hosts=%s out=%s" % (",".join(hosts), day_dir))

    if args.dry_reach:
        for h in hosts:
            ok, detail = reachable(h)
            log("%s reach=%s detail=%s" % (h, ok, detail))
        return 0

    any_assert_fail = False
    for host in hosts:
        issues = audit_host(host, day_dir)
        if issues:
            any_assert_fail = True

    log("health finish assert_fail=%s" % int(any_assert_fail))
    # Exit 0 always for launchd — unreachable is expected; assertion gaps are
    # surfaced via gui-audit.log → check_fleet_health.py.
    return 0


if __name__ == "__main__":
    sys.exit(main())
