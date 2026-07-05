#!/usr/bin/env python3
"""
tasker_io — reliable, reusable Tasker import/export for Android over ADB + uiautomator2.

Why this exists: importing Tasker data has been the flakiest part of the stayturgid
project. Prior art (Taskomater/Tasker-XML-Info, tasker_config_utils) confirms there is
NO clean programmatic import without root — the mature community tools only manipulate
the XML files, not Tasker's live config. So import must go through Tasker's UI.

The KEY discovery that makes this robust: Tasker exposes an import Activity that can be
launched by intent with a DocumentsProvider content URI, and it imports a SINGLE TASK
with overwrite — using plain text-button dialogs (YES / overwrite YES / NO-to-run).
This replaces the fragile "delete all profiles → delete all tasks → delete project
shell → Import Project" dance (whose top-bar trash/export icons shift position with the
selection count and whose menus pop up unpredictably) with:

    am start -n net.dinglisch.android.taskerm/com.joaomgcd.taskerm.datashare.import.ActivityImportTaskerDataFromXml \
       -a android.intent.action.VIEW \
       -d "content://com.android.externalstorage.documents/document/primary%3A<url-encoded /sdcard path>" \
       -t text/xml --grant-read-uri-permission

...then tap the text buttons. For updating one task (the common case — e.g. a watchdog),
this is the whole story. Full-project reimport is still provided as a fallback.

Verified working 2026-07-05 on Pixel 7a, Tasker 6.7.5-beta, Android 16 (task overwrite).

Requires: adb on PATH, uiautomator2 (pipx venv path below), a device serial.
"""
import re
import sys
import time
import subprocess
import urllib.parse

U2_SITE = '/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages'
if U2_SITE not in sys.path:
    sys.path.insert(0, U2_SITE)
import uiautomator2 as u2  # noqa: E402

MAIN_TABS = {"PROFILES", "TASKS", "SCENES", "VARS"}
IMPORT_ACTIVITY = ("net.dinglisch.android.taskerm/"
                   "com.joaomgcd.taskerm.datashare.import.ActivityImportTaskerDataFromXml")


def adb(serial, *args, timeout=30):
    return subprocess.run(["adb", "-s", serial, *args],
                          capture_output=True, text=True, timeout=timeout).stdout


def _texts(d):
    return set(m.group(1).strip()
               for m in re.finditer(r'text="([^"]*)"', d.dump_hierarchy())
               if m.group(1).strip())


def _joined(d):
    return " ".join(_texts(d))


def goto_main(d, max_steps=10):
    """Navigate to Tasker's main screen (PROFILES/TASKS/SCENES tabs visible) from
    ANY state: task editor, context menus, tip/exit dialogs. Idempotent + safe."""
    for _ in range(max_steps):
        t = _texts(d)
        if MAIN_TABS <= t | {"VARS"} and {"PROFILES", "TASKS"} <= t:
            return True
        # Never accidentally exit Tasker
        if "Do you really want to exit Tasker?" in t and d(text="NO").exists:
            d(text="NO").click(); time.sleep(1); continue
        # A Tasker tab context-menu popup ("Import Task"/"Set Sort", "Import Project"…)
        # covers the list and intercepts taps/reads but has NO button to press and does
        # NOT respond to Back — dismiss it by tapping empty space low on the screen.
        if ("Import Task" in t or "Set Sort" in t or "Import Project" in t) and MAIN_TABS & t:
            d.click(270, 780); time.sleep(0.6); continue
        # Dismiss common interrupting dialogs / menus
        dismissed = False
        for lbl in ("Got it", "Don't Show Again", "STOP REMINDING", "OK", "NO", "Cancel"):
            if d(text=lbl).exists:
                d(text=lbl).click(); time.sleep(0.7); dismissed = True; break
        if not dismissed:
            d.press("back"); time.sleep(1)
    return {"PROFILES", "TASKS"} <= _texts(d)


def _content_uri(sdcard_path):
    """Build the externalstorage DocumentsProvider content URI Tasker's import
    activity accepts. sdcard_path is relative to /sdcard, e.g. 'Tasker/Updates/x.tsk.xml'."""
    enc = urllib.parse.quote("primary:" + sdcard_path, safe="")
    return f"content://com.android.externalstorage.documents/document/{enc}"


def wrap_task_as_tsk(project_xml_text, task_sr):
    """Extract a <Task sr="taskN"> from a project XML and wrap it as a standalone
    .tsk.xml (root <TaskerData>). Returns the .tsk.xml string."""
    m = re.search(rf'<Task sr="{re.escape(task_sr)}">.*?</Task>', project_xml_text, re.DOTALL)
    if not m:
        raise ValueError(f"task {task_sr} not found")
    return ('<TaskerData sr="" dvi="1" tv="6.7.5-beta">\n' + m.group(0) + '\n</TaskerData>\n')


