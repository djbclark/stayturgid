# stayturgid — AI Handoff Document

> **Purpose:** This file is a prompt for an AI agent taking over development. Read it fully before doing anything else. It describes what the project does, the current state, the development environment, the tooling rules, and what's next.

---

## What this project does

**stayturgid** keeps wireless ADB (port 5555), Shizuku, and SSH alive on **two personal, unrooted consumer phones** — a Google Pixel 7a and a Samsung Galaxy S24 (SM-S921U1), both Android 16 — across cold reboots, and makes them reliably reachable from the Mac over Tailscale via **two independent, mutually-repairing methods (ADB + SSH)**.

After a reboot and PIN unlock:
1. **Shizuku** (thedjchi fork) auto-starts via Android Wireless Debugging and uses TCP mode to call `adb tcpip 5555` — this is what opens port 5555 without USB.
2. **Termux:Boot** fires `~/.termux/boot/start-adb.sh` → starts `sshd`, then loops self-healing sshd every 5 min.
3. **Tasker** `ADB_Boot_Restore` profile fires on boot → runs `ADB_Core_Watchdog` task.
4. **Tasker** `ADB_Interval_Check` profile runs `ADB_Core_Watchdog` every 20 min — checks port 5555, Shizuku process, sshd, and fires a notification if any fail.

On the Mac side, a launchd agent (`com.djbclark.stayturgid.adb-reconnect`) runs every 60 seconds and reconnects `adb connect <ip>:5555` if it drops, handling DHCP IP changes automatically.

---

## ✅ 7a Termux → GitHub/Obtainium swap — DONE 2026-07-05

The 7a's `com.termux` was the **googleplay build** while its addons were **F-Droid** → signature mismatch → `termux-api` dead (presence indicator + battery alarm were silent no-ops). Fixed by moving the **entire shared-uid Termux ecosystem to GitHub-debug builds** (all match each other) and tracking them in Obtainium.

