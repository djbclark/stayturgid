# stayturgid — AI Handoff Document

> **Purpose:** This file is a prompt for an AI agent taking over development. Read it fully before doing anything else. It describes what the project does, the current state, the development environment, the tooling rules, and what's next.

> **Modular docs:** Each subfolder is usable on its own. Human-readable index: [docs/README.md](docs/README.md) · [README.md](README.md)

---

## What this project does

**stayturgid** keeps wireless ADB (port 5555), Shizuku, and SSH alive on **two personal, unrooted consumer phones** — a Google Pixel 7a and a Samsung Galaxy S24 (SM-S921U1), both Android 16 — across cold reboots, and makes them reliably reachable from the Mac over Tailscale via **two independent, mutually-repairing methods (ADB + SSH)**.

After a reboot and PIN unlock:
1. **Shizuku** (thedjchi fork) auto-starts via Android Wireless Debugging and uses TCP mode to call `adb tcpip 5555` — this is what opens port 5555 without USB.
2. **Termux:Boot** fires `~/.termux/boot/start-adb.sh` → starts `sshd`, then loops self-healing sshd every 5 min.
3. **AutoJs6** `main.js` (20 min interval + boot via `boot-launcher.js`) → Termux `RUN_COMMAND` → `stayturgid-repair.sh`, notifications, Shizuku UI repair if needed.

On the Mac side, a launchd agent (`com.djbclark.stayturgid.adb-reconnect`) runs every 60 seconds and reconnects `adb connect <ip>:5555` if it drops, handling DHCP IP changes automatically.

---

## ✅ Tasker removed from stayturgid (2026-07-06)

**Done in repo:** Deleted `tasker/`, `tasker-io/`, Termux:Tasker wrapper, Tasker auto-update tasks, Maestro Tasker playbooks, and all stayturgid code paths that installed or configured Tasker/AutoInput. **Both fleet phones** use **AutoJs6 only** for the watchdog.

**On devices:** stayturgid Tasker project files purged via `autojs6/mac/purge-stayturgid-from-tasker.sh`. Tasker/AutoInput/Termux:Tasker **remain installed** for the user's other projects — stayturgid does not uninstall them.

**Updates without Tasker:** Bump `version.json`, push to GitHub, run `./ansible/mac/deploy-termux.sh` and `./autojs6/mac/deploy.sh` from the Mac. Optional on-device notifier: `termux/check-repo-version.sh`.

### Ongoing goal: zero Tasker footprint (research)

| Scope | Status | Notes |
|-------|--------|-------|
| stayturgid **codebase** | ✅ Achieved 2026-07-06 | No Tasker XML, tasker-io, or Termux:Tasker bridge in repo |
| stayturgid **config on devices** | ✅ Achieved | Watchdog = AutoJs6; stayturgid exports removed from `/sdcard/Tasker/` |
| **Uninstall Tasker** from phones | ❌ Out of scope | User may use Tasker for unrelated automation; stayturgid must not touch it |
| **Uninstall Termux:Tasker** addon | Optional | Only needed if nothing else uses `~/.termux/tasker/`; safe to keep installed |
| **Uninstall AutoInput** | Optional | Not required by stayturgid; other Tasker projects may still use it |

**Why Tasker was in stayturgid historically**

1. **Watchdog** — periodic repair + Shizuku catastrophic UI tap. Replaced by AutoJs6 (`autojs6/`), validated on S24 2026-07-05 and rolled to 7a 2026-07-06.
2. **Auto-update** — `stayturgid_Update_Check` downloaded task XML from GitHub and drove four Tasker import dialogs via AutoInput gestures. **Removed** — fragile (dialog Y coords drifted; only one AutoInput gesture per Tasker task run; text-click needed per-device UUIDs). Replaced by Mac-side Ansible + `version.json` + optional Termux notification script.
3. **Termux:Tasker bridge** — real-time `%stdout` from repair script. Replaced by AutoJs6 `RUN_COMMAND` (primary) and `repair-bridge.sh` (fallback).

**What would be needed for “never install Tasker for stayturgid” (already true post-2026-07-06)**

Nothing further in software — new phones follow `autojs6/mac/setup-autojs6.sh` only.

**What would be needed to delete Tasker from the phones entirely**

Not a stayturgid concern. User deletes other Tasker projects manually, then uninstalls Tasker from Settings.

**External bugs that blocked Tasker-based auto-update (why we deleted it rather than fix)**

| Issue | Component | Impact |
|-------|-----------|--------|
| Dialog button Y coords change with nav bar / UI | Tasker import Activity | AutoInput gesture missed → “User cancelled” |
| Only first AutoInput **Gestures** action runs per task | AutoInput + Tasker | Dialogs 2–4 never tapped in one task |
| Text-click actions need UUID in AutoInput DB | AutoInput PerformAction | Not portable in Git XML |
| Samsung blocks intent import from `adb shell` | Tasker on S24 | Mac `tasker-io` required for imports anyway |

None of these affect the AutoJs6 stack.

---

## ✅ 7a Termux → GitHub/Obtainium swap — DONE 2026-07-05

The 7a's `com.termux` was the **googleplay build** while its addons were **F-Droid** → signature mismatch → `termux-api` dead (presence indicator + battery alarm were silent no-ops). Fixed by moving the **entire shared-uid Termux ecosystem to GitHub-debug builds** (all match each other) and tracking them in Obtainium.

