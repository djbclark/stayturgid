# stayturgid — AI Handoff Document

> **Purpose:** This file is a prompt for an AI agent taking over development. Read it fully before doing anything else. It describes what the project does, the current state, the environment, the tooling rules, and what's next.
>
> **Modular docs:** each subfolder is usable on its own. Human index: [docs/README.md](docs/README.md) · [README.md](README.md). Full clean-install setup + device gotchas: [HACKING.md](HACKING.md). Git history has the detailed narrative of every change; this file is the condensed durable record.

---

## What this project does

**stayturgid** keeps wireless ADB (port 5555), Shizuku, and SSH alive on **two personal, unrooted consumer phones** — a Google Pixel 7a and a Samsung Galaxy S24 (SM-S921U1), both Android 16 — across cold reboots, and makes them reliably reachable from the Mac over Tailscale via **two independent, mutually-repairing channels (ADB + SSH)**.

After a reboot and PIN unlock:
1. **Shizuku** (thedjchi fork) auto-starts via Android Wireless Debugging and uses TCP mode to call `adb tcpip 5555` — opens port 5555 without USB.
2. **Termux:Boot** fires `~/.termux/boot/start-adb.sh` → starts `sshd`, then loops self-healing sshd every 5 min (liveness by pidfile, relaunch via `setsid`).
3. **AutoJs6** `main.js` (20-min interval + boot via `boot-launcher.js`) → Termux `RUN_COMMAND` → `stayturgid-repair.sh`, notifications, Shizuku UI repair if needed.

On the Mac, a launchd agent runs every 60 s and reconnects `adb connect <ip>:5555` if it drops, handling DHCP IP changes automatically.

**Two-layer self-heal:** the **Termux layer (primary)** keeps the phones reachable via shell over localhost:5555 — this is what must never break. The **AutoJs6 layer (secondary)** adds detection, notifications, and the accessibility-only catastrophic fallback.

---

## How updates work

GitHub `master` is the source of truth. To release:
1. Bump `version.json` (`version` + `changelog`), commit, push.
2. `./mac/deploy-fleet.sh` — full fleet via Ansible (`CHECK=1 ./mac/deploy-fleet.sh` = dry run). Idempotent (re-run = `changed=0`). Or the granular path: `./ansible/mac/deploy-termux.sh [--limit host]` then `./autojs6/mac/deploy.sh {p7a,s24}` + `./autojs6/mac/start-watchdog.sh {p7a,s24}`.

Optional on-device notifier: `check-repo-version.py` (max once/24 h) fires `termux-notification` when GitHub `version.json` moves ahead of the last-seen stamp.

---

## 🚦 Cold-start — current state (read this first)

**As of 2026-07-07.** Three-device fleet: **s24**, **p7a**, **hd8** (Kindle Fire HD 8 added today). AutoJs6-only stack (legacy Tasker removed 2026-07-06). Repo v2.4.

**Healthy / done:**
- **s24 + p7a fully green** — `make verify` PASS after AutoJs6 `pm clear` reset (2026-07-07); watchdog liveness fresh on both; Tasker legacy clean on p7a.
- **Primary Termux self-heal: solid on all three** — `sshd` + boot loop + repair bridge; reachable via `ssh s24` / `ssh p7a` / `ssh hd8` (hd8 over LAN `192.168.68.69:8022` or USB forward).
- **Single-root file consolidation + self-healing** — every writer `mkdir -p`s its dir; deleting the stayturgid root just recreates it.
- **AutoJs6 startup hardened** — `main.js` always establishes the 20-min interval; `guard.enforce()` degrades instead of blocking.
- **Device-tier watchdog liveness check** — fresh `[watchdog]` line < 30 min (s24/p7a passing).
- **hd8 (Kindle Fire HD 8) onboarded** — GitHub-debug Termux stack, thedjchi Shizuku v13.7, AutoJs6 6.7.0, Ansible inventory + `ssh hd8` alias. Fire OS uses `~/.stayturgid/shared` for Termux state/logs (cannot write `/sdcard` from Termux); AutoJs6 project + logs stay on `/sdcard/stayturgid/` (deployed via Mac `adb push`).

