#!/data/data/com.termux/files/usr/bin/python
"""agent-presence (Python) — deployed as ~/stayturgid_agent_presence.py,
reached via the ~/stayturgid_agent_presence.py compat shim.

On-device "an agent is controlling this phone" indicator + consent gate +
screen-control sharing flow. Behavioral parity with the shell version is
unit-tested via tests/test-unit.sh (presence_suite). The ~/stayturgid_agent_presence.py
shim keeps the documented external interface stable.

Exit codes: 0 = proceed, 2 = usage, 75 = gate deferred/disallowed.
"""
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time

os.environ["PATH"] = "/data/data/com.termux/files/usr/bin:" + os.environ.get("PATH", "")
os.environ["LC_ALL"] = "C"

HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
_ENV_FILE = os.path.join(HOME, ".stayturgid", "env")
if os.path.isfile(_ENV_FILE):
    try:
        with open(_ENV_FILE) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line.startswith("export STAYTURGID_SD="):
                    os.environ["STAYTURGID_SD"] = _line.split("=", 1)[1].strip().strip('"')
                elif _line.startswith("export STAYTURGID_NO_LOCAL_ADB="):
                    os.environ["STAYTURGID_NO_LOCAL_ADB"] = (
                        _line.split("=", 1)[1].strip().strip('"')
                    )
    except OSError:
        pass

# Prefer ~/.stayturgid/lib (deployed) then repo control/lib (dev / unit tests).
import stayturgid_shell as sh  # noqa: E402

sh.ensure_lib_path()
try:
    import termux_api as tapi  # noqa: E402
except ImportError:
    tapi = None  # type: ignore

NID = "stayturgid-presence"
# Shared-storage root; self-healing (writers mkdir -p first).
SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")
STATE = os.path.join(SD, "state")
PAUSE_FILE = os.path.join(STATE, "presence_paused")
LATER_FILE = os.path.join(STATE, "presence_check_after")
STOP_FILE = os.path.join(STATE, "stop_requested")
LEASE_FILE = os.path.join(STATE, "screen_control_lease.json")
LEASE_TTL_SEC = 1800
REQUEST_SCREEN_COUNTDOWN_SEC = 10
# Fire: termux-notification* often hangs past soft timeouts and orphans children.
FIRE_NOTIFY_TIMEOUT_SEC = 3

IDLE_PKGS = {
    "", "com.sec.android.app.launcher", "com.google.android.apps.nexuslauncher",
    "com.android.launcher3", "com.android.systemui",
    "com.samsung.android.app.aodservice", "com.termux", "com.tailscale.ipn",
    "moe.shizuku.privileged.api", "org.autojs.autojs6",
}
PKG_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$")


def _no_local_adb():
    return os.environ.get("STAYTURGID_NO_LOCAL_ADB") == "1"


