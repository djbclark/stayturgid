<!-- historical: full bodies of options.md entries that were closed/shipped/done as of the 2026-07-23 docs consolidation. options.md keeps a one-line pointer per ID; this file has the original detail. Real IPs already genericized in the source (example fleet aliases only). -->

# OPTIONS — archived closed/shipped entries (as of 2026-07-23)

Moved out of `docs/options.md` to keep that file scannable. IDs are stable —
if any of these need to be reopened, add a fresh entry back in options.md
under the same ID rather than editing history here.

## Track B — Ansible-native

### ~~60 — Expand Ansible validate + a11y in deploy (agent)~~ · Closed 2026-07-09

`stayturgid.fleet.validate` (repair/sshd/a11y asserts + optional a11y drift merge);
`preflight.yml` replaces `deploy_fleet.py` SSH preflight.

### ~~61 — autojs6_project_deploy module (agent)~~ · Closed 2026-07-09

`stayturgid.android_common.autojs6_project_deploy` + shared util; wired in
`autojs6_watchdog` for Fire adb path; `control/tools/autojs6/deploy.py` thin wrapper retained.

### ~~62 — Remove legacy path aliases and shim-only layout (agent)~~ · Closed 2026-07-10

Removed flat `ansible/playbooks/*.yml` shims (keep `site.yml` + `fleet/` +
`control_node/`). Termux callers use `stayturgid_repair.py` /
`stayturgid_agent_presence.py` (shell shims deleted; retired list cleans devices).
`gplaycli.sh` removed; `stayturgid_root.py` legacy markers dropped.

## Track A — Operational

### ~~H14 — Build & deploy AutoJs6 sticky-a11y rebind APK~~ · Done 2026-07-19 · Cross-ref: A11

AutoJs6#1 merged; fleet debug17 arm64 installed on s24/p7a/hd8 (LeakCanary
disabled). GitHub release asset upload may still be flaky (503).

## Track D — Reliability

### ~~A11 — Sticky AutoJs6 a11y detect + notify~~ · Merged 2026-07-19 · stayturgid#29

Shipped on master (`199ea20`). Companion AutoJs6#1 + fleet debug APK builds 16–17
(LeakCanary off on 17). Note: this predates the K1 native-agent cutover
(2026-07-22) that retired the AutoJs6 watchdog fleet-wide — the sticky-a11y
detect/notify path it shipped no longer runs.

## Track T — Tooling

### T1 — Make `just` the primary operator interface · Shipped 2026-07-13

Replaced most of the 494-line, 79-target command-runner Makefile with a root
`justfile` (3 imported recipe groups, 84 discoverable recipes via
`just --list`). GNU Makefile retired; `make` targets preserved as
compatibility wrappers for CI and operator muscle memory. Plan:
[just-migration-plan.md](plans/just-migration-plan.md).

### T3 — Consolidate host identity into one source of truth · Shipped 2026-07-18 (relay step B5)

Remaining gaps tracked in `~/ops/site-djbclark/docs/relay/reviews/` (Phase B
review findings), not here. Research:
[site-identity-source-of-truth-2026-07-14.md](../research/site-identity-source-of-truth-2026-07-14.md).

## Track G — Python migration & logging (fully completed 2026-07-13)

Shell → Python migration of `start-adb.sh`, `autojs6-bridge.sh`,
`repair-bridge.sh`, `ui_tars_env.sh`, `vlm_migrate_paths.sh`. All old shell
files deleted, Ansible retired lists updated. Unified syslog logging
(`control/lib/logging.py`) with severity levels, 30-day age-based rotation,
and remote error scraping. `/errors` route on fleet dashboard.

- **G1** — Healing coverage registry + pre-flight checker. `tests/healing_registry.json`
  (SSOT of desired states); `tests/check_healing_coverage.py` runs in `just test`.
- **G2** — Shell → Python migration (bridges, boot supervisor, VLM).
- **G3** — Remove automatic accessibility repair. Detection-only, human-gated.
- **G4** — Unified syslog logging + rotation + error scraping.

## Track H — Post-migration cleanup (closed items)

### ~~H2 — stock-android-device port 5555 restored~~ · Closed 2026-07-13

Port 5555, the shell bridge, Shizuku, and accessibility checks are all healthy.

