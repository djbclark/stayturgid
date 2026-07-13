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
import os
import re
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CONTROL = _REPO / "control"
_LIB = _CONTROL / "lib"
_BIN = _CONTROL / "bin"

for d in [_LIB, _BIN]:
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from flask import Flask, render_template_string, request, url_for
from markupsafe import Markup
from fleet_health import probe_device as live_probe, evaluate_health
from check_fleet_health import read_consecutive as read_fleet_consecutive
from stayturgid_device import iter_devices_conf

ROOT = Path(os.path.expanduser("~")) / ".config" / "stayturgid"
FLEET_LOG = ROOT / "logs" / "fleet-health.log"
FIRERPA_LOG = ROOT / "logs" / "firerpa-health.log"
DEVICES_CONF = ROOT / "devices.conf"
ACCESS_STATE = ROOT / "state" / "access-monitor"
DEFAULT_PORT = 4097

app = Flask(__name__,
            template_folder=str(_CONTROL / "templates"),
            static_folder=str(_CONTROL / "static"),
            static_url_path="/static")

OC_WEB_URL = "http://djbclarks-macbook-air.local:4096/"


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


_HEALTH_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+via\s+(\S+):\s+(.*)$"
)


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
        body = _parse_space_kv(rest)
        body["ts"] = ts
        body["via"] = via
        body["host"] = host
        out[host] = body
    return out


# ---------------------------------------------------------------------------
# firerpa-health.log parsing
# ---------------------------------------------------------------------------
_FIRERPA_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+via\s+firerpa:(\S+):\s+(.*)$"
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
    "sshd": "sshd", "bootloop": "bootloop", "shell5555": "sh 5555",
    "shizuku": "shizuku", "a11y": "a11y", "autojs6_a11y": "autojs6",
    "cfengine": "cfengine", "port": "port",
}


def _svc_cls(value: str | None) -> str:
    if value is None:
        return "unknown"
    if value in _SERVICE_OK:
        return "ok"
    if value in _SERVICE_BAD:
        return "error"
    return "unknown"


def _svc_badge(key: str, value: str | None, ok_values: frozenset[str] | None = None) -> Markup:
    if value is None:
        value = "?"
    if ok_values and value in ok_values:
        cls = "ok"
    elif value in _SERVICE_OK:
        cls = "ok"
    elif value in _SERVICE_BAD:
        cls = "error"
    else:
        cls = "unknown"
    return Markup(f'<span class="badge {cls}" title="{key}">{value}</span>')


def _age_badge(sec: int | None) -> Markup:
    if sec is None:
        return Markup('<span class="badge unknown">N/A</span>')
    if sec >= _AGE_CRIT:
        return Markup(f'<span class="badge error">{_age_str(sec)}</span>')
    if sec >= _AGE_WARN:
        return Markup(f'<span class="badge warn">{_age_str(sec)}</span>')
    return Markup(f'<span class="badge ok">{_age_str(sec)}</span>')


def _issue_tags(issues: list[str]) -> Markup:
    if not issues:
        return Markup('<span class="badge ok">none</span>')
    return Markup(" ".join(f'<span class="tag error">{i}</span>' for i in issues))


def _human_actions(issues: list[str], hostname: str) -> list[dict]:
    out: list[dict] = []
    for tag in issues:
        if tag in HUMAN_ACTIONS:
            msg = HUMAN_ACTIONS[tag].replace("<host>", hostname)
            out.append({"issue": tag, "message": msg})
    return out


HUMAN_ACTIONS = {
    "autojs6_a11y_missing": (
        "Open Android Settings → Accessibility → Downloaded apps → AutoJs6 "
        "→ toggle ON. If already ON, toggle OFF then ON again. "
        "This must be done on the device screen — Android blocks programmatic enable on 16+."
    ),
    "a11y_failed": (
        "Accessibility repair failed. Open Android Settings → Accessibility → "
        "Downloaded apps → AutoJs6 → toggle ON. If already ON, toggle OFF then ON again."
    ),
    "a11y_profile_drift": (
        "Expected accessibility services are missing from this device. "
        "Run: make verify-heal HOSTS=<host> to merge-restore the profile."
    ),
    "port_closed": (
        "ADB wireless debugging port 5555 is closed. On the device, open "
        "Developer Options → Wireless debugging → enable. Or connect USB and run: "
        "adb tcpip 5555"
    ),
    "sshd_down": (
        "SSH daemon is not running on the device. The repair loop should auto-restart it. "
        "If persistent, run: make deploy-termux HOSTS=<host>"
    ),
    "repair_stale": (
        "The Termux repair loop has not cycled in over 45 minutes. "
        "The self-heal monitor will attempt to restart it. "
        "If persistent, run: make verify-heal HOSTS=<host>"
    ),
    "repair_missing": (
        "No repair log found. The Termux boot loop may not be running. "
        "Run: make deploy-termux HOSTS=<host>"
    ),
    "shizuku_down": (
        "Shizuku is not running. The repair loop should auto-restart it. "
        "If persistent, open the Shizuku app and tap Start."
    ),
}


