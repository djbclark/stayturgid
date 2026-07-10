# stayturgid — AI Handoff Document

> **Purpose:** This file is a prompt for an AI agent taking over development. Read it fully before doing anything else. It describes what the project does, the current state, the environment, the tooling rules, and what's next.
>
> **Modular docs:** each subfolder is usable on its own. Human index: [docs/README.md](docs/README.md) · [README.md](README.md). Full clean-install setup + device gotchas: [HACKING.md](HACKING.md). **Operator tasks (credentials, deploy approval):** [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). **Open work menu:** [OPTIONS.md](OPTIONS.md) (single list — replace + push when items close). Git history has the detailed narrative of every change; this file is the condensed durable record.

---

## Agent conventions — device preference

When testing, deploying, or verifying on **one** host and the choice does not matter,
use this order (least disruptive / best lab device first):

1. **s24** (Galaxy S24) — **preferred**
2. **hd8** (Kindle Fire HD 8) — second choice
3. **p7a** (Pixel 7a) — third choice (often a daily driver; avoid unless needed)

Use **all** hosts when the task requires fleet-wide validation. Examples:

```bash
make verify HOSTS=s24
./mac/deploy_fleet.py s24
CHECK=1 ./mac/deploy_fleet.py s24
```

Announce before live deploy when someone may be on the device:
`🚨📱🚨 USING — s24 — fleet deploy — ~5 min`

---

## Mac fleet health — **mandatory for agents**

Launchd scrapes soft health every 5 minutes. **You will not be told by a human**
when AutoJs6 stalls or a11y drifts — the Mac log is the signal.

### Session start (do this)

```bash
python3 mac/check_fleet_health.py
```

| Exit | Meaning | Your job |
|------|---------|----------|
| **0** | Clean | Continue; no need to mention unless asked |
| **1** | Soft problems | **Tell the operator in your first reply** (host + `issues=…`). Do not wait for “options” |
| **2** | Log missing / no scrapes | Tell operator launchd may be down; offer `ansible-playbook ansible/playbooks/mac.yml` |

Also skim when the operator asks about fleet status, soak, OPTIONS **43–45**, or
“is anything wrong?”

### Where to look

| Path | What |
|------|------|
| `~/.config/stayturgid/logs/fleet-health.log` | Soft health (watchdog, repair, a11y, sshd, bootloop, shell5555) |
| `~/.config/stayturgid/logs/gui-audit.log` | Nightly quiet Neo/Aurora GUI assertions (`com.stayturgid.gui-audit` @ 03:14) |
| `~/.config/stayturgid/logs/fire-help.log` | Mac→Fire Shizuku/Handsets help (`com.stayturgid.fire-help`) |
| `~/.config/stayturgid/logs/access-monitor.log` | Total outage (ADB+SSH all dead) |
| `~/.config/stayturgid/state/fleet-health/<host>` | Consecutive soft-fail count (≥2 ≈ notified) |
| `~/.config/stayturgid/artifacts/gui-audit/` | Dated screenshots from GUI audit |

Agents: `com.stayturgid.fleet-health`, `com.stayturgid.gui-audit`,
`com.stayturgid.access-monitor` (via `ansible/playbooks/mac.yml`). Disable soft
probes: `STAYTURGID_SKIP_HEALTH=1`. GUI audit uses `STAYTURGID_PRESENCE_QUIET=1`
(no torch/sound). Unreachable hosts are skipped, not fatal.

Mac→Android UI playbook: [docs/research/mac-android-ui-automation.md](docs/research/mac-android-ui-automation.md).

### How to talk about problems

- Lead with the triage output (hosts + issue tags).
- Prefer fixing AutoJs6 / a11y / Termux repair **before** OPTIONS **43–45**.
- Do not treat `watchdog_stale` with fresh `repair_age` as “phone dead” — it
  means the AutoJs6 layer is quiet while Termux heal still runs.

### Health fix → self-heal (mandatory)

