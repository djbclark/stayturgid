#!/usr/bin/env python3
"""Quiet GUI audit: Neo Store + Aurora settings screenshots + assertions.

PARKED (2026-07-09): not scheduled by fleet launchd and not triaged by
check_fleet_health.py. Scripts remain for manual use if app stores are
re-enabled (see docs/modules/fdroid.md, docs/modules/play.md).

Intended for launchd at 03:14 local time when enabled. Tolerates offline Mac wake misses
and unreachable devices (per-host skip, exit 0 unless a reachable host fails
assertions).

  STAYTURGID_PRESENCE_QUIET=1  — no torch / vibrate / dialogs / presence sounds
  No macOS notification sounds.

Logs:  ~/.config/stayturgid/logs/gui-audit.log
Shots: ~/.config/stayturgid/artifacts/gui-audit/<YYYY-MM-DD>/<host>/
Overrides: ~/.config/stayturgid/gui-audit-overrides.conf (host issue per line)

Usage:
  python3 control/bin/gui_audit.py              # all devices.conf hosts
  python3 control/bin/gui_audit.py s24 p7a
  python3 control/bin/gui_audit.py --dry-reach  # reachability only
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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import screen_control as sc  # noqa: E402
import stayturgid_device as dev  # noqa: E402
import ui_driver as uid  # noqa: E402
import vlm_helpers as vh  # noqa: E402

ROOT = Path(os.path.expanduser("~")) / ".config" / "stayturgid"
LOG = ROOT / "logs" / "gui-audit.log"
ART = ROOT / "artifacts" / "gui-audit"
OVERRIDES = ROOT / "gui-audit-overrides.conf"
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
    "Do not auto-update apps",
    "Do not auto-update",
    "Don't auto-update",
    "Never",
)
AUTO_UPDATE_BAD = (
    "Check & install available updates automatically",
    "Check and install available updates automatically",
)


def vlm_aurora_autoupdate_issues(shot: Path) -> list[str]:
    """Optional UI-TARS gate on Aurora auto-update screenshot (STAYTURGID_VLM=1)."""
    return vh.issue_tags_from_verify(shot, "aurora_autoupdate_dont", "aurora_autoupdate_on_vlm")


def vlm_neo_shizuku_issues(shot: Path) -> list[str]:
    return vh.issue_tags_from_verify(shot, "neo_shizuku_installer", "neo_shizuku_off_vlm")


def vlm_aurora_shizuku_issues(shot: Path) -> list[str]:
    return vh.issue_tags_from_verify(shot, "aurora_shizuku_installer", "aurora_shizuku_off_vlm")


def load_gui_audit_overrides(path: Path | None = None) -> dict[str, set[str]]:
    """host -> issue tags suppressed (operator-confirmed on device)."""
    p = path or OVERRIDES
    out: dict[str, set[str]] = {}
    if not p.is_file():
        return out
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            out.setdefault(parts[0], set()).add(parts[1])
    return out


def apply_gui_audit_overrides(
    host: str, issues: list[str], overrides: dict[str, set[str]] | None = None
) -> tuple[list[str], list[str]]:
    """Return (filtered issues, suppressed tags)."""
    skip = (overrides or load_gui_audit_overrides()).get(host, set())
    if not skip:
        return issues, []
    kept: list[str] = []
    suppressed: list[str] = []
    for i in issues:
        if i in skip:
            suppressed.append(i)
        else:
            kept.append(i)
    return kept, suppressed


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
        [dev.adb_bin(), "connect", serial],
        capture_output=True,
        text=True,
        timeout=20,
    )
    out = ((r.stdout or "") + (r.stderr or "")).lower()
    if "connected" in out or "already connected" in out:
        return True
    # Some adb builds print nothing useful; probe shell.
    probe = subprocess.run(
        [dev.adb_bin(), "-s", serial, "shell", "echo", "ok"],
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
        [dev.adb_bin(), "-s", serial, "exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=45,
    )
    path.write_bytes(r.stdout or b"")


def adb_shell(serial: str, *args: str, timeout: int = 30) -> str:
    r = subprocess.run(
        [dev.adb_bin(), "-s", serial, "shell", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (r.stdout or "").replace("\r", "")


def aurora_battery_unrestricted(serial: str) -> bool | None:
    """True if Aurora is currently Doze-whitelisted or background-unrestricted."""
    # Prefer appops — dumpsys deviceidle history lines look like whitelist hits.
    ops = adb_shell(serial, "appops", "get", AURORA, "RUN_ANY_IN_BACKGROUND")
    if "allow" in ops.lower():
        return True
    # Current user whitelist (not the add/remove history log).
    out = adb_shell(serial, "dumpsys", "deviceidle", "whitelist")
    if out.strip():
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("["):
                continue
            if line == AURORA or line.endswith("," + AURORA) or line.startswith(AURORA + ","):
                return True
            if re.search(r"\b%s\b" % re.escape(AURORA), line) and "remove" not in line.lower():
                # e.g. "com.aurora.store" alone in whitelist dump
                if AURORA in line.split():
                    return True
    if "ignore" in ops.lower() or "deny" in ops.lower():
        return False
    return None


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


def _open_aurora_settings(hs, session) -> bool:
    """Open Aurora Settings root (Installation / Updates categories), not Updates tab."""
    if hs is None:
        return False
    hs.tap_id("%s:id/menu_more" % AURORA, timeout_ms=2500) or hs.tap_desc("More", timeout_ms=1500) or hs.tap_desc(
        "Settings", timeout_ms=1500
    )
    time.sleep(0.8)
    if not hs.tap_text("Settings", timeout_ms=2500):
        # Gear on Updates tab / home — content-desc often "Settings"
        if not (
            hs.tap_desc("Settings", timeout_ms=1500) or hs.tap_id("%s:id/action_settings" % AURORA, timeout_ms=1500)
        ):
            return False
    time.sleep(1.2)
    ui = hs.ui()
    # Must see settings categories, not the Updates *tab* list.
    if "Installation" in ui or "Updates" in ui and "Update all" not in ui:
        return True
    # Wrong screen (Updates tab): back and try overflow again.
    if "Update all" in ui or "updates available" in ui.lower():
        session.shell("input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.6)
        hs.tap_id("%s:id/menu_more" % AURORA, timeout_ms=2000)
        time.sleep(0.6)
        hs.tap_text("Settings", timeout_ms=2000)
        time.sleep(1.0)
        ui = hs.ui()
        return "Installation" in ui or ("Updates" in ui and "Update all" not in ui)
    return "Installation" in ui


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
        # Neo: gear / overflow → Settings (avoid bottom-nav "Service" lookalikes).
        for lab in ("Settings", "Preferencias", "Einstellungen"):
            if hs.tap_desc(lab, timeout_ms=1200) or hs.tap_text(lab, timeout_ms=1200):
                opened = True
                break
        if not opened:
            for lab in ("More options", "More", "Overflow"):
                if hs.tap_desc(lab, timeout_ms=1000):
                    time.sleep(0.8)
                    if hs.tap_text("Settings", timeout_ms=1500):
                        opened = True
                        break
        time.sleep(1.0)
        shot(serial, out / "02_neo_settings.png")
        # Neo settings: phone uses bottom tabs; Fire tablet uses left sidebar.
        # Installer / Shizuku live under Service — not Other/Personalization.
        ui = hs.ui()
        if "Personalization" in ui or "Other" in ui or "Repositories" in ui:
            tapped = False
            for line in ui.splitlines():
                if '"Service"' in line and "TextView" in line:
                    m = re.search(r"(\d+)\s*,\s*(\d+)", line)
                    if m and int(m.group(1)) < 250:
                        session.shell("input", "tap", m.group(1), m.group(2))
                        tapped = True
                        break
            if not tapped:
                hs.tap_text("Service", timeout_ms=2500) or hs.tap_desc("Service", timeout_ms=1500)
            time.sleep(1.0)
            ui = hs.ui()
        for lab in ("Installer", "Installation", "Privileges", "Source"):
            if hs.tap_text(lab, timeout_ms=1800):
                time.sleep(1.0)
                break
        shot(serial, out / "03_neo_installer.png")
        ui = hs.ui()
        if "Shizuku" not in ui and "shizuku" not in ui.lower():
            for _ in range(5):
                session.shell("input", "swipe", "700", "1200", "700", "400")
                time.sleep(0.6)
                ui = hs.ui()
                if "Shizuku" in ui or "shizuku" in ui.lower():
                    break
                if hs.tap_text("Installer", timeout_ms=1200):
                    time.sleep(0.8)
                    ui = hs.ui()
                    if "Shizuku" in ui:
                        break
            else:
                issues.append("neo_shizuku_missing")
        shot(serial, out / "04_neo_scrolled.png")
        ui2 = hs.ui()
        if "Auto" in ui2 or "auto" in ui2.lower():
            if re.search(r"auto.?update.*\b(off|disabled|never)\b", ui2, re.I):
                issues.append("neo_autoupdate_off")
        if not opened:
            issues.append("neo_settings_nav_failed")
        neo_inst = out / "03_neo_installer.png"
        if neo_inst.is_file():
            for tag in vlm_neo_shizuku_issues(neo_inst):
                if tag not in issues:
                    issues.append(tag)
    else:
        issues.append("handsets_unavailable")
        shot(serial, out / "02_neo_settings.png")

    # Leave Neo; next step force-stops Aurora. Session exit restores prior screen.
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
        if not _open_aurora_settings(hs, session):
            issues.append("aurora_settings_nav_failed")
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

        aurora_inst = out / "12_aurora_installer.png"
        if aurora_inst.is_file():
            for tag in vlm_aurora_shizuku_issues(aurora_inst):
                if tag not in issues and "aurora_shizuku_off" not in issues:
                    issues.append(tag)

        # Back to Settings root (Installation / Updates categories).
        for _ in range(4):
            ui = hs.ui()
            if "Installation" in ui and "Updates" in ui and "Update all" not in ui:
                break
            session.shell("input", "keyevent", "KEYCODE_BACK")
            time.sleep(0.5)
        else:
            _open_aurora_settings(hs, session)

        hs.tap_text("Updates", timeout_ms=2000)
        time.sleep(1.0)
        shot(serial, out / "13_aurora_updates.png")
        # Guard: if we landed on Updates *tab*, reopen settings.
        if "Update all" in hs.ui():
            issues.append("aurora_updates_tab_not_settings")
            _open_aurora_settings(hs, session)
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
        # Desired: Do not auto-update (battery-optimized policy).
        off_ok = any(b in ui for b in AUTO_UPDATE_OK)
        on_bad = any(g in ui for g in AUTO_UPDATE_BAD)
        if on_bad and not off_ok:
            on_selected = False
            for lab in AUTO_UPDATE_BAD:
                c, ok = hs.switch_near_label(lab, timeout_ms=1200)
                if ok and c:
                    on_selected = True
                    break
            if on_selected or "Check & install" in ui:
                issues.append("aurora_autoupdate_on")
        elif not off_ok and "Automatic" in ui:
            issues.append("aurora_autoupdate_unclear")
        auto_shot = out / "14_aurora_auto_updates.png"
        if auto_shot.is_file():
            vlm_tags = vlm_aurora_autoupdate_issues(auto_shot)
            if "aurora_autoupdate_unclear" in issues and not vlm_tags:
                ok_vlm, detail = vh.verify_shot(auto_shot, "aurora_autoupdate_dont")
                if ok_vlm and not detail.get("skipped"):
                    issues.remove("aurora_autoupdate_unclear")
            for tag in vlm_tags:
                if tag not in issues:
                    issues.append(tag)
    else:
        issues.append("handsets_unavailable")

    # Battery policy — appops + whitelist (not UI text alone).
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
        # Only flag Unrestricted when that radio is clearly selected.
        if re.search(r"Unrestricted.*\b(selected|checked)\b", ui, re.I):
            if "aurora_battery_unrestricted" not in issues:
                issues.append("aurora_battery_unrestricted")
        elif re.search(r"\bUnrestricted\b", ui) and "Optimized" not in ui:
            if "aurora_battery_unrestricted" not in issues:
                issues.append("aurora_battery_unrestricted")

    # Prior screen restored by ScreenControlSession.__exit__.
    return issues


def audit_host(host: str, day_dir: Path) -> list[str]:
    ok, serial_or = reachable(host)
    if not ok:
        log("%s unreachable — skip (%s)" % (host, serial_or))
        return []  # not an assertion failure

    serial = serial_or
    out = day_dir / host
    out.mkdir(parents=True, exist_ok=True)

    import ui_guard

    ui_guard.check_ui_guard(
        host=host,
        action_type="GUI-AUDIT",
        message="Please manually perform the GUI audit on Neo Store and Aurora Store settings.",
    )

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
    uniq, suppressed = apply_gui_audit_overrides(host, uniq)
    if suppressed:
        log("%s override suppressed=%s (%s)" % (host, ",".join(suppressed), OVERRIDES))
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
    # Exit 0 always for launchd — unreachable is expected; assertion gaps go to
    # gui-audit.log (not merged into check_fleet_health.py while gui-audit parked).
    return 0


if __name__ == "__main__":
    sys.exit(main())