def _build_services(h: dict) -> list[dict]:
    svc_order = ["sshd", "bootloop", "shell5555", "shizuku", "a11y",
                 "autojs6_a11y", "cfengine", "port"]
    out: list[dict] = []
    for key in svc_order:
        val = h.get(key)
        if val is None or val in ("skip",):
            continue
        cls = _svc_cls(val)
        if key == "port":
            cls = "ok" if val == "open" else ("error" if val == "closed" else "unknown")
        out.append({"label": _SVC_LABELS.get(key, key), "value": val, "cls": cls})
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
            wa = h.get("watchdog_age")
            d["watchdog_age"] = int(wa) if wa and wa not in ("missing", "unknown") else None
            ra = h.get("repair_age")
            d["repair_age"] = int(ra) if ra and ra not in ("missing", "unknown") else None
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
            d["firerpa_badge"] = _svc_badge("firerpa", fr.get("firerpa_ver"),
                                           ok_values=frozenset({fr.get("firerpa_ver", "?")}))
            d["firerpa_sshd_badge"] = _svc_badge("sshd", fr.get("firerpa_sshd"))
            d["firerpa_shizuku_badge"] = _svc_badge("shizuku", fr.get("firerpa_shizuku"))
        else:
            d["firerpa_age_s"] = None
            d["firerpa_age"] = "--"

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
            return render_template_string(f.read(), **ctx)
    return f"<!-- template {name} not found -->"


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    devices = build_device_data()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cards = "\n".join(
        _render_template("_device_card.html", device=d,
                         oc_web_url=OC_WEB_URL, now=now)
        for d in devices
    )
    return _render_template("dashboard.html", cards=cards,
                            oc_web_url=OC_WEB_URL, now=now)


@app.route("/api/devices")
def api_devices():
    devices = build_device_data()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cards = "\n".join(
        _render_template("_device_card.html", device=d,
                         oc_web_url=OC_WEB_URL, now=now)
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
        return f'<div class="card error">Unknown host: {host}</div>', 404

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
            "health": None,
            "firerpa": _latest_firerpa_health().get(name),
            "access_fails": _read_access_state().get(name, 0),
            "fleet_consec": read_fleet_consecutive().get(name, 0),
            "issues": [],
            "health_age_s": None,
            "health_age": "--",
            "via_display": "unreachable",
            "services": [],
            "watchdog_age": None,
            "repair_age": None,
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
            "health": h,
            "firerpa": _latest_firerpa_health().get(name),
            "access_fails": _read_access_state().get(name, 0),
            "fleet_consec": read_fleet_consecutive().get(name, 0),
            "issues": report_issues,
            "health_age_s": 0,
            "health_age": "live",
            "via_display": h.get("via", "live"),
            "services": _build_services(h),
            "watchdog_age": int(h.get("watchdog_age", "0")) if h.get("watchdog_age") not in ("missing", "unknown", None) else None,
            "repair_age": int(h.get("repair_age", "0")) if h.get("repair_age") not in ("missing", "unknown", None) else None,
            "watchdog_badge": _age_badge(None),
            "repair_badge": _age_badge(None),
            "issue_tags": _issue_tags(report_issues),
            "human_actions": _human_actions(report_issues, name),
            "probe_live": True,
        }
        wa = d["watchdog_age"]
        d["watchdog_badge"] = _age_badge(wa)
        ra = d["repair_age"]
        d["repair_badge"] = _age_badge(ra)

    fr = d["firerpa"]
    if fr is not None:
        d["firerpa_age_s"] = _age_s(fr["ts"])
        d["firerpa_age"] = _age_str(d["firerpa_age_s"])
        d["firerpa_badge"] = _svc_badge("firerpa", fr.get("firerpa_ver"),
                                       ok_values=frozenset({fr.get("firerpa_ver", "?")}))
        d["firerpa_sshd_badge"] = _svc_badge("sshd", fr.get("firerpa_sshd"))
        d["firerpa_shizuku_badge"] = _svc_badge("shizuku", fr.get("firerpa_shizuku"))
    else:
        d["firerpa_age_s"] = None
        d["firerpa_age"] = "--"

    return _render_template("_device_card.html", device=d,
                            oc_web_url=OC_WEB_URL, now=now)


@app.route("/health")
def health():
    return "ok", 200, {"Content-Type": "text/plain"}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="stayturgid fleet dashboard")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"Listen port (default: {DEFAULT_PORT})")
    ap.add_argument("--debug", action="store_true", help="Flask debug mode")
    args = ap.parse_args()

    app.run(host="0.0.0.0", port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
