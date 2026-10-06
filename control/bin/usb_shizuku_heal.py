#!/usr/bin/env python3
# @heals: PORT5555-OPEN SHIZUKU-HEADLESS
"""Heal a fleet phone over USB adb when its TCP adb or Shizuku is down.

The on-phone repair (stayturgid_repair.py) cannot reopen port 5555 once
wireless debugging is off and no privileged shell is left: it logs
"CLOSED_NO_SHELL" and waits. A USB cable to this Mac is a privileged shell,
so when a phone shows up here as an authorised USB device and either its
adbd is not listening on 5555 or ShizukuTendCF's HEADLESS_STATUS is not
RUNNING, this does what the operator did by hand on 2026-10-06 (s24, 3 h
down):

  1. ``adb -s <serial> tcpip 5555`` (only when 5555 is not listening), then
     wait for the USB transport to come back after adbd restarts;
  2. ``am broadcast ... HEADLESS_START`` (only when not RUNNING);
  3. ``adb connect <tailscale-ip>:5555``;
  4. verify: 5555 listening and HEADLESS_STATUS says RUNNING.

Safety rules (operator, 2026-10-06):
  * acts only on a serial that ``adb devices`` lists as ``device``; an
    ``unauthorized``/``offline`` serial is never touched;
  * never taps, accepts or dismisses a dialog, never writes adb_keys;
  * never touches hd8 (the operator's own deploys) or any Fire OS row;
  * at most one heal attempt per phone per 10 min, every attempt logged to
    ~/.config/stayturgid/logs/usb-shizuku-heal.log;
  * one Hermes notice per successful heal, one per run of failures.

Serial -> phone comes from devices.conf (column 2, generated from the site
inventory). Called by adb_reconnect.py on every pass for its alias (launchd,
every 5 min); ``STAYTURGID_SKIP_USB_HEAL=1`` disables it there.

CLI: ``usb_shizuku_heal.py [--dry-run] [alias ...]`` (default: every alias).
"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable

_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
import hermes_notify
import stayturgid_device as dev
from site_logging import NOTICE, WARNING, log

PKG = "moe.shizuku.privileged.api"
STATUS_ACTION = PKG + ".HEADLESS_STATUS"
START_ACTION = PKG + ".HEADLESS_START"
PORT = 5555
COOLDOWN_SEC = 10 * 60
# A failure notice repeats at most this often while failures continue.
FAIL_RENOTIFY_SEC = 6 * 60 * 60
# hd8 deploys are the operator's own (2026-10-06): never act on it.
EXCLUDED_ALIASES = frozenset({"hd8", "fireos-device"})
EXCLUDED_LABEL_WORDS = ("fire", "kindle")
ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
STATE_DIR = os.path.join(ROOT, "state", "usb-shizuku-heal")
LOG_NAME = "usb-shizuku-heal.log"
SKIP_ENV = "STAYTURGID_SKIP_USB_HEAL"

# run(args_after_adb, timeout) -> (returncode, stdout+stderr); rc 124 on timeout.
Runner = Callable[[list[str], int], tuple[int, str]]

_DATA_RE = re.compile(r'data="([^"]*)"')
_PORT_HEX = ":%04X" % PORT


def real_runner(args: list[str], timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run([dev.adb_bin(), *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as e:
        return 127, str(e)


# --------------------------------------------------------------------------
# Pure parsing / decision logic (unit-tested)
# --------------------------------------------------------------------------
def parse_adb_devices(text: str) -> dict[str, str]:
    """`adb devices` -> {serial: state}."""
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and not line.startswith("List of devices") and not line.startswith("*"):
            out[parts[0]] = parts[1]
    return out


def parse_status(rc: int, text: str) -> str | None:
    """HEADLESS_STATUS broadcast -> its data string; "" = no answer; None = probe failed."""
    if rc != 0 or "Broadcast completed" not in (text or ""):
        return None
    m = _DATA_RE.search(text)
    return m.group(1) if m else ""


def status_running(status: str | None) -> bool:
    return status is not None and status.startswith("RUNNING")


def parse_listening(rc: int, text: str) -> bool | None:
    """/proc/net/tcp{,6} dump -> is something listening (state 0A) on PORT? None = probe failed."""
    if rc != 0 or "sl" not in (text or ""):
        return None
    for line in text.splitlines():
        f = line.split()
        if len(f) > 3 and f[1].upper().endswith(_PORT_HEX) and f[3] == "0A":
            return True
    return False


def excluded(alias: str, label: str) -> bool:
    low = (label or "").lower()
    return alias in EXCLUDED_ALIASES or any(w in low for w in EXCLUDED_LABEL_WORDS)


@dataclass
class Decision:
    action: str  # "none" | "skip" | "heal"
    reason: str
    tcpip: bool = False
    start: bool = False


def decide(
    alias: str,
    label: str,
    usb_state: str | None,
    listening: bool | None,
    status: str | None,
    cooldown_ok: bool,
) -> Decision:
    if excluded(alias, label):
        return Decision("skip", "excluded (operator-managed device)")
    if usb_state is None:
        return Decision("none", "not on USB")
    if usb_state != "device":
        return Decision("skip", "USB state %r is not authorised; not touching it" % usb_state)
    if listening is None or status is None:
        return Decision("skip", "probe failed (listening=%s status=%r)" % (listening, status))
    running = status_running(status)
    if listening and running:
        return Decision("none", "healthy (5555 listening, %s)" % status)
    if not cooldown_ok:
        return Decision("skip", "cooldown (one attempt per %d min)" % (COOLDOWN_SEC // 60))
    why = []
    if not listening:
        why.append("5555 not listening")
    if not running:
        why.append("Shizuku %r" % (status or "no answer"))
    return Decision("heal", ", ".join(why), tcpip=not listening, start=not running)


# --------------------------------------------------------------------------
# Probing and healing (runner injected for tests)
# --------------------------------------------------------------------------
def probe_listening(run: Runner, serial: str) -> bool | None:
    rc, out = run(["-s", serial, "shell", "cat /proc/net/tcp /proc/net/tcp6"], 15)
    return parse_listening(rc, out)


def probe_status(run: Runner, serial: str) -> str | None:
    rc, out = run(["-s", serial, "shell", "am broadcast -a %s -p %s" % (STATUS_ACTION, PKG)], 20)
    return parse_status(rc, out)


def usb_state(run: Runner, serial: str) -> str | None:
    rc, out = run(["devices"], 15)
    if rc != 0:
        return None
    return parse_adb_devices(out).get(serial)


def heal(
    run: Runner,
    serial: str,
    ts_ip: str,
    decision: Decision,
    *,
    sleep: Callable[[float], None] = time.sleep,
    usb_wait_sec: int = 60,
    verify_sec: int = 60,
) -> tuple[bool, str]:
    """Run the heal steps; returns (ok, one-line detail). Never taps any UI."""
    steps: list[str] = []
    if decision.tcpip:
        rc, out = run(["-s", serial, "tcpip", str(PORT)], 30)
        steps.append("tcpip rc=%s" % rc)
        if rc != 0:
            return False, "; ".join(steps) + " (%s)" % out.strip()[:120]
        # adbd restarts: the USB transport drops, then returns.
        back = False
        waited = 0
        while waited < usb_wait_sec:
            sleep(3)
            waited += 3
            if usb_state(run, serial) == "device" and probe_listening(run, serial):
                back = True
                break
        steps.append("usb back after %ds" % waited if back else "usb not back after %ds" % waited)
        if not back:
            return False, "; ".join(steps)
    status = probe_status(run, serial)
    if not status_running(status):
        rc, out = run(["-s", serial, "shell", "am broadcast -a %s -p %s" % (START_ACTION, PKG)], 30)
        steps.append("HEADLESS_START rc=%s" % rc)
    if ts_ip and ts_ip != "-":
        rc, out = run(["connect", "%s:%d" % (ts_ip, PORT)], 15)
        steps.append("connect: %s" % (out.strip().splitlines() or ["?"])[-1][:80])
    waited = 0
    listening = status = None
    while True:
        listening = probe_listening(run, serial)
        status = probe_status(run, serial)
        if listening and status_running(status):
            steps.append("verified: %s" % status)
            return True, "; ".join(steps)
        if waited >= verify_sec:
            break
        sleep(5)
        waited += 5
    steps.append("not healed after %ds: listening=%s status=%r" % (waited, listening, status))
    return False, "; ".join(steps)


# --------------------------------------------------------------------------
# State: rate limit, per-alias lock, failure-notice dedup
# --------------------------------------------------------------------------
def _path(alias: str, suffix: str = "") -> str:
    return os.path.join(STATE_DIR, alias + suffix)


def cooldown_ok(alias: str, now: float | None = None) -> bool:
    try:
        return (now or time.time()) - os.path.getmtime(_path(alias)) >= COOLDOWN_SEC
    except OSError:
        return True


def _write(path: str, text: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
    except OSError:
        pass


def _read(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def should_notify(alias: str, ok: bool, now: float | None = None) -> bool:
    """Every success notifies; a failure notifies once per run of failures (re-sent after 6 h)."""
    if ok:
        return True
    last = _path(alias, ".last")
    if _read(last) != "fail":
        return True
    try:
        return (now or time.time()) - os.path.getmtime(last) >= FAIL_RENOTIFY_SEC
    except OSError:
        return True


def _log(level: int, msg: str) -> None:
    log(LOG_NAME, level, msg, also_print=False)


def heal_alias(
    alias: str,
    *,
    dry_run: bool = False,
    run: Runner = real_runner,
    conf: str | None = None,
    notify: Callable[[str, str], None] = hermes_notify.notify,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """One pass for one alias. Returns a one-line summary (printed by the CLI)."""
    row = None
    for name, usb, ts_ip, _lan, label in dev.iter_devices_conf(conf):
        if name == alias:
            row = (usb, ts_ip, label)
            break
    if row is None:
        return "%s: not in devices.conf" % alias
    serial, ts_ip, label = row
    if excluded(alias, label):
        return "%s: skip: excluded (operator-managed device)" % alias
    if serial in ("", "-"):
        return "%s: none: no USB serial in devices.conf" % alias

    state = usb_state(run, serial)
    listening = status = None
    if state == "device":
        listening = probe_listening(run, serial)
        status = probe_status(run, serial)
    d = decide(alias, label, state, listening, status, cooldown_ok(alias))
    summary = "%s (%s): %s: %s" % (alias, serial, d.action, d.reason)
    if d.action == "none":
        if state == "device" and not dry_run:
            # Healthy on USB: a later failure is a new incident and notifies again.
            try:
                os.unlink(_path(alias, ".last"))
            except OSError:
                pass
        return summary
    if d.action == "skip":
        if not dry_run and state is not None and "cooldown" not in d.reason:
            _log(WARNING, summary)
        return summary
    plan = "%s%sconnect" % ("tcpip 5555, " if d.tcpip else "", "HEADLESS_START, " if d.start else "")
    if dry_run:
        return summary + " -> would run: " + plan

    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_path(alias, ".lock"), "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return summary + " -> skip: another heal holds the lock"
        if not cooldown_ok(alias):
            return summary + " -> skip: cooldown"
        # Stamped before acting: a heal that hangs or crashes is still rate-limited.
        _write(_path(alias), str(int(time.time())))
        _log(NOTICE, "%s heal start: %s; plan: %s" % (alias, d.reason, plan))
        try:
            ok, detail = heal(run, serial, ts_ip, d, sleep=sleep)
        except Exception as e:  # never let a heal break the caller
            ok, detail = False, "error: %s" % e
        _log(NOTICE if ok else WARNING, "%s heal %s: %s" % (alias, "OK" if ok else "FAILED", detail))
        if should_notify(alias, ok):
            notify(
                "stayturgid",
                "%s USB heal %s (%s): %s"
                % (alias, "restored TCP adb/Shizuku" if ok else "FAILED", d.reason, detail[:200]),
            )
        _write(_path(alias, ".last"), "ok" if ok else "fail")
    return summary + " -> " + ("OK: " if ok else "FAILED: ") + detail


def run_alias(alias: str) -> None:
    """Entry point for adb_reconnect.py: never raises, honours STAYTURGID_SKIP_USB_HEAL."""
    if os.environ.get(SKIP_ENV) == "1":
        return
    try:
        heal_alias(alias)
    except Exception as e:
        _log(WARNING, "%s heal pass error: %s" % (alias, e))


def mac_reaches(ts_ip: str, timeout: float = 3.0) -> bool:
    try:
        socket.create_connection((ts_ip, PORT), timeout=timeout).close()
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--dry-run", action="store_true", help="decide and print, change nothing")
    p.add_argument("aliases", nargs="*", help="devices.conf aliases (default: all)")
    args = p.parse_args(argv)
    aliases = args.aliases or [row[0] for row in dev.iter_devices_conf()]
    for alias in aliases:
        line = heal_alias(alias, dry_run=args.dry_run)
        if args.dry_run:
            row = dev.device_row(alias)
            if row and row[1] not in ("", "-") and "excluded" not in line:
                line += " [Mac->%s:%d %s]" % (row[1], PORT, "open" if mac_reaches(row[1]) else "closed")
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
