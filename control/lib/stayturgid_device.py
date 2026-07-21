#!/usr/bin/env python3
from __future__ import annotations

"""Shared Mac-side device helpers (Python).

Pure, unit-tested logic (JSON patching, uid/UI-XML parsing, device resolution)
plus a small privileged-shell runner. Imported by control/tools/autojs6/grant_shizuku.py
and control/tools/obtainium/enable_shizuku_installer.py — replaces the fragile
python-in-bash heredocs and `tr '>' '\n' | grep | sed` UI parsing that were
easy to get wrong under macOS bash/zsh.
"""
import json
import os
import re
import shutil
import subprocess
import sys

DEVICES_CONF = os.environ.get(
    "STAYTURGID_DEVICES_CONF",
    os.path.join(os.path.expanduser("~"), ".config", "stayturgid", "devices.conf"),
)
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "LogLevel=ERROR"]

# Cached absolute adb path — launchd agents often have no Homebrew on PATH.
_ADB_BIN: str | None = None


def adb_bin() -> str:
    """Return an absolute path to adb when possible (launchd-safe).

    Order: STAYTURGID_ADB env, Homebrew paths, PATH lookup, bare ``adb``.
    """
    global _ADB_BIN
    if _ADB_BIN is not None:
        return _ADB_BIN
    env = os.environ.get("STAYTURGID_ADB", "").strip()
    candidates = [
        env,
        "/opt/homebrew/bin/adb",
        "/usr/local/bin/adb",
        shutil.which("adb") or "",
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            _ADB_BIN = c
            return _ADB_BIN
    _ADB_BIN = env or "adb"
    return _ADB_BIN


# --------------------------------------------------------------------------
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------
def patch_shizuku_json(current_text, uid, pkg):
    """Add/replace a uid->pkg authorization in shizuku.json, preserving all
    other entries. Mirrors the old embedded heredoc exactly."""
    uid = int(uid)
    raw = (current_text or "").strip()
    try:
        data = json.loads(raw) if raw else {"version": 2, "packages": []}
    except ValueError:
        data = {"version": 2, "packages": []}
    # Handle double-encoded JSON (written by json.dump of a json.dumps result).
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, json.JSONDecodeError):
            data = {"version": 2, "packages": []}
    pkgs = [e for e in data.get("packages", []) if e.get("uid") != uid]
    pkgs.append({"uid": uid, "flags": 2, "packages": [pkg]})
    data["packages"] = pkgs
    return json.dumps(data, separators=(",", ":"))


def parse_uid(pm_output):
    """`pm list packages -U <pkg>` -> uid string, or None. (package:...  uid:10123)"""
    m = re.search(r"uid:(\d+)", pm_output or "")
    return m.group(1) if m else None


def iter_devices_conf(conf_path=None):
    """Yield ``(name, usb_serial, tailscale_ip, lan_ip, label)`` for each devices.conf row.

    Line format: ``name usb_serial tailscale_ip [lan_ip] [device_label]``.
    Missing fields → ``"-"``. Single source of truth for launchd monitors and
    resolve helpers (review L9).
    """
    conf_path = conf_path or DEVICES_CONF
    try:
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                name = parts[0]
                usb, ts_ip = parts[1], parts[2]
                lan = parts[3] if len(parts) > 3 else "-"
                label = parts[4] if len(parts) > 4 else "-"
                yield name, usb, ts_ip, lan, label
    except OSError:
        return


def iter_monitor_hosts(conf_path=None):
    """Yield ``(name, tailscale_ip, lan_ip)`` — monitors that ignore USB serial."""
    for name, _usb, ts_ip, lan, *_label in iter_devices_conf(conf_path):
        yield name, ts_ip, lan


def device_row(alias, conf_path=None):
    """alias -> (usb_serial, tailscale_ip, lan_ip) from devices.conf, or None."""
    conf_path = conf_path or DEVICES_CONF
    for name, usb, ts_ip, lan, *_label in iter_devices_conf(conf_path):
        if name == alias:
            return (usb, ts_ip, lan)
    return None


