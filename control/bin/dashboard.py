#!/usr/bin/env python3
"""Fleet dashboard — Flask + HTMX web UI on port 4097.

Reads the same log files as the existing monitors (fleet-health.log,
firerpa-health.log, access-monitor state). Adds optional live probe via
fleet_health.probe_device(). Serves HTMX partials for auto-refreshing
device status cards.

Usage:
  python3 control/bin/dashboard.py [--port 4097]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_CONTROL = _REPO / "control"
_LIB = _CONTROL / "lib"
_BIN = _CONTROL / "bin"

for d in [_LIB, _BIN]:
    if str(d) not in sys.path:
        sys.path.append(str(d))
if str(_REPO) not in sys.path:
    sys.path.append(str(_REPO))

from check_fleet_health import read_consecutive as read_fleet_consecutive
from flask import Flask, render_template_string, request
from fleet_health import evaluate_health
from fleet_health import probe_device as live_probe
from markupsafe import Markup, escape
from stayturgid_device import SSH_OPTS, PrivShell, adb_bin, iter_devices_conf, resolve_ssh_host

import control.lib.stats as _stats

ROOT = Path(os.path.expanduser("~")) / ".config" / "stayturgid"
FLEET_LOG = ROOT / "logs" / "fleet-health.log"
FIRERPA_LOG = ROOT / "logs" / "firerpa-health.log"
ERROR_LOG = ROOT / "logs" / "errors.log"
DEVICES_CONF = ROOT / "devices.conf"
ACCESS_STATE = ROOT / "state" / "access-monitor"
DEFAULT_PORT = 4097

app = Flask(
    __name__,
    template_folder=str(_CONTROL / "templates"),
    static_folder=str(_CONTROL / "static"),
    static_url_path="/static",
)

TAILNET = "example.ts.net"
OC_WEB_URL = f"https://mac.{TAILNET}/opencode/"
NETWORK_URL = f"https://mac.{TAILNET}/"


def _parse_log_ts(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _age_s(ts: dt.datetime) -> float:
    return (dt.datetime.now() - ts).total_seconds()


def _age_str(sec: float) -> str:
    if sec < 60:
        return f"{int(sec)}s"
    if sec < 3600:
        return f"{int(sec / 60)}m"
    return f"{int(sec / 3600)}h"


def _badge(value: str, mapping: dict[str, str]) -> str:
    cls = mapping.get(value, "unknown")
    return f'<span class="badge {cls}">{value}</span>'


# ---------------------------------------------------------------------------
# fleet-health.log parsing
# ---------------------------------------------------------------------------
def _parse_space_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in text.split():
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        out[k.strip()] = v.strip()
    return out


_HEALTH_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?:[A-Z]+\s+)?(\S+)\s+via\s+(\S+):\s+(.*)$")


def _latest_fleet_health() -> dict[str, dict]:
    """host -> {ts, via, **kv_pairs} for latest scrape per host."""
    out: dict[str, dict] = {}
    if not FLEET_LOG.is_file():
        return out
    text = FLEET_LOG.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = _HEALTH_LINE_RE.search(line.strip())
        if not m:
            continue
        ts_s, host, via, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        ts = _parse_log_ts(ts_s)
        if ts is None:
            continue
        body: dict[str, Any] = dict(_parse_space_kv(rest))
        body["ts"] = ts
        body["via"] = via
        body["host"] = host
        out[host] = body
    return out


# ---------------------------------------------------------------------------
# firerpa-health.log parsing
# ---------------------------------------------------------------------------
_FIRERPA_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?:[A-Z]+\s+)?(\S+)\s+via\s+firerpa:(\S+):\s+(.*)$"
)


def _latest_firerpa_health() -> dict[str, dict]:
    """host -> {ts, firerpa_ip, firerpa_ver, sshd, shizuku, issues}."""
    out: dict[str, dict] = {}
    if not FIRERPA_LOG.is_file():
        return out
    text = FIRERPA_LOG.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = _FIRERPA_LINE_RE.search(line.strip())
        if not m:
            continue
        ts_s, host, ip, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        ts = _parse_log_ts(ts_s)
        if ts is None:
            continue
        kv = _parse_space_kv(rest)
        out[host] = {
            "ts": ts,
            "firerpa_ip": ip,
            "firerpa_ver": kv.get("firerpa", "?"),
            "firerpa_sshd": kv.get("sshd", "?"),
            "firerpa_shizuku": kv.get("shizuku", "?"),
            "firerpa_issues": kv.get("issues", ""),
        }
    return out


# ---------------------------------------------------------------------------
# access-monitor consecutive counters
# ---------------------------------------------------------------------------
def _read_access_state() -> dict[str, int]:
    """host -> consecutive failure count."""
    out: dict[str, int] = {}
    if not ACCESS_STATE.is_dir():
        return out
    for p in ACCESS_STATE.iterdir():
        if not p.is_file():
            continue
        try:
            out[p.name] = int(p.read_text().strip() or "0")
        except (OSError, ValueError):
            out[p.name] = 0
    return out


# ---------------------------------------------------------------------------
# badge helpers
# ---------------------------------------------------------------------------
_SERVICE_OK = {"ok": "ok", "up": "ok", "open": "ok"}
_SERVICE_BAD = {"down": "error", "closed": "error", "failed": "error", "missing": "error"}
_AGE_WARN = 30 * 60
_AGE_CRIT = 45 * 60

_SVC_LABELS = {
    "sshd": "sshd",
    "bootloop": "bootloop",
    "shell5555": "sh 5555",
    "shizuku": "shizuku",
    "a11y": "a11y",
    "autojs6_a11y": "autojs6",
    "cfengine": "cfengine",
    "port": "port",
}


def _svc_cls(value: str | None) -> str:
    if value is None:
        return "unknown"
    v = value.lower()
    if v in _SERVICE_OK or v == "repaired":
        return "ok"
    if v in _SERVICE_BAD or v.startswith(("failed", "closed")):
        return "error"
    return "unknown"


def _svc_badge(key: str, value: str | None, ok_values: frozenset[str] | None = None) -> Markup:
    if value is None:
        value = "?"
    if ok_values and value in ok_values:
        cls = "ok"
    else:
        cls = _svc_cls(value)
    # cls is one of _svc_cls's fixed literal returns; value is explicitly escaped below.
    return Markup(f'<span class="badge {cls}" title="{key}">{escape(value)}</span>')  # nosemgrep


def _age_badge(sec: int | None) -> Markup:
    if sec is None:
        return Markup('<span class="badge unknown">N/A</span>')
    if sec >= _AGE_CRIT:
        return Markup(f'<span class="badge error">{_age_str(sec)}</span>')  # nosemgrep
    if sec >= _AGE_WARN:
        return Markup(f'<span class="badge warn">{_age_str(sec)}</span>')  # nosemgrep
    return Markup(f'<span class="badge ok">{_age_str(sec)}</span>')  # nosemgrep


def _issue_tags(issues: list[str]) -> Markup:
    if not issues:
        return Markup("")
    return Markup(" ".join(f'<span class="tag error">{i}</span>' for i in issues))  # nosemgrep


HUMAN_ACTIONS = {
    "autojs6_a11y_missing": (
        "Open Android Settings → Accessibility → Downloaded apps → AutoJs6 "
        "→ toggle ON. If already ON, toggle OFF then ON again. "
        "This must be done on the device screen — Android blocks programmatic enable on 16+."
    ),
    "autojs6_a11y_stale": (
        "AutoJs6 is still listed as ON in Accessibility but the watchdog is not "
        "cycling — sticky/malfunctioning a11y (enabled but not bound). "
        "On the device: Settings → Accessibility → AutoJs6 → turn OFF then ON, "
        "then open AutoJs6 → run main.js. Do not only flip the switch once if it "
        "already shows ON."
    ),
    "a11y_failed": (
        "Accessibility repair failed. Open Android Settings → Accessibility → "
        "Downloaded apps → AutoJs6 → toggle ON. If already ON, toggle OFF then ON again."
    ),
    "a11y_profile_drift": (
        "Expected accessibility services are missing from this device. "
        "Run: just verify-heal HOSTS=<host> to merge-restore the profile."
    ),
    "port_closed": (
        "ADB wireless debugging port 5555 is closed. On the device, open "
        "Developer Options → Wireless debugging → enable. Or connect USB and run: "
        "adb tcpip 5555"
    ),
    "sshd_down": (
        "SSH daemon is not running on the device. The repair loop should auto-restart it. "
        "If persistent, run: just deploy-termux HOSTS=<host>"
    ),
    "repair_stale": (
        "The Termux repair loop has not cycled in over 45 minutes. "
        "The self-heal monitor will attempt to restart it. "
        "If persistent, run: just verify-heal HOSTS=<host>"
    ),
    "repair_missing": (
        "No repair log found. The Termux boot loop may not be running. Run: just deploy-termux HOSTS=<host>"
    ),
    "shizuku_down": (
        "Shizuku is not running. The repair loop should auto-restart it. "
        "If persistent, open the Shizuku app and tap Start."
    ),
    "watchdog_stale": (
        "AutoJs6 watchdog has not cycled in over 30 minutes. "
        "The self-heal monitor attempts to restart it via ADB. "
        "If persistent, the AutoJs6 JavaScript task may be stuck — "
        "force-stop the AutoJs6 app in Android Settings, then run: "
        "just verify-heal HOSTS=<host>"
    ),
    "watchdog_missing": (
        "No AutoJs6 watchdog log entries found. The AutoJs6 app may not "
        "be running. Run: just verify-heal HOSTS=<host> to attempt restart."
    ),
    "bootloop_down": (
        "The Termux boot loop (start-adb.sh) was not detected at probe time. "
        "This is often a false positive (probe timing gap). If persistent, "
        "run: just deploy-termux HOSTS=<host>"
    ),
    "shell5555_down": (
        "Termux cannot reach ADB on localhost:5555. Wireless debugging "
        "may be off or Shizuku's ADB service needs restart. "
        "Run: just verify-heal HOSTS=<host>"
    ),
    "probe_error": (
        "The fleet-health monitor could not probe this device (ADB missing, "
        "timeout, or script error). Check the fleet-health log for details. "
        "If USB ADB is disconnected, reconnect it."
    ),
    "ssh_echo": (
        "SSH probe echo failed — TCP connection may work but command "
        "execution is failing. Check PerSourcePenalties on the device."
    ),
    "cfengine_down": (
        "CFEngine repair log not found on device. The CFEngine self-heal "
        "policy may not be running. Run: just deploy-termux HOSTS=<host> "
        "to redeploy."
    ),
}


def _rish_probe(hostname: str) -> tuple[bool, str]:
    """Run the canonical UID-2000 probe over the device's Termux SSH path."""
    ssh_host = resolve_ssh_host(hostname)
    if not ssh_host:
        return False, "no Termux SSH path is configured"
    try:
        result = subprocess.run(
            ["ssh", *SSH_OPTS, ssh_host, "~/.stayturgid/bin/rish -c 'id -u'"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "rish probe timed out or SSH is unavailable"
    uid = (result.stdout or "").strip().splitlines()[-1] if result.stdout else ""
    if result.returncode == 0 and uid == "2000":
        return True, "authorized (UID 2000)"
    detail = (result.stderr or result.stdout or "no UID-2000 response").strip()
    return False, "not authorized (%s)" % detail[:180]


def request_shizuku_authorization(hostname: str) -> tuple[bool, str]:
    """Open Shizuku on-device, then verify rish; Android consent stays human-gated."""
    try:
        rc, _output = PrivShell(hostname).sh(
            "am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p moe.shizuku.privileged.api",
            timeout=20,
        )
    except (OSError, ValueError) as exc:
        return False, "could not open Shizuku: %s" % exc
    if rc != 0:
        return False, "could not open Shizuku (device shell rc=%s)" % rc
    ok, detail = _rish_probe(hostname)
    if ok:
        try:
            PrivShell(hostname).sh(
                "am start -a android.intent.action.MAIN -c android.intent.category.HOME",
                timeout=10,
            )
        except (OSError, ValueError):
            pass
        return True, detail
    return False, "Shizuku opened; tap Allow all the time, then retry (%s)" % detail


def _run(args, **kw):
    args = list(args)
    if args and args[0] == "adb":
        args[0] = adb_bin()
    try:
        return subprocess.run(args, capture_output=True, text=True, **kw)
    except (OSError, subprocess.TimeoutExpired):
        return None


def mac_adb_shell(serial, *args, timeout=30):
    r = _run(["adb", "-s", serial, "shell"] + list(args), timeout=timeout)
    if r is None:
        return 127, ""
    return r.returncode, r.stdout.replace("\r", "")


def get_pending_ui(hostname: str) -> dict | None:
    # 1. Check Mac-side pending UI file
    mac_path = Path(os.path.expanduser("~")) / ".config" / "stayturgid" / "state" / "pending_ui.json"
    if mac_path.is_file():
        try:
            with open(mac_path) as f:
                data = json.load(f)
                if data.get("host") == hostname and data.get("status") == "pending":
                    data["elapsed_s"] = int(time.time() - data.get("started_at", time.time()))
                    return data
        except Exception:
            pass

    # 2. Check Device-side pending UI file
    serial = None
    for name, usb, ts_ip, lan, label in iter_devices_conf(str(DEVICES_CONF)):
        if name == hostname:
            serial = usb if usb != "-" else f"{ts_ip}:5555" if ts_ip != "-" else ""
            break
    if serial:
        rc, out = mac_adb_shell(serial, "cat", "/sdcard/stayturgid/state/pending_ui.json", timeout=1.0)
        if rc == 0 and out.strip():
            try:
                data = json.loads(out.strip())
                if data.get("status") == "pending":
                    data["elapsed_s"] = int(time.time() - data.get("started_at", time.time()))
                    data["is_device"] = True
                    data["serial"] = serial
                    return data
            except Exception:
                pass
    return None


def _human_actions(issues: list[str], hostname: str) -> list[dict]:
    out: list[dict] = []
    for tag in issues:
        if tag in HUMAN_ACTIONS:
            msg = HUMAN_ACTIONS[tag].replace("<host>", hostname)
            out.append({"issue": tag, "message": msg, "shizuku_action": tag == "shizuku_down"})
    return out


def _safe_int(s: str | None) -> int | None:
    if s is None or s in ("missing", "unknown", ""):
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _build_services(h: dict) -> list[dict]:
    svc_order = ["sshd", "bootloop", "shell5555", "shizuku", "a11y", "autojs6_a11y", "cfengine", "port"]
    out: list[dict] = []
    for key in svc_order:
        val = h.get(key)
        if val is None or val in ("skip",):
            continue
        out.append({"label": _SVC_LABELS.get(key, key), "value": val, "cls": _svc_cls(val)})
    return out


# ---------------------------------------------------------------------------
# data assembly
# ---------------------------------------------------------------------------
def build_device_data() -> list[dict]:
    health = _latest_fleet_health()
    firerpa = _latest_firerpa_health()
    access_state = _read_access_state()
    fleet_consec = read_fleet_consecutive()

    devices: list[dict] = []
    for name, usb, ts_ip, lan, label in iter_devices_conf(str(DEVICES_CONF)):
        d: dict = {
            "name": name,
            "label": label if label != "-" else name,
            "usb_serial": usb if usb != "-" else "",
            "ts_ip": ts_ip if ts_ip != "-" else "",
            "lan_ip": lan if lan != "-" else "",
            "magicdns": f"{name}.{TAILNET}",
            "health": health.get(name),
            "firerpa": firerpa.get(name),
            "access_fails": access_state.get(name, 0),
            "fleet_consec": fleet_consec.get(name, 0),
        }

        h = d["health"]
        if h is not None:
            report_issues = evaluate_health(h, alias=name)
            d["issues"] = report_issues
            d["health_age_s"] = _age_s(h["ts"])
            d["health_age"] = _age_str(d["health_age_s"])
            d["via_display"] = h.get("via", "?")
            d["services"] = _build_services(h)
            d["agent_age"] = _safe_int(h.get("agent_age"))
            d["watchdog_age"] = _safe_int(h.get("watchdog_age"))
            d["repair_age"] = _safe_int(h.get("repair_age"))
            d["agent_badge"] = _age_badge(d["agent_age"])
            d["watchdog_badge"] = _age_badge(d["watchdog_age"])
            d["repair_badge"] = _age_badge(d["repair_age"])
            d["issue_tags"] = _issue_tags(report_issues)
            d["human_actions"] = _human_actions(report_issues, name)
        else:
            d["issues"] = []
            d["health_age_s"] = None
            d["health_age"] = "--"
            d["via_display"] = "?"
            d["services"] = []
            d["watchdog_age"] = None
            d["repair_age"] = None
            d["watchdog_badge"] = _age_badge(None)
            d["repair_badge"] = _age_badge(None)
            d["issue_tags"] = _issue_tags([])
            d["human_actions"] = []

        fr = d["firerpa"]
        if fr is not None:
            d["firerpa_age_s"] = _age_s(fr["ts"])
            d["firerpa_age"] = _age_str(d["firerpa_age_s"])
            d["firerpa_badge"] = _svc_badge(
                "firerpa", fr.get("firerpa_ver"), ok_values=frozenset({fr.get("firerpa_ver", "?")})
            )
            d["firerpa_sshd_badge"] = _svc_badge("sshd", fr.get("firerpa_sshd"))
            d["firerpa_shizuku_badge"] = _svc_badge("shizuku", fr.get("firerpa_shizuku"))
        else:
            d["firerpa_age_s"] = None
            d["firerpa_age"] = "--"

        d["pending_ui"] = get_pending_ui(name)

        devices.append(d)

    devices.sort(key=lambda x: x["name"])
    return devices


# ---------------------------------------------------------------------------
# templates (inline for single-file portability; also loads from disk)
# ---------------------------------------------------------------------------
def _render_template(name: str, **ctx) -> str:
    template_dir = _CONTROL / "templates"
    template_file = template_dir / name
    if template_file.is_file():
        with open(template_file) as f:
            return render_template_string(f.read(), **ctx)  # nosemgrep
    return f"<!-- template {name} not found -->"


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    devices = build_device_data()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    # Each card is already-rendered HTML; wrap in Markup before interpolating
    # into dashboard.html's {{ cards }} or Jinja re-escapes it (matches the
    # _svc_badge() convention used elsewhere in this file).
    cards = Markup(
        "\n".join(
            _render_template("_device_card.html", device=d, oc_web_url=OC_WEB_URL, network_url=NETWORK_URL, now=now)
            for d in devices
        )
    )
    return _render_template("dashboard.html", cards=cards, oc_web_url=OC_WEB_URL, network_url=NETWORK_URL, now=now)


@app.route("/api/devices")
def api_devices():
    devices = build_device_data()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cards = "\n".join(
        _render_template("_device_card.html", device=d, oc_web_url=OC_WEB_URL, network_url=NETWORK_URL, now=now)
        for d in devices
    )
    return cards


@app.route("/api/probe/<host>", methods=["POST"])
def api_probe(host: str):
    row = None
    for name, usb, ts_ip, lan, label in iter_devices_conf(str(DEVICES_CONF)):
        if name == host:
            row = (name, usb, ts_ip, lan, label)
            break

    if row is None:
        return f'<div class="card error">Unknown host: {host}</div>', 404  # nosemgrep

    name, usb, ts_ip, lan, label = row
    _, report = live_probe(name, ts_ip if ts_ip != "-" else "", lan if lan != "-" else "")

    now = time.strftime("%Y-%m-%d %H:%M:%S")

    if report.get("reachable") == "no":
        d = {
            "name": name,
            "label": label if label != "-" else name,
            "usb_serial": usb if usb != "-" else "",
            "ts_ip": ts_ip if ts_ip != "-" else "",
            "lan_ip": lan if lan != "-" else "",
            "magicdns": f"{name}.{TAILNET}",
            "health": None,
            "firerpa": _latest_firerpa_health().get(name),
            "access_fails": _read_access_state().get(name, 0),
            "fleet_consec": read_fleet_consecutive().get(name, 0),
            "issues": [],
            "health_age_s": None,
            "health_age": "--",
            "via_display": "unreachable",
            "services": [],
            "agent_age": None,
            "watchdog_age": None,
            "repair_age": None,
            "agent_badge": _age_badge(None),
            "watchdog_badge": _age_badge(None),
            "repair_badge": _age_badge(None),
            "issue_tags": _issue_tags([]),
            "human_actions": [],
            "probe_error": True,
        }
    else:
        h = report
        h["ts"] = dt.datetime.now()
        h["via"] = report.get("via", "live")
        report_issues = evaluate_health(h, alias=name)
        d = {
            "name": name,
            "label": label if label != "-" else name,
            "usb_serial": usb if usb != "-" else "",
            "ts_ip": ts_ip if ts_ip != "-" else "",
            "lan_ip": lan if lan != "-" else "",
            "magicdns": f"{name}.{TAILNET}",
            "health": h,
            "firerpa": _latest_firerpa_health().get(name),
            "access_fails": _read_access_state().get(name, 0),
            "fleet_consec": read_fleet_consecutive().get(name, 0),
            "issues": report_issues,
            "health_age_s": 0,
            "health_age": "live",
            "via_display": h.get("via", "live"),
            "services": _build_services(h),
            "agent_age": _safe_int(h.get("agent_age")),
            "watchdog_age": _safe_int(h.get("watchdog_age")),
            "repair_age": _safe_int(h.get("repair_age")),
            "agent_badge": _age_badge(None),
            "watchdog_badge": _age_badge(None),
            "repair_badge": _age_badge(None),
            "issue_tags": _issue_tags(report_issues),
            "human_actions": _human_actions(report_issues, name),
            "probe_live": True,
        }
        aa = d["agent_age"]
        d["agent_badge"] = _age_badge(aa)
        wa = d["watchdog_age"]
        d["watchdog_badge"] = _age_badge(wa)
        ra = d["repair_age"]
        d["repair_badge"] = _age_badge(ra)

    fr = d["firerpa"]
    if fr is not None:
        d["firerpa_age_s"] = _age_s(fr["ts"])
        d["firerpa_age"] = _age_str(d["firerpa_age_s"])
        d["firerpa_badge"] = _svc_badge(
            "firerpa", fr.get("firerpa_ver"), ok_values=frozenset({fr.get("firerpa_ver", "?")})
        )
        d["firerpa_sshd_badge"] = _svc_badge("sshd", fr.get("firerpa_sshd"))
        d["firerpa_shizuku_badge"] = _svc_badge("shizuku", fr.get("firerpa_shizuku"))
    else:
        d["firerpa_age_s"] = None
        d["firerpa_age"] = "--"

    return _render_template("_device_card.html", device=d, oc_web_url=OC_WEB_URL, network_url=NETWORK_URL, now=now)


@app.route("/api/shizuku/<host>", methods=["POST"])
def api_shizuku(host: str):
    """Open Shizuku and immediately verify Termux rish authorization."""
    known = {name for name, *_row in iter_devices_conf(str(DEVICES_CONF))}
    if host not in known:
        return '<div class="probe-error">Unknown host: %s</div>' % escape(host), 404  # nosemgrep
    ok, message = request_shizuku_authorization(host)
    cls = "ok" if ok else "warn"
    return '<div class="shizuku-result %s"><strong>Shizuku:</strong> %s</div>' % (cls, escape(message))  # nosemgrep


@app.route("/api/pending_ui/done/<host>", methods=["POST"])
def api_pending_ui_done(host: str):
    """Mark the pending UI request for host as done, allowing blocked scripts to resume."""
    # 1. Update Mac-side pending UI file
    mac_path = Path(os.path.expanduser("~")) / ".config" / "stayturgid" / "state" / "pending_ui.json"
    updated = False
    if mac_path.is_file():
        try:
            with open(mac_path) as f:
                data = json.load(f)
            if data.get("host") == host:
                data["status"] = "done"
                with open(mac_path, "w") as f:
                    json.dump(data, f, indent=2)
                updated = True
        except Exception:
            pass

    # 2. Update Device-side pending UI file
    serial = None
    for name, usb, ts_ip, lan, label in iter_devices_conf(str(DEVICES_CONF)):
        if name == host:
            serial = usb if usb != "-" else f"{ts_ip}:5555" if ts_ip != "-" else ""
            break
    if serial:
        rc, out = mac_adb_shell(serial, "cat", "/sdcard/stayturgid/state/pending_ui.json", timeout=1.0)
        if rc == 0 and out.strip():
            try:
                data = json.loads(out.strip())
                data["status"] = "done"
                content = json.dumps(data)
                subprocess.run(
                    [adb_bin(), "-s", serial, "shell", "cat > /sdcard/stayturgid/state/pending_ui.json"],
                    input=content,
                    text=True,
                    capture_output=True,
                    timeout=2.0,
                )
                updated = True
                mac_adb_shell(
                    serial,
                    "am",
                    "start",
                    "-a",
                    "android.intent.action.MAIN",
                    "-c",
                    "android.intent.category.HOME",
                    timeout=5.0,
                )
            except Exception:
                pass

    if updated:
        return f'<div class="shizuku-result ok" style="color: #98c379;"><strong>Done signal sent</strong> for {escape(host)}</div>'  # nosemgrep
    return f'<div class="shizuku-result warn" style="color: #e5c07b;">No pending UI request found for {escape(host)}</div>'  # nosemgrep


@app.route("/health")
def health():
    return "ok", 200, {"Content-Type": "text/plain"}


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------
_TIMEFRAME_RE = re.compile(r"^(\d+)\s*(m|min|h|hr|d|day|w|wk|M|mo|y|yr)$")


def _parse_timeframe(range_str: str) -> dt.timedelta:
    m = _TIMEFRAME_RE.match(range_str.strip().lower())
    if not m:
        return dt.timedelta(weeks=1)
    n = int(m.group(1))
    unit = m.group(2)
    if unit in ("m", "min"):
        return dt.timedelta(minutes=n)
    if unit in ("h", "hr"):
        return dt.timedelta(hours=n)
    if unit in ("d", "day"):
        return dt.timedelta(days=n)
    if unit in ("w", "wk"):
        return dt.timedelta(weeks=n)
    if unit in ("M", "mo"):
        return dt.timedelta(days=n * 30)
    if unit in ("y", "yr"):
        return dt.timedelta(days=n * 365)
    return dt.timedelta(weeks=1)


_SELECT_OPTIONS = [
    ("15m", "15 minutes"),
    ("1h", "1 hour"),
    ("6h", "6 hours"),
    ("1d", "1 day"),
    ("3d", "3 days"),
    ("1w", "1 week"),
    ("2w", "2 weeks"),
    ("1M", "1 month"),
    ("3M", "3 months"),
    ("1y", "1 year"),
]


@app.route("/errors")
def errors_page():
    """Show recent device errors from errors.log."""
    _ERROR_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$")
    entries: list[dict] = []
    if ERROR_LOG.is_file():
        try:
            raw = ERROR_LOG.read_text().splitlines()
        except OSError:
            raw = []
        for line in reversed(raw[-500:]):
            m = _ERROR_LINE_RE.match(line)
            if not m:
                continue
            ts, level, rest = m.group(1), m.group(2), m.group(3)
            entries.append(
                {
                    "ts": ts,
                    "level": level,
                    "msg": rest[:300],
                    "cls": "error" if level in ("ERR", "CRIT", "EMERG") else ("warn" if level == "WARNING" else "info"),
                }
            )

    return _render_template(
        "errors.html",
        entries=entries,
        count=len(entries),
        oc_web_url=OC_WEB_URL,
        now=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/stats", strict_slashes=False)
def stats_page():
    range_str = request.args.get("range", "1w")
    delta = _parse_timeframe(range_str)
    since = dt.datetime.now(dt.timezone.utc) - delta
    stat_data = _stats.aggregate_stats(since=since)

    devices = [name for name, *_ in iter_devices_conf(str(DEVICES_CONF))]
    display_range = dict(_SELECT_OPTIONS).get(range_str, range_str)

    return _render_template(
        "stats.html",
        stats=stat_data,
        devices=devices,
        range_str=range_str,
        display_range=display_range,
        select_options=_SELECT_OPTIONS,
        oc_web_url=OC_WEB_URL,
        network_url=NETWORK_URL,
        now=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/api/stats")
def api_stats():
    range_str = request.args.get("range", "1w")
    delta = _parse_timeframe(range_str)
    since = dt.datetime.now(dt.timezone.utc) - delta
    stat_data = _stats.aggregate_stats(since=since)

    devices = [name for name, *_ in iter_devices_conf(str(DEVICES_CONF))]
    display_range = dict(_SELECT_OPTIONS).get(range_str, range_str)

    return _render_template(
        "_stats_content.html",
        stats=stat_data,
        devices=devices,
        range_str=range_str,
        display_range=display_range,
        select_options=_SELECT_OPTIONS,
        now=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="stayturgid fleet dashboard")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Listen port (default: {DEFAULT_PORT})")
    ap.add_argument("--debug", action="store_true", help="Flask debug mode")
    args = ap.parse_args()

    app.run(host="127.0.0.1", port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