**⚠ hd8 Fire OS caveats (expected TODOs when USB unplugged):**
- **Split storage** — Termux under `~/.stayturgid/shared` (cannot read/write `/sdcard`); AutoJs6 under `/sdcard/stayturgid/`. Watchdog skips the Termux RUN_COMMAND bridge on split-storage devices (boot loop owns repair).
- **No Termux→localhost:5555 loopback** — privileged repair from Termux cannot use `adb connect localhost:5555`. Mac USB/LAN adb works (`GN43T503430603PS` / `192.168.68.69:5555`).
- **Tailscale installed (pending login)** — APK v1.98.8 sideloaded; VPN permission granted. **You:** finish Sign in on hd8, enable **Always-on VPN**, then set `ansible_host` in `hosts.yml` to the Tailscale IP and run `ansible-playbook ansible/playbooks/mac.yml` to refresh `devices.conf` / `~/.ssh/config`.
- **Battery** — keep hd8 charged when off USB.

**Deploy / test:**
- Deploy: `./mac/deploy-fleet.sh`. Verify (read-only device tier): `make verify`.
- Test (no device): `make test` (syntax/lint + shell TAP + pytest twins + `ansible-test units`). `make lint` = shellcheck/ansible-lint/yamllint. First run: `make test-venv`. CI runs `make test` on push.

---

## Fleet layout & file roots (single-root, self-healing) — 2026-07-07

All stayturgid files live under ONE root per filesystem (was scattered at /sdcard root, ~/ home, ~/Library/Logs):

| Filesystem | Root | Subdirs |
|-----------|------|---------|
| Device shared | `/sdcard/stayturgid/` (default) or `~/.stayturgid/shared` (Fire OS) | `autojs6/ state/ logs/ run/ tmp/` |
| Termux private | `~/.stayturgid/` | `bin/ logs/ run/ state/ battery-colors/ env` |
| Mac | `~/.config/stayturgid/` | `devices.conf logs/ state/` |

Deployed scripts → `~/.stayturgid/bin`; AutoJs6 project → `/sdcard/stayturgid/autojs6`; `watchdog.log` → `logs/`; `device.json` + `automation_mode` → `state/`; repair-bridge trigger → `run/repair_now`; pidfiles (`bootloop.pid`, bridge) → `run/`. **Self-healing:** python `makedirs(exist_ok=True)`, shell `mkdir -p`, AutoJs6 `files.ensureDir` + `config.ensureDirs()`.

⚠ **`device.json` is only re-rendered by Ansible** (`ansible/playbooks/fleet.yml`, task "Render device profile from inventory layers"). Deleting `/sdcard/stayturgid/state/` self-heals the *dir* but leaves device.json empty → AutoJs6 falls back to `device=generic` (loses tap coords). If you wipe state for a self-heal test, re-render device.json afterward (`ansible-playbook … --start-at-task="Render device profile from inventory layers" --limit <host>`).

---

## Device facts

### Google Pixel 7a (primary)
| Field | Value |
|-------|-------|
| Device / Android | Google Pixel 7a / 16 |
| USB serial | `35261JEHN12374` |
| Wireless ADB | `100.65.230.108:5555` (Tailscale, stable); LAN `192.168.68.x` is DHCP — do not hardcode |
| SSH | `ssh p7a` (alias → Tailscale :8022, key auth, no 1Password dialog) |
| Termux uid | `u0_a591` (changed from a590 in the 2026-07-05 GitHub/Obtainium swap) |
| AutoJs6 | `org.autojs.autojs6` v6.7.0 |
| Shizuku | `moe.shizuku.privileged.api` (thedjchi fork v13.6.0.r1349-thedjchi-beta) |
| Termux stack | GitHub-debug via Obtainium (`com.termux` 0.118.3 + api/boot/styling/widget/float) — all share-uid aligned; `termux-api` works |
| Tailscale | always-on VPN ON (the key to reboot-proof reachability) |

