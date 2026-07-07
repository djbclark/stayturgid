#!/data/data/com.termux/files/usr/bin/python
"""agent-presence (Python) — deployed as ~/stayturgid_agent_presence.py,
reached via the ~/agent-presence.sh compat shim.

On-device "an agent is controlling this phone" indicator + consent gate +
screen-control sharing flow. Behavioral parity with the shell version is
unit-tested via tests/test-unit.sh (presence_suite). The ~/agent-presence.sh
shim keeps the documented external interface stable.

Exit codes: 0 = proceed, 2 = usage, 75 = gate deferred/disallowed.
"""
import datetime
import os
import re
import subprocess
import sys
import time

os.environ["PATH"] = "/data/data/com.termux/files/usr/bin:" + os.environ.get("PATH", "")
os.environ["LC_ALL"] = "C"

NID = "stayturgid-presence"
# Shared-storage root; self-healing (writers mkdir -p first).
SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")
STATE = os.path.join(SD, "state")
PAUSE_FILE = os.path.join(STATE, "presence_paused")
LATER_FILE = os.path.join(STATE, "presence_check_after")
STOP_FILE = os.path.join(STATE, "stop_requested")

IDLE_PKGS = {
    "", "com.sec.android.app.launcher", "com.google.android.apps.nexuslauncher",
    "com.android.launcher3", "com.android.systemui",
    "com.samsung.android.app.aodservice", "com.termux", "com.tailscale.ipn",
    "moe.shizuku.privileged.api", "org.autojs.autojs6",
}
PKG_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$")


def run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except OSError:
        return None


def adb_shell(*cmd):
    if run(["adb", "connect", "localhost:5555"]) is None:
        return ""
    r = run(["adb", "-s", "localhost:5555", "shell"] + list(cmd))
    return (r.stdout if r else "").replace("\r", "")


def invert(state):  # state = "1" | "0"
    adb_shell("settings put secure accessibility_display_inversion_enabled %s" % state)


def pulse(n):
    for _ in range(n):
        run(["termux-torch", "on"]); time.sleep(0.25)
        run(["termux-torch", "off"]); time.sleep(0.20)


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
    """Run termux-dialog (via `timeout`, matching the shell) and extract the
    chosen text — the 4th field when the JSON line is split on double-quotes,
    faithfully mirroring `awk -F '"' '/text/ {print $4}'`."""
    r = run(["timeout", str(args[0])] + args[1:])
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
        print("presence gate: paused (run agent-presence.sh resume to clear)")
        return 75
    if later_active():
        with open(LATER_FILE) as f:
            print("presence gate: check later active until %s" % f.read().strip())
        return 75

    pkg = foreground_pkg()
    if not screen_interactive() or idle_foreground(pkg):
        print("presence gate: proceed (screen idle; foreground=%s)" % (pkg or "unknown"))
        return 0

    run(["termux-vibrate", "-d", "200"])
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
             "--content", "Run agent-presence.sh resume to clear."])
        print("presence gate: pause")
        return 75
    # "Check again in 10 minutes", timeout, or unrecognized: fail closed.
    write(LATER_FILE, str(int(time.time()) + 600))
    print("presence gate: later (choice=%s)" % (choice or "timeout"))
    return 75


def request_screen(label, agent):
    if pause_active():
        print("request-screen: paused (run agent-presence.sh resume to clear)")
        return 75
    run(["termux-vibrate", "-d", "300"])
    choice = dialog_choice(["60", "termux-dialog", "confirm",
                            "-t", "%s wants to CONTROL THE SCREEN of %s" % (agent, label),
                            "-i", "Starting in 60 seconds. Press No to disallow, Yes to start now."])
    if choice.lower() == "no":
        print("request-screen: DISALLOWED by user")
        return 75
    rm(STOP_FILE)
    print("request-screen: allowed (answer or 60s timeout)")
    return 0


def action_on(label, agent):
    rm(LATER_FILE); rm(STOP_FILE)
    invert("1")
    run(["termux-vibrate", "-d", "400"])
    pulse(3)
    now = datetime.datetime.now().strftime("%H:%M:%S")
    btn = ("mkdir -p %s 2>/dev/null; touch %s; "
           "termux-toast 'Stop requested — agent wrapping up (~1 min)'" % (STATE, STOP_FILE))
    run(["termux-notification", "--id", NID, "--ongoing", "--alert-once",
         "--priority", "high", "--icon", "developer_board",
         "--title", "🤖 %s is using %s" % (agent, label),
         "--content", "Automation in progress — started %s. Graceful stop gives "
                      "the agent ~1 min to wrap up." % now,
         "--button1", "Graceful stop", "--button1-action", btn])
    print("presence ON (%s)" % label)
    return 0


def action_off(label, agent):
    stopped = os.path.exists(STOP_FILE)
    invert("0")
    run(["termux-notification-remove", NID])
    run(["termux-notification-remove", "claude-presence"])  # legacy id
    pulse(2)
    run(["termux-vibrate", "-d", "250"])
    rm(STOP_FILE)
    if stopped:
        # Modal handoff-back dialog, detached so `off` returns immediately.
        try:
            subprocess.Popen(
                ["termux-dialog", "confirm",
                 "-t", "%s has released %s" % (agent, label),
                 "-i", "Screen control ended after your stop request. "
                       "The phone is all yours."],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
        print("presence OFF (%s) — graceful stop honored" % label)
    else:
        print("presence OFF (%s)" % label)
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
                  "agent-presence.sh off")
            return 0
        print("no stop requested")
        return 1
    if action == "on":
        return action_on(label, agent)
    if action == "off":
        return action_off(label, agent)
    if action in ("resume", "clear-pause"):
        rm(PAUSE_FILE); rm(LATER_FILE)
        print("presence gate: pause cleared")
        return 0
    sys.stderr.write("usage: agent-presence.sh on|off|gate|request-screen|"
                     "stop-requested [label] [agent] | resume\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
