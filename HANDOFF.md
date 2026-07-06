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

## How updates work

GitHub `master` is the source of truth. To release:

1. Bump `version.json` (`version` + `changelog`), commit, and push.
2. `./ansible/mac/deploy-termux.sh` — Termux layer on all fleet hosts (or `--limit` one host).
3. `./autojs6/mac/deploy.sh p7a` and `./autojs6/mac/deploy.sh s24` — watchdog scripts on device.
4. `./autojs6/mac/start-watchdog.sh p7a` and `./autojs6/mac/start-watchdog.sh s24` — relaunch `main.js`.

Optional on-device notifier: `~/check-repo-version.sh` (deployed by Ansible; compares GitHub `version.json` to last-seen stamp and fires `termux-notification`).

---

## ✅ 7a Termux → GitHub/Obtainium swap — DONE 2026-07-05

The 7a's `com.termux` was the **googleplay build** while its addons were **F-Droid** → signature mismatch → `termux-api` dead (presence indicator + battery alarm were silent no-ops). Fixed by moving the **entire shared-uid Termux ecosystem to GitHub-debug builds** (all match each other) and tracking them in Obtainium.

**Final 7a state (all github-debug signed, all Obtainium-tracked for auto-update):** com.termux 0.118.3, com.termux.api 0.53.0, com.termux.boot 0.8.1, com.termux.styling 0.32.1, com.termux.widget 0.15.0, com.termux.window(float) 0.17.0. `termux-api` now WORKS (verified: presence torch+notification fire, `termux-battery-status` ok). SSH restored (`ssh p7a`, key auth; **Termux uid changed u0_a590→u0_a591**, ssh config updated). sshd up, boot loop running.
- **`com.termux.gui` has NO GitHub release** → left uninstalled (can't share-uid-align it with github com.termux). `com.termux.x11` doesn't share the uid (stays, already Obtainium). Third-party termux apps (io.github.*, com.gardockt.*, com.maazm7d.*) don't share uid — left as-is.
- Backup of the old home: `~/stayturgid-device-backups/termux-home-7a-20260705-073847.tgz` + `7a-restore-stage/`.

**Reusable procedure (also in HACKING.md):** back up `$HOME` via SSH → `adb uninstall` all shared-uid com.termux.* → `gh release download` the `+github(-|.)debug` APKs (main is per-arch `arm64-v8a`, addons universal) → **disable Play Protect verifier** (`verifier_verify_adb_installs`/`package_verifier_enable`→0, `package_verifier_user_consent`→-1; **user-approved, restore all to 1 when done**) since Play Protect gates github-debug installs with a fingerprint prompt → `adb install` each → launch Termux (bootstrap), grant storage → `pkg update && pkg upgrade -y` then `pkg install …` (always update+upgrade before install) + restore `.ssh`/`.termux/boot` + scripts → re-register Termux:Boot → add every app to Obtainium (`obtainium://add/github.com/termux/<repo>`) for auto-updates.

### New TODOs queued 2026-07-05
1. **Smart phone-use presence/consent dialog** — ✅ on both hosts via Ansible (`termux/agent-presence.sh gate` deployed to `~/agent-presence.sh`).
2. **LAST (research only — do not refactor yet):** Evaluate unified orchestration under Ansible; design generic **`obtainium_app` / `google_play_app`** modules. `termux_pkg` module already ships in `ansible/library/`. See **"Architecture research — unified orchestration"** at the bottom. No further refactor until explicitly approved.

## 🧭 Roadmap & tooling decisions (2026-07-05/06)

**Completed roadmap items:**
1. **Ansible-ify the Termux userland setup** — ✅ `ansible/` playbook + `termux_userland` role (`ansible/playbooks/termux-userland.yml`, `ansible/mac/deploy-termux.sh`), validated on both hosts. OS-level bits (Shizuku, Obtainium, a11y) stay manual.
2. **AutoJs6 watchdog** — ✅ `autojs6/` sub-project — `main.js` + `lib/` modules (Termux `RUN_COMMAND` → `stayturgid-repair.sh`, catastrophic Shizuku Start tap via accessibility, shared `/sdcard/stayturgid_watchdog.log`). Deploy: `autojs6/mac/deploy.sh`. Mac scripts use `shared/mac/resolve-adb.sh` (USB serial when plugged in, else Tailscale). Validated on S24 2026-07-05, rolled to 7a 2026-07-06. **AutoJs6 is the watchdog on both fleet phones.**

**Tooling assessment (options considered, decisions made):**
- **Ansible over Termux/SSH** — ✅ adopted. Best-fit config management for the userland layer; prerequisites already in place (sshd + keys + Tailscale).
- **AutoJs6** — ✅ adopted as the automation runtime: element-finding by text (portable across devices/resolutions), Git-friendly plain JavaScript, maintained fork.
- **MDM (Headwind / Esper / SOTI)** — ❌ wrong shape. Assumes Device-Owner provisioning (factory reset into a managed/kiosk state) — inappropriate for personal daily-driver phones. Only relevant for a fleet of dedicated devices.
- **Root (KernelSU / APatch)** — ❌ advised against. The **S24 SM-S921U1 (US model) has a permanently locked bootloader → almost certainly can't be rooted**, giving an asymmetric fleet; and rooting the daily-driver 7a means bootloader unlock (factory reset) + likely Play Integrity breakage. Only worth it if a device is dedicated to automation.
- **Webkey / proprietary remote channels** — ❌ adds dependency more than robustness; we already have two independent channels (ADB + SSH over Tailscale). Prefer hardening cross-device mutual repair over a third proprietary relay.

**Recently completed (2026-07-05):**
- ✅ 7a Termux ecosystem moved to GitHub/Obtainium (termux-api works).

## Current project status (as of 2026-07-06)

**Both fleet phones run the AutoJs6 watchdog** (`main.js`, 20-min interval + boot relaunch), deployed via `autojs6/mac/deploy.sh` + `ansible/mac/deploy-termux.sh`.

**Legacy third-party automation** removed from both devices (2026-07-06). Fleet uses AutoJs6 only.

### Infrastructure abstraction (taxonomy inventory) — 2026-07-06 (late) ✅

- **No device names in code.** The ONLY site-specific file is
  `ansible/inventory/hosts.yml` (hosts declare addresses/serials + membership
  in taxonomy groups). Quirk layers live in `ansible/inventory/group_vars/`:
  all → android_16 → vendor_{google,samsung} → oneui_7 → model_* → host —
  Ansible group precedence IS the "increasingly specific hints" cascade
  (same pattern as kubespray/DebOps group layering, geerlingguy first_found
  OS files, Puppet Hiera hierarchies).
- AutoJs6 device profiles are now DATA: `device.json.j2` rendered per host to
  `/sdcard/stayturgid_device.json`; `devices/p7a.js`+`s24.js` deleted;
  config.js falls back to generic defaults with a warning.
- Mac side: `ansible/playbooks/mac.yml` renders `~/.config/stayturgid/
  devices.conf` + launchd agents (com.stayturgid.*) from inventory; old
  com.djbclark.* agents retired. resolve-adb/access-monitor/adb-reconnect/
  fleet-health/tests all read the conf — zero hardcoded serials/IPs.
- Fixed latent bug: old `ansible/group_vars/` was adjacent to neither
  inventory nor playbooks, so it was silently never loaded; now at
  `ansible/inventory/group_vars/`.
- New device: add a host + group memberships to hosts.yml, run mac.yml +
  deploy-fleet.sh. New quirk: add/extend a group_vars layer.

### Notification self-heal + Python migration start + CI — 2026-07-06 (night) ✅

- **AutoJs6-blocked spam fixed**: repair.sh re-enables accessibility itself
  (append-only, STATUS a11y= field); guard notifies only when the auto-fix
  fails; notify.js persists per-key repeat counts on /sdcard — one
  notification per type, "(Nx)" on repeats. Verified a11y=repaired live on
  both phones. CI (GitHub Actions) runs make test on every push; first-ever
  ansible-lint/yamllint runs are clean (configs document the two skips).
- **bash→python migration begun** (Ansible best practice: Python beyond
  trivial wrappers; python is guaranteed on-device via stayturgid_termux_packages
  + ansible_python_interpreter): `termux/py/stayturgid_battery_alarm.py` is a
  behavior-identical twin; tests/test-unit.sh runs the SAME suite against both
  (battery_suite sh|py, 106 checks green). Shell stays deployed until parity
  soaks. **Queued rewrites** (same twin+parity pattern): stayturgid-repair.sh,
  screen-awake-guard.sh, agent-presence.sh, check-repo-version.sh, then Mac
  adb-reconnect/access-monitor. AutoJs6 JS is excluded (Rhino runtime).
- **Standing practice**: when touching a device, audit its notification shade
  (expected present, none stale). Formalizing as a device-tier expected-set
  probe is queued. Audit at session end: both shades clean (Termux service
  notifications only).

### Tasker exorcism + shell conventions + Ansible-native fleet — 2026-07-06 (evening) ✅

- **Legacy Tasker remnants:** live Tasker configs on BOTH phones are clean; the
  "Watchdog bridge failed" notification was a pre-cleanup zombie (Tasker
  re-asserts old group summaries; force-stop didn't clear it — needs a swipe).
  s24 had 3 more zombie legacy alerts. All legacy exports archived to
  /sdcard/Download/stayturgid-legacy-tasker-archive/ on both phones.
  ⚠ p7a's **upmon** project still references `ADB_Core_Watchdog` (deleted task)
  — user must edit in Tasker GUI. Device tier now probes for legacy Tasker
  notifications/files (excludes Tasker's configs/ backup history).
- **Shell conventions:** never assume the user's default shell (Termux has no
  zsh by default). All remote commands now go through explicit `bash -s` stdin;
  documented in HACKING.md + tests/README.md. shellcheck installed on the Mac;
  whole repo is shellcheck -S warning clean (make lint).
- **Ansible-native fleet deploy:** new `ansible/playbooks/fleet.yml` +
  `autojs6_watchdog` role (AutoJs6 project deployed over SSH via copy — no
  Mac-side adb needed) + `restart boot loop` handler (fires only when boot
  scripts change; uses the `[.]` pkill self-match guard). deploy-fleet.sh is
  now a thin wrapper (`CHECK=1` = dry run). Kept custom on purpose: termux_pkg
  module (no community equivalent for rootless Termux apt), Shizuku/UI scripts,
  on-device runtime scripts, TAP test harness. adb-only fallback:
  autojs6/mac/deploy.sh + start-watchdog.sh.

### Tests + screen-awake guard + sharing protocol session — 2026-07-06 (later) ✅

- **Test suite** (`tests/`, `Makefile`, `./configure`): three entry points —
  `make check|test|verify|dryrun|lint`, `tests/run.sh code|unit|local|device|all`
  (TAP), and standard Ansible (`--syntax-check`, `--check --diff`, lint configs).
  82 device-free unit tests (CODE-REVIEW regressions) + read-only device tier
  with drift detection. See `tests/README.md` for conventions (exit codes 0/1/2/
  75/130, log format, pidfiles-not-pgrep).
- **Screen-awake guard PoC** (`termux/screen-awake-guard.sh`, in the 5-min boot
  loop): while the screen is held awake (stay-on setting, app wakelock, or
  timeout > 10 min) and lit, a notification offers one-tap restore of screen
  lock (saved baseline, or the usual timeout options when unknown — reappears
  each cycle if dismissed while the state persists). Restore also clears
  stay_on/svc stayon and sleeps the screen; a foreign wakelock holder (e.g.
  Wakey) is named instead. **7a context:** timeout was found at 30 min (likely
  Wakey's doing); the 5-min AutoJs6 keepalive was tested and does NOT reset the
  idle timer.
- **Device-sharing flow** (`termux/agent-presence.sh` — renamed from
  claude-presence.sh, which remains as a compat shim): `request-screen` pops a
  modal 60s-countdown dialog (No = disallow, exit 75); `on` shows the running
  notification with a **Graceful stop** button; agents poll `stop-requested`
  (exit 0 = wrap up within ~1 min); `off` clears state and, after a stop
  request, pops a modal "released" dialog.
- Also: `deploy-fleet.sh` now really fails per-host (`|| rc=1` — set -e is
  suspended inside `if !` functions); `termux_pkg` tolerates mirror-sync
  `pkg update` failures with a warning (hit live on p7a); bridges started with
  pidfiles on both phones; drift clean on both.

### 📋 WORK ITEM for any new AI agent joining this fleet

The presence/consent protocol is **shared infrastructure, agent-agnostic by
design**: identify yourself via the 3rd argument or `STAYTURGID_AGENT` when
calling `~/agent-presence.sh`. Required behavior for ANY agent (Claude, GPT,
Gemini, …) before controlling a device screen:

1. `agent-presence.sh request-screen "<label>" "<your-name>"` — abort on exit 75.
2. `agent-presence.sh on "<label>" "<your-name>"` while working.
3. Poll `agent-presence.sh stop-requested` between steps; on exit 0 you have
   ~1 minute to wrap up.
4. `agent-presence.sh off "<label>" "<your-name>"` when done.

Do **not** fork per-agent copies of this script. If your integration needs
something the shared script can't express, re-architect it so all agents
coexist (keep the shim + CLI contract working), then leave a work item here
for the other agents to add themselves to the new architecture.

### Code review + fixes session — 2026-07-06 ✅

- Full-repo review at `6b705d5` → **CODE-REVIEW.md** (commit `ab1d8e1`): 2 high,
  11 medium, 13 low findings; H1/H2/M2/M3 verified empirically (sandboxed runs
  with stubbed `termux-*`/`adb`, read-only SSH probe of the live S24).
- **All findings fixed** in `b4e5e6a`; `version.json` → **1.4**. Highlights:
  repair-script helpers now defined before the flock branch (concurrent STATUS
  was `sshd=unknown` + command-not-found); repair-bridge liveness moved to a
  **pidfile** (`~/.repair-bridge.pid`) because `pgrep -f` self-matches on
  Termux — the bridge never started at boot; battery alarm fires only the
  lowest crossed tier and won't touch the wallpaper without a byte-verified
  backup; consent gate now **fails closed** on dialog timeout and recognizes
  Pixel launchers; watchdog notifications coalesce on stable ids and clear on
  recovery; repair script trims its logs; `adb-reconnect` no longer notifies
  every 60 s (access-monitor owns outage alerts); `termux_pkg` honors
  `--check`; `allow-external-apps` deployed via lineinfile + reload handler;
  shizuku.json patchers abort on failed reads instead of clobbering grants.
- ⚠ **Devices still run the pre-fix scripts** — next session should run
  `./mac/deploy-fleet.sh` and then `./mac/fleet-health.sh`. On each phone,
  verify after deploy: `~/.repair-bridge.pid` exists and the bridge survives a
  reboot; `battery alarm: ok` in fleet-health.

### 🎯 Active development device: **Galaxy S24 (USB `RFCX219CHKA`)**

Both phones run the AutoJs6 watchdog. Prefer the **S24 over USB** when plugged in for interactive work; use **7a over Tailscale** (`ssh p7a`) when the S24 is unplugged. Mac scripts use [shared/mac/resolve-adb.sh](shared/mac/resolve-adb.sh) (USB serial when present, else Tailscale wireless).

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
- ✅ `autojs6/mac/start-watchdog.sh` — relaunch main.js over USB/Tailscale ADB
- ✅ **Termux boot relaunch** for AutoJs6: `start-autojs6-watchdog.sh` + 5-min `boot-launcher.js` nudge in `start-adb.sh` (ASCII paths only; no AutoJs6 timed-task UI required)
- ✅ **Cold-reboot validation (AutoJs6 stack):** one PIN unlock → `boot-launcher.js` at ~18:18 and ~18:44, `port=open sshd=up invoke=ok`; Termux `sshd` self-restarted after unlock
- ✅ **`stayturgid-repair.sh` TMPDIR fix:** Termux `adb` daemon needs `TMPDIR=$PREFIX/tmp` or localhost:5555 checks falsely report `CLOSED_NO_SHELL`
- ✅ **Runtime validation (2026-07-05):** sshd kill → repair-bridge ~2s; `test-watchdog-once` invoke=ok; `test-catastrophic-once` Shizuku Start text-tap ok=true
- ✅ **Shizuku authorized apps synced for AutoJs6:** `autojs6/mac/grant-shizuku.sh` patches `/data/local/tmp/shizuku/shizuku.json` + `pm grant` (manager UI is json-driven, not pm-only)
- ✅ **Obtainium updates (2026-07-05 evening):** Shizuku 13.7.0, Termux:Styling/Widget/Float installed; AutoJs6 6.7.0 refreshed; `obtainium/mac/apply-updates.sh` added; Play Protect may block github-debug installs (verifier disable or manual **More details → Install anyway**)
- ✅ **Obtainium Shizuku installer:** `obtainium/mac/enable-shizuku-installer.sh` — grants API_V23, syncs `shizuku.json`, toggles UI (confirmed on S24 2026-07-05)
- ✅ **Termux overlay permission:** `SYSTEM_ALERT_WINDOW` granted for `com.termux` + `com.termux.window` (Termux:Float)
- ✅ **Watchdog Tailscale probe:** `autojs6/lib/tailscale.js` — tun0 + ping `100.100.100.100`, notify + relaunch `com.tailscale.ipn` if down
- ✅ **Test scripts:** `test-tailscale-probe-once.js`, `test-stale-loop-once.js`; Mac runner `autojs6/mac/run-test.sh`
- ✅ **Tailscale-down live test (2026-07-05):** `autojs6/mac/test-tailscale-down.sh` — force-stop → `probe up=false` → watchdog cycle → relaunch → `up=true` (USB)
- ✅ **Ansible Termux skeleton + S24 validation:** `ansible/playbooks/termux-userland.yml` + `ansible/mac/deploy-termux.sh` (S24 in inventory). Installed Homebrew `ansible`; final S24 run completed `changed=0`, repair check `STATUS port=open shizuku=up sshd=up shell=yes`. Fixed inventory Python path (`.../bin/python`); playbook runs `pkg update && pkg upgrade -y` up front and before any `pkg install`; installs only missing packages; added `abseil-cpp`/protobuf deps after Termux `adb` ABI mismatch.
- ✅ Pushed to GitHub `master` @ `e5d89de`+ (doc alignment, repair flock, Tailscale-down live test, Ansible skeleton)

### Pixel 7a — AutoJs6 watchdog (migrated 2026-07-06)
- ✅ Port 5555 survives cold reboots (verified 2026-06-29)
- ✅ sshd survives cold reboots (Termux:Boot + self-heal loop)
- ✅ AutoJs6 watchdog deployed and running (`mode=autojs6`, 2026-07-06)
- ✅ Mac-side launchd keepalive with macOS notification on reconnect/failure
- ✅ **Obtainium full catalog imported** (32 apps; merges without duplicates)
- ✅ **AutoJs6 v6.7.0 installed**, `RUN_COMMAND` granted, project deployed, `repair-bridge.sh` validated
- ✅ Termux boot/repair scripts synced with S24 (2026-07-05 USB); Ansible `deploy-termux.sh p7a` green; `claude-presence.sh gate` deployed
- ✅ Reconnect path: Tailscale mDNS TLS endpoint → stable port 5555; health check green (Shizuku running, sshd up, port 5555 listening)

### Samsung Galaxy S24 (RFCX219CHKA) — **production AutoJs6**

> Historical bullets below (2026-07-01 initial setup) are superseded where they conflict — Shizuku, port 5555, and AutoJs6 watchdog are all validated 2026-07-05.

- ✅ Termux installed (GitHub signed), sshd running on port 8022
- ✅ Packages installed: openssh, android-tools, wget, git, python, curl, termux-api, runit
- ✅ `~/.termux/boot/start-adb.sh` deployed + Termux:Boot app opened (boot script will run on reboot)
- ✅ Termux runit sshd service fixed with proper env vars (PATH, HOME, PREFIX, TMPDIR, LD_LIBRARY_PATH)
- ✅ SSH key deployed to Termux `~/.ssh/authorized_keys`
- ~~Shizuku SSL / no Shizuku~~ → **resolved:** Shizuku 13.7.0 + wireless-debug Start text-tap validated (AutoJs6 catastrophic path)
- ~~Manual adb tcpip after reboot~~ → **resolved:** Shizuku TCP mode + cold-reboot validation

### S24 session 2026-07-05 — networking + watchdog hardening
- ✅ **Root cause of the old watchdog never restoring ADB found**: it wrote `adb_enabled`/`adb_wifi_enabled` into the **System** settings namespace; both settings actually live in **Global** (verified: `settings get global adb_enabled` → 1, secure/system → null)
- ✅ Tailscale added to Obtainium (github.com/tailscale/tailscale-android) and installed (`com.tailscale.ipn` v1.98.8); user signed in — S24 is **`dannys24` = `100.123.218.30`** on the tailnet (the `daniels-s24` entry is a stale 53-day-old registration, can be deleted in the admin console)
- ✅ **ADB over Tailscale verified**: `adb connect 100.123.218.30:5555`
- ✅ **Direct SSH over Tailscale verified**: `ssh -i ~/.ssh/termux_key -p 8022 djbclark@100.123.218.30` — no ADB forward needed (Android's WiFi SSH block doesn't apply to the tun interface)
- ✅ Battery-optimization exemptions added (deviceidle whitelist): Tailscale, Termux
- ✅ `start-adb.sh` updated with `termux-wake-lock` + deployed to S24 via SSH-over-Tailscale (checksums verified); wake-lock acquired live
- ✅ `mac/adb-reconnect.sh` rewritten: takes `[serial] [lan_ip] [tailscale_ip]` args, tries cached → USB-discovered LAN → Tailscale in order; per-serial IP cache; S24 launchd agent installed + loaded (`com.djbclark.stayturgid.adb-reconnect-s24.plist`)
- ⚠️ S24 LAN IP is DHCP — never hardcode it; use Tailscale `100.123.218.30`
- ✅ Tailscale **Always-on VPN** enabled 2026-07-05 (verified: `settings get secure always_on_vpn_app` → `com.tailscale.ipn`); "Block connections without VPN" deliberately left OFF — it would sever LAN ADB/mDNS whenever the tunnel blips
- ⚠️ **2026-07-05 02:40: S24 at 17% battery and discharging — the USB data cable is NOT charging it.** Phone must live on a real charger or all remote access dies with the battery

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
- **Proven auth-free restart (use this for the watchdog):** launch `moe.shizuku.privileged.api` MainActivity → accessibility-tap the **"Start"** button (wireless-debugging start) — this is what `autojs6/lib/shizuku.js` does by text-match. Verified working (started shizuku_server, no SSL error).
- Shizuku notification permission must be granted for the pairing/start flow (`pm grant moe.shizuku.privileged.api android.permission.POST_NOTIFICATIONS`).

### Repair channel CONFIRMED (tested 2026-07-05)
- **`adb -s localhost:5555 shell` from Termux = full shell uid 2000** (groups incl. `input`,`adb`,`log`). So while 5555 is open, the repair layer can run `input tap`, `settings put`, `setprop`, `am`, `svc` with shell privileges — **no accessibility UI automation and no Shizuku auth token needed.** This is the primary repair channel.
- Shizuku automation **START/STOP broadcasts REQUIRE the per-install auth token even when sent as shell** (verified: without it → `auth_errors` notification, `notify(1450, channel=auth_errors)`). Don't rely on broadcasts.
- **Catastrophic case** (5555 closed AND Shizuku down): no shell reachable → only the AutoJs6 accessibility tap (Shizuku "Start") or a reboot recovers. This is the one place accessibility automation is irreplaceable. Caveat: it can't tap behind a locked screen — the notification still fires, and the boot loop keeps retrying shell repairs.
- Division of labor: **Termux layer** = `stayturgid-repair.sh` (sshd + shell-based repairs via localhost:5555, runs from boot loop + called by watchdog). **AutoJs6 layer** = detection, notifications, and the accessibility catastrophic fallback.

### Remote-access hardening implemented 2026-07-05 (session 2)
- ✅ **mDNS TLS fallback** added to `adb-reconnect.sh` — discovers `adb-<SERIAL>-xxxx._adb-tls-connect._tcp` via `adb mdns services`; reconnects after reboot with no USB / no port 5555 (as long as this host is paired). Candidate order now: cached → USB-discovered LAN → mDNS TLS → Tailscale.
- ✅ **7a reconnect launchd agent** updated with its real LAN + Tailscale IPs (was running arg-less/default before).
- ✅ **Dead-man's switch**: `mac/access-monitor.sh` + `com.djbclark.stayturgid.access-monitor.plist` (every 5 min). Checks every ADB address AND an SSH port-8022 probe per device; fires a macOS notification (with sound) only after ~10 min of total outage across ALL paths, and once on recovery. Per-device consecutive-fail state in `~/.config/stayturgid/access-monitor/`. Installed + loaded; tested (both devices reachable → counters 0).
- ✅ **Low-battery alarm** (`termux/stayturgid-battery-alarm.sh`, called from boot loop): tier alerts at **30, 25, 20, 15, 10, 5%**, then every **1%** below 5 while discharging. Each tier: **colored screen blink** (purple×1 @30 … red×10 @5 and below), **torch** from 15% (count matches tier; DND = one quick flash). Normal hours: notification + toast + vibrate. **DND/silent:** screen (+ single torch) only. State resets on charge or above 30%.
- ✅ **`mac/deploy-fleet.sh`** — one command: Ansible Termux + boot-loop restart + AutoJs6 deploy/start for s24/p7a. **`mac/fleet-health.sh`** — quick SSH/ADB sanity check.
- ✅ **Daily `check-repo-version.sh`** — invoked from boot loop (max once per 24h); notifies when GitHub `version.json` moves ahead of last-seen stamp.
- ✅ **Same stack redeployed to 7a (2026-07-05, USB):** `start-adb.sh` (wake-lock + battery alarm + AutoJs6 nudge), `stayturgid-repair.sh` (TMPDIR fix), `claude-presence.sh`; boot loop restarted.
- ✅ Watchdog Tailscale probe (`autojs6/lib/tailscale.js` — tun0 + ping 100.100.100.100, relaunch if down)

### Remote-access resilience (both devices) — ≥2 independent methods, each able to repair the other

| # | Method | Path | Depends on | Can repair |
|---|--------|------|-----------|------------|
| 1 | ADB over WiFi/Tailscale | `adb connect <ip>:5555` | port 5555 open (Shizuku TCP / `adb tcpip`) | restart sshd, redeploy scripts, reinstall apps |
| 2 | SSH to Termux | `ssh p7a` / `ssh s24` (direct over Tailscale) | sshd running, Termux alive | re-open port 5555 (`adb tcpip` via Termux android-tools) |
| 3 | On-device auto-repair | AutoJs6 watchdog every 20 min + boot | AutoJs6 accessibility + Termux bridge | invokes `stayturgid-repair.sh`, Shizuku Start tap, notifies user |

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
| SSH to Termux | `ssh p7a` (Tailscale), or `adb -s 35261JEHN12374 forward tcp:8022 tcp:8022` then `ssh -i ~/.ssh/termux_key -p 8022 localhost` |
| AutoJs6 | `org.autojs.autojs6` v6.7.0 — watchdog (`main.js`) |
| Shizuku package | `moe.shizuku.privileged.api` (thedjchi fork v13.6.0.r1349-thedjchi-beta) |
| Termux package | `com.termux` (GitHub-debug via Obtainium) |
| Termux:Boot | `com.termux.boot` (GitHub-debug via Obtainium) |
| Termux:API | `com.termux.api` (GitHub-debug via Obtainium) + `termux-api` pkg in Termux |

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
| Shizuku | `moe.shizuku.privileged.api` (thedjchi) — survives cold reboot (verified 2026-07-05) |
| AutoJs6 | `org.autojs.autojs6` v6.7.0 — **production watchdog** (mode=autojs6, `main.js` running) |
| Termux | GitHub-signed stack via Obtainium (`com.termux` + addons) |
| Obtainium | Full stayturgid catalog; **Shizuku installer enabled** (`enable-shizuku-installer.sh`) |
| Automation mode | `/sdcard/stayturgid_automation_mode.txt` = `autojs6` |
| AutoJs6 watchdog | **Validated 2026-07-05** — watchdog + catastrophic + stale-loop + Tailscale probe |

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
**Always use uiautomator2 and Termux:API for device automation.** The repo no longer ships Maestro playbooks (`.maestro/` was removed). Raw ADB (`uiautomator dump`, `input tap`) is the fallback when uiautomator2 breaks.

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
  Caveats: one dump per step (slow, ~2s); coordinates shift between selection modes (some apps move their top-bar buttons as selection count changes — re-dump before every tap); `input swipe` same-point with duration is the long-press idiom.

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
ssh s24 '~/agent-presence.sh gate "Galaxy S24" Auto' # if active use is detected: 30s consent dialog (timeout=continue)
ssh s24 '~/agent-presence.sh on  "Galaxy S24" Auto'   # ongoing "🤖 Auto is using ..." notification
ssh s24 '~/agent-presence.sh off "Galaxy S24" Auto'   # removes notification + 2 pulses + vibrate
ssh s24 '~/agent-presence.sh resume'                  # clear a prior Pause choice
# same for p7a / "Pixel 7a"; agent name is 3rd arg or STAYTURGID_AGENT env (default: Auto)
# Screen-control sessions: request-screen (60s countdown modal) -> on -> poll stop-requested -> off
```

Script lives at `termux/claude-presence.sh` in the repo and `~/agent-presence.sh` on each device. Pair `on` with the USING announcement and `off` with FREE. The `gate` action checks screen/foreground state first; if the phone appears active, it shows a `termux-dialog` radio prompt with **Continue**, **Pause**, and **Check again in 10 minutes**. Timeout defaults to Continue. If SSH is down but ADB is up, run it via `adb -s <dev> shell "run-as ... claude-presence.sh on"` or just skip to the text announcement.

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
autojs6/                                — AutoJs6 watchdog (the automation stack)
  main.js                               — watchdog entry (20 min + boot)
  lib/                                  — guard, termux bridge, shizuku/tailscale, notifications
  mac/deploy.sh, setup-autojs6.sh, set-automation-mode.sh, start-watchdog.sh, grant-shizuku.sh, run-test.sh
obtainium/                              — Obtainium import JSON for all GitHub-sideloaded APKs
  stayturgid-apps.json                  — full catalog (Termux, Shizuku, Tailscale, AutoJs6)
  mac/sync-to-device.sh                 — push + open Obtainium import on device
  mac/apply-updates.sh                  — drive bulk update UI from Mac
  mac/enable-shizuku-installer.sh       — one-time: quieter installs via Shizuku API
ansible/                                — Termux userland playbook (SSH/Tailscale)
  playbooks/termux-userland.yml
  mac/deploy-termux.sh
termux/
  boot/start-adb.sh                     — deploy to ~/.termux/boot/ on device
  stayturgid-repair.sh                  — Termux-side self-heal
  check-repo-version.sh                 — optional update notifier
shared/mac/
  resolve-adb.sh                        — USB-first ADB target resolver (p7a/s24 aliases)
mac/
  adb-reconnect.sh                      — Mac-side keepalive script (run by launchd)
  resolve-adb.sh                        — shim → shared/mac/resolve-adb.sh
  com.djbclark.stayturgid.adb-reconnect.plist — launchd agent (runs every 60s)
version.json                            — repo release version + changelog
```

---

## Pixel 7a accessibility state — verify at session start

Known-good `enabled_accessibility_services` on 7a (as of 2026-07-06; **append only** — never replace the whole list). Other entries are from apps installed on the device; stayturgid requires only AutoJs6:
```
com.samruston.buzzkill/com.samruston.buzzkill.background.accessibility.WorkaroundAccessibilityService
com.notch.touch/com.notch.touch.lock.tas
com.wispr.flowapp/com.wispr.flowapp.service.FlowAccessibilityService
org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher
```

At the start of each session, verify these are all still enabled:
```bash
adb shell settings get secure enabled_accessibility_services | tr ':' '\n'
```

⚠️ A previous session accidentally wiped accessibility services by running `settings put secure enabled_accessibility_services <value>` which **replaces** (not appends) the list. If any are missing, restore with the full colon-separated list above. See HACKING.md Part 5 for the safe append protocol.

---

## Known issues / gotchas

- **uiautomator2 `d.exists()` returns False:** Usually means a dismissable popup from another app is blocking the UI. Fix: `d(text='OK').click()` to dismiss first.
- **Taps not registering at the screen edge:** Tap slightly inward (e.g., x=1010 not x=1028) — the gesture navigation zone interferes.
- **Reddit is blocked** in Claude Code. Use PullPush API instead: `https://api.pullpush.io/reddit/search/submission/?ids=<post_id>`
- **Termux `pkg upgrade` on stale installs:** if `curl` fails with an OpenSSL/ngtcp2 symbol error, run `apt full-upgrade` (or `dpkg --force-confold --configure -a` after killing a stuck upgrade). Conffile prompts (`openssl.cnf`, `sources.list`) block non-interactive runs unless you use `--force-confold` or apt `Dpkg::Options::=--force-confold`.
- **`pgrep -f` self-match (Termux vs macOS):** on Termux, `pgrep -f X` matches the calling script/ssh cmdline containing `X`; macOS pgrep doesn't. Test process guards on-device; prefer pidfiles. (CODE-REVIEW.md H2.)
- **Device IP changes on DHCP.** The mac-side script auto-discovers via USB. Always verify with: `adb -s 35261JEHN12374 shell "ip addr show wlan0"`

See **HACKING.md** for the full development environment setup (all tool versions, Obtainium sources, clean-install walkthrough).

---

## How to start a new AI session

```bash
claude   # open interactive session in terminal (NOT Warp)
```

Verify session type is Pro/Max (not API billing) with `/status`. The working directory is `~/upmon-handoff/` (legacy name) — separate from the project at `~/stayturgid/`.

---

## Architecture research — unified orchestration (LAST — research only)

> **Status:** Queued for independent research and architectural consideration. **Do not refactor the repo yet.** The current hybrid layout (Mac shell scripts + partial Ansible + on-device AutoJs6 + Obtainium scripts) is working production. This section captures a proposed direction for a future consolidation decision.

### Question

Could the whole stayturgid system — Termux/SSH, Termux:API, ADB, uiautomator2, Shizuku, AutoJs6 deploy, Obtainium, launchd — be refactored as **one Ansible project** (or one other sysadmin framework), with everything expressed as modules/roles/collections?

### Preliminary recommendation: Ansible core + custom modules

For this Android-focused, SSH-heavy, multi-tool workflow, the best **overall** shape is an **extensible Ansible orchestration layer** with custom Python modules/roles, optionally augmented by a small Python library for Android-specific glue that doesn't fit YAML well.

#### Why Ansible fits stayturgid

| Strength | How it maps here |
|----------|------------------|
| SSH-first | Termux `sshd` on :8022 over Tailscale is already the control plane; `ansible/inventory/hosts.yml` + `termux_userland` role prove the pattern |
| Modularity | Roles/collections match the desire for "everything as a module of the system" — Termux userland, Shizuku grants, Obtainium catalog, AutoJs6 deploy |
| Complex workflows | Playbooks handle sequencing (`pkg update` → upgrade → install), conditionals (USB vs Tailscale ADB), idempotency, per-host vars, Vault for keys |
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
    mac_launchd/        # adb-reconnect plists (localhost delegate_to)
  library/              # custom modules (Python):
    termux_api.py       # wrap termux-battery-status, termux-dialog, etc.
    adb_shell.py        # resolve USB/Tailscale target, run adb shell
    uiautomator2_run.py # invoke pipx u2 scripts with serial from inventory
    shizuku_rish.py     # privileged settings when localhost:5555 up
  playbooks/
    site.yml            # full device bring-up
    deploy-watchdog.yml # AutoJs6 deploy + start
    validate.yml        # repair STATUS, tailscale probe, cold-reboot checklist
```

#### Custom module candidates

- **`termux_api_call`** — Termux:API from SSH (`termux-notification`, `termux-dialog`, battery)
- **`adb_command`** — Mac-side ADB with inventory-driven serial (wrap `shared/mac/resolve-adb.sh` logic)
- **`uiautomator2_task`** — run one-off UI scripts from the control node
- **`shizuku_privileged`** — wrap `autojs6/mac/grant-shizuku.sh`-style json + pm grant flows
- **`stayturgid_repair_check`** — parse `STATUS port=…` from repair script over SSH

Non-native tools (uiautomator2, Shizuku, Termux:API) are **not** Ansible builtins — wrap them in `library/` modules or `ansible.builtin.script` with clear contracts.

#### Limitations and mitigations

| Limitation | Mitigation |
|------------|------------|
| UI automation is Mac-side + device-screen dependent | Keep uiautomator2 in Python modules; Ansible tasks call them; document Samsung content-URI grant failure (HACKING.md) |
| ADB and SSH are two channels | Inventory vars + `delegate_to: localhost` for Mac ADB tasks; playbooks order SSH-first, ADB fallback |
| On-device watchdog must stay on-device | Ansible **deploys** AutoJs6; does not replace 20-min runtime loops |
| Play Protect / Obtainium / human PIN | Tag tasks `manual` or use `pause:` prompts; don't pretend full unmanned bootstrap |
| Stale Termux mirrors / conffile prompts | Already hit on 7a — role should use `DEBIAN_FRONTEND=noninteractive` + `Dpkg::Options::=--force-confold` |
| Scale | 2 phones — Ansible parallelism is plenty; Salt only matters at fleet scale |

### What should **not** move into Ansible (likely)

- **Runtime watchdog logic** — `stayturgid-repair.sh`, AutoJs6 `main.js` (Ansible configures; devices heal themselves)
- **Cold-reboot Shizuku Start tap** — accessibility-driven; stays in AutoJs6 unless replaced by a maintained UI module
- **Mac launchd keepalive** — can be a `mac_launchd` role with `delegate_to: localhost`, but it's orthogonal to phone SSH
- **Obtainium in-app UI** — `enable-shizuku-installer.sh` + uiautomator2; candidate for a module, not pure YAML

### Strong alternatives (if Ansible boundary feels wrong)

1. **Pure Python orchestrator** (Invoke/Fabric + `subprocess` + uiautomator2 + ppadb)
   - Better for dense UI/state-machine logic (multi-dialog UI chains)
   - Structure as packages: `stayturgid.termux`, `.adb`, `.autojs6`
   - Prefect/Dagster/Airflow only if dependency graphs become large (probably overkill for 2 phones)

2. **SaltStack (Salt SSH)**
   - Faster parallel execution, event-driven reactor model
   - Higher setup cost; weaker ecosystem for "personal phone" DIY docs

3. **Hybrid: Ansible + on-device AutoJs6**
   - Ansible for deploy/config; AutoJs6 for rich UI automation (already production on both phones)
   - Matches current architecture; formalize the split in playbooks

### Current state vs target (gap analysis)

| Layer | Today | Ansible-native? |
|-------|-------|-----------------|
| Termux packages + scripts | ✅ `termux_userland` role | Yes |
| Shizuku install/grant | Mac shell scripts | Partial — custom module |
| Obtainium catalog/install | Mac shell + u2 | Partial — script module |
| AutoJs6 deploy/start | `autojs6/mac/*.sh` | Partial — role + adb delegate |
| ADB reconnect launchd | `mac/adb-reconnect.sh` + plist | localhost role |
| Validation tests | scattered `mac/run-test.sh`, test JS | playbook `validate.yml` |

**Pain points a unified layer would address:** duplicated device resolution (`resolve-adb.sh` vs inventory), no single `site.yml` bring-up, manual ordering documented only in HANDOFF, mixed idempotency story outside Ansible.

**Pain points it would not fix:** Play Protect, PIN unlock, DHCP LAN IP, Samsung Shizuku/content-URI quirks.

**Do not implement until the user explicitly approves a refactor.** Until then, continue extending the existing `ansible/` skeleton and Mac scripts as needed.

---

### Migration priority (when approved): move as much as possible to Ansible

Recommended order — highest value / lowest risk first:

| Phase | Target | Why first |
|-------|--------|-----------|
| **1** | **Termux packages** (`termux_pkg` module) | ✅ Shipped in `ansible/library/termux_pkg.py`; role uses it |
| **2** | Termux files/templates (expand `termux_userland`) | ✅ mostly done — scripts, boot, `termux.properties`, mode files |
| **3** | Mac-delegated ADB (`adb_shell`, `android_apk`) | Wrap `resolve-adb.sh`; sideload APKs without Obtainium UI |
| **4** | Obtainium catalog + updates (`obtainium_app`) | Deep links + JSON import + optional u2/Shizuku install path |
| **5** | Shizuku grants, AutoJs6 deploy roles | Compose existing shell scripts |
| **6** | Play Store semi-automation (`google_play_app`) | Weakest — no silent install API; document limits clearly |
| **7** | uiautomator2 as Ansible action plugins | UI state machines belong in Python called from tasks |

**Principle:** anything reachable over **Termux SSH** moves first; anything needing **Mac ADB + screen** gets a `delegate_to: localhost` role with explicit `tags: [ui, manual]` for human-in-the-loop steps.

---

### Termux packages — fault-tolerant module design (`termux_pkg`)

Today's `termux_userland` role uses the custom **`termux_pkg`** module (`ansible/library/termux_pkg.py`) for update/upgrade/install with conffile recovery — not a raw shell block.

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
| stayturgid `termux_userland` role | Uses `termux_pkg` module in production |

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
4. **`json_import`** — push JSON to `/sdcard/Download/`, u2/automation open Obtainium → Import/Export → Obtainium Import (text-button dialog chain).
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
    package: com.tailscale.ipn
    state: present          # present = installed; open_store = just open Play page
    method: check_only      # check_only | open_store | semi_auto
  delegate_to: localhost
```

- **`check_only`** (default): `adb shell pm path {{ package }}` → ok if installed.
- **`open_store`**: `am start -a android.intent.action.VIEW -d market://details?id=...` — tags `[manual]`.
- **`semi_auto`**: u2 loop: open store → wait for Install button → tap (fragile, locale/OEM dependent) — **not recommended** except as escape hatch.

**Recommendation:** For stayturgid, **prefer Obtainium + GitHub/F-Droid** for every app we control; reserve `google_play_app` for **presence checks only** and document Play-only apps as manual/Obtainium-not-available exceptions.

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

1. ~~**Prototype `termux_pkg`**~~ — ✅ shipped (`ansible/library/termux_pkg.py`).
2. Prototype `stayturgid_repair_check` (SSH → parse STATUS).
3. Prototype `android_apk` + `adb_serial` from inventory (merge `resolve-adb.sh` logic into module util).
4. Prototype `obtainium_app` **layer A only** — deep link + `pm list packages` check for one GitHub app.
5. Sketch `playbooks/site.yml` composing Termux + AutoJs6 deploy roles.
6. Write ADR with explicit non-goals (Play Store silent install, full unmanned Obtainium bulk update on Samsung without Shizuku).
7. Decide collection name: `community.stayturgid` vs upstream contribution to `ivansible.termux`.

### References (prior art bibliography)

- Termux + Ansible: [termux-jenkins-automation](https://github.com/gounthar/termux-jenkins-automation), [ansible-android-termux](https://github.com/guoqiao/ansible-android-termux), [ivansible/termux](https://galaxy.ansible.com/ui/repo/published/ivansible/termux/), [ansible#81547](https://github.com/ansible/ansible/pull/81547)
- ADB + Ansible: [AnsibleAndroidAutomationADB](https://github.com/shresthagrawal/AnsibleAndroidAutomationADB), [ADB connection plugin gist](https://gist.github.com/rpavlik/a0c785fbe568fd4c7fbb67893ec4507a), [ansibel-nspanel](https://github.com/Bierchermuesli/ansibel-nspanel)
- Obtainium automation: [Obtainium repo](https://github.com/ImranR98/Obtainium), [wiki sources](https://wiki.obtainium.page/sources/), [deep links #918](https://github.com/ImranR98/Obtainium/issues/918), [Dhizuku install #1611](https://github.com/ImranR98/Obtainium/issues/1611), [import discussion #1739](https://github.com/ImranR98/Obtainium/discussions/1739)
- Play Store automation limits: [Stack Overflow package install](https://stackoverflow.com/questions/42125096/how-to-automate-installation-of-play-store-apps-by-package-name), [How-To Geek Obtainium+Shizuku](https://www.howtogeek.com/this-is-how-i-keep-my-sideloaded-android-apps-updated-automatically/)
- stayturgid today: `ansible/roles/termux_userland/`, `obtainium/mac/apply-updates.sh`, `obtainium/mac/enable-shizuku-installer.sh`, `obtainium/stayturgid-apps.json`
