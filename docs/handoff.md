# stayturgid — AI Handoff Document

> **Purpose:** This file is a prompt for an AI agent taking over development. Read it fully before doing anything else. It describes what the project does, the current state, the environment, the tooling rules, and what's next.
>
> **Modular docs:** each subfolder is usable on its own. Human index: [docs/README.md](README.md) · [README.md](../README.md). Full clean-install setup + device gotchas: [docs/hacking.md](hacking.md). **Operator tasks (credentials, deploy approval):** [human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md). **Open work menu:** [docs/options.md](options.md) (single list — replace + push when items close). **Current execution order and junior-agent prompt:** [Outstanding Fix Priorities](plans/outstanding-fix-priorities-2026-07-13.md). **Layout reference:** [docs/architecture.md](architecture.md). Git history has the detailed narrative of every change; this file is the condensed durable record.
>
> **Agent rules (always read on handoff):** root [`AGENTS.md`](../AGENTS.md),
> [coding-rules.md](coding-rules.md), and [`.cursor/rules/`](../.cursor/rules/).
> See [§ Cursor agent rules](#cursor-agent-rules--read-on-every-handoff) below.
>
> **2026-07-10:** Massive repo restructure on `master` (`d950c53`) — read [§ Cold-start](#-cold-start--current-state-read-this-first) before assuming any path.

---

## Cursor agent rules — read on every handoff

**Location:** [`.cursor/rules/`](../.cursor/rules/) (repo root; not under `docs/`).

These are **durable project policies** for AI agents (Cursor and handoff successors). They are short Markdown (`.mdc`) files with frontmatter `alwaysApply: true`. **Open the directory and read every rule** at session start / handoff — do not rely only on this handoff body; rules may be added or tightened without rewriting this whole document.

| File | Topic |
|------|--------|
| [`.cursor/rules/fleet-health-self-heal.mdc`](../.cursor/rules/fleet-health-self-heal.mdc) | Health fixes must also update self-heal paths (Termux / AutoJs6 / Mac monitors) — session-only heals are incomplete |
| [`.cursor/rules/screen-control-hold.mdc`](../.cursor/rules/screen-control-hold.mdc) | Keep `ScreenControlSession` held across multi-step UI work; do not open/close per tap |
| [`.cursor/rules/deploy-self-heal-catastrophic.mdc`](../.cursor/rules/deploy-self-heal-catastrophic.mdc) | Every capability must be in deploy, self-heal, **and** catastrophic recovery — no gaps |

```bash
ls .cursor/rules/          # inventory of agent rules
# then read each *.mdc — especially before fleet health or on-glass UI work
```

If you add a new always-on agent policy, put it in `.cursor/rules/` and mention it here (and in the root [README](../README.md) docs table if it is handoff-critical).

---

## Agent conventions — device preference

When testing, deploying, or verifying on **one** host and the choice does not matter,
use this order (least disruptive / best lab device first):

1. **s24** (Galaxy S24) — **preferred**
2. **hd8** (Kindle Fire HD 8) — second choice
3. **p7a** (Pixel 7a) — third choice (often a daily driver; avoid unless needed)

Use **all** hosts when the task requires fleet-wide validation. Examples:

```bash
make help                         # list common commands
make health                       # session start (agents)
make verify HOSTS=s24
make verify-drift HOSTS=s24       # Ansible-based drift check
make deploy HOSTS=s24
make deploy-check HOSTS=s24       # dry run (same as CHECK=1 make deploy)
```

Announce before live deploy when someone may be on the device:
`🚨📱🚨 USING — s24 — fleet deploy — ~5 min`

---

## Mac fleet health — **mandatory for agents**

Launchd scrapes soft health every 5 minutes. **You will not be told by a human**
when AutoJs6 stalls or a11y drifts — the Mac log is the signal.

### Session start (do this)

```bash
make health
python3 control/bin/screen_lease.py status   # cross-project glass holds (esp. p7a); see docs/modules/screen-control-lease.md
# Optional when touching VLM: make vlm-upstream-check  # RQS VLM.md best practices
# Optional when touching phone→Mac et: make check-et-mac
```

| Exit | Meaning | Your job |
|------|---------|----------|
| **0** | Clean | Continue; no need to mention unless asked |
| **1** | Soft problems | **Tell the operator in your first reply** (host + `issues=…`). Do not wait for “options”. **`SCRAPE_STALE` may mean Mac probe failure** (e.g. adb PATH), not a dead phone — read the log line |
| **2** | Log missing / no scrapes | Tell operator launchd may be down; offer `ansible-playbook ansible/playbooks/control_node/agents.yml` |

Also skim when the operator asks about fleet status, soak, OPTIONS **43–45**, or
“is anything wrong?”

### Where to look

| Path | What |
|------|------|
| `~/.config/stayturgid/logs/fleet-health.log` | Soft health (watchdog, repair, a11y, sshd, bootloop, shell5555) |
| `~/.config/stayturgid/logs/fire-help.log` | Mac→Fire Shizuku/Handsets help (`com.stayturgid.fire-help`) |
| `~/.config/stayturgid/logs/access-monitor.log` | Total outage (ADB+SSH all dead) |
| `~/.config/stayturgid/state/fleet-health/<host>` | Consecutive soft-fail count (≥2 ≈ notified) |

Agents: `com.stayturgid.fleet-health`, `com.stayturgid.access-monitor` (via
`ansible/playbooks/control_node/agents.yml`). Neo/Aurora gui-audit is **parked** (`control/bin/gui_audit.py`
remains for manual use). Disable soft probes: `STAYTURGID_SKIP_HEALTH=1`.

Mac→Android UI playbook: [docs/research/mac-android-ui-automation.md](research/mac-android-ui-automation.md).

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

**stayturgid** keeps wireless ADB (port 5555), Shizuku, and SSH alive on a
**three-device fleet** — Galaxy S24 and Pixel 7a (Android 16) plus Kindle Fire HD 8
(Fire OS) — across cold reboots, and makes them reachable from the Mac over
Tailscale via **two independent, mutually-repairing channels (ADB + SSH)**.

After a reboot and PIN unlock:
1. **Shizuku** (thedjchi fork) auto-starts via Android Wireless Debugging and uses TCP mode to call `adb tcpip 5555` — opens port 5555 without USB.
2. **Termux:Boot** fires the minimal `~/.termux/boot/start-adb.sh` compatibility
   entrypoint, which delegates immediately to Python `start_adb.py`; that supervisor
   starts `sshd` and loops self-healing every 5 min (liveness by pidfile, relaunch via `setsid`).
3. **AutoJs6** `main.js` (20 min when engine alive; boot once via `boot-launcher.js`) → notifications, Tailscale probe, catastrophic Shizuku repair. **Routine repair is Termux-only** (5-min loop); no `RunIntentActivity` from the boot loop.

On the Mac, a launchd agent runs every 60 s and reconnects `adb connect <ip>:5555` if it drops, handling DHCP IP changes automatically.

**Two-layer self-heal:** the **Termux layer (primary)** keeps the phones reachable via shell over localhost:5555 — this is what must never break. The **AutoJs6 layer (secondary)** adds detection, notifications, and the accessibility-only catastrophic fallback.

---

## How updates work

GitHub `master` is the source of truth. To release:
1. Bump `version.json` (`version` + `changelog`), commit, push.
2. `make deploy` (or `./control/bin/deploy_fleet.py`) — full fleet via `ansible/playbooks/site.yml`
   (`make deploy-check` / `CHECK=1 make deploy` = dry run): bootstrap APK verify,
   bootstrap APK ensure (version-aware over ADB), Shizuku start, preflight (SSH),
   fleet deploy (Termux, AutoJs6, Obtainium, Tailscale, privileges), post-UI,
   validate. The first three phases run over ADB (no SSH required) — they install
   prerequisite APKs and start Shizuku before SSH bootstrap. Idempotent (re-run =
   `changed=0`). Granular phases: `make bootstrap-apks`, `make verify-bootstrap-apks`,
   `make ensure-shizuku`, `make deploy-termux`.

Optional on-device notifier: `stayturgid_check_repo_version.py` (max once/24 h) fires `termux-notification` when GitHub `version.json` moves ahead of the last-seen stamp.

---

## 🚦 Cold-start — current state (read this first)

**As of 2026-07-13.** Three-device fleet: **s24**, **p7a**, **hd8**.
Source of truth: **`origin/master`** on `https://github.com/djbclark/stayturgid.git`.

### Environment

- **Mac shell:** `/bin/bash` (changed from zsh on 2026-07-12 — dotfiles in `~/.bash_profile`, `~/.bashrc`, zsh backups at `~/.zsh-backup/`)
- **Project venv (FIRERPA):** Python 3.12 at `/tmp/lamda-venv` — `source /tmp/lamda-venv/bin/activate`

### Session start (every agent)

```bash
cd ~/stayturgid && git fetch origin --prune && git status -sb
git pull --ff-only origin master   # if behind only
make health
make firerpa-health 2>/dev/null    # check FIRERPA fleet health
python3 control/bin/screen_lease.py status
# Optional: make verify-drift HOSTS=s24  # Ansible-based drift check
```

Then read [coding-rules.md](coding-rules.md), [docs/options.md](options.md), and the
[ordered outstanding-fix plan](plans/outstanding-fix-priorities-2026-07-13.md)
before selecting work. Its priority order is authoritative for reliability work;
hardware- or human-blocked items remain open while the next independent safe item
may proceed. A copy-paste prompt for a junior implementation agent is included at the
end of that plan.

### Fleet snapshot (2026-07-13 — bootstrap automation deployed)

| Host | Verify | stayturgid | Bootstrap APKs | FIRERPA | CFEngine | Notes |
|------|:------:|:----------:|:--------------:|:-------:|:--------:|-------|
| **s24** | 14/16 PASS | all green | ✅ All 7 current | ✅ v10.0 secure | ✅ 7/7 | Full deploy + AutoJs6 watchdog verified |
| **p7a** | 14/16 PASS | all green | pending | ✅ v10.0 secure | ✅ 7/7 | FIRERPA + Termux supervisor deploy verified |
| **hd8** | 13/16 PASS | offline / watchdog stale | pending | ⚠️ USB only | last ✅ 4/7 | Deferred H1/H3; aggregate `make health` remains nonzero |

**Current fix order:** H1/H3 HD8 maintenance decision → H9 foreground-screen cleanup →
B63/B64 recovery tests → F4 FIRERPA network audit/isolation → T1 `just` migration. See
[the execution plan](plans/outstanding-fix-priorities-2026-07-13.md) for gates and
rollback rules.

**Last verified 2026-07-13:** `make check` and `make test` passed (296 pytest tests,
129 local TAP checks, and all Ansible collection unit suites). `make firerpa-health`
passed; `make health` remains exit 1 only for HD8's documented stale/offline state.
There are no active screen-control leases. H8 is implemented and documented but has
not been live-clicked because the current healthy S24 does not expose a
`shizuku_down` action; use the dashboard action only when that state is present.

**Recommended next decision:** because HD8 is explicitly lower concern and USB-only,
choose intentional maintenance/offline representation for H1/H3 rather than a risky
Fire OS deployment. Do not globally suppress its warning; make the state visible and
reversible in health and the dashboard.

All three apps track `djbclark/<repo>` forks via Obtainium catalog at `catalogs/obtainium/stayturgid-apps.json`.
**Fork sources:** `~/src/AutoJs6/`, `~/src/Shizuku/`, `~/src/Obtainium/` — **read-only** for this project. If changes needed, write a prompt for the fork's AI.
**FIRERPA fork:** `~/src/firerpa-fork/` → [djbclark/lamda](https://github.com/djbclark/lamda) — binaries at [v10.0-binaries](https://github.com/djbclark/lamda/releases/tag/v10.0-binaries).

### Major changes (2026-07-12 — repair hardening, SSH CA, FIRERPA integration)

**Repair self-heal (8 commits, 7 files):**
- `ensure_sshd_down_file()` — removes stale runit `down` file that blocks sshd
- `ensure_wireless_debugging()` — skips cosmetic Samsung toggle + blocked Pixel Android 16 `settings put`
- `ensure_shell_profile_path()` — removes leaked Mac PATH from `.profile`/`.bashrc`/`.bash_profile`
- `ensure_termux_mirror()` — re-pins `packages-cf.termux.dev` after random mirror changes
- Fleet profile guard — checks `[ -f ]` before firing `APPLY_FLEET_PROFILE` intent
- Boot script: `rm -f sshd/down` before `sshd` in `start-adb.sh`

**SSH Certificate Authority:**
- CA key at `~/.ssh/stayturgid_ca` — signs all device host keys
- `@cert-authority *` in Mac + device known_hosts → zero SSH warnings
- `ca.yml` in termux_userland role — auto-signs + deploys certs
- SSH config: `StrictHostKeyChecking accept-new`, `UserKnownHostsFile ~/.ssh/known_hosts` (was `/dev/null`)
- Makefile: `ca-status`, `ca-init`, `ca-sign`

**OpenCode web:**
- Launchd KeepAlive agent: `com.stayturgid.opencode-web` on `:4096`
- Reachable from all fleet devices at `http://<ts-ip>:4096`
- Makefile: `opencode-web-status`, `--restart`, `--deploy`, `--disable`

**FIRERPA/lamda integration (spike + deploy + docs):**
- Spike confirmed on s24 + p7a: gRPC API works, ~43 MB PSS / 120 MB RSS
- Ansible role: `ansible_collections/stayturgid/firerpa/` (install/configure/service/uninstall)
- Playbook: `ansible/playbooks/fleet/firerpa.yml` (default disabled)
- gRPC heal: `control/bin/firerpa_heal.py` — repairs stayturgid via FIRERPA backup channel
- Health monitor: `control/bin/firerpa_health_monitor.py` + launchd agent (10-min)
- Boot integration: FIRERPA lifecycle in Python `start_adb.py`; it prefers localhost
  ADB and uses authorized Shizuku `rish` to restart adbd when needed (direct `rish`
  background children do not survive their binder session)
- Accessibility coexistence: hash-guarded DEX patch changes FIRERPA's
  `getUiAutomation(0)` to `FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES`; lifecycle starts
  the signed JAR for integrity validation, swaps the patch, and restarts only UI helpers
- 4 research docs: `docs/history/firerpa-*-deepseek-pro-2026-07-12.md`
- Install map: `docs/history/firerpa-install-map-2026-07-12.md`
- Upstream issue resolved: [firerpa/lamda#145](https://github.com/firerpa/lamda/issues/145) — inbound SSH works as `shell` with the service certificate
- Secure aliases: `ssh s24-firerpa` / `ssh p7a-firerpa`; gRPC and SSH use `~/.config/stayturgid/firerpa.pem`
- Known limitations: a UID-2000 bridge must exist to start FIRERPA after reboot, built-in ADB needs root, hd8 is USB-only
- Makefile: `firerpa-deploy`, `firerpa-remove`, `firerpa-heal`, `firerpa-health`
- Make sure `lamda-client` is installed in Python 3.12 venv: `source /tmp/lamda-venv/bin/activate`

**CFEngine standalone self-heal (deployed 2026-07-12):**
- Policy at `device/termux/cfengine/stayturgid.cf` — 7 check bundles: sshd, bootloop, mirror, shell5555, shizuku, a11y, profile
- Runs in the Termux boot loop via `cf-agent -D android,linux -Kf` every 5-min cycle (alongside `stayturgid_repair.py`)
- Each bundle is a read-only verify + lightweight auto-repair (sshd restart, mirror re-pin, PATH leak fix, etc.)
- Minimal standalone mode (per evaluation doc's recommendation), not a full policy-server deploy
- s24 + p7a pass all 7 checks; hd8 passes 4/7 (no Shizuku, no AutoJs6 a11y, no localhost:5555 on Fire OS)
- Ansible deploys `os-release` for CFEngine platform detection (`termux_userland` role)
- Evaluation: `docs/history/cfengine-evaluation-2026-07-12.md`

**Ansible-based verification + drift detection (deployed 2026-07-12):**
- `make verify-drift [HOSTS=s24]` — `control/bin/verify_drift.py` → `ansible/playbooks/fleet/verify-drift.yml`
- Uses `stayturgid.fleet.stayturgid_verify` module — declarative Ansible checks for device state drift
- Complements `make verify` (device-tier TAP) with Ansible-native verification
- `make deploy-check` for dry-run deploy verification (`CHECK=1 make deploy`)

**Cross-layer read-before-write guard hardening (2026-07-12):**
All self-heal layers audited for redundant `settings put` / `setprop` / `am start`
triggers that could fire every cycle when state is already correct. Fixes ensure
every write is gated on a read of the current value. Specific changes:

- `stayturgid_repair.py`: `setprop service.adb.tcp.port 5555` now checks `getprop`
first — avoids pointless adbd restart every 5 min. `accessibility_enabled 1` gated
on current value. Fleet profile re-apply gated on `shizuku != "up"`. Removed
KEYCODE_BACK dialog dismissals (replaced with read-before-write gates).
- `comonitor.js`: `restartSshd()` removes `sshd/down` file before restart (was
silently blocked if present). `probeAndRepairA11y()` has backup + shrink-recovery
(matching repair.py's `_repair_a11y_shrink`). `probeWifi()` has Samsung/Pixel
cosmetic false-positive guard. `accessibility_enabled 1` gated on current value.
- `shizuku.js`: `tryShellWirelessRepair()` reads all 3 `settings get global` +
`getprop` before each `settings put` / `setprop` (was 4 unconditional writes per
catastrophic cycle).
- `android_a11y_services.py` (Ansible module): `settings_put()` gates
`accessibility_enabled 1` on current value (matching repair.js + comonitor.js).
- `a11y_services.py` + `stayturgid_enable_autojs6.py`: `put_services()` same gate.
- `firerpa_heal.py` + `firerpa_health_monitor.py`: Shizuku detection uses `pgrep -f
shizuku_server` alongside port 5555 `ss` check (port alone is not sufficient).
- `cfengine/stayturgid.cf`: Mac PATH pattern includes `/System/Cryptexes/`
(matches repair.py + Ansible).
- `stayturgid_verify.py`: Added `wireless_debugging` check to ALL_CHECKS.
- `AGENTS.md`: Added `deploy-check`, `verify-heal`, `ca-status`, `opencode-web-status`,
`hermes-status`, `vlm-check` to key commands table.

**CFEngine server mode — Tier 4 redundancy transport (2026-07-12):**
- `cf-serverd` listens on port 5308 (TLS) for remote repair triggers via `cf-runagent`
  from the Mac. Provides a completely independent repair channel — different port,
  protocol (TLS key trust vs SSH CA), and binary from sshd/FIRERPA.
- Policy: `device/termux/cfengine/cf-serverd.cf` — IP ACL (Tailscale 100.64.0.0/10),
  access rules for 9 bundles, auto-trust on first connection
- Wrapper: `device/termux/cfengine/cf-runagent-wrapper.sh` — sets Termux PATH/LD_LIBRARY_PATH
  before invoking cf-agent with stayturgid.cf repair bundles
- Boot integration: Python `start_adb.py` starts cf-serverd after sshd (via the
  `start-adb.sh` compatibility shim), monitors
  liveness in boot loop, restarts if dead (uses `-F`: no fork for Android seccomp)
- Mac: `control/cfengine/cf-runagent.cf` — runagent policy targeting all 3 devices.
  cfengine installed via Homebrew; keys exchanged and trusted.
- Ansible: cfengine added to `stayturgid_termux_packages`; cf-serverd.cf + wrapper
  deployed via termux_userland role
- Fleet health: cf-serverd port 5308 probed in health gather (`cfengine=ok|down`);
  `cf-runagent` trigger planned for Tier 3a fallback in fleet_health_monitor.py
- Known issue: Mac cf-runagent 3.28.0 protocol negotiation with Termux cf-serverd
  3.27.1 returns "Unspecified server refusal." TLS layer + trust proven working.
  Fix: align CFEngine versions or use `cf-runagent --protocol-version 2`.

### Major changes (2026-07-13 — bootstrap APK automation + Shizuku start module)

**Bootstrap APK automation (3 new playbooks + 1 module + 1 role):**
- `android_apk` module extended with `resign`/`apksigner_bin`/`keystore`/`keystore_pass`/`key_alias` params for unsigned fork builds
- `bootstrap_apks` role: version-aware install of 7 prerequisite APKs (Termux, Termux:Boot, Termux:API, Shizuku, AutoJs6, Tailscale, Obtainium) over ADB — queries `gh release view` per APK, compares against installed versionName, installs only when stale
- `ensure-bootstrap-apks.yml`: playbook wired into `site.yml` before preflight
- `verify-bootstrap-apks.yml`: preflight check that fails early with clear list of missing/stale APKs; tested on s24
- `shizuku_start` module: starts Shizuku over ADB without device interaction — tries HEADLESS_START, falls back to native `libshizuku.so` launch; applies fleet profile, verifies port 5555
- `ensure-shizuku.yml`: playbook wired after APK ensure, before SSH bootstrap
- `check_apk.yml`: per-APK version checker with accumulator pattern
- Makefile targets: `bootstrap-apks`, `verify-bootstrap-apks`, `ensure-shizuku`
- 16 unit tests for `shizuku_start` module

**AutoJs6 versionName fix:**
- Discovered false-positive stale detection: tag `6.7.0-fleet-profile` vs versionName `6.7.0`
- Fix applied in `djbclark/AutoJs6` fork build system (appends branch qualifier to versionName)
- Verified: `aapt dump badging` shows `versionName='6.7.0-fleet-profile'` matching tag
- Installed on s24 via `make bootstrap-apks HOSTS=s24`
- Final verify: all 7 APKs current, no stale warnings

**Bug fixes:**
- `delegate_facts: true` removed from `bootstrap_apks/tasks/main.yml` and `verify-bootstrap-apks.yml` — was routing facts to localhost instead of inventory host, breaking `include_tasks` template resolution
- `include_vars` added to `verify-bootstrap-apks.yml` to load role defaults

### Major changes (2026-07-11 — fork migration + headless automation)

**Fork migration:**
- Migrated from `SuperMonster003/AutoJs6` → `djbclark/AutoJs6` (fleet profile support)
- Migrated from `thedjchi/Shizuku` → `djbclark/Shizuku` (HEADLESS_START/STOP/STATUS broadcasts)
- Added `djbclark/Obtainium` (headless import/update deep-links)
- Catalogs updated in both `stayturgid-apps.json` and Ansible role defaults
- All `filterReleaseTitlesByRegEx` cleared for future mainline switch-back

**UI automation eliminated (-1,440 lines):**
- **Shizuku**: `findOne`/`tapStartButton` replaced by `HEADLESS_START` broadcast
- **Obtainium import**: `ui_driver` + `ScreenControlSession` replaced by `obtainium://apps?confirm=true&headless=true` deep-link
- **Obtainium updates**: replaced with `obtainium://update/all?autoInstall=true&headless=true`
- **Obtainium Shizuku installer**: attempted via `FleetProfileActivity` intent (`installMethod: shizuku`) — **unresolved** (app still shows "System"); see `docs/handoff-obtainium-shizuku.md` for full debugging history
- `stayturgid_import_catalog.py` (389 lines) deleted
- `enableWirelessDebuggingUi` Samsung fallback deleted

**Headless API use:**
- `HEADLESS_START` (djbclark/Shizuku) — starts Shizuku daemon + wireless ADB, no UI
- `HEADLESS_STATUS` (djbclark/Shizuku) — returns server state; pgrep fallback on Samsung
- `FleetProfileActivity` (djbclark/AutoJs6 + djbclark/Obtainium) — SharedPreferences via intent
- `obtainium://apps` (djbclark/Obtainium) — headless catalog import with auto-confirm
- `obtainium://update` (djbclark/Obtainium) — headless update check with auto-install

**Battery alarm:** Lower brightness pulses for better visibility. Wallpaper backup optional.

**USB debugging dialog auto-dismiss:** `fleet_health_monitor.py` now auto-dismisses `UsbDebuggingActivity` and `WifiDebuggingActivity` on every 5-min health cycle.

**Self-heal loop:** `repair_fleet_profiles()` applies AutoJs6 + Shizuku profiles on every 5-min cycle.

**Fleet profile paths:** Moved to `/data/local/tmp/` (no scoped storage). `/sdcard/Download/` blocked on Android 16 without `MANAGE_EXTERNAL_STORAGE`.

**Persistent goal:** Every capability must be in deploy (Ansible), self-heal (repair.py), **and** catastrophic recovery (JS watchdog) — see `.cursor/rules/deploy-self-heal-catastrophic.mdc`.

### ⚠️ Key gotchas for next agent

**Samsung process freezer**: On s24, Samsung freezes the Shizuku Java process so `HEADLESS_STATUS` returns `result=0` even when `shizuku_server` is running. Fallback to `pgrep -f shizuku_server` is in place. After the first manual "Start" tap from the Shizuku app, HEADLESS_START works.

**Obtainium FleetProfileActivity**: Must use `getSharedPreferences("FlutterSharedPreferences", ...)` (the `flutter.` prefixed keys). DataStore DOES NOT work — the app's `SettingsProvider` uses legacy `SharedPreferences`, not `SharedPreferencesAsync`. See docs/handoff-obtainium-shizuku.md for full debugging history.

**Fire OS (hd8)**: Fire OS blocks background broadcasts. Shizuku must be started via peer bootstrap (`fire_peer_help.py`) or USB-tap, not HEADLESS_START.

**`run-as` restricted on Android 16**: Can't read app SharedPreferences files directly for debugging.

**Shizuku versioning**: Installed release10 has `versionCode=1371`. The GitHub release has `versionCode=1369`. If new releases have lower versionCode, uninstall before install.

**Obtainium self-update**: The `djbclark/Obtainium` entry uses `filterReleaseTitlesByRegEx: ""` (empty). The fork release titles don't contain "stayturgid" (unlike Shizuku which does).

**Fork builds are debug (unsigned)**: Must sign with `apksigner sign --ks ~/.android/debug.keystore` before `adb install`.
- **`make help`** + operational targets (`deploy`, `deploy-check`, `health`, `collections`, `syntax`, etc.).
- **`make health` fix:** stale access-monitor LOST for hosts currently OK no longer fails exit 1
  (`control/bin/check_fleet_health.py` + tests).
- Docs sweep: ADR 002, adoption notes, consumer template, `play_store` → `play_apps` in examples.

**Recent landings (2026-07-09):**
- Neo/Aurora **parked** from active fleet deploy, Obtainium catalog, gui-audit, and fleet-health.
- Post-UI routing: `post_ui_remote.run_with_mac_fallback` — SSH-first on s24/p7a, Mac adb on failure; hd8 Mac-only.
- On-device deterministic GUI: `device/termux/py/stayturgid_{import_catalog,enable_autojs6,screen_control,shell,grant_shizuku}.py` + `~/.stayturgid/lib/`.
- Portfolio 2 `site.yml` + thin `deploy_fleet.py`; ADR 001–002; `android_ui` + `post_ui` + `android_a11y_services`.
- Mac soft health: launchd `com.stayturgid.fleet-health` → `control/bin/fleet_health_monitor.py` + `control/lib/fleet_health.py` (watchdog/repair/a11y/sshd/bootloop); log `~/.config/stayturgid/logs/fleet-health.log`; notify after debounce.
- shell-gpt / local LLM (incubator): [docs/incubator/on-device-llm.md](incubator/on-device-llm.md) (OPTIONS **54** only if asked).
- Parked side projects: [docs/incubator/](incubator) — Inferno/Styx **do not implement**.

**Recent landings (2026-07-08):**
- AutoJs6 fleet profile (`device/autojs6/fleet_profile.json`, `enable_autojs6_shizuku.py` via FleetProfileActivity intent).
- Accessibility **detection-only** — no automatic writes. User must enable in Settings.
- PiP/overlay clearance at `ScreenControlSession` start (`control/lib/ui_clearance.py`).
- Deploy order: harden (core apps) → `enable_autojs6_shizuku` (Aurora configure parked).
- AutoJs6 fleet profile API: [issue #553](https://github.com/SuperMonster003/AutoJs6/issues/553), implemented in [djbclark/AutoJs6](https://github.com/djbclark/AutoJs6/releases).

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
- **Sideloaded Google Play:** Play Store can auto-update GMS past Fire-compatible builds → GSF/GMS crash loop. Pin via `make fix-hd8-google`; disable Play Store auto-updates. **VLM close-out** (when `make vlm-server` running): `make verify-hd8-google` or auto after `fix-hd8-google`. See [docs/research/fire-os-google-play.md](research/fire-os-google-play.md) and [docs/vlm.md](vlm.md).

**Next work:** follow
[Outstanding Fix Priorities](plans/outstanding-fix-priorities-2026-07-13.md), with
live status in [options.md](options.md). Start with the first incomplete priority; do not let Galaxy publishing,
LLM, FIRERPA MCP/WebRTC/MITM, Tasker, or `sshd -D` work displace the ordered fixes.
If validating bootstrap flow: `make verify-bootstrap-apks HOSTS=s24` →
`make bootstrap-apks HOSTS=s24` → `make ensure-shizuku HOSTS=s24` →
`make deploy-check HOSTS=s24`. Human unlocks:
[human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md).

**Deploy / test:**
- Deploy: `make deploy [HOSTS=<host>]`. Verify: `make verify HOSTS=<host>`.
- Test (no device): `make test`. First run: `make test-venv`. CI runs `make test` on push.
- All commands: `make help`.

---

## Fleet layout & file roots (single-root, self-healing) — 2026-07-07

All stayturgid files live under ONE root per filesystem (was scattered at /sdcard root, ~/ home, ~/Library/Logs):

| Filesystem | Root | Subdirs |
|-----------|------|---------|
| Device shared | `/sdcard/stayturgid/` (default) or `~/.stayturgid/shared` (Fire OS) | `autojs6/ state/ logs/ run/ tmp/` |
| Termux private | `~/.stayturgid/` | `bin/ logs/ run/ state/ battery-colors/ env` |
| Mac | `~/.config/stayturgid/` | `devices.conf logs/ state/` |

Deployed scripts → `~/.stayturgid/bin`; AutoJs6 project → `/sdcard/stayturgid/autojs6`; `watchdog.log` → `logs/`; `device.json` + `automation_mode` → `state/`; repair-bridge trigger → `run/repair_now`; pidfiles (`bootloop.pid`, bridge) → `run/`. **Self-healing:** python `makedirs(exist_ok=True)`, shell `mkdir -p`, AutoJs6 `files.ensureDir` + `config.ensureDirs()`.

⚠ **`device.json` is only re-rendered by Ansible** (`ansible/playbooks/fleet/fleet.yml`, task "Render device profile from inventory layers"). Deleting `/sdcard/stayturgid/state/` self-heals the *dir* but leaves device.json empty → AutoJs6 falls back to `device=generic` (loses tap coords). If you wipe state for a self-heal test, re-render device.json afterward (`ansible-playbook … --start-at-task="Render device profile from inventory layers" --limit <host>`).

---

## Device facts

### Google Pixel 7a (primary)
| Field | Value |
|-------|-------|
| Device / Android | Google Pixel 7a / 16 |
| USB serial | `35261JEHN12374` |
| Wireless ADB | `100.65.230.108:5555` (Tailscale, stable); LAN `192.168.68.60` (DHCP — may change; see `ansible/inventory/hosts.yml`) |
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
| Wireless ADB | `100.124.55.39:5555` (Tailscale); LAN `192.168.1.157:5555` fallback (DHCP — see `ansible/inventory/hosts.yml`) |
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
| Wireless ADB | `adb connect 100.123.218.30:5555` (Tailscale, stable) — also `192.168.68.54:5555` LAN (DHCP — see `ansible/inventory/hosts.yml`) |
| SSH | `ssh s24` (alias → Tailscale, key auth, no 1Password dialog); via USB: `adb -s RFCX219CHKA forward tcp:8022 tcp:8022 && ssh -p 8022 localhost` |
| Tailscale | `s24` = `100.123.218.30`; always-on VPN ON. "Block connections without VPN" deliberately OFF (would sever LAN ADB/mDNS on tunnel blips) |
| AutoJs6 | `org.autojs.autojs6` v6.7.0 |
| Shizuku | thedjchi fork — **survives cold reboot** (persistent wireless-debugging pairing established) |
| Termux / Obtainium | GitHub-signed stack via Obtainium; Shizuku installer enabled |
| ⚠ Power | the USB *data* cable does NOT reliably charge it — keep it on a real charger or remote access dies with the battery |

Prefer the **S24 over USB** for interactive work when plugged in; use **7a over Tailscale** otherwise. Mac scripts resolve targets via [control/lib/stayturgid_device.py](../control/lib/stayturgid_device.py) or `./control/lib/resolve_adb.py` (USB serial when present, else Tailscale/LAN).

---

## Remote-access resilience — the architecture (≥2 independent, mutually-repairing methods)

### Mac → device connection fallback chain

`fleet_health.py:resolve_path()` and `fleet_health_monitor.py:check_device()` probe in this order:

| Tier | Transport | Probe | Port |
|------|-----------|-------|------|
| **1** | **ADB** | `adb connect` LAN → Tailscale | 5555 |
| **2** | **SSH** | TCP probe (tcp_open) | 8022 |
| **3** | **FIRERPA gRPC** | TCP probe → `firerpa_heal.heal_device()` | 65000 |

If all three are down, `access-monitor` fires a Mac notification. FIRERPA heal is rate-limited (30 min cooldown per host) to prevent restart storms.

### On-device self-heal layers (independent of Mac connectivity)

| # | Layer | Cycle | Transport | Repairs |
|---|-------|-------|-----------|---------|
| 1 | **Termux boot loop** (`start_adb.py`) | 15 min | localhost:5555 privileged shell | sshd restart, mirror pin, PATH leak, fleet profiles |
| 2 | **AutoJs6 watchdog** (`main.js` + `comonitor.js`) | 20 min + boot | AutoJs6 accessibility + Termux bridge | catastrophic Shizuku repair, sshd restart, notifications |
| 3 | **CFEngine** (`cf-agent -Kf stayturgid.cf`) | 15 min (in boot loop) | local process | sshd restart, mirror re-pin, PATH leak fix (3 of 7 bundles auto-repair) |
| 4 | **Repair bridge** (`~/.stayturgid/run/repair_now`) | 15 min poll | any transport that can write files | touch trigger file → boot loop runs full repair next cycle |

CFEngine runs alongside the repair script in the same boot loop cycle — two separate tools, two separate policies, checking the same things independently. CFEngine output (`repair-cfengine.log`) is scraped by the Mac fleet health gather and reported as `cfengine=ok|down`.

### Repair channel — confirmed primitives (tested live 2026-07-05)
- **`adb -s localhost:5555 shell` from Termux = full shell uid 2000** (groups incl. `input`, `adb`, `log`). While 5555 is open, the repair layer runs `input tap` / `settings put` / `setprop` / `am` / `svc` with shell privileges — **no accessibility and no Shizuku token needed.** This is the primary repair channel. (Needs `TMPDIR=$PREFIX/tmp` or localhost:5555 checks falsely report `CLOSED_NO_SHELL`.)
- **Catastrophic case** (5555 closed AND Shizuku down): no shell reachable → only the AutoJs6 accessibility tap on Shizuku "Start", or a reboot, recovers. This is the one place accessibility automation is irreplaceable; it can't tap behind a locked screen (notification still fires; boot loop keeps retrying shell repairs). **FIRERPA gRPC heal** (`firerpa_heal.py`) provides an independent recovery path without ADB or SSH.
- **RUN_COMMAND from an adb shell is BLOCKED** ("Requires permission com.termux.permission.RUN_COMMAND"). The shell-usable trigger for repair is the **bridge**: `touch /sdcard/stayturgid/run/repair_now` (2 s poll). `run-as com.termux` works on these debuggable Termux builds as an adb-side recovery path when SSH is down (must export PATH/LD_LIBRARY_PATH/HOME/PREFIX/TMPDIR).

### Shizuku primitives (for the watchdog)
- shizuku_server runs as **`shell` uid**, has its own process watchdog (respawns on kill), and survives `am force-stop` of the manager app — very resilient.
- **START/STOP automation broadcasts REQUIRE the per-install auth token** even when sent as shell (without it → silently ignored / `auth_errors`). Token changes on reinstall → fragile; don't rely on it.
- **Proven auth-free restart (what `device/autojs6/lib/shizuku.js` does):** launch the manager MainActivity → accessibility-tap the **"Start"** button (wireless-debugging start). Needs POST_NOTIFICATIONS granted.
- On Samsung, `adb_wifi_enabled` reads 0 after boot but 5555 is open anyway — the flag is cosmetic; Shizuku opens 5555 via its own path (so the old watchdog's `Custom Setting adb_wifi_enabled=1` was a no-op). adb enable flags live in the **global** namespace, not system/secure.

### Cold-reboot behavior (both validated 2026-07-05)
After reboot + one PIN unlock, zero further intervention: Tailscale always-on tun0 comes up on unlock; sshd :8022 up (Termux:Boot); Shizuku auto-starts; Termux boot loop running. Port 5555 may lag briefly (7a: down at ~206 s, self-restored by ~338 s) then stays open. **Always-on VPN is the key that makes the tailnet leg reboot-proof — enable it on every device.**

---

## Tooling rules (follow exactly)

### Android automation tools
Use **Handsets** (`~/.handsets/hs` via `control/lib/ui_driver.py`) as the
**primary Mac** UI driver for post-UI scripts. Raw ADB (`uiautomator dump` →
parse bounds → `input tap`) is the fallback when Handsets is down and the
only path for **Termux on-device** scripts. **uiautomator2** is optional Mac
debug only — never run it alongside Handsets (exclusive UiAutomation slot).
Bench: [docs/research/handsets-vs-u2-bench.md](research/handsets-vs-u2-bench.md).
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

**Policy:** Mac UI automation must run inside `ScreenControlSession` (`control/lib/screen_control.py`). The session **locks natural portrait** (disables auto-rotate; restores prior rotation prefs on exit), runs `request-screen` (10s countdown — **timeout proceeds**; press No to deny), enables **accessibility display inversion** (inverted colors on the glass), starts torch + ongoing notification, and **refuses `adb input` if inversion is off**. On exit it **best-effort restores the foreground activity** that was showing when the session started (launchers → HOME). Project scripts must route taps through `session.shell` / `session.tap`. Raw `adb shell input` can still bypass — don't use it for automation. Missing presence script (rc 127) fails closed.

**Unlock:** if a run may need the glass (taps, dialogs, Obtainium/AutoJs6), ask the operator to **unlock the phone and leave it awake** — do not hang silently on a locked keyguard.

**Hold across short gaps:** If you will tap the same phone several times in quick succession (or a later step depends on the prior UI state), keep one session open for the whole sequence — leave inversion on during brief idle between taps. Do not open/close per step. See `.cursor/rules/screen-control-hold.mdc`.

**Inversion always on during live UI:** `STAYTURGID_SKIP_PRESENCE=1` may skip consent/torch for local debugging, but still enables display inversion and still refuses `adb input` when inversion is off. Never use skip to hide active on-glass work.

**Device guard:** boot loop runs `stayturgid_agent_presence.py guard` every 5 min — keeps inversion + notification alive while a lease is active; clears both when the lease expires.

```bash
ssh s24 '~/.stayturgid/bin/stayturgid_agent_presence.py request-screen "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/stayturgid_agent_presence.py on  "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/stayturgid_agent_presence.py off "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/stayturgid_agent_presence.py status'
# gate = consent when phone actively in use; stop-requested = graceful stop poll
```

`STAYTURGID_SKIP_PRESENCE=1` for local debugging only. Ansible now grants `POST_NOTIFICATIONS` to Termux on deploy (fixes silent `termux-notification`).

The protocol is **shared, agent-agnostic infrastructure** — do NOT fork per-agent copies. Any agent (Claude/GPT/Gemini) identifies via the 3rd arg / `STAYTURGID_AGENT`, aborts on `request-screen` exit 75, and on `stop-requested` exit 0 has ~1 min to wrap up. On device: `~/.stayturgid/bin/stayturgid_agent_presence.py` (from `device/termux/py/stayturgid_agent_presence.py`). On-device post-UI uses `stayturgid_screen_control.py` (local presence, no Mac SSH).

### Shell conventions
Never assume the default shell — macOS is zsh, **Termux has no zsh by default**. Declare bash in every shebang; run remote commands via `ssh host 'bash -s'` (stdin), never bare through the login shell. The Bash tool here runs zsh: brace `${var}` before `:`; quote whole remote command strings. `set -e` deliberately NOT used in boot/loop/runtime scripts (a boot loop must survive individual command failures).

---

## Accessibility state — verify at session start (APPEND ONLY)

`settings put secure enabled_accessibility_services <value>` **replaces** the whole list. **Fleet no longer writes accessibility settings automatically** — all auto-merge, backup, and shrink-repair was removed 2026-07-13. Accessibility is detection-only; the user must re-enable AutoJs6 in Settings > Accessibility > AutoJs6 manually. Detection still works: `settings get secure enabled_accessibility_services`, `a11y=up/down/unknown` in STATUS line, `autojs6_a11y_missing` in health tags. See docs/hacking.md Part 5 for manual instructions.

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
control/                     — Mac control node (see docs/architecture.md)
  bin/                       — deploy_fleet.py, check_fleet_health.py, monitors, a11y_services.py
  lib/                       — stayturgid_device.py, adb_cli.py, screen_control.py, fleet_health.py
  tools/{autojs6,obtainium,play,fdroid}/  — Mac deploy helpers (Ansible + operator)
  vlm/ui-tars/               — optional UI-TARS sidecar
device/
  autojs6/                   — watchdog JS (deployed to /sdcard/stayturgid/autojs6/)
  termux/                    — boot/*.sh, repair-bridge, py/*.py → ~/.stayturgid/bin/
  termux/cfengine/           — CFEngine standalone policy (stayturgid.cf, 7 check bundles)
catalogs/obtainium/          — JSON catalogs
docs/                        — handoff.md, hacking.md, options.md, modules/, adr/
ansible/
  playbooks/site.yml         — canonical fleet entry (imports fleet/* + control_node/*)
  playbooks/fleet/           — bootstrap, fleet.yml, post-ui, validate, preflight, firerpa, verify-drift
  playbooks/control_node/    — Mac prereqs, agents, vlm
  roles/control_node/        — launchd plists, devices.conf templates
ansible_collections/stayturgid/
  termux/roles/termux_userland
  fleet/roles/{autojs6_watchdog,post_ui,validate}
  firerpa/roles/firerpa
  obtainium/, fdroid/, play/, android_common/
tests/                       — device_tier.py, python/, test-*.sh TAP harness
Makefile                     — make help, deploy, health, verify, check, test
version.json                 — repo release version + changelog
```

**Deleted from repo root (do not recreate):** `mac/`, `shared/`, `termux/`, `autojs6/`,
`obtainium/`, root `*.md` operator docs (now under `docs/`).

---

## Known issues / gotchas

- **AutoJs6 parent-path API failure (H10 complete 2026-07-13):** replaced both
  unsupported `files.getParent()` calls with the shared `config.ensureParentDir()`
  helper and added missing-parent regression coverage. S24 and P7A were redeployed;
  no new `getParent` errors appeared. P7A's separate headless-Shizuku/
  `CLOSED_NO_SHELL` failures remain tracked by H12.
- **Landing discovery runtime state (H11 complete 2026-07-13):** static service
  definitions remain in `control/landing/services.json`; discovery observations and
  hidden entries now live under `~/.config/stayturgid/landing/services.json`, with
  first-use migration and atomic writes.
- **Recovered error noise (H12 complete 2026-07-13):** default fleet health keeps
  raw `errors.log` detail but groups repeated messages and labels active, recovered,
  and historical conditions. Exit status remains based on current actionable state.
- **Termux Shizuku authorization (H8 complete 2026-07-13):** the dashboard now
  offers **open Shizuku and test rish** when `shizuku_down` is actionable. It opens
  the Shizuku launcher through the device shell, then verifies
  `~/.stayturgid/bin/rish -c 'id -u'` over Termux SSH. The operator must still select
  **Allow all the time**; Android consent is never automated. A missing SSH path
  (notably HD8) is reported explicitly.
- **s24 AutoJs6 watchdog stale (resolved 2026-07-13):** after the human accessibility
  toggle, `boot-launcher.js` still spawned `main.js` with the launcher's `scripts/`
  working directory, making every `./lib/...` import fail. It now supplies the project
  directory explicitly. Clean boot and interval cycles are verified; see closed H6.
- **p7a CLOSED_NO_SHELL (2026-07-13 ~06:20–12:49, resolved):** wireless debugging
  was restored; port 5555, Shizuku, accessibility, the Python supervisor, and secure
  FIRERPA now pass live checks. Historical errors remain in the 24-hour log window;
  a brief 15:21 recurrence was the expected supervisor restart window during deploy,
  followed by green 15:25+ checks. Recovery used the normal wireless-debugging/ADB
  path. See closed OPTIONS H2.
- **Fleet-health monitor log format (2026-07-13):** The shared logging refactoring
  added severity labels (`INFO`, `ERR`) before the hostname in log lines. The
  dashboard regex and `check_fleet_health.py` now handle both old and new formats.
  Format: `TIMESTAMP  [SEVERITY] host via path: ...`
- **Dashboard/stats/landing run on Flask dev server (2026-07-13):** All three web
  UIs (dashboard :4097, stats :4097/stats, landing :8088, HTTPS :443) use Flask's
  dev server behind Caddy. Adequate for local/ Tailscale access; replace with
  gunicorn/uwsgi if external traffic grows.
- **Post-UI foreground churn (deferred):** deploy may foreground Obtainium, AutoJs6,
  Termux:API, Shizuku, or Settings and leave an arbitrary screen visible. The role now
  waits explicitly for an on/unlocked screen. Foreground restoration is OPTIONS H9;
  it is cosmetic and must not block service work.
- **Dashboard H8 implementation:** `control/bin/dashboard.py` owns
  `request_shizuku_authorization()` and `/api/shizuku/<host>`; the card action lives
  in `control/templates/_device_card.html`. Flask is an optional runtime dependency,
  so dashboard tests are skipped when it is not installed in the host test Python.
- **Post-reorg path drift (2026-07-10):** treat any `mac/`, `shared/`, root `termux/`,
  `autojs6/`, `obtainium/` reference as a bug unless it is historical (`docs/history/`),
  OPTIONS **62**, or an on-device path (`/sdcard/stayturgid/autojs6`). External
  consumers (LaunchAgents, RevengeQuickSwitcher, operator scripts outside repo) may
  still point at old paths — grep before deploy.
- **Reorg soak:** full live `make deploy HOSTS=s24` and focused p7a Termux/FIRERPA
  deploys passed on 2026-07-13. hd8 remains deliberately deferred until USB recovery
  is available.
- **make check lint tier:** `shellcheck` / `ansible-lint` / `yamllint` may still fail
  (pre-existing); tier-a syntax/pytest collection passed post-reorg.
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

- **Mac path:** `~/stayturgid/`. **GitHub:** `github.com/djbclark/stayturgid` (private), branch `master`, HTTPS via `gh` CLI (GitHub login = Google SSO + GitHub Mobile 2FA). AI session working dir: `~/stayturgid-hermes` (Hermes worktree).
- **Commit signing:** autonomous file key `~/.ssh/git_signing_key` (passphrase-less, GitHub-verified); `git_signing` memory has the "failed to fill whole buffer" gotcha.
- **Mac tools:** Homebrew ADB (`/opt/homebrew/bin/adb`), Python 3.14.6, pipx 1.15, uiautomator2 3.7, scrcpy 4.0. SSH key `~/.ssh/termux_key` (ed25519). `~/.ssh/config` has `s24`/`p7a` blocks **above** `Host *` with `IdentityAgent none` (first-match wins) so phone SSH doesn't trigger the 1Password dialog; git still uses 1Password.

---

## Changelog (condensed, reverse chronological — git history has full detail)

- **2026-07-13** — **Secure FIRERPA + accessibility coexistence:** private
  certificate auth and `shell` SSH aliases validated on s24/p7a; upstream
  `getUiAutomation(0)` patched to preserve ordinary accessibility services using a
  signed-start/patched-swap lifecycle; Termux Python supervisor can restore localhost
  adbd through authorized `rish`; full S24 deploy and focused p7a deploy passed.
  AutoJs6 child working-directory bug fixed, restoring watchdog self-heal. Post-UI
  unlock is explicit; foreground-screen cleanup deferred as OPTIONS H9.
- **2026-07-13** — **Fleet dashboard + stats + landing + HTTPS consolidation:**
  Fleet dashboard (Flask + HTMX, :4097) with device status cards, human-action-needed
  indicators, long-term stats tracking with timeframe selector, and network landing
  page (:8088). HTTPS-only reverse proxy via Caddy (mac.greyhound-sidemirror.ts.net)
  with HTTP→HTTPS redirect; all backend services bound to 127.0.0.1. Tailnet renamed
  to greyhound-sidemirror.ts.net; all old machine names purged (pixel7a-termux→p7a,
  dannys24→s24, djbclarks-macbook-air→mac, kfraswi→hd8, pixel7a-kvm→p7a-kvm).
  Auto-heal added for repair_stale (SSH restart of stuck boot loop daemon —
  fleet_health_monitor.py + CFEngine check_bootloop_repair bundle). CFEngine
  check_bootloop_repair added to stayturgid.cf and cf-serverd.cf (detects stale
  repair log >1h and restarts). Log format issue fixed (severity_label import +
  dashboard regex). S24's AutoJs6 child working-directory failure and p7a wireless
  ADB were both resolved on 2026-07-13 (OPTIONS H6/H2 closed).
- **2026-07-10** — **Repo restructure + path consistency** (`d950c53`): `control/`,
  `device/`, `catalogs/`, `docs/` layout; Ansible `control_node` role; canonical
  playbooks under `fleet/` + `control_node/`; on-device AutoJs6 path unified;
  OPTIONS **62** shim cleanup menu; pushed to GitHub. **Not fleet-soaked post-reorg.**
- **2026-07-09 night** — Ansible Track B closed: `stayturgid.fleet.validate`, `preflight.yml`, `autojs6_project_deploy`; `make help` + fleet Makefile targets; `make health` stale LOST fix; docs sweep (ADR 002, consumers, parked stores). Commits `5e2b05c`…`4aab300` on `master`.
- **2026-07-09** — Fire OS peer fallbacks F1–F5: boot keepalive (Shizuku+Handsets), Mac as last peer, launchd `com.stayturgid.fire-help`, ForceCommand `id_ed25519_peerhelp` on helpers/Mac. See `docs/research/fire-os-local-adb.md`. Neo/Aurora parked; ADR 002 + `android_ui`/`post_ui`/`android_a11y_services`; on-device post-UI + screen-control port.
- **2026-07-08** — Test/CI batch: log.js ensureDir tests, deploy_fleet/adb_cli mocked flows, in-collection `adb_resolve` units, TCP-probe gate for wireless `adb connect`, tailscale-down abort guard. docs/options.md simplified to single open-items list. hd8 verify 16/16 with Fire OS notes; p7a adb intermittently offline.
- **2026-07-07** — Fleet recovery: s24/p7a AutoJs6 `pm clear` reset → `make verify` green. **hd8** (Kindle Fire HD 8) added to fleet. Fire OS support: `stayturgid_sd_root` override, `STAYTURGID_SD` env file, dual-path device-tier checks, AutoJs6 deploy via `adb push`. Ansible taxonomy: `android_11`, `vendor_amazon`, `model_kindle_hd8`. adb auto-failover, mirror-pin fix, tailscale-down regression fix on s24.
- **2026-07-07** — F-Droid/Neo Store + Play/Aurora support added (`fdroidcl` + `gplaycli` on Mac). Later integrated into `fleet.yml` (2026-07-07). Modules/roles: repo ensure in fdroidcl, `fdroidrepos://` intents, Shizuku grant, Aurora catalog + automated setup.
- **2026-07-06** — Migration to Python COMPLETE (v2.0): all 5 runtime scripts deploy as Python (repair/agent-presence keep thin ~/ shell entrypoints); Mac-side fragile parsers converted (device_tier/access_monitor/adb_reconnect + shared stayturgid_device.py) with pytest; shell fragility boundary reached. Device tier → `device_tier.py`. Taxonomy inventory (no device names in code; group_vars layers all→android_16→vendor→oneui_7→model→host; device.json rendered per host). `obtainium_app` module + `obtainium_apps` role. fleet-health folded into TAP tier (`--heal`). Idempotency/determinism pass (mirror pinned, LC_ALL=C). pytest + `ansible-test units` + `stayturgid.fleet` collection. Ansible-native `fleet.yml` + `autojs6_watchdog` role. Notification self-heal (repair re-enables a11y append-only; notify coalesces per-key). Tasker fully removed (legacy exports archived). CI (GitHub Actions `make test`) green; ansible-lint/yamllint clean. Screen-awake guard + agent-presence consent protocol. sshd PerSourcePenalties lockout fixed.
- **2026-07-06** — Code review (CODE-REVIEW.md): 2 high / 11 med / 13 low, all fixed (repair helpers before flock branch; bridge liveness → pidfile; battery alarm byte-verified backup; consent gate fails closed; shizuku.json patchers abort on failed read).
- **2026-07-05** — 7a Termux ecosystem moved to GitHub/Obtainium (share-uid aligned; `termux-api` works). AutoJs6 watchdog live on S24 then rolled to 7a (`main.js` + boot relaunch + Tailscale probe + catastrophic Shizuku tap). Repair channel confirmed (localhost:5555 shell uid 2000). Shizuku reboot-survival fixed on S24 (persistent pairing). Tailscale always-on VPN enabled on both (reboot-proof). SSH hardening (`ssh s24`/`p7a`, no 1Password dialog). Mac access-monitor + battery alarm + adb-reconnect (cached→USB-LAN→mDNS-TLS→Tailscale). Ansible Termux skeleton validated.
- **earlier** — Pixel 7a: port 5555 + sshd survive cold reboots (2026-06-29). S24 initial bring-up 2026-07-01 (Shizuku SSL workaround via "Start by connecting to a computer"; runit/run-as sshd env fix; content:// URI grant limitation) — see docs/hacking.md Part 5b.

---

## Appendix — Strategic directions (equal weight)

> **For agents:** Ansible consolidation **shipped** for the 80/20 fleet path
> (`site.yml`, validate, preflight, post-UI modules). Remaining open work is
> operational (H5/38 Galaxy), latent reliability (43–45), or optional LLM spike
> (54) — see [docs/options.md](options.md).

The fleet runs on **Ansible-first deploy** (`make deploy` → `site.yml`) with thin
Mac wrappers for health, ADB reconnect, and screen-control UI. Directions still
valid for future investment:

| Track | Summary | Best when… |
|-------|---------|------------|
| **A — Operational** | Deploy soak, human unblockers (H5, 38) | Fleet drift or Galaxy publish wanted |
| **B — Ansible-native** | ✅ Shipped — optional Galaxy publish (38) only | — |
| **C — Hybrid polish** | Incremental module/role fixes without re-architecting | Lowest risk tweaks to existing graph |
| **D — Python orchestrator** | Replace Ansible boundary with Fabric/Invoke | Unlikely — YAML graph is working |
| **E — On-device LLM** | shell-gpt escalation after deterministic heal; see [docs/incubator/on-device-llm.md](incubator/on-device-llm.md) | Rare adaptive repair; never hot-path |

**Parked (not equal-weight):** Inferno/Styx and similar experiments live under
[docs/incubator/](incubator) — agents must not work on them unless the
operator unparks a named project.

**No track fixes:** Play Protect, PIN unlock, DHCP LAN IP, Samsung Shizuku/content-URI
quirks. **MDM and root remain rejected** (daily-driver phones; locked S24 bootloader).
**Inferno always-on / replacing AutoJs6 or SSH** is rejected for battery and
catastrophic-heal reasons ([incubator analysis](incubator/inferno-styx/analysis.md)).

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
| App privileges | ✅ `stayturgid.android_common.app_privileges` in `fleet.yml` | Yes |
| Shizuku install/grant | `shizuku_grant` module + Mac helpers | Mostly yes |
| Obtainium catalog | `obtainium_app` render + `android_ui` / `post_ui` role | Yes (render + tagged UI steps) |
| AutoJs6 deploy | `autojs6_watchdog` + `autojs6_project_deploy` (all hosts) | Yes |
| Post-deploy UI | `stayturgid.fleet.post_ui` + `android_ui` module | Yes (Aurora configure parked) |
| ADB reconnect launchd | `adb_reconnect.py` + `control_node/agents` | localhost role |
| Validation | `device_tier.py` + TAP + `stayturgid_repair_check` | `stayturgid.fleet.validate` role |

**Should NOT move into Ansible:** runtime watchdog (`stayturgid-repair`, AutoJs6
`main.js`); catastrophic accessibility Shizuku tap; Obtainium in-app state API
(nonexistent); Play silent install without MDM.

**Shipped modules (fault-tolerance):** `termux_pkg`, `termux_ssh_bootstrap`,
`termux_sshd`, `stayturgid_repair_check`, `obtainium_app`, `android_apk`,
`android_app_privileges`, fdroid/play/android_common adb modules — see
[std_modules_audit.md](ansible_collections/std_modules_audit.md).

**Prior art:** [termux-jenkins-automation](https://github.com/gounthar/termux-jenkins-automation),
[ansible-android-termux](https://github.com/guoqiao/ansible-android-termux),
[ivansible/termux](https://galaxy.ansible.com/ui/repo/published/ivansible/termux/),
[AnsibleAndroidAutomationADB](https://github.com/shresthagrawal/AnsibleAndroidAutomationADB).

**Concrete Ansible track steps:** ✅ `site.yml` shipped (`preflight` → bootstrap → fleet → post-ui → app-stores re-pass → validate);
`deploy_fleet.py` thin wrapper (collection install); ADR 001–002;
`android_ui` + `post_ui` + `android_a11y_services` + `stayturgid.fleet.validate`.
Optional: Galaxy publish when H5 creds exist.

### F-Droid + Play (wired in fleet.yml, parked by default)

**Status (2026-07-09):** Roles exist in `fleet.yml` / `site.yml` but are gated off
(`stayturgid_app_stores_enabled: false`). `./control/bin/deploy_fleet.py` / `make deploy`
run `ansible/playbooks/site.yml` (post-UI via `fleet/post-ui.yml`).

**Mac prerequisites:** `brew install fdroidcl apkeep`

**Partial re-runs:** `./control/bin/deploy_fleet.py --scope fdroid [host]` · `./control/bin/deploy_fleet.py --scope play [host]` (parked until `stayturgid_app_stores_enabled: true`)

**App stores (parked):** Neo/Aurora may remain on devices; fleet no longer installs,
configures, or health-checks them. Re-enable: [docs/modules/fdroid.md](modules/fdroid.md),
[docs/modules/play.md](modules/play.md).

Run with announcements (`🚨📱🚨 USING — s24 ...`) when someone may be on the device.
Operator-only steps (Play creds, deploy approval): [human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md).