**Final 7a state (all github-debug signed, all Obtainium-tracked for auto-update):** com.termux 0.118.3, com.termux.api 0.53.0, com.termux.boot 0.8.1, com.termux.tasker 0.9.0, com.termux.styling 0.32.1, com.termux.widget 0.15.0, com.termux.window(float) 0.17.0. `termux-api` now WORKS (verified: presence torch+notification fire, `termux-battery-status` ok). SSH restored (`ssh p7a`, key auth; **Termux uid changed u0_a590→u0_a591**, ssh config updated). sshd up, boot loop running.
- **`com.termux.gui` has NO GitHub release** → left uninstalled (can't share-uid-align it with github com.termux). `com.termux.x11` doesn't share the uid (stays, already Obtainium). Third-party termux apps (io.github.*, com.gardockt.*, com.maazm7d.*) don't share uid — left as-is.
- Backup of the old home: `~/stayturgid-device-backups/termux-home-7a-20260705-073847.tgz` + `7a-restore-stage/`.

**Reusable procedure (also in HACKING.md):** back up `$HOME` via SSH → `adb uninstall` all shared-uid com.termux.* → `gh release download` the `+github(-|.)debug` APKs (main is per-arch `arm64-v8a`, addons universal) → **disable Play Protect verifier** (`verifier_verify_adb_installs`/`package_verifier_enable`→0, `package_verifier_user_consent`→-1; **user-approved, restore all to 1 when done**) since Play Protect gates github-debug installs with a fingerprint prompt → `adb install` each → launch Termux (bootstrap), grant storage → `pkg install` + restore `.ssh`/`.termux/boot` + scripts → re-register Termux:Boot → add every app to Obtainium (`obtainium://add/github.com/termux/<repo>`) for auto-updates.

### New TODOs queued 2026-07-05 (do after the Termux swap + watchdog repairer)
1. **Update/republish the TaskerNet project** — the published share still has the old Custom Setting namespace bug (fixed in repo + on both devices). Re-export current `stayturgid` and republish to TaskerNet.
2. **Move version-detection off TaskerNet** — `stayturgid_update_check` should detect new versions from **GitHub** (raw `version.json` / releases), not TaskerNet. Remove the TaskerNet dependency entirely (was HANDOFF "Step 5").
3. **Smart phone-use presence/consent dialog** — before Claude uses a phone, **detect whether the user is actively using it** (screen on + recent interaction / foreground app not idle). If in use, pop a **30-second countdown dialog** (Tasker/`termux-dialog`) with **default = Continue** and three options: **(a) Let Claude use the phone (default on timeout)**, **(b) Pause — don't use this phone until Claude is explicitly told to continue on it**, **(c) Check again in 10 minutes**. This extends the current `claude-presence.sh` (which only announces) into a two-way consent gate per device. Note: needs working `termux-api` (so depends on TODO for the 7a Termux swap).

## 🧭 Roadmap & tooling decisions (2026-07-05)

**Immediate next steps (in order):**
1. **Adopt the Termux:Tasker plugin where helpful.** It's installed (`com.termux.tasker`, github build) but currently **unused** — our Tasker↔Termux link is file-based (Tasker reads `/sdcard/stayturgid_watchdog.log`, which the Termux boot loop writes every 5 min). The win: let the Tasker watchdog **call `stayturgid-repair.sh` directly via Termux:Tasker (stdin/stdout)** and read its **exit code in real time**, instead of acting on a log line up to 5 min stale. Needs `allow-external-apps=true` in `~/.termux/termux.properties` and the script in `~/.termux/tasker/`.
2. **Ansible-ify the Termux userland setup.** Turn the manual per-device rebuild (pkg install, restore `.ssh`, boot script, repair/presence scripts, Termux:Boot re-register) into an **idempotent playbook run over SSH/Tailscale**. Makes device rebuilds (like the 7a Termux swap) a one-command replay and scales to future devices. Scope = Termux userland only (the layer we control without root); OS-level bits stay with ADB/Shizuku/Obtainium.
3. **Add [SuperMonster003/AutoJs6](https://github.com/SuperMonster003/AutoJs6) as an ALTERNATIVE to Tasker+AutoInput** (user request 2026-07-05). AutoJs6 is a maintained Auto.js fork — a JavaScript automation engine using the Accessibility Service. Build a parallel AutoJs6 implementation of the watchdog/repair role so the user can run **either** Tasker+AutoInput **or** AutoJs6 — **no integration, no cross-fallback for now**. They must be **mutually exclusive / locked**: if one is active, the other must not be (e.g. only one accessibility-driven automation enabled at a time; a guard that disables/refuses the other). After building, **compare the two approaches** — technical pros/cons (robustness, element-finding vs coordinate taps, Git-friendliness, install/signature/Play-Protect, battery/background survival, Android-version resilience) and managerial pros/cons (maintainability, collaboration, versioning, learning curve, fork/maintenance risk). This is the **last** roadmap item.

**Tooling assessment (options considered, decisions made):**
- **Ansible over Termux/SSH** — ✅ adopting (see #2). Best-fit config management for the userland layer; prerequisites already in place (sshd + keys + Tailscale).
- **Termux:Tasker hybrid** — ✅ adopting (#1). We already use a variant (Tasker triggers + Termux scripts); the plugin tightens it.
- **Auto.js / AutoX** — ❌ not now. Overkill for our tiny UI-automation surface (one Shizuku "Start" tap); a second accessibility engine + fork-maintenance risk. Revisit only if UI automation grows into its own project.
- **MDM (Headwind / Esper / SOTI)** — ❌ wrong shape. Assumes Device-Owner provisioning (factory reset into a managed/kiosk state) — inappropriate for personal daily-driver phones. Only relevant for a fleet of dedicated devices.
- **Root (KernelSU / APatch)** — ❌ advised against. Would dissolve the Shizuku/AutoInput/Tasker-import fragility on the 7a, but the **S24 SM-S921U1 (US model) has a permanently locked bootloader → almost certainly can't be rooted**, giving an asymmetric fleet; and rooting the daily-driver 7a means bootloader unlock (factory reset) + likely Play Integrity breakage. Only worth it if a device is dedicated to automation.
- **Webkey / proprietary remote channels** — ❌ adds dependency more than robustness; we already have two independent channels (ADB + SSH over Tailscale). Prefer hardening cross-device mutual repair over a third proprietary relay.

**Recently completed (2026-07-05):**
- ✅ `tasker-io/` sub-project — reliable Tasker task import via the `ActivityImportTaskerDataFromXml` **intent** (text-button dialogs only), replacing the flaky delete-everything reimport dance. See `tasker-io/README.md`.
- ✅ 7a Tasker watchdog **repairer** (log-detect → notify → launch Shizuku → AutoInput-tap Start), catastrophic path validated.
- ✅ 7a Termux ecosystem moved to GitHub/Obtainium (termux-api works).

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

### S24 cold-reboot test — 2026-07-05 ✅ (Shizuku reboot survival FIXED)
Rebooted S24 over Tailscale, one PIN unlock, measured at 159s uptime — **everything self-healed with zero intervention:**

| Layer | Result |
|-------|--------|
| Shizuku | ✅ auto-started (BootCompleteReceiver fired — confirmed in `pm dump`, "Start reason: boot", 07:02:18) |
| Port 5555 | ✅ reopened (Shizuku TCP mode) |
| sshd :8022 | ✅ up (Termux:Boot) |
| Tailscale always-on | ✅ tun0 up right after unlock |
| Termux boot loop | ✅ running |

**What fixed it:** establishing Shizuku's persistent wireless-debugging pairing this session (`u0_a383@localhost / shizuku` now in Settings→Wireless debugging→Paired devices). The old "Shizuku doesn't survive reboot on Samsung" belief is obsolete. `adb_wifi_enabled` reads 0 after boot but 5555 is open anyway — the flag is cosmetic on Samsung; Shizuku opens 5555 via its own path. **Corollary: the watchdog's `Custom Setting adb_wifi_enabled=1` (act2) is a no-op on the S24** and secure-setting writes cannot enable the wireless-debugging *service* on Samsung (only the UI toggle does).

### Shizuku repair primitives (tested live 2026-07-05, for the watchdog rebuild)
- **Shizuku has its own process watchdog:** `kill shizuku_server` → respawns instantly (pid 16716→20329). Process crashes already self-heal.
- **shizuku_server runs as `shell` uid**, separate from the manager app (uid 10395) — survives `am force-stop moe.shizuku.privileged.api`. Very resilient.
- **Automation broadcasts** (from `pm dump`): START = `am broadcast -a moe.shizuku.privileged.api.START -n moe.shizuku.privileged.api/moe.shizuku.manager.receiver.ManualStartReceiver`; STOP = same with `.ManualStopReceiver` + action `.STOP`. **BUT they need the per-install auth token** (`View intents` screen shows `auth: <token>`, e.g. `H1wdWH0VlCSvZRi5WI2KkzOI`) — broadcasts without it are silently ignored (verified). Token changes on reinstall, so this path is fragile.
- **Proven auth-free restart (use this for the watchdog):** launch `moe.shizuku.privileged.api` MainActivity → AutoInput-tap the **"Start"** button (wireless-debugging start). Verified working earlier (started shizuku_server pid 3109, no SSL error). Button center on S24 (scrolled to top of that section): ~**(227,1977)** — recalibrate, it moves with scroll.
- Shizuku notification permission must be granted for the pairing/start flow (`pm grant moe.shizuku.privileged.api android.permission.POST_NOTIFICATIONS`).

### Repair channel CONFIRMED (tested 2026-07-05)
- **`adb -s localhost:5555 shell` from Termux = full shell uid 2000** (groups incl. `input`,`adb`,`log`). So while 5555 is open, the repair layer can run `input tap`, `settings put`, `setprop`, `am`, `svc` with shell privileges — **no AutoInput and no Shizuku auth token needed.** This is the primary repair channel.
- Shizuku automation **START/STOP broadcasts REQUIRE the per-install auth token even when sent as shell** (verified: without it → `auth_errors` notification, `notify(1450, channel=auth_errors)`). Don't rely on broadcasts.
- **Catastrophic case** (5555 closed AND Shizuku down): no shell reachable → only Tasker+AutoInput (tap Shizuku "Start") or a reboot recovers. This is the one place AutoInput is irreplaceable.
- Division of labor: **Termux layer** = `stayturgid-repair.sh` (sshd + shell-based repairs via localhost:5555, runs from boot loop + called by watchdog). **Tasker layer** = detection, notifications, and the AutoInput catastrophic fallback.

### TODO (queued): make Tasker import/export ROCK SOLID (own sub-project, reusable)
User directive 2026-07-05: the Tasker project import/export has been finicky all along (empty imports from XML comments, ghost projects from "Delete Contents", silent My Files failures). Build it into something rock-solid and **reusable across projects** — eventually spun out as its own separate project. Develop/test/debug it in a **dedicated sub-folder** here (e.g. `tasker-io/`) rather than against the live `stayturgid` project, so experiments can't corrupt the real one. Goal: a documented, tested, repeatable import/export procedure (or script) usable in any Tasker project. This is a *tail-end* item — after the watchdog repairer.

### ✅ Tasker watchdog repairer (7a) — BUILT + LIVE 2026-07-05
ADB_Core_Watchdog rebuilt as an 18-action repairer, imported into the live 7a project (clean reimport), verified: test run logged `[watchdog] port=open sshd=up fresh=FRESH` and correctly skipped repair/notify when healthy. Both profiles (ADB_Interval_Check interval + ADB_Boot_Restore boot) enabled.
- **Detection**: reads the Termux repair-loop STATUS from `/sdcard/stayturgid_watchdog.log` (avoids unreliable Tasker-uid process/socket visibility).
- **Catastrophic repair** (`%WD_PORT ~ CLOSED_NO_SHELL` = 5555 down + no shell): launch Shizuku → AutoInput-tap Start (227,1992) → notify. Only path that can recover when the Termux shell channel is gone.
- **Notify** on sshd-down and on stale repair-loop (>15 min = boot loop likely dead).
- Division of labor: Termux boot loop (5 min) does all shell repairs + logging; Tasker watchdog (20 min + boot) adds the AutoInput catastrophic recovery + user notifications.
- **Catastrophic path VALIDATED 2026-07-05** (via log-injection of `port=CLOSED_NO_SHELL`, boot loop paused): watchdog fired the notification "⚠ ADB 5555 down — auto-repairing (7a)", logged `[watchdog] port=CLOSED_NO_SHELL`, launched Shizuku, and the **AutoInput gesture tapped Start and restarted shizuku_server (pid changed) — 5555 stayed open**. First attempt revealed the AutoInput action aborts the task *after* it runs, so notify/log were reordered to run BEFORE the AutoInput block (AutoInput is the last action; an abort no longer suppresses the alert). Real-world caveat: AutoInput can't tap behind a locked screen — the notification still fires, and the boot loop keeps retrying shell repairs.

### Watchdog rebuild plan (detect → repair → re-check → notify) — DONE (see above)
Turn the notify-only watchdog into a repairer. Per subsystem: try layered repairs, re-check, notify ONLY if still down. Include AutoInput fallbacks even where not currently needed (per user).
1. **Port 5555 down:** (a) Termux `adb connect localhost:5555 && adb tcpip 5555`; (b) Shizuku START broadcast (best-effort); (c) AutoInput: launch Shizuku → tap "Start" (reopens 5555 via TCP mode).
2. **Shizuku down:** (a) START broadcast; (b) AutoInput launch+Start.
3. **sshd down:** Termux restart (the boot loop already self-heals; watchdog triggers as backup).
4. **Wireless-debugging service off (Samsung fallback, even if unneeded):** AutoInput open `ADB_WIRELESS_SETTINGS` → tap the toggle on.
5. Log every attempt to `/sdcard/stayturgid_watchdog.log`; notify with specific remaining-failure detail only after repairs fail.

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
**Name the specific phone(s)** you're about to use / done with — "Pixel 7a", "Galaxy S24", or both. Before any device interaction, output this as a standalone message (fill in the device):

**🚨📱🚨 USING — &lt;phone(s)&gt; 🚨📱🚨**

When done with those device(s) and not expecting to touch them again until the next user reply:

**✅📱✅ FREE — &lt;phone(s)&gt; ✅📱✅**

Both must be standalone — not buried in other text. If you pick up a second phone mid-run, announce it too.

### On-device presence indicator (CRITICAL — run alongside the announcement)
So it's obvious *from the phone itself* that automation is live, call the presence script at the start and end of each device session. It uses torch + vibration + an ongoing status-bar notification only — nothing on the screen surface, so it never interferes with UI dumps/taps/screenshots. (Screen flashing or color inversion WAS considered and rejected: overlays can cover tap targets and inversion corrupts screenshots.)

```bash
ssh s24 '~/claude-presence.sh on  "Galaxy S24"'   # 3 torch pulses + vibrate + ongoing "🤖 Claude is using ..." notification
ssh s24 '~/claude-presence.sh off "Galaxy S24"'   # removes notification + 2 pulses + vibrate
# same for p7a / "Pixel 7a"
```

Script lives at `termux/claude-presence.sh` in the repo and `~/claude-presence.sh` on each device. Pair `on` with the USING announcement and `off` with FREE. If SSH is down but ADB is up, run it via `adb -s <dev> shell "run-as ... claude-presence.sh on"` or just skip to the text announcement.

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

> **⚠️ This numbered section is historical (the original 2026-06-30 update-mechanism plan). For the CURRENT roadmap and priorities, see "🧭 Roadmap & tooling decisions (2026-07-05)" near the top of this file.** The steps below are kept for context on the auto-update work.

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
