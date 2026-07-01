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
- ✅ Auto-update mechanism implemented — local XML download+import path complete; task imported to device
  - act20: Run Shell `mkdir -p /sdcard/Tasker/Updates`
  - act21: HTTP Request GET `%raw_xml_url` → file save arg7=`Tasker/Updates/stayturgid.prj.xml`
  - act22: Wait 1s
  - act23: Run Shell `am start -a android.intent.action.VIEW -d "file://%http_file_output"`
  - act24: Wait 3s
  - act25: AutoInput IMPORT click (code 1732635924, UUID `75e60f28-41ac-4048-83fd-b55de4bef613`)
  - act26: Wait 1s
  - act27: AutoInput OVERWRITE click (code 1732635924, UUID `e72f5a3d-1985-4cc5-80d7-d56d29721b91`)
  - act28: Go Home (code 25)
  - act29: Delete File `%http_file_output` (code 406)
  - act30–act36: Skip path (formerly act23–act29)
- 🔲 Auto-update flow NOT yet tested end-to-end (Step 2)
- 🔲 `stayturgid_update_check` not yet wired to a trigger profile (Step 3)

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
| ADB (platform-tools) | 1.0.41 / 37.0.0-14910828 | `brew install android-platform-tools` → `/opt/homebrew/bin/adb` |
| uiautomator2 | 3.7.0 via pipx | `pipx install uiautomator2` |
| Python | 3.14.6 (Homebrew) | `brew install python` |
| pipx | 1.15.0 | `brew install pipx` |
| git | current | Homebrew |

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

`stayturgid_update_check.tsk.xml` is designed to use a fully local XML flow — no TaskerNet servers involved in the actual install, only in version detection.

### How it works (target design)

1. `act6` (JavaScript) sets local variables from `updaterData`: `%taskernet_url`, `%raw_xml_url`, `%version`, `%changelog`
2. `act9` (JavaScript) builds the TaskerNet API URL from `%taskernet_url` → `%taskernet_xml`
3. `act10` (HTTP Request) fetches the TaskerNet JSON for the project — this returns JSON containing the raw project XML as a string
4. `act11` (Regex Match) extracts `"version": "..."` from that JSON — the version string is embedded inside `act6`'s JavaScript in the published XML, so the regex finds it there
5. `act13` (JavaScript) compares local `%version` to fetched `%taskernet_version`; sets `%updatestatus` to true/false
6. If update available: shows a sticky notification with Update / Skip buttons (each button calls back into this task with `par1=user_input`, `par2=update` or `par2=skip`)
7. **Update path (act19–act30):**
   - HTTP Request: GET `%raw_xml_url` → save to `/sdcard/Tasker/Updates/ProjectUpdate.prj.xml`
   - Wait 1s (file write settle)
   - Open/view the file (fires Android VIEW intent → Tasker intercepts `.prj.xml` → shows Import dialog)
   - Wait 3s (Import UI render buffer)
   - AutoInput Action: click text "IMPORT" (timeout 20s)
   - Wait 1s
   - AutoInput Action: click text "OVERWRITE" (timeout 20s)
   - Go Home
   - Delete `/sdcard/Tasker/Updates/ProjectUpdate.prj.xml`
   - Task Stop
8. **Skip path (act31–act36):** cancel notification, flash "Skipped...", stop

### Current implementation status

`act6` ✅ — `raw_xml_url` points to GitHub raw URL:
```
https://raw.githubusercontent.com/djbclark/stayturgid/master/tasker/stayturgid.prj.xml
```

**act20–act29 ✅ — local XML path implemented (2026-06-30):** The old TaskerNet actions (JavaScript + Browse URL + Task Stop) have been replaced with the 10-action local import sequence above. File: `tasker/auto-update/stayturgid_update_check.tsk.xml`, imported to device under the `stayturgid` project.

### Discovered Tasker action codes and arg layouts

All action codes and arg layouts below are confirmed from live exports on Tasker 6.7.5-beta. You CAN edit the task XML directly using these.

| Action | Code | Key args |
|--------|------|----------|
| Wait | 30 | arg0=ms, **arg1=seconds**, arg2=minutes, arg3=hours, arg4=days |
| Run Shell | 123 | arg0=command, arg1=root(0/1), arg2=timeout, arg3=output_var, arg6=1(store) |
| HTTP Request | 339 | arg1=method(0=GET), arg2=URL, arg3=headers, arg4=query_params, **arg7=file_save_path**, arg8=timeout |
| JavaScript | 129 | arg0=script |
| Task Stop | 137 | arg0=0(normal) |
| Go Home | 25 | arg0=page(0=main) |
| Delete File | 406 | arg0=path, arg1=0 |
| End If | 40 | (no args) |
| Else/If | 39 | arg0=variable, arg1=value, arg2=comparison |
| AutoInput plugin | **1732635924** | arg0=Bundle(see below), arg1=package, arg2=activity, arg3=timeout, arg4=1 |

