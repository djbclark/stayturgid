#!/usr/bin/env python3
"""Enable Obtainium's Shizuku/Dhizuku/Sui installer for quieter APK updates.

Python replacement for enable-shizuku-installer.sh:
  1. pm grant API_V23 to Obtainium
  2. add Obtainium's uid to shizuku.json (unit-tested patcher)
  3. toggle "Use Dhizuku, Shizuku or Sui to install" in the Obtainium UI
     (uiautomator-XML parsing is now a unit-tested function, not
     `tr '>' '\n' | grep | sed`)

Usage: ./enable_shizuku_installer.py <p7a|s24|serial>
Requires: unlocked screen, Shizuku running, privileged shell on localhost:5555.
"""
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "shared", "mac"))
import stayturgid_device as dev  # noqa: E402
import screen_control as sc  # noqa: E402

OBTAINIUM_PKG = "dev.imranr.obtainium"
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
SHIZUKU_JSON = "/data/local/tmp/shizuku/shizuku.json"
STAGING = "/sdcard/Download/shizuku-obtainium.json"
SWITCH_LABEL = "Use Dhizuku, Shizuku or Sui to install"
PERM_PROMPT = "Allow Obtainium to access Shizuku"


def grant_json(shell):
    uid = shell.app_uid(OBTAINIUM_PKG)
    if not uid:
        sys.stderr.write("ERROR: Obtainium not installed on %s\n" % shell.target)
        return False
    print("Granting Shizuku API to %s (uid=%s)..." % (OBTAINIUM_PKG, uid))
    shell.sh("pm grant %s %s" % (OBTAINIUM_PKG, SHIZUKU_PERM))

    current, ok = shell.read_shizuku_json(SHIZUKU_JSON)
    if not ok:
        sys.stderr.write("ERROR: no privileged shell or unreadable %s — "
                         "aborting to avoid clobbering grants\n" % SHIZUKU_JSON)
        return False
    patched = dev.patch_shizuku_json(current, uid, OBTAINIUM_PKG)
    if not shell.install_shizuku_json(patched, STAGING, SHIZUKU_JSON):
        sys.stderr.write("ERROR: failed to install patched shizuku.json\n")
        return False
    return True


def dump_ui(priv, path):
    priv.sh("uiautomator dump %s" % path)
    return priv.sh("cat %s" % path)[1]


def toggle_installer(priv, session):
    """UI taps go through session.shell (inversion-gated); dumps via PrivShell."""
    def run(*args):
        return session.shell(*args)

    print("Opening Obtainium settings to enable Shizuku installer...")
    run("input", "keyevent", "KEYCODE_WAKEUP")
    time.sleep(1)
    run("am", "start", "-n", "%s/.MainActivity" % OBTAINIUM_PKG)
    time.sleep(2)
    run("input", "tap", "945", "2196")  # settings gear
    time.sleep(2)
    for _ in range(6):  # scroll to top
        run("input", "swipe", "540", "400", "540", "1600", "350")
        time.sleep(0.4)

    xml = ""
    for _ in range(12):
        xml = dump_ui(priv, "/sdcard/obtainium_shizuku.xml")
        if SWITCH_LABEL in xml:
            break
        run("input", "swipe", "540", "1600", "540", "400", "350")
        time.sleep(0.6)
    else:
        sys.stderr.write("WARN: Shizuku installer row not found — scroll manually.\n")
        return False

    sw = dev.parse_switch(xml, SWITCH_LABEL)
    if sw and sw[0]:
        print("Shizuku installer already enabled in Obtainium UI.")
    elif sw:
        run("input", "tap", str(sw[1]), str(sw[2]))
        time.sleep(2)
        print("Tapped Shizuku installer switch.")
    else:
        run("input", "tap", "959", "1266")  # fallback coords
        time.sleep(2)
        print("Tapped Shizuku installer switch (fallback coords).")

    # Shizuku may prompt "Allow Obtainium to access Shizuku?" — approve if shown.
    perm_xml = dump_ui(priv, "/sdcard/obtainium_shizuku_perm.xml")
    if PERM_PROMPT in perm_xml:
        btn = dev.parse_button_center(perm_xml, "android:id/button1")
        if btn:
            run("input", "tap", str(btn[0]), str(btn[1]))
        else:
            run("input", "tap", "540", "1284")
        time.sleep(1)
        print("Approved Shizuku permission dialog for Obtainium.")

    run("input", "keyevent", "KEYCODE_HOME")
    return True


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: enable_shizuku_installer.py <p7a|s24|serial>\n")
        return 2
    priv = dev.PrivShell(argv[0])
    if not grant_json(priv):
        return 1
    try:
        with sc.ScreenControlSession(argv[0], label=argv[0], skip_request=True) as session:
            if not toggle_installer(priv, session):
                return 1
    except sc.ScreenControlError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    print("Done. Obtainium should use Shizuku for installs (fewer dialogs).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