**Every** fleet-health fix must also update self-healing code so the same
failure recovers without a manual one-shot next time. Session-only heals
(`start_watchdog.py`, kill hung PIDs, one-off a11y enable) are incomplete
until encoded in Termux boot loop, AutoJs6 co-monitor/watchdog, and/or Mac
launchd (`fleet_health_monitor` / `fire-help`). See Cursor rule
`.cursor/rules/fleet-health-self-heal.mdc`.

---

## What this project does

**stayturgid** keeps wireless ADB (port 5555), Shizuku, and SSH alive on **two personal, unrooted consumer phones** — a Google Pixel 7a and a Samsung Galaxy S24 (SM-S921U1), both Android 16 — across cold reboots, and makes them reliably reachable from the Mac over Tailscale via **two independent, mutually-repairing channels (ADB + SSH)**.

After a reboot and PIN unlock:
1. **Shizuku** (thedjchi fork) auto-starts via Android Wireless Debugging and uses TCP mode to call `adb tcpip 5555` — opens port 5555 without USB.
2. **Termux:Boot** fires `~/.termux/boot/start-adb.sh` → starts `sshd`, then loops self-healing sshd every 5 min (liveness by pidfile, relaunch via `setsid`).
3. **AutoJs6** `main.js` (20 min when engine alive; boot once via `boot-launcher.js`) → notifications, Tailscale probe, catastrophic Shizuku repair. **Routine repair is Termux-only** (5-min loop); no `RunIntentActivity` from the boot loop.

On the Mac, a launchd agent runs every 60 s and reconnects `adb connect <ip>:5555` if it drops, handling DHCP IP changes automatically.

**Two-layer self-heal:** the **Termux layer (primary)** keeps the phones reachable via shell over localhost:5555 — this is what must never break. The **AutoJs6 layer (secondary)** adds detection, notifications, and the accessibility-only catastrophic fallback.

---

## How updates work

GitHub `master` is the source of truth. To release:
1. Bump `version.json` (`version` + `changelog`), commit, push.
2. `./mac/deploy_fleet.py` — full fleet via `ansible/playbooks/site.yml`
   (`CHECK=1 ./mac/deploy_fleet.py` = dry run): bootstrap, Termux, AutoJs6,
   Obtainium, Tailscale, F-Droid/Neo Store, Play/Aurora, app privileges,
   post-UI automation, validate. Idempotent (re-run = `changed=0`). Or the
   granular path: `./ansible/mac/deploy_termux.py` then `./autojs6/mac/deploy.py`.

Optional on-device notifier: `check-repo-version.py` (max once/24 h) fires `termux-notification` when GitHub `version.json` moves ahead of the last-seen stamp.

---

## 🚦 Cold-start — current state (read this first)

**As of 2026-07-09.** Three-device fleet: **s24**, **p7a**, **hd8**.
On-device post-UI prefers SSH on s24/p7a via Termux `localhost:5555`, with
automatic Mac adb fallback if SSH-invoke fails. hd8 is Mac adb only.
Play downloads: apkeep AAS in `~/.config/stayturgid/play.env`; fleet
`stayturgid_ensure_apps` canary uses `source: play` (google-play + splits).
See [OPTIONS.md](OPTIONS.md).

**Fleet health:**

| Host | Verify | Mac adb | Notes |
|------|--------|---------|-------|
| s24 | **16/16 PASS** (post deploy soak) | USB / LAN / Tailscale | Lab reference; drawer **46** closed; Play canary installed |
| p7a | **16/16** (last run) | mDNS + Tailscale | may need Tailscale/USB when offline |
| hd8 | **16/16 PASS** (Fire OS) | **USB** + wireless | No Termux→5555; Mac adb post-UI |