def run(args, timeout=15):
    """Run a command. Termux:API clients are never SIGKILL'd (ResultReturner)."""
    if tapi is not None and tapi.is_termux_api(args):
        if tapi.is_fire_and_forget(args):
            return tapi.run_ff(args, timeout=min(float(timeout), 4.0))
        return tapi.run(args, timeout=timeout)
    # Non-API (adb, timeout+dialog): may still killpg — those are not ResultReturner.
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as e:
        pid = getattr(e, "pid", None)
        if pid and not str(args[0]).startswith("termux-"):
            try:
                os.killpg(pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        return None
    except OSError:
        return None


def _notify_timeout():
    return FIRE_NOTIFY_TIMEOUT_SEC if _no_local_adb() else 4


def adb_shell(*cmd):
    """Privileged shell via Termux localhost:5555. No-op on Fire (no loopback)."""
    # Fire OS / hosts without Termux→5555: skip rather than hang on connect.
    if os.environ.get("STAYTURGID_NO_LOCAL_ADB") == "1":
        return ""
    if run(["adb", "connect", "localhost:5555"], timeout=5) is None:
        return ""
    r = run(["adb", "-s", "localhost:5555", "shell"] + list(cmd), timeout=15)
    return (r.stdout if r else "").replace("\r", "")


def invert(state):  # state = "1" | "0"
    adb_shell("settings put secure accessibility_display_inversion_enabled %s" % state)
    got = adb_shell("settings get secure accessibility_display_inversion_enabled").strip()
    return got == state


def inversion_enabled():
    return adb_shell("settings get secure accessibility_display_inversion_enabled").strip() == "1"


def read_lease():
    try:
        with open(LEASE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_lease(label, agent):
    """Write on-device lease mirror (DSCL v1 + legacy fields).

    Mac-side interop uses ~/.local/state/device-screen-control/leases/ — this
    file is the on-phone signal (inversion guard + status).
    """
    now = int(time.time())
    project = (
        os.environ.get("DEVICE_SCREEN_CONTROL_PROJECT")
        or os.environ.get("STAYTURGID_SCREEN_PROJECT")
        or "stayturgid"
    )
    write(LEASE_FILE, json.dumps({
        "schema": "device-screen-control-lease/v1",
        "label": label,
        "agent": agent,
        "project": project,
        "holder": {
            "project": project,
            "agent": agent,
        },
        "started": now,
        "expires": now + LEASE_TTL_SEC,
        "started_at": datetime.datetime.utcfromtimestamp(now).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "expires_at": datetime.datetime.utcfromtimestamp(
            now + LEASE_TTL_SEC
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ttl_sec": LEASE_TTL_SEC,
    }) + "\n")


def lease_active():
    lease = read_lease()
    if not lease:
        return False
    try:
        return int(lease.get("expires", 0)) > int(time.time())
    except (TypeError, ValueError):
        return False


def clear_lease():
    rm(LEASE_FILE)


def _quiet_presence() -> bool:
    """STAYTURGID_PRESENCE_QUIET=1 — no torch, vibrate, or toast (scheduled audits)."""
    return os.environ.get("STAYTURGID_PRESENCE_QUIET") == "1"


def pulse(n):
    # Fire OS: termux-torch often hangs past subprocess timeouts and blows the
    # Mac SSH presence budget (~30s). Skip torch; Mac already sets inversion.
    if _no_local_adb() or _quiet_presence():
        return
    if tapi is not None:
        tapi.pulse_torch(n, on_s=0.25, off_s=0.20, torch_timeout=2.0)
        return
    for _ in range(n):
        run(["termux-torch", "on"], timeout=3)
        time.sleep(0.25)
        run(["termux-torch", "off"], timeout=3)
        time.sleep(0.20)


def _vibrate(ms: int) -> None:
    if _quiet_presence():
        return
    if tapi is not None:
        tapi.vibrate(ms)
        return
    run(["termux-vibrate", "-d", str(ms)], timeout=3)


def foreground_pkg():
    for line in adb_shell("dumpsys", "window").splitlines():
        if "mCurrentFocus" in line:
            for field in re.split(r"[ /}]", line):
                if PKG_RE.match(field):
                    return field
    return ""


def screen_interactive():
    out = adb_shell("dumpsys", "power")
    return "mWakefulness=Awake" in out or "mIsInteractive: true" in out


def idle_foreground(pkg):
    return pkg in IDLE_PKGS


def pause_active():
    return os.path.exists(PAUSE_FILE)


def later_active():
    try:
        with open(LATER_FILE) as f:
            until = int(f.read().strip() or 0)
    except (OSError, ValueError):
        return False
    return until > int(time.time())


def dialog_choice(args):
    """Run termux-dialog and extract chosen text (4th "…" field).

    Never SIGKILL the dialog client — that triggers ResultReturner toasts.
    Soft-timeout orphans the process; treat as empty choice (caller decides).
    """
    # args[0] is countdown seconds when using the legacy [sec, termux-dialog, …]
    # form; otherwise the whole list is the dialog argv.
    if args and str(args[0]).isdigit() and len(args) > 1 and "termux-dialog" in str(args[1]):
        limit = int(args[0]) + 2
        cmd = list(args[1:])
    else:
        limit = 35
        cmd = list(args)
    if tapi is not None:
        r = tapi.run(cmd, timeout=limit)
    else:
        r = run(cmd, timeout=limit)
    out = r.stdout if r else ""
    for line in out.splitlines():
        if "text" in line:
            parts = line.split('"')
            if len(parts) > 3:
                return parts[3]
    return ""


def rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def consent_gate(label, agent):
    if pause_active():
        print("presence gate: paused (run stayturgid_agent_presence.py resume to clear)")
        return 75
    if later_active():
        with open(LATER_FILE) as f:
            print("presence gate: check later active until %s" % f.read().strip())
        return 75

    pkg = foreground_pkg()
    if not screen_interactive() or idle_foreground(pkg):
        print("presence gate: proceed (screen idle; foreground=%s)" % (pkg or "unknown"))
        return 0

    _vibrate(200)
    choice = dialog_choice(["30", "termux-dialog", "radio",
                            "-t", "%s wants to use %s" % (agent, label),
                            "-v", "Continue,Pause,Check again in 10 minutes"])
    if choice == "Continue":
        rm(LATER_FILE)
        print("presence gate: continue")
        return 0
    if choice == "Pause":
        write(PAUSE_FILE, str(int(time.time())))
        run(["termux-notification", "--id", NID, "--priority", "high", "--alert-once",
             "--title", "%s paused on %s" % (agent, label),
             "--content", "Run stayturgid_agent_presence.py resume to clear."])
        print("presence gate: pause")
        return 75
    # "Check again in 10 minutes", timeout, or unrecognized: fail closed.
    write(LATER_FILE, str(int(time.time()) + 600))
    print("presence gate: later (choice=%s)" % (choice or "timeout"))
    return 75


def request_screen(label, agent):
    """Countdown consent for screen control.

    Deliberately different from consent_gate: timeout proceeds (silence during
    the countdown = allow). Press No to disallow (75). gate() fails closed on
    timeout because it only appears when the phone is actively in use.
    """
    if pause_active():
        print("request-screen: paused (run stayturgid_agent_presence.py resume to clear)")
        return 75
    # Quiet / overnight audits: no vibrate, no dialog — proceed (inversion still on).
    if _quiet_presence():
        rm(STOP_FILE)
        print("request-screen: allowed (quiet mode)")
        return 0
    _vibrate(300)
    choice = dialog_choice([str(REQUEST_SCREEN_COUNTDOWN_SEC), "termux-dialog", "confirm",
                            "-t", "%s wants to CONTROL THE SCREEN of %s" % (agent, label),
                            "-i", "Starting in %d seconds. Press No to disallow, Yes to start now."
                            % REQUEST_SCREEN_COUNTDOWN_SEC])
    if choice.lower() == "no":
        print("request-screen: DISALLOWED by user")
        return 75
    rm(STOP_FILE)
    print("request-screen: allowed (answer or %ds timeout)" % REQUEST_SCREEN_COUNTDOWN_SEC)
    return 0


def _notify_presence(title, content, button1=None, button1_action=None):
    """Post ongoing presence notification; short wait, never SIGKILL."""
    args = [
        "termux-notification", "--id", NID, "--ongoing", "--alert-once",
        "--priority", "high", "--icon", "developer_board",
        "--title", title, "--content", content,
    ]
    if button1 and button1_action:
        args.extend(["--button1", button1, "--button1-action", button1_action])
    run(args, timeout=_notify_timeout())


def action_on(label, agent):
    rm(LATER_FILE); rm(STOP_FILE)
    write_lease(label, agent)
    if not invert("1"):
        sys.stderr.write("WARN: could not confirm display inversion (localhost:5555 shell?)\n")
    _vibrate(400)
    pulse(3)
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if _quiet_presence():
        print("presence ON quiet (%s)" % label)
        return 0
    btn = ("mkdir -p %s 2>/dev/null; touch %s; "
           "termux-toast 'Stop requested — agent wrapping up (~1 min)'" % (STATE, STOP_FILE))
    _notify_presence(
        "🤖 %s is using %s" % (agent, label),
        "Automation in progress — started %s. Graceful stop gives "
        "the agent ~1 min to wrap up." % now,
        button1="Graceful stop",
        button1_action=btn,
    )
    print("presence ON (%s)" % label)
    return 0


def action_off(label, agent):
    stopped = os.path.exists(STOP_FILE)
    clear_lease()
    if not invert("0"):
        sys.stderr.write("WARN: could not confirm inversion off\n")
    run(["termux-notification-remove", NID], timeout=_notify_timeout())
    run(["termux-notification-remove", "claude-presence"], timeout=_notify_timeout())  # legacy id
    pulse(2)
    _vibrate(250)
    rm(STOP_FILE)
    if stopped and not _no_local_adb() and not _quiet_presence():
        # Modal handoff-back dialog, detached so `off` returns immediately.
        # Skip on Fire — termux-dialog hangs there.
        try:
            subprocess.Popen(
                ["termux-dialog", "confirm",
                 "-t", "%s has released %s" % (agent, label),
                 "-i", "Screen control ended after your stop request. "
                       "The phone is all yours."],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
        except OSError:
            pass
        print("presence OFF (%s) — graceful stop honored" % label)
    elif stopped:
        print("presence OFF (%s) — graceful stop honored" % label)
    else:
        print("presence OFF (%s)" % label)
    return 0


def action_guard():
    """Boot-loop hook: keep inversion on while lease active; expire stale sessions."""
    if not lease_active():
        if inversion_enabled():
            invert("0")
            run(["termux-notification-remove", NID])
            run(["termux-notification-remove", "claude-presence"])
        clear_lease()
        return 0
    lease = read_lease() or {}
    if not inversion_enabled():
        if not invert("1"):
            sys.stderr.write("WARN: guard could not re-enable inversion\n")
    label = lease.get("label", "this phone")
    agent = lease.get("agent", "Auto")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if not _quiet_presence():
        btn = ("mkdir -p %s 2>/dev/null; touch %s; "
               "termux-toast 'Stop requested — agent wrapping up (~1 min)'" % (STATE, STOP_FILE))
        _notify_presence(
            "🤖 %s is using %s" % (agent, label),
            "Automation in progress — guarded %s. Graceful stop gives "
            "the agent ~1 min to wrap up." % now,
            button1="Graceful stop",
            button1_action=btn,
        )
    # Extend lease while automation is still marked active.
    write_lease(label, agent)
    return 0


def action_status():
    lease = read_lease()
    print("lease_active=%s inversion=%s" % (lease_active(), inversion_enabled()))
    if lease:
        print("lease=%s" % json.dumps(lease, sort_keys=True))
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    action = argv[0] if argv else ""
    label = argv[1] if len(argv) > 1 else "this phone"
    agent = argv[2] if len(argv) > 2 else os.environ.get("STAYTURGID_AGENT", "Auto")

    if action == "gate":
        return consent_gate(label, agent)
    if action == "request-screen":
        return request_screen(label, agent)
    if action == "stop-requested":
        if os.path.exists(STOP_FILE):
            print("graceful stop requested — wrap up within ~1 minute, then run: "
                  "stayturgid_agent_presence.py off")
            return 0
        print("no stop requested")
        return 1
    if action == "on":
        return action_on(label, agent)
    if action == "off":
        return action_off(label, agent)
    if action == "guard":
        return action_guard()
    if action == "status":
        return action_status()
    if action in ("resume", "clear-pause"):
        rm(PAUSE_FILE); rm(LATER_FILE)
        print("presence gate: pause cleared")
        return 0
    sys.stderr.write("usage: stayturgid_agent_presence.py on|off|gate|request-screen|"
                     "stop-requested|guard|status [label] [agent] | resume\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