def resolve_adb(alias, conf_path=None):
    """USB when online, else first reachable wireless endpoint (LAN then Tailscale).

    Unknown aliases pass through unchanged (raw serial / host:port).
    Keep in sync with ansible_collections/.../adb_resolve.py.
    """
    row = device_row(alias, conf_path)
    if not row:
        return alias

    def run_command(cmd):
        r = _run(cmd)
        if r is None:
            return 127, "", ""
        return r.returncode, r.stdout, r.stderr or ""

    # Reuse collection resolver when running from the repo checkout.
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    mod_path = os.path.join(
        root,
        "ansible_collections",
        "stayturgid",
        "android_common",
        "plugins",
        "module_utils",
        "adb_resolve.py",
    )
    if os.path.isfile(mod_path):
        spec = importlib.util.spec_from_file_location("_adb_resolve", mod_path)
        _ar = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_ar)
        return _ar.resolve_adb(alias, run_command, conf_path)

    # Minimal fallback when collection path is unavailable.
    usb, ts_ip, _lan = row
    if usb != "-":
        r = _run([adb_bin(), "devices"])
        if r and ("%s\tdevice" % usb) in (r.stdout or ""):
            return usb
    if ts_ip not in ("", "-"):
        return "%s:5555" % ts_ip
    lan = row[2] if len(row) > 2 else "-"
    if lan not in ("", "-"):
        return "%s:5555" % lan
    return alias


def resolve_ssh_host(alias, conf_path=None):
    """SSH alias for a known device, else '' (raw serial isn't SSH-addressable)."""
    return alias if device_row(alias, conf_path) else ""


# Pure XML parsers live in control/lib/ui_parse.py (Mac + Termux).
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
from ui_parse import (  # noqa: F401
    parse_button_center,
    parse_content_desc_center,
    parse_switch,
    parse_text_center,
)


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------
def _run(args, **kw):
    try:
        return subprocess.run(args, capture_output=True, text=True, **kw)
    except (OSError, subprocess.TimeoutExpired):
        return None


# Fire OS / aliases without Termux→localhost:5555 — Mac adb is authoritative.
MAC_ADB_PRIV_ALIASES = frozenset({"fireos-device"})


class PrivShell:
    """Run privileged shell commands on a device.

    Prefer Termux SSH → ``adb -s localhost:5555`` when that channel works
    (oneui-device/stock-android-device). Fire OS (fireos-device) and raw serials use Mac ``adb -s <target>`` —
    there is no Termux loopback on those hosts.
    """

    def __init__(self, alias, conf_path=None):
        self.alias = alias
        self.target = resolve_adb(alias, conf_path)
        self.ssh_host = None
        if alias not in MAC_ADB_PRIV_ALIASES:
            self.ssh_host = resolve_ssh_host(alias, conf_path)

    def sh(self, cmd, timeout=30):
        """Privileged ``adb shell <cmd>``. Returns (rc, stdout)."""
        if self.ssh_host:
            import shlex

            remote = "adb -s localhost:5555 shell %s\n" % shlex.quote(cmd)
            r = _run(["ssh"] + SSH_OPTS + [self.ssh_host, "bash", "-s"], input=remote, timeout=timeout)
        else:
            r = _run([adb_bin(), "-s", self.target, "shell", cmd], timeout=timeout)
        if r is None:
            return 127, ""
        return r.returncode, (r.stdout or "").replace("\r", "")

    def push(self, local_path, remote_path):
        r = _run([adb_bin(), "-s", self.target, "push", local_path, remote_path])
        return r is not None and r.returncode == 0

    def app_uid(self, pkg):
        return parse_uid(self.sh("pm list packages -U %s" % pkg)[1])

    def read_shizuku_json(self, path):
        """Return (current_text, ok). Distinguishes missing (ok, '') from a
        failed read (not ok) so the caller never clobbers other apps' grants."""
        if self.sh("true")[0] != 0:
            return "", False  # no privileged shell
        if self.sh("test -f %s" % path)[0] == 0:
            text = self.sh("cat %s" % path)[1]
            if not text.strip():
                return "", False  # exists but read empty — abort
            return text, True
        return "", True  # missing -> fresh config is fine

    def install_shizuku_json(self, content, staging, path):
        """Push new shizuku.json content and move it into place (chmod 666)."""
        import tempfile

        tmp = tempfile.NamedTemporaryFile("w", delete=False)
        try:
            tmp.write(content)
            tmp.close()
            if not self.push(tmp.name, staging):
                return False
        finally:
            os.unlink(tmp.name)
        return self.sh("cp %s %s && chmod 666 %s" % (staging, path, path))[0] == 0
