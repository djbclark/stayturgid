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

## Current project status (as of 2026-07-05)

### Pixel 7a
- ✅ Port 5555 survives cold reboots (verified 2026-06-29)
- ✅ sshd survives cold reboots (Termux:Boot + self-heal loop)
- ✅ Tasker watchdog with failure notifications
- ✅ Mac-side launchd keepalive with macOS notification on reconnect/failure
- ✅ Published to TaskerNet: `https://taskernet.com/shares/?user=AS35m8lVOCqN0zylSnJKY8pBzCqkgDU8h624gr9CWqSAxD9myEt6n3OjyI4TtJhMtmw%2B&id=Project%3Astayturgid`
- ✅ Auto-update download+import task XML complete — uses **AutoInput Gestures** (coordinate taps) to click through 4 import dialogs
- ⚠️ Auto-update dialog sequence: **dialog 1 click confirmed working** (YES at 894,2058); dialogs 2–4 not yet confirmed end-to-end
- ⚠️ `stayturgid_update_check` daily trigger profile not yet committed to repo

**2026-07-05 session — 7a reconnected and repaired via Tailscale:**
- ✅ Reconnected via `100.65.230.108:38435` (Tailscale mDNS TLS endpoint), then reopened stable port 5555; health check green (Shizuku running, sshd up, port 5555 listening, battery 100%, 4 apps deviceidle-whitelisted)
- ✅ **Live project was 25 KB vs the repo's stale 4 KB** — exported the live version, committed it to `tasker/stayturgid.prj.xml` (was losing uncommitted Tasker work). Contains 2 profiles + 3 tasks (adds `TestUpdateTrigger`)
- ✅ **Custom Setting namespace bug fixed and reimported** (System→Global for adb_enabled/adb_wifi_enabled), verified in the Tasker editor showing Type=Global; both profiles re-enabled
- ⚠️ Repo project now differs from the **TaskerNet-published** copy (still has the old bug) — republish to TaskerNet when convenient
- Note: AutoInput crashed once mid-automation ("AutoInput keeps stopping") — recovered by dismissing and relaunching Tasker

### Samsung Galaxy S24 (RFCX219CHKA) — initial setup COMPLETE 2026-07-01
- ✅ Termux installed (GitHub signed), sshd running on port 8022
- ✅ Packages installed: openssh, android-tools, wget, git, python, curl, termux-api, runit
- ✅ `~/.termux/boot/start-adb.sh` deployed + Termux:Boot app opened (boot script will run on reboot)
- ✅ Termux runit sshd service fixed with proper env vars (PATH, HOME, PREFIX, TMPDIR, LD_LIBRARY_PATH)
- ✅ SSH key deployed to Termux `~/.ssh/authorized_keys`
- ✅ Tasker 6.7.5-beta installed + setup wizard complete + permissions granted
- ✅ stayturgid project imported (ADB_Boot_Restore, ADB_Interval_Check, ADB_Core_Watchdog)
- ✅ stayturgid_Update_Check task imported (lives in "UpdateCheck_Import" project as import workaround)
- ✅ Daily trigger profile created: Time 10:00AM–10:01AM → stayturgid_Update_Check
- ✅ Daily trigger profile renamed to "Daily_Update_Check" (no * prefix) — in stayturgid project
- ✅ stayturgid_Update_Check task is in "stayturgid" project alongside ADB_Core_Watchdog
- ⚠️ Shizuku "Start via Wireless debugging" fails on Samsung (SSL cert error) — currently no Shizuku on S24
- ⚠️ Without Shizuku, `adb tcpip 5555` must be triggered manually after each reboot (until a workaround is found)
- 🔲 AutoInput plugin not yet configured/tested on S24
- 🔲 End-to-end auto-update flow not tested on S24