### Kindle Fire HD 8 (`hd8` — USB `GN43T503430603PS`)
| Field | Value |
|-------|-------|
| Device / Android | Amazon Kindle Fire HD 8 (KFRASWI) / 11 (API 30) |
| USB serial | `GN43T503430603PS` |
| Wireless ADB | `192.168.68.69:5555` (LAN; Mac `adb connect`); Tailscale pending login (APK installed) |
| SSH | `ssh hd8` (alias → LAN :8022, `u0_a310`, key auth); USB: `adb forward tcp:8022 tcp:8022` |
| Termux | GitHub-debug `com.termux` 0.118.3 + api/boot (share-uid); **must** be debug build for `run-as` recovery |
| AutoJs6 | `org.autojs.autojs6` v6.7.0 — project at `/sdcard/stayturgid/autojs6` |
| Shizuku | thedjchi fork v13.7.0 — TCP mode ON |
| Fire OS notes | Termux state/logs under `~/.stayturgid/shared` (`STAYTURGID_SD` in `~/.stayturgid/env`); no Termux localhost:5555 loopback |

### Samsung Galaxy S24 (primary dev device — USB `RFCX219CHKA`)
| Field | Value |
|-------|-------|
| Device / Android | Samsung Galaxy S24 (SM-S921U1) / 16 (SDK 36) |
| USB serial | `RFCX219CHKA` (**use when plugged in**) |
| Wireless ADB | `adb connect 100.123.218.30:5555` (Tailscale, stable) — also `192.168.68.60:5555` LAN (DHCP) |
| SSH | `ssh s24` (alias → Tailscale, key auth, no 1Password dialog); via USB: `adb -s RFCX219CHKA forward tcp:8022 tcp:8022 && ssh -p 8022 localhost` |
| Tailscale | `dannys24` = `100.123.218.30`; always-on VPN ON. "Block connections without VPN" deliberately OFF (would sever LAN ADB/mDNS on tunnel blips) |
| AutoJs6 | `org.autojs.autojs6` v6.7.0 |
| Shizuku | thedjchi fork — **survives cold reboot** (persistent wireless-debugging pairing established) |
| Termux / Obtainium | GitHub-signed stack via Obtainium; Shizuku installer enabled |
| ⚠ Power | the USB *data* cable does NOT reliably charge it — keep it on a real charger or remote access dies with the battery |

Prefer the **S24 over USB** for interactive work when plugged in; use **7a over Tailscale** otherwise. Mac scripts resolve the target via [shared/mac/resolve-adb.sh](shared/mac/resolve-adb.sh) (USB serial when present, else Tailscale).

---

## Remote-access resilience — the architecture (≥2 independent, mutually-repairing methods)

| # | Method | Path | Depends on | Can repair |
|---|--------|------|-----------|------------|
| 1 | ADB over WiFi/Tailscale | `adb connect <ip>:5555` | port 5555 open (Shizuku TCP) | restart sshd, redeploy scripts, reinstall apps |
| 2 | SSH to Termux | `ssh p7a` / `ssh s24` (Tailscale) | sshd + Termux alive | re-open 5555 (`adb tcpip` via Termux android-tools) |
| 3 | On-device auto-repair | AutoJs6 watchdog (20 min + boot) | AutoJs6 a11y + Termux bridge | invokes `stayturgid-repair.sh`, Shizuku Start tap, notifies |

### Repair channel — confirmed primitives (tested live 2026-07-05)
- **`adb -s localhost:5555 shell` from Termux = full shell uid 2000** (groups incl. `input`, `adb`, `log`). While 5555 is open, the repair layer runs `input tap` / `settings put` / `setprop` / `am` / `svc` with shell privileges — **no accessibility and no Shizuku token needed.** This is the primary repair channel. (Needs `TMPDIR=$PREFIX/tmp` or localhost:5555 checks falsely report `CLOSED_NO_SHELL`.)
- **Catastrophic case** (5555 closed AND Shizuku down): no shell reachable → only the AutoJs6 accessibility tap on Shizuku "Start", or a reboot, recovers. This is the one place accessibility automation is irreplaceable; it can't tap behind a locked screen (notification still fires; boot loop keeps retrying shell repairs).
- **RUN_COMMAND from an adb shell is BLOCKED** ("Requires permission com.termux.permission.RUN_COMMAND"). The shell-usable trigger for repair is the **bridge**: `touch /sdcard/stayturgid/run/repair_now` (2 s poll). `run-as com.termux` works on these debuggable Termux builds as an adb-side recovery path when SSH is down (must export PATH/LD_LIBRARY_PATH/HOME/PREFIX/TMPDIR).