**Recent landings (2026-07-09):**
- **15b:** `source: play` ensure_apps + `play_apps` split `install-multiple`; `deploy_fleet` auto-loads `play.env`.
- **H1:** `play/mac/obtain_play_aas.py` (EmbeddedSetup cookie → AAS).
- Post-UI routing: `post_ui_remote.run_with_mac_fallback` — SSH-first on s24/p7a, Mac adb on failure; hd8 Mac-only.
- On-device deterministic GUI: `termux/py/stayturgid_{import_catalog,configure_aurora,enable_autojs6,screen_control,shell,grant_shizuku}.py` + `~/.stayturgid/lib/`.
- Portfolio 2 `site.yml` + thin `deploy_fleet.py`; ADR 001.
- Mac soft health: launchd `com.stayturgid.fleet-health` → `mac/fleet_health_monitor.py` + `shared/mac/fleet_health.py` (watchdog/repair/a11y/sshd/bootloop); log `~/.config/stayturgid/logs/fleet-health.log`; notify after debounce.
- shell-gpt / local LLM (incubator): [docs/incubator/on-device-llm.md](docs/incubator/on-device-llm.md) (OPTIONS **54** only if asked).
- Parked side projects: [docs/incubator/](docs/incubator/) — Inferno/Styx **do not implement**.

**Recent landings (2026-07-08):**
- AutoJs6 fleet drawer profile (`autojs6_drawer_defaults.json`, `enable_autojs6_shizuku.py`).
- Accessibility merge-only + `mac/a11y_services.py` backup/restore (`shared/a11y_profiles.json`).
- PiP/overlay clearance at `ScreenControlSession` start (`shared/ui_clearance.py`).
- Fleet app harden before Aurora; Fire OS background-run dialog handling.
- Deploy order: harden → `configure_aurora` → `enable_autojs6_shizuku`.
- AutoJs6 upstream fleet-config request: [issue #553](https://github.com/SuperMonster003/AutoJs6/issues/553).

**Recent landings (2026-07-07):**
- Termux mirror re-pinned after `pkg update`; Fire OS localhost adb skip reports as verify note (not TODO).
- Shared `adb_resolve` auto-failover (USB → LAN → Tailscale, `adb connect`, `ro.serialno` match); TCP probe prevents hang on dead endpoints.
- `test_tailscale_down.py` aborts when adb rides the tunnel it kills; log.js `ensureDir` regression tests; deploy/adb mocked CI; in-collection `adb_resolve` unit tests.
- Battery alarm M1–M3 fixed in Python (`stayturgid_battery_alarm.py`) with `battery_suite` regression coverage.
- `request-screen` countdown 10 s; `gplaycli.py` launcher; `deploy_fleet.py` post-step failure reporting.

**Solid on all three (unchanged):** Termux self-heal (`sshd` + boot loop + repair bridge); single-root file layout with self-healing dirs; AutoJs6 hardened startup; device-tier verify via `make verify`.

**⚠ hd8 Fire OS caveats:**
- Split storage — Termux under `~/.stayturgid/shared`; AutoJs6 under `/sdcard/stayturgid/`.
- No Termux→localhost:5555 loopback — verify item 4 is an expected informational note, not a failure. Post-UI stays on Mac adb (USB or wireless).
- Mac adb: Tailscale or USB `GN43T503430603PS`; wireless failover works after one USB bootstrap.

**Next work:** [OPTIONS.md](OPTIONS.md) — open items only. Human unlocks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md).

**Deploy / test:**
- Deploy: `./mac/deploy_fleet.py`. Verify: `make verify HOSTS=<host>`.
- Test (no device): `make test`. First run: `make test-venv`. CI runs `make test` on push.

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
| Wireless ADB | `100.124.55.39:5555` (Tailscale); LAN `192.168.68.69:5555` fallback |
| SSH | `ssh hd8` (alias → Tailscale :8022, `u0_a310`, key auth); LAN: `ssh hd8-lan` |
| Termux | GitHub-debug `com.termux` 0.118.3 + api/boot (share-uid); **must** be debug build for `run-as` recovery |
| AutoJs6 | `org.autojs.autojs6` v6.7.0 — project at `/sdcard/stayturgid/autojs6` |
| Shizuku | thedjchi fork v13.7.0 — TCP mode ON |
| Fire OS notes | Termux state/logs under `~/.stayturgid/shared` (`STAYTURGID_SD` in `~/.stayturgid/env`); no Termux localhost:5555 — Handsets via peer bootstrap / keepalive (`stayturgid_peer_bootstrap`, `stayturgid_peer_keepalive`) → s24/p7a or Mac (`fire_peer_help` + launchd `com.stayturgid.fire-help`) |

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