### S24 session 2026-07-05 — verbose watchdog imported and VERIFIED WORKING
- ✅ **ADB_Core_Watchdog rewritten** (17 actions): timestamps, guarded Termux-adb call, port/Shizuku/sshd probes, file logging to `/sdcard/stayturgid_watchdog.log`, three separate verbose notifications with per-failure fix instructions
- ✅ **Root cause of watchdog never restoring ADB found**: old task wrote `adb_enabled`/`adb_wifi_enabled` with Custom Setting type **System** (arg0=2); both settings actually live in **Global**. Custom Setting arg0 mapping is **0=Global, 1=Secure, 2=System** (alphabetical dropdown order — HACKING.md "Tasker XML" section)
- ✅ Import verified: test run wrote correct log line AND flipped `global adb_wifi_enabled` 0→1 (wireless debugging re-enabled by the watchdog itself); all 3 notifications fired with correct titles
- ✅ Tasker granted `WRITE_SECURE_SETTINGS` (needed for Global/Secure writes)
- ✅ Tailscale added to Obtainium (github.com/tailscale/tailscale-android) and installed (`com.tailscale.ipn` v1.98.8); user signed in — S24 is **`dannys24` = `100.123.218.30`** on the tailnet (the `daniels-s24` entry is a stale 53-day-old registration, can be deleted in the admin console)
- ✅ **ADB over Tailscale verified**: `adb connect 100.123.218.30:5555`
- ✅ **Direct SSH over Tailscale verified**: `ssh -i ~/.ssh/termux_key -p 8022 djbclark@100.123.218.30` — no ADB forward needed (Android's WiFi SSH block doesn't apply to the tun interface)
- ✅ Battery-optimization exemptions added (deviceidle whitelist): Tailscale, Termux, Tasker
- ✅ `start-adb.sh` updated with `termux-wake-lock` + deployed to S24 via SSH-over-Tailscale (checksums verified); wake-lock acquired live
- ✅ `mac/adb-reconnect.sh` rewritten: takes `[serial] [lan_ip] [tailscale_ip]` args, tries cached → USB-discovered LAN → Tailscale in order; per-serial IP cache; S24 launchd agent installed + loaded (`com.djbclark.stayturgid.adb-reconnect-s24.plist`)
- ⚠️ S24 LAN IP is DHCP and **changed mid-session .63→.55** — never hardcode it; use the Tailscale IP
- ⚠️ Watchdog notification fix-text still references a hardcoded LAN IP — update to `100.123.218.30` on next watchdog XML revision
- ✅ Tailscale **Always-on VPN** enabled 2026-07-05 (verified: `settings get secure always_on_vpn_app` → `com.tailscale.ipn`); "Block connections without VPN" deliberately left OFF — it would sever LAN ADB/mDNS whenever the tunnel blips
- ⚠️ **2026-07-05 02:40: S24 at 17% battery and discharging — the USB data cable is NOT charging it.** Phone must live on a real charger or all remote access dies with the battery
- ✅ Pixel 7a XMLs Custom Setting namespace bug — **fixed in repo AND deployed to the 7a 2026-07-05** (reimported, verified Type=Global in editor). TaskerNet-published copy still stale — republish when convenient.

### Supervised cold-reboot test — Pixel 7a, 2026-07-05 ✅
Rebooted the 7a over Tailscale (no USB), user did a single PIN unlock, then measured recovery with no further intervention:

| Layer | Result |
|-------|--------|
| Tailscale (always-on VPN) | ✅ `tun0=100.65.230.108` up automatically after unlock — **always-on VPN is what makes the tailnet leg reboot-proof; enable it on every device** |
| sshd :8022 | ✅ up (Termux:Boot) |
| Shizuku | ✅ running |
| Termux boot loop | ✅ running |
| Port 5555 (wireless ADB) | ⚠️ DOWN at 206s, self-restored to LISTENING by ~338s (≈5.5 min post-boot). Recovers on its own, just not instantly |
| `adb_wifi_enabled` (global) | stayed 0 — cosmetic on Pixel; ADB via 5555 works regardless |

