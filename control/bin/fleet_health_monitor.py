#!/usr/bin/env python3
# @heals: A11Y-AUTOJS6 AGENT-FRESH REPAIRLOG-FRESH ET-CONFIG HD8-DOZE-WHITELIST HD8-GSF-PINNED HD8-GMS-PINNED
"""Dedicated Mac fleet soft-health monitor (launchd every 5 min).

Scrapes watchdog/repair/a11y/sshd/bootloop/shell5555 when a device is
reachable. Logs to ~/.config/stayturgid/logs/fleet-health.log and notifies
after CONSECUTIVE_LIMIT consecutive soft failures (~10 min).

When ``agent_stale`` persists (native agent, OPTIONS K1 — the current
mechanism post-cutover), restarts the Kotlin HostService via
``control/tools/native-agent/start_agent.py`` (rate-limited).

Legacy watchdog and AutoJs6 accessibility fields remain in telemetry while
fleet-state verification is incomplete, but they do not create health issues
or trigger repair.

Reachability-only outages stay in access_monitor.py (separate agent).
Disable with STAYTURGID_SKIP_HEALTH=1; skip restarts with
STAYTURGID_SKIP_WATCHDOG_HEAL=1 (also skips agent heal).
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LIB = os.path.join(_REPO, "control", "lib")
for _p in (_LIB, _REPO):
    if _p not in sys.path:
        sys.path.append(_p)
import fleet_health as fh
import hd8_google_stack as hgs
import stayturgid_device as dev
import vlm_helpers as vh

import control.lib.stats as stats
from control.lib.site_logging import (
    ERR,
    INFO,
    NOTICE,
    WARNING,
    log,
    scrape_errors,
    severity_label,
    trim_log,
)

ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
CONF = os.environ.get("STAYTURGID_DEVICES_CONF", os.path.join(ROOT, "devices.conf"))
STATE_DIR = os.path.join(ROOT, "state", "fleet-health")
AGENT_HEAL_STATE_DIR = os.path.join(ROOT, "state", "agent-heal")
GOOGLE_HEAL_STATE_DIR = os.path.join(ROOT, "state", "google-stack-heal")
GOOGLE_VERIFY_STATE_DIR = os.path.join(ROOT, "state", "google-stack-verify")
ERROR_LOG = os.path.join(ROOT, "logs", "errors.log")
LOG_NAME = "fleet-health.log"
CONSECUTIVE_LIMIT = 2
AGENT_HEAL_AFTER = 2
AGENT_HEAL_COOLDOWN_SEC = 30 * 60
GOOGLE_STACK_HEAL_COOLDOWN_SEC = 24 * 60 * 60
GOOGLE_VERIFY_COOLDOWN_SEC = 6 * 60 * 60
SKIP_HEALTH = os.environ.get("STAYTURGID_SKIP_HEALTH") == "1"
SKIP_WATCHDOG_HEAL = os.environ.get("STAYTURGID_SKIP_WATCHDOG_HEAL") == "1"
SKIP_GOOGLE_STACK_HEAL = os.environ.get("STAYTURGID_SKIP_GOOGLE_STACK_HEAL") == "1"
MAX_LOG_LINES = 2000
REPO = _REPO
REPAIR_HEAL_STATE_DIR = os.path.join(ROOT, "state", "repair-heal")
REPAIR_HEAL_COOLDOWN_SEC = 30 * 60
REPAIR_HEAL_AFTER = 2


def _stats_event(event_type: str, device: str, **details: str | int | float) -> None:
    try:
        stats.record_event(event_type, device, **details)
    except Exception:
        pass


def _fleet_log(level: int, msg: str) -> None:
    log(LOG_NAME, level, msg, also_print=False)


def _error_log(level: int, msg: str) -> None:
    log(ERROR_LOG, level, msg, also_print=False)


def notify(title: str, message: str, sound: str | None = None) -> None:
    # Escape quotes for AppleScript.
    message = message.replace("\\", "\\\\").replace('"', '\\"')
    title = title.replace("\\", "\\\\").replace('"', '\\"')
    script = 'display notification "%s" with title "%s"' % (message, title)
    if sound:
        script += ' sound name "%s"' % sound
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def read_devices(conf_path: str):
    try:
        from stayturgid_device import iter_monitor_hosts
    except Exception:
        iter_monitor_hosts = None
    if iter_monitor_hosts is not None:
        yield from iter_monitor_hosts(conf_path)
        return
    try:
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    name, _usb, ts_ip = parts[0], parts[1], parts[2]
                    lan = parts[3] if len(parts) > 3 else "-"
                    yield name, ts_ip, lan
    except OSError:
        return


def read_state(state_file: str) -> int:
    try:
        with open(state_file) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def write_state(state_file: str, n: int) -> None:
    try:
        with open(state_file, "w") as f:
            f.write(str(n))
    except OSError:
        pass


def _heal_cooldown_ok_dir(name: str, state_dir: str, cooldown_sec: int) -> bool:
    path = os.path.join(state_dir, name)
    try:
        age = datetime.datetime.now().timestamp() - os.path.getmtime(path)
        return age >= cooldown_sec
    except OSError:
        return True


def _touch_heal_dir(name: str, state_dir: str) -> None:
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, name), "w") as f:
            f.write(str(int(datetime.datetime.now().timestamp())))
    except OSError:
        pass


def maybe_heal_agent(name: str, issues: list[str], fails: int, adb_serial: str | None = None) -> None:
    """Restart native-agent HostService when agent_stale (OPTIONS K1, post-cutover)."""
    if SKIP_WATCHDOG_HEAL or SKIP_HEALTH:
        return
    if fails < AGENT_HEAL_AFTER:
        return
    if "agent_stale" not in issues:
        return
    if not _heal_cooldown_ok_dir(name, AGENT_HEAL_STATE_DIR, AGENT_HEAL_COOLDOWN_SEC):
        _fleet_log(WARNING, "%s agent heal skipped (cooldown)" % name)
        return
    script = os.path.join(REPO, "control", "tools", "native-agent", "start_agent.py")
    if not os.path.isfile(script):
        _fleet_log(WARNING, "%s agent heal skipped (missing %s)" % (name, script))
        return
    _fleet_log(INFO, "%s agent heal: starting HostService via start_agent.py" % name)
    cmd = [sys.executable, script, name]
    if adb_serial:
        cmd.append(adb_serial)
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        detail = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " | ")
        _fleet_log(INFO, "%s agent heal rc=%s %s" % (name, r.returncode, detail[:300]))
        if r.returncode == 0:
            _touch_heal_dir(name, AGENT_HEAL_STATE_DIR)
            notify(
                "stayturgid heal",
                "%s native-agent restarted" % name,
            )
            _stats_event("heal_triggered", name, heal="agent")
    except (OSError, subprocess.TimeoutExpired) as e:
        _fleet_log(INFO, "%s agent heal error: %s" % (name, e))


def _heal_repair_cooldown_ok(name: str) -> bool:
    return _heal_cooldown_ok_dir(name, REPAIR_HEAL_STATE_DIR, REPAIR_HEAL_COOLDOWN_SEC)


def _touch_heal_repair(name: str) -> None:
    _touch_heal_dir(name, REPAIR_HEAL_STATE_DIR)


def maybe_heal_repair_stale(name: str, issues: list[str], fails: int) -> None:
    if SKIP_WATCHDOG_HEAL or SKIP_HEALTH:
        return
    if fails < REPAIR_HEAL_AFTER:
        return
    if "repair_stale" not in issues and "repair_missing" not in issues:
        return
    if not _heal_repair_cooldown_ok(name):
        _fleet_log(INFO, "%s repair heal skipped (cooldown)" % name)
        return

    _fleet_log(INFO, "%s repair heal: restarting boot loop via SSH" % name)
    try:
        r = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "LogLevel=ERROR",
                name,
                "pkill -f stayturgid_repair 2>/dev/null; "
                "nohup python3 ~/.stayturgid/bin/start_adb.py >/dev/null 2>&1 &",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0 or r.returncode == 255:
            _touch_heal_repair(name)
            _fleet_log(INFO, "%s repair heal: boot loop restarted (rc=%s)" % (name, r.returncode))
            notify("stayturgid heal", "%s repair loop restarted" % name)
            _stats_event("heal_triggered", name, heal="repair")
        else:
            _fleet_log(
                INFO,
                "%s repair heal: unexpected rc=%s stderr=%s" % (name, r.returncode, (r.stderr or "").strip()[:200]),
            )
    except (OSError, subprocess.TimeoutExpired) as e:
        _fleet_log(INFO, "%s repair heal error: %s" % (name, e))


def maybe_heal_hd8_google_stack(name: str) -> None:
    """Keep Doze whitelist + GSF 10; optionally pin GMS if STAYTURGID_HD8_PIN_GMS=1."""
    if SKIP_HEALTH or SKIP_GOOGLE_STACK_HEAL or name != "fireos-device":
        return
    if not _heal_cooldown_ok_dir(name, GOOGLE_HEAL_STATE_DIR, GOOGLE_STACK_HEAL_COOLDOWN_SEC):
        return

    def _run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode, r.stdout or "", r.stderr or ""

    # Entire heal path must never abort soft-health scrape (adb/PATH issues).
    try:
        serial = dev.resolve_adb(name)
        gms_ver = hgs.package_version_code(_run, serial, hgs.GMS_PKG)
        gsf_ver = hgs.package_version_name(_run, serial, hgs.GSF_PKG)
        # Default: whitelist only (no GMS/Play force-downgrade).
        if not hgs.pin_gms_enabled():
            hgs.ensure_doze_whitelist(_run, serial)
            if hgs.needs_gsf_reinstall(gsf_ver):
                _fleet_log(NOTICE, "%s google-stack heal: GSF %s — reinstalling 10-6494331" % (name, gsf_ver))
                hgs.repair_if_needed(_run, serial)
                _touch_heal_dir(name, GOOGLE_HEAL_STATE_DIR)
            return
        if not hgs.needs_gms_downgrade(gms_ver) and not hgs.needs_gsf_reinstall(gsf_ver):
            hgs.ensure_doze_whitelist(_run, serial)
            return
        if hgs.needs_gsf_reinstall(gsf_ver) and not hgs.needs_gms_downgrade(gms_ver):
            _fleet_log(NOTICE, "%s google-stack heal: GSF %s — reinstalling pinned 10-6494331" % (name, gsf_ver))
        else:
            _fleet_log(
                NOTICE,
                "%s google-stack heal: GMS versionCode=%s > %s — pinning Fire-Tools stack"
                % (name, gms_ver, hgs.MAX_GMS_VERSION_CODE),
            )
        result = hgs.repair_if_needed(_run, serial)
        _touch_heal_dir(name, GOOGLE_HEAL_STATE_DIR)
        new_ver = result.get("gms_version")
        _fleet_log(INFO, "%s google-stack heal done gms versionCode=%s" % (name, new_ver))
        _stats_event("heal_triggered", name, heal="google_stack")
        if hgs.needs_gms_downgrade(new_ver):
            notify(
                "stayturgid heal",
                "%s GMS still too new (%s) — run just fix-fireos-device-google" % (name, new_ver),
                sound="Basso",
            )
        else:
            notify(
                "stayturgid heal",
                "%s Google Play Services pinned (%s)" % (name, new_ver),
            )
            maybe_verify_hd8_google_closeout(name)
    except Exception as e:
        _fleet_log(INFO, "%s google-stack heal skipped: %s" % (name, e))


def maybe_verify_hd8_google_closeout(name: str) -> None:
    """Rate-limited VLM verify after stack heal (auto-update + crash dialog)."""
    if SKIP_HEALTH or name != "fireos-device" or not vh.auto_verify_enabled():
        return
    if not _heal_cooldown_ok_dir(name, GOOGLE_VERIFY_STATE_DIR, GOOGLE_VERIFY_COOLDOWN_SEC):
        return
    script = os.path.join(REPO, "control", "bin", "verify_hd8_google.py")
    if not os.path.isfile(script):
        return
    _fleet_log(INFO, "%s google-stack VLM close-out (verify_hd8_google)" % name)
    env = os.environ.copy()
    env.setdefault("STAYTURGID_VLM", "1")
    try:
        r = subprocess.run(
            [sys.executable, script, name],
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        detail = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " | ")
        _fleet_log(INFO, "%s google-stack VLM verify rc=%s %s" % (name, r.returncode, detail[:400]))
        _touch_heal_dir(name, GOOGLE_VERIFY_STATE_DIR)
        if r.returncode != 0:
            notify(
                "stayturgid heal",
                "%s Google stack VLM check failed — see fleet-health.log" % name,
                sound="Basso",
            )
    except (OSError, subprocess.TimeoutExpired) as e:
        _fleet_log(INFO, "%s google-stack VLM verify error: %s" % (name, e))


# Only count catastrophic/headless failures inside this window. Counting the
# entire log (or last-50 grep with no time filter) re-fired Mac notifications
# forever after a resolved CLOSED_NO_SHELL incident (2026-07-19: one fleet phone
# had 55 historical lines → alert every 5 min while fleet was healthy).
CATASTROPHIC_ALERT_WINDOW_SEC = 2 * 60 * 60
CATASTROPHIC_ALERT_MIN = 3
CATASTROPHIC_NOTIFY_COOLDOWN_SEC = 6 * 60 * 60


def _audit_scraped_errors(name: str, text: str) -> None:
    """Scan scraped errors for *recent* excessive catastrophic repairs / loops."""
    now = time.time()
    recent: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if "catastrophic" not in low and "headless start failed" not in low:
            continue
        epoch = _device_log_epoch(line)
        if epoch is None:
            # Cannot age the line — do not inflate the alert with undated history.
            continue
        if now - epoch <= CATASTROPHIC_ALERT_WINDOW_SEC:
            recent.append(line)
    if len(recent) < CATASTROPHIC_ALERT_MIN:
        return
    _fleet_log(
        WARNING,
        "%s: ALERT - excessive catastrophic repairs detected (%d in last %dh)"
        % (name, len(recent), CATASTROPHIC_ALERT_WINDOW_SEC // 3600),
    )
    # Rate-limit operator notifications (log every scrape; ping Mac at most 6h).
    cooldown_path = os.path.join(ROOT, "state", "catastrophic-alert", name)
    try:
        os.makedirs(os.path.dirname(cooldown_path), exist_ok=True)
        last = 0.0
        try:
            with open(cooldown_path) as f:
                last = float(f.read().strip() or 0)
        except (OSError, ValueError):
            pass
        if now - last < CATASTROPHIC_NOTIFY_COOLDOWN_SEC:
            return
        with open(cooldown_path, "w") as f:
            f.write(str(int(now)))
    except OSError:
        pass
    notify(
        "stayturgid alert",
        "%s: Excessive catastrophic repairs (%d in 2h)! Loop bug?" % (name, len(recent)),
        sound="Basso",
    )


def _scrape_device_errors(name: str, ts_ip: str) -> None:
    """SSH into device, grep repair/watchdog logs for errors, log locally."""
    import time as _time

    state_file = os.path.join(ROOT, "state", "error-scrape", name)
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        last = 0.0
        try:
            with open(state_file) as f:
                last = float(f.read().strip() or 0)
        except (OSError, ValueError):
            pass
        now = _time.time()
        if now - last < 120:
            return
        with open(state_file, "w") as f:
            f.write(str(int(now)))
    except OSError:
        return

    grep_cmd = (
        "grep -h -i -E 'FAILED|CLOSED_NO_SHELL|Error|Exception|Traceback|"
        "cannot find|crash|permission|catastrophic|headless' "
        "~/.stayturgid/logs/repair.log "
        "/sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -50"
    )
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR", name, grep_cmd],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError):
        return

    text = (r.stdout or "").strip()
    if not text:
        return

    _audit_scraped_errors(name, text)

    errors = scrape_errors(text)
    for level, line in errors:
        event_time = _device_log_epoch(line)
        if event_time is not None and event_time <= last:
            continue
        _error_log(level, "%s: %s" % (name, line))
        if level <= WARNING:
            _fleet_log(level, "%s device error [%s]: %s" % (name, severity_label(level), line[:200]))


def _device_log_epoch(line: str) -> float | None:
    """Return the timestamp embedded in a device log line, when present.

    Supports Termux-style ``YYYY-MM-DD HH:MM:SS`` and AutoJs6 syslog-style
    ``Mon DD HH:MM:SS`` (year assumed current; roll back one year if future).
    """
    try:
        stamp = line[:19]
        return datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp()
    except (ValueError, OverflowError):
        pass
    try:
        # "Jul 19 20:19:46 ..." — AutoJs6 log.append prefix (year not in line).
        # Bind year explicitly to avoid Python 3.15 ambiguous-day-without-year.
        now = datetime.datetime.now()
        partial = line[:15].strip()
        dt = datetime.datetime.strptime("%d %s" % (now.year, partial), "%Y %b %d %H:%M:%S")
        ts = dt.timestamp()
        if ts > time.time() + 86400:
            dt = datetime.datetime.strptime("%d %s" % (now.year - 1, partial), "%Y %b %d %H:%M:%S")
            ts = dt.timestamp()
        return ts
    except (ValueError, OverflowError):
        return None


def _age_field(raw: str | None) -> int | str:
    """Numeric age for stats, or sentinel strings missing/unknown."""
    if raw is None or raw == "":
        return "unknown"
    if raw in ("missing", "unknown"):
        return raw
    try:
        return int(raw)
    except ValueError:
        return "unknown"


def _record_soft_health_snapshot(
    name: str,
    path: str,
    report: dict[str, str],
    issues: list[str],
) -> None:
    """Persist one soft-health row per probe for dual-run debugging (K1 Phase 3.5).

    Written (fsync) to:
      - ~/.config/stayturgid/stats/events.jsonl (all event types)
      - ~/.config/stayturgid/stats/soft_health.jsonl (Vector → OpenObserve)

    Vector tails soft_health.jsonl with disk buffer + e2e acks so OpenObserve
    can be offline for days. Does not rotate — local query via stats.query_events.
    """
    _stats_event(
        "soft_health",
        name,
        via=path or "",
        agent_age=_age_field(report.get("agent_age")),
        watchdog_age=_age_field(report.get("watchdog_age")),
        repair_age=_age_field(report.get("repair_age")),
        port=report.get("port") or "unknown",
        shizuku=report.get("shizuku") or "unknown",
        tailscale=report.get("tailscale") or "unknown",
        tailscale_policy=report.get("tailscale_policy") or "unknown",
        a11y=report.get("a11y") or "unknown",
        autojs6_a11y=report.get("autojs6_a11y") or "unknown",
        sshd=report.get("sshd") or "unknown",
        shell5555=report.get("shell5555") or "unknown",
        bootloop=report.get("bootloop") or "unknown",
        issues=",".join(issues) if issues else "none",
        issue_count=len(issues),
    )


def check_device(name: str, ts_ip: str, lan_ip: str) -> None:
    state_file = os.path.join(STATE_DIR, name)
    maintenance_file = os.path.join(STATE_DIR, f"{name}.maintenance")
    if os.path.isfile(maintenance_file):
        _fleet_log(INFO, "%s via bypass: issues=maintenance" % name)
        write_state(state_file, 0)
        return

    # Dismiss system dialogs that appear on debuggable-app devices and block the screen.
    target = dev.resolve_adb(name) if dev else None
    if target:
        try:
            import adb_cli

            adb_cli.dismiss_usb_debugging_dialog(target)
            adb_cli.dismiss_app_compatibility_dialog(target)
        except Exception:
            pass
    path, report = fh.probe_device(name, ts_ip, lan_ip)
    if not path:
        _fleet_log(INFO, "%s unreachable — skip soft health (see access-monitor)" % name)
        # FIRERPA gRPC (port 65000) is an independent transport — try it as
        # a last-resort repair channel when both ADB and SSH are down.
        _try_firerpa_heal_fallback(name, ts_ip)
        return

    # Check for state divergence (Mac connected via ADB but watchdog claims CLOSED_NO_SHELL)
    if path.startswith("adb:") and report.get("port") == "CLOSED_NO_SHELL":
        _fleet_log(
            WARNING,
            "%s: ALERT - state divergence detected! Mac reached ADB but watchdog log reports CLOSED_NO_SHELL" % name,
        )
        notify(
            "stayturgid alert",
            "%s: State divergence! Watchdog reports CLOSED_NO_SHELL but ADB is reachable." % name,
            sound="Basso",
        )

    if name == "fireos-device":
        maybe_heal_hd8_google_stack(name)

    issues = fh.evaluate_health(report, alias=name)
    summary = fh.summarize(report, issues)
    _fleet_log(INFO, "%s via %s: %s" % (name, path, summary))

    _stats_event("connection_path", name, via=path)
    for issue in issues:
        _stats_event("issue_detected", name, issue=issue)
    # Long-term dual-run / pre-cutover telemetry (JSONL forever under stats/).
    _record_soft_health_snapshot(name, path, report, issues)

    _scrape_device_errors(name, ts_ip)

    fails = read_state(state_file)
    if not issues:
        if fails >= CONSECUTIVE_LIMIT:
            _fleet_log(INFO, "%s health RECOVERED" % name)
            notify("stayturgid health", "%s soft checks OK again" % name)
        write_state(state_file, 0)
        return

    fails += 1
    write_state(state_file, fails)
    adb_serial = path.split(":", 1)[1] if path and path.startswith("adb:") else None
    maybe_heal_repair_stale(name, issues, fails)
    maybe_heal_agent(name, issues, fails, adb_serial=adb_serial)
    if fails == CONSECUTIVE_LIMIT:
        detail = ",".join(issues)
        if len(detail) > 180:
            detail = detail[:177] + "..."
        notify("stayturgid health", "%s: %s" % (name, detail), sound="Basso")


ET_MAC_HEAL_STATE = os.path.join(ROOT, "state", "et-mac-ensure")
ET_MAC_HEAL_COOLDOWN_SEC = 30 * 60  # re-sync fleet keys on Mac at most 2×/hour
FIRERPA_HEAL_COOLDOWN_SEC = 30 * 60  # try FIRERPA heal at most 2×/hour per host


def _try_firerpa_heal_fallback(name: str, ts_ip: str) -> None:
    """Attempt FIRERPA gRPC repair when both ADB and SSH are down."""
    if not ts_ip:
        return
    # Check if FIRERPA port is reachable via TCP before attempting heal.
    import socket

    try:
        s = socket.create_connection((ts_ip, 65000), timeout=5)
        s.close()
    except (OSError, socket.timeout):
        return
    # Rate-limit — don't spam FIRERPA heals on a device with flaky Tailscale.
    state_file = os.path.join(ROOT, "state", "firerpa-heal-fallback-%s" % name)
    try:
        mtime = os.path.getmtime(state_file)
        if time.time() - mtime < FIRERPA_HEAL_COOLDOWN_SEC:
            return
    except OSError:
        pass
    _fleet_log(INFO, "trigger %s firerpa-heal fallback (ADB+SSH down, gRPC reachable)" % name)
    try:
        import firerpa_heal

        result = firerpa_heal.heal_device(ts_ip)
        _fleet_log(INFO, "firerpa-heal %s: %s" % (name, result))
    except Exception as e:
        _fleet_log(INFO, "firerpa-heal %s error: %s" % (name, e))
    # Write stamp so we don't retry immediately.
    write_state(state_file, int(time.time()))


def maybe_ensure_et_mac() -> None:
    """Idempotent phone→Mac ET authorized_keys reconcile (marked block).

    Collects fleet pubs when hosts are up and rewrites STAYTURGID-ET-MAC.
    Does not touch peer-help ForceCommand lines. Rate-limited.
    """
    if SKIP_HEALTH or os.environ.get("STAYTURGID_SKIP_ET_MAC") == "1":
        return
    stamp = os.path.join(ET_MAC_HEAL_STATE, "last")
    try:
        age = datetime.datetime.now().timestamp() - os.path.getmtime(stamp)
        if age < ET_MAC_HEAL_COOLDOWN_SEC:
            return
    except OSError:
        pass
    script = os.path.join(REPO, "control", "bin", "ensure_et_mac.py")
    if not os.path.isfile(script):
        return
    try:
        r = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                "PATH": "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", ""),
            },
        )
        detail = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " | ")
        _fleet_log(INFO, "et-mac ensure rc=%s %s" % (r.returncode, detail[:400]))
        try:
            os.makedirs(ET_MAC_HEAL_STATE, exist_ok=True)
            with open(stamp, "w") as f:
                f.write(str(int(datetime.datetime.now().timestamp())))
        except OSError:
            pass
    except (OSError, subprocess.TimeoutExpired) as e:
        _fleet_log(INFO, "et-mac ensure error: %s" % e)


def main() -> int:
    if SKIP_HEALTH:
        return 0
    if not os.path.exists(CONF):
        return 0
    os.makedirs(STATE_DIR, exist_ok=True)
    trim_log(os.path.join(ROOT, "logs", LOG_NAME), max_age_days=30, max_lines=4000)
    trim_log(os.path.join(ROOT, "logs", "errors.log"), max_age_days=30, max_lines=2000)
    maybe_ensure_et_mac()
    for name, ts_ip, lan_ip in read_devices(CONF):
        try:
            check_device(name, ts_ip, lan_ip)
        except Exception as e:
            _fleet_log(
                ERR,
                "%s via none: sshd=unknown issues=probe_error probe_error=%s" % (name, str(e).replace(" ", "_")[:120]),
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
