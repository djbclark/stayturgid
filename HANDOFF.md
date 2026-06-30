# stayturgid — AI Handoff Document

> **Purpose:** This file is a prompt for an AI agent taking over development. Read it fully before doing anything else. It describes what the project does, the current state, the development environment, the tooling rules, and what's next.

---

## What this project does

**stayturgid** keeps wireless ADB (port 5555) and Shizuku alive on a Google Pixel 7a running Android 16, across cold reboots, without root.

After a reboot and PIN unlock:
1. **Shizuku** (thedjchi fork) auto-starts via Android Wireless Debugging and uses TCP mode to call `adb tcpip 5555` — this is what opens port 5555 without USB.
2. **Termux:Boot** fires `~/.termux/boot/start-adb.sh` → starts `sshd`, then loops self-healing sshd every 5 min.
3. **Tasker** `ADB_Boot_Restore` profile fires on boot → runs `ADB_Core_Watchdog` task.
4. **Tasker** `ADB_Interval_Check` profile runs `ADB_Core_Watchdog` every 20 min — checks port 5555, Shizuku process, sshd, and fires a notification if any fail.

On the Mac side, a launchd agent (`com.djbclark.stayturgid.adb-reconnect`) runs every 60 seconds and reconnects `adb connect <ip>:5555` if it drops, handling DHCP IP changes automatically.

---

## Current project status (as of 2026-06-30)

- ✅ Port 5555 survives cold reboots (verified 2026-06-29)
- ✅ sshd survives cold reboots (Termux:Boot + self-heal loop)
- ✅ Tasker watchdog with failure notifications
- ✅ Mac-side launchd keepalive with macOS notification on reconnect/failure
- ✅ Published to TaskerNet: `https://taskernet.com/shares/?user=AS35m8lVOCqN0zylSnJKY8pBzCqkgDU8h624gr9CWqSAxD9myEt6n3OjyI4TtJhMtmw%2B&id=Project%3Astayturgid`
- ✅ Auto-update mechanism (`tasker/auto-update/stayturgid_update_check.tsk.xml`) — based on Task Auto Update by Joker; checks TaskerNet for newer version and shows Update/Skip notification
- 🔲 `stayturgid_update_check` not yet imported into device Tasker or wired to a trigger profile

---

## Repository

- **Mac path:** `~/stayturgid/`
- **GitHub:** `github.com/djbclark/stayturgid` (private)
- **Branch:** `master`
- **Working directory for AI sessions:** `~/upmon-handoff/` (legacy name, kept as-is)

---

## Device facts

| Field | Value |
|-------|-------|
| Device | Google Pixel 7a |
| Android | 16 |
| USB serial | `35261JEHN12374` |
| Default wireless ADB | `192.168.68.62:5555` (DHCP — may change; mac-side script auto-discovers via USB) |
| SSH to Termux | `adb -s 35261JEHN12374 forward tcp:8022 tcp:8022` then `ssh -i ~/.ssh/termux_key -p 8022 localhost` |
| Tasker package | `net.dinglisch.android.taskerm` v6.7.5-beta |
| Shizuku package | `moe.shizuku.privileged.api` (thedjchi fork v13.6.0.r1349-thedjchi-beta) |
| Termux package | `com.termux` (F-Droid) |
| Termux:Boot | `com.termux.boot` (F-Droid) |
| Termux:API | `com.termux.api` (F-Droid) + `termux-api` pkg in Termux |
| AutoInput | installed (Tasker plugin — used by auto-update for import clicks) |

Connect wirelessly:
```bash
adb connect 192.168.68.62:5555
# or let the mac script discover it:
adb -s 35261JEHN12374 shell "ip addr show wlan0" | grep "inet "
```

---

## Tooling rules (IMPORTANT — follow these exactly)

### Android automation tools
**Always use uiautomator2 and Termux:API. Do NOT use Maestro mobile unless debugging a suspected uiautomator2/Termux:API bug.**

- **uiautomator2** — UI automation (find elements by text/resource-id, click, read values). Installed via pipx on Mac. Device init required on first connect after reboot.
  ```bash
  /Users/djbclark/.local/bin/uiautomator2 init   # push u2.jar to device
  ```
  Python usage requires adding the pipx venv to sys.path:
  ```python
  import sys
  sys.path.insert(0, '/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages')
  import uiautomator2 as u2
  d = u2.connect('35261JEHN12374')
  ```

- **Termux:API** — Device-level APIs (clipboard, battery, SMS, etc.). Use from Termux shell:
  ```bash
  termux-battery-status   # returns JSON
  termux-clipboard-get
  # etc.
  ```
  Or via ADB shell:
  ```bash
  adb shell am broadcast -a com.termux.api.battery_status ...
  ```

- **Maestro mobile exception:** If uiautomator2 can't find an element that should be there, or a tap isn't registering, use Maestro (`~/.maestro/bin/maestro --udid 35261JEHN12374`) as a diagnostic to rule out tool bugs vs app state. Always tell the user: (1) why uiautomator2 wasn't sufficient, (2) what Maestro was used for, (3) what the result was.

### Phone announcement protocol (CRITICAL)
Before any device interaction, output this as a standalone message:

**🚨📱🚨🚨📱🚨 USING USING USING**

When done with the device and not expecting to touch it again until the next user reply:

**✅📱✅✅📱✅ FREE FREE FREE**

Both must be standalone — not buried in other text.

---

## Mac development environment

| Tool | Version | Install |
|------|---------|---------|
| Homebrew | current | `brew` |
| ADB (platform-tools) | bundled with Android Studio or `brew install android-platform-tools` | `/opt/homebrew/bin/adb` |
| uiautomator2 | latest via pipx | `pipx install uiautomator2` |
| Python | 3.14 (Homebrew) | `brew install python` |
| pipx | current | `brew install pipx` |
| git | current | Homebrew |
| Maestro CLI | v2.6.1 | `~/.maestro/bin/maestro` |