### ~~H4 — ruff + uv tooling~~ · Closed 2026-07-14

`pyproject.toml` at project root with ruff config; `just ruff`/`just lint`/`just check`
all include ruff; `just test-venv` uses `uv`.

### ~~H5 — pre-commit + typos tooling~~ · Closed 2026-07-14

`.pre-commit-config.yaml` runs ruff, typos, shellcheck, yamllint, project Ansible
lint. `.typos.toml` carries approved project vocabulary. Hooks installed via
`pre-commit install`.

(Note: the ID **H5** is reused — see the open Track A entry "H5 — Galaxy
publish API token" in options.md, a different item with the same ID.)

### ~~H6 — oneui-device AutoJs6 watchdog stale (Android 16)~~ · Closed 2026-07-13

Fixed a `boot-launcher.js` working-directory bug that broke every
`require("./lib/...")` in the spawned `main.js`. Accessibility enablement
remains a deliberate human action.

### ~~H7 — Authorize Termux `rish` bridge~~ · Closed 2026-07-13

Fixed via **Allow all the time** in Shizuku's Termux authorization prompt on
both phones; `~/.stayturgid/bin/rish -c 'id -u'` returns UID 2000.

### ~~H8 — Dashboard Shizuku authorization action~~ · Complete 2026-07-13

Dashboard marks `shizuku_down` actionable with an "open Shizuku and test rish"
button.

### ~~H10 — Fix unsupported AutoJs6 parent-path calls~~ · Complete 2026-07-13

Replaced unsupported `files.getParent()` calls with `config.ensureParentDir()`;
deployed to S24 and P7A.

### ~~H11 — Move landing discovery runtime state out of Git~~ · Complete 2026-07-13

Static definitions in tracked `control/landing/services.json`; runtime state in
`~/.config/stayturgid/landing/services.json`.

### ~~H12 — Summarize recovered errors in default fleet health~~ · Complete 2026-07-13

`control/bin/check_fleet_health.py` groups repeated messages and separates
active/recovered/historical conditions.

### ~~H13 — Centralized UI Automation Gating~~ · Complete 2026-07-14

UI automation gated by default unless `STAYTURGID_ALLOW_UI_AUTOMATION=1`;
web dashboard shows interactive warning cards with a "Done / Resume" button.

## Track F — FIRERPA (closed items)

### ~~F2 — WebRTC remote desktop test~~ · Closed 2026-07-14

FIRERPA WebUI spike confirmed working (shell, screen mirroring, WebRTC
H.264). Config reverted to failsafe (WebRTC off). Kept documented, dormant.

### ~~F4 — Network isolation~~ · Abandoned 2026-07-22

The FIRERPA core `lamda` engine was validated as a legitimate, open-source
automation framework; the prior "untrusted black box needing strict outbound
ACLs" assumption was dropped in favor of its built-in auth + standard
SSH/Tailscale hygiene.

## Trailing closed-ledger (batch closures, 2026-07-08 through 2026-07-14)

**Closed (2026-07-14):** F2 (FIRERPA WebRTC spike, confirmed working).
**Closed (2026-07-09 night):** 60–61 validate role + preflight +
`autojs6_project_deploy`; `just --list`/Makefile ops; `just health` stale LOST
fix; docs sweep. 58–59 ADR 002 + `android_ui` / `post_ui` /
`android_a11y_services`. Neo/Aurora parked.
**Closed (2026-07-09 evening):** Aurora CPU thrash policy documented;
screen-control hold rule.
**Closed (2026-07-09):** 15b, H1, H3, 56, 46, 55, 27, 57, Portfolio 2 48–52/53,
co-monitor + Mac AutoJs6 heal, Fire F1–F5, self-heal agent rule. (Note: these
H1/H3 IDs are from the 2026-07-09 ledger and are a different scope than the
still-open Track H H1/H3 items in options.md — fireos-device deployment.)
**Closed (2026-07-08):** drawer profile, a11y, PiP, Aurora order, #553.
**Shipped (2026-07-13):** bootstrap APK automation (version-aware install +
verify + Shizuku start, 7 APKs); `android_apk` resign param; AutoJs6
versionName fix; `shizuku_start` module (16 unit tests); T1 just migration
(root justfile + 3 recipe groups, 84 discoverable recipes, Makefile retired).