Prefer the **S24 over USB** for interactive work when plugged in; use **7a over Tailscale** otherwise. Mac scripts resolve targets via [shared/mac/stayturgid_device.py](shared/mac/stayturgid_device.py) or `./shared/mac/resolve_adb.py` (USB serial when present, else Tailscale/LAN).

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
Use **Handsets** (`~/.handsets/hs` via `shared/mac/ui_driver.py`) as the
**primary Mac** UI driver for post-UI scripts. Raw ADB (`uiautomator dump` →
parse bounds → `input tap`) is the fallback when Handsets is down and the
only path for **Termux on-device** scripts. **uiautomator2** is optional Mac
debug only — never run it alongside Handsets (exclusive UiAutomation slot).
Bench: [docs/research/handsets-vs-u2-bench.md](docs/research/handsets-vs-u2-bench.md).
`scrcpy -s <target> --stay-awake` for live mirror. Keep awake during
automation: `adb shell svc power stayon true` (set `false` when done).
uiautomator2 in Python needs the pipx venv on `sys.path`
(`/Users/djbclark/.local/pipx/venvs/uiautomator2/lib/python3.14/site-packages`);
`uiautomator2 init` pushes u2.jar after a reboot.

### Termux packages (CRITICAL)
At the start of any Termux setup/maintenance, and **before every `pkg install`**: `pkg update && pkg upgrade -y`. The Ansible `termux_userland` role + `termux_pkg` module do this automatically (mirror pinned to `packages-cf.termux.dev` for determinism). Prefer **Obtainium/GitHub over BOTH Play Store and F-Droid**; shared-uid Termux addons must all match signature.

### Phone announcement protocol (CRITICAL)
Before any device interaction, emit a standalone message naming the phone(s): **🚨📱🚨 USING — &lt;phone(s)&gt; 🚨📱🚨**. When done and not expecting to touch them again until the next user reply: **✅📱✅ FREE — &lt;phone(s)&gt; ✅📱✅**. Announce a second phone if picked up mid-run.

### On-device presence indicator (screen control = inverted display)

**Policy:** Mac UI automation must run inside `ScreenControlSession` (`shared/mac/screen_control.py`). The session runs `request-screen` (10s countdown — **timeout proceeds**; press No to deny), enables **accessibility display inversion** (inverted colors on the glass), starts torch + ongoing notification, and **refuses `adb input` if inversion is off**. Project scripts must route taps through `session.shell` / `session.tap`. Raw `adb shell input` can still bypass — don't use it for automation. Missing presence script (rc 127) fails closed.

**Hold across short gaps:** If you will tap the same phone several times in quick succession (or a later step depends on the prior UI state), keep one session open for the whole sequence — leave inversion on during brief idle between taps. Do not open/close per step. See `.cursor/rules/screen-control-hold.mdc`.

**Inversion always on during live UI:** `STAYTURGID_SKIP_PRESENCE=1` may skip consent/torch for local debugging, but still enables display inversion and still refuses `adb input` when inversion is off. Never use skip to hide active on-glass work.

**Device guard:** boot loop runs `agent-presence.sh guard` every 5 min — keeps inversion + notification alive while a lease is active; clears both when the lease expires.

```bash
ssh s24 '~/.stayturgid/bin/agent-presence.sh request-screen "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/agent-presence.sh on  "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/agent-presence.sh off "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/agent-presence.sh status'
# gate = consent when phone actively in use; stop-requested = graceful stop poll
```

`STAYTURGID_SKIP_PRESENCE=1` for local debugging only. Ansible now grants `POST_NOTIFICATIONS` to Termux on deploy (fixes silent `termux-notification`).

The protocol is **shared, agent-agnostic infrastructure** — do NOT fork per-agent copies. Any agent (Claude/GPT/Gemini) identifies via the 3rd arg / `STAYTURGID_AGENT`, aborts on `request-screen` exit 75, and on `stop-requested` exit 0 has ~1 min to wrap up. Script: `termux/claude-presence.sh` (repo) → `~/.stayturgid/bin/agent-presence.sh` (device); `claude-presence.sh` is a compat shim in the same bin dir. On-device post-UI uses `stayturgid_screen_control.py` (local presence, no Mac SSH).