SSH key for Termux: `~/.ssh/termux_key` (ed25519, deployed to Termux `~/.ssh/authorized_keys`)

Mac launchd agent:
```bash
cp ~/stayturgid/mac/com.djbclark.stayturgid.adb-reconnect.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.djbclark.stayturgid.adb-reconnect.plist
```
Log: `~/Library/Logs/stayturgid-adb-reconnect.log`

---

## Key files

```
tasker/
  stayturgid.prj.xml                    — full Tasker project; import to /sdcard/Tasker/projects/
  ADB_Core_Watchdog.tsk.xml             — standalone task XML (9 actions)
  auto-update/
    stayturgid_update_check.tsk.xml     — update-check task pre-configured for stayturgid
    Task_Auto_Update.tsk.xml            — original upstream task from TaskerNet (reference)
    README.md                           — integration docs for auto-update
termux/boot/
  start-adb.sh                          — deploy to ~/.termux/boot/ on device
mac/
  adb-reconnect.sh                      — Mac-side keepalive script (run by launchd)
  com.djbclark.stayturgid.adb-reconnect.plist — launchd agent (runs every 60s)
```

---

## Tasker project structure

**Project:** `stayturgid` (id `7039e243-d549-44a5-b52b-848399f906b7`)

**Profiles:**
- `ADB_Interval_Check` (prof200) — Time trigger, every 20 min, 00:00–23:59 → `ADB_Core_Watchdog`
- `ADB_Boot_Restore` (prof201) — Device Boot event → `ADB_Core_Watchdog`

**Tasks:**
- `ADB_Core_Watchdog` (task100, 9 actions):
  1. Secure Settings: `adb_enabled=1`
  2. Secure Settings: `adb_wifi_enabled=1`
  3. Shell: `adb tcpip 5555` (belt-and-suspenders)
  4. Shell: port check → `%PORT_CHECK`
  5. Shell: Shizuku check → `%SHIZUKU_CHECK`
  6. Shell: sshd check → `%SSHD_CHECK`
  7. If PORT_CLOSED OR NO_SHIZUKU OR NO_SSHD → Notify (channel: `stayturgid`)
  8. End If

**Not yet imported to device:**
- `stayturgid_Update_Check` (`tasker/auto-update/stayturgid_update_check.tsk.xml`)
  - Needs a trigger profile (recommend: Time, once daily at 10:00)

---

## Auto-update mechanism

`stayturgid_update_check.tsk.xml` implements update notifications via the "Task Auto Update" pattern by Joker (u/Bushido---). It:
1. Reads `updateData` in `act6` — contains `taskernet_url`, `version`, `changelog`
2. Fetches the TaskerNet project XML via the undocumented API
3. Regex-extracts the `"version": "..."` string from the returned JSON (which contains the XML)
4. Compares to local `version`; if TaskerNet is newer, shows Update/Skip notification
5. Update button → opens `taskershare://` URI to trigger Tasker's native import UI

**To release an update:** bump `"version": "1.0"` in `act6` of `stayturgid_update_check.tsk.xml`, update `"changelog"`, export the stayturgid project from Tasker, republish to TaskerNet. The URL never changes.

**Future option — local XML update (no TaskerNet dependency):**
Per Grok's suggestion, it's possible to bypass TaskerNet entirely by:
1. Downloading the `.prj.xml` directly from GitHub raw URL via HTTP Request
2. Saving to `Tasker/Updates/ProjectUpdate.prj.xml`
3. Using Tasker's `Open File` action on the `.prj.xml` — Tasker intercepts and shows Import UI
4. AutoInput clicks "IMPORT" then "OVERWRITE"
5. Delete the temp file
This would work without TaskerNet servers and keep the project private. Not implemented yet.

---

## Known issues / gotchas

- **uiautomator2 `d.exists()` returns False:** Usually means a Tasker "NLI: warning: disconnected" popup is blocking the UI. Fix: `d(text='OK').click()` to dismiss first.
- **Tasker ⋮ menu tap not registering at screen edge:** Tap slightly inward (e.g., x=1010 not x=1028) — gesture navigation zone interferes.
- **Tasker XML action IDs must be strictly sequential integers** (act0, act1, act2…). Non-sequential IDs like `act3a` are silently ignored on import.
- **TaskerNet tags** must be from the existing tag database. Free-text tags return HTTP 400. Use the magnifying-glass "Choose" button in the Tasker share UI to browse valid tags.
- **Reddit is blocked** in Claude Code. Use PullPush API instead: `https://api.pullpush.io/reddit/search/submission/?ids=<post_id>`
- **Device IP changes on DHCP.** The mac-side script auto-discovers via USB. Always verify with: `adb -s 35261JEHN12374 shell "ip addr show wlan0"`

---

## Next steps

1. **Import `stayturgid_update_check` into device Tasker** and wire to a daily trigger profile
2. **HACKING.md** — document the full development environment for new contributors (versions, sources, Obtainium lines, clean-install setup steps)
3. **Local XML update path** — evaluate replacing TaskerNet-based update with GitHub raw URL → AutoInput flow (see auto-update section above)
4. **Notification channel fix propagation** — `ADB_Core_Watchdog.tsk.xml` now uses `stayturgid` channel; re-import this task to device if previously had `upmon`

---

## How to start a new AI session

```bash
claude   # open interactive session in terminal (NOT Warp)
```

Verify session type is Pro/Max (not API billing) with `/status`. The working directory is `~/upmon-handoff/` — this is the Maestro agent working dir, separate from the project at `~/stayturgid/`.