**Wait arg critical gotcha:** arg1=seconds, arg2=**minutes**. Setting arg2=3 gives 3 minutes, not 3 seconds!

**AutoInput Bundle structure** (use verbatim — the plugininstanceid must match what's stored in AutoInput's DB on the device):
- `ActionId`: text to match (e.g., `IMPORT`)
- `ActionType`: `16` (click)
- `FieldSelectionType`: `0` (by text)
- `plugintypeid`: `com.joaomgcd.autoinput.intent.IntentPerformAction`
- `plugininstanceid` for IMPORT: `75e60f28-41ac-4048-83fd-b55de4bef613`
- `plugininstanceid` for OVERWRITE: `e72f5a3d-1985-4cc5-80d7-d56d29721b91`

These UUIDs were created by configuring AutoInput on the device and pulling the export (AIProbe task method). See full Bundle XML in `AIProbe.tsk.xml` (was at `/tmp/AIProbe.tsk.xml`, was on-device at `/sdcard/Tasker/tasks/AIProbe.tsk.xml` — purge it post-development).

**How the AutoInput UUIDs were obtained:** Created an `AIProbe` Tasker task on the device with two AutoInput actions (IMPORT and OVERWRITE), verified via BLURB text, exported to `/sdcard/Tasker/tasks/AIProbe.tsk.xml`, pulled with `adb pull`. The UUIDs are now embedded in `stayturgid_update_check.tsk.xml`.

### To release an update (once implementation is complete)

1. Make changes to the project, test on device
2. Export project from Tasker → pull to Mac: `adb pull /sdcard/Tasker/stayturgid.prj.xml ~/stayturgid/tasker/stayturgid.prj.xml`
3. In `tasker/auto-update/stayturgid_update_check.tsk.xml` `act6`, bump `"version"` and update `"changelog"`
4. Commit and push to GitHub master — that's the entire release; no TaskerNet action needed

GitHub raw URL (already set in act6):
```
https://raw.githubusercontent.com/djbclark/stayturgid/master/tasker/stayturgid.prj.xml
```

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

### ✅ Step 1 — Implement local XML update path (COMPLETE as of 2026-06-30)

The task XML was edited directly on Mac (`tasker/auto-update/stayturgid_update_check.tsk.xml`) using the discovered action codes and imported to the device. See "Discovered Tasker action codes" section for reference.

### Step 2 — Test the update flow (CURRENT NEXT STEP)

Set `"version": "0.0"` in act6 temporarily (forces `0.0 < 1.0` comparison → update always triggered). Run the task manually. Verify:
1. Notification appears with Update / Skip buttons
2. Tap Update → file downloads to `/sdcard/Tasker/Updates/ProjectUpdate.prj.xml`
3. Tasker import dialog appears
4. AutoInput clicks IMPORT, then OVERWRITE
5. Home screen
6. Temp file deleted: `adb shell "ls /sdcard/Tasker/Updates/"` should be empty

Reset `"version": "1.0"` after test passes.

### Step 3 — Wire update check to a daily trigger

Create a new Tasker profile: Time → 10:00 → Every day → Task: `stayturgid_Update_Check`. Export and commit.

### Step 4 — Notification channel propagation

`ADB_Core_Watchdog.tsk.xml` in repo uses `stayturgid` channel. If device still has old `upmon` channel version, re-import the task or project.

### Step 5 — Evaluate removing TaskerNet from version detection

Currently version detection still hits TaskerNet (fetches project JSON, regex-extracts `"version"` from the embedded XML). Two options to evaluate:
- **Keep hybrid** (current): TaskerNet for version detection, GitHub for download. Simple, no extra files needed.
- **GitHub-only**: Add a `version.json` file to the repo, fetch that for version detection. Removes all TaskerNet dependency. Would require a new HTTP Request action and updated parse logic in the version-check task.

See **HACKING.md** for the full development environment setup (all tool versions, Obtainium sources, clean-install walkthrough).

---

## How to start a new AI session

```bash
claude   # open interactive session in terminal (NOT Warp)
```

Verify session type is Pro/Max (not API billing) with `/status`. The working directory is `~/upmon-handoff/` — this is the Maestro agent working dir, separate from the project at `~/stayturgid/`.