**Bottom line: after reboot + one unlock, the 7a is reachable via BOTH ADB-over-Tailscale and SSH-over-Tailscale within ~5–6 min, zero further intervention.** Enabling Tailscale always-on VPN on the 7a (was off — `always_on_vpn` was null; the S24 already had it) was the key fix this session.

### SSH access hardening 2026-07-05
- **1Password SSH-agent dialog eliminated for Termux hosts.** `~/.ssh/config` had a global `Host *` block forcing `IdentityAgent` to the 1Password agent, so every ssh (incl. to phones) popped a 1Password unlock. Added device blocks **above** `Host *` (first-match wins) for aliases **`s24`** and **`p7a`** (+ their Tailscale IPs / MagicDNS names) with `IdentityAgent none`, `IdentitiesOnly yes`, `IdentityFile ~/.ssh/termux_key`, `StrictHostKeyChecking no`. Now `ssh s24` / `ssh p7a` connect with no dialog; `ssh github.com` etc. still use 1Password (git untouched).
- **7a Termux key deploy:** the 7a's Termux never had this Mac's key in `authorized_keys` (S24 did). `run-as` is blocked (7a Termux is a non-debuggable build) and RunCommandService wasn't reachable, so deployed via `/sdcard`: `adb push termux_key.pub /sdcard/Download/`, grant Termux `READ_EXTERNAL_STORAGE`, then a Termux one-liner appended it. Both phones now have working SSH. (Note: Termux sshd ignores the login username — `ssh djbclark@` and `ssh u0_aXXX@` both authenticate by key.)
- Quick connect now: **`ssh s24`** / **`ssh p7a`** (no flags needed).

### Remote-access hardening implemented 2026-07-05 (session 2)
- ✅ **mDNS TLS fallback** added to `adb-reconnect.sh` — discovers `adb-<SERIAL>-xxxx._adb-tls-connect._tcp` via `adb mdns services`; reconnects after reboot with no USB / no port 5555 (as long as this host is paired). Candidate order now: cached → USB-discovered LAN → mDNS TLS → Tailscale.
- ✅ **7a reconnect launchd agent** updated with its real LAN + Tailscale IPs (was running arg-less/default before).
- ✅ **Dead-man's switch**: `mac/access-monitor.sh` + `com.djbclark.stayturgid.access-monitor.plist` (every 5 min). Checks every ADB address AND an SSH port-8022 probe per device; fires a macOS notification (with sound) only after ~10 min of total outage across ALL paths, and once on recovery. Per-device consecutive-fail state in `~/.config/stayturgid/access-monitor/`. Installed + loaded; tested (both devices reachable → counters 0).
- ✅ **Low-battery alarm** in `termux/boot/start-adb.sh` self-heal loop: `termux-battery-status` every 5 min; if ≤30% and not charging → `termux-notification` (max priority) + `termux-toast`, auto-cleared on recovery. Deployed to S24 + loop restarted live; notification/toast/remove path tested working. **Rationale: Tasker can't reliably read charging state; Termux:API can.**
- 🔲 Same battery alarm + `termux-wake-lock` boot script not yet redeployed to the 7a (its boot script predates these edits).
- 🔲 Watchdog Tailscale probe (check tun0 / ping 100.100.100.100, relaunch app if down) — next watchdog revision

