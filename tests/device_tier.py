#!/usr/bin/env python3
"""Tier (c): device tests — STRICTLY read-only / non-destructive.

Python replacement for the former tests/test-device.sh. Mac-side dev tooling
runs only here, where macOS bash 3.2 / zsh oddities repeatedly bit us:
  - a $(<<heredoc) with case/$() inside miscounted parens (truncated the
    heredoc, ran `for f` locally -> unbound var);
  - `md5` vs `md5sum` platform split;
  - `${var}` colon-modifier surprises in zsh.
In Python the on-device gather script is inert string data, hashing is
hashlib, and behavior is identical on macOS and Linux (CI).

Usage: device_tier.py [--ansible-check] [--heal] [host ...]
  (default hosts: every device in ~/.config/stayturgid/devices.conf)
Emits TAP. Exit 0 = all pass.
"""
import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVICES_CONF = os.environ.get(
    "STAYTURGID_DEVICES_CONF",
    os.path.join(os.path.expanduser("~"), ".config", "stayturgid", "devices.conf"),
)

# Deployed home scripts whose md5 is compared against the repo copy:
# (deployed_name -> repo path). Runtime logic migrated to Python (termux/py/);
# the remaining .sh are compat shims / the bridge.
TRACKED_SCRIPTS = {
    "stayturgid-repair.sh": "termux/stayturgid-repair.sh",
    "repair-bridge.sh": "termux/repair-bridge.sh",
    "agent-presence.sh": "termux/agent-presence.sh",
    "claude-presence.sh": "termux/claude-presence.sh",
    "stayturgid_check_repo_version.py": "termux/py/stayturgid_check_repo_version.py",
    "stayturgid_screen_awake_guard.py": "termux/py/stayturgid_screen_awake_guard.py",
    "stayturgid_agent_presence.py": "termux/py/stayturgid_agent_presence.py",
    "stayturgid_battery_alarm.py": "termux/py/stayturgid_battery_alarm.py",
    "stayturgid_repair.py": "termux/py/stayturgid_repair.py",
    "stayturgid_autojs6_guard.py": "termux/py/stayturgid_autojs6_guard.py",
}