### Shell conventions
Never assume the default shell — macOS is zsh, **Termux has no zsh by default**. Declare bash in every shebang; run remote commands via `ssh host 'bash -s'` (stdin), never bare through the login shell. The Bash tool here runs zsh: brace `${var}` before `:`; quote whole remote command strings. `set -e` deliberately NOT used in boot/loop/runtime scripts (a boot loop must survive individual command failures).

---

## Accessibility state — verify at session start (APPEND ONLY)

`settings put secure enabled_accessibility_services <value>` **replaces** the whole list — running it with one service silently wipes every other a11y service. Fleet setup uses **merge-only** writes (`mac/a11y_services.py`, `enable_autojs6_shizuku.py` shell path). **Do not** use the AutoJs6 drawer accessibility toggle — it replaces the list. Backup/restore: `shared/a11y_profiles.json`, `python3 mac/a11y_services.py backup|restore <host>`. See HACKING.md Part 5.

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
  mac/                       — deploy.py, setup_autojs6.py, start_watchdog.py, grant_shizuku.py, run_test.py
termux/
  boot/start-adb.sh          — Termux:Boot entry: sshd + 5-min self-heal loop (pidfile) + battery alarm + autojs6 guard (no am start)
  py/*.py + *.sh shims       — repair, agent-presence, screen-awake-guard, battery-alarm, check-repo-version
                               (Python is DEPLOYED; agent-presence + repair keep a thin ~/*.sh compat shim)
  repair-bridge.sh           — 2 s poll of run/repair_now (RUN_COMMAND-free trigger)
ansible/                     — fleet deploy; inventory/hosts.yml + inventory/group_vars taxonomy layers
  playbooks/fleet.yml, mac.yml   roles: termux_userland, autojs6_watchdog, obtainium_apps
ansible_collections/stayturgid/fleet/   — termux_pkg + obtainium_app modules (FQCN stayturgid.fleet.*)
obtainium/                   — stayturgid-apps.json catalog + mac/ sync/import/apply/installer scripts
fdroid/                      — F-Droid / Neo Store docs + Mac helpers
play/                        — Play / Aurora docs + configure_aurora.py
ansible_collections/stayturgid/fdroid/roles/fdroid_repos/  — fdroidcl repo management + on-device push
ansible_collections/stayturgid/play/roles/play_store/        — Aurora Store Shizuku grant + play_apps
shared/mac/                  — stayturgid_device.py, resolve_adb.py, adb_cli.py (Shizuku JSON patcher + UI parsing)
mac/                         — adb_reconnect.py, access_monitor.py, deploy_fleet.py (launchd via ansible mac.yml)
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

- **2026-07-09** — Fire OS peer fallbacks F1–F5: boot keepalive (Shizuku+Handsets), Mac as last peer, launchd `com.stayturgid.fire-help`, ForceCommand `id_ed25519_peerhelp` on helpers/Mac. See `docs/research/fire-os-local-adb.md`.
- **2026-07-08** — Test/CI batch: log.js ensureDir tests, deploy_fleet/adb_cli mocked flows, in-collection `adb_resolve` units, TCP-probe gate for wireless `adb connect`, tailscale-down abort guard. OPTIONS.md simplified to single open-items list. hd8 verify 16/16 with Fire OS notes; p7a adb intermittently offline.
- **2026-07-07** — Fleet recovery: s24/p7a AutoJs6 `pm clear` reset → `make verify` green. **hd8** (Kindle Fire HD 8) added to fleet. Fire OS support: `stayturgid_sd_root` override, `STAYTURGID_SD` env file, dual-path device-tier checks, AutoJs6 deploy via `adb push`. Ansible taxonomy: `android_11`, `vendor_amazon`, `model_kindle_hd8`. adb auto-failover, mirror-pin fix, tailscale-down regression fix on s24.
- **2026-07-07** — F-Droid/Neo Store + Play/Aurora support added (`fdroidcl` + `gplaycli` on Mac). Later integrated into `fleet.yml` (2026-07-07). Modules/roles: repo ensure in fdroidcl, `fdroidrepos://` intents, Shizuku grant, Aurora catalog + automated setup.
- **2026-07-06** — Migration to Python COMPLETE (v2.0): all 5 runtime scripts deploy as Python (repair/agent-presence keep ~/*.sh shims); Mac-side fragile parsers converted (device_tier/access_monitor/adb_reconnect + shared stayturgid_device.py) with pytest; shell fragility boundary reached. Device tier → `device_tier.py`. Taxonomy inventory (no device names in code; group_vars layers all→android_16→vendor→oneui_7→model→host; device.json rendered per host). `obtainium_app` module + `obtainium_apps` role. fleet-health folded into TAP tier (`--heal`). Idempotency/determinism pass (mirror pinned, LC_ALL=C). pytest + `ansible-test units` + `stayturgid.fleet` collection. Ansible-native `fleet.yml` + `autojs6_watchdog` role. Notification self-heal (repair re-enables a11y append-only; notify coalesces per-key). Tasker fully removed (legacy exports archived). CI (GitHub Actions `make test`) green; ansible-lint/yamllint clean. Screen-awake guard + agent-presence consent protocol. sshd PerSourcePenalties lockout fixed.
- **2026-07-06** — Code review (CODE-REVIEW.md): 2 high / 11 med / 13 low, all fixed (repair helpers before flock branch; bridge liveness → pidfile; battery alarm byte-verified backup; consent gate fails closed; shizuku.json patchers abort on failed read).
- **2026-07-05** — 7a Termux ecosystem moved to GitHub/Obtainium (share-uid aligned; `termux-api` works). AutoJs6 watchdog live on S24 then rolled to 7a (`main.js` + boot relaunch + Tailscale probe + catastrophic Shizuku tap). Repair channel confirmed (localhost:5555 shell uid 2000). Shizuku reboot-survival fixed on S24 (persistent pairing). Tailscale always-on VPN enabled on both (reboot-proof). SSH hardening (`ssh s24`/`p7a`, no 1Password dialog). Mac access-monitor + battery alarm + adb-reconnect (cached→USB-LAN→mDNS-TLS→Tailscale). Ansible Termux skeleton validated.
- **earlier** — Pixel 7a: port 5555 + sshd survive cold reboots (2026-06-29). S24 initial bring-up 2026-07-01 (Shizuku SSL workaround via "Start by connecting to a computer"; runit/run-as sshd env fix; content:// URI grant limitation) — see HACKING.md Part 5b.

---

## Appendix — Strategic directions (equal weight)

> **For agents:** Ansible consolidation is a **first-class option**, not a
> deferred research item. Compare it alongside operational work, reliability
> hardening, and staying on the current hybrid. Pick based on operator priority
> and fleet risk — see [OPTIONS.md](OPTIONS.md) for the open menu.

The current hybrid (Mac Python + partial Ansible + on-device AutoJs6 +
Obtainium UI scripts) is **working production**. Three directions are all valid
next investments:

| Track | Summary | Best when… |
|-------|---------|------------|
| **A — Operational** | Deploy, verify, human unblockers (H1–H3, item 46) | Fleet drift or untested landings need a live soak |
| **B — Ansible-native** | `site.yml` composition, more modules/roles, thin `deploy_fleet.py` | You want one idempotent graph, Galaxy-ready collections, less orchestration scatter |
| **C — Hybrid polish** | Keep `deploy_fleet.py` orchestrator; dedupe scripts, fix ordering, incremental modules only | Lowest risk; Ansible grows only where pain is acute |
| **D — Python orchestrator** | Replace Ansible boundary with Fabric/Invoke + shared `adb_cli` / `screen_control` | UI-heavy flows dominate and YAML becomes friction |
| **E — On-device LLM** | shell-gpt escalation after deterministic heal; see [docs/incubator/on-device-llm.md](docs/incubator/on-device-llm.md) | Rare adaptive repair; never hot-path |

**Parked (not equal-weight):** Inferno/Styx and similar experiments live under
[docs/incubator/](docs/incubator/) — agents must not work on them unless the
operator unparks a named project.

**No track fixes:** Play Protect, PIN unlock, DHCP LAN IP, Samsung Shizuku/content-URI
quirks. **MDM and root remain rejected** (daily-driver phones; locked S24 bootloader).
**Inferno always-on / replacing AutoJs6 or SSH** is rejected for battery and
catastrophic-heal reasons ([incubator analysis](docs/incubator/inferno-styx/analysis.md)).

### Track B — Ansible-native (detailed)

**Question:** how much of Termux/SSH, ADB, Shizuku grants, app stores, Obtainium
catalog render, Mac launchd, and post-deploy validation can become **one Ansible
project** (modules + roles + composed playbooks)?

**Target shape (~80/20):** declarative Ansible for fleet state; screen-control
Python scripts invoked from tagged playbook steps for Obtainium import, Aurora
first-run, AutoJs6 drawer — not fake “modules” for UI taps.

**Gap analysis (today → Ansible-native):**

| Layer | Today | Ansible-native? |
|-------|-------|-----------------|
| Pre-SSH bootstrap | ✅ `termux_ssh_bootstrap` + `bootstrap.yml` | Yes |
| Termux packages + scripts | ✅ `termux_userland` + `termux_pkg` | Yes |
| SSH mesh (steady state) | ✅ `authorized_key` + `known_hosts` in role | Yes |
| App privileges | ✅ `app_privileges` role in `fleet.yml` (before post-UI Aurora) | Yes |
| Shizuku install/grant | `shizuku_grant` module + Mac helpers | Mostly yes |
| Obtainium catalog | `obtainium_app` render + `import_catalog.py` UI | Split (render yes, import script) |
| AutoJs6 deploy | `autojs6_watchdog` role + `autojs6/mac/*.py` | Partial |
| Post-deploy UI | `configure_aurora.py`, `enable_autojs6_shizuku.py` | Tagged `script:` steps |
| ADB reconnect launchd | `adb_reconnect.py` + `mac.yml` | localhost role |
| Validation | `device_tier.py` + TAP + `stayturgid_repair_check` | `validate.yml` playbook |

**Should NOT move into Ansible:** runtime watchdog (`stayturgid-repair`, AutoJs6
`main.js`); catastrophic accessibility Shizuku tap; Obtainium in-app state API
(nonexistent); Play silent install without MDM.

**Shipped modules (fault-tolerance):** `termux_pkg`, `termux_ssh_bootstrap`,
`termux_sshd`, `stayturgid_repair_check`, `obtainium_app`, `android_apk`,
`android_app_privileges`, fdroid/play/android_common adb modules — see
[std_modules_audit.md](ansible_collections/docs/std_modules_audit.md).

**Prior art:** [termux-jenkins-automation](https://github.com/gounthar/termux-jenkins-automation),
[ansible-android-termux](https://github.com/guoqiao/ansible-android-termux),
[ivansible/termux](https://galaxy.ansible.com/ui/repo/published/ivansible/termux/),
[AnsibleAndroidAutomationADB](https://github.com/shresthagrawal/AnsibleAndroidAutomationADB).

**Concrete Ansible track steps:** ✅ `site.yml` shipped; `deploy_fleet.py` thin wrapper;
`validate.yml` + ADR 001. Optional: Galaxy publish when H5 creds exist.

### F-Droid + Play (integrated in fleet.yml)

**Status (2026-07-09):** Integrated in `fleet.yml` / `site.yml`. `./mac/deploy_fleet.py`
runs `ansible-playbooks/site.yml` (post-UI scripts orchestrated in `post-ui.yml`).

**Mac prerequisites:** `brew install fdroidcl apkeep`

**Partial re-runs:** `./mac/deploy_fleet.py --scope fdroid [host]` · `./mac/deploy_fleet.py --scope play [host]`

**Human steps (one-time per device):** Neo Store Shizuku installer + auto-updates; Play creds for google-play downloads — see [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md).

**Verified E2E:** s24 + p7a + hd8 — fdroidcl install/uninstall metronome; Aurora automated setup on all three.

Run with announcements (`🚨📱🚨 USING — s24 ...`) when someone may be on the device.
Operator-only steps (Play creds, deploy approval): [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md).
