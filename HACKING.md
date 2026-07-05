# HACKING — stayturgid Development Environment

This document gets a developer from a clean Android + macOS install to a fully working development environment for stayturgid. Follow the sections in order — Android setup first, then Mac, then verification.

---

## What you're setting up

| Layer | Role |
|-------|------|
| Android device | Runs Tasker, Shizuku, Termux — the actual system under management |
| macOS (Mac) | Development workstation; runs ADB, uiautomator2, AI coding agent (Claude Code) |
| Tasker | Automation runtime on the device — the core of stayturgid |
| Shizuku (thedjchi fork) | Grants Tasker `WRITE_SECURE_SETTINGS` via Wireless Debugging (no root) |
| Termux | Linux environment on Android — runs sshd, adb, the boot script |

---

## Tested versions

### Android device
| App | Package | Version | Source |
|-----|---------|---------|--------|
| Android | — | 16 (SDK 36) | — |
| Tasker | `net.dinglisch.android.taskerm` | 6.7.5-beta | Play Store / TaskerNet |
| Shizuku (thedjchi fork) | `moe.shizuku.privileged.api` | 13.6.0.r1349-thedjchi-beta | GitHub (see below) |
| Termux | `com.termux` | 2026.06.21 | Google Play or F-Droid |
| Termux:Boot | `com.termux.boot` | 0.8.1 | F-Droid / GitHub |
| Termux:API (app) | `com.termux.api` | 0.53.0 | F-Droid / GitHub |
| Termux:Tasker | `com.termux.tasker` | 0.9.0 | F-Droid / GitHub |
| AutoInput (Tasker plugin) | `com.joaomgcd.autoinput` | 3.0.12 | Play Store (paid) |

### Termux packages (installed inside Termux via `pkg`)
| Package | Version |
|---------|---------|
| openssh | 10.3p1-1 |
| termux-api (CLI) | 0.59.1 |
| android-tools (adb) | 35.0.2-7 |
| python | 3.13.13-1 |
| curl | 8.21.0 |
| wget | 1.25.0-1 |

### macOS development tools
| Tool | Version | Install |
|------|---------|---------|
| macOS | Sequoia 15.x+ | — |
| Homebrew | current | https://brew.sh |
| ADB (platform-tools) | 1.0.41 / 37.0.0-14910828 | `brew install android-platform-tools` |
| Python | 3.14.6 | `brew install python` |
| pipx | 1.15.0 | `brew install pipx` |
| uiautomator2 (Python) | 3.7.0 | `pipx install uiautomator2` |
| Claude Code (AI agent) | current | `npm install -g @anthropic-ai/claude-code` |
| git | current | `brew install git` |

---

## Part 1 — Android setup

### 1.1 Enable Developer Options and Wireless Debugging

1. **Settings → About phone → Build number**: tap 7 times to enable Developer Options.
2. **Settings → System → Developer options**:
   - Enable **USB debugging**
   - Enable **Wireless debugging**