# Runs on the device (Termux bash — consistent there). Emits key=value lines.
REMOTE_GATHER = r"""
export PATH=/data/data/com.termux/files/usr/bin:$PATH
export TMPDIR=/data/data/com.termux/files/usr/tmp
[ -f ~/.stayturgid/env ] && . ~/.stayturgid/env
SD="${STAYTURGID_SD:-/sdcard/stayturgid}"
FIRE=0
case "$SD" in *termux/files/home*) FIRE=1; echo "localhost_shell=skip" ;; esac
echo "ssh=ok"
pgrep -x sshd >/dev/null 2>&1 && echo "sshd=ok" || echo "sshd=down"
pgrep -f 'start-adb\.sh' >/dev/null 2>&1 && echo "bootloop=ok" || echo "bootloop=down"
pid=$(cat ~/.stayturgid/run/bridge.pid 2>/dev/null)
if [ -n "$pid" ] && [ -d "/proc/$pid" ] && grep -q repair-bridge "/proc/$pid/cmdline" 2>/dev/null; then
    echo "bridge=ok"
else
    echo "bridge=down"
fi
if [ "$FIRE" = 1 ]; then
    echo "shell5555=down"
else
    adb connect localhost:5555 >/dev/null 2>&1 </dev/null
    uid=$(adb -s localhost:5555 shell id -u 2>/dev/null </dev/null | tr -d "\r")
    [ "$uid" = "2000" ] && echo "shell5555=ok" || echo "shell5555=down"
fi
last=$(grep -h "\[repair\]" "$SD/logs/watchdog.log" /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1 | cut -d" " -f1,2)
if [ -n "$last" ]; then
    age=$(( $(date +%s) - $(date -d "$last" +%s 2>/dev/null || echo 0) ))
    [ "$age" -ge 0 ] && [ "$age" -lt 2700 ] && echo "repairlog=fresh" || echo "repairlog=stale"
else
    echo "repairlog=missing"
fi
# AutoJs6 secondary watchdog liveness: it writes a [watchdog] line every ~20
# min (INTERVAL_MS). A gap > ~30 min means the engine stalled (Doze, a11y
# block, crash) — the layer we can't see from the repair log alone.
wlast=$(grep -h "\[watchdog\]" "$SD/logs/watchdog.log" /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1 | cut -d" " -f1,2)
if [ -n "$wlast" ]; then
    wage=$(( $(date +%s) - $(date -d "$wlast" +%s 2>/dev/null || echo 0) ))
    [ "$wage" -ge 0 ] && [ "$wage" -lt 1800 ] && echo "watchdog=fresh" || echo "watchdog=stale:${wage}s"
else
    echo "watchdog=missing"
fi
batt=$(termux-battery-status 2>/dev/null | grep -o '"percentage": *[0-9]*' | grep -o '[0-9]*' || true)
[ -n "$batt" ] && echo "battery=${batt}" || echo "battery=unknown"
if [ "$FIRE" = 1 ]; then
    echo "taskerlegacy=notif:0,files:0"
else
    tn=$(adb -s localhost:5555 shell "dumpsys notification --noredact" </dev/null 2>/dev/null \
        | grep -cE 'pkg=net\.dinglisch\.android\.taskerm.*(Watchdog bridge|stayturgid)')
    tf=$(adb -s localhost:5555 shell "grep -rl -iE 'ADB_Core_Watchdog|ADB_Interval_Check|Watchdog bridge' /sdcard/Tasker/projects /sdcard/Tasker/tasks /sdcard/Tasker/profiles /sdcard/Tasker/Updates 2>/dev/null" </dev/null 2>/dev/null | grep -cv "/configs/")
    echo "taskerlegacy=notif:${tn:-0},files:${tf:-0}"
fi
grep -qF 'packages-cf.termux.dev' "$PREFIX/etc/apt/sources.list" 2>/dev/null \
    && echo "mirror=pinned" || echo "mirror=UNPINNED"
grep -q '^PerSourcePenalties no' "$PREFIX/etc/ssh/sshd_config" 2>/dev/null \
    && echo "penalties=off" || echo "penalties=ON"
case "$SD" in
  *termux/files/home*)
    cmd appops get com.termux.api WRITE_SETTINGS </dev/null 2>/dev/null \
      | tr -d '\r' | grep -q allow && echo "writesettings=allow" || echo "writesettings=MISSING"
    ;;
  *)
    adb -s localhost:5555 shell cmd appops get com.termux.api WRITE_SETTINGS </dev/null 2>/dev/null \
      | tr -d '\r' | grep -q allow && echo "writesettings=allow" || echo "writesettings=MISSING"
    ;;
esac
_overlay_ok=true
for pkg in com.termux com.termux.api com.termux.window; do
  pm list packages --user 0 "$pkg" 2>/dev/null | grep -q "$pkg" || continue
  case "$SD" in
    *termux/files/home*)
      cmd appops get "$pkg" SYSTEM_ALERT_WINDOW </dev/null 2>/dev/null \
        | tr -d '\r' | grep -q allow || _overlay_ok=false
      ;;
    *)
      adb -s localhost:5555 shell cmd appops get "$pkg" SYSTEM_ALERT_WINDOW </dev/null 2>/dev/null \
        | tr -d '\r' | grep -q allow || _overlay_ok=false
      ;;
  esac
done
$_overlay_ok && echo overlay=allow || echo overlay=MISSING
if [ "$FIRE" = 1 ]; then
  echo "vpn_always_on=skip"
else
  adb connect localhost:5555 >/dev/null 2>&1 </dev/null
  vpn_pkg=$(adb -s localhost:5555 shell settings get secure always_on_vpn_app </dev/null 2>/dev/null | tr -d '\r')
  vpn_lock=$(adb -s localhost:5555 shell settings get secure always_on_vpn_lockdown </dev/null 2>/dev/null | tr -d '\r')
  if [ "$vpn_pkg" = "com.tailscale.ipn" ] && [ "$vpn_lock" = "0" ]; then
    echo "vpn_always_on=ok"
  else
    echo "vpn_always_on=MISSING"
  fi
fi
for f in stayturgid-repair.sh repair-bridge.sh agent-presence.sh claude-presence.sh stayturgid_check_repo_version.py stayturgid_screen_awake_guard.py stayturgid_agent_presence.py stayturgid_battery_alarm.py stayturgid_repair.py; do
    printf 'md5 %s %s\n' "$f" "$(md5sum "$HOME/.stayturgid/bin/$f" 2>/dev/null | cut -d' ' -f1)"
done
"""

SSH_BASE = ["ssh", "-o", "BatchMode=yes", "-o", "LogLevel=ERROR"]


# --------------------------------------------------------------------------
# Pure, unit-tested helpers
# --------------------------------------------------------------------------
def parse_report(text):
    """key=value lines -> dict. `md5 <name> <hash>` -> md5[name]."""
    kv, md5 = {}, {}
    for line in text.splitlines():
        if line.startswith("md5 "):
            parts = line.split()
            if len(parts) == 3:
                md5[parts[1]] = parts[2]
        elif "=" in line:
            k, v = line.split("=", 1)
            kv[k] = v
    kv["md5"] = md5
    return kv