**Final 7a state (all github-debug signed, all Obtainium-tracked for auto-update):** com.termux 0.118.3, com.termux.api 0.53.0, com.termux.boot 0.8.1, com.termux.tasker 0.9.0, com.termux.styling 0.32.1, com.termux.widget 0.15.0, com.termux.window(float) 0.17.0. `termux-api` now WORKS (verified: presence torch+notification fire, `termux-battery-status` ok). SSH restored (`ssh p7a`, key auth; **Termux uid changed u0_a590→u0_a591**, ssh config updated). sshd up, boot loop running.
- **`com.termux.gui` has NO GitHub release** → left uninstalled (can't share-uid-align it with github com.termux). `com.termux.x11` doesn't share the uid (stays, already Obtainium). Third-party termux apps (io.github.*, com.gardockt.*, com.maazm7d.*) don't share uid — left as-is.
- Backup of the old home: `~/stayturgid-device-backups/termux-home-7a-20260705-073847.tgz` + `7a-restore-stage/`.

**Reusable procedure (also in HACKING.md):** back up `$HOME` via SSH → `adb uninstall` all shared-uid com.termux.* → `gh release download` the `+github(-|.)debug` APKs (main is per-arch `arm64-v8a`, addons universal) → **disable Play Protect verifier** (`verifier_verify_adb_installs`/`package_verifier_enable`→0, `package_verifier_user_consent`→-1; **user-approved, restore all to 1 when done**) since Play Protect gates github-debug installs with a fingerprint prompt → `adb install` each → launch Termux (bootstrap), grant storage → `pkg update && pkg upgrade -y` then `pkg install …` (always update+upgrade before install) + restore `.ssh`/`.termux/boot` + scripts → re-register Termux:Boot → add every app to Obtainium (`obtainium://add/github.com/termux/<repo>`) for auto-updates.

### New TODOs queued 2026-07-05 (do after the Termux swap + watchdog repairer)
1. **Update/republish the TaskerNet project** — the published share still has the old Custom Setting namespace bug (fixed in repo + on both devices). Re-export current `stayturgid` and republish to TaskerNet. **Optional** — auto-update no longer depends on TaskerNet.
2. **Move version-detection off TaskerNet** — ✅ **DONE 2026-07-05:** `version.json` at repo root; `stayturgid_Update_Check` fetches GitHub raw URL (`version_check_url` in `act6`). Bump `version.json` + `act6` on release; push to `master`. TaskerNet removed from detection path.
3. **Smart phone-use presence/consent dialog** — ✅ S24 implemented 2026-07-05 in `termux/claude-presence.sh gate`: detects interactive screen + non-idle foreground package, shows a 30s `termux-dialog` prompt (timeout=Continue), supports Pause (`resume` clears) and Check-again-in-10-min. Deployed via Ansible; 7a can receive the same script when that track resumes.
4. **LAST (research only — do not refactor yet):** Evaluate unified orchestration under Ansible; **prioritize moving Termux package management** and design generic **`obtainium_app` / `google_play_app`** modules. See **"Architecture research — unified orchestration"** at the bottom of this file. No implementation until explicitly approved.

## 🧭 Roadmap & tooling decisions (2026-07-05)

**Immediate next steps (in order):**
1. **Termux:Tasker — ✅ RUNTIME-VALIDATED on 7a 2026-07-05 (USB).** The watchdog is now **v3**: act0 calls `stayturgid-repair` via the Termux:Tasker plugin (action code `1256900802`, exact format from the official `termux-tasker` template — fetched, not guessed) and reads `%stdout` (STATUS line) + `%result` (exit code) in **real time** each cycle, instead of a log line up to 5 min stale. Bridge set up: `allow-external-apps=true` in `~/.termux/termux.properties`, wrapper at `~/.termux/tasker/stayturgid-repair` (execs `~/stayturgid-repair.sh`; verified runs → exit 0). Imported via the `tasker-io` intent method (clean). `RunCommandService` mechanism confirmed (permission-gated by `com.termux.permission.RUN_COMMAND`, which the plugin holds — an adb-shell test is correctly rejected). **Not yet runtime-validated end-to-end** — couldn't force a manual run because a Tasker "Import Task/Set Sort" **context-menu popup** kept covering the task list (dismiss it by tapping empty space ~`(270,780)` — now handled in `tasker_io.goto_main`), plus a Tailscale ADB dropout. **The 20-min `ADB_Interval_Check` schedule will validate it: look for a `[watchdog] … (termux:tasker)` line + a fresh `[repair] STATUS` in `/sdcard/stayturgid_watchdog.log`.** Safe to leave live: if the bridge returns empty, act5 fires a "bridge failed" notification and the catastrophic branch simply won't match — no broken loop. **Left behind:** an empty throwaway task `TT_fmt` in the stayturgid project (from probing the plugin format before I found the template) — delete it next session.
2. **Ansible-ify the Termux userland setup.** — **✅ SKELETON 2026-07-05:** `ansible/` playbook + `termux_userland` role (`ansible/playbooks/termux-userland.yml`, `ansible/mac/deploy-termux.sh`). S24-only in inventory; run `ansible-playbook … --limit s24`. OS-level bits (Shizuku, Obtainium, a11y) stay manual.
3. **Add [SuperMonster003/AutoJs6](https://github.com/SuperMonster003/AutoJs6) as an ALTERNATIVE to Tasker+AutoInput** (user request 2026-07-05). AutoJs6 is a maintained Auto.js fork — a JavaScript automation engine using the Accessibility Service. Build a parallel AutoJs6 implementation of the watchdog/repair role so the user can run **either** Tasker+AutoInput **or** AutoJs6 — **no integration, no cross-fallback for now**. They must be **mutually exclusive / locked**: if one is active, the other must not be (e.g. only one accessibility-driven automation enabled at a time; a guard that disables/refuses the other). After building, **compare the two approaches** — technical pros/cons (robustness, element-finding vs coordinate taps, Git-friendliness, install/signature/Play-Protect, battery/background survival, Android-version resilience) and managerial pros/cons (maintainability, collaboration, versioning, learning curve, fork/maintenance risk). This is the **last** roadmap item.
   - **✅ IMPLEMENTED + validated on S24 2026-07-05:** `autojs6/` sub-project — `main.js` + `lib/` modules mirror `ADB_Core_Watchdog` v3 (Termux `RUN_COMMAND` → `stayturgid-repair.sh`, catastrophic Shizuku Start tap via accessibility, shared `/sdcard/stayturgid_watchdog.log`, mode guard via `/sdcard/stayturgid_automation_mode.txt`). Deploy: `autojs6/mac/deploy.sh`; mode switch: `autojs6/mac/set-automation-mode.sh`. Comparison: `autojs6/COMPARISON.md` (S24 production pick). Mac scripts use `mac/resolve-adb.sh` (USB serial when plugged in, else Tailscale).
   - **2026-07-05 — deployed to both phones:** AutoJs6 v6.7.0 + Obtainium on 7a and S24. **S24 is production AutoJs6 device** (`mode=autojs6`, Tasker watchdog profiles disabled). **7a remains on Tasker** unless explicitly migrated.

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

### 🎯 Active development device: **Galaxy S24 (USB `RFCX219CHKA`)**
The Pixel 7a is **wrapped up** for this workstream (see below). Use the S24 over **USB when plugged in**; Mac scripts (`mac/resolve-adb.sh`) auto-pick USB serial and fall back to Tailscale wireless when unplugged.

```bash
adb -s RFCX219CHKA shell echo OK          # USB (preferred when attached)
adb -s RFCX219CHKA forward tcp:8022 tcp:8022 && ssh s24 'echo OK'
scrcpy -s RFCX219CHKA --stay-awake        # live mirror during automation
./autojs6/mac/setup-autojs6.sh s24 s24    # resolves to RFCX219CHKA when USB present
```

**2026-07-05 session 3 — S24 AutoJs6 + Obtainium (USB dev handoff):**
- ✅ AutoJs6 v6.7.0 installed via USB; `RUN_COMMAND` granted; battery whitelist added
- ✅ `stayturgid-repair.sh` + `repair-bridge.sh` deployed via SSH; bridge running
- ✅ AutoJs6 project deployed to `/sdcard/Scripts/stayturgid` with device override `s24`
- ✅ Obtainium: AutoJs6 registered + full `stayturgid-apps.json` catalog imported (Automation + Stayturgid categories)
- ✅ **AutoJs6 watchdog LIVE on S24:** `main.js` running (Task tab shows Running task [1]); boot cycle `port=open sshd=up invoke=ok`
- ✅ Tasker watchdog profiles **disabled** via `tasker-io` reimport (`--no-enable` on `ADB_Boot_Restore` + `ADB_Interval_Check`)
- ✅ `autojs6/mac/start-watchdog.sh` — relaunch main.js over USB/Tailscale ADB
- ✅ **Termux boot relaunch** for AutoJs6: `start-autojs6-watchdog.sh` + 5-min `boot-launcher.js` nudge in `start-adb.sh` (ASCII paths only; no AutoJs6 timed-task UI required)
- ✅ **Cold-reboot validation (AutoJs6 stack):** one PIN unlock → `boot-launcher.js` at ~18:18 and ~18:44, `port=open sshd=up invoke=ok`; Termux `sshd` self-restarted after unlock
- ✅ **`stayturgid-repair.sh` TMPDIR fix:** Termux `adb` daemon needs `TMPDIR=$PREFIX/tmp` or localhost:5555 checks falsely report `CLOSED_NO_SHELL`
- ✅ **Runtime validation (2026-07-05):** sshd kill → repair-bridge ~2s; `test-watchdog-once` invoke=ok; `test-catastrophic-once` Shizuku Start text-tap ok=true
- ✅ **Shizuku authorized apps synced for AutoJs6 mode:** `autojs6/mac/grant-shizuku.sh` patches `/data/local/tmp/shizuku/shizuku.json` + `pm grant/revoke` — AutoJs6 allowed, Tasker denied (manager UI is json-driven, not pm-only)
- ✅ **Obtainium updates (2026-07-05 evening):** Shizuku 13.7.0, Termux:Styling/Widget/Float installed; AutoJs6 6.7.0 refreshed; `obtainium/mac/apply-updates.sh` added; Play Protect may block github-debug installs (verifier disable or manual **More details → Install anyway**)
- ✅ **Obtainium Shizuku installer:** `obtainium/mac/enable-shizuku-installer.sh` — grants API_V23, syncs `shizuku.json`, toggles UI (confirmed on S24 2026-07-05)
- ✅ **Termux overlay permission:** `SYSTEM_ALERT_WINDOW` granted for `com.termux` + `com.termux.window` (Termux:Float)
- ✅ **Watchdog Tailscale probe:** `autojs6/lib/tailscale.js` — tun0 + ping `100.100.100.100`, notify + relaunch `com.tailscale.ipn` if down
- ✅ **Test scripts:** `test-tailscale-probe-once.js`, `test-stale-loop-once.js`, `test-locked-screen-catastrophic-once.js`; Mac runner `autojs6/mac/run-test.sh`
- ✅ **Tailscale-down live test (2026-07-05):** `autojs6/mac/test-tailscale-down.sh` — force-stop → `probe up=false` → watchdog cycle → relaunch → `up=true` (USB)
- ✅ **Ansible Termux skeleton + S24 validation:** `ansible/playbooks/termux-userland.yml` + `ansible/mac/deploy-termux.sh` (S24 in inventory). Installed Homebrew `ansible`; final S24 run completed `changed=0`, repair check `STATUS port=open shizuku=up sshd=up shell=yes`. Fixed inventory Python path (`.../bin/python`); playbook runs `pkg update && pkg upgrade -y` up front and before any `pkg install`; installs only missing packages; added `abseil-cpp`/protobuf deps after Termux `adb` ABI mismatch.
- ✅ Pushed to GitHub `master` @ `e5d89de`+ (doc alignment, repair flock, Tailscale-down live test, Ansible skeleton)

### Pixel 7a — WRAPPED UP 2026-07-05 (maintenance-only)
- ✅ Port 5555 survives cold reboots (verified 2026-06-29)
- ✅ sshd survives cold reboots (Termux:Boot + self-heal loop)
- ✅ Tasker watchdog with failure notifications
- ✅ Mac-side launchd keepalive with macOS notification on reconnect/failure
- ✅ Published to TaskerNet: `https://taskernet.com/shares/?user=AS35m8lVOCqN0zylSnJKY8pBzCqkgDU8h624gr9CWqSAxD9myEt6n3OjyI4TtJhMtmw%2B&id=Project%3Astayturgid`
- ✅ Auto-update download+import task XML complete — uses **AutoInput Gestures** (coordinate taps) to click through 4 import dialogs
- ⚠️ Auto-update dialog sequence: **dialog 1 click confirmed working** (YES at 894,2058); dialogs 2–4 not yet confirmed end-to-end
- ⚠️ `stayturgid_update_check` daily trigger profile now in repo (`Daily_Update_Check` in `tasker/stayturgid.prj.xml`); re-import to 7a when convenient

**2026-07-05 session — 7a reconnected and repaired via Tailscale:**
- ✅ Reconnected via `100.65.230.108:38435` (Tailscale mDNS TLS endpoint), then reopened stable port 5555; health check green (Shizuku running, sshd up, port 5555 listening, battery 100%, 4 apps deviceidle-whitelisted)
- ✅ **Live project was 25 KB vs the repo's stale 4 KB** — exported the live version, committed it to `tasker/stayturgid.prj.xml` (was losing uncommitted Tasker work). Contains 2 profiles + 3 tasks (adds `TestUpdateTrigger`)
- ✅ **Custom Setting namespace bug fixed and reimported** (System→Global for adb_enabled/adb_wifi_enabled), verified in the Tasker editor showing Type=Global; both profiles re-enabled
- ⚠️ Repo project now differs from the **TaskerNet-published** copy (still has the old bug) — republish to TaskerNet when convenient
- ✅ **2026-07-05 evening (USB):** Re-imported via `tasker-io` — `stayturgid_Update_Check` (GitHub `version.json`), **Daily_Update_Check** profile (10:00 daily), `ADB_Core_Watchdog` v3. Termux:Tasker bridge **runtime-validated** (`[watchdog] … (termux:tasker)` in log). Fixed broken Termux pkg state (`curl` ABI mismatch → `apt full-upgrade` with `dpkg --force-confold` for conffile prompts). Ansible `deploy-termux.sh p7a` green; `claude-presence.sh gate` deployed.
- Note: AutoInput crashed once mid-automation ("AutoInput keeps stopping") — recovered by dismissing and relaunching Tasker
- ✅ **Obtainium full catalog imported** (32 apps; merges without duplicates)
- ✅ **AutoJs6 v6.7.0 installed**, `RUN_COMMAND` granted, project deployed, `repair-bridge.sh` validated
- ✅ Obtainium full catalog + AutoJs6 installed; **stays on Tasker** (`mode=tasker`); Termux boot/repair scripts synced with S24 (2026-07-05 USB)
- **Leave on Tasker mode** unless explicitly testing AutoJs6

### Samsung Galaxy S24 (RFCX219CHKA) — **production AutoJs6** (Tasker archived on device)

> Historical bullets below (2026-07-01 initial setup) are superseded where they conflict — Shizuku, port 5555, and AutoJs6 watchdog are all validated 2026-07-05.

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
- ~~Shizuku SSL / no Shizuku~~ → **resolved:** Shizuku 13.7.0 + wireless-debug Start text-tap validated (AutoJs6 catastrophic path)
- ~~Manual adb tcpip after reboot~~ → **resolved:** Shizuku TCP mode + cold-reboot validation
- ~~AutoInput on S24~~ → **deferred:** S24 uses AutoJs6; Tasker profiles disabled
- ~~End-to-end auto-update on S24~~ → **deferred:** auto-update remains Tasker-only; 7a path when needed

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
- ⚠️ S24 LAN IP is DHCP — never hardcode it; use Tailscale `100.123.218.30`
- ✅ Tasker notification fix-text in `s24_stayturgid.prj.xml` updated to Tailscale IP (Tasker profiles disabled on S24; AutoJs6 notify uses dynamic text)
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
- ✅ **Same stack redeployed to 7a (2026-07-05, USB):** `start-adb.sh` (74-line, wake-lock + battery alarm + AutoJs6 nudge no-op in tasker mode), `stayturgid-repair.sh` (TMPDIR fix), `claude-presence.sh`; boot loop restarted; `mode=tasker` written explicitly.
- ✅ Watchdog Tailscale probe (`autojs6/lib/tailscale.js` — tun0 + ping 100.100.100.100, relaunch if down)

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
5. ✅ Add a Tailscale probe to the watchdog (check `tun0` / ping `100.100.100.100`, notify + `am start` Tailscale if down) — `autojs6/lib/tailscale.js`
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

### Samsung Galaxy S24 (primary dev device — USB `RFCX219CHKA`)

| Field | Value |
|-------|-------|
| Device | Samsung Galaxy S24 (SM-S921U1) |
| Android | 16 (SDK 36) |
| USB serial | `RFCX219CHKA` (**use this when plugged in**) |
| Wireless ADB | `adb connect 100.123.218.30:5555` (Tailscale, stable); LAN IP is DHCP — do not hardcode |
| Tailscale | `com.tailscale.ipn` v1.98.8; tailnet name `dannys24`, IP `100.123.218.30` |
| SSH (direct) | `ssh s24` (alias → Tailscale, key auth, no 1Password dialog) |
| SSH via USB | `adb -s RFCX219CHKA forward tcp:8022 tcp:8022` then `ssh -p 8022 localhost` |
| Tasker | `net.dinglisch.android.taskerm` v6.7.5-beta — **profiles disabled** (archived fallback) |
| Shizuku | `moe.shizuku.privileged.api` (thedjchi) — survives cold reboot (verified 2026-07-05) |
| AutoJs6 | `org.autojs.autojs6` v6.7.0 — **production watchdog** (mode=autojs6, `main.js` running) |
| Termux | GitHub-signed stack via Obtainium (`com.termux` + addons) |
| Obtainium | Full stayturgid catalog; **Shizuku installer enabled** (`enable-shizuku-installer.sh`) |
| Automation mode | `/sdcard/stayturgid_automation_mode.txt` = `autojs6` |
| AutoJs6 watchdog | **Validated 2026-07-05** — watchdog + catastrophic + stale-loop + locked-screen + Tailscale probe |

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

### Termux packages (CRITICAL)
**At the start of any Termux setup, deploy, or maintenance session**, refresh and upgrade all installed packages:

```bash
pkg update && pkg upgrade -y
```

**Before every `pkg install`** (new package or dependency), run update+upgrade again — even if you just ran it:

```bash
pkg update && pkg upgrade -y && pkg install <packages> -y
```

The Ansible playbook (`ansible/roles/termux_userland`) follows this automatically. Manual SSH sessions and agent workflows must do the same.

### Phone announcement protocol (CRITICAL)
**Name the specific phone(s)** you're about to use / done with — "Pixel 7a", "Galaxy S24", or both. Before any device interaction, output this as a standalone message (fill in the device):

**🚨📱🚨 USING — &lt;phone(s)&gt; 🚨📱🚨**

When done with those device(s) and not expecting to touch them again until the next user reply:

**✅📱✅ FREE — &lt;phone(s)&gt; ✅📱✅**

Both must be standalone — not buried in other text. If you pick up a second phone mid-run, announce it too.

### On-device presence indicator (CRITICAL — run alongside the announcement)
So it's obvious *from the phone itself* that automation is live, call the presence script at the start and end of each device session. It uses torch + vibration + an ongoing status-bar notification only — nothing on the screen surface, so it never interferes with UI dumps/taps/screenshots. (Screen flashing or color inversion WAS considered and rejected: overlays can cover tap targets and inversion corrupts screenshots.)

```bash
ssh s24 '~/claude-presence.sh gate "Galaxy S24" Auto' # if active use is detected: 30s consent dialog (timeout=continue)
ssh s24 '~/claude-presence.sh on  "Galaxy S24" Auto'   # ongoing "🤖 Auto is using ..." notification
ssh s24 '~/claude-presence.sh off "Galaxy S24" Auto'   # removes notification + 2 pulses + vibrate
ssh s24 '~/claude-presence.sh resume'                  # clear a prior Pause choice
# same for p7a / "Pixel 7a"; agent name is 3rd arg or STAYTURGID_AGENT env (default: Auto)
```

Script lives at `termux/claude-presence.sh` in the repo and `~/claude-presence.sh` on each device. Pair `on` with the USING announcement and `off` with FREE. The `gate` action checks screen/foreground state first; if the phone appears active, it shows a `termux-dialog` radio prompt with **Continue**, **Pause**, and **Check again in 10 minutes**. Timeout defaults to Continue. If SSH is down but ADB is up, run it via `adb -s <dev> shell "run-as ... claude-presence.sh on"` or just skip to the text announcement.

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
autojs6/                                — AutoJs6 alternative to Tasker+AutoInput (mutually exclusive)
  main.js                               — watchdog entry (20 min + boot manual)
  lib/                                  — guard, termux bridge, shizuku/tailscale, notifications
  mac/deploy.sh, set-automation-mode.sh, run-test.sh, grant-shizuku.sh
obtainium/                              — Obtainium import JSON for all GitHub-sideloaded APKs
  stayturgid-apps.json                  — full catalog (Termux, Shizuku, Tailscale, AutoJs6)
  mac/sync-to-device.sh                 — push + open Obtainium import on device
  mac/apply-updates.sh                  — drive bulk update UI from Mac
  mac/enable-shizuku-installer.sh       — one-time: quieter installs via Shizuku API
ansible/                                — Termux userland playbook (SSH/Tailscale)
  playbooks/termux-userland.yml
  mac/deploy-termux.sh
termux/boot/
  start-adb.sh                          — deploy to ~/.termux/boot/ on device
mac/
  resolve-adb.sh                        — USB-first ADB target resolver (p7a/s24 aliases)
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

**Not yet imported to device (7a):** re-import `tasker/stayturgid.prj.xml` via `tasker-io` to pick up `Daily_Update_Check` + GitHub version check. S24 uses AutoJs6 (Tasker profiles disabled).

---

## Auto-update mechanism

`stayturgid_update_check.tsk.xml` uses GitHub for version detection (`version.json`) and download — no TaskerNet at runtime.

### How it works

1. `act6` (JavaScript) sets locals from `updaterData`: `%version_check_url`, `%raw_xml_url`, `%version`, `%changelog`
2. `act9` sets HTTP URL → `%taskernet_xml` (legacy var name; value is `version_check_url`)
3. `act10` (HTTP Request) fetches GitHub `version.json`
4. `act11` (Regex Match) extracts `"version": "..."` from JSON
5. `act13` (JavaScript) compares `%version` to `%taskernet_version`; sets `%updatestatus`
6. If update available: sticky notification with Update / Skip buttons
7. **Update path:** download from GitHub + AutoInput import-dialog sequence (see coordinates below)
8. **Skip path:** cancel notification, flash "Skipped...", stop

**Release:** bump `version.json` + matching `act6` version/changelog, push `master`. No TaskerNet step.

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
3. In `version.json` and `tasker/auto-update/stayturgid_update_check.tsk.xml` `act6`, bump `"version"` and update `"changelog"` (keep both in sync)
4. Commit and push to GitHub master — that's the entire release; TaskerNet republish optional

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
- **Termux `pkg upgrade` on stale installs:** if `curl` fails with an OpenSSL/ngtcp2 symbol error, run `apt full-upgrade` (or `dpkg --force-confold --configure -a` after killing a stuck upgrade). Conffile prompts (`openssl.cnf`, `sources.list`) block non-interactive runs unless you use `--force-confold` or apt `Dpkg::Options::=--force-confold`.
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

### ✅ Step 5 — GitHub-only version detection (COMPLETE 2026-07-05)

`version.json` at repo root is the canonical published version. `stayturgid_Update_Check` fetches it via `version_check_url`; TaskerNet is no longer used for detection. Optional: republish to TaskerNet for manual one-click install discovery.

See **HACKING.md** for the full development environment setup (all tool versions, Obtainium sources, clean-install walkthrough).

---

## How to start a new AI session

```bash
claude   # open interactive session in terminal (NOT Warp)
```

Verify session type is Pro/Max (not API billing) with `/status`. The working directory is `~/upmon-handoff/` — this is the Maestro agent working dir, separate from the project at `~/stayturgid/`.

---

## Architecture research — unified orchestration (LAST — research only)

> **Status:** Queued for independent research and architectural consideration. **Do not refactor the repo yet.** The current hybrid layout (Mac shell scripts + partial Ansible + on-device Tasker/AutoJs6 + `tasker-io` + Obtainium scripts) is working production. This section captures a proposed direction for a future consolidation decision.

### Question

Could the whole stayturgid system — Termux/SSH, Termux:API, ADB, uiautomator2, Shizuku, Tasker/AutoJs6 deploy, Obtainium, launchd — be refactored as **one Ansible project** (or one other sysadmin framework), with everything expressed as modules/roles/collections?

### Preliminary recommendation: Ansible core + custom modules

For this Android-focused, SSH-heavy, multi-tool workflow, the best **overall** shape is an **extensible Ansible orchestration layer** with custom Python modules/roles, optionally augmented by a small Python library for Android-specific glue that doesn't fit YAML well.

#### Why Ansible fits stayturgid

| Strength | How it maps here |
|----------|------------------|
| SSH-first | Termux `sshd` on :8022 over Tailscale is already the control plane; `ansible/inventory/hosts.yml` + `termux_userland` role prove the pattern |
| Modularity | Roles/collections match the desire for "everything as a module of the system" — Termux userland, Shizuku grants, Obtainium catalog, AutoJs6 deploy, Tasker import |
| Complex workflows | Playbooks handle sequencing (`pkg update` → upgrade → install), conditionals (USB vs Tailscale ADB), idempotency, per-host vars (`mode=tasker` vs `autojs6`), Vault for keys |
| Git + collaboration | Plain YAML + Python `library/` modules; Galaxy/collection packaging if spun out |
| Idempotency | Already validated on S24/p7a Termux playbook (`changed=0` on steady state) |

We are **already partial Ansible** (`ansible/playbooks/termux-userland.yml`, `deploy-termux.sh`). The research question is how far to extend that boundary — not whether to start from zero.

#### What would become Ansible roles/collections

```
stayturgid-ansible/   (hypothetical future layout)
  inventory/          # p7a, s24 — SSH + optional adb_host vars
  group_vars/           # automation_mode, tailscale_ip, usb_serial
  roles/
    termux_userland/    # ✅ exists today
    termux_boot/        # boot scripts, runit sshd, wake-lock
    shizuku/            # grant scripts, wireless-debug pairing docs-as-tasks
    obtainium/          # catalog sync, Shizuku installer toggle
    autojs6/            # deploy main.js, grant RUN_COMMAND, start watchdog
    tasker/             # tasker-io import tasks, mode guard (disable profiles)
    mac_launchd/        # adb-reconnect plists (localhost delegate_to)
  library/              # custom modules (Python):
    termux_api.py       # wrap termux-battery-status, termux-dialog, etc.
    adb_shell.py        # resolve USB/Tailscale target, run adb shell
    uiautomator2_run.py # invoke pipx u2 scripts with serial from inventory
    shizuku_rish.py     # privileged settings when localhost:5555 up
  playbooks/
    site.yml            # full device bring-up
    deploy-watchdog.yml # mode-conditional: tasker vs autojs6
    validate.yml        # repair STATUS, tailscale probe, cold-reboot checklist
```

#### Custom module candidates

- **`termux_api_call`** — Termux:API from SSH (`termux-notification`, `termux-dialog`, battery)
- **`adb_command`** — Mac-side ADB with inventory-driven serial (wrap `mac/resolve-adb.sh` logic)
- **`uiautomator2_task`** — run `tasker_io.py` or one-off UI scripts from control node
- **`shizuku_privileged`** — wrap `autojs6/mac/grant-shizuku.sh`-style json + pm grant flows
- **`stayturgid_repair_check`** — parse `STATUS port=…` from repair script over SSH

Non-native tools (uiautomator2, Shizuku, Termux:API) are **not** Ansible builtins — wrap them in `library/` modules or `ansible.builtin.script` with clear contracts.

#### Limitations and mitigations

| Limitation | Mitigation |
|------------|------------|
| UI automation is Mac-side + device-screen dependent | Keep uiautomator2 in Python modules; Ansible tasks call them; document Samsung content-URI grant failure (see `tasker-io/README.md`) |
| ADB and SSH are two channels | Inventory vars + `delegate_to: localhost` for Mac ADB tasks; playbooks order SSH-first, ADB fallback |
| On-device watchdog must stay on-device | Ansible **deploys** Tasker/AutoJs6; does not replace 20-min runtime loops |
| Play Protect / Obtainium / human PIN | Tag tasks `manual` or use `pause:` prompts; don't pretend full unmanned bootstrap |
| Stale Termux mirrors / conffile prompts | Already hit on 7a — role should use `DEBIAN_FRONTEND=noninteractive` + `Dpkg::Options::=--force-confold` |
| Scale | 2 phones — Ansible parallelism is plenty; Salt only matters at fleet scale |

### What should **not** move into Ansible (likely)

- **Runtime watchdog logic** — `stayturgid-repair.sh`, AutoJs6 `main.js`, Tasker `ADB_Core_Watchdog` (Ansible configures; devices heal themselves)
- **Cold-reboot Shizuku Start tap** — accessibility-driven; stays Tasker/AutoJs6 unless replaced by a maintained UI module
- **Mac launchd keepalive** — can be a `mac_launchd` role with `delegate_to: localhost`, but it's orthogonal to phone SSH
- **Obtainium in-app UI** — `enable-shizuku-installer.sh` + uiautomator2; candidate for a module, not pure YAML

### Strong alternatives (if Ansible boundary feels wrong)

1. **Pure Python orchestrator** (Invoke/Fabric + `subprocess` + uiautomator2 + ppadb)
   - Better for dense UI/state-machine logic (Tasker import dialog chains)
   - Structure as packages: `stayturgid.termux`, `.adb`, `.tasker_io`, `.autojs6`
   - Prefect/Dagster/Airflow only if dependency graphs become large (probably overkill for 2 phones)

2. **SaltStack (Salt SSH)**
   - Faster parallel execution, event-driven reactor model
   - Higher setup cost; weaker ecosystem for "personal phone" DIY docs

3. **Hybrid: Ansible + on-device AutoJs6**
   - Ansible for deploy/config; AutoJs6 for rich UI automation (already production on S24)
   - Matches current architecture; formalize the split in playbooks (`when: automation_mode == 'autojs6'`)

4. **Tasker + Termux:Tasker only**
   - Familiar, works on 7a, but poor fit for **cross-tool** Mac-side orchestration (ADB forward, launchd, Obtainium sync, git deploy)

### Current state vs target (gap analysis)

| Layer | Today | Ansible-native? |
|-------|-------|-----------------|
| Termux packages + scripts | ✅ `termux_userland` role | Yes |
| Shizuku install/grant | Mac shell scripts | Partial — custom module |
| Obtainium catalog/install | Mac shell + u2 | Partial — script module |
| AutoJs6 deploy/start | `autojs6/mac/*.sh` | Partial — role + adb delegate |
| Tasker import | `tasker-io/tasker_io.py` | Script/module wrapper |
| ADB reconnect launchd | `mac/adb-reconnect.sh` + plist | localhost role |
| Validation tests | scattered `mac/run-test.sh`, test JS | playbook `validate.yml` |

**Pain points a unified layer would address:** duplicated device resolution (`resolve-adb.sh` vs inventory), no single `site.yml` bring-up, manual ordering documented only in HANDOFF, mixed idempotency story outside Ansible.

**Pain points it would not fix:** Play Protect, PIN unlock, DHCP LAN IP, Samsung Shizuku/content-URI quirks, Tasker XML fragility.

**Do not implement until the user explicitly approves a refactor.** Until then, continue extending the existing `ansible/` skeleton and Mac scripts as needed.

---

### Migration priority (when approved): move as much as possible to Ansible

Recommended order — highest value / lowest risk first:

| Phase | Target | Why first |
|-------|--------|-----------|
| **1** | **Termux packages** (`termux_pkg` module) | Already SSH-connected; 7a proved shell task is fragile (broken `curl`, stuck `dpkg`, conffile prompts) |
| **2** | Termux files/templates (expand `termux_userland`) | ✅ mostly done — scripts, boot, `termux.properties`, mode files |
| **3** | Mac-delegated ADB (`adb_shell`, `android_apk`) | Wrap `resolve-adb.sh`; sideload APKs without Obtainium UI |
| **4** | Obtainium catalog + updates (`obtainium_app`) | Deep links + JSON import + optional u2/Shizuku install path |
| **5** | Shizuku grants, AutoJs6/Tasker deploy roles | Compose existing shell scripts |
| **6** | Play Store semi-automation (`google_play_app`) | Weakest — no silent install API; document limits clearly |
| **7** | `tasker-io` / uiautomator2 as Ansible action plugins | UI state machines belong in Python called from tasks |

**Principle:** anything reachable over **Termux SSH** moves first; anything needing **Mac ADB + screen** gets a `delegate_to: localhost` role with explicit `tags: [ui, manual]` for human-in-the-loop steps.

---

### Termux packages — fault-tolerant module design (`termux_pkg`)

Today's `termux_userland` role uses a single `ansible.builtin.shell` block (`pkg update && pkg upgrade -y`, then install missing packages). That failed on 7a when the package DB was half-upgraded. A dedicated module (or role backed by a module) should:

**Module contract (sketch):**

```yaml
- name: Ensure Termux packages
  termux_pkg:
    name: [openssh, android-tools, python, ...]
    state: present          # present | latest | absent
    update_cache: true      # pkg update
    upgrade: auto           # never | auto | full  — auto = upgrade only if installing/upgrading
    force_confold: true     # Dpkg::Options for openssl.cnf / sources.list
    mirror: optional        # termux-change-repo if unset and pkg warns
  environment:
    DEBIAN_FRONTEND: noninteractive
```

**Fault tolerance behaviors:**

| Failure mode | Module behavior |
|--------------|-----------------|
| `curl` / `pkg` binary broken (ABI mismatch) | Detect via preflight `command -v curl && curl --version`; run `dpkg --configure -a` + `apt-get -y -o Dpkg::Options::=--force-confold full-upgrade` before retry |
| Stuck `dpkg` / apt lock | Check lock file; optional `force: true` to kill stale apt (with warning) |
| Conffile prompt blocks non-interactive run | Always pass `--force-confdef` / `--force-confold` to apt/dpkg |
| Mirror 404 / stale index | Retry with `termux-change-repo` candidate list or fail with actionable message |
| Partial install (package X upgraded, Y failed) | Per-package `dpkg-query` check; report `failed_packages` list; don't claim success |
| Idempotency | `state: present` → install missing only; `state: latest` → upgrade named packages |

**Prior art for Termux + Ansible:**

| Source | Notes |
|--------|-------|
| [gounthar/termux-jenkins-automation](https://github.com/gounthar/termux-jenkins-automation) | **Best reference** — 8 roles (`termux-base`, `termux-complete-setup` with 59+ packages, `termux-boot-setup`); Jenkins blog [2025](https://www.jenkins.io/blog/2025/10/31/automating-jenkins-on-android/) |
| [guoqiao/ansible-android-termux](https://github.com/guoqiao/ansible-android-termux) | Early SSH inventory pattern; `termux-url-opener` for Play URLs via `gplaycli` |
| [ivansible/termux](https://galaxy.ansible.com/ui/repo/published/ivansible/termux/) | Galaxy collection `ivansible.termux` (minimal adoption) |
| [ansible/ansible#81547](https://github.com/ansible/ansible/pull/81547) | **Open PR** (rebased Feb 2026) — teach `ansible.builtin.package` to use `apt` on Termux; would help but **doesn't solve conffile/stuck-dpkg** — still need custom logic |
| stayturgid `termux_userland` role | Working baseline; replace shell block with module when implemented |

**Implementation note:** Even if #81547 merges, stayturgid should still ship **`community.stayturgid.termux_pkg`** (or `library/termux_pkg.py`) with the recovery path above — upstream `package` won't know about Termux-specific failure modes we hit on 7a.

---

### Generic module: `obtainium_app` (research — not implemented)

**Goal:** Idempotently ensure an app is **tracked in Obtainium** and optionally **installed/updated**, replacing ad-hoc shell + coordinate taps in `obtainium/mac/*.sh`.

**Obtainium has no server-side API** — automation must use Android intents, JSON import, or UI automation. Prior art:

| Mechanism | Automation level | Prior art / docs |
|-----------|------------------|------------------|
| `obtainium://add/<url>` deep link | Add to catalog (may still need UI confirm) | [Obtainium wiki](https://wiki.obtainium.page/sources/); stayturgid uses `obtainium://add/github.com/termux/<repo>` |
| `obtainium://app/...` | Pre-built app config HTML/JSON links | [Issue #918](https://github.com/ImranR98/Obtainium/issues/918), [PR #2683](https://github.com/ImranR98/Obtainium/pull/2683) |
| **Obtainium Import** JSON file | Bulk add/update configs | `obtainium/stayturgid-apps.json`; [Discussion #1739](https://github.com/ImranR98/Obtainium/discussions/1739); emulation packs ([RJNY/Obtainium-Emulation-Pack](https://github.com/RJNY/Obtainium-Emulation-Pack)) |
| Push JSON to app data dir | Undocumented shortcut mentioned in discussions | Fragile across Obtainium versions / scoped storage |
| Shizuku/Dhizuku/Sui installer | Silent install **after** Obtainium has APK | [Issue #1611](https://github.com/ImranR98/Obtainium/issues/1611); stayturgid `enable-shizuku-installer.sh` |
| uiautomator2 + `adb shell input tap` | Bulk "Update all" + package installer dialogs | stayturgid `apply-updates.sh` (coordinate-based, Samsung-specific) |

**Proposed module layers:**

```yaml
# Layer A — catalog only (no UI if deep link works)
- obtainium_app:
    url: "https://github.com/termux/termux-app"
    state: tracked          # tracked | absent
    method: deep_link       # deep_link | json_import
  delegate_to: localhost
  vars:
    adb_serial: "{{ hostvars[inventory_hostname].adb_serial }}"

# Layer B — bulk catalog from repo file
- obtainium_app:
    import_json: "{{ playbook_dir }}/../obtainium/stayturgid-apps.json"
    state: tracked
    method: json_import
  delegate_to: localhost

# Layer C — install/update (requires Shizuku + UI or privileged adb)
- obtainium_app:
    url: "https://github.com/SuperMonster003/AutoJs6"
    state: latest           # tracked | installed | latest
    install_method: shizuku  # shizuku | adb | ui_bulk
    shizuku: true
  delegate_to: localhost
```

**Module implementation sketch:**

1. **`delegate_to: localhost`** — all Obtainium control is Mac-side ADB (or wireless ADB over Tailscale).
2. **`check_mode`** — `adb shell pm list packages` + compare versionName; for Obtainium-tracked apps, optionally query Obtainium's on-device DB (hard — may skip and rely on JSON manifest in repo).
3. **`deep_link`** — `adb shell am start -a android.intent.action.VIEW -d 'obtainium://add/...'`; optional u2 wait for snackbar/confirm.
4. **`json_import`** — push JSON to `/sdcard/Download/`, u2/automation open Obtainium → Import/Export → Obtainium Import (same pattern as `tasker-io` text-button chains).
5. **`install_method: adb`** — bypass Obtainium: `gh release download` + `adb install -r` (already used for Termux github-debug swap); module wraps Play Protect verifier disable **only** with explicit `allow_play_protect_bypass: true` + docs warning.
6. **`install_method: shizuku`** — prerequisite task ensures Shizuku installer enabled in Obtainium settings (wrap `enable-shizuku-installer.sh`).

**Idempotency honesty:** "tracked in Obtainium" is only fully idempotent if we can read Obtainium state (no stable public API). Practical approach: **declarative JSON catalog in git is source of truth**; module pushes/import-syncs when checksum differs; install/update is `changed_when: version bumped`.

**Community prior art:** No published **`ansible-obtainium`** module found. Closest patterns: [Bierchermuesli/ansibel-nspanel](https://github.com/Bierchermuesli/ansibel-nspanel) (Ansible + parallel `adb install` for IoT panels); FrenchToucan/Toucans-Obtainium-Export shell script pushes JSON then **manual** import step.

---

### Generic module: `google_play_app` (research — not implemented)

**Hard truth:** There is **no supported API to silently install Play Store apps by package name** on a consumer phone without MDM/Device Owner. AnsiblePilot's "Ansible on Android" guide refers to **backend/Play Console CI**, not on-device Play installs ([ansiblepilot.com](https://www.ansiblepilot.com/articles/ansible-on-android-backend-infrastructure-automation-complete-guide)).

| Approach | Feasibility | Notes |
|----------|-------------|-------|
| Play Store `market://details?id=` intent | Semi-auto | Opens Play UI; user taps Install ([Stack Overflow](https://stackoverflow.com/questions/42125096/how-to-automate-installation-of-play-store-apps-by-package-name)) |
| Desktop Play "Install" button (same Google account) | Manual | FCM pushes install to device — not scriptable from Ansible without Google account automation |
| `gplaycli` / `google-play-scraper` on Mac | **Broken/unreliable** | Downloads APKs against ToS; guoqiao repo used it in Termux url-opener — not suitable for production |
| MDM (Headwind, Esper, etc.) | Fleet only | Wrong shape for personal daily-driver phones (already rejected in roadmap) |
| Aurora Store | Alternative store | Could be a separate `aurora_app` module; still UI-heavy |

**Proposed limited module:**

```yaml
- google_play_app:
    package: net.dinglisch.android.taskerm
    state: present          # present = installed; open_store = just open Play page
    method: check_only      # check_only | open_store | semi_auto
  delegate_to: localhost
```

- **`check_only`** (default): `adb shell pm path {{ package }}` → ok if installed.
- **`open_store`**: `am start -a android.intent.action.VIEW -d market://details?id=...` — tags `[manual]`.
- **`semi_auto`**: u2 loop: open store → wait for Install button → tap (fragile, locale/OEM dependent) — **not recommended** except as escape hatch.

**Recommendation:** For stayturgid, **prefer Obtainium + GitHub/F-Droid** for every app we control; reserve `google_play_app` for **presence checks only** (is Tasker installed?) and document Play-only apps as manual/Obtainium-not-available exceptions.

---

### Generic module: `android_apk` (lower layer, shared)

Both Obtainium and direct sideload paths need this. Prior art:

| Source | Notes |
|--------|-------|
| [shresthagrawal/AnsibleAndroidAutomationADB](https://github.com/shresthagrawal/AnsibleAndroidAutomationADB) | Custom Ansible module for ADB (2018, 31★) |
| [rpavlik Ansible ADB connection plugin gist](https://gist.github.com/rpavlik/a0c785fbe568fd4c7fbb67893ec4507a) | Connection plugin prototype — `adb connect host:port` |
| [Bierchermuesli/ansibel-nspanel](https://github.com/Bierchermuesli/ansibel-nspanel) | Fetch GitHub release APK + parallel `adb install -r` + `pm uninstall` debloat |
| `community.general.android_sdk` | **Dev machine only** — SDK packages via `sdkmanager`, not on-device apps |

```yaml
- android_apk:
    src: /tmp/termux-app.apk      # or url: https://github.com/.../releases/download/...
    state: present
    replace: true                 # adb install -r
    package: com.termux           # optional verify
  delegate_to: localhost
```

Handles: download once, `adb -s {{ serial }} install -r`, parse `Failure [INSTALL_FAILED_*]`, version compare via `dumpsys package`.

---

### Updated research steps (when picked up)

1. **Prototype `termux_pkg`** — port 7a recovery logic; replace shell block in `termux_userland/tasks/main.yml`.
2. Prototype `stayturgid_repair_check` (SSH → parse STATUS).
3. Prototype `android_apk` + `adb_serial` from inventory (merge `resolve-adb.sh` logic into module util).
4. Prototype `obtainium_app` **layer A only** — deep link + `pm list packages` check for one GitHub app.
5. Sketch `playbooks/site.yml` composing roles; `when: automation_mode`.
6. Write ADR with explicit non-goals (Play Store silent install, full unmanned Obtainium bulk update on Samsung without Shizuku).
7. Decide collection name: `community.stayturgid` vs upstream contribution to `ivansible.termux`.

### References (prior art bibliography)

- Termux + Ansible: [termux-jenkins-automation](https://github.com/gounthar/termux-jenkins-automation), [ansible-android-termux](https://github.com/guoqiao/ansible-android-termux), [ivansible/termux](https://galaxy.ansible.com/ui/repo/published/ivansible/termux/), [ansible#81547](https://github.com/ansible/ansible/pull/81547)
- ADB + Ansible: [AnsibleAndroidAutomationADB](https://github.com/shresthagrawal/AnsibleAndroidAutomationADB), [ADB connection plugin gist](https://gist.github.com/rpavlik/a0c785fbe568fd4c7fbb67893ec4507a), [ansibel-nspanel](https://github.com/Bierchermuesli/ansibel-nspanel)
- Obtainium automation: [Obtainium repo](https://github.com/ImranR98/Obtainium), [wiki sources](https://wiki.obtainium.page/sources/), [deep links #918](https://github.com/ImranR98/Obtainium/issues/918), [Dhizuku install #1611](https://github.com/ImranR98/Obtainium/issues/1611), [import discussion #1739](https://github.com/ImranR98/Obtainium/discussions/1739)
- Play Store automation limits: [Stack Overflow package install](https://stackoverflow.com/questions/42125096/how-to-automate-installation-of-play-store-apps-by-package-name), [How-To Geek Obtainium+Shizuku](https://www.howtogeek.com/this-is-how-i-keep-my-sideloaded-android-apps-updated-automatically/)
- stayturgid today: `ansible/roles/termux_userland/`, `obtainium/mac/apply-updates.sh`, `obtainium/mac/enable-shizuku-installer.sh`, `obtainium/stayturgid-apps.json`