S24 Tasker project snapshot saved to `tasker/s24_stayturgid.prj.xml` (separate from the Pixel 7a's `tasker/stayturgid.prj.xml` — S24 has different internal task/profile IDs).

### Remote-access resilience plan (S24) — target: ≥2 independent methods, each able to repair the other

| # | Method | Path | Depends on | Can repair |
|---|--------|------|-----------|------------|
| 1 | ADB over WiFi | `adb connect <ip>:5555` | port 5555 open (Shizuku TCP / `adb tcpip`), `adb_enabled`+`adb_wifi_enabled` global settings | restart sshd (via Tasker intent / Termux:Boot), fix Tasker, reinstall apps |
| 2 | SSH to Termux | `ssh -p 8022` (currently only via ADB forward; direct once Tailscale is up) | sshd running, Termux alive | re-open port 5555 (`adb tcpip` via Termux android-tools + Wireless-Debugging pair, or Shizuku `rish settings put …`) |
| 3 | On-device auto-repair | Tasker watchdog every 20 min + boot | Tasker + WRITE_SECURE_SETTINGS | re-enables adb settings, notifies user with manual fix steps |

**Hardening still to do (in order):**
1. **Finish Tailscale sign-in** → both methods get a stable `100.x` IP, reachable off-LAN; SSH no longer needs the ADB forward (Android's WiFi firewall doesn't apply to the tun interface)
2. Tailscale settings: enable **Always-on VPN** (Android Settings → VPN → gear) so it survives reboots
3. Battery-optimization exemptions for Tailscale, Termux, Tasker (`Settings → Apps → … → Battery → Unrestricted`) so Doze can't kill any leg
4. `termux-wake-lock` in `~/.termux/boot/start-adb.sh`, and run sshd under runit (already installed) for auto-restart
5. Add a Tailscale probe to the watchdog (check `tun0` / ping `100.100.100.100`, notify + `am start` Tailscale if down)
6. Extend `mac/adb-reconnect.sh` to fall back to the Tailscale IP when the LAN IP fails
7. Deploy the same stack to the Pixel 7a when it's back in scope

**Current import action sequence (act20–act43):**
- act20: Run Shell `mkdir -p /sdcard/Tasker/Updates`
- act21: HTTP Request GET `%raw_xml_url` → file save `Tasker/Updates/stayturgid_update_check.tsk.xml`
- act22: Wait 1s
- act23: Run Shell `am start -n net.dinglisch.android.taskerm/...ActivityImportTaskerDataFromXml -d "content://...Tasker%2FUpdates%2Fstayturgid_update_check.tsk.xml"` (content:// URI required on Android 10+; file:// silently fails)
- act24: Wait 3s
- act25: **AutoInput Gestures** tap (894, 2058) — dialog 1 "Are you sure?" YES ✅ **CONFIRMED WORKING**
- act37: Wait 2s
- act38: **AutoInput Gestures** tap (894, 1385) — dialog 2 "Task already exists, overwrite?" YES
- act39: Wait 2s
- act40: **AutoInput Gestures** tap (493, 1423) — dialog 3 "Import To Project" → stayturgid row
- act41: Wait 2s
- act42: **AutoInput Gestures** tap (726, 1385) — dialog 4 "Do you want to run?" NO
- act43: Wait 1s
- act28: Go Home
- act29: Delete File `%http_file_output`
- act30: End If

---

## Repository

- **Mac path:** `~/stayturgid/`
- **GitHub:** `github.com/djbclark/stayturgid` (private)
- **Branch:** `master`
- **Transport:** HTTPS via `gh` CLI credential helper (switched from SSH 2026-07-05; `gh auth login` web flow, GitHub account uses Google SSO).
- **Commit signing:** dedicated signing-only key `~/.ssh/git_signing_key` (passphrase-less, registered on GitHub as a signing key, `verified: true` confirmed) — fully autonomous, no 1Password prompt. The old 1Password key stays registered so past commits remain Verified. `gpg.ssh.allowedSignersFile=~/.ssh/allowed_signers` enables local `git log --show-signature`.
- **Working directory for AI sessions:** `~/upmon-handoff/` (legacy name, kept as-is)

---

## Device facts

### Google Pixel 7a (primary)

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

### Samsung Galaxy S24 (secondary — setup in progress)

| Field | Value |
|-------|-------|
| Device | Samsung Galaxy S24 (SM-S921U1) |
| Android | 16 (SDK 36) |
| USB serial | `RFCX219CHKA` |
| Wireless ADB | **preferred: `adb connect 100.123.218.30:5555` (Tailscale, stable)**; LAN IP is DHCP (was .63, then .55 — do not hardcode). Port 5555 opened via `adb tcpip 5555` over USB; Shizuku thedjchi "Start via Wireless debugging" still fails on Samsung, so 5555 does not survive reboot yet |
| Tailscale | `com.tailscale.ipn` v1.98.8 via Obtainium; tailnet name `dannys24`, IP `100.123.218.30`; signed in as djbclark@gmail.com |
| SSH (direct) | `ssh -i ~/.ssh/termux_key -p 8022 djbclark@100.123.218.30` — works over Tailscale with no ADB forward |
| SSH to Termux | `adb -s RFCX219CHKA forward tcp:8022 tcp:8022` then `ssh -i ~/.ssh/termux_key -p 8022 -o StrictHostKeyChecking=no localhost` |
| Tasker | `net.dinglisch.android.taskerm` v6.7.5-beta |
| Shizuku | NOT installed / functional (thedjchi TCP mode doesn't work on Samsung — SSL error) |
| Termux | `com.termux` (GitHub signed — from Obtainium) |
| Termux:Boot | `com.termux.boot` (GitHub signed) |
| Termux:API app | `com.termux.api` (GitHub signed) |
| Termux:Tasker | `com.termux.tasker` (GitHub signed) |
| AutoInput | installed but not yet configured |

S24 Termux SSH quick connect:
```bash
adb -s RFCX219CHKA shell "run-as com.termux /data/data/com.termux/files/usr/bin/bash -c '
  export PATH=/data/data/com.termux/files/usr/bin:\$PATH
  export HOME=/data/data/com.termux/files/home
  pkill sshd 2>/dev/null; sshd
'"
adb -s RFCX219CHKA forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null localhost
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

- **Raw ADB fallback (verified reliable 2026-07-05):** when the uiautomator2 service (or any higher-level tool) breaks — e.g. after `adb tcpip` restarts adbd — this loop always works and needs nothing on the device:
  ```bash
  adb shell uiautomator dump /sdcard/ui.xml          # element tree with text + bounds
  adb shell cat /sdcard/ui.xml | <parse bounds>      # centre = ((x1+x2)/2, (y1+y2)/2)
  adb shell input tap X Y                            # tap / input swipe X Y X Y 1000 = long-press
  adb exec-out screencap -p > /tmp/screen.png        # visual check
  ```
  Caveats: one dump per step (slow, ~2s); coordinates shift between selection modes (Tasker's top-bar buttons move as selection count changes — re-dump before every tap); `input swipe` same-point with duration is the long-press idiom.

- **Maestro mobile exception:** If uiautomator2 can't find an element that should be there, or a tap isn't registering, use Maestro (`~/.maestro/bin/maestro --udid 35261JEHN12374`) as a diagnostic to rule out tool bugs vs app state. Always tell the user: (1) why uiautomator2 wasn't sufficient, (2) what Maestro was used for, (3) what the result was. **Known Maestro failure mode (2026-07-05): its gRPC channel dies permanently when adbd restarts (`adb tcpip`) or the device reconnects — `StatusRuntimeException: UNAVAILABLE`, `Unable to launch app`. Fall back to raw ADB rather than restarting Maestro mid-task.**

- **Keeping the device awake during automation:** `adb shell svc power stayon true` (screen stays on while powered; set `false` when done). The lock screen after adbd restart still needs a manual PIN — plan around it: do everything needing UI in one unlocked window.

- **scrcpy (installed, v4.0):** live screen mirror + control from the Mac. Best tool for watching automation in real time and for manual intervention without picking up the phone; works over the same ADB connection (`scrcpy -s RFCX219CHKA`, or `scrcpy -s 100.123.218.30:5555` over Tailscale). `--stay-awake` keeps the screen on while mirroring.

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

`stayturgid_update_check.tsk.xml` uses a fully local XML flow — no TaskerNet servers at install time, only for version detection.

### How it works

1. `act6` (JavaScript) sets local variables from `updaterData`: `%taskernet_url`, `%raw_xml_url`, `%version`, `%changelog`
2. `act9` (JavaScript) builds the TaskerNet API URL → `%taskernet_xml`
3. `act10` (HTTP Request) fetches TaskerNet JSON (returns project XML embedded in JSON)
4. `act11` (Regex Match) extracts `"version": "..."` from that JSON
5. `act13` (JavaScript) compares `%version` to `%taskernet_version`; sets `%updatestatus`
6. If update available: sticky notification with Update / Skip buttons (callbacks with `par1=user_input`, `par2=update` or `par2=skip`)
7. **Update path:** see current action sequence in "Current project status" above
8. **Skip path (act31+):** cancel notification, flash "Skipped...", stop

**TestUpdateTrigger** (on-device helper task): calls `stayturgid_Update_Check` with `par1=user_input, par2=update`, which bypasses the version check and forces the update download+import path. Useful for testing without bumping version.json. Do NOT delete from device until e2e is confirmed.

### Android 16 click mechanism — what works and what doesn't

**Confirmed BROKEN from Tasker's background process on Android 16:**
- `uiautomator dump` — permission denied
- `input tap X Y` — permission denied  
- `sendevent /dev/input/eventN` — SELinux blocks even with gid=1004 (input group)
- `am broadcast FIRE_SETTING` with flat string extras — AutoInput ignores; requires nested Bundle which `am broadcast --es` cannot provide

**CONFIRMED WORKING:**
- **AutoInput Gestures** (plugin code `778682267`, plugintypeid `com.joaomgcd.autoinput.intent.IntentGestures`) — uses AutoInput's AccessibilityService to perform touch gestures. **Coordinates are stored INLINE** in the `parameters` JSON field inside the Tasker Bundle — NOT looked up from AutoInput's DB by UUID. This means fresh UUIDs work, no per-device DB setup needed.

### Import dialog coordinates (Google Pixel 7a, 1080×2400, Android 16)

| Dialog | Text | Button | Coordinates |
|--------|------|--------|-------------|
| 1 | "Are you sure?" | YES | (894, 2058) — bounds [810,1987][978,2129] |
| 2 | "Task already exists, overwrite?" | YES | (894, 1385) — bounds [810,1314][978,1456] |
| 3 | "Import To Project" | stayturgid row | (493, 1423) — bounds [101,1360][885,1486] |
| 4 | "Do you want to run?" | NO | (726, 1385) — bounds [642,1314][810,1456] |

Dialog 3 (Import To Project) position depends on how many Tasker projects exist and their order. If the device has projects in a different order, (493, 1423) may land on the wrong row — use AutoInput text-click instead for robustness (requires UI config to get the UUID).

**JINA Drawer overlay gotcha:** The JINA Drawer sidebar handle sits at [1018,118][1080,387]. This overlaps the Tasker ⋮ menu button at [975,128][1080,254]. Clicking x=1027 hits the JINA handle and silently fails. Click x≈985 instead.

### AutoInput Gestures Bundle structure (full XML)

```xml
<Action sr="actN" ve="7">
    <code>778682267</code>
    <Bundle sr="arg0">
        <Vals sr="val">
            <EnableDisableAccessibilityService>&lt;null&gt;</EnableDisableAccessibilityService>
            <EnableDisableAccessibilityService-type>java.lang.String</EnableDisableAccessibilityService-type>
            <GestureType>0</GestureType>
            <GestureType-type>java.lang.String</GestureType-type>
            <Password>&lt;null&gt;</Password>
            <Password-type>java.lang.String</Password-type>
            <com.twofortyfouram.locale.intent.extra.BLURB>Gesture Type: Swipe
Start Point: X,Y
End Point: X,Y
Duration: 100</com.twofortyfouram.locale.intent.extra.BLURB>
            <com.twofortyfouram.locale.intent.extra.BLURB-type>java.lang.String</com.twofortyfouram.locale.intent.extra.BLURB-type>
            <net.dinglisch.android.tasker.JSON_ENCODED_KEYS>parameters</net.dinglisch.android.tasker.JSON_ENCODED_KEYS>
            <net.dinglisch.android.tasker.JSON_ENCODED_KEYS-type>java.lang.String</net.dinglisch.android.tasker.JSON_ENCODED_KEYS-type>
            <net.dinglisch.android.tasker.RELEVANT_VARIABLES>... (copy from existing action)</net.dinglisch.android.tasker.RELEVANT_VARIABLES>
            <net.dinglisch.android.tasker.RELEVANT_VARIABLES-type>[Ljava.lang.String;</net.dinglisch.android.tasker.RELEVANT_VARIABLES-type>
            <net.dinglisch.android.tasker.extras.VARIABLE_REPLACE_KEYS>parameters GestureType plugininstanceid plugintypeid </net.dinglisch.android.tasker.extras.VARIABLE_REPLACE_KEYS>
            <net.dinglisch.android.tasker.extras.VARIABLE_REPLACE_KEYS-type>java.lang.String</net.dinglisch.android.tasker.extras.VARIABLE_REPLACE_KEYS-type>
            <net.dinglisch.android.tasker.subbundled>true</net.dinglisch.android.tasker.subbundled>
            <net.dinglisch.android.tasker.subbundled-type>java.lang.Boolean</net.dinglisch.android.tasker.subbundled-type>
            <parameters>{"endPoint":"X,Y","initialPoint":"X,Y","duration":"100","generatedValues":{}}</parameters>
            <parameters-type>java.lang.String</parameters-type>
            <plugininstanceid>ANY-FRESH-UUID-WORKS</plugininstanceid>
            <plugininstanceid-type>java.lang.String</plugininstanceid-type>
            <plugintypeid>com.joaomgcd.autoinput.intent.IntentGestures</plugintypeid>
            <plugintypeid-type>java.lang.String</plugintypeid-type>
        </Vals>
    </Bundle>
    <Str sr="arg1" ve="3">com.joaomgcd.autoinput</Str>
    <Str sr="arg2" ve="3">com.joaomgcd.autoinput.activity.ActivityConfigGestures</Str>
    <Int sr="arg3" val="60"/>
    <Int sr="arg4" val="1"/>
</Action>
```

A zero-distance swipe (initialPoint = endPoint) acts as a tap. Set X,Y in both the BLURB and the `parameters` JSON. The `plugininstanceid` UUID does not need to match any stored AutoInput config — coordinates are read directly from the inline `parameters` field.

### Discovered Tasker action codes and arg layouts

All confirmed from live Tasker 6.7.5-beta exports.

| Action | Code | Key args |
|--------|------|----------|
| Wait | 30 | arg0=ms, **arg1=seconds**, arg2=minutes, arg3=hours, arg4=days |
| Run Shell | 123 | arg0=command, arg1=root(0/1), arg2=timeout, arg3=output_var, arg6=1(store) |
| HTTP Request | 339 | arg1=method(0=GET), arg2=URL, arg7=file_save_path, arg8=timeout |
| JavaScript | 129 | arg0=script |
| Task Stop | 137 | arg0=0(normal) |
| Go Home | 25 | arg0=page(0=main) |
| Delete File | 406 | arg0=path, arg1=0 |
| End If | 40 | (no args) |
| Else/If | 39 | arg0=variable, arg1=value, arg2=comparison |
| AutoInput Gestures | **778682267** | arg0=Bundle (see above), arg1=`com.joaomgcd.autoinput`, arg2=`...ActivityConfigGestures`, arg3=60, arg4=1 |
| AutoInput Actions (text-click) | **1732635924** | requires stored DB config keyed by UUID — avoid; use Gestures instead |

**Wait arg critical gotcha:** arg1=seconds, arg2=**minutes**. Setting arg2=3 gives 3 minutes, not 3 seconds!

**am start content:// URI (Android 10+):** `file://` URIs fail silently for import. Use the content:// provider form:
```
am start -n "net.dinglisch.android.taskerm/com.joaomgcd.taskerm.datashare.import.ActivityImportTaskerDataFromXml" \
  -a android.intent.action.VIEW \
  -d "content://com.android.externalstorage.documents/document/primary%3ATasker%2FUpdates%2Fstayturgid_update_check.tsk.xml" \
  -t "text/xml" --grant-read-uri-permission
```

**Tasker project export (for pulling current in-memory state):** ADB backup (`adb backup net.dinglisch.android.taskerm`) returns empty 47-byte file — both Tasker and AutoInput have `allowBackup=false`. Use: long-press project tab in Tasker → Export → XML to Storage → saves to `/sdcard/Tasker/projects/<name>.prj.xml`.

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

## Pixel 7a accessibility state — verify at session start

Known-good `enabled_accessibility_services` (as of 2026-07-01):
```
com.samruston.buzzkill/com.samruston.buzzkill.background.accessibility.WorkaroundAccessibilityService
net.dinglisch.android.taskerm/net.dinglisch.android.taskerm.MyAccessibilityService
com.joaomgcd.autoinput/com.joaomgcd.autoinput.service.ServiceAccessibilityV2
com.notch.touch/com.notch.touch.lock.tas
com.wispr.flowapp/com.wispr.flowapp.service.FlowAccessibilityService
```

At the start of each session, verify these are all still enabled:
```bash
adb shell settings get secure enabled_accessibility_services | tr ':' '\n'
```

⚠️ A previous session accidentally wiped accessibility services by running `settings put secure enabled_accessibility_services <value>` which **replaces** (not appends) the list. If any are missing, restore with the full colon-separated list above. See HACKING.md Part 5b for the safe append protocol.

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

### ✅ Step 1b — S24 initial setup (COMPLETE as of 2026-07-01)

Termux, sshd, packages, Tasker, stayturgid project, update check task, and daily trigger all set up on S24. See "Current project status → Samsung Galaxy S24" section above for details and remaining gaps.

### Step 2 — Confirm full 4-dialog gesture sequence (CURRENT NEXT STEP — Pixel 7a)

Dialog 1 (YES at 894,2058) is confirmed working. The full 4-dialog flow in the task has not been observed end-to-end yet.

**To test:** Run `TestUpdateTrigger` from Tasker UI (it passes `par1=user_input, par2=update` which bypasses version check). Watch with uiautomator2:

```python
import sys, time
sys.path.insert(0, '/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages')
import uiautomator2 as u2
import xml.etree.ElementTree as ET, subprocess

d = u2.connect('35261JEHN12374')
subprocess.run(['adb', '-s', '35261JEHN12374', 'shell', 'am', 'broadcast',
    '-a', 'net.dinglisch.android.tasker.ACTION_TASK', '-e', 'task_name', 'TestUpdateTrigger'])
for i in range(30):
    time.sleep(1)
    root = ET.fromstring(d.dump_hierarchy())
    texts = {e.get('text','') for e in root.iter() if e.get('text')}
    if any(t in texts for t in ('YES','NO','Import')):
        print(f"t={i+1}: DIALOG: {texts & {'YES','NO','Import','OK'}}")
```

Verify all 4 dialogs are auto-clicked and the task completes cleanly (Tasker TASKS tab still shows `stayturgid_Update_Check`; no import dialog stuck on screen; `/sdcard/Tasker/Updates/` empty after).

**If dialog 3 fails** (Import To Project tap lands on wrong row): coordinate (493,1423) assumes stayturgid is at a specific row. If there are more Tasker projects on the device, the row position may differ. Fix: configure an AutoInput text-click action (code 1732635924) via the Tasker/AutoInput UI to click "stayturgid" by text, extract its UUID from a task export, and replace act40 with that action.

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