### Shizuku primitives (for the watchdog)
- shizuku_server runs as **`shell` uid**, has its own process watchdog (respawns on kill), and survives `am force-stop` of the manager app — very resilient.
- **START/STOP automation broadcasts REQUIRE the per-install auth token** even when sent as shell (without it → silently ignored / `auth_errors`). Token changes on reinstall → fragile; don't rely on it.
- **Proven auth-free restart (what `autojs6/lib/shizuku.js` does):** launch the manager MainActivity → accessibility-tap the **"Start"** button (wireless-debugging start). Needs POST_NOTIFICATIONS granted.
- On Samsung, `adb_wifi_enabled` reads 0 after boot but 5555 is open anyway — the flag is cosmetic; Shizuku opens 5555 via its own path (so the old watchdog's `Custom Setting adb_wifi_enabled=1` was a no-op). adb enable flags live in the **global** namespace, not system/secure.

### Cold-reboot behavior (both validated 2026-07-05)
After reboot + one PIN unlock, zero further intervention: Tailscale always-on tun0 comes up on unlock; sshd :8022 up (Termux:Boot); Shizuku auto-starts; Termux boot loop running. Port 5555 may lag briefly (7a: down at ~206 s, self-restored by ~338 s) then stays open. **Always-on VPN is the key that makes the tailnet leg reboot-proof — enable it on every device.**

---

## Tooling rules (follow exactly)

### Android automation tools
Use **uiautomator2 + Termux:API**; raw ADB (`uiautomator dump` → parse bounds → `input tap`) is the reliable fallback when higher-level tools break (one dump per step, ~2 s; re-dump before each tap — some apps move top-bar buttons as selection state changes; `input swipe X Y X Y 1000` = long-press). `scrcpy -s <target> --stay-awake` for live mirror. Keep awake during automation: `adb shell svc power stayon true` (set `false` when done). uiautomator2 in Python needs the pipx venv on `sys.path` (`/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages`); `uiautomator2 init` pushes u2.jar after a reboot.

### Termux packages (CRITICAL)
At the start of any Termux setup/maintenance, and **before every `pkg install`**: `pkg update && pkg upgrade -y`. The Ansible `termux_userland` role + `termux_pkg` module do this automatically (mirror pinned to `packages-cf.termux.dev` for determinism). Prefer **Obtainium/GitHub over BOTH Play Store and F-Droid**; shared-uid Termux addons must all match signature.

### Phone announcement protocol (CRITICAL)
Before any device interaction, emit a standalone message naming the phone(s): **🚨📱🚨 USING — &lt;phone(s)&gt; 🚨📱🚨**. When done and not expecting to touch them again until the next user reply: **✅📱✅ FREE — &lt;phone(s)&gt; ✅📱✅**. Announce a second phone if picked up mid-run.

### On-device presence indicator (run alongside the announcement)
So it's obvious from the phone itself that automation is live (torch + vibration + ongoing notification only — nothing on the screen surface, so it never interferes with UI dumps/taps):
```bash
ssh s24 '~/agent-presence.sh gate "Galaxy S24" Auto'  # if active use detected: consent dialog (timeout=continue)
ssh s24 '~/agent-presence.sh on  "Galaxy S24" Auto'   # ongoing "🤖 Auto is using ..." notification
ssh s24 '~/agent-presence.sh off "Galaxy S24" Auto'   # remove notification + pulses
# same for p7a / "Pixel 7a"; agent name = 3rd arg or STAYTURGID_AGENT (default Auto)
# Screen-control sessions: request-screen (60s countdown modal) -> on -> poll stop-requested -> off
```
The protocol is **shared, agent-agnostic infrastructure** — do NOT fork per-agent copies. Any agent (Claude/GPT/Gemini) identifies via the 3rd arg / `STAYTURGID_AGENT`, aborts on `request-screen` exit 75, and on `stop-requested` exit 0 has ~1 min to wrap up. Script: `termux/claude-presence.sh` (repo) → `~/agent-presence.sh` (device); `agent-presence.sh` is the current name, `claude-presence.sh` a compat shim.

### Shell conventions
Never assume the default shell — macOS is zsh, **Termux has no zsh by default**. Declare bash in every shebang; run remote commands via `ssh host 'bash -s'` (stdin), never bare through the login shell. The Bash tool here runs zsh: brace `${var}` before `:`; quote whole remote command strings. `set -e` deliberately NOT used in boot/loop/runtime scripts (a boot loop must survive individual command failures).

---

## Accessibility state — verify at session start (APPEND ONLY)

`settings put secure enabled_accessibility_services <value>` **replaces** the whole list — running it with one service silently wipes every other a11y service. Always **append**; restore the original at session end. See HACKING.md Part 5 for the safe protocol.

Pixel 7a known-good list (as of 2026-07-06; stayturgid needs only AutoJs6 — the rest are the user's other apps):
```
com.samruston.buzzkill/com.samruston.buzzkill.background.accessibility.WorkaroundAccessibilityService
com.notch.touch/com.notch.touch.lock.tas
com.wispr.flowapp/com.wispr.flowapp.service.FlowAccessibilityService
org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher
```
Verify: `adb shell settings get secure enabled_accessibility_services | tr ':' '\n'`. Note: `dumpsys accessibility` "Bound services:" lists by **friendly label** (`label=AutoJs6`), not class name — grepping the class miscounts binding. Force-stopping an a11y app unbinds/drops it from the list (re-add is append-only via repair).

---

## Key files

```
autojs6/                     — AutoJs6 watchdog (the automation stack)
  main.js                    — entry: hardened startup + always-on 20-min interval + boot
  lib/                       — config, guard (auto.service a11y check), watchdog, termux bridge,
                               shizuku/tailscale, notify, log  (all mkdir -p / files.ensureDir self-heal)
  scripts/boot-launcher.js   — Termux:Boot nudge; mainAlreadyRunning() matches the full main.js path
  mac/                       — deploy.sh, setup-autojs6.sh, start-watchdog.sh, grant-shizuku.sh, run-test.sh
termux/
  boot/start-adb.sh          — Termux:Boot entry: sshd + 5-min self-heal loop (pidfile) + battery alarm + AutoJs6 nudge
  py/*.py + *.sh shims       — repair, agent-presence, screen-awake-guard, battery-alarm, check-repo-version
                               (Python is DEPLOYED; agent-presence + repair keep a thin ~/*.sh compat shim)
  repair-bridge.sh           — 2 s poll of run/repair_now (RUN_COMMAND-free trigger)
ansible/                     — fleet deploy; inventory/hosts.yml + inventory/group_vars taxonomy layers
  playbooks/fleet.yml, mac.yml   roles: termux_userland, autojs6_watchdog, obtainium_apps
ansible_collections/stayturgid/fleet/   — termux_pkg + obtainium_app modules (FQCN stayturgid.fleet.*)
obtainium/                   — stayturgid-apps.json catalog + mac/ sync/apply/installer scripts
fdroid/                      — side-project docs + support for F-Droid (Neo Store) and Play (Aurora Store)
ansible/roles/fdroid_repos/  — Ansible role + module for fdroidcl (Mac) repo management + explicit push to on-device client (bypasses chooser, preference order Neo > Droid-ify > F-Droid)
ansible/roles/play_store/    — skeleton role for Aurora Store client setup (Shizuku grant, gplaycli notes)
shared/mac/                  — resolve-adb.sh, stayturgid_device.py (shizuku.json patcher + UI parsing)
mac/                         — adb-reconnect.py, access_monitor.py (launchd via ansible mac.yml); deploy-fleet.sh, fleet-health.sh
tests/                       — device_tier.py + python/ (pytest twins) + test-*.sh TAP harness; Makefile, configure
version.json                 — repo release version + changelog
```

---

## Known issues / gotchas

- **uiautomator2 `exists()` False:** usually a dismissable popup from another app blocking the UI — `d(text='OK').click()` first.
- **Taps at the screen edge:** tap slightly inward (gesture-nav zone interferes).
- **`pgrep -f` self-match on Termux** (not macOS): matches the caller's own cmdline → process guards must use **pidfiles** (`/proc/$pid/cmdline` check), and boot-loop restart must never `pkill -f start-adb.sh` (SIGTERMs itself). Test guards on-device. (CODE-REVIEW.md H2.)
- **sshd operator lockout (OpenSSH 10.x PerSourcePenalties):** automation bursts can lock the Mac out. Ansible sets `PerSourcePenalties no`; device tier asserts it. **Never `pkill; sshd` via `run-as`** — that starts sshd with run-as's Android-only PATH, poisoning SSH sessions (`command not found`); recovery is messy. If poisoned: kill the bad sshd by PID, restart with full PATH/PREFIX/HOME/TMPDIR exported, or reboot.
- **Termux `pkg upgrade` conffile prompts** (`openssl.cnf`, `sources.list`) block non-interactive runs → use `--force-confold`; ABI/symbol errors → `apt full-upgrade` / `dpkg --configure -a`.
- **Samsung `am start` as the Termux app uid** is rejected (SecurityException) — route watchdog launch through the localhost:5555 privileged shell (uid 2000).
- **DHCP LAN IP changes** — use Tailscale IPs; the Mac script auto-discovers LAN via USB.
- **Reddit blocked** in Claude Code — use PullPush API (`https://api.pullpush.io/reddit/search/submission/?ids=<id>`).

---

## Repository & environment

- **Mac path:** `~/stayturgid/`. **GitHub:** `github.com/djbclark/stayturgid` (private), branch `master`, HTTPS via `gh` CLI (GitHub login = Google SSO + GitHub Mobile 2FA). AI session working dir: `~/upmon-handoff/` (legacy name).
- **Commit signing:** autonomous file key `~/.ssh/git_signing_key` (passphrase-less, GitHub-verified); `git_signing` memory has the "failed to fill whole buffer" gotcha.
- **Mac tools:** Homebrew ADB (`/opt/homebrew/bin/adb`), Python 3.14.6, pipx 1.15, uiautomator2 3.7, scrcpy 4.0. SSH key `~/.ssh/termux_key` (ed25519). `~/.ssh/config` has `s24`/`p7a` blocks **above** `Host *` with `IdentityAgent none` (first-match wins) so phone SSH doesn't trigger the 1Password dialog; git still uses 1Password.

---

## Changelog (condensed, reverse chronological — git history has full detail)

- **2026-07-07** — Fleet recovery: s24/p7a AutoJs6 `pm clear` reset → `make verify` green. **hd8** (Kindle Fire HD 8) added to fleet. Fire OS support: `stayturgid_sd_root` override, `STAYTURGID_SD` env file, dual-path device-tier checks, AutoJs6 deploy via `adb push`. Ansible taxonomy: `android_11`, `vendor_amazon`, `model_kindle_hd8`.
- **2026-07-07** — Side project: F-Droid/Neo Store + Play/Aurora support. `fdroidcl` + `gplaycli` on Mac. `ansible/roles/fdroid_repos` (module + role: repo ensure in fdroidcl, explicit `fdroidrepos://` to on-device Neo Store bypassing chooser with preference Neo>Droid-ify>F-Droid, Shizuku grant via generalized helper, setups support, client ensure). Aurora + Neo added to Obtainium catalog. `play_store` skeleton. Defensive tests on p7a/s24 (role runs, grants, installs). Docs + HANDOFF updated. (See fdroid/ and roles.)
- **2026-07-06** — Migration to Python COMPLETE (v2.0): all 5 runtime scripts deploy as Python (repair/agent-presence keep ~/*.sh shims); Mac-side fragile parsers converted (device_tier/access_monitor/adb_reconnect + shared stayturgid_device.py) with pytest; shell fragility boundary reached. Device tier → `device_tier.py`. Taxonomy inventory (no device names in code; group_vars layers all→android_16→vendor→oneui_7→model→host; device.json rendered per host). `obtainium_app` module + `obtainium_apps` role. fleet-health folded into TAP tier (`--heal`). Idempotency/determinism pass (mirror pinned, LC_ALL=C). pytest + `ansible-test units` + `stayturgid.fleet` collection. Ansible-native `fleet.yml` + `autojs6_watchdog` role. Notification self-heal (repair re-enables a11y append-only; notify coalesces per-key). Tasker fully removed (legacy exports archived). CI (GitHub Actions `make test`) green; ansible-lint/yamllint clean. Screen-awake guard + agent-presence consent protocol. sshd PerSourcePenalties lockout fixed.
- **2026-07-06** — Code review (CODE-REVIEW.md): 2 high / 11 med / 13 low, all fixed (repair helpers before flock branch; bridge liveness → pidfile; battery alarm byte-verified backup; consent gate fails closed; shizuku.json patchers abort on failed read).
- **2026-07-05** — 7a Termux ecosystem moved to GitHub/Obtainium (share-uid aligned; `termux-api` works). AutoJs6 watchdog live on S24 then rolled to 7a (`main.js` + boot relaunch + Tailscale probe + catastrophic Shizuku tap). Repair channel confirmed (localhost:5555 shell uid 2000). Shizuku reboot-survival fixed on S24 (persistent pairing). Tailscale always-on VPN enabled on both (reboot-proof). SSH hardening (`ssh s24`/`p7a`, no 1Password dialog). Mac access-monitor + battery alarm + adb-reconnect (cached→USB-LAN→mDNS-TLS→Tailscale). Ansible Termux skeleton validated.
- **earlier** — Pixel 7a: port 5555 + sshd survive cold reboots (2026-06-29). S24 initial bring-up 2026-07-01 (Shizuku SSL workaround via "Start by connecting to a computer"; runit/run-as sshd env fix; content:// URI grant limitation) — see HACKING.md Part 5b.

---

## Appendix — Architecture research: unified orchestration (RESEARCH ONLY — not approved)

> **Do not refactor yet.** The current hybrid (Mac shell + partial Ansible + on-device AutoJs6 + Obtainium scripts) is working production. This captures a proposed future consolidation for a later decision.

**Question:** could the whole system (Termux/SSH, Termux:API, ADB, uiautomator2, Shizuku, AutoJs6 deploy, Obtainium, launchd) become **one Ansible project** with everything as modules/roles/collections?

**Preliminary recommendation:** extensible **Ansible core + custom Python modules**, augmented by a small Python library for Android glue that doesn't fit YAML. Rationale: SSH-first control plane already exists; roles/collections match "everything as a module"; idempotency already validated (`changed=0`). We are already partial-Ansible — the question is how far to extend, not whether to start.

**Gap analysis (today → Ansible-native):**

| Layer | Today | Native? |
|-------|-------|---------|
| Termux packages + scripts | ✅ `termux_userland` + `termux_pkg` | Yes |
| Shizuku install/grant | Mac shell (`stayturgid_device.py`) | Partial — custom module |
| Obtainium catalog/install | `obtainium_app` module + Mac scripts | Partial |
| AutoJs6 deploy/start | `autojs6_watchdog` role + `autojs6/mac/*.sh` | Partial — role + adb delegate |
| ADB reconnect launchd | `adb-reconnect.py` + plist (mac.yml) | localhost role |
| Validation | `device_tier.py` + TAP | playbook `validate.yml` |

**Should NOT move into Ansible:** runtime watchdog logic (`stayturgid-repair`, AutoJs6 `main.js` — Ansible configures, devices self-heal); the accessibility catastrophic Shizuku tap; Obtainium in-app UI flows. **Alternatives if the Ansible boundary feels wrong:** pure-Python orchestrator (Invoke/Fabric + uiautomator2 + ppadb) for dense UI state machines; SaltStack (higher setup cost, weak DIY-phone ecosystem).

**Custom-module candidates + fault-tolerance notes:** `termux_pkg` (✅ shipped — conffile recovery via `--force-confold`, `dpkg --configure -a` on ABI break, per-package `dpkg-query` verify, mirror retry); `obtainium_app` (✅ shipped — deep-link / JSON-import; "tracked" is only fully idempotent against the git JSON catalog since Obtainium has no public state API; install needs Shizuku or privileged adb); `android_apk` (`gh release download` + `adb install -r`, parse `INSTALL_FAILED_*`); `google_play_app` (**no supported silent-install API on consumer phones without MDM** — reserve for presence checks / `market://` open only; prefer Obtainium/GitHub for everything we control).

**Non-goals a unified layer would NOT fix:** Play Protect, PIN unlock, DHCP LAN IP, Samsung Shizuku/content-URI quirks. **MDM and root were both rejected** (MDM assumes Device-Owner provisioning — wrong for daily-drivers; S24 US model has a locked bootloader → asymmetric fleet, and rooting the 7a risks Play Integrity).

**Prior art:** [termux-jenkins-automation](https://github.com/gounthar/termux-jenkins-automation) (best Termux+Ansible reference), [ansible-android-termux](https://github.com/guoqiao/ansible-android-termux), [ivansible/termux](https://galaxy.ansible.com/ui/repo/published/ivansible/termux/), [ansible#81547](https://github.com/ansible/ansible/pull/81547) (apt-on-Termux PR — won't cover conffile/stuck-dpkg); ADB: [AnsibleAndroidAutomationADB](https://github.com/shresthagrawal/AnsibleAndroidAutomationADB), [ansibel-nspanel](https://github.com/Bierchermuesli/ansibel-nspanel); Obtainium: [wiki sources](https://wiki.obtainium.page/sources/), [Dhizuku install #1611](https://github.com/ImranR98/Obtainium/issues/1611), [import #1739](https://github.com/ImranR98/Obtainium/discussions/1739).

**Next research steps (when picked up):** prototype `stayturgid_repair_check` (SSH→parse STATUS) and `android_apk`; sketch `playbooks/site.yml` composing Termux + AutoJs6 roles; write an ADR with explicit non-goals; decide collection name (`stayturgid.fleet` today vs upstream `ivansible.termux`). **Do not implement until the user explicitly approves a refactor.**

### Side project: fdroid_repos / play_store (F-Droid + Play support) — next actions (as of 2026-07-07 handoff)

**Status:** Module + role reworked and verified (2026-07-07). `make test` green (56 pytest + 20 ansible-test). **E2E:** s24 + p7a + **hd8** (Fire OS) — role idempotent, `fdroidcl install com.bobek.metronome` verified then uninstalled on each. Deploy via `./mac/deploy-fdroid.sh [host]` (dedicated playbook — intentionally omitted from `fleet.yml` so normal deploys stay fast). Neo Store must be installed via Obtainium first.

**Key files added/updated:**
- `fdroid/README.md`, `ansible/roles/fdroid_repos/{README.md,defaults,tasks,meta}`
- `ansible/roles/play_store/` (skeleton)
- `fdroid/mac/grant_neo_store_shizuku.py` (now takes optional pkg arg)
- Obtainium catalog entries for Neo Store + Aurora Store
- fleet.yml example (commented)
- HANDOFF + main README updated

**Recommended next actions (prioritized, in rough order):**
1. ~~**Verify end-to-end on s24**~~ **Done** (2026-07-07). Optional repeat on **p7a** for parity.
2. **Flesh out play_store role** symmetrically: add `stayturgid_play_apps` list, tasks using gplaycli (or fallback) to download + `adb install -i com.android.vending` (spoof Play as installer), grant for Aurora, explicit handling if Aurora has add-repo intents. Fix gplaycli (protobuf/pkg_resources issues seen; try venv or older protobuf).
3. **Enhance fdroid_repos**: full support for `stayturgid_fdroid_setups` (create/apply in role + module); support removing repos; better fingerprint handling; optional "apply to device via fdroidcl" tasks.
4. **On-device repo management polish**: if explicit intent + NeoActivity is flaky for adding repos to GUI, explore direct methods (e.g. content provider, AutoJs6 script to accept chooser, or file import into Neo Store's DB). Make preference logic also update system preferred activities if possible (without root).
5. **Integration & docs:** ~~uncomment in fleet.yml~~ **Done** — `ansible/playbooks/fdroid.yml` + `./mac/deploy-fdroid.sh`; `play_store.yml` + `./mac/deploy-play.sh`; fleet.yml points there. ~~Expand HACKING with fingerprints~~ **Done** (HACKING Part 6b).
6. **Aurora/Play catalog & client**: `deploy-play.sh p7a` grants Shizuku (verified 2026-07-07). **You:** import Aurora via Obtainium on **s24** and **hd8** (catalog pushed 2026-07-07), then `./mac/deploy-play.sh <host>`; enable Shizuku installer + auto-updates in Aurora settings.
7. ~~**hd8 (Kindle) compatibility**~~ **Done** (2026-07-07) — `deploy-fdroid.sh hd8` + metronome install via USB adb.
8. **Longer term**: decide if fdroidcl/gplaycli stay as external tools or get wrapped into custom collection modules (like termux_pkg/obtainium_app). Consider "unified app ensure" abstraction across Obtainium/F-Droid/Play.

Run with announcements (`🚨📱🚨 USING — p7a ...`) and treat devices as potentially busy. This side project is ready for use in fleet runs but still experimental — keep it gated until more real-device validation.

**Do not merge or run on production fleet without explicit approval.**