3. Open **Wireless debugging** and note the IP address and port shown (you'll need this for pairing, but ADB on the Mac will handle it automatically once you connect via USB).

### 1.2 Install Android apps

Install the following apps. Order matters — Shizuku must be installed before Tasker so Tasker can request the Shizuku permission.

#### Shizuku — thedjchi fork (CRITICAL: must be this fork)

The standard Shizuku from Play Store **does not have TCP mode**. You need thedjchi's fork which adds automatic boot-time TCP (port 5555) support via Wireless Debugging.

**Source:** https://github.com/thedjchi/Shizuku/releases

**Obtainium URL** (add this in Obtainium → Add App):
```
https://github.com/thedjchi/Shizuku
```
Select: "GitHub Releases" → filter for `.apk`.

Install the latest `app-release.apk` from the releases page. Current version: **13.6.0.r1349-thedjchi-beta**.

#### Termux (install from F-Droid or Google Play)

```
https://github.com/termux/termux-app
```
Or F-Droid: search "Termux" by Termux Dev Team.

> Note: F-Droid and Google Play builds are signed differently and **cannot coexist**. Pick one source and stick with it. Google Play version may lag behind F-Droid.

#### Termux:Boot

```
https://github.com/termux/termux-boot
```
Or F-Droid: search "Termux:Boot".

**Must match the signing source of Termux** (F-Droid with F-Droid, Play with Play).

#### Termux:API (app)

```
https://github.com/termux/termux-api
```
Or F-Droid: search "Termux:API".

#### Termux:Tasker

```
https://github.com/termux/termux-tasker
```
Or F-Droid: search "Termux:Tasker".

#### Tasker

Play Store: search "Tasker" by joaomgcd. (Or purchase from https://tasker.joaomgcd.com — direct APK, no Play Store required.)

Current version: **6.7.5-beta**. Use the beta channel for the latest features.

#### AutoInput (Tasker plugin, paid)

Play Store: search "AutoInput" by joaomgcd. Required for the auto-update import flow (clicks "IMPORT" / "OVERWRITE" in Tasker's import UI).

Current version: **3.0.12**.

#### Tailscale

Gives the device a stable `100.x.y.z` IP that survives DHCP lease changes and network switches — so `adb connect <tailscale-ip>:5555` and SSH keep working without hunting for the current WiFi IP. (The S24's LAN IP changed mid-session once and broke every hardcoded `adb connect`; Tailscale eliminates that failure mode.)

**Obtainium URL** (add this in Obtainium → Add App):
```
https://github.com/tailscale/tailscale-android
```
Select: "GitHub Releases" → filter for `.apk`.

After install: sign in, and in Tailscale settings consider enabling **VPN On-Demand / Always-on VPN** so the tunnel survives reboots.

---

### 1.3 Configure Shizuku (thedjchi fork)

Open Shizuku → **Settings (gear icon)**. Set:

| Setting | Value | Why |
|---------|-------|-----|
| Start on boot | ON | Auto-starts via Wireless Debugging on every reboot |
| Watchdog (restart if crash) | ON | Auto-restarts Shizuku if it crashes |
| TCP mode | ON | Calls `adb tcpip 5555` after starting — this opens port 5555 without USB |
| TCP port | 5555 (default) | Standard wireless ADB port |
| Auto-disable USB debugging | OFF | Leave USB debugging active |

Then tap **Start via Wireless debugging → Start**. Once it's running you should see the Shizuku notification. Subsequent reboots are automatic.

---

### 1.4 Configure Termux

Open Termux and install the required packages:

```bash
pkg update && pkg upgrade -y
pkg install openssh android-tools termux-api python wget curl -y
```

**Set up the SSH server and your public key:**

```bash
# Generate a key on the Mac first (if you don't have one):
# ssh-keygen -t ed25519 -f ~/.ssh/termux_key

# On the device, in Termux:
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Paste your Mac's public key (~/.ssh/termux_key.pub):
echo "YOUR_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

**Start sshd and test it (from Mac):**

```bash
# On device in Termux:
sshd

# On Mac (device connected via USB):
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost
```

**Deploy the Termux:Boot script:**

```bash
# From Mac (with repo cloned to ~/stayturgid/):
adb push ~/stayturgid/termux/boot/start-adb.sh /sdcard/start-adb.sh

# In Termux on device:
mkdir -p ~/.termux/boot
cp /sdcard/start-adb.sh ~/.termux/boot/start-adb.sh
chmod +x ~/.termux/boot/start-adb.sh
```

Open the **Termux:Boot app** once to register its `BOOT_COMPLETED` receiver — it won't fire on boot until you do this.

**Verify Termux:API is working:**

```bash
# In Termux (or via SSH):
termux-battery-status
# Should return JSON like: {"health":"GOOD","percentage":85,...}
```

If the command hangs or errors, make sure the Termux:API app is installed (section 1.2) and that you've granted it the necessary permissions when prompted.

---

### 1.5 Grant Tasker `WRITE_SECURE_SETTINGS`

Tasker needs this permission to enforce `adb_enabled` and `adb_wifi_enabled` settings. It cannot be granted from the UI — must be done via ADB from the Mac.

Connect device via USB, then:

```bash
adb -s 35261JEHN12374 shell pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS
```

Verify in Tasker: **Prefs → Android → Android Settings** should show `WRITE_SECURE_SETTINGS` as granted.

---

### 1.6 Import the Tasker project

**Option A — from TaskerNet (easiest):**

Open this URL on the device (or tap from the README link):
```
https://taskernet.com/shares/?user=AS35m8lVOCqN0zylSnJKY8pBzCqkgDU8h624gr9CWqSAxD9myEt6n3OjyI4TtJhMtmw%2B&id=Project%3Astayturgid
```
Tasker will offer to import the project.

**Option B — from XML file:**

```bash
adb push ~/stayturgid/tasker/stayturgid.prj.xml /sdcard/Tasker/projects/stayturgid.prj.xml
```
In Tasker: long-press the project tab → **Import Project** → select `stayturgid`.

**After importing:**
- Verify both profiles are active: `ADB_Boot_Restore` and `ADB_Interval_Check`
- Tap **Run** on `ADB_Core_Watchdog` manually to confirm it executes without errors

---

### 1.7 Import the update-check task (optional but recommended)

```bash
adb push ~/stayturgid/tasker/auto-update/stayturgid_update_check.tsk.xml /sdcard/Tasker/tasks/stayturgid_Update_Check.tsk.xml
```

In Tasker: go to the **TASKS** tab → long-press on any existing task (or blank space) → tap **Import Task** → select `stayturgid_Update_Check`.

> Note: The file goes to `/sdcard/Tasker/tasks/` (not `/sdcard/Tasker/`). The Import Task picker shows this directory by default.

> If reimporting after a change: same procedure — Tasker will create a new copy (doesn't auto-overwrite). If a duplicate appears with the same name, delete the old one in the TASKS list.

Add a trigger profile: in the **PROFILES** tab, tap **+** → Time → 10:00 → Every day → set Entry task to `stayturgid_Update_Check`.

---

## Part 2 — macOS setup

### 2.1 Install Homebrew and core tools

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install android-platform-tools python pipx git
pipx ensurepath
```

### 2.2 Install uiautomator2

uiautomator2 is the primary Android UI automation tool used for development (finding elements, clicking, reading screen state).

```bash
pipx install uiautomator2
```

Verify:
```bash
/Users/$(whoami)/.local/bin/uiautomator2 --version
# Should print: 3.7.0 (or newer)
```

**First-time device initialization** (do this once after each factory reset, or if `u2.jar` is missing from the device):

```bash
# Device must be connected via USB or wireless ADB first
/Users/$(whoami)/.local/bin/uiautomator2 init
```

**Using uiautomator2 in Python scripts:**

The pipx-installed package is in its own venv. Add it to sys.path:

```python
import sys
sys.path.insert(0, '/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages')
import uiautomator2 as u2

d = u2.connect('35261JEHN12374')  # USB serial, or '192.168.68.62:5555' for wireless
print(d.info)
```

Common operations:
```python
d(text='OK').click()                          # click by visible text
d(resourceId='com.foo:id/bar').exists         # check if element exists
d.screenshot('/tmp/screen.png')               # take screenshot
```

> **Gotcha:** If `d(text='SomeButton').exists` returns False when the button is visible, Tasker likely has a dismissable popup (e.g., "NLI: warning: disconnected") covering the UI. Click `d(text='OK').click()` to dismiss it first.

### 2.3 SSH key for Termux

```bash
ssh-keygen -t ed25519 -f ~/.ssh/termux_key
# Copy ~/.ssh/termux_key.pub to Termux ~/.ssh/authorized_keys (see Part 1.4)
```

Add to `~/.ssh/config` for convenience:
```
Host termux
  HostName localhost
  Port 8022
  IdentityFile ~/.ssh/termux_key
  User u0_a<UID>
  StrictHostKeyChecking no
```

Connect:
```bash
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh termux
```

### 2.4 Install the Mac-side launchd keepalive

This runs `adb connect` every 60 seconds, handles DHCP IP changes, and sends a macOS notification on reconnect or failure.

```bash
cp ~/stayturgid/mac/com.djbclark.stayturgid.adb-reconnect.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.djbclark.stayturgid.adb-reconnect.plist
```

> Edit the plist first if you cloned the repo to a different path — `adb-reconnect.sh` path is hardcoded.

Logs: `~/Library/Logs/stayturgid-adb-reconnect.log`

Unload: `launchctl unload ~/Library/LaunchAgents/com.djbclark.stayturgid.adb-reconnect.plist`

### 2.5 Install Claude Code (AI development agent)

```bash
npm install -g @anthropic-ai/claude-code
```

The AI agent session runs from `~/upmon-handoff/` (legacy working directory name). Start a session:

```bash
cd ~/upmon-handoff
claude
```

Verify it's using Pro/Max plan (not API billing): run `/status` inside Claude Code.

---

## Part 3 — Connecting to the device

### Wireless ADB

The device's IP can change across reboots (DHCP). The mac-side script auto-discovers it via USB. To discover manually:

```bash
# Via USB:
adb -s 35261JEHN12374 shell "ip addr show wlan0 | grep 'inet '"
# Then connect wirelessly:
adb connect <discovered-ip>:5555
```

Default/cached IP: `192.168.68.62:5555` (stored in `~/.config/stayturgid/device_ip`).

### SSH to Termux

Direct WiFi SSH is blocked by Android's firewall. Use ADB port-forward:

```bash
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost
```

---

## Part 4 — Development workflow

### Making Tasker changes

1. Edit the Tasker project on the device in the Tasker UI.
2. Export the project: **long-press project tab → Export → As File** → saves to `/sdcard/Tasker/`.
3. Pull to Mac:
   ```bash
   adb pull /sdcard/Tasker/stayturgid.prj.xml ~/stayturgid/tasker/stayturgid.prj.xml
   ```
4. Commit and push.

> **XML format gotcha:** Tasker action IDs must be strictly sequential integers (`act0`, `act1`, `act2`...). Non-sequential IDs (e.g. `act3a`) are silently ignored on import. Always export from Tasker rather than editing the XML by hand unless you're careful about this.

### Using uiautomator2 for device automation

Use for: tapping buttons in Tasker UI, reading screen state, automating setup steps.

```python
import sys
sys.path.insert(0, '/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages')
import uiautomator2 as u2
d = u2.connect('35261JEHN12374')
```

Run the HTTP server on the device first if it's not running:
```bash
/Users/djbclark/.local/bin/uiautomator2 init
```

### Using Termux:API for device state

Use for: reading battery, clipboard, notifications, sensors — anything that's OS-level rather than UI-level.

```bash
# Via SSH to Termux:
termux-battery-status
termux-clipboard-get
termux-sensor -s "Accelerometer" -n 1
```

### Publishing an update

The update flow uses GitHub as the source of truth. When you push a new version of `stayturgid.prj.xml` to `master`, any device running `stayturgid_Update_Check` will detect it on the next daily check and offer to install it automatically via AutoInput.

#### Release steps

1. Make changes and test them on device.
2. Export the project from Tasker: **long-press project tab → Export → As File** → saves to `/sdcard/Tasker/`.
3. Pull to Mac and commit:
   ```bash
   adb pull /sdcard/Tasker/stayturgid.prj.xml ~/stayturgid/tasker/stayturgid.prj.xml
   cd ~/stayturgid
   # Bump version in auto-update task (see below), then:
   git add tasker/ && git commit -m "Release vX.Y"
   git push
   ```
4. Bump `"version"` in `act6` of `tasker/auto-update/stayturgid_update_check.tsk.xml` and update `"changelog"`. Set `%raw_xml_url` to the GitHub raw URL of `stayturgid.prj.xml`:
   ```
   https://raw.githubusercontent.com/djbclark/stayturgid/master/tasker/stayturgid.prj.xml
   ```

#### How the auto-update works (local XML flow)

The update check task (`stayturgid_Update_Check`) uses a fully local flow — no TaskerNet server required at update time:

1. **Version check:** Fetches the raw XML from GitHub, regex-extracts `"version": "X.Y"` from `act6`'s embedded JavaScript, compares to local version.
2. **If newer:** Shows a notification with Update / Skip buttons.
3. **Update tapped:**
   - HTTP Request downloads `stayturgid.prj.xml` from GitHub raw URL → saves to `Tasker/Updates/ProjectUpdate.prj.xml`
   - Open File action on the `.prj.xml` — Android/Tasker intercepts and shows the native Import UI
   - AutoInput clicks **IMPORT**, waits 1 second, clicks **OVERWRITE**
   - Go Home
   - Delete `Tasker/Updates/ProjectUpdate.prj.xml`
4. **Skip tapped:** Dismisses notification, shows "Skipped..." flash.

> **GitHub raw URL note:** Use `raw.githubusercontent.com/...` not the normal GitHub page URL. The page URL returns HTML which Tasker cannot parse as XML.

> **Wait buffer:** The 3-second wait before AutoInput clicks "IMPORT" can be bumped to 4–5 seconds on slower devices if AutoInput times out.

#### TaskerNet (version detection only)

The version string is detected by fetching the TaskerNet API response for the project and regex-matching `"version": "..."` inside the XML that's embedded in the JSON. TaskerNet is only used to read the current published version — the actual project XML download and import use GitHub directly.

Fetch current published XML (for debugging):
```bash
curl "https://taskernet.com/_ah/api/datashare/v1/sharedata/AS35m8lVOCqN0zylSnJKY8pBzCqkgDU8h624gr9CWqSAxD9myEt6n3OjyI4TtJhMtmw%2B/Project%3Astayturgid?a=0&xml=true"
```

#### TaskerNet tag constraint (if re-publishing)

Tags must exist in the TaskerNet tag database — free-text tags return HTTP 400. Use the magnifying-glass "Choose" button in Tasker's share UI. Current stayturgid tags: **Security, Shizuku, WiFi**.

---

## Part 5 — Tasker XML reference (discovered 2026-06-30)

These action codes and arg layouts are confirmed from live Tasker 6.7.5-beta exports on the development device. You can use them to edit `.tsk.xml` files directly on Mac without touching the Tasker UI.

### Action codes

| Action | Code | Notes |
|--------|------|-------|
| Comment | 300 | arg0=text (label only) |
| If | 37 | Condition in `<ConditionList>` |
| Else/If | 39 | arg0=var, arg1=value, arg2=op |
| End If | 40 | no args |
| Goto | 135 | — |
| Regex Match | 396 | — |
| Variable Set | 547 | arg0=name, arg1=value |
| JavaScript | 129 | arg0=script |
| Run Shell | 123 | arg0=cmd, arg1=root, arg2=timeout, arg3=output_var, arg6=1(store) |
| HTTP Request | 339 | see below |
| Wait | 30 | **arg0=ms, arg1=secs, arg2=mins, arg3=hours, arg4=days** |
| Task Stop | 137 | arg0=0 |
| Go Home | 25 | arg0=page (0=main) |
| Delete File | 406 | arg0=path, arg1=0 |
| AutoInput plugin | **1732635924** | see below (version-specific code for Tasker 6.7.5-beta) |
| Show Notification | 523 | — |
| Cancel Notification | 513 | — |
| Cancel Notification by Tag | 779 | arg0=tag |
| Variable Flash | 548 | arg0=text |
| Screen On/Off | 512 | — |
| Task | 130 | call another task |

### Custom Setting action (code 235) — namespace mapping GOTCHA (discovered 2026-07-05)

`arg0` selects the settings namespace from the dropdown in **alphabetical order**:

| arg0 | Namespace |
|------|-----------|
| 0 | **Global** |
| 1 | Secure |
| 2 | System |

Do NOT assume 0=system. The original watchdog wrote `adb_enabled`/`adb_wifi_enabled` with arg0=2 (System) — silently useless, since **both settings live in Global** (verified on S24: `settings get global adb_enabled` → 1, secure/system → null). This was why the watchdog never actually restored ADB. Writing to Global/Secure requires `pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS`.

Other args: arg1=setting name, arg2=value, arg3=0.

### XML comments break Tasker import (discovered 2026-07-02)

Tasker's XML parser does NOT handle `<!-- ... -->` comments inside project/task XML. A file containing them imports as an **empty project** (structure created, no tasks/profiles, no error shown). Strip all comments before pushing:

```bash
python3 -c "import re,sys; p=sys.argv[1]; s=open(p).read(); open(p,'w').write(re.sub(r'<!--.*?-->','',s,flags=re.DOTALL))" file.prj.xml
```

### Import fails with "a project with that name already exists" — ghost project GOTCHA (discovered 2026-07-05)

Tasker's project-tab **Delete → "Delete Contents"** does NOT fully remove the project — the project shell survives in Tasker's internal data (its tab may even disappear from the UI while tasks/profiles remain hidden under it). Any later import of a same-named project then fails; via My Files/content-URI the failure is **silent**, via long-press project tab → **Import Project** you at least get the real error message.

Reliable clean reimport sequence:
1. Delete all profiles first (long-press → select all → trash; tasks can't be deleted while profiles reference them)
2. Delete all tasks
3. Long-press project tab → Delete → **Keep Contents** (this removes the shell)
4. Push the XML to `/sdcard/Tasker/projects/`
5. Long-press any project tab → **Import Project** → pick the file (this path shows real errors, unlike the My Files → Open-with-Tasker path)

Also: editing `/sdcard/Tasker/projects/*.prj.xml` directly does nothing — Tasker only reads those files during an explicit import; live data is in the app's private storage.

### Wait action — CRITICAL GOTCHA

The Wait action (code 30) has a counter-intuitive arg order:
- `arg0` = **milliseconds**
- `arg1` = **seconds**
- `arg2` = **minutes**
- `arg3` = **hours**
- `arg4` = **days**

A 1-second wait:
```xml
<Action sr="actX" ve="7">
    <code>30</code>
    <Int sr="arg0" val="0"/>
    <Int sr="arg1" val="1"/>
    <Int sr="arg2" val="0"/>
    <Int sr="arg3" val="0"/>
    <Int sr="arg4" val="0"/>
</Action>
```

A 3-second wait: same but `arg1` = 3.

### HTTP Request action (code 339)

Key args:
- `arg1` = method (0=GET, 1=POST, 2=HEAD, 3=PUT, 4=DELETE, 5=PATCH)
- `arg2` = URL
- `arg3` = headers (optional)
- `arg4` = query params (optional)
- `arg5` = unknown (leave empty)
- `arg6` = unknown (leave empty)
- **`arg7` = file/directory to save output** (set this to save the response to a file)
- `arg8` = timeout in seconds (60 recommended)
- `arg9–arg12` = flags (0, 0, 0, 1 — copy from existing action)

Output variable `%http_file_output` always contains the full absolute path of the saved file.

### AutoInput Gestures action (code 778682267) — used for import dialog clicks

The auto-update task uses **AutoInput Gestures** (not AutoInput Actions/text-click) to click the import dialogs. This uses AutoInput's AccessibilityService to perform touch gestures at specific screen coordinates.

**Key property:** Coordinates are stored **inline** in the `parameters` JSON field inside the Tasker Bundle. AutoInput reads them directly at runtime — no device-specific DB lookup, so fresh UUIDs work on any device.

```xml
<parameters>{"endPoint":"X,Y","initialPoint":"X,Y","duration":"100","generatedValues":{}}</parameters>
```

Setting `initialPoint == endPoint` performs a tap (zero-distance swipe).

**Dialog button coordinates (Google Pixel 7a, 1080×2400, Android 16):**

| Dialog | Button | Coordinates |
|--------|--------|-------------|
| 1 "Are you sure?" | YES | (894, 2058) |
| 2 "Task already exists, overwrite?" | YES | (894, 1385) |
| 3 "Import To Project" | stayturgid row | (493, 1423) |
| 4 "Do you want to run?" | NO | (726, 1385) |

See `HANDOFF.md` → "AutoInput Gestures Bundle structure" for the full XML template.

**AutoInput Actions text-click (code 1732635924) — AVOID**

The text-click action requires a UUID that matches a config stored in AutoInput's on-device DB. This UUID is device-specific (must be created via the AutoInput UI) and cannot be constructed from scratch. Use the Gestures action instead for new click automations.

**Android 16 click mechanisms — what fails from Tasker's background process:**
- `uiautomator dump` / `input tap` — permission denied
- `sendevent` — SELinux blocks even with gid=1004
- `am broadcast FIRE_SETTING` with flat extras — AutoInput ignores (needs nested Bundle)

---

## Part 5b — Cross-device testing safety rules (discovered 2026-07-01)

### NEVER replace `enabled_accessibility_services` — always append

`settings put secure enabled_accessibility_services <value>` **replaces the entire list**. Running it with just one service wipes every other accessibility service on the device (screen readers, switch access, AutoInput, Tasker, Wispr Flow, Buzzkill — all gone silently).

**Protocol when you need to enable an accessibility service for testing:**

```bash
# 1. Save original list
ORIG=$(adb shell settings get secure enabled_accessibility_services)
echo "ORIG: $ORIG"

# 2. Append new service (do NOT replace)
adb shell settings put secure enabled_accessibility_services \
  "${ORIG}:com.example.app/com.example.app.MyService"

# 3. ... do testing ...

# 4. ALWAYS restore original list when done
adb shell settings put secure enabled_accessibility_services "$ORIG"
```

Also applies to any setting that is a colon-separated list:
`enabled_input_methods`, `enabled_notification_listeners`, etc.

**Verify current state before and after any accessibility change:**
```bash
adb shell settings get secure enabled_accessibility_services | tr ':' '\n'
```

If accessibility services are accidentally wiped, restore from a known-good list recorded at session start. The Pixel 7a's known-good list (as of 2026-07-01):
```
com.samruston.buzzkill/com.samruston.buzzkill.background.accessibility.WorkaroundAccessibilityService
net.dinglisch.android.taskerm/net.dinglisch.android.taskerm.MyAccessibilityService
com.joaomgcd.autoinput/com.joaomgcd.autoinput.service.ServiceAccessibilityV2
com.notch.touch/com.notch.touch.lock.tas
com.wispr.flowapp/com.wispr.flowapp.service.FlowAccessibilityService
```

Restore:
```bash
adb -s 35261JEHN12374 shell settings put secure enabled_accessibility_services \
  "com.samruston.buzzkill/com.samruston.buzzkill.background.accessibility.WorkaroundAccessibilityService:net.dinglisch.android.taskerm/net.dinglisch.android.taskerm.MyAccessibilityService:com.joaomgcd.autoinput/com.joaomgcd.autoinput.service.ServiceAccessibilityV2:com.notch.touch/com.notch.touch.lock.tas:com.wispr.flowapp/com.wispr.flowapp.service.FlowAccessibilityService"
```

### At the start of every session: snapshot device state

Before touching any device settings, record:
```bash
adb shell settings get secure enabled_accessibility_services
adb shell settings get secure default_input_method
adb shell settings get global package_verifier_enable
```
…and restore all of them at the end.

---

## Part 5b-s24 — Samsung Galaxy S24 specific setup (discovered 2026-07-01)

### Shizuku: "Start via Wireless debugging" fails on Samsung

Samsung's SSL implementation throws `javax.net.ssl.SSLProtocolException: SSLV3_ALERT_CERTIFICATE_UNKNOWN` when Shizuku tries to connect to the Wireless Debugging service on port ~38279. **Do not use "Start via Wireless debugging" on Samsung.**

Use **"Start by connecting to a computer"** instead:
1. Connect device via USB ADB
2. In Shizuku → Settings → "Start by connecting to a computer"
3. Tap "View command" to get the actual path (it changes per install), then run it from Mac:
   ```bash
   adb -s RFCX219CHKA shell /data/app/~~.../moe.shizuku.privileged.api-...=/lib/arm64/libshizuku.so
   ```
4. After Shizuku starts via ADB method, port 5555 does NOT auto-open. Manually trigger:
   ```bash
   adb -s RFCX219CHKA tcpip 5555
   ```

### Battery optimization blocks Shizuku toggles on Samsung

Before Shizuku's "Start on boot" and "Watchdog" toggles will respond:
```bash
adb shell dumpsys deviceidle whitelist +moe.shizuku.privileged.api
```
Then the toggles work.

### Termux: sshd requires explicit environment when started from runit or run-as

On Samsung (tested Android 16), sshd fails silently when started via runit (which uses minimal env). The `runsv sshd` process runs but sshd never actually starts.

**Root cause:** PATH does not include Termux's bin dir, so sshd's wrapper script can't find its deps.

**Fix for runit service** (`$PREFIX/var/service/sshd/run`):
```bash
#!/data/data/com.termux/files/usr/bin/bash
export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH
export HOME=/data/data/com.termux/files/home
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR=/data/data/com.termux/files/usr/tmp
export LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib
exec sshd -D -e 2>&1
```

**run-as with Termux:** Must provide full path to Termux bash AND set env:
```bash
adb -s RFCX219CHKA shell "run-as com.termux /data/data/com.termux/files/usr/bin/bash -c '
  export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:\$PATH
  export HOME=/data/data/com.termux/files/home
  export PREFIX=/data/data/com.termux/files/usr
  sshd
'"
```

**Termux:Boot script** (already includes env vars — see `termux/boot/start-adb.sh`).

### Tasker import on Samsung/Android 16: `am start -d content://` fails

On Samsung Android 16, `adb shell am start -d content://com.android.externalstorage...` to import Tasker XML files fails because UID 2000 (shell) cannot grant URI permissions for ExternalStorageProvider. The `--grant-read-uri-permission` flag doesn't help.

**Workaround for PROJECT import:** works via Tasker's built-in file picker:
```
Long-press project tab (home icon, bottom of Tasker screen) → Import Project → select file
```
Project file must be in `/sdcard/Tasker/projects/` first (push via ADB, it works fine).

**Workaround for TASK import:** Tasker doesn't have a built-in task file picker. Wrap the `.tsk.xml` in a proper project XML (with a `<Project>` element listing it), push as `.prj.xml` to `/sdcard/Tasker/projects/`, then import as a project:
```python
# Wrap task in project XML
prj_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<TaskerData sr="" dvi="1" tv="6.7.5-beta">
    <Project sr="proj0" ve="2">
        <cdate>TIMESTAMP_MS</cdate>
        <id>UUID</id>
        <name>ImportName</name>
        <tids>TASK_ID</tids>
    </Project>
    TASK_XML_HERE
</TaskerData>'''
```
The task's `sr` attribute must match the ID in `<tids>`. Avoids ID collision by using a high number (999).

### Tasker permissions needed on Samsung (grant via ADB)

```bash
adb shell pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS
adb shell pm grant net.dinglisch.android.taskerm android.permission.READ_PHONE_STATE
adb shell pm grant net.dinglisch.android.taskerm android.permission.READ_CALL_LOG
adb shell dumpsys deviceidle whitelist +net.dinglisch.android.taskerm
adb shell appops set net.dinglisch.android.taskerm MANAGE_EXTERNAL_STORAGE allow
```

### Termux packages: must match signing source

When Termux main app is installed from GitHub releases (via Obtainium), all add-ons must also come from GitHub — not F-Droid. Mixing sources causes `INSTALL_FAILED_SHARED_USER_INCOMPATIBLE`.

GitHub release pages:
- Termux:Boot — `github.com/termux/termux-boot/releases`
- Termux:API — `github.com/termux/termux-api/releases`  
- Termux:Tasker — `github.com/termux/termux-tasker/releases`

If Play Protect blocks the install: `adb shell settings put global package_verifier_enable 0` before installing, re-enable after.

### S24 Termux SSH access (for future sessions)

```bash
adb -s RFCX219CHKA shell "run-as com.termux /data/data/com.termux/files/usr/bin/bash -c '
  export PATH=/data/data/com.termux/files/usr/bin:\$PATH
  export HOME=/data/data/com.termux/files/home
  pkill sshd 2>/dev/null; sshd
'"
adb -s RFCX219CHKA forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 -o StrictHostKeyChecking=no localhost
```

After SSH is up, all further setup can be done cleanly without dealing with terminal background noise.

---

## Part 6 — Verification checklist

After a cold reboot and PIN unlock, wait ~60 seconds, then run from the Mac:

```bash
# 1. Check port 5555 is open (Shizuku TCP mode did its job)
adb -s 35261JEHN12374 shell "ss -tln 2>/dev/null | grep ':5555'"
# Expected: LISTEN line for :5555

# 2. Connect wirelessly
adb connect 192.168.68.62:5555
# Expected: "connected to 192.168.68.62:5555"

# 3. Check sshd is running (Termux:Boot did its job)
adb shell "ss -tln 2>/dev/null | grep ':8022'"
# Expected: LISTEN line for :8022

# 4. Check Shizuku process
adb shell "pgrep -f shizuku && echo SHIZUKU_OK"
# Expected: SHIZUKU_OK

# 5. SSH into Termux
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost "echo SSH_OK"
# Expected: SSH_OK
```

If port 5555 is not open after 60s:
- Check Shizuku is running: `adb shell pgrep -f shizuku`
- Check TCP mode is ON in Shizuku Settings
- Manually trigger: `adb shell "run-as com.termux sh -c 'adb tcpip 5555'"`

---

## Repo structure

```
tasker/
  stayturgid.prj.xml                    — full Tasker project XML
  ADB_Core_Watchdog.tsk.xml             — standalone task XML
  auto-update/
    stayturgid_update_check.tsk.xml     — update-check task (pre-configured for stayturgid)
    Task_Auto_Update.tsk.xml            — upstream original from TaskerNet (reference)
    README.md                           — auto-update integration docs
termux/boot/
  start-adb.sh                          — deploy to ~/.termux/boot/ on device
mac/
  adb-reconnect.sh                      — Mac keepalive script
  com.djbclark.stayturgid.adb-reconnect.plist  — launchd agent config
HACKING.md                              — this file
HANDOFF.md                              — AI session handoff prompt
README.md                               — user-facing setup guide
```