def file_md5(path):
    """Cross-platform (hashlib, not md5/md5sum)."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return None


def load_hosts(conf_path):
    hosts = []
    try:
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    hosts.append(line.split()[0])
    except OSError:
        pass
    return hosts


def device_row(alias, conf_path):
    """alias -> (usb_serial, tailscale_ip, lan_ip) from devices.conf, or None."""
    try:
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts and parts[0] == alias:
                    return tuple((parts[1:] + ["-", "-", "-"])[:3])
    except OSError:
        pass
    return None


def evaluate(host, report, repo_dir=REPO):
    """Given a parsed report, return a list of TAP result dicts:
    {kind: ok|fail|todo, desc, detail}. Pure — no I/O, fully unit-testable."""
    r = []

    def ok(desc):
        r.append({"kind": "ok", "desc": desc, "detail": ""})

    def ok_note(desc, note):
        r.append({"kind": "ok", "desc": desc, "detail": "", "note": note})

    def fail(desc, detail=""):
        r.append({"kind": "fail", "desc": desc, "detail": detail})

    def todo(desc, detail=""):
        r.append({"kind": "todo", "desc": desc, "detail": detail})

    simple = {
        "sshd": ("sshd running", "ok"),
        "bootloop": ("Termux boot loop running", "ok"),
    }
    for key, (label, good) in simple.items():
        (ok if report.get(key) == good else fail)("%s: %s" % (host, label))

    if report.get("localhost_shell") == "skip":
        ok_note("%s: privileged shell on localhost:5555" % host,
                "Fire OS — Mac adb only; Termux loopback unsupported")
    else:
        (ok if report.get("shell5555") == "ok" else fail)(
            "%s: privileged shell on localhost:5555" % host)

    # bridge: TODO (not a hard fail — may lag a redeploy/reboot)
    if report.get("bridge") == "ok":
        ok("%s: repair bridge alive (pidfile)" % host)
    else:
        todo("%s: repair bridge alive (pidfile)" % host,
             "expected until post-fix redeploy + reboot")

    (ok if report.get("repairlog") == "fresh" else fail)(
        "%s: repair log fresh (<45 min)" % host)

    # AutoJs6 secondary watchdog liveness (writes every ~20 min).
    wd = report.get("watchdog", "")
    if report.get("localhost_shell") == "skip":
        if wd == "fresh":
            ok("%s: AutoJs6 watchdog alive (<30 min)" % host)
        else:
            todo("%s: AutoJs6 watchdog alive (<30 min)" % host,
                 "Fire OS — confirm via Mac adb when USB connected")
    elif wd == "fresh":
        ok("%s: AutoJs6 watchdog alive (<30 min)" % host)
    elif report.get("repairlog") == "fresh":
        todo("%s: AutoJs6 watchdog alive (<30 min)" % host,
             "%s — Termux repair OK; restart main.js via start_watchdog.py when convenient" % (wd or "stale"))
    else:
        fail("%s: AutoJs6 watchdog alive (<30 min)" % host,
             "%s — repair also stale; fix Termux boot loop first" % (wd or "no data"))

    batt = report.get("battery", "unknown")
    if batt not in ("unknown", ""):
        ok("%s: termux-api battery readable (%s%%)" % (host, batt))
    else:
        fail("%s: termux-api battery readable" % host, "termux-api unavailable")

    tasker = report.get("taskerlegacy", "")
    if tasker in ("notif:0,files:0", ""):
        ok("%s: no legacy Tasker stayturgid remnants" % host)
    else:
        fail("%s: no legacy Tasker stayturgid remnants" % host,
             "%s — swipe stale Tasker notifications / archive /sdcard/Tasker" % tasker)

    (ok if report.get("mirror") == "pinned" else fail)(
        "%s: Termux mirror pinned (deterministic pkg update)" % host)
    (ok if report.get("penalties") == "off" else fail)(
        "%s: sshd per-source penalties disabled" % host)
    if report.get("localhost_shell") == "skip":
        if report.get("writesettings") == "allow":
            ok("%s: Termux:API WRITE_SETTINGS granted (battery flash)" % host)
        else:
            todo("%s: Termux:API WRITE_SETTINGS granted (battery flash)" % host,
                 "Fire OS — confirm via Mac adb when USB connected")
    else:
        (ok if report.get("writesettings") == "allow" else fail)(
            "%s: Termux:API WRITE_SETTINGS granted (battery flash)" % host)

    if report.get("localhost_shell") == "skip":
        if report.get("overlay") == "allow":
            ok("%s: Termux overlay (SYSTEM_ALERT_WINDOW) granted" % host)
        else:
            todo("%s: Termux overlay (SYSTEM_ALERT_WINDOW) granted" % host,
                 "Fire OS — confirm via Mac adb when USB connected")
    else:
        (ok if report.get("overlay") == "allow" else fail)(
            "%s: Termux overlay (SYSTEM_ALERT_WINDOW) granted" % host)

    if report.get("localhost_shell") == "skip":
        if report.get("vpn_always_on") == "ok":
            ok("%s: Tailscale always-on VPN enabled" % host)
        else:
            todo("%s: Tailscale always-on VPN enabled" % host,
                 "Fire OS — confirm via Mac adb when USB/Tailscale connected")
    else:
        (ok if report.get("vpn_always_on") == "ok" else fail)(
            "%s: Tailscale always-on VPN enabled" % host)

    # Deployment drift (informational TODO, not a failure)
    md5s = report.get("md5", {})
    drift = []
    for name, repo_path in TRACKED_SCRIPTS.items():
        local = file_md5(os.path.join(repo_dir, repo_path))
        if md5s.get(name) != local:
            drift.append(name)
    if not drift:
        ok("%s: deployed termux scripts match repo" % host)
    else:
        todo("%s: deployed termux scripts match repo" % host,
             "drift: %s (run ./mac/deploy_fleet.py)" % " ".join(drift))
    return r


def parse_heal(heal_out):
    """Last STATUS line -> TAP result dict."""
    if heal_out.startswith("STATUS") and "port=open" in heal_out:
        return {"kind": "ok", "desc": "self-heal ran clean", "note": heal_out}
    if heal_out.startswith("STATUS"):
        return {"kind": "fail", "desc": "self-heal ran clean", "detail": heal_out}
    return {"kind": "fail", "desc": "self-heal ran clean",
            "detail": "no STATUS line (%s)" % (heal_out or "empty")}


# --------------------------------------------------------------------------
# I/O layer
# --------------------------------------------------------------------------
def ssh_gather(host, script, timeout=60):
    try:
        p = subprocess.run(
            SSH_BASE + ["-o", "ConnectTimeout=10", host, "bash", "-s"],
            input=script, capture_output=True, text=True, timeout=timeout,
        )
        return p.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


def run_adb(args, timeout=15):
    try:
        return subprocess.run(["adb"] + args, capture_output=True, text=True,
                              timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None


class Tap:
    def __init__(self):
        self.n = 0
        self.failed = 0

    def emit(self, res):
        self.n += 1
        kind = res["kind"]
        if kind == "ok":
            print("ok %d - %s" % (self.n, res["desc"]))
        elif kind == "todo":
            print("not ok %d - %s # TODO %s" % (self.n, res["desc"], res.get("detail", "")))
        elif kind == "skip":
            print("ok %d - %s # SKIP %s" % (self.n, res["desc"], res.get("detail", "")))
        else:
            self.failed += 1
            print("not ok %d - %s" % (self.n, res["desc"]))
            if res.get("detail"):
                print("# " + res["detail"])
        if res.get("note"):
            print("# " + res["note"])

    def done(self):
        print("1..%d" % self.n)
        return self.failed == 0


def writesettings_via_adb(serial):
    """Mac-side WRITE_SETTINGS check (Fire: Termux cannot query appops)."""
    p = run_adb(["-s", serial, "shell",
                 "cmd appops get com.termux.api WRITE_SETTINGS </dev/null 2>/dev/null"])
    return bool(p and p.returncode == 0 and "allow" in p.stdout)


OVERLAY_PACKAGES = ("com.termux", "com.termux.api", "com.termux.window")


def overlay_via_adb(serial):
    """Mac-side overlay check for installed Termux family apps."""
    for pkg in OVERLAY_PACKAGES:
        lp = run_adb(["-s", serial, "shell", "pm", "list", "packages", "--user", "0", pkg])
        if not lp or pkg not in lp.stdout:
            continue
        p = run_adb(["-s", serial, "shell",
                     "cmd appops get %s SYSTEM_ALERT_WINDOW </dev/null 2>/dev/null" % pkg])
        if not p or "allow" not in p.stdout:
            return False
    return True


def vpn_always_on_via_adb(serial, pkg="com.tailscale.ipn", lockdown="0"):
    """Mac-side always-on VPN check (Fire: Termux cannot query via loopback adb)."""
    p = run_adb(["-s", serial, "shell",
                 "settings get secure always_on_vpn_app </dev/null 2>/dev/null"])
    p2 = run_adb(["-s", serial, "shell",
                  "settings get secure always_on_vpn_lockdown </dev/null 2>/dev/null"])
    if not p or not p2:
        return False
    app = p.stdout.strip().splitlines()[-1].strip()
    lock = p2.stdout.strip().splitlines()[-1].strip()
    return app == pkg and lock == lockdown


def watchdog_fresh_via_adb(serial, max_age_s=1800):
    """Mac-side [watchdog] liveness (Fire OS: Termux cannot read /sdcard logs)."""
    p = run_adb(["-s", serial, "shell",
                 "grep '\\[watchdog\\]' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1"])
    if not p or p.returncode != 0 or not p.stdout.strip():
        return False
    line = p.stdout.strip().splitlines()[-1]
    parts = line.split()
    if len(parts) < 2:
        return False
    try:
        ts = datetime.strptime("%s %s" % (parts[0], parts[1]), "%Y-%m-%d %H:%M:%S")
        age = (datetime.now() - ts).total_seconds()
        return 0 <= age < max_age_s
    except ValueError:
        return False


def check_host(host, tap, heal=False, ansible_check=False):
    report_text = ssh_gather(host, REMOTE_GATHER)
    report = parse_report(report_text)
    if report.get("ssh") != "ok":
        tap.emit({"kind": "fail", "desc": "%s: SSH reachable" % host})
        return
    tap.emit({"kind": "ok", "desc": "%s: SSH reachable" % host})

    # Fire OS: Termux cannot read /sdcard; confirm watchdog via Mac adb when USB is up.
    row = device_row(host, DEVICES_CONF)
    serial = ""
    if row:
        usb, ts, _lan = row
        adb = run_adb(["devices"])
        connected = bool(adb and ("%s\tdevice" % usb) in adb.stdout) if usb != "-" else False
        serial = usb if connected else "%s:5555" % ts
        if ":" in serial:
            run_adb(["connect", serial])
    if report.get("localhost_shell") == "skip" and serial:
        if run_adb(["-s", serial, "shell", "true"]) and \
                run_adb(["-s", serial, "shell", "true"]).returncode == 0:
            if watchdog_fresh_via_adb(serial):
                report["watchdog"] = "fresh"
            if writesettings_via_adb(serial):
                report["writesettings"] = "allow"
            if overlay_via_adb(serial):
                report["overlay"] = "allow"
            if vpn_always_on_via_adb(serial):
                report["vpn_always_on"] = "ok"

    for res in evaluate(host, report):
        tap.emit(res)

    # Mac->device adb path (the Mac's own route, distinct from on-device 5555)
    if serial and run_adb(["-s", serial, "shell", "true"]) and \
            run_adb(["-s", serial, "shell", "true"]).returncode == 0:
        tap.emit({"kind": "ok", "desc": "%s: Mac adb path reachable (%s)" % (host, serial)})
    else:
        tap.emit({"kind": "fail", "desc": "%s: Mac adb path reachable" % host,
                  "detail": "serial=%s" % serial})

    if heal:
        out = ssh_gather(host, '"$HOME/.stayturgid/bin/stayturgid-repair.sh"\n', timeout=30)
        last = out.strip().splitlines()[-1] if out.strip() else ""
        tap.emit(parse_heal(last))

    if ansible_check:
        env = dict(os.environ, ANSIBLE_CONFIG="ansible/ansible.cfg")
        try:
            rc = subprocess.run(
                ["ansible-playbook", "ansible/playbooks/fleet.yml",
                 "--check", "--diff", "--limit", host],
                cwd=REPO, env=env, capture_output=True, text=True, timeout=600,
            ).returncode
            tap.emit({"kind": "ok" if rc == 0 else "fail",
                      "desc": "%s: ansible --check dry run clean" % host,
                      "detail": "re-run manually for the diff"})
        except FileNotFoundError:
            tap.emit({"kind": "skip", "desc": "%s: ansible --check dry run" % host,
                      "detail": "ansible not installed"})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ansible-check", action="store_true")
    ap.add_argument("--heal", action="store_true")
    ap.add_argument("hosts", nargs="*")
    args = ap.parse_args(argv)

    hosts = args.hosts or load_hosts(DEVICES_CONF)
    if not hosts:
        sys.stderr.write(
            "no hosts: pass host args or run ansible/playbooks/mac.yml "
            "to generate devices.conf\n")
        return 2

    tap = Tap()
    for host in hosts:
        check_host(host, tap, heal=args.heal, ansible_check=args.ansible_check)
    return 0 if tap.done() else 1


if __name__ == "__main__":
    sys.exit(main())