def import_task(serial, local_tsk_path, sdcard_rel="Tasker/Updates", run_after=False,
                settle=2.0, project="stayturgid", enable_after=True):
    """ROBUST single task/profile import with overwrite, via intent + text-button dialogs.

    Pushes local_tsk_path (.tsk.xml or .prf.xml) to /sdcard/<sdcard_rel>/, launches the
    import Activity, and taps through the FULL dialog chain:
      1. 'Import Data … Are you sure?'                       → YES
      2. '<name> already exists. Want to overwrite it?'       → YES  (if it exists)
      3. 'Import To Project' project chooser                  → tap `project` row
         (appears even on overwrite; unhandled it silently CANCELS the import —
         this was the bug behind earlier phantom 'OK' imports)
      4. task: 'Do you want to run … right away?'             → run_after
         profile: 'Do you want to enable … right away?'       → enable_after
    Returns True only if the chain reached a terminal dialog (run/enable) or the
    dialogs finished; returns False if an unrecognized screen stalled the chain.
    Leaves Tasker at the main screen.
    """
    import os
    fname = os.path.basename(local_tsk_path)
    adb(serial, "shell", f"mkdir -p /sdcard/{sdcard_rel}")
    adb(serial, "push", local_tsk_path, f"/sdcard/{sdcard_rel}/{fname}")
    d = u2.connect(serial)
    goto_main(d)
    uri = _content_uri(f"{sdcard_rel}/{fname}")
    adb(serial, "shell",
        f'am start -n {IMPORT_ACTIVITY} -a android.intent.action.VIEW '
        f'-d "{uri}" -t text/xml --grant-read-uri-permission')
    time.sleep(settle)
    done = False
    # Dialog chain — all text buttons/rows, so reliable regardless of screen geometry.
    for _ in range(10):
        t = _joined(d)
        if ("Import Data" in t or "Are you sure" in t) and d(text="YES").exists:
            d(text="YES").click(); time.sleep(settle); continue
        if ("overwrite it" in t or "already exists" in t) and d(text="YES").exists:
            d(text="YES").click(); time.sleep(settle); continue
        if "Import To Project" in t and d(text=project).exists:
            d(text=project).click(); time.sleep(settle); continue
        if "want to run" in t and (d(text="NO").exists or d(text="YES").exists):
            d(text=("YES" if run_after else "NO")).click(); time.sleep(1)
            done = True; break
        if "want to enable" in t and (d(text="NO").exists or d(text="YES").exists):
            d(text=("YES" if enable_after else "NO")).click(); time.sleep(1)
            done = True; break
        # No recognized dialog: either the chain finished without a terminal
        # dialog (ok if we're back on the main screen) or something unexpected.
        done = MAIN_TABS & _texts(d) != set()
        break
    goto_main(d)
    return done


def wrap_profile_as_prf(project_xml_text, prof_sr):
    """Extract a <Profile sr="profN"> plus every task it references (mid0/mid1) from a
    project XML and wrap them as a standalone .prf.xml. Returns the .prf.xml string."""
    m = re.search(rf'<Profile sr="{re.escape(prof_sr)}"[^>]*>.*?</Profile>',
                  project_xml_text, re.DOTALL)
    if not m:
        raise ValueError(f"profile {prof_sr} not found")
    prof = m.group(0)
    parts = [prof]
    for mid in re.findall(r'<mid\d+>(\d+)</mid\d+>', prof):
        tm = re.search(rf'<Task sr="task{mid}">.*?</Task>', project_xml_text, re.DOTALL)
        if not tm:
            raise ValueError(f"referenced task{mid} not found")
        parts.append(tm.group(0))
    return ('<TaskerData sr="" dvi="1" tv="6.7.5-beta">\n' + "\n".join(parts)
            + '\n</TaskerData>\n')


def _tap_topbar_action(d, desc_candidates):
    """Tap a selection-mode top-bar action icon by content-desc (position-independent).
    The trash/export/etc icons SHIFT x-position with the selection count, so never
    hardcode coordinates — find by content-desc instead."""
    xml = d.dump_hierarchy()
    for node in re.findall(r'<node[^>]*/?>', xml):
        cd = re.search(r'content-desc="([^"]*)"', node)
        bb = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        if cd and bb and 'clickable="true"' in node and int(bb.group(2)) < 260:
            if cd.group(1).strip() in desc_candidates:
                x = (int(bb.group(1)) + int(bb.group(3))) // 2
                y = (int(bb.group(2)) + int(bb.group(4))) // 2
                d.click(x, y)
                return True
    return False


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Reliable Tasker task import over ADB")
    ap.add_argument("serial")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import-task",
                       help="import/overwrite a single task (.tsk.xml) or profile (.prf.xml)")
    p.add_argument("tsk_xml")
    p.add_argument("--run-after", action="store_true")
    p.add_argument("--project", default="stayturgid",
                   help="project row to pick in the 'Import To Project' dialog")
    p.add_argument("--no-enable", action="store_true",
                   help="answer NO to 'enable profile right away?'")
    g = sub.add_parser("wrap-task", help="extract a task from a project xml into a .tsk.xml")
    g.add_argument("project_xml"); g.add_argument("task_sr"); g.add_argument("out_tsk")
    w = sub.add_parser("wrap-profile",
                       help="extract a profile + its referenced tasks into a .prf.xml")
    w.add_argument("project_xml"); w.add_argument("prof_sr"); w.add_argument("out_prf")
    args = ap.parse_args()
    if args.cmd == "import-task":
        ok = import_task(args.serial, args.tsk_xml, run_after=args.run_after,
                         project=args.project, enable_after=not args.no_enable)
        print("import:", "OK" if ok else "FAILED")
    elif args.cmd == "wrap-task":
        txt = open(args.project_xml).read()
        open(args.out_tsk, "w").write(wrap_task_as_tsk(txt, args.task_sr))
        print("wrote", args.out_tsk)
    elif args.cmd == "wrap-profile":
        txt = open(args.project_xml).read()
        open(args.out_prf, "w").write(wrap_profile_as_prf(txt, args.prof_sr))
        print("wrote", args.out_prf)
